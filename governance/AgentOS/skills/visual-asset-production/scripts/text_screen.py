#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文字筛查闸门：找出生成图里**模型自己画上去的文字**。

背景：文生图模型常在展板、表格纸、书本、便签、记录单上写英文（乱码、错拼、伪手写）。
底图必须零文字 —— 文字一律由矢量层叠加，才能可审校、不臆造。

判据（启发式，宁可误报不可漏报）：
1. 深色像素二值化 → 连通域分析；
2. 取「字形尺度」连通域（高 MIN_H..MAX_H，宽 MIN_W..MAX_W）；
3. 按垂直中心聚成「行」；
4. 一行内 >= MIN_PER_LINE 个连通域 → 疑似文字行；
5. **排版规律性过滤**（关键）：等高、宽度接近、间距均匀。

只加连通域会误报绝大多数图（墨线、齿轮、螺丝、电路走线全是"类字形"）；
必须加第 5 步。实测 43 张真实底图：纯连通域误报 41/41，加规律性后 17/41，
且逐条人工复核确认剩余命中全是误报（木纹/沙粒/砖缝/标尺刻度）。

**筛查器不是判据**：短标签（每行 2-3 词、间距不规则）会逃过它，最终仍需逐张目检。

用法：
    python text_screen.py --dir raw --out _text_hits.json --crops _texthits
    python text_screen.py --self-test          # 负控制：合成图必须能被抓出

