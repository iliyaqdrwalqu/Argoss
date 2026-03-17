# launch.ps1 — Запуск ARGOS Universal OS на Windows 10/11 (PowerShell)
# Использование: powershell -ExecutionPolicy Bypass -File launch.ps1 [аргументы]

param([Parameter(ValueFromRemainingArguments)][string[]]$Args)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  ARGOS UNIVERSAL OS v1.3 — ЗАПУСК" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Найти Python
$python = $null
foreach ($cmd in @("python","py","python3")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) { $python = $cmd; break }
}
if (-not $python) {
    Write-Host "[ОШИБКА] Python не найден. Установи Python 3.10+ с https://python.org" -ForegroundColor Red
    Read-Host "Нажми Enter для выхода"; exit 1
}

# 2. Проверить версию >= 3.10
$ver = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$parts = $ver -split '\.'
if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) {
    Write-Host "[ОШИБКА] Нужен Python 3.10+, найден $ver" -ForegroundColor Red
    Read-Host "Нажми Enter для выхода"; exit 1
}
Write-Host "  Python: $ver" -ForegroundColor Green

# 3. Установить зависимости
$psutilOk = & $python -c "import psutil; print('ok')" 2>$null
if ($psutilOk -ne "ok") {
    Write-Host "  Устанавливаю зависимости..." -ForegroundColor Yellow
    & $python -m pip install -r requirements.txt --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ОШИБКА] Не удалось установить зависимости" -ForegroundColor Red
        Read-Host "Нажми Enter"; exit 1
    }
}

# 4. Первичная инициализация
if (-not (Test-Path ".env")) {
    Write-Host "  Первый запуск — инициализация..." -ForegroundColor Yellow
    & $python genesis.py
}

# 5. Создать папки
foreach ($d in @("data","logs","src\skills","modules","tests\generated")) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# 6. Запуск
$launchArgs = if ($Args.Count -eq 0) { @("--full") } else { $Args }
Write-Host "  Запуск Аргоса ($($launchArgs -join ' '))..." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
& $python main.py @launchArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[ОШИБКА] Аргос завершился с ошибкой. См. logs\argos.log" -ForegroundColor Red
    Read-Host "Нажми Enter для выхода"
}
