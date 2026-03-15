"""
RCA Pocket - Dashboard Streamlit
==================================
Dashboard interativo com múltiplos filtros para análise de RCAs.

Como rodar:
    streamlit run dashboard.py

Lê dados de:
  1. RCA_Pocket.xlsx         (fonte principal — Dados, Ações; decisões tomadas aqui)
  2. data/issues_cache.json  (fallback quando o Excel ainda não foi gerado)
"""

import os
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import yaml

# Garante que o módulo jira_client está no path
sys.path.insert(0, str(Path(__file__).parent))
from jira_client import JiraClient

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================

st.set_page_config(
    page_title="RCA Pocket",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS customizado
st.markdown("""
<style>
    .main { padding-top: 1rem; }

    /* KPI cards — fundo adapta ao tema (claro/escuro) */
    .stMetric { background: var(--secondary-background-color); border-radius: 8px; padding: 8px; border-left: 4px solid #2E75B6; }
    .stMetric label { font-size: 12px !important; }

    /* Headings — herdam a cor do tema, sem fixar valor */
    h1 { font-size: 1.6rem !important; }
    h2 { font-size: 1.2rem !important; }
    h3 { font-size: 1rem !important; }

    .block-container { padding-top: 1rem; padding-bottom: 1rem; }

    /* Sidebar: fundo sempre azul escuro */
    [data-testid="stSidebar"] { background: #1F4E79; }

    /* Texto da sidebar — aplica branco SOMENTE em elementos de texto/label,
       nunca nos inputs/selects (que têm fundo próprio e precisam de cor nativa do tema) */
    [data-testid="stSidebar"] label { color: #BDD7EE !important; font-size: 13px !important; }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] .stMarkdown p { color: white !important; }
    [data-testid="stSidebar"] small,
    [data-testid="stSidebar"] .stCaption,
    [data-testid="stSidebar"] .stCaption p { color: #BDD7EE !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: white !important; }
    [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.2) !important; }
    [data-testid="stSidebar"] .stButton button { color: white !important; }
    [data-testid="stSidebar"] .stRadio label { color: white !important; }

    [data-testid="stAppDeployButton"] { display: none !important; }

    /* Responsividade: colunas rolam horizontalmente em vez de sumir */
    [data-testid="stHorizontalBlock"] { overflow-x: auto; flex-wrap: nowrap; }
    [data-testid="column"] { min-width: 200px; }
    .stPlotlyChart, .js-plotly-plot { min-width: 180px !important; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# CARREGAMENTO DE DADOS
# =============================================================================

@st.cache_data(ttl=300)
def load_config():
    config_path = Path(__file__).parent / "rca_config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# Mapeamento: cabeçalhos do Excel → nomes internos do dashboard
_EXCEL_COL_MAP = {
    "Key":                       "key",
    "Resumo":                    "resumo",
    "Status Jira":               "status",
    "Prioridade":                "prioridade",
    "Data Criação":              "data_criacao",
    "Data Resolução":            "data_resolucao",
    "Dias p/ Resolver":          "tempo_resolucao_dias",
    "Time":                      "time",
    "Área":                      "area",
    "Tipo Erro (Auto)":          "tipo_erro_auto",
    "Ação Realizada no Bug":     "acao_realizada",
    "Análise da Causa":          "analise_causa",
    "Tipo de Ajuste":             "ajuste_realizado",
    "Possui TA":                 "possui_ta",
    "Problema Resolvido?":       "problema_resolvido",
    "QA Principal":              "qa_principal",
    "Dev Principal":             "dev_principal",
    "Analisado":                 "analisado",
    "Qtd Vínculos":              "qtd_vinculos",
    "DeV Responsável pelo Bug":  "dev_responsavel_bug",
    "QA Responsável pelo Bug":   "qa_responsavel_bug",
    "Causa Raiz":                "causa_raiz",
}


@st.cache_data(ttl=300)
def load_issues(config: dict) -> pd.DataFrame:
    """Carrega issues — fonte primária: RCA_Pocket.xlsx (aba 📊 Dados).
    Fallback: data/issues_cache.json → dados mock.
    O Excel tem prioridade porque é onde o time registra decisões manuais
    (Tipo Erro Manual, Revisar?, etc.).
    """
    excel_path = Path(config["excel"]["arquivo_saida"])

    # ── 1ª prioridade: Excel ──────────────────────────────────────────────
    if excel_path.exists():
        try:
            df = pd.read_excel(str(excel_path), sheet_name="📊 Dados", header=0)
            df.columns = [c.strip() for c in df.columns]
            df = df.rename(columns=_EXCEL_COL_MAP)
            df = df.dropna(subset=["key"], how="all")   # descarta linhas vazias
            df = df[df["key"].astype(str).str.startswith(("MODAJOI", "MOD", "RCA"), na=False) |
                    df["key"].astype(str).str.strip().ne("")]
        except Exception as e:
            print(f"[WARN] Falha ao ler Excel: {e} — usando cache JSON")
            df = _load_from_cache(config)
    else:
        # ── 2ª prioridade: cache JSON / mock ─────────────────────────────
        df = _load_from_cache(config)

    # ── Normalização de tipos ─────────────────────────────────────────────
    for col in ["data_criacao", "data_resolucao"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    if "data_criacao" in df.columns:
        df["semana"] = df["data_criacao"].dt.to_period("W").dt.start_time
        df["mes"]    = df["data_criacao"].dt.to_period("M").dt.start_time

    # tipo_erro_manual (corrigido no Excel) tem prioridade sobre o automático
    if "tipo_erro_manual" in df.columns and "tipo_erro_auto" in df.columns:
        df["tipo_erro_efetivo"] = df["tipo_erro_manual"].where(
            df["tipo_erro_manual"].notna() & (df["tipo_erro_manual"].astype(str).str.strip() != ""),
            df["tipo_erro_auto"]
        )
    elif "tipo_erro_auto" in df.columns:
        df["tipo_erro_efetivo"] = df["tipo_erro_auto"]

    return df


def _load_from_cache(config: dict) -> pd.DataFrame:
    """Lê issues do cache JSON; fallback para mock."""
    cache_file = Path(config["cache"]["arquivo_cache"])
    if cache_file.exists():
        try:
            with open(cache_file, encoding="utf-8") as f:
                data = json.load(f)
            issues = data.get("issues", data) if isinstance(data, dict) else data
            return pd.DataFrame(issues)
        except Exception:
            pass
    return pd.DataFrame(_get_mock_issues(config))


@st.cache_data(ttl=300)
def load_acompanhamento(config: dict) -> pd.DataFrame:
    """Carrega aba Acompanhamento Issue do Excel."""
    excel_path = Path(config["excel"]["arquivo_saida"])

    if excel_path.exists():
        try:
            df = pd.read_excel(str(excel_path), sheet_name="🗂️ Acompanhamento Issue", header=0)
            df.columns = [c.strip() for c in df.columns]
            col_map = {
                "Issue Acompanhamento": "issue_acomp",
                "Issue Original":       "issue_original",
                "Responsável":          "responsavel",
                "Área":                   "area",
                "Ação":                   "acao",
                "Status da Ação":       "status_acao",
                "Data Conclusão":       "data_conclusao",
                "Observação":           "observacao",
            }
            df = df.rename(columns=col_map)
            df = df.dropna(how="all")

            # Remove linhas onde Issue de Acompanhamento está vazia
            if "issue_acomp" in df.columns:
                df = df[df["issue_acomp"].notna() & (df["issue_acomp"].astype(str).str.strip() != "")]

            if "data_conclusao" in df.columns:
                df["data_conclusao"] = pd.to_datetime(df["data_conclusao"], errors="coerce")

            return df
        except Exception:
            pass

    return pd.DataFrame(columns=["issue_acomp", "issue_original", "responsavel", "area", "acao",
                                  "status_acao", "data_conclusao", "observacao"])


def _get_mock_issues(config):
    client = JiraClient(config)
    return client.get_normalized_issues()


# =============================================================================
# PALETA DE CORES
# =============================================================================

COLORS_TIPO = {
    "Banco de Dados":    "#5C6BC0",
    "Sistema":           "#EF5350",
    "Indisponibilidade": "#FF7043",
    "Integração":        "#26A69A",
    "Configuração":      "#42A5F5",
    "Segurança":         "#AB47BC",
    "Outro":             "#BDBDBD",
}

COLORS_PRIO = {
    "Crítica": "#D32F2F",
    "Alta":    "#F57C00",
    "Média":   "#FBC02D",
    "Baixa":   "#388E3C",
}

COLORS_STATUS = {
    "Resolvido":  "#4CAF50",
    "Em Análise": "#FF9800",
    "Aberto":     "#F44336",
    "Fechado":    "#9E9E9E",
}

COLORS_ACAO = {
    "Preventiva": "#43A047",
    "Remediação": "#E64A19",
}

# Configuração para permitir download de imagens dos gráficos
PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToAdd": ["toImage"],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "rca_pocket_grafico",
        "height": 600,
        "width": 1200,
        "scale": 2
    }
}


# =============================================================================
# SIDEBAR: FILTROS
# =============================================================================

def build_sidebar(df: pd.DataFrame):
    with st.sidebar:
        st.markdown("## 🎯 RCA Pocket")
        st.markdown("---")
        st.markdown("### 🔍 Filtros")

        if "data_criacao" in df.columns:
            min_date = df["data_criacao"].min()
            max_date = df["data_criacao"].max()
            if pd.isna(min_date):
                min_date = datetime.now() - timedelta(days=180)
            if pd.isna(max_date):
                max_date = datetime.now()
        else:
            min_date = datetime.now() - timedelta(days=180)
            max_date = datetime.now()

        col1, col2 = st.columns(2)
        with col1:
            data_ini = st.date_input("De", value=min_date.date() if hasattr(min_date, "date") else min_date, key="dt_ini")
        with col2:
            data_fim = st.date_input("Até", value=max_date.date() if hasattr(max_date, "date") else max_date, key="dt_fim")

        st.markdown("---")
        st.caption("Vazio = exibe todos. Selecione para filtrar.")

        times = sorted(df["time"].dropna().unique().tolist()) if "time" in df.columns else []
        sel_times = st.multiselect("👥 Time", options=times, default=[],
                                   placeholder="Todos os times")

        df_filtered_time = df[df["time"].isin(sel_times)] if sel_times else df
        areas = sorted(df_filtered_time["area"].dropna().unique().tolist()) if "area" in df.columns else []
        sel_areas = st.multiselect("📁 Área", options=areas, default=[],
                                   placeholder="Todas as áreas")

        tipos = sorted(df["tipo_erro_efetivo"].dropna().unique().tolist()) if "tipo_erro_efetivo" in df.columns else []
        sel_tipos = st.multiselect("🔧 Tipo de Erro", options=tipos, default=[],
                                   placeholder="Todos os tipos")

        statuses = sorted(df["status"].dropna().unique().tolist()) if "status" in df.columns else []
        sel_status = st.multiselect("📌 Status", options=statuses, default=[],
                                    placeholder="Todos os status")

        prios = sorted(df["prioridade"].dropna().unique().tolist()) if "prioridade" in df.columns else []
        sel_prio = st.multiselect("🚨 Prioridade", options=prios, default=[],
                                  placeholder="Todas as prioridades")

        opcoes_ta       = ["Sim", "Não"]
        sel_possui_ta   = st.multiselect("🧪 Possui TA", options=opcoes_ta, default=[],
                                         placeholder="Todos")

        opcoes_res      = ["Sim", "Não"]
        sel_resolvido   = st.multiselect("✅ Problema Resolvido?", options=opcoes_res, default=[],
                                          placeholder="Todos")

        st.markdown("---")
        st.markdown("### ⚙️ Visualização")
        granularidade = st.radio("Tendência por:", ["Semana", "Mês"], index=1, horizontal=True)

        st.markdown("---")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔄 Atualizar", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        with col_btn2:
            if st.button("🧹 Limpar filtros", use_container_width=True):
                for key in ["dt_ini", "dt_fim"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()

        cfg = load_config()
        excel_path = Path(cfg["excel"]["arquivo_saida"])
        if excel_path.exists():
            mtime = datetime.fromtimestamp(excel_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            st.caption(f"📊 RCA_Pocket.xlsx — {mtime}")
        else:
            sync_file = Path(cfg["cache"]["arquivo_ultima_sync"])
            if sync_file.exists():
                st.caption(f"🔄 Cache Jira: {sync_file.read_text().strip()}")
            else:
                st.caption("⚠️ Dados Mock (protótipo)")

    return {
        "data_ini": data_ini,
        "data_fim": data_fim,
        "times": sel_times,
        "areas": sel_areas,
        "tipos": sel_tipos,
        "status": sel_status,
        "prio": sel_prio,
        "possui_ta": sel_possui_ta,
        "problema_resolvido": sel_resolvido,
        "granularidade": granularidade,
    }


# =============================================================================
# APLICAR FILTROS
# =============================================================================

def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    dff = df.copy()

    if "data_criacao" in dff.columns:
        dff = dff[
            (dff["data_criacao"].dt.date >= filters["data_ini"]) &
            (dff["data_criacao"].dt.date <= filters["data_fim"])
        ]

    if filters["times"] and "time" in dff.columns:
        dff = dff[dff["time"].isin(filters["times"])]

    if filters["areas"] and "area" in dff.columns:
        dff = dff[dff["area"].isin(filters["areas"])]

    if filters["tipos"] and "tipo_erro_efetivo" in dff.columns:
        dff = dff[dff["tipo_erro_efetivo"].isin(filters["tipos"])]

    if filters["status"] and "status" in dff.columns:
        dff = dff[dff["status"].isin(filters["status"])]

    if filters["prio"] and "prioridade" in dff.columns:
        dff = dff[dff["prioridade"].isin(filters["prio"])]

    if filters.get("possui_ta") and "possui_ta" in dff.columns:
        dff = dff[dff["possui_ta"].astype(str).str.strip().isin(filters["possui_ta"])]

    if filters.get("problema_resolvido") and "problema_resolvido" in dff.columns:
        dff = dff[dff["problema_resolvido"].astype(str).str.strip().isin(filters["problema_resolvido"])]

    return dff


# =============================================================================
# KPI CARDS
# =============================================================================

def render_kpis(dff: pd.DataFrame, df_acomp: pd.DataFrame):
    total = len(dff)

    # Listas de status reais do Jira
    status_resolvido = ["concluída", "resolvido", "fechado", "done", "closed", "resolved"]
    status_aberto = ["aberto", "em análise", "to do", "in progress", "backlog",
                     "to dev", "in dev", "to test", "in test", "analysis",
                     "to code review", "code review", "to deploy"]
    prio_critica = ["p0 - altíssimo", "p0 - altissimo", "crítica", "critical",
                    "blocker", "highest"]

    s_lower = dff["status"].astype(str).str.strip().str.lower() if "status" in dff.columns else pd.Series(dtype=str)
    p_lower = dff["prioridade"].astype(str).str.strip().str.lower() if "prioridade" in dff.columns else pd.Series(dtype=str)

    resolvidas = int(s_lower.isin(status_resolvido).sum())
    abertos_direto = int(s_lower.isin(status_aberto).sum())
    abertos = abertos_direto if abertos_direto > 0 else (total - resolvidas)
    criticas_abertas = int((p_lower.isin(prio_critica) & ~s_lower.isin(status_resolvido)).sum()) if len(s_lower) > 0 else 0

    taxa = round((resolvidas / total * 100), 1) if total > 0 else 0

    tempo_medio = None
    if "tempo_resolucao_dias" in dff.columns:
        validos = dff["tempo_resolucao_dias"].dropna()
        tempo_medio = round(validos.mean(), 1) if len(validos) > 0 else None

    # Contagem TA
    n_com_ta = n_sem_ta = n_sem_avaliacao = 0
    if "possui_ta" in dff.columns and total > 0:
        ta_lower = dff["possui_ta"].astype(str).str.strip().str.lower()
        n_com_ta = int((ta_lower == "sim").sum())
        n_sem_ta = int((ta_lower == "não").sum())
        n_sem_avaliacao = total - n_com_ta - n_sem_ta

    # % Analisado
    pct_analisado = 0
    n_analisado = 0
    if "analisado" in dff.columns and total > 0:
        n_analisado   = int((dff["analisado"].astype(str).str.strip().str.lower() == "sim").sum())
        pct_analisado = round(n_analisado / total * 100, 1)

    cols = st.columns(6)
    with cols[0]:
        st.metric("📋 Total Issues", total)
        if n_com_ta or n_sem_ta:
            st.caption(f"🟢 {n_com_ta} com TA  \u00a0|\u00a0  🔴 {n_sem_ta} sem TA")
        if n_sem_avaliacao > 0:
            st.caption(f"⚠️ {n_sem_avaliacao} sem avaliação de TA")
    with cols[1]:
        st.metric("🔴 Críticas Abertas", criticas_abertas,
                  delta=f"-{criticas_abertas}" if criticas_abertas > 0 else None,
                  delta_color="inverse")
    with cols[2]:
        st.metric("⏳ Em Aberto", abertos)
    with cols[3]:
        st.metric("✅ Resolvidas", resolvidas)
    with cols[4]:
        st.metric("📈 Taxa Resolução", f"{taxa}%",
                  delta=f"+{taxa}%" if taxa >= 50 else f"{taxa}%",
                  delta_color="normal" if taxa >= 50 else "inverse")
    with cols[5]:
        if tempo_medio:
            st.metric("⏱️ Dias p/ Resolver", f"{tempo_medio}d")
        else:
            st.metric("📊 % Analisado", f"{pct_analisado}%",
                      delta=f"{n_analisado} issues",
                      delta_color="normal" if pct_analisado >= 50 else "off")


# =============================================================================
# GRÁFICOS
# =============================================================================

def chart_tipo_erro(dff: pd.DataFrame) -> go.Figure:
    col = "tipo_erro_efetivo"
    if col not in dff.columns or len(dff) == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem dados de 'Tipo de Erro'<br>Verifique se as colunas 'Tipo Erro (Auto)' ou 'Tipo Erro (Manual)' estão preenchidas",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Incidências por Tipo de Erro", height=300,
                         margin=dict(l=10, r=30, t=40, b=10))
        return fig

    counts = dff[col].dropna().value_counts().reset_index()
    if counts.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Nenhum tipo de erro classificado<br>Preencha as colunas de tipo de erro no Excel",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Incidências por Tipo de Erro", height=300,
                         margin=dict(l=10, r=30, t=40, b=10))
        return fig
    
    counts.columns = ["Tipo de Erro", "Qtd"]
    counts = counts.sort_values("Qtd", ascending=True)
    colors = [COLORS_TIPO.get(t, "#BDBDBD") for t in counts["Tipo de Erro"]]

    fig = go.Figure(go.Bar(
        x=counts["Qtd"], y=counts["Tipo de Erro"],
        orientation="h", marker_color=colors,
        text=counts["Qtd"], textposition="outside",
        hovertemplate="<b>%{y}</b><br>Quantidade: %{x}<extra></extra>",
    ))
    fig.update_layout(
        title="Incidências por Tipo de Erro", height=300,
        margin=dict(l=10, r=30, t=40, b=10),
        showlegend=False, plot_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#EEE", title="Quantidade"),
    )
    return fig


def chart_ajuste_realizado(dff: pd.DataFrame) -> go.Figure:
    col = "ajuste_realizado"
    if col not in dff.columns:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Coluna 'Tipo de Ajuste' não encontrada",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Índice por Tipo de Ajuste", height=300,
                         margin=dict(l=10, r=10, t=40, b=10))
        return fig

    counts = dff[col].dropna().astype(str).str.strip()
    counts = counts[counts.ne("") & counts.ne("nan")].value_counts().reset_index()
    if counts.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem ajustes classificados<br>Preencha a coluna 'Tipo de Ajuste' no Excel",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Índice por Tipo de Ajuste", height=300,
                         margin=dict(l=10, r=10, t=40, b=10))
        return fig
    counts.columns = ["Ajuste", "Qtd"]

    fig = go.Figure(go.Pie(
        labels=counts["Ajuste"], values=counts["Qtd"], hole=0.55,
        textinfo="percent+label", textfont_size=12,
        hovertemplate="<b>%{label}</b><br>Quantidade: %{value}<br>Percentual: %{percent}<extra></extra>",
    ))
    fig.update_layout(
        title="Índice por Tipo de Ajuste", height=300,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, title="Tipo de Ajuste"),
        annotations=[dict(
            text=f"<b>{counts['Qtd'].sum()}</b><br>issues",
            x=0.5, y=0.5, font_size=14, showarrow=False,
        )],
    )
    return fig


def chart_por_area(dff: pd.DataFrame) -> go.Figure:
    col = "area"
    if col not in dff.columns or len(dff) == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem dados de 'Área'<br>Preencha a coluna 'Área' no Excel",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Incidências por Área", height=280,
                         margin=dict(l=10, r=30, t=40, b=10))
        return fig

    counts = dff[col].dropna().value_counts().reset_index()
    if counts.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Nenhuma área classificada<br>Preencha a coluna 'Área' no Excel",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Incidências por Área", height=280,
                         margin=dict(l=10, r=30, t=40, b=10))
        return fig
    
    counts.columns = ["Área", "Qtd"]
    counts = counts.sort_values("Qtd", ascending=True)

    fig = go.Figure(go.Bar(
        x=counts["Qtd"], y=counts["Área"],
        orientation="h", marker_color="#2E75B6",
        text=counts["Qtd"], textposition="outside",
        hovertemplate="<b>%{y}</b><br>Issues: %{x}<extra></extra>",
    ))
    fig.update_layout(
        title="Incidências por Área",
        height=max(280, len(counts) * 45 + 80),
        margin=dict(l=10, r=50, t=40, b=10),
        showlegend=False, plot_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#EEE", title="Quantidade"),
    )
    return fig


def chart_tendencia(dff: pd.DataFrame, granularidade: str) -> go.Figure:
    col = "semana" if granularidade == "Semana" else "mes"
    if col not in dff.columns or len(dff) == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem dados temporais<br>Verifique a coluna 'Data Criação' no Excel",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title=f"Bugs Abertos por {granularidade}", height=300,
                         margin=dict(l=10, r=10, t=40, b=10))
        return fig

    # Conta quantidade de bugs criados em cada período
    counts = dff.groupby(col).size().reset_index(name="Qtd")
    counts = counts.sort_values(col)

    if counts.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem dados no período selecionado",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title=f"Bugs Abertos por {granularidade}", height=300,
                         margin=dict(l=10, r=10, t=40, b=10))
        return fig

    # Formata labels do eixo X
    if granularidade == "Semana":
        counts["label"] = counts[col].dt.strftime("Sem %d/%m")
    else:
        counts["label"] = counts[col].dt.strftime("%b/%Y")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=counts["label"], y=counts["Qtd"],
        marker_color="#E53935",
        text=counts["Qtd"], textposition="outside",
        hovertemplate="<b>%{x}</b><br>Bugs abertos: %{y}<extra></extra>",
    ))

    # Linha de tendência
    if len(counts) >= 2:
        fig.add_trace(go.Scatter(
            x=counts["label"], y=counts["Qtd"],
            mode="lines+markers",
            line=dict(color="#1565C0", width=2, dash="dot"),
            marker=dict(size=6),
            name="Tendência",
            hoverinfo="skip",
        ))

    fig.update_layout(
        title=f"Bugs Abertos por {granularidade}",
        height=300, margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#EEE", title=""),
        yaxis=dict(showgrid=True, gridcolor="#EEE", title="Qtd Bugs",
                   dtick=1),
        showlegend=False,
    )
    return fig


def chart_heatmap(dff: pd.DataFrame) -> go.Figure:
    if "area" not in dff.columns or "tipo_erro_efetivo" not in dff.columns or len(dff) == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Dados insuficientes para heatmap<br>Preencha as colunas 'Área' e 'Tipo de Erro'",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Concentração: Área × Tipo de Erro", height=250,
                         margin=dict(l=10, r=10, t=40, b=10))
        return fig

    # Filtra dados válidos
    df_valid = dff.dropna(subset=["area", "tipo_erro_efetivo"])
    if df_valid.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem área ou tipo de erro classificados<br>Preencha os dados no Excel",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Concentração: Área × Tipo de Erro", height=250,
                         margin=dict(l=10, r=10, t=40, b=10))
        return fig

    pivot = df_valid.groupby(["area", "tipo_erro_efetivo"]).size().unstack(fill_value=0)

    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
        colorscale="Blues", text=pivot.values,
        texttemplate="%{text}", textfont={"size": 12}, hoverongaps=False,
        hovertemplate="<b>%{y}</b> × <b>%{x}</b><br>Issues: %{z}<extra></extra>",
        colorbar=dict(title="Qtd Issues"),
    ))
    fig.update_layout(
        title="Concentração: Área × Tipo de Erro",
        height=max(250, len(pivot.index) * 60 + 80),
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(title="Tipo de Erro"),
        yaxis=dict(title="Área"),
    )
    return fig


def chart_top_ofensores(dff: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Top ofensores: issues com maior Qtd Vínculos (chamados associados)."""
    col_vinculos = "qtd_vinculos"
    if col_vinculos not in dff.columns or len(dff) == 0:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem dados de vínculos<br>Preencha 'Qtd Vínculos' no Excel",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="🔥 Top Ofensores (Qtd Vínculos)", height=280,
                         margin=dict(l=10, r=10, t=40, b=10))
        return fig

    df_valid = dff[["key", col_vinculos]].copy()
    if "resumo" in dff.columns:
        df_valid["resumo"] = dff["resumo"].astype(str).str[:60]
    else:
        df_valid["resumo"] = df_valid["key"]
    if "area" in dff.columns:
        df_valid["area"] = dff["area"].fillna("N/I")
    else:
        df_valid["area"] = "N/I"

    df_valid[col_vinculos] = pd.to_numeric(df_valid[col_vinculos], errors="coerce").fillna(0).astype(int)
    df_valid = df_valid[df_valid[col_vinculos] > 1].sort_values(col_vinculos, ascending=True).tail(top_n)

    if df_valid.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Nenhuma issue com vínculos > 0",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="🔥 Top Ofensores (Qtd Vínculos)", height=280,
                         margin=dict(l=10, r=10, t=40, b=10))
        return fig

    labels = df_valid["key"] + " - " + df_valid["area"]
    hover_text = [
        f"<b>{row['key']}</b><br>{row['resumo']}<br>Área: {row['area']}<br>Vínculos: {row[col_vinculos]}"
        for _, row in df_valid.iterrows()
    ]

    fig = go.Figure(go.Bar(
        x=df_valid[col_vinculos], y=labels,
        orientation="h",
        marker_color="#E53935",
        text=df_valid[col_vinculos], textposition="outside",
        hovertext=hover_text, hoverinfo="text",
    ))
    fig.update_layout(
        title="🔥 Top Ofensores (Qtd Vínculos)",
        height=max(280, len(df_valid) * 40 + 80),
        margin=dict(l=10, r=50, t=40, b=10),
        plot_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#EEE", title="Qtd Vínculos"),
        showlegend=False,
    )
    return fig


