"""Synthetic contracts: target identity, tree membership, portable privacy and gates."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import distribution as d
import weekly_learning as w

spec = importlib.util.spec_from_file_location("weekly_fixture", Path(__file__).with_name("test_weekly_learning.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class DistributionTests(fixtures.WeeklyTests):
    def ready(self):
        package = self.package()
        source = self.root / "bound.md"
        source.write_text("synthetic source")
        bindings = [{"source": str(source), "sha256": w.sha(source.read_bytes())}]
        bp = self.root / "bound.json"
        w.create(bp, bindings)
        review = self.root / "review.json"
        log = self.root / "check.log"
        log.write_text("synthetic test evidence")
        record = {"path": str(log), "sha256": w.sha(log.read_bytes()), "exit_code": 0}
        w.create(review, {"state":"passed", "reviewer":"synthetic-independent", "checks":["synthetic fixture"], "package_fingerprint":w.fingerprint(package), "test_evidence": [record], "independent_review": record})
        path = self.root / "ready.json"
        w.create(path, {"schema": "weekly-publication-ready-v2", "target": d.target(w.load(self.root / ".local/policy.json")),
            "package": str(package), "fingerprint": w.fingerprint(package), "review": str(review),
            "review_sha256": w.sha(review.read_bytes()), "sources": str(bp), "sources_sha256": w.sha(w.encoded(bindings))})
        return path, package

    def test_ps51_bom_preserved_and_enforced(self):
        result, _ = w.portable("#Requires -Version 5.1\nWrite-Output '测试'\n".encode(), ".ps1", {})
        self.assertTrue(result.startswith(b"\xef\xbb\xbf"))
        package = self.package()
        w.create(package / "tools/bad.ps1", b"#Requires -Version 5.1\n")
        with self.assertRaisesRegex(w.Blocked, "BOM"):
            w.validate(package)

    def test_source_tree_added_deleted_file_invalidates(self):
        tree = self.root / "source"
        tree.mkdir()
        (tree / "original.md").write_text("before")
        binding = [{"kind": "tree", "source": str(tree), "files": d.tree(tree, w.SKIP), "excluded": sorted(w.SKIP)}]
        w.check_sources(binding)
        (tree / "added.md").write_text("new")
        with self.assertRaisesRegex(w.Blocked, "membership"):
            w.check_sources(binding)
        (tree / "added.md").unlink()
        (tree / "original.md").unlink()
        with self.assertRaisesRegex(w.Blocked, "membership"):
            w.check_sources(binding)

    def test_tree_walk_permission_failure_is_not_empty(self):
        def denied(root, **kwargs):
            kwargs["onerror"](PermissionError("synthetic denied"))
            return iter([])
        with mock.patch.object(d.os, "walk", side_effect=denied), self.assertRaises(d.Blocked):
            d.tree(self.root, set())

    def test_repository_identity_and_authorization_required(self):
        for policy in ({}, {"repository": "owner/repo", "repository_id": 1},
                       {"repository": "../repo", "repository_id": 1, "authorization": {"reference": "fixture"}}):
            with self.assertRaises(d.Blocked):
                d.target(policy)
        self.assertNotEqual(d.state_root(self.root, {"repository_id": 1}), d.state_root(self.root, {"repository_id": 2}))

    def test_cross_repository_ready_blocks_before_network(self):
        path, _ = self.ready()
        policy = w.load(self.root / ".local/policy.json")
        policy["repository_id"] = 42
        w.atomic(self.root / ".local/policy.json", policy)
        api = mock.Mock()
        with self.assertRaisesRegex(w.Blocked, "repository identity"):
            w.publish(path, self.root, api)
        api.request.assert_not_called()

    def test_remote_wrong_repository_id_blocks(self):
        path, _ = self.ready()
        api = fixtures.FakeAPI()
        original = api.request
        def request(method, route, *args, **kwargs):
            result = original(method, route, *args, **kwargs)
            if route == "":
                result["id"] = 42
            return result
        api.request = request
        with self.assertRaisesRegex(w.Blocked, "not writable"):
            w.publish(path, self.root, api)
        self.assertEqual(api.commits, 0)

    def test_old_repository_baseline_never_authorizes_overwrite(self):
        path, _ = self.ready()
        api = fixtures.FakeAPI()
        api.paths["README.md"] = "human-content"
        w.create(self.root / ".local/last-publication.json", {"paths": {"README.md": "human-content"}})
        with self.assertRaisesRegex(w.Blocked, "Concurrent/unowned"):
            w.publish(path, self.root, api)

    def test_test_log_changed_invalidates_ready(self):
        path, _ = self.ready()
        (self.root / "check.log").write_text("changed")
        with self.assertRaisesRegex(w.Blocked, "evidence missing or changed"):
            w.publish(path, self.root, mock.Mock())

    def test_retired_managed_only_deleted_and_unrelated_preserved(self):
        path, package = self.ready()
        api = fixtures.FakeAPI()
        api.paths["docs/retired.md"] = "old-managed-blob"
        target = d.target(w.load(self.root / ".local/policy.json"))
        w.create(d.state_root(self.root, target) / "last-publication.json",
                 {"target": target, "paths": {"docs/retired.md": "old-managed-blob"}})
        w.publish(path, self.root, api)
        self.assertNotIn("docs/retired.md", api.paths)
        self.assertIn("unrelated.txt", api.paths)

    def test_retired_human_change_blocks(self):
        path, _ = self.ready()
        api = fixtures.FakeAPI()
        api.paths["docs/retired.md"] = "human-modified"
        target = d.target(w.load(self.root / ".local/policy.json"))
        w.create(d.state_root(self.root, target) / "last-publication.json", {"target": target, "paths": {"docs/retired.md": "old"}})
        with self.assertRaisesRegex(w.Blocked, "Human-modified"):
            w.publish(path, self.root, api)
        self.assertEqual(api.commits, 0)

    def test_public_profile_is_opt_in_and_private_chronology_removed(self):
        public = d.portable_policy("${OWNER_SIGNATURE}\n", "runtime/BOOT.md")
        self.assertIn("${OWNER_SIGNATURE}", public)
        self.assertIn("NOT mandatory defaults", public)
        original = "实测样例（EXAMPLE_HOST，6 次崩溃）：\nprivate actual incident\n### 3.3 next"
        public = d.portable_policy(original, "references/bugcheck-codes.md")
        self.assertNotIn("private actual incident", public)

    def test_legacy_install_command_disabled(self):
        public = d.portable_policy("Set-StrictMode -Version Latest", "bin/AgentOS.ps1")
        self.assertIn("legacy install is disabled", public)

    def test_missing_review_and_manifest_never_publish(self):
        path, package = self.ready()
        api = fixtures.FakeAPI()
        review_path = self.root / "review.json"
        w.atomic(review_path, {"fixture": "not an actual review"})
        ready = w.load(path)
        ready["review_sha256"] = w.sha(review_path.read_bytes())
        w.atomic(path, ready)
        with self.assertRaisesRegex(w.Blocked, "Actual review"):
            w.publish(path, self.root, api)
        self.assertEqual(api.commits, 0)
        (package / "portable-manifest.json").unlink()
        with self.assertRaisesRegex(w.Blocked, "complete portable manifest"):
            w.release_review(package, review_path)

    def test_skill_allowlist_and_real_version_projection(self):
        workspace = self.root / "publisher"
        framework = self.root / "framework"
        framework.mkdir()
        for folder in ["adapters", "bin", "constitution", "policies", "profiles", "protocols", "runtime", "templates", "tests", "skills"]:
            (framework / folder).mkdir()
        (framework / "VERSION").write_text("1.6.0\n")
        (framework / "README.md").write_text("fixture framework")
        w.create(framework / "policies/SKILL-REGISTRY.json", {"schema":"agentos-skill-registry-v1", "providers":[{"id":"engineering", "skill":"embedded-software-engineering"}],
                 "capabilities":[{"id":"meta-qc-gate", "provider":"engineering", "availability":"mapped"}]})
        unauthorized = framework / "skills/vendor-unlicensed"
        unauthorized.mkdir()
        (unauthorized / "SKILL.md").write_text("---\nname: vendor-unlicensed\ndescription: fixture\n---\n")
        authored = self.root / "authored"
        authored.mkdir()
        (authored / "SKILL.md").write_text("---\nname: embedded-software-engineering\ndescription: fixture\nmetadata:\n  version: '1.1.2'\n---\n")
        workspace.mkdir()
        for folder in ["docs", "tools", "tests", "config"]:
            (workspace / folder).mkdir()
        for name in ["README.md", "AGENTS.md", ".gitignore", "LICENSE", "NOTICE.md"]:
            (workspace / name).write_text("fixture\n")
        (workspace / "tools/fixture.py").write_text("print('fixture')\n")
        policy = {"repository":w.REPOSITORY, "repository_id":1432645261, "authorization":{"reference":"synthetic fixture"},
                  "agentos_root":str(framework), "authored_roots":[{"path":str(authored), "license":"MIT"}]}
        w.create(workspace / ".local/policy.json", policy)
        scan = self.root / "scan.json"
        w.create(scan, {"policy_sha256":w.sha(w.encoded(policy)), "skills":[w.source_entry(unauthorized,"project")],
                 "projects":[], "records":[], "issues":[], "complete_within_declared_roots":True})
        package = w.stage(scan,workspace)
        self.assertFalse((package / "governance/AgentOS/skills/vendor-unlicensed/SKILL.md").exists())
        manifest = w.load(package / "capability-assets.json")
        skill = next(x for x in manifest["assets"] if x["id"] == "skill.embedded-software-engineering")
        self.assertEqual(skill["version"], "1.1.2")
        self.assertEqual(skill["capabilities"], ["meta-qc-gate"])
        catalog = w.load(package / "catalog.json")
        vendor = next(x for x in catalog["skills"] if x["name"] == "vendor-unlicensed")
        self.assertEqual(vendor["state"], "reference_only")


if __name__ == "__main__":
    unittest.main()
