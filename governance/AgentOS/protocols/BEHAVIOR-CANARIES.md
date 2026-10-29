# Behavior Canaries

A canary is a **known-failure probe**: an input engineered to violate one
specific governance rule, whose correct behaviour is to refuse. Each probe has a
binary pass criterion - a refusal was observed - and runs the real production
path, never a fixture that happens to share the implementation.

Two rules make a canary trustworthy:

- **A canary that has not been observed to fail is not a canary.** The probe
  must actually block something.
- **Test the negative, not the happy path.** A probe that only confirms the
  system works proves nothing about enforcement.
- **The refusal must come from the rule under test.** A probe that refuses for
  an unrelated reason - a missing project file, a malformed argument - proves
  nothing. Every probe pins the expected refusal message.

## Running them

```bash
python -B "$AGENTOS/bin/agentos_canary.py" \
  --root "$AGENTOS" --project "<project root>" \
  --output "<project>/.agentos/evidence/canary-run-<label>.json"
```

The run is local and offline. Every probe works on a throwaway copy of the files
it perturbs; nothing is written to a canonical source, a client rule file or an
evidence ledger. Exit code 0 means every probe observed its refusal.

## The probes

| Canary | Probe | Passes when the gate refuses because |
|---|---|---|
| `import-parity` | an overlay file is edited without refreshing its hash | the overlay contract reports the file as changed |
| `source-contract-typo` | a required overlay loses its `sha256` binding | the overlay binding is invalid |
| `unknown-source-rejected` | a required overlay carries a drifted hash | the overlay is reported as changed |
| `capability-not-invented` | a capability id absent from the registry is routed | the router reports an unknown capability |
| `candidate-never-routed` | a `candidate` capability is routed | the router reports no verified deployment |
| `missing-provider-blocked` | the provider resource file is removed | the router reports the required file missing |
| `synthetic-evidence-cannot-close-gate` | a complete route, output and independent verifier are paired with a `data_class: synthetic` claim | the gate refuses synthetic evidence |

## The mutation check

A suite that cannot go red is a false-green gate. `tests/test_agentos_canary.py`
weakens one governance check at a time and requires the matching probe to stop
passing. The mutation runs in a separate process, because an already-imported
module keeps its original code after the file on disk changed.

This is the same discipline the project applies to its own gates: a check that
was never observed to fail has not been shown to work.

## What a canary run does and does not prove

A green canary run proves that the **governance path** still refuses. It does
not prove that any client loaded the rules, and it cannot promote a client's
`behavior_attested` state by itself. Client behaviour attestation still needs a
client-owned run against that client's real path.

The distinction is deliberate:

| State | Set by | Evidence |
|---|---|---|
| `file_parity` | the verifier tool | recomputed hashes of the installed files |
| `import_reported` | the client | a client-side report |
| `behavior_attested` | the operator, per client | an observed client-side refusal |