def chart_pendencias_por_area(df_acomp: pd.DataFrame) -> go.Figure:
    """Barras horizontais: pendências (sem data_conclusao) agrupadas por Área."""
    if df_acomp.empty or "area" not in df_acomp.columns:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem dados de acompanhamento<br>Adicione ações na aba '🗂️ Acompanhamento Issue'",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(
            title="Pendências por Área (Acompanhamento)", height=280,
            margin=dict(l=10, r=10, t=40, b=10)
        )
        return fig

    # Pendênte = sem data de conclusão ou data NaT/vazia
    if "data_conclusao" in df_acomp.columns:
        pendentes = df_acomp[df_acomp["data_conclusao"].isna()]
    else:
        pendentes = df_acomp[df_acomp["status_acao"].astype(str).str.strip().ne("Concluído")]
    if pendentes.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="✅ Sem pendências abertas<br>Todas as ações foram concluídas!",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#43A047",
            xref="paper", yref="paper"
        )
        fig.update_layout(
            title="Pendências por Área (Acompanhamento)", height=280,
            margin=dict(l=10, r=10, t=40, b=10)
        )
        return fig

    counts = (
        pendentes["area"]
        .astype(str).str.strip()
        .replace("", "Não informado")
        .value_counts()
        .reset_index()
    )
    counts.columns = ["Área", "Pendências"]
    counts = counts.sort_values("Pendências", ascending=True)

    fig = go.Figure(go.Bar(
        x=counts["Pendências"], y=counts["Área"],
        orientation="h",
        marker_color="#EF5350",
        text=counts["Pendências"], textposition="outside",
        hovertemplate="<b>%{y}</b><br>Pendências: %{x}<extra></extra>",
    ))
    fig.update_layout(
        title="Pendências por Área (Acompanhamento)", height=280,
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#EEE", title="Quantidade"),
        yaxis=dict(title="Área"),
        showlegend=False,
    )
    return fig


