# Seedance Prompt Optimizer

面向 Seedance 2.0 的提示词优化技能。普通用户只需要在火山 ArkClaw 企业版的 Hermes Agent 或 Trae 里发送一句需求，技能会把粗糙想法改成结构化、可执行的 Seedance 提示词。

规则优先级：以技能内 `skills/seedance-prompt-optimizer/references/seedance-rules.md` 为准；该文件已汇总 Seedance 2.0 常见问题、官方提示词指南和本工具的自动化规则。

## 普通用户最快用法

你不需要打开终端，也不需要记 CLI 参数。确认技能已安装后，直接在对话里发送需求即可。

### 入口 1：火山 ArkClaw 企业版

1. 打开火山 ArkClaw 企业版。
2. 进入或选择 Hermes Agent。
3. 确认已加载 `seedance-prompt-optimizer` 技能。
4. 上传素材，或直接发送你的 Seedance 视频需求。
5. 复制返回的“优化后提示词”去 Seedance 使用。

### 入口 2：Trae

1. 打开 Trae。
2. 打开或导入本项目。
3. 确认项目里存在 `skills/seedance-prompt-optimizer/SKILL.md`。
4. 新建对话，发送下面的话术。

### 一句话模板

推荐开头写一句：

```text
请使用 seedance-prompt-optimizer 优化下面这段 Seedance 2.0 提示词：
```

然后粘贴你的原始想法、提示词，或上传图片/视频/音频素材。

更完整的小白教程见：[USER_GUIDE.md](USER_GUIDE.md)。

## 直接复制的使用示例

### 1. 只有一个粗略想法

你可以直接发：

```text
请使用 seedance-prompt-optimizer 帮我优化：
我想生成一段江南雨巷里的视频，一个女孩撑伞走路，氛围感电影感，画面好看点，不要背景音乐。
```

适合：你只有一句大概想法，希望技能帮你补成可执行的 Seedance 提示词。

如果信息太少，技能会先问你几个关键问题，比如角色长相、场景、风格、时长和比例。

### 2. 已经写了一段提示词

```text
请使用 seedance-prompt-optimizer 优化这段 Seedance 提示词：
氛围感电影感，一个女孩在江南雨巷里走路，镜头好看点，不要背景音乐。时长 6s，比例 9:16。
```

技能会返回：

- 优化后的三段论提示词
- 原提示词的问题
- 使用到的优化原则
- 如果需要，会提醒你补充哪些信息

### 3. 上传图片做角色参考

```text
请使用 seedance-prompt-optimizer 优化：
我上传了 1 张图片，图片1是女主角色参考。
请生成 6 秒 9:16 视频：女主走在江南雨巷里，撑着油纸伞，轻声说：“今晚雨真大。”
风格想要真人写实、冷青色雨夜光影，不要字幕，不要水印。
```

适合：你有角色图，希望锁定人物外观。

### 4. 图片 + 视频 + 音频多参考

```text
请使用 seedance-prompt-optimizer 优化：
我上传了 2 张图片、1 段视频、1 段音频。
图片1是女主角色参考，图片2是江南雨巷场景参考。
视频1只参考慢速推镜和横移运镜，不要复刻视频里的人物和场景。
音频1参考温柔清亮青年女声的音色。

请生成 6 秒 9:16 视频：女主走在图片2的雨巷里，参考视频1的运镜，使用音频1的音色说：“今晚雨真大。”
不要字幕，不要 logo，不要水印，不要背景音乐。
```

适合：Seedance 全能参考、多参考生视频、角色图 + 场景图 + 运镜视频 + 音色参考。

### 5. 严格编辑视频

```text
请使用 seedance-prompt-optimizer 优化：
我上传了视频1，视频1是待编辑视频。
请严格编辑视频1：把女主身上的蓝色外套改成红色外套。
其余人物、动作、背景、构图、光线、镜头节奏都保持不变。
```

适合：局部替换、元素增删改、瑕疵修复。

注意：编辑视频时，不要写“参考视频1”，要写“严格编辑视频1”。

### 6. 视频向后延长

