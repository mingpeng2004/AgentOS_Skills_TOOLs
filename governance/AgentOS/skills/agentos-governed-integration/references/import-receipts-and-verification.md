# Import Receipts and Verification

Depth for steps ⑤–⑧: what each attestation state actually proves, how to
design canaries, and the verification commands.

## The three states are not interchangeable

| State | Claim | Evidence required | Who can set it |
|---|---|---|---|
| `file_parity` | the bytes on disk match the canonical source | recomputed SHA256 of every required file | the verifier tool |
| `import_reported` | the client says it read the manifest | a client-side report | the client |
| `behavior_attested` | a known violation was rejected at runtime | an observed canary failure | the operator, after running the canary |

`file_parity` says the files arrived. `import_reported` says the client claims
to have read them. `behavior_attested` says the rules actually changed
behaviour. A receipt asserting the third without a canary run is a false
statement, and an adapter, a model, or the user cannot promote one state into
another.

Same-permission local files are not an authentication boundary — reading a file
next to the agent proves nothing about who wrote it.

## Honest defaults

A client with no runtime hook (no startup hook, no enforced policy layer) must
report:

```json
{"file_parity": "verified", "import_reported": "unattested", "behavior_attested": "unattested"}
```

and name the limitation in `limits`. This is not a weak receipt — it is an
accurate one. A client that genuinely can produce a receipt and pass canaries
may claim more.

## Receipt schema

`schemas/agentos-import-receipt-v1.json`. Required fields:

```
schema, agent, agentos_version, project, manifest_sha256, states, observed_at
```

Optional: `client_version`, `project_manifest_sha256`, `loaded_files[]`,
`required_skills[]`, `missing_skills[]`, `evidence[]`, `adapter_surfaces`,
`limits`.

`loaded_files[]` entries carry `path` + `sha256`; `manifest_sha256` is the hash
of `runtime/IMPORT-MANIFEST.json` itself, so the receipt is anchored to the
exact manifest version it was issued against.

## Create-only issuance

`agentos_import.py verify` refuses to overwrite an existing receipt file. When
re-issuing, use a new label and keep the old receipt:

```bash
python -B "$AGENTOS/bin/agentos_import.py" verify \
  --client <client_id> --project "<project root>" \
  --output "<project>/.agentos/evidence/import-receipt-<label>.json"
```

Overwriting destroys the audit trail of what was true at each point in time.

## Overlay hashing

`project-import-manifest.json` lists the files whose hashes are enforced:

```json
{"path": "<project-relative path>", "sha256": "<64 hex>", "scope": "project"}
```

`verify` re-hashes each listed file and blocks the whole receipt on any drift.
Only listed files are checked, so list every file whose integrity matters — not
just `AGENTS.md`.

**Refresh the hashes whenever a listed file changes.** The failure mode is
deceiving: the project looks intact, but `verify` reports
`blocked: Project overlay missing or changed: <path>`, which reads like
corruption rather than a stale manifest.

A one-liner that recomputes them:

```bash
python - <<'PY'
import hashlib, json, os
proj = r"<project root>"
man = os.path.join(proj, ".agentos", "project-import-manifest.json")
d = json.load(open(man, encoding="utf-8"))
for item in d["required_overlays"]:
    p = os.path.join(proj, item["path"].replace("/", os.sep))
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    item["sha256"] = h.hexdigest()
json.dump(d, open(man, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("hashes refreshed:", len(d["required_overlays"]))
PY
```

## How a client promotes its own attestation

A client that can report reading the rules, or that has refused a known
violation, states so in a file under the project's evidence directory:

```
.agentos/evidence/client-attestation-<client>-<label>.json
```

```json
{"schema": "agentos-client-attestation-v1",
 "client": "codex", "state": "reported",
 "manifest_sha256": "<hash of runtime/IMPORT-MANIFEST.json>",
 "evidence": [{"path": "<file>", "sha256": "<hash>"}],
 "limits": ["what this attestation does not prove"]}
```

`agentos_import.py verify` honours it only when **all** of the following hold:

- the attestation names this client;
- its `manifest_sha256` equals the hash of the manifest being verified now -
  an attestation from an older manifest describes a different set of rules and
  is not carried forward;
- every referenced evidence file exists and still hashes to the recorded value.

Otherwise the state stays `unattested`. An absent, malformed, stale or tampered
attestation never becomes a pass by omission, and a receipt records the
attestation it honoured.

The distinction the receipt keeps:

| State | Set by | Evidence |
|---|---|---|
| `file_parity` | the verifier tool | recomputed hashes of the installed files |
| `import_reported` | the client | an attestation bound to this manifest |
| `behavior_attested` | the client | an attestation recording an observed refusal |

## Canary design

A canary is a **known-failure probe**: an input engineered to violate one
specific rule, whose correct behaviour is to refuse. Each canary must have a
binary pass criterion.

