#Requires -Version 5.1

[CmdletBinding()]
param(
    [string]$Configuration = 'Release',
    [string]$SecurityCheckPath = '${PROJECT_PATH}\999_MINIMAX_100_SYS_Maintain\src\SecurityCheck.ps1'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$dist = Join-Path $root 'dist\AgentOS-Installer'
$zip = Join-Path $root 'dist\AgentOS-Installer.zip'

# A refused build must not leave its output behind. The payload is assembled
# before the gates run, so a gate that refuses would otherwise leave a
# half-built tree -- possibly carrying the very content it refused -- on disk
# until the next successful build happened to clean it.
$script:BuildOutputRoot = $root
trap {
    $output = Join-Path $script:BuildOutputRoot 'dist\AgentOS-Installer'
    if (Test-Path -LiteralPath $output) {
        Remove-Item -LiteralPath $output -Recurse -Force -ErrorAction SilentlyContinue
    }
    $archive = Join-Path $script:BuildOutputRoot 'dist\AgentOS-Installer.zip'
    if (Test-Path -LiteralPath $archive) {
        Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    }
    break
}
$payload = Join-Path $dist 'AgentOS-Payload'
$sourceOut = Join-Path $dist 'Source'
$source = Join-Path $PSScriptRoot 'AgentOS.Setup.cs'
$exe = Join-Path $dist 'AgentOS-Installer.exe'
$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'

if (-not (Test-Path -LiteralPath $csc)) { $csc = 'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe' }
if (-not (Test-Path -LiteralPath $csc)) { throw '找不到 .NET Framework csc.exe，无法构建透明安装器。' }

# The default points at the owner's own source tree. In the distributed
# edition that path does not exist, so fall back to the security scanner that
# ships beside this script. A packaged build must be reproducible on the
# machine that received it, not only on the machine that produced it.
if (-not (Test-Path -LiteralPath $SecurityCheckPath)) {
    $bundled = Join-Path $root 'tools\security_check.ps1'
    if (-not (Test-Path -LiteralPath $bundled)) {
        # In the distributed edition the governance root sits under
        # governance/AgentOS, and the scanner ships at the package root's
        # tools/. Search upward so the layout does not have to be assumed.
        $probe = $root
        for ($level = 0; $level -lt 4 -and $probe; $level++) {
            $candidate = Join-Path $probe 'tools\security_check.ps1'
            if (Test-Path -LiteralPath $candidate) { $bundled = $candidate; break }
            $probe = Split-Path -Parent $probe
        }
    }
    if (Test-Path -LiteralPath $bundled) {
        $SecurityCheckPath = $bundled
        Write-Host "Using the bundled security scanner: $bundled"
    } else {
        throw 'SecurityCheckPath is required before packaging: the default path and tools\security_check.ps1 are both absent.'
    }
}
. $SecurityCheckPath
$auditResults = @()
foreach ($candidate in @($source, $PSCommandPath) +
    @(Get-ChildItem -LiteralPath (Join-Path $root 'bin') -Filter '*.ps1' -File | Select-Object -ExpandProperty FullName) +
    @(Get-ChildItem -LiteralPath (Join-Path $root 'bin') -Filter '*.py' -File | Select-Object -ExpandProperty FullName) +
    @(Get-ChildItem -LiteralPath (Join-Path $root 'tests') -Filter '*.py' -File | Select-Object -ExpandProperty FullName) +
    @(Get-ChildItem -LiteralPath (Join-Path $root 'tests') -Filter '*.ps1' -File | Select-Object -ExpandProperty FullName)) {
    $audit = Invoke-MingSecurityCheck -FilePath $candidate -ProjectRoot $root -Quiet
    $auditResults += [ordered]@{ file = $candidate; summary = $audit.Summary; findings = @($audit.Findings) }
    if ($audit.Summary.critical -gt 0 -or $audit.Summary.warning -gt 0) { throw "Security audit blocked packaging: $candidate" }
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Force -Path (Join-Path $root 'reports') | Out-Null
$auditReport = Join-Path $root ('reports\security-build-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
[IO.File]::WriteAllText($auditReport, ($auditResults | ConvertTo-Json -Depth 8), $utf8)

$expectedDist = [IO.Path]::GetFullPath((Join-Path $root 'dist\AgentOS-Installer'))
if ([IO.Path]::GetFullPath($dist) -ne $expectedDist -or
    (Split-Path -Parent $expectedDist) -ne [IO.Path]::GetFullPath((Join-Path $root 'dist'))) {
    throw 'Refusing cleanup outside the installer output directory.'
}
if (Test-Path -LiteralPath $zip) {
    $archiveDir = Join-Path $root 'dist\archives'
    New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
    $archive = Join-Path $archiveDir ('AgentOS-Installer-before-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.zip')
    Copy-Item -LiteralPath $zip -Destination $archive -ErrorAction Stop
}
if (Test-Path -LiteralPath $dist) { Remove-Item -LiteralPath $dist -Recurse -Force }
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
New-Item -ItemType Directory -Force -Path $payload, $sourceOut | Out-Null

$managedFiles = @('README.md', 'VERSION')
$managedDirs = @('adapters', 'bin', 'constitution', 'policies', 'profiles', 'protocols', 'runtime', 'schemas', 'templates', 'tests', 'skills')
foreach ($file in $managedFiles) { Copy-Item -LiteralPath (Join-Path $root $file) -Destination (Join-Path $payload $file) -Force }
foreach ($dir in $managedDirs) { Copy-Item -LiteralPath (Join-Path $root $dir) -Destination (Join-Path $payload $dir) -Recurse -Force }
# The publisher refuses to redistribute material it classifies reference_only,
# and the installer payload is the same content in a different envelope. A Skill
# that does not travel with the published corpus must not reach a target
# machine through the installer either.
$allowlistPath = Join-Path $root 'policies\REDISTRIBUTION-ALLOWLIST.json'
if (Test-Path -LiteralPath $allowlistPath) {
    $allowlist = Get-Content -LiteralPath $allowlistPath -Raw -Encoding UTF8 | ConvertFrom-Json
    # The list is INCLUSION based: a Skill travels only when the declaration
    # names it. An exclusion list would let a Skill that nobody classified
    # travel freely, which is exactly how material the publisher refuses to
    # redistribute reaches another machine.
    $permitted = @($allowlist.skills | ForEach-Object { ([string]$_.path).Replace('\', '/').TrimStart('/') })
    $excluded = @($allowlist.excluded | ForEach-Object { ([string]$_.path).Replace('\', '/').TrimStart('/') })
    $skillsRoot = Join-Path $payload 'skills'
    if (Test-Path -LiteralPath $skillsRoot) {
        foreach ($skillDir in (Get-ChildItem -LiteralPath $skillsRoot -Directory -ErrorAction SilentlyContinue)) {
            $relative = ('skills/' + $skillDir.Name)
            if ($excluded -contains $relative) {
                Remove-Item -LiteralPath $skillDir.FullName -Recurse -Force
                Write-Host "Excluded Skill without redistribution authorisation: $relative"
                continue
            }
            if ($permitted -notcontains $relative) {
                Remove-Item -LiteralPath $skillDir.FullName -Recurse -Force
                Write-Host "Excluded Skill that the declaration does not name: $relative"
            }
        }
    }
}
# Gate F-ND-2: files declared local-only in policies/NON-DISTRIBUTABLE.json
# must never enter the installer payload. The declaration is the single source
# of truth shared with the governed-corpus publisher, so one edit governs both
# channels. A copy of a declared file inherits its status.
$ndPolicyPath = Join-Path $root 'policies\NON-DISTRIBUTABLE.json'
# The declaration is exempt only at this path inside the PAYLOAD. The
# declaration names the signatures it protects, so it necessarily contains
# them; a file that merely shares its name is not exempt.
$ndPolicyPayloadPath = Join-Path $payload 'policies\NON-DISTRIBUTABLE.json'
if (-not (Test-Path -LiteralPath $ndPolicyPath)) { throw 'Non-distributable policy missing: policies\NON-DISTRIBUTABLE.json' }
$ndPolicy = Get-Content -LiteralPath $ndPolicyPath -Raw -Encoding UTF8 | ConvertFrom-Json
# A file whose name derives from a declared local-only file is refused UNLESS
# its bytes are exactly those of an explicitly declared exception. The
# exemption is by content digest, so a same-named file whose content was
# replaced is still refused.
function Test-DerivedCopy($file, $stem, $exceptionDigests) {
    $derived = ($file.Name -like "$stem.*") -or ($file.Name -like "$stem-*") -or ($file.Name -eq $stem)
    if (-not $derived) { return $false }
    if ($exceptionDigests.Count -eq 0) { return $true }
    $digest = ''
    try { $digest = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLower() } catch { return $true }
    return ($exceptionDigests.Values -notcontains $digest)
}
$nonDistributable = @($ndPolicy.files | ForEach-Object { $_.path })
$ndExceptions = @($ndPolicy.distributable_exceptions | ForEach-Object { $_.path })
$ndExceptionDigests = @{}
foreach ($exception in $ndPolicy.distributable_exceptions) {
    if ($exception.sha256) { $ndExceptionDigests[[string]$exception.path] = ([string]$exception.sha256).ToLower() }
}
$ndDigests = @{}
if ($ndPolicy.sha256) {
    foreach ($property in $ndPolicy.sha256.PSObject.Properties) {
        $ndDigests[$property.Name] = ([string]$property.Value).ToLower()
    }
}
# Gate F-ND-6: the payload must not carry a confidential identifier in any
# file. The term list stays on this machine and is used only to check the
# payload; it never travels. This is the same content rule the publisher
# applies, so a payload built here and a package published from the same
# tree agree on what is confidential.
$ndTermsPath = Join-Path $root 'policies\REDACTION-TERMS.json'
$ndTerms = @()
if (Test-Path -LiteralPath $ndTermsPath) {
    $ndTermDocument = Get-Content -LiteralPath $ndTermsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($term in $ndTermDocument.terms) {
        # A term is either an object with a pattern or a bare string. The
        # publisher's reader accepts both, so this one must too: a term list
        # that is valid for one gate must not be fatal for the other.
        if ($term -is [string]) {
            if ($term) { $ndTerms += [pscustomobject]@{ pattern = $term; kind = 'literal' } }
            continue
        }
        if ($term -and $term.pattern) { $ndTerms += $term }
    }
}
foreach ($relative in $nonDistributable) {
    $target = Join-Path $payload $relative
    if (Test-Path -LiteralPath $target) {
        # A declared DIRECTORY is removed as a whole. Its contents change
        # every time a script writes a new timestamped snapshot into it, so
        # a file-level rule cannot keep up with it.
        if ((Test-Path -LiteralPath $target -PathType Container)) {
            Remove-Item -LiteralPath $target -Recurse -Force
            Write-Host "Excluded non-distributable directory from payload: $relative"
        } else {
            Remove-Item -LiteralPath $target -Force
            Write-Host "Excluded non-distributable file from payload: $relative"
        }
        continue
    }
    # A declared directory that is not present under this exact name still
    # refuses everything beneath it: the declaration names a prefix, so a
    # renamed or relocated tree inherits the status.
    if ($relative.TrimEnd('/').Contains('/')) {
        $prefix = $relative.TrimEnd('/')
        Get-ChildItem -LiteralPath $payload -Recurse -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName.Replace('\', '/').StartsWith("$prefix/") } |
            ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Recurse -Force
                Write-Host "Excluded non-distributable tree from payload: $($_.FullName.Replace($payload, ''))"
            }
    }
    # A backup or an older revision of a declared file keeps the same stem but
    # different bytes, so its digest does not match. Remove every file that
    # carries the declared stem in any form.
    # A directory declaration has no file stem: the tree rule above already
    # removed everything beneath it.
    if (-not $relative.TrimEnd('/').Contains('/')) {
        $stem = [IO.Path]::GetFileNameWithoutExtension($relative)
        Get-ChildItem -LiteralPath $payload -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { Test-DerivedCopy $_ $stem $ndExceptionDigests } |
            ForEach-Object {
                Remove-Item -LiteralPath $_.FullName -Force
                Write-Host "Excluded non-distributable copy from payload: $($_.FullName.Replace($payload, ''))"
            }
    }
}
# A renamed or relocated copy has the same bytes and the same digest, so it is
# recognised by content rather than by name.
if ($ndDigests.Count -gt 0) {
    foreach ($file in (Get-ChildItem -LiteralPath $payload -Recurse -File -ErrorAction SilentlyContinue)) {
        # Only the declaration at its declared path is exempt, because it
        # names the signatures it is protecting. A file that merely shares
        # the NAME is not exempt: that name is the one an attacker copies.
        if ($file.FullName -eq $ndPolicyPayloadPath) { continue }
        $digest = ''
        try { $digest = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLower() } catch { continue }
        foreach ($entry in $ndDigests.GetEnumerator()) {
            if ($digest -eq $entry.Value) {
                Remove-Item -LiteralPath $file.FullName -Force
                Write-Host "Excluded non-distributable content from payload: $($file.FullName.Replace($payload, ''))"
                break
            }
        }
    }
}
# Verify the exclusion actually took effect rather than trusting the copy loop.
foreach ($relative in $nonDistributable) {
    if (Test-Path -LiteralPath (Join-Path $payload $relative)) {
        throw "Non-distributable file reached the installer payload: $relative"
    }
    # A declared directory is verified by its prefix: the tree must be gone
    # entirely, not merely the exact path.
    if ($relative.TrimEnd('/').Contains('/')) {
        $prefix = $relative.TrimEnd('/')
        $survivor = Get-ChildItem -LiteralPath $payload -Recurse -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName.Replace('\', '/').StartsWith("$prefix/") } |
            Select-Object -First 1
        if ($survivor) {
            throw "Non-distributable tree reached the installer payload: $($survivor.FullName.Replace($payload, ''))"
        }
    }
}
if ($ndDigests.Count -gt 0) {
    $carriedByDigest = Get-ChildItem -LiteralPath $payload -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -ne $ndPolicyPayloadPath } |
        Where-Object {
            $digest = ''
            try { $digest = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower() } catch { }
            $matched = $false
            foreach ($entry in $ndDigests.GetEnumerator()) { if ($digest -eq $entry.Value) { $matched = $true; break } }
            $matched
        }
    if ($carriedByDigest) {
        throw "Non-distributable content reached the installer payload: $($carriedByDigest[0].FullName.Replace($payload, ''))"
    }
}
# The import manifest requires these report assets. The whole reports/ tree is
# NOT packaged: it holds security audits, deployment receipts and client
# backups that are local evidence, not distributable governance source.
$managedReports = @('reports\TOKEN-BUDGET-GOVERNANCE-BRIEF.md')
foreach ($file in $managedReports) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $file))) { throw "Required report asset missing: $file" }
    $target = Join-Path $payload $file
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath (Join-Path $root $file) -Destination $target -Force
}
# The payload is the portable edition. The owner's personal signature and the
# machine paths in the governance source are replaced exactly as the
# published corpus replaces them, so the two surfaces do not differ in a way
# that tells a recipient about the build machine.
$utf8NoBom2 = New-Object System.Text.UTF8Encoding($false)
$ownerPattern = 'Ming Peng \|[^\r\n"]*'
Get-ChildItem -LiteralPath $payload -Recurse -File -Include '*.md', '*.json', '*.txt' -ErrorAction SilentlyContinue |
    ForEach-Object {
        $file = $_
        $content = $null
        try { $content = [IO.File]::ReadAllText($file.FullName) } catch { return }
        if (-not $content.Contains('Ming Peng |')) { return }
        $updated = [regex]::Replace($content, $ownerPattern, '${OWNER_SIGNATURE}')
        [IO.File]::WriteAllText($file.FullName, $updated, $utf8NoBom2)
    }
# The registry must not name a bundled Skill the payload does not carry.
$registryPath = Join-Path $payload 'policies\SKILL-REGISTRY.json'
if (Test-Path -LiteralPath $registryPath) {
    $registry = Get-Content -LiteralPath $registryPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $registryChanged = $false
    foreach ($provider in $registry.providers) {
        if (-not $provider.bundled) { continue }
        $bundled = ([string]$provider.bundled).Replace('\', '/').TrimStart('/')
        if (-not (Test-Path -LiteralPath (Join-Path $payload $bundled))) {
            $provider.bundled = ''
            $registryChanged = $true
        }
    }
    if ($registryChanged) {
        [IO.File]::WriteAllText($registryPath, ($registry | ConvertTo-Json -Depth 12), $utf8NoBom2)
    }
}

# Attribution travels with the payload. The payload carries the owner's
# authored governance Skills and excludes the material whose redistribution
# rights are not established; the notice says so, so a recipient knows what
# the payload deliberately does not contain.
$attribution = @"
AgentOS Installer Payload - attribution

This payload contains owner-authored governance Skills distributed under the
owner's MIT authorisation. It carries no third-party corpus: every Skill in
it is owner-authored, and material whose redistribution rights are not
established is not shipped here.

Material whose redistribution rights are not established is NOT in this
payload. It is classified reference_only in the published catalogue and is
named in policies/REDISTRIBUTION-ALLOWLIST.json. Nothing in this payload
redistributes it. The governed corpus published at
mingpeng2004/AgentOS_Skills_TOOLs carries the same rules and names the
reference_only entries in its catalogue.

The confidential term list stays on the owner's machine. It is used only to
check that this payload carries no customer identifier; it is not included.
"@
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $payload 'NOTICE.md'), $attribution, $utf8NoBom)
Copy-Item -LiteralPath $source -Destination (Join-Path $sourceOut 'AgentOS.Setup.cs') -Force
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $sourceOut 'build-installer.ps1') -Force
# Python bytecode is never distributable source. Remove it from the payload and
# from the source tree, then re-check: a concurrently running test can recreate
# bin\__pycache__ between the copy and the check, which would otherwise ship a
# .pyc that no manifest hash covers.
Get-ChildItem -LiteralPath $payload -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
Get-ChildItem -LiteralPath $root -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notlike (Join-Path $root 'dist\*') -and $_.FullName -notlike (Join-Path $root 'reports\*') } |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
if (@(Get-ChildItem -LiteralPath $payload -Recurse -Directory -Filter '__pycache__').Count -gt 0) {
    throw 'Python cache must not be packaged. Clean source cache separately before building.'
}
# The import manifest is portable too. A Skill this edition does not carry
# cannot be a required file, or the installed copy fails its own import gate
# for a file it was never given. The exclusion is recorded, not silent.
$manifestPath = Join-Path $payload 'runtime\IMPORT-MANIFEST.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$kept = @()
$excludedRequired = @()
foreach ($file in $manifest.required_files) {
    if (Test-Path -LiteralPath (Join-Path $payload $file)) {
        $kept += $file
        continue
    }
    $excludedRequired += $file
}
if ($excludedRequired.Count -gt 0) {
    $manifest.required_files = $kept
    if ($manifest.PSObject.Properties.Name -contains 'excluded_required_files') {
        $manifest.excluded_required_files = @($manifest.excluded_required_files) + $excludedRequired
    } else {
        $manifest | Add-Member -NotePropertyName 'excluded_required_files' -NotePropertyValue $excludedRequired
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 12), $utf8NoBom)
    Write-Host "Import manifest: $($excludedRequired.Count) required file(s) excluded because this edition does not carry them."
}
foreach ($file in $manifest.required_files) {
    if (-not (Test-Path -LiteralPath (Join-Path $payload $file))) {
        throw "Payload is missing a manifest-required file: $file"
    }
}

# Gate F-ND-6: no payload file may carry a confidential identifier. A path
# rule cannot see an identifier typed into an ordinary note, so the content of
# every text file in the payload is checked against the local term list.
if ($ndTerms.Count -gt 0) {
    # Decode every file and decide by CONTENT whether it is text. A file whose
    # extension is not on a list is still text often enough -- a .bak copy, a
    # .step file, a file with no extension at all -- and an extension
    # whitelist is exactly how a leak walks past a gate.
    $carriers = @()
    $declarationCarries = $false
    foreach ($file in (Get-ChildItem -LiteralPath $payload -Recurse -File -ErrorAction SilentlyContinue)) {
        # The declaration is scanned too. It names the signatures it protects,
        # so it must be allowed to carry them -- but it is allowed to carry
        # them only because it is checked to carry nothing else. The
        # exemption is decided by content, never by path.
        $bytes = $null
        try { $bytes = [IO.File]::ReadAllBytes($file.FullName) } catch { continue }
        if ($null -eq $bytes -or $bytes.Length -eq 0) { continue }
        # Try every encoding the content might be in. A file that hides the
        # term behind a NUL byte or a UTF-16 code unit is still a file that
        # carries the term, and "it looked binary" is not a defence.
        $decodings = @(
            [Text.Encoding]::UTF8,
            [Text.Encoding]::Unicode,
            [Text.Encoding]::BigEndianUnicode,
            [Text.Encoding]::GetEncoding(936)
        )
        foreach ($term in $ndTerms) {
            $pattern = [string]$term.pattern
            if (-not $pattern) { continue }
            $found = $false
            foreach ($encoding in $decodings) {
                $content = $null
                try { $content = $encoding.GetString($bytes) } catch { continue }
                if ([string]$term.kind -eq 'regex') {
                    try { $found = [regex]::IsMatch($content, $pattern) } catch { $found = $false }
                } else {
                    $found = $content.IndexOf($pattern, [StringComparison]::OrdinalIgnoreCase) -ge 0
                }
                if ($found) { break }
            }
            if ($found) {
                if ($file.FullName -eq $ndPolicyPayloadPath) { $declarationCarries = $true; break }
                $carriers += $file.FullName.Replace($payload, '')
                break
            }
        }
    }
    if ($carriers.Count -gt 0) {
        throw "Confidential identifier reached the installer payload: $($carriers[0])"
    }
    if ($declarationCarries) {
        throw "The non-distributable declaration itself carries a confidential identifier: $ndPolicyPayloadPath"
    }
}

$arguments = @(
    '/nologo',
    '/target:winexe',
    '/optimize+',
    '/debug-',
    "/out:$exe",
    '/r:System.dll',
    '/r:System.Drawing.dll',
    '/r:System.Windows.Forms.dll',
    '/r:System.Web.Extensions.dll',
    $source
)
& $csc @arguments
if ($LASTEXITCODE -ne 0) { throw "csc failed with exit code $LASTEXITCODE" }

$readme = @"
Agent Governance OS Installer

运行 AgentOS-Installer.exe，选择：
1. AgentOS 目标目录
2. MiniMax Code 安装目录
3. Kimi Code 安装/配置目录
4. 要接入的项目目录（每行一个）
5. 普通操作默认授权域：session / task / turn

安装器是透明的：AgentOS-Payload 和 Source 目录保留在旁边；安装器不联网、不保存凭据、不启动子进程。
普通开发操作可以使用会话授权；删除、凭据、网络、远程、服务、真实硬件、固件烧录和安全控制始终需要逐次确认。
开工前一次性定调开发与软件框架（12 域契约，用户明确确认，不超时），落盘 .agentos\contract；后续需求以修订迭代。
普通偏好完整推荐实际通知后 300 秒无反馈按既有委托采用，记录 delegated_default；不视作用户已同意或验收。
技能矩阵按需选择一个主能力和至多两个约束，候选能力不冒充已部署；新增本地检查工具需 Python 3.9+（不自动安装）。
截止时间和事实来源保存于项目 .agentos\decisions；恢复后先记录用户新反馈再评估。无活动执行循环/调度器时，不自动唤醒关闭的对话。
安装完成后必须完全退出并重新打开 MiniMax Code、VS Code/Kimi Code。

命令行自测：
AgentOS-Installer.exe --self-test
"@
[IO.File]::WriteAllText((Join-Path $dist 'README.txt'), $readme, $utf8)

$manifest = @{
    product = 'Agent Governance OS Installer'
    agentos_version = (Get-Content -LiteralPath (Join-Path $payload 'VERSION') -Raw -Encoding UTF8).Trim()
    package_format = 'transparent-exe-plus-auditable-payload'
    network_access = $false
    child_process_at_install_runtime = $false
    default_approval_scope = 'session'
    high_risk_actions = @((Get-Content -LiteralPath (Join-Path $payload 'policies\APPROVAL-POLICY.json') -Raw -Encoding UTF8 | ConvertFrom-Json).always_single_approval)
    confirmation_domains = 12
    contract_dir = '.agentos/contract'
    preference_wait_seconds = 300
    safety_timeout_allowed = $false
    unattended_wakeup_service = $false
    payload_directory = 'AgentOS-Payload'
    source_directory = 'Source'
}
[IO.File]::WriteAllText((Join-Path $dist 'MANIFEST.json'), ($manifest | ConvertTo-Json -Depth 5), $utf8)

# The report is written outside dist/, because a failed build removes dist/
# and the report is the only evidence of why it failed.
$selfTestReport = Join-Path (Join-Path $root 'reports') 'installer-self-test.log'
$selfTest = Start-Process -FilePath $exe -ArgumentList @('--self-test', ('"' + $selfTestReport + '"')) -WindowStyle Hidden -PassThru
try {
    if (-not $selfTest.WaitForExit(60000)) { $selfTest.Kill(); throw 'Installer self-test timed out after 60 seconds.' }
    $selfTest.Refresh()
    if ($selfTest.ExitCode -ne 0) { throw "Installer self-test failed with exit code $($selfTest.ExitCode)" }
    if (-not (Test-Path -LiteralPath $selfTestReport) -or
        (Get-Content -LiteralPath $selfTestReport -Raw -Encoding UTF8) -notmatch 'Installer self-test passed\.') {
        throw 'Installer self-test did not produce a complete success report.'
    }
} finally { $selfTest.Dispose() }

$hashLines = Get-ChildItem -LiteralPath $dist -File -Recurse | Sort-Object FullName | ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
    $relative = $_.FullName.Substring($dist.Length).TrimStart('\', '/')
    "$hash  $relative"
}
[IO.File]::WriteAllLines((Join-Path $dist 'SHA256SUMS.txt'), $hashLines, $utf8)

Write-Host "Installer built: $exe"
Write-Host "Payload: $payload"
Write-Host "Checksums: $(Join-Path $dist 'SHA256SUMS.txt')"
Compress-Archive -Path $dist -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Transfer package: $zip"
Write-Host "Security audit: $auditReport"
