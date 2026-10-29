# AgentOS Client Import Protocol v1.1

This protocol is the stable handoff for every current and future agent client.
Read `runtime/IMPORT-MANIFEST.json`, then the client entry in
`runtime/client-adapters.json`, then the project overlay manifest if present.
Follow `protocols/UNIVERSAL-AGENT-INTEGRATION-SOP.md` for the full discovery,
proposal, controlled-integration, canary and knowledge-handling sequence.
For any Skill or Tool creation or change, also follow
`protocols/SKILL-TOOL-MANAGEMENT-SOP.md` before writing client-local files.
For token efficiency, load `protocols/TOKEN-BUDGET.md` and route
`meta-token-budget`; the compact directive in that protocol is a pointer, not
a substitute for the canonical source.
For Tools, use `bin/agentos_tools.py catalog` and select a registered asset ID;
this read-only route is not execution permission or proof that the client can
run the returned path.

## Import sequence

1. Resolve `AGENTOS_HOME` and the project root.
2. Verify the canonical manifest and all required-file hashes.
3. Verify the client adapter record and its hash.
4. Verify project `AGENTS.md`, `.agentos/project.json`, and any declared overlay.
5. Load the canonical files in the order declared by the manifest.
6. Write a create-only import receipt, or report `unattested` if the client has
   no trustworthy receipt mechanism.
7. Run the project's declared behavior canaries before claiming enforcement.

## Immediate propagation rule

When `runtime/IMPORT-MANIFEST.json` or its version changes, every registered
client must re-read the canonical import entry before its next task. Existing
sessions must acknowledge the new manifest or remain `unattested`; a copied
adapter file is not proof of runtime loading. The compact directive is:

> **先验源，次验器；矩阵变即重读；无回执不称载；长物先存证后摘要；质安证据优先。**

## Receipt contract

New receipts use `schemas/agentos-import-receipt-v2.json`; v1 is retained only
for historical records. A v1 `file_parity=verified` does not establish deployed
client parity. V2 separates:

- `canonical_files`: required core files were inspected and hashed, not loaded;

- `file_parity`: declared deployed client targets match their reviewed hashes;
- `import_reported`: the client says it read the files;
- `behavior_attested`: a known violation was rejected;
- `unattested`: the client provides no runtime proof;
- `blocked`: a prerequisite or integrity check failed.

An adapter, model, or user-supplied statement cannot turn `file_parity` into
`behavior_attested`. Same-permission local files are not an authentication
boundary.

Required Skills are checked by frontmatter identity and complete source-tree
hashes, including reference files. A fallback source accessible through the
explicit CLI is not proof of the client's native Skill discovery. Missing
Skills are reported individually; an empty unchecked list cannot satisfy a gate.

## Project overlays

Project-specific rules belong in a project manifest, not in the global core.
The overlay must declare path, SHA256, scope, required skills and canaries.
An absent, changed or unreadable overlay blocks dependent work; it is never
treated as an empty rule set.
