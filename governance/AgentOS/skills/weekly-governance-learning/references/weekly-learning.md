# Weekly governed learning iteration

The weekly cycle turns evidence from the host into an updated governed corpus.
It is a delivery pipeline, not a self-certification: each stage produces an
artifact that the next stage checks.

## Stages

1. **Scan** - `tools/weekly_learning.py scan` reads every declared project and
   Skill source root. Coverage must be complete inside the declared roots;
   an inaccessible or absent source is recorded explicitly, and an unreadable
   source is an issue, not an empty result.
2. **Stage** - build the publish package. The staged package is enumerated with
   the package's own sealed manifest. The source-scan exclusion set governs
   what may be *read from a source tree* and must never filter the staged
   payload; using it for both silently drops manifest-declared files.
3. **Validate and verify** - `tools/verify_release.py` runs the package test
   suites and a per-file security scan over the actual distribution files.
   Coverage must be complete: 0 failed and 0 not_run.
4. **Independent review** - a reviewer artifact that did not produce the
   package checks manifest parity, content hashes, privacy and secret absence.
   The publisher may not review itself.
5. **Prepare** - bind the reviewed fingerprint, the review hash and the source
   bindings. Any drift invalidates readiness.
6. **Publish** - a non-force update to the authorized repository.
7. **Read back** - fetch the remote tree and compare it to the local package
   file by file. A publish that reports success is not proof; the readback is.

## Capability-matrix iteration

- A learning that fits an existing capability **strengthens** that capability.
- A learning that exposes a real gap **registers a new capability** in
  `policies/SKILL-REGISTRY.json`, with the objective regenerated from the
  registry by `bin/gen_capability_objective.py`.
- A learning that only repeats an existing entry is recorded as a duplicate and
  consumes no further source; a "duplicate" label is not a reason to consume
  unrelated sources.
- A third-party Skill corpus found on the host is `reference_only`. It never
  becomes a second governance body. When it overlaps an AgentOS capability,
  AgentOS routing decides; a genuine gap is registered rather than left to
  grow silently in the bundle.

## Honesty boundaries

- File parity proves that installed files match canonical hashes. It does not
  prove that a client read them.
- `import_reported` requires a client-owned receipt. `behavior_attested`
  requires a known-failure canary to fail when the rule is deliberately
  violated. Neither may be inferred from a matching hash.
- Software delivery, runtime adoption and user acceptance are reported
  separately and never merged into one "done".
