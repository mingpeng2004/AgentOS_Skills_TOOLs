#Requires -Version 5.1
# src/SecurityCheck.ps1
# 安全自检 (系统级别要求, 见 DEC-005)
#
# 用法:
#   # 直接执行（推荐，DEC-029 起支持）:
#   pwsh -NoProfile -File src\SecurityCheck.ps1 -All
#   pwsh -NoProfile -File src\SecurityCheck.ps1 -FilePath src\smartmon.ps1
#
#   # dot-source 后手动调用（向后兼容，用于在同一会话内多次调用）:
#   . .\src\SecurityCheck.ps1
#   Invoke-MingSecurityCheck -FilePath 'src\smartmon.ps1'
#   Invoke-MingSecurityCheck -All -ProjectRoot '${PROJECT_PATH}\999_MINIMAX_100_SYS_Maintain'
#
#   不传 -FilePath 时默认全栈扫描（避免「跑起来了但扫了 0 个文件」）。
#
# ⚠️ 验收判据（DEC-027 反向验证纪律）:
#   **不要只看 exit 0**。必须确认 reports\*-security-audit.json 的
#   **时间戳与 total_files 已更新**——那是真正执行过的唯一证据。
#   历史教训: 本文件曾因缺少顶层调用而「无输出 + exit 0 + 报告不更新」。
#
# 检测覆盖:
#   - base64 编码二进制嵌入 (5_obfuscation)
#   - -enc / -EncodedCommand (5_obfuscation)
#   - Invoke-Expression 字符串拼接 (5_obfuscation)
#   - Add-Type 动态编译 (5_obfuscation)
#   - 持久化操作 (3_persistence) 不通过显式脚本
#   - Set-MpPreference / Disable-RealtimeMonitoring (4_bypass)
#   - Add-MpPreference / 排除 (4_bypass)
#   - 凭据硬编码 (6_credential)
#
# 设计原则:
#   - 纯检测, 不修改文件 (findings = @{ File -> [Finding[]] })
#   - 输出结构化 result (适合 CI 集成)
#   - 任何 finding 都可被打包 CI fail (-FailOnCritical / -FailOnWarning)

