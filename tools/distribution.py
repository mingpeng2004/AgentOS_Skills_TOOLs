"""Portable distribution policy, source-tree integrity and asset projection."""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat


class Blocked(ValueError):
    pass


VERSION = "1.0.0"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def no_links(path):
    path = Path(os.path.abspath(str(path)))
    if str(path).startswith("\\\\"):
        raise Blocked("Local source/state paths only")
    for node in reversed([path, *path.parents]):
        try:
            info = node.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise Blocked("Linked/reparse source or ancestor refused")
    return path


def target(policy):
    name = policy.get("repository", "")
    ident = policy.get("repository_id")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name) or type(ident) is not int or ident <= 0:
        raise Blocked("An explicitly authorized repository identity is required")
    if any(part in {".", ".."} for part in name.split("/")):
        raise Blocked("Invalid repository name")
    if not policy.get("authorization", {}).get("reference"):
        raise Blocked("Repository authorization reference missing")
    return {"repository": name, "repository_id": ident}


def state_root(workspace, identity):
    return no_links(Path(workspace) / ".local" / "targets" / str(identity["repository_id"]))


def tree(root, excluded):
    root = no_links(root)
    if not root.is_dir():
        raise Blocked("Source tree missing")
    result = {}
    def error(exc):
        raise Blocked("Source directory unreadable") from exc
    for base, dirs, files in os.walk(root, followlinks=False, onerror=error):
        dirs[:] = sorted(x for x in dirs if x not in excluded)
        for name in dirs + files:
            no_links(Path(base) / name)
        for name in sorted(files):
            file = Path(base) / name
            result[file.relative_to(root).as_posix()] = digest(file.read_bytes())
    return result


def portable_policy(text, relative):
    """Explicit distribution overrides; original owner runtime stays untouched."""
    if relative.endswith("references/bugcheck-codes.md"):
        text = re.sub(r"(?s)实测样例（EXAMPLE_HOST.*?(?=### 3\.3)",
                      "Private incident chronology omitted from this public edition.\n\n", text)
    if relative.endswith("PROVENANCE.md"):
        text = text.replace("项目内部授权使用，非第三方再分发", "历史内部授权；当前公开版本由所有者于 2026-10-25 授权采用 MIT")
        text += "\n\nCurrent public edition: owner-authorized MIT distribution, 2026-10-25. Original internal distribution statements describe history, not a restriction on this edition.\n"
    if relative == "tools/security_check.ps1":
        text = re.sub(r"(?ms)^\$script:RegisteredExternalRoots = @\(.*?^\)", "$script:RegisteredExternalRoots = @()", text, count=1)
        text = re.sub(r"(?m)^#Requires -Version 5\.1\s*\n", "", text)
        text = "#Requires -Version 5.1\n" + text
    text = text.replace("${OWNER_SIGNATURE}", "${OWNER_SIGNATURE}")
    text = text.replace("Ming Peng \\| 放眼看世界，明天更美好", "${OWNER_SIGNATURE}")
    text = text.replace("EXAMPLE_HOST", "EXAMPLE_HOST")
    owner_docs = ("runtime/BOOT.md", "runtime/AGENT-IMPORT.md", "constitution/AGENTOS-CONSTITUTION.md",
                  "protocols/DELIVERABLE-STANDARD.md", "protocols/VISUAL-ASSET-STANDARD.md",
                  "protocols/ZERO-GAP-STANDARD.md", "protocols/DATABASE-INTEGRITY-STANDARD.md",
                  "adapters/kimi/SKILL.md", "adapters/minimax/SKILL.md")
    if any(relative.endswith(x) for x in owner_docs):
        boundary = ("## Public distribution profile boundary (takes precedence over the historical owner text)\n"
                 "Personal signature, bilingual file-triplet, presentation-style and image-generation preferences in this historical owner profile are opt-in only. "
                 "They are NOT mandatory defaults for another user. Configure profiles/OWNER-PROFILE.example.json explicitly. "
                 "This JSON is a declarative configuration example, not a runtime loader; the importing agent must explicitly apply the user's selected profile. "
                 "Core evidence, safety, authorization and truthful reporting remain mandatory. Unknown evidence must stay unknown; a zero-gap preference cannot authorize fabrication.\n\n")
        if text.startswith("---"):
            match = re.match(r"(?s)(---\s*\n.*?\n---\s*\n)(.*)", text)
            text = match[1] + "\n" + boundary + match[2] if match else text + "\n" + boundary
        else:
            text = boundary + text
    if relative.endswith("bin/AgentOS.ps1"):
        text = text.replace("Set-StrictMode -Version Latest", "if ($Command -eq 'install') { throw 'Use tools/portable_install.py for preflight, backups and rollback; legacy install is disabled in the public edition.' }\n\nSet-StrictMode -Version Latest", 1)
    if relative == "governance/AgentOS/README.md":
        text = ("# Public edition deployment boundary\n\nUse the repository root README and tools/portable_install.py. Legacy install commands in the historical subsystem notes that follow are disabled in this edition; do not use them as deployment instructions. File deployment does not activate a client automatically. Explicit client/project integration is a separate user choice.\n\n" + text)
    if "visual-asset-production" in relative and relative.endswith("SKILL.md"):
        text += "\n\nPublic portability note: historical batch-size and project-image counts are not current provider limits or performance guarantees. Inspect the selected provider. Optional image scripts require their separately declared dependencies; none are installed automatically.\n"
    return text


