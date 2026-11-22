# 收敛流程与追溯

> 适用能力：`req-spec-freeze`、`req-acceptance`、`req-trace`、`km-decision-log`
> 本文定义需求如何**收敛**、如何**防失焦**、如何**追溯**。

---

## 1. 收敛的本质

收敛不是"想清楚了"，而是**分歧被显式化并关闭**。

| 状态 | 分歧 | 处理 |
|---|---|---|
| 未记录 | 藏在 Agent 的理解里 | ❌ 最危险 —— 静默失焦 |
| 已记录为 open question | 写在文件里，等用户 | ✅ 可收敛 |
| 已裁决 | 写进 REQ，`agreed` | ✅ 已收敛 |

**"用户没反对"不等于"用户同意"。** 只有明确确认才算收敛。

---

## 2. 一个 Unit 的完整生命周期

```
① 读锚点      → 找到本 Unit 服务的 REQ ID
② 核对范围    → 本 Unit 的产出物能回指该 REQ？不能 → 停下
③ 执行        → 一 Unit 一动作
④ 验证        → 立即跑检查，留证据路径
⑤ 落盘        → 更新锚点（若有需求变更）+ 证据账本 + 任务状态
⑥ 回指        → 产出物关联 REQ ID 与 claim_id
```

**⑤ 在 ⑥ 之前**：先落盘，再回指。反了就又出现"做了但没记录"。

---

## 3. 失焦的四个早期信号

见到这些信号立即停下核对锚点，不要继续往下做：

| 信号 | 说明 | 动作 |
|---|---|---|
| **做不出验收标准** | 不知道什么算完成 | 回锚点找 REQ；找不到就是需求缺失，补 `draft` REQ |
| **产出物回指不到 REQ** | 不知道为谁做 | 范围外工作 → 删或补需求 |
| **连续两轮在改实现方案而非结果** | 目标本身在动 | 回锚点确认 REQ 是否已变；变了先改文件 |
| **用户的话与文件里的 REQ 不一致** | 两份事实源 | 停下来问用户，以文件为准更新（留 history） |
| **产出物形态与目标铆钉对不上** | 锚点本身错了 | 回铆钉节核对；先改铆钉（用户确认 + history），再重做产出 |

**"用户的话 vs 文件"冲突是最危险的失焦** —— 因为两个来源都看起来权威。
规则：**文件是事实源，但用户的最新表述优先** —— 所以要立刻回写文件，而不是继续按旧文件做。

---

## 4. 需求变更的处理

### 4.1 谁可以改

| 变更类型 | 需要谁批准 |
|---|---|
| `draft` → `agreed` | 用户 |
| `agreed` → `frozen` | 用户 |
| `agreed` 内容修正（澄清歧义，不改意图） | 用户知悉即可，需记录 |
| `agreed` 内容修改（改意图） | 用户确认 + 解冻 |
| `frozen` 的任何修改 | 用户解冻 + 记录原因 |
| 新增需求 | 用户确认优先级后才进 `agreed` |

### 4.2 变更流程

```
检测到变更 → 判断类型 → 必要时问用户 → 改 REQUIREMENTS.md
           → 追加 history.jsonl → 刷新 overlay 哈希 → 通知受影响 Unit
           → 重新评估受影响 Unit 是否仍需执行
```

**被替代的需求不删除**，标 `superseded` 并注明替代者。

### 4.3 变更影响分析

改一条需求时，主动检查：

- 依赖它的 REQ 是否还成立？
- 已完成的 Unit 是否产生了需要作废的产出物？
- 已冻结的契约（`.agentos/contract/`）是否需要修订？
- 已开的看板任务是否要重新派发？

---

## 5. 追溯矩阵

### 5.1 三层追溯

```
需求层   REQ-007  用真实工艺能力表替换占位阈值
   ↓
工作层   U-03  实现占位值替换（服务需求: REQ-007）
   ↓         U-04  回归验证（服务需求: REQ-007）
证据层   claim-002  kb/provenance.json 与源文件哈希一致
```

**三层缺一，交付就要说明缺口在哪一层。**

### 5.2 矩阵表

