# AgentOS Skill/Tool Management SOP v1.0

This protocol governs every Skill and Tool created, imported, modified,
distributed or retired by any current or future agent. A client-local directory
is never a second registry.

## 1. Single source of truth

- Capability definitions live only in `policies/SKILL-REGISTRY.json`.
- Skill/Tool assets are projected in `capability-assets.json` and validated by
  `bin/capability_assets.py` or an equivalent registered tool.
- Shared/public packages are derived, reviewed outputs, not source registries.
- Client copies are adapters/cache entries traceable to canonical hashes.
- Obsidian may curate human-readable notes, but it does not redefine a
  capability or grant execution permission.

## 2. Required asset record

Every asset has one stable ID independent of directory name or model name. It
declares `id`, name, `kind` (`skill` or `tool`), semantic version, referenced
capability IDs, entry path, platform, runtime dependencies, side effects,
permissions, network behavior, provenance, license, redistribution state,
complete source-tree hashes, lifecycle state, canonical variant and replacement
links. Tests, behavior canaries and current review references are also bound.

Unknown rights, missing entry, missing hashes or unknown capability references
cannot be `active`. A candidate name is not deployed competence.

## 3. Lifecycle

```text
candidate -> validated -> active (canonical) -> retired
```

Other states are `reference_only` and `blocked`.

- `candidate`: proposal or unproven blind spot; never auto-selected.
- `validated`: structure, hashes, tests and rights checked, not canonical.
- `active`: selected canonical asset with current review and source.
- `reference_only`: indexed but not redistributed or activated.
- `blocked`: a safety, privacy, provenance, conflict or verification gate failed.
- `retired`: no longer selected; history and replacement links remain.

Only one active canonical variant may occupy an asset family and overlapping
platform scope. Complementary assets are not duplicates merely because names
look similar.

## 4. Create or change sequence

1. Read the current registry, this SOP, project rules, contract and active task.
2. Search for an existing capability or asset before creating a new one.
3. Declare strengthen, new candidate, bug fix, compatibility, deprecation or
   retirement.
4. Write a source-backed proposal with scope, dependencies, side effects,
   license, rollback and counterexamples.
5. Add red tests or a known-failure canary before the implementation change.
6. Modify only the canonical source; do not fork a client-local variant.
7. Run normal, negative and boundary tests against the real entry point.
8. Recompute source-tree hashes and validate the asset record.
9. Obtain independent review bound to exact source, target and test hashes.
10. Update the registry/assets projection and checkpoint together.

True blind spots stay `candidate` until real evidence exists. Adding a name does
not create a capability.

### 4.1 Registration is part of creating the asset

A Skill or Tool that is not registered is not part of the matrix, whatever directory
it sits in. Registration therefore belongs to the create-or-change sequence, not to
a later cleanup pass: step 10 is not finished until the registry, the generated
capability objective and the tree receipt all reflect the new asset.

Run the registrar rather than hand-editing the registry. The registry contract has
exact field sets, a globally unique trigger list and a generated objective manifest;
a hand edit that passes validation can still leave the objective manifest stale.

```powershell
python -B "$AGENTOS/bin/agentos_register.py" `
  --provider-id <id> --skill <skill-name> `
  --capability-id <id> --domain <A-H> --group <group> `
  --availability mapped `
  --trigger "<trigger>" --trigger "<second trigger>" `
  --scenario "<one scenario>" --acceptance "<one acceptance criterion>" `
  --resource SKILL.md --resource references/<topic>.md `
  --limit "<what this does not certify>"
```

The registrar backs the registry up, validates the proposed entry against
`bin/agentos_skills.py` before writing it, then regenerates
`protocols/CAPABILITY-OBJECTIVE.md`. A rejected entry means the proposal is wrong;
the contract is not relaxed to make a write succeed.

A Skill that lives outside the AgentOS root also needs a shared tree receipt, so a
later edit of the published copy cannot serve silently:

```powershell
python -B "$AGENTOS/bin/agentos_record_receipt.py" `
  --skill <skill-name> --canonical-root "<absolute path to the skill directory>"
```

### 4.2 Three gates on a new entry

1. **Registration is not deployment.** A new entry enters as `candidate` with
   `provider: null` and empty `resources`. It becomes routable only when a real
   provider and real resource files back it.