def chart_solucoes(dff: pd.DataFrame, granularidade: str) -> go.Figure:
    """Stacked bar: Problema Resolvido Sim/Não por período.
    Só mostra issues explicitamente avaliadas (exclui NaN/vazio)."""
    col_data  = "data_criacao"
    col_res   = "problema_resolvido"

    if col_data not in dff.columns or col_res not in dff.columns or dff.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Dados insuficientes<br>Verifique colunas 'Data Criação' e 'Problema Resolvido?'",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(
            title="Acompanhamento por Solução", height=300,
            margin=dict(l=10, r=10, t=40, b=10)
        )
        return fig

    dfr = dff[[col_data, col_res]].copy()
    dfr[col_data] = pd.to_datetime(dfr[col_data], errors="coerce")
    dfr = dfr.dropna(subset=[col_data])

    # Mantém APENAS issues explicitamente avaliadas como Sim ou Não
    dfr["resolvido_label"] = dfr[col_res].astype(str).str.strip()
    dfr = dfr[dfr["resolvido_label"].isin(["Sim", "N\u00e3o"])]
    dfr["resolvido_label"] = dfr["resolvido_label"].map({"Sim": "Resolvido", "N\u00e3o": "N\u00e3o Resolvido"})

    if dfr.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="Nenhuma issue com 'Problema Resolvido?' avaliada ainda",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
        )
        fig.update_layout(
            title="Acompanhamento por Solu\u00e7\u00e3o", height=300,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        return fig

    freq = "W" if granularidade == "Semana" else "M"
    dfr["periodo"] = dfr[col_data].dt.to_period(freq).dt.start_time

    pivot = (
        dfr.groupby(["periodo", "resolvido_label"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    fig = go.Figure()
    colors = {"Resolvido": "#43A047", "N\u00e3o Resolvido": "#EF5350"}
    for label in ["Resolvido", "N\u00e3o Resolvido"]:
        if label in pivot.columns:
            fig.add_trace(go.Bar(
                name=label,
                x=pivot["periodo"],
                y=pivot[label],
                marker_color=colors[label],
                text=pivot[label], textposition="inside",
            ))

    fmt = "%d/%m" if granularidade == "Semana" else "%b/%Y"
    tickvals = pivot["periodo"].tolist()
    ticktext = [d.strftime(fmt) for d in tickvals]

    total_aval = int(dfr["resolvido_label"].eq("Resolvido").sum())
    total_nao  = int(dfr["resolvido_label"].eq("N\u00e3o Resolvido").sum())

    fig.update_layout(
        barmode="stack",
        title=f"Acompanhamento por Solu\u00e7\u00e3o \u2014 {total_aval} resolvidas / {total_nao} n\u00e3o resolvidas",
        height=300,
        margin=dict(l=10, r=10, t=40, b=40),
        plot_bgcolor="white",
        xaxis=dict(tickvals=tickvals, ticktext=ticktext, tickangle=-30,
                   showgrid=False, title=""),
        yaxis=dict(showgrid=True, gridcolor="#EEE", title="Issues avaliadas"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.35),
    )
    return fig


def chart_erros_por_time(dff: pd.DataFrame) -> go.Figure:
    """Barras: quantidade de erros (issues) por Time (coluna H da aba Dados)."""
    col = "time"
    if col not in dff.columns or dff.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem dados de 'Time'<br>Preencha a coluna 'Time' no Excel",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Erros por Time", height=280,
                         margin=dict(l=10, r=30, t=40, b=10))
        return fig

    counts = (
        dff[col].dropna().astype(str).str.strip()
        .replace("", "Não informado")
        .value_counts()
        .reset_index()
    )
    if counts.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Nenhum time classificado<br>Preencha a coluna 'Time' no Excel",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Erros por Time", height=280,
                         margin=dict(l=10, r=30, t=40, b=10))
        return fig
    
    counts.columns = ["Time", "Issues"]
    counts = counts.sort_values("Issues", ascending=True)

    fig = go.Figure(go.Bar(
        x=counts["Issues"], y=counts["Time"],
        orientation="h",
        marker_color="#5C6BC0",
        text=counts["Issues"], textposition="outside",
        hovertemplate="<b>%{y}</b><br>Issues: %{x}<extra></extra>",
    ))
    fig.update_layout(
        title="Erros por Time",
        height=max(280, len(counts) * 45 + 80),
        margin=dict(l=10, r=50, t=40, b=10),
        plot_bgcolor="white",
        xaxis=dict(showgrid=True, gridcolor="#EEE", title="Quantidade"),
        showlegend=False,
    )
    return fig


def chart_acompanhamento_status(df_acomp: pd.DataFrame) -> go.Figure:
    if "status_acao" not in df_acomp.columns or df_acomp.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem dados de acompanhamento<br>Adicione issues na aba '🗂️ Acompanhamento Issue'",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Status do Acompanhamento", height=280,
                         margin=dict(l=10, r=10, t=40, b=10))
        return fig

    status_order  = ["Análise", "Andamento", "Bloqueado", "Concluído"]
    colors_status = {
        "Concluído":  "#43A047",
        "Andamento":  "#FB8C00",
        "Análise":    "#42A5F5",
        "Bloqueado":  "#E53935",
    }

    counts = df_acomp["status_acao"].value_counts().reset_index()
    if counts.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="📊 Sem status de ação definido",
            x=0.5, y=0.5, showarrow=False, font_size=13, font_color="#888",
            xref="paper", yref="paper"
        )
        fig.update_layout(title="Status do Acompanhamento", height=280,
                         margin=dict(l=10, r=10, t=40, b=10))
        return fig
    
    counts.columns = ["Status", "Qtd"]
    counts["Status"] = pd.Categorical(counts["Status"], categories=status_order, ordered=True)
    counts = counts.sort_values("Status")

    colors = [colors_status.get(str(s), "#BDBDBD") for s in counts["Status"]]
    fig = go.Figure(go.Bar(
        x=counts["Status"], y=counts["Qtd"],
        marker_color=colors, text=counts["Qtd"], textposition="outside",
        hovertemplate="<b>%{x}</b><br>Ações: %{y}<extra></extra>",
    ))
    fig.update_layout(
        title="Status do Acompanhamento", height=280,
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="white",
        xaxis=dict(title="Status da Ação"),
        yaxis=dict(showgrid=True, gridcolor="#EEE", title="Quantidade"),
        showlegend=False,
    )
    return fig


