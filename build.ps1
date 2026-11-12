# Gera dist\BateriaBT\BateriaBT.exe (pasta com o app e as bibliotecas), para rodar sem Python instalado.
# Requisitos: python -m pip install -r requirements.txt pyinstaller
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m PyInstaller --noconfirm --clean --windowed --onedir --name BateriaBT `
    --hidden-import hid --collect-submodules vendors bateria_bt.py
exit $LASTEXITCODE
