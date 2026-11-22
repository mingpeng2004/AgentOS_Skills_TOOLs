---
name: agentos-governed-integration
description: "Integrate agents, providers and projects into AgentOS."
metadata:
  version: "1.0.0"
---

> **本文件是 AgentOS 的 bundled 方法，不是客户端副本。**
> AgentOS 是唯一治理源；本文件只提供**操作方法**，
> 治理正文仍以 `runtime/` `protocols/` `policies/` 下的原文为准。
> 客户端只持有指针与入口，不得复制治理正文。

# AgentOS-Governed Integration

AgentOS is the **single governance source**. A client (Hermes, Codex, Kimi, …) is a
*thin adapter* that imports that source. This skill covers building the
integration — registering a client, registering a provider, standing up a project
overlay, and issuing a receipt that does not overstate what was proven.

## When to Use

- A client (Hermes, Codex, Kimi, MiniMax, Claude Code) must be brought under an
  existing AgentOS governance source.
- A new engineering method needs to ship as a reusable capability that routes to
  real files, instead of living as ad-hoc scripts in one project.
- A project needs an `.agentos/` overlay, a hashed import manifest, and a
  create-only import receipt.
- Someone asks whether a capability is "registered", "deployed", or "working" —
  the three attestation states answer that separately.
- Tool or script decisions must respect a governance root's rules about implicit
  installs, evidence, and provider/data separation.

Skip for: ordinary Hermes profile management with no governance root involved,
and general multi-agent orchestration with no governance system in play.

## The five rules that decide the design

1. **Never create a second governance body.** Do not copy AgentOS protocol text
   into a client or project directory. A client holds pointers and an entry point.
   *Why:* two bodies drift, and the drifting copy is the one people read.
2. **Never add a capability ID to close a gap.** The release verifier requires the
   capability ID set in the registry to equal the manifest set exactly, so a new
   ID is a release break. Promote an existing `candidate` to `protocol` with a
   provider instead. *Why:* the ID set is a contract, not a catalogue.
3. **Never let a provider bundle the project's data.** A provider ships the
   *method*; the knowledge base, rule library and datasets belong to the project
   and are passed in as a path argument. *Why:* bundled data forks silently.
4. **Never let file sync be reported as enforcement.** `file_parity`,
   `import_reported` and `behavior_attested` are three different claims with
   three different evidence. *Why:* a client that cannot prove runtime loading
   must say so, or the whole receipt becomes decorative.
5. **Never install a tool the machine may already have.** Inventory first, then
   request authorization for the gap. *Why:* duplicate installs fork versions and
   break the "which copy is authoritative" question.

## Procedure

### ① Read the governance source before touching anything

```bash
AGENTOS=<agentos root>            # e.g. ${AGENTOS_HOME}
cat "$AGENTOS/VERSION"
python -B "$AGENTOS/bin/agentos_import.py" validate
python -B "$AGENTOS/bin/agentos_skills.py" validate
```

Read at minimum: `runtime/IMPORT-MANIFEST.json`, `runtime/client-adapters.json`,
`runtime/AGENT-IMPORT.md`, `runtime/CLIENT-IMPORT-PROTOCOL.md`,
`protocols/CLIENT-ADAPTER-CONTRACT.md`, `protocols/TRUTH-AND-EVIDENCE.md`,
`protocols/SKILL-MATRIX.md`, `policies/SKILL-REGISTRY.json`.

Record the SHA256 of each file you read. Every later claim of parity is against
those hashes.

### ② Register the client as a thin adapter

Add one entry to `runtime/client-adapters.json`:

- stable `id`, display name, observed version (or `unknown`)
- `source`: the adapter path, or `null` when there is no native file
- `surfaces`: the injection surfaces actually supported — only ones you can prove
  (`user_skill`, `project_rules`, `explicit_cli`, `system_file`, `startup_hook`)
- `fallback`: the portable entry path used when no native surface exists
- `receipt`: `unattested` unless the client genuinely produces a receipt
- `status`: `registered`, `registered_unattested`, or `registered_unknown`

`validate` fails the whole registry if an entry has no surfaces or a `source`
that does not exist — fill the fields honestly rather than dropping the entry.

### ③ Ship the method as a bundled provider, not a new capability

Provider layout under `$AGENTOS/skills/<provider-name>/`:

```
SKILL.md                     entry point + always-on rules
references/<topic>.md        depth needed only sometimes
scripts/<name>.py            statically re-runnable actions
assets/templates/            starter files meant to be copied
```

Register it in `policies/SKILL-REGISTRY.json`:

- add to `providers`: exactly the fields `id`, `skill`, `bundled`
  (`bundled` is a **relative** path — an absolute path or `..` is rejected)
- promote the capabilities this provider actually implements from `candidate` to
  `protocol`, set `provider` to the new provider id, and give each one a
  non-empty `resources` list of relative paths inside the provider directory
- `candidate` capabilities are validated to have `provider: null` **and** empty
  `resources` — a candidate cannot advertise an executable provider
- `limits` must stay honest: what the method does *not* certify

The registry validator rejects unknown fields, duplicate triggers, cyclic graph
edges, and a `capability` whose provider is not registered. Run
`python -B bin/agentos_skills.py validate` after every edit.

### ④ Stand up the project overlay

```
<project>/
├── AGENTS.md                 managed block from templates/PROJECT-ENTRY.md, then project rules
├── .agentos/
│   ├── project.json          mirrors the reference project layout
│   ├── status.json           current phase, open gaps
│   ├── project-import-manifest.json
│   ├── evidence/claims.jsonl create-only evidence ledger
│   ├── tasks/                task / goals / constraints contracts
│   └── checkpoints/ decisions/ approvals/
```

