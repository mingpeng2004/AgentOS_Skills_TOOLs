# Capability Provider Registration

Depth for step ③ of the integration procedure: what the registry actually
validates, and how to promote a capability without breaking the ID set.

## The registry envelope

`policies/SKILL-REGISTRY.json`, schema `agentos-skill-registry-v1`. The
validator in `bin/agentos_skills.py` enforces this envelope exactly — a
differing set of top-level keys is rejected:

```
{schema, version, agentos_version, selection, providers, capabilities}
```

`selection` is fixed and must not be edited:

```json
{"max_constraints": 2, "tie": "blocked_ambiguous",
 "precedence": ["project", "client", "bundled"], "unknown": "blocked"}
```

Consequences encoded there:

- at most **two** constraint capabilities per route
- an ambiguous match is `blocked_ambiguous`, never resolved by guessing
- provider precedence is project → client → bundled, so a project-level
  implementation overrides the bundled one
- an **unknown** capability is `blocked`, not silently routed

## Provider records

Exactly three fields: `id`, `skill`, `bundled`.

- `id` and `skill` must match `^[a-z0-9]+(?:-[a-z0-9]+)*$` — lowercase,
  hyphen-separated, no underscores
- `bundled` must be a **relative** path inside the AgentOS root. An absolute
  path or any `..` segment is rejected.
- `bundled: null` means the provider ships no bundled directory (its method
  lives elsewhere — e.g. an externally authored skill)

## Capability records

Exactly these fields, no more, no fewer:

```
id, domain, group, availability, provider, triggers, scenarios, inputs,
outputs, workflow, acceptance, failure_modes, upstream, downstream,
resources, limits
```

Hard constraints the validator applies:

| Constraint | Why it matters |
|---|---|
| `id` matches the lowercase-hyphen pattern and is unique | IDs are cited in receipts and routing calls |
| `domain` is one letter `A`–`H` | domain-scoped routing |
| `triggers`, `scenarios`, `inputs`, `workflow`, `acceptance` are non-empty string arrays | a capability with no trigger can never be selected |
| `upstream`, `downstream`, `resources` are string arrays (may be empty) | graph edges and provider assets |
| `inputs` is exactly `["task", "goals", "constraints"]` | the router binds these roles from the project |
| `availability` ∈ `mapped` / `protocol` / `candidate` | the three-state contract |
| `candidate` ⇒ `provider is null` **and** `resources` empty | a candidate must not advertise a deployment it lacks |
| non-`candidate` ⇒ `provider` is a registered provider **and** `resources` non-empty | an executable method must point at real files |
| exactly one output, `id == "result"` | the router binds a single artifact |
| at least three `failure_modes`, each `{failure, response}` | a capability must say how it fails |
| no duplicate trigger strings across capabilities | a trigger must resolve to one capability |
| no unknown/self/cyclic graph edges | the dependency graph stays acyclic |
| `limits` is a non-empty string | every capability states what it does not certify |

## Availability levels

| Level | Meaning | Can it be routed? |
|---|---|---|
| `mapped` | existing guidance, provider resources selected | yes |
| `protocol` | a new method workflow ships in the bundled skill and its gates run | yes |
| `candidate` | catalogued opportunity, no deployable provider | **no — blocked** |

Promoting `candidate` → `protocol` is the correct way to close a gap. It states
"a runnable method now exists", which is different from "this is certified".

## The promotion procedure

1. Write the provider under `skills/<provider-name>/` with `SKILL.md` plus
   `references/`, `scripts/`, `assets/templates/`.
2. Verify each script the provider claims to ship actually runs and produces
   non-empty output. A provider whose script silently fails is worse than a
   candidate.
3. Add the provider record to `providers`.
4. For each capability the provider implements: set `availability: "protocol"`,
   `provider: "<provider id>"`, and `resources` to the relative paths of the
   files that carry the method.
5. Rewrite `limits` to say what the method does **not** certify — e.g. that
   placeholder rule values may not gate production, or that no standard
   certification is implied.
6. Run `python -B bin/agentos_skills.py validate` — expect
   `status: valid_structure` and the **same capability count** as before.
7. Run a real route for one promoted capability and confirm `load_only` binds the
   provider's `SKILL.md` and the declared resources. A registry that validates
   but does not resolve proves nothing.

## Keeping the capability set stable

The release verifier requires the capability ID set to equal the manifest set
**exactly**. Adding an ID is a release break; removing one is too.

- To add a *method*: promote an existing `candidate`.
- To add a *capability*: get the ID set change approved and regenerate the
  capability objective (`protocols/CAPABILITY-OBJECTIVE.md`) in the same change.
- To split one capability into two: do not — add a constraint relationship or a
  second provider resource instead.

Keep a backup of `policies/SKILL-REGISTRY.json` before editing it, and never
hand-edit `agentos_version` to fake a compatible release.

## Bundle the method, not the data

A provider carries the **method**: how to extract features, how to compare them
to rules, how to apply an edit, how to validate the result.

The **data** — rule libraries, failure-mode libraries, material tables,
measured datasets — belongs to the project, rebuilt from the user's own source of
truth by a script the provider ships.

Reasons this split matters:

- A bundled data copy forks the moment the project rebuilds, and the fork is
  invisible.
- Data is where the evidence and the review status live; it changes on a
  different cadence than the method and has a different owner.
- Passing the data path in as an argument makes the dependency explicit and
  lets the provider work against any project that has the same shape.

Script convention for a provider that needs project data: default the path
argument to the known project location, allow an override flag, and fail with a
clear message naming the rebuild command when the data is missing — never fall
back to bundled or placeholder data silently.
