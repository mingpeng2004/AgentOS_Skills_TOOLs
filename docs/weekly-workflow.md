# Weekly learning and publication

Run weekly, Sunday 03:00 Asia/Shanghai. The native Codex thread automation holds
the schedule; this repository contains the workflow and portable assets only.
The host app/machine must be available for local execution. Quiet when unchanged;
notify only on meaningful improvement, publication, failure or needed decision.

0. Use the one existing native weekly automation; target only `mingpeng2004/AgentOS_Skills_TOOLs` under explicit owner authorization. Publication state is isolated by repository ID; the old target's baseline/cache is never reused. Transfer the original workflow into the coordinating chat, do not create another periodic job.
1. Read local source policy and previous scan receipt. Discover projects from
   the configured project-bearing roots plus current client/project Skill roots.
   Search project rules, decisions, knowledge, postmortems and lesson records;
   skip dependencies/build output. Record inaccessible roots, missing files,
   scan bounds and hashes. Distinguish true zero, unreadable and not inspected.
2. Inspect changed evidence and the current target Skill/governance. An incident
   is separate from evidence availability; a plausible root cause is not proven.
   Propose a narrow reusable lesson, scope, counterexample and verification.
   Integrate only actually supported lessons into corresponding authored sources.
   Keep conflicting or weakly evidenced lessons proposed/blocked. No raw reports
   or measurements enter the repository.
3. Inventory all discovered Skills, preserve variant content and licensing.
   Built-in/plugin/vendor material without established redistribution permission
   remains reference-only with a visible reason; do not silently omit it. Export
   only explicitly allowlisted authored MIT assets; a user-managed directory is
   not proof of rights. Readable `SKILL.md` files without standard identity are
   preserved as `unregistered_skill` (reference-only), except managed AgentOS
   client entries, which are `client_entry` and are not Skills. Neither category
   is routed or exported as a Skill. Unknown third-party items stay
   reference-only. Binary assets are excluded in this text-first edition.
   Oversize, unreadable, linked/reparse and absent sources remain explicit
   coverage issues; the scanner must not follow links or call an incomplete scan
   complete merely because some linked paths look like duplicate cache entries.
   Links nested below already excluded dependency/build directory names are not
   visited and are not separately counted as scan gaps; links in the remaining
   declared scope remain explicit exclusions. Readable source files up to the
   explicit per-file hash bound are streamed into SHA256, including large binary
   inventory items; oversized files beyond that bound remain an incomplete scan
   issue and are never silently omitted from the coverage report.
   A reparse alias may be marked `linked_alias_verified` only when its stored
   target metadata matches an explicit policy prefix, the mapped physical
   canonical root is link-free, and that source was independently inventoried
   by direct path. Do not open/read through the client link; unresolved aliases
   remain exclusions. This proves only source-tree identity, not client parity,
   native discovery, or runtime activation.
4. Stage portable copies. Remove machine-private absolute paths and remote/local
   identifiers using explicit normalization; preserve semantics and mark generated
   placeholders in documentation. Reject credentials, PII, raw traces, dumps,
   private state, unexpected extensions, linked/reparse paths and large binaries.
   Original source hashes/paths are private; public evidence uses exported hashes.
5. Validate every export path/content/link/Skill frontmatter and run relevant
   tests. Run the existing SecurityCheck on changed code and inspect actual scan
   counts/findings. A pass on an empty or uninspected scope never counts.
   `prepare` additionally requires both `scope_complete=true` and
   `learning_coverage_complete=true` in the staged inventory; an explicit
   independent review cannot waive either machine gate.
   A real review records the package fingerprint and actual test outputs before
   prepare. Recompute source and package hashes immediately before publishing.
6. Publish only reviewed content to the named repository. Observe its default
   branch, prior managed manifest and exact remote file/blob IDs. Preserve
   unrelated files; concurrent changes block and need review. No force update.
   Read back HEAD/tree/blobs and compare hashes before declaring publication.
   A no-change run must not create a meaningless commit.
7. Save private receipt, source inventory, actual review, publication/readback
   and pending lessons. Update the existing task/checkpoint, not a second project
   status ledger. All original records remain local and unmodified.

## Commands

`python -B tools/weekly_learning.py scan`

Review private scan results and apply approved in-scope lessons to actual sources.

`python -B tools/weekly_learning.py stage --scan <private-scan.json>`

`python -B tools/weekly_learning.py validate --package <staged-root>`

After actual tests/review:

`python -B tools/weekly_learning.py prepare --package <staged-root> --review <review.json>`

`python -B tools/weekly_learning.py publish --ready <ready.json>`

No command infers owner approval from elapsed time. Existing weekly publication
delegation covers reviewed portable assets, never secrets or product data.
Credentials come from existing environment/credential manager, never persisted
or printed. Network errors, redirects, branch protection and failed readback
remain failed/unknown and preserve reconciliation state.

## Capability and learning closure / 能力与学习闭环

Existing `SKILL-REGISTRY.json` remains capability SSOT. The derived `capability-assets.json` references existing capability IDs and records Skill/Tool identity, entry, version, hashes, side effects, platforms, dependency graph, rights and canonical/superseded state. Candidate assets are not active specialist competence. Optional image tools are not core stdlib dependencies and are never automatically installed.

现有能力表仍为唯一能力定义。资产表只引用能力、记录技能与工具的身份/依赖/许可/状态。已有能力优先强化；新盲区以候选提案进入，不用“创建名字”冒充能力。语义重复由独立审阅裁决，机器结构检查不等于语义证明。

`capability_assets.scan_learning` reads only explicit persistent-learning paths. Raw session/transcript/trace directories are forbidden. It reports scanned/empty/unreadable/absent/excluded/bounded states. Observation and reviewed disposition watermarks are separate; scan alone never consumes a lesson. Strengthen/new receipts bind source/target/test hashes, a counterexample, normal and boundary checks, and the actual reviewer. Pending or weak evidence stays pending.

扫描不会消费未审候选；处置须绑定来源与目标摘要、反例/正常/边界证据及审阅。未支持客户端或不可读源是覆盖欠账，不是零学习。新增/删除/链接变化使旧发布就绪状态失效。

`tools/agentos_toolkit.py` is the common entry point. Start with `init --policy` using `config/policy.example.json`; publish requires explicitly authorized repository identity and existing secure credentials. `portable_install.py` installs offline with complete preflight, verified backup and rollback; legacy installers are not included. Do not assert client runtime loading from file deployment.


## Reproducible verification / 可复现验证

Run `python -B tools/verify_release.py --package ABS --output NEW_ABS_OUTSIDE_PACKAGE`; the default security scanner is the bundled `tools/security_check.ps1`, or pass an explicit `--security-check ABS`. The output directory is private and must be outside the package. The runner checks nonempty unittest execution, existing AgentOS matrix and four Windows PowerShell5.1 suites, then audits every actual code file with a new one-file report and exact coverage hashes. Missing PowerShell/scanner is `not_run` and makes the release incomplete, never green. Full logs and command receipts stay private; `public_summary.json` is sanitized. Optional visual tool execution/third-party dependencies are not certified by these core suites.

验证器拒绝空测试、超时、非零退出、源漂移和扫描覆盖不符；代码文件前后集合与哈希绑定。日志及完整命令留私有输出目录。哈希不能认证同权限调用者身份；实际独立审阅仍是必需门禁。备份/回滚只恢复文件内容及回执，不声称恢复ACL/owner/mode/timestamps，也不是操作系统原子比较交换。
