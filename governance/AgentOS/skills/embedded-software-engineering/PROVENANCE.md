# PROVENANCE — embedded-software-engineering

> **PROVENANCE_STATUS: RESOLVED**
> 闸 5（写 provenance）判定：**通过**。来源、作者、许可与安装方式均已查清，并留有可核对的证据。

| 字段 | 值 |
|---|---|
| 来源 | **自建**。维护源为本项目 `skills/embedded-software-engineering/`（DEC-021 授权 mavis 维护与受限发布） |
| 发布去向 | 私有仓库 `mingpeng2004/Ming-Skills` 的 `main` 分支（登记来源见 `references/maintenance.md`） |
| 作者 / 许可 | 本项目所有者自有件；许可为历史内部授权；当前公开版本由所有者于 2026-10-25 授权采用 MIT |
| 安装方式 | 由发布工程的 `ming_skills.py install` 安装到各客户端，附 `.ming-skills-receipts/` 收据，绑定版本、摘要与备份路径 |
| 首次登记 | 2026-10-12（DEC-021 生效后首版发布） |
| 当前版本 | 1.1.2 |

## 执行面（闸 2 / 闸 3）

本 Skill **不含可执行代码**：无 `scripts/` 目录、无二进制、无网络调用、无凭据读写。
内容为 Markdown 方法论、Word 审阅快照与 JSON 模板。Word 资产由发布工具的 DOCX
深度校验把关（拒绝宏、OLE 与嵌入对象、外部关系、隐藏内容、失效源哈希或版本不匹配）。

## 版本谱系

| 版本 | 变更要点 |
|---|---|
| 1.1.1 | 2026-10-12 首次发布到私有仓库 |
| 1.1.2 | 合并客户端副本中尚未回流的独有内容（量的单位纪律、必须亲自启动自己的产物、最小对照产物、工程踩坑与教训库），补回副本中丢失的力环优化参考，并定点修复三处字符损坏（`r`→LF、`e`→ESC、`f`→FF），原表格行结构保持不变 |

## 判据

本文件记录的是已查清的事实与证据，不是占位说明。
若来源、许可或安装方式发生变化，必须同步更新本文件，不得保留过期结论。


Current public edition: owner-authorized MIT distribution, 2026-10-25. Original internal distribution statements describe history, not a restriction on this edition.
