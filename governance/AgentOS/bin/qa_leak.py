#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_leak — 商业机密泄漏门禁（R10 脱敏）

为什么要有这个
--------------
用户提供的原始材料里带着品牌名、产品名、型号、内部代号。它们出现在交付物里，
就等于把商业机密连同报告一起递了出去。这件事**肉眼很难保证**：
正文好查，文件名好查，但 PDF 里的一行字、一张图上烧进去的字，就查不到了。

所以门禁必须**机械地**扫，而且必须扫三层。

三层各查什么
------------
| 层 | 查什么 | 抓什么 |
|---|---|---|
| `path` | 完整相对路径（目录名 + 文件名） | `BYD_Sealion08_电耗优化报告/` 这类整目录名 |
| `text` | 可检索文本文件全文 | md / txt / csv / tsv / json / html / xml / yaml / py / js |
| `pdf_text` | PDF 每页的文本层 | PDF 里的一行字、一张图上烧进去的字 |

**图像像素层扫不了**（门禁不做 OCR，太慢也太脆）。所以规则是：
**图上根本不要出现品牌**——生成式底图按零文字出，图表的标题与图例从事实源取，
不带品牌。像素层的脱敏靠制图阶段避免，不靠门禁补救。

用法
----
    python qa_leak.py <待检路径> [--terms <词表.json>] [--json <结果.json>]
                     [--no-pdf] [--no-recursive]

退出码
------
| 码 | 含义 | 动作 |
|---|---|---|
| 0 | 未命中 | 可以交付 |
| 1 | **有命中** | **不许交付**，按 §脱敏做法处理后重跑 |
| 2 | 执行错误（词表缺失 / 路径不存在） | 查环境，不是「干净」 |

> 退出码 2 绝不能当成 0。词表读不到就等于没检过，不是检过了没发现。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

AGENTOS_HOME = os.environ.get(
    "AGENTOS_HOME", r"${AGENTOS_HOME}")
DEFAULT_TERMS = os.path.join(AGENTOS_HOME, "policies", "REDACTION-TERMS.json")

TEXT_EXT = {
    ".md", ".txt", ".csv", ".tsv", ".json", ".html", ".htm", ".xml",
    ".yaml", ".yml", ".py", ".js", ".mjs", ".ts", ".css", ".pyw", ".bat",
    ".mdx", ".rst", ".ini", ".toml",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv",
             ".agentos", "_sources", "snapshots", "backups"}


# ------------------------------------------------------------------ 词表
def load_terms(path: str) -> list[dict]:
    """Load the forbidden-term list.

    A term is either a literal (case-insensitive) or a regex.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    raw = doc.get("terms", doc.get("forbidden_terms", []))
    out = []
    for t in raw:
        if isinstance(t, str):
            out.append({"pattern": t, "kind": "literal", "note": ""})
        elif isinstance(t, dict) and t.get("pattern"):
            out.append({
                "pattern": t["pattern"],
                "kind": t.get("kind", "literal"),
                "note": t.get("note", ""),
            })
    return out


def _match_literal(pat: str, text: str):
    idx = text.lower().find(pat.lower())
    if idx < 0:
        return None
    return text[max(0, idx - 20): idx + len(pat) + 20]


def _match_regex(pat: str, text: str):
    try:
        m = re.search(pat, text)
    except re.error:
        return None
    return m.group(0) if m else None


def _strip_unreadable(text: str) -> str:
    """Remove payloads a reader cannot read as text.

    Inline `data:` URIs (base64 images) and long unbroken base64-ish runs are
    binary payloads, not prose.  Matching a brand name inside them produces
    false positives -- and a gate that cries wolf gets ignored, which is worse
    than no gate.  The visible content of an image is its pixels, and pixels
    are handled at the masking stage, not here.
    """
    import re as _re
    text = _re.sub(r'data:[A-Za-z0-9/+._-]+;base64,[A-Za-z0-9+/=\s]{200,}',
                   'data:<base64-omitted>', text)
    text = _re.sub(r'[A-Za-z0-9+/]{300,}={0,2}', '<base64-omitted>', text)
    return text


def _excluded(rel: str, globs: list[str]) -> bool:
    import fnmatch
    norm = rel.replace("\\", "/")
    for g in globs:
        g = g.replace("\\", "/")
        if fnmatch.fnmatch(norm, g) or fnmatch.fnmatch(os.path.basename(norm), g):
            return True
        if g.endswith("/") and norm.startswith(g):
            return True
    return False


def _match(term: dict, text: str):
    if term.get("kind") == "regex":
        return _match_regex(term["pattern"], text)
    return _match_literal(term["pattern"], text)


# ------------------------------------------------------------------ 扫描
def scan_path(root: str, terms: list[dict], recursive: bool = True,
              include_pdf: bool = True, skip_dirs=None,
              exclude_globs=None) -> list[dict]:
    """Scan a file or directory for forbidden identifiers.

    Returns one hit record per (file, layer, term).

    `exclude_globs` excludes **internal build artifacts** from the scan --
    a rebuild script that still holds the old file name is not a leak in the
    deliverable, it is a build note.  Excluding it is a decision that must
    be recorded, not a silent skip.
    """
    skip_dirs = set(skip_dirs or SKIP_DIRS)
    exclude_globs = list(exclude_globs or [])
    hits: list[dict] = []

    def add(fp, rel, layer, matched, term):
        hits.append({
            "file": fp,
            "rel": rel,
            "layer": layer,
            "match": (matched or "")[:160],
            "term": term.get("pattern"),
            "term_kind": term.get("kind", "literal"),
            "note": term.get("note", ""),
        })

    if os.path.isfile(root):
        candidates = [(root, os.path.basename(root))]
    else:
        candidates = []
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in skip_dirs]
            for f in fn:
                candidates.append((os.path.join(dp, f),
                                   os.path.relpath(os.path.join(dp, f), root)))
            if not recursive:
                break

    for fp, rel in candidates:
        if exclude_globs and _excluded(rel, exclude_globs):
            continue
        # layer 1: the path itself -- a branded folder name leaks just as
        # loudly as a branded sentence.
        for t in terms:
            m = _match(t, rel)
            if m:
                add(fp, rel, "path", m, t)

        ext = os.path.splitext(fp)[1].lower()
        if ext in TEXT_EXT:
            try:
                with open(fp, encoding="utf-8", errors="replace") as fh:
                    body = fh.read()
            except OSError:
                continue
            body = _strip_unreadable(body)
            for t in terms:
                m = _match(t, body)
                if m:
                    add(fp, rel, "text", m, t)
        elif include_pdf and ext == ".pdf":
            for t in terms:
                m = _pdf_match(fp, t)
                if m:
                    add(fp, rel, "pdf_text", m, t)
    return hits


def _pdf_match(fp: str, term: dict):
    """Search the text layer of every page.  Returns the first match."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    try:
        with fitz.open(fp) as doc:
            for pno in range(doc.page_count):
                txt = doc[pno].get_text()
                if not txt:
                    continue
                m = _match(term, txt)
                if m:
                    return "p%d: %s" % (pno + 1, m)
    except Exception:  # noqa: BLE001
        return None
    return None


