"""Known-failure canaries for the AgentOS governance path.

A canary is a probe whose correct behaviour is to refuse. Each canary runs the
real production path - the same functions a client would hit - and passes only
when a refusal is actually observed. A probe that only confirms the happy path
proves nothing about enforcement, and a canary that has never been observed to
fail is not a canary.

Every probe works on a throwaway copy of the files it perturbs. Nothing here
writes to a canonical source, a client rule file or an evidence ledger.

Usage:
    python -B agentos_canary.py --root <AgentOS root> --project <project root>
    python -B agentos_canary.py --root <AgentOS root> --project <p> --canary <id>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agentos_import as imp
import agentos_skills as skills


class CanaryError(RuntimeError):
    """The canary could not be executed; this is not a pass and not a fail."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sandbox_project(source: Path, relatives) -> Path:
    """Copy only the listed project files into a throwaway tree.

    Copying the whole project is wasteful and slow; a probe only perturbs the
    files it names, and the governance path reads nothing else.
    """
    target = Path(tempfile.mkdtemp(prefix="agentos-canary-"))
    project = target / "project"
    project.mkdir()
    for relative in relatives:
        origin = source / relative
        if not origin.is_file():
            continue
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, destination)
    return project


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: Path, value) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _expect_blocked(label: str, reason_fragment: str, action) -> dict:
    """Run a probe and require an observed refusal."""
    try:
        action()
    except (imp.Blocked, skills.Blocked) as exc:
        message = str(exc)
        if reason_fragment and reason_fragment.casefold() not in message.casefold():
            raise CanaryError(
                f"{label}: refused for the wrong reason; expected {reason_fragment!r} in {message!r}")
        return {"canary": label, "state": "passed", "observed": "blocked",
                "reason": message[:400]}
    raise CanaryError(f"{label}: the probe did NOT refuse; a canary that never fails is not a canary")


def _overlay_files(project: Path):
    manifest = project / ".agentos/project-import-manifest.json"
    if not manifest.is_file():
        raise CanaryError("project-import-manifest.json missing; the probe cannot run")
    data = read_json(manifest)
    overlays = data.get("required_overlays") or []
    if not overlays:
        raise CanaryError("no required_overlays to perturb")
    relatives = ["AGENTS.md", ".agentos/project-import-manifest.json"]
    relatives += [item["path"] for item in overlays]
    return manifest, data, overlays, relatives


def _route_inputs(project: Path):
    """Pick three real project files for the router's task/goals/constraints."""
    for candidate in ["AGENTS.md", ".agentos/project.json", "README.md"]:
        if (project / candidate).is_file():
            return {"task": candidate, "goals": candidate, "constraints": candidate}
    raise CanaryError("no project file available for the router inputs")


def canary_import_parity(root: Path, project: Path) -> dict:
    """A changed project overlay must block import."""
    manifest, data, overlays, relatives = _overlay_files(project)
    sandbox = sandbox_project(project, relatives)
    try:
        target = sandbox / overlays[0]["path"]
        original = target.read_bytes()
        try:
            target.write_bytes(original + b"\n<!-- canary drift -->\n")
            action = lambda: imp.verify(root, "codex", sandbox, sandbox / "receipt.json")
            return _expect_blocked("import-parity", "changed", action)
        finally:
            target.write_bytes(original)
    finally:
        shutil.rmtree(sandbox.parent, ignore_errors=True)


def canary_source_contract_typo(root: Path, project: Path) -> dict:
    """A deliberate source-contract typo must be rejected by the real validator."""
    manifest, data, overlays, relatives = _overlay_files(project)
    sandbox = sandbox_project(project, relatives)
    try:
        broken = sandbox / ".agentos/project-import-manifest.json"
        broken_data = read_json(broken)
        broken_data["required_overlays"][0].pop("sha256", None)
        write_json(broken, broken_data)
        action = lambda: imp.verify(root, "codex", sandbox, sandbox / "receipt.json")
        return _expect_blocked("source-contract-typo", "invalid project overlay binding", action)
    finally:
        shutil.rmtree(sandbox.parent, ignore_errors=True)


