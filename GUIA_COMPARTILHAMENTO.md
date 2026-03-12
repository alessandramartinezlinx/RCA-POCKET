# 📤 Guia de Compartilhamento - Opção C (Envio de Arquivos)

Este guia mostra como exportar e compartilhar os dados e gráficos do RCA Pocket via arquivos.

## 🎯 Passo a Passo

### 1️⃣ Executar o Dashboard

```powershell
streamlit run dashboard.py
```

O dashboard abrirá no navegador (geralmente `http://localhost:8501`)

---

### 2️⃣ Aplicar Filtros (Opcional)

Use a barra lateral para filtrar:
- 📅 **Período**: Data inicial e final
- 👥 **Time**: Selecione times específicos
- 📁 **Área**: Filtre por área
- 🔧 **Tipo de Erro**: Escolha tipos específicos
- 📌 **Status** e **Prioridade**

---

### 3️⃣ Exportar Arquivos

Vá até a seção **"📤 Compartilhamento"** (abaixo da tabela de issues):

#### **Opção A: Excel Completo**
- Clique em **"📥 Baixar Excel Completo"**
- Salva: `RCA_Pocket.xlsx` (todas as abas e dados)
- ✅ Ideal para: Enviar base completa atualizada

#### **Opção B: Dados Filtrados**
- Clique em **"📊 Baixar Dados Filtrados"**
- Salva: `RCA_Filtrado_YYYYMMDD_HHMM.xlsx`
- ✅ Ideal para: Compartilhar apenas issues específicas (ex: "erros do time Fatlnt")

#### **Opção C: CSV da Tabela**
- Role até a tabela de issues detalhadas
- Clique em **"⬇️ Exportar CSV"**
- Salva: `rca_pocket_export_YYYYMMDD_HHMM.csv`
- ✅ Ideal para: Importar em outras ferramentas (Excel, Power BI, etc)

---

### 4️⃣ Capturar Gráficos como Imagem

Para compartilhar gráficos específicos:

**Método 1 - Botão do Gráfico (📷 Recomendado):**
1. Passe o mouse sobre qualquer gráfico
2. Aparecerá uma barra de ferramentas no canto superior direito
3. Clique no ícone de **câmera** 📷
4. Imagem PNG será baixada automaticamente (alta resolução)

**Método 2 - Captura de Tela:**
1. Pressione `Win + Shift + S` (Ferramenta de Captura do Windows)
2. Selecione a área do gráfico
3. A imagem vai para a área de transferência
4. Cole onde precisar (Ctrl+V)

---

### 5️⃣ Compartilhar Arquivos

#### **Via E-mail:**
```
Assunto: RCA Pocket - Análise de Incidências [dd/mm/yyyy]

Olá equipe,

Segue análise atualizada do RCA Pocket com os dados de [período].

Arquivos em anexo:
- RCA_Pocket.xlsx - Base completa com [X] issues
- Gráficos em PNG

Destaques:
• [X] issues críticas em aberto
• Taxa de resolução: [Y]%
• Principais áreas: [listar]

Qualquer dúvida, estou à disposição.
```

#### **Via Microsoft Teams:**
1. Vá no canal/chat desejado
2. Clique no ícone de 📎 **Anexar**
3. Selecione o arquivo exportado
4. Adicione uma mensagem contextualizando
5. Envie

#### **Via OneDrive/SharePoint:**
1. Acesse OneDrive/SharePoint
2. Crie uma pasta "RCA Pocket - [Mês/Ano]"
3. Faça upload dos arquivos
4. Clique com botão direito → **Compartilhar**
5. Adicione e-mails das pessoas
6. Configure permissões (Visualização ou Edição)
7. Envie o link

#### **Via Google Drive:**
1. Acesse [drive.google.com](https://drive.google.com)
2. Clique em **Novo** → **Envio de arquivo**
3. Selecione os arquivos exportados
4. Clique com botão direito → **Compartilhar**
5. Adicione e-mails ou gere link compartilhável
6. Envie

---

## 📋 Checklist Antes de Enviar

- [ ] Dashboard executando sem erros
- [ ] Filtros aplicados corretamente (se necessário)
- [ ] Dados atualizados (verifique data no rodapé)
- [ ] Arquivos salvos com nome descritivo
- [ ] Contexto/mensagem preparada para o destinatário
- [ ] Permissões configuradas (se usando drive)

---

## 💡 Dicas Úteis

### Para Envios Recorrentes:
Crie um template de e-mail salvo com:
- Estrutura padrão da mensagem
- Lista de distribuição
- Pasta de destino no OneDrive

### Nomenclatura dos Arquivos:
Exemplo: `RCA_Time-Fatlnt_Jan2026.xlsx`
```
RCA_[Filtro]_[Período].xlsx
```

### Automação Futura:
- Configure um agendamento no Windows para gerar Excel automaticamente
- Use Task Scheduler para rodar `python generate_excel.py` diariamente

---

## ❓ Problemas Comuns

### "Botão de download não aparece"
- ✅ Verifique se o arquivo `RCA_Pocket.xlsx` existe na pasta do projeto
- ✅ Execute `python generate_excel.py` para gerar o arquivo

### "Excel filtrado está vazio"
- ✅ Verifique se há issues após aplicar os filtros
- ✅ Tente remover alguns filtros

### "Gráficos aparecem em branco no arquivo"
- ✅ Use o botão 📷 de cada gráfico para baixar PNG
- ✅ Anexe as imagens PNG separadamente

---

## 📞 Suporte

Para dúvidas ou problemas:
1. Verifique o `MANUAL.md` na raiz do projeto
2. Consulte o `README.md` para instruções de instalação
3. Entre em contato com o time de suporte

---

**Última atualização:** Março 2026  
**Versão:** 1.0
