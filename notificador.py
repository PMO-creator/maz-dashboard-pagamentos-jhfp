#!/usr/bin/env python3
"""
notificador.py — Notificações automáticas de pagamentos atrasados
MAZ | Museu das Amazônias · IDG — Instituto de Desenvolvimento e Gestão

Roda via GitHub Actions (cron diário, seg–sex, 8h Brasília).
O script decide internamente se é dia de envio conforme regra IDG:
  - Dias  1–19 : verificação e envio normais
  - Dias 20–31 : janela morta — script encerra sem enviar
  - Dia  1     : envio especial — inclui vencimentos acumulados do período 20→31
                 do mês anterior (recesso IDG)

Contratos guarda-chuva (identificados no campo "descritivo") são ignorados.
"""

import os
import re
import smtplib
import sys
from calendar import monthrange
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import StringIO

import pandas as pd
import requests

# --------------------------------------------------------------------------- #
# CONFIGURAÇÃO — variáveis de ambiente injetadas pelo GitHub Actions Secrets   #
# --------------------------------------------------------------------------- #
SHEETS_URL          = os.environ["SHEETS_URL"]
SHEETS_ABA          = os.environ.get("SHEETS_ABA", "")
SMTP_HOST           = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT           = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER           = os.environ["SMTP_USER"]
SMTP_PASSWORD       = os.environ["SMTP_PASSWORD"]
EMAIL_DESTINATARIOS = os.environ["EMAIL_DESTINATARIOS"]   # emails separados por vírgula
DIAS_LIMITE         = int(os.environ.get("DIAS_LIMITE", "30"))

# Palavras-chave no descritivo que identificam contratos guarda-chuva
GUARDA_CHUVA_KEYWORDS = ["guarda chuva", "guarda-chuva", "contrato guarda"]

STATUS_CONCLUIDO = ["Pago", "Contrato/Template quitado"]


# --------------------------------------------------------------------------- #
# REGRA DE DATA IDG                                                             #
# --------------------------------------------------------------------------- #

def _deve_enviar_hoje(hoje: date) -> bool:
    """Dias 1–19: envia. Dias 20–31: janela morta, não envia."""
    return hoje.day <= 19


def _vencimento_na_janela_morta_anterior(data_pgto: date | None, hoje: date) -> bool:
    """
    Dia 1 apenas: retorna True se data_pgto caiu entre o dia 20 e o último dia
    do mês anterior (período de recesso IDG). Esses itens são incluídos no
    envio consolidado do dia 1.
    """
    if data_pgto is None or hoje.day != 1:
        return False
    mes_ant = hoje.month - 1 if hoje.month > 1 else 12
    ano_ant = hoje.year if hoje.month > 1 else hoje.year - 1
    ultimo_dia = monthrange(ano_ant, mes_ant)[1]
    janela_inicio = date(ano_ant, mes_ant, 20)
    janela_fim    = date(ano_ant, mes_ant, ultimo_dia)
    return janela_inicio <= data_pgto <= janela_fim


# --------------------------------------------------------------------------- #
# LEITURA DA PLANILHA                                                           #
# --------------------------------------------------------------------------- #

def _sheets_url_para_csv(url: str, aba: str = "") -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(f"URL inválida para Google Sheets: {url}")
    sheet_id = match.group(1)
    if aba.strip():
        return (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}"
            f"/gviz/tq?tqx=out:csv&sheet={aba.strip()}"
        )
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"


