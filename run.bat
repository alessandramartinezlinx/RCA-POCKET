@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
title RCA Pocket

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║           🎯  RCA Pocket - Iniciando...             ║
echo ╚══════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: ─── Lê URL do SharePoint do config ─────────────────────────────────────────
set SHAREPOINT_URL=
for /f "delims=" %%U in ('python _get_config.py excel sharepoint_url 2^>nul') do set SHAREPOINT_URL=%%U

:: ─── Verifica Python ─────────────────────────────────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python não encontrado. Instale Python 3.10+ e adicione ao PATH.
    pause
    exit /b 1
)

:: ─── Instala dependências ─────────────────────────────────────────────────────
echo 📦 Verificando dependências...
python -m pip install -r requirements.txt -q --disable-pip-version-check
if %errorlevel% neq 0 (
    echo ❌ Falha ao instalar dependências. Verifique a conexão.
    pause
    exit /b 1
)
echo ✅ Dependências OK
echo.

:: ─── Menu ─────────────────────────────────────────────────────────────────────
echo Escolha uma opção:
echo.
echo   [1] Sincronizar Jira + Gerar Excel + Abrir Dashboard
echo   [2] Apenas Gerar/Atualizar Excel
echo   [3] Apenas Abrir Dashboard (sem sincronizar)
if not "%SHAREPOINT_URL%"=="" echo   [5] Abrir Excel Online (SharePoint)
echo   [4] Sair
echo.
set /p OPCAO=Opção: 

if "%OPCAO%"=="1" goto SYNC_ALL
if "%OPCAO%"=="2" goto EXCEL_ONLY
if "%OPCAO%"=="3" goto DASHBOARD_ONLY
if "%OPCAO%"=="4" goto FIM
if "%OPCAO%"=="5" goto EXCEL_ONLINE
echo Opção inválida.
goto FIM

:: ─── Modo 1: Tudo ────────────────────────────────────────────────────────────
:SYNC_ALL
echo.
echo 🔄 Sincronizando issues do Jira...
python jira_client.py
if %errorlevel% neq 0 (
    echo ⚠️  Aviso: falha na sincronização. Usando cache ou dados mock.
)

echo.
echo 📊 Gerando Excel...
python generate_excel.py
if %errorlevel% neq 0 (
    echo ❌ Falha ao gerar Excel.
    pause
    exit /b 1
)

echo.
echo 🚀 Abrindo Dashboard...
echo    Acesse: http://localhost:8501
echo    Pressione Ctrl+C para encerrar.
echo.
streamlit run dashboard.py --server.port 8501 --server.headless false
goto FIM

:: ─── Modo 2: Só Excel ────────────────────────────────────────────────────────
:EXCEL_ONLY
echo.
echo 📊 Gerando/Atualizando Excel...
python generate_excel.py
if %errorlevel% neq 0 (
    echo ❌ Falha ao gerar Excel.
    pause
    exit /b 1
)
echo.
echo ✅ Excel gerado: RCA_Pocket.xlsx
if not "%SHAREPOINT_URL%"=="" (
    echo.
    set /p ABRIR_ONLINE=   Abrir Excel Online no SharePoint? [S/N]: 
    if /i "!ABRIR_ONLINE!"=="S" start "" "%SHAREPOINT_URL%"
) else (
    echo    Abra o arquivo manualmente para preencher Ações e 5 Whys.
)
pause
goto FIM

:: ─── Modo 3: Só Dashboard ────────────────────────────────────────────────────
:DASHBOARD_ONLY
echo.
echo 🚀 Abrindo Dashboard...
echo    Acesse: http://localhost:8501
echo    Pressione Ctrl+C para encerrar.
echo.
streamlit run dashboard.py --server.port 8501 --server.headless false
goto FIM

:: ─── Modo 5: Abrir Excel Online ────────────────────────────────────────────
:EXCEL_ONLINE
if "%SHAREPOINT_URL%"=="" (
    echo ⚠️  URL do SharePoint não configurada em rca_config.yaml
    echo    Preencha o campo excel.sharepoint_url com o link do Excel Online.
    pause
    goto FIM
)
echo.
echo 🌐 Abrindo Excel Online...
start "" "%SHAREPOINT_URL%"
goto FIM

:FIM
echo.
echo Até logo!
