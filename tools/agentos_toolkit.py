"""Unified offline-first AgentOS asset, learning, deployment and publication CLI."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capability_assets as assets
import distribution
import portable_install
import weekly_learning as weekly

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "doctor", "assets", "learning", "scan", "stage", "validate", "prepare", "publish", "install", "rollback", "manifest"])
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--source", type=Path, default=ROOT)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--scan", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            if not args.policy:
                raise ValueError("--policy is an explicit, reviewed local configuration")
            policy = weekly.load(args.policy)
            distribution.target(policy)
            for key in ("project_roots", "skill_roots", "authored_roots", "learning_sources"):
                if not isinstance(policy.get(key), list):
                    raise ValueError("Missing bounded source list: " + key)
            weekly.create(ROOT / ".local/policy.json", policy)
            result = {"state": "initialized", "effect": "Private policy only; no scheduling, client, network or environment changes."}
        elif args.command == "doctor":
            result = {"python": sys.version.split()[0], "stdlib_core": True,
                "policy": "configured" if (ROOT / ".local/policy.json").is_file() else "not_initialized",
                "bundle": "manifest_present" if (ROOT / "portable-manifest.json").is_file() else "source_workspace",
                "boundaries": "No network/dependency install/system mutation performed. Optional visual dependencies are not probed or installed."}
            if (ROOT / "portable-manifest.json").exists():
                result["validation"] = portable_install.validate_bundle(ROOT)
        elif args.command == "assets":
            package = args.package or ROOT
            result = assets.validate_assets(package / "capability-assets.json", package / "governance/AgentOS/policies/SKILL-REGISTRY.json", package)
        elif args.command == "learning":
            result = assets.scan_learning(weekly.load(ROOT / ".local/policy.json"), ROOT)
        elif args.command == "install":
            if not args.target:
                raise ValueError("--target required")
            result = portable_install.install(args.source, args.target, args.dry_run)
        elif args.command == "rollback":
            if not args.target:
                raise ValueError("--target required")
            result = portable_install.rollback(args.target, args.dry_run)
        elif args.command == "manifest":
            result = portable_install.build_manifest(args.source)
            weekly.create(args.source / "portable-manifest.json", result)
        else:
            arguments = [args.command]
            for key in ("scan", "package", "review", "ready"):
                if getattr(args, key) is not None:
                    arguments.extend(["--" + key, str(getattr(args, key))])
            return weekly.main(arguments)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
