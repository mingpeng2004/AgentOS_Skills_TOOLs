# AgentOS Managed Client Entry

This is a thin entry, not a second governance body. Resolve `AGENTOS_HOME`;
the local installation used for this entry is `{agentos_root}`.

Before work, read the project's AGENTS.md and the canonical
`runtime/AGENT-IMPORT.md`, `runtime/BOOT.md`, and
`runtime/CLIENT-IMPORT-PROTOCOL.md`. Re-read when their manifest changes.

For Skills and Tools, use `policies/SKILL-REGISTRY.json`,
`bin/agentos_skills.py`, and `protocols/SKILL-TOOL-MANAGEMENT-SOP.md`.
Resolve current client paths through `bin/agentos_paths.py`; never recreate an
old home, fork a registry, or load the whole skill library. Use one primary
capability and only necessary constraints. Canonical authored project skills
remain sources; client copies are caches/entry points.

For a tool-oriented task, inspect the registered projection with
`bin/agentos_tools.py catalog --capability <capability-id>` and resolve an
explicit stable asset ID with `route --tool <asset-id>`. A route reports source,
hash, dependencies, and side effects; it does not run the tool or authorize its
effects. Use the current project and client policy for the actual operation.

When the client supports background subagents, run non-contending Units in the
background and keep working in parallel. Never disable or refuse a
background-task or subagent tool to save tokens, and never read a
one-Unit-at-a-time rule as a concurrency ban; it constrains resource
contention only. Read `protocols/BACKGROUND-AGENT-EXECUTION.md` before
reporting that background execution is unavailable.

No source means no verified fact. File parity, reported import, and observed
behavior are separate states. Honor safety/native permissions and current
project contracts. For long/tool-heavy work, read `protocols/TOKEN-BUDGET.md`;
preserve quality, evidence and privacy before optimizing tokens.

Compact reminder: verify source; load only what is needed; save approved
evidence before summarizing; never claim runtime compliance from copied files.
