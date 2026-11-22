"""Register one new skill provider + capability into the AgentOS capability matrix.

The registry contract is enforced by bin/agentos_skills.py; this script only does the
mechanical edit and then hands the result to that validator. It never weakens a field
to make a write succeed: a rejected edit means the proposed entry is wrong, not that
the contract is too strict.

Steps performed:
  1. back up policies/SKILL-REGISTRY.json (create-only, timestamped);
  2. insert the provider record and the capability record;
  3. regenerate protocols/CAPABILITY-OBJECTIVE.md from the registry;
  4. run the registry validator and a real route resolution for the new capability.

Usage:
  python -B bin/agentos_register.py --provider-id travel --skill auditable-trip-handbook \\
      --capability-id plan-trip-handbook --domain C --group planning \\
      --availability mapped --triggers 行程手册 --triggers 自驾行程手册 \\
      --scenario "..." --acceptance "..." --resource SKILL.md \\
      --resource references/fact-ledger.md

Update an existing capability's resource list (a Skill that gained or lost a
reference file). Same discipline as registration: back up, validate, write,
regenerate the objective, then re-resolve the provider to prove the new
resource really binds:

  python -B bin/agentos_register.py --update-capability plan-trip-handbook \\
      --add-resource references/preflight-and-costs.md
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "policies/SKILL-REGISTRY.json"
OBJECTIVE = ROOT / "protocols/CAPABILITY-OBJECTIVE.md"


def load_runtime():
    spec = importlib.util.spec_from_file_location("_agentos_skills", ROOT / "bin/agentos_skills.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def backup(data_path):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = data_path.with_name(data_path.name + ".bak." + stamp)
    shutil.copy2(data_path, target)
    return target


def regenerate_objective():
    spec = importlib.util.spec_from_file_location("_agentos_gen", ROOT / "bin/gen_capability_objective.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    generator.OBJECTIVE = OBJECTIVE
    # The generator parses sys.argv itself, so clear it before calling: otherwise it
    # reads THIS script's arguments (--provider-id …) and fails after the registry
    # has already been written. Its main() takes no positional argv.
    saved_argv = sys.argv
    sys.argv = [saved_argv[0]]
    try:
        generator.main()
    finally:
        sys.argv = saved_argv


def update_resources(args, runtime, data, caps, providers):
    """Update an existing capability's resources list, keeping every gate in place."""
    cap_id = args.update_capability
    if cap_id not in caps:
        raise SystemExit("capability not registered: " + cap_id)
    cap = caps[cap_id]
    if cap["availability"] == "candidate":
        raise SystemExit("candidate capability must not advertise resources: " + cap_id)
    if not (args.add_resource or args.remove_resource):
        raise SystemExit("--update-capability needs --add-resource and/or --remove-resource")

    # Resolve the provider root first: a resource path that does not exist under the
    # real skill root would validate fine but never bind at routing time.
    root, scope = runtime.resolve_provider(
        providers[cap["provider"]], ROOT / "_no_project_scope", "mavis")

    before = list(cap["resources"])
    after = list(before)
    for r in args.add_resource:
        if r in after:
            continue
        if not (root / r).is_file():
            raise SystemExit("resource file does not exist under provider root: " + r)
        after.append(r)
    for r in args.remove_resource:
        after = [x for x in after if x != r]
    if after == before:
        raise SystemExit("resource list unchanged: nothing to write")

    candidate_data = json.loads(json.dumps(data))
    for c in candidate_data["capabilities"]:
        if c["id"] == cap_id:
            c["resources"] = after
            break
    temp = REGISTRY.with_suffix(".json.tmp-register")
    temp.write_text(json.dumps(candidate_data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")
    try:
        runtime.registry(temp)
    except Exception as exc:
        temp.unlink(missing_ok=True)
        raise SystemExit("REJECTED by the registry validator: " + str(exc))

    if args.dry_run:
        temp.unlink(missing_ok=True)
        print(json.dumps({"status": "would_write", "capability": cap_id,
                          "provider_scope": scope,
                          "resources_before": before, "resources_after": after},
                         ensure_ascii=False, indent=2))
        return 0

    saved = backup(REGISTRY)
    shutil.move(str(temp), str(REGISTRY))
    regenerate_objective()

    _, caps_after, _ = runtime.registry(REGISTRY)
    root2, scope2 = runtime.resolve_provider(
        providers[caps_after[cap_id]["provider"]], ROOT / "_no_project_scope", "mavis")
    bound = [str(root2 / r) for r in caps_after[cap_id]["resources"]]
    missing = [b for b in bound if not Path(b).is_file()]
    if missing:
        raise SystemExit("resource missing after write: " + ", ".join(missing))
    print(json.dumps({
        "status": "updated",
        "capability": cap_id,
        "backup": str(saved),
        "provider_scope": scope2,
        "resources_before": before,
        "resources_after": caps_after[cap_id]["resources"],
        "bound_files": bound,
        "objective": str(OBJECTIVE),
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-id")
    parser.add_argument("--skill", help="kebab-case skill name; must equal the frontmatter name")
    parser.add_argument("--capability-id")
    parser.add_argument("--domain")
    parser.add_argument("--group")
    parser.add_argument("--availability", choices=["mapped", "protocol", "candidate"])
    parser.add_argument("--provider-bundled", default="", help="relative path inside the AgentOS root, or empty")
    parser.add_argument("--trigger", action="append", default=[])
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--acceptance", action="append", default=[])
    parser.add_argument("--resource", action="append", default=[])
    parser.add_argument("--limit", default="")
    parser.add_argument("--upstream", action="append", default=[])
    parser.add_argument("--downstream", action="append", default=[])
    parser.add_argument("--update-capability", default="",
                        help="update an existing capability's resources instead of registering a new one")
    parser.add_argument("--add-resource", action="append", default=[])
    parser.add_argument("--remove-resource", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    runtime = load_runtime()
    data, caps, providers = runtime.registry(REGISTRY)

    if args.update_capability:
        return update_resources(args, runtime, data, caps, providers)

    for required in ("provider_id", "skill", "capability_id", "domain", "group", "availability"):
        if not getattr(args, required):
            raise SystemExit("--" + required.replace("_", "-") + " is required when registering")

    if args.provider_id in providers:
        raise SystemExit("provider already registered: " + args.provider_id)
    if args.capability_id in caps:
        raise SystemExit("capability already registered: " + args.capability_id)

    # The provider's skill must be a real, readable SKILL.md whose frontmatter name
    # matches. resolve_provider re-checks this at routing time, so a mismatch here
    # would produce a registry that validates but cannot route.
    skill_root = None
    for base in [ROOT / "skills", Path.home() / ".minimax/skills",
                 Path.home() / ".config/magpie/library/skills"]:
        candidate = base / args.skill
        if (candidate / "SKILL.md").is_file():
            skill_root = candidate
            break
    if skill_root is None:
        raise SystemExit("no readable SKILL.md found for skill: " + args.skill)
    text = (skill_root / "SKILL.md").read_text(encoding="utf-8-sig")
    if ("name: " + args.skill) not in text:
        raise SystemExit("frontmatter name does not match skill name: " + args.skill)

    provider = {"id": args.provider_id, "skill": args.skill, "bundled": args.provider_bundled}
    capability = {
        "id": args.capability_id,
        "domain": args.domain,
        "group": args.group,
        "availability": args.availability,
        "provider": None if args.availability == "candidate" else args.provider_id,
        "triggers": list(args.trigger),
        "scenarios": list(args.scenario),
        "inputs": ["task", "goals", "constraints"],
        "outputs": [{"id": "result", "format": "project-owned file",
                     "purpose": args.capability_id + " result linked to task and acceptance evidence"}],
        "workflow": [
            "Read only the task and declared authoritative inputs.",
            "Apply " + args.capability_id + " within the current confirmed scope; label missing facts.",
            "Produce the declared result, verify it, and link current claims before handoff.",
        ],
        "acceptance": list(args.acceptance),
        "failure_modes": [
            {"failure": "Missing or outdated input",
             "response": "Block dependent work and acquire the authoritative asset."},
            {"failure": "Unsupported specialist or standard claim",
             "response": "Mark unvalidated and request the relevant tool or specialist."},
            {"failure": "Repeated failed attempt",
             "response": "Change path at second failure; root-cause table at third; escalate at fourth."},
        ],
        "upstream": list(args.upstream),
        "downstream": list(args.downstream),
        "resources": [] if args.availability == "candidate" else list(args.resource),
        "limits": args.limit,
    }

    candidate_data = json.loads(json.dumps(data))
    candidate_data["providers"].append(provider)
    candidate_data["capabilities"].append(capability)
    temp = REGISTRY.with_suffix(".json.tmp-register")
    temp.write_text(json.dumps(candidate_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    try:
        runtime.registry(temp)
    except Exception as exc:
        temp.unlink(missing_ok=True)
        raise SystemExit("REJECTED by the registry validator: " + str(exc))

    if args.dry_run:
        temp.unlink(missing_ok=True)
        print(json.dumps({"status": "would_write", "provider": provider, "capability": capability},
                         ensure_ascii=False, indent=2))
        return 0

    saved = backup(REGISTRY)
    shutil.move(str(temp), str(REGISTRY))

    regenerate_objective()

    _, caps_after, _ = runtime.registry(REGISTRY)
    print(json.dumps({
        "status": "registered",
        "backup": str(saved),
        "provider": args.provider_id,
        "capability": args.capability_id,
        "capability_count": len(caps_after),
        "objective": str(OBJECTIVE),
        "objective_check": "see gen_capability_objective.py --check",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
