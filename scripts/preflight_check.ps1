# 投递前终检：确认这个仓库「拿得出手」
#
# ★ 为什么需要它：
#   简历上每写一个名词，面试官就会顺着往下问。所以投出去之前，
#   要机械地确认一遍「写了的东西是不是真的存在、真的能跑」。
#   靠人肉记，一定会漏。
#
# ★ 这也是 JD 职责 5「自研轻量化效率脚本」的一个具体例子：
#   把「发版前要人工核对的一堆事」变成一条命令。
#
# 用法（注意：本文件必须存成 UTF-8 带 BOM，否则 Windows PowerShell 5.1 会按 GBK 读）
#   powershell -File scripts/preflight_check.ps1
#   powershell -File scripts/preflight_check.ps1 -RunTests

param(
    [switch]$RunTests
)

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$script:Results = @()
function Add-Check {
    param([string]$Name, [string]$Status, [string]$Detail)
    $script:Results += [pscustomobject]@{ 检查 = $Name; 结果 = $Status; 说明 = $Detail }
}
function OK   { param($n, $d = "") Add-Check $n "✅" $d }
function WARN { param($n, $d = "") Add-Check $n "⚠️" $d }
function FAIL { param($n, $d = "") Add-Check $n "❌" $d }

Write-Host ""
Write-Host "══════ 投递前终检  $(Get-Date -Format 'yyyy-MM-dd HH:mm') ══════" -ForegroundColor Cyan
Write-Host ""

# ── 1) 必备文件 ─────────────────────────────────────────────────────
$required = @(
    "README.md",
    "requirements.txt",
    "pytest.ini",
    "conftest.py",
    ".gitignore",
    ".github/workflows/autotest.yml",
    "docs/architecture.svg",
    "sut/app.py",
    "data/cases.yaml"
)
$missing = $required | Where-Object { -not (Test-Path $_) }
if ($missing) { FAIL "必备文件齐全" ("缺少: " + ($missing -join ", ")) }
else          { OK   "必备文件齐全" ("$($required.Count) 个都在") }

# ── 2) README 里还有没有「待填」────────────────────────────────────
#   ★ 这是最重要的一条：README 里的「待填」如果跟着简历一起发出去，
#     面试官一眼就会看到 —— 等于自曝「这项目还没做完」。
if (Test-Path "README.md") {
    $readme = Get-Content "README.md" -Encoding UTF8 -Raw
    $todo = ([regex]::Matches($readme, '待填')).Count
    if ($todo -gt 0) { WARN "README 无待填" "$todo 处「待填」还没写（建议至少把「设计取舍」写完）" }
    else             { OK   "README 无待填" "" }
}

# ── 3) git 状态 ─────────────────────────────────────────────────────
$porcelain = git status --porcelain 2>$null
if ($porcelain) { WARN "工作区干净" ("$($porcelain.Count) 个文件未提交") }
else            { OK   "工作区干净" "" }

$branch = git status -sb 2>$null | Select-Object -First 1
if ($branch -match 'ahead (\d+)') { WARN "已推送到远端" "本地领先远端 $($Matches[1]) 个提交" }
elseif ($branch -match 'no upstream') { FAIL "已推送到远端" "没有配置远端" }
else { OK "已推送到远端" "" }

# ── 4) 绝对路径 & 疑似凭据 ──────────────────────────────────────────
$tracked = git ls-files 2>$null
$absHits = @()
$secretHits = @()

# 只在这些【代码类】文件里查绝对路径。
# ★ 为什么不查 .md：文档里引用一个路径往往是为了说明问题（比如「踩坑记录」里
#   引用修复前的那个路径），那不是硬编码，是讲解。
$codeExt = @(".py", ".ps1", ".yml", ".yaml", ".jmx", ".json", ".js", ".ts", ".sh")

foreach ($f in $tracked) {
    if (-not (Test-Path $f)) { continue }

    if ($codeExt -contains [System.IO.Path]::GetExtension($f).ToLower()) {
        # ★ 必须加 -CaseSensitive！
        #   Select-String 默认【不区分大小写】，光写 [A-Z]: 会把小写字母也匹配上 ——
        #   我第一版就因此把 `sut.app:app` 里的 `p:a` 当成了绝对路径。
        #   正则的大小写语义必须显式写清楚。
        $m1 = Select-String -Path $f -Pattern '[A-Za-z]:\\' -Encoding UTF8 -CaseSensitive -EA SilentlyContinue
        if ($m1) { $absHits += $m1 }
    }

    $m2 = Select-String -Path $f -Pattern 'gho_|ghp_|github_pat_|-----BEGIN [A-Z ]*PRIVATE KEY' -Encoding UTF8 -CaseSensitive -EA SilentlyContinue
    if ($m2) { $secretHits += $m2 }
}
if ($absHits)    { WARN "无硬编码绝对路径" ("$($absHits.Count) 处，例如 $($absHits[0].Filename):$($absHits[0].LineNumber)") }
else             { OK   "无硬编码绝对路径" "" }
if ($secretHits) { FAIL "无凭据泄漏" ("$($secretHits.Count) 处，例如 $($secretHits[0].Filename):$($secretHits[0].LineNumber)") }
else             { OK   "无凭据泄漏" "" }