def _carregar_planilha() -> pd.DataFrame:
    url_csv = _sheets_url_para_csv(SHEETS_URL, SHEETS_ABA)
    resp = requests.get(url_csv, timeout=30)
    resp.raise_for_status()
    texto = resp.text

    # Detecta linha de cabeçalho procurando pela célula "tipo"
    df_raw = pd.read_csv(StringIO(texto), header=None, dtype=str)
    header_row = 0
    for i, row in df_raw.iterrows():
        if "tipo" in row.astype(str).str.strip().str.lower().tolist():
            header_row = i
            break

    df = pd.read_csv(StringIO(texto), header=header_row, dtype=str)

    # Normaliza nomes de colunas
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
        .str.replace(r"[^a-z0-9_:]", "", regex=True)
    )

    # Mapeamento posicional das colunas "Unnamed" (células mescladas no Sheets)
    mapa_posicional = {
        "unnamed:_3":  "valor",
        "unnamed:_4":  "req_mxm",
        "unnamed:_6":  "dias_vencimento",
        "unnamed:_7":  "termino_contrato",
        "unnamed:_9":  "data_pgto",
        "unnamed:_10": "doc_fiscal",
    }
    df = df.rename(columns={k: v for k, v in mapa_posicional.items() if k in df.columns})

    if "tipo" in df.columns:
        df["tipo"] = df["tipo"].astype(str).str.strip().str.title()

    return df


# --------------------------------------------------------------------------- #
# IDENTIFICAÇÃO DE PAGAMENTOS ATRASADOS                                         #
# --------------------------------------------------------------------------- #

def _eh_guarda_chuva(descritivo: str) -> bool:
    desc = str(descritivo).lower()
    return any(kw in desc for kw in GUARDA_CHUVA_KEYWORDS)


def _parse_data(v) -> date | None:
    try:
        return pd.to_datetime(str(v), dayfirst=True).date()
    except Exception:
        return None


def _parse_int(v) -> int | None:
    try:
        return int(float(str(v)))
    except Exception:
        return None


def _parse_float(v) -> float | None:
    try:
        s = str(v).replace("R$", "").replace("\xa0", "").replace(".", "").replace(",", ".").strip()
        return float(s)
    except Exception:
        return None


def _fmt_brl(v: float | None) -> str:
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _agrupar_hierarquia(df: pd.DataFrame) -> list[tuple]:
    grupos: list[tuple] = []
    compra_atual = None
    pags: list = []
    for _, row in df.iterrows():
        tipo = str(row.get("tipo", "")).strip().title()
        if tipo == "Compra":
            if compra_atual is not None:
                grupos.append((compra_atual, pags))
            compra_atual = row
            pags = []
        elif tipo == "Pagamento" and compra_atual is not None:
            pags.append(row)
    if compra_atual is not None:
        grupos.append((compra_atual, pags))
    return grupos


def identificar_atrasados(df: pd.DataFrame, hoje: date) -> list[dict]:
    """
    Percorre a hierarquia Compra→Pagamentos e retorna os itens atrasados.
    Respeita a regra IDG de acumulação no dia 1.
    Exclui contratos guarda-chuva.
    """
    grupos = _agrupar_hierarquia(df)
    atrasados: list[dict] = []

    for compra, pagamentos in grupos:
        descritivo = str(compra.get("descritivo", ""))
        fornecedor = str(compra.get("fornecedor", "—")).strip()
        req        = str(compra.get("req_mxm", "—")).strip()

        if _eh_guarda_chuva(descritivo):
            continue

        total_pags = len(pagamentos)

        for i, pag in enumerate(pagamentos, start=1):
            status = str(pag.get("status", "")).strip()
            if status in STATUS_CONCLUIDO:
                continue

            dias_v    = _parse_int(pag.get("dias_vencimento"))
            data_pgto = _parse_data(pag.get("data_pgto"))

            # Atraso normal: dias_vencimento <= -DIAS_LIMITE
            atrasado_normal = dias_v is not None and dias_v <= -DIAS_LIMITE

            # Acumulado do recesso: vencimento na janela 20→31 do mês anterior
            # (incluso apenas no envio do dia 1, com qualquer valor negativo)
            atrasado_recesso = (
                hoje.day == 1
                and _vencimento_na_janela_morta_anterior(data_pgto, hoje)
                and dias_v is not None
                and dias_v < 0
            )

            if not (atrasado_normal or atrasado_recesso):
                continue

            valor = _parse_float(pag.get("valor"))

            atrasados.append({
                "fornecedor":    fornecedor,
                "req":           req,
                "descritivo":    descritivo[:60] + ("…" if len(descritivo) > 60 else ""),
                "parcela":       f"{i}/{total_pags}",
                "status":        status or "—",
                "data_pgto":     data_pgto.strftime("%d/%m/%Y") if data_pgto else "—",
                "dias_atraso":   abs(dias_v) if dias_v is not None else "?",
                "valor":         _fmt_brl(valor),
                "eh_recesso":    atrasado_recesso and not atrasado_normal,
            })

    return atrasados