# =============================================================================
# COBERTURA DE TAs
# =============================================================================

def chart_cobertura_ta(dff: pd.DataFrame):
    """Gráfico de cobertura de Testes Automatizados (Sim / Não / Sem avaliação)."""
    if "possui_ta" not in dff.columns or len(dff) == 0:
        fig = go.Figure()
        fig.update_layout(title="🧪 Cobertura de TAs", height=320,
                          annotations=[dict(text="Sem dados de TA", showarrow=False,
                                            font=dict(size=16, color="#999"))])
        return fig

    ta_col = dff["possui_ta"].astype(str).str.strip().str.lower()
    n_sim = int((ta_col == "sim").sum())
    n_nao = int((ta_col == "não").sum())
    n_sem = len(dff) - n_sim - n_nao

    labels = []
    values = []
    colors = []
    if n_sim > 0:
        labels.append("Com TA")
        values.append(n_sim)
        colors.append("#43A047")
    if n_nao > 0:
        labels.append("Sem TA")
        values.append(n_nao)
        colors.append("#E53935")
    if n_sem > 0:
        labels.append("Sem avaliação")
        values.append(n_sem)
        colors.append("#BDBDBD")

    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker_colors=colors,
        hole=0.45,
        textinfo="label+value+percent",
        textposition="outside",
        hovertemplate="<b>%{label}</b><br>Issues: %{value}<br>%{percent}<extra></extra>",
    ))
    total = len(dff)
    pct_coberto = round(n_sim / total * 100, 1) if total > 0 else 0
    fig.update_layout(
        title="🧪 Cobertura de TAs",
        height=320,
        margin=dict(l=10, r=10, t=40, b=10),
        showlegend=False,
        annotations=[dict(text=f"{pct_coberto}%", x=0.5, y=0.5,
                          font_size=22, font_color="#2E75B6", showarrow=False)],
    )
    return fig


