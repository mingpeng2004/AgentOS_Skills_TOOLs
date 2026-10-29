# AgentOS 任务简报：把 Token 效率对策升级为治理能力

**任务 ID**：`token-budget-governance-v1`
**提出方**：Ming Peng（经 metal-expert 实施第一版）
**目标**：把已验证有效的 Hermes token 节省配置，从「一次性调参」升级为 **AgentOS 治理能力**，覆盖本机所有 client 的所有 agent，且**不降低专业产出品质**。

---

## 0. 给维护智能体的一页速览

| 项 | 内容 |
|---|---|
| **已完成的** | 第一版对策已在 Hermes 上落地并验证（配置 + 全局记忆 + 测量工具 + provider 参考） |
| **缺的** | ① 不符合 AgentOS `CONTEXT-PIPELINE.md` 的驱逐前置条件；② 覆盖范围只到 Hermes，Claude Code / Codex / Kimi 等 client 未覆盖；③ 无能力注册，无协议级约束，无证据台账 |
| **要做的** | 建 `meta-token-budget` 能力 + `TOKEN-BUDGET.md` 协议 + 落盘式驱逐对齐 + 跨 client 落地 + 证据链 |
| **不要做的** | 不要重做已验证的配置值；不要裁工具集；不要碰 `micro_compact` |
| **验收** | 能力数 65 → 66 且新能力可路由；Hermes 侧前缀实测 ≤120K；驱逐前 artifact+SHA256 落盘率 100% |

---

## 1. 第一版已落地的事实（不要重做，但可以质疑）

### 1.1 诊断（Hermes `state.db` 实测，非估算）

测量工具：`metal-system/scripts/token_audit.py`（已同步到 provider `metal-process-engineering`）

| 指标 | 实测值 |
|---|---|
| API 调用 | 697 |
| `cache_read`（每轮重读的前缀） | 191,445,618 token |
| **平均每轮前缀** | **274,671 token** |
| 上下文最终规模 | 488,614 token |
| 上下文构成 | **工具结果 87%** / assistant 9% / user 5% |
| 工具结果 | 756 条；中位 793 字符，p90 3,251，最大 31,944 |
| 缓存命中率 | **98.9%** |
| 系统提示词 + 全部工具 schema | **908 token** |

**两个被数据推翻的假设**（维护智能体请勿重开这两个讨论）：

1. ~~缓存没生效~~ → 命中率 98.9%，缓存正常。关闭缓存会让成本上升。
2. ~~工具 schema 太占 token~~ → 全部 schema 合计 **908 token**（Hermes 用 deferred 机制，schema 不进 prompt）。裁工具集**零收益**且减少 agent 能力。

**真正的成本结构**：
```
总成本 ≈ (上下文前缀长度 × 调用次数) × 单价 + 输出 token
```
前缀长度是**乘数**。原 `threshold=0.50`（1M 窗口 = 50 万）**整场从未触发压缩**，前缀从 3 万涨到 48.8 万，每轮都在重读。

### 1.2 已落地的配置（生效中，两处都写）

> **重要**：Hermes profile 运行时 `get_config_path()` 指向 profile 自己的目录，**不回退全局**。所以 `config.yaml` 与**每个** `profiles/*/config.yaml` 必须都写。

| 键 | 默认 | 当前值 | 依据 |
|---|---|---|---|
| `threshold` | 0.50 | **0.20** | 0.50 = 50 万才触发，实测根本没触发 |
| `threshold_tokens` | None | **200000** | 绝对上限，与 ratio 取低者；不依赖有争议的模型窗口元数据 |
| `target_ratio` | 0.20 | **0.15** | 压缩后保留 15% 尾部 |
| `protect_first_n` | 3 | 3 | — |
| `protect_last_n` | 20 | 14 | 尾部保留略减 |
| `min_tail_user_messages` | 1 | **2** | 用户原始消息永不被压缩 |
| `tail_mode` | lean | lean | 已是省 token 模式 |
| `proactive_prune_tokens` | 0 | **48000** | 确定性裁剪器，**无 LLM 调用** |
| `proactive_prune_min_result_chars` | 8000 | 6000 | 覆盖更多中等结果 |
| `proactive_prune_min_reclaim_tokens` | 8000 | 6000 | — |
| `micro_compact` | false | **保持 false** | 每轮重写历史、破 prompt cache 前缀，净收益为负 |

**为什么 `proactive_prune_tokens` 比降阈值更重要** —— Hermes 源码注释原文：

> independent of `threshold` (**which rarely fires on large windows, so old tool output is re-sent every turn**)

### 1.3 已验证的效果

**裁剪器实测**（真实会话数据重放）：

