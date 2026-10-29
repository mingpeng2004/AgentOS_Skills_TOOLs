# 等轴测工程插画原语库

> 工具：`scripts/iso_render.py`（matplotlib，无项目依赖）。
> 用法见文末；`--self-test` 跑正负控制；`--demo` 出参考面板。
> 背景与判别口见 [dfm-panel-grammar.md](dfm-panel-grammar.md)。
>
> **适用范围**：本原语库只负责协议 §6.6.2 的 **B 路线（带填充的工程剖面 / 等轴测实体）**。
> A 路线（实景概念渲染）走两层法主流程；**C 路线（符号关系图）不用本库** ——
> 画面里根本没有零件，画的是参考线 / 曲线 / 力矢量，用本库画反而会硬塞一个零件出来。

## 1. 坐标系

世界坐标 `(x 右, y 进深, z 向上)` → axes 空间（0..1）。
投影：`px = ox + (x - y) * sx`，`py = oy + z * sz + (x + y) * sy`。

- `sx, sy` 是 x / y 方向的投影半步长，`sz` 是 z 方向的投影高度；
- `scale` 整体放大（DFM 面板用 1.15~1.30，让实体填满面板而不是浮在白里）；
- `ox, oy` 决定实体落在版面哪个位置。

`Iso.bbox(poly, z0, height)` 返回投影包围盒，版面守卫（`check_layout`）用它
判断实体有没有越界或压到文字列。

## 2. 实体四件套

| 方法 | 作用 | 关键参数 |
|---|---|---|
| `prism(poly, z0, height, color, edge, lw, sheen)` | 把 2D 多边形沿 z 拉伸成实体：侧面按朝向明暗 + 顶面无硬边渐变 | 返回顶面点列，供纹理裁切 |
| `speckle(pts, color, n, seed, ...)` | 切面上的玻纤颗粒（裁切在面轮廓内） | `seed` 固定 ⇒ 可复现 |
| `shadow(cx, cy, rx, ry, alpha)` | 接地投影阴影 | 让物体落地，不悬空 |
| `fibres(pts, color, n, along, ...)` | 面内取向纤维线（表达玻纤方向） | `along="x"/"y"` |

**高光必须用真渐变**：先试过"内缩一块浅色多边形"，读起来像挖了个凹槽
（眼睛看到的是边框和底），没有硬边才让实体读起来是实的。

## 3. 制图标注

| 方法 | 画什么 |
|---|---|
| `dim_v(p1, p2, text, color, size, side)` | 竖向尺寸线；`side>0` 放左侧、`side<0` 放右侧，文字旋转 90° |
| `dim_h(p1, p2, text, color, offset, tick, size)` | 水平尺寸线 + 端点引出线 |
| `callout(point, text, color, tx, ty, ha, size, dot)` | 引出标注：锚点圆点 + 引线 + 标签 |
| `flow(pts, color, lw, alpha, head)` | 熔体/气流走向路径 + 箭头（浇口/流向类规范用） |

尺寸线**放在特征旁边**而不是压在实体上；引出标签落在留白里。

## 4. 主题

`Theme()` 给出与全局 token 同源的默认色板（整页纯白、砂铜 + 苔绿）：

| 键 | 默认 | 用途 |
|---|---|---|
| `bg` | `#FFFFFF` | 面板底 |
| `ink` | `#1F2224` | 标题 |
| `sub` | `#636F77` | 注释、要点 |
| `accent_txt` | `#826430` | 压暗砂铜：理由、看点 |
| `primary_txt` | `#497350` | 压暗苔绿：判据 |
| `alert_txt` | `#A64634` | 砖红：失败模式 |
| `body` / `body_gf` | `#E6E1D7` / `#DED7C8` | 注塑件本体 / 玻纤增强本体 |
| `cavity` | `#C9C2B5` | 掏空面、加工面 |
| `steel` | `#AEB3B7` | 模钢 |
| `fibre` | `#A8895F` | 玻纤颗粒 |

`shade(color, f)`：f<1 调暗，f>1 向白插值（最多 0.6，曝掉就脏）。

## 5. 最小可用片段

```python
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from iso_render import Iso, Theme, check_layout

th = Theme()
fig, ax = plt.subplots(figsize=(5.4, 2.7))
fig.patch.set_facecolor(th.bg); ax.set_facecolor(th.bg)
ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)

iso = Iso(ax, ox=0.16, oy=0.40, sx=0.62, sy=0.34, sz=0.62)
poly = [(0, 0), (0.46, 0), (0.46, 0.09), (0.30, 0.09), (0.30, 0.30),
        (0.27, 0.32), (0.24, 0.30), (0.24, 0.09), (0.0, 0.09)]
top = iso.prism(poly, 0.0, 0.30, th.body_gf)
iso.speckle(top, th.fibre, n=80, seed=11)
iso.shadow(*iso.p(0.23, 0.15, 0), 0.19, 0.040)
iso.dim_v(iso.p(0.27, 0.0, 0.32), iso.p(0.27, 0.0, 0.09), "筋厚", th.accent_txt, side=-0.055)
iso.callout(iso.p(0.0, 0.0, 0.045), "壁厚", th.accent_txt, 0.05, 0.22)

problems = check_layout(iso.bbox(poly, 0.0, 0.30))
assert not problems, problems          # 版面守卫：实体不得越界或压到文字列
fig.savefig("wall_iso.png", dpi=170, facecolor=th.bg)
```

## 6. 自检（负控制）

`python scripts/iso_render.py --self-test` 跑五条断言：

1. 实体渲染的灰度层次 **>** 线框渲染（"实体"是代码画出来的，不是看起来像）；
2. 实体渲染非空（灰度标准差 > 1.0）；
3. 线框与实体可区分；
4. 版面守卫：参考面板的实体 bbox 不越界、不压文字列；
5. **版面守卫负控制**：把实体放大 1.6 倍后越界，必须被拦下。

## 7. 常见坑

- **中文字形变方块**：必须显式注册 `msyh.ttc` / `msyhbd.ttc` 并设
  `font.sans-serif`，否则 matplotlib 回退 DejaVu Sans 只给警告、不报错。
- **实体浮在白里**：`scale` 太小，或 `ox/oy` 没调；用 `bbox()` 看着办。
- **把线框当图**：`prism` 必须调用，`speckle`/`shadow` 至少各来一次。
- **高光用内缩多边形**：会读成凹槽，改真渐变。
- **单位混用**：`iso_render` 的 axes 是 0..1（1 单位 = 446.4 磅 @ 6.2 英寸宽），
  而 `overlay_compose.py` 的画布是 0..100（1 单位 = 7.2 磅）—— 两套基准不能混。
- **锚点靠猜**：画图时把特征点的屏幕坐标**返回出来**，换算成原图相对坐标写进契约。
  门禁会核对锚点像素有没有墨迹 —— 指到空纸上等于没指。
- **给 C 路线硬塞零件**：符号关系图（参考线高差、时效曲线）本来就不该有实体，
  硬画一个零件出来反而把关系讲错了。