```text
请使用 seedance-prompt-optimizer 优化：
我上传了视频1，视频1是上一段成片。
请延长视频1，生成视频1之后自然发生的内容。
女主继续沿雨巷向前走，保持角色外观、场景、光影、运镜和情绪连续。
时长 6 秒。
```

适合：续写剧情、连续长镜头、文戏延长。

### 7. 向前延长 / 前序生成

```text
请使用 seedance-prompt-optimizer 优化：
我上传了视频1，视频1是当前片段。
请向前延长视频1，生成视频1之前自然发生的内容。
女主从巷口走入画面，最后自然衔接到视频1开头。
时长 6 秒。
```

适合：想补一个“前面发生了什么”的镜头。

### 8. 轨道补齐 / 补音频 / 补口型

```text
请使用 seedance-prompt-optimizer 优化：
我上传了视频1。
请给视频1补全音频轨道和口型。
保持原视频主体、动作、场景、构图、光影和时长不变。
```

适合：补声音、补口型、补音轨、补目标轨道。

### 9. 多人 / 多图场景

```text
请使用 seedance-prompt-optimizer 优化：
我上传了 3 张图片。
图片1是女主，图片2是男主，图片3是客厅场景。
请生成 8 秒 16:9 视频：女主站在画面左侧，男主坐在画面右侧沙发上，两人发生争吵。
女主看向男主说：“你到底还想瞒我多久？”
要求真人写实，室内暖光，不要字幕，不要 logo，不要水印。
```

适合：多人对话、短剧、站位容易混乱的画面。

### 10. 长图 / 九宫格参考

```text
请使用 seedance-prompt-optimizer 帮我检查：
我有一张九宫格角色参考图，想直接作为图片1生成视频。这样写会不会有问题？
```

技能会提醒：九宫格、长图、多视图容易让模型混淆，建议拆成单张图片后分别绑定。

## 使用小抄

### 常用开头

```text
请使用 seedance-prompt-optimizer 优化：
```

```text
请使用 seedance-prompt-optimizer 检查这段提示词有什么问题：
```

```text
请使用 seedance-prompt-optimizer 把下面的想法改成 Seedance 2.0 可用提示词：
```

### 素材编号怎么写

```text
图片1是女主角色参考。
图片2是场景参考。
视频1只参考运镜和动作节奏。
音频1参考音色和情绪。
```

### 不推荐的写法

```text
参考视频1进行编辑。
asset-20260324135118-xxxx 是女主。
@图片1跑向@图片2。
一个镜头里同时推镜、横移、环绕。
```

### 推荐的写法

```text
严格编辑视频1，其余内容保持不变。
图片1是女主角色参考。
@图片1（女主）跑向 @图片2（男主）。
镜头采用中景缓慢推镜。
```

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

## 高级用法：CLI

普通用户不用看这里，优先在火山 ArkClaw 企业版的 Hermes Agent 或 Trae 里直接使用技能。CLI 适合批量处理、自动化检查、接入脚本或调试技能。

OpenClaw/ArkClaw 会加载 `<workspace>/skills` 和 `~/.openclaw/skills` 中的技能，工作区技能优先。参考：

- [OpenClaw Skills](https://openclaw.cc/tools/skills)
- [openclaw skills 命令](https://openclaw.cc/cli/skills)
- [ArkClaw 介绍](https://arkclaw.lol/)

一键安装：

```bash
bash <(curl -fsSL https://gitee.com/bolecodex/seedance-prompt-optimizer/raw/main/scripts/setup-gitee.sh)
```

作为工作区仓库安装：

```bash
git clone https://github.com/bolecodex/seedance-prompt-optimizer.git
cd seedance-prompt-optimizer
openclaw skills list
openclaw skills info seedance-prompt-optimizer
```

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

CLI 示例：

```bash
printf '%s' '氛围感电影感，女孩在雨巷里走路，镜头好看点，不要背景音乐。' \
  | python tools/seedance_prompt_optimizer.py optimize --duration 6 --ratio 9:16 --format markdown
```

带素材理解摘要：

```bash
python tools/seedance_prompt_optimizer.py optimize \
  --input prompt.txt \
  --media-analysis media.json \
  --task reference \
  --format markdown
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
