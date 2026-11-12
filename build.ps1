# Gera dist\BateriaBT\BateriaBT.exe (PyInstaller) e o instalador dist\BateriaBT-Setup.exe (Inno Setup).
# Requisitos: python -m pip install -r requirements.txt pyinstaller; winget install JRSoftware.InnoSetup
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m PyInstaller --noconfirm --clean --windowed --onedir --name BateriaBT `
    --hidden-import hid --collect-submodules vendors bateria_bt.py
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { Write-Warning "Inno Setup 6 não encontrado: só a pasta dist\BateriaBT foi gerada."; exit 0 }
$version = (Select-String -Path updater.py -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value
& $iscc /Qp "/DAppVersion=$version" installer.iss
exit $LASTEXITCODE
