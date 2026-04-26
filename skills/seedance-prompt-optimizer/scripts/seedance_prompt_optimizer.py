#!/usr/bin/env python3
"""基于规则的 Seedance 2.0 提示词检查与优化器。

实现仅使用 Python 标准库，便于复制到 Codex 技能中运行。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


TASKS = ("auto", "reference", "edit", "extend", "combo")
OUTPUT_FORMATS = ("text", "markdown", "json")

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
CHINESE_NUMERALS = "一二三四五六七八九十"


@dataclass
class Diagnostic:
    code: str
    severity: str
    message: str


@dataclass
class Analysis:
    task_type: str
    diagnostics: list[Diagnostic]
    media: dict[str, list[int]]
    applied_rules: list[str]
    normalized_prompt: str


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
    if task_type == "extend" and re.search(r"视频\s*[0-9]+", text) and not re.search(r"(?:延长|向前延长)\s*视频\s*[0-9]+", text):
        text = re.sub(r"(?<!延长)(视频\s*[0-9]+)", r"延长\1", text, count=1)
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
    has_edit = bool(re.search(r"严格编辑|编辑|替换|修改|删除|清除|去除|增加", prompt))
    has_extend = bool(re.search(r"向前延长|向后延长|延长|续写|生成.*(?:之前|之后)", prompt))
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


def add_diag(diags: list[Diagnostic], code: str, severity: str, message: str) -> None:
    if not any(d.code == code and d.message == message for d in diags):
        diags.append(Diagnostic(code, severity, message))


def analyze_prompt(prompt: str, args: argparse.Namespace) -> Analysis:
    diagnostics: list[Diagnostic] = []
    applied_rules: list[str] = []
    task_type = detect_task(prompt, args.task)
    media = collect_media(prompt, args.images, args.videos, args.audios)

    normalized = normalize_seconds(prompt.strip())
    if normalized != prompt.strip():
        applied_rules.append("normalized_seconds")

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

    if not has_shots(prompt):
        add_diag(diagnostics, "MISSING_SHOT_STRUCTURE", "error", "提示词缺少清晰的 `镜头1/镜头2/...` 或场景顺序；Seedance 提示词应按时间顺序组织。")
    elif not re.search(r"镜头\s*[0-9一二三四五六七八九十]+", prompt):
        add_diag(diagnostics, "WEAK_SHOT_LABELS", "warning", "建议使用明确的 `镜头1/镜头2/...` 标签，不要只写松散场景描述。")

    if len(re.split(r"\n\s*\n", prompt.strip())) <= 1 and len(prompt.strip()) > 180 and not has_shots(prompt):
        add_diag(diagnostics, "UNSTRUCTURED_BLOB", "warning", "提示词是一整段长文本；建议拆成全局设定、参考素材、分镜和约束。")

    for word in VAGUE_WORDS:
        if word in prompt:
            add_diag(diagnostics, f"VAGUE_WORD_{word}", "warning", f"`{word}` 表述过虚；请替换为具体光线、色调、构图、动作或风格细节。")

    if has_any_media(media):
        if not re.search(r"(?:图片|图|视频|音频)\s*[0-9]+\s*(?:是|为|作为|：|:)", prompt):
            add_diag(diagnostics, "MISSING_MEDIA_ROLE_DECLARATION", "error", "多模态提示词需要在开头声明素材职责，例如 `图片1是角色参考，视频1是运镜参考`。")
        if has_shots(prompt) and not re.search(r"@[图片图视频音频]", prompt):
            add_diag(diagnostics, "MISSING_REPEATED_MEDIA_BINDING", "warning", "分镜中也要重复素材绑定，例如 `Nora@图片1`，不要只在开头声明一次。")

    if re.search(r"asset-[a-zA-Z0-9_-]+", prompt) and not re.search(r"(?:图片|图|视频|音频)\s*[0-9]+\s*(?:是|为|对应)", prompt):
        add_diag(diagnostics, "ASSET_ID_NOT_BINDING", "error", "Asset ID 不能替代 `图片N/视频N/音频N`；请将每个上传素材显式映射到编号引用。")

    if task_type in {"edit", "extend", "combo"} and re.search(r"参考\s*@?视频\s*[0-9]+", prompt):
        add_diag(diagnostics, "REFERENCE_VIDEO_IN_EDIT_EXTEND", "error", "编辑/延长任务不要写 `参考视频N`，请写 `严格编辑视频N` 或 `延长视频N`。")

    if not likely_has_text_generation(prompt) and not re.search(r"无字幕|不要字幕|避免.*字幕|不生成字幕|不要.*文字", prompt):
        add_diag(diagnostics, "MISSING_NO_SUBTITLE_CONSTRAINT", "warning", "如果不需要可见文字，请补充无字幕/无文字约束。")

    if not re.search(r"不要.*(?:logo|Logo|水印)|避免.*(?:logo|Logo|水印)", prompt):
        add_diag(diagnostics, "MISSING_NO_LOGO_WATERMARK", "info", "建议添加 `不要生成logo，不要生成水印`，降低意外平台标识出现概率。")

    if has_any_media(media) and not re.search(r"2D|3D|动漫|国漫|日漫|真人|写实|实拍|CG|胶片|赛博朋克|水墨|手绘", prompt):
        add_diag(diagnostics, "STYLE_DRIFT_RISK", "warning", "使用视觉参考时，请明确目标风格，降低风格漂移风险。")

    if media["image"] and likely_has_people(prompt) and not re.search(r"人脸|面部|脸部|面部特写|大头照|正脸", prompt):
        add_diag(diagnostics, "ID_DRIFT_RISK", "warning", "为保证人物 ID 稳定，建议使用独立人脸特写参考，并声明其职责。")

    if likely_multi_person(prompt, media) and not re.search(r"不要.*(?:同脸|复制|重复人物|双胞胎|分身)|禁止.*(?:同脸|复制|重复人物|双胞胎|分身)", prompt):
        add_diag(diagnostics, "TWIN_CHARACTER_RISK", "warning", "多人提示词应明确禁止重复同脸人物和复制身体。")

    if media["audio"] and not re.search(r"音色|男声|女声|低沉|温润|清亮|沙哑|颗粒感|语气|情绪", prompt):
        add_diag(diagnostics, "AUDIO_TIMBRE_UNDERSPECIFIED", "warning", "音频参考搭配文字音色和说话风格描述会更稳定。")

    return Analysis(task_type, diagnostics, media, applied_rules, normalized)


def extract_media_description(prompt: str, kind: str, media_id: int) -> str:
    label = MEDIA_LABELS[kind]
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


def apply_subject_bindings(text: str, bindings: dict[str, str]) -> str:
    for subject, media_label in sorted(bindings.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(rf"{re.escape(subject)}(?!@图片[0-9]+)", f"{subject}@{media_label}", text)
    return text


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


def build_optimized_prompt(analysis: Analysis, args: argparse.Namespace) -> str:
    prompt = analysis.normalized_prompt
    prompt = normalize_media_refs(prompt)
    shots = split_into_shots(prompt)
    constraints = build_global_constraints(prompt, analysis.media)
    reference_descriptions = {
        (kind, media_id): extract_media_description(prompt, kind, media_id)
        for kind in ("image", "video", "audio")
        for media_id in analysis.media[kind]
    }
    subject_bindings = image_subject_bindings(reference_descriptions)

    media_lines: list[str] = []
    if has_any_media(analysis.media):
        for kind in ("image", "video", "audio"):
            for media_id in analysis.media[kind]:
                media_lines.append(compact_reference_declaration(reference_descriptions[(kind, media_id)]))

    global_parts: list[str] = []
    if args.duration:
        duration = normalize_seconds(str(args.duration))
        if not duration.endswith("秒") and re.fullmatch(r"\d+(?:\.\d+)?", duration):
            duration = f"{duration}秒"
        global_parts.append(f"时长：{duration}")
    else:
        global_parts.append("每个镜头不超过2~3秒")
    if args.ratio:
        global_parts.append(f"比例：{args.ratio}")
    global_parts.append("请补充具体视觉风格、场景、光影和色调")
    global_parts.extend(trim_period(constraint) for constraint in constraints)

    lines: list[str] = [f"【全局设定】{'，'.join(global_parts)}。"]
    if media_lines:
        lines.append(f"{'，'.join(media_lines)}。")

    for index, shot in enumerate(shots, start=1):
        clean_shot = normalize_media_refs(shot)
        if analysis.task_type in {"edit", "extend", "combo"}:
            clean_shot = re.sub(r"@视频([0-9]+)", r"视频\1", clean_shot)
        clean_shot = apply_subject_bindings(clean_shot, subject_bindings)
        clean_shot = re.sub(r"时长\s*[:：]\s*[^，。；;\n]+[，。；;]?\s*", "", clean_shot)
        clean_shot = re.sub(r"比例\s*[:：]\s*[^，。；;\n]+[，。；;]?\s*", "", clean_shot)
        clean_shot = cleanup_text(re.sub(r"\s+", " ", clean_shot))
        lines.append(f"镜头{index}: {ensure_sentence(clean_shot)}")
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


def render_optimization(optimized_prompt: str, analysis: Analysis, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(
            {
                "optimized_prompt": optimized_prompt,
                "diagnostics": [asdict(d) for d in analysis.diagnostics],
                "task_type": analysis.task_type,
                "applied_rules": analysis.applied_rules,
            },
            ensure_ascii=False,
            indent=2,
        )
    if fmt == "markdown":
        diagnostics = render_diagnostics(analysis, "markdown")
        return f"## 优化后提示词\n\n{optimized_prompt}\n## 诊断\n\n{diagnostics}\n"
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
    return f"""【全局设定】
