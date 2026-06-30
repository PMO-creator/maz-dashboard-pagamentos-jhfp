# =============================================================================
# data_handler.py — Motor de Dados do Dashboard MAZ | Museu das Amazônias
# Responsabilidade: carregar, limpar e separar os dados sem duplicar valores.
#
# REGRA DE NEGÓCIO CENTRAL:
#   - "Compra"   → representa o VALOR TOTAL do contrato firmado (orçamento)
#   - "Pagamento"→ representa as PARCELAS efetivamente realizadas ou previstas
#   Nunca somar Compra + Pagamento no mesmo indicador financeiro.
# =============================================================================

import re
import pandas as pd
import streamlit as st


# --------------------------------------------------------------------------- #
# STATUS agrupados por "estado de saúde" — usados para colorização e alertas  #
# --------------------------------------------------------------------------- #
STATUS_GRUPOS = {
    "concluido": [
        "Pago",
        "Contrato/Template quitado",
    ],
    "em_andamento": [
        "Aprovado",
        "NF em análise",
        "Em aprovação",
        "Atendimento Compras/Financeiro",
    ],
    "alerta": [
        "Aguardando emissão de NF/DANFE",
        "Aguardando informações",
        "Aguardando Requisição de Pagamento",
        "Contrato/Template em aberto",
    ],
    "critico": [
        "Contrato/Template vencido",
    ],
}

# Mapeamento inverso: status → grupo (para lookup rápido)
STATUS_PARA_GRUPO = {
    status: grupo
    for grupo, lista in STATUS_GRUPOS.items()
    for status in lista
}

# Cores por grupo (hex) — alinhadas à paleta do config.toml
CORES_GRUPO = {
    "concluido":    "#2DD4BF",   # Verde-água: sucesso
    "em_andamento": "#C9A84C",   # Dourado: em movimento
    "alerta":       "#F59E0B",   # Âmbar: atenção
    "critico":      "#EF4444",   # Vermelho: urgente
}

# Emojis de suporte visual nos cards e tabelas
EMOJI_GRUPO = {
    "concluido":    "✅",
    "em_andamento": "🔄",
    "alerta":       "⚠️",
    "critico":      "🚨",
}


def sheets_url_para_csv(url: str) -> str | None:
    """
    Converte qualquer variante de URL do Google Sheets para a URL
    de exportação direta em CSV (sem autenticação — planilha pública).

    Formatos aceitos:
      - https://docs.google.com/spreadsheets/d/ID/edit#gid=GID
      - https://docs.google.com/spreadsheets/d/ID/edit?usp=sharing
      - https://docs.google.com/spreadsheets/d/ID/pub?gid=GID&...
      - https://docs.google.com/spreadsheets/d/ID/   (aba padrão)

    Retorna None se a URL não for reconhecida como Google Sheets.
    """
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        return None

    sheet_id = match.group(1)

    # Tenta extrair o gid (aba específica)
    gid_match = re.search(r"[#&?]gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else "0"

    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )


# TTL de 5 minutos: o Streamlit recarrega os dados do Sheets a cada 5 min
# automaticamente, sem o usuário precisar fazer nada.
@st.cache_data(ttl=300, show_spinner="Sincronizando com Google Sheets...")
def carregar_do_sheets(url_csv: str) -> pd.DataFrame:
    """
    Lê a planilha diretamente do Google Sheets via URL de exportação CSV.
    Requer que a planilha esteja compartilhada como 'qualquer pessoa com o link'.
    O cache TTL=300s garante atualização automática a cada 5 minutos.
    """
    df = pd.read_csv(url_csv, encoding="utf-8-sig")
    df = _normalizar_colunas(df)
    df = _converter_tipos(df)
    df = _enriquecer(df)
    return df


@st.cache_data(show_spinner="Carregando arquivo...")
def carregar_dados(arquivo) -> pd.DataFrame:
    """
    Carrega arquivo Excel ou CSV enviado manualmente pelo usuário.
    Fallback quando o Google Sheets não está configurado.
    """
    nome = arquivo.name.lower()

    if nome.endswith(".csv"):
        df = pd.read_csv(arquivo, encoding="utf-8-sig", sep=None, engine="python")
    else:
        df = pd.read_excel(arquivo, engine="openpyxl")

    df = _normalizar_colunas(df)
    df = _converter_tipos(df)
    df = _enriquecer(df)
    return df


