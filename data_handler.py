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
from datetime import date, datetime, timedelta

import gspread
import pandas as pd
import pyotp
import streamlit as st


# --------------------------------------------------------------------------- #
# GESTÃO DE ACESSOS — Owner / Admin / Viewer                                   #
# O Owner vem das Secrets do Streamlit (login fixo, não editável pela UI).    #
# Admins, Viewers e Requisitantes são cadastrados pelo Owner (ou por          #
# autocadastro aprovado) e persistidos na PRÓPRIA PLANILHA — nunca em disco.  #
# O disco local do Streamlit Community Cloud é efêmero: qualquer redeploy,    #
# reinício por inatividade ou alteração de Secrets recria o container do     #
# zero e apaga tudo que não estiver versionado no Git ou salvo na planilha.  #
# Um arquivo local (.dashboard_usuarios.json) já causou perda de cadastros    #
# dessa forma — por isso a fonte de verdade agora é a planilha, do mesmo     #
# jeito que já era feito com Aprovações.                                     #
# --------------------------------------------------------------------------- #

PAPEL_OWNER        = "owner"
PAPEL_ADMIN        = "admin"
PAPEL_VIEWER       = "viewer"
PAPEL_REQUISITANTE = "requisitante"

_ABA_USUARIOS   = "_Usuarios"
_HEADER_USUARIOS = ["login", "senha_hash", "papel", "nome", "totp_secret"]

_ABA_SOLICITACOES_ACESSO   = "_SolicitacoesAcesso"
_HEADER_SOLICITACOES_ACESSO = ["login", "senha_hash", "papel", "nome", "data_solicitacao"]

# Papéis que uma pessoa pode pedir por autocadastro — Admin fica de fora de
# propósito; só o Owner promove alguém a Admin, manualmente, depois.
PAPEIS_AUTOCADASTRO = [PAPEL_VIEWER, PAPEL_REQUISITANTE]


class LoginBloqueadoError(Exception):
    """Levantada quando um login excedeu o número de tentativas falhas recentes."""


def _hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def _obter_aba_usuarios(sheets_url: str) -> gspread.Worksheet:
    """Abre a aba de usuários cadastrados; cria com o cabeçalho padrão na 1ª vez."""
    planilha = _abrir_planilha(sheets_url)
    try:
        return planilha.worksheet(_ABA_USUARIOS)
    except gspread.exceptions.WorksheetNotFound:
        ws = planilha.add_worksheet(title=_ABA_USUARIOS, rows=100, cols=len(_HEADER_USUARIOS))
        ws.append_row(_HEADER_USUARIOS, value_input_option="RAW")
        return ws


def _obter_aba_solicitacoes_acesso(sheets_url: str) -> gspread.Worksheet:
    """Abre a aba de solicitações de acesso pendentes; cria na 1ª vez."""
    planilha = _abrir_planilha(sheets_url)
    try:
        return planilha.worksheet(_ABA_SOLICITACOES_ACESSO)
    except gspread.exceptions.WorksheetNotFound:
        ws = planilha.add_worksheet(
            title=_ABA_SOLICITACOES_ACESSO, rows=100, cols=len(_HEADER_SOLICITACOES_ACESSO),
        )
        ws.append_row(_HEADER_SOLICITACOES_ACESSO, value_input_option="RAW")
        return ws


def carregar_usuarios(sheets_url: str) -> dict:
    """Retorna {login: {senha_hash, papel, nome, totp_secret}} dos usuários cadastrados (sem o Owner)."""
    try:
        ws = _obter_aba_usuarios(sheets_url)
        linhas = ws.get_all_values()[1:]  # pula o cabeçalho
        return {
            linha[0]: {
                "senha_hash": linha[1], "papel": linha[2], "nome": linha[3],
                "totp_secret": linha[4] if len(linha) > 4 else "",
            }
            for linha in linhas if linha and linha[0]
        }
    except Exception:
        return {}


def salvar_usuarios(sheets_url: str, usuarios: dict) -> None:
    """Reescreve a aba de usuários por completo a partir do dicionário em memória."""
    ws = _obter_aba_usuarios(sheets_url)
    ws.clear()
    linhas = [_HEADER_USUARIOS] + [
        [login, dados["senha_hash"], dados["papel"], dados["nome"], dados.get("totp_secret", "")]
        for login, dados in usuarios.items()
    ]
    ws.update(linhas, value_input_option="RAW")


def _adicionar_usuario_hash(sheets_url: str, login: str, senha_hash: str, papel: str, nome: str) -> None:
    """Grava o usuário já com o hash pronto — usado tanto pelo cadastro direto
    (Owner) quanto pela aprovação de uma solicitação de acesso (o hash é
    calculado no momento da solicitação; o Owner nunca vê a senha em texto).
    Preserva o segredo de 2FA se o login já existia (ex: Owner reaprovando
    depois de rejeitar por engano)."""
    usuarios = carregar_usuarios(sheets_url)
    login = login.strip()
    totp_existente = usuarios.get(login, {}).get("totp_secret", "")
    usuarios[login] = {
        "senha_hash": senha_hash,
        "papel": papel,
        "nome": nome.strip() or login,
        "totp_secret": totp_existente,
    }
    salvar_usuarios(sheets_url, usuarios)


def definir_totp_usuario(sheets_url: str, login: str, secret: str) -> None:
    """Ativa (secret não-vazio) ou desativa (secret == '') o 2FA de um usuário cadastrado."""
    usuarios = carregar_usuarios(sheets_url)
    login = login.strip()
    if login not in usuarios:
        return
    usuarios[login]["totp_secret"] = secret
    salvar_usuarios(sheets_url, usuarios)


def gerar_segredo_totp() -> str:
    return pyotp.random_base32()


def obter_totp_uri(secret: str, login: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=login, issuer_name="MAZ Dashboard")


def verificar_totp(secret: str, codigo: str) -> bool:
    if not secret or not codigo:
        return False
    try:
        return pyotp.totp.TOTP(secret).verify(codigo.strip(), valid_window=1)
    except Exception:
        return False


def adicionar_usuario(sheets_url: str, login: str, senha: str, papel: str, nome: str) -> None:
    _adicionar_usuario_hash(sheets_url, login, _hash_senha(senha), papel, nome)


def remover_usuario(sheets_url: str, login: str) -> None:
    usuarios = carregar_usuarios(sheets_url)
    usuarios.pop(login.strip(), None)
    salvar_usuarios(sheets_url, usuarios)


# --------------------------------------------------------------------------- #
# SOLICITAÇÕES DE ACESSO — autocadastro na tela de login, aprovado pelo Owner. #
# A senha é hasheada já na solicitação: o Owner aprova o cadastro sem nunca   #
# ver a senha em texto puro. Também persistido na planilha (mesmo motivo).   #
# --------------------------------------------------------------------------- #

def carregar_solicitacoes_acesso(sheets_url: str) -> list[dict]:
    try:
        ws = _obter_aba_solicitacoes_acesso(sheets_url)
        linhas = ws.get_all_values()[1:]
        return [
            {"login": l[0], "senha_hash": l[1], "papel": l[2], "nome": l[3],
             "data_solicitacao": l[4] if len(l) > 4 else ""}
            for l in linhas if l and l[0]
        ]
    except Exception:
        return []


