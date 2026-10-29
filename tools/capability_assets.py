"""Stdlib asset contracts and private, evidence-bound learning intake.

Capability definitions remain authoritative in AgentOS SKILL-REGISTRY.json.
This module never executes tools, promotes capabilities, or publishes records.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import uuid


ASSET_SCHEMA = "agentos-capability-assets-v1"
SCAN_SCHEMA = "agentos-learning-observation-v1"
RECEIPT_SCHEMA = "agentos-learning-receipt-v2"
ID = re.compile(r"[a-z][a-z0-9._-]{0,127}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")
STATUSES = {"candidate", "validated", "active", "reference_only", "blocked", "retired"}
DISPOSITIONS = {"strengthen", "new", "duplicate", "blocked"}
ASSET_FIELDS = {"id", "name", "kind", "version", "capabilities", "entry", "platforms",
                "dependencies", "side_effects", "license", "provenance", "hashes",
                "status", "canonical", "supersedes"}
TEXT_SUFFIXES = {".md", ".mdc", ".txt", ".json", ".yaml", ".yml", ".toml"}
RAW_PARTS = {"sessions", "archived_sessions", "transcripts", "conversations", "raw_sessions",
             "traces", "trace", "dumps", "node_modules", ".git", ".venv", "__pycache__"}


class Blocked(ValueError):
    """An invalid contract, unsafe path, or unbound observation blocks adoption."""


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _no_links(path):
    path = Path(os.path.abspath(os.fspath(path)))
    if str(path).startswith("\\\\"):
        raise Blocked("Network paths are outside local learning scope")
    for node in reversed([path, *path.parents]):
        try:
            info = os.lstat(node)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
            raise Blocked("Link/reparse path refused: " + str(node))
    return path


def _relative(text):
    if not isinstance(text, str) or not text or "\\" in text or ":" in text:
        raise Blocked("Expected a portable relative path")
    rel = PurePosixPath(text)
    if rel.is_absolute() or any(x in {".", ".."} for x in text.split("/")) or "//" in text:
        raise Blocked("Path traversal/absolute path refused")
    return rel


def contained(root, relative, must_exist=True):
    root = _no_links(root)
    rel = _relative(relative)
    path = _no_links(root.joinpath(*rel.parts))
    if root not in path.parents:
        raise Blocked("Asset path escapes its root")
    if must_exist and not path.is_file():
        raise Blocked("Required file missing: " + str(path))
    return path


def _read(path, maximum=8 * 1024 * 1024):
    path = _no_links(path)
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise Blocked("Read bound exceeded: " + str(path))
    return data


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Blocked("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(_read(path).decode("utf-8-sig"), object_pairs_hook=unique)


def _object(value):
    return value if isinstance(value, dict) else load(value)


def _strings(value, label, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise Blocked("Invalid string list: " + label)
    if len({x.casefold() for x in value}) != len(value):
        raise Blocked("Duplicate item: " + label)


def _capabilities(registry):
    data = _object(registry)
    if data.get("schema") != "agentos-skill-registry-v1" or not isinstance(data.get("capabilities"), list):
        raise Blocked("Expected authoritative AgentOS capability registry")
    ids = [item.get("id") for item in data["capabilities"]]
    if not ids or any(not isinstance(x, str) or not ID.fullmatch(x) for x in ids) or len(set(ids)) != len(ids):
        raise Blocked("Invalid/duplicate authoritative capability IDs")
    return set(ids)


def _acyclic(assets, field):
    done = set()
    def visit(key, trail):
        if key in trail:
            raise Blocked("Cyclic " + field + " graph")
        if key not in done:
            for parent in assets[key][field]:
                if parent == key or parent not in assets:
                    raise Blocked("Unknown/self asset reference: " + field)
                visit(parent, trail | {key})
            done.add(key)
    for key in assets:
        visit(key, set())


def validate_assets(manifest, capability_registry, root):
    """Validate local asset integrity; this is not domain competence certification."""
    manifest = _object(manifest)
    caps = _capabilities(capability_registry)
    if set(manifest) != {"schema", "assets"} or manifest["schema"] != ASSET_SCHEMA or not isinstance(manifest["assets"], list):
        raise Blocked("Invalid asset manifest envelope")
    if not manifest["assets"]:
        raise Blocked("Empty asset registry cannot pass")
    _no_links(root)
    assets, canonical, content = {}, {}, {}
    for asset in manifest["assets"]:
        if not isinstance(asset, dict) or not ASSET_FIELDS <= set(asset) or set(asset) - ASSET_FIELDS - {"family", "runtime_dependencies"}:
            raise Blocked("Incomplete/unknown asset fields")
        key = asset["id"]
        if not isinstance(key, str) or not ID.fullmatch(key) or key.casefold() in assets:
            raise Blocked("Invalid/duplicate stable asset ID")
        for field in ("name", "version", "license", "provenance"):
            if not isinstance(asset[field], str) or not asset[field].strip():
                raise Blocked("Missing asset " + field)
        if asset["kind"] not in {"skill", "tool"} or asset["status"] not in STATUSES or type(asset["canonical"]) is not bool:
            raise Blocked("Invalid kind/status/canonical")
        for field in ("capabilities", "dependencies", "supersedes", "side_effects", "platforms"):
            _strings(asset[field], field, nonempty=field in {"platforms", "side_effects"})
        _strings(asset.get("runtime_dependencies", []), "runtime_dependencies", nonempty=False)
        if any(x not in caps for x in asset["capabilities"]):
            raise Blocked("Unknown authoritative capability reference")
        if asset["status"] in {"validated", "active"} and not asset["capabilities"]:
            raise Blocked("Deployed asset requires an existing capability reference")
        if asset["status"] == "active" and not asset["canonical"]:
            raise Blocked("Active asset must be a selected canonical variant")
        if asset["canonical"] and asset["status"] != "active":
            raise Blocked("Only an active asset can be canonical")
        if asset["status"] in {"active", "validated"} and asset["license"].casefold() in {"unknown", "unreviewed", "none"}:
            raise Blocked("Redistribution/deployment rights remain unknown")
        hashes = asset["hashes"]
        if not isinstance(hashes, dict):
            raise Blocked("Invalid asset hashes")
        if asset["status"] not in {"reference_only", "blocked", "retired"} and (not hashes or asset["entry"] is None):
            raise Blocked("Executable/method asset needs entry and bound content")
        folded = set()
        for relative, expected in hashes.items():
            _relative(relative)
            if relative.casefold() in folded or not isinstance(expected, str) or not HASH.fullmatch(expected):
                raise Blocked("Invalid/ambiguous content hash path")
            folded.add(relative.casefold())
            if sha(_read(contained(root, relative))) != expected:
                raise Blocked("Asset content hash mismatch: " + relative)
        if asset["entry"] is not None:
            _relative(asset["entry"])
            if asset["entry"] not in hashes:
                raise Blocked("Asset entry is not hash bound")
        family = asset.get("family", asset["name"])
        if not isinstance(family, str) or not family.strip():
            raise Blocked("Invalid asset family")
        if asset["canonical"]:
            identity = (asset["kind"], family.casefold())
            previous = canonical.setdefault(identity, [])
            for other in previous:
                if "*" in asset["platforms"] or "*" in other["platforms"] or {x.casefold() for x in asset["platforms"]} & {x.casefold() for x in other["platforms"]}:
                    raise Blocked("Ambiguous canonical asset variants: " + family)
            previous.append(asset)
            signature = (asset["kind"], tuple(sorted(hashes.values())))
            if hashes and signature in content:
                raise Blocked("Duplicate active content under different asset IDs")
            content[signature] = key
        assets[key.casefold()] = asset
    # References are exact IDs, not filesystem names or model-supplied aliases.
    exact = {asset["id"]: asset for asset in assets.values()}
    _acyclic(exact, "dependencies")
    _acyclic(exact, "supersedes")
    for asset in exact.values():
        if asset["status"] == "active":
            if any(exact[x]["status"] not in {"active", "validated"} for x in asset["dependencies"]):
                raise Blocked("Active asset depends on an unavailable asset")
            if any(exact[x]["status"] == "active" for x in asset["supersedes"]):
                raise Blocked("Superseded variant is still active")
    return {"schema": ASSET_SCHEMA, "state": "valid", "assets": len(exact),
            "by_kind": {kind: sum(x["kind"] == kind for x in exact.values()) for kind in ("skill", "tool")},
            "capability_count": len(caps), "fingerprint": sha(encoded(manifest)),
            "limits": "Structure and current content only; no capability promotion, dependency installation or execution permission."}


def _private_root(workspace):
    workspace = _no_links(workspace)
    root = contained(workspace, ".local/learning", must_exist=False)
    root.mkdir(parents=True, exist_ok=True)
    return _no_links(root)


def _create(path, value):
    path = _no_links(path)
    _no_links(path.parent).mkdir(parents=True, exist_ok=True)
    _no_links(path.parent)
    with path.open("xb") as stream:
        stream.write(encoded(value))


def _receipts(root):
    directory = contained(root, "receipts", must_exist=False)
    if not directory.exists():
        return []
    _no_links(directory)
    return [load(path) for path in sorted(directory.glob("*.json"))]


def learning_status(workspace):
    """Derive the adjudicated cursor from immutable receipts, never scan activity."""
    root = _private_root(workspace)
    receipts = _receipts(root)
    consumed = {}
    blocked, legacy = 0, []
    for receipt in receipts:
        if receipt.get("schema") == "agentos-learning-receipt-v1":
            legacy.append(receipt.get("id", "unknown"))
            continue
        if receipt.get("schema") != RECEIPT_SCHEMA:
            raise Blocked("Unknown private receipt schema")
        if receipt["disposition"] == "blocked":
            blocked += 1
            continue
        for source in receipt["sources"]:
            consumed.setdefault(source["key"], set()).add(source["sha256"])
    return {"schema": "agentos-learning-status-v1", "receipts": len(receipts), "blocked": blocked,
            "legacy_unvalidated": legacy,
            "adjudicated": {key: sorted(values) for key, values in sorted(consumed.items())}}


def _source_policy(source):
    if not isinstance(source, dict) or not {"id", "path", "kind"} <= set(source):
        raise Blocked("Learning source requires id/path/kind")
    if set(source) - {"id", "path", "kind", "include", "max_files", "max_bytes", "max_directories", "required", "note"}:
        raise Blocked("Unknown learning-source field")
    if not isinstance(source["id"], str) or not ID.fullmatch(source["id"]) or source["kind"] not in {"file", "directory"}:
        raise Blocked("Invalid learning-source identity/kind")
    if not isinstance(source["path"], str) or not Path(source["path"]).is_absolute():
        raise Blocked("Learning source must be an explicit absolute local path")
    for key, default in (("max_files", 1000), ("max_bytes", 4 * 1024 * 1024), ("max_directories", 10000)):
        value = source.get(key, default)
        if type(value) is not int or not 1 <= value <= (64 * 1024 * 1024 if key == "max_bytes" else 1000000):
            raise Blocked("Invalid learning-source bound: " + key)
    if "required" in source and type(source["required"]) is not bool:
        raise Blocked("required must be boolean")
    if "note" in source and (not isinstance(source["note"], str) or not source["note"].strip()):
        raise Blocked("note must be a non-empty string")
    _strings(source.get("include", ["*.md", "*.mdc", "*.txt"]), "include")
    return source


def scan_learning(policy, workspace):
    """Read explicit persistent learning sources; raw sessions never enter intake."""
    policy = _object(policy)
    sources = policy.get("learning_sources")
    if not isinstance(sources, list):
        raise Blocked("Explicit learning_sources policy is required")
    checked = [_source_policy(source) for source in sources]
    if len({x["id"].casefold() for x in checked}) != len(checked):
        raise Blocked("Duplicate learning-source ID")
    root = _private_root(workspace)
    observation_dir = contained(root, "observations", must_exist=False)
    previous_paths = sorted(observation_dir.glob("*.json")) if observation_dir.exists() else []
    previous = load(previous_paths[-1]) if previous_paths else {"records": []}
    old = {x["key"]: x["sha256"] for x in previous["records"]}
    adjudicated = learning_status(workspace)["adjudicated"]
    records, coverage = [], []
    for source in checked:
        summary = {"id": source["id"], "kind": source["kind"], "required": source.get("required", True),
                   "state": "empty", "files_inspected": 0, "directories_inspected": 0, "issues": []}
        coverage.append(summary)
        location = Path(source["path"])
        try:
            _no_links(location)
            if any(part.casefold() in RAW_PARTS for part in location.parts):
                summary.update(state="excluded", issues=[{"state": "raw_or_runtime_source_excluded"}])
                continue
            if not location.exists():
                summary["state"] = "absent"
                continue
            if (source["kind"] == "file" and not location.is_file()) or (source["kind"] == "directory" and not location.is_dir()):
                summary.update(state="invalid", issues=[{"state": "source_kind_mismatch"}])
                continue
            candidates = []
            if source["kind"] == "file":
                candidates = [location]
            else:
                def error(exc):
                    summary["issues"].append({"state": "unreadable", "path": str(exc.filename or location), "error": type(exc).__name__})
                for base, dirs, files in os.walk(location, followlinks=False, onerror=error):
                    summary["directories_inspected"] += 1
                    if summary["directories_inspected"] > source.get("max_directories", 10000):
                        summary["issues"].append({"state": "directory_limit_reached"})
                        break
                    allowed = []
                    for name in sorted(dirs):
                        child = Path(base) / name
                        try:
                            _no_links(child)
                            if name.casefold() not in RAW_PARTS:
                                allowed.append(name)
                            else:
                                summary["issues"].append({"state": "excluded_runtime_directory", "path": str(child)})
                        except (OSError, Blocked) as exc:
                            summary["issues"].append({"state": "excluded_link_or_unreadable", "path": str(child), "error": type(exc).__name__})
                    dirs[:] = allowed
                    for name in sorted(files):
                        file = Path(base) / name
                        relative = file.relative_to(location).as_posix()
                        if any(fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(name, pattern) for pattern in source.get("include", ["*.md", "*.mdc", "*.txt"])):
                            candidates.append(file)
                            if len(candidates) > source.get("max_files", 1000):
                                summary["issues"].append({"state": "file_limit_reached"})
                                break
                    if len(candidates) > source.get("max_files", 1000):
                        break
            for file in candidates[:source.get("max_files", 1000)]:
                relative = file.name if source["kind"] == "file" else file.relative_to(location).as_posix()
                if file.suffix.casefold() not in TEXT_SUFFIXES or any(x.casefold() in RAW_PARTS for x in file.parts):
                    summary["issues"].append({"state": "unsupported_or_raw_file_excluded", "path": str(file)})
                    continue
                try:
                    data = _read(file, source.get("max_bytes", 4 * 1024 * 1024))
                    data.decode("utf-8-sig")
                    digest = sha(data)
                    key = source["id"] + ":" + relative
                    records.append({"key": key, "source_id": source["id"], "path": str(_no_links(file)),
                                    "sha256": digest, "bytes": len(data), "observed_at": now(),
                                    "changed_since_observation": old.get(key) != digest,
                                    "pending_adjudication": digest not in adjudicated.get(key, [])})
                    summary["files_inspected"] += 1
                except (OSError, UnicodeError, Blocked) as exc:
                    summary["issues"].append({"state": "unreadable_or_oversize", "path": str(file), "error": type(exc).__name__})
            if summary["issues"]:
                summary["state"] = "partial" if summary["files_inspected"] else "unreadable_or_excluded"
            elif summary["files_inspected"]:
                summary["state"] = "scanned"
        except (OSError, Blocked) as exc:
            summary.update(state="unreadable_or_excluded", issues=[{"state": "unsafe_or_unreadable_source", "error": type(exc).__name__}])
    observed_keys = {x["key"] for x in records}
    report = {"schema": SCAN_SCHEMA, "created_at": now(), "policy_sha256": sha(encoded({"learning_sources": checked})),
              "records": records, "coverage": coverage,
              "no_longer_observed": sorted(set(old) - observed_keys),
              "complete_within_declared_sources": bool(checked) and all(x["state"] in {"scanned", "empty"} for x in coverage),
              "limits": "Explicit persistent learning only; observations do not consume lessons; raw sessions are not exported."}
    path = observation_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8] + ".json")
    _create(path, report)
    report["observation_path"] = str(path)
    report["observation_sha256"] = sha(_read(path))
    return report


def _binding(binding, label, root=None):
    if not isinstance(binding, dict) or not {"path", "sha256"} <= set(binding):
        raise Blocked("Incomplete " + label + " binding")
    if not isinstance(binding["sha256"], str) or not HASH.fullmatch(binding["sha256"]):
        raise Blocked("Invalid " + label + " hash")
    path = contained(root, binding["path"]) if root is not None else _no_links(binding["path"])
    if root is None and not Path(binding["path"]).is_absolute():
        raise Blocked("Evidence path must be absolute")
    if sha(_read(path)) != binding["sha256"]:
        raise Blocked("Changed/missing " + label + " evidence")
    return path


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError) as exc:
        raise Blocked("Invalid execution timestamp") from exc
    if parsed.tzinfo is None:
        raise Blocked("Execution timestamp requires timezone")
    return parsed


def _hash_map(value, label, absolute=False):
    if not isinstance(value, dict) or not value:
        raise Blocked("Nonempty hash map required: " + label)
    for path, digest in value.items():
        if not isinstance(path, str) or not isinstance(digest, str) or not HASH.fullmatch(digest):
            raise Blocked("Invalid hash map: " + label)
        if absolute:
            _binding({"path": path, "sha256": digest}, label)
    return value


def _execution(evidence, target_hashes, observation_time):
    binding = evidence.get("execution_receipt")
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise Blocked("Actual execution receipt binding required")
    execution_path = _binding(binding, "execution receipt")
    execution = load(execution_path)
    fields = {"command", "exit_code", "output_complete", "log", "target_hashes",
              "test_source_hashes", "started_at", "finished_at"}
    if not isinstance(execution, dict) or set(execution) != fields:
        raise Blocked("Incomplete/unknown execution receipt fields")
    _strings(execution["command"], "execution command")
    if type(execution["exit_code"]) is not int or execution["exit_code"] != 0 or execution["output_complete"] is not True:
        raise Blocked("Execution failed or output incomplete")
    if execution["log"] != {"path": evidence["path"], "sha256": evidence["sha256"]}:
        raise Blocked("Execution log does not match verification artifact")
    _binding(execution["log"], "execution log")
    if execution["target_hashes"] != target_hashes:
        raise Blocked("Execution is not bound to current complete target hashes")
    _hash_map(execution["test_source_hashes"], "test source", absolute=True)
    started, finished = _time(execution["started_at"]), _time(execution["finished_at"])
    if started > finished or finished > datetime.now(timezone.utc) or finished < _time(observation_time):
        raise Blocked("Execution timestamps are incomplete, stale or in the future")
    return {"path": str(execution_path), "sha256": binding["sha256"]}


def _review(receipt, source_hashes, target_hashes, executions):
    producer = receipt.get("producer")
    if not isinstance(producer, str) or not producer.strip():
        raise Blocked("Actual producer identity record required")
    binding = receipt.get("review")
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise Blocked("Independent review artifact binding required")
    review = load(_binding(binding, "independent review"))
    fields = {"state", "producer", "reviewer", "source_hashes", "target_hashes", "verification_receipts"}
    if not isinstance(review, dict) or set(review) != fields or review["state"] != "passed":
        raise Blocked("Independent review has not passed this evidence contract")
    reviewer = review["reviewer"]
    if not isinstance(reviewer, str) or not reviewer.strip() or reviewer.strip().casefold() == producer.strip().casefold() or review["producer"] != producer:
        raise Blocked("Reviewer must be distinct from the recorded producer")
    if "reviewer" in receipt and receipt["reviewer"] != reviewer:
        raise Blocked("Receipt reviewer differs from review artifact")
    if review["source_hashes"] != source_hashes or review["target_hashes"] != target_hashes:
        raise Blocked("Independent review source/target hashes differ")
    expected = {item["path"]: item["sha256"] for item in executions}
    if review["verification_receipts"] != expected:
        raise Blocked("Independent review does not bind this execution round")
    return reviewer


def record_receipt(receipt, workspace, asset_manifest=None, capability_registry=None, root=None):
    """Adjudicate only currently hash-bound evidence; blocked receipts consume nothing."""
    receipt = _object(receipt)
    required = {"schema", "id", "disposition", "reason", "sources", "observation", "observation_sha256"}
    allowed = required | {"capabilities", "assets", "targets", "verification", "reviewer", "producer", "review", "duplicate_of", "proposed_capability"}
    if not required <= set(receipt) or set(receipt) - allowed or receipt["schema"] != RECEIPT_SCHEMA:
        raise Blocked("Invalid learning receipt schema")
    if not isinstance(receipt["id"], str) or not ID.fullmatch(receipt["id"]) or receipt["disposition"] not in DISPOSITIONS:
        raise Blocked("Invalid receipt identity/disposition")
    if not isinstance(receipt["reason"], str) or not receipt["reason"].strip() or not isinstance(receipt["sources"], list):
        raise Blocked("Receipt needs reason and sources")
    private = _private_root(workspace)
    observation_path = _binding({"path": receipt["observation"], "sha256": receipt["observation_sha256"]}, "observation")
    observation_root = contained(private, "observations", must_exist=False)
    if observation_path.parent != observation_root:
        raise Blocked("Observation is outside this workspace")
    observation = load(observation_path)
    if observation.get("schema") != SCAN_SCHEMA:
        raise Blocked("Not a learning observation")
    observed = {x["key"]: x for x in observation["records"]}
    if receipt["disposition"] != "blocked" and not receipt["sources"]:
        raise Blocked("Adjudication requires observed sources")
    keys = set()
    for source in receipt["sources"]:
        if not isinstance(source, dict) or set(source) != {"key", "path", "sha256"} or source["key"] in keys:
            raise Blocked("Invalid/duplicate lesson source binding")
        keys.add(source["key"])
        prior = observed.get(source["key"])
        if prior is None or any(prior[field] != source[field] for field in ("path", "sha256")):
            raise Blocked("Source not bound to the cited observation")
        if receipt["disposition"] != "blocked":
            _binding(source, "lesson source")
    disposition = receipt["disposition"]
    if disposition in {"strengthen", "new"}:
        if asset_manifest is None or capability_registry is None or root is None:
            raise Blocked("Changed learning requires asset, capability and target roots")
        validation = validate_assets(asset_manifest, capability_registry, root)
        assets = {x["id"]: x for x in _object(asset_manifest)["assets"]}
        _strings(receipt.get("assets"), "receipt assets")
        if any(x not in assets for x in receipt["assets"]):
            raise Blocked("Unknown target asset")
        caps = _capabilities(capability_registry)
        _strings(receipt.get("capabilities", []), "receipt capabilities", nonempty=disposition == "strengthen")
        if any(x not in caps for x in receipt.get("capabilities", [])):
            raise Blocked("Unknown capability cannot be auto-promoted")
        selected_capabilities = {cap for key in receipt["assets"] for cap in assets[key]["capabilities"]}
        if any(cap not in selected_capabilities for cap in receipt.get("capabilities", [])):
            raise Blocked("Receipt capability does not belong to its target assets")
        if disposition == "new":
            proposal = receipt.get("proposed_capability")
            if not isinstance(proposal, dict) or set(proposal) != {"id", "reason"} or not isinstance(proposal["id"], str) or not ID.fullmatch(proposal["id"]) or not isinstance(proposal["reason"], str) or not proposal["reason"].strip():
                raise Blocked("New learning needs an explicit candidate/gap proposal")
        targets = receipt.get("targets")
        if not isinstance(targets, list) or not targets:
            raise Blocked("Actual changed target hashes required")
        bound_targets = set()
        selected_hashes = {path: digest for key in receipt["assets"] for path, digest in assets[key]["hashes"].items()}
        for target in targets:
            if not isinstance(target, dict) or set(target) != {"path", "sha256"} or selected_hashes.get(target["path"]) != target["sha256"]:
                raise Blocked("Target not bound to selected asset hashes")
            _binding(target, "target", root)
            if target["path"] in bound_targets:
                raise Blocked("Duplicate target binding")
            bound_targets.add(target["path"])
        if any(not bound_targets.intersection(assets[key]["hashes"]) for key in receipt["assets"]):
            raise Blocked("Each selected asset requires an actual target binding")
        verification = receipt.get("verification")
        if not isinstance(verification, list):
            raise Blocked("Actual verification artifacts required")
        kinds, executions = set(), []
        target_hashes = {item["path"]: item["sha256"] for item in targets}
        for evidence in verification:
            if not isinstance(evidence, dict) or set(evidence) != {"kind", "path", "sha256", "exit_code", "execution_receipt"} or evidence["kind"] not in {"counterexample", "normal", "boundary"} or type(evidence["exit_code"]) is not int or evidence["exit_code"] != 0:
                raise Blocked("Failed/incomplete actual verification evidence")
            _binding(evidence, "verification")
            executions.append(_execution(evidence, target_hashes, observation["created_at"]))
            kinds.add(evidence["kind"])
        if not {"counterexample", "normal", "boundary"} <= kinds:
            raise Blocked("Counterexample, normal and boundary checks are required")
        reviewer = _review(receipt, {item["key"]: item["sha256"] for item in receipt["sources"]}, target_hashes, executions)
        receipt = {**receipt, "reviewer": reviewer, "asset_fingerprint": validation["fingerprint"]}
    elif disposition == "duplicate":
        previous = {x["id"]: x for x in _receipts(private)}
        reference = previous.get(receipt.get("duplicate_of"))
        if reference is None or reference.get("schema") != RECEIPT_SCHEMA or reference["disposition"] not in {"strengthen", "new", "duplicate"}:
            raise Blocked("Duplicate needs an existing adjudicated receipt")
        if Counter(item["sha256"] for item in receipt["sources"]) != Counter(item["sha256"] for item in reference["sources"]):
            raise Blocked("Duplicate sources must have the exact same content hash multiset")
    path = contained(private, "receipts/" + receipt["id"] + ".json", must_exist=False)
    value = {**receipt, "recorded_at": now(), "authority": "Evidence binding is not authentication, execution permission or automatic capability promotion."}
    _create(path, value)
    return {"state": "recorded", "disposition": disposition, "receipt_path": str(path),
            "consumed": disposition != "blocked", "sources": len(receipt["sources"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "scan", "record", "status"])
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate" and args.manifest and args.registry and args.root:
            result = validate_assets(args.manifest, args.registry, args.root)
        elif args.command == "scan" and args.policy:
            result = scan_learning(args.policy, args.workspace)
        elif args.command == "record" and args.receipt:
            result = record_receipt(args.receipt, args.workspace, args.manifest, args.registry, args.root)
        elif args.command == "status":
            result = learning_status(args.workspace)
        else:
            raise Blocked("Required command arguments missing")
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (Blocked, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
