# AgentOS portable entry

This file is a fallback entry point for an agent client with no native Skill,
system-prompt or startup-hook integration.

1. Read the project `AGENTS.md`.
2. Resolve `AGENTOS_HOME` if available; otherwise use the AgentOS package root
   selected by the user.
3. Read `runtime/AGENT-IMPORT.md`, `runtime/BOOT.md` and
   `runtime/CLIENT-IMPORT-PROTOCOL.md`, then follow
   `protocols/UNIVERSAL-AGENT-INTEGRATION-SOP.md`.
4. Validate `runtime/IMPORT-MANIFEST.json` and the client entry in
   `runtime/client-adapters.json`.
5. Keep the client state `unattested` unless it can produce a current import
   receipt and pass the declared behavior canaries.

Compact handoff for clients with a small prompt surface:

> **先验 AgentOS 源与 manifest，次读本令；矩阵变即重读；无源不称实，无回执不称载；长物先存证后摘要；质安证据优先。**

This fallback does not force a client to read files and does not authenticate a
model. It is a portable, user-visible handoff, not a claim of runtime loading.
