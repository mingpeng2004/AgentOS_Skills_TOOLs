## Public distribution profile boundary (takes precedence over the historical owner text)
Personal signature, bilingual file-triplet, presentation-style and image-generation preferences in this historical owner profile are opt-in only. They are NOT mandatory defaults for another user. Configure profiles/OWNER-PROFILE.example.json explicitly. This JSON is a declarative configuration example, not a runtime loader; the importing agent must explicitly apply the user's selected profile. Core evidence, safety, authorization and truthful reporting remain mandatory. Unknown evidence must stay unknown; a zero-gap preference cannot authorize fabrication.

# AgentOS Next-Session Import Contract v1.5

This file is the short, portable import contract for every new AgentOS
conversation. MiniMax Code, Kimi Code, VS Code agents and delegated agents
must read it before doing work.

## Mandatory load order

1. The project's AGENTS.md and its stated SSOT files.
2. The AgentOS root from AGENTOS_HOME.
3. AgentOS/runtime/BOOT.md.
4. AgentOS/constitution/AGENTOS-CONSTITUTION.md.
5. AgentOS/protocols/TRUTH-AND-EVIDENCE.md.
5b. AgentOS/protocols/DERIVATION-DISCIPLINE.md — 推导纪律（证据等级标签、依据链与覆盖性检查、
   缺口即取证任务、输出前自洽扫描、观测工具先校验、推翻痕迹）。**结论强度不得超过证据强度；
   遇到信息缺口先取证，不得用推断填补**。本条对所有技术类结论强制执行。
6. AgentOS/protocols/TASK-PROTOCOL.md and
   AgentOS/protocols/RECURSIVE-PLANNING.md.
7. AgentOS/protocols/CONTEXT-PIPELINE.md,
   AgentOS/protocols/HARNESS-ENHANCEMENTS.md,
   AgentOS/protocols/LONG-HORIZON.md, AgentOS/protocols/QUALITY-GATE.md
   and AgentOS/protocols/MEMORY.md.
8. AgentOS/protocols/TOKEN-BUDGET.md for tool-heavy or long-running work,
   context pressure, compaction or token-efficiency measurement.
9. AgentOS/protocols/DELIVERABLE-STANDARD.md — 对外交付物的署名、中英双语与数据严谨性
   硬规则。任何产出报告、调研、方案、白皮书、评审结论或对外 PPT 的任务，本条为必读；
   不产出对外交付物的任务可跳过。
9b. **凡需要开浏览器（自动化/抓取/渲染/长脚本）**：先读
   `protocols/DESKTOP-NONINTERFERENCE.md` 与 `policies/AI-BROWSER-POLICY.json`，
   并**默认使用 AI 专用浏览器**（`bin/ai_browser.py start`，独立 profile / 端口 9418 / 离屏 / 反限速），
   **绝不启动、注入或结束用户自己的浏览器**；结束只按端口精确关进程。
   需要用户当场操作时才用用户可见界面（内置浏览器面板）。
10. The project's .agentos/project.json, active task and latest checkpoint.
11. The project's .agentos/evidence/claims.jsonl, when present.
12. AgentOS/protocols/DELEGATED-AUTONOMY.md,
    AgentOS/policies/DECISION-POLICY.json and project .agentos/decisions/.
13. When the project has a contract: AgentOS/protocols/UPFRONT-CONFIRMATION.md,
    AgentOS/policies/INTERACTION-POLICY.json and project .agentos/contract/contract.json.
14. Load `runtime/CLIENT-IMPORT-PROTOCOL.md` and the client entry in
    `runtime/client-adapters.json`. If a project declares an overlay manifest,
    verify its hashes before using project-specific governance.
15. For complex engineering work: protocols/SKILL-MATRIX.md and the matching
    capability contracts in policies/SKILL-REGISTRY.json. Load one primary
    provider and up to two necessary constraints, not the whole skills library.
    Candidate or absent capabilities remain blocked. Route/gate reports index
    the existing task and evidence ledger without replacing them.
16. Before installing, relocating or upgrading any tool, CLI, IDE, MCP
    server or skill library on this host, read
    protocols/TOOL-DEPLOYMENT-STANDARD.md. All tool deployment belongs under
    `${PROJECT_PATH}\999_AI_TOOLS_SKILLS`; the C: drive keeps only junctions.

## Import acknowledgement

The agent must internally establish these facts before acting:

- Governance version loaded from AgentOS/VERSION.
- Project root and project SSOT identified.
- Current task, checkpoint and unknowns identified.
- Evidence ledger path identified.
- The structured task contract and recursive planning rules are loaded.
- Authorized routine work proceeds without repeated questions. Notified ordinary
  preferences default after 300 seconds under existing delegation, never inferred
  user approval. Safety, unknown facts, native approvals and user acceptance do
  not default. New feedback is ingested before evaluating saved deadlines.
- No material claim will be presented as verified without a source and a
  validation record.
- Every technical conclusion carries an evidence level label
  ([实测]/[图纸]/[推论]/[假设]/[用户]); an information gap becomes an
  evidence-acquisition task (how to obtain, how to measure, what counts as
  passed), never an inference filled in by analogy or convention.
- Before delivering, the self-consistency scan has been run and the
  derivation-discipline gate
  (bin/check_derivation_discipline.py) reports no blocking finding on the
  changed documents.
- User-stated, model-derived, assumed and synthetic values will remain
  explicitly labeled.
- Conflicting, stale, failed, timed-out or truncated evidence blocks delivery.
- Framework-level domains are confirmed once by the user and enforced by the contract;
  routine work inside the contract proceeds without questions.
- Any deliverable that leaves this machine for the user will carry the fixed
  signature `${OWNER_SIGNATURE}`, will be delivered in both Chinese
  and English, and every number and standard reference in it will be traceable and
  independently reviewable. See protocols/DELIVERABLE-STANDARD.md.

If a required file cannot be read, the agent must report that limitation and
use the state unknown. It must not fill the gap with plausible data.

## New-conversation operating loop

Software/firmware engineering and engineering-Skill maintenance additionally
load protocols/FILE-DRIVEN-ENGINEERING.md and its project-registered Skill
entry. This extension defines MD/DOCX guidance and cross-client file-driven
closure; existing authorization, SSOT and evidence requirements retain priority.

Plan one Unit, execute it, capture complete evidence, record the claim, validate
the ledger, update the task and checkpoint, then select one next action.
At response time, run the truth preflight: separate verified facts from
observations, assumptions, proposals and unknowns.
At Unit boundaries and resume, use bin/AgentOS-Decision.ps1 evaluate after recording
actual new feedback; continue independent ready Units during preference waits.

## Portable client rule

The client skill or overlay is only an entry point. The files under the
AgentOS root are the single source of truth. If a client does not expose a
session-level approval control, AgentOS cannot pretend that such a control
exists; it must state the limitation and preserve the safety gate.

