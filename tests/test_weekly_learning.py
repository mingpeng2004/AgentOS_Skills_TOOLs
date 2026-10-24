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

    def test_skill_frontmatter_and_links(self):
        source = self.root / "fixture-skill"
        source.mkdir()
        (source / "SKILL.md").write_text("---\nname: fixture-skill\ndescription: fixture\n---\n", encoding="utf-8")
        entry = m.source_entry(source, "project")
        self.assertEqual(entry["name"], "fixture-skill")
        (source / "SKILL.md").write_text("No identity", encoding="utf-8")
        with self.assertRaises(m.Blocked):
            m.source_entry(source, "project")

    def package(self):
        package = self.root / "package"
        m.create(package / "README.md", b"fixture public repository\n")
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
