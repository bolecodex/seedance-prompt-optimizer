#!/usr/bin/env python3
"""仓库级入口：转发运行自包含的 Seedance 提示词优化技能 CLI。"""

from __future__ import annotations

import runpy
from pathlib import Path


SKILL_CLI = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "seedance-prompt-optimizer"
    / "scripts"
    / "seedance_prompt_optimizer.py"
)

if not SKILL_CLI.exists():
    raise SystemExit(f"未找到技能内 CLI：{SKILL_CLI}")

runpy.run_path(str(SKILL_CLI), run_name="__main__")
