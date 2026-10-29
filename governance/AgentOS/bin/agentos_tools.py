"""Read-only discovery and routing for registered Tool assets.

This module never executes a selected tool, installs dependencies, grants
permissions or claims that a vendor client can execute a local path.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent


class Blocked(ValueError):
    pass


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Blocked("duplicate JSON field: " + key)
            result[key] = value
        return result
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique)
    except (OSError, ValueError) as exc:
        raise Blocked("unreadable JSON: " + str(path)) from exc


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_assets(root=ROOT):
    root = Path(root).resolve()
    binding_path = root / ".local/host-bindings.json"
    bindings = read_json(binding_path)
    runtime = bindings.get("runtime", {})
    python = runtime.get("python", {}).get("path")
    asset_cfg = runtime.get("assets", {})
    manifest = Path(asset_cfg.get("manifest", ""))
    asset_root = Path(asset_cfg.get("root", ""))
    if not python or not Path(python).is_file():
        raise Blocked("host-bound Python interpreter is absent")
    if not manifest.is_file() or not asset_root.is_dir():
        raise Blocked("host-bound capability asset manifest/root absent")
    expected = asset_cfg.get("manifest_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise Blocked("capability asset manifest lacks a recorded hash")
    if digest(manifest).casefold() != expected.casefold():
        raise Blocked("capability asset manifest changed since host binding")
    # Import only the data validator; no registered asset module is imported.
    module_path = asset_cfg.get("validator_module")
    if not module_path or not Path(module_path).is_file():
        raise Blocked("asset validator module is unavailable")
    module_hash = asset_cfg.get("validator_sha256")
    if not isinstance(module_hash, str) or digest(module_path).casefold() != module_hash.casefold():
        raise Blocked("asset validator changed since host binding")
    spec = importlib.util.spec_from_file_location("agentos_capability_assets", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry_path = root / "policies/SKILL-REGISTRY.json"
    try:
        validation = module.validate_assets(manifest, registry_path, asset_root)
    except Exception as exc:
        raise Blocked("Tool asset integrity validation failed: " + str(exc)) from exc
    data = read_json(manifest)
    governance_tools = [x for x in data.get("assets", [])
                        if x.get("kind") == "tool" and x.get("id", "").startswith("tool.governance.")]
    if governance_tools:
        bundled_version = asset_root / "governance/AgentOS/VERSION"
        canonical_version = root / "VERSION"
        if not bundled_version.is_file() or not canonical_version.is_file():
            raise Blocked("governance Tool projection or canonical AgentOS version file is missing")
        packaged = bundled_version.read_text(encoding="utf-8-sig").strip()
        current = canonical_version.read_text(encoding="utf-8-sig").strip()
        if packaged != current:
            raise Blocked("governance Tool projection version mismatch: package=" + packaged + " canonical=" + current)
    return bindings, data, validation, Path(python), asset_root


def dependency_state(dependency, python, observed_python_version):
    text = dependency.strip()
    match = re.match(r"^Python\s*(>=|==|>|<=|<)?\s*([0-9]+(?:\.[0-9]+)*)", text, re.I)
    if match:
        current = tuple(int(x) for x in (observed_python_version or "0").split("."))
        required = tuple(int(x) for x in match.group(2).split("."))
        current += (0,) * (len(required) - len(current))
        required += (0,) * (len(current) - len(required))
        op = match.group(1) or ">="
        ok = {">=": current >= required, "==": current == required, ">": current > required,
              "<=": current <= required, "<": current < required}[op]
        return {"dependency": text, "state": "observed_present" if ok else "observed_incompatible",
                "path": str(python), "observed_version": observed_python_version or "unknown"}
    # Do not import the candidate module to probe availability; current Python
    # may differ from the host-bound interpreter and import can have side effects.
    return {"dependency": text, "state": "declared_not_probed"}


def tool_record(asset, asset_root, python, python_version):
    rel = asset.get("entry")
    path = (asset_root / rel).resolve() if isinstance(rel, str) else None
    exists = bool(path and path.is_file())
    return {"id": asset["id"], "name": asset["name"], "status": asset["status"],
            "version": asset["version"],
            "canonical": asset["canonical"], "capabilities": asset["capabilities"],
            "entry": str(path) if path else None,
            "entry_sha256": digest(path) if exists else None,
            "entry_present": exists,
            "runtime_dependencies": [dependency_state(x, python, python_version) for x in asset.get("runtime_dependencies", [])],
            "platforms": asset["platforms"], "side_effects": asset["side_effects"],
            "license": asset["license"], "execution": "not_run_by_discovery"}


def catalog(root=ROOT, capability=None):
    bindings, manifest, validation, python, asset_root = load_assets(root)
    python_version = bindings.get("runtime", {}).get("python", {}).get("observed_version")
    items = [tool_record(x, asset_root, python, python_version) for x in manifest["assets"] if x.get("kind") == "tool"]
    if capability:
        items = [x for x in items if capability in x["capabilities"]]
    return {"schema": "agentos-tool-catalog-v1", "state": "validated_inventory",
            "agentos_root": str(Path(root).resolve()), "capability_count": validation["capability_count"],
            "asset_count": validation["assets"], "asset_fingerprint": validation["fingerprint"],
            "python": str(python), "tools": items,
            "limits": ["Asset integrity validation is not tool execution or domain certification.",
                       "The calling client must be able to access the declared path.",
                       "Permissions, side effects and project authorization remain independently required."]}


def route(root, tool_id, capability=None):
    data = catalog(root)
    choices = [x for x in data["tools"] if x["id"] == tool_id]
    if len(choices) != 1:
        raise Blocked("unknown or ambiguous tool asset ID")
    tool = choices[0]
    if tool["status"] != "active" or not tool["canonical"] or not tool["entry_present"]:
        raise Blocked("tool is not active/canonical or its entry is missing")
    if capability and capability not in tool["capabilities"]:
        raise Blocked("tool does not declare requested capability")
    if any(x["state"] == "observed_incompatible" for x in tool["runtime_dependencies"]):
        raise Blocked("bound runtime does not satisfy tool declaration")
    return {"schema": "agentos-tool-route-v1", "status": "ready_for_authorized_unit",
            "tool": tool, "execution_authority": "not_granted",
            "limits": "Route resolves an integrity-checked entry only; it never executes the tool or overrides project/client safety."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["catalog", "route"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--capability")
    parser.add_argument("--tool")
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            result = catalog(args.root, args.capability)
        else:
            if not args.tool:
                raise Blocked("--tool stable asset ID required")
            result = route(args.root, args.tool, args.capability)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (Blocked, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
