# 📘 RCA Pocket — Manual do Usuário

> **Versão:** 1.1 · **Atualizado:** Março/2026  
> Ferramenta interna do time de QA para gestão e análise de Root Cause Analysis (RCA).

---

## 🆕 Novidades da Versão 1.1

### Ordenação Inteligente e Empilhamento Semanal

As issues agora são **automaticamente ordenadas** seguindo critérios de negócio:

1. **Qtd Vínculos** (↓) — Issues com mais relacionamentos têm prioridade
2. **P0 (Crítica)** — Bugs críticos aparecem primeiro
3. **P1 (Alta)** — Bugs de alta prioridade em seguida
4. **Demais prioridades**
5. **Data importação** (↓) — Mais recentes primeiro dentro de cada grupo

**Empilhamento Semanal:** Issues da semana atual ficam no topo; antigas descem automaticamente.

**Novas colunas:**
- **H - Qtd Vínculos**: Quantidade de issues linkadas no Jira (com destaque visual)
- **V - Semana**: Indica se é "Atual" ou "Anterior" (com cores diferentes)
- **W - Possui TA**: Indica se existe teste automatizado (Robot Framework) no GitHub

📄 Detalhes completos em [`FUNCIONALIDADE_ORDENACAO.md`](FUNCIONALIDADE_ORDENACAO.md)

### 🤖 Indexação de Testes Automatizados por Similaridade

Nova integração com o **repositório Robot Framework** no GitHub para identificar testes automatizados relacionados às issues:

