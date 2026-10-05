# Локальная проверка кода: формат, линтер, тесты.
# Запуск: powershell -ExecutionPolicy Bypass -File scripts/check_code.ps1
$ErrorActionPreference = "Continue"

$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    Write-Output "Не найден .venv — создай его: python -m venv .venv"
    Write-Output "Затем: .\.venv\Scripts\pip.exe install -r requirements.txt -r requirements-dev.txt"
    exit 1
}

Write-Output "=== black (форматирование) ==="
& $python -m black .

Write-Output "=== flake8 (линтер) ==="
& $python -m flake8 .

Write-Output "=== pytest (тесты) ==="
& $python -m pytest

if ($LASTEXITCODE -eq 0) {
    Write-Output "OK: код отформатирован, замечаний нет, тесты прошли."
    exit 0
}

Write-Output "ПРОВАЛ: проверьте вывод выше (последняя команда завершилась с кодом $LASTEXITCODE)."
exit $LASTEXITCODE
