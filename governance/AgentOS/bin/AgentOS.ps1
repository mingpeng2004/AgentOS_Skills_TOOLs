#Requires -Version 5.1

[CmdletBinding()]
param(
    [ValidateSet('install', 'diagnose', 'register', 'new-task', 'checkpoint', 'resume', 'grant-approval', 'revoke-approval', 'approval-status', 'evidence-status', 'validate-evidence', 'decision-status', 'evaluate-decisions', 'contract-status', 'contract-check')]
    [string]$Command = 'diagnose',
    [string]$ProjectRoot,
    [string]$TaskId,
    [string]$Title,
    [string]$NextAction,
    [string]$Status,
    [ValidateSet('turn', 'session', 'task')]
    [string]$ApprovalScope = 'session',
    [string]$SessionId,
    [string]$Reason = 'User-approved AgentOS development session',
    [int]$DurationMinutes,
    [switch]$ClientsOnly
)

if ($Command -eq 'install') { throw 'Use tools/portable_install.py for preflight, backups and rollback; legacy install is disabled in the public edition.' }

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:AgentOsRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'VERSION')) -and $env:AGENTOS_HOME) {
    $script:AgentOsRoot = [IO.Path]::GetFullPath($env:AGENTOS_HOME)
}
$script:AgentOsVersion = (Get-Content -LiteralPath (Join-Path $script:AgentOsRoot 'VERSION') -Raw -Encoding UTF8).Trim()

function Write-AgentOsText {
    param([string]$Path, [string]$Content)
    $parent = Split-Path -Parent $Path
    if ($parent -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Content, $utf8)
}

function Get-ProjectPath {
    param([string]$Path)
    if (-not $Path) { throw 'ProjectRoot is required.' }
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "ProjectRoot does not exist: $Path"
    }
    return [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $Path).Path)
}

function Get-ManagedBlock {
    param([string]$Root)
    return @"
<!-- AGENTOS:BEGIN managed v$script:AgentOsVersion -->
## AgentOS 系统治理入口

AGOS-SKILLS：复杂任务读取 protocols/SKILL-MATRIX.md；agentos_skills.py 选主能力和必要约束、检查输入并 gate 产出；候选/缺失能力不冒充已部署，不预载全部。

本项目接入 `Agent Governance OS`。开始复杂任务前读取：

1. `AGENTS.md`、项目需求/契约 SSOT 和当前状态文件。
2. $Root\runtime\BOOT.md。
3. 项目 `.agentos\project.json`、当前任务和最近 checkpoint。

复杂任务必须外置任务状态、逐 Unit 验证并留下证据。没有测试、编译、实测或审计证据，不得声明完成；同类问题第二次失败换路，第三次列根因表，第四次升级。

AGOS-CONFIRM：开工前一次性定调开发与软件框架（12 域契约，需用户明确确认，不超时），落盘 .agentos\contract；后续需求以修订迭代，任务绑定 contract_version 并跑 AgentOS-Contract.ps1 check。读取 protocols/UPFRONT-CONFIRMATION.md。

AGOS-AUTO：已授权普通工作直接推进。完整推荐方案落盘并实际通知后，普通偏好 300 秒无反馈按既有委托采用，记录 delegated_default。安全、未知事实、锁定 SSOT、宿主权限和真实验收不超时放行。每个 Unit/恢复点先记录反馈，再 evaluate .agentos/decisions；等待期间推进独立工作。该明确用户授权更新旧的非安全无限等待规则。读取 protocols/DELEGATED-AUTONOMY.md。

AgentOS 目录：$Root（也可通过 `$env:AGENTOS_HOME` 定位）。客户端适配器、长程协议和安全宪法均以该目录为单一事实源。
<!-- AGENTOS:END managed -->
"@
}

