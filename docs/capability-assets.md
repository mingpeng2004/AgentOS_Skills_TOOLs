# Capability Assets and Evidence-Bound Learning

`tools/capability_assets.py` is a Python 3.9+ standard-library companion to the
publisher. It validates asset contracts and inspects explicitly configured local
persistent learning. It does not execute tools, install dependencies, read raw
conversations, publish data, or promote a capability. AgentOS
`policies/SKILL-REGISTRY.json` remains the capability-definition authority.

## Asset Manifest

The envelope is `{"schema":"agentos-capability-assets-v1","assets":[...]}`.
Every asset has these fields:

| Field | Contract |
| --- | --- |
| `id` | Stable, unique lowercase identifier; not a filesystem alias |
| `name`, `version` | Nonempty identity and reviewed release version |
| `kind` | `skill` or `tool` |
| `capabilities` | Existing AgentOS capability IDs; unknown IDs are rejected |
| `entry` | Portable path relative to the asset root, present in `hashes` |
| `platforms` | Explicit platform identifiers, or `*` for all platforms |
| `dependencies`, `supersedes` | Asset IDs; unknown/self/cyclic references fail |
| `side_effects` | Explicit nonempty list; use `none` when appropriate |
| `license`, `provenance` | Reviewed rights and origin; neither implies ownership |
| `hashes` | Relative file paths mapped to current lowercase SHA256 values |
| `status` | `candidate`, `validated`, `active`, `reference_only`, `blocked`, or `retired` |
| `canonical` | Boolean; only a selected `active` variant is canonical |
| `family` | Optional functional identity; defaults to `name` |
| `runtime_dependencies` | Optional explicit package/runtime string list; never installed by this tool |

Reference-only, blocked and retired entries may have `entry: null` and no file
hashes. An active/validated asset must reference an existing capability and have
reviewed licensing. Candidates may represent an identified gap but are not
deployed competence. Same-kind, same-family canonical variants cannot overlap
platforms. Identical active content under different asset IDs is rejected.
An active dependency must be active/validated; a superseded asset cannot remain
active. Structural validity is not domain certification or execution permission.

```text
python -B tools/capability_assets.py validate --manifest <assets.json> --registry <SKILL-REGISTRY.json> --root <asset-root>
```

Python interface: `validate_assets(manifest, capability_registry, root)` accepts
manifest/registry dictionaries or JSON paths and returns a validation report.
All relative asset paths must stay below `root`. Links, junctions, reparse
ancestors, traversal, ambiguous case paths and mismatched file hashes fail.

## Explicit Local Learning Sources

The private policy contains `learning_sources`, for example:

```json
{
  "learning_sources": [
    {
      "id": "project-feedback",
      "path": "/absolute/project/.agentos/feedback",
      "kind": "directory",
      "include": ["*.md", "*.json"],
      "max_files": 1000,
      "max_bytes": 4194304,
      "max_directories": 10000,
      "required": true
    },
    {
      "id": "client-persistent-memory",
      "path": "/absolute/client/CLAUDE.md",
      "kind": "file"
    }
  ]
}
```

These example paths are placeholders, not executable defaults. Configure exact
approved project feedback/checkpoint directories and client persistent memory
files; do not point intake at a whole user profile or credentials directory.
The source adapter supports UTF-8 `.md`, `.mdc`, `.txt`, `.json`, `.yaml`, `.yml`
and `.toml`. Default directory patterns select Markdown/text only. Raw sessions,
transcripts, conversations, JSONL, traces and dumps are excluded. Project
`.agentos` learning is not globally omitted: approved subdirectories must be
configured explicitly. No source contents are copied into public output.

`scan_learning(policy, workspace)` writes an immutable observation under private
`workspace/.local/learning/observations/`. It returns `observation_path`,
`observation_sha256`, `records`, and a per-source `coverage` table. Each record
has a stable `key`, private absolute path, current hash,
`changed_since_observation`, and `pending_adjudication`.

Coverage distinguishes `scanned`, `empty`, `absent`, `excluded`, `invalid`,
`partial`, and `unreadable_or_excluded`. Counts, read errors, skipped runtime or
linked paths and reached limits remain explicit. Missing optional sources are
still visible gaps; `required: false` is not permission to call them scanned.
An empty source list does not prove complete coverage. Removed/denied records
appear in `no_longer_observed`, not as proof that their lessons vanished.

