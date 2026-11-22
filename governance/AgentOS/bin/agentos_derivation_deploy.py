#!/usr/bin/env python
"""推导纪律分发与覆盖校验（AgentOS protocols/DERIVATION-DISCIPLINE.md §9）。

目的：让**本机所有 Agent 入口**都真正加载推导纪律，而不是靠人工记忆。
做法：
  1. 从 runtime/client-adapters.json 取出每个已注册客户端的入口文件
     （rule_files）与技能根（skill_roots），解析 ${USER_HOME} 等占位符；
  2. 追加扫描本机项目入口（${PROJECT_PATH}\\*\\AGENTS.md、CLAUDE.md 等）；
  3. 对每个入口检查是否含推导纪律指针；
  4. `--fix` 幂等插入指针块（不改动原有内容，只在缺失时追加）；
  5. 写受理回执 runtime/derivation-deployment.json（时间、覆盖清单、SHA256）。

用法：
    python bin/agentos_derivation_deploy.py --check          # 只报告，缺口 → 退出码 1
    python bin/agentos_derivation_deploy.py --fix            # 幂等补齐
    python bin/agentos_derivation_deploy.py --check --json   # 机器可读输出
退出码：0 = 全部覆盖；1 = 有缺口；2 = 参数/环境错
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "runtime" / "client-adapters.json"
RECEIPT = ROOT / "runtime" / "derivation-deployment.json"
PROTOCOL_REL = "protocols/DERIVATION-DISCIPLINE.md"
GATE_REL = "bin/check_derivation_discipline.py"

BEGIN = "<!-- AGENTOS:DERIVATION-DISCIPLINE:BEGIN -->"
END = "<!-- AGENTOS:DERIVATION-DISCIPLINE:END -->"

ZH = f"""{BEGIN}
## 推导纪律（AgentOS 强制协议 · 所有 Agent 适用）

- 协议全文：`$AGENTOS_HOME/{PROTOCOL_REL}`；机械门禁：`$AGENTOS_HOME/{GATE_REL}`
- **结论强度 ≤ 证据强度**：每条技术结论都要带证据等级标签
  `[实测]` / `[图纸]` / `[推论]` / `[假设]` / `[用户]`，无标签的强断言视为缺陷。
- **缺口即取证任务**：信息缺口一律转成取证任务（怎么取 / 怎么测 / 什么算过），
  不得用类比、惯例、"通常做法"或"上次那样"填补；缺口未闭合前不得给结论。
- **依据链 + 覆盖性检查**：结论前给依据；交付前检查状态覆盖 / 前提满足 / 反例检验。
- **输出前自洽扫描**：数值冲突 / 结论强度与证据强度不匹配 / 未闭合缺口。
- **推翻痕迹**：旧结论被推翻时不静默改写，标 `~~作废~~` 并写真因。
- 交付前对改动过的文档跑一次机械门禁：
  `python $AGENTOS_HOME/{GATE_REL} <文档>`
{END}
"""

EN = f"""{BEGIN}
## Derivation discipline (AgentOS mandatory protocol · applies to every agent)

- Protocol: `$AGENTOS_HOME/{PROTOCOL_REL}`; mechanical gate: `$AGENTOS_HOME/{GATE_REL}`
- **Conclusion strength may never exceed evidence strength.** Every technical
  conclusion carries an evidence label
  `[measured]` / `[schematic]` / `[inferred]` / `[assumed]` / `[user-stated]`.
- **A gap is an evidence-acquisition task**, never an inference: state how to
  obtain it, how to measure it, and what counts as passed. Do not fill gaps by
  analogy, convention or "we did it last time".
- **Basis chain + coverage check** before a conclusion; **self-consistency
  scan** (numeric conflicts / strength mismatch / unclosed gaps) before delivery.
