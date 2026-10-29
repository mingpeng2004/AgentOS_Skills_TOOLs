"""Read-only client path resolution. Host bindings are private; adapters portable."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
LEGACY = {
    "codex": ["${CODEX_HOME}/skills"],
    "minimax-code": ["${USER_HOME}/.minimax/agents/mavis/skills", "${USER_HOME}/.minimax/skills"],
    "kimi": ["${USER_HOME}/.kimi/skills"],
    "kimi-code": ["${USER_HOME}/.kimi-code/skills"],
    "hermes": ["${HERMES_HOME}/skills"],
    "claude-code": ["${USER_HOME}/.claude/skills"],
}


class PathError(ValueError):
    pass


def user_home():
    return Path.home()


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PathError("duplicate JSON key: " + key)
            result[key] = value
        return result
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique)
    except (OSError, ValueError) as exc:
        raise PathError("invalid path definition: " + str(path)) from exc


def user_environment(name):
    value = os.environ.get(name)
    if value:
        return value
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, kind = winreg.QueryValueEx(key, name)
                if isinstance(value, str):
                    return os.path.expandvars(value)
        except FileNotFoundError:
            pass
    return None


def substitutions(user_root=None):
    home = Path(user_root) if user_root is not None else user_home()
    isolated = user_root is not None
    def env(name, fallback):
        return str(fallback) if isolated else (user_environment(name) or str(fallback))
    local = env("LOCALAPPDATA", home / "AppData/Local")
    roaming = env("APPDATA", home / "AppData/Roaming")
    return {"USER_HOME": str(home), "CODEX_HOME": env("CODEX_HOME", home / ".codex"),
            "COPILOT_HOME": env("COPILOT_HOME", home / ".copilot"),
            "LOCALAPPDATA": local, "APPDATA": roaming,
            "HERMES_HOME": env("HERMES_HOME", Path(local) / "hermes")}


def expand(value, variables):
    if not isinstance(value, str) or not value.strip():
        raise PathError("empty path template")
    def replace(match):
        key = match[1]
        if key not in variables:
            raise PathError("unsupported path variable: " + key)
        return variables[key]
    result = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", replace, value)
    path = Path(result)
    if not path.is_absolute() or ".." in path.parts:
        raise PathError("expected absolute contained path: " + value)
    return path


def is_link(path):
    path = Path(path)
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        return True
    if os.name == "nt":
        import stat
        try:
            return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        except FileNotFoundError:
            pass
    return False


def trusted_root(path):
    """A declared client root may be a migrated junction; canonicalize it once."""
    path = Path(path)
    if not path.is_absolute():
        raise PathError("client root must be absolute")
    return path.resolve()


def checked_child(root, relative, must_exist=True):
    root = Path(root)
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise PathError("expected relative provider path")
    root = trusted_root(root)
    target = root / rel
    for node in [target, *target.parents]:
        if node == root:
            break
        if is_link(node):
            raise PathError("undeclared nested link/junction rejected: " + str(node))
    resolved = target.resolve()
    if root not in resolved.parents:
        raise PathError("provider path escapes declared root")
    if must_exist and not resolved.is_file():
        raise PathError("provider file missing: " + str(resolved))
    return resolved


def verified_shared_sources(bindings, shared_roots):
    """Expose shared Skills only when a private, complete tree receipt binds them."""
    records = bindings.get("shared_source_verification", [])
    if not isinstance(records, list):
        raise PathError("shared source verification must be a list")
    by_name = {}
    for record in records:
        name = record.get("skill") if isinstance(record, dict) else None
        canonical = record.get("canonical_root") if isinstance(record, dict) else None
        hashes = record.get("file_sha256") if isinstance(record, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise PathError("invalid shared skill verification identity")
        if not isinstance(canonical, str) or not Path(canonical).is_absolute() or not isinstance(hashes, dict) or not hashes:
            raise PathError("shared skill lacks a bound canonical tree")
        source_root = trusted_root(canonical)
        if not any(os.path.normcase(str(source_root.parent.resolve())) == os.path.normcase(str(Path(x).resolve()))
                   for x in shared_roots):
            raise PathError("verified shared skill is outside configured shared roots: " + name)
        observed = {}
        for path in sorted(source_root.rglob("*")):
            if is_link(path):
                raise PathError("link inside shared Skill rejected: " + str(path))
            if path.is_file():
                observed[path.relative_to(source_root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        if observed != hashes:
            raise PathError("shared canonical Skill tree drift: " + name)
        if name in by_name:
            raise PathError("duplicate shared Skill identity: " + name)
        by_name[name] = str(source_root)
    for shared_root in shared_roots:
        path = trusted_root(shared_root)
        declared = [name for name in by_name if (path / name).resolve() == Path(by_name[name]).resolve()]
        if not declared:
            raise PathError("shared root has no reviewed Skill sources: " + str(path))
    return by_name


def definitions(root=ROOT):
    path = Path(root) / "runtime/client-adapters.json"
    adapters = load(path).get("adapters", []) if path.is_file() else [
        {"id": key, "skill_roots": value} for key, value in LEGACY.items()]
    ids, aliases = {}, {}
    for entry in adapters:
        ident = entry.get("id")
        if not isinstance(ident, str) or ident in ids:
            raise PathError("missing or duplicate client id")
        ids[ident] = entry
        names = entry.get("aliases", [])
        if not isinstance(names, list) or any(not isinstance(x, str) for x in names):
            raise PathError("invalid client aliases")
        for name in [ident, *names]:
            if name in aliases:
                raise PathError("conflicting client alias: " + name)
            aliases[name] = ident
    if "minimax-code" in ids and "minimax" not in aliases:
        aliases["minimax"] = "minimax-code"
    return ids, aliases


def client_paths(client, root=ROOT, user_root=None):
    root = Path(root)
    entries, aliases = definitions(root)
    if client not in aliases:
        raise PathError("unregistered client: " + client)
    ident = aliases[client]
    entry = entries[ident]
    variables = substitutions(user_root)
    variables["AGENTOS_HOME"] = str(root.resolve())
    private_path = root / ".local/host-bindings.json"
    private = load(private_path) if user_root is None and private_path.is_file() else {}
    host = private.get("clients", {}).get(ident, {})
    def roots(key, default):
        portable = entry.get(key, default)
        if not isinstance(portable, list):
            raise PathError("portable path roots must be an array: " + key)
        declared = list(dict.fromkeys(str(expand(value, variables)) for value in portable))
        items = host.get(key, declared)
        if not isinstance(items, list):
            raise PathError("path roots must be an array: " + key)
        resolved_declared = {os.path.normcase(str(trusted_root(value))) for value in declared}
        result = list(dict.fromkeys(str(expand(value, variables)) for value in items))
        for value in result:
            if os.path.normcase(str(trusted_root(value))) not in resolved_declared:
                raise PathError("host binding is outside adapter-declared roots: " + key)
        return result
    skills = roots("skill_roots", LEGACY.get(ident, []))
    declared_rules = list(dict.fromkeys(str(Path(expand(value, variables)).resolve())
                                        for value in entry.get("rule_files", [])))
    declared_prefixes = entry.get("rule_file_prefixes", {})
    if not isinstance(declared_prefixes, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in declared_prefixes.items()):
        raise PathError("rule_file_prefixes must map path templates to text")
    rule_prefixes = {str(Path(expand(key, variables)).resolve()): value
                     for key, value in declared_prefixes.items()}
    if not set(rule_prefixes).issubset(set(declared_rules)):
        raise PathError("rule prefix path is not a declared client rule file")
    rules = roots("rule_files", [])
    shared = private.get("shared_skill_roots", [])
    if not isinstance(shared, list):
        raise PathError("shared skill roots must be an array")
    shared = list(dict.fromkeys(str(expand(x, variables)) for x in shared))
    shared_sources = verified_shared_sources(private, shared)
    native_rule_target_present = any(Path(x).is_file() for x in rules)
    client_present = host.get("discovered", native_rule_target_present)
    if not isinstance(client_present, bool):
        raise PathError("host discovery state must be boolean")
    return {"id": ident, "aliases": entry.get("aliases", []), "source": entry.get("source"),
            "skill_roots": skills, "rule_files": rules,
            "required_rule_files": declared_rules, "rule_file_prefixes": rule_prefixes,
            "native_rule_target_present": native_rule_target_present,
            "shared_skill_roots": shared,
            "shared_sources": shared_sources,
            "discovered": client_present or any(Path(x).is_dir() for x in skills),
            "binding_source": "host" if host else "portable", "runtime_import": "unattested"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--client")
    args = parser.parse_args(argv)
    try:
        entries, _ = definitions(args.root)
        records = [client_paths(key, args.root) for key in ([args.client] if args.client else entries)]
        print(json.dumps({"schema": "agentos-client-paths-v1", "clients": records}, ensure_ascii=False, indent=2))
        return 0
    except (PathError, OSError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
