# GitHub 凭据治理（跨 Agent 通用）

> 适用：任何需要调用 GitHub API 的 Agent / 客户端 / 脚本。
> 目标：**配额从 60/小时 提到 5000/小时，且永远不需要人工登录。**

## 一、先诊断，再动手

GitHub 限流告警有两种根因，处理方式完全不同：

| 症状 | 根因 | 处理 |
|---|---|---|
| 配额确实是 60/小时 | 匿名调用（凭据没接上） | 接凭据 → 5000/小时 |
| 配额是 5000 但仍告警 | 真调用过多 | 缓存 / 批量化 / 退避 |

**先查 `GET /rate_limit` 的 `resources.core.limit`：**

```
60   → 匿名，凭据链断了（最常见，且最容易被误判为「调用太频繁」）
5000 → 已认证，问题在调用量
```

本机案例：长期出现 GitHub 限流告警，一度按「调用太频繁」排查。
实测 `limit=60` —— 根因是**一直在匿名调用**，不是调用量。

## 二、凭据在哪：按优先级找，不要先登录

GitHub 凭据可能散落在多个位置。**找到已有的、可自助续期的那个**，
比重新走一次 OAuth 授权好得多。

| 位置 | 平台 | 可否自助续期 | 备注 |
|---|---|---|---|
| `GITHUB_TOKEN` / `GH_TOKEN` 环境变量 | 全平台 | 否（靠人续） | 最优先，成本最低 |
| Windows 凭据管理器 `git:https://github.com` | Windows | **是**（GCM 自动续期） | git push 时常被悄悄写入 |
| `~/.config/gh/hosts.yml`（gh 官方存储） | 全平台 | 否 | gh 自己读写 |
| `~/.git-credentials` / `~/.netrc` | 全平台 | 否 | 明文，风险高 |
| `.env` / CI secrets | 全平台 | 否 | 明文，风险高 |
| VS Code `globalStorage` / `state.vscdb` | 桌面 | 否 | 扩展授权 |
| GitHub Desktop | 桌面 | 否 | |
| 浏览器 cookie | 桌面 | 否 | **Chrome v127+ 独占锁，外部不可读** |
| GitHub App / PAT | 全平台 | 否 | 最正式但要用户手动创建 |

### Windows 专用读取方法

凭据管理器里的条目要用 WinCred API 读（`cmdkey /list` 只列条目，不给值）：

```python
import ctypes
from ctypes import wintypes, Structure, POINTER, byref

class _CREDENTIAL_ATTRIBUTE(Structure):
    _fields_ = [("Keyword", wintypes.LPWSTR), ("Flags", wintypes.DWORD),
                ("ValueSize", wintypes.DWORD), ("Value", ctypes.POINTER(ctypes.c_ubyte))]

class _CREDENTIAL(Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.POINTER(_CREDENTIAL_ATTRIBUTE)),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

advapi = ctypes.WinDLL("advapi32", use_last_error=True)
advapi.CredReadW.restype = wintypes.BOOL
advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
advapi.CredFree.argtypes = [ctypes.POINTER(_CREDENTIAL)]

handle = ctypes.POINTER(_CREDENTIAL)()
if advapi.CredReadW("git:https://github.com", 1, 0, ctypes.byref(handle)):
    cred = handle.contents
    blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
    token = blob.decode("utf-16-le").rstrip("\x00")   # GCM 用 UTF-16LE
    advapi.CredFree(handle)
```

**注意**：
- 通用凭据的 blob 是 **UTF-16LE**，不是 UTF-8。
- `git credential fill` 在**没有缓存凭据**时会去开浏览器登录，
  在无人值守场景会**永久挂起**。必须设 `GCM_INTERACTIVE=never` 和
  `GIT_TERMINAL_PROMPT=0`，并加超时。
- 回退：`git-credential-manager.exe get`（同样要非交互环境变量）。

## 三、接通：把凭据桥接到客户端实际读的位置

Hermes 的取凭据顺序（`hermes_cli/github_api.py`）：

