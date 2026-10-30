"""Isolated path fixtures: no clients, credentials or models are launched."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agentos_paths", ROOT / "bin/agentos_paths.py")
paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)


class PathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agentos-path-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "system"
        self.home = Path(self.temp.name) / "user"
        self.home.mkdir()
        (self.root / "runtime").mkdir(parents=True)
        self.manifest = self.root / "runtime/client-adapters.json"
        self.write_manifest([{"id": "codex", "aliases": ["cx"],
                              "skill_roots": ["${CODEX_HOME}/skills"], "rule_files": ["${CODEX_HOME}/AGENTS.md"], "source": None},
                             {"id": "minimax-code", "aliases": ["minimax"],
                              "skill_roots": ["${USER_HOME}/.minimax/skills"], "source": None}])

    def write_manifest(self, adapters):
        self.manifest.write_text(json.dumps({"adapters": adapters}), encoding="utf-8")

    def test_fixture_user_root_never_reads_host_environment(self):
        with patch.dict(os.environ, {"CODEX_HOME": "Z:/do-not-read", "HERMES_HOME": "Z:/private"}):
            result = paths.client_paths("cx", self.root, user_root=self.home)
        self.assertEqual(result["id"], "codex")
        self.assertEqual(result["skill_roots"], [str(self.home / ".codex/skills")])

    def test_copilot_home_override_is_honored(self):
        custom = Path(self.temp.name) / "copilot-custom"
        self.write_manifest([{"id": "copilot", "skill_roots": [],
                              "rule_files": ["${COPILOT_HOME}/copilot-instructions.md"]}])
        def environment(name):
            return str(custom) if name == "COPILOT_HOME" else None
        with patch.object(paths, "user_home", return_value=self.home), patch.object(
                paths, "user_environment", side_effect=environment):
            result = paths.client_paths("copilot", self.root)
        self.assertEqual(result["required_rule_files"], [str(custom / "copilot-instructions.md")])

    def test_copilot_fixture_root_does_not_read_real_home(self):
        self.write_manifest([{"id": "copilot", "skill_roots": [],
                              "rule_files": ["${COPILOT_HOME}/copilot-instructions.md"]}])
        with patch.dict(os.environ, {"COPILOT_HOME": "Z:/private"}):
            result = paths.client_paths("copilot", self.root, user_root=self.home)
        self.assertEqual(result["rule_files"], [str(self.home / ".copilot/copilot-instructions.md")])

    def test_rule_prefix_cannot_target_an_undeclared_file(self):
        self.write_manifest([{"id": "fixture", "skill_roots": [],
                              "rule_files": ["${USER_HOME}/rules/agentos.md"],
                              "rule_file_prefixes": {"${USER_HOME}/other.md": "frontmatter"}}])
        with self.assertRaisesRegex(paths.PathError, "not a declared"):
            paths.client_paths("fixture", self.root, user_root=self.home)

    def test_rule_prefix_path_is_canonicalized_with_the_rule_target(self):
        template = "${USER_HOME}/.cursor/rules/agentos.mdc"
        prefix = "---\ndescription: governance\nalwaysApply: true\n---\n\n"
        self.write_manifest([{"id": "cursor", "skill_roots": [], "rule_files": [template],
                              "rule_file_prefixes": {template: prefix}}])
        result = paths.client_paths("cursor", self.root, user_root=self.home)
        canonical = str((self.home / ".cursor/rules/agentos.mdc").resolve())
        self.assertEqual(result["required_rule_files"], [canonical])
        self.assertEqual(result["rule_file_prefixes"], {canonical: prefix})

    def test_minimax_rule_surface_is_a_real_file_not_a_client_managed_dir(self):
        manifest = json.loads((ROOT / "runtime/client-adapters.json").read_text(encoding="utf-8-sig"))
        adapter = next(item for item in manifest["adapters"] if item["id"] == "minimax-code")
        self.assertIn(
            "${USER_HOME}/.config/magpie/library/skills/agent-governance-os/SKILL.md",
            adapter["rule_files"],
        )
        # The global MiniMax skills root is a Magpie-owned symlink view of the
        # shared library. It must stay a Skill root, never a required managed
        # rule target, otherwise every private binding looks incomplete.
        self.assertNotIn(
            "${USER_HOME}/.minimax/skills/agent-governance-os/SKILL.md",
            adapter["rule_files"],
        )
        # The Mavis profile skills root is managed by the client, which removes
        # directories it does not know. A managed file placed there does not
        # persist, so it must never be the declared rule surface.
        self.assertNotIn(
            "${USER_HOME}/.minimax/agents/mavis/skills/agent-governance-os/SKILL.md",
            adapter["rule_files"],
        )

    def test_removed_hermes_clients_declare_no_native_surface(self):
        manifest = json.loads((ROOT / "runtime/client-adapters.json").read_text(encoding="utf-8-sig"))
        for client in ["hermes", "hermes-metal-expert", "hermes-ming-systems"]:
            adapter = next(item for item in manifest["adapters"] if item["id"] == client)
            self.assertEqual(adapter["status"], "removed_archived", client)
            self.assertEqual(adapter["skill_roots"], [], client)
            self.assertEqual(adapter["rule_files"], [], client)
            self.assertEqual(adapter["surfaces"], ["portable_fallback"], client)

    def test_install_project_inventory_uses_relocated_stm32_root(self):
        script = (ROOT / "bin/AgentOS.ps1").read_text(encoding="utf-8-sig")
        self.assertIn(r"${PROJECT_PATH}", script)
        self.assertNotIn(r"${PROJECT_PATH}", script)

    def test_registered_ui_client_is_discovered_without_a_file_rule(self):
        self.write_manifest([{"id": "ui-client", "skill_roots": [], "rule_files": [],
                              "source": None, "surfaces": ["portable_fallback"]}])
        (self.root / ".local").mkdir()
        (self.root / ".local/host-bindings.json").write_text(json.dumps({
            "schema": "agentos-host-bindings-v1",
            "clients": {"ui-client": {"rule_files": [], "adapter_files": [], "discovered": True}},
            "shared_skill_roots": []}), encoding="utf-8")
        result = paths.client_paths("ui-client", self.root)
        self.assertTrue(result["discovered"])
        self.assertFalse(result["native_rule_target_present"])

    def test_host_binding_precedes_environment_and_alias(self):
        managed = Path(self.temp.name) / "managed/skills"
        managed.mkdir(parents=True)
        (self.home / ".codex/skills").mkdir(parents=True)
        (self.home / ".codex/AGENTS.md").write_text("rule")
        portable = self.home / ".codex/skills"
        # Bind a declared template to a test-specific managed location without
        # consulting the host's CODEX_HOME or private machine bindings.
        self.write_manifest([{"id": "codex", "aliases": ["cx"],
                              "skill_roots": [str(managed)], "rule_files": [str(self.home / ".codex/AGENTS.md")], "source": None},
                             {"id": "minimax-code", "aliases": ["minimax"],
                              "skill_roots": ["${USER_HOME}/.minimax/skills"], "source": None}])
        (self.root / ".local").mkdir()
        (self.root / ".local/host-bindings.json").write_text(json.dumps({
            "clients": {"codex": {"skill_roots": [str(managed)], "rule_files": []}},
            "shared_skill_roots": []}), encoding="utf-8")
        with patch.object(paths, "user_home", return_value=self.home):
            result = paths.client_paths("cx", self.root)
        self.assertEqual(result["skill_roots"], [str(managed)])
        self.assertTrue(result["discovered"])

    def test_host_binding_outside_declared_roots_rejected(self):
        outside = Path(self.temp.name) / "unrelated/skills"
        (self.root / ".local").mkdir()
        (self.root / ".local/host-bindings.json").write_text(json.dumps({
            "clients": {"codex": {"skill_roots": [str(outside)], "rule_files": []}},
            "shared_skill_roots": []}), encoding="utf-8")
        with patch.object(paths, "user_home", return_value=self.home), patch.object(
                paths, "user_environment", return_value=None):
            with self.assertRaisesRegex(paths.PathError, "outside adapter-declared"):
                paths.client_paths("codex", self.root)

    def test_unreviewed_shared_skill_root_rejected(self):
        shared = Path(self.temp.name) / "shared"
        skill = shared / "fixture-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: fixture-skill\n---\n")
        (self.root / ".local").mkdir()
        (self.root / ".local/host-bindings.json").write_text(json.dumps({
            "schema": "agentos-host-bindings-v1", "clients": {},
            "shared_skill_roots": [str(shared)], "shared_source_verification": []}), encoding="utf-8")
        with self.assertRaisesRegex(paths.PathError, "no reviewed Skill sources"):
            with patch.object(paths, "user_home", return_value=self.home), patch.object(
                    paths, "user_environment", return_value=None):
                paths.client_paths("codex", self.root)

    def test_unknown_and_conflicting_alias_block(self):
        with self.assertRaises(paths.PathError):
            paths.client_paths("missing", self.root, user_root=self.home)
        self.write_manifest([{"id": "one", "aliases": ["same"]},
                             {"id": "two", "aliases": ["same"]}])
        with self.assertRaises(paths.PathError):
            paths.client_paths("same", self.root, user_root=self.home)

    def test_unresolved_or_relative_root_blocks(self):
        for value in ["${UNKNOWN}/skills", "relative/skills"]:
            self.write_manifest([{"id": "fixture", "skill_roots": [value]}])
            with self.subTest(value=value), self.assertRaises(paths.PathError):
                paths.client_paths("fixture", self.root, user_root=self.home)

    def test_absent_client_is_not_discovered(self):
        result = paths.client_paths("minimax", self.root, user_root=self.home)
        self.assertEqual(result["id"], "minimax-code")
        self.assertFalse(result["discovered"])

    def test_declared_root_link_is_resolved_but_nested_link_rejected(self):
        real = Path(self.temp.name) / "real"
        real.mkdir()
        link = self.home / "linked"
        try:
            link.symlink_to(real, target_is_directory=True)
        except OSError:
            self.skipTest("symlink privilege unavailable")
        self.assertEqual(paths.trusted_root(link), real.resolve())
        nested = real / "nested"
        nested.symlink_to(self.home, target_is_directory=True)
        with self.assertRaises(paths.PathError):
            paths.checked_child(real, "nested/file.md", must_exist=False)

    def test_legacy_manifest_still_resolves_codex_fixture(self):
        self.write_manifest([{"id": "codex"}])
        result = paths.client_paths("codex", self.root, user_root=self.home)
        self.assertEqual(result["skill_roots"], [str(self.home / ".codex/skills")])


if __name__ == "__main__":
    unittest.main()
