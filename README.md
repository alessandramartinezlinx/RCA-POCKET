# 🎯 RCA Pocket

Sistema de gestão e análise de Root Cause Analysis (RCA) com integração Jira, geração de relatórios Excel e dashboard interativo.

---

## 📋 Funcionalidades

- ✅ Sincronização automática com Jira (via API)
- 📊 Planilha Excel formatada com 3 blocos de análise
- 📈 Dashboard web interativo (Streamlit)
- 🤖 **Validação automática de TAs** (Robot Framework no GitHub)
- 🔄 Cache inteligente para performance
- 🎨 Classificação automática por tipo de erro
- 📱 Ordenação por vínculos e prioridade

---

## 🚀 Início Rápido

### 1. Instalação

```powershell
# Clone o repositório
cd c:\GIT\rca-pocket

# Instale as dependências
pip install -r requirements.txt
```

### 2. Configuração

#### Token Jira (obrigatório)
Edite `rca_config.yaml` e adicione seu token:
```yaml
jira:
  token: "seu_token_jira_aqui"
```

Ou configure como variável de ambiente (recomendado para produção):
```powershell
$env:JIRA_API_TOKEN = "seu_token_jira"
```

#### Token GitHub (opcional - para validação de TAs)
Para usar a funcionalidade de validação de testes automatizados:

1. **Gere um token**: https://github.com/settings/tokens
   - Marque a permissão: ☑ `repo` (read)
   
2. **Configure a variável de ambiente**:
   ```powershell
   # Permanente (recomendado):
   [System.Environment]::SetEnvironmentVariable('GITHUB_TOKEN', 'ghp_seu_token', 'User')
   
   # Ou temporário (só nesta sessão):
   $env:GITHUB_TOKEN = "ghp_seu_token_aqui"
   ```

---

## 🎮 Uso

### Via Menu Interativo (Recomendado)

```powershell
.\run.bat
```

**Opções disponíveis:**
- `[1]` Sincronizar Jira + Gerar Excel + Abrir Dashboard
- `[2]` Apenas Gerar/Atualizar Excel
- `[3]` Apenas Abrir Dashboard
- `[4]` **Validar Cobertura de TAs** (busca GitHub Robot Framework)
- `[5]` Abrir Excel Online (SharePoint)
- `[0]` Sair

### Via Comandos Diretos

```powershell
# Sincronizar com Jira
python jira_client.py

# Gerar planilha Excel
python generate_excel.py

# Preencher Time/Área automaticamente (inferência inteligente)
python preencher_time_area_inferencia.py

# Validar TAs no GitHub
python validar_tas_planilha.py

# Abrir dashboard
streamlit run dashboard.py
```

---

## 📊 Estrutura da Planilha

### Aba 📊 Dados
27 colunas organizadas em 3 blocos:

**Bloco 1 - Identificação** (azul escuro):
- Key, Resumo, Status, Prioridade, Datas, Responsáveis, Vínculos

**Bloco 2 - Categorização** (cinza):
- Time, Área, Tipo de Erro, Ação Realizada

**Bloco 3 - Análise Manual** (verde):
- Análise da Causa, Tipo de Ajuste
- **Possui TA**, **Arquivo TA** 🤖, Resultado da Automação
- Contexto, Problema Resolvido, QA/Dev Principal

### Outras Abas
- **🗂️ Acompanhamento Issue**: Registro de ações corretivas
- **👥 Responsáveis**: Mapeamento de times e áreas

---

## 🤖 Validação de Testes Automatizados

O sistema busca automaticamente no repositório [ta-robotframework](https://github.com/MEDIUM-RETAIL-MICROVIX/ta-robotframework) se existem testes para cada issue:

1. Executa busca por `MODAJOI-XXXXX` e `SHOP-JOI-XXXXX`
2. Atualiza coluna **R (Possui TA)**: Sim/Não
3. Preenche coluna **S (Arquivo TA)**: lista de arquivos `.robot` encontrados
4. Gera relatório de cobertura (% com/sem TA)

**Requer**: Token GitHub configurado (veja seção [Configuração](#2-configuração))

---

## 📚 Documentação Completa

- **[MANUAL.md](MANUAL.md)**: Guia completo do usuário
- **[VALIDACAO_TAS.md](VALIDACAO_TAS.md)**: Detalhes sobre validação de TAs
- **[FUNCIONALIDADE_ORDENACAO.md](FUNCIONALIDADE_ORDENACAO.md)**: Sistema de ordenação

---

## 🛠️ Tecnologias

- **Python 3.14**: Backend e processamento
- **openpyxl**: Geração/manipulação de Excel
- **Streamlit**: Dashboard web interativo
- **PyGithub**: Integração com GitHub API
- **Jira REST API**: Sincronização de issues

---

## 📝 Configuração Avançada

Edite `rca_config.yaml` para:
- Adicionar novos times/áreas
- Personalizar palavras-chave de classificação
- Ajustar campos customizados do Jira
- Configurar URL do SharePoint

---

## 🆘 Troubleshooting

| Problema | Solução |
|---|---|
| "Token GitHub não configurado" | Configure `GITHUB_TOKEN` (veja [Configuração](#2-configuração)) |
| "Falha ao validar TAs" | Verifique permissão `repo` do token GitHub |
| "Planilha sem Time/Área" | Execute `python preencher_time_area_inferencia.py` |
| Dashboard não atualiza | Clique no botão 🔄 ou regenere o Excel |

---

## 👥 Suporte

Dúvidas ou problemas? Consulte o [MANUAL.md](MANUAL.md) ou entre em contato com o time de QA.

---

**Versão**: 1.1 | **Última atualização**: Março/2026
