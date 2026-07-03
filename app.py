# =============================================================================
# app.py — Dashboard Gerencial de Pagamentos | MAZ | Museu das Amazônias
# Instituto de Desenvolvimento e Gestão (IDG)
#
# Stack:   Python 3.11+ | Streamlit | Plotly | Pandas
# Deploy:  Streamlit Community Cloud (gratuito)
# Versão:  Beta 1.0
#
# Arquitetura de módulos:
#   app.py          → Interface completa (UI/UX, layout, gráficos)
#   data_handler.py → Toda a lógica de dados (separado para manutenção fácil)
# =============================================================================

import html
import json
import os
import re
import time
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import data_handler as dh

# --------------------------------------------------------------------------- #
# CONFIG PERSISTENTE — salva URL e aba em arquivo local por 5 dias             #
# O arquivo sobrevive a F5 e fechamento do navegador. É apagado após 5 dias    #
# ou quando o admin salva novas configurações.                                  #
# --------------------------------------------------------------------------- #
_CONFIG_FILE = os.path.join(os.path.dirname(__file__), ".dashboard_config.json")
_CONFIG_TTL  = timedelta(days=5)


def _ler_config_persistente() -> dict:
    """Lê configuração salva em disco. Retorna {} se expirada ou inexistente."""
    try:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        salvo_em = datetime.fromisoformat(cfg.get("salvo_em", "2000-01-01"))
        if datetime.now() - salvo_em > _CONFIG_TTL:
            return {}
        return cfg
    except Exception:
        return {}


def _salvar_config_persistente(url: str, aba: str) -> None:
    """Salva URL e aba em disco com timestamp."""
    cfg = {"sheets_url": url, "sheets_aba": aba, "salvo_em": datetime.now().isoformat()}
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# PREFERÊNCIA DE TEMA (claro/escuro) — lembrada por login, salva em disco.     #
# É só uma preferência cosmética: se o arquivo se perder num reboot, o pior   #
# cenário é a pessoa ver o tema claro de novo e clicar no alternador — sem    #
# risco de dado real, por isso não precisa do rigor da planilha (Sheets).     #
# --------------------------------------------------------------------------- #
_TEMA_FILE = os.path.join(os.path.dirname(__file__), ".dashboard_tema.json")


def _carregar_tema_salvo(login: str) -> str:
    try:
        with open(_TEMA_FILE, "r", encoding="utf-8") as f:
            prefs = json.load(f)
        return prefs.get(login, "claro")
    except Exception:
        return "claro"