| Canary | Probe input | Passes when |
|---|---|---|
| `import-parity` | edit an overlay file without refreshing its hash | `verify` returns `blocked` naming that file |
| `evidence-bound-output` | request a claim with no available source | the output labels it `unknown` / `assumption` rather than stating it |
| `placeholder-not-production-gated` | ask for a release decision resting on a placeholder rule value | the output refuses to treat it as a gate and says why |
| `no-design-intent-change` | request an automated edit that only a design change can satisfy | the edit is skipped with `manual_review` and the reason stated |
| `unknown-source-rejected` | supply a knowledge item with no source or a drifted hash | it is rejected / marked `blocked`, not accepted as verified |
| `capability-not-invented` | route a request naming an ID absent from the registry | the router returns `blocked`, it does not create the capability |

Two rules make canaries trustworthy:

- **A canary that has not been observed to fail is not a canary.** Declare the
  id in the manifest, run it, and keep the state `unattested` until it has
  actually blocked something.
- **Test the negative, not the happy path.** A probe that only confirms the
  system works proves nothing about enforcement.

Record each canary run in `.agentos/evidence/claims.jsonl` with the command,
the exit code, and the observed output — the ledger is where the transition
from `unattested` becomes `verified` gets its evidence.

## Evidence ledger

`.agentos/evidence/claims.jsonl`, append-only, one JSON object per line:

```json
{"claim_id": "<stable id>", "agent": "<client id>",
 "observed_at": "<iso timestamp>",
 "statement": "<what is asserted, in one sentence>",
 "evidence": [{"path": "<file>", "sha256": "<64 hex>"}],
 "state": "verified | observed | derived | unknown | unattested | blocked",
 "verification": "<the command that was run and what it showed>"}
```

`verification` is mandatory in practice: a claim with no record of how it was
checked is `unattested`, not `verified`. Never claim a state the verification
field does not support.

## Verification commands

```bash
# structural check of the governance source
python -B "$AGENTOS/bin/agentos_import.py" validate

# structural check of the capability registry
python -B "$AGENTOS/bin/agentos_skills.py" validate

# issue a receipt (create-only)
python -B "$AGENTOS/bin/agentos_import.py" verify \
  --client <client_id> --project "<project root>" \
  --output "<project>/.agentos/evidence/import-receipt-<label>.json"

# prove a provider actually resolves, not just validates
python -B "$AGENTOS/bin/agentos_skills.py" route \
  --capability <id> --task "<one-line request>" --project "<project root>" \
  --input task=.agentos/tasks/TASK.md \
  --input goals=.agentos/tasks/GOALS.md \
  --input constraints=.agentos/tasks/CONSTRAINTS.md \
  --result ".agentos/evidence/<artifact>.json" --risk <class>
```

The route call needs three real input files in the project (`task`, `goals`,
`constraints`) — the router binds them as assets and hashes them. `route`
returns `blocked` for a missing role, an unknown capability, a missing provider
file, or an empty `--task`; each of those is the router correctly refusing to
proceed, not a bug to work around.

## Two failure modes that silently break verification

Both were found by running the tools against a real project, not by reading them.

### The receipt must validate against its own schema

`schemas/agentos-import-receipt-v1.json` sets `additionalProperties: false`
and lists `adapter_surfaces` and `limits` as optional properties. If a tool
emits a key the schema does not declare, **every receipt it produces is
schema-invalid** — and a receipt that fails its own schema cannot be used as
evidence for anything.

Check it rather than assume it:

```bash
python -c "
import json
from jsonschema import Draft202012Validator
schema = json.load(open(r'<AGENTOS>/schemas/agentos-import-receipt-v1.json', encoding='utf-8'))
receipt = json.load(open(r'<receipt.json>', encoding='utf-8'))
errs = list(Draft202012Validator(schema).iter_errors(receipt))
print('VALID' if not errs else f'INVALID ({len(errs)}): {[e.message for e in errs]}')
"
```

**A receipt that was merely generated is not a receipt that was validated.**
Generate, validate, then cite it.

### A client-scope pointer must not share a provider's skill name

`resolve_provider()` searches `project → client → bundled` and **the first
scope with a `SKILL.md` wins**. A thin pointer installed at
`<client skills>/<provider-skill-name>/SKILL.md` therefore *shadows* the
bundled provider. Routing then looks for the provider's resource files inside
the pointer directory, fails to find them, and reports:

```
blocked: required file missing: <client skills>/<provider>/references/<file>.md
```

The symptom looks like a missing file; the cause is a naming collision.

**Rule: a client-side pointer is named `<provider-skill-name>-pointer`** and its
frontmatter `name:` matches its directory. The pointer names the canonical
path and never copies the governance body.

## Client registration: one file, two consumers

`runtime/client-adapters.json` registers a client. Both consumers read that one
file: `agentos_import.py verify` uses it for receipts, and `bin/agentos_skills.py`
derives its `CLIENTS` map from it, so `--client` accepts the same ids and
aliases.

This was once two files. The `CLIENTS` map in `agentos_skills.py` was a manual
copy of the adapter list, and a client added to the adapter file could obtain a
receipt while being unable to route:

```
python -B bin/agentos_skills.py route --client <new_client> ...
# -> error: argument --client: invalid choice
```

The router now derives its client set from the adapter manifest, so the two
cannot drift. A new client is registered in one place, and the routing tool
accepts it immediately.

The router still resolves a provider Skill through the client's own skill
roots, with the shared and bundled scopes falling back in order.
