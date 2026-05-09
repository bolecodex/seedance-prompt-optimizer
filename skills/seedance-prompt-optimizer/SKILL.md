---
name: seedance-prompt-optimizer
description: 优化、改写、检查、诊断、模板化和结构化 Seedance 2.0 视频生成提示词。当用户要求优化 Seedance 提示词、将松散文本改成分镜结构、检查多模态参考绑定、修复编辑/延长任务措辞，或创建 Seedance 2.0 提示词模板时使用。
---

# Seedance 提示词优化器

使用本技能将松散的 Seedance 2.0 视频提示词改写为结构清晰、可执行的提示词。最高优先级规则来自 `references/seedance-rules.md`；该文件已汇总 Seedance 2.0 常见问题、官方提示词指南和本工具的自动化规则。

## 工作流程

1. 如果用户只提出高层视频需求而没有具体提示词（例如“生成一个女孩跳舞的视频”），先进入引导模式，询问主体、动作、场景、光影色调、运镜、视觉风格、时长比例和约束条件；不要直接编造关键细节。
2. 判断任务类型：`reference`、`edit`、`extend` 或 `combo`。轨道补齐/补音频/补口型归入 `edit`；向前延长/前序生成归入 `extend`。如果编辑或延长任务提到视频，避免写 `参考视频N`，改用 `严格编辑视频N`、`延长视频N` 或 `向前延长视频N`。
3. 检查上传或提示词中提到的素材数量，要求使用编号绑定：`图片N`、`视频N`、`音频N`。Asset ID 不能替代这些编号引用；如果用户粘贴 Seedance API `content` JSON，可让 CLI 自动按出现顺序映射素材。
4. 如用户上传了图片、视频或音频，先使用宿主多模态能力理解附件，生成结构化素材摘要；CLI 不直接读取真实媒体文件，也不联网调用模型。若发现长图、九宫格、拼图、多视图参考，提醒拆成单图后再绑定。
5. 多图或多人场景中，如人物、站位、首帧/尾帧、素材职责不明确，优先向用户确认；不要静默猜测。若信息已足够，则直接优化，不因可选信息缺失阻塞。
6. 用户直接发来一段提示词时，先用本技能进行优化：默认返回三段论格式：`整体设定：`、`时间片分镜：`、`风格画质约束：`，再返回简短诊断、优化问题和相关原则。
7. 如需要确定性检查、自动改写、JSON 输出或模板，运行随技能附带的 CLI；在 ArkClaw/OpenClaw 中使用 `{baseDir}` 定位当前技能目录：

```bash
python {baseDir}/scripts/seedance_prompt_optimizer.py lint --input prompt.txt
python {baseDir}/scripts/seedance_prompt_optimizer.py optimize --input prompt.txt --output optimized.txt
python {baseDir}/scripts/seedance_prompt_optimizer.py optimize --input prompt.txt --media-analysis media.json
python {baseDir}/scripts/seedance_prompt_optimizer.py template --task reference
```

8. 如果宿主环境不能把素材摘要写成文件，则直接把摘要内容融入手动优化结果，不要阻塞；只有缺失信息无法推断时才列出待确认问题。

## 素材理解摘要

推荐让宿主多模态模型按 JSON 生成摘要，再传给 CLI 的 `--media-analysis`。Markdown 也可用，标题写成 `## 图片1`、`## 视频1`、`## 音频1`，字段使用 `职责：`、`摘要：`、`主体：`、`场景：`、`风格：`、`首帧：`、`尾帧：`、`运镜：`、`动作：`、`音色：`、`情绪：`、`节奏：`、`约束：`。

```json
{
  "images": {"1": {"role": "角色参考", "summary": "年轻女性，黑色长发", "subjects": ["女主"], "style": "真人写实"}},
  "videos": {"1": {"role": "待编辑视频", "summary": "室内对话场景", "start_frame": "女主站在门口", "end_frame": "女主停在桌边", "motion": "中景平稳跟拍"}},
  "audios": {"1": {"role": "音色参考", "summary": "温柔清亮青年女声", "voice": "青年女声，清亮", "emotion": "温柔克制", "rhythm": "平稳"}}
}
```

## 输出标准

生成提示词时使用三段论格式：

- `整体设定：` 写世界观/场景、主体外观、空间环境、光影色调、情绪氛围，以及素材职责声明。
- `时间片分镜：` 下使用 `镜头1:`、`镜头2:` 连续句式，每个镜头写景别/机位/镜头、主体动作、场景光影和配音/音效。每个镜头只保留一种主要运镜；`@图片N`、`@视频N` 后尽量跟角色名或名词解释，例如 `@图片1（女主）`。
- `风格画质约束：` 写视觉风格、动作稳定、字幕/文字、logo/水印、BGM/音效等全局约束。
- 不默认输出字段化的 `【镜头1】`、`- 景别/机位/镜头：`、`- 主体/动作：` 这类模板。

## 资源

- 手动优化或解释诊断原因时，读取 `references/seedance-rules.md`。
- 需要规则检查、自动改写、JSON 输出或模板时，使用 `{baseDir}/scripts/seedance_prompt_optimizer.py`。
- 该 CLI 是自包含脚本；即使只把本技能目录复制到 `~/.openclaw/skills/seedance-prompt-optimizer`，也能独立运行。
