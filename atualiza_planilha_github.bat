@echo off
REM Script para atualizar a planilha do OneDrive no projeto e enviar ao GitHub
set PLANILHA_ONEDRIVE="c:/Users/alessandra.martinez/OneDrive - Linx SA/RCA_Pocket.xlsx"
set PLANILHA_PROJETO="c:/GIT/rca-pocket/RCA_Pocket.xlsx"

copy %PLANILHA_ONEDRIVE% %PLANILHA_PROJETO% /Y

git add RCA_Pocket.xlsx
git commit -m "Atualiza planilha RCA_Pocket.xlsx do OneDrive"
git push

echo Planilha atualizada e enviada ao GitHub!
pause