```text
python -B tools/capability_assets.py scan --policy <private-policy.json> --workspace <private-workspace>
python -B tools/capability_assets.py status --workspace <private-workspace>
```

## Observation Is Not Adjudication

Repeated scans update the observation comparison only. They never consume an
unreviewed lesson. The adjudicated cursor is derived from immutable private
receipts, by exact source key and hash. A changed source becomes pending again.

`record_receipt(receipt, workspace, asset_manifest=None,
capability_registry=None, root=None)` accepts the following receipt contract:

- `schema: agentos-learning-receipt-v2`, stable unique `id`, and nonempty `reason`.
- `disposition`: `strengthen`, `new`, `duplicate`, or `blocked`.
- `observation` and `observation_sha256`: the exact current private scan artifact
  from this workspace. `sources` contains `{key,path,sha256}` records from it.
- `strengthen`/`new`: `assets` names registered target assets; `capabilities`
  references only existing capability IDs. `targets` contains relative
  `{path,sha256}` bindings from those assets' content hashes. Every selected
  asset must have a target binding, and capability references must belong to
  selected assets. `producer` records the actual implementation identity.
- `verification`: actual artifact bindings `{kind,path,sha256,exit_code,execution_receipt}` for
  all three `counterexample`, `normal`, and `boundary` checks. Exit codes must
  be zero and current artifact hashes must match. The counterexample is a test
  that successfully detects the known bad case, not a silently ignored failure.
  `execution_receipt` is a `{path,sha256}` binding to a runner-produced JSON
  artifact with exactly `command` (nonempty argument list), `exit_code: 0`,
  `output_complete: true`, `log: {path,sha256}` matching this verification log,
  `target_hashes` (the complete relative target-path/hash map), nonempty
  `test_source_hashes` (absolute test-source paths/current hashes), `started_at`
  and `finished_at` (ordered timezone-aware timestamps, not in the future;
  completion must be no earlier than the cited observation). Missing output,
  changed tests, arbitrary Markdown presented as a runner receipt, and stale or
  mismatched artifacts all block adoption.
- `review: {path,sha256}` binds an actual independent review JSON artifact with
  exactly `state: passed`, `producer` matching the receipt, `reviewer` distinct
  from that producer, `source_hashes` (complete source-key/hash map),
  `target_hashes` (complete relative target-path/hash map), and
  `verification_receipts` (complete absolute execution-receipt path/hash map).
  An optional receipt-level `reviewer` must equal that artifact's reviewer.
  A reviewer name alone, or review of another execution round, cannot pass.
- `new`: an explicit `proposed_capability: {id,reason}` identifies the candidate
  or gap. This function never modifies the authoritative capability registry.
- `duplicate`: `duplicate_of` must name an existing v2 adjudicated receipt, and
  source SHA256 multisets (including multiplicity) must match exactly. An
  unrelated source cannot be consumed by pointing to any prior success.
  Semantically similar learning with different bytes requires `strengthen` or
  `blocked`, not automatic duplicate consumption. A blocked, legacy or
  nonexistent record does not justify consuming a duplicate.
- `blocked`: records the reason and observation without consuming any source.

Changed/missing source, target, observation or test evidence blocks consumption.
Receipt IDs are create-only; reruns cannot overwrite prior decisions. Receipts
and source paths stay private and must not enter the portable package.
Legacy v1 receipts remain unchanged and appear as `legacy_unvalidated` in
status; they do not consume learning under the strengthened v2 gate.

```text
python -B tools/capability_assets.py record --receipt <private-receipt.json> --workspace <private-workspace> --manifest <assets.json> --registry <SKILL-REGISTRY.json> --root <asset-root>
```

CLI success returns JSON and exit 0; invalid input returns `state: blocked` and
exit 2. Hash bindings verify current bytes, not the truth of a human assertion
inside those bytes. The runner and reviewer must genuinely produce the cited
artifacts; manually inventing JSON is not execution or review evidence.
Same-permission callers can tamper with local files; this
is not authentication, a security boundary, proof of independent human review,
or a sandbox. Actual tests, independent review, privacy checks and the
publisher's source/package/remote-readback gates remain separately required.