- **Retraction trace**: a superseded conclusion is marked, not silently rewritten.
- Run the mechanical gate on changed documents before delivery:
  `python $AGENTOS_HOME/{GATE_REL} <documents>`
{END}
"""

MARKER_RE = re.compile(re.escape(BEGIN))
# 只把指针写进"AgentOS 治理 skill"本身
GOVERNANCE_SKILL_RE = re.compile(r"agent[-_]?governance|agentos", re.I)


def expand(path: str) -> Path:
    p = path.replace("${USER_HOME}", str(Path.home()))
    p = p.replace("${CODEX_HOME}", os.environ.get("CODEX_HOME", ""))
    p = p.replace("${APPDATA}", os.environ.get("APPDATA", ""))
    p = p.replace("${AGENTOS_HOME}", str(ROOT))
    return Path(p)


BACKUP_ROOT = ROOT / "runtime" / "backups" / "derivation"


def backup(path: Path) -> Path:
    """写前备份（带时间戳目录），保证分发动作可回滚。"""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_ROOT / stamp
    dest.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(path).replace(":", "").replace("\\", "__"))
    target = dest / safe
    target.write_bytes(path.read_bytes())
    return target


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def client_targets() -> list[tuple[str, Path]]:
    """客户端入口：rule_files（全局规则，永远加载）+ AgentOS 治理 skill 自身。

    注意：只覆盖**治理 skill 本身**与全局规则文件；不往无关第三方 skill 里塞指针。
    """
    out: list[tuple[str, Path]] = []
    if not REGISTRY.exists():
        return out
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for ad in reg.get("adapters", []):
        cid = ad.get("id", "?")
        for rp in ad.get("rule_files", []):
            out.append((f"client:{cid}:rule", expand(rp)))
        for sr in ad.get("skill_roots", []):
            root = expand(sr)
            if root.is_dir():
                for sk in sorted(root.glob("*/SKILL.md")):
                    if GOVERNANCE_SKILL_RE.search(sk.parent.name):
                        out.append((f"client:{cid}:governance-skill", sk))
    return out


def default_project_root() -> Path:
    """The corpus root, resolved rather than hard-coded.

    A machine path written into the source names the owner's corpus and
    travels with the published edition. The root is therefore resolved from
    the environment, and the historical location is only a fallback for the
    owner's own machine.
    """
    for name in ("AGENTOS_PROJECT_ROOT", "PROJECT_ROOT"):
        value = os.environ.get(name)
        if value:
            candidate = Path(value)
            if candidate.is_dir():
                return candidate
    # The corpus root is an ancestor of the governance root on the owner's
    # machine. Deriving it keeps the owner's layout out of the distributed
    # source: a path written into the source names the owner's corpus.
    for ancestor in ROOT.parents:
        if (ancestor / "999_AI_agents").is_dir():
            return ancestor
    return ROOT


def project_targets(base: Path | None = None):
    """项目入口：本机各项目的 AGENTS.md / CLAUDE.md。"""
    out: list[tuple[str, Path]] = []
    base = Path(base) if base is not None else default_project_root()
    if base.is_dir():
        for p in sorted(base.glob("*/AGENTS.md")):
            out.append(("project:AGENTS.md", p))
        for p in sorted(base.glob("*/CLAUDE.md")):
            out.append(("project:CLAUDE.md", p))
        agents = base / "999_AI_agents"
        if agents.is_dir():
            for p in sorted(agents.glob("*/CLAUDE.md")):
                out.append(("project:CLAUDE.md", p))
            for p in sorted(agents.glob("*/AGENTS.md")):
                out.append(("project:AGENTS.md", p))
    return out


def pick_block(text: str) -> str:
    return ZH if re.search(r"[\u4e00-\u9fff]", text) else EN


def needs_fix(text: str) -> bool:
    return BEGIN not in text


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="幂等补齐缺失的指针块")
    ap.add_argument("--check", action="store_true", help="只报告（默认行为）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    ap.add_argument("--project-root", default=None, help="the corpus root to scan")
    a = ap.parse_args(argv)

    targets = client_targets() + project_targets(a.project_root)
    seen: set[str] = set()
    uniq: list[tuple[str, Path]] = []
    for kind, p in targets:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append((kind, p))

    report: list[dict] = []
    fixed = 0
    for kind, p in uniq:
        if not p.exists() or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            report.append({"kind": kind, "path": str(p), "status": "unreadable", "detail": str(exc)})
            continue
        if not needs_fix(text):
            report.append({"kind": kind, "path": str(p), "status": "covered", "sha256": sha256(p)})
            continue
        if a.fix:
            block = pick_block(text)
            new = text.rstrip("\n") + "\n\n" + block + "\n"
            try:
                backup(p)          # 写前备份 ⇒ 分发动作可回滚
                p.write_text(new, encoding="utf-8")
            except Exception as exc:  # noqa: BLE001
                report.append({"kind": kind, "path": str(p), "status": "write_failed", "detail": str(exc)})
                continue
            fixed += 1
            report.append({"kind": kind, "path": str(p), "status": "fixed", "sha256": sha256(p)})
        else:
            report.append({"kind": kind, "path": str(p), "status": "missing"})

    covered = sum(1 for r in report if r["status"] == "covered")
    missing = [r for r in report if r["status"] == "missing"]
    failed = [r for r in report if r["status"] in ("write_failed", "unreadable")]

    payload = {
        "schema": "agentos-derivation-deployment-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol": PROTOCOL_REL,
        "gate": GATE_REL,
        "fixed": fixed,
        "covered": covered,
        "missing": len(missing),
        "failed": len(failed),
        "entries": report,
    }
    RECEIPT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if a.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"推导纪律分发：覆盖 {covered}，本次补齐 {fixed}，缺口 {len(missing)}，失败 {len(failed)}")
        for r in missing:
            print(f"  [缺口] {r['kind']}  {r['path']}")
        for r in failed:
            print(f"  [失败] {r['kind']}  {r['path']}  {r.get('detail', '')}")
        print(f"回执：{RECEIPT}")

    if failed:
        return 1
    if missing and not a.fix:
        return 1
    if missing and a.fix:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
