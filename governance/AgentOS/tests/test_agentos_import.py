import json
from pathlib import Path
import tempfile
import unittest
import shutil
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))
import agentos_import as tool


def replace_with_link(link_path, target_path):
    """Replace a directory with a real symbolic link to target_path.

    A real link is used rather than a mock so the resolution path under test
    is the one that runs on a real host. If the platform refuses symlinks the
    test is skipped instead of silently passing.
    """
    import os
    if os.name == "nt" and not Path(target_path).is_dir():
        raise unittest.SkipTest("directory symlink target required")
    shutil.rmtree(link_path)
    try:
        os.symlink(str(target_path), str(link_path), target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        raise unittest.SkipTest("symlink unavailable: " + str(exc))


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="agentos-import-"))
        (self.root / "runtime").mkdir()
        (self.root / "VERSION").write_text("test")
        (self.root / "runtime/required.md").write_text("source")
        (self.root / "runtime/managed-client-entry.md").write_text("managed source fixture\n")
        (self.root / "runtime/client-adapters.json").write_text(json.dumps({
            "schema": "agentos-client-adapters-v1", "agentos_version": "test", "adapters": [{"id": "fixture", "version": "test",
            "source": "runtime/managed-client-entry.md", "surfaces": ["project_rules"],
            "skill_roots": [], "rule_files": []}]}))
        (self.root / "runtime/IMPORT-MANIFEST.json").write_text(json.dumps({
            "schema": "agentos-import-manifest-v1", "agentos_version": "test",
            "required_files": ["runtime/required.md", "runtime/client-adapters.json",
                               "runtime/managed-client-entry.md"]}))
        (self.root / "project").mkdir()
        (self.root / "project/AGENTS.md").write_text("project")

    def test_validate_and_receipt_separates_runtime_attestation(self):
        result = tool.validate(self.root)
        self.assertEqual(result["state"], "valid")
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["canonical_files"], "validated")
        self.assertEqual(receipt["states"]["file_parity"], "unknown")
        self.assertEqual(receipt["states"]["import_reported"], "unattested")
        self.assertEqual(receipt["states"]["behavior_attested"], "unattested")

    def test_missing_required_source_blocks(self):
        (self.root / "runtime/required.md").unlink()
        with self.assertRaises(tool.Blocked):
            tool.validate(self.root)

    def test_duplicate_client_blocks(self):
        data = json.loads((self.root / "runtime/client-adapters.json").read_text())
        data["adapters"].append(data["adapters"][0])
        (self.root / "runtime/client-adapters.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(tool.Blocked, "duplicate"):
            tool.validate(self.root)

    def test_receipt_is_create_only(self):
        output = self.root / "receipt.json"
        tool.verify(self.root, "fixture", self.root / "project", output)
        with self.assertRaises(tool.Blocked):
            tool.verify(self.root, "fixture", self.root / "project", output)

    def test_project_overlay_drift_blocks(self):
        overlay = self.root / "project/overlay.md"
        overlay.write_text("overlay")
        manifest = {"schema": "agentos-project-import-manifest-v1", "project_id": "fixture",
                    "required_overlays": [{"path": "overlay.md", "sha256": tool.digest(overlay), "scope": "project"}],
                    "required_skills": ["fixture"], "behavior_canaries": ["fixture-canary"]}
        (self.root / "project/.agentos").mkdir()
        (self.root / "project/.agentos/project-import-manifest.json").write_text(json.dumps(manifest))
        overlay.write_text("changed")
        with self.assertRaisesRegex(tool.Blocked, "overlay"):
            tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")

    def test_empty_and_duplicate_manifest_rejected(self):
        path = self.root / "runtime/IMPORT-MANIFEST.json"
        original = json.loads(path.read_text())
        for entries in [[], ["runtime/required.md", "runtime/required.md"],
                        ["../outside.md"], [str(path.resolve())]]:
            data = dict(original, required_files=entries)
            path.write_text(json.dumps(data))
            with self.subTest(entries=entries), self.assertRaises(tool.Blocked):
                tool.validate(self.root)

    def test_manifest_version_drift_rejected(self):
        (self.root / "VERSION").write_text("changed")
        with self.assertRaises(tool.Blocked):
            tool.validate(self.root)

    def test_client_adapter_manifest_version_drift_rejected(self):
        path = self.root / "runtime/client-adapters.json"
        adapters = json.loads(path.read_text())
        adapters["agentos_version"] = "stale"
        path.write_text(json.dumps(adapters))
        with self.assertRaisesRegex(tool.Blocked, "adapter manifest version"):
            tool.validate(self.root)

    def test_missing_required_skill_is_not_empty_green(self):
        meta = self.root / "project/.agentos"
        meta.mkdir()
        (meta / "project-import-manifest.json").write_text(json.dumps({
            "schema": "agentos-project-import-manifest-v1", "required_overlays": [],
            "required_skills": ["missing-method"]}))
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["missing_skills"], ["missing-method"])
        self.assertEqual(receipt["states"]["file_parity"], "failed")

    def test_overlay_escape_rejected(self):
        meta = self.root / "project/.agentos"
        meta.mkdir()
        outside = self.root / "outside.md"
        outside.write_text("outside")
        (meta / "project-import-manifest.json").write_text(json.dumps({
            "schema": "agentos-project-import-manifest-v1", "required_overlays": [
                {"path": "../outside.md", "sha256": tool.digest(outside)}], "required_skills": []}))
        with self.assertRaises(tool.Blocked):
            tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")

    def test_duplicate_json_fields_rejected(self):
        (self.root / "runtime/IMPORT-MANIFEST.json").write_text('{"schema":"wrong","schema":"agentos-import-manifest-v1"}')
        with self.assertRaises(tool.Blocked):
            tool.validate(self.root)

    def parity_fixture(self, with_frontmatter=False):
        from agentos_client_deploy import deploy_file
        target = self.root / "client"
        target.mkdir()
        rule = target / ("agentos.mdc" if with_frontmatter else "AGENTS.md")
        rule.write_text("project user rule\n")
        prefix = "---\ndescription: AgentOS fixture\nalwaysApply: true\n---\n\n" if with_frontmatter else ""
        formats = {str(rule): prefix} if prefix else {}
        (self.root / "runtime/client-adapters.json").write_text(json.dumps({
            "schema": "agentos-client-adapters-v1", "agentos_version": "test", "adapters": [{
                "id": "fixture", "version": "test", "source": None,
                "surfaces": ["project_rules"], "skill_roots": [str(target / "skills")],
                "rule_files": [str(rule)], "rule_file_prefixes": formats}]}))
        skill = self.root / "skills/fixture-method"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: fixture-method\n---\n")
        (skill / "method.md").write_text("reference content")
        shutil.copytree(skill, target / "skills/fixture-method")
        deploy_binding = deploy_file(rule, self.root, self.root / "backup", prefix=prefix)
        meta = self.root / "project/.agentos"
        meta.mkdir()
        (meta / "project-import-manifest.json").write_text(json.dumps({
            "schema": "agentos-project-import-manifest-v1", "required_overlays": [],
            "required_skills": ["fixture-method"]}))
        (self.root / ".local").mkdir()
        (self.root / ".local/host-bindings.json").write_text(json.dumps({
            "schema": "agentos-host-bindings-v1", "clients": {"fixture": {
                "skill_roots": [str(target / "skills")], "rule_files": [str(rule)],
                "adapter_files": [{"path": str(rule), "sha256": deploy_binding["sha256"],
                    "source_sha256": deploy_binding["source_sha256"],
                    "managed_block_sha256": deploy_binding["managed_block_sha256"],
                    "new_file_prefix": prefix or None,
                    "created": False, "backup_path": deploy_binding["backup_path"],
                    "backup_sha256": deploy_binding["backup_sha256"]}]}}}))
        return target

    def test_real_target_and_complete_skill_tree_parity(self):
        self.parity_fixture()
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["schema"], "agentos-import-receipt-v2")
        self.assertEqual(receipt["states"]["file_parity"], "verified")
        self.assertEqual(receipt["states"]["import_reported"], "unattested")
        self.assertEqual(len(receipt["skill_checks"][0]["files"]), 2)

    def test_reference_drift_and_skill_identity_rejected(self):
        target = self.parity_fixture()
        (target / "skills/fixture-method/method.md").write_text("drift")
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["file_parity"], "failed")
        self.assertIn("fixture-method", receipt["missing_skills"])

    def test_required_skill_skips_linked_candidate_and_uses_direct_profile_copy(self):
        target = self.parity_fixture()
        linked_candidate = target / "skills/fixture-method"
        profile_root = self.root / "profile/skills"
        profile_root.mkdir(parents=True)
        shutil.copytree(self.root / "skills/fixture-method", profile_root / "fixture-method")

        adapters_path = self.root / "runtime/client-adapters.json"
        adapters = json.loads(adapters_path.read_text())
        adapters["adapters"][0]["skill_roots"].append(str(profile_root))
        adapters_path.write_text(json.dumps(adapters))

        bindings_path = self.root / ".local/host-bindings.json"
        bindings = json.loads(bindings_path.read_text())
        bindings["clients"]["fixture"]["skill_roots"].append(str(profile_root))
        bindings_path.write_text(json.dumps(bindings))

        original_linked = tool.linked
        def mark_first_candidate_linked(path):
            return Path(path) == linked_candidate or original_linked(path)

        with mock.patch.object(tool, "linked", side_effect=mark_first_candidate_linked):
            receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")

        self.assertEqual(receipt["states"]["file_parity"], "verified")
        self.assertEqual(receipt["missing_skills"], [])
        self.assertEqual(Path(receipt["skill_checks"][0]["path"]), profile_root / "fixture-method")
        self.assertEqual(receipt["skill_checks"][0]["status"], "verified_files")

    def test_linked_view_of_verified_shared_source_is_accepted(self):
        """A link that resolves to a verified shared source is the same content."""
        target = self.parity_fixture()
        shared = self.root / "shared/skills/fixture-method"
        shutil.copytree(self.root / "skills/fixture-method", shared)

        bindings_path = self.root / ".local/host-bindings.json"
        bindings = json.loads(bindings_path.read_text())
        bindings["shared_skill_roots"] = [str(self.root / "shared/skills")]
        bindings["shared_source_verification"] = [{
            "skill": "fixture-method", "canonical_root": str(shared),
            "file_sha256": tool.skill_tree(shared)}]
        bindings_path.write_text(json.dumps(bindings))

        linked_candidate = target / "skills/fixture-method"
        replace_with_link(linked_candidate, shared)
        self.assertTrue(tool.linked(linked_candidate))
        with mock.patch.object(tool, "skill_tree", wraps=tool.skill_tree):
            receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")

        self.assertEqual(receipt["skill_checks"][0]["status"], "verified_files")
        self.assertEqual(receipt["skill_checks"][0]["availability"], "client_target_verified")
        self.assertEqual(receipt["missing_skills"], [])

    def test_linked_view_of_unverified_source_stays_refused(self):
        """A link that resolves to anything else must not become a target."""
        target = self.parity_fixture()
        elsewhere = self.root / "elsewhere/fixture-method"
        shutil.copytree(self.root / "skills/fixture-method", elsewhere)

        linked_candidate = target / "skills/fixture-method"
        replace_with_link(linked_candidate, elsewhere)
        self.assertTrue(tool.linked(linked_candidate))
        with mock.patch.object(tool, "skill_tree", wraps=tool.skill_tree):
            receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")

        self.assertNotEqual(receipt["skill_checks"][0]["status"], "verified_files")
        self.assertEqual(receipt["skill_checks"][0]["availability"], "canonical_reference_only")

    def test_adapter_drift_rejected(self):
        target = self.parity_fixture()
        (target / "AGENTS.md").write_text("changed user rule")
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["file_parity"], "failed")

    def test_host_subset_cannot_hide_a_required_rule_surface(self):
        target = self.parity_fixture()
        second = target / "SECOND-RULE.md"
        second.write_text("second required rule\n")
        adapters = json.loads((self.root / "runtime/client-adapters.json").read_text())
        adapters["adapters"][0]["rule_files"].append(str(second))
        (self.root / "runtime/client-adapters.json").write_text(json.dumps(adapters))
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["file_parity"], "failed")
        self.assertTrue(any("complete adapter surface" in item["reason"]
                            for item in receipt["client_checks"]))

    def test_host_binding_cannot_redirect_adapter_target(self):
        self.parity_fixture()
        host = json.loads((self.root / ".local/host-bindings.json").read_text())
        host["clients"]["fixture"]["adapter_files"][0]["path"] = str(self.root / "outside.md")
        (self.root / ".local/host-bindings.json").write_text(json.dumps(host))
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["file_parity"], "failed")

    def test_native_rule_frontmatter_is_part_of_verified_deployment(self):
        self.parity_fixture(with_frontmatter=True)
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["file_parity"], "verified")
        adapters = json.loads((self.root / "runtime/client-adapters.json").read_text())
        adapters["adapters"][0]["rule_file_prefixes"][str(self.root / "client/agentos.mdc")] += "tampered"
        (self.root / "runtime/client-adapters.json").write_text(json.dumps(adapters))
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt-2.json")
        self.assertEqual(receipt["states"]["file_parity"], "failed")

    def test_receipt_cannot_replace_source(self):
        with self.assertRaises(tool.Blocked):
            tool.verify(self.root, "fixture", self.root / "project", self.root / "runtime/required.md")
        self.assertEqual((self.root / "runtime/required.md").read_text(), "source")


