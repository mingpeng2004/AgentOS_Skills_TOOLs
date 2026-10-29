# Universal AgentOS Integration SOP v1.0

This is the standard operating procedure for every current and future agent
client: Hermes, Kimi, MiniMax, Codex, Claude Code and later clients.

## 0. Authority and priority

AgentOS is the canonical governance source. This SOP is a protocol entry point,
not a second constitution. A client adapter, model memory, project note or user
prompt cannot silently weaken the AgentOS source, project rules, safety controls,
evidence gates or explicit user acceptance requirements.

The canonical files are:

- `runtime/IMPORT-MANIFEST.json`
- `runtime/AGENT-IMPORT.md`
- `runtime/BOOT.md`
- `runtime/CLIENT-IMPORT-PROTOCOL.md`
- `runtime/client-adapters.json`
- `protocols/CLIENT-ADAPTER-CONTRACT.md`
- `policies/SKILL-REGISTRY.json`
- `bin/agentos_import.py`

The client must read this SOP through the current manifest. A URL or copied
snippet is a discovery aid, not a permission to skip the canonical import
sequence.

## 1. Mandatory operating states

Every integration reports one state for each layer:

1. `discovered` — the client or project path was found.
2. `file_parity` — canonical files and declared overlays match by SHA256.
3. `import_reported` — the client reports that it read the manifest and rules.
4. `behavior_attested` — a known-failure canary was rejected by the client path.
5. `active` — the previous states are current and no blocking drift exists.
6. `unattested` — a runtime hook or trustworthy client report is unavailable.
7. `blocked` — a required file, hash, overlay, license, safety or evidence gate failed.

Never promote `file_parity` to `active` by assumption. A client that cannot
prove runtime loading remains `unattested` while it can still use the portable
fallback.

## 2. Phase A — Read-only discovery

Before editing, installing, publishing or importing memory:

1. Identify the client ID, executable/process path and observed version.
2. Identify its user Skill path, project-rule path, memory path and native
   injection surfaces. Read names and metadata first; do not read credentials,
   raw chats, tokens, traces or private memory content without explicit scope.
3. Resolve `AGENTOS_HOME` and read `runtime/IMPORT-MANIFEST.json`.
4. Read `runtime/CLIENT-IMPORT-PROTOCOL.md`, this SOP and the client adapter entry.
5. Read the project `AGENTS.md`, `.agentos/project.json`, active task,
   checkpoint and `.agentos/project-import-manifest.json` when present.
6. Run `python -B bin/agentos_import.py validate` and produce a bounded inventory.

Discovery output must distinguish `present`, `absent`, `unreadable`, `excluded`,
`not_supported` and `unknown`. Absence of a file is not proof that no event or
knowledge exists.

## 3. Phase B — Integration proposal

Return a proposal before changing client or project state. It must include:

- client identity, observed paths and version evidence;
- source/adapter/overlay hashes and current drift;
- supported injection surfaces and the least-powerful safe surface;
- portable fallback path when native loading is unavailable;
- required files, required Skills, missing providers and candidate gaps;
- file parity/import/behavior states;
- security, privacy, licensing and rollback risks;
- exact files and tests that would change;
- an explicit statement of unknowns and unattested limits.

Do not claim that “the model now follows AgentOS” in this phase.

## 4. Phase C — Controlled integration

Only after explicit user approval for the proposed scope:

1. Back up the current adapter/overlay and record source hashes.
2. Install or update only the thin adapter and canonical references.
3. Never copy a divergent governance constitution into a client-specific file.
4. Never install credentials, services, schedulers or third-party dependencies
   as a side effect of governance import.
5. Use create-only receipts and a reversible update path.
6. Re-run parity and drift checks immediately after the write.

If the client has no native injection hook, install only the portable entry
template and report `unattested`; do not fabricate a runtime import signal.

## 5. Phase D — Behavior canaries

Before `behavior_attested`, run the applicable known-failure tests. At minimum,
the integration must demonstrate that:

- a changed canonical hash blocks import;
- a changed project overlay blocks dependent work;
- a missing required Skill remains `blocked` or `candidate`, never active;
- a deliberate source-contract typo is rejected by the project gate;
- a meta-only rewrite that drops a field is rejected;
- a replay/live or output/source mismatch is visible and fails its gate;
- an incomplete or synthetic evidence record cannot close a real-world gate.

The canary must exercise the real project checker or production path; a test
fixture that accidentally shares the implementation typo is not evidence.

## 6. Phase E — Knowledge and memory handling

The client may propose durable knowledge, but does not write directly into the
shared knowledge base:

```text
private client outbox
  -> source/hash and privacy scan
  -> duplicate/conflict review
  -> evidence-bound learning receipt
  -> Obsidian curated note
  -> AgentOS capability/Skill/Tool decision
```

Raw chats, credentials, traces and private project state stay private. Existing
capabilities are strengthened before a new candidate is proposed. Conflicts are
preserved for review; last-write-wins is forbidden.

## 7. Required report and receipt

The client must save a current `agentos-import-receipt-v2` or explicitly report
why it cannot. The receipt must separate:

- canonical manifest hash;
- project overlay hash;
- loaded-file hashes;
- `file_parity`, `import_reported` and `behavior_attested` states;
- required/missing Skills;
- evidence paths and timestamps;
- privacy and runtime limitations.

Legacy v1 receipts remain historical. Canonical file observation, deployed
adapter parity, explicit-CLI Skill resolution and native runtime behavior are
different checks; never promote the former into the latter automatically.

The report must say “unattested” when runtime loading was not observed. A local
hash is integrity evidence, not authentication of a same-permission process.

## 8. Stop conditions

Stop and report `blocked` when:

- a source or overlay hash changed unexpectedly;
- a required file is missing or unreadable;
- a client asks to bypass a safety, permission, evidence or privacy gate;
- credentials, raw private data or unknown-rights assets would be exported;
- a behavior canary remains red or cannot run;
- the client cannot distinguish file parity from runtime loading.

Do not continue by copying an older adapter, using a stale receipt, or treating
an empty scan as a clean scan.

## 9. Future-client onboarding

For a new client:

1. Add one adapter record to `runtime/client-adapters.json`.
2. Declare the supported injection surfaces and portable fallback.
3. Run parity, receipt and behavior-canary tests.
4. Keep the client `registered_unknown` or `registered_unattested` until evidence
   exists.
5. Update `runtime/IMPORT-MANIFEST.json`, tests and the change receipt together.

No future client is required to share a vendor-specific memory format. It is
required to implement this contract or remain explicitly unattested.

## 10. Completion language

Use these exact meanings:

- “AgentOS source verified” — canonical files and hashes passed.
- “Adapter parity verified” — the client files match the source.
- “Import reported” — the client reported reading the rules.
- “Behavior attested” — canaries passed on the declared path.
- “Agent integration active” — all applicable previous states are current.
- “Unattested” — no runtime proof; do not claim active governance.