退出码：0 = 未发现疑似文字；1 = 发现疑似文字（需人工复核或重生成）；2 = 工具自身出错。
"""
import argparse
import json
import os
import sys

try:
    import numpy as np
    from PIL import Image, ImageDraw
    from scipy import ndimage
except Exception as exc:                      # pragma: no cover
    print("!! 缺少依赖 numpy/Pillow/scipy：%s" % exc)
    sys.exit(2)

MIN_H, MAX_H = 5, 70
MIN_W, MAX_W = 3, 260
MIN_PER_LINE = 3
DARK = 150
H_CV_MAX = 0.28
H_RATIO_MAX = 2.3
W_CV_MAX = 0.95
GAP_CV_MAX = 0.75
GAP_MAX_PX = 90


def suspect_lines(gray):
    """返回疑似文字行：每行 [x0, y0, x1, y1, 连通域数]。"""
    mask = gray < DARK
    lab, n = ndimage.label(mask)
    if n == 0:
        return []
    boxes = []
    for sl in ndimage.find_objects(lab):
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        bh, bw = y1 - y0, x1 - x0
        if not (MIN_H <= bh <= MAX_H):
            continue
        if not (MIN_W <= bw <= MAX_W):
            continue
        if bw > 12 and bh < 7:                 # 长细横线（边框/阴影），不是字
            continue
        boxes.append([x0, y0, x1, y1, bh])
    if not boxes:
        return []
    boxes.sort(key=lambda b: (b[1] + b[3]) / 2.0)
    rows = []
    for b in boxes:
        placed = False
        for r in rows:
            ry = (r[0][1] + r[0][3]) / 2.0
            if abs(ry - (b[1] + b[3]) / 2.0) <= max(8, r[1] * 0.55):
                r[0] = [min(r[0][0], b[0]), min(r[0][1], b[1]),
                        max(r[0][2], b[2]), max(r[0][3], b[3])]
                r[1] = max(r[1], b[3] - b[1])
                r[2].append(b)
                placed = True
                break
        if not placed:
            rows.append([[b[0], b[1], b[2], b[3]], b[3] - b[1], [b]])
    out = []
    for r in rows:
        if len(r[2]) < MIN_PER_LINE:
            continue
        comps = sorted(r[2], key=lambda b: b[0])
        gaps = [comps[i + 1][0] - comps[i][2] for i in range(len(comps) - 1)]
        if gaps and max(gaps) > GAP_MAX_PX:
            continue
        hs = np.array([b[3] - b[1] for b in comps], dtype=float)
        if hs.mean() <= 0:
            continue
        h_cv = hs.std() / hs.mean()
        if h_cv > H_CV_MAX or hs.max() / max(hs.min(), 1) > H_RATIO_MAX:
            continue
        ws = np.array([b[2] - b[0] for b in comps], dtype=float)
        if ws.std() / max(ws.mean(), 1.0) > W_CV_MAX:
            continue
        if len(gaps) >= 2:
            g = np.array(gaps, dtype=float)
            if g.std() / max(g.mean(), 1.0) > GAP_CV_MAX:
                continue
        out.append({"box": r[0], "n": len(r[2]), "h": r[1],
                    "h_cv": round(float(h_cv), 3)})
    return out


def scan(src):
    """src 可以是路径，也可以是已打开的 PIL Image。"""
    im = src if isinstance(src, Image.Image) else Image.open(src)
    gray = np.asarray(im.convert("L"))
    return suspect_lines(gray)


def self_test():
    """负控制：合成一张"有字"的图必须被抓出；一张干净图必须不报。"""
    ok = True
    bad = Image.new("RGB", (1200, 400), "#F3EFE6")
    d = ImageDraw.Draw(bad)
    for i in range(9):                          # 9 个等高、间距均匀的字形
        x = 120 + i * 60
        d.rectangle([x, 180, x + 34, 212], fill="#20242A")
        d.rectangle([x + 4, 216, x + 30, 220], fill="#20242A")
    hits = scan(bad)
    if not hits:
        print("FAIL 负控制：合成文字未被检出")
        ok = False
    else:
        print("PASS 负控制：合成文字被检出（%d 行）" % len(hits))
    clean = Image.new("RGB", (1200, 400), "#F3EFE6")
    d = ImageDraw.Draw(clean)
    for i in range(40):                         # 散乱木纹质感，不成行
        d.ellipse([100 + (i * 37) % 900, 60 + (i * 53) % 260,
                   116 + (i * 37) % 900, 78 + (i * 53) % 260], fill="#C9BFAE")
    hits2 = scan(clean)
    if hits2:
        print("FAIL 负控制：干净图被误报 %d 行" % len(hits2))
        ok = False
    else:
        print("PASS 负控制：干净图不误报")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成图文字筛查闸门")
    ap.add_argument("--dir", help="待筛查图片目录")
    ap.add_argument("--out", default="_text_hits.json", help="命中报告 JSON")
    ap.add_argument("--crops", default="", help="命中区域裁切图输出目录")
    ap.add_argument("--ext", default=".png,.jpg,.jpeg", help="参与筛查的扩展名")
    ap.add_argument("--self-test", action="store_true", help="只跑负控制")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.dir or not os.path.isdir(args.dir):
        print("!! --dir 不存在或不是目录")
        return 2
    exts = tuple(e.strip().lower() for e in args.ext.split(","))
    files = sorted(f for f in os.listdir(args.dir) if f.lower().endswith(exts))
    if not files:
        print("!! 目录里没有可筛查的图片")
        return 2
    if args.crops:
        os.makedirs(args.crops, exist_ok=True)
    report = {}
    for f in files:
        p = os.path.join(args.dir, f)
        try:
            hits = scan(p)
        except Exception as exc:
            print("!! 读取失败 %s：%s" % (f, exc))
            return 2
        if not hits:
            continue
        hits.sort(key=lambda d: -d["n"])
        report[f] = hits
        if args.crops:
            im = Image.open(p)
            for i, hd in enumerate(hits[:6]):
                x0, y0, x1, y1 = hd["box"]
                pad = 14
                crop = im.crop((max(0, x0 - pad), max(0, y0 - pad),
                                min(im.width, x1 + pad), min(im.height, y1 + pad)))
                crop.thumbnail((900, 260))
                crop.convert("RGB").save(
                    os.path.join(args.crops, "%s_%02d.jpg" % (f.rsplit(".", 1)[0], i)),
                    "JPEG", quality=90)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    if not report:
        print("PASS 未发现疑似文字（%d 张）" % len(files))
        return 0
    for f in sorted(report):
        hs = report[f]
        print("HIT  %-24s %d 行（最多一列 %d 个连通域）" % (f, len(hs), max(h["n"] for h in hs)))
    print("共 %d / %d 张有疑似文字，报告 %s" % (len(report), len(files), args.out))
    print("！筛查器不是判据：短标签可能逃过，仍须逐张目检。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
