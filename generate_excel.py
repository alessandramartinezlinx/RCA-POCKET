"""
RCA Pocket - Gerador de Excel
==============================
Gera (ou atualiza) o arquivo RCA_Pocket.xlsx com 3 abas:
  📊 Dados                   — Issues do Jira + colunas de análise manual (tabela com filtros)
  🗂️ Acompanhamento Issue    — Itens para resolução definitiva gerados da col. 'Item p/ Resolução Def.'
  👥 Responsáveis             — Tabela de referência dos times

Se o arquivo já existir:
  - Rows com 'Analisado = Sim' são preservadas integralmente (não sobrescritas pelo Jira)
  - Colunas manuais (K, M–Q) são preservadas nas demais rows
  - Aba Acompanhamento é preservada; novos itens de 'Item p/ Resolução Def.' são adicionados
"""

import os
import json
from pathlib import Path
from datetime import datetime

import yaml
from openpyxl import Workbook, load_workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, GradientFill
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule, FormulaRule

from jira_client import JiraClient, MOCK_ACTIONS

# =============================================================================
# PALETA DE CORES
# =============================================================================
HEADER_BG       = "1F4E79"   # azul escuro
HEADER_FG       = "FFFFFF"
SUBHEADER_BG    = "2E75B6"   # azul médio
ALT_ROW_BG      = "EBF3FB"   # azul claro
WHITE           = "FFFFFF"

PRIO_CRITICA    = "FF0000"   # vermelho
PRIO_ALTA       = "FF6600"   # laranja
PRIO_MEDIA      = "FFCC00"   # amarelo
PRIO_BAIXA      = "92D050"   # verde

STATUS_RESOLVIDO    = "E2EFDA"  # verde claro
STATUS_EM_ANALISE   = "FFF2CC"  # amarelo claro
STATUS_ABERTO       = "FCE4D6"  # laranja claro

TIPO_PREVENTIVA  = "D9EAD3"   # verde
TIPO_REMEDIACAO  = "FDE9D9"   # laranja


# =============================================================================
# HELPERS DE ESTILO
# =============================================================================

def _make_thin_border():
    side = Side(style="thin", color="CCCCCC")
    return Border(left=side, right=side, top=side, bottom=side)


def _header_style(ws, row, cols: list, bg=HEADER_BG, fg=HEADER_FG, bold=True):
    for col_idx, val in enumerate(cols, start=1):
        cell = ws.cell(row=row, column=col_idx)
        cell.value = val
        cell.font = Font(bold=bold, color=fg, size=10)
        cell.fill = PatternFill("solid", fgColor=bg)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _make_thin_border()


def _set_col_widths(ws, widths: dict):
    """widths: {col_letter_or_index: width}"""
    for col, width in widths.items():
        if isinstance(col, int):
            col = get_column_letter(col)
        ws.column_dimensions[col].width = width


def _apply_alt_rows(ws, start_row: int, end_row: int, n_cols: int):
    for row in range(start_row, end_row + 1):
        bg = ALT_ROW_BG if row % 2 == 0 else WHITE
        fill = PatternFill("solid", fgColor=bg)
        for col in range(1, n_cols + 1):
            cell = ws.cell(row=row, column=col)
            if cell.fill.fgColor.rgb in ("00000000", "FFFFFFFF", WHITE, ALT_ROW_BG):
                cell.fill = fill
            cell.border = _make_thin_border()
            cell.alignment = Alignment(vertical="center", wrap_text=True)


def _add_table(ws, table_name: str, ref: str, style="TableStyleMedium2"):
    tbl = Table(displayName=table_name, ref=ref)
    tbl.tableStyleInfo = TableStyleInfo(
        name=style, showFirstColumn=False,
        showLastColumn=False, showRowStripes=True, showColumnStripes=False,
    )
    ws.add_table(tbl)