def _salvar_solicitacoes_acesso(sheets_url: str, lista: list[dict]) -> None:
    ws = _obter_aba_solicitacoes_acesso(sheets_url)
    ws.clear()
    linhas = [_HEADER_SOLICITACOES_ACESSO] + [
        [s["login"], s["senha_hash"], s["papel"], s["nome"], s.get("data_solicitacao", "")]
        for s in lista
    ]
    ws.update(linhas, value_input_option="RAW")


def criar_solicitacao_acesso(sheets_url: str, login: str, senha: str, papel: str, nome: str) -> str | None:
    """
    Registra um pedido de acesso pendente. Retorna None se deu certo, ou uma
    mensagem de erro se o login já estiver em uso (pelo Owner, por um usuário
    já cadastrado, ou por outra solicitação ainda não avaliada).
    """
    login = login.strip()
    if not login or not senha:
        return "Login e senha são obrigatórios."
    if papel not in PAPEIS_AUTOCADASTRO:
        return "Papel inválido para autocadastro."

    usuarios = carregar_usuarios(sheets_url)
    pendentes = carregar_solicitacoes_acesso(sheets_url)
    if login in usuarios:
        return "Este login já está cadastrado."
    if any(s["login"] == login for s in pendentes):
        return "Já existe uma solicitação pendente para este login."

    pendentes.append({
        "login": login,
        "senha_hash": _hash_senha(senha),
        "papel": papel,
        "nome": nome.strip() or login,
        "data_solicitacao": datetime.now().isoformat(),
    })
    _salvar_solicitacoes_acesso(sheets_url, pendentes)
    return None


def aprovar_solicitacao_acesso(sheets_url: str, login: str) -> None:
    """Cadastra o usuário com o papel pedido (ou ajustado pelo Owner) e remove
    a solicitação da fila."""
    pendentes = carregar_solicitacoes_acesso(sheets_url)
    solicitacao = next((s for s in pendentes if s["login"] == login), None)
    if not solicitacao:
        return
    _adicionar_usuario_hash(
        sheets_url, solicitacao["login"], solicitacao["senha_hash"],
        solicitacao["papel"], solicitacao["nome"],
    )
    _salvar_solicitacoes_acesso(sheets_url, [s for s in pendentes if s["login"] != login])


def rejeitar_solicitacao_acesso(sheets_url: str, login: str) -> None:
    pendentes = carregar_solicitacoes_acesso(sheets_url)
    _salvar_solicitacoes_acesso(sheets_url, [s for s in pendentes if s["login"] != login])


# --------------------------------------------------------------------------- #
# BLOQUEIO POR TENTATIVAS — protege contra força bruta de senha.              #
# Persistido na planilha (não em disco/sessão) porque um atacante pode        #
# simplesmente abrir uma sessão nova a cada tentativa — bloquear por login,   #
# de forma global, é o que realmente freia um ataque automatizado.            #
# --------------------------------------------------------------------------- #

_ABA_TENTATIVAS_LOGIN   = "_TentativasLogin"
_HEADER_TENTATIVAS_LOGIN = ["login", "timestamp"]

LOGIN_MAX_TENTATIVAS  = 5
LOGIN_JANELA_MINUTOS  = 15


def _obter_aba_tentativas(sheets_url: str) -> gspread.Worksheet:
    planilha = _abrir_planilha(sheets_url)
    try:
        return planilha.worksheet(_ABA_TENTATIVAS_LOGIN)
    except gspread.exceptions.WorksheetNotFound:
        ws = planilha.add_worksheet(
            title=_ABA_TENTATIVAS_LOGIN, rows=200, cols=len(_HEADER_TENTATIVAS_LOGIN),
        )
        ws.append_row(_HEADER_TENTATIVAS_LOGIN, value_input_option="RAW")
        return ws


def _tentativas_recentes(sheets_url: str, login: str) -> list[datetime]:
    """Lê as tentativas falhas do login nos últimos LOGIN_JANELA_MINUTOS minutos
    (e aproveita a leitura pra descartar linhas antigas de QUALQUER login, o
    que evita a aba crescer pra sempre sem precisar de um job separado)."""
    limite = datetime.now() - timedelta(minutes=LOGIN_JANELA_MINUTOS)
    ws = _obter_aba_tentativas(sheets_url)
    linhas = ws.get_all_values()[1:]

    validas = []
    for l in linhas:
        if not l or not l[0]:
            continue
        try:
            ts = datetime.fromisoformat(l[1])
        except Exception:
            continue
        if ts >= limite:
            validas.append((l[0], ts))

    if len(validas) != len([l for l in linhas if l and l[0]]):
        novas_linhas = [_HEADER_TENTATIVAS_LOGIN] + [[lg, ts.isoformat()] for lg, ts in validas]
        ws.clear()
        ws.update(novas_linhas, value_input_option="RAW")

    return [ts for lg, ts in validas if lg == login]


def _registrar_tentativa_falha(sheets_url: str, login: str) -> None:
    ws = _obter_aba_tentativas(sheets_url)
    ws.append_row([login, datetime.now().isoformat()], value_input_option="RAW")


def autenticar(
    sheets_url: str, login: str, senha: str,
    owner_login: str, owner_senha: str, owner_totp_secret: str = "",
) -> dict | None:
    """
    Verifica credenciais contra o Owner (Secrets) e os usuários cadastrados (planilha).
    Retorna {"papel", "nome", "login", "totp_secret"} se a senha bateu, ou None se
    errou. Levanta LoginBloqueadoError se o login excedeu as tentativas recentes.
    O retorno não confirma a sessão sozinho quando há totp_secret — o chamador
    ainda precisa validar o código de 2FA antes de autenticar de fato.
    """
    login = login.strip()

    if sheets_url:
        try:
            if len(_tentativas_recentes(sheets_url, login)) >= LOGIN_MAX_TENTATIVAS:
                raise LoginBloqueadoError(
                    f"Muitas tentativas de login com esse usuário. "
                    f"Aguarde {LOGIN_JANELA_MINUTOS} minutos e tente novamente."
                )
        except LoginBloqueadoError:
            raise
        except Exception:
            pass  # falha ao checar tentativas não deve travar o login em si

    if owner_login and login == owner_login and senha == owner_senha:
        return {"papel": PAPEL_OWNER, "nome": "Owner", "login": login, "totp_secret": owner_totp_secret}

    if not sheets_url:
        return None

    usuarios = carregar_usuarios(sheets_url)
    registro = usuarios.get(login)
    if registro and registro.get("senha_hash") == _hash_senha(senha):
        return {
            "papel": registro.get("papel", PAPEL_VIEWER),
            "nome": registro.get("nome", login),
            "login": login,
            "totp_secret": registro.get("totp_secret", ""),
        }

    try:
        _registrar_tentativa_falha(sheets_url, login)
    except Exception:
        pass  # não deixa uma falha de escrita mascarar o "senha incorreta"

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
# Mantida como CORES_GRUPO (tema claro) por compatibilidade com código já
# existente; use cores_grupo(tema) nos pontos novos/atualizados para o
# modo escuro responder corretamente.
CORES_GRUPO_CLARO = {
    "concluido":    "#4F6A1E",   # Verde-folha (marca): pago / quitado — a floresta
    "em_andamento": "#3E9489",   # Verde-água (marca): em movimento — o rio que corre
    "alerta":       "#E8920A",   # Laranja-sol (marca): atenção
    "critico":      "#E02838",   # Vermelho-urucum (marca): urgência
}
CORES_GRUPO_ESCURO = {
    "concluido":    "#7FB251",   # Verde-folha, aclarado para contraste no escuro
    "em_andamento": "#5FC4B6",   # Verde-água, aclarado
    "alerta":       "#F2AC4E",   # Laranja-sol, aclarado
    "critico":      "#F16B74",   # Vermelho-urucum, aclarado
}
CORES_GRUPO = CORES_GRUPO_CLARO