| REQ ID | 状态 | Units | 产出物 | 证据 | 覆盖 |
|---|---|---|---|---|---|
| REQ-007 | agreed | U-03, U-04 | kb/dfm_rules.json | claim-002 | ✅ |
| REQ-009 | draft | — | — | — | ⏳ 未开工 |
| REQ-012 | agreed | U-07 | reports/x.pdf | claim-009 | ✅ |

**`覆盖` 列是交付前必看的**：`⏳` 表示需求还没做，`❌` 表示做了但没证据。

### 5.3 生成的命令

```bash
# 从锚点文件与任务目录生成追溯矩阵
python - <<'PY'
import json, os, re, glob
proj = r"<project root>"
reqs = {}
cur = None
for line in open(os.path.join(proj, "REQUIREMENTS.md"), encoding="utf-8"):
    m = re.match(r"^##\s+(REQ-\d+)\s+\[(\w+)\]", line)
    if m:
        cur = m.group(1)
        reqs[cur] = {"status": m.group(2), "units": [], "evidence": []}
    elif cur and "- **证据**：" in line:
        reqs[cur]["evidence"] += re.findall(r"(claim-[\w-]+)", line)
for f in glob.glob(os.path.join(proj, ".agentos", "tasks", "*.md")):
    txt = open(f, encoding="utf-8").read()
    for unit, body in re.findall(r"##\s+(U-\d+)[^\n]*\n(.*?)(?=\n## |\Z)", txt, re.S):
        for rid in re.findall(r"(REQ-\d+)", body.split("- **证据**")[0]):
            if rid in reqs:
                reqs[rid]["units"].append(unit)
for rid, r in sorted(reqs.items()):
    cover = "✅" if r["units"] and r["evidence"] else ("⏳" if r["status"]=="draft" else "❌")
    print(f"{rid:12s} {r['status']:10s} units={r['units']} evidence={r['evidence']} {cover}")
PY
```

---

## 6. 多 Agent 协作

多个 Agent（或多个子智能体）共享同一份锚点：

| 规则 | 原因 |
|---|---|
| 只有一个写入者负责改 `REQUIREMENTS.md` | 避免并发写冲突；其他 Agent 通过 open-questions 提需求 |
| 每个 Agent 只改自己 Unit 对应的产出物 | 冲突面最小 |
| 每个 Agent 在自己的 Unit 描述里写明服务的 REQ ID | 可核对归属 |
| Agent 发现需求有问题 → 写 open question | 不自行改别人的需求 |
| 每个 Agent 的产出物落盘后追加自己的 claim | 证据账本只追加 |

**冲突不靠"最后写入覆盖"解决** —— 那是 AgentOS 的硬规则。
需求冲突进 `open-questions.md` 标 `conflict`，由协调者裁决。

---

## 7. 交付前对账清单

```
[ ] 目标铆钉每项产出物 → 都产出了？格式与定义逐项符合？
[ ] 每条 agreed/frozen 需求 → 有产出物 + 证据？
[ ] 每个产出物 → 能回指到 REQ ID？
[ ] open-questions.md 里还有 open 项吗？（列在交付说明里）
[ ] 需求文件的 overlay 哈希刷新了吗？
[ ] 需求边界里的排除项，有被误做吗？
[ ] 追溯矩阵里没有 ❌ 吗？
[ ] 交付说明里写了「未完成的需求」吗？
```

**对不上就显式报告失焦点**，不要默默交付。

---

## 8. 常见失败及处理

- **需求只存在于对话** → 落盘，否则不算开工。
- **Agent 自升 agreed** → 只有用户能确认。
- **改了需求没通知受影响 Unit** → 变更流程要走完。
- **执行中静默扩大范围** → 新增项必须走 `draft` REQ 或排除项。
- **用户在对话里改了需求但没人回写文件** → 立刻回写 + history。
- **冲突靠最后写入覆盖** → 进 open question，由协调者裁决。
- **交付时不做对账** → §7 不可省。
- **追溯矩阵没有 ❌ 但实际有缺口** → 对账要逐条走，不能凭印象。

---

落款：`${OWNER_SIGNATURE}`
字体：微软雅黑（Microsoft YaHei）
