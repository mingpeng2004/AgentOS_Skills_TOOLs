# 运行时性能治理（卡顿诊断与修复）

> 用于任何「本地 agent 变慢、下午尤其明显、重启后好转」的现象。
> **目标：定位到可测量的根因，而不是猜测。**

**来源**：2026-10-26 Hermes 实战诊断（本机实测，全部结论有日志/代码证据）。

---

## 0. 排除法先行

按这个顺序排除，**不要跳过**——本机案例中三个最直觉的猜测全是错的：

| 猜测 | 怎么测 | 本机结果 |
|---|---|---|
| 内存不足 | 查物理内存/可用/负载 | 59.8 GB 总、25.6 GB 可用、57% 负载 → **排除** |
| 上下文太大 | **按输入规模分组统计 API 延迟** | 50K 输入中位 6.30s vs 350–500K 输入中位 6.90s → **无关，排除** |
| 工具慢 | 按工具名统计耗时 | terminal 中位 3.27s、execute_code 1.24s → **排除** |

> **「API 延迟与输入规模无关」是最关键的一条**：说明 prompt cache 生效，
> 大上下文本身**不卡**。卡的是别的东西。不要在上下文长度上浪费时间。

---

## 1. 真正会拖垮长会话的两个机制

### 1.1 上游 429 → 硬编码超长退避

```
ERROR: 429 - MiniMax: 已达到 Token Plan 速率限制
WARNING: Retrying API call in 600.0s (attempt 1/3) thread=bg-review:2
```

`agent/retry_utils.py` 里 `RETRY_AFTER_CAP_S = 600.0` —— **硬编码常量，无配置项**。
上游一旦返回长 `Retry-After`，线程就睡 10 分钟。

**关键判定**：统计所有 `Retrying API call in` 的 `thread=` 字段。
本机 11/11 次全在 `bg-review:*`，**前台 0 次**。
→ 前台感觉到的慢，是后台线程在抢同一个本地代理。

### 1.2 每次启动都做网络探测

```
INFO: Could not detect context length for model 'MiniMax-M3' at http://127.0.0.1:15721
      - defaulting to 256,000 tokens (probe-down).
```

本机 17 次 probe-down，其中一次阻塞 **95 秒**。
根因是那个端点的 `/v1/models` 返回 `{"models":[]}` 空列表 → 探测必然失败。

---

## 2. 修复动作（都可在配置层完成，无需改上游源码）

### 2.1 显式声明上下文窗口 → 跳过探测

```yaml
model:
  default: <provider>/<model>
  context_length: 1000000
```

`get_model_context_length()` 的**第 0 优先级**是 `config_context_length`，
直接 return，**完全不碰网络**。

实测：`1324.5 ms → 0.0 ms`，probe-down `17 → 0`。

> 附带收益：消除了「Hermes 硬编码目录说 1M，models.dev 说 512K」的元数据冲突。

### 2.2 后台 review —— 开启但压住输入规模

```yaml
auxiliary:
  background_review:
    enabled: true
    max_input_tokens: 150000     # 关键
    timeout: 60
```

**`max_input_tokens` 是关键**：默认值是「review 模型上下文窗口的 **75%**」
= 75 万 token（1M 窗口）。后台 review 的 fork 会重放完整对话，
本机实测单次输入 **341,875 / 350,118 token** —— 这就是 429 的直接诱因。

压到 15 万后与前台主会话同量级，**复核层保留，限流不再被触发**。

运行时验证：
`load_background_review_settings()["enabled"]`、
`_review_input_token_budget()` → 实际预算值。

### 2.3 SQLite WAL 截断

```python
con.execute("PRAGMA wal_checkpoint(TRUNCATE)")   # TRUNCATE 才能真正截断，PASSIVE 可能返回 busy
con.execute("PRAGMA optimize")
```

本机 `state.db-wal` 5.59 MB → 0。运行中会涨回 2–3 MB（每条消息要写
FTS5 全文索引 + trigram 三元组索引），**重启即截断**，属正常。

### 2.4 日志轮转

`logs/agent.log` 长期增长会拖慢排查与启动扫描。轮转后保留最近 N 行，
旧内容改名 `.rotated` 保留作证据。

---