if __name__ == "__main__":
    unittest.main()

class AttestationTests(unittest.TestCase):
    """A client attestation may promote import/behavior, but only when it is
    bound to the manifest being verified and its evidence is intact.

    The fixture is shared with ImportTests, but the cases are separate so the
    suite does not run the same test twice.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agentos-attestation-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = ImportTests("test_real_target_and_complete_skill_tree_parity")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def parity_fixture(self):
        return self.fixture.parity_fixture()

    def attestation(self, manifest_sha, evidence_path, evidence_sha, state="reported"):
        path = self.root / "project/.agentos/evidence/client-attestation-fixture.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": "agentos-client-attestation-v1", "client": "fixture",
            "state": state, "manifest_sha256": manifest_sha,
            "evidence": [{"path": str(evidence_path), "sha256": evidence_sha}]}), encoding="utf-8")
        return path

    def test_absent_attestation_stays_unattested(self):
        self.parity_fixture()
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["import_reported"], "unattested")
        self.assertEqual(receipt["states"]["behavior_attested"], "unattested")

    def test_bound_attestation_is_honoured(self):
        self.parity_fixture()
        evidence = self.root / "project/.agentos/evidence/witness.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("client reported reading the rules\n", encoding="utf-8")
        manifest_sha = tool.digest(self.root / "runtime/IMPORT-MANIFEST.json")
        self.attestation(manifest_sha, evidence, tool.digest(evidence))
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["import_reported"], "reported")
        self.assertEqual(receipt["states"]["behavior_attested"], "unattested")
        self.assertTrue(receipt["evidence"])

    def test_attestation_for_another_manifest_is_refused(self):
        self.parity_fixture()
        evidence = self.root / "project/.agentos/evidence/witness.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("witness\n", encoding="utf-8")
        self.attestation("0" * 64, evidence, tool.digest(evidence))
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["import_reported"], "unattested")

    def test_attestation_with_tampered_evidence_is_refused(self):
        self.parity_fixture()
        evidence = self.root / "project/.agentos/evidence/witness.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("witness\n", encoding="utf-8")
        manifest_sha = tool.digest(self.root / "runtime/IMPORT-MANIFEST.json")
        self.attestation(manifest_sha, evidence, "1" * 64)
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["import_reported"], "unattested")

    def test_attestation_for_another_client_is_refused(self):
        self.parity_fixture()
        evidence = self.root / "project/.agentos/evidence/witness.txt"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("witness\n", encoding="utf-8")
        manifest_sha = tool.digest(self.root / "runtime/IMPORT-MANIFEST.json")
        path = self.root / "project/.agentos/evidence/client-attestation-fixture.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": "agentos-client-attestation-v1", "client": "someone-else",
            "state": "reported", "manifest_sha256": manifest_sha,
            "evidence": [{"path": str(evidence), "sha256": tool.digest(evidence)}]}), encoding="utf-8")
        receipt = tool.verify(self.root, "fixture", self.root / "project", self.root / "receipt.json")
        self.assertEqual(receipt["states"]["import_reported"], "unattested")
