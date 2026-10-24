"""Bounded synthetic runner checks; never run actual AgentOS or network actions."""

import contextlib
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("verify_release", Path(__file__).resolve().parent.parent / "tools/verify_release.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class VerifyReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="verify-release-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / "package"
        self.package.mkdir()
        self.output = self.root / "output"
        self.ps = self.root / "powershell.exe"
        self.ps.write_bytes(b"synthetic path only; never executed")
        self.write("tools/security_check.ps1", b"# synthetic scanner fixture\n")
        self.write("tests/test_example.py", b"# synthetic suite fixture\n")
        self.write("governance/AgentOS/tests/test_agentos_skills.py", b"# synthetic matrix fixture\n")
        for name in m.PS_TESTS:
            self.write("governance/AgentOS/tests/" + name, b"# synthetic suite fixture\n")
        self.commands = []
        self.report_mutation = None
        self.source_mutation = False

    def write(self, name, data):
        path = self.package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def fake_command(self, argv, cwd, output, timeout):
        output.mkdir(parents=True)
        argv = [str(x) for x in argv]
        self.commands.append(argv)
        started = datetime.now(timezone.utc).isoformat()
        if "-Command" in argv:
            stdout = b"5.1.22621.0\n"
        elif "-FilePath" in argv:
            stdout = b"Actual invocation of synthetic scanner\n"
            source = argv[argv.index("-FilePath") + 1]
            project = Path(argv[argv.index("-ProjectRoot") + 1])
            report = {"scanned": source, "total_files": 1, "generated_at": started,
                      "summary": {"critical": 0, "warning": 0, "info": 0, "pass": True}}
            if self.report_mutation:
                self.report_mutation(report)
            reports = project / "reports"
            reports.mkdir()
            (reports / "fixture-security-audit-file.json").write_text(json.dumps(report), encoding="utf-8")
        else:
            script = Path(argv[argv.index("-File") + 1]).name if "-File" in argv else None
            anchors = {
                "Test-AgentOS.ps1": b"AgentOS tests passed: 46 required files, PowerShell parse, boot anchors.\n",
                "Test-AgentOS-Contract.ps1": b"Contract tests passed: 30 checks. Clock and feedback values are synthetic fixtures; no device or user-acceptance evidence.\n",
                "Test-AgentOS-Decision.ps1": b"Decision tests passed: 25 checks. Clock fixtures and feedback are synthetic; no device/user-acceptance evidence.\n",
                "Test-AgentOS-Evidence.ps1": b"AgentOS evidence tests passed: 20 checks. source, hash, duplicate, synthetic, stale, conflict, level and parse gates.\n",
            }
            stdout = anchors.get(script, b"Ran 3 tests in 0.001s\n\nOK\n")
            if self.source_mutation:
                self.write("tools/added-after-snapshot.py", b"# concurrent addition\n")
                self.source_mutation = False
        (output / "stdout.log").write_bytes(stdout)
        (output / "stderr.log").write_bytes(b"")
        result = {"argv": argv, "cwd": str(cwd), "started_at": started,
                  "finished_at": datetime.now(timezone.utc).isoformat(), "exit_code": 0,
                  "state": "finished", "stdout_path": str(output / "stdout.log"),
                  "stderr_path": str(output / "stderr.log"), "stdout_sha256": m._sha(stdout), "stderr_sha256": m._sha(b"")}
        m._json(output / "command.json", result)
        return result

    def run_fake(self, powershell=True):
        with mock.patch.object(m, "_powershell", return_value=self.ps if powershell else None), mock.patch.object(m, "_command", side_effect=self.fake_command):
            return m.run_release(self.package, self.output)

    def test_normal_complete_coverage_and_sanitized_summary(self):
        result = self.run_fake()
        self.assertEqual(result["state"], "passed")
        self.assertEqual(len(result["suites"]), 6)
        self.assertEqual(len(result["security"]), len(result["code_coverage"]))
        self.assertTrue(all(x["state"] == "passed" and x["total_files"] == 1 for x in result["security"]))
        summary = (self.output / "public_summary.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), summary)
        self.assertTrue(json.loads(summary)["log_sha256"])
        scanner_calls = [x for x in self.commands if "-FilePath" in x]
        self.assertTrue(all("-FailOnCritical" in x and "-FailOnWarning" in x for x in scanner_calls))
        self.assertEqual(len({x[x.index("-ProjectRoot") + 1] for x in scanner_calls}), len(scanner_calls))

    def test_dry_run_has_no_output_or_commands(self):
        with mock.patch.object(m, "_command", side_effect=AssertionError("dry-run must not execute")):
            result = m.run_release(self.package, self.output, dry_run=True)
        self.assertEqual(result["state"], "planned")
        self.assertFalse(self.output.exists())

    def test_missing_powershell_is_not_run_not_passed(self):
        result = self.run_fake(False)
        self.assertEqual(result["state"], "incomplete")
        self.assertTrue(all(x["state"] == "not_run" for x in result["security"]))
        self.assertEqual(sum(x["state"] == "not_run" for x in result["suites"]), 4)

    def test_wrong_coverage_source_or_stale_timestamp_fail(self):
        mutations = [lambda x: x.update(total_files=0), lambda x: x.update(scanned=str(self.root / "other.py")),
                     lambda x: x.update(generated_at="2000-01-01T00:00:00+00:00"),
                     lambda x: x["summary"].update(warning=1)]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.output = self.root / ("output-" + str(index))
                self.report_mutation = mutation
                result = self.run_fake()
                self.assertEqual(result["state"], "failed")
                self.assertTrue(all(x["state"] == "failed" for x in result["security"]))

    def test_source_membership_drift_fails(self):
        self.source_mutation = True
        result = self.run_fake()
        self.assertEqual(result["state"], "failed")
        self.assertFalse(result["source_unchanged"])

    def test_output_inside_package_existing_or_relative_refused(self):
        for output in (self.package / "evidence", self.package, self.root, Path("relative")):
            with self.subTest(output=output), self.assertRaises(m.portable.Blocked):
                m.run_release(self.package, output, dry_run=True)

    def test_timeout_records_complete_failure_evidence(self):
        with mock.patch.object(m.subprocess, "run", side_effect=subprocess.TimeoutExpired(["fixture"], 1, output=b"partial", stderr=b"timed out")):
            result = m._command(["fixture"], self.package, self.output, 1)
        self.assertEqual(result["state"], "timeout")
        self.assertIsNone(result["exit_code"])
        self.assertEqual((self.output / "stdout.log").read_bytes(), b"partial")
        self.assertTrue((self.output / "command.json").is_file())

    def test_windows_powershell_does_not_inherit_ps7_module_paths(self):
        inherited = {"SystemRoot": str(self.root / "Windows"), "PSModulePath": "synthetic-ps7-modules", "UNCHANGED": "keep"}
        completed = subprocess.CompletedProcess(["powershell.exe"], 0, b"5.1\n", b"")
        with mock.patch.dict(m.os.environ, inherited, clear=True), mock.patch.object(m.subprocess, "run", return_value=completed) as process:
            m._command([self.ps, "-NoProfile"], self.package, self.output, 1)
            environment = process.call_args.kwargs["env"]
        module_keys = [key for key in environment if key.casefold() == "psmodulepath"]
        self.assertEqual(module_keys, ["PSMODULEPATH"])
        self.assertEqual(environment["PSMODULEPATH"], str(self.root / "Windows/System32/WindowsPowerShell/v1.0/Modules"))
        self.assertNotIn("synthetic-ps7-modules", environment.values())
        self.assertEqual(environment["UNCHANGED"], "keep")

    def test_zero_test_execution_cannot_pass(self):
        fake = self.fake_command
        def zero(argv, cwd, output, timeout):
            result = fake(argv, cwd, output, timeout)
            Path(result["stdout_path"]).write_bytes(b"Ran 0 tests in 0.001s\nOK\n")
            return result
        with mock.patch.object(m, "_powershell", return_value=None), mock.patch.object(m, "_command", side_effect=zero):
            result = m.run_release(self.package, self.output)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["suites"][0]["state"], "failed")

    def test_nonempty_skip_or_zero_powershell_checks_cannot_pass(self):
        for index, text in enumerate([b"skipped; no checks executed\n", b"Contract tests passed: 0 checks. Clock and feedback values are synthetic fixtures; no device or user-acceptance evidence.\n"]):
            with self.subTest(index=index):
                output = self.root / ("ps-skip-" + str(index))
                def command(argv, cwd, folder, timeout):
                    result = self.fake_command(argv, cwd, folder, timeout)
                    Path(result["stdout_path"]).write_bytes(text)
                    return result
                with mock.patch.object(m, "_command", side_effect=command):
                    result = m._suite("Test-AgentOS-Contract.ps1", [self.ps, "-File", self.package / "governance/AgentOS/tests/Test-AgentOS-Contract.ps1"], self.package, output, 1)
                self.assertEqual(result["state"], "failed")

    def test_python_positive_count_without_terminal_ok_cannot_pass(self):
        def command(argv, cwd, folder, timeout):
            result = self.fake_command(argv, cwd, folder, timeout)
            Path(result["stdout_path"]).write_bytes(b"Ran 3 tests in 0.001s\ntruncated before verdict\n")
            return result
        with mock.patch.object(m, "_command", side_effect=command):
            result = m._suite("package-unittest", ["python"], self.package, self.output, 1, True)
        self.assertEqual(result["state"], "failed")

    def test_cli_nonpass_returns_two(self):
        with mock.patch.object(m, "run_release", return_value={"state": "incomplete"}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(["--package", str(self.package), "--output", str(self.output)]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