| 项 | 值 |
|---|---|
| 原始 | 1,400,411 字符 |
| 裁剪后 | 986,324 字符 |
| **削减** | **29.6%（≈104,249 token）** |
| 被降级工具结果 | 52 个 |

裁剪后保留的可回溯线索：

| 工具 | 保留内容 |
|---|---|
| `web_extract` | **URL** |
| `skill_view` | skill 名 + 「可重新加载」提示 |
| 其他 | 工具名 + 字符数 |

**工具调用的参数（执行记录）字节级不改写。**

**组合效果模拟**（真实消息流重放）：

| 压缩触发点 | 裁剪触发点 | 平均前缀 | 相对基线 |
|---|---|---|---|
| 500,000（现状，从未触发） | 0 | 191,918 | 1.51x |
| 500,000 | 48,000 | 136,416 | 1.07x |
| 260,000 | 48,000 | 130,940 | 1.03x ← 偏晚 |
| **200,000** | **48,000** | **96,300** | **0.76x ← 当前采纳** |
| 160,000 | 48,000 | 82,155 | 0.65x |
| 120,000 | 48,000 | 65,613 | 0.52x |

### 1.4 已落地的文件

| 文件 | 改动 |
|---|---|
| `hermes/config.yaml` | `compression` 段 |
| `hermes/profiles/metal-expert/config.yaml` | `compression` 段 |
| `hermes/memories/MEMORY.md` | token 效率条目（378 字符，注入每个 agent 每轮） |
| `hermes/profiles/metal-expert/memories/MEMORY.md` | 同上 |
| `metal-system/AGENTS.md` | §3.3 Token 效率（项目级行为细则） |
| `metal-system/kb/token_policy.json` | 策略台账（基线/依据/实测/回滚） |
| `metal-system/scripts/token_audit.py` | 测量工具 |
| `metal-system/REQUIREMENTS.md` | REQ-016（status=draft） |
| `metal-system/docs/TOKEN-EFFICIENCY-REPORT.md` | 交付报告 |
| `AgentOS/skills/agentos-governed-integration/references/token-efficiency.md` | 可复用方法（已登记进 IMPORT-MANIFEST，85 项） |

**回滚备份**：
- `hermes/backups/config/token-efficiency-20261026-160601/`（config.yaml ×2）
- `hermes/backups/config/token-efficiency-20261026-161105/`（MEMORY.md ×2）

---

## 2. 需要修的四个真问题

### P0 — 驱逐不符合 AgentOS 协议（**必须先修**）

`AgentOS/protocols/CONTEXT-PIPELINE.md` 的 "Context pressure policy" 第 3 条：

> **Evict bulky tool output only after its artifact path and SHA256 are saved.**

**实测当前 Hermes 裁剪器不满足**：`agent/context_compressor.py` 中 `sha256` / `artifact` 命中数均为 **0**。`_demote_tool_result_at()` 直接把原文替换为 1 行摘要，**不落盘、不记哈希**。

后果：
- 原文不可审计、不可追溯、不可举证
- 违反 AgentOS 既有协议
- 无法满足 `TRUTH-AND-EVIDENCE.md` / `EVIDENCE-POLICY.json` 对「引用可验证对象」的要求

**要求**：把 Hermes 侧驱逐改为**先落盘、后驱逐**——驱逐前把原文写入项目级 artifact 目录并记录 SHA256，摘要中带路径 + 哈希，使原文可回取、可举证。

> 落点建议：`metal-system/scripts/` 增加 `tool_output_store.py`；或推动 Hermes 上游修改 `context_compressor.py`（**上游修改需另开任务，不在本简报范围**）。

### P1 — 覆盖范围只到 Hermes，其他 client 没有对应约束

`runtime/client-adapters.json` 已注册 6 个 client：`hermes`、`codex`、`claude-code`、`kimi`、`kimi-code`、`minimax-code`。

当前 token 对策**只对 Hermes 生效**。其他 client 的 agent 行为完全不受约束。

**要求**：把「行为层 token 纪律」做成 **client 无关的协议**，让每个 client 的 adapter 都能落地。

### P2 — 没有能力注册，没有协议级约束

`policies/SKILL-REGISTRY.json` 现有 65 个能力，**无任何 token/context 预算相关能力**。

已核对（勿重复调查）：

- `km-context-pack`（domain G / knowledge / provider core）触发词是「上下文装配 / context / pack / checkpoint」，语义是**知识打包**，**不是 token 预算治理**。不塞进它。
- `meta-*`（domain H，5 个）是治理类能力，`meta-token-budget` 应归此处。

### P3 — 无证据台账、无跨会话趋势

`scripts/token_audit.py` 只能测单会话/全量快照。**没有随时间累积的 token 台账**，无法回答：
- 这个月比上个月省了多少？
- 哪个 client / profile 最费？
- 压缩触发了几次、每次省了多少？

