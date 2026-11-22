---
name: requirements-anchoring
description: "需求锚定：输出形式与定义先行，需求点落盘为锚点，工作单元回指需求 ID。"
metadata:
  version: "1.0.0"
---

# 需求锚定（Requirements Anchoring）

> **这是所有 Agent 通用的工作逻辑**，不是某个项目的专有流程。
> 治理唯一源：`${AGENTOS_HOME}`。本文件只提供方法，不复制治理正文。

---

## 0. 一句话

**沟通产生需求点 → 需求点沉淀成文件 → 文件成为锚定物 → 所有工作单元回指锚点。**
没有落盘的需求点不算需求；没有回指锚点的工作单元算失焦。

---

## 1. 为什么需要它

多轮沟通的失败模式不是"做不出来"，而是**做出来了但不是要的那个**：

| 失败模式 | 表现 | 锚定法如何挡住 |
|---|---|---|
| 需求只存在于对话里 | 换个会话就丢 | 需求在文件里，跨会话可读 |
| 沟通中被悄悄改写 | Agent 按自己的理解推进 | 每次改写都要回写文件并留痕 |
| 范围悄悄膨胀 | "顺便也把这个做了" | 新增项必须进文件才能开工 |
| 交付时不知道对不对 | 没有判断依据 | 每条需求有验收标准与状态 |
| 中途换人/换 Agent | 上下文断档 | 文件是交接物，不依赖任何人的记忆 |

**核心原则：文件是事实源，对话是澄清手段。**
对话用来产生和澄清需求点；文件用来锚定和判定。

---

## 1.5 第零步：先定"输出形式与定义"（目标铆钉）

**在任何需求点之前，先和用户确认这次要产出什么、产出成什么样。**
这一项就是**目标铆钉** —— 它决定后面所有需求点的写法、验收方式和交付形态。

### 为什么必须最先定

- 输出形式决定需求点怎么写。产出是一份 JSON 还是一份报告，需求点的粒度完全不同。
- 输出定义决定验收标准怎么写。"输出一份 DFM 报告"和"输出一份符合 schema 的 DFM JSON"是两个不同的需求。
- 铆钉定错了，后面每一条需求都会跟着歪，返工的是全部内容而不是一处。

### 要确认的四件事

| # | 要确认 | 例子 | 不确认的后果 |
|---|---|---|---|
| 1 | **产出物清单** | 要交付哪几个文件/界面/接口 | 做完了不知道交付什么 |
| 2 | **每项的格式** | JSON / Markdown / STEP / HTML；字段、章节、表格结构 | 每次产出格式都变，无法比对 |
| 3 | **每项的定义** | 每个字段/章节**是什么**、**怎么判定对错** | 字段名对但含义错，验收才发现 |
| 4 | **受众与呈现** | 给谁看、落款、字体、语言、是否要图 | 交付了但形态不对 |

### 第 4 项的默认值（AgentOS 已有规定，不必重新发明）

- 落款：`${OWNER_SIGNATURE}`
- 字体：微软雅黑（Microsoft YaHei）
- 对外交付物：中英双语各一套
- 数据：每个数字标注来源性质，未核实的标 `unknown`

### 落地：铆钉写在锚点文件最前面

```markdown
# REQUIREMENTS — <项目名>

## 目标铆钉（Output Contract）

| 产出物 | 格式 | 定义（是什么 / 怎么判定对错） | 受众 | 状态 |
|---|---|---|---|---|
| DFM 报告 | JSON | 顶层 overall_verdict + analysis_metadata + issues[]；每条 issue 引用真实规则 ID；占位规则须标注 | 工艺工程师 | draft |
| 修改后模型 | STEP | 原模型 + 直接几何修补；体积变化 ≤30%；is_valid=true | 工艺工程师 | draft |
| DFMEA | Markdown | AIAG-VDA 七步法表格；S/O/D 为 assumption 并标信息缺口 | 质量工程师 | draft |

- 落款：${OWNER_SIGNATURE}
- 字体：微软雅黑（Microsoft YaHei）
- 语言：中文 + 英文各一套
```

### 铆钉的生命周期

| 阶段 | 行为 |
|---|---|
| 起步 | **第一时间**与用户确认，状态 `draft` |
| 推进中 | 可以修正，但每次修正都要用户确认 + 追加 `history.jsonl` |
| 已开工 | 修正要**先解冻再改**，并评估已产出物是否需要重做 |
| 收口 | 逐项核对产出物是否符合铆钉定义；不符即失焦，显式报告 |

