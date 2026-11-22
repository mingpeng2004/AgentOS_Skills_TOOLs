"""Report drift between the skills that exist on this host and the capability matrix.

The registry is only useful while it matches reality. This checker answers three
questions that a registry read cannot:

  1. Which installed Skills have no provider entry at all?  (unregistered)
  2. Which registered providers no longer resolve to a real SKILL.md?  (dangling)
  3. Which registered capabilities still resolve for a real client?  (routable)

It reads only; it never writes the registry and never promotes anything.

Usage:
  python -B bin/agentos_matrix_check.py [--client minimax-code] [--project <dir>]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "policies/SKILL-REGISTRY.json"


def load_runtime():
    spec = importlib.util.spec_from_file_location("_agentos_skills", ROOT / "bin/agentos_skills.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", default="minimax-code")
    parser.add_argument("--project", default=r"${PROJECT_PATH}\999_MINIMAX_100_SYS_Maintain")
    args = parser.parse_args(argv)

    runtime = load_runtime()
    data, caps, providers = runtime.registry(REGISTRY)
    bindings = runtime.paths.client_paths(args.client, ROOT)

    # Every directory that can hold a discoverable Skill for this client. A root may
    # be reached twice (a canonical path and a junction that points at it); keep the
    # set unique so one Skill is not counted twice.
    roots = []
    seen_roots = set()
    for base in list(bindings["skill_roots"]) + list(bindings["shared_skill_roots"]):
        root = runtime.paths.trusted_root(Path(base))
        key = str(root).casefold()
        if root.is_dir() and key not in seen_roots:
            seen_roots.add(key)
            roots.append(root)

    # Key by the Skill's own name, not by its resolved path: the canonical copy and
    # every symlink farm entry that points at it are one Skill, and keying by path
    # would let one entry overwrite another and hide the rest.
    # A real directory is preferred over a link entry, so the reported path is the
    # canonical home rather than whichever farm happened to be walked first.
    installed = {}
    for root in roots:
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not (child / "SKILL.md").is_file():
                continue
            name = child.name
            is_link = runtime.paths.is_link(child)
            existing = installed.get(name)
            if existing is not None:
                if existing["link"] and not is_link:
                    installed[name] = {"path": str(child), "link": False}
                continue
            installed[name] = {"path": str(child), "link": is_link}

    registered_skills = {p["skill"] for p in providers.values()}

    unregistered = []
    for name, entry in sorted(installed.items()):
        if name in registered_skills:
            continue
        unregistered.append({"skill": name, "path": entry["path"],
                              "canonical": not entry["link"]})

    dangling = []
    for provider in providers.values():
        found = False
        for root in roots:
            if (root / provider["skill"] / "SKILL.md").is_file():
                found = True
                break
        if not found and provider["bundled"]:
            if (ROOT / provider["bundled"] / "SKILL.md").is_file():
                found = True
        if not found:
            dangling.append({"provider": provider["id"], "skill": provider["skill"]})

    routable = {"available": [], "blocked": [], "candidate": []}
    for cap in caps.values():
        if cap["availability"] == "candidate":
            routable["candidate"].append(cap["id"])
            continue
        try:
            runtime.resolve_provider(providers[cap["provider"]], args.project, args.client)
            routable["available"].append(cap["id"])
        except Exception as exc:
            routable["blocked"].append({"id": cap["id"], "reason": str(exc)[:160]})

    result = {
        "schema": "agentos-matrix-check-v1",
        "client": args.client,
        "registry": {
            "capabilities": len(caps),
            "providers": len(providers),
            "availability": {
                key: sum(1 for c in caps.values() if c["availability"] == key)
                for key in ("mapped", "protocol", "candidate")
            },
        },
        "unregistered_skills": unregistered,
        "dangling_providers": dangling,
        "routing": {
            "available": len(routable["available"]),
            "blocked": routable["blocked"],
            "candidate": len(routable["candidate"]),
        },
        "state": "drift" if (unregistered or dangling or routable["blocked"]) else "consistent",
        "limits": ["File and registry inspection only; it does not prove a Skill's behaviour, "
                   "a client's runtime import, or that a capability deserves its availability level.",
                   "Unregistered Skills are reported, never promoted automatically."],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
