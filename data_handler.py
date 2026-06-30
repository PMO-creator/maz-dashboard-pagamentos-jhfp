# =============================================================================
# data_handler.py — Motor de Dados do Dashboard MAZ | Museu das Amazônias
# Responsabilidade: carregar, limpar e separar os dados sem duplicar valores.
#
# REGRA DE NEGÓCIO CENTRAL:
#   - "Compra"   → representa o VALOR TOTAL do contrato firmado (orçamento)
#   - "Pagamento"→ representa as PARCELAS efetivamente realizadas ou previstas
#   Nunca somar Compra + Pagamento no mesmo indicador financeiro.
# =============================================================================

import hashlib
import json
import os
import re
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st


# --------------------------------------------------------------------------- #
# GESTÃO DE ACESSOS — Owner / Admin / Viewer                                   #
# O Owner vem das Secrets do Streamlit (login fixo, não editável pela UI).    #
# Admins e Viewers são cadastrados pelo Owner e persistidos em disco.         #
# --------------------------------------------------------------------------- #

_USUARIOS_FILE = os.path.join(os.path.dirname(__file__), ".dashboard_usuarios.json")

PAPEL_OWNER  = "owner"
PAPEL_ADMIN  = "admin"
PAPEL_VIEWER = "viewer"


def _hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def carregar_usuarios() -> dict:
    """Retorna {login: {senha_hash, papel, nome}} dos usuários cadastrados (sem o Owner)."""
    try:
        with open(_USUARIOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def salvar_usuarios(usuarios: dict) -> None:
    with open(_USUARIOS_FILE, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, ensure_ascii=False, indent=2)


def adicionar_usuario(login: str, senha: str, papel: str, nome: str) -> None:
    usuarios = carregar_usuarios()
    usuarios[login.strip()] = {
        "senha_hash": _hash_senha(senha),
        "papel": papel,
        "nome": nome.strip() or login.strip(),
    }
    salvar_usuarios(usuarios)


def remover_usuario(login: str) -> None:
    usuarios = carregar_usuarios()
    usuarios.pop(login.strip(), None)
    salvar_usuarios(usuarios)


def autenticar(login: str, senha: str, owner_login: str, owner_senha: str) -> dict | None:
    """
    Verifica credenciais contra o Owner (Secrets) e os usuários cadastrados (disco).
    Retorna {"papel": ..., "nome": ..., "login": ...} se autenticado, senão None.
    """
    login = login.strip()

    if owner_login and login == owner_login and senha == owner_senha:
        return {"papel": PAPEL_OWNER, "nome": "Owner", "login": login}

    usuarios = carregar_usuarios()
    registro = usuarios.get(login)
    if registro and registro.get("senha_hash") == _hash_senha(senha):
        return {"papel": registro.get("papel", PAPEL_VIEWER), "nome": registro.get("nome", login), "login": login}

    return None


# --------------------------------------------------------------------------- #
# LOG DE ALTERAÇÕES — detecta e persiste mudanças na planilha a cada 1 hora   #
# --------------------------------------------------------------------------- #

_SNAPSHOT_FILE = os.path.join(os.path.dirname(__file__), ".dashboard_snapshot.json")
_LOG_FILE      = os.path.join(os.path.dirname(__file__), ".dashboard_changelog.json")
_LOG_INTERVALO = timedelta(hours=1)
_LOG_MAX_ENTRADAS = 300   # máximo de entradas no histórico

_CAMPOS_MONITORADOS = [
    "tipo", "fornecedor", "valor", "status",
    "req_mxm", "data_pgto", "doc_fiscal",
    "termino_contrato", "observacoes",
]


def _df_para_snapshot(df: pd.DataFrame) -> list[dict]:
    cols = [c for c in _CAMPOS_MONITORADOS if c in df.columns]
    return df[cols].fillna("").astype(str).to_dict(orient="records")


def carregar_snapshot() -> tuple[list[dict], str | None]:
    try:
        with open(_SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("dados", []), data.get("ultima_verificacao")
    except Exception:
        return [], None


def salvar_snapshot(df: pd.DataFrame) -> None:
    data = {
        "ultima_verificacao": datetime.now().isoformat(),
        "dados": _df_para_snapshot(df),
    }
    with open(_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def carregar_log() -> list[dict]:
    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("entradas", [])
    except Exception:
        return []


def salvar_log(entradas: list[dict]) -> None:
    with open(_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump({"entradas": entradas[-_LOG_MAX_ENTRADAS:]}, f, ensure_ascii=False)


def detectar_alteracoes(df_atual: pd.DataFrame, snapshot_ant: list[dict]) -> list[dict]:
    """Compara o DataFrame atual com o snapshot anterior linha a linha."""
    snap_at = _df_para_snapshot(df_atual)
    alteracoes = []

    for i in range(max(len(snap_at), len(snapshot_ant))):
        if i >= len(snap_at):
            row = snapshot_ant[i]
            alteracoes.append({
                "linha": i + 1,
                "fornecedor": row.get("fornecedor", "—"),
                "tipo": row.get("tipo", "—"),
                "campo": "(linha)",
                "de": "existia",
                "para": "removida",
            })
        elif i >= len(snapshot_ant):
            row = snap_at[i]
            alteracoes.append({
                "linha": i + 1,
                "fornecedor": row.get("fornecedor", "—"),
                "tipo": row.get("tipo", "—"),
                "campo": "(linha)",
                "de": "—",
                "para": "adicionada",
            })
        else:
            row_at  = snap_at[i]
            row_ant = snapshot_ant[i]
            for campo in _CAMPOS_MONITORADOS:
                v_at  = row_at.get(campo, "")
                v_ant = row_ant.get(campo, "")
                if v_at != v_ant:
                    alteracoes.append({
                        "linha": i + 1,
                        "fornecedor": row_at.get("fornecedor") or row_ant.get("fornecedor") or "—",
                        "tipo": row_at.get("tipo", "—"),
                        "campo": campo,
                        "de": v_ant or "—",
                        "para": v_at or "—",
                    })

    return alteracoes


def verificar_e_logar(df: pd.DataFrame) -> int:
    """Roda a cada carregamento. Só grava no log se passou 1h desde a última verificação.
    Retorna o número de alterações detectadas (0 se ainda não era hora de verificar)."""
    snapshot_ant, ultima_verif = carregar_snapshot()

    agora = datetime.now()
    if ultima_verif:
        ultima_dt = datetime.fromisoformat(ultima_verif)
        if agora - ultima_dt < _LOG_INTERVALO:
            return 0  # ainda dentro da janela de 1h, não faz nada

    # Passou 1h — detecta mudanças e salva novo snapshot
    alteracoes = detectar_alteracoes(df, snapshot_ant) if snapshot_ant else []
    salvar_snapshot(df)

    if alteracoes:
        entradas = carregar_log()
        entradas.append({
            "horario": agora.isoformat(),
            "total": len(alteracoes),
            "alteracoes": alteracoes,
        })
        salvar_log(entradas)
        return len(alteracoes)

    return 0


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


def sheets_url_para_csv(url: str, nome_aba: str = "") -> str | None:
    """
    Converte qualquer variante de URL do Google Sheets para URL de exportação CSV.

    Estratégia de seleção de aba (em ordem de prioridade):
      1. nome_aba informado → usa API gviz (?sheet=NOME), mais confiável
      2. gid presente na URL → usa endpoint /export?gid=GID
      3. Nenhum dos dois → usa gid=0 (primeira aba, pode falhar se foi reordenada)

    A API gviz é preferível pois aceita o nome exato da aba, evitando
    o erro 400 que ocorre quando gid=0 não corresponde a nenhuma aba real.
    """
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        return None

    sheet_id = match.group(1)

    # Prioridade 1: nome da aba informado pelo usuário → API gviz (mais robusta)
    if nome_aba and nome_aba.strip():
        aba = nome_aba.strip()
        return (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}"
            f"/gviz/tq?tqx=out:csv&sheet={aba}"
        )

    # Prioridade 2: gid presente na URL colada (usuário estava na aba certa ao copiar)
    gid_match = re.search(r"[#&?]gid=(\d+)", url)
    if gid_match:
        return (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}"
            f"/export?format=csv&gid={gid_match.group(1)}"
        )

    # Fallback: tenta a primeira aba via gviz sem especificar nome
    # (mais tolerante que gid=0 quando a ordem das abas foi alterada)
    return (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/gviz/tq?tqx=out:csv"
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
    # Lê sem cabeçalho primeiro para detectar automaticamente em qual linha
    # estão os nomes reais das colunas (ignora linhas de título/data do topo).
    df_raw = pd.read_csv(url_csv, encoding="utf-8-sig", header=None)

    # Identifica a linha-cabeçalho: primeira linha que contém "Tipo" em alguma célula
    # (comparação case-insensitive). Isso torna o código robusto a qualquer número
    # de linhas de título acima dos dados reais.
    header_row = 0
    for i, row in df_raw.iterrows():
        valores = row.astype(str).str.strip().str.lower().tolist()
        if "tipo" in valores:
            header_row = i
            break

    # Relê com o cabeçalho correto já identificado
    df = pd.read_csv(url_csv, encoding="utf-8-sig", header=header_row)
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
        df = pd.read_csv(arquivo, encoding="utf-8-sig", sep=None, engine="python", header=None)
        header_row = 0
        for i, row in df.iterrows():
            if "tipo" in row.astype(str).str.strip().str.lower().tolist():
                header_row = i
                break
        arquivo.seek(0)
        df = pd.read_csv(arquivo, encoding="utf-8-sig", sep=None, engine="python", header=header_row)
    else:
        # Para Excel: lê sem cabeçalho, detecta a linha, relê corretamente
        df_raw = pd.read_excel(arquivo, engine="openpyxl", header=None)
        header_row = 0
        for i, row in df_raw.iterrows():
            if "tipo" in row.astype(str).str.strip().str.lower().tolist():
                header_row = i
                break
        arquivo.seek(0)
        df = pd.read_excel(arquivo, engine="openpyxl", header=header_row)

    df = _normalizar_colunas(df)
    df = _converter_tipos(df)
    df = _enriquecer(df)
    return df


def _normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Padroniza os nomes das colunas para snake_case sem acentos.
    Usa comparação case-insensitive e ignora espaços extras para ser
    resistente às variações que a API gviz do Google Sheets pode retornar.
    Remove linhas completamente vazias.
    """
    # Mapa: versão normalizada (lower + strip) → nome interno padronizado
    mapa_normalizado = {
        "tipo":               "tipo",
        "fornecedor":         "fornecedor",
        "req. mxm":           "req_mxm",
        "req mxm":            "req_mxm",
        "requisição mxm":     "req_mxm",
        "valor":              "valor",
        "descritivo":         "descritivo",
        "término contrato":   "termino_contrato",
        "termino contrato":   "termino_contrato",
        "término do contrato":"termino_contrato",
        "dias vencimento":    "dias_vencimento",
        "link contrato":      "link_contrato",
        "link do contrato":   "link_contrato",
        "doc fiscal":         "doc_fiscal",
        "documento fiscal":   "doc_fiscal",
        "data pgto":          "data_pgto",
        "data de pagamento":  "data_pgto",
        "data pagamento":     "data_pgto",
        "status":             "status",
        "situação":           "status",
        "situacao":           "status",
        "observações":        "observacoes",
        "observacoes":        "observacoes",
        "observação":         "observacoes",
    }

    # Constrói mapa real: nome original → nome interno (via lookup normalizado)
    renomear = {}
    for col in df.columns:
        chave = str(col).strip().lower()
        if chave in mapa_normalizado:
            renomear[col] = mapa_normalizado[chave]

    df = df.rename(columns=renomear)

    # --- Mapeamento posicional para colunas "Unnamed: X" ---
    # O Google Sheets retorna células mescladas do cabeçalho como "Unnamed: X".
    # Este mapa corrige pela posição exata detectada na planilha MAZ.
    # Se a ordem das colunas mudar, basta atualizar os índices abaixo.
    mapa_posicional = {
        "Unnamed: 3":  "valor",            # col D — valor financeiro do contrato/parcela
        "Unnamed: 4":  "req_mxm",          # col E — ID da requisição no ERP MXM
        "Unnamed: 6":  "dias_vencimento",  # col G — contador de dias (negativo = vencido)
        "Unnamed: 7":  "termino_contrato", # col H — data de vigência final do contrato
        "Unnamed: 9":  "data_pgto",        # col J — data de pagamento ou previsão
        "Unnamed: 10": "doc_fiscal",       # col K — número da NF/DANFE
    }
    df = df.rename(columns={k: v for k, v in mapa_posicional.items() if k in df.columns})

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


def _soma_segura(df: pd.DataFrame, col_filtro: str, valor_filtro, col_soma: str, operador: str = "==") -> float:
    """
    Soma col_soma após filtrar col_filtro, verificando existência de ambas as colunas.
    operador: "==" (igual), "!=" (diferente), "isin" (lista de valores).
    Retorna 0.0 se qualquer coluna estiver ausente.
    """
    if col_filtro not in df.columns or col_soma not in df.columns:
        return 0.0
    if operador == "==":
        mask = df[col_filtro] == valor_filtro
    elif operador == "!=":
        mask = df[col_filtro] != valor_filtro
    elif operador == "isin":
        mask = df[col_filtro].isin(valor_filtro)
    else:
        return 0.0
    return df.loc[mask, col_soma].sum()


def calcular_kpis(df: pd.DataFrame) -> dict:
    """
    Calcula todos os KPIs gerenciais a partir do DataFrame completo.
    Retorna um dicionário com valores prontos para exibição nos cards.
    Usa _soma_segura() para nunca lançar KeyError mesmo com colunas ausentes.
    """
    df_compras, df_pag = separar_por_tipo(df)

    # KPI 1 — Orçamento Total Contratado (soma das Compras)
    orcamento_total = df_compras["valor"].sum() if "valor" in df_compras.columns else 0

    # KPI 2 — Total Pago
    pago = _soma_segura(df_pag, "status", "Pago", "valor", "==")

    # KPI 3 — Saldo a Pagar
    a_pagar = _soma_segura(df_pag, "status", "Pago", "valor", "!=")

    # KPI 4 — Valor parado em fases de gargalo
    status_gargalo = STATUS_GRUPOS["alerta"] + STATUS_GRUPOS["em_andamento"]
    em_gargalo = _soma_segura(df_pag, "status", status_gargalo, "valor", "isin")

    # KPI 5 — Contratos vencidos
    vencidos = (
        len(df_compras[df_compras["status"].isin(STATUS_GRUPOS["critico"])])
        if "status" in df_compras.columns else 0
    )

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


def agrupar_hierarquia(df: pd.DataFrame) -> list[tuple]:
    """
    Agrupa as linhas de Pagamento sob sua respectiva linha de Compra,
    usando a ORDEM SEQUENCIAL das linhas na planilha (não depende de chave).

    Retorna lista de tuplas: (Series compra, DataFrame pagamentos_filhos)
    Compras sem nenhum Pagamento abaixo retornam DataFrame vazio como filhos.
    """
    grupos = []
    compra_atual = None
    pagamentos_acumulados = []

    for _, row in df.iterrows():
        tipo = str(row.get("tipo", "")).strip().title()

        if tipo == "Compra":
            # Fecha o grupo anterior antes de abrir um novo
            if compra_atual is not None:
                grupos.append((
                    compra_atual,
                    pd.DataFrame(pagamentos_acumulados) if pagamentos_acumulados
                    else pd.DataFrame(columns=df.columns)
                ))
            compra_atual = row
            pagamentos_acumulados = []

        elif tipo == "Pagamento" and compra_atual is not None:
            pagamentos_acumulados.append(row.to_dict())

    # Fecha o último grupo
    if compra_atual is not None:
        grupos.append((
            compra_atual,
            pd.DataFrame(pagamentos_acumulados) if pagamentos_acumulados
            else pd.DataFrame(columns=df.columns)
        ))

    return grupos


# Status que indicam contrato/pagamento encerrado
STATUS_QUITADO = STATUS_GRUPOS["concluido"]  # ["Pago", "Contrato/Template quitado"]
