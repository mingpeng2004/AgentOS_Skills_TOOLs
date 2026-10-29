"""Isolated synthetic fixtures verify failure handling; never network/hardware."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import contextlib
import io

spec = importlib.util.spec_from_file_location("weekly", Path(__file__).resolve().parent.parent / "tools/weekly_learning.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="weekly-learning-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        m.create(self.root / ".local/policy.json", {"repository": m.REPOSITORY, "repository_id": 1432645261,
                 "authorization": {"reference": "synthetic test authorization"}})

    def test_reject_paths_and_credentials(self):
        for path in ["../secret", "/absolute", "a\\b", ".local/state.json", "C:/file"]:
            with self.subTest(path=path), self.assertRaises(m.Blocked):
                m.safe_relative(path)
        secret = ("github" + "_pat_" + "A" * 28).encode()
        with self.assertRaises(m.Blocked):
            m.portable(secret, ".md", {})

    def test_normalize_machine_examples(self):
        original = ("D:" + "\\000_AI\\project\\file.md and " + "192." + "168.2.4").encode()
        value, changed = m.portable(original, ".md", {})
        self.assertTrue(changed)
        self.assertIn(b"${PROJECT_PATH}", value)
        self.assertNotRegex(value.decode(), m.IP)

    def test_changed_source_invalidates(self):
        path = self.root / "input.md"
        path.write_text("before")
        binding = [{"source": str(path), "sha256": m.sha(path.read_bytes())}]
        m.check_sources(binding)
        path.write_text("after")
        with self.assertRaises(m.Blocked):
            m.check_sources(binding)
        with self.assertRaises(m.Blocked):
            m.check_sources([])

    def test_create_only(self):
        path = self.root / "receipt.json"
        m.create(path, {"state": "original"})
        with self.assertRaises(FileExistsError):
            m.create(path, {"state": "overwritten"})
        self.assertEqual(m.load(path)["state"], "original")

    def test_scan_skips_raw_session_directories(self):
        project = self.root / "project"
        project.mkdir()
        (project / "AGENTS.md").write_text("fixture\n", encoding="utf-8")
        sessions = project / "knowledge" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / "request_dump.json").write_text('{"raw": true}\n', encoding="utf-8")
        policy = {"project_roots": [str(project)], "skill_roots": [], "max_directories": 10,
                  "learning_sources": []}
        m.atomic(self.root / ".local/policy.json", policy)

        with contextlib.redirect_stdout(io.StringIO()):
            result = m.scan(self.root)

        self.assertEqual(result["issues"], [])
        self.assertTrue(result["complete_within_declared_roots"])

    def test_skill_frontmatter_and_links(self):
        source = self.root / "fixture-skill"
        source.mkdir()
        (source / "SKILL.md").write_text("---\nname: fixture-skill\ndescription: fixture\n---\n", encoding="utf-8")
        entry = m.source_entry(source, "project")
        self.assertEqual(entry["name"], "fixture-skill")
        (source / "SKILL.md").write_text("No identity", encoding="utf-8")
        with self.assertRaises(m.Blocked):
            m.source_entry(source, "project")

    def test_scan_separates_managed_entry_and_unregistered_skill_from_unreadable(self):
        project = self.root / "project"
        project.mkdir()
        (project / "AGENTS.md").write_text("project rules\n", encoding="utf-8")
        root = self.root / "skill-sources"
        managed = root / "agent-governance-os"
        vendor = root / "vendor-method"
        marker_mention = root / "marker-mention"
        managed.mkdir(parents=True)
        vendor.mkdir()
        marker_mention.mkdir()
        managed_text = "<!-- AGENTOS:BEGIN client-entry-v1 -->\nGovernance entry\n<!-- AGENTOS:END client-entry-v1 -->\n"
        (managed / "SKILL.md").write_text(managed_text, encoding="utf-8")
        (vendor / "SKILL.md").write_text("# Third-party method\n", encoding="utf-8")
        (vendor / "reference.md").write_text("Reference details\n", encoding="utf-8")
        (marker_mention / "SKILL.md").write_text(
            "This document quotes `<!-- AGENTOS:BEGIN client-entry-v1 -->` and "
            "`<!-- AGENTOS:END client-entry-v1 -->` as examples only.\n", encoding="utf-8")
        policy = {"project_roots": [str(project)], "skill_roots": [
            {"path": str(root), "category": "vendor"}], "max_directories": 20,
            "learning_sources": []}
        m.atomic(self.root / ".local/policy.json", policy)

        with contextlib.redirect_stdout(io.StringIO()):
            result = m.scan(self.root)

        by_name = {item["name"]: item for item in result["skills"]}
        self.assertTrue(result["complete_within_declared_roots"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(by_name["managed-client-entry"]["inventory_kind"], "client_entry")
        self.assertEqual(set(by_name["managed-client-entry"]["files"]), {"SKILL.md"})
        self.assertEqual(by_name["vendor-method"]["inventory_kind"], "unregistered_skill")
        self.assertEqual(set(by_name["vendor-method"]["files"]), {"SKILL.md", "reference.md"})
        self.assertEqual(by_name["marker-mention"]["inventory_kind"], "unregistered_skill")

    def test_bounded_large_binary_is_hashed_without_loading_whole_file(self):
        source = self.root / "oversize-skill"
        source.mkdir()
        (source / "SKILL.md").write_text("---\nname: oversize-skill\ndescription: fixture\n---\n", encoding="utf-8")
        binary = source / "showcase.mp4"
        with binary.open("wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)

        entry = m.source_entry(source, "vendor")

        self.assertEqual(entry["files"]["showcase.mp4"], m.sha_file(binary))

    def test_file_over_scan_hash_limit_still_blocks(self):
        source = self.root / "oversize-skill"
        source.mkdir()
        (source / "SKILL.md").write_text("---\nname: oversize-skill\ndescription: fixture\n---\n", encoding="utf-8")
        with (source / "too-large.bin").open("wb") as stream:
            stream.truncate(m.MAX_SKILL_FILE_BYTES + 1)
        with self.assertRaisesRegex(m.Blocked, "Oversize Skill source file"):
            m.source_entry(source, "vendor")

    def test_timestamped_backup_files_are_excluded_from_skill_source(self):
        source = self.root / "fixture-skill"
        source.mkdir()
        (source / "SKILL.md").write_text("---\nname: fixture-skill\ndescription: fixture\n---\n", encoding="utf-8")
        backup = source / "SKILL.md.bak.20261026-121315"
        backup.write_text("private pre-change copy", encoding="utf-8")

        entry = m.source_entry(source, "project")
        exported_paths = {path.relative_to(source).as_posix() for path in m.root_files(source)}

        self.assertEqual(set(entry["files"]), {"SKILL.md"})
        self.assertEqual(exported_paths, {"SKILL.md"})

    def test_portable_agentos_profile_marks_unredistributed_providers_candidate(self):
        package = self.root / "portable"
        agentos = self.root / "canonical-agentos"
        (package / "governance/AgentOS/runtime").mkdir(parents=True)
        (package / "governance/AgentOS/policies").mkdir(parents=True)
        (package / "governance/AgentOS/bin").mkdir(parents=True)
        (package / "governance/AgentOS/skills/public-method").mkdir(parents=True)
        (package / "governance/AgentOS/skills/public-method/SKILL.md").write_text("entry\n")
        (package / "governance/AgentOS/skills/public-method/reference.md").write_text("resource\n")
        (package / "governance/AgentOS/VERSION").write_text("1.8.4\n")
        (package / "governance/AgentOS/bin/agentos.ps1").write_text("included\n")
        (package / "governance/AgentOS/reports").mkdir()
        (agentos / "reports").mkdir(parents=True)
        (agentos / "runtime").mkdir()
        (agentos / "VERSION").write_text("1.8.4\n")
        (agentos / "reports/TOKEN-BUDGET-GOVERNANCE-BRIEF.md").write_text("brief\n")
        (agentos / "runtime/IMPORT-MANIFEST.json").write_text(json.dumps({
            "schema": "agentos-import-manifest-v1", "agentos_version": "1.8.4",
            "required_files": ["bin/agentos.ps1", "skills/private-method/SKILL.md"]
        }))
        (package / "governance/AgentOS/runtime/IMPORT-MANIFEST.json").write_text(
            (agentos / "runtime/IMPORT-MANIFEST.json").read_text())
        registry = {
            "schema": "agentos-skill-registry-v1", "version": "test", "agentos_version": "1.8.4",
            "selection": {}, "providers": [
                {"id": "public", "skill": "public-method", "bundled": "old/path"},
                {"id": "private", "skill": "private-method", "bundled": "skills/private-method"}],
            "capabilities": [
                {"id": "meta-public", "availability": "mapped", "provider": "public", "resources": ["reference.md"], "limits": "original"},
                {"id": "meta-private", "availability": "mapped", "provider": "private", "resources": ["reference.md"], "limits": "original"}]
        }
        (package / "governance/AgentOS/policies/SKILL-REGISTRY.json").write_text(json.dumps(registry))
        catalog = [{"name": "public-method", "state": "exported", "export": "governance/AgentOS/skills/public-method"}]

        result = m.portable_agentos_profile(package, agentos, catalog)

        public = json.loads((package / "governance/AgentOS/policies/SKILL-REGISTRY.json").read_text())
        caps = {item["id"]: item for item in public["capabilities"]}
        self.assertEqual(result["excluded_required_files"], 1)
        self.assertEqual(caps["meta-public"]["availability"], "mapped")
        self.assertEqual(public["providers"][0]["bundled"], "skills/public-method")
        self.assertEqual(caps["meta-private"]["availability"], "candidate")
        self.assertIsNone(caps["meta-private"]["provider"])
        self.assertEqual(caps["meta-private"]["resources"], [])
        manifest = json.loads((package / "governance/AgentOS/runtime/IMPORT-MANIFEST.json").read_text())
        self.assertIn("skills/private-method/SKILL.md", manifest["distribution_profile"]["excluded_required_files"])
        self.assertEqual((package / "governance/AgentOS/tests/test_agentos_skills.py").read_bytes(),
                         (m.WORKSPACE / "tools/templates/portable_agentos_matrix_test.py").read_bytes())

    def package(self):
        package = self.root / "package"
        m.create(package / "README.md", b"fixture public repository\n")
        m.create(package / "evidence/inventory.json", {"scope_complete": True,
                 "learning_coverage_complete": True})
        m.create(package / "governance/AgentOS/VERSION", b"1.4.0\n")
        m.create(package / "catalog.json", {"schema": "governed-skill-catalog-v2", "source_count": 0, "skills": []})
        m.create(package / "governance/AgentOS/policies/SKILL-REGISTRY.json", {"schema": "agentos-skill-registry-v1", "capabilities": [{"id": "fixture-cap"}]})
        m.create(package / "tools/test.py", b"print('fixture')\n")
        m.create(package / "capability-assets.json", {"schema":"agentos-capability-assets-v1", "assets":[{
            "id":"fixture-tool", "name":"fixture", "kind":"tool", "version":"1.0.0", "capabilities":["fixture-cap"],
            "entry":"tools/test.py", "platforms":["*"], "dependencies":[], "side_effects":["synthetic fixture"], "license":"MIT",
            "provenance":"synthetic fixture", "hashes":{"tools/test.py":m.sha((package / "tools/test.py").read_bytes())},
            "status":"active", "canonical":True, "supersedes":[]}]})
        self.seal(package)
        return package

    def seal(self, package):
        import portable_install
        m.atomic(package / "portable-manifest.json", portable_install.build_manifest(package))

    def test_stage_manifest_sealer_emits_complete_install_manifest(self):
        package = self.root / "manifest-sealer"
        m.create(package / "README.md", b"portable fixture\n")

        manifest = m.seal_portable_manifest(package)

        import portable_install
        self.assertIn("README.md", manifest["files"])
        self.assertEqual(portable_install.validate_bundle(package), manifest)

    def test_payload_includes_manifest_declared_files_inside_source_skip_names(self):
        """A staged file under a scan-SKIP directory name must still be published."""
        package = self.root / "payload-skip"
        m.create(package / "README.md", b"portable fixture\n")
        m.create(package / "governance/AgentOS/reports/TOKEN-BUDGET-GOVERNANCE-BRIEF.md",
                 b"token governance brief\n")
        m.create(package / "governance/AgentOS/trace/private.txt", b"must not be staged\n")
        self.seal(package)

        files = m.payload_files(package)

        self.assertIn("governance/AgentOS/reports/TOKEN-BUDGET-GOVERNANCE-BRIEF.md", files)
        self.assertIn("portable-manifest.json", files)

    def test_payload_refuses_bundle_that_contradicts_its_manifest(self):
        package = self.root / "payload-drift"
        m.create(package / "README.md", b"portable fixture\n")
        self.seal(package)
        m.create(package / "unsealed-extra.md", b"added after sealing\n")

        with self.assertRaises(m.Blocked):
            m.validate(package)

    def review_fixture(self, package, review):
        log = self.root / "independent.log"
        if not log.exists():
            log.write_text("synthetic actual test/review fixture")
        evidence = {"path":str(log), "sha256":m.sha(log.read_bytes()), "exit_code":0}
        m.create(review, {"state":"passed", "package_fingerprint":m.fingerprint(package), "reviewer":"fixture-independent", "checks":["synthetic fixture"], "test_evidence":[evidence], "independent_review":evidence})

    def test_validate_leakage_and_inventory(self):
        package = self.package()
        self.assertGreater(m.validate(package)["files"], 0)
        m.create(package / "docs/leak.md", ("C:" + "\\Users\\Person\\secret").encode())
        with self.assertRaises(m.Blocked):
            m.validate(package)

    def test_review_binding_and_stale_readiness(self):
        package = self.package()
        source = self.root / "source.md"
        source.write_text("fixture")
        m.create(package.parent / "source-bindings.json", [{"source": str(source), "sha256": m.sha(source.read_bytes())}])
        test_log = self.root / "test.log"
        test_log.write_text("Actual fixture check output")
        review = {"state": "passed", "package_fingerprint": m.fingerprint(package), "reviewer": "fixture-reviewer",
                  "checks": ["fixture privacy pass"], "independent_review": {"path": str(test_log), "exit_code": 0, "sha256": m.sha(test_log.read_bytes())}, "test_evidence": [{"path": str(test_log), "exit_code": 0, "sha256": m.sha(test_log.read_bytes())}]}
        review_path = self.root / "review.json"
        m.create(review_path, review)
        ready = m.prepare(package, review_path, self.root)
        self.assertEqual(ready["fingerprint"], m.fingerprint(package))
        (package / "README.md").write_text("changed")
        with self.assertRaises(m.Blocked):
            m.publish(package.parent / "ready.json", self.root, api=object())

    def test_incomplete_scan_or_learning_coverage_blocks_release_review(self):
        package = self.package()
        source = self.root / "source.md"
        source.write_text("fixture")

        for field, expected in [
            ("scope_complete", "declared project/Skill scan coverage"),
            ("learning_coverage_complete", "learning-source coverage"),
        ]:
            with self.subTest(field=field):
                inventory_path = package / "evidence/inventory.json"
                inventory = m.load(inventory_path)
                inventory[field] = False
                m.atomic(inventory_path, inventory)
                self.seal(package)
                review_path = self.root / (field + "-review.json")
                self.review_fixture(package, review_path)
                with self.assertRaisesRegex(m.Blocked, expected):
                    m.release_review(package, review_path)
                inventory[field] = True
                m.atomic(inventory_path, inventory)
                self.seal(package)

    def test_publish_readback_preserves_unrelated_and_is_idempotent(self):
        package = self.package()
        for index in range(115):
            m.create(package / ("docs/fixture-" + str(index) + ".md"), b"synthetic bounded tree item\n")
        self.seal(package)
        source = self.root / "source.md"
        source.write_text("fixture")
        bindings = [{"source": str(source), "sha256": m.sha(source.read_bytes())}]
        binding_path = self.root / "sources.json"
        m.create(binding_path, bindings)
        review = self.root / "review.json"
        self.review_fixture(package, review)
        ready = {"schema": "weekly-publication-ready-v2", "target": {"repository": m.REPOSITORY, "repository_id": 1432645261}, "package": str(package), "fingerprint": m.fingerprint(package), "review": str(review),
                 "review_sha256": m.sha(review.read_bytes()), "sources": str(binding_path), "sources_sha256": m.sha(m.encoded(bindings))}
        ready_path = self.root / "ready.json"
        m.create(ready_path, ready)
        api = FakeAPI()
        first = m.publish(ready_path, self.root, api)
        self.assertEqual(first["state"], "published")
        self.assertGreater(api.tree_batches, 1)
        self.assertEqual(api.paths["unrelated.txt"], "keep-original-blob")
        commits = api.commits
        second = m.publish(ready_path, self.root, api)
        self.assertEqual(second["state"], "unchanged")
        self.assertEqual(api.commits, commits)

    def test_remote_conflict_blocks_before_write(self):
        package = self.package()
        api = FakeAPI()
        api.paths["README.md"] = "some-other-human-content"
        source = self.root / "source.md"
        source.write_text("fixture")
        bindings = [{"source": str(source), "sha256": m.sha(source.read_bytes())}]
        binding_path = self.root / "sources.json"
        review = self.root / "review.json"
        m.create(binding_path, bindings)
        self.review_fixture(package, review)
        ready = {"schema": "weekly-publication-ready-v2", "target": {"repository": m.REPOSITORY, "repository_id": 1432645261}, "package": str(package), "fingerprint": m.fingerprint(package), "review": str(review),
                 "review_sha256": m.sha(review.read_bytes()), "sources": str(binding_path), "sources_sha256": m.sha(m.encoded(bindings))}
        path = self.root / "ready.json"
        m.create(path, ready)
        with self.assertRaisesRegex(m.Blocked, "Concurrent/unowned"):
            m.publish(path, self.root, api)
        self.assertEqual(api.commits, 0)

    def test_scan_denied_is_visible_and_prevents_false_complete(self):
        project = self.root / "project"
        project.mkdir()
        (project / "AGENTS.md").write_text("fixture")
        policy = {"project_roots": [str(project)], "skill_roots": [], "max_directories": 10}
        m.atomic(self.root / ".local/policy.json", policy)
        def failed_walk(root, onerror=None, followlinks=False):
            onerror(PermissionError("synthetic denied"))
            return iter([])
        with mock.patch.object(m.os, "walk", side_effect=failed_walk), contextlib.redirect_stdout(io.StringIO()):
            result = m.scan(self.root)
        self.assertFalse(result["complete_within_declared_roots"])
        self.assertEqual(result["issues"][0]["state"], "unreadable")

    def test_scan_ignores_links_inside_declared_excluded_dependency_dirs(self):
        project = self.root / "project"
        project.mkdir()
        (project / "AGENTS.md").write_text("fixture\n", encoding="utf-8")
        policy = {"project_roots": [str(project)], "skill_roots": [], "max_directories": 10,
                  "learning_sources": []}
        m.atomic(self.root / ".local/policy.json", policy)

        def fake_walk(root, onerror=None, followlinks=False):
            yield str(project), ["node_modules", "active-link"], ["AGENTS.md"]

        def fake_is_link(path):
            return Path(path).name in {"node_modules", "active-link"}

        with mock.patch.object(m.os, "walk", side_effect=fake_walk), \
                mock.patch.object(m, "is_link", side_effect=fake_is_link), \
                contextlib.redirect_stdout(io.StringIO()):
            result = m.scan(self.root)

        self.assertFalse(result["complete_within_declared_roots"])
        self.assertEqual([issue["root"] for issue in result["issues"]],
                         [str(project / "active-link")])

    def test_scan_resolves_only_explicit_link_alias_to_scanned_direct_source(self):
        project = self.root / "project"
        project.mkdir()
        (project / "AGENTS.md").write_text("fixture\n", encoding="utf-8")
        source_root = self.root / "canonical-skills"
        source = source_root / "vendor-method"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(
            "---\nname: vendor-method\ndescription: fixture\n---\n", encoding="utf-8")
        alias_path = project / "magpie-skill"
        policy = {"project_roots": [str(project), str(project)], "skill_roots": [
            {"path": str(source_root), "category": "vendor"}], "max_directories": 10,
            "link_aliases": [{"target_prefix": r"C:\Alias\skills",
                              "canonical_root": str(source_root)}],
            "learning_sources": []}
        m.atomic(self.root / ".local/policy.json", policy)

        def fake_walk(root, onerror=None, followlinks=False):
            if Path(root) == project:
                yield str(project), ["magpie-skill", "unmapped-skill"], ["AGENTS.md"]
            else:
                yield str(source_root), ["vendor-method"], []
                yield str(source), [], ["SKILL.md"]

        def fake_is_link(path):
            return Path(path).name in {"magpie-skill", "unmapped-skill"}

        def fake_readlink(path):
            if Path(path) == alias_path:
                return r"C:\Alias\skills\vendor-method"
            raise OSError("not a declared alias")

        with mock.patch.object(m.os, "walk", side_effect=fake_walk), \
                mock.patch.object(m, "is_link", side_effect=fake_is_link), \
                mock.patch.object(m.os, "readlink", side_effect=fake_readlink), \
                contextlib.redirect_stdout(io.StringIO()):
            result = m.scan(self.root)

        self.assertTrue(result["complete_within_declared_roots"] is False)
        self.assertEqual(result["link_aliases"], [{
            "path": str(alias_path), "target": str(source),
            "source_id": m.sha(str(source.resolve()).encode())[:12],
            "state": "linked_alias_verified"}])
        self.assertEqual([issue["root"] for issue in result["issues"]],
                         [str(project / "unmapped-skill")])

    def test_publication_lock_closes_before_cleanup_on_failure(self):
        with mock.patch.object(m, "WORKSPACE", self.root), mock.patch.object(m, "publish", side_effect=m.Blocked("fixture failed")), contextlib.redirect_stdout(io.StringIO()):
            result = m.main(["publish", "--ready", str(self.root / "fixture-ready.json")])
        self.assertEqual(result, 2)
        self.assertFalse((self.root / ".local/publication.lock").exists())

    def test_other_run_lock_never_deleted(self):
        lock = self.root / ".local/publication.lock"
        m.create(lock, b"synthetic-live-owner")
        with mock.patch.object(m, "WORKSPACE", self.root), mock.patch.object(m, "publish") as publish, contextlib.redirect_stdout(io.StringIO()):
            result = m.main(["publish", "--ready", str(self.root / "ready.json")])
        self.assertEqual(result, 2)
        self.assertEqual(lock.read_bytes(), b"synthetic-live-owner")
        publish.assert_not_called()


class FakeAPI:
    """Synthetic GitHub objects; no actual request leaves this test."""
    def __init__(self):
        self.head = "fixture-initial"
        self.paths = {"unrelated.txt": "keep-original-blob"}
        self.staged = None
        self.commits = 0
        self.tree_batches = 0

    def request(self, method, route, body=None, missing=False):
        if route == "":
            return {"id": 1432645261, "full_name": m.REPOSITORY, "default_branch": "main", "permissions": {"push": True}}
        if method == "GET" and route.startswith("/git/ref/"):
            return {"object": {"sha": self.head}}
        if method == "GET" and route.startswith("/git/commits/"):
            return {"tree": {"sha": "fixture-tree"}}
        if method == "GET" and route.startswith("/git/trees/"):
            return {"tree": [{"path": k, "type": "blob", "mode": "100644", "sha": v} for k, v in self.paths.items()]}
        if method == "POST" and route == "/git/trees":
            self.tree_batches += 1
            if len(body["tree"]) > 100:
                raise AssertionError("Unbounded tree upload")
            self.staged = dict(self.staged if self.staged is not None else self.paths)
            for item in body["tree"]:
                if item.get("sha", "present") is None:
                    self.staged.pop(item["path"], None)
                else:
                    self.staged[item["path"]] = m.blob_id(item["content"].encode()) if "content" in item else item["sha"]
            return {"sha": "fixture-next-tree"}
        if method == "POST" and route == "/git/commits":
            self.commits += 1
            return {"sha": "fixture-next-commit"}
        if method == "PATCH":
            if body.get("force") is not False:
                raise AssertionError("Force not permitted")
            self.head = body["sha"]
            self.paths = self.staged
            return {}
        raise AssertionError((method, route))


if __name__ == "__main__":
    unittest.main()
