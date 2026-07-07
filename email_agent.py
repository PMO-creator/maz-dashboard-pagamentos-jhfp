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
# AUTENTICAÇÃO — delegação em nível de domínio (não usa login interativo).
# Reaproveita a MESMA Service Account já usada pra escrever na planilha
# (st.secrets["gcp_service_account"]) — evita totalmente a tela de
# "OAuth Client ID / Interno x Externo" que trava em contas Workspace sem
# uma Organização configurada no Google Cloud.
#
# CONFIGURAÇÃO NECESSÁRIA (uma vez, feita pelo TI/admin do Workspace):
#   1. No Admin Console do Google Workspace (admin.google.com), ir em:
#      Segurança → Controles de API → Delegação em todo o domínio
#      → "Adicionar novo".
#   2. "ID do cliente": o Client ID numérico da Service Account (está no
#      campo "client_id" do JSON da credencial, ou na página da Service
#      Account no Google Cloud Console).
#   3. "Escopos OAuth": cole exatamente
#        https://www.googleapis.com/auth/gmail.modify
#      (dá leitura + criação/aplicação de labels; não permite apagar
#      e-mails nem enviar em nome da conta).
#   4. Salvar. Não tem tela de consentimento, não precisa ninguém logar —
#      a autorização é feita pelo admin, de uma vez, pra essa Service
#      Account específica.
#
# Depois disso, este script já funciona: ele usa as MESMAS Secrets do
# dashboard (SHEETS_URL, gcp_service_account) — precisa rodar num ambiente
# com acesso a elas (ex: `.streamlit/secrets.toml` local com as credenciais
# de produção, ou as variáveis equivalentes no ambiente onde for hospedado).
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

# Caixa que o agente lê, "vestindo a identidade" dela via delegação de
# domínio — não é uma conta separada com senha própria.
CAIXA_DELEGADA = "exposicoeseprojetos@idg.org.br"

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
# AUTENTICAÇÃO GMAIL — delegação de domínio, sem login interativo             #
# --------------------------------------------------------------------------- #

def _autenticar_gmail():
    """
    Usa a mesma Service Account do Sheets (st.secrets["gcp_service_account"]),
    delegada para "vestir a identidade" da caixa CAIXA_DELEGADA. Só funciona
    depois que o admin do Workspace autorizar essa Service Account em
    Segurança → Controles de API → Delegação em todo o domínio (ver o
    cabeçalho deste arquivo). Sem essa autorização, a chamada abaixo falha
    com um erro claro de permissão — não é um bug do script.
    """
    from google.oauth2.service_account import Credentials

    if not hasattr(st, "secrets") or "gcp_service_account" not in st.secrets:
        sys.exit("gcp_service_account não configurado nas Secrets — não é possível autenticar.")

    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=ESCOPOS_GMAIL)
    creds_delegadas = creds.with_subject(CAIXA_DELEGADA)

    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds_delegadas)


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
