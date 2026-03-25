"""Atualiza dropdown de Área na aba Acompanhamento do Excel existente."""
from openpyxl import load_workbook
from openpyxl.worksheet.datavalidation import DataValidation
import shutil

onedrive = r"C:\Users\alessandra.martinez\OneDrive - Linx SA\RCA_Pocket.xlsx"
wb = load_workbook(onedrive)
ws = wb.worksheets[1]  # Aba Acompanhamento
print(f"Aba: {ws.title}")

# Remover validações antigas da coluna D (Área)
to_remove = []
for dv in ws.data_validations.dataValidation:
    if dv.type == "list" and "D" in str(dv.sqref):
        print(f"  Removendo validação antiga: {dv.formula1} em {dv.sqref}")
        to_remove.append(dv)
for dv in to_remove:
    ws.data_validations.dataValidation.remove(dv)

# Adicionar nova validação com Sustentação e Arquitetura
dv_new = DataValidation(
    type="list",
    formula1='"FFC,FatInt,SupCrmImp,Sustenta\u00e7\u00e3o,Arquitetura"',
    allow_blank=True,
)
dv_new.sqref = "D2:D200"
ws.add_data_validation(dv_new)
print(f"  Nova validação adicionada em {dv_new.sqref}")

wb.save(onedrive)
wb.close()
print("OneDrive atualizado!")

shutil.copy2(onedrive, r"c:\GIT\rca-pocket\RCA_Pocket.xlsx")
print("Local atualizado!")