function Add-ManagedSection {
    param([string]$Path)
    $block = Get-ManagedBlock -Root $script:AgentOsRoot
    $truthBlock = "## AgentOS truth gate" + [Environment]::NewLine +
        "No source means no verified fact. Synthetic, failed, stale or conflicted evidence cannot satisfy delivery." + [Environment]::NewLine +
        "Read runtime\AGENT-IMPORT.md and protocols\TRUTH-AND-EVIDENCE.md at every new conversation."
    $block = $block.Replace('<!-- AGENTOS:END managed -->', $truthBlock + [Environment]::NewLine + '<!-- AGENTOS:END managed -->')
    if (Test-Path -LiteralPath $Path) {
        $content = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
    } else {
        $content = "# Project Agent Instructions`r`n"
    }
    $pattern = '(?s)<!-- AGENTOS:BEGIN managed.*?<!-- AGENTOS:END managed -->'
    if ($content -match $pattern) {
        $content = [regex]::Replace($content, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $block })
    } else {
        $content = $content.TrimEnd() + "`r`n`r`n" + $block.Trim() + "`r`n"
    }
    Write-AgentOsText -Path $Path -Content $content
}

function Add-MiniMaxOverlay {
    $client = @((Get-AgentOsClientPaths).clients | Where-Object { $_.id -eq 'minimax-code' })
    if ($client.Count -eq 0 -or -not $client[0].discovered) { return $false }
    $rules = @($client[0].rule_files | Where-Object { [IO.Path]::GetFileName($_) -eq 'agent.md' })
    if ($rules.Count -eq 0) { return $false }
    $path = $rules[0]
    if (-not (Test-Path -LiteralPath (Split-Path -Parent $path))) { return $false }
    $begin = '<!-- AGENTOS:BEGIN minimax overlay -->'
    $end = '<!-- AGENTOS:END minimax overlay -->'
    $block = @"
$begin
## AgentOS 系统治理（托管 v$script:AgentOsVersion）

AGOS-SKILLS：复杂任务读取 protocols/SKILL-MATRIX.md；agentos_skills.py 选主能力和必要约束、检查输入并 gate 产出；候选/缺失能力不冒充已部署，不预载全部。

每次复杂任务先读取 `$env:AGENTOS_HOME\runtime\BOOT.md`，再按需读取 AgentOS 宪法和长程协议。项目 `AGENTS.md`、需求 SSOT、契约和决策记录提供项目事实。

长任务必须有 `.agentos\tasks\` 任务单和 `.agentos\checkpoints\` 检查点；每个 Unit 立即验证并记录机器证据。没有证据不得声明完成。同类问题第二次失败换路，第三次列至少三个根因，第四次升级决策台或用户。授权读取 `policies\APPROVAL-POLICY.json`；高风险动作必须逐次确认。

AGOS-CONFIRM：开工前一次性定调开发与软件框架（12 域契约，需用户明确确认，不超时），落盘 .agentos\contract；后续需求以修订迭代，任务绑定 contract_version 并跑 AgentOS-Contract.ps1 check。读取 protocols/UPFRONT-CONFIRMATION.md。

AGOS-AUTO：已授权普通工作直接推进。普通偏好落盘完整推荐并实际通知后 300 秒无反馈按既有委托采用，记录 delegated_default，不冒充用户同意。安全、未知事实、宿主权限和真实验收不超时放行。每个 Unit/恢复点先记录新反馈，再执行 bin/AgentOS-Decision.ps1 evaluate；等待期间推进独立工作。读取 protocols/DELEGATED-AUTONOMY.md。
$end
"@
    $block = $block.Replace($end, "## AgentOS truth gate" + [Environment]::NewLine +
        "No source means no verified fact. Synthetic, failed, stale or conflicted evidence cannot satisfy delivery." + [Environment]::NewLine +
        "Read runtime\AGENT-IMPORT.md and protocols\TRUTH-AND-EVIDENCE.md at every new conversation." + [Environment]::NewLine + $end)
    if (Test-Path -LiteralPath $path) {
        $content = [IO.File]::ReadAllText($path, [Text.Encoding]::UTF8)
    } else {
        $content = ""
    }
    $pattern = '(?s)<!-- AGENTOS:BEGIN minimax overlay -->.*?<!-- AGENTOS:END minimax overlay -->'
    if ($content -match $pattern) {
        $content = [regex]::Replace($content, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $block })
    } else {
        $content = $content.TrimEnd() + "`r`n`r`n" + $block.Trim() + "`r`n"
    }
    Write-AgentOsText -Path $path -Content $content
    return $true
}

function Get-AgentOsHostBindings {
    $path = Join-Path $script:AgentOsRoot '.local\host-bindings.json'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    return (Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Get-AgentOsField {
    param([object]$Object, [string]$Name, [object]$Default = $null)
    if ($null -eq $Object) { return $Default }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $Default }
    return $property.Value
}

function Get-AgentOsPython {
    $bindings = Get-AgentOsHostBindings
    $runtime = Get-AgentOsField $bindings 'runtime'
    $python = Get-AgentOsField $runtime 'python'
    $pinned = [string](Get-AgentOsField $python 'path' '')
    if ($pinned) {
        if (-not [IO.Path]::IsPathRooted($pinned) -or -not (Test-Path -LiteralPath $pinned -PathType Leaf)) {
            throw "Registered AgentOS Python path is missing or not absolute: $pinned"
        }
        return [ordered]@{ path = $pinned; source = 'host-binding' }
    }
    $command = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command -and $command.Source -and (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
        return [ordered]@{ path = $command.Source; source = 'Get-Command' }
    }
    throw 'No AgentOS Python runtime: host binding unavailable and Get-Command python failed.'
}

function Get-AgentOsClientPaths {
    $python = Get-AgentOsPython
    $tool = Join-Path $script:AgentOsRoot 'bin\agentos_paths.py'
    $json = & $python.path -B $tool inspect --root $script:AgentOsRoot 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Client path resolution failed (python source=$($python.source), exit=$code): $json" }
    return [pscustomobject]@{ resolution = ($json | Out-String | ConvertFrom-Json); python = $python }
}

function Invoke-AgentOsClientDeployment {
    param([string]$Client, [switch]$DryRun)
    $bindings = Join-Path $script:AgentOsRoot '.local\host-bindings.json'
    if (-not (Test-Path -LiteralPath $bindings -PathType Leaf)) {
        return [ordered]@{ state = 'unknown'; reason = 'private host bindings absent; no client writes attempted' }
    }
    $python = Get-AgentOsPython
    $tool = Join-Path $script:AgentOsRoot 'bin\agentos_client_deploy.py'
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) { throw "Controlled deployment tool missing: $tool" }
    $backupRoot = Join-Path $script:AgentOsRoot '.local\client-deployment-backups'
    $arguments = @('-B', $tool, '--root', $script:AgentOsRoot, '--bindings', $bindings,
                   '--backup-root', $backupRoot)
    if ($Client) { $arguments += @('--client', $Client) }
    if ($DryRun) { $arguments += '--dry-run' }
    $receipt = Join-Path $script:AgentOsRoot ("reports\client-deployment-{0}.json" -f [guid]::NewGuid().ToString('N'))
    $arguments += @('--output', $receipt)
    $text = & $python.path @arguments 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Controlled client deployment failed (python source=$($python.source), exit=$code): $text" }
    return (Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Get-AgentOsToolCatalogStatus {
    $python = Get-AgentOsPython
    $tool = Join-Path $script:AgentOsRoot 'bin\agentos_tools.py'
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) { throw 'AgentOS Tool catalog CLI is missing.' }
    $output = & $python.path -B $tool catalog --root $script:AgentOsRoot 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Tool catalog validation failed (exit=$code): $($output | Out-String)" }
    $catalog = ($output | Out-String) | ConvertFrom-Json
    if ($catalog.state -ne 'validated_inventory' -or [int]$catalog.asset_count -lt 1) {
        throw 'Tool catalog returned an invalid or empty inventory.'
    }
    return [ordered]@{ state = $catalog.state; assets = [int]$catalog.asset_count; capabilities = [int]$catalog.capability_count }
}

function Install-ClientAdapters {
    $bindings = Get-AgentOsHostBindings
    $clients = Get-AgentOsField $bindings 'clients'
    if ($null -eq $clients -or @($clients.PSObject.Properties).Count -eq 0) {
        Write-Host 'No registered native client bindings; no client files changed.'
        return [ordered]@{ state = 'unknown'; clients = @() }
    }
    $result = Invoke-AgentOsClientDeployment
    $result | ConvertTo-Json -Depth 8 | Write-Host
    return $result
}

function Register-AgentOsProject {
    param([string]$Path)
    $root = Get-ProjectPath -Path $Path
    $state = Join-Path $root '.agentos'
    foreach ($dir in @('tasks', 'checkpoints', 'evidence', 'reports', 'approvals', 'decisions', 'contract')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $state $dir) | Out-Null
    }
    $project = [ordered]@{
        agentos_version = $script:AgentOsVersion
        project_root = $root
        registered_at = (Get-Date).ToString('o')
        status_file = '.agentos\status.json'
        task_dir = '.agentos\tasks'
        checkpoint_dir = '.agentos\checkpoints'
        evidence_dir = '.agentos\evidence'
        evidence_ledger = '.agentos\evidence\claims.jsonl'
        working_memory = '.agentos\working-memory.json'
        import_contract = 'runtime\AGENT-IMPORT.md'
        truth_protocol = 'protocols\TRUTH-AND-EVIDENCE.md'
        approvals_dir = '.agentos\approvals'
        decisions_dir = '.agentos\decisions'
        autonomy_protocol = 'protocols\DELEGATED-AUTONOMY.md'
        contract_dir = '.agentos\contract'
        interaction_policy = 'policies\INTERACTION-POLICY.json'
        confirmation_protocol = 'protocols\UPFRONT-CONFIRMATION.md'
        design_protocol = 'protocols\DESIGN-CONSISTENCY.md'
        skill_registry = 'policies\SKILL-REGISTRY.json'
        skill_router = 'bin\agentos_skills.py'
        governance_entry = 'AGENTS.md'
    }
    Write-AgentOsText -Path (Join-Path $state 'project.json') -Content ($project | ConvertTo-Json -Depth 5)
    if (-not (Test-Path -LiteralPath (Join-Path $state 'status.json'))) {
        Write-AgentOsText -Path (Join-Path $state 'status.json') -Content (([ordered]@{
            project = $root
            active_task = $null
            state = 'ready'
            last_checkpoint = $null
            updated_at = (Get-Date).ToString('o')
        }) | ConvertTo-Json -Depth 5)
    }
    if (-not (Test-Path -LiteralPath (Join-Path $state 'working-memory.json'))) {
        Write-AgentOsText -Path (Join-Path $state 'working-memory.json') -Content (([ordered]@{
            schema = 'agentos-working-memory-v1'
            agentos_version = $script:AgentOsVersion
            project_root = $root
            active_task = $null
            current_unit = $null
            verified_claim_ids = @()
            open_unknowns = @()
            conflicts = @()
            rejected_assumptions = @()
            last_checkpoint = $null
            next_action = $null
            updated_at = (Get-Date).ToString('o')
        }) | ConvertTo-Json -Depth 6)
    } else {
        $memoryPath = Join-Path $state 'working-memory.json'
        $memoryData = Get-Content -LiteralPath $memoryPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($memoryData.agentos_version -ne $script:AgentOsVersion) {
            $memoryData.agentos_version = $script:AgentOsVersion
            Write-AgentOsText -Path $memoryPath -Content ($memoryData | ConvertTo-Json -Depth 12)
        }
    }
    Add-ManagedSection -Path (Join-Path $root 'AGENTS.md')
    return $root
}

function New-AgentOsTask {
    $root = Register-AgentOsProject -Path (Get-ProjectPath -Path $ProjectRoot)
    if (-not $TaskId -or $TaskId -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{1,80}$') { throw 'TaskId must contain 2-81 safe characters.' }
    if (-not $Title) { throw 'Title is required.' }
    $taskPath = Join-Path $root ".agentos\tasks\$TaskId.md"
    if (Test-Path -LiteralPath $taskPath) { throw "Task already exists: $taskPath" }
    $template = [IO.File]::ReadAllText((Join-Path $script:AgentOsRoot 'templates\TASK.md'), [Text.Encoding]::UTF8)
    $content = $template.Replace('{{TASK_ID}}', $TaskId).Replace('{{TITLE}}', $Title).Replace('{{CREATED_AT}}', (Get-Date).ToString('o')).Replace('{{PROJECT_ROOT}}', $root)
    Write-AgentOsText -Path $taskPath -Content $content
    $statusPath = Join-Path $root '.agentos\status.json'
    $statusData = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $statusData.active_task = $TaskId
    $statusData.state = 'in_progress'
    $statusData.updated_at = (Get-Date).ToString('o')
    Write-AgentOsText -Path $statusPath -Content ($statusData | ConvertTo-Json -Depth 5)
    $memoryPath = Join-Path $root '.agentos\working-memory.json'
    if (Test-Path -LiteralPath $memoryPath) {
        $memoryData = Get-Content -LiteralPath $memoryPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $memoryData.active_task = $TaskId
        $memoryData.updated_at = (Get-Date).ToString('o')
        Write-AgentOsText -Path $memoryPath -Content ($memoryData | ConvertTo-Json -Depth 6)
    }
    Write-Host "Created task: $taskPath"
}

function New-AgentOsCheckpoint {
    $root = Get-ProjectPath -Path $ProjectRoot
    if (-not $TaskId) { throw 'TaskId is required.' }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $path = Join-Path $root ".agentos\checkpoints\$TaskId-$stamp.md"
    $template = [IO.File]::ReadAllText((Join-Path $script:AgentOsRoot 'templates\CHECKPOINT.md'), [Text.Encoding]::UTF8)
    $content = $template.Replace('{{TASK_ID}}', $TaskId).Replace('{{STAMP}}', $stamp)
    if ($NextAction) { $content = [regex]::Replace($content, '(?s)(## 下一步唯一动作\r?\n\r?\n)-', "`$1- $NextAction") }
    Write-AgentOsText -Path $path -Content $content
    $statusPath = Join-Path $root '.agentos\status.json'
    if (Test-Path -LiteralPath $statusPath) {
        $statusData = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $statusData.last_checkpoint = $path
        $statusData.state = 'in_progress'
        $statusData.updated_at = (Get-Date).ToString('o')
        Write-AgentOsText -Path $statusPath -Content ($statusData | ConvertTo-Json -Depth 5)
    }
    $memoryPath = Join-Path $root '.agentos\working-memory.json'
    if (Test-Path -LiteralPath $memoryPath) {
        $memoryData = Get-Content -LiteralPath $memoryPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $memoryData.last_checkpoint = $path
        $memoryData.updated_at = (Get-Date).ToString('o')
        if ($NextAction) { $memoryData.next_action = $NextAction }
        Write-AgentOsText -Path $memoryPath -Content ($memoryData | ConvertTo-Json -Depth 6)
    }
    Write-Host "Created checkpoint: $path"
}

