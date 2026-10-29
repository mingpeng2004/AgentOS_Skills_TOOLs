---
name: visual-asset-production
description: "报告与演示文稿的示意图生产方法：实景概念渲染底图 + 程序化矢量标注层，两层分工、底图禁字、文字筛查闸门、压缩与版式约束；含 DFM/设计规范配图模式（三条底图路线 + 要点 + 机理理由 + 失败模式 + 八道门禁）。用于任何需要场景图/示意图/封面主视觉/方向扉页配图的交付物；图表、流程图、动图仍按 VISUAL-ASSET-STANDARD.md 既有章节执行。"
metadata:
  version: "1.2.0"
---

# 视觉资产生产（示意图默认水准）

> 用户裁决（2026-10-23）：报告配图若达不到**实景概念渲染**水准，视为未完成。
> 用户裁决（2026-10-25）：**DFM / 设计规范章节的配图**按同一水准沉淀为标准能力。
> 细则以 `${AGENTOS_HOME}\protocols\VISUAL-ASSET-STANDARD.md` §6 为准。

## 0. 一句话

**示意图 = 生成式实景概念渲染（底图） + 程序化矢量标注层（信息层）。**
底图负责「形象逼真」，矢量层负责「可审校」。两者缺一，图就不合格。

## 1. 两条模式（先选对路，再动手）

| 模式 | 底图 | 回答什么问题 | 工具 |
|---|---|---|---|
| **A. 创意实景** | 生成式手绘淡彩实景（**零文字零人脸**） | "这个创意/装置做出来长什么样" | `text_screen.py` → `overlay_compose.py` |
| **B. 设计规范 / DFM** | 三条底图路线（下表） | "这条规范的几何关系是什么、为什么这么定" | `iso_render.py` → `dfm_panel.py` |

> 模式 B 也可用生成式实景底图（塑胶 DFM 章节两种都用了）。**判据口**：
> 要表达"外观与实景"走 A，要表达"几何与尺寸关系"走 B。
> 要表达**精确数值关系**的图，两条都不走 —— 那是数据图表（`VISUAL-ASSET-STANDARD.md` §3）。

### 1.1 DFM 模式下的三条底图路线（协议 §6.6.2）

| 路线 | 对应协议 | 合格判据 | 工具 |
|---|---|---|---|
| **B1 实景概念渲染** | §6.6.2 A | 底图零文字零人脸；标注层由程序叠加 | `text_screen.py` → `overlay_compose.py` |
| **B2 带填充的工程剖面 / 等轴测实体** | §6.6.2 B | **有填充的实体**（剖面线或三面受光）+ 制图式尺寸线与引出标注 + 接地阴影 | `iso_render.py` |
| **B3 符号关系图** | §6.6.2 C | 画面里**没有零件**；表达的是参考线高差 / 曲线 / 力矢量 / 区间 | 程序化绘制 |

**全库只有一种图不合格：骨架图** —— 用轮廓线勾了个零件、标了文字标签，
而它所讲的关系本可以由 B1 或 B2 表达。

> **判别口**：这张图里有没有**零件**？
> 有零件却没有填充 ⇒ 骨架图（不合格）；根本没有零件，画的是参考线或曲线 ⇒ B3（合格）。
>
> **不要拿"受光三面"当唯一标准**：金属制程库 118 个带填充的工程剖面
> （剖面线 + 引出线 + 尺寸线）都是合格的 B2。套"必须受光三面"会把它们全判不合格。
>
> **审计实测**（金属制程库 240 cell）：B1 形态 120 个、B2 形态 118 个、B3 形态 2 个。

## 2. 三条铁律

1. **底图禁字**：生成图里**不得出现任何文字、数字、字母、水印、标签**。
   文字与数值一律由矢量层叠加 —— 只有程序画出来的字才可审校、才不臆造。
2. **文字筛查是硬闸门**：出图后必须跑 `scripts/text_screen.py` 并**逐张目检**。
   生成模型会在展板、表格纸、书本、便签上自己写英文（乱码/伪手写），一律重做。