# =============================================================================
# TABELA DETALHADA
# =============================================================================

def render_detail_table(dff: pd.DataFrame):
    st.markdown("### 📋 Issues Detalhadas")

    if len(dff) == 0:
        st.info("Nenhuma issue encontrada com os filtros selecionados.")
        return

    cols_show = ["key", "resumo", "area", "status", "prioridade", "tipo_erro_efetivo",
                 "acao_realizada", "ajuste_realizado", "possui_ta", "analisado",
                 "qa_principal", "dev_principal", "data_criacao", "tempo_resolucao_dias"]
    cols_show = [c for c in cols_show if c in dff.columns]

    df_show = dff[cols_show].copy()
    rename_map = {
        "key":                 "Key",
        "resumo":              "Resumo",
        "area":                "Área",
        "status":              "Status",
        "prioridade":          "Prioridade",
        "tipo_erro_efetivo":   "Tipo de Erro",
        "acao_realizada":      "Ação Realizada",
        "ajuste_realizado":    "Ajuste Realizado",
        "possui_ta":           "Possui TA",
        "analisado":           "Analisado",
        "qa_principal":        "QA Principal",
        "dev_principal":       "Dev Principal",
        "data_criacao":        "Criação",
        "tempo_resolucao_dias":"Dias p/ Resolver",
    }
    df_show = df_show.rename(columns=rename_map)

    if "Criação" in df_show.columns:
        df_show["Criação"] = df_show["Criação"].dt.strftime("%d/%m/%Y")

    st.dataframe(
        df_show,
        width="stretch",
        height=min(400, (len(df_show) + 1) * 35 + 38),
        column_config={
            "Key":              st.column_config.TextColumn("Key", width="small"),
            "Resumo":           st.column_config.TextColumn("Resumo", width="large"),
            "Ação Realizada":   st.column_config.TextColumn("Ação Realizada", width="large"),
            "Prioridade":       st.column_config.TextColumn("Prioridade", width="small"),
            "Status":           st.column_config.TextColumn("Status", width="small"),
            "Tipo de Erro":     st.column_config.TextColumn("Tipo de Erro", width="medium"),
            "Analisado":        st.column_config.TextColumn("Analisado", width="small"),
            "Dias p/ Resolver": st.column_config.NumberColumn("Dias p/ Resolver", width="small"),
        },
        hide_index=True,
    )

    csv = dff[cols_show].rename(columns=rename_map).to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Exportar CSV",
        data=csv,
        file_name=f"rca_pocket_export_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )



