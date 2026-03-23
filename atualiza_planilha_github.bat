@echo off
REM Script para atualizar a planilha do OneDrive no projeto e enviar ao GitHub
cd /d "%~dp0"
set PLANILHA_ONEDRIVE=
for /f "delims=" %%U in ('python _get_config.py excel arquivo_saida 2^>nul') do set PLANILHA_ONEDRIVE=%%U
set PLANILHA_PROJETO="%~dp0RCA_Pocket.xlsx"

if "%PLANILHA_ONEDRIVE%"=="" (
  echo Configuracao excel.arquivo_saida nao encontrada.
  pause
  exit /b 1
)

if not exist "%PLANILHA_ONEDRIVE%" (
  echo Arquivo fonte nao encontrado: %PLANILHA_ONEDRIVE%
  pause
  exit /b 1
)

python -c "import shutil; shutil.copy2(r'%PLANILHA_ONEDRIVE%', %PLANILHA_PROJETO%)"
if %errorlevel% neq 0 (
  echo Fallback: tentando copy nativo...
  copy "%PLANILHA_ONEDRIVE%" %PLANILHA_PROJETO% /Y
)

git add RCA_Pocket.xlsx
git commit -m "Atualiza planilha RCA_Pocket.xlsx do OneDrive"
git push

echo Planilha atualizada e enviada ao GitHub!
pause
