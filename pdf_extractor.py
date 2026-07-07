# =============================================================================
# pdf_extractor.py — Motor de extração de dados de PDF (pedido de compra e
# contrato/termo aditivo), por padrões de texto — sem IA/API paga.
#
# Módulo compartilhado: usado pelo app.py (importador manual do wizard de
# lançamento) e por qualquer processo externo que precise da mesma extração
# (ex: um agente que lê e-mails e registra pedidos automaticamente).
#
# Calibrado nos modelos de "Ordem de Compra" e "Termo Aditivo/Contrato" do
# IDG. Se o layout de um fornecedor variar muito, o campo simplesmente não é
# encontrado e fica ausente do dict (nunca inventa dado).
# =============================================================================

import re
from datetime import datetime

_MESES_EXTENSO_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}

# Status inicial sugerido para a parcela recém-importada: o pagamento ainda não
# aconteceu e a NF costuma não ter sido emitida quando o pedido/contrato é lançado.
STATUS_PARCELA_PADRAO = "Aguardando emissão de NF/DANFE"

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


def extrair_texto_pdf(pdf_bytes: bytes) -> str:
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
        return [{"valor": v, "status": STATUS_PARCELA_PADRAO} for v in valores]

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


def extrair_pedido_compra(texto: str) -> dict:
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


def extrair_contrato(texto: str) -> dict:
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


def mesclar_dados_extraidos(docs: list[dict]) -> dict:
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
    parcelas = resultado.get("parcelas")
    if parcelas and len(parcelas) == 1 and resultado.get("valor"):
        parcelas = [{**parcelas[0], "valor": float(resultado["valor"])}]
        resultado["parcelas"] = parcelas
    return resultado


def extrair_dados_documento(pdf_bytes: bytes) -> dict | None:
    """
    Lê o PDF (pedido de compra ou contrato) e tenta reconhecer os campos
    correspondentes por padrões de texto — sem IA paga, sem dado saindo do
    servidor. Nunca escreve nada sozinho: quem chama decide o que fazer com
    o resultado (pré-preencher um formulário, gravar numa fila de aprovação
    etc.) — sempre com revisão humana antes de qualquer gravação financeira.

    Retorna None se o PDF não puder ser lido; campos não reconhecidos ficam
    simplesmente ausentes do dict (nunca inventa dado).
    """
    try:
        texto = extrair_texto_pdf(pdf_bytes)
    except Exception:
        return None
    if not texto.strip():
        return None
    if re.search(r"ORDEM DE COMPRA", texto, re.IGNORECASE):
        return extrair_pedido_compra(texto)
    return extrair_contrato(texto)
