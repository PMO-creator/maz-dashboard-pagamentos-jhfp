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

# Prioridade de configuração: 1) Secrets  2) Arquivo local (5 dias)  3) Vazio
_url_secrets = st.secrets.get("SHEETS_URL", "") if hasattr(st, "secrets") else ""
_aba_secrets = st.secrets.get("SHEETS_ABA", "") if hasattr(st, "secrets") else ""
_cfg_disk    = _ler_config_persistente()

# Carrega URL e aba: Secrets > arquivo em disco > vazio
sheets_url_input = _url_secrets or _cfg_disk.get("sheets_url", "")
nome_aba_input   = _aba_secrets or _cfg_disk.get("sheets_aba", "")

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
    # Filtro por Fornecedor
    todos_fornecedores = sorted(df["fornecedor"].dropna().unique().tolist()) if "fornecedor" in df.columns else []
    sel_fornecedor = st.multiselect(
        "Fornecedor",
        options=todos_fornecedores,
        default=[],
        placeholder="Todos os fornecedores",
    )

    # Filtro por Grupo de Status (saúde do fluxo)
    opcoes_grupo = {
        "✅ Concluído":    "concluido",
        "🔄 Em andamento": "em_andamento",
        "⚠️ Alerta":       "alerta",
        "🚨 Crítico":      "critico",
    }
    sel_grupos_label = st.multiselect(
        "Situação do fluxo",
        options=list(opcoes_grupo.keys()),
        default=[],
        placeholder="Todas as situações",
    )
    sel_grupos = [opcoes_grupo[l] for l in sel_grupos_label]

    st.markdown("---")
    st.caption(f"**{len(df)}** registros carregados · **{df['fornecedor'].nunique() if 'fornecedor' in df.columns else 0}** fornecedores")

# Aplica filtros ao dataframe principal
df_filtrado = dh.aplicar_filtros(df, sel_fornecedor, sel_grupos)
_, df_pag_filtrado = dh.separar_por_tipo(df_filtrado)


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