2. **A candidate is never auto-selected.** The router blocks `candidate`, so an
   unproven entry cannot be picked up by a task that merely mentions its topic.
3. **The objective manifest must match.** `bin/gen_capability_objective.py --check`
   compares the generated capability IDs against the registry. A new capability ID
   that is not regenerated is a release break, not a harmless omission.

### 4.3 Keep the matrix current

The registry is only useful while it matches reality. Two checks keep it honest:

- `python -B bin/agentos_skills.py catalog --project <project>` reports the provider
  status of every capability. A capability that claims `mapped` or `protocol` but
  resolves as `blocked` is a drift, not a warning.
- A capability whose provider file was moved or renamed stops resolving. Fix the
  provider path or retire the capability; do not leave an entry that only looks
  registered.

Every new Skill or Tool on this host is registered in the same change that creates
it. An unregistered asset is invisible to routing, so its absence is cheaper to
prevent than to discover later.

### 4.4 A Skill that gains or loses a reference file

`capabilities[].resources` is not decoration: routing loads exactly
`["SKILL.md"] + resources`. A Skill that grows a new `references/*.md` but keeps
the old list resolves cleanly and then runs **without** the new file — the method
silently loses a step.

Update it through the script, not by hand-editing the registry:

```powershell
python -B bin/agentos_register.py --update-capability <capability-id> `
    --add-resource references/<new-file>.md
```

The script resolves the provider root first and refuses to register a path that
does not exist under it, validates the candidate registry, backs up, regenerates
`protocols/CAPABILITY-OBJECTIVE.md`, and re-resolves the provider to prove the new
resource binds. `--remove-resource` takes the same path. A `candidate` capability
must not advertise resources at all, so the script refuses that combination too.

If the file list changes on a **shared** Skill, re-record the tree receipt
(`bin/agentos_record_receipt.py --skill <name> --canonical-root <dir>`) before the
registry update: the provider is bound by a private tree receipt, and an edited
shared copy without a refreshed receipt stops resolving.


## 5. Learning to capability

```text
source observation -> private receipt -> privacy/rights review
-> existing capability or candidate gap -> counterexample/normal/boundary tests
-> independent review -> strengthen or propose candidate
```

Observation and adjudication watermarks are separate. Scanning never consumes
an unreviewed lesson. `duplicate` requires an exact source-hash match; semantic
similarity with different bytes requires explicit review. Legacy or weak receipts
cannot authorize consumption.

## 6. Dependencies and conflicts

- Dependencies reference stable asset IDs, never path aliases.
- Dependency and supersession graphs must be acyclic.
- Runtime dependencies are declared, not silently installed.
- Changed dependencies invalidate dependent readiness.
- Conflicting active variants block release until platform separation or a
  canonical selection is reviewed.
- Retiring an asset preserves its reason and replacement link.
- Remote removal requires controlled retirement; user-modified paths are never
  deleted automatically.

## 7. Distribution and propagation

Before distribution, validate the asset projection against the registry and
source tree; check rights, privacy, links/reparse paths and hashes; run source
and staged tests plus actual security coverage; bind an independent review;
generate a complete portable manifest; install only through preflight/backup/
rollback; publish without force updates and read back the complete tree/blob map.

Clients receive canonical reviewed bytes or thin adapters. File parity,
import-reported and behavior-attested remain separate. A client without a
runtime hook remains `unattested`.

## 8. Security, privacy and licensing

Block credentials, raw chats, traces, private project state, unreviewed binaries
and unknown-rights third-party content. Owner-authored licensing does not
relicense third-party code. Do not add services, schedulers, network listeners,
permission bypasses or dependency installation as implicit Skill side effects.

## 9. Retirement and rollback

Every change identifies the previous canonical asset and rollback path. A failed
update restores previous files and receipt without erasing history. Content
rollback does not claim ACL/owner/mode/timestamp restoration. Source or test
drift makes readiness stale and blocks publication until gates rerun.

## 10. Required language

Use precise states: `registered`, `validated`, `active`, `distributed`,
`imported`, `behavior-attested`, `unattested`, `blocked` and `reference-only`.
No Agent may collapse these into “installed and working”.
