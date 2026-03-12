# 🌐 Guia: Hospedar Dashboard Online (Link Compartilhável)

Este guia mostra como colocar o dashboard RCA Pocket online para que outras pessoas acessem via link e filtrem os dados interativamente.

---

## 🎯 Opções de Hospedagem

### **Opção 1: Streamlit Cloud** ⭐ Recomendado
- ✅ **Gratuito**
- ✅ Link público compartilhável
- ✅ Atualização automática via GitHub
- ✅ Sem necessidade de servidor próprio
- ⚠️ Requer conta GitHub

### **Opção 2: Rede Local/VPN**
- ✅ Controle total
- ✅ Dados ficam internos
- ⚠️ Requer VPN ou mesma rede
- ⚠️ Seu computador precisa ficar ligado

### **Opção 3: Azure/AWS/Google Cloud**
- ✅ Controle total e escalável
- ⚠️ Pago (custos variáveis)
- ⚠️ Requer conhecimento técnico

---

## 🚀 Opção 1: Streamlit Cloud (GRATUITO)

### **Passo 1: Preparar o Projeto**

1. **Criar arquivo `requirements.txt`** (se não existir):

```bash
cd c:\GIT\rca-pocket
```

Crie/atualize o arquivo com todas as dependências:

```txt
streamlit>=1.28.0
pandas>=2.0.0
plotly>=5.17.0
openpyxl>=3.1.0
PyYAML>=6.0
jira>=3.5.0
python-dateutil>=2.8.0
```

2. **Criar arquivo `.streamlit/config.toml`**:

```bash
mkdir .streamlit
```

Crie o arquivo `.streamlit/config.toml`:

```toml
[theme]
primaryColor = "#2E75B6"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
font = "sans serif"

[server]
enableXsrfProtection = false
enableCORS = false
```

3. **Criar arquivo `.gitignore`** (para não expor dados sensíveis):

```gitignore
# Dados sensíveis
rca_config.yaml
data/issues_cache*.json
data/ta_validation_cache.json
data/last_sync.txt
RCA_Pocket.xlsx

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info/
dist/
build/

# Ambientes virtuais
venv/
env/
ENV/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db
```

4. **Criar arquivo `rca_config_exemplo.yaml`** (template público):

```yaml
# Exemplo de configuração - Copie para rca_config.yaml e preencha
jira:
  url: "https://seu-jira.atlassian.net"
  email: "seu-email@empresa.com"
  api_token: "SEU_TOKEN_AQUI"
  jql: "project = MODAJOI AND issuetype = Bug"

excel:
  arquivo_saida: "RCA_Pocket.xlsx"

cache:
  arquivo_cache: "data/issues_cache.json"
  arquivo_ultima_sync: "data/last_sync.txt"
```

---

### **Passo 2: Subir para GitHub**

