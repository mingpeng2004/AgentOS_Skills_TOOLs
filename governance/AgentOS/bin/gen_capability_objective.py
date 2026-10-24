"""Generate the machine-checkable capability objective manifest from the registry.

The release verifier extracts capability IDs from the generated file and requires
the set to equal the registry set exactly, so the file must be regenerated
whenever the registry changes. Capability IDs are emitted one per line at
column 0 because the verifier's regex anchors on the start of the line.

Usage:  python bin/gen_capability_objective.py [--check]
        --check regenerates in memory and fails if the file on disk is stale.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "policies/SKILL-REGISTRY.json"
OBJECTIVE = ROOT / "protocols/CAPABILITY-OBJECTIVE.md"

DOMAIN_NAME = {
    "A": "requirements", "B": "architecture", "C": "planning", "D": "design",
    "E": "mechanical", "F": "embedded", "G": "software", "H": "quality",
}
ID_LINE = re.compile(r"(?m)^((?:req|arch|plan|hw|mech|id|emb|sw|ui|qa|mfg|km|meta|vis)-[a-z0-9-]+)\s")


def render(data):
    caps = data["capabilities"]
    providers = {p["id"]: p["skill"] for p in data["providers"]}
    groups = {}
    for cap in caps:
        groups.setdefault(cap["domain"], []).append(cap)

    lines = [
        "# AgentOS 能力目标清单（CAPABILITY-OBJECTIVE）",
        "",
        f"> 版本：AgentOS {data['agentos_version']} · 注册表 {data['version']} · 能力总数 {len(caps)}",
        ">",
        "> 本文件由 `policies/SKILL-REGISTRY.json` 生成（生成器：`bin/gen_capability_objective.py`），",
        "> 是**能力集合的机读基准**。`tests/verify_matrix_release.py` 会抽取本文件中每行开头的",
        "> 能力 ID，要求其集合与注册表**完全相等**（不缺、不多、不改名）。",
        "> 改能力请改注册表后运行 `python bin/gen_capability_objective.py` 重新生成，不要手改 ID 行。",
        ">",
        "> 每行格式：`能力ID  域/域组 · 供给状态 · 提供者/技能 · 触发词 · 验收项数`。",
        ">",
        "> 供给状态：`protocol` = 已部署且带可运行实现；`mapped` = 已映射到既有方法；",
        "> `candidate` = 仅登记候选，尚无已验证部署，路由时直接阻断。",
        "> 提供者：`core` / `engineering` / `visual`，括号内为实际 skill 目录。",
        "",
    ]
    for domain in sorted(groups):
        lines.append(f"## 域 {domain} · {DOMAIN_NAME.get(domain, domain)}")
        lines.append("")
        for cap in groups[domain]:
            triggers = "、".join(cap["triggers"][:4])
            provider = cap["provider"]
            provider_text = "—（未部署）" if provider is None else f"{provider}/{providers.get(provider, provider)}"
            lines.append(f"{cap['id']}  {domain}/{cap['group']} · {cap['availability']} · "
                         f"{provider_text} · {triggers} · {len(cap['acceptance'])} 项验收")
        lines.append("")

    counts = {}
    for cap in caps:
        counts[cap["availability"]] = counts.get(cap["availability"], 0) + 1
    lines.append("## 汇总")
    lines.append("")
    for key in sorted(counts):
        lines.append(f"- {key}: {counts[key]} 项")
    lines.append(f"- 合计: {len(caps)} 项")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail when the file on disk differs from the generated content")
    args = parser.parse_args()

    data = json.loads(REGISTRY.read_text(encoding="utf-8-sig"))
    text = render(data)
    if args.check:
        current = OBJECTIVE.read_text(encoding="utf-8-sig") if OBJECTIVE.is_file() else ""
        if current != text:
            print("STALE: protocols/CAPABILITY-OBJECTIVE.md differs from the registry; "
                  "run python bin/gen_capability_objective.py")
            return 1
        ids = set(ID_LINE.findall(current))
        actual = {c["id"] for c in data["capabilities"]}
        if ids != actual:
            print("MISMATCH: objective IDs differ from registry IDs")
            return 1
        print(f"OK: objective matches registry ({len(actual)} capabilities)")
        return 0

    OBJECTIVE.write_text(text, encoding="utf-8", newline="\n")
    print(f"written {OBJECTIVE} ({len(data['capabilities'])} capabilities)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
