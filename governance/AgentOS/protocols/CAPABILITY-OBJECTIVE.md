# AgentOS 能力目标清单（CAPABILITY-OBJECTIVE）

> 版本：AgentOS 1.8.5 · 注册表 1.4.0 · 能力总数 67
>
> 本文件由 `policies/SKILL-REGISTRY.json` 生成（生成器：`bin/gen_capability_objective.py`），
> 是**能力集合的机读基准**。`tests/verify_matrix_release.py` 会抽取本文件中每行开头的
> 能力 ID，要求其集合与注册表**完全相等**（不缺、不多、不改名）。
> 改能力请改注册表后运行 `python bin/gen_capability_objective.py` 重新生成，不要手改 ID 行。
>
> 每行格式：`能力ID  域/域组 · 供给状态 · 提供者/技能 · 触发词 · 验收项数`。
>
> 供给状态：`protocol` = 已部署且带可运行实现；`mapped` = 已映射到既有方法；
> `candidate` = 仅登记候选，尚无已验证部署，路由时直接阻断。
> 提供者：`core` / `engineering` / `visual`，括号内为实际 skill 目录。

## 域 A · requirements

req-jtbd  A/requirements · mapped · requirements/requirements-anchoring · JTBD、用户任务、场景、需求定义 · 2 项验收
req-kano  A/requirements · mapped · requirements/requirements-anchoring · Kano、需求分级、镀金 · 2 项验收
req-qfd  A/requirements · mapped · requirements/requirements-anchoring · QFD、用户需求、工程指标 · 2 项验收
req-spec-freeze  A/requirements · mapped · requirements/requirements-anchoring · 规格冻结、冻结约束、specification · 2 项验收
req-acceptance  A/requirements · mapped · requirements/requirements-anchoring · 验收标准、acceptance、criteria、DoD · 2 项验收
req-trace  A/requirements · mapped · requirements/requirements-anchoring · 需求追溯、traceability、追溯矩阵 · 2 项验收

## 域 B · architecture

arch-mbse  B/architecture · candidate · —（未部署） · MBSE、SysML、系统模型 · 2 项验收
arch-icd  B/architecture · mapped · engineering/embedded-software-engineering · 接口控制、ICD、interface、contract · 2 项验收
arch-modular  B/architecture · mapped · engineering/embedded-software-engineering · 模块化、模块边界、依赖方向 · 2 项验收
arch-adr  B/architecture · mapped · engineering/embedded-software-engineering · ADR、架构决策、被否方案 · 2 项验收
arch-ddd  B/architecture · candidate · —（未部署） · DDD、领域驱动、限界上下文 · 2 项验收
arch-api-first  B/architecture · mapped · engineering/embedded-software-engineering · API优先、API、first、接口先行 · 2 项验收

## 域 C · planning

plan-wbs  C/planning · mapped · core/production-skill-routing · WBS、工作分解、任务树 · 2 项验收
plan-cpm  C/planning · candidate · —（未部署） · CPM、PERT、关键路径 · 2 项验收
plan-gate  C/planning · protocol · core/production-skill-routing · Stage-Gate、SRR、PDR、CDR · 2 项验收
plan-rolling  C/planning · mapped · core/production-skill-routing · 滚动规划、远粗近细、rolling · 2 项验收
plan-risk  C/planning · protocol · core/production-skill-routing · 风险登记、预案、风险敞口 · 2 项验收
plan-decompose  C/planning · mapped · core/production-skill-routing · 任务派发、子智能体、工作包 · 2 项验收

## 域 D · design