def cores_grupo(tema: str = "claro") -> dict:
    """Retorna o dicionário de cores por grupo de status, conforme o tema ativo."""
    return CORES_GRUPO_ESCURO if tema == "escuro" else CORES_GRUPO_CLARO


# Emojis de suporte visual nos cards e tabelas
EMOJI_GRUPO = {
    "concluido":    "✅",
    "em_andamento": "🔄",
    "alerta":       "⚠️",
    "critico":      "🚨",
}

# Lista plana de todos os status válidos, na ordem em que aparecem nos grupos
# (usada para popular os selectbox dos formulários de lançamento).
STATUS_TODOS = [s for grupo in STATUS_GRUPOS.values() for s in grupo]


# --------------------------------------------------------------------------- #
# PRAZOS DE CONTRATO — classificação por urgência de vencimento               #
# Baseada em 'termino_contrato' (data real, preenchida manualmente após       #
# leitura do contrato) comparada com a data de hoje.                          #
# Reaproveita a mesma paleta de 4 cores da marca usada em CORES_GRUPO.        #
# --------------------------------------------------------------------------- #

PRAZO_VENCIDO    = "vencido"
PRAZO_URGENTE    = "urgente"     # vence em até 30 dias
PRAZO_ATENCAO    = "atencao"     # vence em 31 a 90 dias
PRAZO_TRANQUILO  = "tranquilo"   # vence em mais de 90 dias
PRAZO_SEM_DATA   = "sem_data"    # término do contrato não preenchido ainda

CORES_PRAZO_CLARO = {
    PRAZO_VENCIDO:   "#E02838",  # vermelho-urucum
    PRAZO_URGENTE:   "#E8920A",  # laranja-sol
    PRAZO_ATENCAO:   "#3E9489",  # verde-água
    PRAZO_TRANQUILO: "#4F6A1E",  # verde-folha
    PRAZO_SEM_DATA:  "#6B6552",  # neutro
}
CORES_PRAZO_ESCURO = {
    PRAZO_VENCIDO:   "#F16B74",
    PRAZO_URGENTE:   "#F2AC4E",
    PRAZO_ATENCAO:   "#5FC4B6",
    PRAZO_TRANQUILO: "#7FB251",
    PRAZO_SEM_DATA:  "#9BAAA0",
}
CORES_PRAZO = CORES_PRAZO_CLARO


def cores_prazo(tema: str = "claro") -> dict:
    """Retorna o dicionário de cores por faixa de prazo, conforme o tema ativo."""
    return CORES_PRAZO_ESCURO if tema == "escuro" else CORES_PRAZO_CLARO

EMOJI_PRAZO = {
    PRAZO_VENCIDO:   "🚨",
    PRAZO_URGENTE:   "⚠️",
    PRAZO_ATENCAO:   "🔔",
    PRAZO_TRANQUILO: "✅",
    PRAZO_SEM_DATA:  "—",
}

LABEL_PRAZO = {
    PRAZO_VENCIDO:   "Vencido",
    PRAZO_URGENTE:   "Vence em até 30 dias",
    PRAZO_ATENCAO:   "Vence em 31–90 dias",
    PRAZO_TRANQUILO: "Sem urgência",
    PRAZO_SEM_DATA:  "Sem data de término",
}


def classificar_prazo(termino_contrato, hoje: date | None = None) -> str:
    """Classifica a urgência de vencimento a partir da data de término do contrato."""
    if pd.isna(termino_contrato):
        return PRAZO_SEM_DATA
    hoje = hoje or date.today()
    dias = (pd.Timestamp(termino_contrato).date() - hoje).days
    if dias < 0:
        return PRAZO_VENCIDO
    if dias <= 30:
        return PRAZO_URGENTE
    if dias <= 90:
        return PRAZO_ATENCAO
    return PRAZO_TRANQUILO


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


def _extrair_sheet_id(url: str) -> str | None:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return match.group(1) if match else None


# --------------------------------------------------------------------------- #
# ESCRITA AUTENTICADA — lançamentos feitos pelo dashboard gravam direto na    #
# planilha via Service Account (Google Sheets API), em vez do link público   #
# somente-leitura usado para exibição. Requer st.secrets["gcp_service_account"].
#
# Os dois dicionários abaixo espelham os mesmos usados em _normalizar_colunas
# (leitura via CSV) — se a estrutura da planilha mudar, atualize os dois.
# --------------------------------------------------------------------------- #

_MAPA_NOME_PARA_CAMPO = {
    "tipo":                "tipo",
    "fornecedor":          "fornecedor",
    "req. mxm":            "req_mxm",
    "req mxm":             "req_mxm",
    "requisição mxm":      "req_mxm",
    "valor":               "valor",
    "descritivo":          "descritivo",
    "término contrato":    "termino_contrato",
    "termino contrato":    "termino_contrato",
    "término do contrato": "termino_contrato",
    "dias vencimento":     "dias_vencimento",
    "link contrato":       "link_contrato",
    "link do contrato":    "link_contrato",
    "doc fiscal":          "doc_fiscal",
    "documento fiscal":    "doc_fiscal",
    "data pgto":           "data_pgto",
    "data de pagamento":   "data_pgto",
    "data pagamento":      "data_pgto",
    "status":              "status",
    "situação":            "status",
    "situacao":            "status",
    "observações":         "observacoes",
    "observacoes":         "observacoes",
    "observação":          "observacoes",
}

# Índice de coluna (0-based) → campo lógico, para as colunas de cabeçalho
# mesclado/vazio que a API não consegue identificar pelo nome do texto.
# Estrutura real da planilha (verificada nos dados + confirmado com o time):
#   C(2)=Req. MXM · D(3)=Valor · E(4)=Descritivo(nome) · F(5)=Término contrato
#   G(6)=Dias vencimento · H(7)=Link contrato(nome) · I(8)=Doc Fiscal
#   J(9)=Data pgto · K(10)=Status(nome)
_MAPA_POSICIONAL_INDICE = {
    2: "req_mxm",
    3: "valor",
    5: "termino_contrato",
    6: "dias_vencimento",
    8: "doc_fiscal",
    9: "data_pgto",
}


def _abrir_planilha(sheets_url: str) -> gspread.Spreadsheet:
    """
    Abre o arquivo da planilha (não uma aba específica) via Service Account.
    Requer a chave da Service Account em st.secrets["gcp_service_account"].
    """
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError(
            "Credenciais da Service Account não configuradas nos Secrets "
            "(gcp_service_account). Lançamentos pelo dashboard exigem essa "
            "configuração — veja o guia de configuração da Service Account."
        )

    sheet_id = _extrair_sheet_id(sheets_url)
    if not sheet_id:
        raise ValueError("URL do Google Sheets inválida.")

    gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    return gc.open_by_key(sheet_id)


def conectar_planilha_autenticada(sheets_url: str, nome_aba: str) -> gspread.Worksheet:
    """
    Abre uma aba específica via Service Account (leitura E escrita), diferente
    da leitura pública (gviz/CSV) usada para exibir o dashboard.
    """
    planilha = _abrir_planilha(sheets_url)
    return planilha.worksheet(nome_aba) if nome_aba and nome_aba.strip() else planilha.sheet1


