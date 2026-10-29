"""Synthetic deployment guards; no real client is started by these tests."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
spec = importlib.util.spec_from_file_location("deploy", ROOT / "bin/agentos_client_deploy.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "source"
        (self.root / "runtime").mkdir(parents=True)
        (self.root / "runtime/managed-client-entry.md").write_text("Load {agentos_root} and preserve evidence.\n")
        self.target = self.base / "client/AGENTS.md"
        self.backup = self.base / "backup"

    def test_create_and_idempotent(self):
        first = tool.deploy_file(self.target, self.root, self.backup)
        second = tool.deploy_file(self.target, self.root, self.backup, first["sha256"])
        self.assertEqual(second["state"], "unchanged")
        self.assertEqual(self.target.read_text().count(tool.BEGIN), 1)

    def test_preserve_user_body_and_backup(self):
        self.target.parent.mkdir()
        original = b"\xef\xbb\xbf# User rules\r\nDo not replace me.\r\n"
        self.target.write_bytes(original)
        receipt = tool.deploy_file(self.target, self.root, self.backup)
        self.assertTrue(self.target.read_bytes().startswith(original))
        self.assertEqual(Path(receipt["backup_path"]).read_bytes(), original)
        self.assertEqual(tool.sha(original), receipt["backup_sha256"])

    def test_refuse_modified_managed_update(self):
        receipt = tool.deploy_file(self.target, self.root, self.backup)
        self.target.write_bytes(self.target.read_bytes() + b"user edit")
        with self.assertRaisesRegex(tool.Blocked, "registered expected"):
            tool.deploy_file(self.target, self.root, self.backup, receipt["sha256"])

    def test_refuse_unregistered_existing_managed_region(self):
        tool.deploy_file(self.target, self.root, self.backup)
        with self.assertRaisesRegex(tool.Blocked, "requires a registered"):
            tool.deploy_file(self.target, self.root, self.backup)

    def test_concurrent_edit_preserved_and_backup_retained(self):
        self.target.parent.mkdir()
        self.target.write_text("original")
        def edit():
            self.target.write_text("concurrent user edit")
        with self.assertRaisesRegex(tool.Blocked, "concurrent"):
            tool.deploy_file(self.target, self.root, self.backup, before_commit=edit)
        self.assertEqual(self.target.read_text(), "concurrent user edit")
        self.assertEqual(len(list(self.backup.glob("*.bak"))), 1)

    def test_source_change_blocks(self):
        def edit():
            (self.root / "runtime/managed-client-entry.md").write_text("changed")
        with self.assertRaisesRegex(tool.Blocked, "canonical entry changed"):
            tool.deploy_file(self.target, self.root, self.backup, before_commit=edit)
        self.assertFalse(self.target.exists())

    def test_rollback_preserves_original(self):
        self.target.parent.mkdir()
        self.target.write_text("user body")
        receipt = tool.deploy_file(self.target, self.root, self.backup)
        tool.rollback_file(receipt)
        self.assertEqual(self.target.read_text(), "user body")

    def test_rollback_refuses_edited_target(self):
        receipt = tool.deploy_file(self.target, self.root, self.backup)
        self.target.write_text("user edit")
        with self.assertRaises(tool.Blocked):
            tool.rollback_file(receipt)
        self.assertEqual(self.target.read_text(), "user edit")

    def test_dry_run_no_writes(self):
        receipt = tool.deploy_file(self.target, self.root, self.backup, dry_run=True)
        self.assertEqual(receipt["state"], "dry_run")
        self.assertFalse(self.target.exists())
        self.assertFalse(self.backup.exists())

    def test_duplicate_marker_rejected(self):
        self.target.parent.mkdir()
        self.target.write_text(tool.BEGIN + tool.BEGIN + tool.END)
        with self.assertRaises(tool.Blocked):
            tool.deploy_file(self.target, self.root, self.backup)

    def bindings_fixture(self, target_name="AGENTS.md"):
        target = self.base / "client" / target_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("original")
        (self.root / "runtime/client-adapters.json").write_text(json.dumps({
            "schema": "agentos-client-adapters-v1", "agentos_version": "test", "adapters": [{
                "id": "fixture", "aliases": [], "skill_roots": [],
                "rule_files": [str(target)], "surfaces": ["project_rules"]}]}))
        bindings = self.base / "host-bindings.json"
        bindings.write_text(json.dumps({"schema": "agentos-host-bindings-v1",
            "clients": {"fixture": {"rule_files": [str(target)], "adapter_files": [
                {"path": str(target), "sha256": tool.sha(target.read_bytes())}]}}}))
        return target, bindings

    def test_bindings_deploy_only_adapter_declared_target(self):
        target, bindings = self.bindings_fixture()
        receipt = tool.deploy_bindings(self.root, bindings, self.backup, client="fixture")
        self.assertEqual(receipt["clients"][0]["adapter_files"][0]["state"], "written")
        self.assertIn(tool.BEGIN, target.read_text())

    def test_bindings_allow_declared_extensionless_plain_text_rule(self):
        target, bindings = self.bindings_fixture("user_rules")
        receipt = tool.deploy_bindings(self.root, bindings, self.backup, client="fixture")
        self.assertEqual(receipt["clients"][0]["adapter_files"][0]["state"], "written")
        self.assertIn(tool.BEGIN, target.read_text())

    def test_bindings_cannot_redirect_write_outside_adapter_surface(self):
        _, bindings = self.bindings_fixture()
        data = json.loads(bindings.read_text())
        other = self.base / "unrelated.md"
        other.write_text("private")
        data["clients"]["fixture"]["rule_files"] = [str(other)]
        bindings.write_text(json.dumps(data))
        with self.assertRaisesRegex(tool.Blocked, "not declared"):
            tool.deploy_bindings(self.root, bindings, self.backup, client="fixture")
        self.assertEqual(other.read_text(), "private")


if __name__ == "__main__":
    unittest.main()
