#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""矢量标注层合成器：底图 + 信息层 → 最终成品图。

两层法的第二层。**所有文字与数字都由本模块画**，不来自生成模型，
因此可逐条审校、不会臆造、不会出现中文乱码或部件数量错误。

配置格式（JSON）：

{
  "canvas": {"width": 1700, "height": 952, "dpi": 170},
  "band":   {"top_ratio": 0.243, "paper": "#FBF9F5", "rule": "#E8E4DD"},
  "items": {
    "a1": {
      "base": "raw/a1.png",
      "accent": "#826430",
      "zh": {"title": "...", "sub": "...", "labels": ["...", "..."], "crit": "..."},
      "en": {"title": "...", "sub": "...", "labels": ["...", "..."], "crit": "..."}
    }
  }
}

用法：
    python overlay_compose.py --config info.json --outdir ../assets/diagrams
    python overlay_compose.py --self-test        # 负控制：缺件必须报错

退出码：0 = 全部合成成功；1 = 有条目失败；2 = 工具自身出错。
"""
import argparse
import json
import os
import sys

try:
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    from matplotlib.patches import FancyBboxPatch
    from PIL import Image
except Exception as exc:                      # pragma: no cover
    print("!! 缺少依赖 matplotlib/Pillow/numpy：%s" % exc)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
for _f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
    try:
        fm.fontManager.addfont(_f)
    except Exception:
        pass
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

INK = "#1F2224"
BODY = "#2C3236"
MUTED = "#636F77"
PAPER = "#FBF9F5"
RULE = "#E8E4DD"
BG = "#FFFFFF"
AXIS_W, AXIS_H = 100.0, 56.0          # 画布坐标：0..100 × 0..56
_FCACHE = {}


# ----------------------------------------------------------------- 度量
def _rgb(h):
    """'#RRGGBB' → [r, g, b] 浮点 0..1。"""
    h = str(h).lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float) / 255.0


def text_w(s, pt):
    """文字宽度（轴单位）。1 轴单位 = 0.1 英寸 = 7.2 磅。

    **单位换算不能漏 /7.2**：旧实现漏了它，宽度被放大 72 倍，
    导致竖向分隔线永远算不出空档。
    """
    key = (s, pt)
    if key in _FCACHE:
        return _FCACHE[key]
    from PIL import ImageFont
    path = r"C:\Windows\Fonts\msyhbd.ttc" if pt >= 9.0 else r"C:\Windows\Fonts\msyh.ttc"
    f = ImageFont.truetype(path, int(round(pt * 10)))
    _FCACHE[key] = f.getlength(s) / 10.0 / 7.2
    return _FCACHE[key]


# ----------------------------------------------------------------- 底图
def trim_mat(im, thresh=243, tol=10):
    """裁掉四周的纯色纸衬边（有些出图自带白框）。"""
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    h, w, _ = a.shape
    x0, x1, y0, y1 = 0, w, 0, h

    def row_uniform(y):
        r = a[y]
        return r.max(axis=1).min() >= thresh and (r.max(axis=1) - r.min(axis=1)).max() <= tol

    def col_uniform(x):
        c = a[:, x]
        return c.max(axis=0).min() >= thresh and (c.max(axis=0) - c.min(axis=0)).max() <= tol

    while y0 < y1 - 2 and row_uniform(y0):
        y0 += 1
    while y1 > y0 + 2 and row_uniform(y1 - 1):
        y1 -= 1
    while x0 < x1 - 2 and col_uniform(x0):
        x0 += 1
    while x1 > x0 + 2 and col_uniform(x1 - 1):
        x1 -= 1
    if (x1 - x0) < w * 0.5 or (y1 - y0) < h * 0.5:
        return im.convert("RGB")
    return im.convert("RGB").crop((x0, y0, x1, y1))


def cover(im, w, h):
    """等比裁切铺满目标尺寸（不拉伸）。"""
    iw, ih = im.size
    s = max(w / iw, h / ih)
    im = im.resize((int(round(iw * s)), int(round(ih * s))), Image.LANCZOS)
    left, top = (im.size[0] - w) // 2, (im.size[1] - h) // 2
    return im.crop((left, top, left + w, top + h))


# ----------------------------------------------------------------- 合成
def compose(item, lang, out_path, canvas, band_cfg, dkey=None):
    W, H = canvas["width"], canvas["height"]
    fig = plt.figure(figsize=(W / canvas["dpi"], H / canvas["dpi"]),
                     dpi=canvas["dpi"], facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, AXIS_W)
    ax.set_ylim(0, AXIS_H)
    ax.axis("off")
    ax.set_facecolor(BG)

    im = cover(trim_mat(Image.open(item["base"])), W, H)
    ax.imshow(im, extent=(0, AXIS_W, 0, AXIS_H), aspect="auto", zorder=0)

    info = item[lang]
    accent = item.get("accent", "#826430")
    band_top = AXIS_H * band_cfg.get("top_ratio", 0.243)

    # 渐变遮罩 + 实心信息带
    n = int(band_top * 10)
    paper_rgb = _rgb(band_cfg.get("paper", PAPER))
    grad = np.zeros((n, 2, 4), dtype=float)
    for i in range(n):
        t = i / max(n - 1, 1)
        grad[i, :, :3] = paper_rgb
        grad[i, :, 3] = 0.97 * (t ** 0.75)
    ax.imshow(grad, extent=(0, AXIS_W, 0, band_top + 1.2), origin="upper",
              aspect="auto", zorder=3, interpolation="bilinear")
    ax.add_patch(plt.Rectangle((0, 0), AXIS_W, band_top,
                               fc=band_cfg.get("paper", PAPER), ec="none",
                               alpha=0.97, zorder=4))
    ax.plot([0, AXIS_W], [band_top, band_top], color=band_cfg.get("rule", RULE),
            lw=0.9, zorder=5)

    # 方向色条
    ax.add_patch(plt.Rectangle((0, 0), 0.9, band_top, fc=accent, ec="none",
                               alpha=0.95, zorder=6))

    # 标题 / 副题
    title, sub = info.get("title", ""), info.get("sub", "")
    ax.text(3.2, band_top * 0.76, title, fontsize=13.6, color=INK, va="center",
            ha="left", fontweight="bold", zorder=6)
    if sub:
        ax.text(3.2, band_top * 0.56, sub, fontsize=8.6, color=MUTED, va="center",
                ha="left", zorder=6)

    # 关键部件（微标签 + 值）
    labels = info.get("labels") or []
    lab_w = 0.0
    if labels:
        txt = "  ·  ".join(labels)
        lab_w = text_w(txt, 8.4)
        ax.text(96.8, band_top * 0.70, txt, fontsize=8.4, color=BODY,
                va="center", ha="right", zorder=6)
        ax.text(96.8, band_top * 0.83, ("关键部件" if lang == "zh" else "KEY PARTS"),
                fontsize=6.4, color=MUTED, va="center", ha="right", zorder=6)

    # 关键判据（微标签 + 值）
    crit = info.get("crit", "")
    crit_w = 0.0
    if crit:
        crit_w = text_w(crit, 9.2)
        ax.text(96.8, band_top * 0.38, crit, fontsize=9.2, color=accent,
                va="center", ha="right", zorder=6, fontweight="bold")
        ax.text(96.8, band_top * 0.52, ("看点" if lang == "zh" else "FOCUS"),
                fontsize=6.4, color=MUTED, va="center", ha="right", zorder=6)

    # 竖向细线：位置按实测文字宽度动态计算，绝不压字
    left_end = 3.2 + max(text_w(title, 13.6), text_w(sub, 8.6) if sub else 0.0)
    right_start = 96.8 - max(lab_w, crit_w)
    if right_start - left_end > 6.0:
        rx = (left_end + right_start) / 2.0
        ax.plot([rx, rx], [band_top * 0.28, band_top * 0.86], color=RULE, lw=0.8, zorder=5)

    # 免责行 + 编号徽标
    note = ("概念渲染示意图（非实物照片）· 数值以实测回填为准" if lang == "zh"
            else "Concept rendering, not a photograph - measured values replace the targets")
    ax.text(3.2, band_top * 0.18, note, fontsize=6.6, color=MUTED,
            va="center", ha="left", zorder=6)
    if dkey:
        ax.add_patch(FancyBboxPatch((91.6, band_top * 0.09), 5.2, band_top * 0.19,
                                    boxstyle="round,pad=0,rounding_size=1.0",
                                    fc=accent, ec=accent, alpha=0.92, zorder=6))
        ax.text(94.2, band_top * 0.18, dkey.upper(), fontsize=8.0, color="#FFFFFF",
                va="center", ha="center", fontweight="bold", zorder=7)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    fig.savefig(out_path, dpi=canvas["dpi"], facecolor=BG, format="jpg",
                pil_kwargs={"quality": 94, "subsampling": 0, "optimize": True})
    plt.close(fig)
    return out_path


def self_test():
    """负控制：缺底图必须报错；成品图必须存在且尺寸正确。"""
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "b.png")
        Image.new("RGB", (800, 450), "#EDE7DA").save(base)
        cfg = {"canvas": {"width": 1700, "height": 952, "dpi": 170},
               "band": {"top_ratio": 0.243},
               "items": {"t1": {"base": base, "accent": "#826430",
                                "zh": {"title": "测试标题", "sub": "副题",
                                       "labels": ["甲", "乙", "丙"], "crit": "看点一句"},
                                "en": {"title": "Test title", "sub": "subtitle",
                                       "labels": ["a", "b", "c"], "crit": "focus line"}}}}
        out = os.path.join(td, "o")
        compose(cfg["items"]["t1"], "zh", os.path.join(out, "t1_zh.jpg"),
                cfg["canvas"], cfg["band"], "t1")
        p = os.path.join(out, "t1_zh.jpg")
        if not os.path.exists(p):
            print("FAIL 负控制：成品图未生成")
            ok = False
        else:
            with Image.open(p) as im:
                if im.size != (1700, 952):
                    print("FAIL 负控制：成品尺寸 %s != (1700, 952)" % (im.size,))
                    ok = False
                else:
                    print("PASS 负控制：合成成功且尺寸正确")
        # 缺底图必须抛错
        try:
            compose({"base": os.path.join(td, "nope.png"), "zh": {}}, "zh",
                    os.path.join(out, "x.jpg"), cfg["canvas"], cfg["band"], "x")
            print("FAIL 负控制：缺底图未报错")
            ok = False
        except Exception:
            print("PASS 负控制：缺底图正确报错")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="矢量标注层合成器")
    ap.add_argument("--config", help="信息层配置 JSON")
    ap.add_argument("--outdir", help="成品图输出目录")
    ap.add_argument("--base-root", default="", help="底图相对路径的根目录")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.config or not os.path.exists(args.config):
        print("!! --config 不存在")
        return 2
    if not args.outdir:
        print("!! --outdir 必填")
        return 2
    with open(args.config, encoding="utf-8") as fh:
        cfg = json.load(fh)
    canvas = cfg.get("canvas", {"width": 1700, "height": 952, "dpi": 170})
    band = cfg.get("band", {"top_ratio": 0.243})
    items = cfg.get("items") or {}
    if not items:
        print("!! 配置里没有 items")
        return 2
    root = args.base_root or os.path.dirname(os.path.abspath(args.config))
    made, failed = 0, []
    for dkey, item in sorted(items.items()):
        if not os.path.isabs(item["base"]):
            item = dict(item, base=os.path.join(root, item["base"]))
        if not os.path.exists(item["base"]):
            failed.append("%s: 缺底图 %s" % (dkey, item["base"]))
            continue
        for lang in ("zh", "en"):
            if lang not in item:
                continue
            out = os.path.join(args.outdir, "%s_%s.jpg" % (dkey, lang))
            try:
                compose(item, lang, out, canvas, band, dkey)
                made += 1
            except Exception as exc:
                failed.append("%s[%s]: %s" % (dkey, lang, exc))
    print("合成 %d 张" % made)
    if failed:
        print("失败 %d 条：" % len(failed))
        for f in failed:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
