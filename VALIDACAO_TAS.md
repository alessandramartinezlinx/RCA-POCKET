# 🤖 Validação de Testes Automatizados (TAs) - RCA Pocket

## 📋 Overview

Este documento descreve a **integração automática** entre a planilha RCA Pocket e o repositório Robot Framework do GitHub para validar se existem **testes automatizados (TAs)** associados aos bugs registrados.

---

## 🎯 Objetivo

Identificar automaticamente quais issues da planilha RCA possuem cobertura de testes automatizados, atualizando a coluna **"Possui TA"** e gerando relatórios de cobertura.

---

## 🔍 Como Funciona

### 1. **Leitura da Planilha**
O script `validar_tas_planilha.py` lê todos os issues (coluna **Key**) da aba `📊 Dados`.

### 2. **Busca no GitHub**
Para cada issue, o script busca no repositório [ta-robotframework](https://github.com/MEDIUM-RETAIL-MICROVIX/ta-robotframework):

- **Busca direta**: Arquivos `.robot` que mencionam `MODAJOI-XXXXX`
- **Busca por tag**: Testes com tags `[Tags] SHOP-JOI-XXXXX` (padrão Robot Framework)
- **Busca em comentários**: Documentação ou comentários que referenciam o issue

### 3. **Atualização Automática**
A coluna **"Possui TA"** (coluna W) é atualizada:
- ✅ **"Sim"**: Encontrado pelo menos 1 teste automatizado
- ❌ **"Não"**: Nenhum teste encontrado

### 4. **Relatório de Cobertura**
Gera relatório com:
- Porcentagem de cobertura (issues com TA vs. sem TA)
- Lista detalhada de arquivos `.robot` para cada issue
- Sugestões de priorização para issues sem cobertura

---

## 🚀 Uso

### **Opção 1: Via run.bat (Recomendado)**

```batch
run.bat
```

Escolha a opção **[4] Validar Cobertura de TAs**.

### **Opção 2: Execução Direta**

```powershell
# 1. Configurar token GitHub (primeiro uso)
$env:GITHUB_TOKEN = "ghp_seu_token_aqui"

# 2. Executar validação
python validar_tas_planilha.py
```

---

## 🔑 Configuração do Token GitHub

### **Passo 1: Gerar Token**
1. Acesse: https://github.com/settings/tokens
2. Clique em **"Generate new token (classic)"**
3. Marque permissão: `☑ repo` (read-only)
4. Gere e **copie o token**

### **Passo 2: Configurar (escolha um método)**

**Método A: Variável de Ambiente (Permanente)**
```powershell
# Windows PowerShell (Administrador)
[System.Environment]::SetEnvironmentVariable('GITHUB_TOKEN', 'ghp_seu_token_aqui', 'User')
```

**Método B: Sessão Temporária**
```powershell
$env:GITHUB_TOKEN = "ghp_seu_token_aqui"
python validar_tas_planilha.py
```

**Método C: Arquivo .env (não recomendado para tokens)**
```env
# Criar arquivo .env na raiz
GITHUB_TOKEN=ghp_seu_token_aqui
```

---

## 📊 Exemplo de Saída

```
🔍 VALIDAÇÃO DE TESTES AUTOMATIZADOS - RCA POCKET
======================================================================

📦 Cache carregado: 5 issue(s) em cache

📄 Lendo planilha RCA_Pocket.xlsx...
  16 issue(s) encontrado(s)

  Buscando TAs para MODAJOI-98445...
    ✅ MODAJOI-98445: 2 TA(s) encontrado(s)
  Buscando TAs para MODAJOI-99590...
    ❌ MODAJOI-99590: Nenhum TA encontrado
  [CACHE] MODAJOI-100041: True

📝 Atualizando planilha...
  ✅ 3 issue(s) atualizado(s)

======================================================================
📊 RELATÓRIO DE COBERTURA DE TESTES AUTOMATIZADOS
======================================================================

Total de issues analisados: 16
  ✅ Com TA:  8 (50.0%)
  ❌ Sem TA:  8 (50.0%)

----------------------------------------------------------------------
Issues COM teste automatizado:
----------------------------------------------------------------------

  MODAJOI-98445:
    • Tests/ERP/Faturamento/Venda_Facil/Venda/Venda_Nfe.robot
    • Tests/ERP/Faturamento/Venda_Facil/Troca_Facil/Troca_Facil.robot

  MODAJOI-59726:
    • Tests/ERP/Faturamento/Venda_Facil/Venda/Venda_Nfe.robot

----------------------------------------------------------------------
⚠️  Issues SEM teste automatizado (sugestão de priorização):
----------------------------------------------------------------------
  • MODAJOI-99590
  • MODAJOI-100041
  • MODAJOI-99958

======================================================================

✅ Validação concluída!
```

---

## 🗂️ Cache de Validações

O script mantém um **cache local** em `data/ta_validation_cache.json` para:
- ⚡ Evitar requisições repetidas ao GitHub
- 💰 Economizar rate limit da API
- 🚀 Acelerar validações subsequentes

**Limpar cache manualmente:**
```powershell
Remove-Item data/ta_validation_cache.json
```

---

## 🔗 Padrões de Mapeamento

### **1. MODAJOI Direto (Raro)**
Alguns testes mencionam diretamente o issue MODAJOI:
```robot
*** Test Cases ***
CD05-Acessar Venda Facil SmartPOS - MODAJOI-59726
    [Tags]    FatInt    CI/CD
    Login Venda Facil SmartPOS
```

### **2. Tag SHOP-JOI (Padrão)**
Maioria dos testes usa tags SHOP-JOI:
```robot
*** Test Cases ***
CD01-Cadastrar Balanco
    [Tags]    SupCrmImp    Estoque    SHOP-JOI-864
    Efetuar login ERP - Sustentacao
```

### **3. Comentários/Documentação**
Issues mencionados em documentação:
```robot
[Documentation]    Fix para MODAJOI-12345 - corrige erro de cálculo
```

---

## 📌 Notas Importantes

1. **Rate Limit GitHub**: API pública permite ~60 requisições/hora sem token, ~5000/hora com token
2. **Cache Persistente**: Validações anteriores são reutilizadas automaticamente
3. **Atualização Manual**: Coluna "Possui TA" pode ser editada manualmente se necessário
4. **Repositório Privado**: Token GitHub com permissão `repo` é **obrigatório**

---

## 🛠️ Troubleshooting

### **Erro: "Token GitHub não configurado"**
```
⚠️  ATENÇÃO: Token GitHub não configurado!
```
**Solução**: Configure a variável `GITHUB_TOKEN` (veja seção "Configuração do Token")

### **Erro: "API rate limit exceeded"**
```
⚠️  Erro ao buscar MODAJOI-12345: 403 API rate limit exceeded
```
**Solução**: Aguarde 1 hora ou configure um token para aumentar o limite

### **Erro: "Worksheet does not exist"**
```
KeyError: 'Worksheet 📊 Dados does not exist.'
```
**Solução**: Certifique-se que `RCA_Pocket.xlsx` existe e tem a aba `📊 Dados`

---

## 🔄 Integração com Workflow

### **Fluxo Recomendado**

1. **Importar Dados**: `python import_exemplo.py` ou Opção [2] no `run.bat`
2. **Gerar Planilha**: Sistema gera `RCA_Pocket.xlsx` automaticamente
3. **Validar TAs**: `python validar_tas_planilha.py` ou Opção [4] no `run.bat`
4. **Visualizar Dashboard**: Opção [3] no `run.bat` para análise interativa

### **Automação Completa**

Adicionar ao final de `import_exemplo.py`:
```python
if __name__ == "__main__":
    # ... código existente ...
    
    # Validação automática de TAs após importação
    if os.getenv("GITHUB_TOKEN"):
        print("\n🤖 Validando cobertura de TAs...")
        os.system("python validar_tas_planilha.py")
```

---

## 📚 Dependências

```txt
openpyxl>=3.1.0
PyGithub>=2.1.1
```

**Instalar**:
```powershell
pip install PyGithub openpyxl
```

---

## 🎓 Cenários de Uso

### **Caso 1: Análise de Cobertura Mensal**
```powershell
# Sincronizar com Jira
python main.py

# Gerar planilha RCA
# (automático no main.py)

# Validar cobertura de TAs
python validar_tas_planilha.py

# Visualizar no dashboard
streamlit run dashboard.py
```

### **Caso 2: Validação Pontual**
```powershell
# Após adicionar issues manualmente à planilha
python validar_tas_planilha.py
```

### **Caso 3: Priorização de Automação**
Use o relatório para identificar:
- ✅ Issues **prioritários** sem TA (P0/P1)
- ⚠️  Áreas com **baixa cobertura** (Time/Módulo)
- 📊 **Tendências** de cobertura ao longo do tempo

---

## 🤝 Contribuição

Sugestões de melhorias:
1. Adicionar coluna "Arquivo TA" com link direto ao GitHub
2. Integrar com TestLink para rastreabilidade completa
3. Gerar gráficos de cobertura por módulo/time
4. Alertas automáticos para issues P0 sem TA

---

## 📞 Suporte

Dúvidas ou problemas? Entre em contato com o time de QA ou abra uma issue no repositório.

---

**Última Atualização**: 11/03/2026  
**Versão**: 1.0.0  
**Autor**: Alessandra Martinez (via GitHub Copilot)