def _to_excel_date(val):
    """Converte string ISO, string DD/MM/YYYY ou datetime/date para objeto datetime.
    Necessário para que fórmulas FILTER() possam comparar datas corretamente."""
    if val is None or val == "":
        return None
    if hasattr(val, "strftime"):
        # Já é datetime ou date — garante que é datetime
        return val if isinstance(val, datetime) else datetime(val.year, val.month, val.day)
    if isinstance(val, str):
        val = val.strip()
        for fmt, length in [
            ("%Y-%m-%dT%H:%M:%S.%f", 26),
            ("%Y-%m-%dT%H:%M:%S",    19),
            ("%Y-%m-%d",             10),
            ("%d/%m/%Y",             10),
        ]:
            try:
                return datetime.strptime(val[:length], fmt)
            except (ValueError, IndexError):
                continue
    return None


# =============================================================================
# ABA: DADOS
# =============================================================================

DADOS_COLS = [
    # ── BLOCO 1: Identificação Jira (cabeçalho azul escuro A–G) ──────────────
    ("A", "Key",                       14),
    ("B", "Resumo",                    52),
    ("C", "Status Jira",               15),
    ("D", "Prioridade",                13),
    ("E", "Data Criação",              14),
    ("F", "Data Resolução",            14),
    ("G", "Dias p/ Resolver",          14),
    # ── BLOCO 2: Categorização Jira (cabeçalho slate H–K) ────────────────────
    ("H", "Time",                      16),
    ("I", "Área",                      18),
    ("J", "Tipo Erro (Auto)",          18),
    ("K", "Ação Realizada no Bug",     50),
    # ── BLOCO 3: Análise Manual (cabeçalho verde L–S) ───────────────────────
    ("L", "Análise da Causa",        40),
    ("M", "Tipo de Ajuste",           22),
    ("N", "Possui TA",               14),
    ("O", "Problema Resolvido?",     18),
    ("P", "Item p/ Resolução Def.",  42),
    ("Q", "QA Principal",            18),
    ("R", "Dev Principal",           18),
    ("S", "Analisado",               14),
]

# Cores dos 3 blocos de cabeçalho
_BG_BLOCO1 = "1F4E79"   # azul escuro  — A–G (dados Jira)
_BG_BLOCO2 = "44546A"   # slate        — H–K (categorização)
_BG_BLOCO3 = "375623"   # verde escuro — L–S (análise manual)