`.agentos/project-import-manifest.json` is schema `agentos-project-import-manifest-v1`:

```json
{
  "schema": "agentos-project-import-manifest-v1",
  "project_id": "<project>",
  "required_overlays": [
    {"path": "AGENTS.md", "sha256": "<64 hex>", "scope": "project"},
    {"path": ".agentos/project.json", "sha256": "<64 hex>", "scope": "project"}
  ],
  "required_skills": ["<provider skill name>"],
  "behavior_canaries": ["<canary id>", "..."]
}
```

**Every overlay hash must be recomputed whenever the referenced file changes.**
`agentos_import.py verify` re-hashes each overlay and blocks on drift — a stale
manifest turns a working project into `blocked`.

The `required_overlays` entries are the *only* files whose hash is enforced, so
anything you want drift-detected must be listed there. Put the files that
actually govern behaviour in it, not just the entry document.

### ⑤ Declare behaviour canaries, then run them

A canary is a known-failure probe: deliberately violate a rule and confirm the
system blocks it. Categories that pay off:

| Probe | Fails when |
|---|---|
| import-parity | an overlay file is edited without refreshing its hash |
| evidence-bound-output | a claim is emitted without a source reference |
| placeholder-not-production-gated | an E3/placeholder value is used as a release gate |
| no-design-intent-change | an automated edit crosses into design intent |
| unknown-source-rejected | a knowledge item with no source is accepted as verified |
| capability-not-invented | a routing request names a capability ID absent from the registry |

Until a canary has actually run and been observed to fail, the corresponding
state stays `unattested`.

### ⑥ Issue the receipt (create-only)

```bash
python -B "$AGENTOS/bin/agentos_import.py" verify \
  --client <client_id> \
  --project "<project root>" \
  --output "<project>/.agentos/evidence/import-receipt-<label>.json"
```

`verify` refuses to overwrite an existing receipt — create-only by design. Use a
new label for each re-issue and keep the old one.

The receipt separates three claims and the tool fills them honestly:

| State | Meaning | Tool default |
|---|---|---|
| `file_parity` | bytes match the canonical source | `verified` |
| `import_reported` | the client says it read the manifest | `unattested` |
| `behavior_attested` | a known violation was rejected | `unattested` |

A client with no runtime hook cannot honestly report `behavior_attested`. Say
`unattested` and name the limitation in `limits` — see
[references/import-receipts-and-verification.md](references/import-receipts-and-verification.md).

### ⑦ Route work through the registry, not by memory

```bash
python -B "$AGENTOS/bin/agentos_skills.py" catalog --project "<project>"
python -B "$AGENTOS/bin/agentos_skills.py" route \
  --capability <id> --task "<one-line request>" --project "<project>" \
  --input task=.agentos/tasks/TASK.md \
  --input goals=.agentos/tasks/GOALS.md \
  --input constraints=.agentos/tasks/CONSTRAINTS.md \
  --result ".agentos/evidence/<artifact>.json" --risk <class>
```

Rules the router enforces: **one primary capability plus at most two
constraints**; an unknown capability or an ambiguous match is `blocked`, never
guessed; a `candidate` capability is `blocked` because it has no deployable
provider. `--task` is the request string — `--summary` is not it, and an empty
task yields `blocked: empty request`. Routing success means *preconditions for
execution are met*; it is not execution permission and not delivery evidence.

### ⑧ Keep the evidence ledger honest

`.agentos/evidence/claims.jsonl` is append-only. One JSON object per line with
the claim, its evidence paths + hashes, the state, and the verification that was
actually run. A claim whose verification was never executed is `unattested`,
not `verified`.

## Deliverable standards for anything this system produces

- **Signature**: `${OWNER_SIGNATURE}` — used verbatim, not
  translated, no model name, no AI watermark.
- **Font**: 微软雅黑 (Microsoft YaHei) for reports, decks, charts and diagrams.
- Outward-facing deliverables (reports, reviews, decks, whitepapers) are
  **bilingual** — Chinese and English, section-for-section equivalent, English
  adding and omitting nothing.
- Every number states its provenance (standard / journal / supplier / derived);
  unverified values are marked `unknown` and carry no conclusion.
- Engineering judgements are labelled as such and do not replace an engineer's
  sign-off.

## Pitfalls

- **Copying AgentOS prose into the client.** The client holds a pointer and an
  entry file. A copied body becomes a second governance body that drifts.
- **Registering a capability with `provider: null` but non-empty `resources`.**
  The validator rejects it — a candidate with resources claims a deployment it
  does not have.
- **Absolute `bundled` paths in the registry.** Must be relative to the
  AgentOS root; the validator rejects absolute paths and `..`.
- **Editing an overlay file without refreshing the manifest hash.** The next
  `verify` blocks the project and the failure looks like corruption, not a
  stale hash.
- **Overwriting an import receipt.** `verify` is create-only; write a new file.
- **Promoting a capability to `protocol` and calling it certified.** `protocol`
  means a method ships and gates run — it does not mean standard certification
  or production capability. Say so in `limits`.
- **Bundling the knowledge base inside the provider.** Pass the project path in;
  a bundled copy forks the moment the project rebuilds.
- **Routing with `--summary` instead of `--task`.** `--task` is the request;
  with it empty the router blocks.
- **Treating a passing script exit code as verified.** A script that wrote no
  output still exits 0 — require non-empty output and check the artifact.
- **Installing a dependency before checking what is present.** Inventory the
  machine first; the fix is usually a path, not a download.

## References

- Capability provider registration, promotion rules, validator constraints:
  [references/capability-provider-registration.md](references/capability-provider-registration.md)
- Receipt states, canary design, overlay hashing, verification commands:
  [references/import-receipts-and-verification.md](references/import-receipts-and-verification.md)
