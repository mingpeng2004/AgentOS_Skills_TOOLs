"""Produce the installer confidentiality-gate receipt for a staged package.

The installer channels (F-ND-2 and F-ND-3) live in the AgentOS source tree
and are exercised there. That source tree is not part of the published
package, so their result reaches the release gate as a receipt bound to the
AgentOS content that is actually shipping.

    python tools/installer_gate_receipt.py --package <path> --agentos-root <path>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import distribution as dist

RECEIPT_SCHEMA = "agentos-installer-gate-receipt-v1"
SUITE = "test_agentos_non_distributable.py"
LIMITS = ("Proves the installer confidentiality gates pass against the AgentOS "
          "content named in tested_against_sha256, which is the source tree the "
          "suite ran in. agentos_sha256 names the bytes that ship, which may "
          "differ by the portable normalisation. A file whose shipped bytes differ "
          "from the tested bytes is proven only for the tested form. It does not "
          "prove that a client loaded the rules, and it does not cover the remote "
          "repository history.")


# The portable edition rewrites a file in a declared way. A file whose shipped
# bytes differ from the tested bytes is therefore proven only for the tested
# form -- but the DIFFERENCE must be a declared normalisation, not an
# unexplained one. An undeclared difference means the suite ran against
# content that is not what ships, and the receipt must say so rather than
# letting a reader infer coverage it does not have.
def normalisation_reason(relative):
    """Why the shipped bytes of this file differ from the tested bytes."""
    if relative.endswith(".cs"):
        return ("byte-order-mark-strip: the published edition carries no BOM on "
                "C# sources; the C# compiler does not require one")
    if relative.endswith(".ps1"):
        return ("portable-path-placeholder: an absolute machine path is replaced "
                "by ${PROJECT_PATH} in the published edition")
    if relative.endswith(".py"):
        return ("byte-order-mark-strip: the published edition carries no BOM on "
                "Python sources; the interpreter does not require one")
    return None


def _normalisations(shipped, tested, package=None, agentos_root=None):
    """The reason each file's shipped bytes differ from its tested bytes.

    A file whose bytes are identical needs no reason. A file whose bytes
    differ needs one, AND the reason must be verified: applying the declared
    normalisation to the tested bytes must reproduce the shipped bytes
    exactly. A reason that is merely asserted is not a reason.
    """
    result = {}
    for relative, digest in sorted(shipped.items()):
        tested_digest = tested.get(relative)
        if tested_digest is None or tested_digest == digest:
            continue
        reason = normalisation_reason(relative)
        if reason is not None and package is not None and agentos_root is not None:
            reason = _verify_normalisation(relative, reason, package, agentos_root)
        if reason is None:
            reason = ("UNEXPLAINED: the shipped bytes differ from the tested bytes "
                      "and no normalisation reproduces the shipped bytes")
        result[relative] = reason
    return result


def _verify_normalisation(relative, reason, package, agentos_root):
    """Check that the declared normalisation reproduces the shipped bytes.

    The reason is kept only when the transformation actually produces the
    shipped content. A rule that says "these differ for a good reason" is
    not evidence that the reason is the reason.
    """
    import re as _re
    source = Path(agentos_root) / relative
    shipped_file = Path(package) / "governance" / "AgentOS" / relative
    if not source.is_file() or not shipped_file.is_file():
        return None
    source_bytes = source.read_bytes()
    shipped_bytes = shipped_file.read_bytes()
    candidates = [source_bytes]
    if source_bytes.startswith(b"\xef\xbb\xbf"):
        candidates.append(source_bytes[3:])
    text = source_bytes.decode("utf-8-sig")
    # The publisher replaces the drive ROOT and keeps the path beneath it, so
    # the model must do the same or it will not reproduce the shipped bytes.
    replaced = _re.sub(r"(?i)[A-Z]:[\\/]+000_AI(?![A-Za-z0-9])", "${PROJECT_PATH}", text)
    replaced = _re.sub(r"(?i)[A-Z]:[\\/]+Users[\\/]+[^\s\"'`<>]+", "${USER_SKILLS_PATH}", replaced)
    candidates.append(replaced.encode("utf-8"))
    candidates.append(replaced.encode("utf-8-sig") if relative.endswith(".ps1")
                      else replaced.encode("utf-8"))
    if shipped_bytes in candidates:
        return reason
    return None


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bound_files(package):
    """The AgentOS files as they ship in the package."""
    agentos = Path(package) / "governance" / "AgentOS"
    wanted = [
        "policies/NON-DISTRIBUTABLE.json",
        "policies/REDACTION-TERMS.example.json",
        "installer/AgentOS.Setup.cs",
        "installer/build-installer.ps1",
        "tests/test_agentos_non_distributable.py",
    ]
    bound = {}
    for relative in wanted:
        target = agentos / relative
        if target.is_file():
            bound[relative] = sha(target.read_bytes())
    return bound


def tested_files(agentos_root):
    """The AgentOS files the installer gate suite actually ran against.

    The suite runs in the AgentOS source tree, not in the package, because the
    installer sources it needs are not all part of the package in every
    edition. The two sets are recorded separately so a consumer can see
    exactly which bytes were proven and which bytes ship.
    """
    agentos = Path(agentos_root)
    wanted = [
        "policies/NON-DISTRIBUTABLE.json",
        "policies/REDACTION-TERMS.example.json",
        "installer/AgentOS.Setup.cs",
        "installer/build-installer.ps1",
        "tests/test_agentos_non_distributable.py",
    ]
    tested = {}
    for relative in wanted:
        target = agentos / relative
        if target.is_file():
            tested[relative] = sha(target.read_bytes())
    return tested


def run_suite(agentos_root):
    """Run the installer gate suite in the AgentOS source tree."""
    tests = Path(agentos_root) / "tests"
    if not tests.is_dir():
        return None
    return subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(tests),
         "-p", SUITE, "-v"],
        capture_output=True, text=True, timeout=900)


def observed_count(text):
    match = re.search(r"Ran\s+(\d+)\s+tests?\b", text)
    return int(match[1]) if match else 0


def executed_tests(text):
    """The tests that actually ran, named.

    unittest verbose output prints the test name on one line and the result
    on the next when the test has a docstring, so the name is read from the
    line that carries it.
    """
    # The verbose output puts the test name at the start of a line, but the
    # name and its result can be separated by a carriage return when the
    # output is wrapped. Normalise the line endings first, then match.
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    executed = []
    for line in normalised.split("\n"):
        match = re.match(r"^\s*(test_[A-Za-z0-9_]+)\s+\(", line)
        if match and match.group(1) not in executed:
            executed.append(match.group(1))
    return executed


def skipped_count(text):
    """How many of the observed tests were skipped."""
    match = re.search(r"skipped=(\d+)", text)
    return int(match[1]) if match else 0


def executed_tests(text):
    """Names of the tests that actually ran, from unittest verbose output.

    With a docstring, unittest prints the test name on one line and the
    result on the next, so the result is read from the line that follows.
    """
    executed = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(test_[A-Za-z0-9_]+)\s+\([^)]*\)\s*$", line)
        if not match:
            continue
        result = ""
        if index + 1 < len(lines):
            result = lines[index + 1]
        else:
            result = line
        if re.search(r"\.\.\.\s+(ok|FAIL|ERROR|skipped)", result):
            if "skipped" not in result:
                executed.append(match.group(1))
    return executed


# A gate that was skipped proves nothing. This test builds the installer from
# the current source and refuses a tainted payload, so it is the one that
# demonstrates the installer channel is actually exercised.
LOAD_BEARING_TEST = "test_runtime_gate_rejects_a_tainted_payload_when_executed"


def main(argv=None, strict=True):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--agentos-root", type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else [])

    package = dist.no_links(args.package)
    result = run_suite(args.agentos_root)
    if result is None:
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "state": "not_run",
            "suite": SUITE,
            "exit_code": None,
            "observed_test_count": 0,
            "agentos_sha256": bound_files(package),
            "reason": "The AgentOS source tree has no tests directory; the installer gates could not be exercised.",
            "limits": LIMITS,
        }
        target = package / "evidence" / "installer-gate-receipt.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")
        print(json.dumps({"receipt": str(target), "state": receipt["state"],
                          "observed_test_count": 0}, ensure_ascii=False))
        return 1 if strict else 0
    output = (result.stdout or "") + (result.stderr or "")
    count = observed_count(output)
    skipped = skipped_count(output)
    executed = executed_tests(output)
    # A suite that ran nothing proves nothing. Record that honestly instead of
    # claiming a pass; the release gate refuses a receipt that is not a pass.
    load_bearing_ran = LOAD_BEARING_TEST in executed
    passed = result.returncode == 0 and load_bearing_ran
    if result.returncode == 0 and not load_bearing_ran:
        state = "not_run"
        reason = ("The load-bearing installer gate test did not run in this "
                  "environment; nothing about the installer channel was proven.")
    elif passed:
        state = "passed"
        reason = ""
    else:
        state = "failed"
        reason = output[-800:]
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "state": state,
        "suite": SUITE,
        "exit_code": result.returncode,
        "observed_test_count": count,
        "executed_test_count": len(executed_tests(output)),
        "executed_tests": executed_tests(output),
        "agentos_sha256": bound_files(package),
        "tested_against_sha256": tested_files(args.agentos_root),
        "normalisation": _normalisations(bound_files(package),
                                         tested_files(args.agentos_root),
                                         package, args.agentos_root),
        "reason": reason,
        "limits": LIMITS,
    }
    target = package / "evidence" / "installer-gate-receipt.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
    print(json.dumps({"receipt": str(target), "state": receipt["state"],
                      "observed_test_count": count}, ensure_ascii=False))
    if passed:
        return 0
    # A suite that could not run is reported, not hidden. The release gate
    # refuses a receipt that is not a pass; staging only refuses a real failure.
    return 1 if strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