def _mapear_colunas_por_nome(header: list[str]) -> dict[str, int]:
    """
    Mapeamento simples nome→índice, usado nas abas que o PRÓPRIO dashboard
    cria (ex: Aprovações) — ao contrário da planilha principal, aqui não há
    células mescladas nem cabeçalhos ausentes, então dispensa o mapeamento
    posicional usado em _mapear_colunas_planilha().
    """
    return {str(nome).strip(): i for i, nome in enumerate(header) if str(nome).strip()}


def _detectar_header_gspread(valores: list[list[str]]) -> int:
    """Mesma heurística da leitura via CSV: primeira linha que contém 'tipo'."""
    for i, linha in enumerate(valores):
        if "tipo" in [str(c).strip().lower() for c in linha]:
            return i
    return 0


def _mapear_colunas_planilha(header: list[str]) -> dict[str, int]:
    """Constrói {campo_lógico: índice_0based} a partir da linha de cabeçalho real."""
    mapa: dict[str, int] = {}
    for i, texto in enumerate(header):
        chave = str(texto).strip().lower()
        if chave in _MAPA_NOME_PARA_CAMPO:
            mapa[_MAPA_NOME_PARA_CAMPO[chave]] = i
    for indice, campo in _MAPA_POSICIONAL_INDICE.items():
        if indice < len(header):
            mapa[campo] = indice
    return mapa


def _formatar_valor_para_planilha(valor) -> str:
    """Converte cada tipo de dado para o texto que a planilha deve interpretar
    (USER_ENTERED faz a planilha reconhecer número/data como se fosse digitado)."""
    if valor is None:
        return ""
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, float):
        return f"{valor:.2f}".replace(".", ",")
    return str(valor).strip()


def _preencher_linha(linha: list, mapa_col: dict[str, int], dados: dict) -> None:
    """Preenche `linha` (lista já do tamanho certo) nos índices mapeados."""
    for campo, valor in dados.items():
        idx = mapa_col.get(campo)
        if idx is not None and idx < len(linha):
            linha[idx] = _formatar_valor_para_planilha(valor)


def _copiar_formula_ajustada(ws: gspread.Worksheet, col_1based: int, linha_origem_1based: int, linha_destino_1based: int) -> None:
    """
    Copia a fórmula de uma célula vizinha (ex: 'Dias vencimento') para a nova
    linha, ajustando referências que apontem para a própria linha de origem.
    Falha silenciosamente se não houver fórmula — não é crítico ao lançamento.
    """
    try:
        celula = ws.cell(linha_origem_1based, col_1based, value_render_option="FORMULA")
        formula = celula.value
        if not formula or not isinstance(formula, str) or not formula.startswith("="):
            return
        padrao = re.compile(rf"([A-Za-z]{{1,3}}){linha_origem_1based}\b")
        nova_formula = padrao.sub(lambda m: f"{m.group(1)}{linha_destino_1based}", formula)
        ws.update_cell(linha_destino_1based, col_1based, nova_formula)
    except Exception:
        pass  # Cosmético — a ausência da fórmula não impede o lançamento


def _ultima_linha_do_tipo(valores: list[list[str]], header_row: int, mapa_col: dict[str, int], tipo: str) -> int | None:
    """Índice 0-based (em `valores`) da última linha existente com o 'tipo' indicado."""
    idx_tipo = mapa_col.get("tipo")
    if idx_tipo is None:
        return None
    for r in range(len(valores) - 1, header_row, -1):
        linha = valores[r]
        if idx_tipo < len(linha) and str(linha[idx_tipo]).strip().title() == tipo:
            return r
    return None


def _copiar_formatacao_linha(ws: gspread.Worksheet, linha_origem_1based: int, linha_destino_1based: int, n_cols: int) -> str | None:
    """
    Copia a FORMATAÇÃO VISUAL (moeda, data, cor, borda, fonte...) de uma linha
    de referência para a nova linha, via Sheets API (copyPaste/PASTE_FORMAT).
    Não altera nenhum valor — só o estilo.

    Best-effort quanto ao LANÇAMENTO (nunca impede o registro do dado), mas
    retorna a mensagem de erro (em vez de escondê-la) para que a interface
    possa avisar o usuário quando a cópia de formatação falhar.
    """
    try:
        sheet_id = ws.id
        origem      = {"sheetId": sheet_id, "startRowIndex": linha_origem_1based - 1,  "endRowIndex": linha_origem_1based,
                        "startColumnIndex": 0, "endColumnIndex": n_cols}
        destino     = {"sheetId": sheet_id, "startRowIndex": linha_destino_1based - 1, "endRowIndex": linha_destino_1based,
                        "startColumnIndex": 0, "endColumnIndex": n_cols}
        ws.spreadsheet.batch_update({
            "requests": [{"copyPaste": {"source": origem, "destination": destino, "pasteType": "PASTE_FORMAT"}}]
        })
        return None
    except Exception as e:
        return str(e)


def descritivo_parcela(indice: int, total: int) -> str:
    """
    Regra de descritivo das parcelas:
      - 1 parcela  → "Parcela única"
      - N parcelas → "1ª Parcela", "2ª Parcela", ...
    `indice` é 0-based.
    """
    if total <= 1:
        return "Parcela única"
    return f"{indice + 1}ª Parcela"


def inserir_compra_com_parcelas(sheets_url: str, nome_aba: str,
                                dados_compra: dict, parcelas: list[dict]) -> list[str]:
    """
    Grava, em uma única operação, a linha 'Compra' seguida das suas linhas
    'Pagamento' (parcelas) — contíguas e nesta ordem, garantindo o
    agrupamento sequencial de que agrupar_hierarquia() depende.

    - dados_compra: campos lógicos do pedido (fornecedor, req_mxm, valor, ...)
    - parcelas: lista de dicts, cada um com valor/status/doc_fiscal/data_pgto.
      O 'descritivo' de cada parcela é definido automaticamente
      (ver descritivo_parcela); o 'tipo' é forçado em cada linha.

    Retorna uma lista de avisos não-críticos (ex: falha ao copiar a
    formatação visual) — o lançamento em si já foi gravado com sucesso
    quando esta função retorna sem lançar exceção.
    """
    ws = conectar_planilha_autenticada(sheets_url, nome_aba)
    valores = ws.get_all_values()
    header_row = _detectar_header_gspread(valores)
    mapa_col = _mapear_colunas_planilha(valores[header_row])
    n_cols = max(len(valores[header_row]), max(mapa_col.values(), default=-1) + 1)

    # Referências de formatação: a última linha existente de cada tipo
    ref_compra_0b    = _ultima_linha_do_tipo(valores, header_row, mapa_col, "Compra")
    ref_pagamento_0b = _ultima_linha_do_tipo(valores, header_row, mapa_col, "Pagamento")

    linhas: list[list] = []

    # 1) Linha da Compra
    linha_compra = [""] * n_cols
    _preencher_linha(linha_compra, mapa_col, {**dados_compra, "tipo": "Compra"})
    linhas.append(linha_compra)

    # 2) Linhas de Pagamento (parcelas), com descritivo automático
    total = len(parcelas)
    for i, p in enumerate(parcelas):
        linha_pag = [""] * n_cols
        _preencher_linha(linha_pag, mapa_col, {
            **p,
            "tipo": "Pagamento",
            "descritivo": descritivo_parcela(i, total),
        })
        linhas.append(linha_pag)

    # Uma única chamada de API grava todas as linhas contíguas ao final
    ws.append_rows(linhas, value_input_option="USER_ENTERED")

    primeira_nova_1based = len(valores) + 1

    # Best-effort: herda a fórmula de "Dias vencimento" para cada nova linha
    if "dias_vencimento" in mapa_col and len(valores) > header_row + 1:
        col_1based = mapa_col["dias_vencimento"] + 1
        origem_1based = len(valores)            # última linha que já existia
        for offset in range(len(linhas)):
            _copiar_formula_ajustada(ws, col_1based, origem_1based, primeira_nova_1based + offset)

    # Best-effort: herda a formatação visual (moeda, data, cor, borda...) de
    # uma linha existente do MESMO TIPO — Compra copia de Compra, cada
    # Pagamento copia de Pagamento. Erros viram avisos, não bloqueiam nada.
    avisos: list[str] = []
    if ref_compra_0b is not None:
        erro = _copiar_formatacao_linha(ws, ref_compra_0b + 1, primeira_nova_1based, n_cols)
        if erro:
            avisos.append(f"Formatação do pedido não copiada: {erro}")
    if ref_pagamento_0b is not None:
        for offset in range(1, len(linhas)):  # offset 0 é a linha da Compra
            erro = _copiar_formatacao_linha(ws, ref_pagamento_0b + 1, primeira_nova_1based + offset, n_cols)
            if erro:
                avisos.append(f"Formatação da parcela {offset} não copiada: {erro}")
    return avisos


