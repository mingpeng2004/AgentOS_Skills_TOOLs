#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 专用浏览器 —— **默认**的智能体浏览器（后台、离屏、独立实例）。

为什么是"默认"
--------------
2026-10-31 用户裁决：*"以后默认后台调用 AI 专用高效浏览器，不要影响我的工作，这是默认系统级的要求"*。
本机用户同时在用 Chrome 办公，智能体**不得**动用户的浏览器。

本工具提供的"AI 专用浏览器"
--------------------------
- **独立 profile**：`<AgentOS>/.local/ai-browser-profile`（持久化 ⇒ 保留站点 clearance，少被 Cloudflare 挑战）
- **独立调试端口**：9418（只按此端口精确关闭自己起的进程）
- **离屏 + 反限速**：`--window-position=-32000,-32000` + 关闭定时器节流/渲染器挂起
  （否则离屏窗口被 Chrome 节流，页面永远渲染不完）
- **与用户浏览器物理隔离**：不启动、不结束、不注入用户的 Chrome

用法
----
    python ai_browser.py start      # 启动（幂等）
    python ai_browser.py status     # 状态（含 CDP 端点）
    python ai_browser.py stop       # 关闭（只关本端口的进程）
    python ai_browser.py info       # 打印 JSON，供其它脚本读取

配套：`ai_browser.js`（CDP 操作：打开/截图/打印 PDF/取文本）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTOS = os.path.dirname(HERE)
PROFILE = os.path.join(AGENTOS, ".local", "ai-browser-profile")
PORT = 9418
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

# 离屏 + 反限速（离屏窗口默认被 Chrome 节流 ⇒ SPA 渲染不完）
FLAGS = [
    "--no-first-run", "--no-default-browser-check", "--disable-gpu",
    "--window-size=1600,1400", "--window-position=-32000,-32000",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    "--disable-ipc-flooding-protection",
    "--disable-background-networking",
    "--disable-session-crashed-bubble", "--disable-features=Translate",
    "--hide-crash-restore-bubble", "--force-color-profile=srgb",
    f"--user-agent={UA}", "--lang=zh-CN",
]


def chrome_path():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise SystemExit("找不到 Chrome/Edge 可执行文件")


def ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                          capture_output=True, text=True).stdout.strip()


def running():
    out = ps("Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | "
             "Where-Object { $_.CommandLine -match 'remote-debugging-port=%d' } | "
             "Select-Object -ExpandProperty ProcessId" % PORT)
    return [int(x) for x in out.split() if x.strip().isdigit()]


def cdp_alive():
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/json/version" % PORT, timeout=4) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def start():
    if cdp_alive():
        print("AI 浏览器已在运行（端口 %d）" % PORT)
        return 0
    os.makedirs(PROFILE, exist_ok=True)
    exe = chrome_path()
    args = [exe, "--user-data-dir=%s" % PROFILE,
            "--remote-debugging-port=%d" % PORT, "--remote-allow-origins=*"] + FLAGS + ["about:blank"]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(1.5)
        if cdp_alive():
            print("AI 浏览器已启动：端口 %d · profile %s" % (PORT, PROFILE))
            return 0
    print("AI 浏览器启动超时")
    return 3


def stop():
    ps("Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | "
       "Where-Object { $_.CommandLine -match 'remote-debugging-port=%d' } | "
       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" % PORT)
    print("AI 浏览器已关闭（仅端口 %d 的进程）" % PORT)
    return 0


def status():
    v = cdp_alive()
    print(json.dumps({
        "running": bool(v),
        "port": PORT,
        "cdp": ("http://127.0.0.1:%d" % PORT) if v else None,
        "profile": PROFILE,
        "browser": (v or {}).get("Browser"),
        "pids": running(),
        "user_browser_touched": False,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    fn = {"start": start, "stop": stop, "status": status, "info": status}.get(cmd)
    if not fn:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(fn())