[CmdletBinding()]
param(
    [string]$FilePath,
    [switch]$All,
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
    [string[]]$ExternalScanRoot = @(),
    [switch]$FailOnCritical,
    [switch]$FailOnWarning,
    [switch]$Quiet
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# === 严重度 ===
$script:Severities = @{
    'CRITICAL' = 3
    'WARNING'  = 2
    'INFO'     = 1
}

# === 白名单: 这些文件/目录经人工审计, 跳过部分检测 ===
$script:WhitelistFiles = @(
    # 安装脚本本身调 schtasks 是合规的 (由 DEC 显式授权)
    (Join-Path $PSScriptRoot 'Install-ScheduledTask.ps1')
)
$script:WhitelistDirs = @(
    # tests/ 目录的测试用例故意包含恶意代码字面量 (用于单元测试)
    # 它们不代表实际漏洞
    (Join-Path (Split-Path $PSScriptRoot -Parent) 'tests')
)

# === 已登记的外部受管代码根（DEC-047） ===
# 判别口同 DEC-042：「新增一个目录，里面放的是不是脚本？是 ⇒ 它必须出现在扫描范围里」。
# Ming-Skills 发布工程的 tools/ 与 tests/ **会被发布到远端 GitHub 仓库**，
# 属于本项目负责维护的代码（AGENTS.md §2.1），却从未进入过本项目的强制门禁。
# 实测后果：2026-10-20 改了 tools/ming_skills.py，门禁「通过」却从未看过它一眼。
# 路径不存在时**必须显式记录为未扫描**，不得静默跳过。
$script:RegisteredExternalRoots = @()

# === 检测规则定义 ===
# 设计: 正则匹配"实际调用形式", 不匹配"字符串字面量" (避免规则定义自命中)
$script:Rules = @(
    # --- 5_obfuscation_audit ---
    @{
            Id          = 'OBS-001'
            Severity    = 'CRITICAL'
            Title       = 'base64 编码的二进制嵌入'
            # 匹配 @{ ... Base64 = "..." 实际声明格式 (要求 Base64 = "..." 后还有 Size 或 短横线)
            Pattern     = '@\{[^{}]*Base64\s*=\s*["''][A-Za-z0-9+/=]{40,}["''][^{}]*\}'
            Description = '检测到 base64 编码的二进制嵌入 (典型 TrojanDropper 行为). 立即移除.'
            Hint        = '改用透明分发: vendor/ 目录 + .ps1 + bat. 见 DEC-005/006.'
        }
    @{
            Id          = 'OBS-002'
            Severity    = 'CRITICAL'
            Title       = '-EncodedCommand / -enc 参数'
            # 匹配 powershell.exe -enc XXX 实际调用形式 (前面有 powershell / pwsh)
            Pattern     = '(?i)(?:powershell|pwsh)[\w\.]*\s+.*?-[eE](?:nc|ncodedcommand)?\s+[A-Za-z0-9+/=]{20,}'
            Description = '检测到 PowerShell -EncodedCommand (绕过审计的常见手段).'
            Hint        = '改用透明脚本, 不要用 base64 编码的命令.'
        }
    @{
            Id          = 'OBS-003'
            Severity    = 'WARNING'
            Title       = 'Invoke-Expression 字符串拼接'
            # 实际执行: iex ($var) 或 iex $var 或 Invoke-Expression "..."
            Pattern     = '(?i)(?:^|\s|;)(?:iex|invoke-expression)\s+(\$["''])'
            Description = 'IEX 拼接字符串执行常见于恶意 payload.'
            Hint        = '改用 & $cmd 或 Invoke-Expression 接收 PSCustomObject.'
        }
    @{
            Id          = 'OBS-004'
            Severity    = 'WARNING'
            Title       = 'Add-Type 动态编译'
            # 实际调用 Add-Type -TypeDefinition "..." 或 Add-Type -Path X.cs
            Pattern     = 'Add-Type\s+-(?:TypeDefinition|Path)\s+["''\$]'
            Description = 'Add-Type 动态加载 C# 代码 (需审计来源).'
            Hint        = '如果必须, 显式审计 .cs 文件来源 + 加 review.'
        }

    # --- 4_security_control_bypass ---
    @{
            Id          = 'BYP-001'
            Severity    = 'CRITICAL'
            Title       = 'Set-MpPreference 修改 Defender'
            # 实际调用: Set-MpPreference -DisableRealtimeMonitoring $true (必须配 -参数)
            Pattern     = 'Set-MpPreference\s+-\w+\s+\$?\w+'
            Description = '修改 Defender 配置 (可能被滥用关闭防病毒).'
            Hint        = '禁止. 如果必须, 走 Windows Security Center 显式 API.'
        }
    @{
            Id          = 'BYP-002'
            Severity    = 'CRITICAL'
            Title       = 'Disable-RealtimeMonitoring 关闭实时扫描'
            # 实际调用形式
            Pattern     = 'Set-MpPreference\s+-DisableRealtimeMonitoring\s+\$true'
            Description = '关闭 Defender 实时扫描.'
            Hint        = '禁止.'
        }
    @{
            Id          = 'BYP-003'
            Severity    = 'CRITICAL'
            Title       = 'Add-MpPreference 添加 Defender 排除'
            # 实际调用 Add-MpPreference -ExclusionPath "..." (必须配 -ExclusionPath 或 -ExclusionExtension)
            Pattern     = 'Add-MpPreference\s+-(?:ExclusionPath|ExclusionExtension)\s+["''\$]'
            Description = '向 Defender 添加排除路径/扩展名 (常用于隐藏恶意文件).'
            Hint        = '禁止.'
        }
    @{
            Id          = 'BYP-004'
            Severity    = 'CRITICAL'
            Title       = 'Stop-Service / Set-Service 关闭安全服务'
            Pattern     = 'Stop-Service\s+-?Name\s+["'']?WinDefend|Set-Service\s+-?Name\s+["'']?WinDefend\s+-?StartupType\s+["'']?Disabled'
            Description = '直接停止 Defender 服务.'
            Hint        = '禁止.'
        }
    @{
            Id          = 'BYP-005'
            Severity    = 'WARNING'
            Title       = '修改 UAC 策略'
            # 实际调用 New-ItemProperty -Path HKLM:\... -Name EnableLUA
            Pattern     = 'New-ItemProperty\s+-?Path\s+.*?HKLM:\\.*?SOFTWARE.*?Microsoft.*?Windows.*?CurrentVersion.*?Policies.*?System\s+-?Name\s+["'']?(?:EnableLUA|ConsentPromptBehaviorAdmin)'
            Description = '修改 UAC 启用/提示行为 (可能被滥用).'
            Hint        = '禁止修改 UAC.'
        }

    # --- 3_persistence_audit ---
    @{
            Id          = 'PER-001'
            Severity    = 'WARNING'
            Title       = 'schtasks 注册计划任务 (需走 Install-ScheduledTask.ps1)'
            # 实际调用 schtasks /Create /TN ...
            Pattern     = 'schtasks\s+/(?:Create|CreateXML)'
            Description = '直接注册计划任务 (应走 Install-ScheduledTask.ps1 显式审计流程).'
            Hint        = '调用 src/Install-ScheduledTask.ps1 而非直接 schtasks.'
        }
    @{
            Id          = 'PER-002'
            Severity    = 'CRITICAL'
            Title       = '注册表 Run / RunOnce'
            # 实际调用: New-ItemProperty -Path "...\CurrentVersion\Run" -Name "X"
            # Path 通常在引号里, "CurrentVersion\Run" 后是 ", 然后 \s+-Name
            # 用 CurrentVersion 前缀避免误报
            Pattern     = 'New-ItemProperty\s+-?Path\s+["'']?.*?CurrentVersion\\Run["'']?\s+-?Name'
            Description = '注册 Run/RunOnce 启动项 (典型持久化手法).'
            Hint        = '禁止.'
        }
    @{
            Id          = 'PER-003'
            Severity    = 'WARNING'
            Title       = 'Windows 服务安装'
            Pattern     = 'New-Service\s+-?Name\s+|sc\.exe\s+create\s+'
            Description = '安装 Windows 服务 (高权限持久化).'
            Hint        = '服务安装需独立审计.'
        }
    @{
            Id          = 'PER-004'
            Severity    = 'WARNING'
            Title       = 'WMI 事件订阅'
            # 实际调用: __EventFilter... 或 Register-WmiEvent
            Pattern     = '(?:New-CimInstance.*?__EventFilter|New-CimInstance.*?__EventConsumer|Register-WmiEvent\s+-?Class)'
            Description = 'WMI 持久化 (高级文件集, 即 fileless 持久化).'
            Hint        = '禁止.'
        }

    # --- 6_credential_audit ---
    @{
            Id          = 'CRE-001'
            Severity    = 'CRITICAL'
            Title       = '凭据硬编码 (password=)'
            # 实际声明: $var = @{ password = "..." } 或 password = "..." 在赋值左边
            # 不匹配 description 字符串 (加 negative lookahead: 不在引号注释中)
            Pattern     = '(?i)(?:^|\s|;)(?:password|pwd|passwd|secret|apikey|api_key|token)\s*[:=]\s*["''][^"''\n;]{6,}["'']'
            Description = '明文密码/Token 写进源码.'
            Hint        = '用 Get-Credential 或 Windows Credential Manager.'
        }
    @{
            Id          = 'CRE-002'
            Severity    = 'WARNING'
            Title       = '常见测试密码'
            Pattern     = '(?i)(?:^|\s|;)(?:"'')?(?:test1234?|TestP@ss123|admin123?|passw0rd)["'']'
            Description = '脚本中出现常见测试密码 (即使 demo 也不该有).'
            Hint        = '用占位符 like <REPLACE_WITH_REAL>.'
        }
)

# === 内部: 检测单个文件 ===
function Get-FileFindings {
    param(
        [string]$Path
    )
    $findings = @()
    if (-not (Test-Path $Path)) { return $findings }

    # 白名单文件: 完全跳过
    if ($script:WhitelistFiles -contains $Path) {
        return $findings
    }

    # 白名单目录: 该目录下所有文件跳过
    foreach ($dir in $script:WhitelistDirs) {
        if ($Path -like "$dir*") {
            return $findings
        }
    }

    $content = Get-Content $Path -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if (-not $content) { return $findings }

    # --- 语法有效性检查（.ps1） ---
    # ⚠ 门禁不能只扫危险模式。2026-10-20 实测：src\web_console.ps1 被某次
    #   「反向验证」误写成一行 "x"，**语法完全错误**，但 SecurityCheck 依然
    #   报告 0 findings / 通过。危险模式扫描回答的是「这段代码危不危险」，
    #   语法检查回答的是「这段代码**能不能跑**」——两者不可互相替代。
    #   一个跑都跑不起来的脚本，比一个危险的脚本更糟：它让门禁绿灯，
    #   而依赖它的计划任务会静默失效（DEC-027：注册成功 ≠ 存活）。
    if ([System.IO.Path]::GetExtension($Path) -ieq '.ps1') {
        try {
            $parseErrors = $null
            $tokens = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$parseErrors)
            if ($parseErrors -and $parseErrors.Count -gt 0) {
                $first = $parseErrors[0]
                $findings += [PSCustomObject]@{
                    File        = $Path
                    Line        = $first.Extent.StartLineNumber
                    RuleId      = 'SYN-001'
                    Severity    = 'CRITICAL'
                    Title       = 'PowerShell 脚本语法错误（无法执行）'
                    Description = "解析失败: $($first.Message)"
                    Hint        = '该脚本无法被 pwsh 执行。修复语法错误后再提交；' +
                                  '若文件被意外覆盖，请从暂存区或版本库恢复。'
                    Match       = $first.Message
                }
            }
        } catch {
            $findings += [PSCustomObject]@{
                File        = $Path
                Line        = 1
                RuleId      = 'SYN-002'
                Severity    = 'WARNING'
                Title       = 'PowerShell 脚本无法解析'
                Description = "解析过程异常: $($_.Exception.Message)"
                Hint        = '检查文件是否被截断或编码损坏。'
                Match       = $_.Exception.Message
            }
        }
    }

    foreach ($rule in $script:Rules) {
        $matches = [regex]::Matches($content, $rule.Pattern, [System.Text.RegularExpressions.RegexOptions]::Multiline)
        foreach ($m in $matches) {
            # 二次过滤: 命中位置是否在字符串/注释里 (避免规则定义自命中)
            # 简单启发式: 命中位置前面 200 字符内是否有 Pattern 字面量 (说明是规则定义)
            $ctxStart = [Math]::Max(0, $m.Index - 200)
            $ctxEnd = [Math]::Min($content.Length, $m.Index + $m.Length + 100)
            $ctx = $content.Substring($ctxStart, $ctxEnd - $ctxStart)
            # 如果上下文有 Pattern/Id/Severity/Description 字眼, 是规则定义自身
            $isRuleDef = $ctx -match '(?:Pattern|Id|Severity|Description)\s*='
            if ($isRuleDef) { continue }

            $lineNum = ($content.Substring(0, $m.Index) -split "`n").Count
            $findings += [PSCustomObject]@{
                File        = $Path
                Line        = $lineNum
                RuleId      = $rule.Id
                Severity    = $rule.Severity
                Title       = $rule.Title
                Description = $rule.Description
                Hint        = $rule.Hint
                Match       = $m.Value.Substring(0, [Math]::Min(120, $m.Value.Length))
            }
        }
    }
    return $findings
}

