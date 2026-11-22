# Candidate Capability Promotion Gate

> **Scope**: how a `candidate` capability in `policies/SKILL-REGISTRY.json` earns
> `mapped`. Capabilities are atomic, generic units; promotion adds no process
> coupling and never follows from elapsed time or a scan alone.

## Principle

A candidate capability is a planned slot with no provider. It is promoted to
`mapped` only when a canonical provider Skill carries it with verified,
reviewed, reversible evidence. Promotion is per-capability and reversible: any
source change re-invalidates it until re-reviewed.

## Requirements (all must hold)

1. **Provider exists** — a provider Skill declares this capability and has a
   canonical, link-free source tree.
2. **Redistribution authorized** — the provider Skill is on
   `policies/REDISTRIBUTION-ALLOWLIST.json` (owner-authored MIT) or is an
   explicitly reviewed vendor asset.
3. **Targeted tests** — normal, boundary, and counterexample cases exist for
   this capability with current passing evidence.
4. **Independent review** — a fingerprint-bound review of the provider package
   passed.
5. **Routable** — `bin/agentos_matrix_check.py` reports the capability as
   routable (not dangling, not blocked) for the target client.
6. **Source binding** — source tree and content hashes are bound; drift
   re-invalidates promotion.

## Non-goals

- Promotion does not order capabilities into a fixed process. Dependencies in
  the registry express conceptual input/output coupling only, never a mandated
  workflow.
- A candidate with no provider stays a planned slot; it is never promoted
  automatically by inventory, scanning, or the passage of time.

## Evidence

Each promotion records the provider Skill id, the bound source hashes, the test
evidence paths, the review artifact, and the reviewer, so the decision can be
re-derived and rolled back.
