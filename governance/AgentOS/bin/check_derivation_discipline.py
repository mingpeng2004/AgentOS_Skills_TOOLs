#!/usr/bin/env python
"""推导纪律机械门禁（AgentOS protocols/DERIVATION-DISCIPLINE.md §4）。

三条扫描，对应协议 §4 的 S1/S2/S3：

  S1 数值冲突     同一标识符在同一批文件里出现**不同数值** ⇒ 需裁决（先前的自相矛盾）
  S2 强度不匹配   强断言（必须/保证/就是/因此断定…）所在段落**无证据等级标签**
  S3 未闭合缺口   缺口词（TBD/待实测/待确认/待补/空占位）所在段落**无取证路径**
  S4 弱化与强断言并存  同一段落既说"可能/大概/应该"又说"必须/保证/就是" ⇒ 措辞可疑

用法：
    python check_derivation_discipline.py <file-or-dir> [<file-or-dir> ...]
    python check_derivation_discipline.py --warn-only <paths>     # 只报告不阻断
退出码：0 = 通过；1 = 有发现（阻断）；2 = 参数/环境错
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---- 词表 ----
TAGS = ("[实测]", "[图纸]", "[推论]", "[假设]", "[用户]", "[推导]", "[观测]", "[代码]",
         "[规范]", "[normative]")
STRONG = ("必须", "保证", "一定会", "就是", "因此断定", "因此可以断定", "必然", "绝不会", "等价于")
HEDGE = ("可能", "大概", "应该", "推测", "似乎", "也许", "倾向于")
GAP = ("TBD", "tbd", "待确认", "待实测", "待补", "待定", "待核实", "待查", "？？", "??", "___", "???")
CLOSE = ("取证", "如何验证", "验证方法", "怎么测", "下一步", "量测", "实测", "复测", "方法", "路径", "待取", "需测")
# 流程指令句式：不是技术断言，S2 不报
PROCEDURAL = ("必须核对", "必须确认", "必须执行", "必须遵守", "必须走", "必须填", "必须先",
              "必须按", "必须用", "必须把", "必须给", "必须能", "必须每", "必须做", "必须量",
              "必须等", "必须再", "必须保持", "必须连", "必须带", "禁止", "务必", "不得")

DOC_EXT = {".md", ".markdown", ".txt", ".rst"}
CODE_FENCE = re.compile(r"^\s*```")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
NUM_ASSIGN = re.compile(r"`([A-Za-z_][A-Za-z0-9_./-]{2,})`\s*(?:=|＝)\s*([-+]?\d+(?:\.\d+)?)")
TABLE_ROW = re.compile(r"^\s*\|")
# 文档级规范标记：整篇是"应当怎么做"的规范/经验条目 ⇒ 不做强度匹配（S2/S4），仍做 S1/S3
NORMATIVE_DOC_MARKER = "<!-- DERIVATION:NORMATIVE-DOC -->"


def strip_code_blocks(lines: list[str]) -> list[str]:
    """移除代码块内容，但**保留行数**（用空行占位）⇒ 报告的行号始终等于文件真实行号。"""
    out, inside = [], False
    for ln in lines:
        if CODE_FENCE.match(ln):
            inside = not inside
            out.append("")          # 围栏行本身也占位
            continue
        out.append("" if inside else ln)
    return out


def paragraphs(lines: list[str]) -> list[tuple[int, str]]:
    """把正文切成段落：空行分隔；**表格行各自成段**（表头/分隔行不参与判定）。"""
    paras, buf, start = [], [], 0
    for i, ln in enumerate(lines, 1):
        if not ln.strip():
            if buf:
                paras.append((start, "\n".join(buf)))
                buf = []
            continue
        if TABLE_ROW.match(ln):
            if buf:
                paras.append((start, "\n".join(buf)))
                buf = []
            if set(ln.strip()) <= set("|-: "):
                continue                      # 表格分隔行
            paras.append((i, ln.strip()))
            continue
        if not buf:
            start = i
        buf.append(ln)
    if buf:
        paras.append((start, "\n".join(buf)))
    return paras


def collect_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            files += [f for f in pp.rglob("*")
                      if f.is_file() and f.suffix.lower() in DOC_EXT
                      and ".git" not in f.parts]
        elif pp.is_file():
            files.append(pp)
    return sorted(set(files))


def check(files: list[Path]) -> list[tuple[str, str, int, str]]:
    findings: list[tuple[str, str, int, str]] = []

    # S1 数值冲突：同一标识符 → 多个不同数值
    seen: dict[str, dict[str, list[tuple[Path, int]]]] = {}
    for f in files:
        try:
            lines = strip_code_blocks(f.read_text(encoding="utf-8", errors="replace").splitlines())
        except Exception as exc:  # noqa: BLE001
            findings.append(("S0", str(f), 0, f"读取失败：{exc}"))
            continue
        for i, ln in enumerate(lines, 1):
            for ident, num in NUM_ASSIGN.findall(ln):
                seen.setdefault(ident, {}).setdefault(num, []).append((f, i))

    for ident, nums in sorted(seen.items()):
        if len(nums) > 1:
            detail = "；".join(
                f"{v} @ {p.name}:{ln}" for v, locs in sorted(nums.items()) for p, ln in locs[:2])
            findings.append(("S1", ident, 0, f"同一标识符出现 {len(nums)} 个不同数值 ⇒ 需裁决：{detail}"))

    # S2/S3/S4 段落级扫描
    for f in files:
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
            head = " ".join(raw.splitlines()[:40])
            doc_normative = NORMATIVE_DOC_MARKER in head
            lines = strip_code_blocks(raw.splitlines())
        except Exception:
            continue
        for start, para in paragraphs(lines):
            if TABLE_ROW.match(para):
                # 表格行交给 S1（数值冲突）判定；证据标签纪律在正文与表注中执行
                continue
            has_tag = any(re.search(r"\[" + t.strip("[]") + r"[^\]]*\]", para) for t in TAGS)
            has_strong = any(w in para for w in STRONG)
            has_hedge = any(w in para for w in HEDGE)
            has_gap = any(w in para for w in GAP)
            has_close = any(w in para for w in CLOSE)
            has_digit = bool(re.search(r"\d", para))
            # 流程指令（"必须逐条核对/必须执行/必须遵守…"）不是技术断言，不报 S2
            procedural = any(p in para for p in PROCEDURAL)
            if has_strong and not has_tag and has_digit and not procedural and len(para) > 40 and not doc_normative:
                findings.append(("S2", f.name, start,
                                "强断言无证据等级标签（须加 [实测]/[图纸]/[推论]/[假设]）"))
            if has_gap and not has_close:
                findings.append(("S3", f.name, start,
                                "缺口词未附取证路径（须写：怎么取/怎么测/什么算过）"))
            # 规范句（[规范]）规定"应当怎么做"，不是对世界的断言 ⇒ 不参与强度匹配检查
            normative = ("[规范]" in para) or ("[normative]" in para)
            if has_hedge and has_strong and not normative and not doc_normative:
                findings.append(("S4", f.name, start,
                                "同段既有弱化词又有强断言 ⇒ 措辞与证据强度不匹配"))
    return findings


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--warn-only", action="store_true")
    ap.add_argument("--regression", metavar="FILE",
                    help="run against the real-error regression set and report the catch rate")
    args = ap.parse_args(argv)

    if args.regression:
        return run_regression(Path(args.regression))

    if not args.paths:
        ap.error("no paths given")
    files = collect_files(args.paths)
    if not files:
        print("未找到可检查的文档（.md/.txt/.rst）")
        return 2
    findings = check(files)
    if not findings:
        print(f"推导纪律门禁：通过（{len(files)} 个文件，0 发现）")
        return 0
    by_kind: dict[str, list] = {}
    for kind, where, line, msg in findings:
        by_kind.setdefault(kind, []).append((where, line, msg))
    print(f"推导纪律门禁：{len(findings)} 处发现（{len(files)} 个文件）")
    for kind in sorted(by_kind):
        print(f"\n[{kind}] {len(by_kind[kind])} 处")
        for where, line, msg in by_kind[kind][:40]:
            loc = f"{where}:{line}" if line else where
            print(f"   {loc}  {msg}")
    return 0 if args.warn_only else 1


def run_regression(path: Path) -> int:
    """Measure this gate's discriminating power against real errors.

    A gate that reports "pass, exit 0" on errors that actually happened has no
    discriminating power for that error class, no matter how well it is
    distributed.  This mode is the only way to see that number.

    The samples are written to a temporary directory: the regression set lives
    on the production disk and must never be modified by a measurement.
    """
    import json
    import shutil
    import tempfile

    data = json.loads(path.read_text(encoding="utf-8"))
    samples = data.get("samples") or []
    if not samples:
        print(f"回归集为空：{path}")
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="derivation_regression_"))
    try:
        for s in samples:
            (tmp / f"{s['id']}.md").write_text(
                f"# {s.get('title', s['id'])}\n\n{s['verbatim']}\n", encoding="utf-8")
        files = collect_files([str(tmp)])
        findings = check(files)
        hit_ids = set()
        for _kind, where, _line, _msg in findings:
            for s in samples:
                if Path(str(where)).name == f"{s['id']}.md":
                    hit_ids.add(s["id"])

        total = len(samples)
        caught = len(hit_ids)
        rate = caught / total if total else 0.0
        min_rate = float(data.get("admission_rule", {}).get("min_catch_rate_for_new_gate", 0.75))

        print(f"推导纪律门禁 · 真实错误回归集：{path}")
        print(f"  样本 {total} 条，命中 {caught} 条，抓取率 {caught}/{total} = {rate:.0%}")
        print("  闸的退出码在无命中时为 0 ⇒ 抓取率低时该闸对这些错误类无鉴别力")
        print()
        for s in samples:
            mark = "CAUGHT" if s["id"] in hit_ids else "MISSED"
            print(f"  {mark:7s} {s['id']:5s} [{s.get('tier','?')}] {s.get('title','')}")
        print()
        if rate >= min_rate:
            print(f"VERDICT: 达到准入门槛（>= {min_rate:.0%}）")
            return 0
        print(f"VERDICT: 未达准入门槛（< {min_rate:.0%}）⇒ 该闸对本错误类无鉴别力，"
              "不得作为阻断闸上线")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
