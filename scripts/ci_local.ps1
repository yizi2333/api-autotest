# 本地模拟 CI：起被测系统 → 等健康检查 → 跑 pytest → 收尾
#
# ★ 为什么需要它：
#   CI 里干的事就是「起服务 → 等就绪 → 跑测试 → 出报告」。
#   在本地把这个流程脚本化之后：
#     ① 不用每次开两个终端
#     ② CI 挂了能在本地复现（"CI 上红、本地绿"是最烦人的一类问题）
#     ③ 提前验证流水线逻辑，不用等 push 上去才知道写错了
#
# 用法（★ 注意：这个文件必须存成 UTF-8 **带 BOM**，否则 Windows PowerShell 5.1
# 会按 GBK 读，中文全乱、脚本直接解析失败 —— 我在这里真踩过一次）：
#   powershell -File scripts/ci_local.ps1              # 全量
#   powershell -File scripts/ci_local.ps1 -Marker smoke  # 只跑冒烟

param(
    [string]$Marker = "",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# 项目根目录（脚本在 scripts/ 下，往上一层）
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# 选 Python：按优先级找一个可用的解释器
#   ★ 不要写死绝对路径 —— 别人 clone 下来路径不一样，
#     写死的话脚本要么报错，要么更糟：静默用了另一个环境的解释器
$pathPython = $null
$cmd = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
if ($cmd) { $pathPython = $cmd.Source }

$Candidates = @(
    $env:AUTOTEST_PYTHON,                 # 1) 显式指定（最高优先级，也方便 CI 覆盖）
    "$Root\.venv\Scripts\python.exe",     # 2) 项目自带 venv（Windows 布局）
    "$Root\.venv\bin\python",             # 3) 项目自带 venv（Linux / macOS 布局）
    "$Root\venv\Scripts\python.exe",      # 4) 另一种常见目录名
    $pathPython                           # 5) PATH 里的 python（最后兜底）
) | Where-Object { $_ -and (Test-Path $_) }

$Py = $Candidates | Select-Object -First 1
if (-not $Py) {
    Write-Host "[ci] 找不到可用的 Python。" -ForegroundColor Red
    Write-Host "[ci] 请先建环境：python -m venv .venv 然后 .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host "[ci] 或用环境变量指定：AUTOTEST_PYTHON=C:\path\to\python.exe" -ForegroundColor Yellow
    exit 1
}
Write-Host "[ci] Python: $Py" -ForegroundColor Cyan

# ── 校验这个解释器真的有项目依赖 ────────────────────────────────────
#   ★ 为什么必须校验：
#     能"找到一个 python"不等于"找到对的 python"。
#     如果它没装 uvicorn/pytest，脚本会先花 30 秒等健康检查，
#     然后报一句"服务未就绪" —— 你会去查服务，而真正的问题是解释器选错了。
#     **报错信息指错方向，是最贵的调试成本。**
#
#   ★★ 这里有个 PowerShell 5.1 的坑（我在这行代码上真踩了一次）：
#     脚本开头设了 `$ErrorActionPreference = "Stop"`。
#     在这个模式下，**原生命令往 stderr 写任何东西都会被当成终止错误**，
#     直接中断脚本 —— 于是这段"友好报错"代码自己先死了，
#     用户看到的是一个 NativeCommandError 堆栈，而不是我写的提示。
#     所以必须在调用前后把 ErrorActionPreference 临时切回 Continue。
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$depCheck = & $Py -c "import uvicorn, pytest, fastapi, requests, yaml, jsonschema" 2>&1
$depExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($depExit -ne 0) {
    Write-Host "[ci] 这个 Python 缺少项目依赖：" -ForegroundColor Red
    Write-Host "     $Py" -ForegroundColor Red
    Write-Host "     $($depCheck | Select-Object -Last 1)" -ForegroundColor DarkGray
    Write-Host "[ci] 请在该项目下建立独立环境：" -ForegroundColor Yellow
    Write-Host "     python -m venv .venv" -ForegroundColor Yellow
    Write-Host "     .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host "[ci] 或指定已有环境：`$env:AUTOTEST_PYTHON='<python.exe 路径>'" -ForegroundColor Yellow
    exit 1
}

# ── 1) 起被测系统 ───────────────────────────────────────────────────
Write-Host "[ci] 启动被测系统（端口 $Port）..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $Py `
    -ArgumentList "-m", "uvicorn", "sut.app:app", "--port", "$Port" `
    -WorkingDirectory $Root -PassThru -WindowStyle Hidden

$ready = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        $r = Invoke-WebRequest "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 1 }
}

if (-not $ready) {
    Write-Host "[ci] 被测系统 30 秒内未就绪 —— 这就是 CI 里最常见的失败原因" -ForegroundColor Red
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Host "[ci] 被测系统已就绪（等待 $i 秒）" -ForegroundColor Green

# ── 2) 跑测试 ───────────────────────────────────────────────────────
try {
    $pytestArgs = @("-m", "pytest", "--no-header", "-p", "no:cacheprovider")
    if ($Marker) { $pytestArgs += @("-m", $Marker) }

    Write-Host "[ci] 执行: $Py $($pytestArgs -join ' ')" -ForegroundColor Cyan
    & $Py @pytestArgs
    $code = $LASTEXITCODE
}
finally {
    # ── 3) 收尾 ─────────────────────────────────────────────────────
    # ★ 一定要放在 finally 里：测试挂了也要把服务关掉，
    #   否则下次跑会因为端口被占用而失败（然后你以为是代码问题）。
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Write-Host "[ci] 被测系统已停止" -ForegroundColor Cyan
}

if ($code -eq 0) {
    Write-Host "[ci] ✅ 通过" -ForegroundColor Green
} else {
    Write-Host "[ci] ❌ 失败（exit=$code）" -ForegroundColor Red
    Write-Host "[ci] 报告: $Root\report\report.html" -ForegroundColor Yellow
}
exit $code
