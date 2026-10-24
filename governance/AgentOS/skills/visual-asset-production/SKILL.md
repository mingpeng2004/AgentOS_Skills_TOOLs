---
name: visual-asset-production
description: "报告与演示文稿的示意图生产方法：实景概念渲染底图 + 程序化矢量标注层，两层分工、底图禁字、文字筛查闸门、压缩与版式约束。用于任何需要场景图/示意图/封面主视觉/方向扉页配图的交付物；图表、流程图、动图仍按 VISUAL-ASSET-STANDARD.md 既有章节执行。"
metadata:
  version: "1.0.0"
---

# 视觉资产生产（示意图默认水准）

> 用户裁决（2026-10-23）：报告配图若达不到**实景概念渲染**水准，视为未完成。
> 本 Skill 是该水准的可执行实现，细则以
> `${AGENTOS_HOME}\protocols\VISUAL-ASSET-STANDARD.md` §6 为准。

## 0. 一句话

**示意图 = 生成式实景概念渲染（底图） + 程序化矢量标注层（信息层）。**
底图负责「形象逼真」，矢量层负责「可审校」。两者缺一，图就不合格。

## 1. 三条铁律

1. **底图禁字**：生成图里**不得出现任何文字、数字、字母、水印、标签**。
   文字与数值一律由矢量层叠加 —— 只有程序画出来的字才可审校、才不臆造。
2. **文字筛查是硬闸门**：出图后必须跑 `scripts/text_screen.py` 并**逐张目检**。
   生成模型会在展板、表格纸、书本、便签上自己写英文（乱码/伪手写），一律重做。
3. **信息层只许来自事实源**：标题、副题、关键部件、关键判据全部抽自已审的图规格或内容源，
   **不另起一套口径**；与画面不一致的，用 OVERRIDE 表**人工校准**并留痕。

## 2. 工作流

| 步 | 动作 | 产物 | 失败处理 |
|---|---|---|---|
| 1 | 写主体描述 | `subjects.py`（每图 60-110 词，含**数量**与**位置**） | 描述里出现"展板/表格/书本/标签"→ 先改成空白载体 |
| 2 | 生成底图 | `raw/<dkey>.png`（2K，16:9 / 21:9 / 3:4） | 单批上限 5 张，超限静默返回 0 成功 |
| 3 | **文字筛查** | `_text_hits.json` + 命中裁切图 | 有文字 → 改主体描述 → 回到第 2 步 |
| 4 | 目检 | 逐张确认内容对应、无文字、无人脸 | 不合格 → 重生成，不将就 |
| 5 | 合成 | `assets/diagrams/<dkey>_<lang>.jpg` | 信息层与画面不符 → 写 OVERRIDE，不改口径 |
| 6 | 压缩与排版 | JPEG q94 / 4:4:4 | 见 `references/qa-gates.md` §3 |

## 3. 快速开始

```bash
cd <project>/build/art
python subjects.py --init 40          # 从内容源导出主体描述骨架
python gen.py 5                       # 批量生成底图（5 张一批，可断点续跑）
python text_screen.py --raw raw        # 文字筛查闸门（退出码非 0 = 有疑似文字）
python sheet.py raw                    # 接触印相，供逐张目检
python annotate.py                     # 合成成品图（中英各一套）
python pack.py                         # 封面主视觉/横幅压缩
```

## 4. 引用

- 两层法细节、底图规格、覆写机制：[references/pipeline.md](references/pipeline.md)
- 默认风格基线、配色 token、prompt 模板：[references/style-library.md](references/style-library.md)
- 文字筛查、压缩、版式约束、负控制：[references/qa-gates.md](references/qa-gates.md)
- 主体描述模板：[assets/templates/subject-template.md](assets/templates/subject-template.md)
- 信息层模板：[assets/templates/info-layer-template.json](assets/templates/info-layer-template.json)

## 5. 常见失败及处理

- **模型在图里写字**：不是加一句 "no text" 就行 —— 把**可写字的载体**从画面里拿掉
  （"blank unmarked sheet" 而不是 "a sheet with notes"），再叠全局"任何纸张/卡片/屏幕/板面必须完全空白"。
- **画面与标签对不上**：旧图规格讲的是"三种做法对比"，新画面是一个真实场景 → 用 OVERRIDE 人工校准，
  **不另起一套口径**。
- **批量生成静默返回 0 张**：单批上限 5 张，超过会被吞；分批跑。
- **底图与信息层都要压缩**：PNG 存连续调图像要 1.9MB，JPEG q94 只要 0.37MB。
  改格式前先做像素级差分验证（全图最大差 ≤24/255 即视觉无差）。


Public portability note: historical batch-size and project-image counts are not current provider limits or performance guarantees. Inspect the selected provider. Optional image scripts require their separately declared dependencies; none are installed automatically.