function Show-AgentOsResume {
    $root = Get-ProjectPath -Path $ProjectRoot
    $statePath = Join-Path $root '.agentos\status.json'
    Write-Host "AgentOS project: $root"
    if (Test-Path -LiteralPath $statePath) { Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | Write-Host }
    $tasks = Get-ChildItem -LiteralPath (Join-Path $root '.agentos\tasks') -Filter '*.md' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
    $checkpoints = Get-ChildItem -LiteralPath (Join-Path $root '.agentos\checkpoints') -Filter '*.md' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
    if ($tasks) { Write-Host "Latest task: $($tasks[0].FullName)" }
    if ($checkpoints) { Write-Host "Latest checkpoint: $($checkpoints[0].FullName)" }
    $memoryPath = Join-Path $root '.agentos\working-memory.json'
    if (Test-Path -LiteralPath $memoryPath) { Write-Host "Working memory: $memoryPath" }
    Write-Host 'Saved decisions (read-only): ingest actual new feedback, then evaluate-decisions before dependent work.'
    & (Join-Path $script:AgentOsRoot 'bin\AgentOS-Decision.ps1') -Command status -ProjectRoot $root
}

function Grant-AgentOsApproval {
    $root = Get-ProjectPath -Path $ProjectRoot
    $approvalDir = Join-Path $root '.agentos\approvals'
    New-Item -ItemType Directory -Force -Path $approvalDir | Out-Null
    $id = if ($SessionId) { $SessionId } else { "session_$(Get-Date -Format 'yyyyMMdd-HHmmss')" }
    if ($id -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{1,80}$') { throw 'SessionId must contain 2-81 safe characters.' }
    $ttl = if ($DurationMinutes -gt 0) { $DurationMinutes } elseif ($ApprovalScope -eq 'session') { 480 } elseif ($ApprovalScope -eq 'task') { 240 } else { 15 }
    $grant = [ordered]@{
        agentos_version = $script:AgentOsVersion
        grant_id = $id
        scope = $ApprovalScope
        project_root = $root
        created_at = (Get-Date).ToString('o')
        expires_at = (Get-Date).AddMinutes($ttl).ToString('o')
        reason = $Reason
        critical_requires_single_confirm = $true
        normal_operations = @('read', 'edit_code', 'run_tests', 'build', 'inspect_logs', 'update_agentos_state')
    }
    $path = Join-Path $approvalDir "$id.json"
    Write-AgentOsText -Path $path -Content ($grant | ConvertTo-Json -Depth 5)
    Write-Host "Approval grant created: $path"
    Write-Host "Scope: $ApprovalScope; expires: $($grant.expires_at)"
}

function Revoke-AgentOsApproval {
    $root = Get-ProjectPath -Path $ProjectRoot
    if (-not $SessionId) { throw 'SessionId is required for revoke-approval.' }
    $path = Join-Path $root ".agentos\approvals\$SessionId.json"
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
        Write-Host "Approval grant revoked: $path"
    } else {
        Write-Host "Approval grant not found: $path"
    }
}

