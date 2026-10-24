# AgentOS capability matrix and production skill contracts

Single registry: policies/SKILL-REGISTRY.json. Runtime: bin/agentos_skills.py.
Machine-checkable capability manifest: protocols/CAPABILITY-OBJECTIVE.md, generated from the registry; the release verifier requires its capability ID set to equal the registry set exactly.
Reusable workflow: skills/production-skill-routing/SKILL.md. This extends the
existing ROLE-ROUTER, TASK-PROTOCOL, QUALITY-GATE and TRUTH-AND-EVIDENCE rules.
Visual asset production: skills/visual-asset-production/SKILL.md. This extends
VISUAL-ASSET-STANDARD.md and DELIVERABLE-STANDARD.md R4/R8.

## Intake and coverage

The supplied proposal has 64 capability IDs across A-H. Every ID is catalogued.
`mapped`: existing guidance with selected provider resources. `protocol`: new
method workflow supported in the bundled skill. `candidate`: currently missing
specialist implementation/validation. Structural validation is not empirical
capability certification. `catalog` reports the exact status of every entry.

Each record requires ID, domain, triggers/scenarios, input contract, executable
workflow, output contract, acceptance, three failure modes, graph edges, limits
and provider resources where available. Missing fields, unknown fields, duplicate
triggers/IDs, unknown/self/cyclic graph edges fail registration. New capabilities
are reviewed as candidate before actual project evidence justifies promotion.

Capability groups are domain-scoped: requirements, architecture, planning,
hardware, mechanical, industrial-design, embedded, software, ui, **visual**,
quality, manufacturing, knowledge, meta. The `visual` group covers deliverable
illustration production and is bound to `VISUAL-ASSET-STANDARD.md`.

### Visual asset production

`vis-concept-illustration` (domain D, group visual, availability protocol,
provider `visual` -> bundled `skills/visual-asset-production`) is the default
route for any deliverable that needs a scene, device, build or concept picture.
It is registered as `protocol`, not `candidate`, because the method ships with
runnable gates (`scripts/text_screen.py`, `scripts/overlay_compose.py`, each with
its own negative control) and has project evidence: 43 generated base images and
80 composites for the Xiangxiang 50th competition deck, delivered with geometry,
asset, bilingual-parity and real-render gates all green.

The method is deliberately two-layer: the generative model supplies a text-free
base image for realism, and every title, component name, criterion and number is
drawn by the programmatic overlay layer from the audited fact source. A model
that writes its own text is a defect, not a stylistic variant, and is rejected by
the screening gate. Capability selection does not exempt a deliverable from
`VISUAL-ASSET-STANDARD.md` R4/R8, and the visual capability does not replace
data charts: figures that must express a precise data relation stay in
`VISUAL-ASSET-STANDARD.md` section 3.

## Routing contract

One primary method plus at most two explicitly applicable constraints; do not
preload the matrix. Provider priority: project, current client, bundled fallback.
User-skill preference cannot override higher-priority instructions, locked
requirements, evidence or safety controls. Ambiguous/unknown matches are blocked
with candidates for the Coordinator to disambiguate from the actual deliverable.

Missing inputs -> inspect the upstream output/authoritative project asset first.
Candidate specialist -> state the missing expertise/tool and continue only
independent supported work. No implicit download, external tool installation,
hardware action, shell execution or standards certification is added.

## Output and adoption gate

Bind the actual task/goals/constraints, governance/contract/policy files, provider
files and result path. Before handoff, check current source hashes, applicable
evidence level, latest claim status, full artifact hash, timestamp, actual Unit
and distinct verifier record. Keep existing task/evidence sources authoritative;
skill-runs reports are disposable indexes, not a competing state/claims ledger.

Adopted methods: selective loading; trace matrix; risk/FMEA; V-model; appropriate
SRR/PDR/CDR/TRR reviews; ECN-style amendments; reproducible lesson feedback.
Not adopted: ceremonial checklists for every small edit; mass installation of
63 names; fabricated standards clauses or test results; model memory as SSOT;
fixed 72-hour guaranteed automation; custom skills overriding safety controls.

## Deployment and measurement

The same bundled skill/protocol applies across Codex, MiniMax and Kimi. Portable
installer includes the registry, Python CLI, method skill and local tests. Python
3.9+ is required for the new inspector; existing PowerShell features retain their
runtime. Missing Python is a reported prerequisite, not an auto-install.

Gate tests use clearly labeled synthetic fixtures and known failure injection.
Real task demonstration must record an actual route, result, executable check,
current ledger claim and verifier artifact. Client file installation proves
file parity only. Model-triggered invocation, execution quality, certification,
production performance and hardware acceptance need their own observations.

72-hour feedback is a review deadline, no new scheduler/service is installed.
Each lesson is proposed, reviewed, validated against a counterexample, then
promoted within existing authorization and publication workflow. Preserve raw
history and recompute derived statistics from original fields with safe defaults.


## Skill/Tool asset projection

A distribution may publish capability-assets.json referencing IDs in the existing SKILL-REGISTRY.json. It records asset identity, entry, version, platform/runtime dependencies, side effects, license, hashes and canonical/superseded state, not duplicate capability definitions. Unknown rights stay reference-only; unavailable runtime/provider remains candidate. The asset CLI performs structural/hash checks, never automatic capability promotion, external installation or authorization.

Weekly feedback uses evidence-bound private learning receipts with separate observed/processed watermarks. Existing capabilities are strengthened first; true blind spots are proposed for review with counterexample, normal/boundary tests and a current independent review. Semantic duplication is a review decision; strict IDs/graphs alone cannot prove semantic uniqueness.
