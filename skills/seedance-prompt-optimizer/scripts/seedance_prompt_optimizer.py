#!/usr/bin/env python3
"""基于规则的 Seedance 2.0 提示词检查与优化器。

实现仅使用 Python 标准库，便于复制到 Codex 技能中运行。
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


TASKS = ("auto", "reference", "edit", "extend", "combo")
OUTPUT_FORMATS = ("text", "markdown", "json")
MEDIA_ANALYSIS_FORMATS = ("auto", "json", "markdown")
MEDIA_PROVIDERS = ("ark",)
DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
DEFAULT_ARK_MODEL = "ep-20260506192525-qtw9h"
DIRECT_UPLOAD_LIMIT_BYTES = 18 * 1024 * 1024

VAGUE_WORDS = ("氛围感", "电影感", "好看点", "高级感", "大片感", "质感拉满")
VAGUE_REPLACEMENTS = {
    "氛围感": "具体环境氛围、光影与色调",
    "电影感": "明确景别、运镜、光影层次与色彩风格",
    "好看点": "具备明确构图、主体动作和光影设计",
    "高级感": "克制色彩、材质细节和清晰构图",
    "大片感": "大景别构图、明确光源和稳定运镜",
    "质感拉满": "材质、光影和细节清晰",
}
INEFFECTIVE_QUALITY_PATTERNS = (
    r"\b4K\b",
    r"\b8K\b",
    r"\b60\s*fps\b",
    r"\bHDR\b",
    r"高帧率",
    r"超高分辨率",
)
SHOT_RE = re.compile(r"(?:^|[\n。；;])\s*(?:【?\s*(?:镜头|场景)\s*[0-9一二三四五六七八九十]+|镜头[:：])", re.I)
MEDIA_PATTERNS = {
    "image": re.compile(r"@?(?:图片|图)\s*([0-9]+)"),
    "video": re.compile(r"@?视频\s*([0-9]+)"),
    "audio": re.compile(r"@?音频\s*([0-9]+)"),
}
MEDIA_LABELS = {
    "image": "图片",
    "video": "视频",
    "audio": "音频",
}
MEDIA_ANALYSIS_KEYS = {
    "images": "image",
    "image": "image",
    "图片": "image",
    "图": "image",
    "videos": "video",
    "video": "video",
    "视频": "video",
    "audios": "audio",
    "audio": "audio",
    "音频": "audio",
}
MARKDOWN_FIELD_KEYS = {
    "职责": "role",
    "摘要": "summary",
    "主体": "subjects",
    "场景": "scene",
    "风格": "style",
    "首帧": "start_frame",
    "尾帧": "end_frame",
    "运镜": "motion",
    "动作": "actions",
    "音色": "voice",
    "情绪": "emotion",
    "节奏": "rhythm",
    "约束": "constraints",
}
CHINESE_NUMERALS = "一二三四五六七八九十"
CAMERA_MOTION_PATTERNS = {
    "推镜": re.compile(r"推镜|推进|向前推|镜头推近"),
    "拉镜": re.compile(r"拉镜|拉远|向后拉|镜头拉开"),
    "摇镜": re.compile(r"摇镜|摇移|左右摇|上下摇"),
    "移镜": re.compile(r"横移|平移|向左移|向右移|跟移"),
    "环绕": re.compile(r"环绕|绕行|绕拍"),
    "固定": re.compile(r"固定机位|固定镜头|静止镜头"),
}
GRID_IMAGE_RE = re.compile(r"九宫格|宫格|拼图|长图|多视图|三视图|四视图|拼接图")


@dataclass
class Diagnostic:
    code: str
    severity: str
    message: str


@dataclass
class MediaItem:
    kind: str
    media_id: int
    role: str = ""
    summary: str = ""
    subjects: list[str] | None = None
    scene: str = ""
    style: str = ""
    constraints: list[str] | None = None
    start_frame: str = ""
    end_frame: str = ""
    motion: str = ""
    actions: list[str] | None = None
    timing: str = ""
    audio: str = ""
    voice: str = ""
    emotion: str = ""
    rhythm: str = ""


@dataclass
class MediaAnalysis:
    items: dict[tuple[str, int], MediaItem]

    def get(self, kind: str, media_id: int) -> MediaItem | None:
        return self.items.get((kind, media_id))

    def ids(self, kind: str) -> list[int]:
        return sorted(media_id for item_kind, media_id in self.items if item_kind == kind)


@dataclass
class ContentAsset:
    kind: str
    media_id: int
    source: str
    role: str = ""


@dataclass
class ContentAssetMapping:
    text: str
    assets: list[ContentAsset]


@dataclass
class MediaInput:
    kind: str
    media_id: int
    path: Path


@dataclass
class Analysis:
    task_type: str
    diagnostics: list[Diagnostic]
    media: dict[str, list[int]]
    applied_rules: list[str]
    normalized_prompt: str
    media_analysis: MediaAnalysis
    content_mapping: ContentAssetMapping | None = None


def read_prompt(path: str | None) -> str:
    if path and path != "-":
        return Path(path).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        raise SystemExit("除非通过标准输入传入提示词，否则必须提供 --input")
    return sys.stdin.read()


def write_output(path: str | None, content: str) -> None:
    if path:
        Path(path).write_text(content, encoding="utf-8")
        print(f"已写入 {path}")
    else:
        print(content)


def read_media_analysis(path: str | None, fmt: str) -> MediaAnalysis:
    if not path:
        return MediaAnalysis({})
    if path == "-":
        content = sys.stdin.read()
        source = ""
    else:
        source_path = Path(path)
        content = source_path.read_text(encoding="utf-8")
        source = source_path.suffix.lower()
    return parse_media_analysis(content, fmt, source)


def parse_media_analysis(content: str, fmt: str, source_suffix: str = "") -> MediaAnalysis:
    content = content.strip()
    if not content:
        return MediaAnalysis({})
    if fmt == "auto":
        if source_suffix in {".md", ".markdown"}:
            fmt = "markdown"
        elif source_suffix == ".json" or content[0] in "[{":
            fmt = "json"
        else:
            fmt = "markdown"
    if fmt == "json":
        return parse_json_media_analysis(content)
    if fmt == "markdown":
        return parse_markdown_media_analysis(content)
    raise SystemExit(f"不支持的素材理解摘要格式：{fmt}")


def parse_json_media_analysis(content: str) -> MediaAnalysis:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"素材理解摘要 JSON 解析失败：{exc}") from exc

    items: dict[tuple[str, int], MediaItem] = {}
    if isinstance(payload, list):
        containers = {"items": payload}
    elif isinstance(payload, dict):
        containers = payload
    else:
        raise SystemExit("素材理解摘要 JSON 顶层必须是对象或数组。")

    for key, value in containers.items():
        normalized_key = MEDIA_ANALYSIS_KEYS.get(str(key).strip(), "")
        if normalized_key and isinstance(value, dict):
            for media_id, raw_item in value.items():
                item = media_item_from_mapping(normalized_key, media_id, raw_item)
                items[(item.kind, item.media_id)] = item
        elif str(key).strip() == "items" and isinstance(value, list):
            for raw_item in value:
                if not isinstance(raw_item, dict):
                    continue
                kind = normalize_media_kind(str(raw_item.get("kind") or raw_item.get("type") or raw_item.get("media_type") or ""))
                media_id = raw_item.get("id") or raw_item.get("media_id") or raw_item.get("index")
                if kind and media_id is not None:
                    item = media_item_from_mapping(kind, media_id, raw_item)
                    items[(item.kind, item.media_id)] = item
    return MediaAnalysis(items)


def parse_markdown_media_analysis(content: str) -> MediaAnalysis:
    items: dict[tuple[str, int], MediaItem] = {}
    header_re = re.compile(r"^#{1,4}\s*(图片|图|视频|音频)\s*([0-9]+)\s*$")
    current_kind = ""
    current_id = 0
    current_fields: dict[str, object] = {}

    def flush() -> None:
        if current_kind and current_id:
            item = media_item_from_mapping(current_kind, current_id, current_fields)
            items[(item.kind, item.media_id)] = item

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = header_re.match(line)
        if header:
            flush()
            current_kind = normalize_media_kind(header.group(1))
            current_id = int(header.group(2))
            current_fields = {}
            continue
        if not current_kind:
            continue
        line = re.sub(r"^[-*]\s*", "", line)
        field = re.match(r"([^：:]+)[：:]\s*(.+)$", line)
        if not field:
            continue
        raw_key = field.group(1).strip()
        value = field.group(2).strip()
        key = MARKDOWN_FIELD_KEYS.get(raw_key)
        if key:
            current_fields[key] = split_list_value(value) if key in {"subjects", "actions", "constraints"} else value
    flush()
    return MediaAnalysis(items)


def normalize_media_kind(value: str) -> str:
    return MEDIA_ANALYSIS_KEYS.get(value.strip(), "")


def media_item_from_mapping(kind: str, media_id: object, raw_item: object) -> MediaItem:
    try:
        item_id = int(str(media_id))
    except ValueError as exc:
        raise SystemExit(f"素材编号必须是数字：{media_id}") from exc
    mapping = raw_item if isinstance(raw_item, dict) else {}
    return MediaItem(
        kind=kind,
        media_id=item_id,
        role=string_value(mapping.get("role")),
        summary=string_value(mapping.get("summary")),
        subjects=list_value(mapping.get("subjects")),
        scene=string_value(mapping.get("scene")),
        style=string_value(mapping.get("style")),
        constraints=list_value(mapping.get("constraints")),
        start_frame=string_value(mapping.get("start_frame") or mapping.get("first_frame")),
        end_frame=string_value(mapping.get("end_frame") or mapping.get("last_frame")),
        motion=string_value(mapping.get("motion") or mapping.get("camera")),
        actions=list_value(mapping.get("actions")),
        timing=string_value(mapping.get("timing")),
        audio=string_value(mapping.get("audio")),
        voice=string_value(mapping.get("voice") or mapping.get("timbre")),
        emotion=string_value(mapping.get("emotion")),
        rhythm=string_value(mapping.get("rhythm")),
    )


def string_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "，".join(string_value(item) for item in value if string_value(item))
    return str(value).strip()


def list_value(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [string_value(item) for item in value if string_value(item)]
    return split_list_value(string_value(value))


def split_list_value(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[，,、/；;]\s*", value) if part.strip()]


def media_analysis_to_json_dict(media_analysis: MediaAnalysis) -> dict[str, dict[str, dict[str, object]]]:
    output: dict[str, dict[str, dict[str, object]]] = {"images": {}, "videos": {}, "audios": {}}
    group_by_kind = {"image": "images", "video": "videos", "audio": "audios"}
    for (kind, media_id), item in sorted(media_analysis.items.items(), key=lambda entry: (entry[0][0], entry[0][1])):
        data = asdict(item)
        data.pop("kind", None)
        data.pop("media_id", None)
        cleaned: dict[str, object] = {}
        for key, value in data.items():
            if isinstance(value, list):
                if value:
                    cleaned[key] = value
            elif value:
                cleaned[key] = value
        output[group_by_kind[kind]][str(media_id)] = cleaned
    return {key: value for key, value in output.items() if value}


def merge_media_analysis(base: MediaAnalysis, generated: MediaAnalysis) -> MediaAnalysis:
    merged = dict(base.items)
    for key, generated_item in generated.items.items():
        existing = merged.get(key)
        if not existing:
            merged[key] = generated_item
            continue
        merged[key] = merge_media_item(existing, generated_item)
    return MediaAnalysis(merged)


def merge_media_item(existing: MediaItem, generated: MediaItem) -> MediaItem:
    data = asdict(existing)
    generated_data = asdict(generated)
    for key, value in generated_data.items():
        if key in {"kind", "media_id"}:
            continue
        current = data.get(key)
        if isinstance(current, list):
            if not current and isinstance(value, list) and value:
                data[key] = value
        elif not current and value:
            data[key] = value
    return MediaItem(**data)


def parse_media_inputs(values: Sequence[str] | None, kind: str) -> list[MediaInput]:
    inputs: list[MediaInput] = []
    for raw_value in values or []:
        if "=" not in raw_value:
            raise SystemExit(f"{MEDIA_LABELS[kind]}素材参数必须使用 N=PATH 格式：{raw_value}")
        raw_id, raw_path = raw_value.split("=", 1)
        try:
            media_id = int(raw_id.strip())
        except ValueError as exc:
            raise SystemExit(f"{MEDIA_LABELS[kind]}素材编号必须是数字：{raw_id}") from exc
        path = Path(raw_path).expanduser()
        if not path.exists():
            raise SystemExit(f"{MEDIA_LABELS[kind]}{media_id} 文件不存在：{path}")
        if not path.is_file():
            raise SystemExit(f"{MEDIA_LABELS[kind]}{media_id} 不是文件：{path}")
        inputs.append(MediaInput(kind, media_id, path))
    return inputs


def collect_media_inputs(args: argparse.Namespace) -> list[MediaInput]:
    inputs: list[MediaInput] = []
    inputs.extend(parse_media_inputs(getattr(args, "image", None), "image"))
    inputs.extend(parse_media_inputs(getattr(args, "video", None), "video"))
    inputs.extend(parse_media_inputs(getattr(args, "audio", None), "audio"))
    return inputs


def require_ark_api_key() -> str:
    api_key = os.environ.get("ARK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("缺少 ARK_API_KEY 环境变量。请先设置 ARK_API_KEY；不要把密钥写进代码、命令行参数或技能目录。")
    return api_key


def require_ffmpeg_tools() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise SystemExit("缺少必需工具：" + "、".join(missing) + "。请先安装 ffmpeg/ffprobe 后再分析视频或音频素材。")


def data_url_for_file(path: Path, mime_type: str | None = None) -> str:
    mime = mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64_for_file(path)}"


def base64_for_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def file_size(path: Path) -> int:
    return path.stat().st_size


def media_prompt(kind: str, media_id: int) -> str:
    if kind == "image":
        return (
            f"请分析图片{media_id}，输出 JSON。"
            "字段：role, summary, subjects, scene, style, constraints。"
            "重点描述可用于 Seedance 视频生成的角色、场景、风格和一致性约束。"
        )
    if kind == "video":
        return (
            f"请分析视频{media_id}，输出 JSON。"
            "字段：role, summary, start_frame, end_frame, motion, actions, timing, audio。"
            "重点描述首帧、尾帧、运镜、动作节奏、场景和音频/对白特征。"
        )
    return (
        f"请分析音频{media_id}，输出 JSON。"
        "字段：role, summary, voice, emotion, rhythm, constraints。"
        "重点描述音色、情绪、语速节奏和生成台词时应保持的约束。"
    )


def ark_chat_completion(messages: list[dict[str, object]], args: argparse.Namespace) -> str:
    api_key = require_ark_api_key()
    base_url = os.environ.get("ARK_BASE_URL", "").strip() or DEFAULT_ARK_BASE_URL
    model = getattr(args, "ark_model", None) or DEFAULT_ARK_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        base_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Ark 多模态分析请求失败：HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Ark 多模态分析请求失败：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Ark 响应不是合法 JSON：{exc}") from exc
    try:
        return str(response_payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit("Ark 响应缺少 choices[0].message.content。") from exc


def parse_ark_media_item(kind: str, media_id: int, content: str) -> MediaItem:
    raw_content = content.strip()
    if raw_content.startswith("```"):
        raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
        raw_content = re.sub(r"\s*```$", "", raw_content)
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Ark 素材分析结果 JSON 解析失败：{exc}") from exc
    if isinstance(payload, dict):
        for container_key in (MEDIA_LABELS[kind] + str(media_id), str(media_id), "result", "analysis"):
            nested = payload.get(container_key)
            if isinstance(nested, dict):
                payload = nested
                break
    return media_item_from_mapping(kind, media_id, payload)


def analyze_image_with_ark(media_input: MediaInput, args: argparse.Namespace) -> MediaItem:
    content = [
        {"type": "text", "text": media_prompt("image", media_input.media_id)},
        {"type": "image_url", "image_url": {"url": data_url_for_file(media_input.path)}},
    ]
    return parse_ark_media_item("image", media_input.media_id, ark_chat_completion([{"role": "user", "content": content}], args))


def analyze_audio_with_ark(media_input: MediaInput, args: argparse.Namespace) -> MediaItem:
    direct_failed = False
    if file_size(media_input.path) <= DIRECT_UPLOAD_LIMIT_BYTES:
        content = [
            {"type": "text", "text": media_prompt("audio", media_input.media_id)},
            {"type": "input_audio", "input_audio": {"data": base64_for_file(media_input.path), "format": media_input.path.suffix.lstrip(".") or "wav"}},
        ]
        try:
            return parse_ark_media_item("audio", media_input.media_id, ark_chat_completion([{"role": "user", "content": content}], args))
        except SystemExit:
            direct_failed = True
    require_ffmpeg_tools()
    with tempfile.TemporaryDirectory() as tmp_dir:
        converted = Path(tmp_dir) / "audio.wav"
        run_ffmpeg(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(media_input.path), "-t", "20", "-ac", "1", "-ar", "16000", str(converted)])
        content = [
            {"type": "text", "text": media_prompt("audio", media_input.media_id) + ("直传失败，以下为转换后的代表性音频片段。" if direct_failed else "")},
            {"type": "input_audio", "input_audio": {"data": base64_for_file(converted), "format": "wav"}},
        ]
        return parse_ark_media_item("audio", media_input.media_id, ark_chat_completion([{"role": "user", "content": content}], args))


def analyze_video_with_ark(media_input: MediaInput, args: argparse.Namespace) -> MediaItem:
    direct_failed = False
    if file_size(media_input.path) <= DIRECT_UPLOAD_LIMIT_BYTES:
        content = [
            {"type": "text", "text": media_prompt("video", media_input.media_id)},
            {"type": "video_url", "video_url": {"url": data_url_for_file(media_input.path)}},
        ]
        try:
            return parse_ark_media_item("video", media_input.media_id, ark_chat_completion([{"role": "user", "content": content}], args))
        except SystemExit:
            direct_failed = True
    require_ffmpeg_tools()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        duration = ffprobe_duration(media_input.path)
        timestamps = video_sample_timestamps(duration)
        frame_paths = extract_video_frames(media_input.path, timestamps, tmp_path)
        audio_path = extract_video_audio(media_input.path, tmp_path)
        content: list[dict[str, object]] = [
            {
                "type": "text",
                "text": media_prompt("video", media_input.media_id)
                + ("直传失败或文件较大，以下为视频首帧、中间帧、尾帧和代表性音频片段。" if direct_failed else "以下为视频首帧、中间帧、尾帧和代表性音频片段。"),
            }
        ]
        for index, frame_path in enumerate(frame_paths, start=1):
            content.append({"type": "text", "text": f"视频{media_input.media_id}关键帧{index}"})
            content.append({"type": "image_url", "image_url": {"url": data_url_for_file(frame_path, "image/jpeg")}})
        if audio_path.exists() and audio_path.stat().st_size > 0:
            content.append({"type": "text", "text": f"视频{media_input.media_id}代表性音频片段"})
            content.append({"type": "input_audio", "input_audio": {"data": base64_for_file(audio_path), "format": "wav"}})
        return parse_ark_media_item("video", media_input.media_id, ark_chat_completion([{"role": "user", "content": content}], args))


def run_ffmpeg(command: list[str]) -> None:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "ffmpeg 执行失败。")


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "ffprobe 执行失败。")
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError:
        return 0.0


def video_sample_timestamps(duration: float) -> list[float]:
    if duration <= 0:
        return [0.0, 1.0, 2.0]
    return [min(0.5, duration / 4), duration / 2, max(0.0, duration - min(1.0, duration / 4))]


def extract_video_frames(path: Path, timestamps: list[float], tmp_path: Path) -> list[Path]:
    frames: list[Path] = []
    for index, timestamp in enumerate(timestamps, start=1):
        frame_path = tmp_path / f"frame_{index}.jpg"
        run_ffmpeg(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.3f}", "-i", str(path), "-frames:v", "1", str(frame_path)])
        if frame_path.exists():
            frames.append(frame_path)
    return frames


def extract_video_audio(path: Path, tmp_path: Path) -> Path:
    audio_path = tmp_path / "video_audio.wav"
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-t", "20", "-vn", "-ac", "1", "-ar", "16000", str(audio_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        return audio_path
    return audio_path


def analyze_media_inputs(args: argparse.Namespace) -> MediaAnalysis:
    inputs = collect_media_inputs(args)
    if not inputs:
        return MediaAnalysis({})
    require_ffmpeg_tools()
    items: dict[tuple[str, int], MediaItem] = {}
    for media_input in inputs:
        if media_input.kind == "image":
            item = analyze_image_with_ark(media_input, args)
        elif media_input.kind == "video":
            item = analyze_video_with_ark(media_input, args)
        else:
            item = analyze_audio_with_ark(media_input, args)
        items[(item.kind, item.media_id)] = item
    return MediaAnalysis(items)


def save_media_analysis(path: str | None, media_analysis: MediaAnalysis) -> None:
    if not path:
        return
    Path(path).write_text(json.dumps(media_analysis_to_json_dict(media_analysis), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_content_asset_mapping(prompt: str) -> ContentAssetMapping | None:
    if '"content"' not in prompt and "'content'" not in prompt:
        return None
    try:
        payload = json.loads(prompt)
    except json.JSONDecodeError:
        return None

    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, list):
        return None

    counters = {"image": 0, "video": 0, "audio": 0}
    assets: list[ContentAsset] = []
    text_parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = string_value(item.get("type"))
        if item_type == "text":
            text_parts.append(string_value(item.get("text")))
            continue
        kind = kind_from_content_item(item)
        source = source_from_content_item(item)
        if not kind or not source:
            continue
        counters[kind] += 1
        assets.append(ContentAsset(kind, counters[kind], source, string_value(item.get("role"))))

    if not assets:
        return None
    text = "\n".join(part for part in text_parts if part).strip() or prompt
    for asset in assets:
        text = text.replace(asset.source, media_ref(asset.kind, asset.media_id))
    return ContentAssetMapping(text=text, assets=assets)


def kind_from_content_item(item: dict[str, object]) -> str:
    item_type = string_value(item.get("type")).lower()
    role = string_value(item.get("role")).lower()
    if "image" in item_type or "image" in role or "reference_image" in role:
        return "image"
    if "video" in item_type or "video" in role or "reference_video" in role:
        return "video"
    if "audio" in item_type or "audio" in role or "reference_audio" in role:
        return "audio"
    for key in item:
        lowered = str(key).lower()
        if "image" in lowered:
            return "image"
        if "video" in lowered:
            return "video"
        if "audio" in lowered:
            return "audio"
    return ""


def source_from_content_item(item: dict[str, object]) -> str:
    for key in ("image_url", "video_url", "audio_url", "url"):
        value = item.get(key)
        if isinstance(value, dict):
            source = string_value(value.get("url"))
            if source:
                return source
        source = string_value(value)
        if source:
            return source
    for value in item.values():
        if isinstance(value, dict):
            source = string_value(value.get("url"))
            if source:
                return source
    return ""


def media_ref(kind: str, media_id: int) -> str:
    return f"{MEDIA_LABELS[kind]}{media_id}"


def normalize_seconds(text: str) -> str:
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*([~～\-至到])\s*(\d+(?:\.\d+)?)\s*s\b",
        r"\1\2\3秒",
        text,
        flags=re.I,
    )
    text = re.sub(r"(\d+(?:\.\d+)?)\s*s\b", r"\1秒", text, flags=re.I)
    return text


def remove_ineffective_quality(text: str) -> tuple[str, bool]:
    changed = False
    for pattern in INEFFECTIVE_QUALITY_PATTERNS:
        text, count = re.subn(pattern, "", text, flags=re.I)
        changed = changed or count > 0
    return cleanup_text(text), changed


def replace_vague_words(text: str) -> tuple[str, bool]:
    changed = False
    for vague, replacement in VAGUE_REPLACEMENTS.items():
        if vague in text:
            text = text.replace(vague, replacement)
            changed = True
    return cleanup_text(text), changed


def cleanup_text(text: str) -> str:
    text = text.replace("具体环境氛围、光影与色调明确景别", "具体环境氛围、光影与色调，明确景别")
    text = re.sub(r"[，,、；;]\s*([，,、；;])", r"\1", text)
    text = re.sub(r"[，,、；;]\s*([。.!！?？])", r"\1", text)
    text = re.sub(r"[，,、；;]\s*(?=$|\n)", "", text)
    text = re.sub(r"([。.!！?？])\s*([。.!！?？])", r"\1", text)
    text = re.sub(r"([，。；：、])\s+", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def normalize_forbidden_dash_dash(text: str) -> tuple[str, bool]:
    if "--" not in text:
        return text, False
    return text.replace("--", "，"), True


def normalize_video_task_words(text: str, task_type: str) -> tuple[str, bool]:
    if task_type not in {"edit", "extend", "combo"}:
        return text, False
    changed = False
    text, count = re.subn(r"参考\s*@?视频\s*([0-9]+)", r"视频\1", text)
    changed = changed or count > 0
    if task_type == "edit" and re.search(r"视频\s*[0-9]+", text) and not re.search(r"严格编辑\s*视频\s*[0-9]+", text):
        text = re.sub(r"(?<!严格编辑)(视频\s*[0-9]+)", r"严格编辑\1", text, count=1)
        changed = True
    if task_type == "extend" and re.search(r"视频\s*[0-9]+", text) and not re.search(r"(?:延长|向前延长|向后延长)\s*视频\s*[0-9]+", text):
        prefix = "向前延长" if wants_prequel(text) else "延长"
        text = re.sub(r"(?<!延长)(视频\s*[0-9]+)", rf"{prefix}\1", text, count=1)
        changed = True
    return text, changed


def normalize_media_refs(text: str) -> str:
    text = re.sub(r"(?<!@)图片\s*([0-9]+)", r"@图片\1", text)
    text = re.sub(r"(?<!@)图\s*([0-9]+)", r"@图片\1", text)
    text = re.sub(r"(?<!@)视频\s*([0-9]+)", r"@视频\1", text)
    text = re.sub(r"(?<!@)音频\s*([0-9]+)", r"@音频\1", text)
    text = re.sub(r"(严格编辑|延长|向前延长)@视频", r"\1视频", text)
    return text


def detect_task(prompt: str, requested: str) -> str:
    if requested != "auto":
        return requested
    has_reference = bool(re.search(r"参考|提取|结合|按照|保持.*一致", prompt))
    has_edit = bool(re.search(r"严格编辑|编辑|替换|修改|删除|清除|去除|增加|轨道补[齐全]|补(?:全)?(?:音频|声音|口型|音轨|视频轨)", prompt))
    has_extend = bool(re.search(r"向前延长|向后延长|延长|续写|前序|生成.*(?:之前|之后)", prompt))
    if has_reference and has_edit:
        return "combo"
    if has_extend:
        return "extend"
    if has_edit:
        return "edit"
    return "reference"


def media_ids_from_prompt(prompt: str, kind: str) -> list[int]:
    ids = {int(match.group(1)) for match in MEDIA_PATTERNS[kind].finditer(prompt)}
    return sorted(ids)


def collect_media(prompt: str, images: int, videos: int, audios: int) -> dict[str, list[int]]:
    counts = {"image": images, "video": videos, "audio": audios}
    media: dict[str, list[int]] = {}
    for kind, count in counts.items():
        ids = set(media_ids_from_prompt(prompt, kind))
        ids.update(range(1, max(0, count) + 1))
        media[kind] = sorted(ids)
    return media


def merge_media_analysis_ids(media: dict[str, list[int]], media_analysis: MediaAnalysis) -> dict[str, list[int]]:
    merged = {kind: set(ids) for kind, ids in media.items()}
    for kind in ("image", "video", "audio"):
        merged[kind].update(media_analysis.ids(kind))
    return {kind: sorted(ids) for kind, ids in merged.items()}


def merge_content_asset_ids(media: dict[str, list[int]], content_mapping: ContentAssetMapping | None) -> dict[str, list[int]]:
    if not content_mapping:
        return media
    merged = {kind: set(ids) for kind, ids in media.items()}
    for asset in content_mapping.assets:
        merged[asset.kind].add(asset.media_id)
    return {kind: sorted(ids) for kind, ids in merged.items()}


def has_any_media(media: dict[str, list[int]]) -> bool:
    return any(media[kind] for kind in media)


def has_shots(prompt: str) -> bool:
    return bool(SHOT_RE.search(prompt))


def likely_has_text_generation(prompt: str) -> bool:
    return bool(re.search(r"字幕|文字|slogan|Slogan|logo|Logo|气泡|文字框|标题|标语", prompt))


def likely_has_people(prompt: str) -> bool:
    return bool(re.search(r"人物|角色|男生|女生|男人|女人|男孩|女孩|人脸|面部|脸|主角|女主|男主|他|她", prompt))


def likely_multi_person(prompt: str, media: dict[str, list[int]]) -> bool:
    return bool(re.search(r"多人|两人|二人|三人|四人|一群|男.*女|女.*男|父.*女|母.*子", prompt))


def wants_prequel(prompt: str) -> bool:
    return bool(re.search(r"向前延长|前序|之前|前面|开头之前|生成.*之前", prompt))


def wants_track_fill(prompt: str) -> bool:
    return bool(re.search(r"轨道补[齐全]|补(?:全)?(?:音频|声音|口型|音轨|视频轨)|补齐.*(?:音频|声音|口型|音轨|视频轨)", prompt))


def camera_motion_conflicts(text: str) -> list[str]:
    return [name for name, pattern in CAMERA_MOTION_PATTERNS.items() if pattern.search(text)]


def prompt_camera_motion_conflicts(prompt: str) -> list[str]:
    conflicts: list[str] = []
    for shot in split_into_shots(prompt):
        if re.search(r"参考|素材|职责|作为", shot):
            continue
        motions = camera_motion_conflicts(shot)
        if len(motions) > 1:
            for motion in motions:
                if motion not in conflicts:
                    conflicts.append(motion)
    return conflicts


def has_long_grid_image_risk(prompt: str, media_analysis: MediaAnalysis) -> bool:
    if GRID_IMAGE_RE.search(prompt):
        return True
    for item in media_analysis.items.values():
        if item.kind == "image" and GRID_IMAGE_RE.search(dedupe_join([item.role, item.summary, item.scene, item.style])):
            return True
    return False


def ambiguous_media_refs(prompt: str) -> list[str]:
    refs = set(re.findall(r"@?(?:图片|图)\s*([0-9]+)(?=\s*(?:跑|走|站|坐|位于|看|拿|说|冲|跳|转|进入|离开))", prompt))
    return [f"图片{media_id}" for media_id in sorted(refs, key=int)]


def add_diag(diags: list[Diagnostic], code: str, severity: str, message: str) -> None:
    if not any(d.code == code and d.message == message for d in diags):
        diags.append(Diagnostic(code, severity, message))


def analyze_prompt(prompt: str, args: argparse.Namespace, media_analysis: MediaAnalysis) -> Analysis:
    diagnostics: list[Diagnostic] = []
    applied_rules: list[str] = []
    content_mapping = extract_content_asset_mapping(prompt)
    analysis_prompt = content_mapping.text if content_mapping else prompt
    task_type = detect_task(analysis_prompt, args.task)
    media = merge_content_asset_ids(merge_media_analysis_ids(collect_media(analysis_prompt, args.images, args.videos, args.audios), media_analysis), content_mapping)

    normalized = normalize_seconds(analysis_prompt.strip())
    if normalized != analysis_prompt.strip():
        applied_rules.append("normalized_seconds")

    if content_mapping:
        add_diag(diagnostics, "CONTENT_ASSET_MAPPING_FOUND", "info", "已从 `content` JSON 中按素材出现顺序识别图片/视频/音频，并将 Asset ID 或 URL 映射为 `图片N/视频N/音频N`。")
        applied_rules.append("mapped_content_assets")

    normalized, dash_changed = normalize_forbidden_dash_dash(normalized)
    if dash_changed:
        add_diag(diagnostics, "FORBIDDEN_DASH_DASH", "error", "提示词包含 `--`；Seedance 可能忽略其后的内容，已替换为中文标点。")
        applied_rules.append("removed_forbidden_dash_dash")

    normalized, quality_changed = remove_ineffective_quality(normalized)
    if quality_changed:
        add_diag(diagnostics, "INEFFECTIVE_QUALITY_TERMS", "warning", "已移除或标记 4K/8K/60fps/HDR 等画质词；这些不是可靠的提示词控制项。")
        applied_rules.append("removed_ineffective_quality_terms")

    normalized, vague_changed = replace_vague_words(normalized)
    if vague_changed:
        applied_rules.append("replaced_vague_terms")

    normalized, task_word_changed = normalize_video_task_words(normalized, task_type)
    if task_word_changed:
        add_diag(diagnostics, "VIDEO_TASK_WORDING", "warning", "编辑/延长任务应使用 `视频N`、`严格编辑视频N` 或 `延长视频N`，不要写 `参考视频N`。")
        applied_rules.append("normalized_edit_extend_video_wording")

    if not has_shots(analysis_prompt):
        add_diag(diagnostics, "MISSING_SHOT_STRUCTURE", "error", "提示词缺少清晰的 `镜头1/镜头2/...` 或场景顺序；Seedance 提示词应按时间顺序组织。")
    elif not re.search(r"镜头\s*[0-9一二三四五六七八九十]+", analysis_prompt):
        add_diag(diagnostics, "WEAK_SHOT_LABELS", "warning", "建议使用明确的 `镜头1/镜头2/...` 标签，不要只写松散场景描述。")

    if len(re.split(r"\n\s*\n", analysis_prompt.strip())) <= 1 and len(analysis_prompt.strip()) > 180 and not has_shots(analysis_prompt):
        add_diag(diagnostics, "UNSTRUCTURED_BLOB", "warning", "提示词是一整段长文本；建议拆成全局设定、参考素材、分镜和约束。")

    for word in VAGUE_WORDS:
        if word in analysis_prompt:
            add_diag(diagnostics, f"VAGUE_WORD_{word}", "warning", f"`{word}` 表述过虚；请替换为具体光线、色调、构图、动作或风格细节。")

    if has_any_media(media):
        has_media_role_declaration = bool(re.search(r"(?:图片|图|视频|音频)\s*[0-9]+\s*(?:是|为|作为|：|:)", analysis_prompt))
        if not media_analysis.items and not content_mapping and not has_media_role_declaration:
            add_diag(diagnostics, "MEDIA_ANALYSIS_NOT_PROVIDED", "info", "如已上传图片/视频/音频，可提供素材理解摘要；CLI 会用摘要生成更具体的素材职责、运镜、首尾帧和音色描述。")
        if not media_analysis.items and not content_mapping and not has_media_role_declaration:
            add_diag(diagnostics, "MISSING_MEDIA_ROLE_DECLARATION", "error", "多模态提示词需要在开头声明素材职责，例如 `图片1是角色参考，视频1是运镜参考`。")
        if has_shots(analysis_prompt) and not re.search(r"@[图片图视频音频]", analysis_prompt):
            add_diag(diagnostics, "MISSING_REPEATED_MEDIA_BINDING", "warning", "分镜中也要重复素材绑定，例如 `Nora@图片1`，不要只在开头声明一次。")

    if re.search(r"asset-[a-zA-Z0-9_-]+", analysis_prompt) and not re.search(r"(?:图片|图|视频|音频)\s*[0-9]+\s*(?:是|为|对应)", analysis_prompt):
        add_diag(diagnostics, "ASSET_ID_NOT_BINDING", "error", "Asset ID 不能替代 `图片N/视频N/音频N`；请将每个上传素材显式映射到编号引用。")

    if task_type in {"edit", "extend", "combo"} and re.search(r"参考\s*@?视频\s*[0-9]+", analysis_prompt):
        add_diag(diagnostics, "REFERENCE_VIDEO_IN_EDIT_EXTEND", "error", "编辑/延长任务不要写 `参考视频N`，请写 `严格编辑视频N` 或 `延长视频N`。")

    motion_conflicts = prompt_camera_motion_conflicts(analysis_prompt)
    if len(motion_conflicts) > 1:
        add_diag(diagnostics, "CAMERA_MOTION_CONFLICT", "warning", "同一提示中出现多个可能冲突的运镜要求：" + "、".join(motion_conflicts) + "；建议每个镜头只保留一种主要运镜。")

    if has_long_grid_image_risk(analysis_prompt, media_analysis):
        add_diag(diagnostics, "LONG_GRID_IMAGE_RISK", "warning", "检测到长图/九宫格/多视图参考风险；建议拆分为单张参考图并逐一绑定到分镜。")

    ambiguous_refs = ambiguous_media_refs(analysis_prompt)
    if ambiguous_refs:
        add_diag(diagnostics, "MEDIA_REFERENCE_AMBIGUITY", "warning", "素材引用后直接连接动作或方位，可能产生分词歧义；建议写成 `@图片N（角色名）` 或 `@图片N的主体`。涉及：" + "、".join(ambiguous_refs))

    if len(media["image"]) >= 2 and not media_analysis.items and not re.search(r"左|右|前景|后景|首帧|尾帧|作为|是|为", analysis_prompt):
        add_diag(diagnostics, "AMBIGUOUS_MEDIA_MAPPING", "warning", "存在多张图片但缺少人物/站位/首尾帧等映射说明；建议明确每张图的职责和画面位置。")

    if not likely_has_text_generation(analysis_prompt) and not re.search(r"无字幕|不要字幕|避免.*字幕|不生成字幕|不要.*文字", analysis_prompt):
        add_diag(diagnostics, "MISSING_NO_SUBTITLE_CONSTRAINT", "warning", "如果不需要可见文字，请补充无字幕/无文字约束。")

    if not re.search(r"不要.*(?:logo|Logo|水印)|避免.*(?:logo|Logo|水印)", analysis_prompt):
        add_diag(diagnostics, "MISSING_NO_LOGO_WATERMARK", "info", "建议添加 `不要生成logo，不要生成水印`，降低意外平台标识出现概率。")

    if has_any_media(media) and not re.search(r"2D|3D|动漫|国漫|日漫|真人|写实|实拍|CG|胶片|赛博朋克|水墨|手绘", analysis_prompt):
        add_diag(diagnostics, "STYLE_DRIFT_RISK", "warning", "使用视觉参考时，请明确目标风格，降低风格漂移风险。")

    if media["image"] and likely_has_people(analysis_prompt) and not re.search(r"人脸|面部|脸部|面部特写|大头照|正脸", analysis_prompt):
        add_diag(diagnostics, "ID_DRIFT_RISK", "warning", "为保证人物 ID 稳定，建议使用独立人脸特写参考，并声明其职责。")

    if likely_multi_person(analysis_prompt, media) and not re.search(r"不要.*(?:同脸|复制|重复人物|双胞胎|分身)|禁止.*(?:同脸|复制|重复人物|双胞胎|分身)", analysis_prompt):
        add_diag(diagnostics, "TWIN_CHARACTER_RISK", "warning", "多人提示词应明确禁止重复同脸人物和复制身体。")

    for media_id in media["video"]:
        item = media_analysis.get("video", media_id)
        if item and (not item.motion or not (item.start_frame or item.end_frame)):
            add_diag(diagnostics, "VIDEO_ANALYSIS_UNDERSPECIFIED", "warning", f"视频{media_id}的素材理解摘要缺少首尾帧或运镜信息；编辑/延长衔接稳定性会下降。")

    for media_id in media["audio"]:
        item = media_analysis.get("audio", media_id)
        if item and not (item.voice or item.emotion or item.rhythm):
            add_diag(diagnostics, "AUDIO_TIMBRE_UNDERSPECIFIED", "warning", f"音频{media_id}的素材理解摘要缺少音色、情绪或节奏描述；音色参考稳定性会下降。")

    if media["audio"] and not re.search(r"音色|男声|女声|低沉|温润|清亮|沙哑|颗粒感|语气|情绪", analysis_prompt) and not any(media_analysis.get("audio", media_id) for media_id in media["audio"]):
        add_diag(diagnostics, "AUDIO_TIMBRE_UNDERSPECIFIED", "warning", "音频参考搭配文字音色和说话风格描述会更稳定。")

    return Analysis(task_type, diagnostics, media, applied_rules, normalized, media_analysis, content_mapping)


def extract_media_description(prompt: str, kind: str, media_id: int, media_analysis: MediaAnalysis) -> str:
    label = MEDIA_LABELS[kind]
    item = media_analysis.get(kind, media_id)
    if item:
        description = media_analysis_description(item)
        if description:
            return f"{label}{media_id}：{description}"
    alias = rf"(?:{label}|{'图' if kind == 'image' else label})\s*{media_id}"
    direct = re.search(rf"@?{alias}\s*(?:是|为|作为|：|:)\s*([^，。；;\n]+)", prompt)
    if direct:
        return f"{label}{media_id}：{direct.group(1).strip()}"
    lines = [line.strip() for line in prompt.splitlines() if line.strip()]
    for line in lines[:40]:
        if re.search(alias, line) and re.search(r"是|为|作为|：|:", line):
            line = re.split(r"(?=镜头\s*[0-9一二三四五六七八九十]+\s*[:：])", line, maxsplit=1)[0]
            clean = normalize_media_refs(line)
            clean = re.sub(r"^[@\s]*", "", clean)
            return clean.rstrip("。；;")
    return f"{label}{media_id}：请补充素材职责（角色/场景/道具/站位/运镜/音色等）"


def content_asset_description(content_mapping: ContentAssetMapping | None, kind: str, media_id: int) -> str:
    if not content_mapping:
        return ""
    for asset in content_mapping.assets:
        if asset.kind == kind and asset.media_id == media_id:
            label = MEDIA_LABELS[kind]
            role = asset.role or {
                "image": "参考图片",
                "video": "参考视频",
                "audio": "参考音频",
            }[kind]
            return f"{label}{media_id}：{role}（资产 ID: {asset.source}）"
    return ""


def media_analysis_description(item: MediaItem) -> str:
    parts: list[str] = []
    if item.role:
        parts.append(item.role)
    if item.summary:
        parts.append(item.summary)
    if item.kind == "image":
        parts.extend(item.subjects or [])
        if item.scene:
            parts.append(item.scene)
        if item.style:
            parts.append(item.style)
    elif item.kind == "video":
        if item.motion:
            parts.append(f"运镜：{item.motion}")
        if item.start_frame:
            parts.append(f"首帧：{item.start_frame}")
        if item.end_frame:
            parts.append(f"尾帧：{item.end_frame}")
        if item.actions:
            parts.append("动作：" + "、".join(item.actions))
        if item.timing:
            parts.append(f"节奏：{item.timing}")
        if item.audio:
            parts.append(f"音频：{item.audio}")
    elif item.kind == "audio":
        if item.voice:
            parts.append(item.voice)
        if item.emotion:
            parts.append(f"情绪：{item.emotion}")
        if item.rhythm:
            parts.append(f"节奏：{item.rhythm}")
    return dedupe_join(parts)


def dedupe_join(parts: Iterable[str]) -> str:
    seen: set[str] = set()
    cleaned: list[str] = []
    for part in parts:
        clean = cleanup_text(str(part)).strip("，。；; ")
        if clean and clean not in seen:
            seen.add(clean)
            cleaned.append(clean)
    return "，".join(cleaned)


def image_subject_bindings(reference_descriptions: dict[tuple[str, int], str]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    blocked = re.compile(r"参考|场景|背景|道具|服饰|妆造|运镜|音色|构图|站位|风格")
    for (kind, media_id), description in reference_descriptions.items():
        if kind != "image" or "：" not in description:
            continue
        subject = description.split("：", 1)[1].strip()
        if not subject or blocked.search(subject) or len(subject) > 12:
            continue
        bindings[subject] = f"图片{media_id}"
    return bindings


def media_analysis_subject_bindings(media_analysis: MediaAnalysis) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for (kind, media_id), item in media_analysis.items.items():
        if kind != "image":
            continue
        for subject in item.subjects or []:
            subject = subject.strip()
            if subject:
                bindings[subject] = f"图片{media_id}"
    return bindings


def apply_subject_bindings(text: str, bindings: dict[str, str]) -> str:
    for subject, media_label in sorted(bindings.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(rf"{re.escape(subject)}(?!@图片[0-9]+)", f"{subject}@{media_label}", text)
    return text


def reference_labels(reference_descriptions: dict[tuple[str, int], str], media_analysis: MediaAnalysis) -> dict[tuple[str, int], str]:
    labels: dict[tuple[str, int], str] = {}
    for key, description in reference_descriptions.items():
        kind, media_id = key
        item = media_analysis.get(kind, media_id)
        if item and item.subjects:
            labels[key] = item.subjects[0]
            continue
        if kind == "image" and "：" in description:
            candidate = description.split("：", 1)[1].split("，", 1)[0].strip()
            candidate = re.sub(r"^(角色参考|场景参考|参考图片|图片|图)\s*", "", candidate).strip()
            if candidate and len(candidate) <= 12 and not re.search(r"参考|场景|背景|风格|资产|请补充", candidate):
                labels[key] = candidate
    return labels


def disambiguate_bare_media_refs(text: str, labels: dict[tuple[str, int], str]) -> str:
    def replace(match: re.Match[str]) -> str:
        kind = "image" if match.group(1) in {"图片", "图"} else "video"
        media_id = int(match.group(2))
        label = labels.get((kind, media_id), "主体" if kind == "image" else "素材")
        return f"@{MEDIA_LABELS[kind]}{media_id}（{label}）"

    text = re.sub(r"@?(图片|图|视频)\s*([0-9]+)(?![0-9]*[）\)])(?=\s*(?:跑|走|站|坐|位于|看|拿|说|冲|跳|转|进入|离开))", replace, text)
    return re.sub(r"@?(图片|图|视频)\s*([0-9]+)(?![0-9]*[）\)])(?=\s*(?:[，。；,.!?！？]|$))", replace, text)


def strip_reference_lines(prompt: str) -> str:
    kept: list[str] = []
    reference_prefix = re.compile(
        r"^@?(?:图片|图|视频|音频)\s*[0-9]+\s*(?:是|为|作为|：|:)\s*[^，。；;\n]+[，。；;]?\s*"
    )
    for line in prompt.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("参考图片说明"):
            continue
        if re.search(r"^@?(?:图片|图|视频|音频)\s*[0-9]+\s*(?:是|为|作为|：|:)", stripped):
            remainder = stripped
            while True:
                next_remainder, count = reference_prefix.subn("", remainder, count=1)
                if count == 0:
                    break
                remainder = next_remainder.strip()
            if remainder:
                kept.append(remainder)
            continue
        kept.append(stripped)
    return "\n".join(kept)


def split_into_shots(prompt: str) -> list[str]:
    prompt = strip_reference_lines(prompt).strip()
    if not prompt:
        return ["请补充画面内容、主体动作、镜头运动与音频信息。"]

    shot_marker = re.compile(r"(?:^|[\n。；;])\s*(?:【?\s*(?:镜头|场景)\s*([0-9一二三四五六七八九十]+)\s*】?\s*[:：]?)")
    matches = list(shot_marker.finditer(prompt))
    if matches:
        shots: list[str] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(prompt)
            content = prompt[start:end].strip(" \n:：")
            if content:
                shots.append(content)
        if shots:
            return shots

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", prompt) if part.strip()]
    if len(paragraphs) > 1:
        return paragraphs

    return [prompt]


def task_display(task_type: str) -> str:
    return {
        "reference": "参考生成",
        "edit": "严格编辑",
        "extend": "延长",
        "combo": "参考 + 编辑组合",
    }.get(task_type, task_type)


def build_global_constraints(prompt: str, media: dict[str, list[int]]) -> list[str]:
    constraints: list[str] = []
    if not likely_has_text_generation(prompt):
        constraints.append("保持无字幕，避免画面生成任何文字。")
    constraints.append("不要生成logo，不要生成水印。")
    if likely_has_people(prompt):
        constraints.append("人物面部稳定不变形，五官清晰，人体结构正常，动作自然流畅。")
    if likely_multi_person(prompt, media):
        constraints.append("视频全程不要在同一画面中复制相同人物，不要多人同脸，不出现重复人物、分身或双胞胎效果。")
    constraints.append("画面无卡顿，无规律闪烁。")
    return constraints


def analysis_style_parts(media_analysis: MediaAnalysis) -> list[str]:
    parts: list[str] = []
    for item in media_analysis.items.values():
        if item.style:
            parts.append(f"目标视觉风格保持{item.style}")
        parts.extend(item.constraints or [])
    return parts


def build_shot_context(analysis: Analysis, prompt: str) -> str:
    media_analysis = analysis.media_analysis
    parts: list[str] = []
    if analysis.task_type == "extend":
        for video_id in analysis.media["video"]:
            item = media_analysis.get("video", video_id)
            if wants_prequel(prompt):
                parts.append(f"向前延长视频{video_id}，生成视频{video_id}之前自然发生的内容")
                if item and item.start_frame:
                    parts.append(f"衔接锚点为视频{video_id}首帧：{item.start_frame}")
            else:
                parts.append(f"延长视频{video_id}，生成视频{video_id}之后自然发生的内容")
                if item and item.end_frame:
                    parts.append(f"衔接锚点为视频{video_id}尾帧：{item.end_frame}")
            if item and item.motion:
                parts.append(f"保持视频{video_id}的运镜节奏：{item.motion}")
    if analysis.task_type in {"edit", "combo"} and wants_track_fill(prompt):
        for video_id in analysis.media["video"] or [1]:
            parts.append(f"严格编辑视频{video_id}，只补齐目标音频/口型/轨道内容")
            parts.append("保持原视频主体、动作、场景、构图、光影和时长不变")
    for video_id in analysis.media["video"]:
        item = media_analysis.get("video", video_id)
        if item and analysis.task_type == "reference":
            if item.motion:
                parts.append(f"参考@视频{video_id}的运镜：{item.motion}")
            if item.actions:
                parts.append(f"参考@视频{video_id}的动作节奏：" + "、".join(item.actions))
    for audio_id in analysis.media["audio"]:
        item = media_analysis.get("audio", audio_id)
        if item:
            audio_parts = [item.voice, item.emotion, item.rhythm]
            audio_text = dedupe_join(audio_parts)
            if audio_text:
                parts.append(f"使用@音频{audio_id}的音色和节奏：{audio_text}")
    return dedupe_join(parts)


def build_optimized_prompt(analysis: Analysis, args: argparse.Namespace) -> str:
    prompt = analysis.normalized_prompt
    prompt = normalize_media_refs(prompt)
    shots = split_into_shots(prompt)
    constraints = build_global_constraints(prompt, analysis.media)
    reference_descriptions = {
        (kind, media_id): (
            content_asset_description(analysis.content_mapping, kind, media_id)
            or extract_media_description(prompt, kind, media_id, analysis.media_analysis)
        )
        for kind in ("image", "video", "audio")
        for media_id in analysis.media[kind]
    }
    subject_bindings = image_subject_bindings(reference_descriptions)
    subject_bindings.update(media_analysis_subject_bindings(analysis.media_analysis))
    ref_labels = reference_labels(reference_descriptions, analysis.media_analysis)

    media_lines: list[str] = []
    if has_any_media(analysis.media):
        for kind in ("image", "video", "audio"):
            for media_id in analysis.media[kind]:
                media_lines.append(compact_reference_declaration(reference_descriptions[(kind, media_id)]))

    setting_parts: list[str] = []
    if args.duration:
        duration = normalize_seconds(str(args.duration))
        if not duration.endswith("秒") and re.fullmatch(r"\d+(?:\.\d+)?", duration):
            duration = f"{duration}秒"
        setting_parts.append(f"总时长约{duration}")
    if args.ratio:
        setting_parts.append(f"画面比例{args.ratio}")
    setting_parts.append("请补充明确的故事场景、主体外观、空间环境、光影色调和情绪氛围")
    if media_lines:
        setting_parts.append("参考素材：" + "，".join(media_lines))

    style_parts = [
        "请补充具体视觉风格、画面质感和镜头节奏",
        "动作流畅无穿模",
        "主体清晰稳定",
    ]
    if args.duration:
        style_parts.append(f"按总时长{duration}自然分配镜头节奏")
    else:
        style_parts.append("每个镜头不超过2~3秒")
    style_parts.extend(trim_period(constraint) for constraint in constraints)
    style_parts.extend(trim_period(part) for part in analysis_style_parts(analysis.media_analysis))

    lines: list[str] = [
        f"整体设定：{ensure_sentence('，'.join(setting_parts))}",
        "时间片分镜：",
    ]

    for index, shot in enumerate(shots, start=1):
        clean_shot = normalize_media_refs(shot)
        if analysis.task_type in {"edit", "extend", "combo"}:
            clean_shot = re.sub(r"@视频([0-9]+)", r"视频\1", clean_shot)
        clean_shot = apply_subject_bindings(clean_shot, subject_bindings)
        clean_shot = disambiguate_bare_media_refs(clean_shot, ref_labels)
        if index == 1:
            shot_context = build_shot_context(analysis, prompt)
            if shot_context:
                clean_shot = f"{shot_context}。{clean_shot}"
        clean_shot = re.sub(r"时长\s*[:：]\s*[^，。；;\n]+[，。；;]?\s*", "", clean_shot)
        clean_shot = re.sub(r"比例\s*[:：]\s*[^，。；;\n]+[，。；;]?\s*", "", clean_shot)
        clean_shot = cleanup_text(re.sub(r"\s+", " ", clean_shot))
        lines.append(f"镜头{index}: {ensure_sentence(clean_shot)}")
    lines.append(f"风格画质约束：{ensure_sentence('，'.join(style_parts))}")
    return "\n".join(lines).strip() + "\n"


def trim_period(text: str) -> str:
    return text.rstrip("。.!！?？")


def ensure_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return "请补充景别/机位/镜头、主体动作、场景光影和配音/音效。"
    if text[-1] not in "。.!！?？":
        return f"{text}。"
    return text


def compact_reference_declaration(description: str) -> str:
    if "：" in description:
        label, value = description.split("：", 1)
        return f"@{label.strip()}是{value.strip()}"
    if ":" in description:
        label, value = description.split(":", 1)
        return f"@{label.strip()}是{value.strip()}"
    if description.startswith("@"):
        return description
    return f"@{description}"


def render_diagnostics(analysis: Analysis, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(
            {
                "task_type": analysis.task_type,
                "diagnostics": [asdict(d) for d in analysis.diagnostics],
                "applied_rules": analysis.applied_rules,
                "media": analysis.media,
            },
            ensure_ascii=False,
            indent=2,
        )

    bullet = "-" if fmt == "markdown" else "*"
    lines = [f"任务类型：{task_display(analysis.task_type)}", "诊断："]
    if analysis.diagnostics:
        for diag in analysis.diagnostics:
            lines.append(f"{bullet} [{diag.severity}] {diag.code}: {diag.message}")
    else:
        lines.append(f"{bullet} 未发现问题。")
    if analysis.applied_rules:
        lines.append("已应用规则：")
        lines.extend(f"{bullet} {rule}" for rule in analysis.applied_rules)
    return "\n".join(lines)


def issue_for_diagnostic(diag: Diagnostic) -> str:
    return f"{diag.code}: {diag.message}"


PRINCIPLE_BY_CODE = {
    "CONTENT_ASSET_MAPPING_FOUND": "Asset ID 屏蔽原则：Asset ID 或 URL 需要映射为 `图片N/视频N/音频N` 后再被 Seedance 使用。",
    "ASSET_ID_NOT_BINDING": "Asset ID 屏蔽原则：不要让无语义 Asset ID 独立承担角色或素材指代。",
    "MEDIA_REFERENCE_AMBIGUITY": "断句防歧义原则：`@图片N` 后紧跟角色名或名词解释，避免和动作/方位连读。",
    "CAMERA_MOTION_CONFLICT": "单镜头单运镜原则：一个时间切片内只保留一种主要运镜，降低运动冲突。",
    "LONG_GRID_IMAGE_RISK": "单图参考原则：长图、九宫格和多视图应拆成单图后逐一绑定到分镜。",
    "AMBIGUOUS_MEDIA_MAPPING": "素材映射原则：多图场景必须明确人物、站位、首帧/尾帧或素材职责。",
    "MISSING_SHOT_STRUCTURE": "时间片分镜原则：按镜头顺序描述主体、动作、场景、光影和音频。",
    "MISSING_MEDIA_ROLE_DECLARATION": "多模态绑定原则：开头声明素材职责，并在分镜里重复绑定。",
    "MISSING_REPEATED_MEDIA_BINDING": "重复绑定原则：分镜中继续使用 `人物@图片N`、`@视频N`、`@音频N`。",
    "REFERENCE_VIDEO_IN_EDIT_EXTEND": "任务措辞原则：编辑/延长任务直接编辑或延长 `视频N`，不要写 `参考视频N`。",
    "VIDEO_TASK_WORDING": "任务措辞原则：参考、编辑、延长要用不同动词，避免模型误判任务。",
    "STYLE_DRIFT_RISK": "风格锁定原则：多模态参考时明确目标视觉风格，降低风格漂移。",
    "AUDIO_TIMBRE_UNDERSPECIFIED": "音色稳定原则：音频参考要补充音色、情绪和台词风格。",
}


def render_issues(analysis: Analysis) -> list[str]:
    return [issue_for_diagnostic(diag) for diag in analysis.diagnostics]


def render_principles(analysis: Analysis) -> list[str]:
    principles: list[str] = []
    seen: set[str] = set()
    for diag in analysis.diagnostics:
        principle = PRINCIPLE_BY_CODE.get(diag.code)
        if principle and principle not in seen:
            seen.add(principle)
            principles.append(principle)
    if not principles:
        principles.append("三段论结构原则：用整体设定、时间片分镜、风格画质约束组织 Seedance 提示词。")
    return principles


def render_bullets(title: str, items: list[str]) -> str:
    lines = [title]
    lines.extend(f"- {item}" for item in items)
    return "\n".join(lines)


def render_optimization(optimized_prompt: str, analysis: Analysis, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(
            {
                "optimized_prompt": optimized_prompt,
                "diagnostics": [asdict(d) for d in analysis.diagnostics],
                "task_type": analysis.task_type,
                "applied_rules": analysis.applied_rules,
                "issues": render_issues(analysis),
                "principles": render_principles(analysis),
            },
            ensure_ascii=False,
            indent=2,
        )
    if fmt == "markdown":
        diagnostics = render_diagnostics(analysis, "markdown")
        issues = render_bullets("## 优化问题", render_issues(analysis))
        principles = render_bullets("## 相关原则", render_principles(analysis))
        return f"## 优化后提示词\n\n{optimized_prompt}\n## 诊断\n\n{diagnostics}\n\n{issues}\n\n{principles}\n"
    return optimized_prompt


def template_for(task: str, args: argparse.Namespace) -> str:
    duration = normalize_seconds(str(args.duration)) if args.duration else "请填写时长，如 4秒"
    if re.fullmatch(r"\d+(?:\.\d+)?", duration):
        duration = f"{duration}秒"
    ratio = args.ratio or "请填写比例，如 16:9 或 9:16"
    common_constraints = (
        "保持无字幕，避免画面生成任何文字；不要生成logo，不要生成水印；"
        "人物面部稳定不变形，动作自然流畅，画面无卡顿，无规律闪烁。"
    )
    task_line = {
        "reference": "参考@图片1中的主体/风格/场景，生成一个全新视频。",
        "edit": "严格编辑视频1，将其中的[原特征]修改为[新特征]，其余内容保持不变。",
        "extend": "延长视频1，生成视频1之后自然发生的内容，保持主体、场景、光影和叙事一致。",
        "combo": "参考@图片1的[参考维度]，严格编辑视频1，[具体编辑内容]，其余内容保持不变。",
    }[task]
    return f"""整体设定：任务类型：{task_display(task)}，时长：{duration}，比例：{ratio}，请写清故事场景、主体外观、空间环境、光影色调和情绪氛围。如有素材，请写清 @图片1、@视频1、@音频1 的职责。
