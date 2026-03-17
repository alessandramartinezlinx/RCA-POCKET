"""
RCA Pocket - Jira Client
========================
Responsável por:
  - Buscar issues do Jira via API REST (Personal Access Token)
  - Gerenciar cache local D+1 (evita sobrecarga no Jira Data Center)
  - Classificar tipo de erro por palavras-chave
  - Mapear issues para time/área/responsáveis
  - Fallback automático para dados MOCK quando token não configurado
"""

import json
import os
import base64
import time
import tempfile
import concurrent.futures
import re
import unicodedata
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# =============================================================================
# DADOS MOCK — Protótipo sem token real
# 30 issues realistas cobrindo Out/2025 → Mar/2026 (time Suprimentos)
# =============================================================================

_TODAY = datetime(2026, 3, 6)


def _d(days_ago, hour=10, minute=0):
    """Retorna data ISO subtraindo N dias de hoje."""
    dt = _TODAY - timedelta(days=days_ago)
    return dt.replace(hour=hour, minute=minute).strftime("%Y-%m-%dT%H:%M:%S.000+0000")


MOCK_ISSUES = [
    # ── ENTRADA XML ──────────────────────────────────────────────────────────
    {
        "key": "MODAJOI-98001",
        "fields": {
            "summary": "Erro ao importar XML NF-e: ORA-01555 snapshot too old",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(151), "updated": _d(148), "resolutiondate": _d(148),
            "assignee": {"displayName": "Vinícius Souza Martins"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "ORA-01555 ao importar XML de NF-e. Undo retention insuficiente no banco.",
            "resolution": {"name": "Resolvido"},
            "comment": {"comments": [{"body": "Aumentado undo_retention para 7200 no banco (undo_retention=7200). Deploy aplicado em produção após janela de manutenção."}]},
            "issuelinks": [{"id": "1"}, {"id": "2"}, {"id": "3"}],  # 3 vínculos
        },
    },
    {
        "key": "MODAJOI-98045",
        "fields": {
            "summary": "Timeout na consulta ao SEFAZ durante importação de XML",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(145), "updated": _d(140), "resolutiondate": _d(140),
            "assignee": {"displayName": "Vinícius Souza Martins"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "Consulta ao SEFAZ ultrapassa timeout configurado (30s). Integração externa instável.",
            "resolution": {"name": "Resolvido"},
            "issuelinks": [{"id": "1"}],  # 1 vínculo
        },
    },
    {
        "key": "MODAJOI-98089",
        "fields": {
            "summary": "Certificado digital expirado bloqueia importação de XML",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Crítica"},
            "created": _d(138), "updated": _d(135), "resolutiondate": _d(135),
            "assignee": {"displayName": "Willian Dias Brito"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "Certificado A1 da empresa expirou. Sistema falha silenciosamente sem mensagem clara.",
            "resolution": {"name": "Resolvido"},
            "comment": {"comments": [{"body": "Certificado A1 renovado (validade 3 anos). Implementado alerta automático 30 dias antes do vencimento via job agendado."}]},
            "issuelinks": [{"id": "1"}, {"id": "2"}, {"id": "3"}, {"id": "4"}, {"id": "5"}],  # 5 vínculos (P0 com muitos links)
        },
    },
    {
        "key": "MODAJOI-98134",
        "fields": {
            "summary": "XML com schema inválido não apresenta mensagem de erro adequada",
            "status": {"name": "Em Análise"},
            "priority": {"name": "Média"},
            "created": _d(130), "updated": _d(120), "resolutiondate": None,
            "assignee": {"displayName": "Vinícius Souza Martins"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "Quando fornecedor envia XML com schema divergente, sistema retorna error 500 sem detalhar.",
            "resolution": None,
            "issuelinks": [],  # 0 vínculos
        },
    },
    {
        "key": "MODAJOI-98178",
        "fields": {
            "summary": "Duplicate key violation ao reprocessar XML já importado",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(120), "updated": _d(115), "resolutiondate": _d(115),
            "assignee": {"displayName": "Vinícius Souza Martins"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "Duplicate key constraint SQL ao reimportar XML. Falta validação de idempotência.",
            "resolution": {"name": "Resolvido"},
            "issuelinks": [{}, {}],  # 2 vínculos
        },
    },
    {
        "key": "MODAJOI-98223",
        "fields": {
            "summary": "Lentidão na importação de XMLs em lote acima de 50 arquivos",
            "status": {"name": "Aberto"},
            "priority": {"name": "Média"},
            "created": _d(125), "updated": _d(100), "resolutiondate": None,
            "assignee": {"displayName": "Willian Dias Brito"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "Importação de lote com 50+ arquivos demora 10min+. Processamento síncrono sem fila.",
            "resolution": None,
        },
    },
    {
        "key": "MODAJOI-98756",
        "fields": {
            "summary": "ORA-00060 deadlock ao processar lote de XMLs simultâneos",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(95), "updated": _d(90), "resolutiondate": _d(90),
            "assignee": {"displayName": "Willian Dias Brito"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "Deadlock ORA-00060 ao processar múltiplos XMLs em paralelo. Contention em tabela de staging.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-98800",
        "fields": {
            "summary": "Inconsistência de quantidade após importação de XML de devolução",
            "status": {"name": "Em Análise"},
            "priority": {"name": "Alta"},
            "created": _d(80), "updated": _d(60), "resolutiondate": None,
            "assignee": {"displayName": "Vinícius Souza Martins"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "Após importar XML de devolução, estoque fica negativo. Exception no cálculo de sinal da movimentação.",
            "resolution": None,
        },
    },
    {
        "key": "MODAJOI-98933",
        "fields": {
            "summary": "SEFAZ retorna erro 539 não tratado na importação de CT-e",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(70), "updated": _d(65), "resolutiondate": _d(65),
            "assignee": {"displayName": "Vinícius Souza Martins"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "Código de retorno 539 do SEFAZ não mapeado no handler. NullPointerException no parser.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-99066",
        "fields": {
            "summary": "Importação XML falha silenciosamente sem log de erro gerado",
            "status": {"name": "Em Análise"},
            "priority": {"name": "Média"},
            "created": _d(50), "updated": _d(40), "resolutiondate": None,
            "assignee": {"displayName": "Willian Dias Brito"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "Processo de importação termina sem erro mas arquivo não processado. Bug no exception handler.",
            "resolution": None,
        },
    },
    {
        "key": "MODAJOI-99199",
        "fields": {
            "summary": "Thread leak em processamento paralelo de XMLs em lote",
            "status": {"name": "Em Análise"},
            "priority": {"name": "Crítica"},
            "created": _d(30), "updated": _d(20), "resolutiondate": None,
            "assignee": {"displayName": "Vinícius Souza Martins"},
            "labels": ["Entrada XML", "Suprimentos"],
            "description": "Pool de threads não libera workers após processamento. JVM heap cresce progressivamente. OutOfMemory iminente.",
            "resolution": None,
            "issuelinks": [{}, {}, {}, {}, {}, {}],  # 6 vínculos (P0 com muitos links - deve ficar no topo)
        },
    },
    # ── BALANÇO ──────────────────────────────────────────────────────────────
    {
        "key": "MODAJOI-98267",
        "fields": {
            "summary": "Timeout na execução do balanço em lojas com mais de 50k itens",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Crítica"},
            "created": _d(148), "updated": _d(143), "resolutiondate": _d(143),
            "assignee": {"displayName": "Willian Dias Brito"},
            "labels": ["Balanço", "Suprimentos"],
            "description": "Query de consolidação de balanço ultrapassa 30min em lojas grandes. Full scan na tabela de produtos sem índice.",
            "resolution": {"name": "Resolvido"},
            "comment": {"comments": [{"body": "Criado índice composto idx_produto_loja_cod em tabela de produtos. Tempo caiu de 30min para 45s. Full scan eliminado."}]},
        },
    },
    {
        "key": "MODAJOI-98312",
        "fields": {
            "summary": "Deadlock ao salvar contagem simultânea de múltiplos coletores",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(135), "updated": _d(130), "resolutiondate": _d(130),
            "assignee": {"displayName": "João Vitor Leone"},
            "labels": ["Balanço", "Suprimentos"],
            "description": "Deadlock SQL ao gravar contagens de balanço simultâneas. Lock em linha da tabela de partidas.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-98356",
        "fields": {
            "summary": "Relatório de balanço retorna divergência incorreta de quantidade",
            "status": {"name": "Em Análise"},
            "priority": {"name": "Alta"},
            "created": _d(122), "updated": _d(100), "resolutiondate": None,
            "assignee": {"displayName": "Willian Dias Brito"},
            "labels": ["Balanço", "Suprimentos"],
            "description": "Relatório apresenta divergências que não existem. Bug no cálculo quando há múltiplos depósitos.",
            "resolution": None,
        },
    },
    {
        "key": "MODAJOI-98401",
        "fields": {
            "summary": "OutOfMemoryError ao gerar relatório de balanço com histórico completo",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(118), "updated": _d(112), "resolutiondate": _d(112),
            "assignee": {"displayName": "Willian Dias Brito"},
            "labels": ["Balanço", "Suprimentos"],
            "description": "Heap overflow ao carregar histórico de 5 anos no relatório de balanço. Falta paginação na query.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-98445",
        "fields": {
            "summary": "Query de divergência no balanço demora 40 minutos para executar",
            "status": {"name": "Aberto"},
            "priority": {"name": "Alta"},
            "created": _d(108), "updated": _d(90), "resolutiondate": None,
            "assignee": {"displayName": "João Vitor Leone"},
            "labels": ["Balanço", "Suprimentos"],
            "description": "Query SQL sem índice adequado. Plano de execução com hash join em tabela de 2M registros.",
            "resolution": None,
        },
    },
    {
        "key": "MODAJOI-98844",
        "fields": {
            "summary": "Balanço parcial não consolida corretamente com contagens anteriores",
            "status": {"name": "Aberto"},
            "priority": {"name": "Média"},
            "created": _d(85), "updated": _d(60), "resolutiondate": None,
            "assignee": {"displayName": "Willian Dias Brito"},
            "labels": ["Balanço", "Suprimentos"],
            "description": "Quando balanço parcial inicia com contagens anteriores abertas, consolidação soma duplicado.",
            "resolution": None,
        },
    },
    {
        "key": "MODAJOI-98977",
        "fields": {
            "summary": "Erro de permissão no schema de BD ao abrir módulo de balanço",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(75), "updated": _d(70), "resolutiondate": _d(70),
            "assignee": {"displayName": "Willian Dias Brito"},
            "labels": ["Balanço", "Suprimentos"],
            "description": "Usuário do sistema sem grant SELECT no schema de staging após deploy. Configuração de permissão incorreta.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-99110",
        "fields": {
            "summary": "Índice corrompido causa lentidão crítica em consultas de balanço",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(55), "updated": _d(48), "resolutiondate": _d(48),
            "assignee": {"displayName": "João Vitor Leone"},
            "labels": ["Balanço", "Suprimentos"],
            "description": "Index corruption identificado pelo DBA. Rebuild do índice resolveu a lentidão de query.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-99243",
        "fields": {
            "summary": "Balanço não finaliza quando há produto sem código de barras",
            "status": {"name": "Aberto"},
            "priority": {"name": "Média"},
            "created": _d(25), "updated": _d(15), "resolutiondate": None,
            "assignee": {"displayName": "Ana Paula Coelho"},
            "labels": ["Balanço", "Suprimentos"],
            "description": "NullPointerException ao finalizar balanço quando produto não possui código de barras cadastrado.",
            "resolution": None,
        },
    },
    # ── COMPRAS 2.0 ──────────────────────────────────────────────────────────
    {
        "key": "MODAJOI-98489",
        "fields": {
            "summary": "Sugestão de compras retorna valores nulos para produtos novos",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(140), "updated": _d(133), "resolutiondate": _d(133),
            "assignee": {"displayName": "Rafael Flecha"},
            "labels": ["Compras 2.0", "Suprimentos"],
            "description": "Produto sem histórico de vendas retorna null na engine de sugestão. NullPointerException no cálculo de média.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-98534",
        "fields": {
            "summary": "API de fornecedores timeout após 30s na tela de sugestão de compras",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(128), "updated": _d(122), "resolutiondate": _d(122),
            "assignee": {"displayName": "Mauricio Maia"},
            "labels": ["Compras 2.0", "Suprimentos"],
            "description": "Endpoint de consulta de fornecedores demora 30s+ em catálogos grandes. Query sem paginação.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-98578",
        "fields": {
            "summary": "Cálculo de estoque mínimo incorreto: overflow numérico em produtos com alta rotatividade",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Crítica"},
            "created": _d(115), "updated": _d(108), "resolutiondate": _d(108),
            "assignee": {"displayName": "Rafael Flecha"},
            "labels": ["Compras 2.0", "Suprimentos"],
            "description": "Integer overflow no cálculo de estoque mínimo para SKUs com >32k vendas/mês. Campo definido como INT32.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-98622",
        "fields": {
            "summary": "Tela de compras 2.0 não carrega para usuário com perfil Comprador",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(100), "updated": _d(94), "resolutiondate": _d(94),
            "assignee": {"displayName": "Mauricio Maia"},
            "labels": ["Compras 2.0", "Suprimentos"],
            "description": "Permissão de acesso ao módulo não configurada para perfil Comprador após atualização de roles.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-98667",
        "fields": {
            "summary": "Integração com ERP retorna 500 ao confirmar pedido de compra com 200+ itens",
            "status": {"name": "Em Análise"},
            "priority": {"name": "Crítica"},
            "created": _d(88), "updated": _d(70), "resolutiondate": None,
            "assignee": {"displayName": "Rafael Flecha"},
            "labels": ["Compras 2.0", "Suprimentos"],
            "description": "Endpoint /api/compras/confirmar retorna HTTP 500 quando pedido possui 200+ itens. StackOverflow no parser.",
            "resolution": None,
        },
    },
    {
        "key": "MODAJOI-98711",
        "fields": {
            "summary": "Token JWT expira durante sessão longa de compras sem aviso ao usuário",
            "status": {"name": "Aberto"},
            "priority": {"name": "Média"},
            "created": _d(92), "updated": _d(75), "resolutiondate": None,
            "assignee": {"displayName": "Mauricio Maia"},
            "labels": ["Compras 2.0", "Suprimentos"],
            "description": "Após 2h de sessão token JWT expirado. Usuário perde alterações sem aviso. Autenticação silenciosa falha.",
            "resolution": None,
        },
    },
    {
        "key": "MODAJOI-98889",
        "fields": {
            "summary": "Performance degradada no módulo de sugestão em horários de pico",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(68), "updated": _d(60), "resolutiondate": _d(60),
            "assignee": {"displayName": "Rafael Flecha"},
            "labels": ["Compras 2.0", "Suprimentos"],
            "description": "Durante horário de pico (12h-14h), tela de sugestão demora 60s+. Connection pool esgotado.",
            "resolution": {"name": "Resolvido"},
        },
    },
    {
        "key": "MODAJOI-99021",
        "fields": {
            "summary": "Sugestão de compras ignora parâmetro de estoque de segurança configurado",
            "status": {"name": "Aberto"},
            "priority": {"name": "Média"},
            "created": _d(45), "updated": _d(30), "resolutiondate": None,
            "assignee": {"displayName": "Mauricio Maia"},
            "labels": ["Compras 2.0", "Suprimentos"],
            "description": "Parâmetro estoque_segurança não lido da configuração de empresa. Usando valor default zerado.",
            "resolution": None,
        },
    },
    {
        "key": "MODAJOI-99154",
        "fields": {
            "summary": "API de compras retorna 401 após renovação de certificado do servidor",
            "status": {"name": "Aberto"},
            "priority": {"name": "Alta"},
            "created": _d(35), "updated": _d(25), "resolutiondate": None,
            "assignee": {"displayName": "Rafael Flecha"},
            "labels": ["Compras 2.0", "Suprimentos"],
            "description": "Após renovação de certificado SSL, client-side não atualizou truststore. 401 em todas as chamadas.",
            "resolution": None,
        },
    },
    {
        "key": "MODAJOI-99287",
        "fields": {
            "summary": "Sugestão de compras duplica pedidos em caso de erro de rede com retry",
            "status": {"name": "Resolvido"},
            "priority": {"name": "Alta"},
            "created": _d(18), "updated": _d(10), "resolutiondate": _d(10),
            "assignee": {"displayName": "Rafael Flecha"},
            "labels": ["Compras 2.0", "Suprimentos"],
            "description": "Sem idempotência no endpoint de criação de pedido. Retry automático do frontend gera duplicatas no banco.",
            "resolution": {"name": "Resolvido"},
        },
    },
]

# Ações pré-preenchidas para demonstração (preventivas e remediações)
MOCK_ACTIONS = [
    {"key": "MODAJOI-98001", "acao": "Aumentar UNDO_RETENTION no banco de 900s para 3600s", "responsavel": "Willian Dias Brito", "data_prevista": "2025-10-10", "data_conclusao": "2025-10-08", "status_acao": "Concluída", "tipo_acao": "Remediação", "observacoes": "Parâmetro ajustado pelo DBA em produção."},
    {"key": "MODAJOI-98001", "acao": "Criar monitoramento proativo de utilização de undo tablespace (alerta > 80%)", "responsavel": "Willian Dias Brito", "data_prevista": "2025-10-30", "data_conclusao": "", "status_acao": "Em Andamento", "tipo_acao": "Preventiva", "observacoes": "Script de monitoramento em desenvolvimento."},
    {"key": "MODAJOI-98045", "acao": "Aumentar timeout de consulta SEFAZ de 30s para 60s", "responsavel": "Vinícius Souza Martins", "data_prevista": "2025-10-14", "data_conclusao": "2025-10-12", "status_acao": "Concluída", "tipo_acao": "Remediação", "observacoes": ""},
    {"key": "MODAJOI-98089", "acao": "Criar alerta automático de expiração de certificado com 30 dias de antecedência", "responsavel": "Willian Dias Brito", "data_prevista": "2025-11-15", "data_conclusao": "", "status_acao": "Em Andamento", "tipo_acao": "Preventiva", "observacoes": "Automação via E-mail agendado."},
    {"key": "MODAJOI-98178", "acao": "Implementar validação de idempotência na importação de XML (chave de controle)", "responsavel": "Vinícius Souza Martins", "data_prevista": "2025-11-10", "data_conclusao": "2025-11-08", "status_acao": "Concluída", "tipo_acao": "Preventiva", "observacoes": ""},
    {"key": "MODAJOI-98267", "acao": "Adicionar índice composto na query de consolidação de balanço (idx_balanco_produto)", "responsavel": "João Vitor Leone", "data_prevista": "2025-10-16", "data_conclusao": "2025-10-15", "status_acao": "Concluída", "tipo_acao": "Remediação", "observacoes": "Índice reduziu tempo de 30min para 45s."},
    {"key": "MODAJOI-98312", "acao": "Implementar retry com backoff exponencial em contagens simultâneas de balanço", "responsavel": "João Vitor Leone", "data_prevista": "2025-11-05", "data_conclusao": "2025-11-03", "status_acao": "Concluída", "tipo_acao": "Remediação", "observacoes": ""},
    {"key": "MODAJOI-98401", "acao": "Implementar paginação no relatório de balanço (máx. 10k registros por página)", "responsavel": "Willian Dias Brito", "data_prevista": "2025-11-20", "data_conclusao": "2025-11-18", "status_acao": "Concluída", "tipo_acao": "Preventiva", "observacoes": ""},
    {"key": "MODAJOI-98489", "acao": "Tratar produtos sem histórico de vendas com valor default 0 na engine de sugestão", "responsavel": "Rafael Flecha", "data_prevista": "2025-11-12", "data_conclusao": "2025-11-10", "status_acao": "Concluída", "tipo_acao": "Remediação", "observacoes": ""},
    {"key": "MODAJOI-98534", "acao": "Adicionar paginação na consulta de fornecedores (100 por página)", "responsavel": "Mauricio Maia", "data_prevista": "2025-11-25", "data_conclusao": "2025-11-22", "status_acao": "Concluída", "tipo_acao": "Remediação", "observacoes": ""},
    {"key": "MODAJOI-98578", "acao": "Migrar campo de estoque mínimo de INT32 para INT64 em todas as tabelas", "responsavel": "Rafael Flecha", "data_prevista": "2025-12-10", "data_conclusao": "2025-12-08", "status_acao": "Concluída", "tipo_acao": "Remediação", "observacoes": ""},
    {"key": "MODAJOI-98578", "acao": "Criar checklist de code review obrigatório para campos numéricos em módulos de cálculo", "responsavel": "Guilherme Rocha", "data_prevista": "2025-12-20", "data_conclusao": "", "status_acao": "Em Andamento", "tipo_acao": "Preventiva", "observacoes": "Documento em revisão pelo time."},
    {"key": "MODAJOI-98622", "acao": "Corrigir mapeamento de permissões para perfil Comprador no módulo de Compras 2.0", "responsavel": "Mauricio Maia", "data_prevista": "2025-12-05", "data_conclusao": "2025-12-03", "status_acao": "Concluída", "tipo_acao": "Remediação", "observacoes": ""},
    {"key": "MODAJOI-98756", "acao": "Adicionar controle de concorrência com lock optimista na tabela de staging de XML", "responsavel": "Willian Dias Brito", "data_prevista": "2026-01-15", "data_conclusao": "2026-01-14", "status_acao": "Concluída", "tipo_acao": "Preventiva", "observacoes": ""},
    {"key": "MODAJOI-98889", "acao": "Aumentar pool de conexões de 10 para 30 no módulo de Compras 2.0", "responsavel": "Rafael Flecha", "data_prevista": "2026-01-20", "data_conclusao": "2026-01-18", "status_acao": "Concluída", "tipo_acao": "Remediação", "observacoes": ""},
    {"key": "MODAJOI-98933", "acao": "Mapear todos os códigos de retorno SEFAZ no handler de erros", "responsavel": "Vinícius Souza Martins", "data_prevista": "2026-01-30", "data_conclusao": "2026-01-28", "status_acao": "Concluída", "tipo_acao": "Preventiva", "observacoes": "Lista completa de códigos SEFAZ mapeada."},
    {"key": "MODAJOI-98977", "acao": "Corrigir scripts de deploy para incluir grant de permissão no schema de staging", "responsavel": "Willian Dias Brito", "data_prevista": "2026-02-05", "data_conclusao": "2026-02-04", "status_acao": "Concluída", "tipo_acao": "Remediação", "observacoes": ""},
    {"key": "MODAJOI-99110", "acao": "Implementar rebuild automático de índices corrompidos via job noturno", "responsavel": "João Vitor Leone", "data_prevista": "2026-02-20", "data_conclusao": "", "status_acao": "Em Andamento", "tipo_acao": "Preventiva", "observacoes": ""},
    {"key": "MODAJOI-99287", "acao": "Implementar idempotência no endpoint de criação de pedido (chave de deduplicação)", "responsavel": "Rafael Flecha", "data_prevista": "2026-03-05", "data_conclusao": "2026-03-04", "status_acao": "Concluída", "tipo_acao": "Preventiva", "observacoes": ""},
]


# =============================================================================
# CAMPOS MANUAIS MOCK — usados para demo quando não há Excel preenchido
# Simula o preenchimento manual que o time faz na aba 📊 Dados
# =============================================================================
_MOCK_MANUAL = {
    # Campos: possui_ta, ajuste_realizado, problema_resolvido, analise_causa,
    #         acomp_area (FFC/FatInt/SupCrmImp/RC),
    #         acomp_responsavel, acomp_acao, acomp_status_acao, acomp_data_conclusao
    "MODAJOI-98001": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de banco de dados",
        "problema_resolvido": "Sim", "analise_causa": "Undo retention insuficiente causava ORA-01555 em transações longas",
        "item_resolucao_def": "Revisar parâmetro UNDO_RETENTION via procedure agendada",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Willian Dias Brito",
        "acomp_acao": "Implementar job de monitoramento de undo tablespace (alerta > 80%)",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2025-10-10",
    },
    "MODAJOI-98045": {
        "possui_ta": "Não", "ajuste_realizado": "Ajuste de configuração",
        "problema_resolvido": "Sim", "analise_causa": "Timeout de 30s insuficiente para SEFAZ em horários de pico",
        "item_resolucao_def": "Aumentar timeout SEFAZ e implementar retry com backoff exponencial",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Vinícius Souza Martins",
        "acomp_acao": "Configurar timeout para 60s e adicionar retry com backoff de 3 tentativas",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2025-10-15",
    },
    "MODAJOI-98089": {
        "possui_ta": "Sim", "ajuste_realizado": "Preventiva / Processo",
        "problema_resolvido": "Sim", "analise_causa": "Ausência de processo de renovação antecipada de certificado A1",
        "item_resolucao_def": "Criar job de alerta 30 dias antes do vencimento do certificado",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Willian Dias Brito",
        "acomp_acao": "Automatizar renovação de certificado com alerta antecipado por e-mail",
        "acomp_status_acao": "Andamento", "acomp_data_conclusao": None,
    },
    "MODAJOI-98134": {
        "possui_ta": "Não", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Não", "analise_causa": "Schema inválido do XML não validado antes do processamento",
        "item_resolucao_def": "Validar schema XML antes do processamento com XSD",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Vinícius Souza Martins",
        "acomp_acao": "Implementar validação XSD no início do pipeline de importação",
        "acomp_status_acao": "Análise", "acomp_data_conclusao": None,
    },
    "MODAJOI-98178": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Sim", "analise_causa": "Falta de validação de idempotência no endpoint de importação XML",
        "item_resolucao_def": "Implementar controle de idempotência no import de XML",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Vinícius Souza Martins",
        "acomp_acao": "Adicionar chave de controle única por XML importado na tabela de staging",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2025-11-10",
    },
    "MODAJOI-98223": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Não", "analise_causa": "Processamento síncrono sem fila para lotes grandes de XML",
        "item_resolucao_def": "Migrar processamento em lote para fila assíncrona",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Willian Dias Brito",
        "acomp_acao": "Estudar viabilidade de fila RabbitMQ para processamento assíncrono de XMLs",
        "acomp_status_acao": "Bloqueado", "acomp_data_conclusao": None,
    },
    "MODAJOI-98267": {
        "possui_ta": "Sim", "ajuste_realizado": "Otimização de banco de dados",
        "problema_resolvido": "Sim", "analise_causa": "Full scan em tabela de produtos sem índice composto adequado",
        "item_resolucao_def": "Criar índice composto idx_produto_loja na consolidação de balanço",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "João Vitor Leone",
        "acomp_acao": "Criar índice e validar plano de execução com DBA",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2025-10-18",
    },
    "MODAJOI-98312": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Sim", "analise_causa": "Lock em linha durante gravação simultânea sem controle de concorrência",
        "item_resolucao_def": "Implementar lock optimista em contagens simultâneas de balanço",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "João Vitor Leone",
        "acomp_acao": "Refatorar gravação de contagens com retry optimista + backoff",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2025-11-05",
    },
    "MODAJOI-98356": {
        "possui_ta": "Não", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Não", "analise_causa": "Cálculo de divergência incorreto quando há múltiplos depósitos",
        "item_resolucao_def": "Corrigir lógica de cálculo de divergência com múltiplos depósitos",
        "acomp_area": "FatInt", "acomp_responsavel": "Willian Dias Brito",
        "acomp_acao": "Revisar e corrigir cálculo de divergência para cenário multi-depósito",
        "acomp_status_acao": "Andamento", "acomp_data_conclusao": None,
    },
    "MODAJOI-98401": {
        "possui_ta": "Não", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Sim", "analise_causa": "Ausência de paginação causava carga total do histórico em memória",
        "item_resolucao_def": "Paginar relatório de balanço com no máximo 10k registros",
        "acomp_area": "FatInt", "acomp_responsavel": "Willian Dias Brito",
        "acomp_acao": "Implementar paginação server-side no relatório de balanço",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2025-11-20",
    },
    "MODAJOI-98445": {
        "possui_ta": "Não", "ajuste_realizado": "Otimização de banco de dados",
        "problema_resolvido": "Não", "analise_causa": "Query de divergência sem índice adequado, plan com hash join em 2M registros",
        "item_resolucao_def": "Adicionar índice na query de divergência de balanço",
        "acomp_area": "FatInt", "acomp_responsavel": "João Vitor Leone",
        "acomp_acao": "Analisar plano de execução e criar índice com DBA",
        "acomp_status_acao": "Análise", "acomp_data_conclusao": None,
    },
    "MODAJOI-98489": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Sim", "analise_causa": "Produto sem histórico gerava NullPointerException na engine de sugestão",
        "item_resolucao_def": "Tratar produto sem histórico com valor default 0 na engine",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Rafael Flecha",
        "acomp_acao": "Adicionar tratamento de null safety na engine de sugestão de compras",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2025-11-12",
    },
    "MODAJOI-98534": {
        "possui_ta": "Não", "ajuste_realizado": "Otimização de banco de dados",
        "problema_resolvido": "Sim", "analise_causa": "Consulta de fornecedores sem paginação retornava catálogo completo de uma vez",
        "item_resolucao_def": "Paginar consulta de fornecedores a 100 itens por página",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Mauricio Maia",
        "acomp_acao": "Implementar paginação no endpoint de fornecedores",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2025-11-25",
    },
    "MODAJOI-98578": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Sim", "analise_causa": "Integer overflow em INT32 para SKUs com volume de vendas acima de 32k/mês",
        "item_resolucao_def": "Migrar campo estoque mínimo de INT32 para INT64",
        "acomp_area": "FFC", "acomp_responsavel": "Rafael Flecha",
        "acomp_acao": "Migrar tipo de dados e criar checklist de code review para campos numéricos",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2025-12-10",
    },
    "MODAJOI-98622": {
        "possui_ta": "Não", "ajuste_realizado": "Configuração / Parâmetro",
        "problema_resolvido": "Sim", "analise_causa": "Perfil Comprador não recebeu grant correto na atualização de roles",
        "item_resolucao_def": "Corrigir mapeamento de permissões para perfil Comprador no Compras 2.0",
        "acomp_area": "RC", "acomp_responsavel": "Mauricio Maia",
        "acomp_acao": "Corrigir script de configuração de roles e validar em todos os ambientes",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2025-12-05",
    },
    "MODAJOI-98667": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Não", "analise_causa": "StackOverflow no parser ao processar pedidos com 200+ itens",
        "item_resolucao_def": "Corrigir StackOverflow no parser de pedidos com 200+ itens",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Rafael Flecha",
        "acomp_acao": "Refatorar parser para processamento iterativo em vez de recursivo",
        "acomp_status_acao": "Andamento", "acomp_data_conclusao": None,
    },
    "MODAJOI-98711": {
        "possui_ta": "Não", "ajuste_realizado": "Preventiva / Processo",
        "problema_resolvido": "Não", "analise_causa": "Autenticação silenciosa não renova token JWT em sessões longas",
        "item_resolucao_def": "Implementar refresh token automático antes da expiração",
        "acomp_area": "RC", "acomp_responsavel": "Mauricio Maia",
        "acomp_acao": "Implementar interceptor para renovar token 5 min antes de expirar",
        "acomp_status_acao": "Análise", "acomp_data_conclusao": None,
    },
    "MODAJOI-98756": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Sim", "analise_causa": "Contention em tabela de staging sem controle de lock optimista",
        "item_resolucao_def": "Implementar lock optimista em tabela de staging de XML",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Willian Dias Brito",
        "acomp_acao": "Adicionar controle de concorrência com versioning na tabela de staging",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2026-01-15",
    },
    "MODAJOI-98800": {
        "possui_ta": "Não", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Não", "analise_causa": "Cálculo de sinal incorreto na movimentação de devolução XML",
        "item_resolucao_def": "Corrigir cálculo de sinal em XML de devolução",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Vinícius Souza Martins",
        "acomp_acao": "Revisar lógica de sinal na movimentação de devolução",
        "acomp_status_acao": "Bloqueado", "acomp_data_conclusao": None,
    },
    "MODAJOI-98844": {
        "possui_ta": "Não", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Não", "analise_causa": "Consolidação de balanço parcial soma duplicado com contagens anteriores",
        "item_resolucao_def": "Corrigir consolidação de balanço parcial com contagens abertas",
        "acomp_area": "FatInt", "acomp_responsavel": "Willian Dias Brito",
        "acomp_acao": "Revisar lógica de consolidação para ignorar contagens do período anterior",
        "acomp_status_acao": "Análise", "acomp_data_conclusao": None,
    },
    "MODAJOI-98889": {
        "possui_ta": "Não", "ajuste_realizado": "Ajuste de configuração",
        "problema_resolvido": "Sim", "analise_causa": "Pool de conexões esgotado em horário de pico por configuração subdimensionada",
        "item_resolucao_def": "Aumentar pool de conexões de 10 para 30 no módulo Compras 2.0",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Rafael Flecha",
        "acomp_acao": "Ajustar configuração do pool e monitorar utilização em pico",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2026-01-20",
    },
    "MODAJOI-98933": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Sim", "analise_causa": "Código 539 do SEFAZ não mapeado no handler, causando NullPointerException",
        "item_resolucao_def": "Mapear todos os códigos de retorno SEFAZ no handler de erros",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Vinícius Souza Martins",
        "acomp_acao": "Criar mapa completo de códigos SEFAZ e cobrir com testes unitários",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2026-01-30",
    },
    "MODAJOI-98977": {
        "possui_ta": "Não", "ajuste_realizado": "Configuração / Parâmetro",
        "problema_resolvido": "Sim", "analise_causa": "Script de deploy não incluía grant de SELECT no schema de staging",
        "item_resolucao_def": "Corrigir scripts de deploy para incluir grants de permissão",
        "acomp_area": "RC", "acomp_responsavel": "Willian Dias Brito",
        "acomp_acao": "Atualizar pipeline de deploy com script de grant automático",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2026-02-05",
    },
    "MODAJOI-99021": {
        "possui_ta": "Não", "ajuste_realizado": "Configuração / Parâmetro",
        "problema_resolvido": "Não", "analise_causa": "Parâmetro estoque_segurança não lido da configuração de empresa",
        "item_resolucao_def": "Corrigir leitura do parâmetro estoque_segurança da configuração",
        "acomp_area": "FFC", "acomp_responsavel": "Mauricio Maia",
        "acomp_acao": "Corrigir bug de leitura de parâmetro e adicionar teste de integração",
        "acomp_status_acao": "Andamento", "acomp_data_conclusao": None,
    },
    "MODAJOI-99110": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de banco de dados",
        "problema_resolvido": "Sim", "analise_causa": "Índice corrompido sem processo automatizado de detecção e reconstrução",
        "item_resolucao_def": "Implementar rebuild automático de índices corrompidos",
        "acomp_area": "FatInt", "acomp_responsavel": "João Vitor Leone",
        "acomp_acao": "Criar job noturno de verificação e rebuild de índices",
        "acomp_status_acao": "Andamento", "acomp_data_conclusao": None,
    },
    "MODAJOI-99154": {
        "possui_ta": "Sim", "ajuste_realizado": "Configuração / Parâmetro",
        "problema_resolvido": "Não", "analise_causa": "Truststore do client não atualizado após renovação de certificado SSL",
        "item_resolucao_def": "Atualizar truststore e automatizar renovação SSL no client",
        "acomp_area": "RC", "acomp_responsavel": "Rafael Flecha",
        "acomp_acao": "Criar script de atualização de truststore e incluir no processo de renovação",
        "acomp_status_acao": "Análise", "acomp_data_conclusao": None,
    },
    "MODAJOI-99243": {
        "possui_ta": "Não", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Não", "analise_causa": "NullPointerException ao finalizar balanço com produto sem código de barras",
        "item_resolucao_def": "Tratar produto sem código de barras no encerramento do balanço",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Ana Paula Coelho",
        "acomp_acao": "Adicionar null check no campo código de barras antes de finalizar balanço",
        "acomp_status_acao": "Análise", "acomp_data_conclusao": None,
    },
    "MODAJOI-99287": {
        "possui_ta": "Sim", "ajuste_realizado": "Correção de código",
        "problema_resolvido": "Sim", "analise_causa": "Endpoint sem idempotência combinado com retry automático do frontend",
        "item_resolucao_def": "Implementar idempotência no endpoint de criação de pedido",
        "acomp_area": "SupCrmImp", "acomp_responsavel": "Rafael Flecha",
        "acomp_acao": "Adicionar chave de deduplicação e tratar responses idempotentes",
        "acomp_status_acao": "Concluído", "acomp_data_conclusao": "2026-03-05",
    },
    # restante sem avaliação ainda (Empty → NaN no Excel)
}


# =============================================================================
# CLASSIFICADOR DE TIPO DE ERRO

# =============================================================================

def classify_error_type(text: str, tipos_config: dict) -> tuple:
    """
    Classifica tipo de erro por palavras-chave no texto da issue.
    Retorna (tipo: str, precisa_revisao: bool)
    """
    if not text:
        return "Outro", True

    text_lower = text.lower()
    scores = {}

    for tipo, config in tipos_config.items():
        if tipo == "Outro":
            continue
        keywords = config.get("keywords", [])
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            scores[tipo] = score

    if not scores:
        return "Outro", True

    best_type = max(scores, key=scores.get)
    max_score = scores[best_type]
    needs_review = max_score <= 1  # baixa confiança = uma única keyword

    return best_type, needs_review


def _parse_date(date_str: str):
    """Converte string de data ISO para datetime ou None."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return None


def map_issue_to_area(labels: list, times_config: dict) -> dict:
    """Mapeia labels da issue para time/área/responsáveis conforme config."""
    result = {
        "time": "Não Mapeado",
        "area": "Não Mapeado",
        "qa_principal": "",
        "qa_secundario": "",
        "dev_principal": "",
        "dev_secundario": "",
    }

    if not labels:
        return result

    labels_lower = [lbl.lower() for lbl in labels]

    # 1. Prioriza Venda Fácil se presente
    for time_name, time_data in times_config.items():
        for area in time_data.get("areas", []):
            if area["nome"].lower() == "venda fácil" or area["nome"].lower() == "venda facil":
                area_labels = [lbl.lower() for lbl in area.get("labels_jira", [])]
                if any(al in labels_lower for al in area_labels):
                    result.update({
                        "time": time_name,
                        "area": area["nome"],
                        "qa_principal": area.get("qa_principal", ""),
                        "qa_secundario": area.get("qa_secundario", ""),
                        "dev_principal": area.get("dev_principal", ""),
                        "dev_secundario": area.get("dev_secundario", ""),
                    })
                    return result

    # 2. Mapeamento padrão (ordem YAML)
    for time_name, time_data in times_config.items():
        for area in time_data.get("areas", []):
            area_labels = [lbl.lower() for lbl in area.get("labels_jira", [])]
            if any(al in labels_lower for al in area_labels):
                result.update({
                    "time": time_name,
                    "area": area["nome"],
                    "qa_principal": area.get("qa_principal", ""),
                    "qa_secundario": area.get("qa_secundario", ""),
                    "dev_principal": area.get("dev_principal", ""),
                    "dev_secundario": area.get("dev_secundario", ""),
                })
                return result

    return result


# =============================================================================
# INFERÊNCIA INTELIGENTE DE TIME/ÁREA (fallback quando não há labels)
# =============================================================================

KEYWORDS_TIME_AREA = {
    "Suprimentos": {
        "Entrada XML": ["xml", "nfe", "nf-e", "nota fiscal", "entrada", "sefaz", "danfe"],
        "Balanço": ["balanço", "balanco", "inventário", "inventario", "contagem", "estoque físico"],
        "Compras 2.0": ["compras", "compra", "pedido de compra", "sugestão de compra", "sugestao compras"],
        "Estoque": ["estoque", "movimentação", "movimentacao", "saldo", "deposito", "depósito"]
    },
    "FFC": {
        "Conciliadores": ["conciliador", "conciliação", "conciliacao", "pagamento", "recebimento"],
        "Gestão Financeira": ["gestão financeira", "gestao financeira", "financeiro", "contas a pagar", "contas a receber"],
        "NF-e": ["emissão", "emissao", "faturamento", "nf-e", "nota fiscal saída"],
        "Rejeições": ["rejeição", "rejeicao", "rejeições", "rejeicoes", "sefaz rejeitou", "erro sefaz"]
    },
    "FatInt": {
        "Venda Fácil": ["venda fácil", "venda facil", "pdv", "pos", "caixa", "frente de loja", "checkout"],
        "B2C": ["b2c", "e-commerce", "ecommerce", "loja virtual", "marketplace", "carrinho"],
        "B2B": ["b2b", "atacado", "distribuidora"],
        "Integração": ["integração", "integracao", "webhook", "api", "rest", "sincronização"]
    }
}


def _normalize_text_for_match(text: str) -> str:
    """Normaliza texto para matching tolerante a acentos e caixa."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", str(text))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.lower()


def _empty_area_map(time_name: str = "Não Mapeado") -> dict:
    return {
        "time": time_name,
        "area": "" if time_name != "Não Mapeado" else "Não Mapeado",
        "qa_principal": "",
        "qa_secundario": "",
        "dev_principal": "",
        "dev_secundario": "",
    }


def _text_contains_alias(texto_normalizado: str, alias_normalizado: str) -> bool:
    """Evita falsos positivos para aliases curtos como POS ou TEF."""
    if not texto_normalizado or not alias_normalizado:
        return False

    if len(alias_normalizado) <= 4 and alias_normalizado.replace("-", "").isalnum():
        pattern = rf"(?<!\w){re.escape(alias_normalizado)}(?!\w)"
        return re.search(pattern, texto_normalizado) is not None

    return alias_normalizado in texto_normalizado


def _extract_navigation_segments(texto: str) -> list[str]:
    """Extrai segmentos de um bloco 'Caminho:' ou 'Caminho de Navegação:'."""
    if not texto:
        return []

    lines = texto.splitlines()
    collecting = False
    collected: list[str] = []
    stop_prefixes = (
        "filtro:",
        "resultado:",
        "resultado exibido:",
        "observacao:",
        "observação:",
        "analise:",
        "análise:",
        "impacto:",
        "paliativo:",
        "passos de reproducao:",
        "passos de reprodução:",
        "base de reproducao:",
        "base de reprodução:",
    )

    for raw_line in lines:
        line = raw_line.strip()
        line_normalized = _normalize_text_for_match(line)

        if not collecting:
            if line_normalized.startswith("caminho:") or line_normalized.startswith("caminho de navegacao:"):
                collecting = True
                after_colon = line.split(":", 1)[1].strip() if ":" in line else ""
                if after_colon:
                    collected.append(after_colon)
            continue

        if not line:
            if collected:
                break
            continue

        if line_normalized.startswith(stop_prefixes):
            break

        if re.match(r"^\d+\.", line):
            break

        collected.append(line)

    if not collected:
        return []

    joined = " > ".join(collected).replace("›", ">")
    parts = [part.strip(" >\t-") for part in joined.split(">")]
    return [part for part in parts if part]


def _map_from_navigation_path(texto: str, times_config: dict) -> dict:
    """Usa o bloco 'Caminho' como sinal forte; aceita time sem área."""
    segments = _extract_navigation_segments(texto)
    if not segments:
        return _empty_area_map()

    normalized_segments = [_normalize_text_for_match(segment) for segment in segments]
    matched_time_name = None
    matched_time_index = None

    for idx, segment in enumerate(normalized_segments):
        for time_name in times_config.keys():
            if segment == _normalize_text_for_match(time_name):
                matched_time_name = time_name
                matched_time_index = idx
                break
        if matched_time_name:
            break

    if not matched_time_name:
        return _empty_area_map()

    candidate_segments = normalized_segments[matched_time_index + 1:]
    for area in times_config.get(matched_time_name, {}).get("areas", []):
        aliases = list(area.get("labels_jira", []))
        area_name = area.get("nome", "")
        if area_name and area_name not in aliases:
            aliases.append(area_name)

        normalized_aliases = [_normalize_text_for_match(alias) for alias in aliases if alias]
        if any(segment == alias for segment in candidate_segments for alias in normalized_aliases):
            return {
                "time": matched_time_name,
                "area": area_name,
                "qa_principal": area.get("qa_principal", ""),
                "qa_secundario": area.get("qa_secundario", ""),
                "dev_principal": area.get("dev_principal", ""),
                "dev_secundario": area.get("dev_secundario", ""),
            }

    return _empty_area_map(matched_time_name)


def _map_area_from_text_alias(texto: str, times_config: dict) -> dict:
    """Prioriza nomes/aliases reais da área quando aparecerem no texto da issue."""
    texto_normalizado = _normalize_text_for_match(texto)
    best_match = None

    for time_name, time_data in times_config.items():
        for area in time_data.get("areas", []):
            aliases = list(area.get("labels_jira", []))
            area_name = area.get("nome", "")
            if area_name and area_name not in aliases:
                aliases.append(area_name)

            for alias in aliases:
                alias_normalizado = _normalize_text_for_match(alias)
                if not alias_normalizado:
                    continue
                if _text_contains_alias(texto_normalizado, alias_normalizado):
                    score = (len(alias_normalizado.split()), len(alias_normalizado))
                    if best_match is None or score > best_match["score"]:
                        best_match = {
                            "score": score,
                            "time": time_name,
                            "area": area_name,
                            "qa_principal": area.get("qa_principal", ""),
                            "qa_secundario": area.get("qa_secundario", ""),
                            "dev_principal": area.get("dev_principal", ""),
                            "dev_secundario": area.get("dev_secundario", ""),
                        }

    if best_match:
        best_match.pop("score", None)
        return best_match

    return _empty_area_map()


def inferir_time_area_por_texto(texto: str, times_config: dict) -> dict:
    """
    Infere Time/Área/Responsáveis analisando texto (resumo + descrição).
    Usado como fallback quando issue não tem labels.
    
    Args:
        texto: texto combinado (resumo + descrição)
        times_config: config['times'] do rca_config.yaml
    
    Returns:
        dict com time, area, qa_principal, dev_principal ou "Não Mapeado" se sem match
    """
    path_map = _map_from_navigation_path(texto, times_config)
    if path_map["time"] != "Não Mapeado":
        return path_map

    area_from_alias = _map_area_from_text_alias(texto, times_config)
    if area_from_alias["time"] != "Não Mapeado" and area_from_alias["area"] != "Não Mapeado":
        return area_from_alias

    texto_normalizado = _normalize_text_for_match(texto)
    
    melhor_match = None
    melhor_score = 0
    melhor_time = None
    melhor_area_nome = None
    
    # Busca por keywords
    for time_name, areas_keywords in KEYWORDS_TIME_AREA.items():
        for area_nome, keywords in areas_keywords.items():
            score = sum(
                1 for keyword in keywords
                if _text_contains_alias(texto_normalizado, _normalize_text_for_match(keyword))
            )
            
            if score > melhor_score:
                melhor_score = score
                melhor_match = (time_name, area_nome)
                melhor_time = time_name
                melhor_area_nome = area_nome
    
    # Se encontrou match, busca responsáveis no config
    if melhor_match and melhor_score > 0:
        # Busca dados completos (qa_principal, dev_principal) no times_config
        time_data = times_config.get(melhor_time, {})
        for area in time_data.get("areas", []):
            if area.get("nome") == melhor_area_nome:
                return {
                    "time": melhor_time,
                    "area": melhor_area_nome,
                    "qa_principal": area.get("qa_principal", ""),
                    "qa_secundario": area.get("qa_secundario", ""),
                    "dev_principal": area.get("dev_principal", ""),
                    "dev_secundario": area.get("dev_secundario", ""),
                }
    
    # Sem match: retorna "Não Mapeado"
    return _empty_area_map()


def _clean_jira_wiki_markup(text: str) -> str:
    """Remove formatação wiki/markup do Jira de um texto, preservando newlines."""
    if not text:
        return ""
    import re
    # Extrai títulos de paineis: {panel:title=TITULO|...} → TITULO
    text = re.sub(r'\{panel:title=([^|}]*)[^}]*\}', r'\1', text)
    # Remove blocos {panel} (abertura sem title ou fechamento)
    text = re.sub(r'\{panel\}', '', text)
    # Remove blocos {code:...} e {code}
    text = re.sub(r'\{code(?::[^}]*)?\}', '', text)
    # Remove blocos {noformat}{noformat}
    text = re.sub(r'\{noformat\}', '', text)
    # Remove {color:...}{color}
    text = re.sub(r'\{color(?::[^}]*)?\}', '', text)
    # Remove {quote}{quote}
    text = re.sub(r'\{quote\}', '', text)
    # Remove negrito/itálico wiki: {*}texto{*}
    text = re.sub(r'\{\*\}', '', text)
    # Remove links wiki: [texto|url] → texto (ANTES de remover [ ])
    text = re.sub(r'\[([^|\]]*)\|[^\]]+\]', r'\1', text)
    # Remove referências a imagens: !image-xxxxx.png!
    text = re.sub(r'!image-[^!]*!', '', text)
    # Remove formatação markdown/wiki (* _ [ ] ~)
    text = re.sub(r'[\*_\[\]~]', '', text)
    # Remove \xa0 (non-breaking space)
    text = text.replace('\xa0', ' ')
    # Colapsa múltiplos espaços em cada linha (preserva newlines)
    lines = text.splitlines()
    lines = [' '.join(line.split()) for line in lines]
    # Remove linhas vazias consecutivas
    result = []
    prev_empty = False
    for line in lines:
        if not line.strip():
            if not prev_empty:
                result.append('')
            prev_empty = True
        else:
            result.append(line)
            prev_empty = False
    return '\n'.join(result).strip()


def _extract_sintoma(description: str) -> str:
    """
    Extrai o texto após 'Sintoma:' da descrição do Jira.
    Retorna o texto até a próxima linha vazia ou próximo campo (ex: 'Impacto:', 'Causa:', etc.).
    Se não encontrar, retorna string vazia.
    """
    if not description:
        return ""
    
    # Procura por "Sintoma:" (case insensitive)
    # Para quando encontrar: dupla quebra de linha OU início de outro campo (palavra com : )
    import re
    match = re.search(r'Sintoma\s*:\s*(.+?)(?:\n\s*\n|\n\s*[*_]*[A-ZÀ-Ú][a-zà-úç]+\s*[*_]*\s*:|$)', 
                      description, 
                      re.IGNORECASE | re.DOTALL)
    
    if match:
        sintoma = _clean_jira_wiki_markup(match.group(1))
        sintoma = ' '.join(sintoma.split())  # colapsa em uma linha
        # Limita a 200 caracteres para não poluir a planilha
        if len(sintoma) > 200:
            sintoma = sintoma[:197] + "..."
        return sintoma
    
    return ""


def _find_conclusao_comment(comments_list: list) -> str:
    """
    Procura nos comentários por aquele que contém '1 - Conclusão:'.
    Retorna o corpo completo do comentário de conclusão, ou string vazia se não encontrar.
    """
    if not comments_list:
        return ""
    
    import re
    for comment in comments_list:
        body = str(comment.get("body") or "").strip()
        # Procura por "1 - Conclusão:" (aceita variações: 1- Conclusão, 1 -Conclusão, etc.)
        if re.search(r'1\s*-\s*Conclus[aã]o\s*:', body, re.IGNORECASE):
            return body
    
    return ""


def _extract_causa_raiz(description: str) -> str:
    """
    Extrai a Causa Raiz da descrição do Jira.
    Busca o texto que vem logo após "Sintoma:" ou "Situação:".
    Retorna o texto até a próxima linha vazia ou próximo campo.
    """
    if not description:
        return ""
    
    import re
    # Padrões: procura por "Sintoma:" ou "Situação:" e pega o texto que vem depois
    # Para quando encontrar: dupla quebra de linha OU início de outro campo
    patterns = [
        r'Sintoma\s*:\s*(.+?)(?:\n\s*\n|\n\s*[*_]*[A-ZÀ-Ú][\w\s]+\s*[*_]*\s*:|$)',
        r'Situa[çc][aã]o\s*:\s*(.+?)(?:\n\s*\n|\n\s*[*_]*[A-ZÀ-Ú][\w\s]+\s*[*_]*\s*:|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE | re.DOTALL)
        if match:
            causa = _clean_jira_wiki_markup(match.group(1))
            causa = ' '.join(causa.split())  # colapsa em uma linha
            # Limita tamanho
            if len(causa) > 300:
                causa = causa[:297] + "..."
            return causa
    
    return ""


def _extract_acao_realizada(comments_list: list, resolution_name: str = "") -> str:
    """
    Extrai a Ação Realizada dos comentários do Jira.
    
    Ordem de prioridade:
    1. "Solução:" no comentário de conclusão (seção 1)
    2. Texto completo da seção "1 - Conclusão:" (excluindo checklists)
    3. Último comentário significativo (não-checklist, não-imagem)
    4. resolution_name como fallback
    """
    if not comments_list:
        return resolution_name
    
    import re
    
    # Detecta alteração de código em qualquer comentário
    houve_alteracao_codigo = False
    for comment in comments_list:
        body = str(comment.get("body") or "")
        if re.search(r'altera[çc][aã]o\s+(no\s+|de\s+)?(c[óo]digo|fonte)|'
                     r'ajuste\s+(no\s+)?c[óo]digo|corre[çc][aã]o\s+(no\s+|de\s+)?c[óo]digo',
                     body, re.IGNORECASE):
            houve_alteracao_codigo = True
            break
    
    # 1. Busca no comentário de conclusão
    conclusao_comment = _find_conclusao_comment(comments_list)
    if conclusao_comment:
        conclusao_clean = _clean_jira_wiki_markup(conclusao_comment)
        
        # Isola seção 1 (antes da seção 2)
        match_secao1 = re.search(
            r'1\s*-\s*Conclus[aã]o\s*:?\s*(.+?)(?=\n\s*2\s*-\s|$)',
            conclusao_clean,
            re.IGNORECASE | re.DOTALL,
        )
        secao1_text = match_secao1.group(1).strip() if match_secao1 else conclusao_clean
        
        # Busca "Solução:" dentro da seção 1
        match_solucao = re.search(
            r'Solu[çc][aã]o\s*:\s*(.+?)(?=\n\s*(?:Causa|Impacto|Sintoma)\s*:|$)',
            secao1_text,
            re.IGNORECASE | re.DOTALL,
        )
        if match_solucao:
            acao = ' '.join(match_solucao.group(1).split())
            if acao and len(acao) > 5:  # evita matches espúrios
                return _format_acao(acao, houve_alteracao_codigo)
        
        # Busca "Causa:" + contexto se não tem "Solução:"
        match_causa = re.search(
            r'Causa\s*:\s*(.+?)(?=\n\s*(?:Solu[çc]|Impacto|Sintoma)\s*:|$)',
            secao1_text,
            re.IGNORECASE | re.DOTALL,
        )
        
        # Se tem Causa mas não Solução, usa a seção 1 inteira
        secao1_oneline = ' '.join(secao1_text.split())
        # Remove checklists (Sim/Não, x Sim, etc)
        secao1_oneline = re.sub(r'\b(x\s+)?Sim\b|\bN[aã]o\b', '', secao1_oneline, flags=re.IGNORECASE)
        secao1_oneline = re.sub(r'(seja aplicada|foi identificad|originou o problema)\?', '', secao1_oneline, flags=re.IGNORECASE)
        secao1_oneline = ' '.join(secao1_oneline.split()).strip()
        
        if secao1_oneline and len(secao1_oneline) > 10:
            return _format_acao(secao1_oneline, houve_alteracao_codigo)
    
    # 2. Fallback: último comentário significativo
    for comment in reversed(comments_list):
        body_raw = str(comment.get("body") or "").strip()
        if not body_raw:
            continue
        
        body_clean = _clean_jira_wiki_markup(body_raw)
        body_oneline = ' '.join(body_clean.split())
        
        # Ignora comentários que são basicamente imagens, links curtos, ou conclusão vazia
        if len(body_oneline) < 10:
            continue
        if re.match(r'^!image-.*!$', body_oneline):
            continue
        
        return _format_acao(body_oneline, houve_alteracao_codigo)
    
    # 3. Último fallback
    if houve_alteracao_codigo and resolution_name:
        return f"[Alteração no código] {resolution_name}"
    return resolution_name


def _format_acao(acao: str, houve_alteracao: bool) -> str:
    """Formata a ação realizada com limite de tamanho e indicador de alteração."""
    if houve_alteracao:
        if "alteração" not in acao.lower() and "código" not in acao.lower():
            acao = f"[Alteração no código] {acao}"
    if len(acao) > 400:
        acao = acao[:397] + "..."
    return acao


def _extract_dev_responsavel(description: str, fields: dict = None, config: dict = None) -> str:
    """
    Extrai o nome do Responsável Desenvolvimento.
    1. Campo configurado (customfield_14100)
    2. Fallback: qualquer customfield de pessoa
    3. Fallback: assignee
    4. Fallback: descrição
    """
    import re
    
    if fields:
        # 1. Campo configurado
        dev_field = (config or {}).get("jira", {}).get("dev_responsavel_field", "customfield_14100")
        v = fields.get(dev_field)
        if isinstance(v, dict) and "displayName" in v:
            return v["displayName"]
        
        # 2. Fallback: busca genérica em customfields de pessoa
        person_fields = []
        for k, val in sorted(fields.items()):
            if (k.startswith("customfield_") and val and
                isinstance(val, dict) and "displayName" in val and
                k not in ("customfield_20506",)):
                person_fields.append((k, val["displayName"]))
        if person_fields:
            return person_fields[0][1]
        
        # 3. Fallback: assignee
        assignee = (fields.get("assignee") or {}).get("displayName", "")
        if assignee:
            return assignee
    
    # 4. Fallback: descrição
    if description:
        for pat in [r'Respons[aá]vel\s+Desenvolvimento\s*:\s*([^\n]+)',
                    r'Respons[aá]vel\s+Dev\s*:\s*([^\n]+)']:
            m = re.search(pat, description, re.IGNORECASE)
            if m:
                return ' '.join(re.sub(r'[\*_\[\]]', '', m.group(1)).split())[:100]
    return ""


def _extract_qa_responsavel(description: str, fields: dict = None, config: dict = None) -> str:
    """
    Extrai o nome do Responsável QA.
    1. Campo configurado (customfield_14101)
    2. Fallback: segundo customfield de pessoa
    3. Fallback: descrição
    """
    import re
    
    if fields:
        # 1. Campo configurado
        qa_field = (config or {}).get("jira", {}).get("qa_responsavel_field", "customfield_14101")
        v = fields.get(qa_field)
        if isinstance(v, dict) and "displayName" in v:
            return v["displayName"]
        
        # 2. Fallback: segundo customfield de pessoa
        person_fields = []
        for k, val in sorted(fields.items()):
            if (k.startswith("customfield_") and val and
                isinstance(val, dict) and "displayName" in val and
                k not in ("customfield_20506",)):
                person_fields.append((k, val["displayName"]))
        if len(person_fields) >= 2:
            return person_fields[1][1]
    
    # 3. Fallback: descrição
    if description:
        for pat in [r'Respons[aá]vel\s+QA\s*:\s*([^\n]+)',
                    r'QA\s+Respons[aá]vel\s*:\s*([^\n]+)']:
            m = re.search(pat, description, re.IGNORECASE)
            if m:
                return ' '.join(re.sub(r'[\*_\[\]]', '', m.group(1)).split())[:100]
    return ""


def _extract_sla_dates(fields: dict, sla_field_name: str = None):
    """
    Extrai datas do SLA Panel (Start Date e End Date).
    
    Args:
        fields: Objeto fields da issue do Jira
        sla_field_name: Nome do campo customizado do SLA (ex: "customfield_10000")
                       Se None, tenta procurar automaticamente
    
    Returns:
        Tupla (start_date, end_date) ou (None, None) se não encontrar
    """
    # Se foi especificado um campo SLA, tenta usar ele
    if sla_field_name and sla_field_name in fields:
        sla_data = fields.get(sla_field_name)
        if sla_data:
            # SLA pode ser um array ou objeto único
            if isinstance(sla_data, list) and len(sla_data) > 0:
                sla_obj = sla_data[0]  # Pega o primeiro SLA
            else:
                sla_obj = sla_data
            
            # Tenta extrair ongoingCycle (ciclo em andamento) ou completedCycles
            if isinstance(sla_obj, dict):
                # Procura por startTime/breachTime no ciclo em andamento
                ongoing = sla_obj.get("ongoingCycle") or {}
                start_time = ongoing.get("startTime") or ongoing.get("goalDuration", {}).get("startTime")
                end_time = ongoing.get("breachTime") or ongoing.get("endTime")
                
                if start_time or end_time:
                    return (start_time, end_time)
                
                # Se não tem ciclo em andamento, procura nos completados
                completed = sla_obj.get("completedCycles") or []
                if completed and isinstance(completed, list) and len(completed) > 0:
                    last_cycle = completed[-1]  # Pega o último ciclo completado
                    start_time = last_cycle.get("startTime")
                    end_time = last_cycle.get("stopTime") or last_cycle.get("endTime")
                    if start_time or end_time:
                        return (start_time, end_time)
    
    # Busca automática: procura por campos que parecem ser SLA
    # Campos customizados no Jira geralmente têm formato "customfield_XXXXX"
    for field_key, field_value in fields.items():
        if field_key.startswith("customfield_") and field_value:
            # Verifica se o campo tem estrutura de SLA
            if isinstance(field_value, dict):
                if "ongoingCycle" in field_value or "completedCycles" in field_value:
                    # Encontrou campo SLA, tenta extrair datas
                    ongoing = field_value.get("ongoingCycle") or {}
                    start_time = ongoing.get("startTime")
                    end_time = ongoing.get("breachTime") or ongoing.get("endTime")
                    
                    if start_time or end_time:
                        return (start_time, end_time)
                    
                    completed = field_value.get("completedCycles") or []
                    if completed and isinstance(completed, list) and len(completed) > 0:
                        last_cycle = completed[-1]
                        start_time = last_cycle.get("startTime")
                        end_time = last_cycle.get("stopTime") or last_cycle.get("endTime")
                        if start_time or end_time:
                            return (start_time, end_time)
    
    # Não encontrou SLA
    return (None, None)


def _extract_numero_caso_count(fields: dict, numero_caso_field: str = None) -> int:
    """
    Conta a quantidade de "Número do Caso" vinculados à issue.
    
    O campo customfield_20506 é uma lista de strings (números de caso).
    Se for string, tenta contar por URLs ou chaves de issue.
    
    Args:
        fields: Objeto fields da issue do Jira
        numero_caso_field: Nome do campo customizado (ex: "customfield_20506")
                          Se None, tenta buscar automaticamente
    
    Returns:
        Quantidade de casos encontrados (int)
    """
    import re
    
    valor = None
    
    # Se foi especificado um campo, tenta usar ele
    if numero_caso_field and numero_caso_field in fields:
        valor = fields.get(numero_caso_field)
    else:
        # Busca automática em customfields
        for field_key, field_value in fields.items():
            if field_key.startswith("customfield_") and field_value:
                # Se for lista de strings (padrão do campo Número do Caso)
                if isinstance(field_value, list) and field_value and isinstance(field_value[0], str):
                    # Verifica se parece ser números de caso (sequências numéricas)
                    if all(re.match(r'^\d+$', str(v)) for v in field_value[:3]):
                        valor = field_value
                        break
    
    if valor is None:
        return 0
    
    # Se for lista (caso padrão: customfield_20506 = ['05130974', '05268248', ...])
    if isinstance(valor, list):
        return len(valor)
    
    # Se for string, tenta contar por separadores ou links
    texto = str(valor)
    if not texto.strip():
        return 0
    
    # Conta URLs
    urls = re.findall(r'https?://[^\s\)]+', texto)
    if urls:
        return len(urls)
    
    # Conta chaves de issue (PROJETO-1234)
    chaves = re.findall(r'\b[A-Z][A-Z0-9]+-\d+\b', texto)
    if chaves:
        return len(chaves)
    
    # Conta por separadores (vírgula, espaço, quebra de linha)
    partes = re.split(r'[,;\n]+', texto)
    partes = [p.strip() for p in partes if p.strip()]
    return len(partes) if len(partes) > 1 else (1 if texto.strip() else 0)


def normalize_issue(issue: dict, config: dict) -> dict:
    """Normaliza issue do Jira para o formato interno unificado."""
    fields = issue["fields"]

    # Extrai Sintoma da descrição (se existir) para usar como Resumo na planilha
    description = fields.get("description") or ""
    sintoma = _extract_sintoma(description)
    
    # Extrai Responsáveis Dev e QA (customfields de pessoa > descrição)
    dev_responsavel = _extract_dev_responsavel(description, fields, config)
    qa_responsavel = _extract_qa_responsavel(description, fields, config)
    
    # Se não encontrou Sintoma, usa o summary do Jira como fallback
    resumo_planilha = sintoma if sintoma else fields.get("summary", "")

    # Texto combinado para classificação
    resolution_text = (fields.get("resolution") or {}).get("name", "")
    text = " ".join(filter(None, [
        fields.get("summary", ""),
        description,
        resolution_text,
    ]))

    tipo_erro, needs_review = classify_error_type(text, config["tipos_erro"])
    area_map = map_issue_to_area(fields.get("labels", []), config["times"])
    
    # Se não mapeou por labels, tenta inferência inteligente por texto
    if area_map["time"] == "Não Mapeado" or area_map["area"] == "Não Mapeado":
        area_map = inferir_time_area_por_texto(text, config["times"])

    # ── Extração de datas: prioriza SLA Panel (Start/End Date) ────────────────
    # Tenta extrair do SLA configurado ou busca automaticamente
    sla_field = config.get("jira", {}).get("sla_field_name")
    sla_start, sla_end = _extract_sla_dates(fields, sla_field)
    
    # Se encontrou datas no SLA, usa elas; senão, fallback para created/resolutiondate
    if sla_start:
        data_criacao = _parse_date(sla_start)
    else:
        data_criacao = _parse_date(fields.get("created"))
    
    if sla_end:
        data_resolucao = _parse_date(sla_end)
    else:
        data_resolucao = _parse_date(fields.get("resolutiondate"))
    
    # ── Contagem de vínculos: prioriza campo "Número do Caso" ─────────────────
    # Tenta extrair do campo configurado ou busca automaticamente
    numero_caso_field = config.get("jira", {}).get("numero_caso_field")
    qtd_vinculos = _extract_numero_caso_count(fields, numero_caso_field)
    
    # Se não encontrou no campo "Número do Caso", fallback para issuelinks
    if qtd_vinculos == 0:
        issuelinks = fields.get("issuelinks", [])
        qtd_vinculos = len(issuelinks) if issuelinks else 0

    tempo_resolucao_dias = None
    if data_criacao and data_resolucao:
        tempo_resolucao_dias = (data_resolucao - data_criacao).days

    # ── Comentários: para extrair Ação Realizada ──────────────────────────────
    comment_data    = fields.get("comment") or {}
    comments_list   = comment_data.get("comments", [])
    
    # Extrai Causa Raiz da descrição: texto após "Sintoma:" ou "Situação:" (coluna K)
    causa_raiz = _extract_causa_raiz(description)
    
    # ── Ação Realizada no Bug: busca "Solução:" nos comentários (coluna O) ────
    resolution_name = (fields.get("resolution") or {}).get("name", "")
    acao_realizada = _extract_acao_realizada(comments_list, resolution_name)

    issue_key = issue["key"]
    manual_mock = _MOCK_MANUAL.get(issue_key, {})

    return {
        "key":                   issue_key,
        "resumo":                resumo_planilha,  # Extrai "Sintoma:" da descrição, fallback para summary
        "descricao":             description,
        "status":                (fields.get("status") or {}).get("name", ""),
        "prioridade":            (fields.get("priority") or {}).get("name", ""),
        "data_criacao":          data_criacao,
        "data_atualizacao":      _parse_date(fields.get("updated")),
        "data_resolucao":        data_resolucao,
        "tempo_resolucao_dias":  tempo_resolucao_dias,
        "responsavel_jira":      (fields.get("assignee") or {}).get("displayName", ""),
        "labels":                ", ".join(fields.get("labels", [])),
        "tipo_erro_auto":        tipo_erro,
        "tipo_erro_manual":      "",  # preenchido pelo usuário no Excel
        "acao_realizada":        acao_realizada,  # Extrai "Solução:" dos comentários
        "causa_raiz":            causa_raiz,  # Extrai texto após "Sintoma:" ou "Situação:" da descrição
        "analisado":             "",  # preenchido pelo usuário no Excel
        "revisar_classificacao": "⚠️ Revisar" if needs_review else "✅ OK",
        "time":                  area_map["time"],
        "area":                  area_map["area"],
        "qa_principal":          area_map["qa_principal"],
        "qa_secundario":         area_map["qa_secundario"],
        "dev_principal":         area_map["dev_principal"],
        "dev_secundario":        area_map["dev_secundario"],
        "dev_responsavel_bug":   dev_responsavel,  # Customfield > assignee > descrição
        "qa_responsavel_bug":    qa_responsavel,   # Customfield > descrição
        "link_jira":             f"{config['jira']['base_url']}/browse/{issue_key}",
        "qtd_vinculos":          qtd_vinculos,  # Quantidade de issuelinks
        "data_importacao":       datetime.now(),  # Data de importação
        # Campos manuais demo (preenchidos via _MOCK_MANUAL; em produção vêm do Excel)
        "analise_causa":         manual_mock.get("analise_causa", ""),
        "ajuste_realizado":      manual_mock.get("ajuste_realizado", ""),
        "possui_ta":             manual_mock.get("possui_ta", ""),
        "problema_resolvido":    manual_mock.get("problema_resolvido", ""),
        # Campos de acompanhamento demo
        "acomp_area":           manual_mock.get("acomp_area", ""),
        "acomp_responsavel":    manual_mock.get("acomp_responsavel", ""),
        "acomp_acao":           manual_mock.get("acomp_acao", ""),
        "acomp_status_acao":    manual_mock.get("acomp_status_acao", ""),
        "acomp_data_conclusao": manual_mock.get("acomp_data_conclusao", None),
    }


# =============================================================================
# CLIENTE JIRA
# =============================================================================

class JiraClient:
    """
    Cliente para buscar issues do Jira Data Center via API REST.
    Em modo MOCK (token = 'SEU_TOKEN_AQUI'), retorna dados de demonstração.
    """

    def __init__(self, config: dict):
        self.config = config
        self.base_url = config["jira"]["base_url"]
        self.token = config["jira"]["token"]
        self.auth_type = config["jira"].get("auth_type", "pat")
        self.cache_file = Path(config["cache"]["arquivo_cache"])
        self.last_sync_file = Path(config["cache"]["arquivo_ultima_sync"])

        # Garante que pasta data/ existe
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

    def _is_mock_mode(self) -> bool:
        token = self._get_effective_token()
        if token in ("SEU_TOKEN_AQUI", "", None):
            return True
        # Para Basic Auth, também precisa verificar se username está configurado
        if self.auth_type == "basic":
            username = self.config["jira"].get("username", "")
            if not username or username == "":
                return True
        return False

    def _get_effective_token(self) -> str:
        """Prioridade: env var JIRA_API_TOKEN (Key Vault via pipeline) > rca_config.yaml."""
        return os.environ.get("JIRA_API_TOKEN", "").strip() or self.token

    def _get_headers(self) -> dict:
        token = self._get_effective_token()
        if self.auth_type == "pat":
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        # basic auth (usuário:senha)
        username = self.config["jira"].get("username", "")
        creds = base64.b64encode(f"{username}:{token}".encode()).decode()
        return {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _make_session(self) -> requests.Session:
        """Session com retry automático para erros transitórios (500/502/503/504).
        429 é tratado manualmente em _fetch_page para respeitar Retry-After.
        """
        session = requests.Session()
        session.headers.update(self._get_headers())
        retry = Retry(
            total=4,
            backoff_factor=1,          # 1s → 2s → 4s → 8s entre tentativas
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,     # 429 não entra aqui; tratado abaixo
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _fetch_page(self, session: requests.Session, jql: str, fields: str,
                    max_results: int, start_at: int) -> dict:
        """Busca uma página de resultados.
        Respeita o header Retry-After em caso de 429 (rate limit do Jira DC).
        Usa timeout separado para conexão (5s) e leitura (30s).
        """
        print(f"[DEBUG] Fazendo requisição startAt={start_at}, maxResults={max_results}")
        
        for attempt in range(1, 4):
            try:
                response = session.get(
                    f"{self.base_url}/rest/api/2/search",
                    params={"jql": jql, "fields": fields,
                            "maxResults": max_results, "startAt": start_at},
                    timeout=(10, 120),       # (connect timeout, read timeout)
                )
                print(f"[DEBUG] Status Code: {response.status_code}")
                
                if response.status_code == 401:
                    print(f"[ERROR] 401 Unauthorized - Credenciais inválidas!")
                    print(f"[ERROR] Response: {response.text[:300]}")
                    raise requests.exceptions.HTTPError("401 Unauthorized")
                    
                if response.status_code == 403:
                    print(f"[ERROR] 403 Forbidden - Sem permissão!")
                    print(f"[ERROR] Response: {response.text[:300]}")
                    raise requests.exceptions.HTTPError("403 Forbidden")
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    print(f"[WARN] Rate limit (429) — aguardando {retry_after}s "
                          f"(tentativa {attempt}/3)...")
                    time.sleep(retry_after)
                    continue
                    
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.Timeout:
                print(f"[ERROR] Timeout após 30s (tentativa {attempt}/3)")
                if attempt == 3:
                    raise
                time.sleep(5)
            except requests.exceptions.ConnectionError as e:
                print(f"[ERROR] Erro de conexão (tentativa {attempt}/3): {e}")
                if attempt == 3:
                    raise
                time.sleep(5)
                
        raise RuntimeError("Rate limit persistente (429) — tente novamente mais tarde.")

    def _fetch_from_api(self) -> list:
        """Busca issues via API Jira com paginação, retry e paralelismo opcional.

        Melhorias implementadas:
          - ORDER BY updated ASC: garante consistência na paginação
          - Session + HTTPAdapter com Retry: reconnect automático em 5xx
          - timeout=(5, 30): separa connect timeout de read timeout
          - 429 + Retry-After: respeita rate limit do Jira DC
          - Delta update com UTC ISO 8601: sem dependência de fuso horário local
          - Log seguro: expõe apenas domínio, não URL completa
          - Paralelismo opcional: cache.parallel_pagination=true para >500 issues

        Nota — ETag/If-Modified-Since: o endpoint /rest/api/2/search do Jira DC
        não gera ETags para resultados de busca dinâmica; o delta update com
        'updated >= timestamp' já cobre esse caso de forma confiável e sem overhead.
        """
        fields = ",".join(self.config["jira"]["fields"])
        max_results = self.config["jira"]["max_results_per_page"]
        domain = urlparse(self.base_url).netloc  # log seguro: sem path/credenciais

        # ORDER BY garante consistência na paginação (evita duplicatas/omissões)
        jql = f"filter={self.config['jira']['filter_id']} ORDER BY updated ASC"

        if self.config["cache"]["delta_update"] and self.last_sync_file.exists():
            last_sync_raw = self.last_sync_file.read_text().strip()
            # Suporta formato novo (ISO 8601 UTC ex: "2026-03-06T10:00:00Z")
            # e formato legado ("2026-03-06 10:00") para retrocompatibilidade
            try:
                if last_sync_raw.endswith("Z"):
                    last_sync_dt = datetime.fromisoformat(last_sync_raw[:-1]).replace(
                        tzinfo=timezone.utc
                    )
                else:
                    last_sync_dt = datetime.strptime(last_sync_raw, "%Y-%m-%d %H:%M")
                jql_date = last_sync_dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                jql_date = last_sync_raw  # fallback sem conversão
            jql = (
                f"filter={self.config['jira']['filter_id']}"
                f" AND updated >= \"{jql_date}\""
                f" ORDER BY updated ASC"
            )
            print(f"[INFO] Delta update — desde {jql_date} | Jira: {domain}")
        else:
            print(f"[INFO] Sincronização completa | Jira: {domain}")

        with self._make_session() as session:
            # Primeira página: obtém total antes de decidir estratégia de paginação
            first_data = self._fetch_page(session, jql, fields, max_results, 0)
            total = first_data.get("total", 0)
            first_batch = first_data.get("issues", [])
            issues = list(first_batch)
            print(f"[INFO] Total no filtro: {total} | Recebido: {len(issues)}/{total}...")

            if len(issues) >= total or not first_batch:
                return issues

            parallel = self.config.get("cache", {}).get("parallel_pagination", False)

            if parallel:
                # Paralelismo controlado: máx. 4 workers para não sobrecarregar o DC
                remaining_starts = list(range(len(first_batch), total, max_results))
                max_workers = min(4, len(remaining_starts))
                print(f"[INFO] Paginação paralela: {len(remaining_starts)} páginas, "
                      f"{max_workers} workers...")

                def _fetch_one(start_at):
                    return self._fetch_page(
                        session, jql, fields, max_results, start_at
                    ).get("issues", [])

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                    # executor.map preserva a ordem das páginas
                    for batch in ex.map(_fetch_one, remaining_starts):
                        issues.extend(batch)
                print(f"[INFO] Recebido {len(issues)}/{total} issues (paralelo)...")
            else:
                start_at = len(first_batch)
                while len(issues) < total:
                    data = self._fetch_page(session, jql, fields, max_results, start_at)
                    batch = data.get("issues", [])
                    if not batch:
                        break
                    issues.extend(batch)
                    print(f"[INFO] Recebido {len(issues)}/{total} issues...")
                    if len(batch) < max_results:
                        break
                    start_at += len(batch)

        return issues

    def _load_cache(self) -> list:
        """Carrega lista de issues do cache local."""
        if self.cache_file.exists():
            with open(self.cache_file, encoding="utf-8") as f:
                data = json.load(f)
            # Cache sempre salvo como {"synced_at": ..., "issues": [...]}
            return data.get("issues", []) if isinstance(data, dict) else data
        return []
    
    def _load_cache_raw(self) -> dict:
        """Carrega cache no formato bruto (dict completo com meta)."""
        if self.cache_file.exists():
            with open(self.cache_file, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_cache(self, issues_raw: list, normalized: list):
        """Salva cache com gravação atômica (write temp + rename) para evitar corrupção.
        Se o processo for interrompido durante a escrita, o arquivo anterior permanece
        intacto pois o rename() só ocorre após a escrita completa.
        """
        cache_data = {
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "total": len(normalized),
            "issues": normalized,
        }
        # Escreve em arquivo temporário na mesma pasta para garantir
        # que temp e destino estejam no mesmo filesystem (rename atômico)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self.cache_file.parent,
            prefix=".~cache_",
            suffix=".json",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp_path, self.cache_file)  # atômico no SO
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        # UTC ISO 8601 — consistência independente do fuso horário local
        # Retrocompatível: _fetch_from_api aceita tanto "2026-03-06T10:00:00Z"
        # quanto o legado "2026-03-06 10:00"
        self.last_sync_file.write_text(
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        print(f"[INFO] Cache salvo: {self.cache_file.name} ({len(normalized)} issues)")

    def get_normalized_issues(self) -> list:
        """
        Retorna lista de issues normalizadas.
        - Mock mode: retorna MOCK_ISSUES processados (a menos que cache tenha flag force_use)
        - Real mode: busca Jira API + merge com cache existente
        """
        # Verifica se há cache com flag force_use (importado de planilha exemplo) 
        if self._is_mock_mode():
            cached = self._load_cache_raw()  # Carrega formato bruto
            if cached and cached.get("meta", {}).get("force_use_cache"):
                print("[INFO] Usando cache importado (força uso mesmo em modo mock)")
                return cached.get("issues", [])
            
            print("[MOCK] Token não configurado — usando dados de demonstração")
            normalized = [normalize_issue(i, self.config) for i in MOCK_ISSUES]
            self._save_cache(MOCK_ISSUES, normalized)
            return normalized

        print(f"[INFO] Consultando Jira: {urlparse(self.base_url).netloc}")
        try:
            raw_issues = self._fetch_from_api()

            # Merge com cache existente (delta update mantém issues antigas)
            if self.config["cache"]["delta_update"]:
                existing = self._load_cache()
                existing_keys = {i["key"] for i in existing}
                new_normalized = [normalize_issue(i, self.config) for i in raw_issues]
                new_keys = {i["key"] for i in new_normalized}
                # Mantém antigas que não foram atualizadas
                merged = [i for i in existing if i["key"] not in new_keys] + new_normalized
            else:
                merged = [normalize_issue(i, self.config) for i in raw_issues]

            self._save_cache(raw_issues, merged)
            return merged

        except requests.exceptions.RequestException as e:
            print(f"[WARN] Falha na API Jira: {e}")
            print("[WARN] Carregando cache local...")
            cached = self._load_cache()
            if cached:
                return cached  # _load_cache já retorna lista de issues
            print("[WARN] Sem cache local. Usando dados mock.")
            return [normalize_issue(i, self.config) for i in MOCK_ISSUES]

    def get_actions(self) -> list:
        """Retorna ações mock para demonstração do protótipo."""
        return MOCK_ACTIONS


def load_normalized_issues(config: dict) -> list:
    """Função de conveniência: retorna issues normalizadas prontas para uso."""
    client = JiraClient(config)
    return client.get_normalized_issues()


if __name__ == "__main__":
    from config_loader import load_config as load_project_config

    cfg = load_project_config(__file__)

    issues = load_normalized_issues(cfg)
    print(f"\n✅ {len(issues)} issues carregadas")

    for i in issues[:3]:
        print(f"  {i['key']} | {i['area']} | {i['tipo_erro_auto']} | {i['status']}")