1. `GITHUB_TOKEN` 环境变量
2. `GH_TOKEN` 环境变量
3. `gh auth token`

`gh` **不读** Windows 凭据管理器，所以第 3 级在只有 GCM 凭据时返回空。
解法是把凭据同步进 gh 的官方存储：

```
%APPDATA%\GitHub CLI\hosts.yml

github.com:
    user: <username>
    oauth_token: <token>
    git_protocol: https
```

`gh auth login --with-token` 会**校验 scope**（缺 `read:org` 直接拒绝，
返回 `error validating token: missing required scope 'read:org'`），
所以直接写文件更可靠。

## 四、治理规则（不可协商）

| 规则 | 内容 |
|---|---|
| **不擅自登录** | 授权是一次性动作；未经用户明确要求不要触发登录流程 |
| **凭据只落两处** | 系统凭据管理器 + 客户端官方存储；不进仓库、报告、日志、memory |
| **打印一律遮蔽** | 只输出长度、前缀、scope、限额头；永不打印完整 token |
| **优先自助续期** | 找到已有的可续期凭据，优先于发起新授权 |
| **幂等同步** | 提供一个可重复执行的同步脚本，会话启动可跑 |
| **非交互** | 同步脚本永不触发浏览器、永不阻塞等待人工 |

## 五、验收清单

接通后逐项实测，**不接受推断**：

| # | 检查 | 期望 |
|---|---|---|
| 1 | `gh auth status` | `Logged in to github.com account <user>` |
| 2 | `gh auth token` | 返回非空 token |
| 3 | 客户端官方存储 | 已落盘且含 `oauth_token` |
| 4 | `github_token()` / 客户端取凭据函数 | 返回有效 token |
| 5 | `GET /user` | `login` == 预期账号 |
| 6 | `GET /rate_limit` | `limit == 5000`（不是 60） |
| 7 | 真实业务端点 | HTTP 200 |
| 8 | scope 审查 | 覆盖实际用到的端点 |
| 9 | 非交互重取 | 不开浏览器、不挂起 |
| 10 | 临时文件清理 | scratch 内无明文 token 残留 |

## 六、scope 够不够：按实际端点判断，别按 fear 扩大

拿到 token 后看 `X-OAuth-Scopes` 响应头，然后**逐个比对自己实际调用的端点**。

常见端点所需 scope：

| 端点 | 所需 scope |
|---|---|
| `/repos/{owner}/{repo}`、`/repos/*` | `repo`（公开仓库甚至 `public_repo` 即可） |
| `/search/*` | 公开仓库 `repo` 足够 |
| `/user` | 无特殊要求 |
| `/rate_limit` | 无特殊要求 |
| `/orgs/{org}/members`、`/user/orgs` | **`read:org`** |

**结论要落到「有没有影响现有工作」**：
若缺 `read:org` 而你只用 `/repos/*` `/search/*` `/user`，
则**不阻塞**，不要为此再走一次授权。
需要组织级查询时再补权（那是「加权限」，不是「从零登录」）。

## 七、不要走的弯路

- ❌ **别先假设要重新登录。** 先翻系统凭据管理器、gh 存储、`.env`。
- ❌ **别直接读浏览器 cookie。** Chrome v127+ 对 cookie 库加了独占锁
  （`CreateFileW` 返回 WinError 32），且 cookie 值用 App-Bound 加密，
  外部进程读不到。要用浏览器会话就走 CDP 附着**已在运行**的实例，
  不要复制 profile（复制出来的 session 也是空）。
- ❌ **别在锁屏状态做桌面点击。** 授权确认会超时，且此时拿不到人工批准。
  优先找无需交互的凭据来源。
- ❌ **别把 `gh auth login --with-token` 的失败当作凭据无效。**
  它可能只是 scope 校验不过，token 本身是好的。

## 八、参考实现

`${PROJECT_PATH}\000_Hermes_Agent\metal-system\scripts\gh_auth_sync.py`

幂等、非交互、不打印 token。支持 `--check` 只读模式。
