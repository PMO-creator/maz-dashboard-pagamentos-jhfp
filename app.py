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

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import data_handler as dh


# --------------------------------------------------------------------------- #
# CONFIGURAÇÃO DA PÁGINA — deve ser a primeira chamada Streamlit               #
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="MAZ | Dashboard de Pagamentos",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------- #
# CSS GLOBAL — sobrescreve estilos do Streamlit para o visual corporativo MAZ  #
# Paleta: #0D1117 fundo | #C9A84C dourado | #2DD4BF verde-água | #161B22 cards#
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
/* --- Fonte global e fundo --- */
html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', sans-serif;
}

/* --- Cards de KPI --- */
.kpi-card {
    background: #161B22;
    border: 1px solid #21262D;
    border-radius: 12px;
    padding: 20px 24px;
    text-align: center;
    transition: border-color 0.2s;
}
.kpi-card:hover { border-color: #C9A84C; }
.kpi-label {
    font-size: 0.78rem;
    color: #8B949E;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 1.7rem;
    font-weight: 700;
    color: #E6EDF3;
    line-height: 1.1;
}
.kpi-value.dourado  { color: #C9A84C; }
.kpi-value.verde    { color: #2DD4BF; }
.kpi-value.alerta   { color: #F59E0B; }
.kpi-value.critico  { color: #EF4444; }
.kpi-sub {
    font-size: 0.72rem;
    color: #8B949E;
    margin-top: 4px;
}

/* --- Cabeçalho principal --- */
.header-container {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 0 24px 0;
    border-bottom: 1px solid #21262D;
    margin-bottom: 28px;
}
.header-title {
    font-size: 1.6rem;
    font-weight: 700;
    color: #E6EDF3;
    margin: 0;
}
.header-sub {
    font-size: 0.85rem;
    color: #8B949E;
    margin: 0;
}
.badge-beta {
    background: #C9A84C22;
    border: 1px solid #C9A84C;
    color: #C9A84C;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 20px;
    letter-spacing: 0.1em;
    vertical-align: middle;
}

/* --- Seções --- */
.section-title {
    font-size: 0.8rem;
    font-weight: 600;
    color: #8B949E;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin: 28px 0 12px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid #21262D;
}

/* --- Barra de progresso customizada --- */
.progress-bar-container {
    background: #21262D;
    border-radius: 8px;
    height: 8px;
    margin-top: 8px;
    overflow: hidden;
}
.progress-bar-fill {
    height: 100%;
    border-radius: 8px;
    background: linear-gradient(90deg, #C9A84C, #2DD4BF);
    transition: width 0.6s ease;
}

/* --- Tabela de dados --- */
div[data-testid="stDataFrame"] {
    border: 1px solid #21262D;
    border-radius: 8px;
    overflow: hidden;
}

/* --- Sidebar --- */
[data-testid="stSidebar"] {
    background: #0D1117;
    border-right: 1px solid #21262D;
}

/* --- Upload box --- */
[data-testid="stFileUploader"] {
    border: 1px dashed #C9A84C44;
    border-radius: 8px;
    padding: 8px;
}

/* Remove padding excessivo do container principal */
.block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# HELPERS DE FORMATAÇÃO                                                         #
# --------------------------------------------------------------------------- #

def fmt_brl(valor: float) -> str:
    """Formata número para moeda brasileira: R$ 1.234.567,89"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def kpi_card(label: str, valor: str, sub: str = "", classe: str = "") -> str:
    """Retorna o HTML de um card de KPI."""
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value {classe}">{valor}</div>
        <div class="kpi-sub">{sub}</div>
    </div>
    """


# --------------------------------------------------------------------------- #
# CABEÇALHO PRINCIPAL                                                           #
# --------------------------------------------------------------------------- #

st.markdown("""
<div class="header-container">
    <div style="font-size:2.2rem;">🏛️</div>
    <div>
        <p class="header-title">
            MAZ | Museu das Amazônias
            <span class="badge-beta">BETA</span>
        </p>
        <p class="header-sub">Dashboard Gerencial de Pagamentos · IDG — Instituto de Desenvolvimento e Gestão</p>
    </div>
</div>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# SIDEBAR — Fonte de dados e filtros interativos                                #
# --------------------------------------------------------------------------- #

# Lê credenciais de administrador das Secrets do Streamlit.
# NUNCA hardcode senhas no código — elas ficam apenas no painel do Streamlit Cloud.
_ADMIN_LOGIN = st.secrets.get("ADMIN_LOGIN", "") if hasattr(st, "secrets") else ""
_ADMIN_SENHA = st.secrets.get("ADMIN_SENHA", "") if hasattr(st, "secrets") else ""

# Lê configurações de fonte de dados das Secrets (valores padrão fixados pelo admin)
_url_secrets  = st.secrets.get("SHEETS_URL", "") if hasattr(st, "secrets") else ""
_aba_secrets  = st.secrets.get("SHEETS_ABA", "") if hasattr(st, "secrets") else ""

# Inicializa estado de autenticação do administrador na sessão
if "admin_autenticado" not in st.session_state:
    st.session_state["admin_autenticado"] = False

# Usa os valores das Secrets como padrão; o admin pode sobrescrever via UI
sheets_url_input = st.session_state.get("sheets_url", _url_secrets)
nome_aba_input   = st.session_state.get("sheets_aba", _aba_secrets)

with st.sidebar:

    # ------------------------------------------------------------------ #
    # Seção de configuração — protegida por login de administrador         #
    # ------------------------------------------------------------------ #
    with st.expander("⚙️ Configurações", expanded=not bool(sheets_url_input)):

        if not st.session_state["admin_autenticado"]:
            # Formulário de login — submetido com Enter ou botão
            with st.form("form_admin", clear_on_submit=False):
                st.caption("Acesso restrito a administradores.")
                login_input = st.text_input("Login", placeholder="seu login")
                senha_input = st.text_input("Senha", type="password", placeholder="••••••••")
                entrar = st.form_submit_button("Entrar", use_container_width=True)

            if entrar:
                if login_input == _ADMIN_LOGIN and senha_input == _ADMIN_SENHA:
                    st.session_state["admin_autenticado"] = True
                    st.rerun()
                else:
                    st.error("Login ou senha incorretos.")
        else:
            # Admin autenticado — exibe campos de configuração
            st.success("✅ Administrador autenticado")

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

            col_s, col_l = st.columns(2)
            with col_s:
                if st.button("💾 Salvar", use_container_width=True):
                    st.session_state["sheets_url"] = novo_url
                    st.session_state["sheets_aba"] = nova_aba
                    sheets_url_input = novo_url
                    nome_aba_input   = nova_aba
                    st.rerun()
            with col_l:
                if st.button("🔒 Sair", use_container_width=True):
                    st.session_state["admin_autenticado"] = False
                    st.rerun()

    # Fallback: upload manual (disponível para todos, sem autenticação)
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

st.markdown('<p class="section-title">📊 Indicadores Executivos</p>', unsafe_allow_html=True)

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    st.markdown(kpi_card(
        "Orçamento Total",
        fmt_brl(kpis["orcamento_total"]),
        "Valor total contratado",
        "dourado"
    ), unsafe_allow_html=True)

with col2:
    st.markdown(kpi_card(
        "Total Pago",
        fmt_brl(kpis["pago"]),
        "Pagamentos realizados",
        "verde"
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
        "alerta"
    ), unsafe_allow_html=True)

with col5:
    st.markdown(kpi_card(
        "Contratos Vencidos",
        str(kpis["vencidos"]),
        "Requer atenção imediata",
        "critico" if kpis["vencidos"] > 0 else "verde"
    ), unsafe_allow_html=True)

with col6:
    st.markdown(kpi_card(
        "Execução Orçamentária",
        f"{kpis['perc_execucao']:.1f}%",
        f"{kpis['fornecedores']} fornecedores ativos",
        "dourado"
    ), unsafe_allow_html=True)

# Barra de progresso da execução orçamentária
pct = min(kpis["perc_execucao"], 100)
st.markdown(f"""
<div style="margin: 12px 0 4px 0; font-size:0.72rem; color:#8B949E;">
    EXECUÇÃO ORÇAMENTÁRIA GLOBAL — {pct:.1f}% concluído
</div>
<div class="progress-bar-container">
    <div class="progress-bar-fill" style="width:{pct}%;"></div>
</div>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# SEÇÃO 2 — PANORAMA GERAL (2 gráficos lado a lado)                            #
# --------------------------------------------------------------------------- #

st.markdown('<p class="section-title">🗺️ Panorama Geral</p>', unsafe_allow_html=True)

col_esq, col_dir = st.columns([1.1, 0.9])

# --- Gráfico 1: Distribuição por Situação do Fluxo (donut chart) ---
with col_esq:
    if "status" in df_pag.columns:
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
            font_color="#E6EDF3",
            showlegend=False,
            title_font_size=13,
            title_font_color="#8B949E",
            margin=dict(t=40, b=10, l=10, r=10),
            annotations=[dict(
                text=f"<b>{fmt_brl(kpis['a_pagar'])}</b><br><span style='font-size:10px'>a pagar</span>",
                x=0.5, y=0.5, font_size=12, showarrow=False, font_color="#E6EDF3"
            )],
        )
        st.plotly_chart(fig_donut, use_container_width=True)

# --- Gráfico 2: Top 10 Fornecedores por Valor Contratado (barras horizontais) ---
with col_dir:
    if "fornecedor" in df_compras.columns and "valor" in df_compras.columns:
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
            color_continuous_scale=[[0, "#1F2937"], [0.5, "#C9A84C"], [1, "#2DD4BF"]],
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
            font_color="#E6EDF3",
            title_font_size=13,
            title_font_color="#8B949E",
            coloraxis_showscale=False,
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=False),
            margin=dict(t=40, b=10, l=10, r=80),
        )
        st.plotly_chart(fig_bar, use_container_width=True)


# --------------------------------------------------------------------------- #
# SEÇÃO 3 — ANÁLISE DE GARGALOS (foco em tomada de decisão)                    #
# --------------------------------------------------------------------------- #

st.markdown('<p class="section-title">⚠️ Análise de Gargalos · Pagamentos Bloqueados</p>', unsafe_allow_html=True)

# Status de alerta e em andamento são os gargalos a monitorar
status_gargalo_lista = dh.STATUS_GRUPOS["alerta"] + dh.STATUS_GRUPOS["em_andamento"]
df_gargalo = df_pag[df_pag["status"].isin(status_gargalo_lista)]

if df_gargalo.empty:
    st.success("✅ Nenhum pagamento em situação de gargalo no momento.")
else:
    col_g1, col_g2 = st.columns([1.2, 0.8])

    with col_g1:
        # Gráfico de barras: valor parado por status de gargalo
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
        gargalo_agrupado["Cor"] = gargalo_agrupado["Grupo"].map(dh.CORES_GRUPO)

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
            font_color="#E6EDF3",
            title_font_size=13,
            title_font_color="#8B949E",
            showlegend=False,
            xaxis=dict(showgrid=False, tickangle=-20),
            yaxis=dict(showgrid=True, gridcolor="#21262D", visible=False),
            margin=dict(t=50, b=60, l=10, r=10),
        )
        st.plotly_chart(fig_gargalo, use_container_width=True)

    with col_g2:
        # Tabela resumo de gargalos por fornecedor
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

st.markdown('<p class="section-title">📅 Fluxo Temporal de Pagamentos</p>', unsafe_allow_html=True)

if "mes_pgto" in df_pag.columns and "valor" in df_pag.columns:
    df_tempo = df_pag.dropna(subset=["mes_pgto"])

    if not df_tempo.empty:
        # Agrupa por mês e status (pago x a pagar)
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
            color_discrete_map={"Realizado": "#2DD4BF", "Previsto": "#C9A84C"},
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
            font_color="#E6EDF3",
            title_font_size=13,
            title_font_color="#8B949E",
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#21262D", visible=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=60, b=40, l=10, r=10),
        )
        st.plotly_chart(fig_tempo, use_container_width=True)
    else:
        st.info("Não há datas de pagamento registradas para gerar o gráfico temporal.")
else:
    st.info("Coluna 'Data pgto' não encontrada ou sem dados de pagamento.")


# --------------------------------------------------------------------------- #
# SEÇÃO 5 — TABELA DETALHADA COM FILTROS APLICADOS                             #
# --------------------------------------------------------------------------- #

st.markdown('<p class="section-title">📋 Detalhamento de Registros</p>', unsafe_allow_html=True)

# Indicador de filtros ativos
filtros_ativos = []
if sel_fornecedor:
    filtros_ativos.append(f"**Fornecedor:** {', '.join(sel_fornecedor)}")
if sel_grupos_label:
    filtros_ativos.append(f"**Situação:** {', '.join(sel_grupos_label)}")

if filtros_ativos:
    st.caption("Filtros ativos: " + " · ".join(filtros_ativos) + f" · {len(df_filtrado)} registros")
else:
    st.caption(f"Exibindo todos os {len(df_filtrado)} registros")

# Colunas a exibir na tabela (apenas as que existem no dataframe)
colunas_tabela = [c for c in [
    "tipo", "fornecedor", "req_mxm", "valor", "descritivo",
    "status", "grupo_status", "data_pgto", "termino_contrato",
    "doc_fiscal", "observacoes"
] if c in df_filtrado.columns]

df_exibir = df_filtrado[colunas_tabela].copy()

# Formata valor para exibição
if "valor" in df_exibir.columns:
    df_exibir["valor"] = df_exibir["valor"].apply(
        lambda v: fmt_brl(v) if pd.notna(v) and v != 0 else "—"
    )

# Adiciona emoji de grupo no status para leitura visual rápida
if "grupo_status" in df_exibir.columns and "status" in df_exibir.columns:
    df_exibir["status"] = df_exibir.apply(
        lambda r: f"{dh.EMOJI_GRUPO.get(r['grupo_status'], '')} {r['status']}",
        axis=1
    )
    df_exibir = df_exibir.drop(columns=["grupo_status"])

# Renomeia para português amigável
renomear = {
    "tipo": "Tipo", "fornecedor": "Fornecedor", "req_mxm": "Req. MXM",
    "valor": "Valor", "descritivo": "Descritivo", "status": "Status",
    "data_pgto": "Data Pgto", "termino_contrato": "Término Contrato",
    "doc_fiscal": "Doc. Fiscal", "observacoes": "Observações",
}
df_exibir = df_exibir.rename(columns={k: v for k, v in renomear.items() if k in df_exibir.columns})

st.dataframe(df_exibir, use_container_width=True, hide_index=True)

# Botão de download da tabela filtrada
csv_export = df_filtrado.to_csv(index=False, encoding="utf-8-sig")
st.download_button(
    label="⬇️  Exportar tabela filtrada (.csv)",
    data=csv_export,
    file_name="maz_pagamentos_filtrado.csv",
    mime="text/csv",
)


# --------------------------------------------------------------------------- #
# RODAPÉ                                                                        #
# --------------------------------------------------------------------------- #

st.markdown("""
<div style="
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid #21262D;
    text-align: center;
    color: #8B949E;
    font-size: 0.72rem;
">
    MAZ | Museu das Amazônias · IDG — Instituto de Desenvolvimento e Gestão<br>
    Dashboard Gerencial de Pagamentos · Versão Beta 1.0 · Dados atualizados via upload manual
</div>
""", unsafe_allow_html=True)