def _salvar_tema(login: str, tema: str) -> None:
    try:
        with open(_TEMA_FILE, "r", encoding="utf-8") as f:
            prefs = json.load(f)
    except Exception:
        prefs = {}
    prefs[login] = tema
    try:
        with open(_TEMA_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# CONFIGURAÇÃO DA PÁGINA — deve ser a primeira chamada Streamlit               #
# --------------------------------------------------------------------------- #
_favicon_path = os.path.join(os.path.dirname(__file__), "assets", "logo_vertical.png")
st.set_page_config(
    page_title="MAZ | Dashboard de Pagamentos",
    page_icon=_favicon_path if os.path.exists(_favicon_path) else "🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------- #
# TEMA — claro ("papel de galeria") e escuro ("noite sobre a floresta")        #
# Mesma identidade e as mesmas 4 cores da marca nos dois; no escuro, os        #
# acentos são levemente aclarados para manter contraste sobre fundo escuro.   #
# --------------------------------------------------------------------------- #
TEMA_CLARO = {
    "paper": "#ECE7DC", "paper_deep": "#E4DECF", "surface": "#FFFFFF",
    "ink": "#26261C", "ink_soft": "#7C7563", "line": "#EAE3D4",
    "folha": "#4F6A1E", "urucum": "#E02838", "sol": "#E8920A", "rio": "#3E9489",
    "sol_texto": "#B97200", "rio_texto": "#2C6E64",
    "shadow_soft": "#2624190F", "upload_border": "#4F6A1E55",
    "card_shadow": "0 1px 2px #26261C0A, 0 6px 20px #26261C0F",
    "bar_scale": ["#C9D6B0", "#7FA34A", "#4F6A1E"],
}
TEMA_ESCURO = {
    "paper": "#0F1613", "paper_deep": "#151F1A", "surface": "#1B2822",
    "ink": "#EDEAE0", "ink_soft": "#9BAAA0", "line": "#2C3B34",
    "folha": "#7FB251", "urucum": "#F16B74", "sol": "#F2AC4E", "rio": "#5FC4B6",
    "sol_texto": "#F2AC4E", "rio_texto": "#5FC4B6",
    "shadow_soft": "#FFFFFF14", "upload_border": "#7FB25166",
    "card_shadow": "0 1px 2px #00000030, 0 8px 24px #00000040",
    "bar_scale": ["#26362B", "#4F7A3E", "#7FB251"],
}

# Recarrega a preferência sempre que o login "mudar" (inclui o momento em que
# deixa de ser None logo após autenticar) — não só na primeira execução —
# senão a preferência salva nunca seria lida (o login ainda não existe na
# primeira vez que este bloco roda, antes da tela de login).
_TEMA_SENTINELA = "__nunca_carregado__"
_login_para_tema = st.session_state.get("login_usuario")
if st.session_state.get("_tema_carregado_para", _TEMA_SENTINELA) != _login_para_tema:
    st.session_state["tema"] = _carregar_tema_salvo(_login_para_tema) if _login_para_tema else "claro"
    st.session_state["_tema_carregado_para"] = _login_para_tema
    # Se a mesma aba trocar de usuário sem fechar o navegador, o alternador
    # (widget) não pode continuar preso na posição da pessoa anterior.
    st.session_state.pop("toggle_tema", None)

TEMA_ATUAL = st.session_state["tema"]
C = TEMA_ESCURO if TEMA_ATUAL == "escuro" else TEMA_CLARO


# --------------------------------------------------------------------------- #
# CSS GLOBAL — Identidade "Trançado das Amazônias"                              #
# Paleta da marca MAZ sobre papel de galeria (ou noite, no modo escuro)        #
# --------------------------------------------------------------------------- #
st.markdown(f"""
<style>
:root {{
    --paper:          {C['paper']};
    --paper-deep:     {C['paper_deep']};
    --surface:        {C['surface']};
    --ink:            {C['ink']};
    --ink-soft:       {C['ink_soft']};
    --line:           {C['line']};
    --folha:          {C['folha']};
    --urucum:         {C['urucum']};
    --sol:            {C['sol']};
    --rio:            {C['rio']};
    --sol-texto:      {C['sol_texto']};
    --rio-texto:      {C['rio_texto']};
    --shadow-soft:    {C['shadow_soft']};
    --upload-border:  {C['upload_border']};
    --card-shadow:    {C['card_shadow']};
}}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* --- Fonte global --- */
html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* Faces geométricas (ecoam o wordmark da marca, "A" triangulares) */
.maz-display {
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* --- Faixa trançada: motivo direto da logo (4 fios cruzando) --- */
.maz-trancado {
    height: 8px;
    background: repeating-linear-gradient(45deg,
        #4F6A1E 0 14px, #E02838 14px 28px,
        #E8920A 28px 42px, #3E9489 42px 56px);
    background-size: 56px 56px;
    border-radius: 999px;
    opacity: 0.9;
    margin-bottom: 18px;
}

/* --- Cards de KPI (estilo SaaS: arredondado, sombra, chip + pílula) --- */
.kpi-card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 18px;
    box-shadow: var(--card-shadow);
    transition: box-shadow 0.2s, transform 0.2s;
    height: 100%;
}
.kpi-card:hover { transform: translateY(-2px); box-shadow: 0 2px 6px #26261C0F, 0 16px 32px #26261C1A; }
.kpi-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.kpi-chip {
    width: 42px; height: 42px; border-radius: 13px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.15rem; line-height: 1;
}
.kpi-chip.folha  { background: color-mix(in srgb, var(--folha) 14%, transparent); color: var(--folha); }
.kpi-chip.rio    { background: color-mix(in srgb, var(--rio) 14%, transparent); color: var(--rio); }
.kpi-chip.sol    { background: color-mix(in srgb, var(--sol) 18%, transparent); color: var(--sol-texto); }
.kpi-chip.urucum { background: color-mix(in srgb, var(--urucum) 14%, transparent); color: var(--urucum); }
.kpi-pill {
    font-size: 0.66rem; font-weight: 700; padding: 3px 9px; border-radius: 999px;
    letter-spacing: 0.02em; white-space: nowrap;
}
.kpi-pill.folha  { background: color-mix(in srgb, var(--folha) 14%, transparent); color: var(--folha); }
.kpi-pill.rio    { background: color-mix(in srgb, var(--rio) 16%, transparent); color: var(--rio-texto); }
.kpi-pill.sol    { background: color-mix(in srgb, var(--sol) 18%, transparent); color: var(--sol-texto); }
.kpi-pill.urucum { background: color-mix(in srgb, var(--urucum) 14%, transparent); color: var(--urucum); }
.kpi-value {
    font-size: 1.65rem;
    font-weight: 700;
    color: var(--ink);
    line-height: 1.05;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
}
.kpi-label {
    font-size: 0.8rem;
    color: var(--ink-soft);
    margin-top: 3px;
}

/* --- Cabeçalho principal --- */
.header-container {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 4px 0 18px 0;
    border-bottom: 1px solid var(--line);
    margin-bottom: 24px;
}
.header-divider { width: 1px; height: 46px; background: var(--line); }
.header-eyebrow {
    display: block;
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--ink-soft);
    text-transform: uppercase;
    letter-spacing: 0.2em;
    margin-bottom: 3px;
}
.header-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--ink);
    margin: 0;
    letter-spacing: 0.01em;
}
.header-topbar {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-left: auto;
}
.header-search {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--paper-deep);
    border: 1px solid var(--line);
    border-radius: 999px;
    padding: 8px 16px;
    color: var(--ink-soft);
    font-size: 0.82rem;
    min-width: 220px;
}
.header-bell {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 38px; height: 38px;
    border-radius: 50%;
    background: var(--paper-deep);
    border: 1px solid var(--line);
    color: var(--ink-soft);
    flex-shrink: 0;
}
.header-bell-badge {
    position: absolute;
    top: -3px; right: -3px;
    min-width: 16px; height: 16px;
    border-radius: 999px;
    background: var(--urucum);
    color: #fff;
    font-size: 0.6rem;
    font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    padding: 0 3px;
    border: 2px solid var(--paper);
}
.header-avatar-wrap {
    display: flex;
    align-items: center;
    gap: 10px;
    padding-left: 12px;
    border-left: 1px solid var(--line);
}
.header-avatar {
    width: 38px; height: 38px;
    border-radius: 50%;
    background: var(--folha);
    color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85rem;
    font-weight: 700;
    flex-shrink: 0;
}
.header-avatar-name { font-size: 0.82rem; font-weight: 700; color: var(--ink); line-height: 1.2; }
.header-avatar-role { font-size: 0.7rem; color: var(--ink-soft); line-height: 1.2; }

/* --- Seções --- */
.section-title {
    font-size: 0.82rem;
    font-weight: 700;
    color: var(--ink);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin: 52px 0 18px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--line);
}

/* --- Barra de progresso customizada --- */
.progress-bar-container {
    background: var(--paper-deep);
    border-radius: 999px;
    height: 8px;
    margin: 8px 0 16px 0;
    overflow: hidden;
}
.progress-bar-fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--folha), var(--rio));
    transition: width 0.6s ease;
}

/* --- Tabela de dados --- */
div[data-testid="stDataFrame"] {
    border: 1px solid var(--line);
    border-radius: 6px;
    overflow: hidden;
}

/* --- Sidebar: painel flutuante arredondado (estilo do mockup) --- */
[data-testid="stAppViewContainer"] {
    background: var(--paper);
}
[data-testid="stSidebar"] {
    background: var(--paper-deep);
    border: 1px solid var(--line);
    border-radius: 20px;
    margin: 16px 0 16px 16px;
    height: calc(100vh - 32px);
    box-shadow: var(--card-shadow);
    overflow-y: auto;
    overflow-x: hidden;
}

/* --- Upload box --- */
[data-testid="stFileUploader"] {
    border: 1px dashed var(--upload-border);
    border-radius: 6px;
    padding: 8px;
}

/* Remove padding excessivo do container principal */
.block-container { padding-top: 1.5rem; }

/* --------------------------------------------------------------------- */
/* MOTION — reservado à tela de login (momento de marca, sem distrair)   */
/* --------------------------------------------------------------------- */

/* Barra trançada fluindo — como um tear/rio em movimento contínuo */
@keyframes maz-flow {
    from { background-position: 0 0; }
    to   { background-position: 56px 0; }
}
.maz-trancado.maz-flow { animation: maz-flow 3.2s linear infinite; }

/* Cobra lateral, minimalista: fixa na borda direita, cabeça no topo,
   corpo em ladrilho repetido até o fim da tela — sem deslocamento. */
.maz-cobra-lateral {
    position: fixed;
    top: 0;
    right: 22px;
    width: 26px;
    height: 100vh;
    z-index: 0;
    pointer-events: none;
}
.maz-cobra-lateral .cabeca {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: auto;
    display: block;
}
.maz-cobra-lateral .corpo {
    /* 41px = altura real da cabeça (proporção 64:101) na largura de 26px da fita */
    position: absolute;
    left: 0;
    right: 0;
    top: 41px;
    bottom: 0;
    background-repeat: repeat-y;
    background-size: 100% auto;
}

/* Acessibilidade: quem prefere menos movimento não vê a barra fluir */
@media (prefers-reduced-motion: reduce) {
    .maz-trancado.maz-flow { animation: none; }
}

/* Em telas estreitas a fita lateral compete com o formulário — oculta */
@media (max-width: 680px) {
    .maz-cobra-lateral { display: none; }
}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# OVERRIDE DO "CHROME" DO STREAMLIT — faz o FUNDO do app, a sidebar e os       #
# textos/inputs nativos seguirem o tema. Sem isto, só os elementos que nós    #
# desenhamos (cards) mudam de cor; o fundo e os widgets do próprio Streamlit  #
# ficariam presos no tema claro do config.toml.                               #
#                                                                             #
# Usa as variáveis de tema já definidas em :root, então serve aos dois modos.#
# `!important` em background é seguro (não definimos fundo inline no app).    #
# Em `color`, o !important no CONTÊINER não sobrepõe cores inline dos filhos  #
# (spans coloridos dos cards seguem com sua cor própria) — só define o texto #
# padrão dos widgets, que era o que ficava ilegível no escuro.               #
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
/* Fundo geral do app + barra de topo */
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main,
.stApp {
    background-color: var(--paper) !important;
}
[data-testid="stHeader"] {
    background-color: var(--paper) !important;
}

/* Sidebar: fundo */
[data-testid="stSidebar"] {
    background-color: var(--paper-deep) !important;
}

/* Texto padrão dos widgets e do corpo (labels, markdown, radio, expander) —
   no NÍVEL do parágrafo/label, para não sobrepor spans com cor própria
   (ex: o selo vermelho de pendentes, que tem texto branco inline). */
[data-testid="stAppViewContainer"] .stMarkdown p,
[data-testid="stAppViewContainer"] .stMarkdown li,
[data-testid="stAppViewContainer"] .stMarkdown h1,
[data-testid="stAppViewContainer"] .stMarkdown h2,
[data-testid="stAppViewContainer"] .stMarkdown h3,
[data-testid="stAppViewContainer"] label p,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown li,
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3,
[data-testid="stSidebar"] label p,
[data-testid="stWidgetLabel"] p,
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p,
div[role="radiogroup"] label p {
    color: var(--ink) !important;
}

/* Legendas discretas (st.caption) em tom suave, legível nos dois temas */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: var(--ink-soft) !important;
}

/* Campos de entrada seguem o tema (fundo + texto) */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input,
[data-testid="stTextArea"] textarea,
div[data-baseweb="select"] > div {
    background-color: var(--surface) !important;
    color: var(--ink) !important;
}
input::placeholder, textarea::placeholder { color: var(--ink-soft) !important; opacity: 0.7; }

/* Expander e caixas de destaque seguem o tema */
[data-testid="stExpander"] {
    background-color: var(--surface) !important;
    border: 1px solid var(--line) !important;
    border-radius: 6px;
}

/* Painéis de gráfico no estilo SaaS: st.container(border=True, key="panel_...")
   gera a classe "st-key-<key>" (recurso documentado do Streamlit) — usamos
   prefixo comum "panel_" para estilizar todos de uma vez. */
div[class*="st-key-panel_"] {
    background-color: var(--surface) !important;
    border: 1px solid var(--line) !important;
    border-radius: 18px !important;
    padding: 18px 20px !important;
    box-shadow: var(--card-shadow);
}
</style>
""", unsafe_allow_html=True)


# No modo escuro, a faixa trançada E os sublinhados dos títulos de seção
# adotam o padrão vermelho/verde da cobra do login (vermelho dominante =
# corpo; verde = escamas), no lugar do trançado de 4 cores / do sublinhado
# verde-laranja. Injetado só no escuro; no claro mantém o original.
# O !important no .section-title é necessário para vencer o estilo inline
# (imagem cobra_divisor) aplicado por secao_titulo().
if TEMA_ATUAL == "escuro":
    st.markdown("""
    <style>
    .maz-trancado {
        background: repeating-linear-gradient(45deg,
            #E02838 0 18px, #4F6A1E 18px 28px) !important;
        background-size: 28px 28px !important;
    }
    .section-title {
        border-bottom: none !important;
        background-image: repeating-linear-gradient(45deg,
            #E02838 0 8px, #4F6A1E 8px 14px) !important;
        background-size: 14px 6px !important;
        background-position: left bottom !important;
        background-repeat: repeat-x !important;
    }
    </style>
    """, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# HELPERS DE FORMATAÇÃO                                                         #
# --------------------------------------------------------------------------- #

def fmt_brl(valor: float) -> str:
    """Formata número para moeda brasileira: R$ 1.234.567,89"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_brl_curto(valor: float) -> str:
    """Versão compacta para os KPIs: R$ 15,1 mi · R$ 320 mil · R$ 850,00.
    O valor exato completo continua disponível no tooltip do card."""
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        return "R$ 0"
    n = abs(v)
    if n >= 1_000_000:
        txt = f"R$ {v/1_000_000:.1f} mi"
    elif n >= 1_000:
        txt = f"R$ {v/1_000:.0f} mil"
    else:
        return fmt_brl(v)
    return txt.replace(".", ",")


def tem_colunas(df: pd.DataFrame, *colunas) -> bool:
    """Verifica se TODAS as colunas listadas existem no dataframe."""
    return all(c in df.columns for c in colunas)


# --------------------------------------------------------------------------- #
# ÍCONES DE LINHA — usados onde nós controlamos o HTML (chips de KPI,         #
# títulos de seção, badges/selos). Widgets NATIVOS do Streamlit (st.button,   #
# st.expander, st.multiselect...) só aceitam texto simples no rótulo — não    #
# renderizam SVG — então esses continuam com emoji, por limitação da          #
# ferramenta, não por escolha.                                                #
# --------------------------------------------------------------------------- #

_ICON_PATHS = {
    "list":         '<path d="M3 7h18M3 12h18M3 17h18"/>',
    "bar_chart":    '<path d="M4 20V10M12 20V4M20 20v-7"/>',
    "check_circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5 5-5"/>',
    "dollar":       '<path d="M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "clock":        '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    "alert_tri":    '<path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    "alert_octagon":'<path d="M7.86 2h8.28L22 7.86v8.28L16.14 22H7.86L2 16.14V7.86z"/><path d="M12 8v5M12 16h.01"/>',
    "trend_up":     '<path d="M7 17 17 7M9 7h8v8"/>',
    "grid":         '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "calendar":     '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/>',
    "file_text":    '<path d="M6 3h9l5 5v13H6z"/><path d="M15 3v5h5M9 13h6M9 17h6"/>',
    "plus":         '<path d="M12 5v14M5 12h14"/>',
    "user":         '<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.5-7 8-7s8 3 8 7"/>',
    "bell":         '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    "refresh":      '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>',
    "dash":         '<path d="M5 12h14"/>',
    "link":         '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "search":       '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
}


@st.cache_data
def _svg_icon_data_uri(nome: str, tamanho: int, cor: str, peso: float) -> str:
    """Monta o SVG e cacheia como data URI base64 (a combinação nome+cor+tamanho é a chave)."""
    import base64
    inner = _ICON_PATHS.get(nome, _ICON_PATHS["dash"])
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tamanho}" height="{tamanho}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{cor}" stroke-width="{peso}" '
        f'stroke-linecap="round" stroke-linejoin="round">{inner}</svg>'
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def svg_icon(nome: str, tamanho: int = 16, cor: str = "#6B6552", peso: float = 1.9) -> str:
    """
    Ícone de linha (estilo do mockup aprovado), como <img> de SVG em data URI.
    Precisa de `cor` explícita (hex) — não usa 'currentColor': o card_html do
    dashboard é renderizado via st.html(), que remove tags <svg> inline por
    sanitização, mas preserva <img src="data:image/svg+xml;...">. Testado e
    confirmado localmente antes desta escolha.
    """
    uri = _svg_icon_data_uri(nome, tamanho, cor, peso)
    return (
        f'<img src="{uri}" width="{tamanho}" height="{tamanho}" alt="" '
        f'style="display:inline-block;vertical-align:middle;flex-shrink:0;">'
    )


# Ícone de linha correspondente a cada grupo de status / faixa de prazo
_ICON_POR_GRUPO = {
    "concluido":    "check_circle",
    "em_andamento": "refresh",
    "alerta":       "alert_tri",
    "critico":      "alert_octagon",
}
_ICON_POR_PRAZO = {
    dh.PRAZO_VENCIDO:   "alert_octagon",
    dh.PRAZO_URGENTE:   "alert_tri",
    dh.PRAZO_ATENCAO:   "bell",
    dh.PRAZO_TRANQUILO: "check_circle",
    dh.PRAZO_SEM_DATA:  "dash",
}


def _val_num(v) -> float:
    """
    Converte para float, aceitando tanto números 'de verdade' (vindos do
    dataframe principal, já tratados) quanto texto no formato brasileiro
    (ex: "46900,00", vindo de leituras cruas de outras abas, como Aprovações).
    """
    try:
        if pd.isna(v):
            return 0.0
    except (TypeError, ValueError):
        pass
    if isinstance(v, str):
        s = v.strip().replace("R$", "").strip()
        if not s:
            return 0.0
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0
    try:
        return float(v)
    except Exception:
        return 0.0


def _fmt(v, tipo="texto"):
    """
    Formata valor para exibição em cards/tabelas.
    Sempre escapa caracteres HTML especiais (<, >, &, ", ')
    para evitar que conteúdo da planilha quebre o template HTML do card.
    """
    if pd.isna(v) or str(v).strip() in ("", "nan", "None"):
        return "—"
    if tipo == "valor":
        return fmt_brl(_val_num(v))
    if tipo == "data":
        try:
            return pd.to_datetime(v, dayfirst=True).strftime("%d/%m/%Y")
        except Exception:
            return html.escape(str(v))
    return html.escape(str(v))


def _val_txt(v) -> str:
    """Texto limpo para preencher inputs (NaN/None → ''; float inteiro sem '.0')."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def _val_date(v):
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return pd.to_datetime(v, dayfirst=True).date() if pd.notna(v) else None
    except Exception:
        return None


@st.cache_data
def _logo_data_uri(nome_arquivo: str) -> str:
    """Carrega uma logo da pasta assets/ como data URI (cacheado). Retorna '' se ausente."""
    import base64
    caminho = os.path.join(os.path.dirname(__file__), "assets", nome_arquivo)
    try:
        with open(caminho, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


@st.cache_data
def _video_data_uri(nome_arquivo: str) -> str:
    """Carrega um vídeo da pasta assets/ como data URI (cacheado). Retorna '' se ausente."""
    import base64
    caminho = os.path.join(os.path.dirname(__file__), "assets", nome_arquivo)
    try:
        with open(caminho, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return f"data:video/mp4;base64,{b64}"
    except Exception:
        return ""


def cobra_lateral() -> None:
    """Renderiza a cobra decorativa fixa na lateral direita (cabeça no topo,
    corpo em ladrilho repetido) — usada apenas na tela de login."""
    cabeca = _logo_data_uri("cobra_lateral_head.png")
    tile   = _logo_data_uri("cobra_lateral_tile.png")
    if not cabeca or not tile:
        return
    st.markdown(
        f"""
        <div class="maz-cobra-lateral">
            <img class="cabeca" src="{cabeca}" alt="">
            <div class="corpo" style="background-image:url({tile});"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def estado_vazio(mensagem: str) -> None:
    """Renderiza um estado vazio ilustrado com a cobra da marca."""
    cobra = _logo_data_uri("cobra_vazio.png")
    img = f'<img src="{cobra}" alt="" style="width:220px;max-width:60%;opacity:0.85;margin-bottom:14px;">' if cobra else ""
    st.markdown(
        f"""
        <div style="text-align:center;padding:40px 20px;color:{C['ink_soft']};">
            {img}
            <p style="font-size:0.9rem;margin:0;">{html.escape(mensagem)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def secao_titulo(texto: str, icone: str = "dash") -> None:
    """Título de seção com ícone de linha + sublinhado no grafismo de cobra da marca."""
    div = _logo_data_uri("cobra_divisor.png")
    if div:
        estilo = (
            "border-bottom:none;padding-bottom:11px;"
            f"background:url({div}) left bottom / auto 7px repeat-x;"
        )
    else:
        estilo = ""
    ic = svg_icon(icone, tamanho=15, peso=2.1, cor=C["ink"])
    st.markdown(
        f'<p class="section-title" style="{estilo}display:flex;align-items:center;gap:8px;">{ic}{texto}</p>',
        unsafe_allow_html=True,
    )


def kpi_card(valor: str, sub: str = "", classe: str = "folha",
             icone: str = "", pill_texto: str = "", pill_classe: str = "",
             titulo: str = "") -> str:
    """
    Card de KPI no estilo SaaS: chip de ícone (cor da marca) + pílula de
    variação/estado no topo, número grande e rótulo abaixo.
    `classe`/`pill_classe` ∈ {folha, rio, sol, urucum}.
    `icone` é HTML pronto — normalmente o retorno de svg_icon(). `sub` é o
    rótulo descritivo sob o número. `titulo` vira o tooltip do número
    (usado para mostrar o valor exato quando o card exibe o valor abreviado).
    """
    classe = classe or "folha"
    chip = f'<div class="kpi-chip {classe}">{icone}</div>'
    pill = f'<span class="kpi-pill {pill_classe or classe}">{html.escape(pill_texto)}</span>' if pill_texto else ""
    sub_html = f'<div class="kpi-label">{html.escape(sub)}</div>' if sub else ""
    title_attr = f' title="{html.escape(titulo)}"' if titulo else ""
    # HTML em uma única linha lógica, SEM linhas em branco internas — uma
    # linha em branco faria o st.markdown encerrar o bloco HTML e renderizar
    # o resto como texto (bug já observado com pílula vazia).
    return (
        '<div class="kpi-card">'
        f'<div class="kpi-top">{chip}{pill}</div>'
        f'<div class="kpi-value"{title_attr}>{valor}</div>'
        f'{sub_html}'
        '</div>'
    )


# --------------------------------------------------------------------------- #
# AUTENTICAÇÃO — Owner / Admin / Viewer                                        #
# O Owner vem das Secrets (login fixo). Admins e Viewers são cadastrados        #
# pelo Owner e ficam persistidos em disco. Toda a aplicação fica bloqueada     #
# até o login ser validado — a sessão dura até o navegador ser fechado.       #
# --------------------------------------------------------------------------- #

_OWNER_LOGIN = st.secrets.get("ADMIN_LOGIN", "") if hasattr(st, "secrets") else ""
_OWNER_SENHA = st.secrets.get("ADMIN_SENHA", "") if hasattr(st, "secrets") else ""

if "autenticado" not in st.session_state:
    st.session_state["autenticado"]   = False
    st.session_state["papel"]         = None
    st.session_state["nome_usuario"]  = None
    st.session_state["login_usuario"] = None

if not st.session_state["autenticado"]:
    _logo_login = _logo_data_uri("logo_vertical.png")
    _img_html = (
        f'<img src="{_logo_login}" alt="Museu das Amazônias" '
        f'style="height:150px;width:auto;margin-bottom:6px;">'
        if _logo_login else '<div style="font-size:2.6rem;">🏛️</div>'
    )
    # Cobra fixa na lateral direita — cabeça no topo, minimalista
    cobra_lateral()
    st.markdown(
        f"""
        <div class="maz-trancado maz-flow" style="max-width:420px;margin:48px auto 26px;"></div>
        <div style="max-width:420px;margin:0 auto 8px;text-align:center;">
            {_img_html}
            <p class="maz-display" style="font-size:0.72rem;font-weight:700;color:{C['ink_soft']};
               text-transform:uppercase;letter-spacing:0.2em;margin-top:14px;">
                Dashboard Gerencial de Pagamentos
            </p>
            <p style="font-size:0.8rem;color:{C['ink_soft']};margin-bottom:18px;">
                IDG — Instituto de Desenvolvimento e Gestão
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, col_form, _ = st.columns([1, 1.2, 1])
    with col_form:
        with st.form("form_login"):
            login_input = st.text_input("Login", placeholder="seu login")
            senha_input = st.text_input("Senha", type="password", placeholder="••••••••")
            entrar = st.form_submit_button("Entrar", use_container_width=True)

        if entrar:
            resultado = dh.autenticar(login_input, senha_input, _OWNER_LOGIN, _OWNER_SENHA)
            if resultado:
                st.session_state["autenticado"]   = True
                st.session_state["papel"]         = resultado["papel"]
                st.session_state["nome_usuario"]  = resultado["nome"]
                st.session_state["login_usuario"] = resultado["login"]
                st.session_state["intro_pendente"] = True
                st.rerun()
            else:
                st.error("Login ou senha incorretos.")

    st.stop()

# --------------------------------------------------------------------------- #
# ANIMAÇÃO DE ABERTURA — toca uma vez, logo após o login ser confirmado        #
# --------------------------------------------------------------------------- #
if st.session_state.pop("intro_pendente", False):
    _video_intro = _video_data_uri("intro_escuro.mp4" if TEMA_ATUAL == "escuro" else "intro_claro.mp4")
    if _video_intro:
        _intro_placeholder = st.empty()
        _intro_placeholder.markdown(
            f"""
            <div style="position:fixed;inset:0;z-index:9999;background:{C['paper']};
                        display:flex;align-items:center;justify-content:center;">
                <video autoplay muted playsinline
                       style="max-width:1100px;width:92%;max-height:92vh;height:auto;">
                    <source src="{_video_intro}" type="video/mp4">
                </video>
            </div>
            """,
            unsafe_allow_html=True,
        )
        time.sleep(4.0)
        _intro_placeholder.empty()

_papel_usuario = st.session_state["papel"]
_PAPEL_LABEL = {
    dh.PAPEL_OWNER:        "👑 Owner",
    dh.PAPEL_ADMIN:        "🛠️ Admin",
    dh.PAPEL_VIEWER:       "👁️ Viewer",
    dh.PAPEL_REQUISITANTE: "🙋 Requisitante",
}
_PAPEL_DESCRICAO = {
    dh.PAPEL_ADMIN:        "🛠️ Admin (edita configurações e lança direto)",
    dh.PAPEL_VIEWER:       "👁️ Viewer (somente visualização)",
    dh.PAPEL_REQUISITANTE: "🙋 Requisitante (solicita pedidos p/ aprovação)",
}


# --------------------------------------------------------------------------- #
# Fonte de dados — carregada aqui (antes do cabeçalho) para que o sininho de   #
# aprovações pendentes, no topo, já tenha a contagem real disponível.         #
# Prioridade: 1) Arquivo local (5 dias, editável em Configurações)             #
#             2) Secrets (valor inicial, antes da 1ª configuração)             #
#             3) Vazio                                                        #
# --------------------------------------------------------------------------- #
_url_secrets = st.secrets.get("SHEETS_URL", "") if hasattr(st, "secrets") else ""
_aba_secrets = st.secrets.get("SHEETS_ABA", "") if hasattr(st, "secrets") else ""
_cfg_disk    = _ler_config_persistente()

sheets_url_input = _cfg_disk.get("sheets_url", "") or _url_secrets
nome_aba_input   = _cfg_disk.get("sheets_aba", "") or _aba_secrets

_n_pendentes_header = 0
if _papel_usuario == dh.PAPEL_OWNER and sheets_url_input and "gcp_service_account" in st.secrets:
    try:
        _n_pendentes_header = dh.contar_pendentes(sheets_url_input)
    except Exception:
        _n_pendentes_header = 0


# --------------------------------------------------------------------------- #
# CABEÇALHO PRINCIPAL                                                           #
# --------------------------------------------------------------------------- #

_logo_header = _logo_data_uri("logo_horizontal.png")
_logo_html = (
    f'<img src="{_logo_header}" alt="Museu das Amazônias" style="height:52px;width:auto;">'
    if _logo_header else '<div style="font-size:2.2rem;">🏛️</div>'
)
_icon_search = svg_icon("search", 15, C["ink_soft"])
_icon_bell   = svg_icon("bell", 17, C["ink_soft"])
_avatar_nome = st.session_state.get("nome_usuario") or "?"
_avatar_iniciais = "".join(p[0] for p in _avatar_nome.split()[:2]).upper() or "?"
_badge_html = (
    f'<span class="header-bell-badge">{_n_pendentes_header}</span>'
    if _n_pendentes_header > 0 else ""
)
def _render_header(titulo_pagina: str):
    """Cabeçalho fixo no topo de todas as páginas; o título reflete a página atual."""
    st.markdown('<div class="maz-trancado"></div>', unsafe_allow_html=True)
    st.markdown(f"""
<div class="header-container">
    {_logo_html}
    <div class="header-divider"></div>
    <div>
        <span class="header-eyebrow">Gestão de Pagamentos · IDG</span>
        <p class="header-title">{html.escape(titulo_pagina)}</p>
    </div>
    <div class="header-topbar">
        <div class="header-search">{_icon_search} Buscar pedidos, fornecedores...</div>
        <div class="header-bell">{_icon_bell}{_badge_html}</div>
        <div class="header-avatar-wrap">
            <div class="header-avatar">{_avatar_iniciais}</div>
            <div>
                <div class="header-avatar-name">{_avatar_nome}</div>
                <div class="header-avatar-role">{_PAPEL_LABEL.get(_papel_usuario, _papel_usuario)}</div>
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# SIDEBAR — Fonte de dados e filtros interativos                                #
# --------------------------------------------------------------------------- #

with st.sidebar:

    # ------------------------------------------------------------------ #
    # Identidade do usuário logado + logout                               #
    # ------------------------------------------------------------------ #
    col_user, col_logout = st.columns([2.2, 1])
    with col_user:
        st.markdown(
            f"**{st.session_state['nome_usuario']}**  \n"
            f"<span style='color:{C['ink_soft']};font-size:0.75rem;'>{_PAPEL_LABEL.get(_papel_usuario, _papel_usuario)}</span>",
            unsafe_allow_html=True,
        )
    with col_logout:
        if st.button("Sair", use_container_width=True):
            st.session_state["autenticado"]   = False
            st.session_state["papel"]         = None
            st.session_state["nome_usuario"]  = None
            st.session_state["login_usuario"] = None
            st.rerun()

    # ------------------------------------------------------------------ #
    # Alternador de tema — lembrado por pessoa (claro/escuro)              #
    # ------------------------------------------------------------------ #
    _tema_escuro_ativo = st.toggle(
        "🌙 Modo escuro",
        value=(TEMA_ATUAL == "escuro"),
        key="toggle_tema",
    )
    _novo_tema = "escuro" if _tema_escuro_ativo else "claro"
    if _novo_tema != TEMA_ATUAL:
        st.session_state["tema"] = _novo_tema
        _login_atual = st.session_state.get("login_usuario")
        if _login_atual:
            _salvar_tema(_login_atual, _novo_tema)
        st.rerun()

    # ------------------------------------------------------------------ #
    # Upload manual — fonte alternativa ao Google Sheets (fallback)       #
    # As telas de Configurações / Acessos / Log viraram a página          #
    # "Configurações" (seção Sistema do menu).                            #
    # ------------------------------------------------------------------ #
    st.markdown("---")
    st.markdown("### 📎 Upload Manual")
    arquivo = st.file_uploader(
        "Planilha (.xlsx ou .csv)",
        type=["xlsx", "xls", "csv"],
        help="Alternativa ao Google Sheets. O upload tem prioridade sobre o link.",
    )


# --------------------------------------------------------------------------- #
# CARREGAMENTO E PROCESSAMENTO DOS DADOS                                        #
# Prioridade: 1) Upload manual  2) Google Sheets  3) Tela de boas-vindas       #
# --------------------------------------------------------------------------- #

df = None
fonte_dados = None

if arquivo:
    # Upload manual tem prioridade (útil para testes pontuais)
    df = dh.carregar_dados(arquivo)
    fonte_dados = f"📎 Arquivo: `{arquivo.name}`"

elif sheets_url_input:
    # Sincronização automática com Google Sheets
    url_csv = dh.sheets_url_para_csv(sheets_url_input, nome_aba_input)

    if url_csv is None:
        st.error(
            "❌ URL não reconhecida como Google Sheets. "
            "Cole o link completo da planilha (deve conter `/spreadsheets/d/`)."
        )
        st.stop()

    try:
        df = dh.carregar_do_sheets(url_csv)
        fonte_dados = "🔄 Google Sheets · atualiza automaticamente a cada 5 min"
        # Verifica mudanças a cada 1h e registra no log (operação silenciosa)
        dh.verificar_e_logar(df)
    except Exception as e:
        st.error(
            "❌ Não foi possível acessar a planilha. Verifique se ela está compartilhada "
            "como **'Qualquer pessoa com o link pode ver'** e tente novamente.\n\n"
            f"Detalhe técnico: `{e}`"
        )
        st.stop()

else:
    # Tela de boas-vindas — nenhuma fonte configurada
    st.info("👈  **Cole o link do Google Sheets** ou faça o upload da planilha para visualizar o dashboard.", icon="📊")
    st.markdown('<p class="section-title">Estrutura esperada da planilha</p>', unsafe_allow_html=True)
    preview = pd.DataFrame({
        "Tipo":       ["Compra", "Pagamento", "Pagamento"],
        "Fornecedor": ["Empresa Exemplo Ltda"] * 3,
        "Req. MXM":   ["REQ-001"] * 3,
        "Valor":      ["R$ 30.000,00", "R$ 15.000,00", "R$ 15.000,00"],
        "Descritivo": ["Contrato de Serviços", "Parcela 1/2", "Parcela 2/2"],
        "Status":     ["Contrato/Template em aberto", "Pago", "Aprovado"],
        "Data pgto":  ["—", "01/05/2025", "01/06/2025"],
    })
    st.dataframe(preview, use_container_width=True, hide_index=True)
    st.caption("⚠️ A coluna **Tipo** é essencial para separar orçamento (Compra) de fluxo de caixa (Pagamento) sem duplicar valores.")
    st.stop()

if df is None or df.empty:
    st.error("A planilha parece estar vazia ou com formato incompatível. Verifique o arquivo e tente novamente.")
    st.stop()

df_compras, df_pag = dh.separar_por_tipo(df)
kpis = dh.calcular_kpis(df)

def _render_topo_contexto():
    """Fonte de dados, alerta de prazos e aviso de mapeamento — no topo de toda página."""
    # Indicador discreto de fonte e última atualização
    st.caption(fonte_dados)

    # Alerta automático de prazos (vencidos / vencendo em 30 dias)
    if "prazo_status" in df_compras.columns:
        _n_vencidos = int((df_compras["prazo_status"] == dh.PRAZO_VENCIDO).sum())
        _n_urgentes = int((df_compras["prazo_status"] == dh.PRAZO_URGENTE).sum())
        if _n_vencidos or _n_urgentes:
            _partes = []
            if _n_vencidos:
                _partes.append(f"🚨 <strong>{_n_vencidos}</strong> contrato{'s' if _n_vencidos != 1 else ''} vencido{'s' if _n_vencidos != 1 else ''}")
            if _n_urgentes:
                _partes.append(f"⚠️ <strong>{_n_urgentes}</strong> vencendo em até 30 dias")
            st.markdown(
                f"""
                <div style="background:{C['urucum']}0F;border:1px solid {C['urucum']}55;border-radius:6px;
                            padding:10px 16px;margin-bottom:14px;font-size:0.85rem;color:{C['ink']};">
                    {" &nbsp;·&nbsp; ".join(_partes)}
                    &nbsp;·&nbsp; <span style="color:{C['ink_soft']};">detalhes em 📅 Prazos de Contratos</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Aviso de diagnóstico: colunas essenciais não mapeadas
    _colunas_essenciais = {"tipo", "fornecedor", "valor", "status"}
    _colunas_faltando = _colunas_essenciais - set(df.columns)
    if _colunas_faltando:
        with st.expander("⚠️ Aviso de mapeamento de colunas — clique para ver detalhes", expanded=True):
            st.warning(
                f"As seguintes colunas não foram reconhecidas: **{', '.join(sorted(_colunas_faltando))}**\n\n"
                "Verifique se os nomes na planilha coincidem com os esperados.\n\n"
                f"**Colunas recebidas da planilha:** `{', '.join(df.columns.tolist())}`"
            )


# --------------------------------------------------------------------------- #
# APROVAÇÕES — diálogo de revisão (Owner corrige antes de aprovar, ou rejeita) #
# --------------------------------------------------------------------------- #

@st.dialog("Revisar Solicitação")
def _dialog_revisar_solicitacao(solicitacao: dict) -> None:
    c = solicitacao["compra"]
    st.caption(
        f"Solicitado por **{solicitacao['solicitante_nome']}** "
        f"em {solicitacao['data_solicitacao']}"
    )

    _opts_status = dh.STATUS_TODOS
    _idx_status = _opts_status.index(c.get("status")) if c.get("status") in _opts_status else 0

    col1, col2 = st.columns(2)
    with col1:
        f_fornecedor = st.text_input("Fornecedor *", value=c.get("fornecedor", ""))
        f_req        = st.text_input("Req. MXM", value=c.get("req_mxm", ""))
        f_valor      = st.number_input("Valor total (R$) *", min_value=0.0, step=100.0, format="%.2f", value=_val_num(c.get("valor")))
        f_status     = st.selectbox("Status inicial", options=_opts_status, index=_idx_status)
    with col2:
        f_descritivo = st.text_input("Descritivo", value=c.get("descritivo", ""))
        f_termino    = st.date_input("Término do contrato", value=_val_date(c.get("termino_contrato")))
        f_link       = st.text_input("Link do contrato", value=c.get("link_contrato", ""))
    f_obs = st.text_area("Observações", value=c.get("observacoes", ""), height=70)

    st.markdown("**Parcelas**")
    parcelas_editadas = []
    for i, p in enumerate(solicitacao["parcelas"]):
        st.caption(p.get("descritivo") or f"Parcela {i + 1}")
        pc1, pc2 = st.columns(2)
        with pc1:
            pv = st.number_input(
                "Valor da parcela (R$)", min_value=0.0, step=100.0, format="%.2f",
                value=_val_num(p.get("valor")), key=f"rev_valor_{i}",
            )
            _opts_p = dh.STATUS_TODOS
            _idx_p = _opts_p.index(p.get("status")) if p.get("status") in _opts_p else 0
            ps = st.selectbox("Status", options=_opts_p, index=_idx_p, key=f"rev_status_{i}")
        with pc2:
            pdoc = st.text_input("Doc. Fiscal", value=p.get("doc_fiscal", ""), key=f"rev_doc_{i}")
            pdt  = st.date_input("Data de pagamento", value=_val_date(p.get("data_pgto")), key=f"rev_data_{i}")
        parcelas_editadas.append({"valor": pv, "status": ps, "doc_fiscal": pdoc, "data_pgto": pdt})

    st.divider()
    col_aprovar, col_cancelar = st.columns(2)
    with col_aprovar:
        if st.button("✅ Aprovar e lançar", use_container_width=True, type="primary"):
            if not f_fornecedor.strip() or f_valor <= 0:
                st.error("Fornecedor e Valor total são obrigatórios.")
            else:
                try:
                    avisos = dh.aprovar_solicitacao(
                        sheets_url_input, nome_aba_input, solicitacao["idx"],
                        {
                            "fornecedor": f_fornecedor, "req_mxm": f_req, "valor": f_valor,
                            "descritivo": f_descritivo, "status": f_status,
                            "termino_contrato": f_termino, "link_contrato": f_link,
                            "observacoes": f_obs,
                        },
                        parcelas_editadas,
                    )
                    dh.carregar_do_sheets.clear()
                    st.session_state["flash_ok"] = f"Pedido de {f_fornecedor} aprovado e lançado na planilha."
                    if avisos:
                        st.session_state["flash_avisos"] = avisos
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao aprovar: `{e}`")
    with col_cancelar:
        if st.button("Fechar", use_container_width=True):
            st.rerun()

    motivo = st.text_area("Motivo da rejeição (opcional)", key="rev_motivo", height=60)
    if st.button("❌ Rejeitar solicitação", use_container_width=True):
        try:
            dh.rejeitar_solicitacao(sheets_url_input, solicitacao["idx"], motivo)
            st.session_state["flash_ok"] = "Solicitação rejeitada."
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao rejeitar: `{e}`")


# --------------------------------------------------------------------------- #
# SIDEBAR — Filtros dinâmicos (renderizados após carga dos dados)               #
# --------------------------------------------------------------------------- #

with st.sidebar:
    # A busca substituiu os filtros de sidebar; as Aprovações viraram a página
    # "Aprovações" (seção Fluxo do menu, visível ao Owner).
    st.markdown("---")
    st.caption(
        f"**{len(df)}** registros carregados · "
        f"**{df['fornecedor'].nunique() if 'fornecedor' in df.columns else 0}** fornecedores"
    )

# Sem filtros de sidebar: os KPIs, gráficos e a exportação usam a base completa.
df_filtrado = df


# --------------------------------------------------------------------------- #
# LANÇAMENTOS — grava direto na planilha via Service Account (Owner/Admin)     #
# Diferente da leitura (link público), a escrita exige credenciais próprias.  #
# --------------------------------------------------------------------------- #

def _limpar_wizard_lancamento() -> None:
    """Remove do session_state todo o estado do assistente de lançamento."""
    for k in list(st.session_state.keys()):
        if k.startswith("np_") or k.startswith("wiz_") or k in (
            "lanc_etapa", "lanc_compra", "lanc_n_parcelas", "lanc_parcelas_extraidas",
        ):
            del st.session_state[k]


# --------------------------------------------------------------------------- #
# Extração de dados de PDF por padrões de texto (sem IA/API paga) — calibrada  #
# nos modelos de "Ordem de Compra" e "Termo Aditivo/Contrato" do IDG.          #
# Se o layout de um fornecedor variar muito, o campo simplesmente não é       #
# encontrado e fica em branco para preenchimento manual (nunca inventa dado). #
# --------------------------------------------------------------------------- #

_MESES_EXTENSO_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}


def _extrair_texto_pdf(pdf_bytes: bytes) -> str:
    import io
    import pypdf
    leitor = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)


def _parse_valor_brl(texto: str) -> float | None:
    try:
        return float(texto.strip().replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _parse_data_extenso_pt(texto: str) -> "date | None":
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", texto, re.IGNORECASE)
    if not m:
        return None
    dia, mes_nome, ano = m.groups()
    mes = _MESES_EXTENSO_PT.get(mes_nome.lower())
    if not mes:
        return None
    try:
        return datetime(int(ano), mes, int(dia)).date()
    except ValueError:
        return None


def _parse_data_qualquer(texto: str) -> "date | None":
    """Aceita data em DD/MM/AAAA ou por extenso ('31 de julho de 2026')."""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto)
    if m:
        dia, mes, ano = m.groups()
        try:
            return datetime(int(ano), int(mes), int(dia)).date()
        except ValueError:
            return None
    return _parse_data_extenso_pt(texto)


def _extrair_termino_vigencia(texto: str) -> "date | None":
    """
    Acha a data final de vigência do contrato. Como termos aditivos citam
    tanto a vigência original quanto as prorrogações, coletamos TODAS as datas
    finais e devolvemos a mais distante (a prorrogação vigente estende o prazo).
    Normaliza espaços antes para não depender de quebras de linha do PDF.
    """
    t = re.sub(r"\s+", " ", texto)
    candidatos: list = []
    padroes = [
        r"vig[êe]ncia\s+de\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\s+a\s+(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
        r"vig[êe]ncia\s+de\s+\d{1,2}/\d{1,2}/\d{4}\s+a\s+(\d{1,2}/\d{1,2}/\d{4})",
        r"vig[êe]ncia[^.]{0,60}?\bat[ée]\s+(\d{1,2}\s+de\s+\w+\s+de\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})",
        # "vigorará durante o período de X a Y" / "período de X a Y"
        r"per[íi]odo\s+de\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\s+a\s+(\d{1,2}\s+de\s+\w+\s+de\s+\d{4})",
        r"per[íi]odo\s+de\s+\d{1,2}/\d{1,2}/\d{4}\s+a\s+(\d{1,2}/\d{1,2}/\d{4})",
    ]
    for p in padroes:
        for m in re.finditer(p, t, re.IGNORECASE):
            dt = _parse_data_qualquer(m.group(1))
            if dt:
                candidatos.append(dt)
    return max(candidatos) if candidatos else None


# Status inicial sugerido para a parcela recém-importada: o pagamento ainda não
# aconteceu e a NF costuma não ter sido emitida quando o pedido/contrato é lançado.
_STATUS_PARCELA_PADRAO = "Aguardando emissão de NF/DANFE"


def _extrair_parcelas(texto: str, valor_total: "float | None") -> list[dict]:
    """
    Reconhece as parcelas de pagamento descritas no documento. A grande maioria
    dos pedidos/contratos do IDG é pagamento único (uma parcela = valor total),
    mas contratos parcelados descrevem cada parcela na cláusula de pagamento.
    Divide em várias parcelas quando o texto as descreve explicitamente:
      - enumeração com valor próprio ('(i) Primeira Parcela, no valor bruto de
        R$ X ... (ii) Saldo Remanescente, no valor bruto de R$ Y') — o total
        usa 'valor bruto E TOTAL de R$', que é distinto e fica de fora;
      - 'em N parcelas de R$ X';
      - '1ª parcela ... R$ X ... 2ª parcela ... R$ Y';
      - divisão percentual do valor total ('30% ... 70%', '50% ... 50%').
    O detalhamento de custos por item (ex: 'a) Projeto R$3.800 b) Visita
    R$6.480') NÃO conta como parcela — nesses casos o pagamento é integral.
    """
    t = re.sub(r"\s+", " ", texto)

    def _parcelas(valores: list[float]) -> list[dict]:
        return [{"valor": v, "status": _STATUS_PARCELA_PADRAO} for v in valores]

    # 1) Enumeração de parcelas com valor próprio ("no valor bruto de R$ X").
    #    O valor total do contrato usa "valor bruto E TOTAL de R$" — não casa
    #    aqui; ainda assim, por segurança, descartamos qualquer valor igual ao
    #    total (caso algum contrato escreva o total de outra forma).
    enumeradas = [v for v in (
        _parse_valor_brl(x) for x in re.findall(r"valor\s+bruto\s+de\s+R\$\s*([\d.,]+)", t, re.IGNORECASE)
    ) if v]
    if valor_total:
        enumeradas = [v for v in enumeradas if abs(v - valor_total) >= 0.01]
    if len(enumeradas) >= 2:
        return _parcelas(enumeradas)

    # 2) "em N (…) parcelas [iguais/mensais] de R$ X"
    m = re.search(
        r"\bem\s+(\d{1,2})\s*(?:\([^)]*\)\s*)?parcelas?\b[^.]{0,80}?de\s+R\$\s*([\d.,]+)",
        t, re.IGNORECASE,
    )
    if m:
        n = int(m.group(1))
        v = _parse_valor_brl(m.group(2))
        if 2 <= n <= 60 and v:
            return _parcelas([v] * n)

    # 3) parcelas nomeadas: "1ª parcela ... R$ X", "2ª parcela ... R$ Y"
    nomeadas = [v for v in (
        _parse_valor_brl(mm.group(1))
        for mm in re.finditer(r"\b\d{1,2}[ªaºo]\s*parcela\b[^R]{0,50}R\$\s*([\d.,]+)", t, re.IGNORECASE)
    ) if v]
    if len(nomeadas) >= 2:
        return _parcelas(nomeadas)

    # 4) divisão por percentuais do valor total ("30% ... 70%", "50% ... 50%")
    if valor_total:
        percs = [int(x) for x in re.findall(r"(\d{1,3})\s*%\s*(?:\([^)]*\)\s*)?do valor total", t, re.IGNORECASE)]
        if len(percs) >= 2 and abs(sum(percs) - 100) <= 1:
            return _parcelas([round(valor_total * p / 100, 2) for p in percs])

    # 5) padrão: pagamento único = valor total
    if valor_total:
        return _parcelas([float(valor_total)])
    return []


def _extrair_pedido_compra(texto: str) -> dict:
    """Padrão 'ORDEM DE COMPRA' (PO) gerado pelo próprio sistema do IDG."""
    d: dict = {"_tipo": "pedido"}
    m = re.search(r"FORNECEDOR:\s*\n\s*I\.E\.:.*\n\s*(.+)", texto)
    if m:
        d["fornecedor"] = m.group(1).strip()
    m = re.search(r"REQUISIÇÃO\(ÕES\):\s*([\d;,\s]+)", texto)
    if m:
        d["req_mxm"] = m.group(1).strip().rstrip(";").strip()
    m = re.search(r"PO #:\s*(\S+)", texto)
    if m:
        d["numero_contrato"] = f"Pedido de Compra nº {m.group(1)}"
    m = re.search(r"^\d+\s+.*R\$\s*[\d.,]+\s+([\d.,]+)\s*$", texto, re.MULTILINE)
    if m:
        d["valor"] = _parse_valor_brl(m.group(1))
    m = re.search(r"Descritivo para emiss[ãa]o de nota fiscal:\s*(.+)", texto)
    if m:
        d["descritivo"] = m.group(1).strip()
    m = re.search(r"OBSERVAÇÃO DO PEDIDO:\s*(.+)", texto)
    if m:
        d["observacoes"] = m.group(1).strip()
        d.setdefault("descritivo", d["observacoes"])
    # Data de entrega do pedido → serve de término quando não há contrato anexo
    m = re.search(r"DATA DE ENTREGA:\s*\n\s*CONTRATANTE:\s*\n\s*(\d{2}/\d{2}/\d{4})", texto)
    if m:
        d["termino_contrato"] = _parse_data_qualquer(m.group(1))
    parcelas = _extrair_parcelas(texto, d.get("valor"))
    if parcelas:
        d["parcelas"] = parcelas
    return d


def _extrair_contrato(texto: str) -> dict:
    """Padrão de Contrato/Termo Aditivo de prestação de serviços do IDG."""
    d: dict = {"_tipo": "contrato"}
    m = re.search(r"N[°ºo]\s*(\d{4}\s*[–-]\s*\d+(?:\s*\([^)]*\))?)", texto)
    if m:
        d["numero_contrato"] = f"Contrato nº {re.sub(r'\s+', ' ', m.group(1)).strip()}"
    m = re.search(r"De outro lado,\s*([A-ZÁ-Ú0-9][A-ZÀ-Ü0-9.\-\s&/]+?),", texto)
    if m:
        d["fornecedor"] = m.group(1).strip()
    m = re.search(r"valor bruto e total de R\$\s*([\d.,]+)", texto, re.IGNORECASE)
    if m:
        d["valor"] = _parse_valor_brl(m.group(1))
    m = re.search(r"(no prazo de[^.]+?apresenta[çc][ãa]o da Nota\s*Fiscal[^.]*)\.", texto, re.IGNORECASE)
    if m:
        d["observacoes"] = re.sub(r"\s+", " ", m.group(1)).strip()
    termino = _extrair_termino_vigencia(texto)
    if termino:
        d["termino_contrato"] = termino
    m = re.search(
        r"(TERMO ADITIVO.+?AMAZ[ÔO]NIAS|CONTRATO DE PRESTA[ÇC][ÃA]O.+?AMAZ[ÔO]NIAS)",
        texto, re.IGNORECASE | re.DOTALL,
    )
    if m:
        d["descritivo"] = re.sub(r"\s+", " ", m.group(1)).strip().title()
    parcelas = _extrair_parcelas(texto, d.get("valor"))
    if parcelas:
        d["parcelas"] = parcelas
    return d


# Para cada campo, a ordem de fontes preferidas ao mesclar vários documentos.
# Pedido é a melhor fonte de requisição/valor/descritivo; contrato é a melhor
# fonte de número, vigência e condição de pagamento.
_PRIORIDADE_MESCLA = {
    "fornecedor":       ("pedido", "contrato"),
    "req_mxm":          ("pedido", "contrato"),
    "valor":            ("pedido", "contrato"),
    "descritivo":       ("pedido", "contrato"),
    "numero_contrato":  ("contrato", "pedido"),
    "termino_contrato": ("contrato", "pedido"),
    "observacoes":      ("contrato", "pedido"),
    "parcelas":         ("contrato", "pedido"),
}


def _mesclar_dados_extraidos(docs: list[dict]) -> dict:
    """
    Combina os dados de vários PDFs (ex: pedido de compra + contrato), pegando
    cada campo da fonte mais confiável (ver _PRIORIDADE_MESCLA). Com um só
    documento, devolve os dados dele sem alteração.
    """
    por_tipo: dict[str, dict] = {}
    for doc in docs:
        por_tipo.setdefault(doc.get("_tipo", "pedido"), doc)
    resultado: dict = {}
    for campo, ordem in _PRIORIDADE_MESCLA.items():
        for tipo in ordem:
            valor = por_tipo.get(tipo, {}).get(campo)
            if valor:
                resultado[campo] = valor
                break
    # Pagamento único: mantém a parcela alinhada ao valor total escolhido na
    # mesclagem (que pode ter vindo de um documento diferente do da parcela).
    _parcelas = resultado.get("parcelas")
    if _parcelas and len(_parcelas) == 1 and resultado.get("valor"):
        _parcelas = [{**_parcelas[0], "valor": float(resultado["valor"])}]
        resultado["parcelas"] = _parcelas
    return resultado


def _extrair_dados_documento_ia(pdf_bytes: bytes) -> dict | None:
    """
    Lê o PDF (pedido de compra ou contrato) e tenta reconhecer os campos do
    wizard de lançamento por padrões de texto — sem IA paga, sem dado saindo
    do servidor. Nunca escreve nada sozinho: só sugere valores para a pessoa
    revisar no formulário antes de confirmar.

    Retorna None se o PDF não puder ser lido; campos não reconhecidos ficam
    simplesmente ausentes do dict (o formulário mantém o padrão vazio/manual).
    """
    try:
        texto = _extrair_texto_pdf(pdf_bytes)
    except Exception:
        return None
    if not texto.strip():
        return None
    if re.search(r"ORDEM DE COMPRA", texto, re.IGNORECASE):
        return _extrair_pedido_compra(texto)
    return _extrair_contrato(texto)


def _wizard_pedido(modo: str) -> None:
    """
    Assistente de 2 etapas (Pedido de Compra → Parcelas) reaproveitado por
    dois fluxos, conforme `modo`:
      - "lancar":    Owner/Admin grava direto na planilha (como já era)
      - "solicitar": Requisitante envia para a fila de aprovação do Owner
    """
    ss = st.session_state
    ss.setdefault("lanc_etapa", 1)
    ss.setdefault("lanc_compra", {})
    ss.setdefault("lanc_n_parcelas", 1)

    # ==================== ETAPA 1 — Pedido de Compra ==================== #
    if ss["lanc_etapa"] == 1:
        c = ss["lanc_compra"]
        _opts_status = dh.STATUS_TODOS
        _idx_status = _opts_status.index(c["status"]) if c.get("status") in _opts_status else 0

        with st.expander("📄 Importar dados de PDF (pedido de compra e/ou contrato)", expanded=False):
            st.caption(
                "Sobe o pedido de compra, o contrato/termo aditivo, ou os dois juntos — "
                "os campos abaixo são pré-preenchidos automaticamente, combinando o melhor "
                "de cada documento. Confira e ajuste antes de avançar."
            )
            _arquivos_ia = st.file_uploader(
                "Documentos (PDF)", type=["pdf"], accept_multiple_files=True, key="upload_ia_doc",
            )
            if st.button("✨ Extrair dados", key="btn_extrair_ia", disabled=not _arquivos_ia):
                with st.spinner("Lendo o(s) documento(s)..."):
                    _extraidos = [
                        _d for _arq in _arquivos_ia
                        if (_d := _extrair_dados_documento_ia(_arq.read()))
                    ]
                _dados_ia = _mesclar_dados_extraidos(_extraidos) if _extraidos else None
                if not _dados_ia:
                    st.error("Não foi possível reconhecer os dados desse(s) documento(s). Preencha manualmente abaixo.")
                else:
                    # Seed direto nas chaves dos widgets (não só em lanc_compra): um
                    # widget já instanciado ignora `value=` em reruns seguintes — só
                    # session_state[key] setado ANTES da nova instanciação é confiável
                    # (mesma lição aprendida no botão "Limpar" da busca).
                    if _dados_ia.get("fornecedor"):
                        ss["wiz_fornecedor"] = _dados_ia["fornecedor"]
                    if _dados_ia.get("req_mxm"):
                        ss["wiz_req"] = _dados_ia["req_mxm"]
                    if _dados_ia.get("valor"):
                        ss["wiz_valor"] = float(_dados_ia["valor"])
                    if _dados_ia.get("descritivo"):
                        ss["wiz_descritivo"] = _dados_ia["descritivo"]
                    if _dados_ia.get("termino_contrato"):
                        ss["wiz_termino"] = _dados_ia["termino_contrato"]
                    _obs_partes = []
                    if _dados_ia.get("numero_contrato"):
                        _obs_partes.append(_dados_ia["numero_contrato"])
                    if _dados_ia.get("observacoes"):
                        _obs_partes.append(_dados_ia["observacoes"])
                    if _obs_partes:
                        ss["wiz_obs"] = " · ".join(_obs_partes)
                    if _dados_ia.get("parcelas"):
                        ss["lanc_parcelas_extraidas"] = _dados_ia["parcelas"]
                    _campos_achados = sum(1 for k in ("fornecedor", "valor", "descritivo", "termino_contrato", "numero_contrato") if _dados_ia.get(k))
                    if not _campos_achados:
                        st.warning("Nenhum campo reconhecido nesse documento. Preencha manualmente abaixo.")
                    st.rerun(scope="fragment")

        with st.form("form_compra"):
            st.markdown("**1. Dados do Pedido de Compra**")
            col1, col2 = st.columns(2)
            with col1:
                f_fornecedor = st.text_input("Fornecedor *", value=c.get("fornecedor", ""), key="wiz_fornecedor")
                f_req        = st.text_input("Req. MXM", value=c.get("req_mxm", ""), key="wiz_req")
                f_valor      = st.number_input("Valor total do contrato (R$) *", min_value=0.0, step=100.0, format="%.2f", value=float(c.get("valor", 0.0)), key="wiz_valor")
                f_status     = st.selectbox("Status inicial *", options=_opts_status, index=_idx_status)
            with col2:
                f_descritivo = st.text_input("Descritivo", value=c.get("descritivo", ""), key="wiz_descritivo")
                f_termino    = st.date_input("Término do contrato", value=c.get("termino_contrato") or None, key="wiz_termino")
                f_link       = st.text_input("Link do contrato", value=c.get("link_contrato", ""), key="wiz_link")
            f_obs = st.text_area("Observações", height=80, value=c.get("observacoes", ""), key="wiz_obs")

            avancar = st.form_submit_button("Avançar para pagamento  →", use_container_width=True)

        if avancar:
            if not f_fornecedor.strip() or f_valor <= 0:
                st.error("Fornecedor e Valor total são obrigatórios.")
            else:
                ss["lanc_compra"] = {
                    "fornecedor":       f_fornecedor,
                    "req_mxm":          f_req,
                    "valor":            f_valor,
                    "descritivo":       f_descritivo,
                    "status":           f_status,
                    "termino_contrato": f_termino,
                    "link_contrato":    f_link,
                    "observacoes":      f_obs,
                }
                _parcelas_ia = ss.pop("lanc_parcelas_extraidas", None)
                if _parcelas_ia:
                    ss["lanc_n_parcelas"] = len(_parcelas_ia)
                    for _i, _p in enumerate(_parcelas_ia):
                        if _p.get("valor"):
                            ss[f"np_valor_{_i}"] = float(_p["valor"])
                        if _p.get("status") in dh.STATUS_TODOS:
                            ss[f"np_status_{_i}"] = _p["status"]
                ss["lanc_etapa"] = 2
                st.rerun(scope="fragment")
        return

    # ==================== ETAPA 2 — Condições de Pagamento ==================== #
    c = ss["lanc_compra"]
    st.markdown(
        "**2. Condições de Pagamento** &nbsp;·&nbsp; "
        f"<span style='color:{C['ink_soft']};'>{html.escape(str(c.get('fornecedor', '')))} · "
        f"{fmt_brl(c.get('valor', 0))}</span>",
        unsafe_allow_html=True,
    )
    if st.button("←  Voltar ao pedido", key="lanc_voltar"):
        ss["lanc_etapa"] = 1
        st.rerun(scope="fragment")

    n = ss["lanc_n_parcelas"]
    for i in range(n):
        rotulo = "Parcela única" if n == 1 else f"{i + 1}ª Parcela"
        st.markdown(f"**{rotulo}**")
        col1, col2 = st.columns(2)
        with col1:
            st.number_input("Valor da parcela (R$) *", min_value=0.0, step=100.0, format="%.2f", key=f"np_valor_{i}")
            st.selectbox("Status *", options=dh.STATUS_TODOS, key=f"np_status_{i}")
        with col2:
            st.text_input("Doc. Fiscal (nº da NF)", key=f"np_doc_{i}")
            st.date_input("Data de pagamento", value=None, key=f"np_data_{i}")

    label_botao = "💾 Registrar pagamento" if modo == "lancar" else "📨 Enviar para aprovação"

    col_add, col_reg = st.columns(2)
    with col_add:
        if st.button("➕ Adicionar parcela", use_container_width=True, key="lanc_add"):
            ss["lanc_n_parcelas"] += 1
            st.rerun(scope="fragment")
    with col_reg:
        registrar = st.button(label_botao, use_container_width=True, type="primary", key="lanc_reg")

    if registrar:
        # Coleta só as parcelas efetivamente preenchidas (valor > 0)
        parcelas = []
        for i in range(n):
            valor = ss.get(f"np_valor_{i}", 0.0)
            if valor and valor > 0:
                parcelas.append({
                    "valor":      valor,
                    "status":     ss.get(f"np_status_{i}"),
                    "doc_fiscal": ss.get(f"np_doc_{i}", ""),
                    "data_pgto":  ss.get(f"np_data_{i}"),
                })

        if not parcelas:
            st.error("Informe ao menos uma parcela com valor.")
        else:
            try:
                if modo == "lancar":
                    avisos = dh.inserir_compra_com_parcelas(sheets_url_input, nome_aba_input, c, parcelas)
                    dh.carregar_do_sheets.clear()
                    msg = f"Pedido de {c.get('fornecedor')} e {len(parcelas)} parcela(s) registrados na planilha."
                else:
                    dh.criar_solicitacao(
                        sheets_url_input, c, parcelas,
                        st.session_state["login_usuario"], st.session_state["nome_usuario"],
                    )
                    dh.contar_pendentes.clear()
                    avisos = []
                    msg = f"Solicitação de {c.get('fornecedor')} enviada para aprovação do Owner."
                _limpar_wizard_lancamento()
                st.session_state["flash_ok"] = msg
                if avisos:
                    st.session_state["flash_avisos"] = avisos
                st.rerun(scope="app")
            except Exception as e:
                st.error(f"Não foi possível gravar.\n\nDetalhe técnico: `{e}`")


@st.fragment
def _bloco_novo_lancamento():
    """Owner/Admin: lança direto na planilha (isolado com @st.fragment)."""
    if _papel_usuario not in (dh.PAPEL_OWNER, dh.PAPEL_ADMIN):
        return
    secao_titulo("Novo Lançamento", icone="plus")
    if "gcp_service_account" not in st.secrets:
        st.info(
            "🔒 Os lançamentos pelo dashboard exigem a Service Account configurada "
            "nos Secrets (`gcp_service_account`). Até isso ser configurado, "
            "novos pedidos e pagamentos continuam sendo lançados direto na planilha.",
            icon="ℹ️",
        )
        return
    _wizard_pedido("lancar")


@st.fragment
def _bloco_solicitar_pedido():
    """Requisitante: envia o pedido para a fila de aprovação do Owner."""
    if _papel_usuario != dh.PAPEL_REQUISITANTE:
        return
    secao_titulo("Solicitar Pedido de Compra", icone="user")
    if "gcp_service_account" not in st.secrets:
        st.info(
            "🔒 O envio de solicitações exige a Service Account configurada "
            "nos Secrets (`gcp_service_account`). Fale com o Owner do dashboard.",
            icon="ℹ️",
        )
        return
    st.caption("Preencha os dados abaixo. Seu pedido será enviado para aprovação antes de valer oficialmente.")
    _wizard_pedido("solicitar")


@st.fragment
def _bloco_meus_pedidos():
    """Requisitante: acompanha o status dos próprios pedidos enviados."""
    if _papel_usuario != dh.PAPEL_REQUISITANTE:
        return
    if "gcp_service_account" not in st.secrets:
        return

    secao_titulo("Meus Pedidos", icone="user")
    login_atual = st.session_state.get("login_usuario", "")
    try:
        meus = dh.listar_solicitacoes(sheets_url_input, apenas_login=login_atual)
    except Exception as e:
        st.error(f"Não foi possível carregar seus pedidos: `{e}`")
        return

    if not meus:
        st.caption("Você ainda não enviou nenhum pedido.")
        return

    _cor_aprov = {
        dh.STATUS_APROVACAO_PENDENTE:  C["sol"],
        dh.STATUS_APROVACAO_APROVADO:  C["folha"],
        dh.STATUS_APROVACAO_REJEITADO: C["urucum"],
    }
    _emoji_aprov = {
        dh.STATUS_APROVACAO_PENDENTE:  "⏳",
        dh.STATUS_APROVACAO_APROVADO:  "✅",
        dh.STATUS_APROVACAO_REJEITADO: "❌",
    }

    for s in meus:
        c = s["compra"]
        st_aprov = s["status_aprovacao"] or dh.STATUS_APROVACAO_PENDENTE
        cor = _cor_aprov.get(st_aprov, C["ink_soft"])
        emoji = _emoji_aprov.get(st_aprov, "•")
        motivo_html = (
            f"<div style='color:{C['ink_soft']};font-size:0.76rem;margin-top:4px;'>Motivo: {html.escape(s['motivo_rejeicao'])}</div>"
            if st_aprov == dh.STATUS_APROVACAO_REJEITADO and s.get("motivo_rejeicao") else ""
        )
        st.markdown(
            f"""
            <div style="background:{C['surface']};border:1px solid {C['line']};border-left:4px solid {cor};
                        border-radius:6px;padding:10px 16px;margin-bottom:6px;">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                    <div>
                        <span style="font-weight:700;color:{C['ink']};font-size:0.9rem;">{html.escape(c.get('fornecedor', '—'))}</span>
                        <span style="color:{C['ink_soft']};font-size:0.76rem;margin-left:8px;">{html.escape(_fmt(c.get('valor'), 'valor'))}</span>
                    </div>
                    <span style="color:{cor};font-weight:700;font-size:0.78rem;">{emoji} {html.escape(st_aprov)}</span>
                </div>
                <div style="color:{C['ink_soft']};font-size:0.74rem;margin-top:4px;">Enviado em {html.escape(s['data_solicitacao'])}</div>
                {motivo_html}
            </div>
            """,
            unsafe_allow_html=True,
        )


def _pagina_lancamento():
    _bloco_novo_lancamento()
    _bloco_solicitar_pedido()
    _bloco_meus_pedidos()


# --------------------------------------------------------------------------- #
# SEÇÃO 1 — KPI CARDS (visão macro para a diretoria)                           #
# Alguns cards são clicáveis: abrem um modal com a lista por trás do número.   #
# --------------------------------------------------------------------------- #

def _tabela_pagamentos_kpi(d):
    """Tabela de parcelas/pagamentos para o modal de detalhe de um KPI."""
    if d is None or d.empty:
        st.caption("Nenhum registro nesta categoria.")
        return
    d = d.sort_values("valor", ascending=False) if "valor" in d.columns else d
    cols = {}
    if "fornecedor" in d.columns: cols["Fornecedor"] = d["fornecedor"].astype(str)
    if "valor" in d.columns:      cols["Valor"] = d["valor"].apply(fmt_brl)
    if "status" in d.columns:     cols["Status"] = d["status"].astype(str)
    if "doc_fiscal" in d.columns: cols["NF"] = d["doc_fiscal"].apply(lambda x: _val_txt(x) or "—")
    if "data_pgto" in d.columns:  cols["Data pgto"] = d["data_pgto"].apply(lambda x: _fmt(x, "data"))
    st.dataframe(pd.DataFrame(cols), use_container_width=True, hide_index=True)


def _tabela_contratos_kpi(d):
    """Tabela de contratos (compras) para o modal de detalhe de um KPI."""
    if d is None or d.empty:
        st.caption("Nenhum registro nesta categoria.")
        return
    d = d.sort_values("dias_para_vencer") if "dias_para_vencer" in d.columns else d
    cols = {}
    if "fornecedor" in d.columns:       cols["Fornecedor"] = d["fornecedor"].astype(str)
    if "valor" in d.columns:            cols["Valor"] = d["valor"].apply(fmt_brl)
    if "termino_contrato" in d.columns: cols["Término"] = d["termino_contrato"].apply(lambda x: _fmt(x, "data"))
    if "descritivo" in d.columns:       cols["Descritivo"] = d["descritivo"].apply(lambda x: _val_txt(x) or "—")
    st.dataframe(pd.DataFrame(cols), use_container_width=True, hide_index=True)


@st.dialog("Detalhamento do indicador", width="large")
def _dialog_kpi_detalhe(qual: str):
    if qual == "pago":
        st.markdown(f"**Total pago** &nbsp;·&nbsp; {fmt_brl(kpis['pago'])}")
        _d = df_pag[df_pag["status"] == "Pago"] if "status" in df_pag.columns else None
        _tabela_pagamentos_kpi(_d)
    elif qual == "a_pagar":
        st.markdown(f"**Saldo a pagar** &nbsp;·&nbsp; {fmt_brl(kpis['a_pagar'])}")
        _d = df_pag[df_pag["status"] != "Pago"] if "status" in df_pag.columns else None
        _tabela_pagamentos_kpi(_d)
    elif qual == "gargalo":
        st.markdown(f"**Em gargalo · aguardando** &nbsp;·&nbsp; {fmt_brl(kpis['em_gargalo'])}")
        _sts = dh.STATUS_GRUPOS["alerta"] + dh.STATUS_GRUPOS["em_andamento"]
        _d = df_pag[df_pag["status"].isin(_sts)] if "status" in df_pag.columns else None
        _tabela_pagamentos_kpi(_d)
    elif qual == "a_vencer":
        st.markdown(f"**A vencer em até 30 dias** &nbsp;·&nbsp; {fmt_brl(kpis['a_vencer_30d'])}")
        _d = df_compras[df_compras["prazo_status"] == dh.PRAZO_URGENTE] if "prazo_status" in df_compras.columns else None
        _tabela_contratos_kpi(_d)
    elif qual == "vencidos":
        st.markdown(f"**Contratos vencidos** &nbsp;·&nbsp; {kpis['vencidos']} contrato(s)")
        _d = df_compras[df_compras["prazo_status"] == dh.PRAZO_VENCIDO] if "prazo_status" in df_compras.columns else None
        _tabela_contratos_kpi(_d)


def _botao_detalhe(qual: str, key: str):
    """Botão discreto sob um KPI clicável — abre o modal com a lista por trás."""
    if st.button("Ver detalhes  →", key=key, use_container_width=True):
        _dialog_kpi_detalhe(qual)


def _secao_indicadores():
    secao_titulo("Indicadores Executivos", icone="bar_chart")

    # Valores exibidos abreviados (R$ 15,1 mi); o valor exato fica no tooltip.
    _row1 = st.columns(4)
    with _row1[0]:
        st.markdown(kpi_card(
            fmt_brl_curto(kpis["orcamento_total"]),
            sub="Orçamento total contratado",
            classe="folha", icone=svg_icon("list", cor=C["folha"]),
            titulo=fmt_brl(kpis["orcamento_total"]),
        ), unsafe_allow_html=True)

    with _row1[1]:
        st.markdown(kpi_card(
            fmt_brl_curto(kpis["pago"]),
            sub="Total pago",
            classe="rio", icone=svg_icon("check_circle", cor=C["rio"]),
            pill_texto=f"{kpis['perc_execucao']:.1f}%", pill_classe="folha",
            titulo=fmt_brl(kpis["pago"]),
        ), unsafe_allow_html=True)
        _botao_detalhe("pago", "kpi_det_pago")

    with _row1[2]:
        st.markdown(kpi_card(
            fmt_brl_curto(kpis["a_pagar"]),
            sub="Saldo a pagar",
            classe="folha", icone=svg_icon("dollar", cor=C["folha"]),
            pill_texto="pendente", pill_classe="sol",
            titulo=fmt_brl(kpis["a_pagar"]),
        ), unsafe_allow_html=True)
        _botao_detalhe("a_pagar", "kpi_det_apagar")

    with _row1[3]:
        _nv30 = kpis["n_a_vencer_30d"]
        st.markdown(kpi_card(
            fmt_brl_curto(kpis["a_vencer_30d"]),
            sub="A vencer em até 30 dias",
            classe="sol", icone=svg_icon("calendar", cor=C["sol_texto"]),
            pill_texto=(f"{_nv30} contrato{'s' if _nv30 != 1 else ''}" if _nv30 else "nenhum"),
            pill_classe="sol",
            titulo=fmt_brl(kpis["a_vencer_30d"]),
        ), unsafe_allow_html=True)
        _botao_detalhe("a_vencer", "kpi_det_avencer")

    _row2 = st.columns(4)
    with _row2[0]:
        st.markdown(kpi_card(
            fmt_brl_curto(kpis["em_gargalo"]),
            sub="Em gargalo · aguardando",
            classe="sol", icone=svg_icon("clock", cor=C["sol_texto"]),
            pill_texto="atenção", pill_classe="sol",
            titulo=fmt_brl(kpis["em_gargalo"]),
        ), unsafe_allow_html=True)
        _botao_detalhe("gargalo", "kpi_det_gargalo")

    with _row2[1]:
        _venc = kpis["vencidos"]
        _cor_venc = C["urucum"] if _venc > 0 else C["folha"]
        st.markdown(kpi_card(
            str(_venc),
            sub="Contratos vencidos",
            classe="urucum" if _venc > 0 else "folha", icone=svg_icon("alert_tri", cor=_cor_venc),
            pill_texto="crítico" if _venc > 0 else "ok",
            pill_classe="urucum" if _venc > 0 else "folha",
        ), unsafe_allow_html=True)
        _botao_detalhe("vencidos", "kpi_det_vencidos")

    with _row2[2]:
        st.markdown(kpi_card(
            f"{kpis['perc_execucao']:.1f}%",
            sub=f"{kpis['fornecedores']} fornecedores ativos",
            classe="rio", icone=svg_icon("trend_up", cor=C["rio"]),
        ), unsafe_allow_html=True)

    # Barra de progresso da execução orçamentária
    pct = min(kpis["perc_execucao"], 100)
    st.markdown(f"""
<div class="maz-display" style="margin: 12px 0 4px 0; font-size:0.7rem; color:{C['ink_soft']}; letter-spacing:0.1em; text-transform:uppercase;">
    Execução Orçamentária Global — {pct:.1f}% concluído
</div>
<div class="progress-bar-container">
    <div class="progress-bar-fill" style="width:{pct}%;"></div>
</div>
""", unsafe_allow_html=True)


    # --------------------------------------------------------------------------- #
# SEÇÃO — PRAZOS DE CONTRATOS (visível para todos os papéis)                  #
# --------------------------------------------------------------------------- #

def _secao_prazos():
    secao_titulo("Prazos de Contratos", icone="calendar")

    if "termino_contrato" not in df_compras.columns:
        st.caption("Coluna de término do contrato não encontrada na planilha.")
    else:
        with st.expander("🔍 Ver contratos por prazo de vencimento (filtrar e listar)", expanded=False):
            _MESES_PT = {
                1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
                7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
            }

            def _rotulo_mes(periodo: str) -> str:
                try:
                    ano, mes = periodo.split("-")
                    return f"{_MESES_PT[int(mes)]} {ano}"
                except Exception:
                    return periodo

            col_faixa, col_mes = st.columns(2)
            with col_faixa:
                opcoes_faixa = {
                    f"{dh.EMOJI_PRAZO[k]} {dh.LABEL_PRAZO[k]}": k
                    for k in [dh.PRAZO_VENCIDO, dh.PRAZO_URGENTE, dh.PRAZO_ATENCAO, dh.PRAZO_TRANQUILO, dh.PRAZO_SEM_DATA]
                }
                sel_faixa_label = st.multiselect(
                    "Faixa de urgência",
                    options=list(opcoes_faixa.keys()),
                    default=[],
                    placeholder="Todas as faixas",
                )
                sel_faixas = [opcoes_faixa[l] for l in sel_faixa_label]

            with col_mes:
                meses_disponiveis = sorted(
                    [m for m in df_compras["mes_vencimento"].dropna().unique().tolist() if m]
                )
                opcoes_mes = {_rotulo_mes(m): m for m in meses_disponiveis}
                sel_mes_label = st.selectbox(
                    "Mês de vencimento",
                    options=["Todos os meses"] + list(opcoes_mes.keys()),
                )
                sel_mes = opcoes_mes.get(sel_mes_label)

            df_prazos = df_compras.copy()
            if sel_faixas:
                df_prazos = df_prazos[df_prazos["prazo_status"].isin(sel_faixas)]
            if sel_mes:
                df_prazos = df_prazos[df_prazos["mes_vencimento"] == sel_mes]

            # Ordena por urgência: vencidos primeiro, depois por proximidade da data
            _ordem_urgencia = {dh.PRAZO_VENCIDO: 0, dh.PRAZO_URGENTE: 1, dh.PRAZO_ATENCAO: 2, dh.PRAZO_TRANQUILO: 3, dh.PRAZO_SEM_DATA: 4}
            df_prazos = df_prazos.assign(_ordem=df_prazos["prazo_status"].map(_ordem_urgencia))
            df_prazos = df_prazos.sort_values(["_ordem", "dias_para_vencer"], na_position="last")

            st.caption(f"**{len(df_prazos)}** contrato(s) encontrados")

            if df_prazos.empty:
                estado_vazio("Nenhum contrato encontrado com os critérios de prazo selecionados.")
            else:
                _cores_prazo_ativo = dh.cores_prazo(TEMA_ATUAL)
                for _, linha in df_prazos.iterrows():
                    _ps = str(linha.get("prazo_status", "sem_data"))
                    if _ps not in _cores_prazo_ativo:
                        _ps = "sem_data"
                    _cor = _cores_prazo_ativo[_ps]
                    _dias = linha.get("dias_para_vencer")
                    if pd.notna(_dias):
                        _dias = int(_dias)
                        _dias_txt = f"vence em {_dias} dia(s)" if _dias >= 0 else f"vencido há {abs(_dias)} dia(s)"
                    else:
                        _dias_txt = "sem data de término"

                    _ic_prazo = svg_icon(_ICON_POR_PRAZO.get(_ps, "dash"), tamanho=14, cor=_cor)
                    st.markdown(
                        f"""
                    <div style="display:flex;align-items:center;gap:12px;background:{C['surface']};
                                border:1px solid {C['line']};border-left:4px solid {_cor};
                                border-radius:14px;padding:12px 18px;margin-bottom:8px;
                                box-shadow:{C['card_shadow']};">
                        <div style="flex:1;">
                            <span style="font-weight:700;color:{C['ink']};font-size:0.9rem;">
                                {html.escape(_val_txt(linha.get('fornecedor')) or '—')}
                            </span>
                            <span style="color:{C['ink_soft']};font-size:0.76rem;margin-left:8px;">
                                {html.escape(_val_txt(linha.get('descritivo')) or '—')}
                            </span>
                        </div>
                        <div style="color:{C['ink_soft']};font-size:0.78rem;white-space:nowrap;">
                            {_fmt(linha.get('termino_contrato'), 'data')}
                        </div>
                        <div style="display:flex;align-items:center;gap:6px;color:{_cor};font-weight:700;font-size:0.78rem;white-space:nowrap;">
                            {_ic_prazo} {html.escape(_dias_txt)}
                        </div>
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )


# --------------------------------------------------------------------------- #
# SEÇÃO 2 — PANORAMA GERAL (2 gráficos lado a lado)                            #
# --------------------------------------------------------------------------- #

def _secao_panorama():
    secao_titulo("Panorama Geral", icone="grid")

    col_esq, col_dir = st.columns([1.1, 0.9])

    # --- Gráfico 1: Distribuição por Situação do Fluxo (donut chart) ---
    with col_esq, st.container(border=True, key="panel_donut"):
        if tem_colunas(df_pag, "status", "valor"):
            contagem_status = df_pag.groupby("status")["valor"].sum().reset_index()
            contagem_status.columns = ["Status", "Valor"]
            contagem_status = contagem_status[contagem_status["Valor"] > 0]
            contagem_status["Grupo"] = contagem_status["Status"].map(
                lambda s: dh.STATUS_PARA_GRUPO.get(s, "alerta")
            )
            # Cor baseada no grupo de saúde
            cores_mapa = contagem_status["Grupo"].map(dh.cores_grupo(TEMA_ATUAL)).tolist()

            fig_donut = px.pie(
                contagem_status,
                values="Valor",
                names="Status",
                hole=0.58,
                color_discrete_sequence=cores_mapa,
                title="Distribuição Financeira por Status",
            )
            fig_donut.update_traces(
                textposition="outside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}<extra></extra>",
            )
            fig_donut.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color=C['ink'],
                showlegend=False,
                title_font_size=13,
                title_font_color=C['ink_soft'],
                margin=dict(t=40, b=10, l=10, r=10),
                annotations=[dict(
                    text=f"<b>{fmt_brl(kpis['a_pagar'])}</b><br><span style='font-size:10px'>a pagar</span>",
                    x=0.5, y=0.5, font_size=12, showarrow=False, font_color=C['folha']
                )],
            )
            st.plotly_chart(fig_donut, use_container_width=True)

    # --- Gráfico 2: Top 10 Fornecedores por Valor Contratado (barras horizontais) ---
    with col_dir, st.container(border=True, key="panel_top10"):
        if tem_colunas(df_compras, "fornecedor", "valor"):
            top_fornecedores = (
                df_compras.groupby("fornecedor")["valor"]
                .sum()
                .sort_values(ascending=True)
                .tail(10)
                .reset_index()
            )
            top_fornecedores.columns = ["Fornecedor", "Valor"]

            fig_bar = px.bar(
                top_fornecedores,
                x="Valor",
                y="Fornecedor",
                orientation="h",
                title="Top 10 Fornecedores · Valor Contratado",
                color="Valor",
                color_continuous_scale=[[0, C['bar_scale'][0]], [0.5, C['bar_scale'][1]], [1, C['bar_scale'][2]]],
                text="Valor",
            )
            fig_bar.update_traces(
                texttemplate="R$ %{x:,.0f}",
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>",
            )
            fig_bar.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color=C['ink'],
                title_font_size=13,
                title_font_color=C['ink_soft'],
                coloraxis_showscale=False,
                xaxis=dict(showgrid=False, visible=False),
                yaxis=dict(showgrid=False),
                margin=dict(t=40, b=10, l=10, r=80),
            )
            st.plotly_chart(fig_bar, use_container_width=True)


# --------------------------------------------------------------------------- #
# SEÇÃO 3 — ANÁLISE DE GARGALOS (foco em tomada de decisão)                    #
# --------------------------------------------------------------------------- #

def _secao_gargalos():
    secao_titulo("Análise de Gargalos · Pagamentos Bloqueados", icone="alert_tri")

    # Status de alerta e em andamento são os gargalos a monitorar
    status_gargalo_lista = dh.STATUS_GRUPOS["alerta"] + dh.STATUS_GRUPOS["em_andamento"]
    df_gargalo = (
        df_pag[df_pag["status"].isin(status_gargalo_lista)]
        if "status" in df_pag.columns
        else pd.DataFrame()
    )

    if df_gargalo.empty or not tem_colunas(df_gargalo, "status", "valor"):
        st.success("✅ Nenhum pagamento em situação de gargalo no momento.")
    else:
        col_g1, col_g2 = st.columns([1.2, 0.8])

        with col_g1, st.container(border=True, key="panel_gargalo_bar"):
            gargalo_agrupado = (
                df_gargalo.groupby("status")["valor"]
                .sum()
                .sort_values(ascending=False)
                .reset_index()
            )
            gargalo_agrupado.columns = ["Status", "Valor"]
            gargalo_agrupado["Grupo"] = gargalo_agrupado["Status"].map(
                lambda s: dh.STATUS_PARA_GRUPO.get(s, "alerta")
            )

            fig_gargalo = px.bar(
                gargalo_agrupado,
                x="Status",
                y="Valor",
                title="Valor Parado por Fase de Gargalo",
                color="Grupo",
                color_discrete_map=dh.cores_grupo(TEMA_ATUAL),
                text="Valor",
            )
            fig_gargalo.update_traces(
                texttemplate="R$ %{y:,.0f}",
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>R$ %{y:,.2f}<extra></extra>",
            )
            fig_gargalo.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color=C['ink'],
                title_font_size=13,
                title_font_color=C['ink_soft'],
                showlegend=False,
                xaxis=dict(showgrid=False, tickangle=-20),
                yaxis=dict(showgrid=True, gridcolor=C['line'], visible=False),
                margin=dict(t=50, b=60, l=10, r=10),
            )
            st.plotly_chart(fig_gargalo, use_container_width=True)

        with col_g2, st.container(border=True, key="panel_gargalo_lista"):
            if tem_colunas(df_gargalo, "fornecedor", "valor"):
                st.markdown("**Fornecedores com maior valor bloqueado**")
                gargalo_forn = (
                    df_gargalo.groupby("fornecedor")["valor"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(8)
                    .reset_index()
                )
                gargalo_forn.columns = ["Fornecedor", "Valor Bloqueado"]
                gargalo_forn["Valor Bloqueado"] = gargalo_forn["Valor Bloqueado"].apply(fmt_brl)
                st.dataframe(gargalo_forn, use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
# SEÇÃO 4 — FLUXO TEMPORAL DE PAGAMENTOS                                       #
# --------------------------------------------------------------------------- #

def _secao_fluxo():
    secao_titulo("Fluxo Temporal de Pagamentos", icone="calendar")

    if tem_colunas(df_pag, "mes_pgto", "valor", "status"):
        df_tempo = df_pag.dropna(subset=["mes_pgto"])

        if not df_tempo.empty:
            with st.container(border=True, key="panel_fluxo_tempo"):
                df_tempo["Situacao"] = df_tempo["status"].apply(
                    lambda s: "Realizado" if s == "Pago" else "Previsto"
                )
                fluxo = (
                    df_tempo.groupby(["mes_pgto", "Situacao"])["valor"]
                    .sum()
                    .reset_index()
                )
                fluxo.columns = ["Mês", "Situação", "Valor"]
                fluxo = fluxo.sort_values("Mês")

                fig_tempo = px.bar(
                    fluxo,
                    x="Mês",
                    y="Valor",
                    color="Situação",
                    barmode="group",
                    title="Pagamentos Realizados vs. Previstos por Mês",
                    color_discrete_map={"Realizado": C['folha'], "Previsto": C['sol']},
                    text="Valor",
                )
                fig_tempo.update_traces(
                    texttemplate="R$ %{y:,.0f}",
                    textposition="outside",
                    hovertemplate="<b>%{x}</b> · %{data.name}<br>R$ %{y:,.2f}<extra></extra>",
                )
                fig_tempo.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font_color=C['ink'],
                    title_font_size=13,
                    title_font_color=C['ink_soft'],
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor=C['line'], visible=False),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(t=60, b=40, l=10, r=10),
                )
                st.plotly_chart(fig_tempo, use_container_width=True)
        else:
            st.info("Não há datas de pagamento registradas para gerar o gráfico temporal.")
    else:
        st.info("Coluna 'Data pgto' não encontrada ou sem dados de pagamento.")


# --------------------------------------------------------------------------- #
# SEÇÃO 5 — DETALHAMENTO HIERÁRQUICO (Compras + Pagamentos expansíveis)        #
# O título e o corpo de renderização ficam em _secao_acompanhar() (mais abaixo);#
# aqui em nível de módulo ficam só os helpers e os diálogos de edição.         #
# --------------------------------------------------------------------------- #

# Cor do TEXTO do badge (versão com bom contraste sobre o fundo do card)
_COR_TEXTO_BADGE = {
    "concluido":    C["folha"],
    "em_andamento": C["rio_texto"],
    "alerta":       C["sol_texto"],
    "critico":      C["urucum"],
}


def _status_badge(status: str, grupo: str) -> str:
    """Retorna HTML do badge de status colorido, conforme o tema ativo."""
    cor = dh.cores_grupo(TEMA_ATUAL).get(grupo, C["ink_soft"])
    cor_txt = _COR_TEXTO_BADGE.get(grupo, C["ink_soft"])
    # status pode conter caracteres especiais vindos da planilha — escapar sempre
    status_safe = html.escape(str(status))
    return (
        f'<span class="maz-display" style="background:{cor}1A;border:1px solid {cor}99;color:{cor_txt};'
        f'font-size:0.62rem;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;'
        f'padding:3px 10px;border-radius:999px;white-space:nowrap;">'
        f'{status_safe}</span>'
    )


_pode_editar = _papel_usuario in (dh.PAPEL_OWNER, dh.PAPEL_ADMIN)
_escrita_ok  = "gcp_service_account" in st.secrets


# --------------------------------------------------------------------------- #
# DIÁLOGOS DE EDIÇÃO (modal central, fundo escurecido — st.dialog nativo)      #
# --------------------------------------------------------------------------- #

def _fechar_dialog_e_atualizar(msg: str = "", avisos: list[str] | None = None) -> None:
    dh.carregar_do_sheets.clear()
    st.session_state.pop("edit_target", None)
    if msg:
        st.session_state["flash_ok"] = msg
    if avisos:
        st.session_state["flash_avisos"] = avisos
    st.rerun()


@st.dialog("Editar Pedido de Compra")
def _dialog_pedido(gi: int, atual) -> None:
    _opts = dh.STATUS_TODOS
    _cur = _val_txt(atual.get("status"))
    _idx = _opts.index(_cur) if _cur in _opts else 0

    col1, col2 = st.columns(2)
    with col1:
        f_fornecedor = st.text_input("Fornecedor *", value=_val_txt(atual.get("fornecedor")))
        f_req        = st.text_input("Req. MXM", value=_val_txt(atual.get("req_mxm")))
        f_valor      = st.number_input("Valor total (R$) *", min_value=0.0, step=100.0, format="%.2f", value=_val_num(atual.get("valor")))
        f_status     = st.selectbox("Status", options=_opts, index=_idx)
    with col2:
        f_descritivo = st.text_input("Descritivo", value=_val_txt(atual.get("descritivo")))
        f_termino    = st.date_input("Término do contrato", value=_val_date(atual.get("termino_contrato")))
        f_link       = st.text_input("Link do contrato", value=_val_txt(atual.get("link_contrato")))
    f_obs = st.text_area("Observações", value=_val_txt(atual.get("observacoes")), height=80)

    c_salvar, c_cancelar = st.columns(2)
    with c_salvar:
        if st.button("💾 Salvar", use_container_width=True, type="primary"):
            if not f_fornecedor.strip() or f_valor <= 0:
                st.error("Fornecedor e Valor são obrigatórios.")
            else:
                try:
                    dh.atualizar_pedido(sheets_url_input, nome_aba_input, gi, {
                        "fornecedor": f_fornecedor, "req_mxm": f_req, "valor": f_valor,
                        "descritivo": f_descritivo, "status": f_status,
                        "termino_contrato": f_termino, "link_contrato": f_link,
                        "observacoes": f_obs,
                    })
                    _fechar_dialog_e_atualizar("Pedido atualizado.")
                except Exception as e:
                    st.error(f"Erro ao salvar: `{e}`")
    with c_cancelar:
        if st.button("Cancelar", use_container_width=True):
            _fechar_dialog_e_atualizar()

    st.divider()
    confirmar = st.checkbox("Confirmo excluir este pedido e **todas** as suas parcelas")
    if st.button("🗑️ Excluir pedido", use_container_width=True, disabled=not confirmar):
        try:
            dh.excluir_pedido(sheets_url_input, nome_aba_input, gi)
            _fechar_dialog_e_atualizar("Pedido excluído.")
        except Exception as e:
            st.error(f"Erro ao excluir: `{e}`")


@st.dialog("Editar Parcela")
def _dialog_parcela(gi: int, pi: int, atual) -> None:
    _opts = dh.STATUS_TODOS
    _cur = _val_txt(atual.get("status"))
    _idx = _opts.index(_cur) if _cur in _opts else 0

    col1, col2 = st.columns(2)
    with col1:
        f_valor  = st.number_input("Valor da parcela (R$) *", min_value=0.0, step=100.0, format="%.2f", value=_val_num(atual.get("valor")))
        f_status = st.selectbox("Status", options=_opts, index=_idx)
    with col2:
        f_doc  = st.text_input("Doc. Fiscal (nº da NF)", value=_val_txt(atual.get("doc_fiscal")))
        f_data = st.date_input("Data de pagamento", value=_val_date(atual.get("data_pgto")))

    c_salvar, c_cancelar = st.columns(2)
    with c_salvar:
        if st.button("💾 Salvar", use_container_width=True, type="primary"):
            if f_valor <= 0:
                st.error("O valor da parcela é obrigatório.")
            else:
                try:
                    dh.atualizar_parcela(sheets_url_input, nome_aba_input, gi, pi, {
                        "valor": f_valor, "status": f_status,
                        "doc_fiscal": f_doc, "data_pgto": f_data,
                    })
                    _fechar_dialog_e_atualizar("Parcela atualizada.")
                except Exception as e:
                    st.error(f"Erro ao salvar: `{e}`")
    with c_cancelar:
        if st.button("Cancelar", use_container_width=True):
            _fechar_dialog_e_atualizar()

    st.divider()
    if st.button("🗑️ Excluir parcela", use_container_width=True):
        try:
            dh.excluir_parcela(sheets_url_input, nome_aba_input, gi, pi)
            _fechar_dialog_e_atualizar("Parcela excluída.")
        except Exception as e:
            st.error(f"Erro ao excluir: `{e}`")


@st.dialog("Adicionar Parcela")
def _dialog_nova_parcela(gi: int) -> None:
    col1, col2 = st.columns(2)
    with col1:
        f_valor  = st.number_input("Valor da parcela (R$) *", min_value=0.0, step=100.0, format="%.2f")
        f_status = st.selectbox("Status", options=dh.STATUS_TODOS)
    with col2:
        f_doc  = st.text_input("Doc. Fiscal (nº da NF)")
        f_data = st.date_input("Data de pagamento", value=None)

    c_add, c_cancelar = st.columns(2)
    with c_add:
        if st.button("💾 Adicionar", use_container_width=True, type="primary"):
            if f_valor <= 0:
                st.error("O valor da parcela é obrigatório.")
            else:
                try:
                    avisos = dh.adicionar_parcela(sheets_url_input, nome_aba_input, gi, {
                        "valor": f_valor, "status": f_status,
                        "doc_fiscal": f_doc, "data_pgto": f_data,
                    })
                    _fechar_dialog_e_atualizar("Parcela adicionada.", avisos)
                except Exception as e:
                    st.error(f"Erro ao adicionar: `{e}`")
    with c_cancelar:
        if st.button("Cancelar", use_container_width=True):
            _fechar_dialog_e_atualizar()


def _mostrar_flash():
    """Mensagens de sucesso/aviso após ações — mostradas em qualquer página,
    já que a ação pode ter sido feita numa página diferente da atual."""
    _flash = st.session_state.pop("flash_ok", None)
    if _flash:
        st.success(f"✅ {_flash}")
    # Avisos não-críticos (ex: falha ao copiar formatação visual) — não impedem
    # o lançamento, mas precisam aparecer pra gente conseguir diagnosticar.
    _flash_avisos = st.session_state.pop("flash_avisos", None)
    if _flash_avisos:
        for _av in _flash_avisos:
            st.warning(f"⚠️ {_av}")


def _secao_acompanhar():
    secao_titulo("Acompanhar Pedidos de Compra", icone="file_text")

    # ---- Busca: caixas separadas, uma por campo ----
    st.markdown(
        "<span class='maz-display' style='font-size:0.72rem;font-weight:700;"
        f"letter-spacing:0.14em;text-transform:uppercase;color:{C['ink_soft']};'>Buscar por</span>",
        unsafe_allow_html=True,
    )
    def _limpar_busca_callback() -> None:
        # Roda ANTES do script recarregar os widgets — só assim dá pra alterar
        # o valor de um text_input pelo session_state sem o Streamlit reclamar
        # ("cannot be modified after the widget is instantiated").
        for _k in ("q_forn", "q_req", "q_serv", "q_nf"):
            st.session_state[_k] = ""


    bc1, bc2, bc3, bc4, bc5 = st.columns([1, 1, 1, 1, 0.5])
    q_forn = bc1.text_input("Fornecedor", placeholder="Fornecedor", label_visibility="collapsed", key="q_forn").strip().lower()
    q_req  = bc2.text_input("Requisição", placeholder="Requisição", label_visibility="collapsed", key="q_req").strip().lower()
    q_serv = bc3.text_input("Serviço",    placeholder="Serviço",    label_visibility="collapsed", key="q_serv").strip().lower()
    q_nf   = bc4.text_input("Nº da NF",   placeholder="Nº da NF",   label_visibility="collapsed", key="q_nf").strip().lower()
    with bc5:
        st.button("🧹 Limpar", use_container_width=True, key="btn_limpar_busca", on_click=_limpar_busca_callback)

    # ---- Abas: Em andamento | Quitados ----
    aba_ativa = st.radio(
        "",
        options=["🔄  Em Andamento", "✅  Quitados"],
        horizontal=True,
        label_visibility="collapsed",
    )
    mostrar_quitados = aba_ativa.startswith("✅")


    def _eh_quitado(compra) -> bool:
        status = str(compra.get("status", ""))
        grupo  = str(compra.get("grupo_status", ""))
        return status in dh.STATUS_QUITADO or grupo == "concluido"


    def _passa_busca(compra, pags) -> bool:
        """Cada caixa preenchida filtra o seu campo (lógica E entre as caixas)."""
        if q_forn and q_forn not in str(compra.get("fornecedor", "")).lower():
            return False
        if q_req:
            reqs = [str(compra.get("req_mxm", ""))] + [str(p.get("req_mxm", "")) for _, p in pags.iterrows()]
            if q_req not in " ".join(reqs).lower():
                return False
        if q_serv:
            servs = [str(compra.get("descritivo", ""))] + [str(p.get("descritivo", "")) for _, p in pags.iterrows()]
            if q_serv not in " ".join(servs).lower():
                return False
        if q_nf:
            docs = " ".join(str(p.get("doc_fiscal", "")) for _, p in pags.iterrows())
            if q_nf not in docs.lower():
                return False
        return True


    # Hierarquia sobre a base COMPLETA — o índice (gi) é a posição absoluta do
    # grupo na planilha, usada para localizar a linha exata na edição/exclusão.
    hier_full = dh.agrupar_hierarquia(df)

    _algum_filtro = any((q_forn, q_req, q_serv, q_nf))

    itens = []
    for gi, (compra, df_pags) in enumerate(hier_full):
        if _eh_quitado(compra) != mostrar_quitados:
            continue
        if not _passa_busca(compra, df_pags):
            continue
        itens.append((gi, compra, df_pags))

    # Abre o diálogo de edição, se houver um alvo selecionado
    _alvo = st.session_state.get("edit_target")
    if _alvo and _pode_editar and _escrita_ok:
        _tipo, _gi = _alvo[0], _alvo[1]
        if _gi < len(hier_full):
            _compra_a, _pags_a = hier_full[_gi]
            if _tipo == "pedido":
                _dialog_pedido(_gi, _compra_a)
            elif _tipo == "parcela":
                _pi = _alvo[2]
                if _pi < len(_pags_a):
                    _dialog_parcela(_gi, _pi, _pags_a.iloc[_pi])
                else:
                    st.session_state.pop("edit_target", None)
            elif _tipo == "nova_parcela":
                _dialog_nova_parcela(_gi)
        else:
            st.session_state.pop("edit_target", None)

    # Indicador de resultado
    st.caption(
        f"{'✅ Contratos quitados' if mostrar_quitados else '🔄 Contratos em andamento'}: "
        f"**{len(itens)}**" + (" · filtro ativo" if _algum_filtro else "")
    )

    if not itens:
        estado_vazio("Nenhum contrato encontrado com os critérios atuais.")
    else:
        for gi, compra, df_pags in itens:

            # --- Dados principais da Compra ---
            fornecedor  = _fmt(compra.get("fornecedor"))
            valor       = _fmt(compra.get("valor"), "valor")
            descritivo  = _fmt(compra.get("descritivo"))
            termino     = _fmt(compra.get("termino_contrato"), "data")
            observacoes = _fmt(compra.get("observacoes"))

            # Requisição: mostra o número (col C) ou um aviso quando ausente
            req_val = _val_txt(compra.get("req_mxm"))
            if req_val:
                req_html = (
                    f"<span style=\"color:{C['ink_soft']};font-size:0.74rem;margin-left:10px;"
                    f"letter-spacing:0.03em;\">Req. {html.escape(req_val)}</span>"
                )
            else:
                req_html = (
                    f"<span style=\"background:{C['sol']}1A;border:1px solid {C['sol']}99;"
                    f"color:{C['sol_texto']};font-size:0.6rem;font-weight:700;letter-spacing:0.04em;"
                    "text-transform:uppercase;padding:2px 8px;border-radius:999px;"
                    "margin-left:10px;\">⚠ sem requisição</span>"
                )

            status_raw = str(compra.get("status", ""))
            status     = "Sem status" if status_raw in ("nan", "", "None") else status_raw
            grupo      = str(compra.get("grupo_status", "alerta"))
            if grupo in ("nan", "", "None"):
                grupo = "alerta"

            n_parcelas   = len(df_pags) if not df_pags.empty else 0
            label_expand = f"  ({n_parcelas} pagamento{'s' if n_parcelas != 1 else ''})" if n_parcelas > 0 else ""

            detalhes_parts = [descritivo] if descritivo != "—" else []
            if observacoes != "—":
                detalhes_parts.append(observacoes)
            detalhes_html = " &nbsp;·&nbsp; ".join(detalhes_parts)

            badge = _status_badge(status, grupo)
            cor_spine = dh.cores_grupo(TEMA_ATUAL).get(grupo, C["ink_soft"])

            # --- Selo de prazo: código/link do contrato + término + urgência ---
            prazo_status = str(compra.get("prazo_status", "sem_data"))
            _cores_prazo_ativo2 = dh.cores_prazo(TEMA_ATUAL)
            if prazo_status not in _cores_prazo_ativo2:
                prazo_status = "sem_data"
            cor_prazo   = _cores_prazo_ativo2[prazo_status]
            icone_prazo = svg_icon(_ICON_POR_PRAZO.get(prazo_status, "dash"), tamanho=13, cor=cor_prazo)
            label_prazo = dh.LABEL_PRAZO[prazo_status]

            link_val = _val_txt(compra.get("link_contrato"))
            partes_prazo = []
            if link_val:
                if link_val.lower().startswith("http"):
                    partes_prazo.append(
                        f'<a href="{html.escape(link_val)}" target="_blank" '
                        f'style="color:inherit;text-decoration:underline;display:inline-flex;'
                        f'align-items:center;gap:4px;">{svg_icon("link", tamanho=13, cor=cor_prazo)} Contrato</a>'
                    )
                else:
                    partes_prazo.append(f'{svg_icon("file_text", tamanho=13, cor=cor_prazo)} {html.escape(link_val)}')
            if termino != "—":
                partes_prazo.append(f'{svg_icon("calendar", tamanho=13, cor=cor_prazo)} Término: {termino}')
            partes_prazo.append(f"{icone_prazo} {label_prazo}")

            prazo_chip_html = (
                f'<span style="display:inline-flex;align-items:center;flex-wrap:wrap;'
                f'gap:6px;background:{cor_prazo}14;border:1px solid {cor_prazo}66;'
                f'color:{cor_prazo};font-size:0.7rem;font-weight:600;padding:4px 10px;'
                f'border-radius:6px;margin-top:8px;">'
                + " &nbsp;·&nbsp; ".join(partes_prazo) +
                "</span>"
            )

            card_html = f"""
            <div style="
                background:{C['surface']};border:1px solid {C['line']};border-radius:14px;
                margin-bottom:10px;font-family:sans-serif;display:flex;overflow:hidden;
                box-shadow:{C['card_shadow']};
            ">
                <div style="width:5px;flex-shrink:0;background:{cor_spine};"></div>
                <div style="flex:1;padding:16px 20px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                        <div>
                            <span style="font-weight:700;color:{C['ink']};font-size:0.96rem;">{fornecedor}</span>
                            {req_html}
                        </div>
                        <div style="display:flex;align-items:center;gap:12px;">
                            <span style="color:{C['ink']};font-weight:700;font-size:1rem;font-variant-numeric:tabular-nums;">{valor}</span>
                            {badge}
                        </div>
                    </div>
                    {f'<div style="color:{C["ink_soft"]};font-size:0.78rem;margin-top:8px;">{detalhes_html}</div>' if detalhes_html else ""}
                    <div>{prazo_chip_html}</div>
                </div>
            </div>
        """

            # Card + botão de editar pedido (só Owner/Admin com escrita habilitada)
            if _pode_editar and _escrita_ok:
                c_card, c_edit = st.columns([24, 1])
                c_card.html(card_html)
                if c_edit.button("✏️", key=f"edped_{gi}", help="Editar pedido de compra"):
                    st.session_state["edit_target"] = ("pedido", gi)
                    st.rerun()
            else:
                st.html(card_html)

            # --- Expansor de pagamentos/parcelas ---
            with st.expander(f"＋ Ver pagamentos / parcelas{label_expand}", expanded=False):
                if n_parcelas > 0:
                    for pi in range(len(df_pags)):
                        prow = df_pags.iloc[pi]
                        p_grupo = str(prow.get("grupo_status", "alerta"))
                        p_desc  = _val_txt(prow.get("descritivo")) or "—"
                        p_stat  = _val_txt(prow.get("status")) or "Sem status"
                        cols = st.columns([3, 2, 2, 2, 1]) if (_pode_editar and _escrita_ok) else st.columns([3, 2, 2, 3])
                        _ic_grupo = svg_icon(_ICON_POR_GRUPO.get(p_grupo, "dash"), tamanho=13, cor=dh.cores_grupo(TEMA_ATUAL).get(p_grupo, C["ink_soft"]))
                        cols[0].markdown(f"**{p_desc}**  \n{_ic_grupo} <span style='font-size:0.75rem;color:{C['ink_soft']};'>{html.escape(p_stat)}</span>", unsafe_allow_html=True)
                        cols[1].markdown(f"<span style='font-size:0.85rem;'>{_fmt(prow.get('valor'), 'valor')}</span>", unsafe_allow_html=True)
                        cols[2].markdown(f"<span style='font-size:0.85rem;color:{C['ink_soft']};'>{_fmt(prow.get('data_pgto'), 'data')}</span>", unsafe_allow_html=True)
                        cols[3].markdown(f"<span style='font-size:0.85rem;color:{C['ink_soft']};'>NF {_val_txt(prow.get('doc_fiscal')) or '—'}</span>", unsafe_allow_html=True)
                        if _pode_editar and _escrita_ok:
                            if cols[4].button("✏️", key=f"edpar_{gi}_{pi}", help="Editar parcela"):
                                st.session_state["edit_target"] = ("parcela", gi, pi)
                                st.rerun()
                        st.markdown(f"<hr style='margin:4px 0;border:none;border-top:1px solid {C['line']};'>", unsafe_allow_html=True)
                else:
                    st.caption("Nenhuma parcela lançada para este pedido.")

                if _pode_editar and _escrita_ok:
                    if st.button("➕ Adicionar parcela", key=f"addpar_{gi}", use_container_width=True):
                        st.session_state["edit_target"] = ("nova_parcela", gi)
                        st.rerun()

    # Botão de exportação
    csv_export = df_filtrado.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        label="⬇️  Exportar dados (.csv)",
        data=csv_export,
        file_name="maz_pagamentos.csv",
        mime="text/csv",
    )


# --------------------------------------------------------------------------- #
# NAVEGAÇÃO MULTIPÁGINA — cada página é uma função; o menu vai para a sidebar   #
# --------------------------------------------------------------------------- #

def _pagina_painel():
    _secao_indicadores()
    _secao_panorama()
    _secao_gargalos()
    _secao_fluxo()


def _pagina_prazos():
    _secao_prazos()


def _pagina_contratos():
    _secao_acompanhar()


def _pagina_aprovacoes():
    """Owner revisa/aprova/rejeita as solicitações enviadas pelos Requisitantes."""
    secao_titulo("Aprovações Pendentes", icone="bell")
    if not sheets_url_input or "gcp_service_account" not in st.secrets:
        st.info(
            "🔒 As aprovações exigem a Service Account configurada nos Secrets "
            "(`gcp_service_account`).",
            icon="ℹ️",
        )
        return
    try:
        _solicitacoes = dh.listar_solicitacoes(sheets_url_input, apenas_status=dh.STATUS_APROVACAO_PENDENTE)
    except Exception as e:
        st.error(f"Não foi possível carregar as solicitações: `{e}`")
        return

    if not _solicitacoes:
        st.success("✅ Nenhuma solicitação pendente no momento.")
        return

    for _s in _solicitacoes:
        _c = _s["compra"]
        col_info, col_ver = st.columns([4, 1])
        with col_info:
            st.markdown(
                f"**{html.escape(str(_c.get('fornecedor', '—')))}** &nbsp;·&nbsp; "
                f"{html.escape(_fmt(_c.get('valor'), 'valor'))}  \n"
                f"<span style='color:{C['ink_soft']};font-size:0.76rem;'>"
                f"{html.escape(str(_s['solicitante_nome']))} · {html.escape(str(_s['data_solicitacao']))}</span>",
                unsafe_allow_html=True,
            )
        with col_ver:
            if st.button("👁️ Revisar", key=f"revisar_{_s['idx']}", use_container_width=True):
                _dialog_revisar_solicitacao(_s)


def _pagina_configuracoes():
    """Fonte de dados, gestão de acessos e log de alterações (Owner/Admin)."""
    secao_titulo("Configurações", icone="dash")

    # --- Fonte de dados (Google Sheets) — Owner e Admin ---
    st.markdown("**Fonte de dados**")
    novo_url = st.text_input(
        "🔗 Link do Google Sheets",
        value=sheets_url_input,
        placeholder="https://docs.google.com/spreadsheets/d/...",
    )
    nova_aba = st.text_input(
        "📑 Nome da aba",
        value=nome_aba_input,
        placeholder="Ex: Pagamentos 2025",
        help="Nome exato da aba (case sensitive).",
    )
    if st.button("💾 Salvar fonte de dados"):
        _salvar_config_persistente(novo_url, nova_aba)
        st.session_state["flash_ok"] = "Configurações salvas por 5 dias."
        st.rerun()

    # --- Gerenciar Acessos — visível APENAS para o Owner ---
    if _papel_usuario == dh.PAPEL_OWNER:
        st.divider()
        secao_titulo("Gerenciar Acessos", icone="user")
        st.caption("Cadastre administradores, visualizadores e requisitantes.")

        with st.form("form_novo_usuario", clear_on_submit=True):
            novo_login = st.text_input("Login do novo usuário")
            novo_nome  = st.text_input("Nome de exibição")
            nova_senha = st.text_input("Senha", type="password")
            novo_papel = st.selectbox(
                "Papel",
                options=[dh.PAPEL_ADMIN, dh.PAPEL_VIEWER, dh.PAPEL_REQUISITANTE],
                format_func=lambda p: _PAPEL_DESCRICAO.get(p, p),
            )
            cadastrar = st.form_submit_button("➕ Cadastrar")

        if cadastrar:
            if not novo_login.strip() or not nova_senha:
                st.error("Login e senha são obrigatórios.")
            elif novo_login.strip() == _OWNER_LOGIN:
                st.error("Este login já é o do Owner.")
            else:
                dh.adicionar_usuario(novo_login, nova_senha, novo_papel, novo_nome)
                st.session_state["flash_ok"] = f"Usuário {novo_login} cadastrado como {_PAPEL_LABEL.get(novo_papel, novo_papel)}."
                st.rerun()

        st.caption("Usuários cadastrados:")
        usuarios_cadastrados = dh.carregar_usuarios()
        if not usuarios_cadastrados:
            st.caption("Nenhum administrador ou viewer cadastrado ainda.")
        else:
            for login_u, dados_u in usuarios_cadastrados.items():
                col_info, col_del = st.columns([4, 1])
                with col_info:
                    papel_u = dados_u.get("papel", dh.PAPEL_VIEWER)
                    st.markdown(
                        f"**{dados_u.get('nome', login_u)}**  \n"
                        f"<span style='color:{C['ink_soft']};font-size:0.72rem;'>{login_u} · {_PAPEL_LABEL.get(papel_u, papel_u)}</span>",
                        unsafe_allow_html=True,
                    )
                with col_del:
                    if st.button("🗑️", key=f"del_{login_u}", help=f"Remover {login_u}"):
                        dh.remover_usuario(login_u)
                        st.rerun()

    # --- Log de Alterações — Owner e Admin ---
    st.divider()
    secao_titulo("Log de Alterações", icone="file_text")
    entradas_log = dh.carregar_log()
    if not entradas_log:
        st.caption("Nenhuma alteração registrada ainda.\nO dashboard verifica mudanças a cada 1 hora automaticamente.")
    else:
        for entrada in reversed(entradas_log[-20:]):
            horario_str = datetime.fromisoformat(entrada["horario"]).strftime("%d/%m/%Y %H:%M")
            total = entrada.get("total", len(entrada.get("alteracoes", [])))
            st.markdown(f"**🕐 {horario_str}** — {total} alteração{'ões' if total != 1 else ''}")
            for alt in entrada.get("alteracoes", []):
                linha   = alt.get("linha", "?")
                forn    = alt.get("fornecedor", "—")
                tipo    = alt.get("tipo", "")
                campo   = alt.get("campo", "—")
                de_val  = alt.get("de", "—")
                para    = alt.get("para", "—")
                if campo == "(linha)":
                    if para == "adicionada":
                        st.caption(f"  ➕ Linha {linha} · {tipo} · {forn} — nova linha")
                    else:
                        st.caption(f"  ➖ Linha {linha} · {tipo} · {forn} — removida")
                else:
                    _NOMES_CAMPOS = {
                        "status": "Status", "valor": "Valor", "fornecedor": "Fornecedor",
                        "req_mxm": "Req. MXM", "data_pgto": "Data Pgto",
                        "doc_fiscal": "Doc. Fiscal", "termino_contrato": "Término",
                        "observacoes": "Observações", "tipo": "Tipo",
                    }
                    campo_label = _NOMES_CAMPOS.get(campo, campo)
                    st.caption(f"  ✏️ Linha {linha} · {forn} · **{campo_label}**: {de_val} → {para}")
            st.divider()


_paginas_menu = [
    st.Page(_pagina_painel,    title="Painel Gerencial",     icon=":material/dashboard:", default=True),
    st.Page(_pagina_prazos,    title="Prazos de Contratos",  icon=":material/event:"),
    st.Page(_pagina_contratos, title="Contratos",            icon=":material/description:"),
]
_estrutura_nav = {"Menu": _paginas_menu}

# Fluxo: Novo Lançamento (quem lança/solicita) + Aprovações (só Owner)
_fluxo = []
if _papel_usuario in (dh.PAPEL_OWNER, dh.PAPEL_ADMIN, dh.PAPEL_REQUISITANTE):
    _fluxo.append(st.Page(_pagina_lancamento, title="Novo Lançamento", icon=":material/add_circle:"))
if _papel_usuario == dh.PAPEL_OWNER:
    _titulo_aprov = f"Aprovações ({_n_pendentes_header})" if _n_pendentes_header else "Aprovações"
    _fluxo.append(st.Page(_pagina_aprovacoes, title=_titulo_aprov, icon=":material/inbox:"))
if _fluxo:
    _estrutura_nav["Fluxo"] = _fluxo

# Sistema: Configurações (Owner/Admin)
if _papel_usuario in (dh.PAPEL_OWNER, dh.PAPEL_ADMIN):
    _estrutura_nav["Sistema"] = [
        st.Page(_pagina_configuracoes, title="Configurações", icon=":material/settings:"),
    ]

_nav = st.navigation(_estrutura_nav)
_render_header(_nav.title)
_render_topo_contexto()
_mostrar_flash()
_nav.run()


# --------------------------------------------------------------------------- #
# RODAPÉ                                                                        #
# --------------------------------------------------------------------------- #

st.markdown('<div class="maz-trancado" style="margin-top:44px;height:5px;"></div>', unsafe_allow_html=True)

# Logo do IDG (mantenedora) — aparece no rodapé quando o arquivo existir em assets/
_logo_idg = _logo_data_uri("logo_idg.png")
_idg_html = (
    f'<img src="{_logo_idg}" alt="IDG — Instituto de Desenvolvimento e Gestão" '
    f'style="height:38px;width:auto;opacity:0.7;margin-bottom:10px;">'
    if _logo_idg else ""
)
st.markdown(f"""
<div style="
    padding-top: 16px;
    text-align: center;
    color: {C['ink_soft']};
    font-size: 0.72rem;
">
    {_idg_html}
    <div>MAZ | Museu das Amazônias · uma realização do IDG — Instituto de Desenvolvimento e Gestão</div>
    <div>Dashboard Gerencial de Pagamentos · Versão Beta 1.0</div>
</div>
""", unsafe_allow_html=True)
