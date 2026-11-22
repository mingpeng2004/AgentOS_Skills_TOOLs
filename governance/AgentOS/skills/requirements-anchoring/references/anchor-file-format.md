# 锚点文件格式规范

> 适用能力：`req-spec-freeze`（冻结）、`req-acceptance`（验收）、`req-trace`（追溯）
> 本文定义需求锚点文件与配套文件的**字段规范**。工作流程见 SKILL.md。

---

## 1. 文件位置与命名

| 文件 | 路径 | 生命周期 |
|---|---|---|
| 需求锚点 | `<PROJECT>/REQUIREMENTS.md` | 长期，SSOT |
| 待澄清问题 | `<PROJECT>/.agentos/requirements/open-questions.md` | 长期 |
| 变更台账 | `<PROJECT>/.agentos/requirements/history.jsonl` | **create-only**，只追加 |

锚点文件名固定为 `REQUIREMENTS.md`，位于**项目根**。
理由：AgentOS 的项目入口是根目录 `AGENTS.md`，SSOT 与入口同层最容易被发现。

---

## 2. 需求 ID

```
REQ-<NNN>
```

- 三位数字，**只增不改**：一旦分配就永久占用，删除的需求也不复用编号。
- 编号按创建顺序，不按优先级。
- 需求 ID 一旦出现在 Unit、证据、交付物里，就成为长期引用。

**禁止**：复用编号、改写编号含义、把两个需求合并成一个 ID。

---

## 3. 需求条目字段

```markdown
## REQ-007 [agreed] 用用户实际工艺能力表替换 DFM 规则库的占位阈值
- **验收**：kb/dfm_rules.json 的 knowledge_status == "USER_OWNED_VERIFIED"；
  evidence_level == "E3" 的规则条目数为 0
- **来源**：用户原话（2026-10-26 确认"接入真实工艺能力表后，占位规则必须被替换"）
- **优先级**：P0
- **依赖**：REQ-003（知识库可溯源重建）
- **证据**：claim-002（kb/provenance.json 的 SHA256 一致性）
```

| 字段 | 必填 | 取值 | 规则 |
|---|---|---|---|
| 标题行 | 是 | `## REQ-NNN [状态] 陈述` | 陈述用动词开头，可验证 |
| 验收 | 是 | 可判定条件 | 必须是**能判真假**的条件；"体验好"不是验收标准 |
| 来源 | 是 | 用户原话 / 推导 / 提案 | 不得写"推测""应该是"；提案类必须标明未确认 |
| 优先级 | 是 | P0 / P1 / P2 | P0 未完成则不得交付 |
| 依赖 | 否 | 其他 REQ ID | 依赖成环即 invalid |
| 证据 | 否 | claim_id | 指向 `.agentos/evidence/claims.jsonl` |

### 3.1 验收标准的写法

| 不合格 | 合格 |
|---|---|
| 性能要好 | p95 延迟 < 200ms |
| 要支持多种工艺 | `cnc_milling` / `die_casting` / `stamping` 三种工艺各有一组通过用例 |
| 界面要美观 | 走查清单 8 项全部通过，其中字体为微软雅黑 |
| 错误要处理 | 非法输入返回 `blocked` 并指明缺失字段 |

**判据**：两个人独立看这条验收，能不能得出一样的结论。能，就是合格。

### 3.2 来源字段的证据等级

沿用 AgentOS 的口径：

| 来源写法 | 含义 |
|---|---|
| 用户原话（日期） | 用户明确表述过 |
| 推导（来源 REQ-ID） | 由某条已确认需求逻辑推出 |
| 提案（待确认） | Agent 提出、用户尚未确认 → 状态必须是 `draft` |

---

## 4. 状态取值

| 状态 | 含义 | 谁可以设定 |
|---|---|---|
| `draft` | 沟通中，尚未与用户确认 | Agent |
| `agreed` | 已与用户确认，可作为工作依据 | **仅用户确认后** |
| `frozen` | 冻结，后续执行中不得修改 | 用户 |
| `superseded` | 被新需求替代，保留原文 | Agent（需注明替代者） |
| `conflict` | 与其他需求冲突，需用户裁决 | Agent |

**Agent 不得自行把 `draft` 提升为 `agreed`。**
用户说"可以"、"就这样"、"按这个来"才算确认。

---

## 5. 需求边界（排除项）

锚点文件必须有一节明确**不做**什么：

```markdown
## 需求边界（不在范围内）

- 不做 AutoCAD COM 自动化 —— 第一版用 ODA/accoreconsole 路径
- 不覆盖压铸模具设计 —— 只做零件 DFM
- 不做标准认证声明 —— Agent 不替代工程师签字
```

**排除项也要落盘。** 否则"顺手加上"会从对话里溜进执行。

---

## 6. 待澄清问题文件

