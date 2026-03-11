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
echo   [3] Apenas Abrir Dashboard (usa dados do Excel existente)
echo   [4] Validar Cobertura de TAs (busca GitHub Robot Framework)
if not "%SHAREPOINT_URL%"=="" echo   [5] Abrir Excel Online (SharePoint)
echo   [0] Sair
echo.
echo Nota: O Dashboard sempre lê os dados atualizados do Excel automaticamente.
echo       Se você editou campos manuais no Excel, basta abrir o Dashboard (opção 3).
echo.
set /p OPCAO=Opção: 

if "%OPCAO%"=="1" goto SYNC_ALL
if "%OPCAO%"=="2" goto EXCEL_ONLY
if "%OPCAO%"=="3" goto DASHBOARD_ONLY
if "%OPCAO%"=="4" goto VALIDAR_TAS
if "%OPCAO%"=="5" goto EXCEL_ONLINE
if "%OPCAO%"=="0" goto FIM
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

:: ─── Modo 6: Validar TAs ──────────────────────────────────────────────────────
:VALIDAR_TAS
echo.
echo 🤖 Validando cobertura de Testes Automatizados...
echo.

:: Verifica token GitHub
if "%GITHUB_TOKEN%"=="" (
    echo ⚠️  ATENÇÃO: Token GitHub não configurado!
    echo.
    echo    Para usar este recurso, você precisa:
    echo.
    echo    1. Criar token em: https://github.com/settings/tokens
    echo       ^(Marque permissão: repo - read^)
    echo.
    echo    2. Configurar variável de ambiente:
    echo       PowerShell: $env:GITHUB_TOKEN = "ghp_seu_token"
    echo       CMD:        set GITHUB_TOKEN=ghp_seu_token
    echo.
    echo    3. Ou salvar permanentemente:
    echo       [System.Environment]::SetEnvironmentVariable^('GITHUB_TOKEN', 'ghp_token', 'User'^)
    echo.
    echo    Consulte VALIDACAO_TAS.md para instruções detalhadas.
    echo.
    pause
    goto FIM
)

:: Verifica PyGithub
python -c "import github" 2>nul
if %errorlevel% neq 0 (
    echo 📦 Instalando PyGithub...
    pip install PyGithub -q
)

echo 🔍 Buscando TAs no repositório GitHub...
echo    Repo: MEDIUM-RETAIL-MICROVIX/ta-robotframework
echo.
python validar_tas_planilha.py
if %errorlevel% neq 0 (
    echo ❌ Falha ao validar TAs.
    pause
    goto FIM
)

echo.
echo ✅ Validação concluída!
echo    Coluna "Possui TA" atualizada no Excel.
echo.
set /p ABRIR_DASH=   Abrir Dashboard para visualizar? [S/N]: 
if /i "!ABRIR_DASH!"=="S" (
    echo.
    echo 🚀 Abrindo Dashboard...
    streamlit run dashboard.py --server.port 8501 --server.headless false
)
goto FIM

:FIM
echo.
echo Até logo!
