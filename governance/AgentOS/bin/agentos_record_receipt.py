"""Add or refresh the shared_source_verification receipt for one skill.

The receipt binds a shared skill's canonical tree to a file-by-file SHA-256 list.
Without it, resolve_provider refuses the skill once its shared-receipt check is live.

Usage:
  python -B bin/agentos_record_receipt.py --skill auditable-trip-handbook \\
      --canonical-root "D:\\...\\magpie-library\\skills\\auditable-trip-handbook"
  python -B bin/agentos_record_receipt.py --list
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
BINDINGS = ROOT / ".local/host-bindings.json"


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_hashes(root):
    """Hash every file under root, rejecting links: a receipt must pin real bytes."""
    hashes = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise SystemExit("link inside skill tree refused: " + str(path))
        if path.is_file():
            hashes[path.relative_to(root).as_posix()] = sha256_file(path)
    return hashes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill")
    parser.add_argument("--canonical-root")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)

    bindings = json.loads(BINDINGS.read_text(encoding="utf-8-sig"))
    records = bindings.get("shared_source_verification", [])

    if args.list:
        for record in records:
            print(record["skill"], "->", record["canonical_root"],
                  "(" + str(len(record.get("file_sha256", {}))) + " files)")
        return 0

    if not args.skill or not args.canonical_root:
        raise SystemExit("--skill and --canonical-root are required")

    root = Path(args.canonical_root)
    if not (root / "SKILL.md").is_file():
        raise SystemExit("canonical root has no SKILL.md: " + str(root))

    # The canonical root must sit inside a configured shared root, otherwise the
    # receipt would bind a tree the router never consults.
    shared_roots = [Path(x).resolve() for x in bindings.get("shared_skill_roots", [])]
    if not any(str(root.resolve().parent) == str(x) for x in shared_roots):
        raise SystemExit("canonical root is not directly inside a configured shared root")

    hashes = tree_hashes(root)
    record = {"skill": args.skill, "canonical_root": str(root), "file_sha256": hashes}

    existing = next((i for i, r in enumerate(records) if r["skill"] == args.skill), None)
    if existing is None:
        records.append(record)
        action = "added"
    else:
        records[existing] = record
        action = "refreshed"

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = BINDINGS.with_name(BINDINGS.name + ".bak." + stamp)
    shutil.copy2(BINDINGS, backup)

    bindings["shared_source_verification"] = records
    BINDINGS.write_text(json.dumps(bindings, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    print(json.dumps({"status": action, "skill": args.skill,
                      "canonical_root": str(root), "files": len(hashes),
                      "backup": str(backup)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
