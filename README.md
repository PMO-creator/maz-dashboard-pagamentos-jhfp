# 🏛️ MAZ | Dashboard Gerencial de Pagamentos
**Instituto de Desenvolvimento e Gestão (IDG) · Projeto Museu das Amazônias**

> Versão Beta 1.0 — Dashboard interativo para acompanhamento do fluxo de pagamentos a fornecedores.

---

## 📸 O que este painel faz

| Funcionalidade | Descrição |
|---|---|
| **KPIs Executivos** | Orçamento total, total pago, saldo a pagar, gargalos e execução % |
| **Análise de Gargalos** | Identifica quanto dinheiro está parado em cada fase do fluxo |
| **Fluxo Temporal** | Gráfico mensal de pagamentos realizados vs. previstos |
| **Top Fornecedores** | Ranking por valor contratado |
| **Filtros Dinâmicos** | Por fornecedor e por situação do fluxo |
| **Exportação** | Download da tabela filtrada em CSV |

---

## 🗂️ Estrutura do Projeto

```
maz-dashboard-pagamentos-jhfp/
├── app.py                  ← Dashboard principal (interface + gráficos)
├── data_handler.py         ← Lógica de dados (Compra x Pagamento, KPIs)
├── requirements.txt        ← Bibliotecas Python necessárias
├── .streamlit/
│   └── config.toml         ← Tema visual (cores, fontes)
└── README.md               ← Este guia
```

---

## 📋 Formato da Planilha

O dashboard aceita arquivos `.xlsx` ou `.csv`. As colunas esperadas são:

| Coluna | Obrigatória | Descrição |
|---|---|---|
| **Tipo** | ✅ Sim | `Compra` ou `Pagamento` |
| **Fornecedor** | ✅ Sim | Nome da empresa |
| **Valor** | ✅ Sim | Valor em R$ (ex: `R$ 15.000,00`) |
| **Status** | ✅ Sim | Situação atual (ver lista abaixo) |
| Req. MXM | Não | ID da requisição no ERP |
| Descritivo | Não | Detalhes da contratação |
| Término Contrato | Não | Data de vigência final |
| Dias vencimento | Não | Contador de dias |
| Link contrato | Não | URL do documento |
| Doc Fiscal | Não | Número da NF/DANFE |
| Data pgto | Não | Data do pagamento |
| Observações | Não | Notas gerais |

### ⚠️ Regra Anti-Duplicidade

```
Compra    → Valor TOTAL do contrato  (orçamento)
Pagamento → Parcelas individuais     (fluxo de caixa)

O dashboard NUNCA soma Compra + Pagamento juntos.
KPIs de orçamento usam apenas linhas "Compra".
KPIs de pagamentos usam apenas linhas "Pagamento".
```

### Status válidos

```
✅ Concluído:    Pago | Contrato/Template quitado
🔄 Em andamento: Aprovado | NF em análise | Em aprovação | Atendimento Compras/Financeiro
⚠️ Alerta:       Aguardando emissão de NF/DANFE | Aguardando informações |
                 Aguardando Requisição de Pagamento | Contrato/Template em aberto
🚨 Crítico:      Contrato/Template vencido
```

---

## 🚀 Guia de Implantação — Passo a Passo

### PRÉ-REQUISITO: Contas necessárias (ambas gratuitas)

1. **GitHub** — github.com (você já tem ✅)
2. **Streamlit Community Cloud** — share.streamlit.io (criar conta gratuita com seu GitHub)

---

### PASSO 1 — Verificar os arquivos no GitHub

Confirme que o repositório `PMO-creator/maz-dashboard-pagamentos-jhfp` contém:
- `app.py`
- `data_handler.py`
- `requirements.txt`
- `.streamlit/config.toml`

---

### PASSO 2 — Fazer o Deploy no Streamlit Community Cloud

1. Acesse share.streamlit.io
2. Clique em **"Sign in with GitHub"** e autorize o acesso
3. Clique em **"New app"** (botão azul no canto superior direito)
4. Preencha os campos:
   - **Repository:** `PMO-creator/maz-dashboard-pagamentos-jhfp`
   - **Branch:** `main`
   - **Main file path:** `app.py`
5. Clique em **"Deploy!"**
6. Aguarde ~2 minutos enquanto o Streamlit instala as bibliotecas
7. Seu dashboard estará online em uma URL como:
   `https://maz-dashboard-pagamentos-jhfp.streamlit.app`

---

### PASSO 3 — Compartilhar com a equipe

1. Copie o link gerado pelo Streamlit
2. Envie para gestores, coordenadores e diretoria
3. Qualquer pessoa com o link pode acessar — sem precisar de login ou instalação

---

### PASSO 4 — Atualizar os dados (uso diário)

O dashboard não armazena dados — você faz o upload da planilha a cada uso:

1. Abra o link do dashboard
2. Na barra lateral esquerda, clique em **"Browse files"**
3. Selecione sua planilha `.xlsx` ou `.csv` atualizada
4. O painel atualiza automaticamente em segundos

---

### PASSO 5 — Atualizar o código (quando houver melhorias)

Quando precisar alterar o dashboard:

1. Edite o arquivo desejado no GitHub (clique no arquivo → ícone de lápis)
2. Faça a alteração e clique em **"Commit changes"**
3. O Streamlit detecta a mudança automaticamente e atualiza o app em ~1 minuto

---

## 🛠️ Rodando Localmente (para testes)

```bash
# 1. Instale o Python (versão 3.11+) em python.org

# 2. Abra o terminal na pasta do projeto e instale as dependências:
pip install -r requirements.txt

# 3. Rode o dashboard:
streamlit run app.py

# 4. Acesse no navegador: http://localhost:8501
```

---

## 🎨 Personalização Visual

Para alterar cores, edite o arquivo `.streamlit/config.toml`:

```toml
primaryColor             = "#C9A84C"    # Cor principal (dourado MAZ)
backgroundColor          = "#0D1117"    # Fundo principal
secondaryBackgroundColor = "#161B22"    # Fundo dos cards
textColor                = "#E6EDF3"    # Cor do texto
```

---

## ❓ Dúvidas Frequentes

**P: Posso proteger o dashboard com senha?**
R: Sim. O Streamlit Community Cloud permite configurar autenticação por e-mail na aba "Settings" do app.

**P: O dashboard salva minha planilha em algum lugar?**
R: Não. Os dados ficam apenas na memória da sessão do navegador e são descartados ao fechar a aba.

**P: Posso usar o dashboard em celular?**
R: Sim, o layout é responsivo. Funciona em tablets e celulares, mas a experiência é melhor em telas maiores.

**P: Quantas pessoas podem acessar ao mesmo tempo?**
R: No plano gratuito do Streamlit Community Cloud, o limite é generoso para uso interno de equipes.

---

*Dashboard desenvolvido para o IDG — Instituto de Desenvolvimento e Gestão · Projeto MAZ | Museu das Amazônias*