- ✅ **Indexação automática** de test cases do [ta-robotframework](https://github.com/MEDIUM-RETAIL-MICROVIX/ta-robotframework)
- 🔍 **Matching por similaridade**: compara palavras-chave do resumo com nomes dos testes
- 📊 **Preenchimento automático**: coluna "Possui TA" e "Arquivo TA" na planilha
- 💾 **Cache inteligente**: índice válido por 7 dias em `data/ta_test_index.json`

**Como usar**: A indexação acontece automaticamente ao gerar o Excel (opção **[2]** no `run.bat`).

---

## 1. O que é o RCA Pocket?

Sistema composto por **dois entregáveis complementares**:

| Entregável | Arquivo | Para quê |
|---|---|---|
| **Planilha Excel** | `RCA_Pocket.xlsx` | Registro offline, edição manual, filtros por data |
| **Dashboard Web** | `dashboard.py` (Streamlit) | Visualização interativa em tempo real |

Ambos leem dos mesmos dados: issues do Jira (via API ou cache local).

---

## 2. Pré-requisitos

```bash
pip install -r requirements.txt
```

**Dependências principais:** `openpyxl`, `requests`, `streamlit`, `plotly`, `pandas`, `pyyaml`, `PyGithub` (validação TAs)

---

## 3. Configuração (`rca_config.yaml`)

Arquivo central — **todas as personalizações ficam aqui**, sem mexer no código.

### Token Jira (prioridade de leitura)
```
1. Variável de ambiente JIRA_API_TOKEN  ← injetada pela pipeline via Azure Key Vault
2. Campo token: no rca_config.yaml      ← uso local/desenvolvimento
3. Valor padrão "SEU_TOKEN_AQUI"        ← ativa modo MOCK automaticamente
```

**Para uso local:** gere um PAT em `Jira › Perfil › Personal Access Tokens` e preencha o campo `token:`.

### Principais configurações
```yaml
jira:
  base_url: "https://jira.linx.com.br"
  token: "SEU_TOKEN_AQUI"
  filter_id: "62693"          # ID do filtro Jira com as issues de RCA

cache:
  delta_update: true           # Busca apenas issues atualizadas desde a última sync
  parallel_pagination: false   # true = mais rápido para >500 issues

excel:
  arquivo_saida: "RCA_Pocket.xlsx"
```

### Adicionar novos times/responsáveis
Edite a seção `times:` no `rca_config.yaml`. Cada `área` mapeia labels do Jira para QA e Dev responsável. Após editar, execute `python generate_excel.py` para atualizar a aba **👥 Responsáveis**.

---

## 4. Planilha Excel (`RCA_Pocket.xlsx`)

### 4.1 Como gerar ou atualizar
```bash
cd rca_pocket
python generate_excel.py
```

> ⚠️ Se o arquivo já existir, **dados manuais (Ações e 5 Whys) são preservados** automaticamente.

---

### 4.2 Estrutura das abas

#### 📊 Dados
Lista todas as issues do Jira com classificação automática.

| Coluna | Descrição |
|---|---|
| Key | Código da issue (ex: MODAJOI-98001) — clicável, abre no Jira |
| Resumo / Descrição | Título e descrição da issue |
| Status | Aberto / Em Análise / Resolvido |
| Prioridade | Crítica / Alta / Média / Baixa (colorido) |
| **Data Criação** | Data de abertura da issue no Jira |
| Data Resolução | Data de fechamento |
| Dias p/ Resolver | Calculado automaticamente |
| Time / Área | Mapeado via labels do Jira + `rca_config.yaml` |
| **Tipo Erro Auto** | Classificado por palavras-chave (Banco de Dados, Sistema, etc.) |
| **Tipo Erro Manual** | Dropdown para correção manual — tem prioridade sobre o automático |
| Revisar? | Flag para issues que precisam de reclassificação |
| QA/Dev Principal/Secundário | Responsáveis mapeados por área |
| **Possui TA** 🤖 | **Sim** ou **Não** — indica se existe teste automatizado no GitHub (Robot Framework) |
| **Arquivo TA** 📁 | Nome dos arquivos `.robot` encontrados (ex: `Venda_Nfe.robot, Troca_Facil.robot (+1)`) |
| **Resultado da Automação** | Detectou problema / Não detectou / Não se Aplica (dropdown) |
| Labels / Link Jira | Labels originais e link direto |

**Como filtrar:** clique nas setas do cabeçalho da tabela (AutoFilter nativo do Excel).

---

#### ✅ Ações
Registro das ações realizadas após cada incidente.

| Coluna | Descrição |
|---|---|
| Data Criação | Herdada da issue (preenchida automaticamente) |
| Key Issue | Código da issue relacionada |
| Ação Realizada | Descrição da ação tomada |
| Responsável | Quem executou |
| Data Prevista / Conclusão | Datas de prazo e real |
| **Status Ação** | Pendente / Em Andamento / Concluída / Cancelada (dropdown) |
| **Tipo** | Preventiva ou Remediação (dropdown) |
| Observações | Campo livre |

> **Preencha manualmente** as colunas D–J. As linhas são preservadas a cada regeneração.

---

#### 🔍 5 Whys
Análise de causa raiz por issue (técnica dos 5 Porquês).

| Coluna | Descrição |
|---|---|
| Data Criação | Herdada da issue |
| Key / Resumo | Identificação da issue |
| Por quê 1–5 | Cadeia de causas (fundo amarelo — editável) |
| **Causa Raiz** | Conclusão da análise (fundo laranja) |
| Ação Preventiva | Proposta para evitar recorrência (fundo verde) |
| **Lição Aprendida** | Insight documentado para o time (fundo azul) |

**Como filtrar por período:** use o AutoFilter na coluna **A (Data Criação)** — igual a Dados e Ações.

---

#### 👥 Responsáveis
Tabela de referência gerada a partir do `rca_config.yaml`. Somente leitura — edite o YAML e regenere.

---
---

## 5. Dashboard Web (`dashboard.py`)

### 5.1 Como iniciar
```bash
cd rca_pocket
streamlit run dashboard.py
# Acesse: http://localhost:8501
```

### 5.2 Fonte de dados
- Lê `data/issues_cache.json` (gerado pelo Jira client) + `RCA_Pocket.xlsx` (ações)
- Cache atualizado a cada 5 min no browser (`ttl=300`)
- Em modo protótipo (sem token), usa **30 issues mock** de Out/2025 a Mar/2026

---

### 5.3 Painel lateral — Filtros

| Filtro | Descrição |
|---|---|
| **De / Até** | Período pela Data de Criação da issue |
| **Time** | Suprimentos, FatInt, etc. |
| **Área** | Sub-área dentro do time (dependente do Time selecionado) |
| **Tipo de Erro** | Banco de Dados, Sistema, Integração, etc. |
| **Status** | Aberto, Em Análise, Resolvido |
| **Prioridade** | Crítica, Alta, Média, Baixa |
| **Tendência por** | Semana ou Mês |
| 🔄 Atualizar | Força reload dos dados (limpa cache) |
| 🧹 Limpar filtros | Reseta período e filtros |

> **Dica:** Seleção vazia = exibe todos. Última sincronização aparece no rodapé da sidebar.

---

### 5.4 KPIs (topo da página)

| Métrica | Cálculo |
|---|---|
| 📋 Total Issues | Total no período filtrado |
| 🔴 Críticas Abertas | Prioridade Crítica + Status Aberto/Em Análise |
| ⏳ Em Aberto | Status Aberto + Em Análise |
| ✅ Resolvidas | Status Resolvido |
| 📈 Taxa Resolução | Resolvidas ÷ Total × 100% |
| ⏱️ Dias p/ Resolver | Média de `tempo_resolucao_dias` |

---

### 5.5 Gráficos

| Gráfico | O que mostra |
|---|---|
| **Incidências por Tipo de Erro** | Barras horizontais — quais categorias mais ocorrem |
| **Preventiva vs Remediação** | Donut — proporção das ações tomadas |
| **Incidências por Área** | Barras — quais módulos concentram mais issues |
| **Prioridades por Área** | Barras empilhadas — severidade por módulo |
| **Tendência Temporal** | Linha por status — evolução semana/mês |
| **Concentração Área × Tipo de Erro** | Heatmap — onde cada tipo de erro ocorre mais |
| **Status das Ações por Tipo** | Barras empilhadas Preventiva/Remediação |

---

### 5.6 Tabela detalhada + Export
No final da página: tabela com todas as issues filtradas.  
Clique em **⬇️ Exportar CSV** para baixar os dados exibidos.

---

## 6. Fluxo completo de uso

```
1. [Automático]           python sync_jira_browser.py
                             → abre browser, login manual no Jira
                             → extrai issues e salva em data/issues_cache.json

2. [Manual ou agendado]     python generate_excel.py
                             → gera/atualiza RCA_Pocket.xlsx
                             → indexa TAs automaticamente (requer GITHUB_TOKEN)
                             → dados manuais existentes são preservados

3. [Time de QA]             Abre RCA_Pocket.xlsx
                             → preenche Ações (aba ✅) e 5 Whys (aba 🔍)
                             → corrige Tipo Erro Manual se necessário
                             → verifica coluna "Possui TA" para priorizar automação

4. [Gesture / Reunião]      streamlit run dashboard.py
                             → filtra por período, time, área
                             → exporta CSV para apresentação
```

---

## 7. 🤖 Indexação de Testes Automatizados (TAs)

### 7.1 Visão Geral

Integração com o **repositório Robot Framework** no GitHub para identificar testes automatizados relacionados às issues por **similaridade de palavras-chave**.

**Benefícios:**
- Identifica **gaps de cobertura** (issues sem TA)
- Matching inteligente por **palavras-chave do resumo** da issue
- Cache de índice com validade de **7 dias**
- Execução **automática** durante a geração do Excel

### 7.2 Como Funciona

1. **Indexação**: O script `indexar_testes.py` busca arquivos `.robot` no GitHub e extrai nomes de test cases
2. **Matching**: Para cada issue, extrai palavras-chave do resumo e compara com os nomes dos testes
3. **Score**: Pontua matches exatos (3pts), parciais (1pt) e bônus de sistema/área (2pts)
4. **Resultado**: Preenche automaticamente:
   - Coluna **R (Possui TA)**: "Sim" ou vazio
   - Coluna **S (Arquivo TA)**: Top 3 test cases mais relevantes

### 7.3 Configuração

**Token GitHub (obrigatório):**
```powershell
# Permanente (recomendado):
[System.Environment]::SetEnvironmentVariable('GITHUB_TOKEN', 'ghp_seu_token', 'User')

# Ou temporário:
$env:GITHUB_TOKEN = "ghp_seu_token"
```

**Gerar token:**
1. Acesse: https://github.com/settings/tokens
2. Clique: "Generate new token (classic)"
3. Marque: ☑ repo (read)
4. Copie o token gerado

### 7.4 Uso

A indexação de TAs acontece **automaticamente** ao gerar o Excel:
```batch
run.bat → Opção [2] Apenas Gerar/Atualizar Excel
```

Ou via comando direto:
```bash
python generate_excel.py
```

### 7.5 Cache

O índice de test cases é salvo em `data/ta_test_index.json` com validade de 7 dias.

**Limpar cache manualmente:**
```powershell
Remove-Item data/ta_test_index.json
```

### 7.6 Resolução de Problemas

| Erro | Solução |
|---|---|
| "Token GitHub não configurado" | Configure `GITHUB_TOKEN` (veja seção 7.3) |
| TAs não encontrados | Verifique se o índice está atualizado (limpe o cache) |
| "No module named 'github'" | Execute: `pip install PyGithub` |

---

## 8. Modo MOCK (protótipo sem token)

Quando o token **não está configurado**, o sistema usa **30 issues fictícias** cobrindo Out/2025 a Mar/2026 do time de Suprimentos. Ideal para demonstrações e validação da ferramenta antes da integração com Jira real.

Para ativar token real: defina `JIRA_API_TOKEN` como variável de ambiente ou preencha `token:` no `rca_config.yaml`.

---

## 9. Resolução de problemas

| Sintoma | Causa provável | Solução |
---|---|---
| Dashboard mostra "Dados Mock" | Token não configurado | Configure `JIRA_API_TOKEN` ou `token:` no YAML |
| Excel substituiu dados manuais | Arquivo não encontrado no caminho configurado | Verifique `excel.arquivo_saida` no YAML |
| Erro 429 no Jira | Rate limit atingido | Client aguarda automaticamente (Retry-After); reduzir `parallel_pagination` |
| Issues não aparecem no período | Cache desatualizado | Clique 🔄 Atualizar no dashboard ou reexecute `generate_excel.py` |
| Tipo de erro errado | Keywords não mapeadas | Adicione keywords na seção `tipos_erro:` do YAML |
| Validação de TA falha | Token GitHub ausente | Configure `GITHUB_TOKEN` (veja seção 7.3) |
| Coluna "Possui TA" vazia | Validação não executada | Execute opção [4] no `run.bat` |
