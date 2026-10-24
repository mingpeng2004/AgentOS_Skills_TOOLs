# 默认风格基线与配色

> 没有项目自有视觉语言时的**默认水准**。项目已有品牌/视觉语言时以项目为准，
> 但"两层分工、底图禁字、筛查闸门"三条铁律不豁免。

## 1. 默认风格模板（英文，直接拼进 prompt）

```
Technical concept illustration for a school science project. Subject: {subject}
Style: hand-drawn editorial technical illustration, warm off-white paper background,
soft natural daylight, muted low-saturation earth-tone palette of sand bronze, moss green,
brick red and warm grey, delicate ink linework with soft painted shading, gentle soft
shadows, shallow depth of field, calm and precise, high detail on the handmade student
device, no text, no letters, no numbers, no labels, no watermark, no visible faces.
Every sheet of paper, card, notebook, screen, board and label anywhere in the scene is
completely blank and unmarked: nothing written, printed, handwritten, engraved or
labelled on it, and no chart, table, caption or diagram carrying symbols on it
```

**为什么是这一套**：暖白纸底 + 细墨线 + 低饱和土色 = "技术编辑插画"，
读起来像专业杂志的技术插页，既不塑料、也不像玩具渲染；信息带用同一色系叠上去才不打架。

## 2. 配色 token（与版式层同源，不另抄）

默认低饱和土色三色 + 中性灰。**不设科技蓝默认**：

| 用途 | hex | 说明 |
|---|---|---|
| 砂铜 primary | `#A8895F` | 标题强调、主色条 |
| 苔绿 accent | `#6E8B74` | 次级强调、"可以" |
| 砖红 alert | `#A64634` | 风险、截止、警示 |
| 暖灰 muted | `#636F77` | 注释、图注、免责行 |
| 纸面 paper | `#FBF9F5` | 信息带底 |
| 分隔 rule | `#E8E4DD` | 细线 |
| 正文 ink | `#1F2224` | 标题 |

**正文对比度 ≥ 4.5:1**；高饱和色只用于极小面积强调。

> **迁移陷阱**：暗底 hex 直接搬到白底会整体塌（实测苔绿 6.5:1 → 1.8:1，读不出来且不报错）。
> 换配色是**迁移工程**不是改几个 hex：内容里写死的 hex 会架空主题，
> 须先迁成 token 名再改 token。

## 3. 主体描述模板

每图一条，60-110 词，只写"画什么"，风格由模板统一附加：

```
<一句总述：场景 + 主体 + 环境光>，
<关键部件 1：数量 + 形态 + 位置>，
<关键部件 2：数量 + 形态 + 位置>，
<关键部件 3：数量 + 形态 + 位置>，
<氛围：精确、手工、有学生痕迹>
```

**必须写清的三件事**：
1. **数量**（`two photoresistors` 而不是 `photoresistors`）
2. **位置**（`on the lower left` / `at the far edge`）
3. **载体是否可写字**（能写的一律改写成"空白载体"）

## 4. 反面样例（会踩坑的写法）

| 写法 | 会发生什么 | 改法 |
|---|---|---|
| "a display board with labels" | 模型自己写英文标签 | "a blank unmarked board" |
| "a notebook with notes" | 伪手写 | "a closed plain notebook with a blank unmarked cover" |
| "a printed table" | 表格 + 列标题 + 乱码 | "a plain empty wooden board" / 直接不写表 |
| "a student drawing" | 清晰人脸 | "a student seen strictly from behind over the shoulder ... no face no eyes no profile" |
| "several sensors" | 数量随机 | "three sensors" |

## 5. 跨题材复用

同一套模板可覆盖：科普原理图、赛事方案图、产品概念图、流程场景图。
**只有"画面要准确表达某个数据关系"时不要用生成图** —— 那种场景用真正的数据图表
（见 `VISUAL-ASSET-STANDARD.md` §3），生成图表达不了精确数值关系。