hw-schematic-review  D/hardware · candidate · —（未部署） · 原理图、去耦、复位、时钟 · 2 项验收
hw-drc  D/hardware · candidate · —（未部署） · DRC、布线规则、间距、阻抗 · 2 项验收
hw-si-pi  D/hardware · candidate · —（未部署） · SI、PI、信号完整性、电源完整性 · 2 项验收
hw-dfm  D/hardware · protocol · metal/metal-process-engineering · DFM、PCB、可制造性、SMT · 2 项验收
hw-bom-audit  D/hardware · candidate · —（未部署） · BOM、生命周期、二供、物料 · 2 项验收
mech-dfma  D/mechanical · protocol · metal/metal-process-engineering · DFMA、装配、防呆 · 2 项验收
mech-tolerance  D/mechanical · protocol · metal/metal-process-engineering · 公差堆叠、极值法、RSS · 2 项验收
mech-gdt  D/mechanical · protocol · metal/metal-process-engineering · GD&T、几何公差 · 2 项验收
mech-sim  D/mechanical · candidate · —（未部署） · 结构仿真、强度、跌落、热仿真 · 2 项验收
id-cmf  D/mechanical · candidate · —（未部署） · CMF、颜色、材料、工艺 · 2 项验收
id-ergo  D/mechanical · candidate · —（未部署） · 人因、握持、重心、热区 · 2 项验收
id-design-language  D/mechanical · candidate · —（未部署） · 造型一致性、家族化、比例 · 2 项验收
emb-state-machine  D/embedded · mapped · engineering/embedded-software-engineering · 状态机、firmware、state、machine · 2 项验收
emb-misra  D/embedded · candidate · —（未部署） · MISRA、C、规范合规 · 2 项验收
emb-rtos-pattern  D/embedded · mapped · engineering/embedded-software-engineering · RTOS、优先级、队列、信号量 · 2 项验收
emb-hil  D/embedded · mapped · engineering/embedded-software-engineering · HIL、硬件在环 · 2 项验收
emb-lowpower  D/embedded · candidate · —（未部署） · 低功耗、睡眠、功耗预算 · 2 项验收
sw-tdd  D/software · mapped · engineering/embedded-software-engineering · TDD、测试驱动、先红后绿 · 2 项验收
sw-solid-clean  D/software · mapped · engineering/embedded-software-engineering · SOLID、整洁架构、软件分层 · 2 项验收
sw-ci-gate  D/software · mapped · engineering/embedded-software-engineering · CI、构建、可重复、构建门禁 · 2 项验收
sw-code-review  D/software · mapped · engineering/embedded-software-engineering · 代码评审、code、review、回归 · 2 项验收
sw-threat-model  D/software · candidate · —（未部署） · STRIDE、威胁建模 · 2 项验收
ui-design-system  D/ui · mapped · core/production-skill-routing · Design、Tokens、设计系统、UI一致性 · 2 项验收
ui-heuristic  D/ui · candidate · —（未部署） · Nielsen、可用性启发式 · 2 项验收
ui-a11y  D/ui · mapped · core/production-skill-routing · 可访问性、无障碍、焦点、对比度 · 2 项验收
vis-concept-illustration  D/visual · protocol · visual/visual-asset-production · 概念渲染、实景插画、场景插画、示意图风格 · 4 项验收
vis-dfm-illustration  D/visual · protocol · visual/visual-asset-production · DFM 配图、设计规范配图、注塑设计准则、工艺准则插图 · 6 项验收

## 域 E · mechanical

qa-fmea  E/quality · protocol · core/production-skill-routing · FMEA、失效模式、检测控制 · 2 项验收
qa-vmodel  E/quality · protocol · core/production-skill-routing · V模型、V-model、设计验证对应 · 2 项验收
qa-test-pyramid  E/quality · mapped · engineering/embedded-software-engineering · 测试金字塔、测试层次 · 2 项验收
qa-doe  E/quality · mapped · engineering/embedded-software-engineering · DOE、多因素、实验设计 · 2 项验收
qa-reliability  E/quality · candidate · —（未部署） · HALT、可靠性、寿命预估 · 2 项验收
qa-8d  E/quality · candidate · —（未部署） · 8D、围堵、问题求解 · 2 项验收
qa-review-checklist  E/quality · protocol · core/production-skill-routing · 设计评审、清单、checklist · 2 项验收

## 域 F · embedded

mfg-npi  F/manufacturing · protocol · metal/metal-process-engineering · NPI、EVT、DVT、PVT · 2 项验收
mfg-ppap  F/manufacturing · candidate · —（未部署） · PPAP、生产件批准 · 2 项验收
mfg-spc  F/manufacturing · protocol · metal/metal-process-engineering · SPC、Cpk、统计过程控制 · 2 项验收
mfg-change  F/manufacturing · protocol · core/production-skill-routing · ECN、工程变更、影响分析 · 2 项验收

## 域 G · software

km-decision-log  G/knowledge · mapped · core/production-skill-routing · 决策台账、decision、log · 2 项验收
km-postmortem  G/knowledge · protocol · core/production-skill-routing · 复盘、AAR、事故教训 · 2 项验收
km-lessons  G/knowledge · protocol · core/production-skill-routing · 教训入库、checklist更新 · 2 项验收
km-context-pack  G/knowledge · mapped · core/production-skill-routing · 上下文装配、context、pack、checkpoint · 2 项验收

## 域 H · quality

meta-router  H/meta · protocol · core/production-skill-routing · 技能路由、任务分类、route · 2 项验收
meta-skill-registry  H/meta · protocol · governance/agentos-governed-integration · 技能注册、冲突检测、registry · 2 项验收
meta-qc-gate  H/meta · protocol · core/production-skill-routing · 产出质检、质量门禁、output、gate · 2 项验收
meta-escalation  H/meta · mapped · core/production-skill-routing · 连续失败、熔断、升级 · 2 项验收
meta-no-fabrication  H/meta · mapped · core/production-skill-routing · 数据校验、零编造、证据真实性 · 2 项验收
meta-token-budget  H/meta · protocol · governance/agentos-governed-integration · Token预算、token效率、上下文压缩、context pressure · 4 项验收
meta-background-agent  H/meta · protocol · governance/agentos-governed-integration · 后台子智能体、后台运行、background agent、background subagent · 3 项验收

## 汇总

- candidate: 18 项
- mapped: 28 项
- protocol: 21 项
- 合计: 67 项