def _build_dados(ws, issues: list, tipos_erro: list, preserved: dict):
    ws.title = "📊 Dados"
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 36

    # ── Cabeçalho com 3 blocos de cores ──────────────────────────────────────
    headers = [col[1] for col in DADOS_COLS]
    _header_style(ws, 1, headers, bg=_BG_BLOCO1)
    for ci in range(8, 12):   # H–K → bloco 2
        cell = ws.cell(row=1, column=ci)
        cell.fill = PatternFill("solid", fgColor=_BG_BLOCO2)
    for ci in range(12, 20):  # L–S → bloco 3 (agora 8 colunas)
        cell = ws.cell(row=1, column=ci)
        cell.fill = PatternFill("solid", fgColor=_BG_BLOCO3)

    _set_col_widths(ws, {col[0]: col[2] for col in DADOS_COLS})

    # ── Fills pastel por bloco (aplicados em TODAS as linhas de dados) ────────
    fill_b1     = PatternFill("solid", fgColor="D6E4F0")  # azul pastel    — A–G
    fill_b2     = PatternFill("solid", fgColor="E8EAED")  # cinza-azul pastel — H–K
    fill_b3     = PatternFill("solid", fgColor="EBF1DE")  # verde pastel   — L–R
    fill_frozen = PatternFill("solid", fgColor="EFF6FF")  # azul claro — linhas congeladas

    # ── Validações — string inline com unicode explícito (compatível Excel + LibreOffice) ──────
    _sim_nao = '"Sim,N\u00e3o"'   # "Sim,Não"
    _ajuste  = '"C\u00f3digo,Banco de Dados,Infraestrutura,Contrata\u00e7\u00e3o de ferramenta"'
    dv_ajuste    = DataValidation(type="list", formula1=_ajuste,   allow_blank=True)
    dv_possui_ta = DataValidation(type="list", formula1=_sim_nao,  allow_blank=True)
    dv_prob_res  = DataValidation(type="list", formula1=_sim_nao,  allow_blank=True)
    dv_analisado = DataValidation(type="list", formula1=_sim_nao,  allow_blank=True)

    dados_analisados  = preserved.get("dados_analisados", {})
    dados_manual_cols = preserved.get("dados_manual_cols", {})

    for row_idx, issue in enumerate(issues, start=2):
        key  = issue.get("key", "")
        link = issue.get("link_jira", "")
        ws.row_dimensions[row_idx].height = 20

        # ── Row congelada (Analisado = Sim) ───────────────────────────────────
        if key in dados_analisados:
            preserved_row = dados_analisados[key]
            for ci, col_def in enumerate(DADOS_COLS, start=1):
                val  = preserved_row.get(col_def[1])
                cell = ws.cell(row=row_idx, column=ci, value=val)
                cell.border    = _make_thin_border()
                cell.font      = Font(size=9)
                cell.alignment = Alignment(vertical="center", wrap_text=False)
                cell.fill      = fill_frozen
            kc = ws.cell(row=row_idx, column=1)
            if link:
                kc.hyperlink = link
            kc.font = Font(color="0563C1", underline="single", size=9, bold=True)
            continue

        # ── Row normal ────────────────────────────────────────────────────────
        manual = dados_manual_cols.get(key, {})
        # Campos manuais: preferência para dados preservados do Excel;
        # fallback para campos mock do issue (demo sem Excel prévio)
        def _m(field):
            v = manual.get(field)
            if v:
                return v
            return issue.get(field, "") or ""

        data_criacao   = issue.get("data_criacao")
        data_resolucao = issue.get("data_resolucao")

        vals = [
            key,                                            # A  Key
            issue.get("resumo", ""),                       # B  Resumo
            issue.get("status", ""),                       # C  Status Jira
            issue.get("prioridade", ""),                   # D  Prioridade
            _to_excel_date(data_criacao),                  # E  Data Criação
            _to_excel_date(data_resolucao),                # F  Data Resolução
            None,                                          # G  Dias p/ Resolver ← fórmula
            issue.get("time", ""),                         # H  Time
            issue.get("area", ""),                         # I  Área
            issue.get("tipo_erro_auto", ""),               # J  Tipo Erro (Auto)
            issue.get("acao_realizada", ""),               # K  Ação Realizada no Bug
            _m("analise_causa"),                  # L  Análise da Causa ← manual
            _m("ajuste_realizado"),               # M  Tipo de Ajuste ← manual
            _m("possui_ta"),                      # N  Possui TA ← manual
            _m("problema_resolvido"),             # O  Problema Resolvido? ← manual
            _m("item_resolucao_def"),             # P  Item p/ Resolução Def. ← manual
            issue.get("qa_principal", ""),         # Q  QA Principal
            issue.get("dev_principal", ""),        # R  Dev Principal
            _m("analisado"),                      # S  Analisado ← manual (ÚLTIMA)
        ]

        # Escreve valores base
        for ci, val in enumerate(vals, start=1):
            cell           = ws.cell(row=row_idx, column=ci, value=val)
            cell.border    = _make_thin_border()
            cell.font      = Font(size=9)
            cell.alignment = Alignment(vertical="center", wrap_text=False)

        # Aplica cor pastel de bloco em TODAS as células da linha
        for ci in range(1, 8):    ws.cell(row=row_idx, column=ci).fill = fill_b1
        for ci in range(8, 12):   ws.cell(row=row_idx, column=ci).fill = fill_b2
        for ci in range(12, 20):  ws.cell(row=row_idx, column=ci).fill = fill_b3

        # G (7): fórmula — diferença em dias entre datas
        g_cell = ws.cell(row=row_idx, column=7)
        g_cell.value         = f'=IF(OR(E{row_idx}="",F{row_idx}=""),"",INT(F{row_idx}-E{row_idx}))'
        g_cell.number_format = "0"
        g_cell.fill          = fill_b1

        # A (1): Key como hyperlink
        kc = ws.cell(row=row_idx, column=1)
        if link:
            kc.hyperlink = link
        kc.font = Font(color="0563C1", underline="single", size=9, bold=True)

        # E (5) e F (6): formato de data
        for dc in [5, 6]:
            c = ws.cell(row=row_idx, column=dc)
            if c.value:
                c.number_format = "DD/MM/YYYY"

        # K (11): Ação Realizada — wrap text; altura variável
        k_cell = ws.cell(row=row_idx, column=11)
        k_cell.alignment = Alignment(vertical="top", wrap_text=True)
        if vals[10]:
            ws.row_dimensions[row_idx].height = 40

        # D (4): cor por prioridade (override do bloco)
        prio_cell   = ws.cell(row=row_idx, column=4)
        colors_prio = {"Crítica": PRIO_CRITICA, "Alta": PRIO_ALTA,
                       "Média": PRIO_MEDIA, "Baixa": PRIO_BAIXA}
        prio_color = colors_prio.get(issue.get("prioridade", ""))
        if prio_color:
            is_dark = issue.get("prioridade") in ("Crítica", "Alta")
            prio_cell.fill = PatternFill("solid", fgColor=prio_color)
            prio_cell.font = Font(bold=True, size=9,
                                  color="FFFFFF" if is_dark else "333333")

        # C (3): cor por status (override do bloco)
        status_cell   = ws.cell(row=row_idx, column=3)
        colors_status = {"Resolvido": STATUS_RESOLVIDO,
                         "Em Análise": STATUS_EM_ANALISE, "Aberto": STATUS_ABERTO}
        st_color = colors_status.get(issue.get("status", ""))
        if st_color:
            status_cell.fill = PatternFill("solid", fgColor=st_color)

    n_rows   = len(issues)
    last_row = max(1 + n_rows, 2)
    last_col = len(DADOS_COLS)
    sfx      = last_row + 50

    dv_ajuste.sqref    = "M2:M{sfx}".format(sfx=sfx)
    dv_possui_ta.sqref = "N2:N{sfx}".format(sfx=sfx)
    dv_prob_res.sqref  = "O2:O{sfx}".format(sfx=sfx)
    dv_analisado.sqref = "S2:S{sfx}".format(sfx=sfx)
    ws.add_data_validation(dv_ajuste)
    ws.add_data_validation(dv_possui_ta)
    ws.add_data_validation(dv_prob_res)
    ws.add_data_validation(dv_analisado)

    _add_table(ws, "TabelaDados", f"A1:{get_column_letter(last_col)}{last_row}", "TableStyleMedium2")