---

## 3. 请维护智能体执行的 6 项工作

### 任务 1：新建 `meta-token-budget` 能力（P0）

**归属**（已核对 registry 结构，请照此填写）：

| 字段 | 值 |
|---|---|
| `id` | `meta-token-budget` |
| `domain` | `H` |
| `group` | `meta` |
| `availability` | `protocol`（与 `meta-qc-gate` / `meta-router` 同级；方法未成熟前不要标 `mapped`） |
| `provider` | `governance` → `skills/agentos-governed-integration` |
| `resources` | `references/token-efficiency.md`（**已存在，4,788 B**）、`references/token-budget-workflow.md`（**待新建**） |
| `upstream` | `[]` |
| `downstream` | `meta-qc-gate`（质量门禁消费 token 指标） |

**硬约束**：
- `resources` **只能指向自身 provider 目录内**。跨 provider 只能文档交叉引用。
- 能力数 **65 → 66**。**只加这一个**，不得为凑数新增。
- `limits` 字段必须诚实写明：「提供 token 计量与配置建议；不替代提供方计费数据，实测账单金额需以提供方为准；模型窗口元数据在 Hermes 硬编码与 models.dev 之间存在冲突，本能力不依赖争议值。」

**结构**（照 `meta-qc-gate` 的完整字段，不要少写）：
`id / domain / group / availability / provider / triggers / scenarios / inputs / outputs / workflow / acceptance / failure_modes / upstream / downstream / resources / limits`

### 任务 2：新建 `protocols/TOKEN-BUDGET.md`（P0）

AgentOS 协议级文档，让约束对**所有 client** 生效。要求：

1. **成本模型**：`总成本 ≈ (前缀长度 × 调用次数) × 单价 + 输出 token`——前缀是乘数。
2. **测量规范**：任何 client 的 token 主张必须有测量来源，禁止估计。
3. **行为层纪律**（client 无关，可直接落成各 client 的规则文件）：
   - `read_file` 用 `offset`/`limit` 只读需要的段
   - 工具输出先经代码过滤/聚合再回显
   - 探索性命令一次成型并**落盘 JSON** 供后续复用，不反复重跑
   - 能批量的工具调用合并为一次
   - 外部网页取片段而非全文
   - 单次工具输出超过约 3,000 字符，先问自己真正需要哪几行
4. **驱逐前置条件**：引用并强化 `CONTEXT-PIPELINE.md` 第 3 条（artifact path + SHA256 先保存）。
5. **禁止项**（附实测理由）：
   - 禁止裁剪工具集（schema 合计 908 token，零收益且减能力）
   - 禁止默认开 `micro_compact`（每轮破 prompt cache）
   - 禁止为省 token 换更小模型或削减治理内容（品质与治理优先）
6. **回滚规范**：任何 client 侧 token 配置变更必须先备份、给出触发回滚的条件（质量下降 / 前缀不降反升）。

### 任务 3：把驱逐改成「先落盘、后驱逐」（P0 —— 见 §2 P0）

- Hermes 侧：实现 `tool_output_store.py`（原文 → artifact 目录 → SHA256 → 摘要带路径与哈希）
- 与 `metal-system/scripts/token_audit.py` 打通：审计输出能列出被驱逐 artifact 的路径与哈希
- 验证：跑一遍裁剪，断言 **artifact 落盘率 100%**、SHA256 可复算、原文可回取

### 任务 4：跨 client 落地（P1）

- `runtime/client-adapters.json`：确认 `hermes` 之外各 client 的 `surfaces` 能承载 token 规则
- 为每个 client 落一份**薄适配**（不复制治理正文，只指向 `protocols/TOKEN-BUDGET.md`）
- 参考 `adapters/hermes/SKILL.md` 的既有做法
- 状态诚实：未实测的 client 保持 `unattested` / `file_parity_only`，**不得标 verified**

### 任务 5：token 台账与趋势（P3）

扩展 `scripts/token_audit.py`：
- `--append` 模式：把每次测量追加到 `kb/token_trend.jsonl`
- 新增 `--by-client` / `--by-profile` 维度
- 输出：按周 / 按 profile 的平均前缀、缓存命中率、压缩次数

台账是**决策依据**，不是日志。字段至少：时间、client、profile、会话 id、API 调用数、`cache_read`、平均前缀、上下文构成占比、当时的 `compression` 配置快照。

### 任务 6：证据与验收链（P0/P3 收口）

