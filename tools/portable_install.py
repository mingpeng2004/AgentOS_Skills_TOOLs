"""Transparent, offline bundle installation with verified backups and rollback."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import uuid

MANIFEST_NAME = "portable-manifest.json"
STATE_DIR = ".agentos-install"
SCHEMA = "agentos-portable-bundle-v1"
RECEIPT_SCHEMA = "agentos-portable-install-v1"
_UNCHECKED = object()


class Blocked(RuntimeError):
    """The requested operation failed a precondition; no permission is inferred."""


def _encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise Blocked("An explicit absolute path is required")
    return Path(os.path.abspath(str(path)))


def _check_path(path):
    """Check every existing ancestor without following a symlink or junction."""
    path = _absolute(path)
    for item in reversed([path, *path.parents]):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise Blocked("Linked/reparse path refused: " + str(item))
    return path


def _relative(value):
    if not isinstance(value, str) or not value:
        raise Blocked("Invalid manifest path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or "\\" in value or ":" in value:
        raise Blocked("Unsafe manifest path: " + value)
    for part in path.parts:
        if (part in {".", ".."} or part.casefold() == STATE_DIR.casefold() or part.endswith((".", " "))
                or any(ord(char) < 32 or char in '<>"|?*' for char in part)):
            raise Blocked("Unsafe/reserved manifest path: " + value)
        if re.match(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", part):
            raise Blocked("Nonportable device path: " + value)
    return value


def _walk(root, skip_state=False):
    root = _check_path(root)
    if not root.is_dir():
        raise Blocked("Bundle/target directory is absent")
    result = {}
    folded = set()
    def onerror(exc):
        raise Blocked("Directory unreadable: " + str(exc)) from exc
    for base, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
        for name in list(dirs):
            path = _check_path(Path(base) / name)
            if skip_state and name == STATE_DIR and Path(base) == root:
                dirs.remove(name)
            elif name.casefold() == STATE_DIR.casefold():
                raise Blocked("Source contains reserved installation state")
        for name in sorted(files):
            path = _check_path(Path(base) / name)
            if not stat.S_ISREG(path.lstat().st_mode):
                raise Blocked("Only regular files may be installed")
            relative = _relative(path.relative_to(root).as_posix())
            if relative.casefold() in folded:
                raise Blocked("Case-insensitive path collision")
            folded.add(relative.casefold())
            result[relative] = path
    return result


def _file_record(path):
    data = _check_path(path).read_bytes()
    return {"sha256": _hash(data), "bytes": len(data)}


def _records(paths):
    return {name: _file_record(path) for name, path in sorted(paths.items())}


def _validate_records(records):
    if not isinstance(records, dict):
        raise Blocked("Invalid file manifest")
    folded = set()
    components = {}
    file_names = {name.casefold() for name in records if isinstance(name, str)}
    for name, value in records.items():
        _relative(name)
        if name.casefold() in folded:
            raise Blocked("Case-insensitive manifest collision")
        folded.add(name.casefold())
        parts = PurePosixPath(name).parts
        for index in range(1, len(parts) + 1):
            component = "/".join(parts[:index])
            key = component.casefold()
            if key in components and components[key] != component:
                raise Blocked("Case-insensitive directory collision")
            components[key] = component
        if any("/".join(parts[:index]).casefold() in file_names for index in range(1, len(parts))):
            raise Blocked("File/directory manifest collision")
        if (not isinstance(value, dict) or set(value) != {"sha256", "bytes"}
                or not re.fullmatch(r"[0-9a-f]{64}", str(value["sha256"]))
                or type(value["bytes"]) is not int or value["bytes"] < 0):
            raise Blocked("Invalid manifest hash/size")


def build_manifest(package, exclusions=()):
    """Return a complete manifest; exclusions are exact files, never patterns."""
    paths = _walk(package)
    exclusions = sorted(set(_relative(name) for name in exclusions))
    if MANIFEST_NAME in exclusions:
        raise Blocked("The manifest is already implicitly excluded")
    if any(name not in paths for name in exclusions):
        raise Blocked("An exclusion does not identify an existing file")
    files = {name: path for name, path in paths.items()
             if name != MANIFEST_NAME and name not in exclusions}
    if not files:
        raise Blocked("Empty bundle refused")
    records = _records(files)
    _validate_records(records)
    return {"schema": SCHEMA, "files": records, "exclusions": exclusions}


def _load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(_check_path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique)
    except (OSError, UnicodeError, ValueError) as exc:
        raise Blocked("Invalid/missing JSON: " + str(path)) from exc


def validate_bundle(source):
    source = _check_path(source)
    manifest = _load(source / MANIFEST_NAME)
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "files", "exclusions"} or manifest["schema"] != SCHEMA:
        raise Blocked("Unsupported bundle manifest")
    _validate_records(manifest["files"])
    if not isinstance(manifest["exclusions"], list) or not all(isinstance(x, str) for x in manifest["exclusions"]):
        raise Blocked("Invalid exclusions")
    if build_manifest(source, manifest["exclusions"]) != manifest:
        raise Blocked("Bundle missing/added/modified files or hashes")
    return manifest


def _assert_current(path, expected):
    path = _check_path(path)
    if expected is None:
        if path.exists():
            raise Blocked("Concurrent addition prevents payload replacement: " + str(path))
    elif not path.is_file() or _file_record(path) != expected:
        raise Blocked("Concurrent change prevents payload replacement: " + str(path))


def _write_bytes(path, data, expected=_UNCHECKED):
    path = _check_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _check_path(path.parent)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _check_path(path)
        if expected is not _UNCHECKED:
            _assert_current(path, expected)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json(path, value):
    _write_bytes(path, _encoded(value))


def _delete_payload(path, expected):
    path = _check_path(path)
    _assert_current(path, expected)
    path.unlink()


def _payload(target):
    return _records(_walk(target, skip_state=True))


def _validate_receipt(receipt):
    if (not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA
            or set(receipt) != {"schema", "state", "transaction", "files", "manifest_sha256", "before_sha256"}
            or receipt.get("state") != "installed"
            or not re.fullmatch(r"[0-9a-f]{32}", str(receipt.get("transaction")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("manifest_sha256")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("before_sha256")))):
        raise Blocked("Target is not a completed managed installation")
    _validate_records(receipt.get("files"))


def _receipt(target):
    receipt = _load(target / STATE_DIR / "receipt.json")
    _validate_receipt(receipt)
    if _payload(target) != receipt["files"]:
        raise Blocked("Installed files are missing, added or user-modified")
    expected = {"receipt.json"}
    seen = set()
    previous = receipt
    while previous is not None:
        _validate_receipt(previous)
        ident = previous["transaction"]
        if ident in seen:
            raise Blocked("Cyclic installation history")
        seen.add(ident)
        before, _ = _before(target, previous)
        prefix = "history/" + ident + "/"
        expected.add(prefix + "before.json")
        expected.update(prefix + "backup/" + name for name in before["files"])
        previous = before["receipt"]
    actual = set(_walk(target / STATE_DIR)) - {"operation.lock"}
    if actual != expected:
        raise Blocked("Installation metadata has missing/added files")
    return receipt


@contextmanager
def _lock(target):
    path = _check_path(target / STATE_DIR / "operation.lock")
    try:
        handle = path.open("xb")
    except FileExistsError as exc:
        raise Blocked("Another operation or interrupted recovery holds the lock") from exc
    try:
        with handle:
            handle.write(str(os.getpid()).encode("ascii"))
        yield
    finally:
        if path.exists():
            path.unlink()


def _overlap(source, target):
    if source == target or source in target.parents or target in source.parents:
        raise Blocked("Source and target may not overlap")
    if target == Path(target.anchor) or target.parent == target:
        raise Blocked("A filesystem root cannot be the target")


def _remove_empty_dirs(root):
    for base, dirs, _ in os.walk(root, topdown=False, followlinks=False):
        for name in dirs:
            path = _check_path(Path(base) / name)
            if path == root / STATE_DIR or root / STATE_DIR in path.parents:
                continue
            try:
                path.rmdir()
            except OSError:
                pass


def _remove_created_tree(target):
    """Only called after payload verification, for a transaction-created root."""
    target = _check_path(target)
    if target == Path(target.anchor):
        raise Blocked("Refusing root cleanup")
    paths = []
    directories = []
    def onerror(exc):
        raise Blocked("Cleanup directory unreadable") from exc
    for base, dirs, files in os.walk(target, followlinks=False, onerror=onerror):
        directories.extend(_check_path(Path(base) / name) for name in dirs)
        paths.extend(_check_path(Path(base) / name) for name in files)
    for path in paths:
        path.unlink()
    for path in sorted(directories, key=lambda x: len(x.parts), reverse=True):
        path.rmdir()
    target.rmdir()


def _remove_transaction(target, transaction):
    if transaction.parent != target / STATE_DIR / "history" or not re.fullmatch(r"[0-9a-f]{32}", transaction.name):
        raise Blocked("Refusing transaction cleanup outside managed history")
    if transaction.exists():
        _remove_created_tree(transaction)


def _before(target, receipt):
    transaction = target / STATE_DIR / "history" / receipt["transaction"]
    before_path = transaction / "before.json"
    if _hash(_check_path(before_path).read_bytes()) != receipt.get("before_sha256"):
        raise Blocked("Backup descriptor changed")
    before = _load(before_path)
    if set(before) != {"target_existed", "receipt", "files"} or type(before["target_existed"]) is not bool:
        raise Blocked("Invalid backup descriptor")
    _validate_records(before["files"])
    backup_root = transaction / "backup"
    if not backup_root.is_dir() or _records(_walk(backup_root)) != before["files"]:
        raise Blocked("Backup missing/added/modified files")
    if before["target_existed"]:
        old = before["receipt"]
        _validate_receipt(old)
        if old["files"] != before["files"]:
            raise Blocked("Prior installation receipt is invalid")
    elif before["receipt"] is not None or before["files"]:
        raise Blocked("New-target backup descriptor is inconsistent")
    return before, backup_root


def _restore(target, current, before, backup_root, allow_partial=False):
    actual = _payload(target)
    if allow_partial:
        for name, record in actual.items():
            if record not in [current["files"].get(name), before["files"].get(name)]:
                raise Blocked("Recovery refused: a file changed outside this transaction")
    elif actual != current["files"]:
        raise Blocked("Rollback would overwrite later user changes")
    # The complete target and complete backup are checked before the first write.
    if _records(_walk(backup_root)) != before["files"]:
        raise Blocked("Backup changed before restore")
    for name in sorted(before["files"]):
        data = _check_path(backup_root / name).read_bytes()
        if {"sha256": _hash(data), "bytes": len(data)} != before["files"][name]:
            raise Blocked("Backup changed during restore")
        _write_bytes(target / name, data, expected=actual.get(name))
    for name in sorted(set(actual) - set(before["files"])):
        _delete_payload(target / name, actual[name])
    _remove_empty_dirs(target)
    if _payload(target) != before["files"]:
        raise Blocked("Rollback readback failed")
    if before["target_existed"]:
        _write_json(target / STATE_DIR / "receipt.json", before["receipt"])


def install(source, target, dry_run=False):
    """Install a manifest-verified bundle, or update an unchanged managed target."""
    source, target = _check_path(source), _check_path(target)
    _overlap(source, target)
    manifest = validate_bundle(source)
    desired = manifest["files"]
    digest = _hash(_encoded(manifest))
    existed = target.exists()
    if existed:
        old = _receipt(target)
    else:
        if not target.parent.is_dir():
            raise Blocked("Target parent must already exist")
        old = None
    if old and old.get("manifest_sha256") == digest and old["files"] == desired:
        return {"state": "unchanged", "target": str(target), "files": len(desired)}
    for name in desired:
        destination = _check_path(target / name)
        if destination.is_dir() or any(parent.exists() and not parent.is_dir()
                                       for parent in destination.parents if parent != target and target in parent.parents):
            raise Blocked("Update would require a file/directory shape change")
    if dry_run:
        return {"state": "planned", "action": "update" if existed else "install", "files": len(desired), "target": str(target)}
    if not existed:
        target.mkdir()
        (target / STATE_DIR).mkdir()
    transaction_id = uuid.uuid4().hex
    transaction = target / STATE_DIR / "history" / transaction_id
    complete_backup = False
    new = None
    try:
        with _lock(target):
            if existed and _receipt(target) != old:
                raise Blocked("Target receipt changed during preflight")
            transaction.mkdir(parents=True)
            backup = transaction / "backup"
            backup.mkdir()
            before = {"target_existed": existed, "receipt": old, "files": old["files"] if old else {}}
            _write_json(transaction / "before.json", before)
            for name, record in before["files"].items():
                data = _check_path(target / name).read_bytes()
                if {"sha256": _hash(data), "bytes": len(data)} != record:
                    raise Blocked("Target changed during backup")
                _write_bytes(backup / name, data)
            if _records(_walk(backup)) != before["files"]:
                raise Blocked("Backup readback failed")
            complete_backup = True
            new = {"schema": RECEIPT_SCHEMA, "state": "installing", "transaction": transaction_id,
                   "files": desired, "manifest_sha256": digest,
                   "before_sha256": _hash(_encoded(before))}
            _write_json(target / STATE_DIR / "receipt.json", new)
            for name, record in desired.items():
                data = _check_path(source / name).read_bytes()
                if {"sha256": _hash(data), "bytes": len(data)} != record:
                    raise Blocked("Source changed during installation")
                _write_bytes(target / name, data, expected=before["files"].get(name))
            for name in sorted(set(before["files"]) - set(desired)):
                _delete_payload(target / name, before["files"][name])
            _remove_empty_dirs(target)
            if _payload(target) != desired or validate_bundle(source) != manifest:
                raise Blocked("Installation/source readback failed")
            new["state"] = "installed"
            _write_json(target / STATE_DIR / "receipt.json", new)
            _receipt(target)
    except Exception as exc:
        try:
            if complete_backup and new:
                _restore(target, new, before, backup, allow_partial=True)
            if existed:
                _remove_transaction(target, transaction)
                _receipt(target)
            if not existed:
                if _payload(target):
                    raise Blocked("Unexpected payload prevents new-target cleanup")
                _remove_created_tree(target)
        except Exception as recovery:
            raise Blocked("Installation failed; recovery required, state preserved: " + str(recovery)) from exc
        raise Blocked("Installation failed; original state restored: " + str(exc)) from exc
    return {"state": "installed", "action": "update" if existed else "install", "target": str(target),
            "files": len(desired), "receipt": str(target / STATE_DIR / "receipt.json")}


def rollback(target, dry_run=False):
    """Restore the prior state only after global target and backup verification."""
    target = _check_path(target)
    current = _receipt(target)
    before, backup = _before(target, current)
    if dry_run:
        return {"state": "planned", "action": "rollback", "target": str(target), "restore_files": len(before["files"])}
    with _lock(target):
        if _receipt(target) != current:
            raise Blocked("Target changed during rollback preflight")
        before, backup = _before(target, current)
        _restore(target, current, before, backup)
        if before["target_existed"]:
            _remove_transaction(target, target / STATE_DIR / "history" / current["transaction"])
            _receipt(target)
    if not before["target_existed"]:
        if _payload(target):
            raise Blocked("Unexpected payload prevents cleanup")
        _remove_created_tree(target)
    return {"state": "rolled_back", "target": str(target), "target_exists": target.exists()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["manifest", "validate", "install", "rollback"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "manifest" and args.source:
            value = build_manifest(args.source, args.exclude)
            output = _absolute(args.output) if args.output else _absolute(args.source) / MANIFEST_NAME
            if output != _absolute(args.source) / MANIFEST_NAME:
                raise Blocked("Manifest output must be source/" + MANIFEST_NAME)
            _write_json(output, value)
            result = {"state": "manifest_created", "files": len(value["files"]), "path": str(output)}
        elif args.command == "validate" and args.source:
            result = {"state": "valid", "files": len(validate_bundle(args.source)["files"])}
        elif args.command == "install" and args.source and args.target:
            result = install(args.source, args.target, args.dry_run)
        elif args.command == "rollback" and args.target:
            result = rollback(args.target, args.dry_run)
        else:
            raise Blocked("Required command input missing")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (Blocked, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
