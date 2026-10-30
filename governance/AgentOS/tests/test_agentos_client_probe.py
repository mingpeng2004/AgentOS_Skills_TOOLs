"""The client probe must separate a client that read the rules from one that guessed.

A probe that a general-purpose model can pass proves nothing. These tests check
that the expected answers are derived from the canonical file at run time, that
a correct answer passes, and that plausible-looking guesses and partial answers
are refused without producing an attestation.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import agentos_client_probe as probe


class ClientProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agentos-client-probe-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)

    def correct_answers(self):
        built = {p["id"]: p for p in probe.build_probe(ROOT)}
        return {
            "import-load-order": built["import-load-order"]["expected_answer"],
            "unknown-never-defaults": ", ".join(built["unknown-never-defaults"]["expected_answer"]),
            "candidate-blocks": built["candidate-blocks"]["expected_answer"],
        }

    def test_expected_answers_are_derived_from_the_canonical_file(self):
        built = {p["id"]: p for p in probe.build_probe(ROOT)}
        source = (ROOT / "runtime/AGENT-IMPORT.md").read_text(encoding="utf-8-sig")
        for item in built.values():
            self.assertIn(item["source_sha256"],
                          [__import__("hashlib").sha256((ROOT / item["source"]).read_bytes()).hexdigest()])
            self.assertTrue(item["expected_answer"], item)
        # The first answer must be a path that appears in the contract.
        self.assertIn("runtime/BOOT.md", source)

    def test_a_correct_answer_passes_and_writes_an_attestation(self):
        answers = self.correct_answers()
        answers["answered_at"] = "20260101-000000"
        path = self.project / "answers.json"
        path.write_text(json.dumps(answers), encoding="utf-8")
        result = probe.grade_and_attest(ROOT, "fixture", answers)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["passed"], len(result["results"]))
        out = probe.write_attestation(ROOT, self.project, "fixture", result,
                                      probe.sha((ROOT / "runtime/IMPORT-MANIFEST.json").read_bytes()),
                                      "20260101-000000")
        self.assertTrue(out.is_file())
        doc = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(doc["state"], "passed")
        self.assertEqual(doc["client"], "fixture")

    def test_guessed_answers_are_refused_and_produce_no_attestation(self):
        guesses = {
            "import-load-order": "AGENTS.md",
            "unknown-never-defaults": "Anything uncertain, missing files, errors",
            "candidate-blocks": "Use it if available, otherwise pick the closest similar capability",
        }
        result = probe.grade_and_attest(ROOT, "fixture", guesses)
        self.assertEqual(result["passed"], 0)
        self.assertGreater(result["failed"], 0)
        with self.assertRaises(probe.ProbeError):
            probe.write_attestation(ROOT, self.project, "fixture", result, "0" * 64, "x")

    def test_a_partial_answer_does_not_produce_an_attestation(self):
        answers = self.correct_answers()
        answers["candidate-blocks"] = "Try it and see what happens"
        answers["answered_at"] = "20260101-000001"
        result = probe.grade_and_attest(ROOT, "fixture", answers)
        self.assertLess(result["passed"], len(result["results"]))
        with self.assertRaises(probe.ProbeError):
            probe.write_attestation(ROOT, self.project, "fixture", result, "0" * 64, "y")

    def test_a_missing_answer_is_unattested_not_failed(self):
        result = probe.grade_and_attest(ROOT, "fixture", {})
        self.assertEqual(result["unattested"], len(result["results"]))
        self.assertEqual(result["failed"], 0)


if __name__ == "__main__":
    unittest.main()
