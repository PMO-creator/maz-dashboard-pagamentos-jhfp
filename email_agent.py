# =============================================================================
# email_agent.py — Agente de recebimento de Pedidos de Compra por e-mail.
#
# O QUE FAZ:
#   1. Lê a caixa de entrada configurada (ex: exposicoeseprojetos@idg.org.br)
#      procurando e-mails com PDF anexado que ainda não foram processados.
#   2. Extrai os dados do(s) PDF(s) com o MESMO motor usado no importador
#      manual do dashboard (pdf_extractor.py) — pedido de compra e/ou
#      contrato, mesclando os dois quando ambos estiverem no mesmo e-mail.
#   3. Grava o resultado na fila de "Aprovações Pendentes" do dashboard
#      (dh.criar_solicitacao) — NUNCA lança direto na planilha oficial.
#      Um humano (Owner) sempre revisa e aprova antes de qualquer coisa virar
#      um lançamento financeiro de verdade.
#   4. Marca o e-mail como processado (label do Gmail) para nunca reprocessar.
#      Se a extração falhar ou vier incompleta, marca como erro em vez de
#      "desaparecer" silenciosamente.
#
# O QUE NÃO FAZ (ainda):
#   - Upload dos PDFs para pastas do Drive (Fase seguinte, depois de validar
#     este fluxo).
#   - Agendamento automático — por enquanto, rode manualmente com:
#       python email_agent.py
#     Fase 3 decide onde isso roda de forma recorrente (Cloud Function,
#     GitHub Actions etc.).
#
# CONFIGURAÇÃO NECESSÁRIA (uma vez, feita por quem tem acesso à caixa):
#   1. Criar um "OAuth Client ID" tipo Desktop no Google Cloud Console (no
#      mesmo projeto onde já existe a Service Account do Sheets, ou um novo)
#      e habilitar a Gmail API para o projeto.
#   2. Baixar o arquivo de credenciais e salvar como `.credenciais_gmail.json`
#      nesta pasta (mesmo nível deste arquivo — está no .gitignore).
#   3. Rodar este script uma vez: ele abre o navegador pedindo para a pessoa
#      logar na caixa exposicoeseprojetos@idg.org.br e autorizar o acesso.
#      Depois disso, um `.token_gmail.json` é salvo e o script nunca mais
#      pede login (renova o token sozinho).
#   4. Este script usa as MESMAS Secrets do dashboard (SHEETS_URL, SHEETS_ABA,
#      gcp_service_account) — precisa rodar num ambiente com acesso a elas
#      (ex: `.streamlit/secrets.toml` local com as credenciais de produção,
#      ou as variáveis equivalentes no ambiente onde for hospedado).
# =============================================================================

import base64
import os
import sys

import streamlit as st

import data_handler as dh
import pdf_extractor

# --------------------------------------------------------------------------- #
# CONFIGURAÇÃO                                                                #
# --------------------------------------------------------------------------- #

CAMINHO_CREDENCIAIS = os.path.join(os.path.dirname(__file__), ".credenciais_gmail.json")
CAMINHO_TOKEN        = os.path.join(os.path.dirname(__file__), ".token_gmail.json")

# gmail.modify inclui leitura + criação/aplicação de labels (para marcar como
# processado); não inclui apagar e-mails nem enviar em nome da conta.
ESCOPOS_GMAIL = ["https://www.googleapis.com/auth/gmail.modify"]

LABEL_PROCESSADO = "PC-Processado"
LABEL_ERRO       = "PC-Erro-Extracao"

# Só processa e-mails vindos de dentro do domínio — reduz superfície de ataque
# de um anexo malicioso forjado por remetente externo. Ajuste se necessário.
DOMINIOS_CONFIAVEIS = ["@idg.org.br"]

# Status inicial do pedido quando registrado via e-mail (o Owner ajusta na
# revisão, se precisar).
STATUS_PADRAO_PEDIDO = "Contrato/Template em aberto"

NOME_AGENTE  = "Agente de E-mail (recebimento de PC)"
LOGIN_AGENTE = "agente-email-pc"


# --------------------------------------------------------------------------- #
# AUTENTICAÇÃO GMAIL (OAuth — autorização única, renovação automática)        #
# --------------------------------------------------------------------------- #

