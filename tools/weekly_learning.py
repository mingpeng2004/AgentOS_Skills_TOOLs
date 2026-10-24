"""Bounded local lesson inventory and reviewed public corpus publisher; stdlib."""

from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
import stat

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import distribution as dist
import capability_assets

REPOSITORY = "mingpeng2004/AgentOS_Skills_TOOLs"
API = "https://api.github.com/repos/" + REPOSITORY
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".archive", "_tmp",
        "archive", "archives", "vendor", ".local", ".agentos", "attachments", "reports", "trace", "traces"}
TEXT = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".py", ".ps1", ".cs", ".jsx", ".tsx", ".mjs", ".cjs",
        ".mdc", ".sh", ".bat", ".js", ".ts", ".html", ".css", ".svg", ".xml", ".ini", ".cfg"}
BINARY = {".png", ".jpg", ".jpeg", ".webp", ".docx", ".mp3", ".mp4", ".wav", ".woff2", ".woff", ".ttf"}
SECRETS = re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{25,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
LOCAL = re.compile(r"(?i)(?:[a-z]:[\\/](?:users|000_ai)[\\/]|/" + r"Users/[^/]+/|/" + r"home/[^/]+/)")
IP = re.compile(r"\b(?:192\.168|10\.\d+|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.\d+\b")


class Blocked(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def load(path):
    dist.no_links(path)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def create(path, value):
    path = dist.no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(value if isinstance(value, bytes) else encoded(value))


def atomic(path, value):
    path = dist.no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    create(temporary, value)
    os.replace(temporary, path)


def safe_relative(text):
    rel = PurePosixPath(text)
    if rel.is_absolute() or ".." in rel.parts or "\\" in text or ":" in text or not rel.parts:
        raise Blocked("Unsafe publish path")
    if any(x.startswith(".") and x not in {".gitignore", ".gitkeep", ".env.example"} for x in rel.parts):
        raise Blocked("Private/hidden publish path: " + text)
    return rel.as_posix()


def is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def root_files(root):
    root = dist.no_links(root)
    if not root.is_dir():
        raise Blocked("Source directory missing")
    if is_link(root):
        raise Blocked("Linked source root refused")
    def unreadable(exc):
        raise Blocked("Source directory unreadable") from exc
    for base, dirs, files in os.walk(root, followlinks=False, onerror=unreadable):
        dirs[:] = sorted(x for x in dirs if x not in SKIP)
        for name in dirs:
            if is_link(Path(base) / name):
                raise Blocked("Linked source directory refused")
        for name in sorted(files):
            path = Path(base) / name
            if is_link(path):
                raise Blocked("Linked source file refused")
            yield path


def source_entry(root, category):
    root = Path(root)
    files = {}
    for file in root_files(root):
        if file.stat().st_size > 8 * 1024 * 1024:
            raise Blocked("Oversize Skill source file")
        files[file.relative_to(root).as_posix()] = sha(file.read_bytes())
    if "SKILL.md" not in files:
        raise Blocked("Skill entry missing")
    text = (root / "SKILL.md").read_text(encoding="utf-8-sig")
    match = re.search(r"(?m)^name:\s*[\"']?([A-Za-z0-9][A-Za-z0-9-]{0,63})[\"']?\s*$", text)
    if not match:
        raise Blocked("Skill identity absent")
    return {"path": str(root), "category": category, "name": match[1].lower(), "files": files,
            "digest": sha(encoded(files)), "observed_at": now()}


def scan(workspace=WORKSPACE):
    policy = load(Path(workspace) / ".local/policy.json")
    run = Path(workspace) / ".local/runs" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    skills, records, projects, issues = {}, [], {}, []
    directory_count = 0
    previous_file = Path(workspace) / ".local/last-scan.json"
    previous = load(previous_file) if previous_file.exists() else {"records": []}
    old = {x["path"]: x["sha256"] for x in previous["records"]}
    roots = [(x, "project") for x in policy["project_roots"]]
    roots += [(x["path"], x["category"]) for x in policy["skill_roots"]]
    for location, category in roots:
        root = Path(location)
        if not root.is_dir():
            issues.append({"root": str(root), "state": "absent_at_scan", "observed_at": now()})
            continue
        def error(exc):
            issues.append({"root": str(root), "state": "unreadable", "error": type(exc).__name__})
        for base, dirs, files in os.walk(root, onerror=error, followlinks=False):
            directory_count += 1
            if directory_count > policy.get("max_directories", 160000):
                raise Blocked("Scan bound reached; expand reviewed scope before claiming complete")
            here = Path(base)
            if here.resolve() == Path(workspace).resolve():
                dirs[:] = []
                continue
            linked = [x for x in dirs if is_link(here / x)]
            issues.extend({"root": str(here / x), "state": "linked_excluded"} for x in linked)
            dirs[:] = sorted(x for x in dirs if x not in SKIP and x not in linked)
            if "SKILL.md" in files:
                try:
                    entry = source_entry(here, category)
                    skills[str(here.resolve())] = entry
                except (Blocked, OSError, UnicodeError) as exc:
                    issues.append({"root": str(here), "state": "skill_unreadable", "error": str(exc)})
                    # Keep malformed/unportable Skills visible in the full inventory.
                    key = str(here.resolve())
                    skills[key] = {"path": str(here), "category": category,
                                   "name": re.sub(r"[^a-z0-9-]+", "-", here.name.lower()).strip("-") or "unnamed-skill",
                                   "digest": sha(str(here).encode()), "files": {},
                                   "inventory_only": str(exc)}
                dirs[:] = []
            if any(x in files for x in ["AGENTS.md", "PROJECT_GOVERNANCE.md", "DEC.md"]) or (here / ".git").is_dir():
                projects[str(here.resolve())] = {"id": sha(str(here.resolve()).encode())[:12], "path": str(here), "category": category}
            for name in files:
                lower = name.lower()
                relevant = lower in {"agents.md", "dec.md", "decisions.log", "engineering_lessons.md"} or (
                    Path(name).suffix.lower() in {".md", ".yaml", ".json"} and
                    any(x in str(here).lower() + lower for x in ["knowledge", "postmortem", "lessons"]))
                if category != "project" or not relevant:
                    continue
                path = here / name
                try:
                    if path.stat().st_size > 4 * 1024 * 1024:
                        issues.append({"root": str(path), "state": "oversize_not_read"})
                        continue
                    data = path.read_bytes()
                    records.append({"path": str(path), "sha256": sha(data), "bytes": len(data),
                                    "changed": old.get(str(path)) != sha(data), "observed_at": now()})
                except OSError as exc:
                    issues.append({"root": str(path), "state": "unreadable", "error": type(exc).__name__})
    learning_policy = dict(policy)
    learning_policy["learning_sources"] = list(policy.get("learning_sources", []))
    for item in projects.values():
        for folder in ("skill-runs", "lessons", "checkpoints"):
            path = Path(item["path"]) / ".agentos" / folder
            if path.is_dir():
                learning_policy["learning_sources"].append({"id": "project-" + item["id"] + "-" + folder,
                    "path": str(path), "kind": "directory", "include": ["*.md", "**/*.md", "*.json", "**/*.json"],
                    "max_files": 500, "max_bytes": 4 * 1024 * 1024, "required": False})
    learning = capability_assets.scan_learning(learning_policy, workspace) if learning_policy["learning_sources"] else None
    report = {"schema": "weekly-learning-scan-v2", "created_at": now(), "policy_sha256": sha(encoded(policy)),
              "projects": list(projects.values()), "skills": list(skills.values()), "records": records,
              "issues": issues, "directories_inspected": directory_count, "scope": policy,
              "learning": learning,
              "complete_within_declared_roots": not issues}
    create(run / "scan.json", report)
    atomic(Path(workspace) / ".local/last-scan.json", report)
    print(json.dumps({"scan": str(run / "scan.json"), "projects": len(projects), "skill_sources": len(skills),
                      "lesson_records": len(records), "changed": sum(x["changed"] for x in records), "issues": len(issues)}))
    return report


def portable(data, suffix, replacements):
    if SECRETS.search(data):
        raise Blocked("Credential pattern detected; source quarantined")
    if suffix in BINARY:
        if suffix == ".docx":
            import io
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for name in archive.namelist():
                    if "vbaProject" in name or "embeddings/" in name:
                        raise Blocked("Active DOCX payload refused")
                    item = archive.read(name)
                    if SECRETS.search(item) or LOCAL.search(item.decode("utf-8", errors="ignore")):
                        raise Blocked("Private DOCX metadata/content refused")
        return data, False
    if suffix not in TEXT and suffix not in {"", ".gitignore"}:
        raise Blocked("Unreviewed file type: " + suffix)
    text = data.decode("utf-8-sig")
    original = text
    for old, new in sorted(replacements.items(), key=lambda x: -len(x[0])):
        text = text.replace(old, new).replace(old.replace("\\", "/"), new)
        text = text.replace(old.replace("\\", "\\\\"), new.replace("\\", "\\\\"))
    # Private paths in examples are portable placeholders, never executable defaults.
    text = re.sub(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\s\"'`<>]+", "${USER_SKILLS_PATH}", text)
    text = re.sub(r"(?i)[A-Z]:[\\/]+000_AI[\\/]+[^\s\"'`<>]+", "${PROJECT_PATH}", text)
    text = re.sub(r"/(?:" + r"Users|home)/[^/\s]+/[^\s\"'`<>]*", "${USER_PROJECT_PATH}", text)
    text = re.sub(r"\bmvs_[a-z0-9]{16,}\b", "LOCAL_SESSION_REDACTED", text)
    text = IP.sub("PRIVATE_HOST", text)
    if LOCAL.search(text) or SECRETS.search(text.encode()):
        raise Blocked("Unresolved private path or secret")
    return text.encode("utf-8-sig" if suffix == ".ps1" else "utf-8"), text != original


def payload_files(package):
    package = Path(package)
    result = {}
    for file in root_files(package):
        rel = file.relative_to(package).as_posix()
        safe_relative(rel)
        result[rel] = file.read_bytes()
    return result


def fingerprint(package):
    files = payload_files(package)
    return sha(encoded({key: sha(value) for key, value in files.items()}))


def stage(scan_path, workspace=WORKSPACE):
    workspace = dist.no_links(workspace)
    scan_data = load(scan_path)
    policy_path = workspace / ".local/policy.json"
    policy = load(policy_path)
    identity = dist.target(policy)
    if scan_data["policy_sha256"] != sha(encoded(policy)):
        raise Blocked("Source policy changed since scan")
    run = workspace / ".local/packages" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    package = run / "payload"
    replacements = {policy["agentos_root"]: "${AGENTOS_HOME}", str(Path.home()): "${USER_HOME}"}
    catalog, bindings, source_trees = [], [], []
    def bind_tree(root):
        root = Path(root)
        source_trees.append({"kind": "tree", "source": str(root), "files": dist.tree(root, SKIP), "excluded": sorted(SKIP)})
    def export(relative, source, data=None):
        relative = safe_relative(relative)
        raw = Path(source).read_bytes() if data is None else data
        out, normalized = portable(raw, Path(relative).suffix.lower(), replacements)
        if Path(relative).suffix.lower() in TEXT:
            text = dist.portable_policy(out.decode("utf-8-sig"), relative)
            out = text.encode("utf-8-sig" if relative.endswith(".ps1") else "utf-8")
        path = package / relative
        if path.exists():
            if path.read_bytes() != out:
                raise Blocked("Conflicting portable content: " + relative)
        else:
            create(path, out)
        bindings.append({"source": str(source), "sha256": sha(raw), "target": relative, "normalized": normalized})
        return out
    bindings.append({"source": str(policy_path), "sha256": sha(policy_path.read_bytes())})
    bindings.append({"source": str(scan_path), "sha256": sha(Path(scan_path).read_bytes())})
    agentos = Path(policy["agentos_root"])
    if policy.get("security_check_source"):
        export("tools/security_check.ps1", policy["security_check_source"])
    # Legacy installers mutate client/environment state without rollback; do not ship them.
    for name in ["VERSION", "README.md", "adapters", "bin", "constitution", "policies", "profiles", "protocols", "runtime", "templates", "tests"]:
        base = agentos / name
        if base.is_file():
            export("governance/AgentOS/" + name, base)
        else:
            bind_tree(base)
            for file in root_files(base):
                if file.suffix.lower() in BINARY:
                    continue
                export("governance/AgentOS/" + file.relative_to(agentos).as_posix(), file)
    authored = {}
    for declaration in policy.get("authored_roots", []):
        if declaration.get("license") != "MIT":
            raise Blocked("Explicit authored redistribution license required")
        root = dist.no_links(declaration["path"])
        entry = source_entry(root, "authored")
        authored[str(root)] = entry
        bind_tree(root)
    items = {str(Path(x["path"])): x for x in scan_data["skills"]}
    for root, item in authored.items():
        items.setdefault(root, item)
    selected, canonical = {}, {}
    for root, item in sorted(authored.items()):
        key = (item["name"], item["digest"])
        selected.setdefault(key, root)
    for item in sorted(items.values(), key=lambda x: (x["name"], x["digest"], x["category"], x["path"])):
        public = {"name": item["name"], "source_category": item["category"], "source_id": sha(item["path"].encode())[:12]}
        key = (item["name"], item["digest"])
        if key not in selected or item.get("inventory_only"):
            public.update(state="reference_only", reason="Redistribution rights or complete source integrity not established; obtain from original provider.", license="unknown")
            catalog.append(public)
            continue
        if key in canonical:
            public.update(state="deduplicated", export=canonical[key], license="MIT")
            catalog.append(public)
            continue
        source = Path(selected[key])
        actual = source_entry(source, "authored")
        if actual["digest"] != item["digest"]:
            raise Blocked("Authored Skill drift after scan")
        if source.parent == agentos / "skills":
            prefix = "governance/AgentOS/skills/" + item["name"]
        else:
            prefix = "skills/" + item["name"]
        content, omitted = {}, []
        for rel in actual["files"]:
            file = source / rel
            if file.suffix.lower() in BINARY or file.suffix.lower() in {".log", ".pyc"}:
                omitted.append({"file": rel, "reason": "Binary/privacy review not included in text-only first release"})
                continue
            out = export(prefix + "/" + rel, file)
            content[rel] = sha(out)
        canonical[key] = prefix
        public.update(state="exported", export=prefix, digest=sha(encoded(content)), files=content,
            omitted_runtime_assets=omitted, license="MIT", license_notices=["LICENSE"],
            provenance="Owner-authored maintained source; explicit public MIT authorization 2026-10-25. This is a portable text edition, not a byte-identical local installation.")
        catalog.append(public)
    for name in ["README.md", "AGENTS.md", ".gitignore", "LICENSE", "NOTICE.md", "docs", "tools", "tests", "config"]:
        base = workspace / name
        if not base.exists():
            raise Blocked("Distribution source missing: " + name)
        if base.is_dir():
            bind_tree(base)
            for file in root_files(base):
                export(file.relative_to(workspace).as_posix(), file)
        else:
            export(name, base)
    bind_tree(workspace)
    owner_profile = {"schema": "agentos-owner-profile-v1", "enabled": False, "signature": "",
        "bilingual_reports": False, "report_file_triplets": False, "presentation_style": "user-defined",
        "note": "Explicit opt-in only; no personal author identity is imposed on downstream users."}
    create(package / "governance/AgentOS/profiles/OWNER-PROFILE.example.json", owner_profile)
    create(package / "catalog.json", {"schema": "governed-skill-catalog-v2", "skills": catalog,
        "source_count": len(catalog), "scan_scope": "Configured roots; every unavailable or unsupported source remains explicit.",
        "privacy": "Raw project, client learning and machine data remain private."})
    create(package / "capability-assets.json", dist.assets(package, catalog))
    summary = {"projects_inspected": len(scan_data["projects"]), "lesson_records_inspected": len(scan_data["records"]),
        "skill_sources": len(catalog), "states": {s: sum(x["state"] == s for x in catalog) for s in sorted({x["state"] for x in catalog})},
        "scan_issues": [{"state": x["state"], "source_id": sha(x["root"].encode())[:12]} for x in scan_data["issues"]],
        "scope_complete": scan_data["complete_within_declared_roots"],
        "legacy_installer": "Not distributed; use the preflight/backup/rollback tool.",
        "limits": "Inventory/file checks are not domain certification, client invocation, second-computer or future scheduler evidence."}
    learning = scan_data.get("learning")
    if learning:
        summary["learning_coverage"] = [{k: v for k, v in x.items() if k in {"id", "state", "required", "files_inspected", "directories_inspected", "reason"}} for x in learning["coverage"]]
        bindings.append({"source": learning["observation_path"], "sha256": learning["observation_sha256"]})
    create(package / "evidence/inventory.json", summary)
    for file in (workspace / ".local/public-evidence").glob("*"):
        if file.is_file():
            export("evidence/" + file.name, file)
    bindings.extend(source_trees)
    create(run / "source-bindings.json", bindings)
    create(run / "target.json", identity)
    atomic(workspace / ".local/latest-package.json", {"package": str(package), "sources": str(run / "source-bindings.json"), "scan": str(scan_path)})
    print(json.dumps({"package": str(package), "inventory": summary}, ensure_ascii=False))
    return package


def validate(package):
    package = Path(package)
    files = payload_files(package)
    if not files or "catalog.json" not in files or "governance/AgentOS/VERSION" not in files:
        raise Blocked("Incomplete/empty publish package")
    for name, data in files.items():
        if len(data) > 8 * 1024 * 1024 or SECRETS.search(data):
            raise Blocked("Secret/oversize public file: " + name)
        if Path(name).suffix.lower() in TEXT or name == ".gitignore":
            text = data.decode("utf-8-sig")
            if LOCAL.search(text) or IP.search(text):
                raise Blocked("Private machine data in public file: " + name)
            if name.endswith("SKILL.md") and (not text.startswith("---") or not re.search(r"(?m)^description:\s*\S", text)):
                raise Blocked("Invalid Skill frontmatter: " + name)
        if name.endswith(".ps1") and not data.startswith(b"\xef\xbb\xbf"):
            raise Blocked("PowerShell 5.1 distribution requires UTF-8 BOM: " + name)
    catalog = load(package / "catalog.json")
    if len(catalog["skills"]) != catalog["source_count"]:
        raise Blocked("Incomplete source inventory")
    for item in catalog["skills"]:
        if item["state"] == "exported":
            for rel, expected in item["files"].items():
                name = item["export"] + "/" + rel
                if name not in files or sha(files[name]) != expected:
                    raise Blocked("Export catalog mismatch")
    if catalog.get("schema") == "governed-skill-catalog-v2":
        capability_assets.validate_assets(package / "capability-assets.json", package / "governance/AgentOS/policies/SKILL-REGISTRY.json", package)
    if (package / "portable-manifest.json").exists():
        import portable_install
        try:
            portable_install.validate_bundle(package)
        except portable_install.Blocked as exc:
            raise Blocked(str(exc)) from exc
    return {"state": "valid", "files": len(files), "fingerprint": fingerprint(package)}


def check_sources(bindings):
    if not bindings:
        raise Blocked("Empty source binding")
    for item in bindings:
        if item.get("kind") == "tree":
            if dist.tree(item["source"], set(item["excluded"])) != item["files"]:
                raise Blocked("Source tree membership/content drift invalidates readiness")
            continue
        path = Path(item["source"])
        dist.no_links(path)
        if not path.is_file() or sha(path.read_bytes()) != item["sha256"]:
            raise Blocked("Source drift invalidates publication readiness")


def release_review(package, review_path):
    package = dist.no_links(package)
    validation = validate(package)
    catalog = load(package / "catalog.json")
    if catalog.get("schema") != "governed-skill-catalog-v2" or not (package / "portable-manifest.json").is_file():
        raise Blocked("Production release requires v2 catalog and complete portable manifest")
    review = load(review_path)
    if review.get("state") != "passed" or review.get("package_fingerprint") != validation["fingerprint"]:
        raise Blocked("Actual review must pass for this exact package")
    if not review.get("checks") or not review.get("test_evidence") or not review.get("reviewer"):
        raise Blocked("Incomplete actual review")
    if not review.get("independent_review"):
        raise Blocked("Independent concrete review artifact required")
    for evidence in review["test_evidence"] + [review["independent_review"]]:
        path = Path(evidence["path"])
        if evidence["exit_code"] != 0 or not path.is_file() or sha(path.read_bytes()) != evidence["sha256"]:
            raise Blocked("Test evidence missing or changed")
    return validation


def prepare(package, review_path, workspace=WORKSPACE):
    package = dist.no_links(package)
    validation = release_review(package, review_path)
    sources = load(package.parent / "source-bindings.json")
    check_sources(sources)
    identity = dist.target(load(Path(workspace) / ".local/policy.json"))
    ready = {"schema": "weekly-publication-ready-v2", "target": identity, "package": str(package), "fingerprint": validation["fingerprint"],
             "review": str(Path(review_path).resolve()), "review_sha256": sha(Path(review_path).read_bytes()),
             "sources": str(package.parent / "source-bindings.json"), "sources_sha256": sha(encoded(sources)), "prepared_at": now()}
    path = package.parent / "ready.json"
    create(path, ready)
    print(json.dumps({"state": "ready", "ready": str(path), "files": validation["files"]}))
    return ready


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Blocked("GitHub redirect refused")


class GitHub:
    def __init__(self, repository=REPOSITORY):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise Blocked("Invalid repository identity")
        self.api = "https://api.github.com/repos/" + repository
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            result = subprocess.run(["git", "-c", "credential.interactive=false", "credential", "fill"],
                input="protocol=https\nhost=github.com\n\n", text=True, capture_output=True, timeout=30,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"})
            if result.returncode:
                raise Blocked("Existing GitHub credential unavailable")
            token = next((x.partition("=")[2] for x in result.stdout.splitlines() if x.startswith("password=")), None)
        if not token:
            raise Blocked("Existing GitHub credential unavailable")
        self.headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": "AgentOS-weekly-learning"}
        self.open = urllib.request.build_opener(NoRedirect()).open

    def request(self, method, route, body=None, missing=False):
        if (route and not route.startswith("/")) or ".." in route or "http" in route:
            raise Blocked("Invalid GitHub route")
        request = urllib.request.Request(self.api + route, data=encoded(body) if body is not None else None,
            headers=self.headers, method=method)
        try:
            with self.open(request, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if missing and exc.code in {404, 409}:
                return None
            try:
                failure = json.loads(exc.read())
                # GitHub validation text only, never headers/request bodies/tokens.
                detail = str(failure.get("message", ""))[:180]
            except (ValueError, OSError):
                detail = "validation response unavailable"
            raise Blocked("GitHub HTTP " + str(exc.code) + ": " + detail) from None


def blob_id(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def remote(api, branch):
    ref = api.request("GET", "/git/ref/heads/" + branch, missing=True)
    if ref is None:
        return None, {}, None
    head = ref["object"]["sha"]
    commit = api.request("GET", "/git/commits/" + head)
    tree = api.request("GET", "/git/trees/" + commit["tree"]["sha"] + "?recursive=1")
    if tree.get("truncated"):
        raise Blocked("Truncated remote tree")
    paths = {}
    for item in tree["tree"]:
        if item["type"] == "blob":
            if item.get("mode") == "120000":
                raise Blocked("Remote symlink requires review")
            paths[item["path"]] = item["sha"]
    return head, paths, commit["tree"]["sha"]


def publish(ready_path, workspace=WORKSPACE, api=None):
    workspace = Path(workspace)
    ready = load(ready_path)
    identity = dist.target(load(workspace / ".local/policy.json"))
    if ready.get("schema") != "weekly-publication-ready-v2" or ready.get("target") != identity:
        raise Blocked("Readiness is not authorized for this repository identity")
    target_state = dist.state_root(workspace, identity)
    package = Path(ready["package"])
    actual = release_review(package, ready["review"])
    if ready["fingerprint"] != actual["fingerprint"] or sha(Path(ready["review"]).read_bytes()) != ready["review_sha256"]:
        raise Blocked("Reviewed package changed")
    review = load(ready["review"])
    for evidence in review.get("test_evidence", []) + ([review["independent_review"]] if review.get("independent_review") else []):
        if evidence["exit_code"] != 0 or sha(Path(evidence["path"]).read_bytes()) != evidence["sha256"]:
            raise Blocked("Actual review/test evidence drift")
    sources = load(ready["sources"])
    if sha(encoded(sources)) != ready["sources_sha256"]:
        raise Blocked("Source bindings changed")
    check_sources(sources)
    payload = payload_files(package)
    manifest = {key: blob_id(data) for key, data in payload.items()}
    api = api or GitHub(identity["repository"])
    info = api.request("GET", "")
    if info.get("full_name") != identity["repository"] or info.get("id") != identity["repository_id"] or info.get("archived") or not info.get("permissions", {}).get("push"):
        raise Blocked("Target repository is not writable")
    branch = info["default_branch"]
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch) or ".." in branch:
        raise Blocked("Unsupported default branch")
    head, paths, tree_id = remote(api, branch)
    if head is None:
        refs = api.request("GET", "/git/matching-refs/heads/", missing=True)
        if refs:
            raise Blocked("Default branch missing in nonempty repository; inspect before bootstrap")
        api.request("PUT", "/contents/README.md", {"message": "Initialize governed skills corpus",
                    "content": base64.b64encode(payload["README.md"]).decode(), "branch": branch})
        head, paths, tree_id = remote(api, branch)
        if head is None:
            raise Blocked("Empty repository bootstrap not verified")
    baseline_path = target_state / "last-publication.json"
    baseline = load(baseline_path) if baseline_path.exists() else {"paths": {}}
    if baseline.get("target", identity) != identity:
        raise Blocked("Cross-repository publication baseline refused")
    previous = baseline["paths"]
    for path, expected in manifest.items():
        current = paths.get(path)
        if current is not None and current != expected and current != previous.get(path):
            raise Blocked("Concurrent/unowned remote path change: " + path)
    changes = [key for key in manifest if paths.get(key) != manifest[key]]
    retired = [key for key in previous if key not in manifest and key in paths]
    for key in retired:
        safe_relative(key)
        if paths[key] != previous[key]:
            raise Blocked("Human-modified retired path must be reconciled: " + key)
    if not changes and not retired:
        receipt = {"state": "unchanged", "target": identity, "head": head, "branch": branch, "paths": manifest, "verified_at": now()}
        atomic(baseline_path, receipt)
        pending = target_state / "pending-publication.json"
        if pending.exists():
            saved = load(pending)
            if saved.get("target") == identity and saved.get("paths") == manifest:
                create(target_state / ("reconciled-" + uuid.uuid4().hex[:8] + ".json"),
                       {"state": "verified_remote_content", "head": head, "pending": saved, "verified_at": now()})
                pending.unlink()
        print(json.dumps({key: receipt[key] for key in ["state", "head", "branch"]}))
        return receipt
    # Bound tree requests; one huge content-embedded tree is rejected by GitHub.
    tree_entries = []
    object_cache = target_state / "uploaded-objects.json"
    uploaded = load(object_cache) if object_cache.exists() else {}
    for path in changes:
        data = payload[path]
        try:
            content = data.decode("utf-8")
            tree_entries.append({"path": path, "mode": "100644", "type": "blob", "content": content})
        except UnicodeError:
            ident = manifest[path]
            if not uploaded.get(ident):
                created = api.request("POST", "/git/blobs", {"content": base64.b64encode(data).decode(), "encoding": "base64"})
                if created["sha"] != ident:
                    raise Blocked("Uploaded blob mismatch")
                uploaded[ident] = True
                atomic(object_cache, uploaded)
            tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": ident})
    tree_entries.extend({"path": key, "mode": "100644", "type": "blob", "sha": None} for key in retired)
    batches, batch = [], []
    for entry in tree_entries:
        if batch and (len(batch) >= 100 or len(encoded(batch + [entry])) > 900000):
            batches.append(batch)
            batch = []
        batch.append(entry)
    if batch:
        batches.append(batch)
    for index, batch in enumerate(batches):
        body = {"tree": batch}
        if tree_id:
            body["base_tree"] = tree_id
        tree = api.request("POST", "/git/trees", body)
        tree_id = tree["sha"]
        print(json.dumps({"state": "uploading_tree", "batch": index + 1, "batches": len(batches)}), flush=True)
    commit = api.request("POST", "/git/commits", {"message": "Update verified governance and skills corpus", "tree": tree["sha"], "parents": [head] if head else []})
    pending_path = target_state / "pending-publication.json"
    atomic(pending_path, {"target": identity, "head": commit["sha"], "paths": manifest, "branch": branch, "at": now()})
    check_sources(sources)
    before, _, _ = remote(api, branch)
    if before != head:
        raise Blocked("Remote head changed before update; inspect and merge")
    if head:
        api.request("PATCH", "/git/refs/heads/" + branch, {"sha": commit["sha"], "force": False})
    else:
        # GitHub's empty-repository git API may reject tree creation; a one-file
        # Contents bootstrap is handled explicitly by the operator if required.
        api.request("POST", "/git/refs", {"ref": "refs/heads/" + branch, "sha": commit["sha"]})
    actual_head, actual_paths, _ = remote(api, branch)
    if actual_head != commit["sha"] or any(actual_paths.get(k) != value for k, value in manifest.items()):
        raise Blocked("Remote readback mismatch; publication remains unknown")
    if any(key in actual_paths for key in retired):
        raise Blocked("Retired path deletion not verified")
    if any(actual_paths.get(k) != value for k, value in paths.items() if k not in manifest and k not in retired):
        raise Blocked("Unrelated remote contents changed")
    receipt = {"state": "published", "target": identity, "head": actual_head, "branch": branch, "paths": manifest,
               "package_fingerprint": ready["fingerprint"], "verified_at": now(), "changed_files": len(changes),
               "retired_files": len(retired), "url": "https://github.com/" + identity["repository"] + "/commit/" + actual_head}
    create(package.parent / ("publication-" + uuid.uuid4().hex[:6] + ".json"), receipt)
    atomic(baseline_path, receipt)
    if pending_path.exists():
        pending_path.unlink()
    print(json.dumps({k: receipt[k] for k in ["state", "head", "branch", "changed_files", "url"]}))
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["scan", "stage", "validate", "prepare", "publish"])
    parser.add_argument("--scan", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--ready", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            scan()
        elif args.command == "stage" and args.scan:
            stage(args.scan)
        elif args.command == "validate" and args.package:
            print(json.dumps(validate(args.package)))
        elif args.command == "prepare" and args.package and args.review:
            prepare(args.package, args.review)
        elif args.command == "publish" and args.ready:
            lock = WORKSPACE / ".local/publication.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            created_lock = False
            try:
                with lock.open("x") as handle:
                    created_lock = True
                    handle.write(str(os.getpid()))
                    handle.flush()
                    publish(args.ready)
            finally:
                if created_lock:
                    lock.unlink()
        else:
            raise Blocked("Required command input missing")
        return 0
    except (Blocked, OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