# --------------------------------------------------------------------------- #
# EMAIL HTML                                                                    #
# --------------------------------------------------------------------------- #

def _montar_email_html(atrasados: list[dict], hoje: date) -> str:
    data_str = hoje.strftime("%d/%m/%Y")

    aviso_recesso = ""
    if hoje.day == 1 and any(a["eh_recesso"] for a in atrasados):
        aviso_recesso = """
        <div style="background:#F59E0B22;border:1px solid #F59E0B;border-radius:8px;
                    padding:12px 16px;margin-bottom:20px;font-size:0.88rem;">
          <span style="color:#F59E0B;font-weight:700;">⚠️ Consolidado do período de recesso (dias 20 → 31)</span><br>
          <span style="color:#d4a843;">Este email inclui pagamentos cujo vencimento ocorreu durante o período
          sem emissão de NF. Os itens marcados com <strong>[recesso]</strong> devem ser priorizados.</span>
        </div>
        """

    linhas_html = ""
    for a in atrasados:
        dias = a["dias_atraso"]
        cor_dias = "#EF4444" if isinstance(dias, int) and dias > 60 else "#F59E0B"
        tag_recesso = (
            '<span style="background:#3B82F622;border:1px solid #3B82F6;color:#3B82F6;'
            'font-size:0.68rem;padding:1px 6px;border-radius:10px;margin-left:6px;">'
            'recesso</span>'
            if a["eh_recesso"] else ""
        )
        linhas_html += f"""
        <tr style="border-bottom:1px solid #21262D;">
          <td style="padding:10px 8px;color:#E6EDF3;white-space:nowrap;">
            {a['fornecedor']}{tag_recesso}
          </td>
          <td style="padding:10px 8px;color:#8B949E;font-size:0.83rem;">{a['req']}</td>
          <td style="padding:10px 8px;color:#8B949E;font-size:0.83rem;">{a['descritivo']}</td>
          <td style="padding:10px 8px;color:#8B949E;white-space:nowrap;">{a['parcela']}</td>
          <td style="padding:10px 8px;color:#8B949E;white-space:nowrap;">{a['data_pgto']}</td>
          <td style="padding:10px 8px;color:{cor_dias};font-weight:700;white-space:nowrap;">
            {dias} dias
          </td>
          <td style="padding:10px 8px;color:#C9A84C;font-weight:700;white-space:nowrap;">
            {a['valor']}
          </td>
          <td style="padding:10px 8px;color:#8B949E;font-size:0.83rem;">{a['status']}</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0D1117;font-family:'Segoe UI',Arial,sans-serif;">
  <div style="max-width:860px;margin:32px auto;background:#161B22;border-radius:12px;
              border:1px solid #21262D;overflow:hidden;">

    <!-- Cabeçalho -->
    <div style="background:#0D1117;padding:24px 32px;border-bottom:1px solid #21262D;">
      <p style="margin:0;font-size:1.3rem;font-weight:700;color:#E6EDF3;">
        🏛️ MAZ | Museu das Amazônias
      </p>
      <p style="margin:4px 0 0;font-size:0.82rem;color:#8B949E;">
        Alerta de Pagamentos Atrasados &nbsp;·&nbsp; {data_str} &nbsp;·&nbsp;
        IDG — Instituto de Desenvolvimento e Gestão
      </p>
    </div>

    <!-- Corpo -->
    <div style="padding:24px 32px;">
      {aviso_recesso}

      <p style="color:#E6EDF3;margin:0 0 20px;font-size:0.95rem;">
        Foram identificados
        <strong style="color:#EF4444;">{len(atrasados)} pagamento(s)</strong>
        com atraso igual ou superior a <strong>{DIAS_LIMITE} dias</strong>
        sem confirmação de recebimento no sistema.
      </p>

      <div style="overflow-x:auto;">
        <table style="width:100%;border-collapse:collapse;font-size:0.85rem;min-width:640px;">
          <thead>
            <tr style="background:#0D1117;color:#8B949E;font-size:0.72rem;
                       text-transform:uppercase;letter-spacing:0.08em;">
              <th style="padding:8px;text-align:left;">Fornecedor</th>
              <th style="padding:8px;text-align:left;">Req. MXM</th>
              <th style="padding:8px;text-align:left;">Descritivo</th>
              <th style="padding:8px;text-align:left;">Parcela</th>
              <th style="padding:8px;text-align:left;">Prev. Pgto</th>
              <th style="padding:8px;text-align:left;">Atraso</th>
              <th style="padding:8px;text-align:left;">Valor</th>
              <th style="padding:8px;text-align:left;">Status</th>
            </tr>
          </thead>
          <tbody>
            {linhas_html}
          </tbody>
        </table>
      </div>

      <p style="color:#8B949E;font-size:0.75rem;margin-top:20px;border-top:1px solid #21262D;padding-top:12px;">
        ⚙️ Contratos <em>Guarda-Chuva</em> foram excluídos deste alerta automaticamente.<br>
        📋 Esta mensagem é gerada automaticamente pelo Dashboard MAZ. Não responda a este email.
      </p>
    </div>

    <!-- Rodapé -->
    <div style="background:#0D1117;padding:14px 32px;border-top:1px solid #21262D;
                text-align:center;color:#8B949E;font-size:0.7rem;">
      IDG — Instituto de Desenvolvimento e Gestão &nbsp;·&nbsp; Dashboard Gerencial MAZ &nbsp;·&nbsp;
      Notificação automática via GitHub Actions
    </div>
  </div>
</body>
</html>"""


