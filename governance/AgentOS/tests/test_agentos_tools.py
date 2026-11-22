"""Synthetic Tool routing tests; registered tools are never executed."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import agentos_tools as tools


class ToolRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agentos-tools-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "agentos"
        (self.root / ".local").mkdir(parents=True)
        (self.root / "policies").mkdir()
        (self.root / "policies/SKILL-REGISTRY.json").write_text(json.dumps({
            "schema": "agentos-skill-registry-v1", "capabilities": [{"id": "meta-qc-gate"}]}))
        self.assets = Path(self.temp.name) / "assets"
        (self.assets / "tools").mkdir(parents=True)
        entry = self.assets / "tools/check.py"
        entry.write_text("raise RuntimeError('must not be executed')\n")
        entry_hash = hashlib.sha256(entry.read_bytes()).hexdigest()
        self.manifest = self.assets / "capability-assets.json"
        self.manifest.write_text(json.dumps({"schema": "agentos-capability-assets-v1", "assets": [{
            "id": "tool.fixture-check", "name": "Fixture check", "kind": "tool", "version": "1.0.0",
            "capabilities": ["meta-qc-gate"], "entry": "tools/check.py", "platforms": ["*"],
            "dependencies": [], "side_effects": ["none"], "license": "MIT", "provenance": "fixture",
            "hashes": {"tools/check.py": entry_hash}, "status": "active", "canonical": True,
            "supersedes": [], "runtime_dependencies": []}]}))
        self.validator = self.assets / "capability_assets.py"
        # Look for the validator relative to this tree, not at a fixed machine
        # path. A fixed path made these tests skip in every distributed
        # package, so the coverage existed only on the build machine.
        source = None
        probe = ROOT
        for _ in range(4):
            if not probe:
                break
            candidate = probe / "tools" / "capability_assets.py"
            if candidate.is_file():
                source = candidate
                break
            probe = probe.parent
        if source is None:
            self.skipTest("capability_assets validator source is unavailable here")
        shutil.copy2(source, self.validator)
        binding = {"schema": "agentos-host-bindings-v1", "runtime": {"python": {
            "path": sys.executable, "observed_version": "3.14.0"}, "assets": {
                "root": str(self.assets), "manifest": str(self.manifest),
                "manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
                "validator_module": str(self.validator),
                "validator_sha256": hashlib.sha256(self.validator.read_bytes()).hexdigest()}}}
        (self.root / ".local/host-bindings.json").write_text(json.dumps(binding))

    def test_catalog_and_route_resolve_entry_without_execution(self):
        found = tools.catalog(self.root, "meta-qc-gate")
        self.assertEqual(found["state"], "validated_inventory")
        self.assertEqual(len(found["tools"]), 1)
        self.assertEqual(found["tools"][0]["version"], "1.0.0")
        plan = tools.route(self.root, "tool.fixture-check", "meta-qc-gate")
        self.assertEqual(plan["execution_authority"], "not_granted")
        self.assertTrue(Path(plan["tool"]["entry"]).is_file())
        self.assertIn("must not be executed", Path(plan["tool"]["entry"]).read_text())

    def test_stale_governance_tool_projection_blocks(self):
        asset_root = self.assets / "governance"
        (asset_root / "AgentOS").mkdir(parents=True)
        (asset_root / "AgentOS/VERSION").write_text("1.8.2\n")
        (self.root / "VERSION").write_text("1.8.3\n")
        data = json.loads(self.manifest.read_text())
        data["assets"][0]["id"] = "tool.governance.agentos-skills"
        self.manifest.write_text(json.dumps(data))
        bindings = json.loads((self.root / ".local/host-bindings.json").read_text())
        bindings["runtime"]["assets"]["manifest_sha256"] = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        (self.root / ".local/host-bindings.json").write_text(json.dumps(bindings))
        with self.assertRaisesRegex(tools.Blocked, "version mismatch"):
            tools.catalog(self.root)

    def test_asset_manifest_tamper_blocks(self):
        self.manifest.write_text(self.manifest.read_text() + " ")
        with self.assertRaisesRegex(tools.Blocked, "manifest changed"):
            tools.catalog(self.root)

    def test_asset_entry_drift_blocks(self):
        (self.assets / "tools/check.py").write_text("changed\n")
        with self.assertRaisesRegex(tools.Blocked, "integrity validation failed"):
            tools.catalog(self.root)

    def test_unknown_asset_and_wrong_capability_block(self):
        with self.assertRaisesRegex(tools.Blocked, "unknown or ambiguous"):
            tools.route(self.root, "tool.missing")
        with self.assertRaisesRegex(tools.Blocked, "does not declare"):
            tools.route(self.root, "tool.fixture-check", "meta-no-fabrication")

    def test_active_asset_with_missing_entry_is_not_routable(self):
        entry = self.assets / "tools/check.py"
        entry.unlink()
        asset = json.loads(self.manifest.read_text())
        self.manifest.write_text(json.dumps(asset))
        bindings = json.loads((self.root / ".local/host-bindings.json").read_text())
        bindings["runtime"]["assets"]["manifest_sha256"] = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        (self.root / ".local/host-bindings.json").write_text(json.dumps(bindings))
        with self.assertRaisesRegex(tools.Blocked, "Required file missing"):
            tools.route(self.root, "tool.fixture-check", "meta-qc-gate")

    def test_validator_module_drift_blocks(self):
        self.validator.write_text("# changed validator\n")
        with self.assertRaisesRegex(tools.Blocked, "validator changed"):
            tools.catalog(self.root)


if __name__ == "__main__":
    unittest.main()
