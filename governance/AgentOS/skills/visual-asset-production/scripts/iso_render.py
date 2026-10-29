#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""等轴测工程插画原语库（具象工程插画的绘图工具箱）。

来源：塑胶材料库 DFM 章节实际使用的 `illus.py`，按可独立复用的形态收拢。
**线框式示意图 = AI 味**：只有线条和文字标签的图不算画。本库画的是**实体**：
  · 受光的三面体（顶面渐变、侧面按朝向明暗）
  · 切面上的玻纤颗粒纹理
  · 接地投影阴影
  · 制图式尺寸线与引出标注

坐标系：世界坐标 (x 右, y 进深, z 向上) 投影到 axes 空间。

用法：
    from iso_render import Iso, Theme, shade
    th = Theme()
    fig, ax = plt.subplots(figsize=(5.4, 2.7))
    iso = Iso(ax, ox=0.24, oy=0.46, sx=0.62, sy=0.32, sz=0.56, scale=1.30)
    top = iso.prism(poly, 0.0, 0.30, th.body_gf)      # 实体
    iso.speckle(top, th.fibre, n=80, seed=11)        # 切面玻纤
    iso.shadow(*iso.p(0.23, 0.15, 0), 0.20, 0.042)  # 接地阴影
    iso.callout(iso.p(0.0, 0.0, 0.045), "壁厚", th.accent_txt, 0.09, 0.70, ha="right")
    iso.dim_v(iso.p(0.27, 0.0, 0.32), iso.p(0.27, 0.0, 0.09), "筋厚", th.accent_txt)

命令行：
    python iso_render.py --demo out.png      # 渲染一张参考面板（证明原语可用）
    python iso_render.py --self-test         # 负控制：实体渲染必须与线框渲染有本质差异
