from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_CLI = ROOT / "tools" / "seedance_prompt_optimizer.py"
SKILL_DIR = ROOT / "skills" / "seedance-prompt-optimizer"
SKILL_CLI = SKILL_DIR / "scripts" / "seedance_prompt_optimizer.py"


def run_cli(args: list[str], prompt: str | None = None, script: Path = REPO_CLI) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        input=prompt,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
    )


class SeedancePromptOptimizerTest(unittest.TestCase):
    def test_bad_multireference_prompt_returns_diagnostics_and_structure(self) -> None:
        prompt = (
            "图片1是女主，图片2是女主服饰参考，图片3是江南雨巷场景，"
            "视频1是慢速推镜和横移运镜参考，音频1是温柔清亮青年女声音色参考。"
            "时长：6s，比例：9:16。氛围感电影感，女主走在图片3中的雨巷里，"
            "参考视频1的运镜，使用音频1说：今晚雨真大。画面好看点，不要背景音乐。"
        )
        result = run_cli(
            [
                "optimize",
                "--task",
                "reference",
                "--images",
                "3",
                "--videos",
                "1",
                "--audios",
                "1",
                "--duration",
                "6",
                "--ratio",
                "9:16",
                "--format",
                "json",
            ],
            prompt,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["task_type"], "reference")
        self.assertIn("optimized_prompt", payload)
        self.assertIn("diagnostics", payload)
        self.assertIn("applied_rules", payload)
        self.assertIn("整体设定：", payload["optimized_prompt"])
        self.assertIn("时间片分镜：", payload["optimized_prompt"])
        self.assertIn("风格画质约束：", payload["optimized_prompt"])
        self.assertIn("@图片1是女主", payload["optimized_prompt"])
        self.assertIn("@视频1是慢速推镜和横移运镜参考", payload["optimized_prompt"])
        self.assertIn("@音频1是温柔清亮青年女声音色参考", payload["optimized_prompt"])
        self.assertNotIn("【参考素材说明】", payload["optimized_prompt"])
        self.assertNotIn("【全局设定】", payload["optimized_prompt"])
        self.assertNotIn("【镜头1】", payload["optimized_prompt"])
        self.assertIn("镜头1:", payload["optimized_prompt"])
        self.assertNotIn("- 景别/机位/镜头：", payload["optimized_prompt"])
        self.assertIn("女主@图片1", payload["optimized_prompt"])
        self.assertIn("@视频1", payload["optimized_prompt"])
        self.assertIn("@音频1", payload["optimized_prompt"])
        self.assertIn("MISSING_SHOT_STRUCTURE", {item["code"] for item in payload["diagnostics"]})
        self.assertIn("normalized_seconds", payload["applied_rules"])

    def test_good_multireference_prompt_has_no_diagnostics(self) -> None:
        prompt = (
            "图片1是女主人脸特写，图片2是女主全身服饰，图片3是江南雨巷场景，"
            "视频1是慢速推镜和横移运镜参考，音频1是温柔清亮青年女声音色参考。"
            "镜头1：中景，女主@图片1穿着@图片2中的服饰，站在@图片3雨巷入口，"
            "参考@视频1的慢速推镜，使用@音频1温柔清亮青年女声说：{今晚雨真大}。"
            "真人写实风格，冷青色雨夜光影。保持无字幕，避免画面生成文字，"
            "不要生成logo，不要生成水印。"
        )
        result = run_cli(
            [
                "lint",
                "--task",
                "reference",
                "--images",
                "3",
                "--videos",
                "1",
                "--audios",
                "1",
                "--format",
                "markdown",
            ],
            prompt,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("未发现问题", result.stdout)

    def test_skill_cli_runs_without_repo_tools_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            isolated_skill = Path(tmp) / "seedance-prompt-optimizer"
            shutil.copytree(SKILL_DIR, isolated_skill)
            isolated_cli = isolated_skill / "scripts" / "seedance_prompt_optimizer.py"
            result = subprocess.run(
                [sys.executable, str(isolated_cli), "template", "--task", "combo", "--duration", "6"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("参考 + 编辑组合", result.stdout)
        self.assertIn("6秒", result.stdout)

    def test_repo_cli_wrapper_delegates_to_skill_cli(self) -> None:
        result = run_cli(["template", "--task", "extend", "--duration", "5"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("任务类型：延长", result.stdout)
        self.assertIn("5秒", result.stdout)

    def test_json_media_analysis_enriches_optimized_prompt(self) -> None:
        media_analysis = {
            "images": {
                "1": {
                    "role": "角色参考",
                    "summary": "年轻女性，黑色长发，白色衬衫",
                    "subjects": ["女主"],
                    "style": "真人写实",
                    "constraints": ["保持发型和服装一致"],
                },
                "2": {
                    "role": "场景参考",
                    "summary": "江南雨巷，青石板路，冷青色雨夜光影",
                    "scene": "江南雨巷",
                },
            },
            "videos": {
                "1": {
                    "role": "运镜参考",
                    "summary": "室外慢速推镜",
                    "start_frame": "女主站在巷口",
                    "end_frame": "女主走到油纸伞下",
                    "motion": "中景缓慢推镜",
                    "actions": ["缓慢前行", "轻轻回头"],
                    "timing": "节奏缓慢",
                }
            },
            "audios": {
                "1": {
                    "role": "音色参考",
                    "summary": "温柔清亮青年女声",
                    "voice": "青年女声，清亮，语速中等",
                    "emotion": "温柔克制",
                    "rhythm": "平稳",
                }
            },
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as file:
            json.dump(media_analysis, file, ensure_ascii=False)
            file.flush()
            result = run_cli(
                [
                    "optimize",
                    "--task",
                    "reference",
                    "--images",
                    "2",
                    "--videos",
                    "1",
                    "--audios",
                    "1",
                    "--media-analysis",
                    file.name,
                    "--format",
                    "json",
                ],
                "镜头1：女主走进雨巷，使用音频1说：{今晚雨真大}。真人写实风格，不要字幕，不要生成logo，不要生成水印。",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        prompt = payload["optimized_prompt"]
        self.assertIn("@图片1是角色参考，年轻女性，黑色长发，白色衬衫", prompt)
        self.assertIn("@图片2是场景参考，江南雨巷", prompt)
        self.assertIn("@视频1是运镜参考，室外慢速推镜，运镜：中景缓慢推镜", prompt)
        self.assertIn("@音频1是音色参考，温柔清亮青年女声", prompt)
        self.assertIn("女主@图片1", prompt)
        self.assertIn("参考@视频1的运镜：中景缓慢推镜", prompt)
        self.assertIn("使用@音频1的音色和节奏：青年女声，清亮，语速中等", prompt)
        self.assertIn("保持发型和服装一致", prompt)

    def test_markdown_media_analysis_enriches_reference_declaration(self) -> None:
        markdown = """## 图片1
职责：角色参考
摘要：年轻男性，灰色西装
主体：男主
风格：真人写实

## 视频1
职责：待编辑视频
摘要：办公室对话场景
首帧：男主坐在桌前
尾帧：男主站起身
运镜：固定中景
"""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md") as file:
            file.write(markdown)
            file.flush()
            result = run_cli(
                [
                    "optimize",
                    "--task",
                    "reference",
                    "--images",
                    "1",
                    "--videos",
                    "1",
                    "--media-analysis",
                    file.name,
                    "--format",
                    "json",
                ],
                "镜头1：男主看向镜头。真人写实风格，不要字幕，不要生成logo，不要生成水印。",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = json.loads(result.stdout)["optimized_prompt"]
        self.assertIn("@图片1是角色参考，年轻男性，灰色西装，男主，真人写实", prompt)
        self.assertIn("@视频1是待编辑视频，办公室对话场景，运镜：固定中景", prompt)
        self.assertIn("男主@图片1", prompt)

    def test_prequel_extend_uses_start_frame_anchor(self) -> None:
        media_analysis = {
            "videos": {
                "1": {
                    "role": "待延长视频",
                    "summary": "女主站在雨巷尽头",
                    "start_frame": "女主背对镜头站在雨巷入口",
                    "end_frame": "女主走到灯笼下",
                    "motion": "缓慢跟拍",
                }
            }
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as file:
            json.dump(media_analysis, file, ensure_ascii=False)
            file.flush()
            result = run_cli(
                [
                    "optimize",
                    "--task",
                    "extend",
                    "--videos",
                    "1",
                    "--media-analysis",
                    file.name,
                    "--format",
                    "json",
                ],
                "生成视频1之前的内容，镜头1：女主从巷外走来。真人写实风格，不要字幕，不要生成logo，不要生成水印。",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = json.loads(result.stdout)["optimized_prompt"]
        self.assertIn("向前延长视频1，生成视频1之前自然发生的内容", prompt)
        self.assertIn("衔接锚点为视频1首帧：女主背对镜头站在雨巷入口", prompt)
        self.assertNotIn("参考视频1", prompt)

    def test_track_fill_is_edit_and_preserves_original_video(self) -> None:
        result = run_cli(
            [
                "optimize",
                "--videos",
                "1",
                "--format",
                "json",
            ],
            "给视频1补全音频轨道和口型，镜头1：补充人物说话声。真人写实风格，不要字幕，不要生成logo，不要生成水印。",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["task_type"], "edit")
        prompt = payload["optimized_prompt"]
        self.assertIn("严格编辑视频1，只补齐目标音频/口型/轨道内容", prompt)
        self.assertIn("保持原视频主体、动作、场景、构图、光影和时长不变", prompt)
        self.assertNotIn("参考视频1", prompt)

    def test_content_json_maps_assets_to_media_refs(self) -> None:
        payload = {
            "content": [
                {"type": "text", "text": "asset-img-001和asset-vid-001一起生成，镜头1：图片1走向镜头，参考视频1的动作。真人写实风格，不要字幕，不要生成logo，不要生成水印。"},
                {"type": "image_url", "image_url": {"url": "asset-img-001"}, "role": "reference_image"},
                {"type": "video_url", "video_url": {"url": "asset-vid-001"}, "role": "reference_video"},
            ]
        }
        result = run_cli(["optimize", "--format", "json"], json.dumps(payload, ensure_ascii=False))
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        codes = {item["code"] for item in output["diagnostics"]}
        prompt = output["optimized_prompt"]
        self.assertIn("CONTENT_ASSET_MAPPING_FOUND", codes)
        self.assertIn("@图片1是reference_image", prompt)
        self.assertIn("@视频1是reference_video", prompt)
        self.assertNotIn("asset-img-001和asset-vid-001一起生成", prompt)
        self.assertIn("issues", output)
        self.assertIn("principles", output)

    def test_bare_media_refs_get_disambiguated_with_subjects(self) -> None:
        media_analysis = {
            "images": {
                "1": {"role": "角色参考", "summary": "红衣女生", "subjects": ["女主"]},
                "2": {"role": "角色参考", "summary": "黑衣男生", "subjects": ["男主"]},
            }
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as file:
            json.dump(media_analysis, file, ensure_ascii=False)
            file.flush()
            result = run_cli(
                ["optimize", "--media-analysis", file.name, "--format", "json"],
                "镜头1：@图片1跑向@图片2，镜头固定。真人写实风格，不要字幕，不要生成logo，不要生成水印。",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = json.loads(result.stdout)["optimized_prompt"]
        self.assertIn("@图片1（女主）跑向@图片2（男主）", prompt)

    def test_camera_motion_conflict_is_reported(self) -> None:
        result = run_cli(
            ["lint", "--format", "json"],
            "镜头1：中景，角色缓慢走路，镜头缓慢推镜并向左横移同时环绕。真人写实风格，不要字幕，不要生成logo，不要生成水印。",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        codes = {item["code"] for item in json.loads(result.stdout)["diagnostics"]}
        self.assertIn("CAMERA_MOTION_CONFLICT", codes)

    def test_grid_image_risk_is_reported_from_media_analysis(self) -> None:
        media_analysis = {"images": {"1": {"role": "角色参考", "summary": "九宫格多视图角色拼图", "subjects": ["女主"]}}}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as file:
            json.dump(media_analysis, file, ensure_ascii=False)
            file.flush()
            result = run_cli(
                ["lint", "--media-analysis", file.name, "--format", "json"],
                "镜头1：女主@图片1看向镜头。真人写实风格，不要字幕，不要生成logo，不要生成水印。",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        codes = {item["code"] for item in json.loads(result.stdout)["diagnostics"]}
        self.assertIn("LONG_GRID_IMAGE_RISK", codes)

    def test_markdown_output_includes_issues_and_principles(self) -> None:
        result = run_cli(
            ["optimize", "--format", "markdown"],
            "氛围感电影感，镜头1：人物走在街上。",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## 优化问题", result.stdout)
        self.assertIn("## 相关原则", result.stdout)


if __name__ == "__main__":
    unittest.main()