# --------------------------------------------------------------------------- #
# EDIÇÃO / EXCLUSÃO / ADIÇÃO de linhas existentes                              #
#                                                                              #
# A linha-alvo é identificada pela POSIÇÃO do grupo (mesma lógica sequencial  #
# de agrupar_hierarquia): `grupo_idx` = índice da Compra na ordem da planilha #
# e `parcela_idx` = posição da parcela dentro do grupo. Não há ID único por   #
# linha na planilha; se a ordem mudar entre a leitura e a escrita (edição     #
# concorrente), há risco de atingir a linha errada — aceitável para o uso     #
# esparso e de poucos usuários deste beta.                                     #
# --------------------------------------------------------------------------- #

def _abrir_e_mapear(sheets_url: str, nome_aba: str):
    """Abre a planilha (autenticada) e devolve (ws, valores, header_row, mapa_col)."""
    ws = conectar_planilha_autenticada(sheets_url, nome_aba)
    valores = ws.get_all_values()
    header_row = _detectar_header_gspread(valores)
    mapa_col = _mapear_colunas_planilha(valores[header_row])
    return ws, valores, header_row, mapa_col


def _localizar_grupos(valores: list[list[str]], header_row: int, mapa_col: dict[str, int]) -> list[dict]:
    """
    Replica agrupar_hierarquia() sobre os valores brutos da planilha, mas
    devolvendo ÍNDICES DE LINHA (0-based em `valores`).
    Retorna: [{"compra": r, "parcelas": [r, r, ...]}, ...] na ordem da planilha.
    """
    idx_tipo = mapa_col.get("tipo")
    grupos: list[dict] = []
    atual = None
    for r in range(header_row + 1, len(valores)):
        linha = valores[r]
        tipo = ""
        if idx_tipo is not None and idx_tipo < len(linha):
            tipo = str(linha[idx_tipo]).strip().title()
        if tipo == "Compra":
            atual = {"compra": r, "parcelas": []}
            grupos.append(atual)
        elif tipo == "Pagamento" and atual is not None:
            atual["parcelas"].append(r)
    return grupos


def _atualizar_campos(ws, row_1based: int, mapa_col: dict[str, int], dados: dict) -> None:
    """Atualiza apenas as colunas mapeadas de uma linha (preserva as demais)."""
    celulas = []
    for campo, valor in dados.items():
        col = mapa_col.get(campo)
        if col is not None:
            celulas.append(gspread.Cell(row_1based, col + 1, _formatar_valor_para_planilha(valor)))
    if celulas:
        ws.update_cells(celulas, value_input_option="USER_ENTERED")


def _renumerar_descritivos(ws, grupo_idx: int) -> None:
    """
    Recalcula o 'descritivo' de todas as parcelas de um grupo após adição/
    exclusão (Parcela única / 1ª Parcela / 2ª Parcela ...). Re-lê a planilha
    para trabalhar com as posições já atualizadas.
    """
    valores = ws.get_all_values()
    header_row = _detectar_header_gspread(valores)
    mapa_col = _mapear_colunas_planilha(valores[header_row])
    col_desc = mapa_col.get("descritivo")
    if col_desc is None:
        return
    grupos = _localizar_grupos(valores, header_row, mapa_col)
    if grupo_idx >= len(grupos):
        return
    parcelas = grupos[grupo_idx]["parcelas"]
    total = len(parcelas)
    celulas = [
        gspread.Cell(r + 1, col_desc + 1, descritivo_parcela(i, total))
        for i, r in enumerate(parcelas)
    ]
    if celulas:
        ws.update_cells(celulas, value_input_option="USER_ENTERED")


_ERRO_GRUPO = ("O item não foi encontrado na planilha — ela pode ter sido "
               "alterada. Atualize a página e tente novamente.")


def atualizar_pedido(sheets_url: str, nome_aba: str, grupo_idx: int, dados: dict) -> None:
    """Atualiza os campos da linha 'Compra' do grupo indicado."""
    ws, valores, header_row, mapa_col = _abrir_e_mapear(sheets_url, nome_aba)
    grupos = _localizar_grupos(valores, header_row, mapa_col)
    if grupo_idx >= len(grupos):
        raise ValueError(_ERRO_GRUPO)
    _atualizar_campos(ws, grupos[grupo_idx]["compra"] + 1, mapa_col, dados)


def atualizar_parcela(sheets_url: str, nome_aba: str, grupo_idx: int, parcela_idx: int, dados: dict) -> None:
    """Atualiza os campos de uma parcela ('Pagamento') dentro do grupo."""
    ws, valores, header_row, mapa_col = _abrir_e_mapear(sheets_url, nome_aba)
    grupos = _localizar_grupos(valores, header_row, mapa_col)
    if grupo_idx >= len(grupos) or parcela_idx >= len(grupos[grupo_idx]["parcelas"]):
        raise ValueError(_ERRO_GRUPO)
    linha = grupos[grupo_idx]["parcelas"][parcela_idx] + 1
    _atualizar_campos(ws, linha, mapa_col, dados)


def excluir_parcela(sheets_url: str, nome_aba: str, grupo_idx: int, parcela_idx: int) -> None:
    """Remove uma parcela e renumera os descritivos das restantes do grupo."""
    ws, valores, header_row, mapa_col = _abrir_e_mapear(sheets_url, nome_aba)
    grupos = _localizar_grupos(valores, header_row, mapa_col)
    if grupo_idx >= len(grupos) or parcela_idx >= len(grupos[grupo_idx]["parcelas"]):
        raise ValueError(_ERRO_GRUPO)
    linha = grupos[grupo_idx]["parcelas"][parcela_idx] + 1
    ws.delete_rows(linha)
    _renumerar_descritivos(ws, grupo_idx)


