# Seedance Prompt Optimizer

面向 Seedance 2.0 的提示词优化 CLI 与 ArkClaw/OpenClaw Skill。用户把自己写的提示词发给 ArkClaw，ArkClaw 触发 `seedance-prompt-optimizer` 技能后，返回结构化、可执行的优化提示词和简短诊断。

规则优先级：以技能内 `skills/seedance-prompt-optimizer/references/seedance-rules.md` 为准；该文件已汇总 Seedance 2.0 常见问题、官方提示词指南和本工具的自动化规则。

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

## 快速开始

只想立刻优化一段提示词，可以直接把文本从标准输入传给 `optimize`：

```bash
printf '%s' '氛围感电影感，女孩在雨巷里走路，镜头好看点，不要背景音乐。' \
  | python tools/seedance_prompt_optimizer.py optimize --duration 6 --ratio 9:16 --format markdown
```

如果已经有提示词文件：

```bash
python tools/seedance_prompt_optimizer.py optimize \
  --input prompt.txt \
  --output optimized.txt \
  --duration 6 \
  --ratio 9:16
```

只想检查问题，不改写：

```bash
python tools/seedance_prompt_optimizer.py lint --input prompt.txt --format markdown
```

生成一个可填写模板：

```bash
python tools/seedance_prompt_optimizer.py template --task reference --duration 6 --ratio 9:16
```

## 常见场景示例

### 1. 纯文本提示词优化

输入：

```text
氛围感电影感，一个女孩在江南雨巷里走路，镜头好看点，不要背景音乐。
```

命令：

```bash
printf '%s' '氛围感电影感，一个女孩在江南雨巷里走路，镜头好看点，不要背景音乐。' \
  | python tools/seedance_prompt_optimizer.py optimize --duration 6 --ratio 9:16 --format markdown
```

适合：用户只有一个粗略想法，想先得到三段论结构化提示词。

### 2. 图片 + 视频 + 音频多参考生成

输入：

```text
图片1是女主，图片2是江南雨巷场景，视频1是慢速推镜参考，音频1是温柔女声音色参考。氛围感电影感，女主走在图片2的雨巷里，参考视频1的运镜，使用音频1说：今晚雨真大。
```

命令：

```bash
printf '%s' '图片1是女主，图片2是江南雨巷场景，视频1是慢速推镜参考，音频1是温柔女声音色参考。氛围感电影感，女主走在图片2的雨巷里，参考视频1的运镜，使用音频1说：今晚雨真大。' \
  | python tools/seedance_prompt_optimizer.py optimize \
      --task reference \
      --images 2 \
      --videos 1 \
      --audios 1 \
      --duration 6 \
      --ratio 9:16 \
      --format markdown
```

适合：Seedance 全能参考、多参考生视频、角色图 + 场景图 + 运镜视频 + 音色参考。

### 3. 带素材理解摘要的多模态优化

先让宿主多模态模型或人工写一个 `media.json`：

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

再运行：

```bash
python tools/seedance_prompt_optimizer.py optimize \
  --input prompt.txt \
  --media-analysis media.json \
  --task reference \
  --format markdown
```

适合：已经上传了真实图片/视频/音频，希望把素材内容更准确地写进提示词。

Markdown 摘要也支持，保存为 `media.md` 即可：

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

```bash
python tools/seedance_prompt_optimizer.py optimize \
  --input prompt.txt \
  --media-analysis media.md \
  --format markdown
```

### 4. 严格编辑视频

输入：

```text
视频1是待编辑视频。把视频1中女主的蓝色外套改成红色外套，其余人物、动作、背景和光线保持不变。
```

命令：

```bash
printf '%s' '视频1是待编辑视频。把视频1中女主的蓝色外套改成红色外套，其余人物、动作、背景和光线保持不变。' \
  | python tools/seedance_prompt_optimizer.py optimize --task edit --videos 1 --format markdown
```

适合：局部替换、元素增删改、瑕疵修复。编辑任务里不要写 `参考视频1`，工具会提示并修正这类措辞风险。

### 5. 视频向后延长

输入：

```text
视频1是上一段成片。延长视频1，生成视频1之后自然发生的内容，女主继续沿雨巷向前走，保持角色、场景、光影和运镜连续。
```

命令：

```bash
printf '%s' '视频1是上一段成片。延长视频1，生成视频1之后自然发生的内容，女主继续沿雨巷向前走，保持角色、场景、光影和运镜连续。' \
  | python tools/seedance_prompt_optimizer.py optimize --task extend --videos 1 --duration 6 --format markdown
```

适合：续写剧情、连续长镜头、文戏延长。

### 6. 向前延长 / 前序生成

输入：

```text
视频1是当前片段。生成视频1之前的内容，女主从巷口走入画面，最后自然衔接到视频1开头。
```

命令：

```bash
printf '%s' '视频1是当前片段。生成视频1之前的内容，女主从巷口走入画面，最后自然衔接到视频1开头。' \
  | python tools/seedance_prompt_optimizer.py optimize --task extend --videos 1 --duration 6 --format markdown
```

如果 `media.json` 里有 `start_frame`，工具会把首帧作为衔接锚点写进分镜。

### 7. 轨道补齐 / 补音频 / 补口型

输入：

```text
给视频1补全音频轨道和口型，保持原视频主体、动作、场景、构图、光影和时长不变。
```

命令：

```bash
printf '%s' '给视频1补全音频轨道和口型，保持原视频主体、动作、场景、构图、光影和时长不变。' \
  | python tools/seedance_prompt_optimizer.py optimize --videos 1 --format markdown
```

工具会自动把这类需求判定为 `edit`。

### 8. Seedance API `content` JSON 自动映射

如果你从接口日志里复制了完整 `content` JSON，可以直接传给 CLI：

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

工具会按非文本素材出现顺序映射：

```text
asset-img-001 -> 图片1
asset-vid-001 -> 视频1
```

### 9. 官方规则诊断示例

```text
断句防歧义：把 @图片1跑向@图片2 改为 @图片1（女主）跑向@图片2（男主）。
单镜头单运镜：不要在同一镜头同时写“推镜、横移、环绕”。
长图/九宫格：拆分成单图后分别写 @图片1、@图片2、@图片3 的职责。
```

可以用 `lint` 快速检查：

```bash
printf '%s' '镜头1：@图片1跑向@图片2，镜头缓慢推镜并横移同时环绕。' \
  | python tools/seedance_prompt_optimizer.py lint --images 2 --format markdown
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
