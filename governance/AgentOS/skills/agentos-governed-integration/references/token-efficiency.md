# Token 效率（全局策略）

> 用于任何长时间、多轮、工具密集的会话。**目标：降低 token 消耗，不降低产出品质。**

---

## 1. 先测量，再调参

不要凭感觉判断 token 花在哪。Hermes 把真实用量记在 `state.db`：

```bash
python scripts/token_audit.py --session <id>
```

它给出：

| 指标 | 含义 | 为什么重要 |
|---|---|---|
| `cache_read / API 调用` | **每轮重读的上下文前缀** | **唯一的决定性指标** |
| `context_composition` | 工具结果 / assistant / user 各占多少 | 决定该优化哪一层 |
| `cache_hit_rate` | 缓存是否生效 | 高（>95%）说明缓存正常，不是优化点 |
| `base_count` | 系统提示词 + 工具 schema | 通常只有几百 token，**不是瓶颈** |

---

## 2. 成本结构

```
总成本 ≈ (上下文前缀长度 × 调用次数) × 单价 + 输出 token
```

**前缀长度是乘数。** 单次请求再小，前缀涨到 50 万就是每次调用付 50 万。

反过来：**裁剪工具 schema 几乎没用** —— Hermes 用 deferred 机制，schema 不进 prompt。
实测系统提示词 + 全部工具 schema = **908 token**。裁工具集零收益且减少 agent 能力。

---

## 3. 配置层（`compression` 段）

profile **不回退**全局 config.yaml —— 运行时 `get_config_path()` 指向
profile 自己的目录。所以**全局和每个 profile 都要写**。

| 键 | 默认 | 建议 | 理由 |
|---|---|---|---|
| `threshold` | 0.50 | **0.20** | 1M 窗口下 0.50 = 50 万才触发，实测常常根本不触发 |
| `threshold_tokens` | None | **200000** | 绝对上限，与 ratio 取低者，任何模型都封顶 |
| `target_ratio` | 0.20 | **0.15** | 压缩后保留 15% 尾部 |
| `protect_last_n` | 20 | 14 | 尾部保留略减，仍足够承载近期细节 |
| `min_tail_user_messages` | 1 | **2** | 保证用户原始消息不被压缩 |
| `proactive_prune_tokens` | 0 | **48000** | 确定性裁剪器，**无 LLM 调用** |
| `proactive_prune_min_result_chars` | 8000 | 6000 | 覆盖更多中等大小的工具结果 |
| `micro_compact` | false | **保持 false** | 每轮重写历史、破坏 prompt cache 前缀，净收益为负 |

### 3.1 为什么 `proactive_prune_tokens` 比降阈值更重要

官方注释说得很直白：

> `proactive_prune_tokens`: ... independent of `threshold` (**which rarely fires on large
> windows, so old tool output is re-sent every turn**)

裁剪器把旧工具结果**降级为有界摘要**，且：
- 保留可回溯线索：`web_extract` 保留 URL，`skill_view` 保留 skill 名并提示可重新加载
- **不改写 tool_calls 的参数**（执行记录字节级一致）
- 保护刚加载的 skill、保护的尾部、待处理的工具轮次

实测：一次裁剪减少 **29.6% 字符（≈10.4 万 token）**，52 个工具结果被降级。

### 3.2 `micro_compact` 为什么不开

它每轮都重写 sent history，**每轮破一次 prompt cache**。缓存命中时前缀是折扣价，
每轮破一次等于每轮付全价。官方注释也建议只在摊销收益超过缓存折扣时才开。

---

## 4. 行为层（更大的大头）

配置治标，行为治本。**一次工具调用输出超过约 3000 字符，先问自己真正需要哪几行。**

| 做法 | 替代 |
|---|---|
| `read_file` 读整个大文件 | `offset` / `limit` 只读需要的段 |
| 工具输出直接回显 | 先用代码过滤/聚合，再回显结论 |
| 把 200 行代码贴进上下文 | 只贴关键函数签名 + 差异 |
| 反复 `ls` / `find` 探索 | 一次成型扫描并落盘 JSON，后续读 JSON |
| 每个小问题单独调一次工具 | 能批量的合并成一次 `execute_code` |
| 引用外部网页全文 | `web_extract` 带 `char_limit`，或只取需要的片段 |

**探索性工作落盘**：扫描结果写成 JSON，后续所有查询读那个 JSON，
而不是重新跑一遍扫描命令。这是最容易忽略的大头。

---

## 5. 交付前自查

- [ ] 有工具调用产生了本可避免的大段输出？
- [ ] 同一份文件被反复读取？
- [ ] 探索性命令是否落盘成 JSON 供复用？
- [ ] 长任务的中间输出是否只报结论、不报过程？

---

## 6. 验证与回滚

```bash
python scripts/token_audit.py --session <id>   # 对比前后
```

回滚：备份在 `$HERMES_HOME/backups/config/` 下，把 `__config.yaml` 复制回对应位置。

**若质量下降**：调高 `protect_last_n`、调低 `proactive_prune_min_result_chars`，
或关掉 `proactive_prune`（保留降阈值）。

---

## 治理任务简报

AgentOS 侧的实施任务（新建 `meta-token-budget` 能力、`protocols/TOKEN-BUDGET.md`、
驱逐先落盘对齐 `CONTEXT-PIPELINE.md`、跨 client 落地、token 台账）见：

`AgentOS/reports/TOKEN-BUDGET-GOVERNANCE-BRIEF.md`（任务 ID `token-budget-governance-v1`）

---

落款：`${OWNER_SIGNATURE}`
字体：微软雅黑（Microsoft YaHei）