**修正权归用户。** Agent 可以提出更好的格式建议，但不能自己改了就开工。
这与需求状态机一致：`draft` -> `agreed` 只有用户能确认。

### 铆钉未确认时怎么办

不阻塞启动，但**必须在第一份交付说明里写明"目标铆钉仍为 draft"**，
并且不得声称交付格式已符合要求。

---

## 2. 三类文件（每个项目一套）

```
<PROJECT>/
├── REQUIREMENTS.md          # ① 需求锚点（主文件，SSOT）
│                              含「目标铆钉」节 —— 排在最前
├── .agentos/
│   ├── requirements/
│   │   ├── history.jsonl    # ③ 变更台账（create-only）
│   │   └── open-questions.md # ② 待澄清问题（沟通中持续补充）
│   ├── tasks/               # 任务契约（AgentOS 既有）
│   └── evidence/claims.jsonl # 证据账本（AgentOS 既有）
```

### ① `REQUIREMENTS.md` —— 锚点

唯一的目标事实源。**每个工作单元必须回指其中一条需求 ID。**

```markdown
## REQ-001 [agreed] <需求陈述>
- **验收**：<可判定条件>
- **来源**：<用户原话（日期）/ 推导 / 提案>
- **优先级**：P0
- **依赖**：<其他 REQ ID>
- **证据**：<claim_id>
```

### ② `.agentos/requirements/open-questions.md` —— 待澄清问题

沟通中产生但**尚未确认**的问题。问题一旦落盘就不会被遗忘。

### ③ `.agentos/requirements/history.jsonl` —— 变更台账

需求文件的每次实质变更都留一行，**create-only**。
字段规范见 [references/anchor-file-format.md](references/anchor-file-format.md)。

---

## 3. 工作流程

### ① 起步：先钉输出形式，再落盘需求

**顺序不能反。**

1. **先和用户确认目标铆钉**（产出物清单 / 格式 / 定义 / 受众）-> 写进
   `REQUIREMENTS.md` 的「目标铆钉」节，状态 `draft`。
2. **再沉淀需求点** -> 逐条写进同一文件，状态 `draft`。
3. **再动手做技术工作。**

先做技术、后定格式，是返工量最大的顺序。

### ② 沟通中：需求点即时沉淀

| 情况 | 动作 |
|---|---|
| 明确的新需求 | 加一条 `REQ`，状态 `draft` |
| 澄清后的明确需求 | 状态改 `agreed`，填验收标准 |
| 范围外的想法 | 写进「需求边界」排除项，**不做** |
| 用户没答的问题 | 写进 `open-questions.md`，状态 `open` |
| 与现有需求冲突 | 在文件里标 `conflict`，**停下来问**，不自行裁决 |

**不要在对话里回答完就翻页。** 需求点必须落盘才算存在。

### ③ 派工：每个单元回指需求 ID

AgentOS 的任务契约本来就有 `task / goals / constraints` 三个输入角色。
在此之上，**每个 Unit 的描述必须写明它服务的 REQ ID**：

```markdown
## Unit U-03：实现规则库占位值替换
- 服务需求：REQ-007（工艺能力表接入后解除 PARTIAL_PLACEHOLDER）
- 输入：kb/dfm_rules.json、用户工艺能力表
- 完成条件：knowledge_status 变为 USER_OWNED_VERIFIED，且 E3 规则数为 0
- 验证：python scripts/kb_build.py 后 grep -c '"E3"' kb/dfm_rules.json
```

**没有 REQ ID 的 Unit 不许开工** —— 它要么是需求外的工作，要么是需求没写清。

### ④ 执行中：发现需求变了，先改文件

| 情况 | 动作 |
|---|---|
| 执行中发现需求描述有误 | 改文件（留 history），通知用户，再继续 |
| 执行中发现缺信息 | 记 `open-questions.md`，该 Unit 挂起，不猜 |
| 执行中产生新需求 | 新增 REQ（`draft`），当前 Unit 不自动扩大范围 |
| 用户口头改了需求 | **立刻回写文件**，再继续执行 |

**顺序永远是：先落盘，后执行。** 反过来做就会出现"执行了但锚点没更新"的失焦。

### ⑤ 收口：锚点对账

交付前逐条核对：