时间片分镜：
镜头1: 明确景别、机位和单一运镜。{task_line} 补充当前镜头的场景、光影、空间关系、台词、旁白、音效或环境音。
镜头2: 按时间顺序继续描述主体动作、表情和空间变化，补充当前镜头的景别/机位/镜头、场景光影和配音/音效。
风格画质约束：请写清具体视觉风格、画面质感和镜头节奏，{common_constraints}
"""


def render_template(task: str, args: argparse.Namespace, fmt: str) -> str:
    if task == "auto":
        task = "reference"
    content = template_for(task, args)
    if fmt == "json":
        return json.dumps({"task_type": task, "template": content}, ensure_ascii=False, indent=2)
    return content


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task", choices=TASKS, default="auto", help="提示词任务类型。")
    parser.add_argument("--duration", help="视频时长；纯数字会按秒处理。")
    parser.add_argument("--ratio", help="画面比例，例如 16:9 或 9:16。")
    parser.add_argument("--images", type=int, default=0, help="上传参考图片数量。")
    parser.add_argument("--videos", type=int, default=0, help="上传参考视频数量。")
    parser.add_argument("--audios", type=int, default=0, help="上传参考音频数量。")
    parser.add_argument("--media-analysis", help="素材理解摘要文件，支持 JSON/Markdown；传 '-' 时从标准输入读取。")
    parser.add_argument("--media-analysis-format", choices=MEDIA_ANALYSIS_FORMATS, default="auto", help="素材理解摘要格式。")
    parser.add_argument("--format", choices=OUTPUT_FORMATS, default="text", help="输出格式。")


def add_media_input_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--image", action="append", default=[], metavar="N=PATH", help="直接分析图片素材，可重复传入，例如 --image 1=role.jpg。")
    parser.add_argument("--video", action="append", default=[], metavar="N=PATH", help="直接分析视频素材，可重复传入，例如 --video 2=ref.mp4。")
    parser.add_argument("--audio", action="append", default=[], metavar="N=PATH", help="直接分析音频素材，可重复传入，例如 --audio 1=voice.wav。")
    parser.add_argument("--media-provider", choices=MEDIA_PROVIDERS, default="ark", help="直接素材分析后端。")
    parser.add_argument("--ark-model", default=DEFAULT_ARK_MODEL, help="Ark OpenAI-compatible model/endpoint id。")
    parser.add_argument("--analyze-media-output", help="保存自动生成的素材理解摘要 JSON。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查并优化 Seedance 2.0 提示词。", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="显示此帮助信息并退出。")
    parser._positionals.title = "位置参数"
    parser._optionals.title = "可选参数"
    subparsers = parser.add_subparsers(dest="command", required=True)

    lint = subparsers.add_parser("lint", help="诊断 Seedance 提示词。", add_help=False)
    lint.add_argument("-h", "--help", action="help", help="显示此帮助信息并退出。")
    lint._positionals.title = "位置参数"
    lint._optionals.title = "可选参数"
    lint.add_argument("--input", "-i", help="输入提示词文件。省略或传 '-' 时从标准输入读取。")
    add_common_options(lint)
    add_media_input_options(lint)

    optimize = subparsers.add_parser("optimize", help="将提示词改写为结构化 Seedance 格式。", add_help=False)
    optimize.add_argument("-h", "--help", action="help", help="显示此帮助信息并退出。")
    optimize._positionals.title = "位置参数"
    optimize._optionals.title = "可选参数"
    optimize.add_argument("--input", "-i", help="输入提示词文件。省略或传 '-' 时从标准输入读取。")
    optimize.add_argument("--output", "-o", help="优化后提示词的输出文件。")
    add_common_options(optimize)
    add_media_input_options(optimize)

    template = subparsers.add_parser("template", help="输出可填写的 Seedance 提示词模板。", add_help=False)
    template.add_argument("-h", "--help", action="help", help="显示此帮助信息并退出。")
    template._positionals.title = "位置参数"
    template._optionals.title = "可选参数"
    template.add_argument("--output", "-o", help="模板输出文件。")
    add_common_options(template)

    analyze_media = subparsers.add_parser("analyze-media", help="直接分析图片/视频/音频素材并输出素材理解摘要 JSON。", add_help=False)
    analyze_media.add_argument("-h", "--help", action="help", help="显示此帮助信息并退出。")
    analyze_media._positionals.title = "位置参数"
    analyze_media._optionals.title = "可选参数"
    analyze_media.add_argument("--output", "-o", help="素材理解摘要输出文件。")
    add_media_input_options(analyze_media)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "template":
        output = render_template(args.task, args, args.format)
        write_output(args.output, output)
        return 0

    if args.command == "analyze-media":
        generated_media_analysis = analyze_media_inputs(args)
        output = json.dumps(media_analysis_to_json_dict(generated_media_analysis), ensure_ascii=False, indent=2)
        write_output(args.output, output)
        return 0

    media_analysis = read_media_analysis(args.media_analysis, args.media_analysis_format)
    generated_media_analysis = analyze_media_inputs(args)
    save_media_analysis(args.analyze_media_output, generated_media_analysis)
    media_analysis = merge_media_analysis(media_analysis, generated_media_analysis)
    prompt = read_prompt(args.input)
    analysis = analyze_prompt(prompt, args, media_analysis)

    if args.command == "lint":
        print(render_diagnostics(analysis, args.format))
        return 1 if any(d.severity == "error" for d in analysis.diagnostics) else 0

    optimized_prompt = build_optimized_prompt(analysis, args)
    output = render_optimization(optimized_prompt, analysis, args.format)
    write_output(args.output, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