# ── 5) .gitignore 覆盖产物 ──────────────────────────────────────────
if (Test-Path ".gitignore") {
    $gi = Get-Content ".gitignore" -Encoding UTF8 -Raw
    $need = @("report/", "*.db", "jmeter.log")
    $miss = $need | Where-Object { $gi -notmatch [regex]::Escape($_) }
    if ($miss) { WARN ".gitignore 覆盖产物" ("缺: " + ($miss -join ", ")) }
    else       { OK   ".gitignore 覆盖产物" "" }
}

# ── 6) 有没有把产物提交上去 ─────────────────────────────────────────
$junk = $tracked | Where-Object { $_ -match '\.(db|jtl|log)$|^report/' }
if ($junk) { FAIL "没有提交运行产物" (($junk | Select-Object -First 3) -join ", ") }
else       { OK   "没有提交运行产物" "" }

# ── 7) 用例统计 ─────────────────────────────────────────────────────
$py = $null
foreach ($c in @("$Root\.venv\Scripts\python.exe", "$Root\.venv\bin\python")) {
    if (Test-Path $c) { $py = $c; break }
}
if (-not $py) {
    $cmd = Get-Command python -EA SilentlyContinue | Select-Object -First 1
    if ($cmd) { $py = $cmd.Source }
}

if ($py) {
    $collect = & $py -m pytest --collect-only -p no:cacheprovider 2>&1 | Out-String
    if ($collect -match 'collected (\d+) items') {
        $n = [int]$Matches[1]
        if ($n -lt 20) { WARN "用例数量" "$n 条（偏少，"框架"这个词要有说服力建议 40+）" }
        else           { OK   "用例数量" "$n 条" }
    } else {
        WARN "用例数量" "pytest 没跑起来"
    }

    if ($RunTests) {
        Write-Host "  跑测试中（约 1 秒）..." -ForegroundColor DarkGray

        # ★ 为什么不用 Start-Process —— 见 ci_local.ps1 里的同一段注释：
        #   PowerShell 5.1 的 Start-Process 用大小写不敏感的字典装环境变量，
        #   环境里同时存在 NO_PROXY 和 no_proxy 时会抛「已添加项」，进程起不来。
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $py
        $psi.Arguments = "-m uvicorn sut.app:app --port 8000"
        $psi.WorkingDirectory = $Root
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $svc = [System.Diagnostics.Process]::Start($psi)
        $ready = $false
        for ($i = 1; $i -le 20; $i++) {
            try {
                $r = Invoke-WebRequest "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2
                if ($r.StatusCode -eq 200) { $ready = $true; break }
            } catch { Start-Sleep -Seconds 1 }
        }
        if ($ready) {
            $out = & $py -m pytest --no-header -q -p no:cacheprovider 2>&1 | Out-String
            if ($out -match '(\d+) passed') {
                $passed = [int]$Matches[1]
                if ($out -match '(\d+) failed') { FAIL "测试全绿" "$passed passed / $($Matches[1]) failed" }
                else { OK "测试全绿" "$passed passed" }
            } else { FAIL "测试全绿" "没解析到结果" }
        } else {
            FAIL "测试全绿" "被测系统没起来"
        }
        # .NET 起的进程没有 -PassThru，用 HasExited + Kill 收尾
        if ($svc -and -not $svc.HasExited) { try { $svc.Kill() } catch { } }
    }
} else {
    WARN "用例数量" "找不到 python"
}

# ── 汇总 ────────────────────────────────────────────────────────────
Write-Host ""
$script:Results | Format-Table -AutoSize -Wrap -Property 检查, 结果, 说明

$fail = ($script:Results | Where-Object { $_.结果 -eq "❌" }).Count
$warn = ($script:Results | Where-Object { $_.结果 -eq "⚠️" }).Count

Write-Host ""
if ($fail -gt 0) {
    Write-Host "❌ 有 $fail 项必须修 —— 带着这些硬伤投出去，等于把面试机会浪费掉" -ForegroundColor Red
    exit 1
} elseif ($warn -gt 0) {
    Write-Host "🟡 $warn 项建议处理，但不阻塞投递" -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "✅ 全部通过，可以投" -ForegroundColor Green
    exit 0
}