```markdown
# Open Questions — <项目名>

| 问题 ID | 问题 | 提出于 | 提出方 | 状态 | 答案 | 落到 |
|---|---|---|---|---|---|---|
| Q-01 | 阈值用通用值还是实际工艺能力表？ | 2026-10-26 | hermes | open | — | — |
| Q-02 | 交付是否要中英双语？ | 2026-10-26 | hermes | answered | 是 | REQ-004 |
| Q-03 | 破边孔是否算不合格？ | 2026-10-26 | 用户 | answered | 按工艺能力表定 | REQ-009 |
```

| 状态 | 含义 |
|---|---|
| `open` | 未解决，依赖它的 Unit 挂起 |
| `answered` | 已回答，必须填「落到哪个 REQ」或标 `no-req`（确认不需要进需求） |
| `dropped` | 提问本身不需要了 |

**`open` 状态的问题必须在交付说明里列出**，不能默默消失。

---

## 7. 变更台账（history.jsonl）

**create-only**，每行一个 JSON 对象：

```json
{"ts":"2026-10-26T11:00:00+08:00","req_id":"REQ-007","change":"status draft->agreed",
 "reason":"用户确认「就按真实工艺能力表来」","before_sha256":"a1b2...","after_sha256":"c3d4...",
 "by":"hermes","user_confirmed":true}
```

| 字段 | 说明 |
|---|---|
| `ts` | ISO 时间戳，带时区 |
| `req_id` | 受影响的需求；新增需求时用该需求的 ID |
| `change` | 变更摘要，用 `->` 表示状态迁移 |
| `reason` | 为什么改 |
| `before_sha256` / `after_sha256` | 变更前后 `REQUIREMENTS.md` 的哈希 |
| `by` | 变更者（客户端 ID） |
| `user_confirmed` | 该变更是否经用户确认 |

**追加，不修改，不删除。** 覆盖历史等于销毁审计线索。

---

## 8. 哈希与 AgentOS overlay

`REQUIREMENTS.md` 是会变的文件，因此**必须列入**项目 overlay，
让漂移可被检出：

```json
{
  "schema": "agentos-project-import-manifest-v1",
  "project_id": "<project>",
  "required_overlays": [
    {"path": "AGENTS.md", "sha256": "...", "scope": "project"},
    {"path": "REQUIREMENTS.md", "sha256": "...", "scope": "project"}
  ],
  "required_skills": ["production-skill-routing", "requirements-anchoring"]
}
```

**每次改动 `REQUIREMENTS.md` 都要刷新哈希**，否则
`agentos_import.py verify` 会 `blocked: Project overlay missing or changed`。

刷新方法：

```bash
python - <<'PY'
import hashlib, json, os
proj = r"<project root>"
man = os.path.join(proj, ".agentos", "project-import-manifest.json")
d = json.load(open(man, encoding="utf-8"))
for item in d["required_overlays"]:
    p = os.path.join(proj, item["path"].replace("/", os.sep))
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    item["sha256"] = h.hexdigest()
json.dump(d, open(man, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("hashes refreshed:", len(d["required_overlays"]))
PY
```

---

## 9. 追溯矩阵

需求到交付的追溯链：

```
REQ-007
  └─ Unit U-03  (服务需求: REQ-007)
       ├─ 产出物: kb/dfm_rules.json (sha256=...)
       ├─ 证据:   claim-002
       └─ 验证:   python scripts/kb_build.py → E3 计数为 0
```

**每个交付物都必须能回指到至少一条 REQ ID。**
回指不到的产出物是范围外工作，应当删除或补需求。

---

## 10. 常见失败及处理

- **需求 ID 复用** → 编号只增不改，删除也不复用。
- **验收标准不可判定** → 改写成能判真假的条件。
- **Agent 自升 agreed** → 只有用户确认才能改。
- **改文件不刷哈希** → verify 会 blocked；见 §8。
- **history.jsonl 被重写** → 只能追加。
- **open question 被遗忘** → 交付说明必须列出 `open` 项。
- **交付物回指不到 REQ** → 范围外工作，删除或补需求。

---

落款：`${OWNER_SIGNATURE}`
字体：微软雅黑（Microsoft YaHei）

---

## 11. 薄指针的命名陷阱（客户端侧）

客户端（Hermes）如果放置一个指向本 provider 的薄指针，**指针的目录名不能与 provider skill 名相同**。

AgentOS `bin/agentos_skills.py` 的 `resolve_provider()` 按
`project → client → bundled` 顺序查找，**第一个找到 `SKILL.md` 的作用域胜出**。
若客户端作用域存在 `skills/requirements-anchoring/SKILL.md`（薄指针），
它会遮蔽 bundled 的完整 provider；随后路由去找指针里并不存在的
`references/anchor-file-format.md`，结果是 `blocked: required file missing`。

**规则：客户端指针用 `<provider-skill-name>-pointer` 命名。**

```
AgentOS/skills/requirements-anchoring/SKILL.md          ← 完整方法（正本）
Hermes/skills/engineering/requirements-anchoring-pointer/SKILL.md  ← 薄指针
```

指针内部必须**指向正本路径**，且 frontmatter 的 `name:` 与目录名一致。

**指针不得复制治理正文** —— 只列正本路径与四条核心。