3. **信息层只许来自事实源**：标题、副题、关键部件、关键判据、要点、理由、失败模式
   全部抽自已审的事实源，**不另起一套口径**；与画面不一致的，用 OVERRIDE 表
   **人工校准**并留痕。

## 3. 模式 A 工作流（创意实景）

| 步 | 动作 | 产物 | 失败处理 |
|---|---|---|---|
| 1 | 写主体描述 | 每图 60-110 词，含**数量**与**位置** | 出现"展板/表格/书本/标签"→ 改成空白载体或去掉 |
| 2 | 生成底图 | `raw/<dkey>.png`（2K，16:9 / 21:9 / 3:4） | 单批上限 5 张，超限静默返回 0 成功 |
| 3 | **文字筛查** | `_text_hits.json` + 命中裁切图 | 有文字 → 改主体描述 → 回到第 2 步 |
| 4 | 目检 | 逐张确认内容对应、无文字、无人脸 | 不合格 → 重生成，不将就 |
| 5 | 合成 | `assets/diagrams/<dkey>_<lang>.jpg` | 信息层与画面不符 → 写 OVERRIDE，不改口径 |
| 6 | 压缩与排版 | JPEG q94 / 4:4:4 | 见 `references/qa-gates.md` §3 |

## 4. 模式 B 工作流（设计规范 / DFM）

| 步 | 动作 | 产物 | 失败处理 |
|---|---|---|---|
| 1 | 写规范条目 | 契约 JSON：要点 / 理由 / **失败模式**（中英） | 缺理由或失败模式 → 门禁拦下 |
| 2 | 画底图 | 按 §1.1 选一条路线 → 底图 PNG | **骨架图**（勾轮廓 + 文字标签）→ 改成 B2 的带填充实体 |
| 3 | 装配面板 | `dfm_panel.py --spec … --outdir …` | 实体压文字列 → `check_layout()` 拦下 |
| 4 | **过门禁** | 覆盖率 / 双语纯度 / 数值自洽 / **失败模式可溯** / **锚点落墨** / 判定完整 | 见 §4.1 |

**一条规范 = 一张图 + 要点清单 + 机理理由 + 失败模式**，缺一不可。
理由段讲**机理**（为什么会这样），不是复述规则 —— 这是 DFM 配图的价值所在。

**失败模式必须在理由段里被点明**：只写在要点里，读者读完理由仍然不知道做错会怎样。
更稳的做法是把失败模式**逐字**写进事实源文件，门禁会核对它是事实源的逐字子串
（§9.13：渲染值不得自撰）。

### 4.1 门禁清单（`dfm_panel.py --gate` 会逐条查）

| # | 门禁 | 坏情形 |
|---|---|---|
| 1 | 覆盖率 | 声明条数 ≠ 实际条数 |
| 2 | 双语纯度 | 英文侧含中文 —— **含页脚声明行** |
| 3 | 数值自洽 | 面板里的数字在事实源里找不到出处 |
| 4 | 失败模式可溯 | 失败模式不是事实源的逐字子串 |
| 5 | 锚点落墨 | 引出线的锚点落在空白处 |
| 6 | 判定完整 | 底图没有显式声明 good / bad / neutral |
| 7 | 双语要点/理由/失败模式齐备 | 缺中英标题、理由或失败模式 |
| 8 | 版面守卫 | 实体越界、侵入文字列，或右列文本溢出面板 |

### 4.2 多面板与左右顺序

- 一条规范可并置多个底图（`bodies[]`），**好一律在左、坏一律在右**由装配器在加载期统一，
  不逐图手写。
- 判定必须**显式声明**（good / bad / neutral）。**未声明 ≠ 中立**：缺判定直接判不合格。
- 三面板及以上若是**参数序列**（过小 / 合适 / 过大），好的在中间是语义正确的，
  **不要强排** —— 判别口：这几个面板之间是"对与错"还是"参数由小到大"？

## 5. 快速开始

