# AgentOS Universal Client Adapter Contract v1

AgentOS governance has one canonical source. A client adapter is a thin entry
point that imports that source; it is not a second governance constitution.

## Required adapter record

Every current or future client must have one entry in
`runtime/client-adapters.json` with:

- stable `id`, display name and observed version (or `unknown`);
- adapter source path and SHA256;
- supported injection surfaces (`system_file`, `user_skill`, `project_rules`,
  `startup_hook`, `explicit_cli`, or `none`);
- fallback path when native injection is unavailable;
- required manifest version and required core files;
- whether the client can report an import receipt or only file parity.

Unknown capabilities stay unknown. A new client is not blocked from using the
portable fallback, but it cannot be marked runtime-attested without a receipt.

## Propagation states

`file_parity` means the adapter and required sources match the canonical hashes.
`import_reported` means the client reported reading the manifest. Neither state
proves that the model used the rules. `behavior_attested` requires a known-failure
canary to fail when the rule is deliberately violated. `unattested` is the honest
state when the client exposes no trustworthy loading signal. `blocked` means a
required source, hash, overlay or canary is missing.

## Canary evidence

`behavior_attested` needs an observed refusal at runtime, not a file that
matches. `bin/agentos_canary.py` provides the known-failure probes for the
governance path itself, and `protocols/BEHAVIOR-CANARIES.md` defines them. A
green canary run shows that the governance path still refuses; it does not
promote a client to `behavior_attested`. That still needs a client-owned run
against that client's real path.

## New-client onboarding

1. Register the client in `runtime/client-adapters.json`.
2. Select the least-powerful supported injection surface.
3. Install only the thin adapter and canonical manifest; do not copy a divergent
   governance body.
4. Run parity and drift checks.
5. Produce an import receipt.
6. Run the applicable behavior canaries.
7. Keep the client `unattested` until the canary evidence exists.

If no native surface exists, use the portable fallback: project `AGENTS.md`,
`runtime/AGENT-IMPORT.md`, and an explicit startup prompt supplied by the user.
The fallback is a documented limitation, not a claim of host enforcement.

## Security and recovery

Adapters never receive credentials, raw chats, traces or private project data.
Source drift invalidates the receipt. Installation is idempotent and reversible;
failed parity or canary checks preserve the previous adapter and receipt.
