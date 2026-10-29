# 实景底图 brief 写法（创意配图的描述语法）

> 一条底图描述只写"画什么"，风格与禁令由统一模板附加。
> 下面的数字是**对 40 条真实交付描述的统计**（湘乡 50 届 40 个点子），
> 不是经验估计；改写规则前请重新统计，别凭印象。

## 1. 骨架

```
<一句总述：场景 + 主体 + 环境光>，
<关键部件 1：数量 + 形态 + 位置>，
<关键部件 2：数量 + 形态 + 位置>，
<关键部件 3：数量 + 形态 + 位置>，
<可测量道具：让画面自带"怎么验证">，
<氛围：精确、手工、有使用痕迹>
```

词数：60–110 词（实测 40 条：min 60 / 中位 84 / max 119）。
封面主视觉是例外（实测 661 词），横幅 73–113 词。

## 2. 六条硬规则（附实测命中率）

| 规则 | 实测 | 说明 |
|---|---|---|
| ① 写清**数量** | 33/40 (83%) | `two photoresistors` 而非 `photoresistors`；不写数量模型会自己编 |
| ② 写清**位置** | 必写 | `on the lower left` / `at the far edge` / `in the middle` |
| ③ 结尾落在**环境与光** | 39/40 (98%) 含光词，36/40 落在末 90 字符 | `soft window light from a rural primary school classroom` |
| ④ 放一个**可测量道具** | 19/40 (48%) | 卡尺、电子秤、卷尺、秒表、螺旋桨桨距尺 —— 让画面自带"怎么验证" |
| ⑤ 有人物只写**手/背影/局部** | 22/40 (55%) | 不写正脸、不写眼睛、不写侧脸轮廓 |
| ⑥ 载体可写字就写**空白载体** | 12/40 (30%) | **只有画面里确实有纸/板/卡/屏时才写** |

> 规则 ⑥ 的 30% 命中率是个容易搞反的点：**大多数场景根本没有可写字的载体**，
> 所以不需要每条都写 "blank"。真出现了展板、表格纸、书本、便签、记录单、
> 屏幕、标签，就必须写成 `blank and unmarked`（或直接不写那个载体）。
> 全局禁令由 STYLE 常量兜底（"任何纸张/卡片/屏幕/板面必须完全空白"）。

## 3. 统一风格模板（112 词，直接拼进 prompt）

```
Technical concept illustration for a <题材>. Subject: {subject}
Style: hand-drawn editorial technical illustration, warm off-white paper background,
soft natural daylight, muted low-saturation earth-tone palette of sand bronze, moss green,
brick red and warm grey, delicate ink linework with soft painted shading, gentle soft
shadows, shallow depth of field, calm and precise, high detail on the <主体>,
no text, no letters, no numbers, no labels, no watermark, no visible faces.
Every sheet of paper, card, notebook, screen, board and label anywhere in the scene is
completely blank and unmarked: nothing written, printed, handwritten, engraved or labelled
on it, and no chart, table, caption or diagram carrying symbols on it
```

模板里写死的 6 条禁令（`no text / no letters / no numbers / no labels / no watermark /
no visible faces`）与 1 条载体总则，**一条都不能删** —— 它们是"底图禁字"的执行面。

## 4. 底图尺寸

| 用途 | 比例 | 理由 |
|---|---|---|
| 正文插图 | 16:9 | 与信息带画布一致 |
| 多场景横幅 | 21:9 | 原生比例，**用 fit 不用 cover**（留白也不切画面） |
| 封面主视觉 | 3:4 单独出 | 16:9 竖裁会切掉工作台大半 |

给宽高两个数 = 压扁 = 硬伤。**比例不对就重新生成，别硬裁**。

## 5. 生成与筛查

```bash
python scripts/text_screen.py --dir raw --out _text_hits.json --crops _texthits
```

- 筛查器**不是判据**：它只抓"等高、等宽、间距均匀"的疑似文字行。
  实测 43 张真实底图：纯连通域误报 41/41，加排版规律性后 17/41，逐条人工复核确认
  剩余命中全是误报（木纹/沙粒/砖缝/标尺刻度）。短标签仍会逃过，**必须逐张目检**。
- 批次上限：单批 ≤ 5 张，超限会**静默返回 0 成功**。分批跑。
- 批次返回顺序不保证对应，脚本要按响应里的标识回验，长度不符时**拒绝按下标猜测**。

## 6. 反例 → 正解

| 反例 | 后果 | 正解 |
|---|---|---|
| `a display board listing the five steps` | 模型自己写英文标签 | `a plain unmarked corkboard` |
| `a notebook with the teacher's notes` | 伪手写 | `a closed plain notebook with a blank unmarked cover` |
| `a printed comparison table` | 表格 + 乱码列标题 | `a plain empty wooden board` |
| `a student drawing a city` | 清晰人脸 | `a student seen strictly from behind over the shoulder ... no face no eyes no profile` |
| `some sensors` | 数量随机 | `three sensors` |
| `a robot on a bench` | 泛泛、看不出在做什么 | `a wheeled robot hugging the raised paddy ridge ... a phone clamped on a mini tripod at the far end of the course` |

## 7. 判别口

- 一张图如果去掉所有标注就**看不出在讲什么**，是底图失败（画面没承载主体）。
- 一张图如果标注写的是画面里没有的东西，是信息层失败（回到事实源核对）。
- 一张图如果读起来像渲染玩具而不是技术插页，是 STYLE 没生效。
