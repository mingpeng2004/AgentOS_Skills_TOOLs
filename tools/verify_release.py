"""Reproduce release tests and per-file security coverage without network access."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portable_install as portable

EXCLUDED = {".git", ".local", ".agentos", ".agentos-install", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules"}
CODE_EXTENSIONS = {".py", ".ps1", ".js", ".cs"}
PS_TESTS = ["Test-AgentOS.ps1", "Test-AgentOS-Contract.ps1", "Test-AgentOS-Decision.ps1", "Test-AgentOS-Evidence.ps1"]
PS_SUCCESS = {
    "Test-AgentOS.ps1": r"(?m)^AgentOS tests passed: (\d+) required files, PowerShell parse, boot anchors\.\s*$",
    "Test-AgentOS-Contract.ps1": r"(?m)^Contract tests passed: (\d+) checks\. Clock and feedback values are synthetic fixtures; no device or user-acceptance evidence\.\s*$",
    "Test-AgentOS-Decision.ps1": r"(?m)^Decision tests passed: (\d+) checks\. Clock fixtures and feedback are synthetic; no device/user-acceptance evidence\.\s*$",
    "Test-AgentOS-Evidence.ps1": r"(?m)^AgentOS evidence tests passed: (\d+) checks\. source, hash, duplicate, synthetic, stale, conflict, level and parse gates\.\s*$",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _snapshot(package):
    package = portable._check_path(package)
    if not package.is_dir():
        raise portable.Blocked("Package directory missing")
    result = {}
    def error(exc):
        raise portable.Blocked("Release source unreadable") from exc
    for base, dirs, files in os.walk(package, followlinks=False, onerror=error):
        dirs[:] = sorted(name for name in dirs if name.casefold() not in EXCLUDED)
        for name in dirs + files:
            portable._check_path(Path(base) / name)
        for name in sorted(files):
            path = Path(base) / name
            result[path.relative_to(package).as_posix()] = _sha(path.read_bytes())
    if not result:
        raise portable.Blocked("Empty release source cannot pass")
    return result


def _powershell():
    if os.name != "nt":
        return None
    windows = os.environ.get("SystemRoot", r"C:\Windows")
    path = Path(windows) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return portable._check_path(path) if path.is_file() else None


def _command(argv, cwd, output, timeout):
    output.mkdir(parents=True)
    started = _now()
    state, code = "finished", None
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    if Path(str(argv[0])).name.casefold() == "powershell.exe":
        # PS7's inherited module paths can break Windows PowerShell 5.1 cmdlets.
        environment = {key: value for key, value in environment.items() if key.casefold() != "psmodulepath"}
        windows = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT") or r"C:\Windows"
        environment["PSMODULEPATH"] = str(Path(windows) / "System32/WindowsPowerShell/v1.0/Modules")
    try:
        process = subprocess.run([str(x) for x in argv], cwd=str(cwd), capture_output=True,
                                 timeout=timeout, env=environment)
        stdout, stderr, code = process.stdout, process.stderr, process.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, state = exc.stdout or b"", exc.stderr or b"", "timeout"
    except OSError as exc:
        stdout, stderr, state = b"", str(exc).encode("utf-8"), "failed"
    (output / "stdout.log").write_bytes(stdout)
    (output / "stderr.log").write_bytes(stderr)
    result = {"argv": [str(x) for x in argv], "cwd": str(cwd), "started_at": started,
              "finished_at": _now(), "exit_code": code, "state": state,
              "stdout_sha256": _sha(stdout), "stderr_sha256": _sha(stderr),
              "stdout_path": str(output / "stdout.log"), "stderr_path": str(output / "stderr.log")}
    _json(output / "command.json", result)
    return result


def _output(command):
    return (Path(command["stdout_path"]).read_bytes() + b"\n" + Path(command["stderr_path"]).read_bytes()).decode("utf-8", errors="replace")


def _suite(name, argv, package, output, timeout, python=False):
    command = _command(argv, package, output, timeout)
    text = _output(command)
    count = re.search(r"Ran\s+(\d+)\s+tests?\b", text) if python else re.search(PS_SUCCESS.get(name, r"(?!)"), text)
    success = command["state"] == "finished" and command["exit_code"] == 0 and bool(text.strip())
    if python:
        terminal = re.search(r"(?m)^OK(?: \((?:skipped=\d+|expected failures=\d+)(?:, (?:skipped=\d+|expected failures=\d+))*\))?\s*\Z", text)
        success = success and terminal is not None
    success = success and count is not None and int(count[1]) > 0
    return {"suite": name, "state": "passed" if success else "failed", "command": command,
            "observed_test_count": int(count[1]) if count else None}


def _verify_installer_receipt(receipt_path, package, output):
    """Check the external receipt that proves the installer gates passed.

    The installer confidentiality gates live in the AgentOS source tree, which
    is not part of the published package. Their result therefore arrives as a
    receipt. A receipt is honoured only when it names the suite that ran, the
    package content it was run against, and the exit status of that run.
    """
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt is unreadable: " + str(exc)}
    if receipt.get("schema") != "agentos-installer-gate-receipt-v1":
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Unsupported installer gate receipt schema"}
    if receipt.get("state") != "passed":
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate suite did not pass: " + str(receipt.get("reason", ""))}
    if receipt.get("exit_code") != 0:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate suite exit code is not zero"}
    observed = receipt.get("observed_test_count")
    if not isinstance(observed, int) or observed <= 0:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt claims no tests"}
    # The receipt must be bound to the AgentOS content that is shipping.
    agentos = package / "governance" / "AgentOS"
    bound = receipt.get("agentos_sha256") or {}
    if not isinstance(bound, dict) or not bound:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt is not bound to the shipped AgentOS content"}
    mismatched = []
    for relative, digest in bound.items():
        target = agentos / relative
        if not target.is_file() or _sha(target.read_bytes()) != digest:
            mismatched.append(relative)
    if mismatched:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt does not cover the shipped content: "
                          ", ".join(sorted(mismatched)[:6])}
    # The receipt must also say which bytes were actually tested. A receipt
    # that names only the shipped content asserts coverage it cannot show.
    tested = receipt.get("tested_against_sha256")
    if not isinstance(tested, dict) or not tested:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt does not name the content it was tested against"}
    # The tested set must cover the same files as the shipped set, and every
    # named file must exist in the package. Otherwise the receipt is naming
    # files that were never part of what ships.
    if set(tested) != set(bound):
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt tested and shipped file sets differ"}
    absent = [relative for relative in tested
              if not (agentos / relative).is_file()]
    if absent:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt names files that are not in the package: "
                          + ", ".join(sorted(absent)[:6])}
    # The test count must be backed by the named tests. A count that is only
    # a positive integer is a number, not evidence.
    executed = receipt.get("executed_tests")
    if not isinstance(executed, list) or not executed:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt names no executed test"}
    # unittest counts every test it ran, including the ones a fixture
    # skipped; the receipt names the ones that actually executed. The named
    # set must therefore fit inside the reported count, not match it.
    if len(executed) > observed:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt names more tests than it reports"}
    # The named tests must be the tests that ran. The receipt is produced by
    # the code that runs the suite, so a hand-edited receipt could keep the
    # load-bearing name and drop the rest, and the gate would not notice.
    # The count of executed tests is therefore cross-checked against the
    # count the suite reported, and the receipt's own count field -- which
    # nothing else reads -- must agree with the list beside it.
    declared_count = receipt.get("executed_test_count")
    if declared_count is not None and declared_count != len(executed):
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt counts %s executed tests but names %s"
                          % (declared_count, len(executed))}
    if len(executed) < 2:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt names only the load-bearing test; "
                          "the gate cannot show that the suite actually ran"}
    if not any("runtime_gate_rejects_a_tainted_payload" in str(name) for name in executed):
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt does not name the load-bearing test"}
    # A file whose shipped bytes differ from the tested bytes is proven only
    # for the tested form. The DIFFERENCE must therefore be declared: an
    # unexplained difference means the suite ran against content that is not
    # what ships, and the receipt must not let a reader infer coverage it does
    # not have.
    normalisation = receipt.get("normalisation")
    if not isinstance(normalisation, dict):
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt declares no normalisation for differing files"}
    differing = sorted(relative for relative, digest in tested.items()
                       if bound.get(relative) != digest)
    undeclared = [relative for relative in differing
                  if not normalisation.get(relative)
                  or str(normalisation[relative]).startswith("UNEXPLAINED")]
    if undeclared:
        return {"suite": "installer-gate-receipt", "state": "failed",
                "reason": "Installer gate receipt does not explain why these files differ: "
                          + ", ".join(undeclared[:6])}
    return {"suite": "installer-gate-receipt", "state": "passed",
            "observed_test_count": observed,
            "receipt": str(receipt_path)}


def _publisher_confidentiality_gate(package, agentos_root, output, timeout):
    """Run the publisher's own confidentiality gate against this package.

    The publisher refuses a package that carries a declared local-only file,
    a declared digest, or a confidential identifier. That refusal lived in
    the `stage` step, so the release gate relied on a receipt produced
    elsewhere instead of running the gate itself. This runs it in-process
    against the exact package being released.

    The confidential term list stays on the owner's machine and is read from
    the governance root. It never travels and never enters the package.
    """
    if agentos_root is None:
        return {"suite": "publisher-confidentiality-gate", "state": "failed",
                "reason": "No governance root was given; the publisher gate cannot be run."}
    root = Path(agentos_root)
    if not root.is_dir():
        return {"suite": "publisher-confidentiality-gate", "state": "failed",
                "reason": "Governance root is absent: " + str(root)}
    # The gate must run the code that is IN the package, not the publisher
    # that happens to be on this machine. Otherwise the release proves the
    # local tool, not the shipped one.
    shipped = package / "tools" / "weekly_learning.py"
    if not shipped.is_file():
        return {"suite": "publisher-confidentiality-gate", "state": "failed",
                "reason": "The package does not carry the publisher."}
    record = {"suite": "publisher-confidentiality-gate"}
    # The gate is run as a small script file rather than an inline -c string:
    # a multi-line -c program is quoted through two shells and loses its
    # newlines, which turns a refusal message into a syntax error and hides
    # the reason the package was refused.
    # The gate's command output lives in its own directory, and the runner
    # script must not sit in the directory _command creates: creating the
    # same directory twice is a refused operation on Windows.
    runner = output / "publisher-confidentiality-gate" / "run-gate.py"
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_text(
        "import importlib.util, json, sys\n"
        "spec = importlib.util.spec_from_file_location('weekly', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "try:\n"
        "    print(json.dumps(module.validate(sys.argv[2], sys.argv[3]), sort_keys=True))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'state': 'refused', 'reason': str(exc)}, sort_keys=True))\n"
        "    sys.exit(2)\n",
        encoding="utf-8")
    command = [sys.executable, "-B", str(runner), str(shipped), str(package), str(root)]
    result = _command(command, package, output / "publisher-confidentiality-gate" / "command", timeout)
    record["command"] = result
    output_text = _output(result)
    if result["state"] != "finished" or result["exit_code"] != 0:
        reason = ""
        for line in reversed(output_text.strip().splitlines()):
            try:
                reason = json.loads(line).get("reason", "")
            except (ValueError, AttributeError):
                continue
            if reason:
                break
        record.update(state="failed",
                      reason="The publisher gate refused the package: "
                             + (reason or output_text[-400:]))
        return record
    try:
        record["validation"] = json.loads(output_text.strip().splitlines()[-1])
    except (ValueError, IndexError):
        record.update(state="failed", reason="The publisher gate produced no verdict.")
        return record
    record["state"] = "passed"
    return record


def _verify_report(directory, source, command):
    reports = sorted((directory / "reports").glob("*-security-audit-*.json"))
    if len(reports) != 1:
        raise portable.Blocked("Scanner did not produce exactly one current report")
    report_path = reports[0]
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    generated = datetime.fromisoformat(report["generated_at"].replace("Z", "+00:00"))
    started = datetime.fromisoformat(command["started_at"])
    finished = datetime.fromisoformat(command["finished_at"])
    if generated.tzinfo is None or not started - timedelta(seconds=2) <= generated <= finished + timedelta(seconds=2):
        raise portable.Blocked("Scanner report timestamp is stale/invalid")
    summary = report["summary"]
    if (type(report.get("total_files")) is not int or report["total_files"] != 1
            or summary.get("critical") != 0 or summary.get("warning") != 0 or summary.get("pass") is not True):
        raise portable.Blocked("Scanner coverage/findings failed")
    if os.path.normcase(os.path.abspath(report["scanned"])) != os.path.normcase(str(source)):
        raise portable.Blocked("Scanner reported a different source path")
    return {"report_sha256": _sha(report_path.read_bytes()), "total_files": 1,
            "critical": 0, "warning": 0, "generated_at": report["generated_at"]}


def run_release(package, output, security_check=None, dry_run=False, timeout=300,
                agentos_root=None):
    package, output = portable._check_path(package), portable._check_path(output)
    if package == output or package in output.parents or output in package.parents:
        raise portable.Blocked("Evidence output must be outside the package")
    if output.exists() or not output.parent.is_dir():
        raise portable.Blocked("Evidence output must be a new directory with an existing parent")
    if type(timeout) is not int or timeout <= 0:
        raise portable.Blocked("Timeout must be a positive number of seconds")
    sources = _snapshot(package)
    code = {name: value for name, value in sources.items() if Path(name).suffix.lower() in CODE_EXTENSIONS}
    if not code:
        raise portable.Blocked("No code files were found; zero coverage cannot pass")
    # Every shipped file is scanned, not only the ones whose extension looks
    # like code. The scanner looks for malicious-code patterns, and a file
    # named .md or .json is just as capable of carrying one. Limiting the scan
    # to a self-defined subset made "coverage_complete" answer its own
    # question instead of the real one.
    scan_targets = dict(sources)
    scanner = portable._check_path(security_check) if security_check else package / "tools/security_check.ps1"
    powershell = _powershell()
    suite_names = ["package-unittest", "agentos-skills-unittest",
                   "publisher-confidentiality-gate", *PS_TESTS]
    if dry_run:
        return {"state": "planned", "suites": suite_names, "code_files": len(code), "source_files": len(sources),
                "powershell": "available_unverified" if powershell else "not_run", "scanner": "available" if scanner.is_file() else "not_run",
                "limits": "Dry run only; no tests, scanner, installation or output writes occurred."}
    output.mkdir()
    run = {"schema": "agentos-release-verification-v1", "started_at": _now(), "state": "running",
           "package": str(package), "sources": sources, "code_coverage": code, "suites": [], "security": [], "commands": []}
    _json(output / "run.json", run)
    try:
        tests = package / "tests"
        if tests.is_dir():
            run["suites"].append(_suite("package-unittest", [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(tests), "-v"], package, output / "tests/package", timeout, True))
        else:
            run["suites"].append({"suite": "package-unittest", "state": "failed", "reason": "Required test directory missing"})
        agent_tests = package / "governance/AgentOS/tests"
        if (agent_tests / "test_agentos_skills.py").is_file():
            run["suites"].append(_suite("agentos-skills-unittest", [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(agent_tests), "-p", "test_agentos_skills.py", "-v"], package, output / "tests/agentos-skills", timeout, True))
        else:
            run["suites"].append({"suite": "agentos-skills-unittest", "state": "failed", "reason": "Required matrix test missing"})
        # Run the WHOLE shipped AgentOS test tree against the package. A test
        # that ships and never runs is a test that proves nothing, and a test
        # that ships broken is worse than no test: it reports a failure nobody
        # sees until a consumer runs it.
        if agent_tests.is_dir():
            run["suites"].append(_suite("agentos-package-unittest", [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(agent_tests), "-p", "test_*.py", "-v"], package, output / "tests/agentos-package", timeout, True))
        else:
            run["suites"].append({"suite": "agentos-package-unittest", "state": "failed", "reason": "Shipped AgentOS test tree is missing"})
        # The installer channels are a distribution surface of their own, and
        # their gates live in the AgentOS source tree, which is not part of
        # this package. The publisher therefore requires an external receipt
        # proving that the installer gate suite passed against this package's
        # AgentOS content. A receipt that is absent or stale fails the
        # release; a receipt that is merely claimed does not.
        receipt = package / "evidence" / "installer-gate-receipt.json"
        if not receipt.is_file():
            run["suites"].append({"suite": "installer-gate-receipt", "state": "failed",
                                  "reason": "Installer confidentiality gate receipt is missing from the package"})
        else:
            run["suites"].append(_verify_installer_receipt(receipt, package, output))
        # The publisher's own confidentiality gate must run inside the release
        # gate, not only in the separate `stage` step that produced the
        # package. A package edited after staging, or one whose declaration
        # was replaced, would otherwise pass here: the receipt proves the
        # installer channels were exercised, not that the corpus is clean.
        run["suites"].append(_publisher_confidentiality_gate(package, agentos_root, output, timeout))
        if powershell:
            version = _command([powershell, "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"], package, output / "powershell-version", timeout)
            run["commands"].append(version)
            run["dependency_probe_failed"] = version["state"] != "finished" or version["exit_code"] != 0
            if version["state"] != "finished" or version["exit_code"] != 0 or not re.search(r"(?m)^5\.1(?:\.|\s|$)", _output(version)):
                powershell = None
        for index, name in enumerate(PS_TESTS):
            file = agent_tests / name
            if not powershell:
                record = {"suite": name, "state": "not_run", "reason": "Windows PowerShell 5.1 unavailable/unverified"}
            elif not file.is_file():
                record = {"suite": name, "state": "failed", "reason": "Required PowerShell suite missing"}
            else:
                record = _suite(name, [powershell, "-NoProfile", "-NonInteractive", "-File", file], package, output / ("tests/powershell-" + str(index)), timeout)
            run["suites"].append(record)
        scanner_hash = _sha(scanner.read_bytes()) if scanner.is_file() else None
        run["security_scanner_sha256"] = scanner_hash
        for index, (name, expected) in enumerate(sorted(scan_targets.items())):
            record = {"file": name, "sha256": expected}
            if not powershell or scanner_hash is None:
                record.update(state="not_run", reason="Windows PowerShell 5.1 or security scanner unavailable")
            else:
                directory = output / "security" / ("file-" + str(index).zfill(5))
                directory.mkdir(parents=True)
                command = _command([powershell, "-NoProfile", "-NonInteractive", "-File", scanner,
                                    "-FilePath", package / name, "-ProjectRoot", directory,
                                    "-FailOnCritical", "-FailOnWarning"], package, directory / "command", timeout)
                record["command"] = command
                try:
                    if command["state"] != "finished" or command["exit_code"] != 0:
                        raise portable.Blocked("Scanner command failed or timed out")
                    if _sha((package / name).read_bytes()) != expected:
                        raise portable.Blocked("Code changed during security scan")
                    record.update(_verify_report(directory, package / name, command), state="passed")
                except (portable.Blocked, ValueError, OSError, KeyError, TypeError) as exc:
                    record.update(state="failed", reason=str(exc))
            run["security"].append(record)
            _json(output / "run.json", run)
        after = _snapshot(package)
        run["source_unchanged"] = after == sources
        run["coverage_complete"] = {x["file"]: x["sha256"] for x in run["security"]} == scan_targets
        run["code_files"] = len(code)
        run["scanned_files"] = len(scan_targets)
        run["scanner_unchanged"] = scanner_hash is None or (scanner.is_file() and _sha(scanner.read_bytes()) == scanner_hash)
        states = [x["state"] for x in run["suites"] + run["security"]]
        if "failed" in states or run.get("dependency_probe_failed") or not all(run[x] for x in ["source_unchanged", "coverage_complete", "scanner_unchanged"]):
            run["state"] = "failed"
        else:
            run["state"] = "incomplete" if "not_run" in states else "passed"
    except (portable.Blocked, ValueError, OSError, KeyError, TypeError) as exc:
        run.update(state="failed", reason=str(exc))
    run["finished_at"] = _now()
    _json(output / "run.json", run)
    logs = {path.relative_to(output).as_posix(): _sha(path.read_bytes()) for path in sorted(output.rglob("*.log"))}
    public = {"schema": run["schema"], "state": run["state"], "source_files": len(sources),
               "code_files": len(code), "scanned_files": run.get("scanned_files", len(code)),
               "unscanned_files": len(sources) - run.get("scanned_files", len(code)),
               "scan_scope": ("Every shipped file is scanned individually by the security scanner. "
                              "code_files counts the files whose extension is a code extension; it is "
                              "a description of the package, not the scope of the scan."),
              "suite_results": [{"suite": x["suite"], "state": x["state"], "observed_test_count": x.get("observed_test_count")} for x in run["suites"]],
              "security_counts": {state: sum(x["state"] == state for x in run["security"]) for state in ["passed", "failed", "not_run"]},
              "log_sha256": logs, "run_sha256": _sha((output / "run.json").read_bytes()),
              "limits": "Actual local command execution and static coverage only; synthetic test fixtures are not real-device, client activation, second-computer or future-scheduler acceptance. Missing dependencies are not_run. Scanner findings are bounded heuristic checks, not a comprehensive vulnerability certification."}
    _json(output / "public_summary.json", public)
    return run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--security-check", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--agentos-root", type=Path,
                        help="Governance root that holds the local confidential term list. "
                             "Required so the publisher's own confidentiality gate can run.")
    args = parser.parse_args(argv)
    try:
        result = run_release(args.package, args.output, args.security_check, args.dry_run,
                             args.timeout, args.agentos_root)
        print(json.dumps({key: value for key, value in result.items() if key in {"state", "suites", "code_files", "source_files", "limits"} and key != "suites"}, sort_keys=True))
        return 0 if result["state"] in {"passed", "planned"} else 2
    except (portable.Blocked, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"state": "failed", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