# =============================================================================
# ABA: ACOMPANHAMENTO ISSUE
# =============================================================================

ACOMP_COLS = [
    ("A", "Item",           45),
    ("B", "Responsável",    22),
    ("C", "Área",            22),
    ("D", "Ação",           45),
    ("E", "Status da Ação", 18),
    ("F", "Data Conclusão", 14),
    ("G", "Observação",     40),
]


def _build_acompanhamento(ws, issues: list, preserved_acomp: list, preserved_manual: dict):
    ws.title = "🗂️ Acompanhamento Issue"
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 32

    headers = [col[1] for col in ACOMP_COLS]
    _header_style(ws, 1, headers, bg=SUBHEADER_BG)
    _set_col_widths(ws, {col[0]: col[2] for col in ACOMP_COLS})

    dv_status = DataValidation(
        type="list",
        formula1='"An\u00e1lise,Andamento,Bloqueado,Conclu\u00eddo"',
        allow_blank=True,
    )
    ws.add_data_validation(dv_status)

    dv_area = DataValidation(
        type="list",
        formula1='"FFC,FatInt,SupCrmImp,RC"',
        allow_blank=True,
    )
    ws.add_data_validation(dv_area)

    # Lookup D–H preservados por Key Issue (dados manuais entre gerações)
    preserved_by_key: dict = {r.get("key", ""): r for r in preserved_acomp if r.get("key")}

    colors_acomp = {
        "Concluído": STATUS_RESOLVIDO,
        "Andamento": STATUS_EM_ANALISE,
        "Análise":   ALT_ROW_BG,
        "Bloqueado": STATUS_ABERTO,
    }

    # Uma linha por issue — apenas col A tem fórmula (espelha Dados!O ao vivo)
    for idx, issue in enumerate(issues):
        row_idx   = idx + 2
        dados_row = idx + 2
        key       = issue.get("key", "")
        acomp_data = preserved_by_key.get(key, {})
        # Fallback para campos de acompanhamento embutidos na issue (modo demo/mock)
        if not acomp_data:
            acomp_data = {
                "responsavel":    issue.get("acomp_responsavel", ""),
                "area":           issue.get("acomp_area", ""),
                "acao":           issue.get("acomp_acao", ""),
                "status_acao":    issue.get("acomp_status_acao", ""),
                "data_conclusao": issue.get("acomp_data_conclusao"),
                "observacao":     "",
            }

        ws.row_dimensions[row_idx].height = 20

        # A: única coluna automática — espelha Dados!O; vazio se O estiver vazio
        cell_a = ws.cell(row=row_idx, column=1)
        sheet = "\U0001f4ca Dados"
        cell_a.value = f"=IF('{sheet}'!P{dados_row}=\"\",\"\",'{sheet}'!P{dados_row})"
        cell_a.border    = _make_thin_border()
        cell_a.font      = Font(size=9, color="444444")
        cell_a.alignment = Alignment(vertical="center", wrap_text=True)
        cell_a.fill      = PatternFill("solid", fgColor="F2F2F2")

        # B–G: dados manuais (preservados entre gerações)
        status_val = acomp_data.get("status_acao", "")
        vals_manual = [
            acomp_data.get("responsavel", ""),           # B
            acomp_data.get("area", ""),                  # C
            acomp_data.get("acao", ""),                  # D
            status_val,                                   # E
            (_to_excel_date(acomp_data["data_conclusao"])
             if acomp_data.get("data_conclusao") else None),  # F
            acomp_data.get("observacao", ""),            # G
        ]
        for ci, val in enumerate(vals_manual, start=2):
            cell           = ws.cell(row=row_idx, column=ci, value=val)
            cell.border    = _make_thin_border()
            cell.font      = Font(size=9)
            cell.alignment = Alignment(vertical="center", wrap_text=(ci == 7))

        # Data Conclusão (F=6) — formato de data
        dcf = ws.cell(row=row_idx, column=6)
        if dcf.value:
            dcf.number_format = "DD/MM/YYYY"

        # Cor por Status (E=5)
        sc = colors_acomp.get(status_val)
        if sc:
            ws.cell(row=row_idx, column=5).fill = PatternFill("solid", fgColor=sc)

    n_rows   = len(issues)
    last_row = max(1 + n_rows, 2)
    last_col = len(ACOMP_COLS)

    dv_status.sqref = f"E2:E{last_row + 50}"
    dv_area.sqref   = f"C2:C{last_row + 50}"

    if n_rows > 0:
        _add_table(ws, "TabelaAcompanhamento",
                   f"A1:{get_column_letter(last_col)}{last_row}", "TableStyleMedium7")

    for extra in range(n_rows + 2, n_rows + 12):
        ws.row_dimensions[extra].height = 20
        for col in range(1, last_col + 1):
            ws.cell(row=extra, column=col).border = _make_thin_border()


