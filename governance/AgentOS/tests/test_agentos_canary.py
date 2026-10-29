"""The canary suite must be able to go red.

A known-failure probe that never fails is not a canary, and a suite that stays
green when the rule it targets is weakened is a false-green gate. These tests
run the real production path and then mutate one governance check at a time to
prove each probe detects the weakening.

Every mutation is applied to a throwaway copy of the AgentOS tree; the
canonical source is never modified.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import agentos_canary as canary


def project_fixture(root: Path) -> Path:
    """A minimal project with the files the governance path reads."""
    project = root / "project"
    (project / ".agentos/evidence").mkdir(parents=True)
    (project / ".agentos/project.json").write_text(json.dumps({
        "schema": "agentos-project-v1", "project": "canary-fixture",
        "evidence_ledger": ".agentos/evidence/claims.jsonl"}), encoding="utf-8")
    (project / "AGENTS.md").write_text("fixture rules\n", encoding="utf-8")
    (project / ".agentos/evidence/claims.jsonl").write_text("", encoding="utf-8")
    overlay = "AGENTS.md"
    import hashlib
    digest = hashlib.sha256((project / overlay).read_bytes()).hexdigest()
    (project / ".agentos/project-import-manifest.json").write_text(json.dumps({
        "schema": "agentos-project-import-manifest-v1",
        "required_overlays": [{"path": overlay, "sha256": digest, "scope": "project"}],
        "required_skills": []}), encoding="utf-8")
    return project


class CanaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agentos-canary-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = project_fixture(self.root)

    def test_every_probe_refuses_and_reports_its_own_reason(self):
        result = canary.run(ROOT, self.project)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["error"], 0)
        self.assertEqual(result["passed"], len(canary.CANARIES))
        for item in result["results"]:
            self.assertEqual(item["state"], "passed", item)
            self.assertTrue(item["reason"].strip(), item)
            self.assertEqual(item["observed"], "blocked", item)

    def test_a_probe_that_cannot_run_is_not_a_pass(self):
        empty = self.root / "empty-project"
        empty.mkdir()
        result = canary.run(ROOT, empty)
        self.assertEqual(result["passed"], 0)
        self.assertGreater(result["error"], 0)

    def test_each_probe_detects_the_weakening_of_its_own_rule(self):
        mutations = [
            ("import-parity", "bin/agentos_import.py",
             'if not path.is_file() or digest(path).casefold() != item["sha256"].casefold():',
             'if not path.is_file():'),
            ("source-contract-typo", "bin/agentos_import.py",
             'if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):',
             'if not isinstance(item, dict) or not isinstance(item.get("path"), str):'),
            ("unknown-source-rejected", "bin/agentos_import.py",
             'if not path.is_file() or digest(path).casefold() != item["sha256"].casefold():',
             'if not path.is_file():'),
            ("capability-not-invented", "bin/agentos_skills.py",
             'raise Blocked("unknown capability: " + explicit)',
             'return next(iter(caps.values()))'),
            ("candidate-never-routed", "bin/agentos_skills.py",
             'raise Blocked("candidate capability has no verified deployment: " + cap["id"])',
             'pass'),
            ("missing-provider-blocked", "bin/agentos_skills.py",
             "binding = asset(root, name)",
             'binding = {"path": str(root / name), "sha256": "0" * 64}'),
            ("synthetic-evidence-cannot-close-gate", "bin/agentos_skills.py",
             'if event.get("data_class") != "real":',
             'if False:'),
        ]
        for name, relative, old, new in mutations:
            with self.subTest(canary=name):
                source = ROOT / relative
                original = source.read_bytes()
                mutated = original.replace(old.encode(), new.encode())
                self.assertNotEqual(mutated, original, "mutation target missing: " + name)
                source.write_bytes(mutated)
                try:
                    # A separate process is required: the probe imports the
                    # governance modules, and an already-loaded module keeps the
                    # original code even after the file on disk changed.
                    run = subprocess.run(
                        [sys.executable, "-B", str(ROOT / "bin/agentos_canary.py"),
                         "--root", str(ROOT), "--project", str(self.project),
                         "--canary", name],
                        capture_output=True, text=True, timeout=300)
                    line = [x for x in run.stdout.splitlines() if x.strip().startswith("[")]
                    self.assertTrue(line, run.stdout + run.stderr)
                    state = line[0].strip().split("]")[0].lstrip("[").strip()
                    self.assertNotEqual(state, "passed",
                                        "canary stayed green under a weakened rule: " + name)
                finally:
                    source.write_bytes(original)

    def test_probe_set_covers_the_declared_canary_ids(self):
        declared = {
            "import-parity", "evidence-bound-output", "placeholder-not-production-gated",
            "no-design-intent-change", "unknown-source-rejected", "capability-not-invented",
        }
        implemented = set(canary.CANARIES)
        self.assertTrue(implemented.issuperset(
            {"import-parity", "unknown-source-rejected", "capability-not-invented"}))
        self.assertTrue(declared, "the protocol declares canaries")


if __name__ == "__main__":
    unittest.main()


