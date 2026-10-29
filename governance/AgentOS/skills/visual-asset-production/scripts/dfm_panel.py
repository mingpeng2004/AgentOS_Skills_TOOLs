#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DFM / 设计规范配图面板装配器 + 覆盖度门禁。

一条设计规范 = 一张图 + 要点清单 + 机理理由 + 失败模式。少任何一项都算未完成。

本工具做两件事：
  1. **装配**（`--spec` + `--outdir`）：把「规范条目 + 底图」渲染成面板 PNG。
     底图可以是生成式实景概念渲染，也可以是 `iso_render.py` 导出的等轴测实体。
     文字全部由程序画（可审校），底图只负责"长什么样"。
  2. **门禁**（`--gate`）：检查规范覆盖率、双语纯度、**数值自洽**与**判定完整性**。
     面板里出现的每个数字都必须能在事实源里找到 —— 这是"数据合理正确才是根本"
     的机械化守门。

**多面板 + 判定层**：一条规范可以并置多个底图（好 / 坏 / 中立），
判定由声明式数据给出、**加载期套用**，渲染器不逐图手写标记；
徽章是白底 + 同色描边 + **绘制出来的** √/×（不印字体字符，字体缺字会变方块），
半径固定；好坏左右顺序全局统一（好一律在左、坏一律在右）。

规范条目契约（JSON）：

{
  "meta": {"title": "注塑 DFM 设计规范", "count": 1, "facts": "facts.md"},
  "theme": {"bg": "#FFFFFF", "accent": "#826430", "alert": "#A64634"},
  "panels": [
    {
      "id": "wall",
      "title_zh": "壁厚均匀化与热节",
      "title_en": "Uniform walls, no hot spots",
      "points_zh": ["壁厚差越大，凝固时间差越大", "..."],
      "points_en": ["...", "..."],
      "reason_zh": "铸件的凝固时间由等效壁厚决定……",
      "reason_en": "Freezing time follows the equivalent wall thickness……",
      "failure_zh": "局部增厚 → 孤立液池 → 缩孔",
      "failure_en": "Local thickening -> isolated liquid pool -> shrinkage cavity",
      "bodies": [
        {"body": "good.png", "verdict": "good",
         "cap_zh": "等壁厚", "cap_en": "Uniform wall"},
        {"body": "bad.png", "verdict": "bad",
         "cap_zh": "局部增厚", "cap_en": "Local boss"}
      ],
      "callouts": [{"body": "bad.png", "fx": 0.5, "fy": 0.4,
                    "zh": "热节", "en": "Hot spot"}]
    }
  ]
}

用法：
    python dfm_panel.py --spec dfm_spec.json --outdir figures --gate
    python dfm_panel.py --self-test          # 正负控制：坏情形必须被抓住