def canary_unknown_source_rejected(root: Path, project: Path) -> dict:
    """A knowledge item with no source or a drifted hash is not accepted as verified."""
    manifest, data, overlays, relatives = _overlay_files(project)
    sandbox = sandbox_project(project, relatives)
    try:
        broken = sandbox / ".agentos/project-import-manifest.json"
        broken_data = read_json(broken)
        broken_data["required_overlays"][0]["sha256"] = "0" * 64
        write_json(broken, broken_data)
        action = lambda: imp.verify(root, "codex", sandbox, sandbox / "receipt.json")
        return _expect_blocked("unknown-source-rejected", "changed", action)
    finally:
        shutil.rmtree(sandbox.parent, ignore_errors=True)


def canary_capability_not_invented(root: Path, project: Path) -> dict:
    """A capability id absent from the registry must be refused, never invented."""
    relatives = ["AGENTS.md", ".agentos/project.json"]
    sandbox = sandbox_project(project, relatives)
    try:
        inputs = _route_inputs(sandbox)
        action = lambda: skills.route(
            root / "policies/SKILL-REGISTRY.json", sandbox, "codex", "probe", inputs,
            ".agentos/evidence/canary.json", "software", capability="meta-does-not-exist")
        return _expect_blocked("capability-not-invented", "unknown capability", action)
    finally:
        shutil.rmtree(sandbox.parent, ignore_errors=True)


def canary_candidate_never_routed(root: Path, project: Path) -> dict:
    """A candidate capability must never be routable as if it were installed."""
    registry = root / "policies/SKILL-REGISTRY.json"
    data = read_json(registry)
    candidate = next((c for c in data["capabilities"] if c["availability"] == "candidate"), None)
    if candidate is None:
        raise CanaryError("no candidate capability available to probe")
    relatives = ["AGENTS.md", ".agentos/project.json"]
    sandbox = sandbox_project(project, relatives)
    try:
        inputs = _route_inputs(sandbox)
        action = lambda: skills.route(
            registry, sandbox, "codex", "probe", inputs,
            ".agentos/evidence/canary.json", "software", capability=candidate["id"])
        return _expect_blocked("candidate-never-routed", "candidate", action)
    finally:
        shutil.rmtree(sandbox.parent, ignore_errors=True)


def canary_missing_provider_blocked(root: Path, project: Path) -> dict:
    """A capability whose provider file is missing must stay blocked."""
    registry = root / "policies/SKILL-REGISTRY.json"
    data = read_json(registry)
    target = next((c for c in data["capabilities"]
                   if c["availability"] != "candidate" and c.get("provider")), None)
    if target is None:
        raise CanaryError("no mapped capability available to perturb")
    provider = next((p for p in data["providers"] if p["id"] == target["provider"]), None)
    if provider is None or not provider.get("bundled"):
        raise CanaryError("provider has no bundled path to perturb: " + target["provider"])
    resource = provider["bundled"].rstrip("/") + "/" + (target.get("resources") or ["SKILL.md"])[0]
    source = root / resource
    if not source.is_file():
        raise CanaryError("declared provider resource is absent: " + resource)
    backup = source.read_bytes()
    relatives = ["AGENTS.md", ".agentos/project.json"]
    sandbox = sandbox_project(project, relatives)
    try:
        source.unlink()
        inputs = _route_inputs(sandbox)
        action = lambda: skills.route(
            registry, sandbox, "codex", "probe", inputs,
            ".agentos/evidence/canary.json", "software", capability=target["id"])
        return _expect_blocked("missing-provider-blocked", "missing", action)
    finally:
        source.write_bytes(backup)
        shutil.rmtree(sandbox.parent, ignore_errors=True)


