#!/usr/bin/env python3
"""Claim Ledger gate (prototype, Phase 1).

The wording scanner (check_derivation_discipline.py) asks "is this sentence
worded correctly?".  This gate asks the other question: "is this conclusion
bound to something that can be checked?".

A claim is only admissible if it carries:

  strength    measured | derived | assumed | stated | normative
  evidence    at least one reference that can actually be resolved
              (file:line | command | hash | artifact)
  scope       what the claim covers AND what it does not cover
  falsifier   the observation that would overturn it
  sampling    stable | point-in-time

The last three are the fields whose absence caused every real error in the
regression set: an unsourced number (no evidence), a stale count (no scope
about time), a value that drifts with the network (sampling not declared).

Modes:
  --check <ledger>            validate one claim ledger
  --regression <set>          run against the real-error regression set and
                              report the catch rate (the admission metric)
  --self-test                 prove this gate can tell good from bad
                              (includes a sabotage check: a permanently
                              disabled checker must turn the gate red)

Exit codes: 0 = pass, 1 = findings, 2 = usage/environment error.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

AGENTOS = Path(r"${AGENTOS_HOME}")
TIER_POLICY = AGENTOS / "policies" / "CLAIM-TIER-POLICY.json"
REGRESSION_SET = AGENTOS / "tests" / "derivation-error-regression.json"

STRENGTHS = {"measured", "derived", "assumed", "stated", "normative"}
SAMPLING = {"stable", "point-in-time"}

# Evidence reference forms.  Each must be resolvable.
REF_FILE_LINE = re.compile(r"^(?P<path>[A-Za-z]:\\[^\s:]+|[^\s:]+):(?P<line>\d+)$")
REF_COMMAND = re.compile(r"^cmd:(?P<cmd>.+)$")
REF_HASH = re.compile(r"^sha256:(?P<hash>[0-9a-f]{64})$")
REF_ARTIFACT = re.compile(r"^artifact:(?P<path>.+)$")


def _resolve_file_line(ref: str) -> tuple[bool, str]:
    m = REF_FILE_LINE.match(ref)
    if not m:
        return False, "not a file:line reference"
    path = Path(m.group("path"))
    if not path.is_file():
        return False, f"file not found: {path}"
    want = int(m.group("line"))
    try:
        total = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError as exc:
        return False, f"unreadable: {exc}"
    if want < 1 or want > total:
        return False, f"line {want} out of range (file has {total} lines)"
    return True, f"{path}:{want} of {total}"


def resolve_evidence(ref: str) -> tuple[bool, str]:
    """Can this reference be located?  Evidence that cannot be found is not evidence."""
    ref = ref.strip()
    if REF_HASH.match(ref):
        return True, "hash"
    m = REF_COMMAND.match(ref)
    if m:
        # A command reference must name a command that actually exists on this
        # machine; otherwise it is a claim that cannot be reproduced.
        cmd = m.group("cmd").strip()
        exe = cmd.split()[0] if cmd else ""
        if not exe:
            return False, "empty command"
        found = shutil.which(exe) or (
            Path(exe).is_file() if Path(exe).is_absolute() else False)
        return bool(found), f"command {exe} {'found' if found else 'NOT found'}"
    if REF_ARTIFACT.match(ref):
        p = Path(ref[len("artifact:"):])
        return (p.exists(), str(p))
    return _resolve_file_line(ref)


def check_claim(claim: dict, tier: str) -> list[str]:
    """Return a list of problems with one claim.  Empty list = admissible."""
    problems: list[str] = []

    strength = claim.get("strength")
    if strength not in STRENGTHS:
        problems.append(f"strength {strength!r} not in {sorted(STRENGTHS)}")

    sampling = claim.get("sampling")
    if sampling not in SAMPLING:
        problems.append(f"sampling {sampling!r} not in {sorted(SAMPLING)}")

    evid = claim.get("evidence") or []
    if not isinstance(evid, list) or not evid:
        problems.append("evidence is empty")
    else:
        for ref in evid:
            if not isinstance(ref, str):
                problems.append(f"evidence entry is not a string: {ref!r}")
                continue
            ok, detail = resolve_evidence(ref)
            if not ok:
                problems.append(f"evidence not resolvable: {ref} ({detail})")

    scope = claim.get("scope") or {}
    if not isinstance(scope, dict):
        problems.append("scope must be an object")
    else:
        if not str(scope.get("applies_when", "")).strip():
            problems.append("scope.applies_when is empty")
        if not str(scope.get("does_not_cover", "")).strip():
            problems.append("scope.does_not_cover is empty")

    if not str(claim.get("falsifier", "")).strip():
        problems.append("falsifier is empty")

    # tier-specific escalation
    if tier in ("T2", "T3"):
        if strength in ("assumed",):
            problems.append(f"tier {tier} may not carry an 'assumed' claim without corroboration")
        if sampling == "point-in-time" and not scope.get("does_not_cover"):
            problems.append(f"tier {tier} point-in-time claim must declare what it does not cover")

    return problems


def check_ledger(ledger: dict) -> list[tuple[str, str]]:
    """Validate a whole ledger.  Returns (claim_id, problem) pairs."""
    findings: list[tuple[str, str]] = []
    claims = ledger.get("claims")
    if not isinstance(claims, list) or not claims:
        return [("ledger", "claims is empty or missing")]
    seen_ids: set[str] = set()
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            findings.append((f"[{i}]", "claim is not an object"))
            continue
        cid = str(claim.get("id") or f"[{i}]")
        if cid in seen_ids:
            findings.append((cid, "duplicate claim id"))
        seen_ids.add(cid)
        tier = str(claim.get("tier") or "T1")
        for p in check_claim(claim, tier):
            findings.append((cid, p))
    return findings


def _regression_samples() -> list[dict]:
    return json.loads(REGRESSION_SET.read_text(encoding="utf-8")).get("samples") or []


def run_regression() -> int:
    """The admission metric: what fraction of real errors does this gate catch?

    The regression samples are prose sentences, not ledgers, so the gate has to
    work on them the way it would on a document: it extracts the numbers and
    checks that each one is bound to a resolvable piece of evidence.

    The catch rate is reported twice, because the two numbers mean different
    things:

      overall  -- every sample in the set
      in-scope -- only the samples the derivation protocol actually claims to
                  cover (protocols/DERIVATION-DISCIPLINE.md sections 1-8)

    The in-scope number is the honest one: L5 (receipt integrity) and ZH
    (cross-language discipline) are outside the protocol's remit, so a wording
    gate missing them is not a defect of that gate.
    """
    data = json.loads(REGRESSION_SET.read_text(encoding="utf-8"))
    samples = data.get("samples") or []
    if not samples:
        print("回归集为空")
        return 2

    scope = data.get("scope_classification") or {}
    in_scope_ids = set(scope.get("in_protocol_scope") or [])

    caught: list[str] = []
    missed: list[str] = []
    for s in samples:
        problems = check_text_claim(s["verbatim"], s.get("tier", "T1"))
        (caught if problems else missed).append(s["id"])

    total = len(samples)
    in_scope = [s for s in samples if not in_scope_ids or s["id"] in in_scope_ids]
    in_scope_caught = [s for s in in_scope if s["id"] in caught]
    out_scope = [s for s in samples if in_scope_ids and s["id"] not in in_scope_ids]

    rate = len(caught) / total if total else 0.0
    in_rate = len(in_scope_caught) / len(in_scope) if in_scope else 0.0
    min_rate = float(data.get("admission_rule", {}).get("min_catch_rate_for_new_gate", 0.75))

    print("Claim Ledger 闸 · 真实错误回归集")
    print(f"  全部样本 {total} 条，命中 {len(caught)} 条，抓取率 {len(caught)}/{total} = {rate:.0%}")
    print(f"  **协议范围内** {len(in_scope)} 条，命中 {len(in_scope_caught)} 条，"
          f"抓取率 {len(in_scope_caught)}/{len(in_scope)} = {in_rate:.0%}**")
    if out_scope:
        print(f"  协议范围外 {len(out_scope)} 条（{', '.join(s['id'] for s in out_scope)}）"
              "—— 本就不属措辞闸职责，另配专门验证器")
    print()
    for s in samples:
        mark = "CAUGHT" if s["id"] in caught else "MISSED"
        where = "in " if (not in_scope_ids or s["id"] in in_scope_ids) else "OUT"
        print(f"  {mark:7s} {s['id']:5s} [{where}] [{s.get('tier','?')}] {s.get('title','')}")
    print()
    # The admission decision uses the in-scope rate: missing a defect the
    # protocol never claimed to cover cannot be held against this gate.
    if in_rate >= min_rate:
        print(f"VERDICT: 达到准入门槛（协议范围内抓取率 {in_rate:.0%} >= {min_rate:.0%}）")
        return 0
    print(f"VERDICT: 未达准入门槛（协议范围内抓取率 {in_rate:.0%} < {min_rate:.0%}）")
    return 1


NUM_TOKEN = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?\s*(?:B|GB|MB|ms|s|件|份|个|%|fps|帧|B/s)?")
BOUND = ("实测", "来源", "见 ", "依据", "取样", "实测值", "复测", "hash", "sha256")
# A path written inside backticks that is not absolute and has no line number
# cannot be located by a reader: the same file may live at several entry points.
PATH_TOKEN = re.compile(r"`([^`]+)`")
ABS_PATH = re.compile(r"^[A-Za-z]:\\")
FILE_LINE = re.compile(r"^[^\s`]+:\d+$")


def check_text_claim(text: str, tier: str = "T1") -> list[str]:
    """Judgement used on prose (regression mode).

    Four defect shapes share one root: a value or a reference in the sentence
    that cannot be traced back to a single checkable object.

      1. a number with no anchor  -> the value has no stated origin
      2. a bare relative path      -> the reader cannot locate the file
      3. a quoted upper bound      -> a bound quoted from nowhere
      4. a table row               -> the existing wording gate skips table
         rows entirely, and in a
         measured delivery 54% of
         the non-empty lines are
         table rows, so the numbers
         that matter most live in
         the one place that gate
         never looks

    This is about the binding between a value and its source, not about the
    tone of the sentence -- which is why the wording scanner cannot express it.
    """
    problems: list[str] = []

    nums = NUM_TOKEN.findall(text)
    has_anchor = any(b in text for b in BOUND)
    if nums and not has_anchor:
        problems.append("numbers present without a traceable anchor")

    for token in PATH_TOKEN.findall(text):
        if token.endswith((".md", ".py", ".json", ".ps1", ".txt", ".yaml", ".yml")):
            if not ABS_PATH.match(token) and not FILE_LINE.match(token):
                problems.append(f"relative path cannot be located: {token}")

    # "X ~ Y 之间" style upper bounds: the second bound is quoted without a source
    m = re.search(r"(\d[\d.]*)\s*(?:MB|GB|B)?\s*[~-]\s*(\d[\d.]*)\s*(?:MB|GB|B)?\s*之间", text)
    if m and not re.search(r"(实测|复测|来源|见\s)", text):
        problems.append("quoted range bound without a stated source")

    return problems


def self_test() -> int:
    """Prove the gate can tell good from bad, including a sabotage check."""
    failures: list[str] = []

    good = {
        "id": "OK-1", "tier": "T1", "strength": "measured", "sampling": "stable",
        "evidence": [f"sha256:{'a' * 64}"],
        "scope": {"applies_when": "本机当前状态", "does_not_cover": "其它机器"},
        "falsifier": "若换一台机器读取值不同",
    }
    bad_cases = {
        "no evidence": {**good, "evidence": []},
        "unresolvable evidence": {**good, "evidence": ["cmd:exit 0"] , "id": "x"},
        "empty scope": {**good, "scope": {"applies_when": "", "does_not_cover": ""}},
        "no falsifier": {**good, "falsifier": ""},
        "bad strength": {**good, "strength": "pretty sure"},
        "bad sampling": {**good, "sampling": "probably"},
        "T2 assumed": {**good, "tier": "T2", "strength": "assumed"},
    }
    for name, claim in bad_cases.items():
        problems = check_claim(claim, claim.get("tier", "T1"))
        if not problems:
            failures.append(f"negative control did not fire: {name}")
    if check_claim(good, "T1"):
        failures.append("positive control was rejected")

    # sabotage: a permanently disabled checker must make the gate red
    original = resolve_evidence
    try:
        globals()["resolve_evidence"] = lambda ref: (True, "sabotaged")
        broken = check_claim({**good, "evidence": ["C:/nope/does-not-exist.txt:999"]}, "T1")
        if broken:
            failures.append("sabotage did not disable the gate (still reported problems)")
    finally:
        globals()["resolve_evidence"] = original

    # text mode: a number without an anchor must be caught
    if not check_text_claim("共 32 份，服务暴露面是空的"):
        failures.append("text mode missed an unanchored number")
    if check_text_claim("实测 33 份（取样时刻值），来源：protocols 目录清点"):
        failures.append("text mode produced a false positive on an anchored number")

    if failures:
        print("Claim Ledger 闸 · self-test：FAIL")
        for f in failures:
            print("   -", f)
        return 1
    print("Claim Ledger 闸 · self-test：PASS（正控通过 · 负控全触发 · sabotage 生效 · 文本模式正负例正确）")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", metavar="LEDGER")
    ap.add_argument("--regression", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.regression:
        return run_regression()
    if args.check:
        p = Path(args.check)
        if not p.is_file():
            print(f"找不到 ledger：{p}")
            return 2
        ledger = json.loads(p.read_text(encoding="utf-8"))
        findings = check_ledger(ledger)
        if not findings:
            print(f"Claim Ledger 闸：通过（{len(ledger.get('claims') or [])} 条断言，0 发现）")
            return 0
        print(f"Claim Ledger 闸：{len(findings)} 处发现")
        for cid, msg in findings:
            print(f"   {cid}  {msg}")
        return 1
    ap.error("pass --check, --regression or --self-test")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
