"""Isolated synthetic asset/learning fixtures; no network or real tool execution."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid
from unittest import mock


MODULE = Path(__file__).resolve().parent.parent / "tools/capability_assets.py"
SPEC = importlib.util.spec_from_file_location("capability_assets", MODULE)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="asset-learning-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.payload = self.root / "payload"
        self.payload.mkdir()
        self.registry = {"schema": "agentos-skill-registry-v1", "capabilities": [{"id": "km-lessons"}, {"id": "meta-router"}]}
        self.write("skills/sample/SKILL.md", "---\nname: sample\ndescription: Synthetic fixture\n---\n")
        self.manifest = {"schema": m.ASSET_SCHEMA, "assets": [self.asset()]}

    def write(self, relative, content, base=None):
        path = (base or self.payload) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def asset(self, **changes):
        relative = "skills/sample/SKILL.md"
        value = {"id": "sample-skill", "name": "sample", "kind": "skill", "version": "1.0.0",
                 "capabilities": ["km-lessons"], "entry": relative, "platforms": ["*"],
                 "dependencies": [], "side_effects": ["none"], "license": "MIT",
                 "provenance": "Synthetic owner-authored fixture", "hashes": {relative: m.sha((self.payload / relative).read_bytes())},
                 "status": "active", "canonical": True, "supersedes": []}
        value.update(changes)
        return value

    def validate(self, manifest=None):
        return m.validate_assets(manifest or self.manifest, self.registry, self.payload)

    def policy(self, path=None, **changes):
        if path is None:
            path = self.write("CLAUDE.md", "Synthetic persistent learning", self.root)
        source = {"id": "client-memory", "path": str(path), "kind": "file"}
        source.update(changes)
        return {"learning_sources": [source]}

    def scan(self, policy=None):
        return m.scan_learning(policy or self.policy(), self.workspace)

    def receipt(self, scan, **changes):
        suffix = uuid.uuid4().hex
        log = self.write("verification-" + suffix + ".log", "Synthetic execution-artifact fixture; not an actual independent review or command receipt.\n", self.root)
        record = scan["records"][0]
        value = {"schema": m.RECEIPT_SCHEMA, "id": "lesson-001", "disposition": "strengthen",
                 "reason": "Synthetic observed counterexample has a scoped reusable correction",
                 "sources": [{field: record[field] for field in ("key", "path", "sha256")}],
                 "observation": scan["observation_path"], "observation_sha256": scan["observation_sha256"],
                 "capabilities": ["km-lessons"], "assets": ["sample-skill"],
                 "targets": [{"path": "skills/sample/SKILL.md", "sha256": next(iter(self.manifest["assets"][0]["hashes"].values()))}],
                 "reviewer": "synthetic-independent-reviewer",
                 "producer": "synthetic-producer",
                 "verification": [{"kind": kind, "path": str(log), "sha256": m.sha(log.read_bytes()), "exit_code": 0}
                                  for kind in ("counterexample", "normal", "boundary")]}
        target_hashes = {item["path"]: item["sha256"] for item in value["targets"]}
        test_source = self.write("synthetic_test_source.py", "# Synthetic test source binding, not executed.\n", self.root)
        execution = {"command": [sys.executable, "-m", "unittest", "synthetic-fixture"], "exit_code": 0,
                     "output_complete": True, "log": {"path": str(log), "sha256": m.sha(log.read_bytes())},
                     "target_hashes": target_hashes, "test_source_hashes": {str(test_source): m.sha(test_source.read_bytes())},
                     "started_at": m.now(), "finished_at": m.now()}
        execution_path = self.write("execution-" + suffix + ".json", m.encoded(execution).decode(), self.root)
        binding = {"path": str(execution_path), "sha256": m.sha(execution_path.read_bytes())}
        for item in value["verification"]:
            item["execution_receipt"] = binding.copy()
        review = {"state": "passed", "producer": value["producer"], "reviewer": value["reviewer"],
                  "source_hashes": {record["key"]: record["sha256"]}, "target_hashes": target_hashes,
                  "verification_receipts": {str(execution_path): binding["sha256"]}}
        review_path = self.write("review-" + suffix + ".json", m.encoded(review).decode(), self.root)
        value["review"] = {"path": str(review_path), "sha256": m.sha(review_path.read_bytes())}
        value.update(changes)
        return value

    def mutate_execution(self, receipt, change):
        binding = receipt["verification"][0]["execution_receipt"]
        execution = m.load(binding["path"])
        change(execution)
        Path(binding["path"]).write_bytes(m.encoded(execution))
        digest = m.sha(Path(binding["path"]).read_bytes())
        for item in receipt["verification"]:
            item["execution_receipt"]["sha256"] = digest

    def mutate_review(self, receipt, change):
        binding = receipt["review"]
        review = m.load(binding["path"])
        change(review)
        Path(binding["path"]).write_bytes(m.encoded(review))
        binding["sha256"] = m.sha(Path(binding["path"]).read_bytes())

    def record(self, receipt):
        return m.record_receipt(receipt, self.workspace, self.manifest, self.registry, self.payload)

    def test_normal_asset_and_empty_registry_boundary(self):
        result = self.validate()
        self.assertEqual(result["state"], "valid")
        self.assertEqual(result["by_kind"], {"skill": 1, "tool": 0})
        with self.assertRaises(m.Blocked):
            self.validate({"schema": m.ASSET_SCHEMA, "assets": []})

    def test_tool_runtime_dependencies_are_declared_not_installed(self):
        path = self.write("tools/sample.py", "# Synthetic tool fixture, not executed.\n")
        tool = self.asset(id="sample-tool", name="sample-tool", kind="tool", status="candidate", canonical=False,
                          entry="tools/sample.py", hashes={"tools/sample.py": m.sha(path.read_bytes())},
                          runtime_dependencies=["numpy", "Pillow", "scipy", "matplotlib"])
        self.manifest["assets"].append(tool)
        result = self.validate()
        self.assertEqual(result["by_kind"], {"skill": 1, "tool": 1})
        for invalid in ("numpy", ["numpy", "NumPy"], [""]):
            tool["runtime_dependencies"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(m.Blocked):
                self.validate()

    def test_duplicate_ids_unknown_capability_and_fields_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["assets"].append(copy.deepcopy(bad["assets"][0]))
        with self.assertRaisesRegex(m.Blocked, "duplicate stable"):
            self.validate(bad)
        for field, value in (("capabilities", ["unknown-capability"]), ("surprise", True), ("version", "")):
            with self.subTest(field=field), self.assertRaises(m.Blocked):
                bad = copy.deepcopy(self.manifest)
                bad["assets"][0][field] = value
                self.validate(bad)

    def test_content_drift_entry_binding_and_portable_paths(self):
        for relative in ("../secret", "/absolute", "C:/secret", "a\\secret", "a/../secret", "a//secret"):
            bad = copy.deepcopy(self.manifest)
            bad["assets"][0]["entry"] = relative
            with self.subTest(relative=relative), self.assertRaises(m.Blocked):
                self.validate(bad)
        (self.payload / "skills/sample/SKILL.md").write_text("Changed", encoding="utf-8")
        with self.assertRaisesRegex(m.Blocked, "hash mismatch"):
            self.validate()

    def test_dependency_and_supersedes_graph_cycles(self):
        for field in ("dependencies", "supersedes"):
            bad = copy.deepcopy(self.manifest)
            first = bad["assets"][0]
            second = self.asset(id="second", status="validated", canonical=False)
            first[field] = ["second"]
            second[field] = ["sample-skill"]
            bad["assets"].append(second)
            with self.subTest(field=field), self.assertRaisesRegex(m.Blocked, "Cyclic"):
                self.validate(bad)
            second[field] = ["missing-asset"]
            with self.assertRaisesRegex(m.Blocked, "Unknown/self"):
                self.validate(bad)

    def test_canonical_overlap_blocked_and_distinct_platforms_allowed(self):
        self.write("skills/second/SKILL.md", "Synthetic alternative")
        second = self.asset(id="sample-other", entry="skills/second/SKILL.md", platforms=["linux"],
                            hashes={"skills/second/SKILL.md": m.sha((self.payload / "skills/second/SKILL.md").read_bytes())})
        bad = copy.deepcopy(self.manifest)
        bad["assets"].append(second)
        with self.assertRaisesRegex(m.Blocked, "Ambiguous canonical"):
            self.validate(bad)
        bad["assets"][0]["platforms"] = ["windows"]
        self.assertEqual(self.validate(bad)["assets"], 2)

    def test_duplicate_active_content_and_unknown_rights(self):
        bad = copy.deepcopy(self.manifest)
        bad["assets"].append(self.asset(id="alias", name="alias"))
        with self.assertRaisesRegex(m.Blocked, "Duplicate active content"):
            self.validate(bad)
        bad = copy.deepcopy(self.manifest)
        bad["assets"][0]["license"] = "unknown"
        with self.assertRaisesRegex(m.Blocked, "rights remain unknown"):
            self.validate(bad)
        bad["assets"][0].update(status="reference_only", canonical=False, entry=None, hashes={})
        self.assertEqual(self.validate(bad)["state"], "valid")

    def test_unavailable_dependency_and_active_superseded_variant_block(self):
        bad = copy.deepcopy(self.manifest)
        bad["assets"].append(self.asset(id="candidate", status="candidate", canonical=False))
        bad["assets"][0]["dependencies"] = ["candidate"]
        with self.assertRaisesRegex(m.Blocked, "unavailable"):
            self.validate(bad)
        bad["assets"][0]["dependencies"] = []
        bad["assets"][1].update(status="active", canonical=True, platforms=["linux"])
        bad["assets"][0]["platforms"] = ["windows"]
        bad["assets"][0]["supersedes"] = ["candidate"]
        # Give the alternative distinct content so the supersedes gate is reached.
        path = self.write("skills/alternate/SKILL.md", "Synthetic newer content")
        bad["assets"][1].update(entry="skills/alternate/SKILL.md", hashes={"skills/alternate/SKILL.md": m.sha(path.read_bytes())})
        with self.assertRaisesRegex(m.Blocked, "still active"):
            self.validate(bad)

    def test_root_and_ancestor_reparse_rejected(self):
        original = m.os.lstat
        unsafe = self.payload / "skills"
        def fake(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if Path(path) == unsafe:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024))
            return info
        with mock.patch.object(m.os, "lstat", side_effect=fake), self.assertRaisesRegex(m.Blocked, "reparse"):
            self.validate()

    def test_observation_never_consumes_unreviewed_learning(self):
        policy = self.policy()
        first = self.scan(policy)
        second = self.scan(policy)
        self.assertTrue(first["records"][0]["changed_since_observation"])
        self.assertFalse(second["records"][0]["changed_since_observation"])
        self.assertTrue(second["records"][0]["pending_adjudication"])
        self.assertEqual(m.learning_status(self.workspace)["adjudicated"], {})

    def test_verified_receipt_consumes_exact_hash_only(self):
        policy = self.policy()
        observed = self.scan(policy)
        result = self.record(self.receipt(observed))
        self.assertTrue(result["consumed"])
        self.assertFalse(self.scan(policy)["records"][0]["pending_adjudication"])
        Path(policy["learning_sources"][0]["path"]).write_text("New learning", encoding="utf-8")
        self.assertTrue(self.scan(policy)["records"][0]["pending_adjudication"])
        with self.assertRaises(FileExistsError):
            self.record(self.receipt(self.scan(policy)))

    def test_blocked_receipt_preserves_pending_and_duplicate_needs_reference(self):
        policy = self.policy()
        observed = self.scan(policy)
        receipt = self.receipt(observed, disposition="blocked")
        self.assertFalse(self.record(receipt)["consumed"])
        self.assertTrue(self.scan(policy)["records"][0]["pending_adjudication"])
        with self.assertRaisesRegex(m.Blocked, "existing adjudicated"):
            self.record(self.receipt(observed, id="duplicate-001", disposition="duplicate", duplicate_of="lesson-001"))
        self.record(self.receipt(observed, id="accepted-001"))
        duplicate = self.receipt(observed, id="duplicate-002", disposition="duplicate", duplicate_of="accepted-001")
        self.assertTrue(self.record(duplicate)["consumed"])

    def test_duplicate_cannot_consume_unrelated_source_or_different_multiplicity(self):
        observed = self.scan()
        self.record(self.receipt(observed, id="accepted"))
        unrelated = self.write("different.md", "Unrelated learning B", self.root)
        second = self.scan(self.policy(unrelated))
        with self.assertRaisesRegex(m.Blocked, "exact same content hash multiset"):
            self.record(self.receipt(second, id="unrelated", disposition="duplicate", duplicate_of="accepted"))
        shared = self.write("same.md", Path(observed["records"][0]["path"]).read_text(encoding="utf-8"), self.root)
        identical = self.scan(self.policy(shared))
        self.assertTrue(self.record(self.receipt(identical, id="identical", disposition="duplicate", duplicate_of="accepted"))["consumed"])
        source = identical["records"][0]
        extra = self.write("same2.md", shared.read_text(encoding="utf-8"), self.root)
        both = self.scan({"learning_sources": [self.policy(shared)["learning_sources"][0],
                                              {"id": "second", "path": str(extra), "kind": "file"}]})
        receipt = self.receipt(both, id="double", disposition="duplicate", duplicate_of="accepted")
        receipt["sources"] = [{field: item[field] for field in ("key", "path", "sha256")} for item in both["records"]]
        with self.assertRaisesRegex(m.Blocked, "multiset"):
            self.record(receipt)
        status = m.learning_status(self.workspace)
        self.assertNotIn(second["records"][0]["sha256"], status["adjudicated"].get(second["records"][0]["key"], []))

    def test_execution_contract_rejects_unstructured_failed_stale_and_drifted_evidence(self):
        observed = self.scan()
        for mutation in ("missing_receipt", "arbitrary_md", "failed", "incomplete", "wrong_log", "wrong_target", "wrong_test", "backward_time", "naive_time", "stale", "future"):
            receipt = self.receipt(observed)
            if mutation == "missing_receipt":
                del receipt["verification"][0]["execution_receipt"]
            elif mutation == "arbitrary_md":
                binding = receipt["verification"][0]["execution_receipt"]
                binding.update(path=receipt["verification"][0]["path"], sha256=receipt["verification"][0]["sha256"])
            else:
                def change(value):
                    if mutation == "failed":
                        value["exit_code"] = 1
                    elif mutation == "incomplete":
                        value["output_complete"] = False
                    elif mutation == "wrong_log":
                        value["log"]["sha256"] = "0" * 64
                    elif mutation == "wrong_target":
                        value["target_hashes"] = {}
                    elif mutation == "wrong_test":
                        key = next(iter(value["test_source_hashes"]))
                        value["test_source_hashes"][key] = "0" * 64
                    elif mutation == "backward_time":
                        value["started_at"] = "2099-01-01T00:00:00+00:00"
                    elif mutation == "naive_time":
                        value["started_at"] = "2020-01-01T00:00:00"
                    elif mutation == "stale":
                        value["started_at"] = value["finished_at"] = "2020-01-01T00:00:00+00:00"
                    else:
                        value["started_at"] = value["finished_at"] = "2099-01-01T00:00:00+00:00"
                self.mutate_execution(receipt, change)
            with self.subTest(mutation=mutation), self.assertRaises((m.Blocked, ValueError)):
                self.record(receipt)
        self.assertEqual(m.learning_status(self.workspace)["adjudicated"], {})

    def test_review_contract_requires_independent_identity_current_sources_and_exact_executions(self):
        observed = self.scan()
        for mutation in ("missing", "same_identity", "padded_identity", "wrong_producer", "wrong_sources", "wrong_targets", "wrong_executions", "failed", "unknown_field"):
            receipt = self.receipt(observed)
            if mutation == "missing":
                del receipt["review"]
            else:
                def change(value):
                    if mutation == "same_identity":
                        value["reviewer"] = receipt["producer"]
                    elif mutation == "padded_identity":
                        value["reviewer"] = "  " + receipt["producer"].upper() + "  "
                    elif mutation == "wrong_producer":
                        value["producer"] = "someone-else"
                    elif mutation == "wrong_sources":
                        value["source_hashes"] = {}
                    elif mutation == "wrong_targets":
                        value["target_hashes"] = {}
                    elif mutation == "wrong_executions":
                        value["verification_receipts"] = {}
                    elif mutation == "failed":
                        value["state"] = "failed"
                    else:
                        value["invented"] = True
                self.mutate_review(receipt, change)
            with self.subTest(mutation=mutation), self.assertRaises(m.Blocked):
                self.record(receipt)

    def test_legacy_receipts_are_preserved_but_do_not_consume_learning(self):
        observed = self.scan()
        legacy = self.receipt(observed)
        legacy["schema"] = "agentos-learning-receipt-v1"
        root = m._private_root(self.workspace)
        m._create(root / "receipts" / "legacy.json", legacy)
        status = m.learning_status(self.workspace)
        self.assertEqual(status["adjudicated"], {})
        self.assertEqual(status["legacy_unvalidated"], [legacy["id"]])
        with self.assertRaisesRegex(m.Blocked, "existing adjudicated"):
            self.record(self.receipt(observed, id="cannot-reference-v1", disposition="duplicate", duplicate_of=legacy["id"]))

    def test_new_gap_stays_proposal_and_unknown_reference_blocks(self):
        observed = self.scan()
        receipt = self.receipt(observed, disposition="new", capabilities=[], proposed_capability={"id": "new-candidate", "reason": "Synthetic blind spot"})
        before = copy.deepcopy(self.registry)
        self.assertTrue(self.record(receipt)["consumed"])
        self.assertEqual(before, self.registry)
        receipt["id"] = "second"
        receipt["capabilities"] = ["new-candidate"]
        with self.assertRaisesRegex(m.Blocked, "auto-promoted"):
            self.record(receipt)

    def test_receipt_requires_all_test_kinds_and_rejects_failed_or_changed_evidence(self):
        observed = self.scan()
        for mutation in ("missing_kind", "failed", "changed", "outside_target", "unknown_asset", "unrelated_capability"):
            receipt = self.receipt(observed)
            if mutation == "missing_kind":
                receipt["verification"].pop()
            elif mutation == "failed":
                receipt["verification"][0]["exit_code"] = 1
            elif mutation == "changed":
                receipt["verification"][0]["sha256"] = "0" * 64
            elif mutation == "outside_target":
                receipt["targets"][0]["path"] = "../outside"
            elif mutation == "unknown_asset":
                receipt["assets"] = ["unknown"]
            else:
                receipt["capabilities"] = ["meta-router"]
            with self.subTest(mutation=mutation), self.assertRaises(m.Blocked):
                self.record(receipt)
        self.assertEqual(m.learning_status(self.workspace)["receipts"], 0)

    def test_changed_or_unobserved_source_cannot_be_consumed(self):
        observed = self.scan()
        receipt = self.receipt(observed)
        receipt["sources"][0]["key"] = "invented:source"
        with self.assertRaisesRegex(m.Blocked, "not bound"):
            self.record(receipt)
        receipt = self.receipt(observed)
        Path(receipt["sources"][0]["path"]).write_text("Changed source", encoding="utf-8")
        with self.assertRaisesRegex(m.Blocked, "Changed/missing"):
            self.record(receipt)

    def test_foreign_observation_and_changed_snapshot_block(self):
        observed = self.scan()
        receipt = self.receipt(observed)
        other = self.root / "other"
        other.mkdir()
        foreign = m.scan_learning(self.policy(), other)
        receipt.update(observation=foreign["observation_path"], observation_sha256=foreign["observation_sha256"])
        with self.assertRaisesRegex(m.Blocked, "outside this workspace"):
            self.record(receipt)
        receipt = self.receipt(observed)
        receipt["observation_sha256"] = "0" * 64
        with self.assertRaisesRegex(m.Blocked, "Changed/missing"):
            self.record(receipt)

    def test_coverage_distinguishes_empty_absent_excluded_and_denied(self):
        empty = self.root / "empty"
        empty.mkdir()
        raw = self.write("sessions/raw.md", "Never ingest raw conversations", self.root)
        policy = {"learning_sources": [
            {"id": "empty", "path": str(empty), "kind": "directory"},
            {"id": "absent", "path": str(self.root / "missing"), "kind": "file", "required": False},
            {"id": "raw", "path": str(raw), "kind": "file"}]}
        report = self.scan(policy)
        self.assertEqual([x["state"] for x in report["coverage"]], ["empty", "absent", "excluded"])
        self.assertFalse(report["complete_within_declared_sources"])
        self.assertEqual(report["records"], [])
        def denied(root, onerror=None, followlinks=False):
            onerror(PermissionError(13, "Synthetic denied", str(root)))
            return iter([])
        with mock.patch.object(m.os, "walk", side_effect=denied):
            report = self.scan({"learning_sources": [policy["learning_sources"][0]]})
        self.assertEqual(report["coverage"][0]["state"], "unreadable_or_excluded")
        self.assertFalse(report["complete_within_declared_sources"])

    def test_limits_are_explicit_and_partial_records_remain_pending(self):
        directory = self.root / "lessons"
        self.write("lessons/a.md", "A", self.root)
        self.write("lessons/b.md", "B", self.root)
        report = self.scan(self.policy(directory, kind="directory", max_files=1))
        self.assertEqual(len(report["records"]), 1)
        self.assertEqual(report["coverage"][0]["state"], "partial")
        self.assertTrue(any(x["state"] == "file_limit_reached" for x in report["coverage"][0]["issues"]))
        self.assertTrue(report["records"][0]["pending_adjudication"])
        oversized = self.write("oversized.md", "12345", self.root)
        report = self.scan(self.policy(oversized, max_bytes=4))
        self.assertFalse(report["records"])
        self.assertFalse(report["complete_within_declared_sources"])

    def test_invalid_policy_raw_jsonl_and_duplicate_source_ids(self):
        with self.assertRaises(m.Blocked):
            self.scan({"learning_sources": [{"id": "bad", "path": "relative", "kind": "file"}]})
        policy = self.policy()
        policy["learning_sources"].append(copy.deepcopy(policy["learning_sources"][0]))
        with self.assertRaisesRegex(m.Blocked, "Duplicate learning"):
            self.scan(policy)
        report = self.scan(self.policy(self.write("raw.jsonl", "{}", self.root)))
        self.assertEqual(report["records"], [])
        self.assertFalse(report["complete_within_declared_sources"])

    def test_duplicate_json_keys_rejected_and_cli_errors_are_bounded(self):
        path = self.write("bad.json", '{"schema":"one","schema":"two"}', self.root)
        with self.assertRaisesRegex(m.Blocked, "Duplicate JSON"):
            m.load(path)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = m.main(["validate", "--workspace", str(self.workspace)])
        self.assertEqual(result, 2)
        self.assertEqual(json.loads(output.getvalue())["state"], "blocked")

    def test_deleted_or_inaccessible_source_is_not_called_empty(self):
        policy = self.policy()
        before = self.scan(policy)
        Path(policy["learning_sources"][0]["path"]).unlink()
        after = self.scan(policy)
        self.assertEqual(after["no_longer_observed"], [before["records"][0]["key"]])
        self.assertEqual(after["coverage"][0]["state"], "absent")
        self.assertEqual(m.learning_status(self.workspace)["adjudicated"], {})


if __name__ == "__main__":
    unittest.main()