1. **Criar repositório no GitHub:**
   - Acesse [github.com](https://github.com)
   - Clique em **"New repository"**
   - Nome: `rca-pocket-dashboard` (ou outro nome)
   - Visibilidade: 
     - **Private** (recomendado - só quem você autorizar acessa)
     - **Public** (qualquer um com link acessa)
   - Clique **"Create repository"**

2. **Configurar Git localmente:**

```powershell
cd c:\GIT\rca-pocket

# Inicializar repositório (se ainda não tiver)
git init

# Adicionar arquivos
git add .
git commit -m "Setup inicial do dashboard RCA Pocket"

# Conectar ao GitHub (substitua SEU-USUARIO e NOME-REPO)
git remote add origin https://github.com/SEU-USUARIO/rca-pocket-dashboard.git

# Enviar código
git branch -M main
git push -u origin main
```

---

### **Passo 3: Deploy no Streamlit Cloud**

1. **Acessar Streamlit Cloud:**
   - Vá para [share.streamlit.io](https://share.streamlit.io)
   - Clique em **"Sign in"**
   - Faça login com sua conta GitHub

2. **Criar novo app:**
   - Clique em **"New app"**
   - Selecione:
     - **Repository**: `seu-usuario/rca-pocket-dashboard`
     - **Branch**: `main`
     - **Main file path**: `dashboard.py`
   - Clique em **"Deploy!"**

3. **Aguardar deploy** (2-5 minutos)
   - Streamlit Cloud instalará as dependências
   - Compilará o dashboard
   - Seu link será algo como: `https://rca-pocket-dashboard.streamlit.app`

---

### **Passo 4: Configurar Dados**

**Opção A: Usar dados de exemplo (mock)**
- O dashboard já funciona com dados mock
- Ideal para demonstração

**Opção B: Configurar credenciais Jira (via Secrets)**
1. No Streamlit Cloud, acesse seu app
2. Clique em **"⚙️ Settings"** → **"Secrets"**
3. Adicione:

```toml
[jira]
url = "https://seu-jira.atlassian.net"
email = "seu-email@empresa.com"
api_token = "seu_token_aqui"
jql = "project = MODAJOI AND issuetype = Bug"
```

4. Modifique `_get_config.py` para ler secrets:

```python
import streamlit as st

def load_config():
    # Tenta carregar de secrets do Streamlit Cloud
    if hasattr(st, 'secrets') and 'jira' in st.secrets:
        return dict(st.secrets)
    
    # Fallback para arquivo local
    with open('rca_config.yaml') as f:
        return yaml.safe_load(f)
```

---

### **Passo 5: Compartilhar Link**

Seu link será:
```
https://rca-pocket-dashboard.streamlit.app
```

**Compartilhe via:**
- 📧 E-mail
- 💬 Teams/Slack
- 📱 WhatsApp
- 🔗 Intranet da empresa

**Exemplo de mensagem:**

```
📊 Dashboard RCA Pocket está online!

Acesse: https://rca-pocket-dashboard.streamlit.app

Funcionalidades:
✅ Visualize incidências em tempo real
✅ Aplique filtros por time, área, período
✅ Exporte dados em Excel/CSV
✅ Baixe gráficos como imagem

Qualquer dúvida, entre em contato!
```

---

## 🔒 Controle de Acesso

### **Repositório Privado (Recomendado)**
- Somente pessoas com acesso ao GitHub repo podem fazer deploy
- Link continua público, mas código fica privado

### **Adicionar Autenticação (Avançado)**

Adicione login ao dashboard editando `dashboard.py`:

```python
import streamlit as st

def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["dashboard_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "Senha", type="password", on_change=password_entered, key="password"
        )
        st.write("*Digite a senha para acessar o dashboard*")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "Senha", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Senha incorreta")
        return False
    else:
        return True

# No início do main()
def main():
    if not check_password():
        st.stop()
    
    # ... resto do código
```

Adicione em Secrets:
```toml
dashboard_password = "sua_senha_aqui"
```

---

## 📱 Opção 2: Rede Local (Intranet)

Para compartilhar apenas na rede da empresa:

### **1. Descobrir seu IP:**

```powershell
ipconfig
```

Anote o "IPv4 Address" (ex: `192.168.1.50`)

### **2. Executar dashboard em rede:**

```powershell
streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8501
```

### **3. Compartilhar link:**

```
http://192.168.1.50:8501
```

⚠️ **Importante:**
- Seu computador precisa ficar ligado
- Pessoas precisam estar na mesma rede/VPN
- Pode precisar liberar porta no firewall:

```powershell
New-NetFirewallRule -DisplayName "Streamlit Dashboard" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow
```

---

## 🔄 Atualizar Dashboard Online

### **Streamlit Cloud:**

1. **Faça alterações localmente**
2. **Commit e push:**

```powershell
git add .
git commit -m "Atualizações no dashboard"
git push
```

3. **Streamlit Cloud detecta e redeploy automaticamente** (1-2 min)

### **Forçar rebuild:**
- Acesse Streamlit Cloud
- Clique em "⚙️" → "Reboot app"

---

## 📊 Monitoramento e Logs

### **Ver logs no Streamlit Cloud:**
1. Acesse seu app em share.streamlit.io
2. Clique em "⚙️ Manage app"
3. Veja logs em tempo real

### **Estatísticas de uso:**
- Streamlit Cloud mostra número de acessos
- Tempo de atividade
- Erros recentes

---

## ⚡ Melhorias de Performance

Para dashboard mais rápido online:

```python
# Adicionar no topo do dashboard.py
import streamlit as st

# Cache agressivo para dados
@st.cache_data(ttl=3600)  # Cache de 1 hora
def load_issues(config):
    # ... código existente
    
# Cache para configurações
@st.cache_resource
def load_config():
    # ... código existente
```

---

## ❓ Problemas Comuns

### **"App está em sleep mode"**
- ✅ Apps gratuitos hibernam após 7 dias sem uso
- ✅ Primeiro acesso demora ~30s para "acordar"
- ✅ Acesse periodicamente para manter ativo

### **"Erros de dependências"**
- ✅ Verifique `requirements.txt`
- ✅ Use versões específicas: `pandas==2.0.0`

### **"Dados não aparecem"**
- ✅ Verifique se `issues_cache.json` tem dados
- ✅ Configure secrets corretamente
- ✅ Teste localmente primeiro

### **"Deploy falhou"**
- ✅ Verifique logs no Streamlit Cloud
- ✅ Teste localmente: `streamlit run dashboard.py`
- ✅ Verifique sintaxe do Python

---

## 💰 Custos

### **Streamlit Cloud (Gratuito):**
- ✅ 1 app privado gratuito
- ✅ Apps públicos ilimitados
- ✅ Recursos limitados mas suficientes

### **Streamlit Cloud (Pago - $20/mês):**
- Mais recursos (CPU/RAM)
- Mais apps privados
- Suporte prioritário

---

## 🎓 Recursos Adicionais

- [Documentação Streamlit Cloud](https://docs.streamlit.io/streamlit-community-cloud)
- [Deploy Tutorial](https://docs.streamlit.io/streamlit-community-cloud/get-started)
- [Secrets Management](https://docs.streamlit.io/streamlit-community-cloud/get-started/deploy-an-app/connect-to-data-sources/secrets-management)

---

## 📞 Suporte

Problemas com deploy?
1. Verifique logs no Streamlit Cloud
2. Teste localmente primeiro
3. Consulte documentação oficial
4. Entre em contato com equipe de TI

---

**Última atualização:** Março 2026  
**Versão:** 1.0
