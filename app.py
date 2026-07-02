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
# CSS GLOBAL — Identidade "Trançado das Amazônias"                              #
# Paleta da marca MAZ sobre papel de galeria:                                   #
#   #F6F1E7 papel | #4F6A1E folha | #E02838 urucum | #E8920A sol | #3E9489 rio #
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
:root {
    --paper:      #F6F1E7;
    --paper-deep: #EFE8D8;
    --surface:    #FCFAF4;
    --ink:        #262419;
    --ink-soft:   #6B6552;
    --line:       #E3DAC7;
    --folha:      #4F6A1E;
    --urucum:     #E02838;
    --sol:        #E8920A;
    --rio:        #3E9489;
}

/* --- Fonte global --- */
html, body, [class*="css"] {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* Faces geométricas (ecoam o wordmark da marca, "A" triangulares) */
.maz-display {
    font-family: 'Futura', 'Century Gothic', 'Trebuchet MS', sans-serif;
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

/* --- Cards de KPI --- */
.kpi-card {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 6px;
    overflow: hidden;
    transition: box-shadow 0.2s, transform 0.2s;
}
.kpi-card:hover { box-shadow: 0 4px 18px #2624190F; transform: translateY(-1px); }
.kpi-cap { height: 4px; }
.kpi-cap.folha { background: var(--folha); }
.kpi-cap.rio   { background: var(--rio); }
.kpi-cap.sol   { background: var(--sol); }
.kpi-cap.urucum{ background: var(--urucum); }
.kpi-body { padding: 16px 20px 18px; }
.kpi-label {
    font-family: 'Futura', 'Century Gothic', 'Trebuchet MS', sans-serif;
    font-size: 0.68rem;
    font-weight: 700;
    color: var(--ink-soft);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 10px;
}
.kpi-value {
    font-family: 'Futura', 'Century Gothic', 'Trebuchet MS', sans-serif;
    font-size: 1.7rem;
    font-weight: 700;
    color: var(--ink);
    line-height: 1.05;
    font-variant-numeric: tabular-nums;
}
.kpi-value.folha  { color: var(--folha); }
.kpi-value.rio    { color: var(--rio); }
.kpi-value.sol    { color: #B97200; }
.kpi-value.urucum { color: var(--urucum); }
.kpi-sub {
    font-size: 0.72rem;
    color: var(--ink-soft);
    margin-top: 8px;
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
    font-family: 'Futura', 'Century Gothic', 'Trebuchet MS', sans-serif;
    display: block;
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--ink-soft);
    text-transform: uppercase;
    letter-spacing: 0.2em;
    margin-bottom: 3px;
}
.header-title {
    font-family: 'Futura', 'Century Gothic', 'Trebuchet MS', sans-serif;
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--ink);
    margin: 0;
    letter-spacing: 0.01em;
}

/* --- Seções --- */
.section-title {
    font-family: 'Futura', 'Century Gothic', 'Trebuchet MS', sans-serif;
    font-size: 0.82rem;
    font-weight: 700;
    color: var(--ink);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin: 30px 0 14px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--line);
}

/* --- Barra de progresso customizada --- */
.progress-bar-container {
    background: var(--paper-deep);
    border-radius: 999px;
    height: 8px;
    margin-top: 8px;
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

/* --- Sidebar --- */
[data-testid="stSidebar"] {
    background: var(--paper-deep);
    border-right: 1px solid var(--line);
}

/* --- Upload box --- */
[data-testid="stFileUploader"] {
    border: 1px dashed #4F6A1E55;
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
# HELPERS DE FORMATAÇÃO                                                         #
# --------------------------------------------------------------------------- #

def fmt_brl(valor: float) -> str:
    """Formata número para moeda brasileira: R$ 1.234.567,89"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tem_colunas(df: pd.DataFrame, *colunas) -> bool:
    """Verifica se TODAS as colunas listadas existem no dataframe."""
    return all(c in df.columns for c in colunas)


def _fmt(v, tipo="texto"):
    """
    Formata valor para exibição em cards/tabelas.
    Sempre escapa caracteres HTML especiais (<, >, &, ", ')
    para evitar que conteúdo da planilha quebre o template HTML do card.
    """
    if pd.isna(v) or str(v).strip() in ("", "nan", "None"):
        return "—"
    if tipo == "valor":
        try:
            return fmt_brl(float(v))
        except Exception:
            return html.escape(str(v))
    if tipo == "data":
        try:
            return pd.to_datetime(v).strftime("%d/%m/%Y")
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


def _val_num(v) -> float:
    try:
        return float(v) if pd.notna(v) else 0.0
    except Exception:
        return 0.0


def _val_date(v):
    try:
        return pd.to_datetime(v).date() if pd.notna(v) else None
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
        <div style="text-align:center;padding:40px 20px;color:#6B6552;">
            {img}
            <p style="font-size:0.9rem;margin:0;">{html.escape(mensagem)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def secao_titulo(texto: str) -> None:
    """Renderiza um título de seção com sublinhado no grafismo de cobra da marca."""
    div = _logo_data_uri("cobra_divisor.png")
    if div:
        estilo = (
            "border-bottom:none;padding-bottom:11px;"
            f"background:url({div}) left bottom / auto 7px repeat-x;"
        )
    else:
        estilo = ""
    st.markdown(f'<p class="section-title" style="{estilo}">{texto}</p>', unsafe_allow_html=True)


def kpi_card(label: str, valor: str, sub: str = "", classe: str = "") -> str:
    """Retorna o HTML de um card de KPI. `classe` ∈ {folha, rio, sol, urucum}."""
    cap = f'<div class="kpi-cap {classe}"></div>' if classe else '<div class="kpi-cap folha"></div>'
    return f"""
    <div class="kpi-card">
        {cap}
        <div class="kpi-body">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value {classe}">{valor}</div>
            <div class="kpi-sub">{sub}</div>
        </div>
    </div>
    """


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
            <p class="maz-display" style="font-size:0.72rem;font-weight:700;color:#6B6552;
               text-transform:uppercase;letter-spacing:0.2em;margin-top:14px;">
                Dashboard Gerencial de Pagamentos
            </p>
            <p style="font-size:0.8rem;color:#6B6552;margin-bottom:18px;">
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
                st.rerun()
            else:
                st.error("Login ou senha incorretos.")

    st.stop()

_papel_usuario = st.session_state["papel"]
_PAPEL_LABEL = {
    dh.PAPEL_OWNER:  "👑 Owner",
    dh.PAPEL_ADMIN:  "🛠️ Admin",
    dh.PAPEL_VIEWER: "👁️ Viewer",
}


# --------------------------------------------------------------------------- #
# CABEÇALHO PRINCIPAL                                                           #
# --------------------------------------------------------------------------- #

_logo_header = _logo_data_uri("logo_horizontal.png")
_logo_html = (
    f'<img src="{_logo_header}" alt="Museu das Amazônias" style="height:52px;width:auto;">'
    if _logo_header else '<div style="font-size:2.2rem;">🏛️</div>'
)
st.markdown('<div class="maz-trancado"></div>', unsafe_allow_html=True)
st.markdown(f"""
<div class="header-container">
    {_logo_html}
    <div class="header-divider"></div>
    <div>
        <span class="header-eyebrow">Gestão de Pagamentos · IDG</span>
        <p class="header-title">Painel Gerencial</p>
    </div>
</div>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# SIDEBAR — Fonte de dados e filtros interativos                                #
# --------------------------------------------------------------------------- #

# Prioridade de configuração: 1) Arquivo local (5 dias, editável em Configurações)
#                              2) Secrets (valor inicial, antes da 1ª configuração)
#                              3) Vazio
# Secrets deixou de ser uma trava fixa: agora serve só de ponto de partida,
# para que trocar a planilha pela tela (ex: alternar entre cópia de teste e
# produção) tenha efeito de verdade, sem precisar editar Secrets a cada troca.
_url_secrets = st.secrets.get("SHEETS_URL", "") if hasattr(st, "secrets") else ""
_aba_secrets = st.secrets.get("SHEETS_ABA", "") if hasattr(st, "secrets") else ""
_cfg_disk    = _ler_config_persistente()

sheets_url_input = _cfg_disk.get("sheets_url", "") or _url_secrets
nome_aba_input   = _cfg_disk.get("sheets_aba", "") or _aba_secrets

with st.sidebar:

    # ------------------------------------------------------------------ #
    # Identidade do usuário logado + logout                               #
    # ------------------------------------------------------------------ #
    col_user, col_logout = st.columns([2.2, 1])
    with col_user:
        st.markdown(
            f"**{st.session_state['nome_usuario']}**  \n"
            f"<span style='color:#6B6552;font-size:0.75rem;'>{_PAPEL_LABEL.get(_papel_usuario, _papel_usuario)}</span>",
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
    # Configurações — visível para Owner e Admin                          #
    # ------------------------------------------------------------------ #
    if _papel_usuario in (dh.PAPEL_OWNER, dh.PAPEL_ADMIN):
        st.markdown("---")
        with st.expander("⚙️ Configurações", expanded=not bool(sheets_url_input)):
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

            if st.button("💾 Salvar", use_container_width=True):
                # Persiste em disco por 5 dias — sobrevive a F5 e recargas
                _salvar_config_persistente(novo_url, nova_aba)
                sheets_url_input = novo_url
                nome_aba_input   = nova_aba
                st.success("Configurações salvas por 5 dias.")
                st.rerun()

    # ------------------------------------------------------------------ #
    # Gerenciar Acessos — visível APENAS para o Owner                      #
    # ------------------------------------------------------------------ #
    if _papel_usuario == dh.PAPEL_OWNER:
        st.markdown("---")
        with st.expander("👑 Gerenciar Acessos", expanded=False):
            st.caption("Cadastre administradores e visualizadores. Visível apenas para você.")

            with st.form("form_novo_usuario", clear_on_submit=True):
                novo_login = st.text_input("Login do novo usuário")
                novo_nome  = st.text_input("Nome de exibição")
                nova_senha = st.text_input("Senha", type="password")
                novo_papel = st.selectbox(
                    "Papel",
                    options=[dh.PAPEL_ADMIN, dh.PAPEL_VIEWER],
                    format_func=lambda p: "🛠️ Admin (edita configurações)" if p == dh.PAPEL_ADMIN else "👁️ Viewer (somente visualização)",
                )
                cadastrar = st.form_submit_button("➕ Cadastrar", use_container_width=True)

            if cadastrar:
                if not novo_login.strip() or not nova_senha:
                    st.error("Login e senha são obrigatórios.")
                elif novo_login.strip() == _OWNER_LOGIN:
                    st.error("Este login já é o do Owner.")
                else:
                    dh.adicionar_usuario(novo_login, nova_senha, novo_papel, novo_nome)
                    st.success(f"Usuário **{novo_login}** cadastrado como {_PAPEL_LABEL.get(novo_papel, novo_papel)}.")
                    st.rerun()

            st.divider()
            st.caption("Usuários cadastrados:")
            usuarios_cadastrados = dh.carregar_usuarios()

            if not usuarios_cadastrados:
                st.caption("Nenhum administrador ou viewer cadastrado ainda.")
            else:
                for login_u, dados_u in usuarios_cadastrados.items():
                    col_info, col_del = st.columns([3, 1])
                    with col_info:
                        papel_u = dados_u.get("papel", dh.PAPEL_VIEWER)
                        st.markdown(
                            f"**{dados_u.get('nome', login_u)}**  \n"
                            f"<span style='color:#6B6552;font-size:0.72rem;'>{login_u} · {_PAPEL_LABEL.get(papel_u, papel_u)}</span>",
                            unsafe_allow_html=True,
                        )
                    with col_del:
                        if st.button("🗑️", key=f"del_{login_u}", help=f"Remover {login_u}"):
                            dh.remover_usuario(login_u)
                            st.rerun()

    # ------------------------------------------------------------------ #
    # Log de Alterações — visível para Owner e Admin                       #
    # ------------------------------------------------------------------ #
    if _papel_usuario in (dh.PAPEL_OWNER, dh.PAPEL_ADMIN):
        st.markdown("---")
        with st.expander("📋 Log de Alterações", expanded=False):
            entradas_log = dh.carregar_log()
            if not entradas_log:
                st.caption("Nenhuma alteração registrada ainda.\nO dashboard verifica mudanças a cada 1 hora automaticamente.")
            else:
                # Mostra as últimas 20 entradas, mais recentes primeiro
                for entrada in reversed(entradas_log[-20:]):
                    horario_str = datetime.fromisoformat(entrada["horario"]).strftime("%d/%m/%Y %H:%M")
                    total = entrada.get("total", len(entrada.get("alteracoes", [])))
                    st.markdown(
                        f"**🕐 {horario_str}** — {total} alteração{'ões' if total != 1 else ''}",
                    )
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

    # Upload manual (disponível para todos)
    st.markdown("### 📎 Upload Manual")
    arquivo = st.file_uploader(
        "Planilha (.xlsx ou .csv)",
        type=["xlsx", "xls", "csv"],
        help="Alternativa ao Google Sheets. O upload tem prioridade sobre o link.",
    )

    st.markdown("---")
    st.markdown("### 🎛️ Filtros")


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

# Indicador discreto de fonte e última atualização
st.caption(fonte_dados)

# --------------------------------------------------------------------------- #
# ALERTA AUTOMÁTICO DE PRAZOS — aparece sozinho, sem precisar clicar em nada  #
# --------------------------------------------------------------------------- #
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
            <div style="background:#E028380F;border:1px solid #E0283855;border-radius:6px;
                        padding:10px 16px;margin-bottom:14px;font-size:0.85rem;color:#262419;">
                {" &nbsp;·&nbsp; ".join(_partes)}
                &nbsp;·&nbsp; <span style="color:#6B6552;">veja em 📅 Prazos de Contratos, abaixo</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

# Alerta de diagnóstico: exibe aviso se colunas essenciais não foram mapeadas.
# Isso ajuda a identificar quando o nome da coluna na planilha é diferente do esperado.
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
# SIDEBAR — Filtros dinâmicos (renderizados após carga dos dados)               #
# --------------------------------------------------------------------------- #

with st.sidebar:
    # Os filtros de fornecedor/situação foram substituídos pela BUSCA em
    # destaque no topo do Detalhamento de Contratos (mais rápida de usar).
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
        if k.startswith("np_") or k in ("lanc_etapa", "lanc_compra", "lanc_n_parcelas"):
            del st.session_state[k]


@st.fragment
def _bloco_novo_lancamento():
    """
    Assistente de lançamento em 2 etapas (Pedido de Compra → Parcelas),
    isolado com @st.fragment para que as interações (avançar, adicionar
    parcela, digitar) recarreguem só este bloco — não o dashboard inteiro.
    Grava a Compra e todas as suas parcelas numa única operação.
    """
    if _papel_usuario not in (dh.PAPEL_OWNER, dh.PAPEL_ADMIN):
        return

    secao_titulo("➕ Novo Lançamento")

    if "gcp_service_account" not in st.secrets:
        st.info(
            "🔒 Os lançamentos pelo dashboard exigem a Service Account configurada "
            "nos Secrets (`gcp_service_account`). Até isso ser configurado, "
            "novos pedidos e pagamentos continuam sendo lançados direto na planilha.",
            icon="ℹ️",
        )
        return

    ss = st.session_state
    ss.setdefault("lanc_etapa", 1)
    ss.setdefault("lanc_compra", {})
    ss.setdefault("lanc_n_parcelas", 1)

    # ==================== ETAPA 1 — Pedido de Compra ==================== #
    if ss["lanc_etapa"] == 1:
        c = ss["lanc_compra"]
        _opts_status = dh.STATUS_TODOS
        _idx_status = _opts_status.index(c["status"]) if c.get("status") in _opts_status else 0

        with st.form("form_compra"):
            st.markdown("**1. Dados do Pedido de Compra**")
            col1, col2 = st.columns(2)
            with col1:
                f_fornecedor = st.text_input("Fornecedor *", value=c.get("fornecedor", ""))
                f_req        = st.text_input("Req. MXM", value=c.get("req_mxm", ""))
                f_valor      = st.number_input("Valor total do contrato (R$) *", min_value=0.0, step=100.0, format="%.2f", value=float(c.get("valor", 0.0)))
                f_status     = st.selectbox("Status inicial *", options=_opts_status, index=_idx_status)
            with col2:
                f_descritivo = st.text_input("Descritivo", value=c.get("descritivo", ""))
                f_termino    = st.date_input("Término do contrato", value=c.get("termino_contrato") or None)
                f_link       = st.text_input("Link do contrato", value=c.get("link_contrato", ""))
            f_obs = st.text_area("Observações", height=80, value=c.get("observacoes", ""))

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
                ss["lanc_etapa"] = 2
                st.rerun(scope="fragment")
        return

    # ==================== ETAPA 2 — Condições de Pagamento ==================== #
    c = ss["lanc_compra"]
    st.markdown(
        "**2. Condições de Pagamento** &nbsp;·&nbsp; "
        f"<span style='color:#6B6552;'>{html.escape(str(c.get('fornecedor', '')))} · "
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

    col_add, col_reg = st.columns(2)
    with col_add:
        if st.button("➕ Adicionar parcela", use_container_width=True, key="lanc_add"):
            ss["lanc_n_parcelas"] += 1
            st.rerun(scope="fragment")
    with col_reg:
        registrar = st.button("💾 Registrar pagamento", use_container_width=True, type="primary", key="lanc_reg")

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
                avisos = dh.inserir_compra_com_parcelas(sheets_url_input, nome_aba_input, c, parcelas)
                dh.carregar_do_sheets.clear()
                _limpar_wizard_lancamento()
                st.session_state["flash_ok"] = (
                    f"Pedido de {c.get('fornecedor')} e "
                    f"{len(parcelas)} parcela(s) registrados na planilha."
                )
                if avisos:
                    st.session_state["flash_avisos"] = avisos
                st.rerun(scope="app")
            except Exception as e:
                st.error(f"Não foi possível gravar na planilha.\n\nDetalhe técnico: `{e}`")


_bloco_novo_lancamento()


# --------------------------------------------------------------------------- #
# SEÇÃO 1 — KPI CARDS (visão macro para a diretoria)                           #
# --------------------------------------------------------------------------- #

secao_titulo("📊 Indicadores Executivos")

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    st.markdown(kpi_card(
        "Orçamento Total",
        fmt_brl(kpis["orcamento_total"]),
        "Valor total contratado",
        "folha"
    ), unsafe_allow_html=True)

with col2:
    st.markdown(kpi_card(
        "Total Pago",
        fmt_brl(kpis["pago"]),
        "Pagamentos realizados",
        "rio"
    ), unsafe_allow_html=True)

with col3:
    st.markdown(kpi_card(
        "Saldo a Pagar",
        fmt_brl(kpis["a_pagar"]),
        "Pagamentos pendentes",
        ""
    ), unsafe_allow_html=True)

with col4:
    st.markdown(kpi_card(
        "Em Gargalo",
        fmt_brl(kpis["em_gargalo"]),
        "Aguardando desbloqueio",
        "sol"
    ), unsafe_allow_html=True)

with col5:
    st.markdown(kpi_card(
        "Contratos Vencidos",
        str(kpis["vencidos"]),
        "Requer atenção imediata",
        "urucum" if kpis["vencidos"] > 0 else "folha"
    ), unsafe_allow_html=True)

with col6:
    st.markdown(kpi_card(
        "Execução Orçamentária",
        f"{kpis['perc_execucao']:.1f}%",
        f"{kpis['fornecedores']} fornecedores ativos",
        "folha"
    ), unsafe_allow_html=True)

# Barra de progresso da execução orçamentária
pct = min(kpis["perc_execucao"], 100)
st.markdown(f"""
<div class="maz-display" style="margin: 12px 0 4px 0; font-size:0.7rem; color:#6B6552; letter-spacing:0.1em; text-transform:uppercase;">
    Execução Orçamentária Global — {pct:.1f}% concluído
</div>
<div class="progress-bar-container">
    <div class="progress-bar-fill" style="width:{pct}%;"></div>
</div>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# SEÇÃO — PRAZOS DE CONTRATOS (visível para todos os papéis)                  #
# --------------------------------------------------------------------------- #

secao_titulo("📅 Prazos de Contratos")

if "termino_contrato" not in df_compras.columns:
    st.caption("Coluna de término do contrato não encontrada na planilha.")
else:
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
        for _, linha in df_prazos.iterrows():
            _ps = str(linha.get("prazo_status", "sem_data"))
            if _ps not in dh.CORES_PRAZO:
                _ps = "sem_data"
            _cor = dh.CORES_PRAZO[_ps]
            _dias = linha.get("dias_para_vencer")
            if pd.notna(_dias):
                _dias = int(_dias)
                _dias_txt = f"vence em {_dias} dia(s)" if _dias >= 0 else f"vencido há {abs(_dias)} dia(s)"
            else:
                _dias_txt = "sem data de término"

            st.markdown(
                f"""
                <div style="display:flex;align-items:center;gap:12px;background:#FCFAF4;
                            border:1px solid #E3DAC7;border-left:4px solid {_cor};
                            border-radius:6px;padding:10px 16px;margin-bottom:6px;">
                    <div style="flex:1;">
                        <span style="font-family:'Futura','Century Gothic','Trebuchet MS',sans-serif;
                                     font-weight:700;color:#262419;font-size:0.9rem;">
                            {html.escape(_val_txt(linha.get('fornecedor')) or '—')}
                        </span>
                        <span style="color:#6B6552;font-size:0.76rem;margin-left:8px;">
                            {html.escape(_val_txt(linha.get('descritivo')) or '—')}
                        </span>
                    </div>
                    <div style="color:#6B6552;font-size:0.78rem;white-space:nowrap;">
                        {_fmt(linha.get('termino_contrato'), 'data')}
                    </div>
                    <div style="color:{_cor};font-weight:700;font-size:0.78rem;white-space:nowrap;">
                        {dh.EMOJI_PRAZO[_ps]} {html.escape(_dias_txt)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# --------------------------------------------------------------------------- #
# SEÇÃO 2 — PANORAMA GERAL (2 gráficos lado a lado)                            #
# --------------------------------------------------------------------------- #

secao_titulo("🗺️ Panorama Geral")

col_esq, col_dir = st.columns([1.1, 0.9])

# --- Gráfico 1: Distribuição por Situação do Fluxo (donut chart) ---
with col_esq:
    if tem_colunas(df_pag, "status", "valor"):
        contagem_status = df_pag.groupby("status")["valor"].sum().reset_index()
        contagem_status.columns = ["Status", "Valor"]
        contagem_status = contagem_status[contagem_status["Valor"] > 0]
        contagem_status["Grupo"] = contagem_status["Status"].map(
            lambda s: dh.STATUS_PARA_GRUPO.get(s, "alerta")
        )
        # Cor baseada no grupo de saúde
        cores_mapa = contagem_status["Grupo"].map(dh.CORES_GRUPO).tolist()

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
            font_color="#262419",
            showlegend=False,
            title_font_size=13,
            title_font_color="#6B6552",
            margin=dict(t=40, b=10, l=10, r=10),
            annotations=[dict(
                text=f"<b>{fmt_brl(kpis['a_pagar'])}</b><br><span style='font-size:10px'>a pagar</span>",
                x=0.5, y=0.5, font_size=12, showarrow=False, font_color="#4F6A1E"
            )],
        )
        st.plotly_chart(fig_donut, use_container_width=True)

# --- Gráfico 2: Top 10 Fornecedores por Valor Contratado (barras horizontais) ---
with col_dir:
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
            color_continuous_scale=[[0, "#C9D6B0"], [0.5, "#7FA34A"], [1, "#4F6A1E"]],
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
            font_color="#262419",
            title_font_size=13,
            title_font_color="#6B6552",
            coloraxis_showscale=False,
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=False),
            margin=dict(t=40, b=10, l=10, r=80),
        )
        st.plotly_chart(fig_bar, use_container_width=True)


# --------------------------------------------------------------------------- #
# SEÇÃO 3 — ANÁLISE DE GARGALOS (foco em tomada de decisão)                    #
# --------------------------------------------------------------------------- #

secao_titulo("⚠️ Análise de Gargalos · Pagamentos Bloqueados")

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

    with col_g1:
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
            color_discrete_map=dh.CORES_GRUPO,
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
            font_color="#262419",
            title_font_size=13,
            title_font_color="#6B6552",
            showlegend=False,
            xaxis=dict(showgrid=False, tickangle=-20),
            yaxis=dict(showgrid=True, gridcolor="#E3DAC7", visible=False),
            margin=dict(t=50, b=60, l=10, r=10),
        )
        st.plotly_chart(fig_gargalo, use_container_width=True)

    with col_g2:
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

secao_titulo("📅 Fluxo Temporal de Pagamentos")

if tem_colunas(df_pag, "mes_pgto", "valor", "status"):
    df_tempo = df_pag.dropna(subset=["mes_pgto"])

    if not df_tempo.empty:
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
            color_discrete_map={"Realizado": "#4F6A1E", "Previsto": "#E8920A"},
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
            font_color="#262419",
            title_font_size=13,
            title_font_color="#6B6552",
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#E3DAC7", visible=False),
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
# --------------------------------------------------------------------------- #

secao_titulo("📋 Detalhamento de Contratos")


# Cor do TEXTO do badge sobre fundo claro (laranja puro tem baixo contraste)
_COR_TEXTO_BADGE = {
    "concluido":    "#4F6A1E",
    "em_andamento": "#2C6E64",
    "alerta":       "#B97200",
    "critico":      "#E02838",
}


def _status_badge(status: str, grupo: str) -> str:
    """Retorna HTML do badge de status colorido (tema claro)."""
    cor = dh.CORES_GRUPO.get(grupo, "#6B6552")
    cor_txt = _COR_TEXTO_BADGE.get(grupo, "#6B6552")
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


# Mensagem de sucesso após uma ação de edição (sobrevive ao rerun do diálogo)
_flash = st.session_state.pop("flash_ok", None)
if _flash:
    st.success(f"✅ {_flash}")

# Avisos não-críticos (ex: falha ao copiar formatação visual) — não impedem
# o lançamento, mas precisam aparecer pra gente conseguir diagnosticar.
_flash_avisos = st.session_state.pop("flash_avisos", None)
if _flash_avisos:
    for _av in _flash_avisos:
        st.warning(f"⚠️ {_av}")


# ---- Busca: caixas separadas, uma por campo ----
st.markdown(
    "<span class='maz-display' style='font-size:0.72rem;font-weight:700;"
    "letter-spacing:0.14em;text-transform:uppercase;color:#6B6552;'>Buscar por</span>",
    unsafe_allow_html=True,
)
bc1, bc2, bc3, bc4 = st.columns(4)
q_forn = bc1.text_input("Fornecedor", placeholder="Fornecedor", label_visibility="collapsed", key="q_forn").strip().lower()
q_req  = bc2.text_input("Requisição", placeholder="Requisição", label_visibility="collapsed", key="q_req").strip().lower()
q_serv = bc3.text_input("Serviço",    placeholder="Serviço",    label_visibility="collapsed", key="q_serv").strip().lower()
q_nf   = bc4.text_input("Nº da NF",   placeholder="Nº da NF",   label_visibility="collapsed", key="q_nf").strip().lower()

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
                "<span style=\"color:#6B6552;font-size:0.74rem;margin-left:10px;"
                f"letter-spacing:0.03em;\">Req. {html.escape(req_val)}</span>"
            )
        else:
            req_html = (
                "<span style=\"background:#E8920A1A;border:1px solid #E8920A99;"
                "color:#B97200;font-size:0.6rem;font-weight:700;letter-spacing:0.04em;"
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
        cor_spine = dh.CORES_GRUPO.get(grupo, "#6B6552")

        # --- Selo de prazo: código/link do contrato + término + urgência ---
        prazo_status = str(compra.get("prazo_status", "sem_data"))
        if prazo_status not in dh.CORES_PRAZO:
            prazo_status = "sem_data"
        cor_prazo   = dh.CORES_PRAZO[prazo_status]
        emoji_prazo = dh.EMOJI_PRAZO[prazo_status]
        label_prazo = dh.LABEL_PRAZO[prazo_status]

        link_val = _val_txt(compra.get("link_contrato"))
        partes_prazo = []
        if link_val:
            if link_val.lower().startswith("http"):
                partes_prazo.append(
                    f'<a href="{html.escape(link_val)}" target="_blank" '
                    f'style="color:inherit;text-decoration:underline;">🔗 Contrato</a>'
                )
            else:
                partes_prazo.append(f"📄 {html.escape(link_val)}")
        if termino != "—":
            partes_prazo.append(f"📅 Término: {termino}")
        partes_prazo.append(f"{emoji_prazo} {label_prazo}")

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
                background:#FCFAF4;border:1px solid #E3DAC7;border-radius:6px;
                margin-bottom:6px;font-family:sans-serif;display:flex;overflow:hidden;
            ">
                <div style="width:5px;flex-shrink:0;background:{cor_spine};"></div>
                <div style="flex:1;padding:14px 18px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                        <div>
                            <span style="font-family:'Futura','Century Gothic','Trebuchet MS',sans-serif;font-weight:700;color:#262419;font-size:0.96rem;">{fornecedor}</span>
                            {req_html}
                        </div>
                        <div style="display:flex;align-items:center;gap:12px;">
                            <span style="font-family:'Futura','Century Gothic','Trebuchet MS',sans-serif;color:#262419;font-weight:700;font-size:1rem;font-variant-numeric:tabular-nums;">{valor}</span>
                            {badge}
                        </div>
                    </div>
                    {f'<div style="color:#6B6552;font-size:0.78rem;margin-top:8px;">{detalhes_html}</div>' if detalhes_html else ""}
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
                    cols[0].markdown(f"**{p_desc}**  \n{dh.EMOJI_GRUPO.get(p_grupo, '')} <span style='font-size:0.75rem;color:#6B6552;'>{html.escape(p_stat)}</span>", unsafe_allow_html=True)
                    cols[1].markdown(f"<span style='font-size:0.85rem;'>{_fmt(prow.get('valor'), 'valor')}</span>", unsafe_allow_html=True)
                    cols[2].markdown(f"<span style='font-size:0.85rem;color:#6B6552;'>{_fmt(prow.get('data_pgto'), 'data')}</span>", unsafe_allow_html=True)
                    cols[3].markdown(f"<span style='font-size:0.85rem;color:#6B6552;'>NF {_val_txt(prow.get('doc_fiscal')) or '—'}</span>", unsafe_allow_html=True)
                    if _pode_editar and _escrita_ok:
                        if cols[4].button("✏️", key=f"edpar_{gi}_{pi}", help="Editar parcela"):
                            st.session_state["edit_target"] = ("parcela", gi, pi)
                            st.rerun()
                    st.markdown("<hr style='margin:4px 0;border:none;border-top:1px solid #E3DAC7;'>", unsafe_allow_html=True)
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
    color: #6B6552;
    font-size: 0.72rem;
">
    {_idg_html}
    <div>MAZ | Museu das Amazônias · uma realização do IDG — Instituto de Desenvolvimento e Gestão</div>
    <div>Dashboard Gerencial de Pagamentos · Versão Beta 1.0</div>
</div>
""", unsafe_allow_html=True)