- 任务类型：{task_display(task)}
- 时长：{duration}
- 比例：{ratio}
- 风格/场景/光影：请写清具体视觉风格、光线、色调、环境和画面基调。

【参考素材说明】
- 图片1：请说明角色/场景/道具/风格职责。
- 视频1：请说明是被编辑/延长的视频，或仅用于动作/运镜参考。
- 音频1：请说明音色、情绪、语气或音效职责。

【镜头1】
- 景别/机位/运镜：请填写一个明确景别、机位和单一运镜。
- 主体/动作：{task_line}
- 场景/光影：请填写当前镜头环境、空间关系和光影变化。
- 配音/音效：请填写台词、旁白、音效或环境音；台词语言保持统一。

【镜头2】
- 景别/机位/运镜：请填写。
- 主体/动作：请按时间顺序继续描述主体动作、表情和空间变化。
- 场景/光影：请填写。
- 配音/音效：请填写。

【全局约束】
- {common_constraints}
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
    parser.add_argument("--format", choices=OUTPUT_FORMATS, default="text", help="输出格式。")


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

    optimize = subparsers.add_parser("optimize", help="将提示词改写为结构化 Seedance 格式。", add_help=False)
    optimize.add_argument("-h", "--help", action="help", help="显示此帮助信息并退出。")
    optimize._positionals.title = "位置参数"
    optimize._optionals.title = "可选参数"
    optimize.add_argument("--input", "-i", help="输入提示词文件。省略或传 '-' 时从标准输入读取。")
    optimize.add_argument("--output", "-o", help="优化后提示词的输出文件。")
    add_common_options(optimize)

    template = subparsers.add_parser("template", help="输出可填写的 Seedance 提示词模板。", add_help=False)
    template.add_argument("-h", "--help", action="help", help="显示此帮助信息并退出。")
    template._positionals.title = "位置参数"
    template._optionals.title = "可选参数"
    template.add_argument("--output", "-o", help="模板输出文件。")
    add_common_options(template)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "template":
        output = render_template(args.task, args, args.format)
        write_output(args.output, output)
        return 0

    prompt = read_prompt(args.input)
    analysis = analyze_prompt(prompt, args)

    if args.command == "lint":
        print(render_diagnostics(analysis, args.format))
        return 1 if any(d.severity == "error" for d in analysis.diagnostics) else 0

    optimized_prompt = build_optimized_prompt(analysis, args)
    output = render_optimization(optimized_prompt, analysis, args.format)
    write_output(args.output, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
