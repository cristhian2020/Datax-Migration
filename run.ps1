Set-Location -Path $PSScriptRoot
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "           Iniciando DataX Migration Studio (Web)" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Verificando librerias necesarias..." -ForegroundColor Yellow
python -m pip install -r requirements.txt
Write-Host ""
Write-Host "2. Abriendo plataforma en tu navegador..." -ForegroundColor Green
python -m streamlit run app.py
