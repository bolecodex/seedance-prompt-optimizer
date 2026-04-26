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
        self.assertIn("【全局设定】", payload["optimized_prompt"])
        self.assertIn("- 多模态参考：", payload["optimized_prompt"])
        self.assertNotIn("【参考素材说明】", payload["optimized_prompt"])
        self.assertIn("【镜头1】", payload["optimized_prompt"])
        self.assertIn("- 景别/机位/镜头：", payload["optimized_prompt"])
        self.assertIn("- 风格/画质：", payload["optimized_prompt"])
        self.assertIn("- 约束：", payload["optimized_prompt"])
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


if __name__ == "__main__":
    unittest.main()