def _autenticar_gmail():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(CAMINHO_TOKEN):
        creds = Credentials.from_authorized_user_file(CAMINHO_TOKEN, ESCOPOS_GMAIL)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CAMINHO_CREDENCIAIS):
                sys.exit(
                    f"Faltam as credenciais OAuth em {CAMINHO_CREDENCIAIS}.\n"
                    "Veja o passo a passo no topo deste arquivo."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CAMINHO_CREDENCIAIS, ESCOPOS_GMAIL)
            creds = flow.run_local_server(port=0)
        with open(CAMINHO_TOKEN, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


# --------------------------------------------------------------------------- #
# LABELS — controle de idempotência (nunca processa o mesmo e-mail 2x)        #
# --------------------------------------------------------------------------- #

def _obter_ou_criar_label(service, nome: str) -> str:
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for lbl in labels:
        if lbl["name"] == nome:
            return lbl["id"]
    novo = service.users().labels().create(
        userId="me",
        body={"name": nome, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
    ).execute()
    return novo["id"]


def _marcar_mensagem(service, msg_id: str, label_id: str) -> None:
    service.users().messages().modify(
        userId="me", id=msg_id, body={"addLabelIds": [label_id]},
    ).execute()


# --------------------------------------------------------------------------- #
# LEITURA DE MENSAGENS E ANEXOS                                                #
# --------------------------------------------------------------------------- #

def _remetente_confiavel(headers: dict) -> bool:
    de = headers.get("From", "").lower()
    return any(dominio in de for dominio in DOMINIOS_CONFIAVEIS)


def _extrair_headers(payload: dict) -> dict:
    return {h["name"]: h["value"] for h in payload.get("headers", [])}


def _coletar_anexos_pdf(service, msg_id: str, payload: dict) -> list[bytes]:
    """Percorre as partes da mensagem e baixa todo anexo .pdf encontrado."""
    anexos = []

    def _percorrer(parte):
        nome = (parte.get("filename") or "").lower()
        corpo = parte.get("body", {})
        if nome.endswith(".pdf") and corpo.get("attachmentId"):
            dados = service.users().messages().attachments().get(
                userId="me", messageId=msg_id, id=corpo["attachmentId"],
            ).execute()
            anexos.append(base64.urlsafe_b64decode(dados["data"]))
        for sub in parte.get("parts", []) or []:
            _percorrer(sub)

    _percorrer(payload)
    return anexos


def _listar_mensagens_pendentes(service) -> list[dict]:
    query = f"has:attachment filename:pdf -label:{LABEL_PROCESSADO} -label:{LABEL_ERRO}"
    resultado = service.users().messages().list(userId="me", q=query).execute()
    return resultado.get("messages", [])


# --------------------------------------------------------------------------- #
# PROCESSAMENTO DE UMA MENSAGEM                                                #
# --------------------------------------------------------------------------- #

def _montar_dados_compra(extraido: dict) -> dict:
    """Mesmo mapeamento usado no wizard manual: numero_contrato entra
    embutido nas observações (não existe coluna própria na planilha)."""
    dados = {
        "fornecedor":       extraido.get("fornecedor", ""),
        "req_mxm":          extraido.get("req_mxm", ""),
        "valor":            float(extraido["valor"]) if extraido.get("valor") else 0.0,
        "descritivo":       extraido.get("descritivo", ""),
        "status":           STATUS_PADRAO_PEDIDO,
        "termino_contrato": extraido.get("termino_contrato"),
        "link_contrato":    "",
        "observacoes":      "",
    }
    obs_partes = []
    if extraido.get("numero_contrato"):
        obs_partes.append(extraido["numero_contrato"])
    if extraido.get("observacoes"):
        obs_partes.append(extraido["observacoes"])
    obs_partes.append("Registrado automaticamente via e-mail — revisar antes de aprovar.")
    dados["observacoes"] = " · ".join(obs_partes)
    return dados


def _processar_mensagem(service, msg_stub: dict, sheets_url: str) -> None:
    msg_id = msg_stub["id"]
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    payload = msg["payload"]
    headers = _extrair_headers(payload)
    assunto = headers.get("Subject", "(sem assunto)")

    label_erro = _obter_ou_criar_label(service, LABEL_ERRO)
    label_ok   = _obter_ou_criar_label(service, LABEL_PROCESSADO)

    if not _remetente_confiavel(headers):
        print(f"  [ignorado] remetente não confiável: {headers.get('From')} — {assunto!r}")
        _marcar_mensagem(service, msg_id, label_erro)
        return

    anexos = _coletar_anexos_pdf(service, msg_id, payload)
    if not anexos:
        print(f"  [sem anexo pdf de verdade] {assunto!r}")
        _marcar_mensagem(service, msg_id, label_erro)
        return

    extraidos = [d for d in (pdf_extractor.extrair_dados_documento(a) for a in anexos) if d]
    dados_ia = pdf_extractor.mesclar_dados_extraidos(extraidos) if extraidos else None

    if not dados_ia or not dados_ia.get("fornecedor") or not dados_ia.get("valor"):
        print(f"  [extração incompleta — fornecedor/valor não reconhecidos] {assunto!r}")
        _marcar_mensagem(service, msg_id, label_erro)
        return

    dados_compra = _montar_dados_compra(dados_ia)
    parcelas = dados_ia.get("parcelas") or [{
        "valor": dados_compra["valor"],
        "status": pdf_extractor.STATUS_PARCELA_PADRAO,
        "doc_fiscal": "",
        "data_pgto": None,
    }]

    dh.criar_solicitacao(sheets_url, dados_compra, parcelas, LOGIN_AGENTE, NOME_AGENTE)
    _marcar_mensagem(service, msg_id, label_ok)
    print(f"  [OK] {dados_compra['fornecedor']} · R$ {dados_compra['valor']:.2f} — {len(parcelas)} parcela(s) — {assunto!r}")


# --------------------------------------------------------------------------- #
# PONTO DE ENTRADA                                                             #
# --------------------------------------------------------------------------- #

def main():
    sheets_url = st.secrets.get("SHEETS_URL", "") if hasattr(st, "secrets") else ""
    if not sheets_url:
        sys.exit("SHEETS_URL não configurado nas Secrets — nada a fazer.")
    if not hasattr(st, "secrets") or "gcp_service_account" not in st.secrets:
        sys.exit("gcp_service_account não configurado nas Secrets — não é possível gravar na fila de Aprovações.")

    service = _autenticar_gmail()
    pendentes = _listar_mensagens_pendentes(service)
    print(f"{len(pendentes)} e-mail(s) pendente(s) de processamento.")
    for stub in pendentes:
        try:
            _processar_mensagem(service, stub, sheets_url)
        except Exception as e:
            print(f"  [ERRO inesperado] mensagem {stub['id']}: {e}")


if __name__ == "__main__":
    main()
