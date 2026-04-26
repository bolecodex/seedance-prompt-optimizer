---
name: seedance-prompt-optimizer
description: 优化、改写、检查、诊断、模板化和结构化 Seedance 2.0 视频生成提示词。当用户要求优化 Seedance 提示词、将松散文本改成分镜结构、检查多模态参考绑定、修复编辑/延长任务措辞，或创建 Seedance 2.0 提示词模板时使用。
---

# Seedance 提示词优化器

使用本技能将松散的 Seedance 2.0 视频提示词改写为结构清晰、可执行的提示词。最高优先级规则来自 `references/seedance-rules.md`；该文件基于仓库文档整理，规则冲突时以《Seedance 2.0提示词常见问题与处理指南》为准。

## 工作流程

1. 判断任务类型：`reference`、`edit`、`extend` 或 `combo`。如果编辑或延长任务提到视频，避免写 `参考视频N`，改用 `严格编辑视频N` 或 `延长视频N`。
2. 检查上传或提示词中提到的素材数量，要求使用编号绑定：`图片N`、`视频N`、`音频N`。Asset ID 不能替代这些编号引用。
3. 用户直接发来一段提示词时，先用本技能进行优化：优先返回 `【全局设定】/【参考素材说明】/【镜头N】/【全局约束】` 结构化提示词，再返回简短诊断。
4. 如需要确定性检查或模板，运行随技能附带的 CLI；在 ArkClaw/OpenClaw 中使用 `{baseDir}` 定位当前技能目录：

```bash
python {baseDir}/scripts/seedance_prompt_optimizer.py lint --input prompt.txt
python {baseDir}/scripts/seedance_prompt_optimizer.py optimize --input prompt.txt --output optimized.txt
python {baseDir}/scripts/seedance_prompt_optimizer.py template --task reference
```

5. 只有缺失信息无法推断时才列出待确认问题；不要因为缺少可选素材说明而停止优化。

## 输出标准

生成提示词时使用这些部分：

- `【全局设定】`：任务类型、已知时长/比例、具体风格、场景、光影、色调和动态顺序。
- `【参考素材说明】`：每个图片、视频、音频都要有编号和职责说明。
- `【镜头N】`：按镜头顺序写景别/机位/运镜、主体/动作、场景/光影和当前镜头音频。
- `【全局约束】`：按需补充字幕/文字、logo/水印、人物 ID 稳定、重复同脸人物、动作、闪烁和音频约束。

## 资源

- 手动优化或解释诊断原因时，读取 `references/seedance-rules.md`。
- 需要规则检查、自动改写、JSON 输出或模板时，使用 `{baseDir}/scripts/seedance_prompt_optimizer.py`。
- 该 CLI 是自包含脚本；即使只把本技能目录复制到 `~/.openclaw/skills/seedance-prompt-optimizer`，也能独立运行。