1. 每条 `agreed`/`frozen` 需求 → 有对应的产出物与证据？
2. 每个产出物 → 能回指到某条 REQ ID？
3. `open-questions.md` 里还有 `open` 状态的问题吗？（有就要在交付说明里列出）
4. 需求文件的 hash 变了吗？变了就要刷新 project-import-manifest。

**对不上就是失焦，必须显式报告，不能默默交付。**

---

## 4. 需求状态机

```
draft ──(用户确认)──> agreed ──(冻结)──> frozen
  │                     │                    │
  │                     └──(被新需求替代)──> superseded
  └──(澄清后确认)────────────────────────────> agreed
```

- 只有用户能确认 → `agreed`。Agent 自行判定不算。
- `frozen` 的需求**不得**在执行中修改；要改必须先解冻并记录原因。
- `superseded` 保留原文，不删除（历史可追）。

---

## 5. 通用性

这套逻辑**不属于任何项目**。它是 AgentOS 的横切方法，
适用于：金属制程面板、STM32 项目、PCB 项目、任何多轮沟通的工程任务。

| 场景 | 怎么用 |
|---|---|
| 新项目启动 | 先建 `REQUIREMENTS.md`，再拆任务 |
| 长周期项目 | 每次会话开始先读锚点文件；结束时回写 |
| 多 Agent 协作 | 每个 Agent 读同一份锚点，各写自己的 Unit |
| 用户临时提新想法 | 进 `open-questions.md` 或新增 `draft` REQ，不直接开工 |
| 交付验收 | 按锚点逐条对账，产出物回指 REQ ID |

**跨项目复用**：锚点文件本身跟着项目走（每个项目一份），
但**方法**来自 AgentOS 的这一个 bundled skill，各项目不复制正文。

---

## 6. 与 AgentOS 其他机制的关系

| AgentOS 机制 | 与锚定法的关系 |
|---|---|
| `req-spec-freeze` | 冻结需求 → `frozen` 状态的需求集 |
| `req-acceptance` | 每条 REQ 的验收标准 → 该能力的产出 |
| `req-trace` | REQ ID → Unit → 证据 的追溯矩阵 |
| `km-decision-log` | 需求变更的决策记录（与 history.jsonl 互补） |
| `plan-wbs` | 任务树按 REQ 分组 |
| `plan-gate` | 阶段评审以锚点对账为门禁 |
| `meta-no-fabrication` | 需求的"来源"字段必须可溯源 |

**本 provider 为上述既有能力提供可执行方法**，不新增能力 ID。

---

## 7. 常见失败及处理

- **需求只在对话里，文件没写** → 违反核心原则。立刻落盘，否则该工作单元不算开工。
- **文件写了但没回指** → 每个 Unit 必须带 REQ ID，见 §3③。
- **Agent 自行把 draft 改成 agreed** → 越权。只有用户能确认。
- **执行中悄悄扩大范围** → 新增项必须走 `draft` REQ 或排除项，不能顺手做。
- **冻结后又被改** → 必须先解冻并记 `history.jsonl`。
- **需求变了但没人知道** → 每轮沟通结束回写文件 + history。
- **把 open question 当成已知继续做** → 该 Unit 挂起并显式说明缺什么。
- **多个需求互相冲突** → 标 `conflict` 停下来问，不自行裁决。
- **交付时漏对账** → 收口步骤不可省；漏了要补，不能默认算通过。

---

## 8. 客户端薄指针

客户端（Hermes 等）放**薄指针**时，目录名必须带 `-pointer` 后缀
（`requirements-anchoring-pointer`），否则会在 `resolve_provider()` 中遮蔽本 provider。
详见 [references/anchor-file-format.md](references/anchor-file-format.md) §11。

---

## 9. 引用

- 锚点文件的完整写法与字段规范：[references/anchor-file-format.md](references/anchor-file-format.md)
- 收敛流程、状态机、追溯矩阵：[references/convergence-and-traceability.md](references/convergence-and-traceability.md)
- 需求文件模板：[assets/templates/REQUIREMENTS.template.md](assets/templates/REQUIREMENTS.template.md)
- 待澄清问题模板：[assets/templates/open-questions.template.md](assets/templates/open-questions.template.md)
- 变更台账格式：[references/anchor-file-format.md](references/anchor-file-format.md#7-变更台账historyjsonl)

---

落款：`${OWNER_SIGNATURE}`
字体：微软雅黑（Microsoft YaHei）
