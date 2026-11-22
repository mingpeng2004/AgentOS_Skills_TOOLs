# Background Agent Execution — capability reference

Canonical protocol: `protocols/BACKGROUND-AGENT-EXECUTION.md`.

This file is the routed reference for capability `meta-background-agent`. It
does not restate or compete with the protocol; it points to it and gives the
operational steps for producing the capability report.

## Capability report

Produce one record per client with these fields:

```yaml
client: <adapter id>
background_task_tools_published: true | false | unknown
background_subagent_launchable: true | false | unknown
background_subagent_unreachable: true | false
effective_tool_list: <names observed in the client's own record>
evidence:
  - kind: runtime_evidence | binary_evidence | live_launch
    source: <path or command>
    detail: <what was observed>
    sha256: <hash when a file is the source>
rejection_reason: <the client's own message, verbatim>
```

## Steps

1. Read the client adapter record in `runtime/client-adapters.json`.
2. Read the client's **own** active-tool record (not a governance copy). For
   Kimi Code this is the `tools.set_active_tools` record in the session
   `wire.jsonl`; for other clients use the equivalent native signal.
3. Attempt a live background subagent launch. Do not simulate it.
4. If the launch is rejected, capture the client's verbatim rejection text and
   the effective tool list that caused it.
5. Confirm that no AgentOS file is the cause by scanning the governance tree
   for the client's actual disabling key. Record the scan result.

## Recording rules

- A missing governance key is **not** a cause. Only a present, disabling key
  is.
- "I could not find a setting" is `unknown`, not "unsupported".
- A successful foreground subagent is **not** evidence of background support.
- A tool list copied into a client directory is file parity, not runtime
  behavior.

## Token-budget interaction

`meta-token-budget` and `meta-background-agent` are independent. Token work
may reduce context size, batch calls, or evict artifacts. It may not remove
`TaskList`, `TaskOutput`, `TaskStop`, `Agent`, `AgentSwarm` or
`run_in_background` from any client. If a proposed saving depends on
removing concurrency, the proposal is rejected and the saving is reported as
not achievable by that route.

## Known client states on this host

See `protocols/BACKGROUND-AGENT-EXECUTION.md` § "Client notes". These are
point-in-time observations and must be re-verified before being quoted as
current.

