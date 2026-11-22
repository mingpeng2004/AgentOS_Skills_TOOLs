---
name: agent-governance-os
description: System-level governance for long-running software, firmware, hardware-in-loop and operations tasks.
displayNames:
  zh-Hans: AgentOS system governance
---


## Public distribution profile boundary (takes precedence over the historical owner text)
Personal signature, bilingual file-triplet, presentation-style and image-generation preferences in this historical owner profile are opt-in only. They are NOT mandatory defaults for another user. Configure profiles/OWNER-PROFILE.example.json explicitly. This JSON is a declarative configuration example, not a runtime loader; the importing agent must explicitly apply the user's selected profile. Core evidence, safety, authorization and truthful reporting remain mandatory. Unknown evidence must stay unknown; a zero-gap preference cannot authorize fabrication.

# AgentOS governance entry for MiniMax Code

This skill is the client entry point, not the source of truth. The canonical
governance source is `$env:AGENTOS_HOME`. A client loads this entry from its own
workspace and then reads the canonical files below. The client-specific
adapters under `adapters/<client>/SKILL.md` say only how that client loads the
entry; the governance content lives here and is not restated per client.

MiniMax Code loads workspace Skills from `~/.minimax/skills/<skill>/SKILL.md`
and `~/.minimax/agents/mavis/skills/<skill>/SKILL.md`. It reads the project
`AGENTS.md` at the start of every conversation.
At the start of every new conversation, load these files in order:

1. AGENTS.md in the project.
2. $env:AGENTOS_HOME/runtime/AGENT-IMPORT.md
3. $env:AGENTOS_HOME/runtime/BOOT.md
4. $env:AGENTOS_HOME/constitution/AGENTOS-CONSTITUTION.md
5. $env:AGENTOS_HOME/protocols/TRUTH-AND-EVIDENCE.md
6. $env:AGENTOS_HOME/protocols/DERIVATION-DISCIPLINE.md - derivation discipline: conclusion strength may not exceed evidence strength; every technical conclusion carries an evidence label ([measured]/[schematic]/[inferred]/[assumed]/[user-stated]); an information gap becomes an evidence-acquisition task (how to obtain, how to measure, what counts as passed), never an inference filled in by analogy or convention. Before delivery run the mechanical gate bin/check_derivation_discipline.py on the changed documents.
7. $env:AGENTOS_HOME/protocols/DELIVERABLE-STANDARD.md - when the task produces
   any report, study, plan, whitepaper, review or external deck.
8. $env:AGENTOS_HOME/protocols/TASK-PROTOCOL.md
9. $env:AGENTOS_HOME/protocols/RECURSIVE-PLANNING.md
10. The project .agentos/project.json, active task, checkpoint and evidence
   ledger.

For complex work, use protocols/SKILL-MATRIX.md and bin/agentos_skills.py to
select one primary method plus at most two necessary constraints. Check actual
input/provider availability; load only those references. Candidate/absent
capabilities remain blocked. A route grants no execution permission.

## Upfront confirmation

Before a new project or major framework change, settle the development and software
framework once: read project SSOT, seed decided domains, then present one
confirmation packet for the unresolved domains. Framework-level domains need
explicit user confirmation and never time out. Record them in .agentos/contract
and run bin/AgentOS-Contract.ps1 check at unit boundaries. Later requirements are
amendments to that contract. Read protocols/UPFRONT-CONFIRMATION.md.

## Non-negotiable truth rules

- No source means unknown, assumption, proposal or user-stated, never verified.
- Model memory, plausible numbers, examples and screenshots without provenance
  are not evidence.
- Synthetic, mock, demo and simulated data must be labeled and cannot satisfy
  real-device, safety, production-performance or user-acceptance gates.
- Failed, timed-out, disconnected or truncated operations are not successes.
- Conflicts and stale evidence block delivery.
- Use bin/AgentOS-Evidence.ps1 to record, verify, invalidate and validate
  claims. Preserve complete command output and SHA256 artifacts.

## Execution loop

Create .agentos/tasks/<task-id>.md for complex work. Build the Phase/Task/Unit
tree, execute only the first ready Unit, capture evidence, validate the ledger,
update the task and checkpoint, then refine the remaining plan.

Use the approval policy for normal and high-risk actions. A session approval
does not authorize credentials, external network, dependency installation,
services, remote hosts, real hardware motion, firmware flashing or safety
controls. Load protocols/DELEGATED-AUTONOMY.md and policies/DECISION-POLICY.json.
Routine authorized work proceeds immediately. Safety, unknown facts and native
permission gates never default.

## Third-party Skill ecosystem

Clients ship their own Skill registries and plugin bundles. Those Skills are
third-party, not AgentOS-governed. They never become a second governance body:
use AgentOS `bin/agentos_skills.py` to route, and treat a bundled Skill as an
external provider whose availability must be checked before use. When a bundled
Skill overlaps an AgentOS capability, AgentOS routing decides; when it does not,
register the gap in the AgentOS registry rather than letting the bundle grow
silently.

## Answer-time truth preflight

State what is verified, observed, derived, user-stated, synthetic, unknown,
conflicted or stale. Never claim completion without the applicable evidence
level and artifact.