# =============================================================================
# ABA: RESPONSÁVEIS
# =============================================================================

def _build_responsaveis(ws, times_config: dict):
    ws.title = "👥 Responsáveis"
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 32

    headers = ["Time", "Área", "QA Principal", "QA Secundário", "Dev Principal", "Dev Secundário"]
    _header_style(ws, 1, headers, bg=SUBHEADER_BG)
    _set_col_widths(ws, {"A": 18, "B": 22, "C": 22, "D": 22, "E": 22, "F": 22})

    row_idx = 2
    for time_name, time_data in times_config.items():
        for area in time_data.get("areas", []):
            vals = [
                time_name,
                area.get("nome", ""),
                area.get("qa_principal", ""),
                area.get("qa_secundario", ""),
                area.get("dev_principal", ""),
                area.get("dev_secundario", ""),
            ]
            for col_idx, val in enumerate(vals, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = _make_thin_border()
                cell.font = Font(size=9)
                cell.alignment = Alignment(vertical="center")

            bg = ALT_ROW_BG if row_idx % 2 == 0 else WHITE
            for col_idx in range(1, 7):
                ws.cell(row=row_idx, column=col_idx).fill = PatternFill("solid", fgColor=bg)

            row_idx += 1

    if row_idx > 2:
        _add_table(ws, "TabelaResponsaveis", f"A1:F{row_idx - 1}", "TableStyleLight9")

    # Instruções
    ws.cell(row=row_idx + 1, column=1).value = "ℹ️ Edite o arquivo rca_config.yaml para alterar responsáveis. Re-execute generate_excel.py para atualizar."
    ws.cell(row=row_idx + 1, column=1).font = Font(italic=True, color="888888", size=8)
    ws.merge_cells(f"A{row_idx + 1}:F{row_idx + 1}")


# =============================================================================
# PRESERVAÇÃO DE DADOS MANUAIS
# =============================================================================

def _read_existing_manual_data(filepath: str) -> dict:
    """
    Lê dados existentes do Excel para preservar entre atualizações.

    Retorna:
        {
          "dados_analisados":  {key: {col_name: val, ...}},  # linhas com Analisado=Sim (row inteira)
          "dados_manual_cols": {key: {col_name: val, ...}},  # colunas manuais de todas as linhas
          "acompanhamento":    [{item, key, data_criacao, responsavel, acao,
                                 status_acao, data_conclusao, observacao}, ...],
        }
    Colunas manuais da aba Dados (lookup por nome de cabeçalho):
        L Tipo de Ajuste, M Possui TA, N Problema Resolvido?,
        O Item p/ Resolução Def., R Analisado (última coluna)
    """
    result: dict = {
        "dados_analisados":  {},
        "dados_manual_cols": {},
        "acompanhamento":    [],
    }
    try:
        wb = load_workbook(filepath, read_only=True, data_only=True)
        issues_list: list = []  # ordem das issues para lookup posicional do acompanhamento

        # ── Aba Dados ────────────────────────────────────────────────────────
        dados_sheet = "📊 Dados"
        if dados_sheet in wb.sheetnames:
            ws = wb[dados_sheet]
            all_rows = list(ws.iter_rows(values_only=True))
            if not all_rows:
                wb.close()
                return result

            header = [str(h).strip() if h is not None else "" for h in all_rows[0]]
            # índices 0-based
            col_key       = header.index("Key")            if "Key"                    in header else 0
            col_analisado = header.index("Analisado")      if "Analisado"              in header else None
            col_analise   = header.index("Análise da Causa")    if "Análise da Causa"    in header else None
            col_ajuste    = header.index("Tipo de Ajuste")        if "Tipo de Ajuste"        in header else None
            col_ta        = header.index("Possui TA")              if "Possui TA"              in header else None
            col_prob      = header.index("Problema Resolvido?")    if "Problema Resolvido?"    in header else None
            col_item      = header.index("Item p/ Resolução Def.") if "Item p/ Resolução Def." in header else None

            manual_indices = {
                "analise_causa":      col_analise,
                "ajuste_realizado":   col_ajuste,
                "possui_ta":          col_ta,
                "problema_resolvido": col_prob,
                "item_resolucao_def": col_item,
                "analisado":          col_analisado,
            }

            for row in all_rows[1:]:
                if not any(v for v in row):
                    continue
                key = str(row[col_key] or "").strip()
                if not key:
                    continue

                analisado_val = ""
                if col_analisado is not None and col_analisado < len(row):
                    analisado_val = str(row[col_analisado] or "").strip()

                # Preserva colunas manuais para todas as linhas
                manual_data: dict = {}
                for field_name, ci in manual_indices.items():
                    if ci is not None and ci < len(row):
                        manual_data[field_name] = row[ci]

                result["dados_manual_cols"][key] = manual_data
                issues_list.append({"key": key})

                # Linha inteira preservada se Analisado = "Sim"
                if analisado_val.lower() == "sim":
                    full_row: dict = {}
                    for col_name, ci_val in zip(header, row):
                        full_row[col_name] = ci_val
                    result["dados_analisados"][key] = full_row

        # ── Aba Acompanhamento Issue ──────────────────────────────────────────
        # Col A é fórmula (auto-populada de Dados!O). B e C são valores estáticos.
        # Preservamos apenas D–H (dados manuais), identificados pela Key em B.
        acomp_sheet = "🗂️ Acompanhamento Issue"
        if acomp_sheet in wb.sheetnames:
            ws = wb[acomp_sheet]
            rows = list(ws.iter_rows(min_row=2, values_only=True))
            for row in rows:
                # B (índice 1) contém o Key — valor estático
                key_val = row[1] if len(row) > 1 else None
                if not key_val:
                    continue
                key_str = str(key_val).strip()
                if not key_str or key_str.startswith("="):
                    continue
                result["acompanhamento"].append({
                    "key":            key_str,
                    "responsavel":    row[3] or "" if len(row) > 3 else "",
                    "area":           row[2] or "" if len(row) > 2 else "",
                    "acao":           row[3] or "" if len(row) > 3 else "",
                    "status_acao":    row[4] or "" if len(row) > 4 else "",
                    "data_conclusao": row[5] or None if len(row) > 5 else None,
                    "observacao":     row[6] or "" if len(row) > 6 else "",
                })

        wb.close()
    except Exception as e:
        print(f"[WARN] Não foi possível ler dados existentes: {e}")

    return result


# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def generate_excel(config: dict, output_path: str = None):
    """
    Gera o arquivo RCA_Pocket.xlsx com 3 abas:
      📊 Dados               — issues do Jira + colunas manuais
      🗂️ Acompanhamento Issue — itens de resolução definitiva + plano de ação
      👥 Responsáveis         — mapeamento time → QA/Dev

    Preservação entre re-gerações:
      - Linhas com Analisado = "Sim" ficam intocadas (frozen).
      - Colunas manuais (K, M–Q) são preservadas para demais linhas.
      - Aba Acompanhamento Issue é totalmente preservada; novos itens de
        "Item p/ Resolução Def." são acrescentados sem duplicar.
    """
    output_path = output_path or config.get("excel", {}).get("arquivo_saida", "RCA_Pocket.xlsx")
    output_path = Path(output_path)

    print(f"\n{'='*60}")
    print(f"  RCA Pocket — Gerador de Excel")
    print(f"{'='*60}")

    # 1. Buscar issues no Jira
    client = JiraClient(config)
    issues = client.get_normalized_issues()
    print(f"✅ {len(issues)} issues carregadas")

    # 2. Preservar dados manuais se arquivo já existe
    preserved: dict = {"dados_analisados": {}, "dados_manual_cols": {}, "acompanhamento": []}
    if output_path.exists():
        print(f"🔄 Arquivo existente detectado — preservando dados manuais...")
        preserved = _read_existing_manual_data(str(output_path))
        n_frozen = len(preserved["dados_analisados"])
        n_acomp  = len(preserved["acompanhamento"])
        print(f"   ↳ {n_frozen} linhas congeladas (Analisado=Sim) | "
              f"{n_acomp} itens de acompanhamento preservados")

    # Tipos de erro disponíveis (para dropdown)
    tipos_erro = list(config.get("tipos_erro", {}).keys())

    # 3. Construir workbook
    wb = Workbook()
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]


    ws_dados = wb.create_sheet("📊 Dados")
    ws_acomp = wb.create_sheet("🗂️ Acompanhamento Issue")
    ws_resp  = wb.create_sheet("👥 Responsáveis")

    print("📊 Construindo aba Dados...")
    _build_dados(ws_dados, issues, tipos_erro, preserved)

    print("🗂️  Construindo aba Acompanhamento Issue...")
    _build_acompanhamento(ws_acomp, issues, preserved["acompanhamento"], preserved["dados_manual_cols"])

    print("👥 Construindo aba Responsáveis...")
    _build_responsaveis(ws_resp, config.get("times", {}))

    # 4. Metadados
    wb.properties.title = "RCA Pocket"
    wb.properties.description = f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"

    # 5. Salvar
    wb.save(str(output_path))
    n_acomp_final = len(preserved["acompanhamento"])
    print(f"\n✅ Excel gerado: {output_path.resolve()}")
    print(f"   Abas: {' | '.join(wb.sheetnames)}")
    print(f"   Issues: {len(issues)} | Acompanhamento: {n_acomp_final} itens")
    print(f"{'='*60}\n")

    return str(output_path.resolve())


if __name__ == "__main__":
    config_path = Path(__file__).parent / "rca_config.yaml"
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    generate_excel(cfg)