## 3. 测量脚本骨架

```python
# 按输入规模分桶统计 API 延迟 —— 判断"上下文大是否等于慢"
api_re = re.compile(r"API call #(\d+): .*?in=(\d+).*?latency=([\d.]+)")
for lo, hi in [(0,50_000),(50_000,150_000),(150_000,250_000),
               (250_000,350_000),(350_000,500_000),(500_000,10**9)]:
    b = [lat for lat, inp in rows if lo <= inp < hi]
    print(lo, hi, len(b), median(b))
```

```python
# 并发重建：start = 日志时刻，end = start + latency
events = [(t, +1), (t + latency, -1)]
# → 峰值并发、本地代理排队时长
```

```python
# 谁在重试（前台 vs 后台）
for l in lines:
    if "Retrying API call in" in l:
        print(re.search(r"thread=(\S+)", l).group(1))
```

---

## 4. 观测指标基线（本机，供对照）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| API 延迟中位 | 6.30s | 3.50s |
| API 延迟 p90 | 22.90s | 5.60s |
| 单次输入中位 | 257,582 | 149,439 |
| 429 / 长退避 | 22 次 | 0 次 |
| probe-down | 17 次 | 0 次 |
| 上下文探测耗时 | 1324.5 ms | 0.0 ms |

---

## 5. 禁区

| 不要做 | 原因 |
|---|---|
| 关闭 prompt cache | 命中率实测 98.9%，本来就是健康的 |
| 裁剪工具 schema | 全部工具 schema 仅 908 token，零收益且损失能力 |
| 启用 `micro_compact` | 每轮破坏 prompt cache，得不偿失 |
| 自动模型分流 | **用户明确拒绝**；需要时自行切换 |
| 删除用户的本地 provider | 可能是他自己的另一个代理，不是垃圾 |
| 擅自配置账号凭据 | token 类凭据必须用户本人授权 |
| 改 Hermes 上游源码改 `RETRY_AFTER_CAP_S` | 配置层可控就别动源码；上游改动会随版本升级丢失 |

---

## 6. 安装二进制工具：走官方 pm，不要手工解压

```bash
hermes pm install --tools-only          # 工具闭包
```

单包用官方 API（会按 `pm/lock.json` 的锁定版本下载、校验 SHA256、注册 PATH）：

```python
import pm.install as PI
PI.ensure("gh", explicit=True, verify=True)
```

**为什么不能手工装**：Hermes 的 `tools/facts.json` 驱动 PATH 组装。
手工解压的二进制不在 facts 里 → 不进 PATH → `gh auth token` 这类**裸命令调用会失败**。
（本机先手工装了 v2.103.2，`pm doctor` 报 "outdated" —— 因为 Hermes 清单本就锁定 v2.97.0。）

---

## 7. 凭据接入：让 agent 复用用户的 CLI 登录

Hermes 的 `hermes_cli/github_api.py`：

```python
def github_token():
    return github_token_from_env() or _gh_cli_token()   # GITHUB_TOKEN/GH_TOKEN → gh auth token
```

所以**用户登录一次 CLI，agent 侧自动生效**，不必把 token 字符串写进任何配置。

设备码流程（用户在浏览器完成授权，agent 不代替登录）：

```python
# POST https://github.com/login/device/code
#   client_id = GitHub CLI 的公开 OAuth App ID
#   -> user_code 给用户，device_code 给 agent 轮询
# POST https://github.com/login/oauth/access_token
#   grant_type = urn:ietf:params:oauth:grant-type:device_code
#   遇 authorization_pending 继续等，slow_down 则拉长间隔
```

---

## 8. 交付前自检

- [ ] 三个直觉猜测都实测排除过（有数字，不是印象）
- [ ] 重试线程分布查过（前台还是后台？）
- [ ] 配置改动**全局 + 每个 profile** 都写了（profile 不回退全局）
- [ ] 用 Hermes 自己的加载器验证配置被解析到（不是只看 YAML 长得对）
- [ ] 运行时函数实测生效（不只是配置项存在）
- [ ] 备份存在，回滚路径明确
- [ ] 修前修后对比有数字

---

*AI 辅助生成，需人工审核*

${OWNER_SIGNATURE}
