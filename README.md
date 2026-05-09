# Seedance Prompt Optimizer

面向 Seedance 2.0 的提示词优化 CLI 与 ArkClaw/OpenClaw Skill。用户把自己写的提示词发给 ArkClaw，ArkClaw 触发 `seedance-prompt-optimizer` 技能后，返回结构化、可执行的优化提示词和简短诊断。

规则优先级：如文档之间存在冲突，以 `docs/Seedance 2.0提示词常见问题与处理指南.md` 为准。

## 能力

- 将松散提示词改写为三段论格式：`整体设定：`、`时间片分镜：`、`风格画质约束：`。
- 检查缺少分镜、多模态素材未绑定、`参考视频N` 误用于编辑/延长、`--`、`s` 时长、空泛词、无效画质词、字幕/logo/水印、风格漂移、人物 ID 漂移、双胞胎问题和音色描述不足。
- 支持 0-9 张图片、0-3 段视频、0-3 段音频的多参考生视频提示词检查与优化。
- 支持读取 JSON/Markdown 素材理解摘要，将图片主体/场景/风格、视频首尾帧/运镜/动作、音频音色/情绪/节奏融入提示词。
- 支持扫描 Seedance API 风格 `content` JSON，按素材出现顺序建立 Asset ID/URL 到 `图片N/视频N/音频N` 的映射。
- 检查长图/九宫格参考、素材引用连读歧义和同镜头运镜冲突，并在 Markdown/JSON 输出中补充优化问题与相关原则。
- 只依赖 Python 标准库。

边界：CLI 不直接读取真实图片、视频、音频，也不联网调用多模态模型；真实素材理解由 ArkClaw/OpenClaw/Codex 等宿主多模态能力完成，CLI 只消费结构化摘要。

## 最新增强

- `--media-analysis` 可接收宿主多模态模型产出的 JSON/Markdown 摘要，让 CLI 把素材理解结果稳定写入提示词。
- `optimize --format markdown` 会额外输出 `优化问题` 和 `相关原则`；`--format json` 会返回 `issues` 与 `principles` 字段，便于上层系统展示或二次处理。
- 粘贴 Seedance API 风格 `content` JSON 时，CLI 会按非文本素材出现顺序建立 `asset-*`/URL 到 `图片N`、`视频N`、`音频N` 的映射。
- 官方规则已内置为诊断：长图/九宫格风险、素材引用连读歧义、同镜头多运镜冲突、编辑/延长任务误用 `参考视频N` 等。

## ArkClaw/OpenClaw 安装

OpenClaw/ArkClaw 会加载 `<workspace>/skills` 和 `~/.openclaw/skills` 中的技能，工作区技能优先。参考：

- [OpenClaw Skills](https://openclaw.cc/tools/skills)
- [openclaw skills 命令](https://openclaw.cc/cli/skills)
- [ArkClaw 介绍](https://arkclaw.lol/)

### 一键安装

```bash
bash <(curl -fsSL https://gitee.com/bolecodex/seedance-prompt-optimizer/raw/main/scripts/setup-gitee.sh)
```

该命令会安装技能到 `~/.openclaw/skills/seedance-prompt-optimizer`，并安装 CLI 到 `~/.local/bin/seedance-prompt-optimizer`。

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
--media-analysis media.json
--media-analysis-format auto|json|markdown
--format text|markdown|json
```

## 示例

```bash
printf '%s' '图片1是女主，图片2是江南雨巷场景，视频1是慢速推镜参考，音频1是温柔女声音色参考。氛围感电影感，女主走在图片2的雨巷里，参考视频1的运镜，使用音频1说：今晚雨真大。' \
  | python tools/seedance_prompt_optimizer.py optimize --task reference --images 2 --videos 1 --audios 1 --duration 6 --ratio 9:16 --format markdown
```

带素材理解摘要：

```json
{
  "images": {
    "1": {"role": "角色参考", "summary": "年轻女性，黑色长发，白色衬衫", "subjects": ["女主"], "style": "真人写实"}
  },
  "videos": {
    "1": {"role": "运镜参考", "summary": "室外慢速推镜", "start_frame": "女主站在巷口", "end_frame": "女主走到油纸伞下", "motion": "中景缓慢推镜"}
  },
  "audios": {
    "1": {"role": "音色参考", "summary": "温柔清亮青年女声", "voice": "青年女声，清亮", "emotion": "温柔克制", "rhythm": "平稳"}
  }
}
```

```bash
python tools/seedance_prompt_optimizer.py optimize \
  --input prompt.txt \
  --media-analysis media.json \
  --task reference \
  --format markdown
```

Markdown 摘要也支持：

```markdown
## 图片1
职责：角色参考
摘要：年轻女性，黑色长发
主体：女主
风格：真人写实

## 视频1
职责：待编辑视频
摘要：室内对话场景
首帧：女主站在门口
尾帧：女主停在桌边
运镜：中景平稳跟拍
```

API `content` JSON 映射示例：

```bash
python tools/seedance_prompt_optimizer.py optimize --format json <<'JSON'
{
  "content": [
    {"type": "text", "text": "asset-img-001和asset-vid-001一起生成，镜头1：图片1走向镜头，参考视频1的动作。"},
    {"type": "image_url", "image_url": {"url": "asset-img-001"}, "role": "reference_image"},
    {"type": "video_url", "video_url": {"url": "asset-vid-001"}, "role": "reference_video"}
  ]
}
JSON
```

官方规则增强示例：

```text
断句防歧义：把 @图片1跑向@图片2 改为 @图片1（女主）跑向@图片2（男主）。
单镜头单运镜：不要在同一镜头同时写“推镜、横移、环绕”。
长图/九宫格：拆分成单图后分别写 @图片1、@图片2、@图片3 的职责。
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