# =============================================================================
# MAIN
# =============================================================================

def main():
    config = load_config()
    df = load_issues(config)
    df_acomp = load_acompanhamento(config)

    filters = build_sidebar(df)
    dff = apply_filters(df, filters)

    # Filtrar aba Acompanhamento pelas issues filtradas (coluna "Issue Original")
    if "issue_original" in df_acomp.columns and len(dff) > 0:
        filtered_keys = set(dff["key"].tolist())
        df_acomp_filtered = df_acomp[df_acomp["issue_original"].isin(filtered_keys)]
    else:
        df_acomp_filtered = df_acomp

    # Header
    st.title("🎯 RCA Pocket — Dashboard de Incidências")
    st.markdown("---")

    # KPIs
    render_kpis(dff, df_acomp_filtered)

    st.markdown("---")

    # Linha 1: Tipo de Erro + Ajuste Realizado
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(chart_tipo_erro(dff), use_container_width=True, key="chart_tipo_erro", config=PLOTLY_CONFIG)
    with col2:
        st.plotly_chart(chart_ajuste_realizado(dff), use_container_width=True, key="chart_ajuste", config=PLOTLY_CONFIG)

    # Linha 2: Por Área | Erros por Time
    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(chart_por_area(dff), use_container_width=True, key="chart_por_area", config=PLOTLY_CONFIG)
    with col4:
        st.plotly_chart(chart_erros_por_time(dff), use_container_width=True, key="chart_erros_time", config=PLOTLY_CONFIG)

    # Linha 3: Pendências por Área | Top Ofensores (Vínculos)
    col5a, col5b = st.columns(2)
    with col5a:
        st.plotly_chart(chart_pendencias_por_area(df_acomp_filtered), use_container_width=True, key="chart_pendencias_area", config=PLOTLY_CONFIG)
    with col5b:
        st.plotly_chart(chart_top_ofensores(dff), use_container_width=True, key="chart_top_ofensores", config=PLOTLY_CONFIG)

    # Linha 4: Tendência Temporal + Acompanhamento por Solução
    col_tend, col_sol = st.columns(2)
    with col_tend:
        st.plotly_chart(chart_tendencia(dff, filters["granularidade"]), use_container_width=True, key="chart_tendencia", config=PLOTLY_CONFIG)
    with col_sol:
        st.plotly_chart(chart_solucoes(dff, filters["granularidade"]), use_container_width=True, key="chart_solucoes", config=PLOTLY_CONFIG)

    # Linha 5: Heatmap + Status do Acompanhamento
    col5, col6 = st.columns(2)
    with col5:
        st.plotly_chart(chart_heatmap(dff), use_container_width=True, key="chart_heatmap", config=PLOTLY_CONFIG)
    with col6:
        st.plotly_chart(chart_acompanhamento_status(df_acomp_filtered), use_container_width=True, key="chart_acomp_status", config=PLOTLY_CONFIG)

    # Linha 6: Cobertura de TAs
    col_ta1, col_ta2 = st.columns(2)
    with col_ta1:
        st.plotly_chart(chart_cobertura_ta(dff), use_container_width=True, key="chart_cobertura_ta", config=PLOTLY_CONFIG)

    st.markdown("---")

    # Tabela detalhada
    render_detail_table(dff)

    # Seção de Compartilhamento
    st.markdown("---")
    st.markdown("### 📤 Compartilhamento")
    
    col_share1, col_share2, col_share3 = st.columns([1, 1, 2])
    
    with col_share1:
        # Botão para baixar Excel
        excel_path = Path(config["excel"]["arquivo_saida"])
        if excel_path.exists():
            with open(excel_path, "rb") as f:
                excel_data = f.read()
            st.download_button(
                "📥 Baixar Excel Completo",
                data=excel_data,
                file_name="RCA_Pocket.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Baixe o arquivo Excel com todas as abas e dados"
            )
        else:
            st.info("📊 Excel não encontrado")
    
    with col_share2:
        # Botão para exportar dados filtrados
        if len(dff) > 0:
            # Cria Excel filtrado apenas com dados visíveis
            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                dff.to_excel(writer, sheet_name='Dados Filtrados', index=False)
                if not df_acomp_filtered.empty:
                    df_acomp_filtered.to_excel(writer, sheet_name='Acompanhamento', index=False)
            output.seek(0)
            
            st.download_button(
                "📊 Baixar Dados Filtrados",
                data=output.getvalue(),
                file_name=f"RCA_Filtrado_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Baixe apenas os dados filtrados em Excel"
            )
    
    with col_share3:
        # Instruções de compartilhamento
        with st.expander("ℹ️ Como compartilhar o dashboard?", expanded=False):
            st.markdown("""
            **Opções para compartilhar:**
            
            **1. Localmente (mesma rede):**
            - Execute: `streamlit run dashboard.py --server.address 0.0.0.0`
            - Compartilhe o IP da sua máquina + porta (ex: http://192.168.1.10:8501)
            
            **2. Streamlit Cloud (gratuito):**
            - Suba o projeto para GitHub
            - Acesse [share.streamlit.io](https://share.streamlit.io)
            - Conecte o repositório e faça deploy
            - Compartilhe o link público gerado
            
            **3. Enviar arquivos:**
            - Use os botões ao lado para baixar Excel/CSV
            - Compartilhe por e-mail ou drive
            
            **4. Capturas de tela:**
            - Use a ferramenta de captura do Windows (Win + Shift + S)
            - Ou tire prints dos gráficos específicos
            """)

    # Rodapé
    st.markdown("---")
    sync_file = Path(config["cache"]["arquivo_ultima_sync"])
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        st.caption(f"🗂️ Total no período: **{len(dff)}** issues filtradas de **{len(df)}** totais")
    with col_f2:
        st.caption("📊 RCA Pocket — Protótipo v1.0")
    with col_f3:
        st.caption(f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    with col_f4:
        excel_path = Path(config["excel"]["arquivo_saida"])
        if excel_path.exists():
            mtime = datetime.fromtimestamp(excel_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            st.caption(f"📊 Fonte: RCA_Pocket.xlsx ({mtime})")
        elif sync_file.exists():
            st.caption(f"🔄 Fonte: cache Jira ({sync_file.read_text().strip()})")
        else:
            st.caption("📌 Modo Protótipo (dados mock)")


if __name__ == "__main__":
    main()
