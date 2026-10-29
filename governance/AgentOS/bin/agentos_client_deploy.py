"""Append/update only registered managed entry blocks, with backup and CAS guards.

No client is started, no network is used, and no model/config/credential file is
read. Host bindings are private machine-local paths, not portable governance.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable
import uuid

from agentos_paths import client_paths


BEGIN = "<!-- AGENTOS:BEGIN client-entry-v1 -->"
END = "<!-- AGENTOS:END client-entry-v1 -->"


class Blocked(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_optional(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def block_for(root: Path) -> tuple[bytes, str]:
    source = root / "runtime/managed-client-entry.md"
    if source.is_symlink() or not source.is_file():
        raise Blocked("canonical managed entry missing or symlinked")
    data = source.read_bytes()
    text = data.decode("utf-8-sig").replace("{agentos_root}", str(root.resolve()))
    return (BEGIN + "\n" + text.rstrip() + "\n" + END + "\n").encode("utf-8"), sha(data)


def merged(existing: bytes | None, block: bytes, prefix: str = "") -> bytes:
    if existing is None:
        return prefix.encode("utf-8") + block
    text = existing.decode("utf-8-sig")
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise Blocked("malformed or duplicate managed block")
    if BEGIN in text:
        start = text.index(BEGIN)
        finish = text.index(END, start) + len(END)
        if finish < len(text) and text[finish] == "\r":
            finish += 1
        if finish < len(text) and text[finish] == "\n":
            finish += 1
        # Preserve every byte outside the managed region, including a UTF-8 BOM.
        lead = b"\xef\xbb\xbf" if existing.startswith(b"\xef\xbb\xbf") else b""
        return lead + text[:start].encode("utf-8") + block + text[finish:].encode("utf-8")
    separator = b"" if not existing or existing.endswith(b"\n\n") else (b"\n" if existing.endswith(b"\n") else b"\n\n")
    return existing + separator + block


def deploy_file(target: Path, root: Path, backup_root: Path,
                expected_sha256: str | None = None, prefix: str = "",
                dry_run: bool = False,
                before_commit: Callable[[], None] | None = None) -> dict:
    target = Path(target)
    root = Path(root)
    backup_root = Path(backup_root)
    if not target.is_absolute() or not root.is_absolute() or not backup_root.is_absolute():
        raise Blocked("all deployment paths must be absolute")
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise Blocked("target is not a regular file")
    # Targets are concrete bindings, not portable templates: every existing
    # ancestor must be an ordinary directory. Even a declared-looking junction
    # can be swapped after preflight and redirect an atomic replace elsewhere.
    for ancestor in reversed([target.parent, *target.parent.parents]):
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        if ancestor.is_symlink() or getattr(info, "st_file_attributes", 0) & 1024:
            raise Blocked("target ancestor link/reparse rejected: " + str(ancestor))
    parent_identity = target.parent.resolve()
    old = read_optional(target)
    old_hash = sha(old) if old is not None else None
    if expected_sha256 and old_hash != expected_sha256:
        raise Blocked("target differs from registered expected SHA256")
    block, source_hash = block_for(root)
    if old is not None and BEGIN.encode() in old and not expected_sha256:
        raise Blocked("managed update requires a registered expected SHA256")
    new = merged(old, block, prefix)
    result = {"path": str(target), "before_sha256": old_hash,
              "sha256": sha(new), "managed_block_sha256": sha(block),
              "source_sha256": source_hash, "created": old is None,
              "backup_path": None, "backup_sha256": None,
              "state": "unchanged" if old == new else "dry_run" if dry_run else "written"}
    if dry_run or old == new:
        return result
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_root.mkdir(parents=True, exist_ok=True)
    lock = backup_root / (sha(str(target.resolve()).encode()) + ".lock")
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise Blocked("another deployment holds this target lock") from exc
    temporary = None
    try:
        os.close(lock_fd)
        if old is not None:
            backup = backup_root / (uuid.uuid4().hex + ".bak")
            with backup.open("xb") as stream:
                stream.write(old)
            result.update(backup_path=str(backup), backup_sha256=sha(backup.read_bytes()))
        fd, name = tempfile.mkstemp(prefix=".agentos-entry-", dir=target.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(new)
            stream.flush()
            os.fsync(stream.fileno())
        if before_commit:
            before_commit()
        if target.parent.resolve() != parent_identity or read_optional(target) != old:
            raise Blocked("concurrent target/path change; backup retained")
        if block_for(root)[1] != source_hash:
            raise Blocked("canonical entry changed during deployment")
        os.replace(temporary, target)
        temporary = None
        if sha(target.read_bytes()) != result["sha256"]:
            raise Blocked("post-write target hash differs")
        return result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def rollback_file(receipt: dict) -> dict:
    target = Path(receipt["path"])
    if target.is_symlink() or sha(target.read_bytes()) != receipt["sha256"]:
        raise Blocked("rollback refuses changed target")
    if receipt["created"]:
        target.unlink()
    else:
        backup = Path(receipt["backup_path"])
        original = backup.read_bytes()
        if sha(original) != receipt["backup_sha256"]:
            raise Blocked("rollback backup hash mismatch")
        if sha(target.read_bytes()) != receipt["sha256"]:
            raise Blocked("rollback refuses concurrent target edit")
        target.write_bytes(original)
    return {"state": "rolled_back", "path": str(target)}


def deploy_bindings(root: Path, bindings_path: Path, backup_root: Path,
                    client: str | None = None, dry_run: bool = False) -> dict:
    binding_bytes = bindings_path.read_bytes()
    data = json.loads(binding_bytes.decode("utf-8-sig"))
    if data.get("schema") != "agentos-host-bindings-v1":
        raise Blocked("unsupported host bindings schema")
    if client and client not in data.get("clients", {}):
        raise Blocked("unknown client; register before deployment")
    results = []
    for ident, record in data.get("clients", {}).items():
        if client and ident != client:
            continue
        expected = {x["path"]: x for x in record.get("adapter_files", [])}
        files = []
        resolved = client_paths(ident, root)
        permitted = {os.path.normcase(str(Path(name).resolve())) for name in resolved["rule_files"]}
        portable_prefixes = resolved.get("rule_file_prefixes", {})
        for name in record.get("rule_files", []):
            path = Path(name)
            if not path.is_absolute() or os.path.normcase(str(path.resolve())) not in permitted:
                raise Blocked("deployment target is not declared by the portable adapter: " + str(path))
            if path.suffix.lower() not in {".md", ".mdc", ".txt"} and path.suffix:
                raise Blocked("only registered plain-text or Markdown rule/Skill targets are permitted")
            prefix = portable_prefixes.get(str(path.resolve()), "")
            previous = expected.get(name, {})
            if path.exists() and not previous.get("sha256"):
                raise Blocked("existing target needs a reviewed SHA256 before deployment: " + str(path))
            if previous.get("new_file_prefix") not in (None, prefix):
                raise Blocked("host prefix differs from canonical adapter format: " + str(path))
            item = deploy_file(path, root, backup_root, previous.get("sha256"), prefix, dry_run)
            item["new_file_prefix"] = prefix or None
            if item["state"] == "unchanged":
                for field in ("created", "backup_path", "backup_sha256"):
                    if field in previous:
                        item[field] = previous[field]
            files.append(item)
        if not dry_run:
            record["adapter_files"] = files
            record["states"] = {"file_parity": "verified" if files else "unknown",
                                "import_reported": "unattested", "behavior_attested": "unattested"}
        results.append({"id": ident, "adapter_files": files,
                        "limits": record.get("limits", [])})
    if not dry_run:
        if bindings_path.read_bytes() != binding_bytes:
            raise Blocked("bindings changed concurrently; targets recorded only in caller result")
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        fd, name = tempfile.mkstemp(prefix=".host-bindings-", dir=bindings_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            if bindings_path.read_bytes() != binding_bytes:
                raise Blocked("bindings changed concurrently")
            os.replace(name, bindings_path)
        finally:
            Path(name).unlink(missing_ok=True)
    return {"schema": "agentos-client-deployment-v1", "dry_run": dry_run,
            "clients": results, "limits": "File parity only; no client start/import/behavior claim."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--client")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.output and args.output.exists():
            raise Blocked("output receipt already exists; choose a new path")
        result = deploy_bindings(args.root, args.bindings, args.backup_root, args.client, args.dry_run)
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (Blocked, ValueError, OSError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