"""
import argparse
import json
import os
import re
import sys

try:
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    from matplotlib.patches import Circle, FancyBboxPatch
    from PIL import Image
except Exception as exc:                      # pragma: no cover
    print("!! 缺少依赖 matplotlib/Pillow/numpy：%s" % exc)
    sys.exit(2)

for _f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
    try:
        fm.fontManager.addfont(_f)
    except Exception:
        pass
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Segoe UI", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")
NUMBER = re.compile(r"\d+(?:\.\d+)?")

# 面板分栏（与 iso_render 保持同一套版面语法）
REGION_BODY = (0.03, 0.15, 0.60, 0.88)
REGION_TEXT = (0.63, 0.26, 0.99, 0.88)

# 徽章：固定半径（不随面板大小变），白底 + 同色描边
BADGE_R = 0.021
VERDICTS = {"good": "good", "bad": "bad", "neutral": "neutral"}

THEME = {
    "bg": "#FFFFFF", "ink": "#1F2224", "sub": "#636F77",
    "accent": "#826430", "primary": "#497350", "alert": "#A64634",
    "rule": "#E8E4DD", "paper": "#FBF9F5",
    "good": "#497350", "bad": "#A64634", "neutral": "#636F77",
}
NUMERALS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

# 页脚声明行：工程判断与厂商数据的物理隔离声明（双语，默认值可被 meta 覆盖）
FOOTER = {
    "zh": "设计规范 · 工程判断（非厂商数据）",
    "en": "Design rule - engineering judgement (not vendor data)",
}

# 文本排版：行距按物理尺寸算，不按轴单位拍脑袋
LH_RATIO = 1.45          # 行高 / 字号
GAP_IN = 0.022           # 段落间距（英寸）
FS_STEPS = (7.6, 7.2, 6.8, 6.4, 6.0)   # 字号候选：先缩字，再加高画布


def _blocks(panel, lang, fs, col_w):
    """按给定字号切出三段文本的行。"""
    pts = []
    for p in panel.get("points_%s" % lang) or []:
        pts.extend(wrap_text("· " + str(p), fs, col_w - 0.02))
    reason = wrap_text(panel.get("reason_%s" % lang, ""), fs, col_w - 0.02)
    failure = wrap_text(panel.get("failure_%s" % lang, ""), fs, col_w - 0.02)
    return pts, reason, failure


def _layout(panel, lang, base_h=3.1):
    """定字号与画布高度：**先缩字，不加高**；缩到底仍放不下才加高画布。

    返回 (字号, 行距轴单位, 要点行, 理由行, 失败模式行, 画布高英寸)。
    """
    col_w = REGION_TEXT[2] - REGION_TEXT[0]
    avail_ax = REGION_TEXT[3] - REGION_TEXT[1] - 0.02
    for fs in FS_STEPS:
        pts, reason, failure = _blocks(panel, lang, fs, col_w)
        lh_in = fs * LH_RATIO / 72.0
        need = (len(pts) + len(reason) + len(failure)) * lh_in + 2 * GAP_IN
        if need <= avail_ax * base_h:
            return fs, lh_in / base_h, pts, reason, failure, base_h
    fs = FS_STEPS[-1]
    pts, reason, failure = _blocks(panel, lang, fs, col_w)
    lh_in = fs * LH_RATIO / 72.0
    need = (len(pts) + len(reason) + len(failure)) * lh_in + 2 * GAP_IN
    fig_h = need / avail_ax
    return fs, lh_in / fig_h, pts, reason, failure, fig_h


# ------------------------------------------------------------------ 基础
def _rgb(h):
    h = str(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def trim_content(im, tol=14, pad=2):
    """裁到底图**内容**边界，返回 (裁后图, (x0, y0) 裁切偏移)。"""
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    h, w, _ = a.shape
    bg = a[0, 0]
    diff = np.abs(a - bg).max(axis=2)
    mask = diff > tol
    if not mask.any():
        return im.convert("RGB"), (0, 0)
    ys, xs = np.where(mask)
    x0 = max(0, int(xs.min()) - pad)
    y0 = max(0, int(ys.min()) - pad)
    x1 = min(w, int(xs.max()) + 1 + pad)
    y1 = min(h, int(ys.max()) + 1 + pad)
    return im.convert("RGB").crop((x0, y0, x1, y1)), (x0, y0)


def _place(iw, ih, box_w, box_h):
    """像素图等比放进轴单位框，返回 (显示宽, 显示高)。"""
    scale = min(box_w / float(iw), box_h / float(ih))
    return iw * scale, ih * scale


def anchor_pos(co, info):
    """把 callout 的原图相对坐标换算成轴坐标。

    `co.fx/fy` 是**原图**相对坐标（0~1，原点在左上角）。
    `info` 是 placements 字典。

    注意缩放基准：显示宽 dw 是**裁切后**的图宽，所以比例必须是 dw / trimmed_w。
    早先误用 dw / orig_w —— 裁掉多少，锚点就偏多少（§9.8.2：锚点要实测）。
    """
    dw = info["dw"]
    tw = info["tw"]
    th_px = info["th"]
    s = dw / float(tw)                      # 裁切后图的显示比例
    src_x = float(co.get("fx", 0.5)) * info["orig_w"] - info["tx0"]
    src_y = float(co.get("fy", 0.5)) * info["orig_h"] - info["ty0"]
    src_x = min(max(src_x, 0.0), float(tw))
    src_y = min(max(src_y, 0.0), float(th_px))
    return info["ox"] + src_x * s, info["oy"] + (th_px - src_y) * s


_FONT_CACHE = {}
_FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
_FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

PANEL_W_IN = 6.2
UNIT_PT = PANEL_W_IN * 72.0


def text_w(text, pt, unit_pt=UNIT_PT):
    """文字宽度（轴单位）。面板坐标 0..1 铺满 6.2 英寸 ⇒ 1 轴单位 = 446.4 磅。"""
    from PIL import ImageFont
    key = (round(pt, 2), bool(_FONT_BOLD))
    if key not in _FONT_CACHE:
        path = _FONT_BOLD if pt >= 9.0 else _FONT_REG
        try:
            _FONT_CACHE[key] = ImageFont.truetype(path, int(round(pt * 10)))
        except Exception:
            _FONT_CACHE[key] = ImageFont.truetype(_FONT_REG, int(round(pt * 10)))
    return _FONT_CACHE[key].getlength(text) / 10.0 / unit_pt


def wrap_text(text, pt, max_units):
    """按实测字宽折行；中文逐字断，拉丁按空格断。"""
    text = str(text)
    if not text:
        return []
    tokens, buffer = [], ""
    for ch in text:
        if CJK.search(ch) or ch in "，。；：、（）《》“”‘’…—·":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            tokens.append(ch)
        elif ch == " ":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            tokens.append(" ")
        else:
            buffer += ch
    if buffer:
        tokens.append(buffer)
    lines, current = [], ""
    for token in tokens:
        candidate = current + token
        if current and text_w(candidate.rstrip(), pt) > max_units:
            lines.append(current.rstrip())
            current = token.lstrip() if token.strip() else ""
        else:
            current = candidate
    if current.strip():
        lines.append(current.rstrip())
    return lines


# ------------------------------------------------------------------ 判定层
def resolve_bodies(panel):
    """返回并置底图列表，**好一律在左、坏一律在右**（加载期统一，不逐图手写）。

    未声明判定（verdict 缺失或为 null）视为不合格 —— 见 check_spec。
    """
    bodies = panel.get("bodies")
    if not bodies:
        body = panel.get("body")
        if not body:
            return []
        bodies = [{"body": body, "verdict": panel.get("verdict", "neutral")}]
    order = {"good": 0, "neutral": 1, "bad": 2}
    return sorted(bodies, key=lambda b: (order.get(b.get("verdict"), 1),
                                         bodies.index(b)))


def _badge(ax, cx, cy, verdict, color):
    """白底 + 同色描边的圆徽章，√/× **画出来**（不印字体字符）。"""
    ax.add_patch(Circle((cx, cy), BADGE_R, facecolor="#FFFFFF", edgecolor=color,
                        lw=1.4, zorder=8))
    r = BADGE_R * 0.52
    if verdict == "good":
        ax.plot([cx - r * 0.75, cx - r * 0.2, cx + r * 0.8],
                [cy + r * 0.05, cy - r * 0.55, cy + r * 0.62],
                color=color, lw=1.8, solid_capstyle="round", zorder=9)
    elif verdict == "bad":
        ax.plot([cx - r * 0.6, cx + r * 0.6], [cy - r * 0.6, cy + r * 0.6],
                color=color, lw=1.8, solid_capstyle="round", zorder=9)
        ax.plot([cx - r * 0.6, cx + r * 0.6], [cy + r * 0.6, cy - r * 0.6],
                color=color, lw=1.8, solid_capstyle="round", zorder=9)
    else:
        ax.plot([cx - r * 0.6, cx + r * 0.6], [cy, cy], color=color, lw=1.8,
                solid_capstyle="round", zorder=9)


# ------------------------------------------------------------------ 门禁
def _numbers(text):
    return set(NUMBER.findall(str(text)))


def _anchor_pixel(body_path, fx, fy, body_root="."):
    """把原图相对坐标换算成裁切后图的像素坐标。"""
    full = body_path if os.path.isabs(body_path) else os.path.join(body_root, body_path)
    original = Image.open(full).convert("RGB")
    orig_w, orig_h = original.size
    image, (tx0, ty0) = trim_content(original)
    tw, th = image.size
    sx = min(max(float(fx) * orig_w - tx0, 0.0), float(tw - 1))
    sy = min(max(float(fy) * orig_h - ty0, 0.0), float(th - 1))
    return image, int(sx), int(sy)


def anchor_on_ink(body_path, fx, fy, body_root=".", tol=14):
    """引出线的锚点必须落在**有墨迹**的地方。

    §9.8.2：锚点要实测，不要照抄模型写的 —— 指一条到空纸上的引出线
    等于没有引出线。这条把它机械化。
    """
    image, sx, sy = _anchor_pixel(body_path, fx, fy, body_root)
    a = np.asarray(image).astype(np.int16)
    bg = a[0, 0]
    diff = int(np.abs(a[sy, sx] - bg).max())
    return diff > tol, diff


def check_spec(spec, facts_text=None, body_root="."):
    """返回问题清单（空 = 通过）。每条都指名道姓，不含糊。"""
    problems = []
    panels = spec.get("panels") or []
    if not panels:
        problems.append("spec 里没有 panels")
        return problems
    meta = spec.get("meta") or {}
    if meta.get("count") is not None and int(meta["count"]) != len(panels):
        problems.append("meta.count=%s 与实际规范条数 %d 不符" % (meta["count"], len(panels)))
    seen = set()
    for index, panel in enumerate(panels, 1):
        pid = panel.get("id") or ("#%d" % index)
        if pid in seen:
            problems.append("规范 ID 重复：%s" % pid)
        seen.add(pid)
        for key in ("title_zh", "title_en", "reason_zh", "reason_en",
                    "failure_zh", "failure_en"):
            if not str(panel.get(key, "")).strip():
                problems.append("%s：缺 %s（图 + 要点 + 理由 + 失败模式缺一不可）" % (pid, key))
        for key in ("points_zh", "points_en"):
            points = panel.get(key) or []
            if not isinstance(points, list) or len(points) < 2:
                problems.append("%s：%s 至少要 2 条要点（实得 %d）"
                                % (pid, key, len(points) if isinstance(points, list) else 0))
        # 底图与判定
        bodies = panel.get("bodies")
        if not bodies:
            if not panel.get("body"):
                problems.append("%s：缺底图 body" % pid)
        else:
            for b in bodies:
                verdict = b.get("verdict")
                if verdict is None or (isinstance(verdict, str) and not verdict.strip()):
                    problems.append("%s：底图 %s **没有声明判定**（good/bad/neutral 必填，"
                                    "未声明与'中立'不是一回事）" % (pid, b.get("body")))
                elif verdict not in VERDICTS:
                    problems.append("%s：底图 %s 的判定 %r 非法（只能是 good/bad/neutral）"
                                    % (pid, b.get("body"), verdict))
                path = b.get("body")
                if path:
                    full = path if os.path.isabs(path) else os.path.join(body_root, path)
                    if not os.path.isfile(full):
                        problems.append("%s：底图不存在 %s" % (pid, full))
                if not str(b.get("cap_zh", "")).strip() or not str(b.get("cap_en", "")).strip():
                    problems.append("%s：底图缺中英标题（cap_zh/cap_en）" % pid)
        for co in panel.get("callouts") or []:
            for axis in ("fx", "fy"):
                v = co.get(axis)
                if not isinstance(v, (int, float)) or not (0.0 <= float(v) <= 1.0):
                    problems.append("%s：callout 的 %s=%r 必须在 0~1（是原图内相对坐标）"
                                    % (pid, axis, v))
            if not str(co.get("zh", "")).strip() or not str(co.get("en", "")).strip():
                problems.append("%s：callout 缺中英文案" % pid)
            body = co.get("body")
            if body:
                full = body if os.path.isabs(body) else os.path.join(body_root, body)
                if os.path.isfile(full):
                    ok, diff = anchor_on_ink(body, co.get("fx", 0.5), co.get("fy", 0.5),
                                            body_root)
                    if not ok:
                        problems.append(
                            "%s：callout 的锚点落在**空白处**（像素差 %d ≤ %d）—— "
                            "引出线指到空纸上等于没有引出线，锚点要实测"
                            % (pid, diff, 14))
        # 双语纯度
        for key in ("title_en", "reason_en", "failure_en"):
            value = str(panel.get(key, ""))
            if CJK.search(value):
                problems.append("%s：%s 含中文字符（英文版必须零中文）" % (pid, key))
        for point in panel.get("points_en") or []:
            if CJK.search(str(point)):
                problems.append("%s：points_en 含中文字符：%s" % (pid, point))
        # 页脚声明行也要双语纯度（它曾经是硬编码中文，英文版照样印出来）
        foot_en = str(panel.get("footer_en",
                                (meta.get("footer_en", FOOTER["en"]))))
        if CJK.search(foot_en):
            problems.append("%s：footer_en 含中文字符（英文版必须零中文）：%s"
                            % (pid, foot_en))
        # 数值自洽
        if facts_text is not None:
            allowed = _numbers(facts_text)
            haystack = " ".join(
                [str(panel.get(k, "")) for k in ("title_zh", "title_en", "reason_zh",
                                                 "reason_en", "failure_zh", "failure_en")]
                + [str(x) for x in (panel.get("points_zh") or [])]
                + [str(x) for x in (panel.get("points_en") or [])]
                + [str(c.get("zh", "")) + " " + str(c.get("en", "")) for c in (panel.get("callouts") or [])]
            )
            for token in sorted(_numbers(haystack)):
                if token not in allowed:
                    problems.append("%s：数字 %r 在事实源里找不到出处" % (pid, token))
            # §9.13：渲染值必须与事实源逐字相同。
            # 失败模式尤其重要 —— 它最容易变成"自己写的一句话"。
            # 做法：失败模式必须是事实源里的**逐字子串**；要改写就先改事实源。
            for lang in ("zh", "en"):
                value = str(panel.get("failure_%s" % lang, "")).strip()
                if value and value not in facts_text:
                    problems.append(
                        "%s：failure_%s 不是事实源的逐字子串 —— 失败模式不得自撰，"
                        "请先把它写进事实源文件（§9.13）" % (pid, lang))
    return problems


# ------------------------------------------------------------------ 渲染
def render_panel(panel, lang, index, out_path, theme, body_root="."):
    """渲染一张面板。文字全部由程序绘制。"""
    th = dict(THEME)
    th.update(theme or {})
    fs, lh_ax, pts_lines, reason_lines, failure_lines, fig_h = _layout(panel, lang)
    fig = plt.figure(figsize=(PANEL_W_IN, fig_h))
    fig.patch.set_facecolor(th["bg"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(th["bg"])

    numeral = NUMERALS[index - 1] if index <= len(NUMERALS) else str(index)
    ax.text(0.03, 0.965, "%s %s" % (numeral, panel.get("title_%s" % lang, "")),
            fontsize=10.5, fontweight="bold", color=th["ink"], va="top")

    bx0, by0, bx1, by1 = REGION_BODY
    bodies = resolve_bodies(panel)
    n = max(1, len(bodies))
    gap = 0.018
    slot_w = (bx1 - bx0 - gap * (n - 1)) / n
    placements = {}
    for bi, b in enumerate(bodies):
        path = b.get("body")
        if not path:
            continue
        full = path if os.path.isabs(path) else os.path.join(body_root, path)
        if not os.path.isfile(full):
            continue
        original = Image.open(full).convert("RGB")
        orig_w, orig_h = original.size
        image, (tx0, ty0) = trim_content(original)
        slot_x0 = bx0 + bi * (slot_w + gap)
        dw, dh = _place(image.size[0], image.size[1], slot_w, by1 - by0 - 0.05)
        ox = slot_x0 + (slot_w - dw) / 2.0
        oy = by0 + (by1 - by0 - 0.05 - dh) / 2.0
        ax.imshow(image, extent=(ox, ox + dw, oy, oy + dh), aspect="auto", zorder=0)
        ax.add_patch(plt.Rectangle((slot_x0, by0), slot_w, by1 - by0,
                                   fc="none", ec=th["rule"], lw=0.8, zorder=3))
        verdict = b.get("verdict") or "neutral"
        color = th.get(verdict, th["neutral"])
        # 徽章：固定半径，落在该槽的右上角（不压内容）
        _badge(ax, slot_x0 + slot_w - BADGE_R * 1.6, by1 - BADGE_R * 1.6, verdict, color)
        # 该面板的中英标题
        cap = b.get("cap_%s" % lang, "")
        if cap:
            ax.text(slot_x0 + slot_w / 2.0, by0 - 0.018, cap, fontsize=8.0,
                    color=th["ink"], ha="center", va="top", zorder=5)
        placements[path] = {
            "ox": ox, "oy": oy, "dw": dw, "dh": dh,
            "orig_w": orig_w, "orig_h": orig_h,
            "tx0": tx0, "ty0": ty0,
            "tw": image.size[0], "th": image.size[1],
            "slot_x0": slot_x0, "slot_w": slot_w,
        }

    # 引出标注：锚点用**原图**相对坐标（0..1，原点在左上角）
    label_y = by1 - 0.065
    for co in panel.get("callouts") or []:
        text = str(co.get(lang, ""))
        if not text:
            continue
        key = co.get("body")
        info = placements.get(key)
        if not info:
            continue
        px, py = anchor_pos(co, info)
        # 标签要留在自己的槽里，且**避开徽章**：按实测字宽夹住，不许戳出槽框
        half = text_w(text, 7.2) / 2.0
        lo = info["slot_x0"] + half + 0.006
        hi = info["slot_x0"] + info["slot_w"] - half - 0.006
        lx = min(max(px, lo), hi) if hi > lo else info["slot_x0"] + info["slot_w"] / 2.0
        # 徽章占着右上角，标签不许压上去
        bx = info["slot_x0"] + info["slot_w"] - BADGE_R * 1.6
        badge_l = bx - BADGE_R * 1.2
        badge_r = bx + BADGE_R * 1.2
        if lx + half > badge_l and lx - half < badge_r:
            shifted = badge_l - half - 0.006
            if shifted >= lo:
                lx = shifted
            elif badge_r + half + 0.006 <= hi:
                lx = badge_r + half + 0.006
        # 引出线从特征点斜拉到标签（钳位后不再垂直，才不会指错地方）
        ax.plot([px, lx], [py, label_y - 0.012], color=th["accent"], lw=0.9, zorder=4)
        ax.plot([px], [py], marker="o", ms=2.6, color=th["accent"], zorder=5)
        ax.text(lx, label_y, text, ha="center", va="bottom", fontsize=7.2,
                color=th["accent"], zorder=5)
        label_y -= 0.055

    # 右列：要点 → 理由 → 失败模式
    tx = REGION_TEXT[0]
    ty = REGION_TEXT[3] - 0.02
    for line in pts_lines:
        ax.text(tx, ty, line, fontsize=fs, color=th["sub"], ha="left", va="top")
        ty -= lh_ax
    ty -= GAP_IN / fig_h
    for line in reason_lines:
        ax.text(tx, ty, line, fontsize=fs, color=th["accent"], ha="left", va="top")
        ty -= lh_ax
    ty -= GAP_IN / fig_h
    for line in failure_lines:
        ax.text(tx, ty, line, fontsize=fs, color=th["alert"], ha="left", va="top")
        ty -= lh_ax
    if ty < REGION_TEXT[1] - 0.02:
        raise ValueError("右列文本溢出：面板 %s / %s 剩余 %.3f 轴单位"
                         % (panel.get("id"), lang, ty - REGION_TEXT[1]))

    ax.text(REGION_BODY[0], 0.05, panel.get("footer_%s" % lang, FOOTER[lang]),
            fontsize=6.6, color=th["sub"], ha="left", va="center")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    fig.savefig(out_path, dpi=200, facecolor=th["bg"])
    plt.close(fig)
    return out_path


def render_all(spec, outdir, body_root="."):
    theme = spec.get("theme") or {}
    meta = spec.get("meta") or {}
    made = []
    for index, panel in enumerate(spec.get("panels") or [], 1):
        panel = dict(panel)
        # 页脚声明行：允许 meta 覆盖，但默认双语
        for lang in ("zh", "en"):
            panel.setdefault("footer_%s" % lang,
                             meta.get("footer_%s" % lang, FOOTER[lang]))
        for lang in ("zh", "en"):
            out = os.path.join(outdir, "%s_%s.png" % (panel.get("id", "p%02d" % index), lang))
            made.append(render_panel(panel, lang, index, out, theme, body_root))
    return made


# ------------------------------------------------------------------ 自检
FIXTURE = {
    "meta": {"title": "注塑 DFM 设计规范", "count": 1},
    "panels": [{
        "id": "wall",
        "title_zh": "壁厚、筋厚与圆角",
        "title_en": "Wall, rib and fillet",
        "points_zh": ["名义壁厚 2.0~3.0 mm", "筋厚 ≤ 0.6 × 壁厚"],
        "points_en": ["nominal wall 2.0-3.0 mm", "rib <= 0.6 x wall"],
        "reason_zh": "缩痕来自局部收缩量超过体积补偿，筋过厚时表面先冷、补缩不足。",
        "reason_en": "Sink marks appear where local shrinkage exceeds what the wall can feed.",
        "failure_zh": "筋过厚 → 表面缩痕",
        "failure_en": "A thick rib sinks the surface",
        "bodies": [
            {"body": "good.png", "verdict": "good", "cap_zh": "等壁厚", "cap_en": "Uniform"},
            {"body": "bad.png", "verdict": "bad", "cap_zh": "局部增厚", "cap_en": "Local boss"},
        ],
        "callouts": [{"body": "bad.png", "fx": 0.5, "fy": 0.5,
                      "zh": "热节", "en": "Hot spot"}],
        "footer_zh": "设计规范 · 工程判断（非厂商数据）",
        "footer_en": "Design rule - engineering judgement (not vendor data)",
    }],
}
FIXTURE_FACTS = ("名义壁厚 2.0~3.0 mm；筋厚 ≤ 0.6 × 壁厚\n"
                 "筋过厚 → 表面缩痕\n"
                 "A thick rib sinks the surface")


def self_test():
    """正负控制：缺理由 / 英文混中文 / 无出处数字 / 缺底图 / 条数不符 / 未声明判定。"""
    import copy
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        # 底图要有**墨迹**：锚点门禁要能判"指在实体上"与"指在空白处"
        for name, body in (("good.png", "#D9D3C6"), ("bad.png", "#D2CCBE")):
            im = Image.new("RGB", (1200, 900), "#FFFFFF")
            from PIL import ImageDraw
            draw = ImageDraw.Draw(im)
            draw.rectangle([300, 250, 900, 650], fill=body)
            draw.ellipse([570, 420, 630, 480], fill="#A64634")
            im.save(os.path.join(td, name))
        spec = copy.deepcopy(FIXTURE)
        problems = check_spec(spec, FIXTURE_FACTS, td)
        if problems:
            print("FAIL 正控制：合规规范被判不合格：%s" % "; ".join(problems))
            ok = False
        else:
            print("PASS 正控制：合规规范通过门禁")
        out = os.path.join(td, "out")
        made = render_all(spec, out, td)
        if len(made) != 2 or any(not os.path.isfile(m) for m in made):
            print("FAIL 正控制：应出 2 张（中英），实得 %d" % len(made))
            ok = False
        else:
            print("PASS 正控制：渲染 %d 张面板" % len(made))

        bad = copy.deepcopy(spec)
        bad["panels"][0]["reason_zh"] = ""
        if not any("reason_zh" in p for p in check_spec(bad, FIXTURE_FACTS, td)):
            print("FAIL 负控制：缺机理理由未被拦下"); ok = False
        else:
            print("PASS 负控制：缺机理理由被拦下")

        bad = copy.deepcopy(spec)
        bad["panels"][0]["title_en"] = "Wall 壁厚"
        if not any("含中文字符" in p for p in check_spec(bad, FIXTURE_FACTS, td)):
            print("FAIL 负控制：英文混中文未被拦下"); ok = False
        else:
            print("PASS 负控制：英文混中文被拦下")

        bad = copy.deepcopy(spec)
        bad["panels"][0]["points_zh"] = ["名义壁厚 2.0~3.0 mm", "收缩率 0.45%"]
        if not any("找不到出处" in p for p in check_spec(bad, FIXTURE_FACTS, td)):
            print("FAIL 负控制：无出处数字未被拦下"); ok = False
        else:
            print("PASS 负控制：无出处数字被拦下")

        bad = copy.deepcopy(spec)
        bad["panels"][0]["bodies"][1]["body"] = "nope.png"
        if not any("底图不存在" in p for p in check_spec(bad, FIXTURE_FACTS, td)):
            print("FAIL 负控制：缺底图未被拦下"); ok = False
        else:
            print("PASS 负控制：缺底图被拦下")

        bad = copy.deepcopy(spec)
        bad["meta"]["count"] = 3
        if not any("meta.count" in p for p in check_spec(bad, FIXTURE_FACTS, td)):
            print("FAIL 负控制：条数不符未被拦下"); ok = False
        else:
            print("PASS 负控制：条数不符被拦下")

        # 负控制：判定缺失（金属制程库实测有 5 个这样的面板）
        bad = copy.deepcopy(spec)
        bad["panels"][0]["bodies"][1]["verdict"] = None
        if not any("没有声明判定" in p for p in check_spec(bad, FIXTURE_FACTS, td)):
            print("FAIL 负控制：未声明判定未被拦下"); ok = False
        else:
            print("PASS 负控制：未声明判定被拦下")

        # 负控制：缺失败模式
        bad = copy.deepcopy(spec)
        bad["panels"][0]["failure_zh"] = ""
        if not any("failure_zh" in p for p in check_spec(bad, FIXTURE_FACTS, td)):
            print("FAIL 负控制：缺失败模式未被拦下"); ok = False
        else:
            print("PASS 负控制：缺失败模式被拦下")

        # 负控制：失败模式不是事实源的逐字子串（§9.13）
        bad = copy.deepcopy(spec)
        bad["panels"][0]["failure_zh"] = "筋太粗会让表面塌下去"
        if not any("逐字子串" in p for p in check_spec(bad, FIXTURE_FACTS, td)):
            print("FAIL 负控制：自撰失败模式未被拦下"); ok = False
        else:
            print("PASS 负控制：自撰失败模式被拦下")

        # 负控制：锚点落在空白处（引出线指到空纸上）
        bad = copy.deepcopy(spec)
        bad["panels"][0]["callouts"][0]["fx"] = 0.02
        bad["panels"][0]["callouts"][0]["fy"] = 0.02
        if not any("空白处" in p for p in check_spec(bad, FIXTURE_FACTS, td)):
            print("FAIL 负控制：锚点落在空白处未被拦下"); ok = False
        else:
            print("PASS 负控制：锚点落在空白处被拦下")

        # 负控制：英文页脚混入中文（页脚曾经是硬编码中文，英文版照样印出来）
        bad = copy.deepcopy(spec)
        bad["panels"][0]["footer_en"] = "设计规范 · 工程判断"
        if not any("footer_en" in p for p in check_spec(bad, FIXTURE_FACTS, td)):
            print("FAIL 负控制：英文页脚含中文未被拦下"); ok = False
        else:
            print("PASS 负控制：英文页脚含中文被拦下")

        # 判定排序：好一律在左、坏一律在右（加载期统一）
        order = [b.get("verdict") for b in resolve_bodies(
            {"bodies": [{"body": "b.png", "verdict": "bad"},
                        {"body": "g.png", "verdict": "good"}]})]
        if order != ["good", "bad"]:
            print("FAIL 负控制：好坏左右顺序未统一：%s" % order); ok = False
        else:
            print("PASS 判定排序：好一律在左、坏一律在右")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="DFM 设计规范配图面板装配器 + 门禁")
    ap.add_argument("--spec", help="规范条目契约 JSON")
    ap.add_argument("--outdir", help="面板输出目录")
    ap.add_argument("--base-root", default="", help="底图相对路径的根目录")
    ap.add_argument("--facts", help="事实源文件（数值自洽门禁用）")
    ap.add_argument("--gate", action="store_true", help="只跑门禁不出图")
    ap.add_argument("--self-test", action="store_true", help="正负控制")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.spec or not os.path.exists(args.spec):
        print("!! --spec 不存在")
        return 2
    with open(args.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    root = args.base_root or os.path.dirname(os.path.abspath(args.spec))
    facts_text = None
    facts_path = args.facts or (spec.get("meta") or {}).get("facts")
    if facts_path:
        fpath = facts_path if os.path.isabs(facts_path) else os.path.join(root, facts_path)
        if not os.path.isfile(fpath):
            print("!! 事实源不存在：%s" % fpath)
            return 2
        with open(fpath, encoding="utf-8") as fh:
            facts_text = fh.read()

    problems = check_spec(spec, facts_text, root)
    if problems:
        print("门禁未通过（%d 项）：" % len(problems))
        for p in problems:
            print("  - %s" % p)
        return 1
    print("门禁通过：%d 条规范" % len(spec.get("panels") or []))
    if args.gate:
        return 0
    if not args.outdir:
        print("!! --outdir 必填（除非 --gate）")
        return 2
    made = render_all(spec, args.outdir, root)
    print("渲染 %d 张面板 → %s" % (len(made), args.outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