def assets(package, catalog):
    package = Path(package)
    items = []
    cap_map = {"embedded-software-engineering": ["meta-qc-gate"], "engineering-contract-and-confirmation": ["meta-router"],
               "windows-crash-forensics": ["km-postmortem"], "production-skill-routing": ["meta-skill-registry"],
               "visual-asset-production": ["vis-concept-illustration"], "weekly-governance-learning": ["km-lessons", "meta-skill-registry"]}
    registry = json.loads((package / "governance/AgentOS/policies/SKILL-REGISTRY.json").read_text("utf-8-sig"))
    governance_version = (package / "governance/AgentOS/VERSION").read_text("utf-8-sig").strip()
    for provider in registry["providers"]:
        cap_map[provider["skill"]] = [x["id"] for x in registry["capabilities"] if x.get("provider") == provider["id"] and x["availability"] != "candidate"]
    def entry(ident, name, kind, path, hashes, caps, state="active", side_effects=None, platforms=None, version=VERSION):
        return {"id": ident, "name": name, "kind": kind, "version": version, "capabilities": caps,
                "entry": path, "platforms": platforms or ["*"], "dependencies": [],
                "side_effects": side_effects or ["Read method files only; no permission implied"],
                "license": "MIT", "provenance": "Owner-authored source; explicit public MIT authorization 2026-10-25; exported-content hashes.",
                "hashes": hashes, "status": state, "canonical": state == "active", "supersedes": []}
    for item in catalog:
        if item["state"] != "exported":
            continue
        prefix = item["export"]
        hashes = {prefix + "/" + p: h for p, h in item["files"].items()}
        text = (package / prefix / "SKILL.md").read_text("utf-8-sig")
        match = re.search(r'(?m)^\s+version:\s*["\']?([A-Za-z0-9.+-]+)', text)
        version = match[1] if match else (governance_version + "+bundled" if prefix.startswith("governance/") else VERSION + "+distribution")
        asset = entry("skill." + item["name"], item["name"], "skill", prefix + "/SKILL.md", hashes,
                      cap_map[item["name"]], version=version)
        if item["name"] == "visual-asset-production":
            asset["runtime_dependencies"] = ["Optional scripts only: numpy", "Optional scripts only: Pillow", "Optional scripts only: scipy", "Optional scripts only: matplotlib"]
        items.append(asset)
    paths = sorted((package / "tools").glob("*.py"))
    paths += sorted((package / "tools").glob("*.ps1"))
    paths += sorted((package / "governance/AgentOS/bin").glob("*.py"))
    paths += sorted((package / "governance/AgentOS/bin").glob("*.ps1"))
    paths += sorted((package / "governance/AgentOS/skills").glob("*/scripts/*.py"))
    for file in paths:
        rel = file.relative_to(package).as_posix()
        # Utility modules are indexed too, but only the documented CLIs are active.
        name = file.stem.lower().replace("_", "-")
        ident = "tool." + ("governance." if rel.startswith("governance/") else "distribution.") + name
        effects = ["Local file/state access according to explicit command; no implicit execution authorization"]
        if name == "weekly-learning":
            effects += ["Explicit publish command uses authenticated GitHub writes; scan is local"]
        if name == "portable-install":
            effects += ["Explicit install/rollback writes only the requested target and verified backup state"]
        optional = "/scripts/" in rel
        documented_cli = name in {"weekly-learning", "agentos-toolkit", "capability-assets", "portable-install", "verify-release", "security-check", "agentos-skills", "agentos", "agentos-contract", "agentos-decision", "agentos-evidence"}
        asset = entry(ident, name, "tool", rel, {rel: digest(file.read_bytes())},
                      ["vis-concept-illustration"] if optional else ["meta-skill-registry" if "capability" in name or "skills" in name else "meta-qc-gate"],
                      state="candidate" if optional else "active" if documented_cli else "validated", side_effects=effects,
                      platforms=["windows"] if file.suffix == ".ps1" else ["*"],
                      version=governance_version if rel.startswith("governance/") else VERSION)
        asset["runtime_dependencies"] = (["Python 3.9+", "numpy", "Pillow", "scipy", "matplotlib"] if optional else
                                         ["Windows PowerShell 5.1+"] if file.suffix == ".ps1" else ["Python 3.9+"])
        items.append(asset)
    dependency_map = {"tool.distribution.weekly-learning": ["tool.distribution.distribution", "tool.distribution.capability-assets", "tool.distribution.portable-install"],
                      "tool.distribution.agentos-toolkit": ["tool.distribution.weekly-learning", "tool.distribution.distribution", "tool.distribution.capability-assets", "tool.distribution.portable-install"]}
    known = {x["id"] for x in items}
    for item in items:
        item["dependencies"] = [x for x in dependency_map.get(item["id"], []) if x in known]
    return {"schema": "agentos-capability-assets-v1", "assets": items}