function Show-AgentOsApprovalStatus {
    $root = Get-ProjectPath -Path $ProjectRoot
    $approvalDir = Join-Path $root '.agentos\approvals'
    if (-not (Test-Path -LiteralPath $approvalDir)) { Write-Host 'No approval grants.'; return }
    $now = Get-Date
    foreach ($file in (Get-ChildItem -LiteralPath $approvalDir -Filter '*.json' | Sort-Object LastWriteTime -Descending)) {
        try {
            $grant = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            $expired = ([DateTime]$grant.expires_at) -le $now
            Write-Host ("{0} scope={1} expires={2} expired={3}" -f $grant.grant_id, $grant.scope, $grant.expires_at, $expired)
        } catch {
            Write-Host "Invalid approval record: $($file.FullName)"
        }
    }
}

function Invoke-AgentOsDiagnose {
    $script:diagnoseChecks = @()
    function Add-Check { param([string]$Name, [bool]$Pass, [string]$Detail) $script:diagnoseChecks += [ordered]@{ name = $Name; pass = $Pass; detail = $Detail } }
    $coreCheckCount = 0
    Add-Check 'core-import-contract' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'runtime\AGENT-IMPORT.md')) 'next-session import contract'
    Add-Check 'core-boot' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'runtime\BOOT.md')) (Join-Path $script:AgentOsRoot 'runtime\BOOT.md')
    Add-Check 'truth-protocol' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'protocols\TRUTH-AND-EVIDENCE.md')) 'truth protocol'
    Add-Check 'evidence-policy' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'policies\EVIDENCE-POLICY.json')) 'evidence policy'
    Add-Check 'evidence-tool' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'bin\AgentOS-Evidence.ps1')) 'evidence ledger tool'
    Add-Check 'task-protocol' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'protocols\TASK-PROTOCOL.md')) 'structured task protocol'
    Add-Check 'context-pipeline' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'protocols\CONTEXT-PIPELINE.md')) 'context pipeline'
    Add-Check 'autonomy-protocol' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'protocols\DELEGATED-AUTONOMY.md')) 'delegated preference deadlines'
    Add-Check 'decision-policy' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'policies\DECISION-POLICY.json')) '300-second preference policy'
    Add-Check 'decision-tool' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'bin\AgentOS-Decision.ps1')) 'durable decision state machine'
    Add-Check 'contract-protocol' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'protocols\UPFRONT-CONFIRMATION.md')) 'upfront confirmation'
    Add-Check 'skill-matrix' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'protocols\SKILL-MATRIX.md')) 'capability contract workflow'
    Add-Check 'skill-registry' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'policies\SKILL-REGISTRY.json')) 'capability coverage registry'
    Add-Check 'skill-inspector' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'bin\agentos_skills.py')) 'stdlib input and output gate'
    Add-Check 'interaction-policy' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'policies\INTERACTION-POLICY.json')) 'confirmation tiers'
    Add-Check 'contract-tool' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'bin\AgentOS-Contract.ps1')) 'contract state machine'
    Add-Check 'design-protocol' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'protocols\DESIGN-CONSISTENCY.md')) 'design consistency'
    Add-Check 'constitution' (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'constitution\AGENTOS-CONSTITUTION.md')) 'constitution present'
    if (Test-Path -LiteralPath (Join-Path $script:AgentOsRoot 'bin\agentos_tools.py') -PathType Leaf) {
        try {
            $toolStatus = Get-AgentOsToolCatalogStatus
            Add-Check 'tool-catalog' ($toolStatus.assets -gt 0) ("validated {0} assets / {1} capabilities" -f $toolStatus.assets, $toolStatus.capabilities)
        } catch {
            Add-Check 'tool-catalog' $false $_.Exception.Message
        }
    }
    $coreCheckCount = $script:diagnoseChecks.Count
    $clientReport = @()
    $pythonInfo = $null
    $pathError = $null
    try {
        $resolved = Get-AgentOsClientPaths
        $pythonInfo = $resolved.python
        $binding = Get-AgentOsHostBindings
        $hostClients = Get-AgentOsField $binding 'clients'
        foreach ($client in $resolved.resolution.clients) {
            $hostRecord = if ($hostClients) { Get-AgentOsField $hostClients ([string]$client.id) } else { $null }
            $declaredRules = @($client.rule_files)
            $fileState = 'unknown'
            $reason = 'No verified native rule target; canonical fallback remains available but runtime import is unattested.'
            $checks = @()
            if ($declaredRules.Count -gt 0) {
                if ($null -eq $hostRecord) {
                    $fileState = 'missing'
                    $reason = 'Native rule target is declared but has no private host binding/expected hash.'
                } else {
                    try {
                        $deployment = Invoke-AgentOsClientDeployment -Client $client.id -DryRun
                        $items = @($deployment.clients | ForEach-Object { $_.adapter_files } | ForEach-Object { $_ })
                        if ($items.Count -eq 0) { throw 'Registered native target produced no deployment checks.' }
                        $bad = @($items | Where-Object {
                            $_.state -ne 'unchanged' -or -not $_.sha256 -or
                            $_.sha256 -ne $_.before_sha256 -or -not $_.source_sha256 -or
                            -not $_.managed_block_sha256
                        })
                        if ($bad.Count) {
                            $fileState = 'drift'
                            $reason = 'Registered full-target/source/managed-block hash does not match canonical bytes.'
                        } else {
                            $fileState = 'verified'
                            $reason = 'Controlled deployment dry-run verified registered full-target, source and managed-block hashes; runtime remains unattested.'
                        }
                        $checks = $items
                    } catch {
                        $fileState = 'drift'
                        $reason = $_.Exception.Message
                    }
                }
                Add-Check ('client-file-parity:' + $client.id) ($fileState -eq 'verified') $reason
            }
            $states = Get-AgentOsField $hostRecord 'states'
            $importState = [string](Get-AgentOsField $states 'import_reported' 'unattested')
            $behaviorState = [string](Get-AgentOsField $states 'behavior_attested' 'unattested')
            $clientReport += [ordered]@{
                id = $client.id; discovered = [bool]$client.discovered
                native_rule_target_present = [bool](Get-AgentOsField $client 'native_rule_target_present' $false)
                skill_roots = @($client.skill_roots); rule_files = $declaredRules
                file_parity = $fileState; import_reported = $importState
                behavior_attested = $behaviorState; checks = $checks; reason = $reason
            }
        }
    } catch {
        $pathError = $_.Exception.Message
        Add-Check 'client-path-inventory' $false $pathError
    }
    $checks = @($script:diagnoseChecks)
    $coreFailures = @($checks | Select-Object -First $coreCheckCount | Where-Object { -not $_.pass }).Count
    $nativeFailures = @($checks | Select-Object -Skip $coreCheckCount | Where-Object { -not $_.pass }).Count
    $complete = $clientReport.Count -gt 0 -and @($clientReport | Where-Object {
        $_.file_parity -ne 'verified' -or $_.import_reported -ne 'reported' -or $_.behavior_attested -ne 'verified'
    }).Count -eq 0
    $report = [ordered]@{
        generated_at = (Get-Date).ToString('o'); root = $script:AgentOsRoot
        python = $pythonInfo; client_inventory_error = $pathError; checks = $checks; clients = $clientReport
        core_pass = $coreFailures -eq 0; native_client_pass = $nativeFailures -eq 0
        complete = $complete; pass = ($coreFailures -eq 0 -and $nativeFailures -eq 0)
        limits = @('Fallback-only clients remain unknown and do not fail core checks.',
                   'Runtime import and behavior are not inferred from file parity.')
    }
    $path = Join-Path $script:AgentOsRoot "reports\diagnose-$(Get-Date -Format 'yyyyMMdd-HHmmss').json"
    Write-AgentOsText -Path $path -Content ($report | ConvertTo-Json -Depth 5)
    $report | ConvertTo-Json -Depth 5 | Write-Host
    Write-Host "Report: $path"
    if (-not $report.pass) { exit 1 }
}