# === 主函数 ===
function Invoke-MingSecurityCheck {
    [CmdletBinding()]
    param(
        [string]$FilePath,
        [switch]$All,
        [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
        [string[]]$ExternalScanRoot = @(),
        [switch]$FailOnCritical,
        [switch]$FailOnWarning,
        [switch]$Quiet
    )

    $allFindings = @()
    # DEC-041：实际扫描到的文件清单，total_files 由它得出（统计与事实同源）
    $scannedFiles = @()
    # DEC-047：外部受管代码根的扫描结果（不存在时必须显式记为「未扫描」）
    $externalReport = @()

    if ($FilePath) {
        $allFindings += Get-FileFindings -Path $FilePath
    }

    if ($All) {
        # 扫描所有 .ps1：src/、remote_agent/src/、tests/、**scripts/**
        # DEC-041 第 26 例：scripts/ 原本不在扫描范围内 ——
        # 该目录存放 Install-*/Harvest-*/WinDbg-Analyze-* 等**提权脚本**，
        # 恰恰是攻击面最高的一批，却从未被 AGENTS.md §4.5 的强制门禁覆盖。
        # 「门禁通过」在字面上成立，在事实上漏掉了最该扫的那一格。
        #
        # 2026-10-20：src\web\ 加入扫描范围，且 .js 也扫。
        # 判别口同 DEC-042：「新增一个目录，里面放的是不是脚本？是 ⇒ 它必须出现在
        # 扫描范围里」。Web 控制台的 app.js 同样是**在浏览器里执行的脚本**，
        # 若它能构造 innerHTML 注入，就把服务器端的门禁防线从内部绕过。
        # 只扫 *.ps1 会让「全栈扫描通过」在一格有风险代码时依然是绿的。
        # 2026-10-20（DEC-047）：外部受管代码根与 *.py 纳入范围。
        # 判别口仍是 DEC-042 那一句：「新增一个目录，里面放的是不是脚本？是 ⇒ 它必须出现在
        # 扫描范围里」。Ming-Skills 发布工程的 tools/ 与 tests/ **会被发布到远端
        # GitHub 仓库**，属于本项目负责维护的代码（AGENTS.md §2.1），却在门禁之外。
        $scanDirs = @('src', 'remote_agent\src', 'tests', 'scripts')
        $scanExts = @('*.ps1', '*.js', '*.py')
        foreach ($dir in $scanDirs) {
            $fullDir = Join-Path $ProjectRoot $dir
            if (Test-Path $fullDir) {
                foreach ($ext in $scanExts) {
                    Get-ChildItem -Path $fullDir -Recurse -Filter $ext -ErrorAction SilentlyContinue | ForEach-Object {
                        if ($scannedFiles -notcontains $_.FullName) {
                            $scannedFiles += $_.FullName
                            $allFindings += Get-FileFindings -Path $_.FullName
                        }
                    }
                }
            }
        }

        # 外部受管代码根（默认取已登记列表；可用 -ExternalScanRoot 覆盖）。
        # 根目录不存在时**显式记录为未扫描**——静默跳过等于给了一个不会响的门禁。
        $roots = @()
        if ($ExternalScanRoot -and $ExternalScanRoot.Count -gt 0) {
            $roots = @($ExternalScanRoot)
        } else {
            $roots = @($script:RegisteredExternalRoots | ForEach-Object { $_.Path })
        }
        foreach ($root in $roots) {
            $resolved = $root
            if (-not [System.IO.Path]::IsPathRooted($resolved)) {
                $resolved = Join-Path $ProjectRoot $resolved
            }
            $entry = [ordered]@{ path = $resolved; exists = $false; files_scanned = 0; note = '' }
            if (Test-Path $resolved) {
                # 规范化路径（去掉 '..\'），让报告里的路径可直接使用。
                $resolved = (Resolve-Path $resolved).Path
                $entry.path = $resolved
                $entry.exists = $true
                foreach ($ext in $scanExts) {
                    Get-ChildItem -Path $resolved -Recurse -Filter $ext -ErrorAction SilentlyContinue | ForEach-Object {
                        if ($scannedFiles -notcontains $_.FullName) {
                            $scannedFiles += $_.FullName
                            $allFindings += Get-FileFindings -Path $_.FullName
                            $entry.files_scanned = $entry.files_scanned + 1
                        }
                    }
                }
            } else {
                $entry.note = 'registered external root not found on this machine; its code was NOT scanned'
            }
            $externalReport += $entry
        }
    }

    # === 输出 ===
    $result = @{
        generated_at = (Get-Date).ToString('o')
        scanned      = if ($FilePath) { $FilePath } else { "$ProjectRoot (全栈)" }
        # DEC-041：total_files 必须等于**实际扫描到的文件数**。
        # 原实现只统计 src\，于是「往 tests\ 或 scripts\ 加文件」不会让该数字变化——
        # 而 AGENTS.md 把「total_files 是否更新」写成了验收判据，等于给了一个
        # 不会响的门禁。现在它直接由 $scannedFiles 得出，统计与事实同源。
        total_files  = if ($FilePath) { 1 } else { $scannedFiles.Count }
        scan_dirs    = if ($FilePath) { @($FilePath) } else { $scanDirs }
        # DEC-047：外部受管代码根的覆盖情况。缺失时必须看得到「未扫描」，
        # 否则 total_files 变小会被误读成「没东西可扫」。
        external_scan_roots = if ($FilePath) { @() } else { @($externalReport) }
        findings     = $allFindings
        summary      = @{
            critical = @($allFindings | Where-Object { $_.Severity -eq 'CRITICAL' }).Count
            warning  = @($allFindings | Where-Object { $_.Severity -eq 'WARNING' }).Count
            info     = @($allFindings | Where-Object { $_.Severity -eq 'INFO' }).Count
            pass     = ($allFindings.Count -eq 0)
        }
    }

    # 写 JSON 报告
    # DEC-032: 全栈扫描与单文件扫描此前共用 `YYYY-MM-DD -security-audit.json`，
    # 后者会覆盖前者。实测后果：governance 探针跑测试期间，某个 -FilePath
    # 调用把全栈结果（18 文件 0 Critical）覆盖成单文件结果
    # （total_files=1, critical=1 —— 扫到的是 Test-SecurityCheck.ps1 的
    # 故障注入临时文件），治理探针随即误报 security_critical。
    # 报告是唯一证据产物，被覆盖 = 证据被伪造，因此按扫描范围分文件。
    $reportDir = Join-Path $ProjectRoot 'reports'
    if (-not (Test-Path $reportDir)) { New-Item -ItemType Directory -Force -Path $reportDir | Out-Null }
    $dateTag = Get-Date -Format 'yyyy-MM-dd'
    if ($FilePath) {
        # 单文件：带上文件名的短摘要，避免互相覆盖
        $leaf = [System.IO.Path]::GetFileNameWithoutExtension($FilePath) -replace '[^\w\-]', '_'
        $reportPath = Join-Path $reportDir "$dateTag -security-audit-$leaf.json"
    } else {
        $reportPath = Join-Path $reportDir "$dateTag -security-audit-fullstack.json"
    }
    $json = $result | ConvertTo-Json -Depth 5
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($reportPath, $json, $utf8NoBom)

    if (-not $Quiet) {
        Write-Host ""
        Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
        Write-Host "  🔐 MING 安全自检 (DEC-005)" -ForegroundColor Cyan
        Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
        Write-Host "  扫描范围: $($result.scanned)"
        Write-Host "  文件数:   $($result.total_files)"
        Write-Host "  Critical: $($result.summary.critical)  Warning: $($result.summary.warning)  Info: $($result.summary.info)"
        Write-Host ""

        if ($allFindings.Count -eq 0) {
            Write-Host "  ✅ 通过" -ForegroundColor Green
        } else {
            foreach ($f in $allFindings) {
                $color = switch ($f.Severity) {
                    'CRITICAL' { 'Red' }
                    'WARNING' { 'Yellow' }
                    default { 'Gray' }
                }
                Write-Host "  [$($f.Severity)] $($f.RuleId): $($f.Title)" -ForegroundColor $color
                Write-Host "    文件: $($f.File):$($f.Line)"
                Write-Host "    命中: $($f.Match)"
                Write-Host "    建议: $($f.Hint)"
                Write-Host ""
            }
        }
        Write-Host "  📄 报告: $reportPath"
    }

    # === 退出码 ===
    if ($FailOnCritical -and $result.summary.critical -gt 0) { exit 1 }
    if ($FailOnWarning -and $result.summary.warning -gt 0) { exit 1 }
    if ($FailOnCritical -eq $false -and $FailOnWarning -eq $false -and $result.summary.critical -gt 0) {
        return @{ Pass = $false; Summary = $result.summary; Findings = $allFindings; TotalFiles = $result.total_files; ExternalScanRoots = @($externalReport) }
    }
    return @{ Pass = $true; Summary = $result.summary; Findings = $allFindings; TotalFiles = $result.total_files; ExternalScanRoots = @($externalReport) }
}

# 注: dot-source 时所有函数自动可用, 不需 Export-ModuleMember

# === 直接执行守卫（DEC-029）===
#
# 问题: 本文件原本**只有函数定义、没有顶层调用**。
#   `pwsh -File src\SecurityCheck.ps1 -All` 会「无输出、exit 0」——
#   看起来完美通过，实际什么都没跑。
#   AGENTS.md §4.5 要求「任何代码改动必须跑 SecurityCheck」，
#   按常规方式执行等于**安全门禁形同虚设**，且没有任何报警。
#
# 解法: 仅当本文件是被**直接执行**（而非 dot-source）时，
#   自动调用 Invoke-MingSecurityCheck。
#   - `pwsh -File src\SecurityCheck.ps1 -All`      → 自动跑（现在才符合直觉）
#   - `. .\src\SecurityCheck.ps1` + 手动 Invoke   → 仍然可用（向后兼容）
#
# 判别方式: $MyInvocation.InvocationName 为 '.' 表示被 dot-source 引入。
$isDotSourced = ($MyInvocation.InvocationName -eq '.')

if (-not $isDotSourced) {
    # 未指定 -FilePath 时默认全栈扫描，避免「跑起来了但扫了 0 个文件」
    $useAll = $All.IsPresent -or [string]::IsNullOrWhiteSpace($FilePath)
    if ($useAll) {
        $autoResult = Invoke-MingSecurityCheck -All -ProjectRoot $ProjectRoot -ExternalScanRoot $ExternalScanRoot `
            -Quiet:$Quiet -FailOnCritical:$FailOnCritical -FailOnWarning:$FailOnWarning
    } else {
        $autoResult = Invoke-MingSecurityCheck -FilePath $FilePath -ProjectRoot $ProjectRoot `
            -Quiet:$Quiet -FailOnCritical:$FailOnCritical -FailOnWarning:$FailOnWarning
    }
    # 门禁语义: Critical/Warning 非零即失败，否则 exit 0
    if ($autoResult.Summary.critical -gt 0) { exit 1 }
    if ($autoResult.Summary.warning -gt 0 -and $FailOnWarning) { exit 1 }
    exit 0
}
