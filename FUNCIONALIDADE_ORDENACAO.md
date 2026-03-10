# RCA Pocket - Funcionalidade de Ordenação e Empilhamento Semanal

## 📋 Funcionalidades Implementadas

### 1. **Nova Coluna: Qtd Vínculos (H)**
- Mostra quantidade de issues linkadas/relacionadas no Jira
- **Destaque visual**:
  - **5+ vínculos**: Fundo vermelho claro (prioridade máxima)
  - **3-4 vínculos**: Fundo amarelo (atenção)
  - **0-2 vínculos**: Sem destaque

### 2. **Nova Coluna: Semana (V)**
- Identifica se a issue foi importada esta semana ou em semanas anteriores
- **Destaque visual**:
  - **"Atual"**: Fundo verde claro (issues desta semana)
  - **"Anterior"**: Fundo amarelo claro (issues antigas)

### 3. **Ordenação Inteligente**

As issues são ordenadas automaticamente seguindo esta hierarquia:

1. **Qtd Vínculos** (decrescente) - Issues com mais relacionamentos aparecem primeiro
2. **Prioridade P0 (Crítica)** - Bugs críticos têm prioridade máxima
3. **Prioridade P1 (Alta)** - Bugs de alta prioridade vêm em seguida
4. **Demais prioridades** - Média, Baixa, etc.
5. **Data de importação** (mais recente primeiro) - Dentro de cada grupo

**Exemplo de ordenação:**
```
1. MODAJOI-99199 (6 vínculos, Crítica) ← P0 com muitos links
2. MODAJOI-98089 (5 vínculos, Crítica) ← P0 com muitos links
3. MODAJOI-98267 (0 vínculos, Crítica) ← P0 sem links
4. MODAJOI-98001 (3 vínculos, Alta)    ← P1 com links
5. MODAJOI-98178 (2 vínculos, Alta)    ← P1 com links
6. MODAJOI-98045 (1 vínculo, Alta)     ← P1 com poucos links
...
```

### 4. **Empilhamento Semanal**

A cada nova importação do Jira:
- ✅ **Issues da semana atual** aparecem no **TOPO** da planilha
- ⬇️ **Issues de semanas anteriores** descem automaticamente
- 📍 Marcação visual na coluna "Semana" facilita identificação

**Fluxo:**
```
Segunda-feira (Importação 1)
├─ 10 issues novas → Linhas 1-10 (Semana: Atual)

Segunda-feira seguinte (Importação 2)
├─ 15 issues novas → Linhas 1-15 (Semana: Atual)
└─ 10 issues anteriores → Linhas 16-25 (Semana: Anterior)
```

## 🎯 Benefícios

1. **Priorização Automática**: Issues com mais impacto (muitos vínculos + P0/P1) ficam visíveis no topo
2. **Histórico Preservado**: Issues antigas não são perdidas, apenas descem na planilha
3. **Visibilidade Temporal**: Fácil identificar o que é novo vs. antigo
4. **Zero Configuração Manual**: Ordenação acontece automaticamente a cada sincronização

## 🔧 Como Usar

1. Execute `python generate_excel.py` ou escolha a opção [1] no `run.bat`
2. O sistema busca issues do Jira
3. Aplica ordenação automática (vínculos > P0 > P1)
4. Aplica empilhamento semanal (novas no topo)
5. Gera o Excel RCA_Pocket.xlsx

**Observação**: A cada nova execução na mesma semana, as issues continuam marcadas como "Atual". Na segunda-feira seguinte, elas automaticamente vão para "Anterior".

## 📊 Exemplo Visual

```
┌──────────────────────────────────────────────────────────────┐
│ Linha │ Key           │ Vínculos │ Prio    │ Semana          │
├──────────────────────────────────────────────────────────────┤
│   2   │ MODAJOI-99199 │    6 🔴  │ Crítica │ Atual (verde)   │ ← P0 + 6 links
│   3   │ MODAJOI-98089 │    5 🔴  │ Crítica │ Atual (verde)   │ ← P0 + 5 links
│   4   │ MODAJOI-98267 │    0     │ Crítica │ Atual (verde)   │ ← P0 sem links
│   5   │ MODAJOI-98001 │    3 🟡  │ Alta    │ Atual (verde)   │ ← P1 + 3 links
│   6   │ MODAJOI-98178 │    2     │ Alta    │ Atual (verde)   │ ← P1 + 2 links
│   ...
└──────────────────────────────────────────────────────────────┘
```

## 🔮 Próxima Semana (Automático)

```
┌──────────────────────────────────────────────────────────────┐
│ Linha │ Key           │ Vínculos │ Prio    │ Semana          │
├──────────────────────────────────────────────────────────────┤
│   2   │ MODAJOI-99456 │    8 🔴  │ Crítica │ Atual (verde)   │ ← NOVAS issues
│   3   │ MODAJOI-99457 │    4 🟡  │ Crítica │ Atual (verde)   │
│   ...
│  15   │ MODAJOI-99199 │    6 🔴  │ Crítica │ Anterior (amar) │ ← Issues antigas
│  16   │ MODAJOI-98089 │    5 🔴  │ Crítica │ Anterior (amar) │    descem
│   ...
└──────────────────────────────────────────────────────────────┘
```
