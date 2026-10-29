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