def _fmt(v, tipo="texto"):
    """
    Formata valor para exibição na tabela hierárquica.
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


# ---- Abas: Em andamento | Quitados ----
aba_ativa = st.radio(
    "",
    options=["🔄  Em Andamento", "✅  Quitados"],
    horizontal=True,
    label_visibility="collapsed",
)
mostrar_quitados = aba_ativa.startswith("✅")

# Monta hierarquia a partir do df filtrado (mantém ordem da planilha)
hierarquia = dh.agrupar_hierarquia(df_filtrado)

# Filtra por aba ativa
def _eh_quitado(compra) -> bool:
    status = str(compra.get("status", ""))
    grupo  = str(compra.get("grupo_status", ""))
    return status in dh.STATUS_QUITADO or grupo == "concluido"

hierarquia_filtrada = [
    (c, p) for c, p in hierarquia
    if _eh_quitado(c) == mostrar_quitados
]

# Indicador de resultado
n_contratos = len(hierarquia_filtrada)
st.caption(f"{'✅ Contratos quitados' if mostrar_quitados else '🔄 Contratos em andamento'}: **{n_contratos}**")

if not hierarquia_filtrada:
    estado_vazio("Nenhum contrato encontrado nesta categoria com os filtros aplicados.")
else:
    for compra, df_pags in hierarquia_filtrada:

        # --- Dados principais da Compra ---
        # _fmt() aplica html.escape() em todos os valores de texto,
        # evitando que conteúdo da planilha quebre a estrutura HTML do card.
        fornecedor  = _fmt(compra.get("fornecedor"))
        valor       = _fmt(compra.get("valor"), "valor")
        req         = _fmt(compra.get("req_mxm"))
        descritivo  = _fmt(compra.get("descritivo"))
        termino     = _fmt(compra.get("termino_contrato"), "data")
        observacoes = _fmt(compra.get("observacoes"))

        # Status: trata "nan" (pandas NaN convertido para string) como sem status
        status_raw = str(compra.get("status", ""))
        status     = "Sem status" if status_raw in ("nan", "", "None") else status_raw
        grupo      = str(compra.get("grupo_status", "alerta"))
        if grupo in ("nan", "", "None"):
            grupo = "alerta"

        n_parcelas   = len(df_pags) if not df_pags.empty else 0
        label_expand = f"  ({n_parcelas} pagamento{'s' if n_parcelas != 1 else ''})" if n_parcelas > 0 else ""

        # Linha de detalhes secundários (só mostra se houver conteúdo)
        detalhes_parts = [descritivo] if descritivo != "—" else []
        if termino != "—":
            detalhes_parts.append(f"Término: {termino}")
        if observacoes != "—":
            detalhes_parts.append(observacoes)
        detalhes_html = " &nbsp;·&nbsp; ".join(detalhes_parts)

        badge = _status_badge(status, grupo)
        cor_spine = dh.CORES_GRUPO.get(grupo, "#6B6552")

        # st.html() renderiza HTML puro sem processamento markdown,
        # eliminando interferência de caracteres especiais nos dados.
        st.html(f"""
            <div style="
                background:#FCFAF4;border:1px solid #E3DAC7;border-radius:6px;
                margin-bottom:6px;font-family:sans-serif;display:flex;overflow:hidden;
            ">
                <div style="width:5px;flex-shrink:0;background:{cor_spine};"></div>
                <div style="flex:1;padding:14px 18px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                        <div>
                            <span style="font-family:'Futura','Century Gothic','Trebuchet MS',sans-serif;font-weight:700;color:#262419;font-size:0.96rem;">{fornecedor}</span>
                            <span style="color:#6B6552;font-size:0.74rem;margin-left:10px;letter-spacing:0.03em;">Req. {req}</span>
                        </div>
                        <div style="display:flex;align-items:center;gap:12px;">
                            <span style="font-family:'Futura','Century Gothic','Trebuchet MS',sans-serif;color:#262419;font-weight:700;font-size:1rem;font-variant-numeric:tabular-nums;">{valor}</span>
                            {badge}
                        </div>
                    </div>
                    {f'<div style="color:#6B6552;font-size:0.78rem;margin-top:8px;">{detalhes_html}</div>' if detalhes_html else ""}
                </div>
            </div>
        """)

        # --- Expansor de pagamentos/parcelas ---
        if n_parcelas > 0:
            with st.expander(f"＋ Ver pagamentos / parcelas{label_expand}", expanded=False):

                # Monta tabela de pagamentos
                colunas_pag = [c for c in [
                    "req_mxm", "descritivo", "valor", "status",
                    "data_pgto", "doc_fiscal", "observacoes"
                ] if c in df_pags.columns]

                df_pag_exibir = df_pags[colunas_pag].copy()

                if "valor" in df_pag_exibir.columns:
                    df_pag_exibir["valor"] = df_pag_exibir["valor"].apply(
                        lambda v: _fmt(v, "valor")
                    )
                if "data_pgto" in df_pag_exibir.columns:
                    df_pag_exibir["data_pgto"] = df_pag_exibir["data_pgto"].apply(
                        lambda v: _fmt(v, "data")
                    )
                if "status" in df_pag_exibir.columns and "grupo_status" in df_pags.columns:
                    grupos_pag = df_pags["grupo_status"].tolist()
                    df_pag_exibir["status"] = [
                        f"{dh.EMOJI_GRUPO.get(g, '')} {s}"
                        for s, g in zip(df_pag_exibir["status"], grupos_pag)
                    ]

                renomear_pag = {
                    "req_mxm": "Req. MXM", "descritivo": "Descritivo",
                    "valor": "Valor", "status": "Status",
                    "data_pgto": "Data Pgto", "doc_fiscal": "Doc. Fiscal",
                    "observacoes": "Observações",
                }
                df_pag_exibir = df_pag_exibir.rename(
                    columns={k: v for k, v in renomear_pag.items() if k in df_pag_exibir.columns}
                )
                st.dataframe(df_pag_exibir, use_container_width=True, hide_index=True)

# Botão de exportação
csv_export = df_filtrado.to_csv(index=False, encoding="utf-8-sig")
st.download_button(
    label="⬇️  Exportar dados filtrados (.csv)",
    data=csv_export,
    file_name="maz_pagamentos_filtrado.csv",
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
