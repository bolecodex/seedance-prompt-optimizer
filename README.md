# Seedance Prompt Optimizer

面向 Seedance 2.0 的提示词优化 CLI 与 ArkClaw/OpenClaw Skill。用户把自己写的提示词发给 ArkClaw，ArkClaw 触发 `seedance-prompt-optimizer` 技能后，返回结构化、可执行的优化提示词和简短诊断。

规则优先级：如文档之间存在冲突，以 `docs/Seedance 2.0提示词常见问题与处理指南.md` 为准。

## 能力

- 将松散提示词改写为 `【全局设定】/【参考素材说明】/【镜头N】/【全局约束】`。
- 检查缺少分镜、多模态素材未绑定、`参考视频N` 误用于编辑/延长、`--`、`s` 时长、空泛词、无效画质词、字幕/logo/水印、风格漂移、人物 ID 漂移、双胞胎问题和音色描述不足。
- 支持 0-9 张图片、0-3 段视频、0-3 段音频的多参考生视频提示词检查与优化。
- 只依赖 Python 标准库。

## ArkClaw/OpenClaw 安装

OpenClaw/ArkClaw 会加载 `<workspace>/skills` 和 `~/.openclaw/skills` 中的技能，工作区技能优先。参考：

- [OpenClaw Skills](https://openclaw.cc/tools/skills)
- [openclaw skills 命令](https://openclaw.cc/cli/skills)
- [ArkClaw 介绍](https://arkclaw.lol/)

### 方式一：作为工作区仓库安装

```bash
git clone https://github.com/bolecodex/seedance-prompt-optimizer.git
cd seedance-prompt-optimizer
openclaw skills list
openclaw skills info seedance-prompt-optimizer
```

在新会话中直接发送：

```text
请使用 seedance-prompt-optimizer 优化这段 Seedance 提示词：
图片1是女主，图片2是江南雨巷场景，视频1是慢速推镜参考...
```

### 方式二：作为全局技能安装

```bash
git clone https://github.com/bolecodex/seedance-prompt-optimizer.git
mkdir -p ~/.openclaw/skills
cp -R seedance-prompt-optimizer/skills/seedance-prompt-optimizer ~/.openclaw/skills/
openclaw skills list
openclaw skills info seedance-prompt-optimizer
```

技能内 CLI 是自包含的；只复制 `skills/seedance-prompt-optimizer` 也能运行。

## CLI 用法

仓库入口：

```bash
python tools/seedance_prompt_optimizer.py lint --input prompt.txt
python tools/seedance_prompt_optimizer.py optimize --input prompt.txt --output optimized.txt
python tools/seedance_prompt_optimizer.py template --task reference
```

技能内入口：

```bash
python skills/seedance-prompt-optimizer/scripts/seedance_prompt_optimizer.py lint --input prompt.txt
python skills/seedance-prompt-optimizer/scripts/seedance_prompt_optimizer.py optimize --input prompt.txt --output optimized.txt
python skills/seedance-prompt-optimizer/scripts/seedance_prompt_optimizer.py template --task reference
```

常用参数：

```bash
--task auto|reference|edit|extend|combo
--duration 6
--ratio 9:16
--images 3
--videos 1
--audios 1
--format text|markdown|json
```

## 示例

```bash
printf '%s' '图片1是女主，图片2是江南雨巷场景，视频1是慢速推镜参考，音频1是温柔女声音色参考。氛围感电影感，女主走在图片2的雨巷里，参考视频1的运镜，使用音频1说：今晚雨真大。' \
  | python tools/seedance_prompt_optimizer.py optimize --task reference --images 2 --videos 1 --audios 1 --duration 6 --ratio 9:16 --format markdown
```

## 验证

```bash
python3 -m py_compile \
  tools/seedance_prompt_optimizer.py \
  skills/seedance-prompt-optimizer/scripts/seedance_prompt_optimizer.py

python3 /Users/bytedance/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/seedance-prompt-optimizer

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

如果没有本机 Codex 的 `quick_validate.py`，可跳过该项，或只检查 `skills/seedance-prompt-optimizer/SKILL.md` 是否包含合法的 `name` 与 `description` frontmatter。

## 故障排查

- ArkClaw 没有识别技能：重开新会话，确认技能位于 `<workspace>/skills/seedance-prompt-optimizer/SKILL.md` 或 `~/.openclaw/skills/seedance-prompt-optimizer/SKILL.md`。
- 全局安装后 CLI 找不到仓库文件：请确认复制的是当前版本技能目录；技能内脚本应为完整 CLI，而不是转发脚本。
- `lint` 返回非零退出码：表示存在 error 级诊断，例如缺少分镜或缺少多模态素材职责声明。
