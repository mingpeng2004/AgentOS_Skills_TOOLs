# AgentOS Background Agent Execution Protocol v1

## Purpose

Every registered client must be able to run a subagent in the background
(`run_in_background=true`) and to manage those background tasks. AgentOS
governance must never be the reason a client silently loses that capability.

This protocol is the canonical source. Client adapters may point at it; they
must not copy a competing rule.

## Why this exists

On 2026-10-29 the owner reported that "KimiCode 无法后台启用子智能体". The
investigation proved the cause was **not** AgentOS:

- AgentOS contains no setting that disables background agents. A full scan of
  `protocols/`, `policies/`, `adapters/`, `runtime/` and `constitution/` found
  no occurrence of `TaskList`, `TaskOutput`, `TaskStop`, `disallowedTools`,
  `allowedTools` or `run_in_background`.
- The restriction lives **inside the client product**. Kimi Code gates
  background execution on the three task-management tools being active:

  ```text
  allowBackground = isExactToolEnabled("TaskList")
                 && isExactToolEnabled("TaskOutput")
                 && isExactToolEnabled("TaskStop")
  ```

  When any one of them is missing, the `Agent` tool description is rewritten to
  "Background agent execution is disabled for this agent", and a
  `run_in_background=true` call is rejected before the subagent launches.
- Kimi Desktop ("Kimi Work" / daimon) additionally computes the active tool
  list from a host-side policy that requires **all four** of these at once:

  ```text
  sessionKind == "conversation"
  && executionSurface == "local-control"
  && backgroundTaskSupport == true
  && permissionModeSupportsBackgroundTasks(permissionMode)
  ```

  Desktop conversation turns run on the `message-route` surface, so the three
  task tools are never published and background execution is structurally
  unreachable. This is a host-side product decision, not a user setting:
  no `executionSurface` / `backgroundTaskSupport` key exists in any user
  config, `config.json` or `config.toml` on this host.

The failure mode is silent: the agent still spawns foreground subagents and
still returns a correct-looking answer, so the capability loss is only visible
in the tool description and in a rejected `run_in_background=true` call.

## Rules

1. **AgentOS never removes a client's background-agent capability.** No
   AgentOS policy, protocol, adapter, project overlay or token-budget rule may
   disable, deny or filter `TaskList`, `TaskOutput`, `TaskStop`, `Agent`,
   `AgentSwarm`, `run_in_background` or an equivalent background-task tool.
2. **Token efficiency is never implemented by disabling concurrency.**
   `protocols/TOKEN-BUDGET.md` governs context cost (read ranges, batch calls,
   artifact-first eviction, compression thresholds). It does not authorize
   removing parallel or background execution paths. If a token reduction
   measure would require a client to lose background subagents, that measure is
   rejected.
3. **One current execution Unit does not mean one running agent.** The
   constitution's "一次只有一个当前执行单元；并行单元必须互不争用文件、设备或
   串口" is a safety constraint on **resource contention**, not a scheduling
   restriction. A coordinator may run a background subagent for a Unit that
   needs no exclusive resource while the coordinator continues another
   independent Unit. Two Units that contend for the same file, device, serial
   port, or exclusive hardware lock still run serially.
4. **Verify the client's real capability, not the copied rule file.** A
   governance file present in a client directory proves file parity only. The
   background-agent capability is proven by a live attempt to launch a
   background subagent and observing either a background task handle or a
   named rejection reason.
5. **Record the rejection reason honestly.** When a client refuses
   background execution, capture the client's own message and the effective
   tool list. Do not report "background agents unsupported" without the
   client's own evidence, and do not report success when only a foreground
   subagent ran.

## Verification

Per client, the capability has three independent states and must not be
collapsed:

| State | Meaning | How to prove it |
|---|---|---|
| `background_task_tools_published` | The client's active tool list contains the task-management tools. | Read the client's own active-tool record or tool schema. |
| `background_subagent_launchable` | A background subagent can actually start and detach. | Live launch; observe a task/agent handle that outlives the turn. |
| `background_subagent_unreachable` | The client rejects background execution and names the reason. | Live launch; capture the rejection text and the effective tool list. |

An adapter or project overlay may report `background_subagent_unreachable`
honestly, but it must not claim the other two states without evidence.

## Client notes

### Kimi Code CLI

The CLI's default agent profile publishes `TaskList`, `TaskOutput` and
`TaskStop`, so background execution works. Verified on 2026-10-29 with CLI
0.22.0: a live `Agent(run_in_background=true)` returned a background task
handle.

### Kimi Desktop (Kimi Work / daimon)

Desktop conversations are restricted by host policy and are not user
configurable on this host. Use the Kimi Code CLI for background subagent
work until the host exposes a supported surface. This is recorded as a
client-side limitation, not an AgentOS enforcement.

### Other clients

Claude Code runs subagents in the background by default. Codex exposes a
multi-agent surface. Hermes exposes a `delegation` toolset. MiniMax Code has
its own background task store. Each client's state must be verified with the
table above rather than assumed from a sibling client.

## Anti-patterns

- Assuming a client lost background execution because a governance file
  mentions concurrency limits. Scan for the **actual** disabling key.
- Concluding "unsupported" from the absence of a file in the AgentOS tree.
  Absence of a setting is not evidence of a cause.
- Silently falling back to foreground subagents and reporting the task as
  completed with background semantics.
- Patching or reverse-patching a signed client bundle to force a tool list.
  Record the limitation and use a supported path.

