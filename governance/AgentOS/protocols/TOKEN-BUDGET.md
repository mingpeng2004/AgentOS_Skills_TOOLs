# AgentOS Token Budget Protocol v1.0

## Purpose

Reduce measured token consumption without reducing task quality, safety,
traceability or evidence. The target is a **50% reduction against the same
client/profile/task baseline**; it is not an unconditional provider-billing
guarantee. Each client must be measured separately.

## Single source and compact import order

The canonical source is this file plus the registered capability
`meta-token-budget`. Client adapters may be thin entry points only; they must
not copy a competing policy.

> **速令（非正文，便于低耗传达）**：先寻 `AGENTOS_HOME`，验 manifest 与 adapter；
> 次读 `BOOT`、`TRUTH`、`CONTEXT`、本令；再按任务选能力。无源不称实，
> 无回执不称已载；新/改 Skill、Tool 先循管理 SOP。矩阵更新即重读；
> 只传必要片段，长物先存证后摘要。质量、安全、证据优先于省 Token。

Every registered or future client must do the following on first use and when
the import manifest changes:

1. Resolve AgentOS and verify manifest and adapter hashes.
2. Read this protocol and the routed capability contract.
3. Reload the canonical entry before acting on the new task.
4. Write an import receipt when supported; otherwise remain `unattested`.

The compact directive saves prompt space; it never waives the full protocol or
the truth gate.

## Cost and measurement

Use this model for diagnosis:

```text
local context cost ~= (prefix tokens * calls) + output tokens
```

Record, when available, provider telemetry for input, cached input, output and
total tokens. If a provider does not expose billing data, report only measured
local tokens and explicitly state that provider cost is unknown. Never invent
`estimated_cost_usd`, `actual_cost_usd` or cache-write values.

Every baseline and comparison identifies client, profile, model, task mix,
time window, session IDs, measurement source and configuration snapshot.

## Behavior rules

- Read only the needed file range (`offset`/`limit`) and avoid repeated scans.
- Filter, aggregate or summarize tool output in code before returning it.
- Batch independent tool calls and persist reusable exploration results once.
- Fetch external pages by bounded excerpts, not whole documents.
- For output over roughly 3,000 characters, identify the needed lines before
  echoing the full result.
- Keep user requirements, constraints, decisions, tool-call parameters and
  current evidence intact.
- Do not remove tools or governance text merely to save tokens.
- Do not switch to a smaller model solely for token savings when quality may
  change. Preserve caching unless a measured comparison proves otherwise.
- Do not enable per-turn history rewriting/compaction by default when it
  breaks a useful prompt-cache prefix.
- **Concurrency is not a token lever.** Never disable, deny or filter a
  client's background-task or subagent tools (`TaskList`, `TaskOutput`,
  `TaskStop`, `Agent`, `AgentSwarm`, `run_in_background`) to reduce token
  consumption. Background execution removes the need for the parent to hold
  intermediate results, so removing it usually *increases* context cost. If a
  proposed saving depends on removing concurrency, reject the proposal and
  report the saving as not achievable by that route. See
  `protocols/BACKGROUND-AGENT-EXECUTION.md`.

## Artifact-first eviction

Bulky tool output may be evicted only after the complete output is saved as an
approved artifact with path, SHA256, timestamp, source and data classification.
The replacement summary must retain the artifact path and hash. Tool-call
parameters are immutable. Original user messages are never evicted.

Before persistence, apply the data policy:

- secrets, access tokens, passwords and private keys: never store;
- private/raw chats or traces: store only when explicitly approved and
  protected by the project policy;
- ordinary engineering output: store under the project evidence/artifact root;
- mixed or unknown data: do not evict until classified, or mark the operation
  blocked.

If the artifact cannot be saved and hashed, do not claim that eviction was
safe. Preserve the output or stop with `blocked`.

## Quality and rollback gates

Token savings are accepted only when the task's existing quality and evidence
gates remain green. Roll back a client-specific tuning change when quality,
traceability, safety, user-message retention or measured prefix size worsens.
Keep a pre-change backup and a reproducible comparison artifact.

The 50% target is reported as `verified`, `observed`, `derived`, `unknown` or
`blocked` according to the Truth and Evidence Protocol. A simulation alone
cannot satisfy a real client or production-performance gate.

## Ledger contract

Append one observation per measurement to the project or provider-owned
`token-trend.jsonl` ledger. Minimum fields:

`observed_at`, `client`, `profile`, `model`, `task_mix`, `session_ids`,
`input_tokens`, `cached_input_tokens`, `output_tokens`, `prefix_tokens`,
`tool_result_tokens`, `compression_events`, `configuration`, `source`,
`evidence_level`, `artifact_path`, `sha256`, `data_class`.

Derived weekly summaries must point to the original observations. They must not
replace or rewrite the append-only evidence ledger.
