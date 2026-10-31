# AgentOS 用户桌面不干扰协议 v1

## Purpose

智能体在执行**浏览器自动化 / 抓取 / 渲染 / 长时间脚本**时，
**不得占用用户的桌面**：不弹窗、不抢焦点、不移动用户鼠标、不让用户看到自己的窗口在闪。

用户在同一台机器上办公；智能体的自动化是"后台工序"，不是"前台应用"。
2026-10-31 用户明确要求（原文）：
> "你如果需要运行浏览器，请后台运行，不要影响我的工作"，
并要求按**系统级要求**处理，不得只当本次会话的临时做法。

## 默认浏览器 = AI 专用浏览器（2026-10-31 用户裁决：默认后台调用）

**默认口径**：任何需要开浏览器的活儿（自动化 / 抓取 / 渲染 / 长脚本），
**默认使用 AI 专用浏览器**，不用用户自己的 Chrome/Edge。

| 项 | 值 |
|---|---|
| 管理器 | `${AGENTOS_HOME}\bin\ai_browser.py start｜stop｜status` |
| CDP 操作台 | `${AGENTOS_HOME}\bin\ai_browser.js open｜shot｜pdf｜text` |
| 独立 profile | `<AgentOS>/.local/ai-browser-profile`（持久化 ⇒ 保留 clearance，少被挑战） |
| 调试端口 | **9418**（关闭时只按此端口精确匹配） |
| 窗口 | `--window-position=-32000,-32000`（离屏，不占用户桌面） |
| 反限速（必须） | `--disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-background-timer-throttling --disable-ipc-flooding-protection` |

策略文件：`policies/AI-BROWSER-POLICY.json`；每次会话由 `runtime/AGENT-IMPORT.md` 强制加载。

## Hard rules

1. **浏览器必须离屏或无头**：自动化浏览器一律用
   `--window-position=-32000,-32000`（离屏真实窗口）或 `--headless=new`；
   **禁止**在默认坐标（0,0 / 40,40 等）启动可见窗口。
2. **禁止抢焦点**：不使用 `--start-maximized` 之外的任何置前行为；
   脚本里不做 `window.focus()`、不模拟系统级鼠标键盘（`Input.dispatchMouseEvent`
   只作用于**目标页面内的元素坐标**，不移动系统指针）。
3. **不碰用户自己的浏览器**：自动化必须使用**独立 profile 目录**与独立调试端口；
   结束任务时只关闭自己起的进程（按 `--remote-debugging-port=` 精确匹配），
   绝不按进程名批量杀 chrome / msedge。
4. **通知可见性**：用户询问"你在干什么"时，用一句话说明当前在后台做什么、
   预计还要多久，不靠弹窗告知。
5. **例外**：需要用户当场操作（登录、授权、点确认）时，
   优先用**内置浏览器面板**（右侧 FilePanel），那是用户可见且预期的界面；
   只有在内置浏览器不可用时，才请用户配合一次前台动作。

## Why

- 用户在同一台机器上干活；一个抢焦点的自动化窗口会打断正在写的文档、正在点的表格；
- 这类打断是**不可逆的注意力损失**，比任务慢几分钟代价大得多。
- 自动化的产物应当是**文件**（截图/PDF/数据），不是"屏幕上有个窗口在动"。

## Evidence / verification

启动自动化浏览器后，必须能自证离屏：

```powershell
Get-CimInstance Win32_Process -Filter "name='chrome.exe'" |
  Where-Object { $_.CommandLine -match 'remote-debugging-port=94\d\d' } |
  Select-Object ProcessId, CommandLine
# 期望：命令行含 --window-position=-32000,-32000 或 --headless=new
```

## Scope

本机所有智能体、以后新装的智能体、全部客户端（MiniMax Code、Kimi Code、VS Code 集成、
委派子智能体）、以及任何后台子智能体与批处理脚本。不可按客户端或个人偏好豁免。