def excluir_pedido(sheets_url: str, nome_aba: str, grupo_idx: int) -> None:
    """Remove a Compra e TODAS as suas parcelas (linhas contíguas)."""
    ws, valores, header_row, mapa_col = _abrir_e_mapear(sheets_url, nome_aba)
    grupos = _localizar_grupos(valores, header_row, mapa_col)
    if grupo_idx >= len(grupos):
        raise ValueError(_ERRO_GRUPO)
    g = grupos[grupo_idx]
    inicio = g["compra"] + 1
    fim = (g["parcelas"][-1] if g["parcelas"] else g["compra"]) + 1
    ws.delete_rows(inicio, fim)


def adicionar_parcela(sheets_url: str, nome_aba: str, grupo_idx: int, dados: dict) -> list[str]:
    """
    Insere uma nova parcela ao final do grupo (logo após a última parcela, ou
    logo abaixo da Compra se for a primeira) e renumera os descritivos.
    Retorna avisos não-críticos (ex: falha ao copiar a formatação visual).
    """
    ws, valores, header_row, mapa_col = _abrir_e_mapear(sheets_url, nome_aba)
    grupos = _localizar_grupos(valores, header_row, mapa_col)
    if grupo_idx >= len(grupos):
        raise ValueError(_ERRO_GRUPO)
    g = grupos[grupo_idx]
    ref = g["parcelas"][-1] if g["parcelas"] else g["compra"]   # 0-based
    destino_1based = ref + 2                                    # linha logo abaixo

    # Referência de FORMATAÇÃO: precisa ser uma linha 'Pagamento' de verdade
    # (se este for a 1ª parcela do grupo, `ref` é a própria Compra — errado
    # para copiar estilo). Sem parcela alguma no grupo, usa a última do sheet.
    ref_formato_0b = g["parcelas"][-1] if g["parcelas"] else _ultima_linha_do_tipo(valores, header_row, mapa_col, "Pagamento")

    n_cols = max(len(valores[header_row]), max(mapa_col.values(), default=-1) + 1)
    nova = [""] * n_cols
    _preencher_linha(nova, mapa_col, {**dados, "tipo": "Pagamento"})
    ws.insert_row(nova, index=destino_1based, value_input_option="USER_ENTERED")

    if "dias_vencimento" in mapa_col:
        _copiar_formula_ajustada(ws, mapa_col["dias_vencimento"] + 1, ref + 1, destino_1based)

    avisos: list[str] = []
    if ref_formato_0b is not None:
        ref_formato_1based = ref_formato_0b + 1
        # `insert_row` empurra para baixo (+1) qualquer linha que já estava
        # NO ponto de inserção ou depois dele.
        if ref_formato_1based >= destino_1based:
            ref_formato_1based += 1
        erro = _copiar_formatacao_linha(ws, ref_formato_1based, destino_1based, n_cols)
        if erro:
            avisos.append(f"Formatação da parcela não copiada: {erro}")

    _renumerar_descritivos(ws, grupo_idx)
    return avisos


# --------------------------------------------------------------------------- #
# CONFIGURAÇÕES DE NEGÓCIO — parâmetros ajustáveis pelo Owner na tela de       #
# Configurações, persistidos na PLANILHA (não em disco — mesmo motivo de      #
# sempre: o disco do Streamlit Cloud é efêmero e já causou perda de dado).    #
# --------------------------------------------------------------------------- #

_ABA_CONFIG    = "_Config"
_HEADER_CONFIG = ["chave", "valor"]

CONFIG_DIAS_ALERTA_PARCELA = "dias_alerta_parcela_atrasada"
_CONFIG_PADRAO = {
    CONFIG_DIAS_ALERTA_PARCELA: "40",
}


def _obter_aba_config(sheets_url: str) -> gspread.Worksheet:
    planilha = _abrir_planilha(sheets_url)
    try:
        return planilha.worksheet(_ABA_CONFIG)
    except gspread.exceptions.WorksheetNotFound:
        ws = planilha.add_worksheet(title=_ABA_CONFIG, rows=20, cols=len(_HEADER_CONFIG))
        ws.append_row(_HEADER_CONFIG, value_input_option="RAW")
        return ws


@st.cache_data(ttl=60, show_spinner=False)
def carregar_config(sheets_url: str) -> dict:
    """Config de negócio ajustável (ex: dias de alerta de parcela atrasada).
    Sempre retorna os padrões preenchidos, mesmo se a aba ainda não existir
    ou a leitura falhar — nunca derruba o dashboard por causa de um parâmetro."""
    config = dict(_CONFIG_PADRAO)
    try:
        ws = _obter_aba_config(sheets_url)
        linhas = ws.get_all_values()[1:]
        for l in linhas:
            if l and l[0]:
                config[l[0].strip()] = l[1].strip() if len(l) > 1 else ""
    except Exception:
        pass
    return config


def salvar_config_valor(sheets_url: str, chave: str, valor: str) -> None:
    ws = _obter_aba_config(sheets_url)
    linhas = ws.get_all_values()
    idx_existente = next((i for i, l in enumerate(linhas[1:], start=1) if l and l[0].strip() == chave), None)
    if idx_existente is not None:
        ws.update_cell(idx_existente + 1, 2, valor)
    else:
        ws.append_row([chave, valor], value_input_option="RAW")


# --------------------------------------------------------------------------- #
# AUTO-BAIXA DE PARCELAS — "Data Pgto" só é preenchida quando a NF já foi     #
# atendida e representa a DATA-LIMITE em que o pagamento sai: ao chegar nela, #
# o pagamento já é certo. Assim, qualquer parcela cuja Data Pgto já tenha     #
# passado (e que ainda não esteja como "Pago") é marcada automaticamente.    #
#                                                                              #
# Não existe processo em segundo plano — isso roda quando alguém abre o      #
# dashboard (com cache de 1h pra não pesar a cada clique). Na prática, a     #
# baixa acontece na PRÓXIMA VEZ que alguém abrir o dashboard após a data,    #
# não no instante exato em que ela chega.                                    #
# --------------------------------------------------------------------------- #

@st.cache_data(ttl=3600, show_spinner=False)
def marcar_parcelas_vencidas_como_pagas(sheets_url: str, nome_aba: str) -> int:
    """Varre todas as parcelas da planilha e marca como 'Pago' as que já
    passaram da Data Pgto e ainda não estavam com esse status. Retorna
    quantas parcelas foram atualizadas (0 se nenhuma, ou se algo falhar)."""
    try:
        ws, valores, header_row, mapa_col = _abrir_e_mapear(sheets_url, nome_aba)
    except Exception:
        return 0

    col_tipo   = mapa_col.get("tipo")
    col_status = mapa_col.get("status")
    col_data   = mapa_col.get("data_pgto")
    if col_tipo is None or col_status is None or col_data is None:
        return 0

    hoje = date.today()
    celulas = []
    for r in range(header_row + 1, len(valores)):
        linha = valores[r]
        if col_tipo >= len(linha) or str(linha[col_tipo]).strip().title() != "Pagamento":
            continue
        status_atual = linha[col_status].strip() if col_status < len(linha) else ""
        if status_atual in STATUS_GRUPOS["concluido"]:
            continue
        data_bruta = linha[col_data] if col_data < len(linha) else ""
        if not data_bruta:
            continue
        data_pgto = pd.to_datetime(data_bruta, dayfirst=True, errors="coerce")
        if pd.isna(data_pgto):
            continue
        if data_pgto.date() <= hoje:
            celulas.append(gspread.Cell(r + 1, col_status + 1, "Pago"))

    if celulas:
        try:
            ws.update_cells(celulas, value_input_option="USER_ENTERED")
        except Exception:
            return 0
    return len(celulas)