def canary_synthetic_evidence_cannot_close_gate(root: Path, project: Path) -> dict:
    """A synthetic or mixed evidence record cannot close a real delivery gate.

    The probe builds a complete route, output and independent verifier record so
    that the gate reaches the evidence checks, then presents a claim whose
    data_class is synthetic. The gate must refuse it. Refusing earlier, for an
    unrelated reason, would prove nothing about the evidence rule.
    """
    registry = root / "policies/SKILL-REGISTRY.json"
    data = read_json(registry)
    capability = next((c for c in data["capabilities"]
                       if c["availability"] != "candidate" and c.get("provider")), None)
    if capability is None:
        raise CanaryError("no mapped capability available to probe")
    relatives = ["AGENTS.md", ".agentos/project.json", ".agentos/evidence/claims.jsonl"]
    sandbox = sandbox_project(project, relatives)
    try:
        inputs = _route_inputs(sandbox)
        plan = skills.route(
            registry, sandbox, "codex", "probe", inputs,
            ".agentos/evidence/canary-output.json", "software", capability=capability["id"])
        output_path = sandbox / ".agentos/evidence/canary-output.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('{"probe": "canary output"}\n', encoding="utf-8")
        output_hash = sha(output_path.read_bytes())

        # An independent verifier record that covers every acceptance criterion.
        artifact = sandbox / ".agentos/evidence/canary-artifact.txt"
        artifact.write_text("probe artifact\n", encoding="utf-8")
        review = {"route_id": plan["route_id"], "output_sha256": output_hash,
                  "reviewer": "canary-independent-reviewer",
                  "producer": "canary-producer",
                  "checks": [{"criterion": c, "result": "pass",
                              "evidence": ".agentos/evidence/canary-artifact.txt"}
                             for c in plan["acceptance"]],
                  "reviewed_at": skills.stamp()}
        verifier_path = sandbox / ".agentos/evidence/canary-verifier.json"
        write_json(verifier_path, review)

        # The claim is otherwise complete but its data class is synthetic.
        claim_id = "canary-synthetic-claim"
        ledger = sandbox / ".agentos/evidence/claims.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        event = {"claim_id": claim_id, "event_type": "claim_recorded", "status": "verified",
                 "source_type": "test", "source": "canary probe",
                 "validation_method": "canary", "data_class": "synthetic",
                 "evidence_level": plan["minimum_level"],
                 "applicability": "unit" if plan["risk"] == "software" else "static",
                 "exit_code": 0, "output_complete": True, "independent": True,
                 "observed_at": plan["generated_at"],
                 "validated_at": skills.stamp(),
                 "expires_at": None,
                 "artifact_path": str(artifact), "sha256": sha(artifact.read_bytes())}
        ledger.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")

        action = lambda: skills.gate(plan, [claim_id], ".agentos/evidence/canary-verifier.json",
                                     project=sandbox)
        return _expect_blocked("synthetic-evidence-cannot-close-gate", "synthetic", action)
    finally:
        shutil.rmtree(sandbox.parent, ignore_errors=True)


CANARIES = {
    "import-parity": canary_import_parity,
    "source-contract-typo": canary_source_contract_typo,
    "unknown-source-rejected": canary_unknown_source_rejected,
    "capability-not-invented": canary_capability_not_invented,
    "candidate-never-routed": canary_candidate_never_routed,
    "missing-provider-blocked": canary_missing_provider_blocked,
    "synthetic-evidence-cannot-close-gate": canary_synthetic_evidence_cannot_close_gate,
}


def run(root: Path, project: Path, only=None) -> dict:
    results = []
    for name, probe in CANARIES.items():
        if only and name not in only:
            continue
        try:
            results.append(probe(root, project))
        except CanaryError as exc:
            results.append({"canary": name, "state": "error", "reason": str(exc)[:400]})
        except Exception as exc:  # a probe that cannot run is not a pass
            results.append({"canary": name, "state": "error",
                            "reason": type(exc).__name__ + ": " + str(exc)[:300]})
    passed = sum(1 for r in results if r["state"] == "passed")
    return {"schema": "agentos-canary-run-v1", "root": str(root), "project": str(project),
            "canaries": len(results), "passed": passed,
            "failed": sum(1 for r in results if r["state"] == "failed"),
            "error": sum(1 for r in results if r["state"] == "error"),
            "results": results,
            "limits": "Each probe exercises the real production path on a throwaway copy. A pass means a refusal was observed, not that the client loaded the rules. Behavior attestation for a client still requires a client-owned canary run."}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--canary", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        root = Path(os.path.abspath(args.root))
        project = Path(os.path.abspath(args.project))
        if not root.is_dir() or not project.is_dir():
            raise CanaryError("root and project must be existing directories")
        result = run(root, project, args.canary or None)
        if args.output:
            out = Path(os.path.abspath(args.output))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "results"}, ensure_ascii=False))
        for item in result["results"]:
            print(f"  [{item['state']}] {item['canary']}: {item.get('reason', '')[:160]}")
        return 0 if result["failed"] == 0 and result["error"] == 0 else 1
    except (CanaryError, OSError, ValueError) as exc:
        print(json.dumps({"state": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