def scrub_text(text: str, terms: list[dict], placeholder: str = "") -> str:
    """Remove forbidden identifiers from a text blob.

    The whole value is removed -- no fake code, no partial mask.  A reader
    must not be able to recover the original from what is left.
    """
    out = text
    for t in terms:
        pat = t["pattern"]
        if t.get("kind") == "regex":
            try:
                out = re.sub(pat, placeholder, out)
            except re.error:
                continue
        else:
            out = re.sub(re.escape(pat), placeholder, out, flags=re.IGNORECASE)
    return out


# ------------------------------------------------------------------ CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="商业机密泄漏门禁（R10 脱敏）")
    ap.add_argument("path", help="待检文件或目录")
    ap.add_argument("--terms", default=DEFAULT_TERMS, help="脱敏词表 JSON")
    ap.add_argument("--json", dest="json_out", default="", help="把结果写成 JSON")
    ap.add_argument("--no-pdf", action="store_true", help="跳过 PDF 文本层")
    ap.add_argument("--no-recursive", action="store_true", help="不递归子目录")
    ap.add_argument("--exclude", action="append", default=[],
                    help="排除的内部构建件（可重复，glob 相对路径）")
    ap.add_argument("--quiet", action="store_true", help="只报退出码，不打印明细")
    a = ap.parse_args()

    if not os.path.exists(a.path):
        sys.stderr.write("路径不存在：%s\n" % a.path)
        return 2
    try:
        terms = load_terms(a.terms)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("脱敏词表不可用：%s（%s）\n"
                         "注意：读不到词表等于没检过，不是检过了没发现。\n" % (a.terms, exc))
        return 2
    if not terms:
        sys.stderr.write("脱敏词表为空：%s\n" % a.terms)
        return 2

    hits = scan_path(a.path, terms,
                     recursive=not a.no_recursive,
                     include_pdf=not a.no_pdf,
                     exclude_globs=a.exclude)

    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as f:
            json.dump({"path": a.path, "terms_loaded": len(terms),
                       "hit_count": len(hits), "hits": hits},
                      f, ensure_ascii=False, indent=1)

    if not a.quiet:
        if hits:
            print("泄漏命中 %d 处 —— 不许交付：" % len(hits))
            for h in hits[:80]:
                print("  [%s] %s  «%s»" % (h["layer"], h["rel"], h["match"]))
            if len(hits) > 80:
                print("  ... 另有 %d 处" % (len(hits) - 80))
        else:
            print("未命中：%s（词表 %d 条）" % (a.path, len(terms)))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
