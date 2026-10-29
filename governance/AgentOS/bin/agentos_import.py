"""Validate AgentOS propagation manifests and emit honest import receipts."""

from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re


class Blocked(RuntimeError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Blocked("Duplicate JSON field: " + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def linked(path):
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(getattr(stat, "st_file_attributes", 0) & 1024)


def contained(root, relative):
    text = str(relative).replace("\\", "/")
    path = Path(text)
    if not text or path.is_absolute() or re.match(r"^[A-Za-z]:", text) or ".." in path.parts:
        raise Blocked("Unsafe relative path: " + text)
    root = Path(root).resolve()
    target = root / path
    for node in [target, *target.parents]:
        if node == root:
            break
        if linked(node):
            raise Blocked("Undeclared nested link: " + str(node))
    if root not in target.resolve().parents:
        raise Blocked("Path escapes root: " + text)
    return target


def strings(value, label, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value) or any(
            not isinstance(item, str) or not item.strip() for item in value):
        raise Blocked("Invalid string list: " + label)
    normalized = [item.replace("\\", "/").casefold() for item in value]
    if len(normalized) != len(set(normalized)):
        raise Blocked("Duplicate entries: " + label)
    return value


def validate(root: Path):
    root = Path(root)
    if not root.is_absolute() or linked(root):
        raise Blocked("AgentOS root must be absolute and not a link")
    root = root.resolve()
    manifest_path = root / "runtime/IMPORT-MANIFEST.json"
    manifest = load(manifest_path)
    if manifest.get("schema") != "agentos-import-manifest-v1":
        raise Blocked("Unsupported import manifest")
    required = strings(manifest.get("required_files"), "required_files", nonempty=True)
    version = root / "VERSION"
    if version.is_file() and version.read_text(encoding="utf-8-sig").strip() != manifest.get("agentos_version"):
        raise Blocked("Manifest version differs from VERSION")
    missing = []
    hashes = {}
    for relative in required:
        path = contained(root, relative)
        if not path.is_file():
            missing.append(relative)
        else:
            hashes[relative] = digest(path)
    if missing:
        raise Blocked("Missing required AgentOS files: " + ", ".join(missing))
    adapters_path = contained(root, "runtime/client-adapters.json")
    adapters = load(adapters_path)
    if adapters.get("schema") != "agentos-client-adapters-v1":
        raise Blocked("Unsupported client adapter manifest")
    if adapters.get("agentos_version") != manifest.get("agentos_version"):
        raise Blocked("Client adapter manifest version differs from import manifest")
    ids, aliases = set(), set()
    for adapter in adapters.get("adapters", []):
        ident = adapter.get("id")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", ident) or ident in ids:
            raise Blocked("Invalid or duplicate client adapter id")
        ids.add(ident)
        names = adapter.get("aliases", [])
        if not isinstance(names, list) or any(not isinstance(x, str) or not x for x in names):
            raise Blocked("Invalid aliases: " + ident)
        for name in names:
            if name in aliases or name in ids:
                raise Blocked("Duplicate client alias: " + name)
            aliases.add(name)
        if not isinstance(adapter.get("surfaces"), list) or not adapter["surfaces"]:
            raise Blocked("Client adapter has no declared injection surface: " + ident)
        source = adapter.get("source")
        if source is not None and not contained(root, source).is_file():
            raise Blocked("Client adapter source missing: " + ident)
    return {"state": "valid", "agentos_version": manifest.get("agentos_version"),
            "required_files": len(hashes), "clients": len(ids),
            "manifest_sha256": digest(manifest_path), "file_hashes": hashes}


def skill_tree(root):
    entry = root / "SKILL.md"
    if not entry.is_file():
        raise Blocked("Skill entry missing: " + str(root))
    tree = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in {".git", "__pycache__"} for part in rel.parts):
            continue
        if linked(path):
            raise Blocked("Nested Skill link rejected: " + str(path))
        if path.is_file():
            tree[rel.as_posix()] = digest(path)
    return tree


def resolve_verified_shared(candidate, resolved_paths):
    """Resolve a linked Skill view to a verified canonical source.

    A client may expose a Skill through a symlinked root (for example a shared
    library mounted into several client homes). Such a view is the same content
    as its source, so it must not be reported as a missing target. It is
    accepted only when it resolves to a source that is already hash-verified
    for this client and the content matches byte-for-byte; a link to anything
    else stays refused.
    """
    try:
        resolved = Path(candidate).resolve()
    except OSError:
        return None
    for source in (resolved_paths.get("shared_sources") or {}).values():
        root = Path(source)
        try:
            if not root.is_dir() or root.resolve() != resolved:
                continue
        except OSError:
            continue
        try:
            if skill_tree(resolved) == skill_tree(root):
                return resolved
        except (Blocked, OSError, ValueError):
            continue
    return None


def host_and_paths(root, client):
    host_file = root / ".local/host-bindings.json"
    if host_file.exists() and linked(host_file):
        raise Blocked("Host binding file cannot be a link")
    host = load(host_file) if host_file.is_file() else {}
    if host and host.get("schema") != "agentos-host-bindings-v1":
        raise Blocked("Unsupported host binding")
    binding = host.get("clients", {}).get(client, {})
    roots = [Path(item) for item in binding.get("skill_roots", [])]
    shared = [Path(item) for item in host.get("shared_skill_roots", [])]
    return binding, roots, shared


def client_parity(root, client, project, required_skills):
    from agentos_paths import client_paths
    from agentos_client_deploy import BEGIN, END, block_for, merged

    binding, roots, shared = host_and_paths(root, client)
    resolved_paths = client_paths(client, root)
    declared_rule_paths = {os.path.normcase(str(Path(item).resolve()))
                           for item in resolved_paths["rule_files"]}
    checks, skill_checks, missing, native_missing = [], [], [], []
    source = root / "runtime/managed-client-entry.md"
    declared = {os.path.normcase(str(Path(x).resolve())): str(Path(x).resolve())
                for x in resolved_paths["required_rule_files"]}
    declared_prefixes = {os.path.normcase(str(Path(path).resolve())): prefix
                         for path, prefix in resolved_paths.get("rule_file_prefixes", {}).items()}
    items = binding.get("adapter_files", [])
    if not isinstance(items, list):
        raise Blocked("adapter_files must be a list")
    expected_paths = set(declared)
    recorded_paths = [os.path.normcase(str(Path(item.get("path", "")).resolve())) for item in items]
    if len(recorded_paths) != len(set(recorded_paths)):
        raise Blocked("duplicate adapter target binding")
    if expected_paths != set(recorded_paths):
        if expected_paths or items:
            return "failed", [{"path": str(x), "sha256": None, "expected_sha256": None,
                                "status": "failed", "reason": "binding does not cover the complete adapter surface"}
                               for x in declared.values()], [], list(required_skills), list(required_skills)
    expected_block, canonical_source_sha = block_for(root)
    for item in items:
        path = Path(item["path"])
        if not path.is_absolute() or os.path.normcase(str(path.resolve())) not in expected_paths:
            raise Blocked("Adapter target is not declared by the portable client surface: " + str(path))
        actual = digest(path) if path.is_file() else None
        expected = item.get("sha256")
        status, reason = "verified", None
        if not expected or actual != expected:
            status, reason = "failed", "deployed target SHA256 differs from host binding"
        if item.get("source_sha256") != canonical_source_sha or item.get("managed_block_sha256") != hashlib.sha256(expected_block).hexdigest():
            status, reason = "failed", "managed entry provenance/hash is missing or stale"
        if status == "verified":
            try:
                raw = path.read_bytes()
                text = raw.decode("utf-8-sig")
                if text.count(BEGIN) != 1 or text.count(END) != 1 or expected_block not in raw:
                    raise Blocked("managed block is absent, duplicate or altered")
                prefix = declared_prefixes.get(os.path.normcase(str(path.resolve())), "")
                created = item.get("created")
                backup_name, backup_hash = item.get("backup_path"), item.get("backup_sha256")
                if not isinstance(created, bool):
                    raise Blocked("deployment provenance lacks created state")
                if created:
                    if backup_name is not None or backup_hash is not None or raw != (prefix.encode("utf-8") + expected_block):
                        raise Blocked("new client rule is not exactly the reviewed managed block")
                else:
                    backup = Path(backup_name or "")
                    if not backup.is_absolute() or not backup.is_file() or digest(backup) != backup_hash:
                        raise Blocked("prior user-content backup missing or hash-invalid")
                    if item.get("new_file_prefix") != (prefix or None):
                        raise Blocked("deployed rule prefix differs from canonical adapter format")
                    restored = merged(backup.read_bytes(), expected_block, prefix)
                    if restored != raw:
                        raise Blocked("unmanaged client rule content differs from protected pre-deploy backup")
            except (OSError, UnicodeError, Blocked) as exc:
                status, reason = "failed", str(exc)
        checks.append({"path": str(path), "sha256": actual, "expected_sha256": expected,
                       "source_sha256": item.get("source_sha256"), "managed_block_sha256": item.get("managed_block_sha256"),
                       "status": status, "reason": reason})
    for name in required_skills:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise Blocked("Invalid required Skill identity")
        canonical = root / "skills" / name
        canonical = canonical if (canonical / "SKILL.md").is_file() else None
        shared_source = resolved_paths.get("shared_sources", {}).get(name)
        target_choices = [project / "skills" / name, *[p / name for p in roots]]
        # A client may expose a shared provider through a symlinked root before
        # its direct managed profile root. Never follow that link merely because
        # it appears first; choose the first complete non-reparse target instead.
        selected = None
        for candidate in target_choices:
            if not (candidate / "SKILL.md").is_file():
                continue
            if linked(candidate):
                # A linked Skill view is acceptable only when it resolves to a
                # verified canonical source and its content matches it
                # byte-for-byte. The link is then a view of the same content,
                # not a divergent copy; the target is still never trusted
                # because it is a link (DEC-064/071).
                resolved_shared = resolve_verified_shared(candidate, resolved_paths)
                if resolved_shared is None:
                    continue
                candidate = resolved_shared
            try:
                skill_tree(candidate)
            except (Blocked, OSError, ValueError):
                continue
            selected = candidate
            break
        reference = Path(shared_source) if shared_source else canonical
        item = {"skill": name, "path": str(selected) if selected else None,
                "canonical": str(reference) if reference else None,
                "status": "missing_target" if not selected and reference else "missing_source" if not reference else "failed"}
        if selected:
            try:
                text = (selected / "SKILL.md").read_text(encoding="utf-8-sig")
                if not re.search(r"(?m)^name:\s*[\"']?" + re.escape(name) + r"[\"']?\s*$", text):
                    raise Blocked("Skill frontmatter identity mismatch")
                observed = skill_tree(selected)
                item["files"] = observed
                if reference and observed != skill_tree(reference):
                    raise Blocked("Skill content differs from verified canonical source")
                item["status"] = "verified_files" if reference else "unattested_source"
            except (Blocked, OSError, ValueError) as exc:
                item["reason"] = str(exc)
        if item["status"] == "missing_target":
            item["availability"] = "canonical_reference_only"
        elif item["status"] == "verified_files":
            item["availability"] = "client_target_verified"
        else:
            item["availability"] = "unavailable"
        if item["status"] not in {"verified_files", "missing_target"}:
            missing.append(name)
        if item["status"] != "verified_files":
            native_missing.append(name)
        skill_checks.append(item)
    if missing or any(item["status"] == "failed" for item in checks):
        state = "failed"
    elif checks and all(item["status"] == "verified" for item in checks) and binding.get("rule_files"):
        state = "verified"
    else:
        state = "unknown"
    return state, checks, skill_checks, missing, native_missing


def verify(root: Path, client: str, project: Path, output: Path):
    root = Path(root)
    project = Path(project)
    if not root.is_absolute() or linked(root):
        raise Blocked("AgentOS root must be absolute and not a link")
    if not project.is_absolute() or linked(project):
        raise Blocked("Project root must be absolute and not a link")
    root = root.resolve()
    checked = validate(root)
    adapters = load(root / "runtime/client-adapters.json")["adapters"]
    adapter = next((item for item in adapters if item["id"] == client or client in item.get("aliases", [])), None)
    if adapter is None:
        raise Blocked("Unknown client adapter: " + client)
    client = adapter["id"]
    project = project.resolve()
    if not (project / "AGENTS.md").is_file():
        raise Blocked("Project AGENTS.md missing")
    project_manifest = project / ".agentos/project-import-manifest.json"
    project_hash = digest(project_manifest) if project_manifest.is_file() else None
    required_skills = []
    if project_manifest.is_file():
        overlay = load(project_manifest)
        if overlay.get("schema") != "agentos-project-import-manifest-v1":
            raise Blocked("Unsupported project import manifest")
        required_overlays = overlay.get("required_overlays", [])
        if not isinstance(required_overlays, list):
            raise Blocked("required_overlays must be a list")
        for item in required_overlays:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
                raise Blocked("invalid project overlay binding")
            path = contained(project, item["path"])
            if not path.is_file() or digest(path).casefold() != item["sha256"].casefold():
                raise Blocked("Project overlay missing or changed: " + item["path"])
        required_skills = strings(overlay.get("required_skills", []), "required_skills")
    parity, client_checks, skill_checks, missing, native_missing = client_parity(root, client, project, required_skills)
    receipt = {
        "schema": "agentos-import-receipt-v2", "agent": client,
        "client_version": adapter.get("version", "unknown"),
        "agentos_version": checked["agentos_version"], "project": str(project),
        "manifest_sha256": checked["manifest_sha256"],
        "project_manifest_sha256": project_hash,
        "observed_files": [{"path": key, "sha256": value} for key, value in checked["file_hashes"].items()],
        "client_checks": client_checks, "skill_checks": skill_checks,
        "required_skills": required_skills, "missing_skills": missing,
        "native_missing_skills": native_missing,
        "states": {"canonical_files": "validated", "file_parity": parity,
                   "import_reported": "unattested", "behavior_attested": "unattested"},
        "adapter_surfaces": adapter["surfaces"],
        "native_surface_reference": adapter.get("native_surface_reference"),
        "limits": "Canonical hashes are observations, not proof of loading. File parity compares recorded deployed targets; runtime import and behavior remain unattested. Shared Skill files do not prove native discovery or tool execution. Host policy is local integrity evidence, not authentication.",
        "observed_at": datetime.now(timezone.utc).isoformat()
    }
    output = Path(os.path.abspath(output))
    protected = {root / name.replace("\\", "/") for name in checked["file_hashes"]}
    protected.update({project / "AGENTS.md", project / ".agentos/project.json", project_manifest,
                      project / ".agentos/evidence/claims.jsonl", root / "VERSION"})
    if output in protected or root == output:
        raise Blocked("Receipt cannot overwrite a canonical source or evidence ledger")
    for node in [output, *output.parents]:
        if linked(node):
            raise Blocked("Receipt output link rejected")
    if output.exists():
        raise Blocked("Receipt output already exists; create-only")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "verify"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--client")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate(args.root) if args.command == "validate" else verify(
            args.root, args.client or "", args.project or Path.cwd(), args.output or Path("import-receipt.json"))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get("states", {}).get("file_parity") == "failed" else 0
    except (Blocked, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