"""
import math

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
except Exception as exc:                      # pragma: no cover
    raise SystemExit("!! 缺少 matplotlib：%s" % exc)

# 中文字形必须显式注册，否则回退 DejaVu Sans 会画出方块（且不报错）
for _f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
    try:
        fm.fontManager.addfont(_f)
    except Exception:
        pass
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Segoe UI", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

__all__ = ["hexc", "shade", "Theme", "Iso", "demo_figure"]


def hexc(h):
    """接受 '#RRGGBB' 或已是 RGB 元组，返回 (r, g, b) 0-255。"""
    if not isinstance(h, str):
        return tuple(h[:3])
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def shade(color, f):
    """按系数 f 调暗（f<1）或提亮（f>1），返回 matplotlib 可用的 RGBA。

    f>1 时按 (f-1) 向白色插值，最大到 1.6（再高会曝掉）。
    """
    r, g, b = hexc(color)
    if f <= 1:
        r, g, b = r * f, g * f, b * f
    else:
        t = min(0.6, f - 1.0)
        r, g, b = r + (255 - r) * t, g + (255 - g) * t, b + (255 - b) * t
    return (max(0, min(255, int(r))) / 255.0,
            max(0, min(255, int(g))) / 255.0,
            max(0, min(255, int(b))) / 255.0)


class Theme:
    """默认色板：与 VISUAL-ASSET-STANDARD 的 token 同源（整页纯白、砂铜+苔绿）。"""

    def __init__(self, **kw):
        self.bg = kw.get("bg", "#FFFFFF")
        self.ink = kw.get("ink", "#1F2224")
        self.sub = kw.get("sub", "#636F77")
        self.accent_txt = kw.get("accent_txt", "#826430")   # 压暗砂铜：理由/看点
        self.primary_txt = kw.get("primary_txt", "#497350")  # 压暗苔绿：判据
        self.alert_txt = kw.get("alert_txt", "#A64634")      # 砖红：失败模式
        self.body = kw.get("body", "#E6E1D7")                # 注塑件本体
        self.body_gf = kw.get("body_gf", "#DED7C8")          # 玻纤增强本体
        self.cavity = kw.get("cavity", "#C9C2B5")            # 掏空/加工面
        self.steel = kw.get("steel", "#AEB3B7")              # 模钢
        self.fibre = kw.get("fibre", "#A8895F")               # 玻纤颗粒
        self.rule = kw.get("rule", "#E8E4DD")


class Iso:
    """等轴测投影 + 实体绘制。

    参数含义：
      ox, oy  投影原点在 axes 空间的位置
      sx, sy  x / y 方向的投影半步长
      sz      z 方向的投影高度
      scale   整体放大系数（DFM 面板里用 1.30，让实体填满面板而不是浮在白里）
    """

    def __init__(self, ax, ox=0.50, oy=0.66, sx=0.40, sy=0.20, sz=0.52, scale=1.0):
        self.ax = ax
        self.ox, self.oy = ox, oy
        self.sx, self.sy, self.sz = sx * scale, sy * scale, sz * scale
        self.last_face = None

    # ----------------------------------------------------------------- 投影
    def p(self, x, y, z):
        """世界坐标 → axes 坐标（z 向上，matplotlib 的 y 向上）。"""
        return (self.ox + (x - y) * self.sx,
                self.oy + z * self.sz + (x + y) * self.sy)

    def bbox(self, poly, z0, height):
        """多边形拉伸体的投影包围盒 (x0, y0, x1, y1)，axes 坐标。

        版面守卫要用它判断"实体有没有压到文字列"。
        """
        pts = [self.p(x, y, z0) for x, y in poly] + \
              [self.p(x, y, z0 + height) for x, y in poly]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    # ----------------------------------------------------------------- 实体
    def prism(self, poly, z0, height, color, edge=None, lw=1.1, sheen=True):
        """把世界坐标的 2D 多边形沿 z 拉伸成实体。

        先画按朝向明暗的侧壁，再画顶面并叠一层柔和渐变。
        返回顶面点列，调用方可用它裁切纹理。
        """
        n = len(poly)
        top = [self.p(x, y, z0 + height) for x, y in poly]
        bot = [self.p(x, y, z0) for x, y in poly]
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            ex, ey = x2 - x1, y2 - y1
            nx, ny = ey, -ex
            facing = -(nx * 0.6 + ny * 0.8)
            f = 0.74 + 0.20 * max(0.0, facing)
            quad = [bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]]
            self.ax.add_patch(Polygon(quad, closed=True, facecolor=shade(color, f),
                                      edgecolor=edge or shade(color, 0.55),
                                      lw=lw, joinstyle="round"))
        face = self.ax.add_patch(Polygon(top, closed=True,
                                         facecolor=shade(color, 1.04),
                                         edgecolor=edge or shade(color, 0.55),
                                         lw=lw, joinstyle="round", zorder=3))
        self.last_face = face
        if sheen and len(top) >= 3:
            self._lit_face(top, color)
        return top

    def _lit_face(self, top, color):
        """顶面柔和光照渐变，裁切在面内。

        先试过"内缩一块浅色多边形"，读起来像挖了个凹槽（眼睛看到的是边框和底）。
        **没有硬边的真渐变**才让实体读起来是实的。
        """
        import numpy as np
        from matplotlib.colors import LinearSegmentedColormap
        xs = [p[0] for p in top]
        ys = [p[1] for p in top]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
            return
        lo = shade(color, 1.13)
        hi = shade(color, 0.97)
        cmap = LinearSegmentedColormap.from_list("lit", [hi, lo])
        grad = np.linspace(0, 1, 256).reshape(256, 1)
        im = self.ax.imshow(grad, extent=(x0, x1, y0, y1), aspect="auto",
                            cmap=cmap, origin="lower", zorder=3, interpolation="bilinear")
        im.set_clip_path(self.last_face)

    def speckle(self, pts, color, n=120, seed=3, length=0.016, lw=0.9,
                alpha=0.45, zorder=6):
        """切面上的玻纤颗粒，裁切在面轮廓内。"""
        import random
        from matplotlib.path import Path
        from matplotlib.patches import PathPatch
        if len(pts) < 3:
            return
        rnd = random.Random(seed)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        clip = PathPatch(Path(list(pts) + [pts[0]], closed=True), facecolor="none",
                         edgecolor="none")
        self.ax.add_patch(clip)
        for _ in range(n):
            x = rnd.uniform(x0, x1)
            y = rnd.uniform(y0, y1)
            a = rnd.uniform(-0.45, 0.45)
            L = length * rnd.uniform(0.5, 1.5)
            ln = self.ax.plot([x - L * math.cos(a), x + L * math.cos(a)],
                              [y - L * math.sin(a), y + L * math.sin(a)],
                              color=color, lw=lw, alpha=rnd.uniform(0.3, 1.0) * alpha,
                              solid_capstyle="round", zorder=zorder)[0]
            ln.set_clip_path(clip)

    def shadow(self, cx, cy, rx, ry, color="#1F2224", alpha=0.13):
        """接地投影阴影。"""
        from matplotlib.patches import Ellipse
        self.ax.add_patch(Ellipse((cx, cy), rx, ry, facecolor=color,
                                   edgecolor="none", alpha=alpha, zorder=0))

    # ------------------------------------------------------------- 制图标注
    def dim_h(self, p1, p2, text, color, offset=0.0, tick=True, size=7.6,
              text_dy=0.018):
        """两点之间的水平尺寸线（制图式）。"""
        x1, y1 = p1
        x2, y2 = p2
        yy = max(y1, y2) + offset if offset else (y1 + y2) / 2
        self.ax.annotate("", xy=(x1, yy), xytext=(x2, yy),
                         arrowprops=dict(arrowstyle="<|-|>", color=color, lw=0.9,
                                         mutation_scale=7))
        if tick:
            self.ax.plot([x1, x1], [y1, yy], color=color, lw=0.6, alpha=0.8)
            self.ax.plot([x2, x2], [y2, yy], color=color, lw=0.6, alpha=0.8)
        self.ax.text((x1 + x2) / 2, yy + text_dy, text, ha="center", va="bottom",
                     fontsize=size, color=color)

    def dim_v(self, p1, p2, text, color, size=7.6, side=0.012):
        """两点之间的竖向尺寸线。

        side > 0 尺寸线放在特征左侧，side < 0 放右侧。
        """
        x1, y1 = p1
        x2, y2 = p2
        if side >= 0:
            xx = min(x1, x2) - side
            ha = "right"
            tx = xx - 0.006
        else:
            xx = max(x1, x2) + (-side)
            ha = "left"
            tx = xx + 0.006
        self.ax.annotate("", xy=(xx, y1), xytext=(xx, y2),
                         arrowprops=dict(arrowstyle="<|-|>", color=color, lw=0.9,
                                         mutation_scale=7))
        self.ax.plot([x1, xx], [y1, y1], color=color, lw=0.6, alpha=0.8)
        self.ax.plot([x2, xx], [y2, y2], color=color, lw=0.6, alpha=0.8)
        self.ax.text(tx, (y1 + y2) / 2, text, ha=ha, va="center",
                     fontsize=size, color=color, rotation=90)

    def callout(self, point, text, color, tx, ty, ha="left", size=7.8, dot=2.4):
        """从特征点引出到标签的引出线。"""
        px, py = point
        self.ax.plot([px, tx], [py, ty], color=color, lw=0.9, zorder=5)
        self.ax.plot([px], [py], marker="o", ms=dot, color=color, zorder=5)
        self.ax.text(tx + (0.008 if ha == "left" else -0.008), ty, text,
                     ha=ha, va="center", fontsize=size, color=color, zorder=5)

    def flow(self, pts, color, lw=1.3, alpha=0.85, head=7):
        """熔体/气流走向的路径 + 箭头。"""
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.ax.plot(xs, ys, color=color, lw=lw, alpha=alpha, solid_capstyle="round")
        if len(pts) >= 2:
            x1, y1 = pts[-2]
            x2, y2 = pts[-1]
            self.ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                             arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                             alpha=alpha, mutation_scale=head))

    def fibres(self, pts, color, n=16, seed=5, along="x", lw=1.5, alpha=0.5,
               clip=True):
        """面内的取向纤维线（表示玻纤方向）。"""
        import random
        from matplotlib.path import Path
        from matplotlib.patches import PathPatch
        rnd = random.Random(seed)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        cp = None
        if clip and len(pts) >= 3:
            cp = PathPatch(Path(list(pts) + [pts[0]], closed=True), facecolor="none",
                           edgecolor="none")
            self.ax.add_patch(cp)
        for _ in range(n):
            x = rnd.uniform(x0, x1)
            y = rnd.uniform(y0, y1)
            if along == "x":
                L = rnd.uniform(0.012, 0.03)
                ln = self.ax.plot([x - L, x + L], [y, y], color=color, lw=lw,
                                  alpha=alpha, solid_capstyle="round", zorder=6)[0]
            else:
                L = rnd.uniform(0.010, 0.026)
                ln = self.ax.plot([x, x], [y - L, y + L], color=color, lw=lw,
                                  alpha=alpha, solid_capstyle="round", zorder=6)[0]
            if cp is not None:
                ln.set_clip_path(cp)


# matplotlib 补丁延后导入，避免模块级循环依赖
from matplotlib.patches import Polygon  # noqa: E402


# --------------------------------------------------------------------- 演示
# 面板分栏：实体区在左，文字列在右，**互不相交**（版面守卫强制）
REGION_BODY = (0.04, 0.14, 0.60, 0.88)   # x0, y0, x1, y1
REGION_TEXT = (0.64, 0.26, 0.98, 0.88)


def check_layout(bbox):
    """版面守卫：实体必须待在实体区，且不得侵入文字列。

    返回问题清单（空 = 通过）。
    """
    problems = []
    x0, y0, x1, y1 = bbox
    if x0 < REGION_BODY[0] or x1 > REGION_BODY[2]:
        problems.append("实体横向越界 [%.3f, %.3f] 不在 [%.3f, %.3f]"
                        % (x0, x1, REGION_BODY[0], REGION_BODY[2]))
    if y0 < REGION_BODY[1] or y1 > REGION_BODY[3]:
        problems.append("实体纵向越界 [%.3f, %.3f] 不在 [%.3f, %.3f]"
                        % (y0, y1, REGION_BODY[1], REGION_BODY[3]))
    if x1 > REGION_TEXT[0]:
        problems.append("实体侵入文字列 (实体右缘 %.3f > 文字列左缘 %.3f)"
                        % (x1, REGION_TEXT[0]))
    return problems


def demo_figure(th=None, wireframe=False, figsize=(5.4, 2.7)):
    """渲染一张参考面板：壁厚 + 筋 + 圆角的等轴测实体。

    wireframe=True 时只画轮廓线不画实体 —— 用于自检证明"实体"是代码画出来的，
    不是"看起来像"。
    """
    th = th or Theme()
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(th.bg)
    ax.set_facecolor(th.bg)
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.03, 0.965, "参考面板 · 壁厚 / 筋厚 / 圆角", fontsize=10,
            fontweight="bold", color=th.ink, va="top")
    iso = Iso(ax, ox=0.16, oy=0.40, sx=0.62, sy=0.34, sz=0.62)
    poly = [(0, 0), (0.46, 0), (0.46, 0.09), (0.30, 0.09), (0.30, 0.30),
            (0.27, 0.32), (0.24, 0.30), (0.24, 0.09), (0.0, 0.09)]
    if wireframe:
        top = [iso.p(x, y, 0.30) for x, y in poly]
        ax.add_patch(Polygon(top, closed=True, facecolor="none",
                             edgecolor=th.ink, lw=1.0))
        for (x, y) in poly:
            ax.plot([iso.p(x, y, 0.0)[0], iso.p(x, y, 0.30)[0]],
                    [iso.p(x, y, 0.0)[1], iso.p(x, y, 0.30)[1]],
                    color=th.ink, lw=0.8)
    else:
        top = iso.prism(poly, 0.0, 0.30, th.body_gf)
        iso.speckle(top, th.fibre, n=80, seed=11)
        iso.shadow(*iso.p(0.23, 0.15, 0), 0.19, 0.040)
        iso.callout(iso.p(0.0, 0.0, 0.045), "壁厚", th.accent_txt, 0.05, 0.22, ha="left")
        iso.dim_v(iso.p(0.27, 0.0, 0.32), iso.p(0.27, 0.0, 0.09), "筋厚",
                  th.accent_txt, size=7.4, side=-0.055)
        iso.fibres([iso.p(0.03, 0.02, 0.09), iso.p(0.21, 0.02, 0.09),
                    iso.p(0.21, 0.26, 0.09), iso.p(0.03, 0.26, 0.09)],
                   th.fibre, n=14, along="x", lw=1.4, alpha=0.45)
    ax.text(0.66, 0.84, "名义壁厚 2.0~3.0 mm", fontsize=7.8, color=th.sub, ha="left")
    ax.text(0.66, 0.75, "筋厚 ≤ 0.6 × 壁厚", fontsize=7.8, color=th.sub, ha="left")
    ax.text(0.66, 0.66, "内圆角 R ≥ 0.5 × 壁厚", fontsize=7.8, color=th.sub, ha="left")
    ax.text(0.66, 0.50, "玻纤沿流向取向 →\n刚度与收缩随方向而变",
            fontsize=7.6, color=th.accent_txt, ha="left")
    ax.text(0.04, 0.05, "筋过厚 → 表面缩痕   ·   R 过小 → 纤维堆积",
            fontsize=7.4, color=th.sub)
    return fig, iso.bbox(poly, 0.0, 0.30)


def _luma_clusters(path):
    """统计灰度直方图里的显著簇数（粗略衡量"是不是有实体层次"）。"""
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        a = np.asarray(im.convert("L")).astype(float).ravel()
    hist, edges = np.histogram(a, bins=64, range=(0, 255))
    occupied = hist[hist > a.size * 0.004]
    # 合并相邻簇
    clusters = 0
    prev = 0
    for c in occupied:
        clusters += 1 if (prev == 0 or c != prev) else 0
        prev = c
    return clusters, float(a.std())


def self_test():
    """负控制：实体渲染必须与线框渲染有本质差异（否则"实体"就只是说法）。"""
    import os
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        solid = os.path.join(td, "solid.png")
        wire = os.path.join(td, "wire.png")
        fig, bbox = demo_figure()
        fig.savefig(solid, dpi=160, facecolor="#FFFFFF")
        demo_figure(wireframe=True)[0].savefig(wire, dpi=160, facecolor="#FFFFFF")
        cs, ss = _luma_clusters(solid)
        cw, sw = _luma_clusters(wire)
        if cs <= cw:
            print("FAIL 负控制：实体渲染的层次(%d) 未多于线框(%d)" % (cs, cw))
            ok = False
        else:
            print("PASS 负控制：实体渲染层次 %d > 线框 %d（实体是画出来的）" % (cs, cw))
        if ss <= 1.0:
            print("FAIL 负控制：实体渲染几乎是空白（灰度标准差 %.2f）" % ss)
            ok = False
        else:
            print("PASS 负控制：实体渲染非空（灰度标准差 %.2f）" % ss)
        if sw >= ss:
            print("FAIL 负控制：线框与实体差异不足（%.2f vs %.2f）" % (sw, ss))
            ok = False
        else:
            print("PASS 负控制：线框(%.2f) 与实体(%.2f) 可区分" % (sw, ss))
        problems = check_layout(bbox)
        if problems:
            for p in problems:
                print("FAIL 版面守卫：%s" % p)
            ok = False
        else:
            print("PASS 版面守卫：实体 bbox (%.3f, %.3f, %.3f, %.3f) 不越界、不压文字列"
                  % bbox)
        # 负控制：把实体放大到压住文字列，守卫必须报出来
        big = Iso(fig.axes[0], ox=0.16, oy=0.40, sx=0.62, sy=0.34, sz=0.62, scale=1.6)
        poly = [(0, 0), (0.46, 0), (0.46, 0.09)]
        if not check_layout(big.bbox(poly, 0.0, 0.30)):
            print("FAIL 版面守卫负控制：放大后越界却没报出来")
            ok = False
        else:
            print("PASS 版面守卫负控制：放大后越界被拦下")
    return 0 if ok else 1


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="等轴测工程插画原语库")
    ap.add_argument("--demo", help="渲染参考面板到指定 PNG")
    ap.add_argument("--self-test", action="store_true", help="负控制")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.demo:
        print("!! 需要 --demo <path> 或 --self-test")
        return 2
    fig, bbox = demo_figure()
    fig.savefig(args.demo, dpi=200, facecolor="#FFFFFF")
    problems = check_layout(bbox)
    if problems:
        for p in problems:
            print("!! 版面守卫：%s" % p)
        return 1
    print("参考面板：%s" % args.demo)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
