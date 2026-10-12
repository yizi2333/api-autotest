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

# 选 Python：优先用项目/环境里的 venv，都没有就用当前 python
$Candidates = @(
    "$Root\.venv\Scripts\python.exe",
    "D:\Code\security-lab\.venv\Scripts\python.exe"
)
$Py = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Py) { $Py = "python" }
Write-Host "[ci] Python: $Py" -ForegroundColor Cyan

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