def enviar_email(html_body: str, total: int, hoje: date) -> None:
    destinatarios = [e.strip() for e in EMAIL_DESTINATARIOS.split(",") if e.strip()]
    if not destinatarios:
        raise ValueError("EMAIL_DESTINATARIOS está vazio.")

    prefixo = "📦 Consolidado recesso · " if hoje.day == 1 else ""
    assunto = (
        f"[MAZ] {prefixo}⚠️ {total} pagamento(s) atrasado(s) · "
        f"{hoje.strftime('%d/%m/%Y')}"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"]    = SMTP_USER
    msg["To"]      = ", ".join(destinatarios)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, destinatarios, msg.as_string())

    print(f"✅ Email enviado para {len(destinatarios)} destinatário(s): {', '.join(destinatarios)}")


# --------------------------------------------------------------------------- #
# PONTO DE ENTRADA                                                              #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    hoje = date.today()
    print(f"[{hoje}] Verificação de pagamentos atrasados — MAZ Dashboard")

    if not _deve_enviar_hoje(hoje):
        print(f"[{hoje}] Dia {hoje.day} está na janela de recesso IDG (dias 20–31). Nenhum email enviado.")
        sys.exit(0)

    print("Carregando planilha do Google Sheets…")
    df = _carregar_planilha()
    print(f"Planilha carregada: {len(df)} linhas brutas.")

    atrasados = identificar_atrasados(df, hoje)
    n = len(atrasados)
    print(f"Pagamentos atrasados identificados: {n}")

    if n == 0:
        print("Nenhum pagamento atrasado encontrado. Nenhum email enviado.")
        sys.exit(0)

    html_body = _montar_email_html(atrasados, hoje)
    enviar_email(html_body, n, hoje)
    print("Concluído.")