switch ($Command) {
    'install' {
        Install-ClientAdapters | Out-Null
        $known = @(
            '${PROJECT_PATH}\999_MINIMAX_100_SYS_Maintain',
            '${PROJECT_PATH}\003_STM32F407_4Motor_MiniMax20260924'
        )
        if ($ProjectRoot) { $known += $ProjectRoot }
        if (-not $ClientsOnly) {
            foreach ($item in ($known | Select-Object -Unique)) {
                if (Test-Path -LiteralPath $item -PathType Container) { Register-AgentOsProject -Path $item | Out-Null }
            }
        }
        Invoke-AgentOsDiagnose
    }
    'diagnose' { Invoke-AgentOsDiagnose }
    'register' { Register-AgentOsProject -Path $ProjectRoot | Write-Host }
    'new-task' { New-AgentOsTask }
    'checkpoint' { New-AgentOsCheckpoint }
    'resume' { Show-AgentOsResume }
    'grant-approval' { Grant-AgentOsApproval }
    'revoke-approval' { Revoke-AgentOsApproval }
    'approval-status' { Show-AgentOsApprovalStatus }
    'decision-status' {
        & (Join-Path $script:AgentOsRoot 'bin\AgentOS-Decision.ps1') -Command status -ProjectRoot $ProjectRoot
    }
    'contract-status' {
        & (Join-Path $script:AgentOsRoot 'bin\AgentOS-Contract.ps1') -Command status -ProjectRoot $ProjectRoot
    }
    'contract-check' {
        & (Join-Path $script:AgentOsRoot 'bin\AgentOS-Contract.ps1') -Command check -ProjectRoot $ProjectRoot
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    'evaluate-decisions' {
        & (Join-Path $script:AgentOsRoot 'bin\AgentOS-Decision.ps1') -Command evaluate -ProjectRoot $ProjectRoot
    }
    'evidence-status' {
        & (Join-Path $script:AgentOsRoot 'bin\AgentOS-Evidence.ps1') -Command evidence-status -ProjectRoot $ProjectRoot
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    'validate-evidence' {
        & (Join-Path $script:AgentOsRoot 'bin\AgentOS-Evidence.ps1') -Command validate-ledger -ProjectRoot $ProjectRoot
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}
