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


def run_release(package, output, security_check=None, dry_run=False, timeout=300):
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
    scanner = portable._check_path(security_check) if security_check else package / "tools/security_check.ps1"
    powershell = _powershell()
    suite_names = ["package-unittest", "agentos-skills-unittest", *PS_TESTS]
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
        for index, (name, expected) in enumerate(sorted(code.items())):
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
        run["coverage_complete"] = {x["file"]: x["sha256"] for x in run["security"]} == code
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
    public = {"schema": run["schema"], "state": run["state"], "source_files": len(sources), "code_files": len(code),
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
    args = parser.parse_args(argv)
    try:
        result = run_release(args.package, args.output, args.security_check, args.dry_run, args.timeout)
        print(json.dumps({key: value for key, value in result.items() if key in {"state", "suites", "code_files", "source_files", "limits"} and key != "suites"}, sort_keys=True))
        return 0 if result["state"] in {"passed", "planned"} else 2
    except (portable.Blocked, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"state": "failed", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
