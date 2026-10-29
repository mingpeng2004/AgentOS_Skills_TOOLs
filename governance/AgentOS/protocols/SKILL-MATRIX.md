# AgentOS capability matrix and production skill contracts

Single registry: policies/SKILL-REGISTRY.json. Runtime: bin/agentos_skills.py.
Machine-checkable capability manifest: protocols/CAPABILITY-OBJECTIVE.md, generated from the registry; the release verifier requires its capability ID set to equal the registry set exactly.
Reusable workflow: skills/production-skill-routing/SKILL.md. This extends the
existing ROLE-ROUTER, TASK-PROTOCOL, QUALITY-GATE and TRUTH-AND-EVIDENCE rules.
Visual asset production: skills/visual-asset-production/SKILL.md. This extends
VISUAL-ASSET-STANDARD.md and DELIVERABLE-STANDARD.md R4/R8.

## Intake and coverage

The supplied proposal has 66 capability IDs across A-H. Every ID is catalogued.
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

`vis-dfm-illustration` (domain D, group visual, availability protocol, provider
`visual` -> the same bundled skill) is the route for deliverables that explain a
**design rule or process criterion** rather than a concept: a DFM chapter, a
moulding or forming rule set, a "what the part must look like and why" section.
One rule is delivered as four things: the picture, the checklist of testable
constraints, the mechanism (why the rule exists) and the failure mode (what
breaks when it is ignored). A rule with a picture but no mechanism is not done.

It is registered as `protocol` because the method ships with runnable gates:
`scripts/iso_render.py` draws solid isometric bodies (lit faces, fibre speckle on
cut faces, contact shadow, drafting dimensions and leader callouts) and
`scripts/dfm_panel.py` assembles the panel and enforces eight gates - coverage,
bilingual purity including the footer, numeric self-consistency, verbatim failure
mode, anchor-on-ink, verdict completeness, layout and a negative control for
each. Project evidence: 12 isometric body panels for the plastic material DFM
chapter, the same two-layer method behind 43 base images and 80 composites for
the Xiangxiang 50th competition deck, and a 240-cell audit of the metal process
DFM chapter that produced the pilot panel for PC-01 p1c1.

**Three body routes, and only one unacceptable form.** A body is either
**A** a text-free generated scene, **B** a filled engineering section or
isometric solid, or **C** a symbolic relation diagram with no part in it (two
reference quantities - a melting point against a service temperature, an
ageing curve, a force direction). The single unacceptable form is the
**skeleton drawing**: a part outlined with text labels where a filled body would
have carried the relation. Judge by that test, not by a single lighting
recipe - the metal process library has 118 filled engineering sections that a
"must have three lit faces" rule would have rejected wrongly. Numbers may
appear on the figure only when they pass the numeric self-consistency gate -
every number must be traceable to the fact source; otherwise, per
`VISUAL-ASSET-STANDARD.md` section 9.8, the number stays in the checklist and the
figure keeps descriptive labels only. This capability also does not replace data
charts and does not relax the rules in `VISUAL-ASSET-STANDARD.md` sections
9.8/9.9 (verdict layer, badges, left/right order) for DFM chapters - it tightens
them: a verdict must be declared explicitly, an undeclared verdict never reads
as neutral, and the good-left/bad-right order applies to two-panel comparisons
rather than to parameter sequences such as too small / right / too large.

## Routing contract

### Universal client propagation

AgentOS is the canonical governance source for current and future clients.
Use `runtime/client-adapters.json` and `protocols/CLIENT-ADAPTER-CONTRACT.md`
to register thin adapters. File parity, client-reported import and behavior
attestation are separate states; a client without a trustworthy runtime hook
remains `unattested` and must use the portable fallback. Do not create a second
governance body inside a vendor-specific adapter.

One primary method plus at most two explicitly applicable constraints; do not
preload the matrix. Provider priority: project, current client, bundled fallback.
User-skill preference cannot override higher-priority instructions, locked
requirements, evidence or safety controls. Ambiguous/unknown matches are blocked
with candidates for the Coordinator to disambiguate from the actual deliverable.

Missing inputs -> inspect the upstream output/authoritative project asset first.
Candidate specialist -> state the missing expertise/tool and continue only
independent supported work. No implicit download, external tool installation,
hardware action, shell execution or standards certification is added.

### Token budget governance

`meta-token-budget` is the single route for measuring and reducing context and
Token consumption. Its canonical contract is `protocols/TOKEN-BUDGET.md` and
its workflow reference is in the governance provider. The 50% reduction is a
matched-baseline target, not a universal billing promise. Client parameters,
quality gates, artifact-first eviction, data classification and rollback must
remain client/task specific and evidence-bound.

### Tool asset discovery and routing

Capability-to-Tool projections are checked via `bin/agentos_tools.py catalog`
and selected by stable asset ID via `bin/agentos_tools.py route --tool ...`.
The catalog validates declared assets against the current registry and
content hashes; it reports entry paths and dependencies but never executes a
tool, installs dependencies, grants permission or proves native client access.
Before use, the client must confirm that it can access the route's entry and
that the task's existing permission/safety gates authorize the tool's declared
side effects. Missing host bindings or dependencies remain `unknown`/blocked.

## Output and adoption gate

Bind the actual task/goals/constraints, governance/contract/policy files, provider
files and result path. Before handoff, check current source hashes, applicable
evidence level, latest claim status, full artifact hash, timestamp, actual Unit
and distinct verifier record. Keep existing task/evidence sources authoritative;
skill-runs reports are disposable indexes, not a competing state/claims ledger.

Adopted methods: selective loading; trace matrix; risk/FMEA; V-model; appropriate
SRR/PDR/CDR/TRR reviews; ECN-style amendments; reproducible lesson feedback.
Not adopted: ceremonial checklists for every small edit; mass installation of
66 names; fabricated standards clauses or test results; model memory as SSOT;
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