```bash
cd <project>/build

# 模式 A：创意实景
python art/subjects.py --init 40          # 从内容源导出主体描述骨架
python art/gen.py 5                       # 批量生成底图（5 张一批，可断点续跑）
python art/text_screen.py --raw raw        # 文字筛查闸门（退出码非 0 = 有疑似文字）
python art/sheet.py raw                    # 接触印相，供逐张目检
python art/annotate.py                     # 合成成品图（中英各一套）

# 模式 B：设计规范 / DFM
python <skill>/scripts/iso_render.py --demo wall_iso.png   # 等轴测实体（照着改几何）
python <skill>/scripts/dfm_panel.py --spec dfm_spec.json --facts facts.md --outdir figures
python <skill>/scripts/dfm_panel.py --spec dfm_spec.json --facts facts.md --gate   # 只过门禁
```

## 6. 引用

- 两层法细节、底图规格、覆写机制：[references/pipeline.md](references/pipeline.md)
- 默认风格基线、配色 token、prompt 模板：[references/style-library.md](references/style-library.md)
- **实景底图 brief 写法（40 条真实描述统计出的硬规则）**：[references/scene-brief-grammar.md](references/scene-brief-grammar.md)
- **DFM 面板语法（版面分栏 / 四段文案 / 门禁）**：[references/dfm-panel-grammar.md](references/dfm-panel-grammar.md)
- **等轴测原语库用法**：[references/iso-primitives.md](references/iso-primitives.md)
- 文字筛查、压缩、版式约束、负控制：[references/qa-gates.md](references/qa-gates.md)
- 主体描述模板：[assets/templates/subject-template.md](assets/templates/subject-template.md)
- 信息层模板：[assets/templates/info-layer-template.json](assets/templates/info-layer-template.json)
- **DFM 规范契约模板**：[assets/templates/dfm-spec-sheet.json](assets/templates/dfm-spec-sheet.json)
- **面板样板**：[assets/samples/dfm-panel-sample-zh.png](assets/samples/dfm-panel-sample-zh.png)

## 7. 常见失败及处理

- **模型在图里写字**：不是加一句 "no text" 就行 —— 把**可写字的载体**从画面里拿掉
  （"blank unmarked sheet" 而不是 "a sheet with notes"），再叠全局"任何纸张/卡片/屏幕/板面必须完全空白"。
- **画面与标签对不上**：旧图规格讲的是"三种做法对比"，新画面是一个真实场景 → 用 OVERRIDE 人工校准，
  **不另起一套口径**。
- **批量生成静默返回 0 张**：单批上限 5 张，超过会被吞；分批跑。
- **底图与信息层都要压缩**：PNG 存连续调图像要 1.9MB，JPEG q94 只要 0.37MB。
  改格式前先做像素级差分验证（全图最大差 ≤24/255 即视觉无差）。
- **骨架图当成图交了**：线框 = AI 味。用 `iso_render.py` 画**带填充的实体**
  （剖面线或三面受光 + 接地阴影 + 制图标注）。但注意判别口 ——
  **图里根本没有零件**、画的是参考线或曲线的（符号关系图），是合格的，不是骨架图。
- **理由段写成要点的复述**：理由必须讲机理（收缩速率差、冷却先后、纤维取向、应力集中）。
- **失败模式只藏在要点里**：必须在理由段里被点明，否则读者读完理由仍不知道做错会怎样。
- **数值随手写**：走 `dfm_panel.py --gate`，事实源里没有的数字会被拦下。
- **失败模式自己编一句**：门禁要求它是事实源的**逐字子串** —— 要改写就先改事实源。
- **英文版页脚还是中文**：页脚声明行必须双语，门禁会查 `footer_en` 里的中文字符。
- **引出线指到空纸上**：锚点要**实测**（画图时返回坐标），门禁会核对锚点像素是否有墨迹。
- **把三面板参数序列强排成好左坏右**：好的在中间是语义正确的（§4.2）。


Public portability note: historical batch-size and project-image counts are not current provider limits or performance guarantees. Inspect the selected provider. Optional image scripts require their separately declared dependencies; none are installed automatically.