# --------------------------------------------------------------------------- #
# ALERTA DE PARCELA POSSIVELMENTE ATRASADA — heurística de acompanhamento:    #
# se uma parcela foi paga e, X dias corridos depois, a parcela SEGUINTE do    #
# mesmo pedido ainda não tem Doc. Fiscal preenchido (ou seja, a NF dela nunca #
# foi emitida), é sinal de que o fluxo pode ter travado — vale checar.       #
# Puramente informativo: não altera nada na planilha.                        #
# --------------------------------------------------------------------------- #

def _campo_vazio(valor) -> bool:
    if valor is None:
        return True
    try:
        if pd.isna(valor):
            return True
    except (TypeError, ValueError):
        pass
    return str(valor).strip().lower() in ("", "nan", "none", "—", "-")


def detectar_parcelas_atrasadas(df: pd.DataFrame, dias_limite: int) -> list[dict]:
    """
    Para cada pedido (Compra + parcelas na ordem da planilha), verifica pares
    de parcelas consecutivas: se a parcela N está Paga há `dias_limite` dias
    ou mais e a parcela N+1 não tem Doc. Fiscal preenchido, retorna um alerta.
    """
    hoje = date.today()
    alertas: list[dict] = []
    for compra, pagamentos in agrupar_hierarquia(df):
        if pagamentos is None or pagamentos.empty:
            continue
        registros = pagamentos.to_dict("records")
        for i in range(len(registros) - 1):
            atual = registros[i]
            proxima = registros[i + 1]
            if str(atual.get("status", "")).strip() not in STATUS_GRUPOS["concluido"]:
                continue
            data_pgto = atual.get("data_pgto")
            if pd.isna(data_pgto):
                continue
            dias_desde_pagamento = (hoje - data_pgto.date()).days
            if dias_desde_pagamento < dias_limite:
                continue
            if not _campo_vazio(proxima.get("doc_fiscal")):
                continue
            alertas.append({
                "fornecedor":            compra.get("fornecedor", ""),
                "descritivo_pedido":     compra.get("descritivo", ""),
                "descritivo_parcela":    atual.get("descritivo", ""),
                "descritivo_proxima":    proxima.get("descritivo", ""),
                "data_pgto_anterior":    data_pgto,
                "dias_desde_pagamento":  dias_desde_pagamento,
                "valor_proxima":         proxima.get("valor", 0.0),
            })
    alertas.sort(key=lambda a: a["dias_desde_pagamento"], reverse=True)
    return alertas


# --------------------------------------------------------------------------- #
# FLUXO DE APROVAÇÃO — Requisitante solicita, Owner aprova/rejeita             #
#                                                                              #
# Os pedidos pendentes ficam numa aba própria ("Aprovações"), criada           #
# automaticamente pelo dashboard na primeira vez que for necessária — com     #
# cabeçalho limpo definido por nós mesmos (sem os problemas de células        #
# mescladas da planilha principal). O histórico (aprovados/rejeitados) é      #
# mantido na mesma aba, apenas com o status atualizado.                       #
# --------------------------------------------------------------------------- #

_ABA_APROVACOES = "Aprovações"

_HEADER_APROVACOES = [
    "tipo", "fornecedor", "req_mxm", "valor", "descritivo", "status",
    "termino_contrato", "link_contrato", "doc_fiscal", "data_pgto", "observacoes",
    "solicitante_login", "solicitante_nome", "status_aprovacao",
    "data_solicitacao", "motivo_rejeicao",
]

STATUS_APROVACAO_PENDENTE  = "Pendente"
STATUS_APROVACAO_APROVADO  = "Aprovado"
STATUS_APROVACAO_REJEITADO = "Rejeitado"


def _obter_aba_aprovacoes(sheets_url: str) -> gspread.Worksheet:
    """Abre a aba de Aprovações; cria com o cabeçalho padrão na primeira vez."""
    planilha = _abrir_planilha(sheets_url)
    try:
        return planilha.worksheet(_ABA_APROVACOES)
    except gspread.exceptions.WorksheetNotFound:
        ws = planilha.add_worksheet(title=_ABA_APROVACOES, rows=200, cols=len(_HEADER_APROVACOES))
        ws.append_row(_HEADER_APROVACOES, value_input_option="RAW")
        return ws


def _localizar_grupos_simples(valores: list[list[str]], idx_tipo: int) -> list[dict]:
    """Mesma lógica de agrupamento sequencial (Compra→Pagamentos), mas para
    uma aba com cabeçalho na linha 0 e sem quirks de posição."""
    grupos: list[dict] = []
    atual = None
    for r in range(1, len(valores)):
        linha = valores[r]
        tipo = str(linha[idx_tipo]).strip().title() if idx_tipo < len(linha) else ""
        if tipo == "Compra":
            atual = {"compra": r, "parcelas": []}
            grupos.append(atual)
        elif tipo == "Pagamento" and atual is not None:
            atual["parcelas"].append(r)
    return grupos


def criar_solicitacao(sheets_url: str, dados_compra: dict, parcelas: list[dict],
                       solicitante_login: str, solicitante_nome: str) -> None:
    """Grava um pedido (Compra + parcelas) na aba de Aprovações, status Pendente."""
    ws = _obter_aba_aprovacoes(sheets_url)
    header = ws.row_values(1)
    mapa_col = _mapear_colunas_por_nome(header)
    n_cols = len(header)

    comuns = {
        "solicitante_login": solicitante_login,
        "solicitante_nome":  solicitante_nome,
        "status_aprovacao":  STATUS_APROVACAO_PENDENTE,
        "data_solicitacao":  datetime.now().strftime("%d/%m/%Y %H:%M"),
    }

    linhas: list[list] = []
    linha_compra = [""] * n_cols
    _preencher_linha(linha_compra, mapa_col, {**dados_compra, "tipo": "Compra", **comuns})
    linhas.append(linha_compra)

    total = len(parcelas)
    for i, p in enumerate(parcelas):
        linha_pag = [""] * n_cols
        _preencher_linha(linha_pag, mapa_col, {
            **p, "tipo": "Pagamento", "descritivo": descritivo_parcela(i, total), **comuns,
        })
        linhas.append(linha_pag)

    ws.append_rows(linhas, value_input_option="USER_ENTERED")


def listar_solicitacoes(sheets_url: str, apenas_login: str | None = None,
                         apenas_status: str | None = None) -> list[dict]:
    """
    Lê a aba de Aprovações e agrupa em solicitações (Compra + parcelas).
    Cada item: {"idx", "compra", "parcelas", "solicitante_login",
    "solicitante_nome", "status_aprovacao", "data_solicitacao", "motivo_rejeicao"}.
    `idx` identifica a posição do grupo — usado para aprovar/rejeitar depois.
    Retorna mais recentes primeiro.
    """
    ws = _obter_aba_aprovacoes(sheets_url)
    valores = ws.get_all_values()
    if len(valores) < 2:
        return []

    header = valores[0]
    mapa_col = _mapear_colunas_por_nome(header)
    idx_tipo = mapa_col.get("tipo", 0)
    grupos = _localizar_grupos_simples(valores, idx_tipo)

    def _linha_para_dict(r: int) -> dict:
        linha = valores[r]
        return {campo: (linha[i] if i < len(linha) else "") for campo, i in mapa_col.items()}

    resultado = []
    for i, g in enumerate(grupos):
        compra_dict = _linha_para_dict(g["compra"])
        if apenas_login and compra_dict.get("solicitante_login", "").strip() != apenas_login.strip():
            continue
        if apenas_status and compra_dict.get("status_aprovacao", "") != apenas_status:
            continue
        resultado.append({
            "idx":               i,
            "compra":            compra_dict,
            "parcelas":          [_linha_para_dict(r) for r in g["parcelas"]],
            "solicitante_login": compra_dict.get("solicitante_login", ""),
            "solicitante_nome":  compra_dict.get("solicitante_nome", ""),
            "status_aprovacao":  compra_dict.get("status_aprovacao", ""),
            "data_solicitacao":  compra_dict.get("data_solicitacao", ""),
            "motivo_rejeicao":   compra_dict.get("motivo_rejeicao", ""),
        })

    resultado.reverse()
    return resultado