- 更新 `runtime/IMPORT-MANIFEST.json`（登记新文件）
- 重新生成 `import-receipt.json`，必须 **jsonschema 0 错误**
- `agentos_import.py validate` 通过
- `agentos_skills.py validate` → `valid_structure`，**count = 66**
- 新能力可路由：`agentos_skills.py route --capability meta-token-budget --client hermes` 成功
- 在 `metal-system/REQUIREMENTS.md` 把 REQ-016 从 `draft` 更新为 `agreed`（**前提是用户确认目标铆钉**；未确认则保持 draft 并在 `open-questions.md` 记一条）

---

## 4. 验收标准

| # | 标准 | 判定方式 |
|---|---|---|
| A1 | 能力数 65 → **66**，且 `meta-token-budget` 可路由 | `agentos_skills.py validate` + `route` |
| A2 | `protocols/TOKEN-BUDGET.md` 存在，含 6 项禁止项与回滚规范 | 文件检查 + 人工评审 |
| A3 | 驱逐时 artifact 落盘率 **100%**，SHA256 可复算，原文可回取 | 跑裁剪并断言 |
| A4 | 新会话平均前缀 **≤120,000 token**（基线 274,671） | `token_audit.py` 实测 |
| A5 | 产出品质不降：DFM 合成夹具 **10/10** 与历史基准一致 | `dfm_check.py` 回归逐项比对 |
| A6 | 裁剪后工具结果**保留可回溯线索**（URL / skill 名 / artifact 路径） | 断言 |
| A7 | 工具调用参数在裁剪中**零改写** | 断言 |
| A8 | 用户原始消息**永不被压缩** | 断言（`min_tail_user_messages=2`） |
| A9 | token 台账可按周 / client / profile 出趋势 | `token_audit.py --by-client` |
| A10 | 其他 client 状态保持 `unattested` / `file_parity_only`，未虚标 | `client-adapters.json` 检查 |
| A11 | import receipt jsonschema **0 错误** | 校验脚本 |
| A12 | 供应商侧金额**未被虚构**——本机 `estimated_cost_usd` / `actual_cost_usd` 均为 0 且不报 `cache_write_tokens`，只能给 token 量 | 台账与报告措辞检查 |

---

## 5. 明确不要做的事

| 不要做 | 理由 |
|---|---|
| 裁剪工具集 / 精简工具 schema | 全部 schema 合计 908 token，零收益，且减少 agent 能力 |
| 开启 `micro_compact` | 每轮重写历史、破坏 prompt cache 前缀，净收益为负 |
| 关闭 / 削弱缓存 | 命中率 98.9%，是最优状态 |
| 换更小的模型省 token | 产出品质优先于成本 |
| 削减 `AGENTS.md` / 协议内容省 token | 治理内容不是 token 瓶颈 |
| 依赖模型窗口元数据做阈值 | Hermes 硬编码（MiniMax M3 = 1M）与 models.dev（512K）冲突；用 `threshold_tokens` 绝对封顶 |
| 虚构供应商账单金额 | 本地代理不提供计费数据 |
| 为凑数新增能力 | 能力数只 +1（→66） |
| 未经用户确认把 REQ-016 改成 `agreed` | 目标铆钉确认权在用户 |

---

## 6. 本简报未覆盖、需维护智能体自行判断的部分

1. **`threshold_tokens = 200000` 是否最优** —— 模拟显示 120,000 可到 0.52x，但压缩更频繁、体验更差。请基于 `CONTEXT-PIPELINE.md` 的「durable state first」原则判断是否更激进，或保留 200,000 并在 `limits` 中说明理由。
2. **`protect_last_n = 14` 是否够** —— 若 A5 回归出现偏差，这是第一个回调旋钮。
3. **是否推动 Hermes 上游修改 `context_compressor.py`** —— 任务 3 若在项目侧做代理，是 workaround；上游修改是正解但需另开任务并评估对所有用户的影响。请给出建议并标注。
4. **能力 ID 命名** —— 已建议 `meta-token-budget`（与 `meta-qc-gate` / `meta-router` / `meta-no-fabrication` 风格一致）。若 registry 另有命名约定，以 registry 为准。

---

## 7. 协作约定

- 遵循 `protocols/FILE-DRIVEN-ENGINEERING.md`：**先改文件、追加 `history.jsonl`（create-only），再执行**
- 需求点落盘为 `REQ-NNN` 条目，状态 `draft`，回指不到需求 ID 的工作单元不执行
- 交付前对账：产出物 ↔ 需求 ID ↔ 证据
- 报告落款：`Ming Peng | 放眼看世界，明天更美好`
- 报告 / PPT / 图表字体：微软雅黑（Microsoft YaHei）
- 专业输出标注「AI 辅助生成，需人工审核」
- 部署前核对许可证与费用；**任何付费工具需用户先确认**

---

*AI 辅助生成，需人工审核*

Ming Peng | 放眼看世界，明天更美好
