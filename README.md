# 🎯 RCA Pocket

Sistema de gestão e análise de Root Cause Analysis (RCA) com integração Jira, geração de relatórios Excel e dashboard interativo.

---

## 📋 Funcionalidades

- 🌐 Sincronização com Jira via browser (login manual)
- 📊 Planilha Excel formatada com 3 blocos de análise
- 📈 Dashboard web interativo (Streamlit)
- 🤖 **Indexação de TAs por similaridade** (Robot Framework no GitHub)
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
- `[1]` Sincronizar Jira (browser) + Gerar Excel + Abrir Dashboard
- `[2]` Apenas Gerar/Atualizar Excel (inclui indexação de TAs)
- `[3]` Apenas Abrir Dashboard
- `[4]` Abrir Excel Online (SharePoint)
- `[0]` Sair

### Via Comandos Diretos

```powershell
# Sincronizar com Jira (via browser)
python sync_jira_browser.py

# Gerar planilha Excel
python generate_excel.py

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

## 🤖 Indexação de Testes Automatizados

O sistema indexa test cases do repositório [ta-robotframework](https://github.com/MEDIUM-RETAIL-MICROVIX/ta-robotframework) e faz matching por similaridade de palavras-chave:

1. Indexa test cases dos arquivos `.robot` no GitHub
2. Compara palavras-chave do resumo de cada issue com nomes dos testes
3. Atualiza coluna **R (Possui TA)**: Sim/Não
4. Preenche coluna **S (Arquivo TA)**: top 3 test cases mais relevantes

**Requer**: Token GitHub configurado (veja seção [Configuração](#2-configuração))

---

## 📚 Documentação Completa

- **[MANUAL.md](MANUAL.md)**: Guia completo do usuário
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
| "Planilha sem Time/Área" | Regenere o Excel com `python generate_excel.py` |
| Dashboard não atualiza | Clique no botão 🔄 ou regenere o Excel |

---

## 👥 Suporte

Dúvidas ou problemas? Consulte o [MANUAL.md](MANUAL.md) ou entre em contato com o time de QA.

---

**Versão**: 1.1 | **Última atualização**: Março/2026