@st.cache_data(ttl=30, show_spinner=False)
def contar_pendentes(sheets_url: str) -> int:
    """Conta solicitações pendentes — cache curto pra não pesar a sidebar a cada clique."""
    try:
        return len(listar_solicitacoes(sheets_url, apenas_status=STATUS_APROVACAO_PENDENTE))
    except Exception:
        return 0


def aprovar_solicitacao(sheets_url: str, nome_aba_destino: str, idx_grupo: int,
                         dados_compra_final: dict, parcelas_final: list[dict]) -> list[str]:
    """
    Grava o pedido (com eventuais correções feitas pelo Owner) na planilha
    real e marca a solicitação como Aprovada na aba de Aprovações (mantém
    o histórico, só atualiza o status).
    """
    avisos = inserir_compra_com_parcelas(sheets_url, nome_aba_destino, dados_compra_final, parcelas_final)

    ws = _obter_aba_aprovacoes(sheets_url)
    valores = ws.get_all_values()
    mapa_col = _mapear_colunas_por_nome(valores[0])
    idx_tipo = mapa_col.get("tipo", 0)
    grupos = _localizar_grupos_simples(valores, idx_tipo)
    if idx_grupo >= len(grupos):
        return avisos + ["Não foi possível marcar a solicitação como aprovada (posição não encontrada)."]

    linhas_grupo = [grupos[idx_grupo]["compra"]] + grupos[idx_grupo]["parcelas"]
    col_status = mapa_col.get("status_aprovacao")
    if col_status is not None:
        celulas = [gspread.Cell(r + 1, col_status + 1, STATUS_APROVACAO_APROVADO) for r in linhas_grupo]
        ws.update_cells(celulas, value_input_option="RAW")

    contar_pendentes.clear()
    return avisos


def rejeitar_solicitacao(sheets_url: str, idx_grupo: int, motivo: str) -> None:
    """Marca a solicitação como Rejeitada, com o motivo (mantém o histórico)."""
    ws = _obter_aba_aprovacoes(sheets_url)
    valores = ws.get_all_values()
    mapa_col = _mapear_colunas_por_nome(valores[0])
    idx_tipo = mapa_col.get("tipo", 0)
    grupos = _localizar_grupos_simples(valores, idx_tipo)
    if idx_grupo >= len(grupos):
        raise ValueError(_ERRO_GRUPO)

    linhas_grupo = [grupos[idx_grupo]["compra"]] + grupos[idx_grupo]["parcelas"]
    col_status = mapa_col.get("status_aprovacao")
    col_motivo = mapa_col.get("motivo_rejeicao")
    celulas = []
    for r in linhas_grupo:
        if col_status is not None:
            celulas.append(gspread.Cell(r + 1, col_status + 1, STATUS_APROVACAO_REJEITADO))
        if col_motivo is not None:
            celulas.append(gspread.Cell(r + 1, col_motivo + 1, motivo))
    if celulas:
        ws.update_cells(celulas, value_input_option="RAW")

    contar_pendentes.clear()


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
    # Estrutura real da planilha (verificada nos dados):
    #   C(2)=Req. MXM · D(3)=Valor · E=Descritivo(nome) · G(6)=Dias vencimento
    #   H=Link contrato(nome) · I(8)=Doc Fiscal · J(9)=Data pgto · K=Status(nome)
    mapa_posicional = {
        "Unnamed: 2":  "req_mxm",           # col C — ID da requisição no ERP MXM
        "Unnamed: 3":  "valor",             # col D — valor financeiro do contrato/parcela
        "Unnamed: 5":  "termino_contrato",  # col F — data de término do contrato (manual)
        "Unnamed: 6":  "dias_vencimento",   # col G — contador de dias (negativo = vencido)
        "Unnamed: 8":  "doc_fiscal",        # col I — número da NF/DANFE
        "Unnamed: 9":  "data_pgto",         # col J — data de pagamento ou previsão
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
    - 'grupo_status'    → categoria de saúde (concluido, alerta, etc.)
    - 'mes_pgto'        → mês/ano de pagamento para série temporal
    - 'prazo_status'    → urgência de vencimento do contrato
    - 'dias_para_vencer'→ dias até o término (negativo = já vencido)
    - 'mes_vencimento'  → mês/ano de término, para filtro por calendário
    """
    if "status" in df.columns:
        df["grupo_status"] = df["status"].map(
            lambda s: STATUS_PARA_GRUPO.get(s, "alerta")
        )

    if "data_pgto" in df.columns:
        df["mes_pgto"] = df["data_pgto"].dt.to_period("M").astype(str)

    if "termino_contrato" in df.columns:
        hoje = date.today()
        df["prazo_status"] = df["termino_contrato"].apply(lambda d: classificar_prazo(d, hoje))
        df["dias_para_vencer"] = df["termino_contrato"].apply(
            lambda d: (pd.Timestamp(d).date() - hoje).days if pd.notna(d) else None
        )
        df["mes_vencimento"] = df["termino_contrato"].dt.to_period("M").astype(str)
        df.loc[df["termino_contrato"].isna(), "mes_vencimento"] = ""

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

    # KPI 5 — Contratos vencidos (por DATA de término já passada, alinhado ao
    # alerta do topo e ao card "A vencer em 30 dias" — ambos por data).
    vencidos = (
        int((df_compras["prazo_status"] == PRAZO_VENCIDO).sum())
        if "prazo_status" in df_compras.columns else 0
    )

    # KPI 6 — Total de fornecedores únicos
    fornecedores = df["fornecedor"].nunique() if "fornecedor" in df.columns else 0

    # KPI 7 — Percentual de execução orçamentária
    perc_execucao = (pago / orcamento_total * 100) if orcamento_total > 0 else 0

    # KPI 8 — Contratos a vencer em até 30 dias (valor e contagem)
    if "prazo_status" in df_compras.columns:
        _urgentes = df_compras[df_compras["prazo_status"] == PRAZO_URGENTE]
        a_vencer_30d = _urgentes["valor"].sum() if "valor" in _urgentes.columns else 0
        n_a_vencer_30d = len(_urgentes)
    else:
        a_vencer_30d = 0
        n_a_vencer_30d = 0

    return {
        "orcamento_total":  orcamento_total,
        "pago":             pago,
        "a_pagar":          a_pagar,
        "em_gargalo":       em_gargalo,
        "vencidos":         vencidos,
        "fornecedores":     fornecedores,
        "perc_execucao":    perc_execucao,
        "a_vencer_30d":     a_vencer_30d,
        "n_a_vencer_30d":   n_a_vencer_30d,
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
