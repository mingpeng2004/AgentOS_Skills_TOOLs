"""Grade every client answer file in one run.

Each answer file is named ``answers-<client>.json`` and may carry an
``answered_at`` stamp. A file that is still the template (placeholders intact)
is skipped, so an unanswered client is reported as unattested rather than
failed.
"""
import json
import subprocess
import sys
from pathlib import Path


def parse_json(text):
    """The grader prints one JSON document; take the outermost object."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON in output")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:index + 1])
    raise ValueError("unterminated JSON in output")


def run(root, project, answers_dir):
    root = Path(root)
    project = Path(project)
    answers_dir = Path(answers_dir)
    summary = {"schema": "agentos-client-selftest-grade-v1", "clients": []}
    for path in sorted(answers_dir.glob("answers-*.json")):
        if path.name.endswith(".template.json"):
            continue
        client = path.stem[len("answers-"):]
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except ValueError as exc:
            summary["clients"].append({"client": client, "state": "error", "reason": str(exc)})
            continue
        answers = {k: v for k, v in data.items() if k != "answered_at"}
        if any(isinstance(v, str) and v.startswith("<") for v in answers.values()):
            summary["clients"].append({"client": client, "state": "unattested",
                                       "reason": "answer file still holds template placeholders"})
            continue
        process = subprocess.run(
            [sys.executable, "-B", str(root / "bin/agentos_client_probe.py"), "grade",
             "--client", client, "--root", str(root), "--project", str(project),
             "--answers", str(path)], capture_output=True, text=True, timeout=300)
        try:
            result = parse_json(process.stdout)
        except ValueError as exc:
            summary["clients"].append({"client": client, "state": "error",
                                       "reason": str(exc) + " | " + (process.stdout + process.stderr)[-160:]})
            continue
        entry = {"client": client, "passed": result.get("passed"), "failed": result.get("failed"),
                 "unattested": result.get("unattested"), "state": "error"}
        if result.get("failed") == 0 and result.get("unattested") == 0 and result.get("passed"):
            entry["state"] = "passed"
            entry["attestation"] = result.get("attestation")
        summary["clients"].append(entry)
    summary["passed"] = sum(1 for c in summary["clients"] if c["state"] == "passed")
    summary["failed"] = sum(1 for c in summary["clients"] if c["state"] == "failed")
    summary["unattested"] = sum(1 for c in summary["clients"] if c["state"] == "unattested")
    summary["errors"] = sum(1 for c in summary["clients"] if c["state"] == "error")
    return summary


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 3:
        print(json.dumps({"state": "blocked",
                          "reason": "usage: grade_client_selftests.py <root> <project> <answers-dir>"},
                         ensure_ascii=False))
        return 2
    summary = run(argv[0], argv[1], argv[2])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