def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Padroniza os nomes das colunas para snake_case sem acentos,
    tornando o código resistente a variações de digitação na planilha.
    Também remove linhas completamente vazias.
    """
    mapa = {
        # Coluna original (aproximada) → nome interno padronizado
        "Tipo":              "tipo",
        "Fornecedor":        "fornecedor",
        "Req. MXM":          "req_mxm",
        "Req MXM":           "req_mxm",
        "Valor":             "valor",
        "Descritivo":        "descritivo",
        "Término Contrato":  "termino_contrato",
        "Termino Contrato":  "termino_contrato",
        "Dias vencimento":   "dias_vencimento",
        "Link contrato":     "link_contrato",
        "Link Contrato":     "link_contrato",
        "Doc Fiscal":        "doc_fiscal",
        "Data pgto":         "data_pgto",
        "Data Pgto":         "data_pgto",
        "Status":            "status",
        "Observações":       "observacoes",
        "Observacoes":       "observacoes",
    }
    # Renomeia apenas as colunas que existem no dataframe
    df = df.rename(columns={k: v for k, v in mapa.items() if k in df.columns})
    df = df.dropna(how="all")
    return df


def _converter_tipos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garante que cada coluna tenha o tipo Python/Pandas correto:
    - 'valor'           → float  (trata R$, pontos e vírgulas)
    - 'data_pgto'       → datetime
    - 'termino_contrato'→ datetime
    - 'tipo'            → string em Title Case para comparações seguras
    """
    # --- Valor financeiro ---
    if "valor" in df.columns:
        df["valor"] = (
            df["valor"]
            .astype(str)
            .str.replace(r"[R$\s]", "", regex=True)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)

    # --- Datas ---
    for col in ["data_pgto", "termino_contrato"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], dayfirst=True, errors="coerce")

    # --- Tipo (Compra / Pagamento) ---
    if "tipo" in df.columns:
        df["tipo"] = df["tipo"].astype(str).str.strip().str.title()

    # --- Status ---
    if "status" in df.columns:
        df["status"] = df["status"].astype(str).str.strip()
        df["status"] = df["status"].replace("nan", "Sem status")

    # --- Fornecedor ---
    if "fornecedor" in df.columns:
        df["fornecedor"] = df["fornecedor"].astype(str).str.strip()

    return df


def _enriquecer(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adiciona colunas derivadas que alimentam os KPIs e gráficos:
    - 'grupo_status'  → categoria de saúde (concluido, alerta, etc.)
    - 'mes_pgto'      → mês/ano de pagamento para série temporal
    """
    if "status" in df.columns:
        df["grupo_status"] = df["status"].map(
            lambda s: STATUS_PARA_GRUPO.get(s, "alerta")
        )

    if "data_pgto" in df.columns:
        df["mes_pgto"] = df["data_pgto"].dt.to_period("M").astype(str)

    return df


# --------------------------------------------------------------------------- #
# Funções de separação — CORAÇÃO da regra de negócio anti-duplicidade         #
# --------------------------------------------------------------------------- #

def separar_por_tipo(df: pd.DataFrame):
    """
    Retorna dois DataFrames separados:
      - df_compras   → linhas com tipo == 'Compra'  (orçamento contratado)
      - df_pagamentos→ linhas com tipo == 'Pagamento' (fluxo de caixa real)

    Usar df_compras  para KPIs de orçamento/contratação.
    Usar df_pagamentos para KPIs de pagamentos realizados e previstos.
    NUNCA somar os dois para o mesmo indicador financeiro.
    """
    if "tipo" not in df.columns:
        return df.copy(), pd.DataFrame(columns=df.columns)

    df_compras    = df[df["tipo"] == "Compra"].copy()
    df_pagamentos = df[df["tipo"] == "Pagamento"].copy()
    return df_compras, df_pagamentos


def calcular_kpis(df: pd.DataFrame) -> dict:
    """
    Calcula todos os KPIs gerenciais a partir do DataFrame completo.
    Retorna um dicionário com valores prontos para exibição nos cards.
    """
    df_compras, df_pag = separar_por_tipo(df)

    # KPI 1 — Orçamento Total Contratado (soma das Compras)
    orcamento_total = df_compras["valor"].sum() if "valor" in df_compras.columns else 0

    # KPI 2 — Total Pago (Pagamentos com status "Pago")
    pago = df_pag[df_pag["status"] == "Pago"]["valor"].sum() if "status" in df_pag.columns else 0

    # KPI 3 — Saldo a Pagar (Pagamentos ainda não pagos)
    a_pagar = df_pag[df_pag["status"] != "Pago"]["valor"].sum() if "status" in df_pag.columns else 0

    # KPI 4 — Pagamentos "parados" em fases de gargalo
    status_gargalo = STATUS_GRUPOS["alerta"] + STATUS_GRUPOS["em_andamento"]
    em_gargalo = (
        df_pag[df_pag["status"].isin(status_gargalo)]["valor"].sum()
        if "status" in df_pag.columns else 0
    )

    # KPI 5 — Contratos vencidos (Compras com status crítico)
    vencidos = len(df_compras[df_compras["status"].isin(STATUS_GRUPOS["critico"])]) if "status" in df_compras.columns else 0

    # KPI 6 — Total de fornecedores únicos
    fornecedores = df["fornecedor"].nunique() if "fornecedor" in df.columns else 0

    # KPI 7 — Percentual de execução orçamentária
    perc_execucao = (pago / orcamento_total * 100) if orcamento_total > 0 else 0

    return {
        "orcamento_total":  orcamento_total,
        "pago":             pago,
        "a_pagar":          a_pagar,
        "em_gargalo":       em_gargalo,
        "vencidos":         vencidos,
        "fornecedores":     fornecedores,
        "perc_execucao":    perc_execucao,
    }


def aplicar_filtros(df: pd.DataFrame, fornecedores: list, grupos_status: list) -> pd.DataFrame:
    """
    Aplica filtros interativos selecionados pelo usuário na sidebar.
    Recebe listas vazias para "sem filtro aplicado" (retorna tudo).
    """
    df_filtrado = df.copy()

    if fornecedores:
        df_filtrado = df_filtrado[df_filtrado["fornecedor"].isin(fornecedores)]

    if grupos_status:
        df_filtrado = df_filtrado[df_filtrado["grupo_status"].isin(grupos_status)]

    return df_filtrado
