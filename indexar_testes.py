"""
Indexador de Testes Automatizados do repositório Robot Framework.

Busca todos os test cases do repo ta-robotframework no GitHub,
extrai nomes e paths, e salva como índice local JSON.
Depois cruza por similaridade de palavras-chave com os bugs do RCA Pocket.

Uso:
    python indexar_testes.py          # Indexa testes (requer GITHUB_TOKEN)
    python indexar_testes.py --match  # Indexa + mostra matches com issues do cache
"""

import os
import sys
import json
import re
import base64
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

GITHUB_REPO = "MEDIUM-RETAIL-MICROVIX/ta-robotframework"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
INDEX_FILE = "data/ta_test_index.json"
CACHE_MAX_DAYS = 7
INDEX_SCHEMA_VERSION = 2

STOPWORDS = {
    "de", "do", "da", "dos", "das", "no", "na", "nos", "nas",
    "em", "um", "uma", "uns", "umas", "o", "a", "os", "as",
    "ao", "aos", "por", "para", "com", "sem", "sob", "sobre",
    "que", "nao", "se", "ou", "mas", "foi", "ser", "esta",
    "tipo", "erro", "error", "null", "undefined", "none",
    "quando", "apos", "onde", "como", "entre", "the", "and",
    "pv", "cd", "erp", "tests", "robot", "test", "cases",
}

# =============================================================================
# UTILITÁRIOS
# =============================================================================

def normalizar(texto: str) -> str:
    """Remove acentos, converte para lowercase."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def extrair_keywords(texto: str, min_len: int = 3) -> List[str]:
    """Extrai palavras-chave relevantes de um texto."""
    texto = normalizar(texto)
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    palavras = texto.split()
    keywords = [p for p in palavras if p not in STOPWORDS and len(p) >= min_len]
    return list(dict.fromkeys(keywords))  # deduplica preservando ordem


def combinar_keywords(*partes: str) -> List[str]:
    """Combina várias fontes textuais em uma lista única de keywords."""
    combined: List[str] = []
    for parte in partes:
        if not parte:
            continue
        for keyword in extrair_keywords(parte):
            if keyword not in combined:
                combined.append(keyword)
    return combined


# =============================================================================
# INDEXAÇÃO VIA GITHUB
# =============================================================================

def indexar_testes_github() -> List[Dict]:
    """
    Busca todos os test cases do repositório Robot Framework.
    Usa a API do GitHub para:
    1. Obter árvore de arquivos (1 request)
    2. Buscar conteúdo de cada .robot via blob (N requests)
    3. Parsear nomes de test cases do conteúdo Robot Framework

    Retorna lista de {nome, path, sistema, keywords}.
    """
    try:
        from github import Github, Auth
    except ImportError:
        print("❌ PyGithub não instalado. Execute: pip install PyGithub")
        return []

    if not GITHUB_TOKEN:
        print("⚠️  Token GitHub não configurado!")
        print("Configure: $env:GITHUB_TOKEN = 'ghp_seu_token'")
        return []

    try:
        g = Github(auth=Auth.Token(GITHUB_TOKEN))
    except TypeError:
        g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPO)

    print("🔍 Buscando arquivos .robot no GitHub...")
    try:
        tree = repo.get_git_tree(sha="master", recursive=True)
    except Exception:
        tree = repo.get_git_tree(sha="main", recursive=True)

    robot_items = [item for item in tree.tree
                   if item.path.endswith(".robot")
                   and item.type == "blob"
                   and "/Resource/" not in item.path
                   and "/Keywords/" not in item.path
                   and "/Variables/" not in item.path]

    print(f"  📄 {len(robot_items)} arquivos .robot de testes encontrados")

    # --- Fase 1: Extrair testes dos nomes de arquivo e caminhos (sem download) ---
    testes = []
    for item in robot_items:
        parts = item.path.replace("\\", "/").split("/")
        # Extrair sistema/módulo do path
        sistema = ""
        for p in parts:
            p_norm = p.replace("_", " ").replace(".robot", "")
            if p_norm.lower() not in ("tests", "erp", "resource", "resources",
                                       "keywords", "variables", "libs"):
                if not sistema:
                    sistema = p_norm

        # Usar o nome do arquivo e o path inteiro como fonte de keywords
        nome_arquivo = parts[-1].replace(".robot", "").replace("_", " ")
        path_texto = item.path.replace("/", " ").replace("_", " ").replace(".robot", "")
        kws = extrair_keywords(path_texto + " " + nome_arquivo)

        testes.append({
            "nome": nome_arquivo,
            "path": item.path,
            "sistema": sistema,
            "keywords": kws,
            "sha": item.sha,
        })

    print(f"  ✅ Fase 1: {len(testes)} arquivos de teste indexados (paths)")

    # --- Fase 2: Baixar conteúdo apenas dos arquivos em pastas relevantes ---
    # Foca em pastas que contém "Venda", "Troca", "NF", "Pedido" etc (somente Tests/)
    BATCH_SIZE = 300
    downloaded = 0
    tests_from_content = []

    # Filtra items relevantes para download de conteúdo
    items_para_download = [item for item in robot_items
                           if item.path.startswith("Tests/")]

    # Limita a BATCH_SIZE para não estourar rate limit
    if len(items_para_download) > BATCH_SIZE:
        print(f"  ⚠️  {len(items_para_download)} arquivos de teste. Baixando detalhes dos primeiros {BATCH_SIZE}...")
        items_para_download = items_para_download[:BATCH_SIZE]

    print(f"  📥 Fase 2: Baixando conteúdo de {len(items_para_download)} arquivos para extrair test cases...")

    for i, item in enumerate(items_para_download):
        if (i + 1) % 50 == 0:
            print(f"    Processando {i + 1}/{len(items_para_download)}...")

        parts = item.path.replace("\\", "/").split("/")
        sistema = ""
        for p in parts:
            p_norm = p.replace("_", " ").replace(".robot", "")
            if p_norm.lower() not in ("tests", "erp", "resource", "resources",
                                       "keywords", "variables", "libs"):
                if not sistema:
                    sistema = p_norm

        try:
            blob = repo.get_git_blob(item.sha)
            content = base64.b64decode(blob.content).decode("utf-8", errors="replace")
            downloaded += 1

            in_test_cases = False
            current_test = None

            def flush_current_test():
                if not current_test:
                    return
                documentation = " ".join(current_test.get("documentation_lines", [])).strip()
                steps = " ".join(current_test.get("step_lines", [])[:8]).strip()
                texto_para_keywords = " ".join(filter(None, [
                    current_test["nome"],
                    current_test["path"].replace("/", " ").replace("_", " ").replace(".robot", ""),
                    documentation,
                    steps,
                ]))
                kws = extrair_keywords(texto_para_keywords)
                tests_from_content.append({
                    "nome": current_test["nome"],
                    "path": current_test["path"],
                    "sistema": current_test["sistema"],
                    "documentacao": documentation,
                    "passos": current_test.get("step_lines", [])[:8],
                    "keywords": kws,
                })

            for line in content.split("\n"):
                stripped = line.rstrip()
                # Linha de seção
                if stripped.strip().startswith("*** Test Case"):
                    in_test_cases = True
                    continue
                elif stripped.strip().startswith("***"):
                    flush_current_test()
                    current_test = None
                    in_test_cases = False
                    continue

                if not in_test_cases:
                    continue

                # Test case name = linha que começa na coluna 0 (sem indentação)
                if stripped and not stripped[0].isspace():
                    flush_current_test()
                    # Ignora linhas que parecem keywords/settings
                    if stripped.startswith(("[", "#", "...", "$", "%", "&", "@")):
                        current_test = None
                        continue
                    nome = stripped.strip()
                    if len(nome) < 5:
                        current_test = None
                        continue
                    current_test = {
                        "nome": nome,
                        "path": item.path,
                        "sistema": sistema,
                        "documentation_lines": [],
                        "step_lines": [],
                    }
                    continue

                if current_test and stripped.strip():
                    linha = stripped.strip()
                    linha_norm = normalizar(linha)
                    if linha_norm.startswith("[documentation]"):
                        current_test["documentation_lines"].append(linha.split("]", 1)[-1].strip())
                    elif not linha.startswith(("[", "#", "...")):
                        current_test["step_lines"].append(linha)

            flush_current_test()
        except Exception:
            continue

    print(f"  ✅ Fase 2: {len(tests_from_content)} test cases extraídos de {downloaded} arquivos")

    # Combina: test cases do conteúdo têm prioridade, paths como fallback
    # Cria set de paths com test cases detalhados
    paths_com_conteudo = {t["path"] for t in tests_from_content}
    # Mantém entries de path para arquivos que não foram baixados
    testes_finais = tests_from_content + [t for t in testes if t["path"] not in paths_com_conteudo]

    print(f"  ✅ Total: {len(testes_finais)} entradas indexadas")
    return testes_finais


def carregar_indice() -> List[Dict]:
    """Carrega índice do cache local. Retorna [] se não existir ou expirado."""
    if not os.path.exists(INDEX_FILE):
        return []
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("schema_version") != INDEX_SCHEMA_VERSION:
            print("⚠️  Índice em formato antigo. Use reindexação para melhorar a precisão da busca de TAs.")
        ts = datetime.fromisoformat(data.get("timestamp", "2000-01-01"))
        if datetime.now() - ts > timedelta(days=CACHE_MAX_DAYS):
            print(f"⚠️  Índice expirado ({CACHE_MAX_DAYS} dias). Re-indexando...")
            return []
        testes = data.get("testes", [])
        print(f"📦 Índice carregado: {len(testes)} test cases (cache de {ts.strftime('%d/%m/%Y')})")
        return testes
    except Exception:
        return []


def salvar_indice(testes: List[Dict]):
    """Salva índice como JSON."""
    os.makedirs(os.path.dirname(INDEX_FILE), exist_ok=True)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "schema_version": INDEX_SCHEMA_VERSION,
            "timestamp": datetime.now().isoformat(),
            "total_testes": len(testes),
            "testes": testes,
        }, f, ensure_ascii=False, indent=2)
    print(f"💾 Índice salvo: {INDEX_FILE} ({len(testes)} test cases)")


def obter_indice(forcar: bool = False) -> List[Dict]:
    """Obtém índice: do cache se válido, senão re-indexa do GitHub."""
    if not forcar:
        testes = carregar_indice()
        if testes:
            return testes

    testes = indexar_testes_github()
    if testes:
        salvar_indice(testes)
    return testes


# =============================================================================
# MATCHING POR SIMILARIDADE
# =============================================================================

def buscar_tas_relacionados(resumo: str, area: str,
                            testes: List[Dict],
                            acao_realizada: str = "",
                            causa_raiz: str = "",
                            analise_causa: str = "",
                            contexto: str = "",
                            top_n: int = 8) -> List[Dict]:
    """
    Busca TAs relacionados a um bug baseando-se em palavras-chave.

    Args:
        resumo: Resumo/título do bug
        area: Área do bug (ex: "Venda Fácil")
        testes: Lista de testes indexados
        top_n: Máximo de resultados

    Returns:
        Lista de {nome, path, sistema, score, keywords_matched}
    """
    if not testes or not resumo:
        return []

    area_norm = normalizar(area) if area else ""
    area_kws = extrair_keywords(area) if area else []
    resumo_kws = extrair_keywords(resumo)
    acao_kws = extrair_keywords(acao_realizada) if acao_realizada else []
    causa_kws = extrair_keywords(causa_raiz) if causa_raiz else []
    analise_kws = extrair_keywords(analise_causa) if analise_causa else []
    contexto_kws = extrair_keywords(contexto) if contexto else []

    if not any([resumo_kws, area_kws, acao_kws, causa_kws, analise_kws, contexto_kws]):
        return []

    issue_field_keywords = {
        "resumo": resumo_kws,
        "area": area_kws,
        "acao_realizada": acao_kws,
        "causa_raiz": causa_kws,
        "analise_causa": analise_kws,
        "contexto": contexto_kws,
    }
    field_weights = {
        "resumo": 4,
        "area": 3,
        "acao_realizada": 2,
        "causa_raiz": 2,
        "analise_causa": 2,
        "contexto": 1,
    }

    resultados = []
    for test in testes:
        score = 0
        matched_kws = []
        test_kw_set = set(test.get("keywords", []))
        test_blob = normalizar(" ".join(filter(None, [
            test.get("nome", ""),
            test.get("path", ""),
            test.get("sistema", ""),
            test.get("documentacao", ""),
            " ".join(test.get("passos", [])),
        ])))

        if not test_kw_set:
            continue

        # 1) Match de sistema/área (bônus)
        sistema_norm = normalizar(test.get("sistema", ""))
        if area_norm and area_norm in sistema_norm:
            score += 2
        elif area_kws:
            for ak in area_kws:
                if ak in sistema_norm:
                    score += 1
                    break

        # 2) Match exato/forte por campo
        for field_name, kws in issue_field_keywords.items():
            field_weight = field_weights[field_name]
            for kw in kws:
                if kw in test_kw_set:
                    score += field_weight
                    matched_kws.append(f"{field_name}:{kw}")
                elif len(kw) >= 4 and kw in test_blob:
                    score += max(1, field_weight - 1)
                    matched_kws.append(f"{field_name}:{kw}*")

        # 3) Match parcial (substring) para keywords >= 5 chars
        if score < 5:
            for field_name, kws in issue_field_keywords.items():
                for kw in kws:
                    if len(kw) < 5:
                        continue
                    for tk in test_kw_set:
                        if len(tk) >= 5 and (kw in tk or tk in kw):
                            score += 1
                            matched_kws.append(f"{field_name}:{kw}≈{tk}")
                            break

        # 4) Bônus para frases fortes no path/nome/documentação do TA
        strong_phrases = [resumo, area, acao_realizada, causa_raiz]
        for phrase in strong_phrases:
            phrase_norm = normalizar(phrase)
            if phrase_norm and len(phrase_norm) >= 8 and phrase_norm in test_blob:
                score += 3
                matched_kws.append(f"phrase:{phrase[:30]}")

        if score >= 3 and matched_kws:
            resultados.append({
                "nome": test["nome"],
                "path": test["path"],
                "sistema": test.get("sistema", ""),
                "documentacao": test.get("documentacao", ""),
                "score": score,
                "keywords_matched": matched_kws,
            })

    # Ordena por score desc, depois por nome
    resultados.sort(key=lambda x: (-x["score"], x["nome"]))

    # Deduplica por nome de teste (pode ter duplicatas de paths diferentes)
    vistos = set()
    unicos = []
    for r in resultados:
        if r["nome"] not in vistos:
            vistos.add(r["nome"])
            unicos.append(r)
        if len(unicos) >= top_n:
            break

    return unicos


def buscar_tas_para_issues(issues: List[Dict], testes: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Para cada issue, busca TAs relacionados.

    Args:
        issues: Lista de dicts com pelo menos 'key', 'resumo', 'area'
        testes: Índice de testes

    Returns:
        Dict {issue_key: [tas_relacionados]}
    """
    resultado = {}
    for issue in issues:
        key = issue.get("key", "")
        resumo = issue.get("resumo", "")
        area = issue.get("area", "")
        if key and resumo:
            resultado[key] = buscar_tas_relacionados(
                resumo,
                area,
                testes,
                acao_realizada=issue.get("acao_realizada", ""),
                causa_raiz=issue.get("causa_raiz", ""),
                analise_causa=issue.get("analise_causa", ""),
                contexto=issue.get("contexto", ""),
            )
    return resultado


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("🤖 INDEXADOR DE TESTES AUTOMATIZADOS - RCA POCKET")
    print("=" * 60)

    forcar = "--force" in sys.argv
    mostrar_match = "--match" in sys.argv

    testes = obter_indice(forcar=forcar)
    if not testes:
        print("❌ Nenhum teste indexado. Verifique GITHUB_TOKEN.")
        return

    if mostrar_match:
        # Carrega issues do cache
        cache_file = "data/issues_cache.json"
        if not os.path.exists(cache_file):
            print(f"❌ Cache de issues não encontrado: {cache_file}")
            return

        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        issues = data.get("issues", [])

        print(f"\n🔎 Buscando TAs relacionados para {len(issues)} issues...\n")

        for issue in issues:
            key = issue.get("key", "")
            resumo = issue.get("resumo", "")
            area = issue.get("area", "")
            matches = buscar_tas_relacionados(
                resumo,
                area,
                testes,
                acao_realizada=issue.get("acao_realizada", ""),
                causa_raiz=issue.get("causa_raiz", ""),
                analise_causa=issue.get("analise_causa", ""),
                contexto=issue.get("contexto", ""),
            )

            print(f"\n{'─'*60}")
            print(f"📌 {key}: {resumo[:70]}")
            print(f"   Área: {area}")
            if matches:
                print(f"   🟢 {len(matches)} TA(s) relacionados:")
                for m in matches[:5]:
                    kws = ", ".join(m["keywords_matched"][:4])
                    print(f"      • {m['nome']}")
                    print(f"        📁 {m['path']}")
                    print(f"        🔑 Keywords: {kws}  (score: {m['score']})")
            else:
                print("   🔴 Nenhum TA relacionado encontrado")

        print(f"\n{'='*60}")
        print("✅ Análise concluída!")

    print(f"\n📊 Total: {len(testes)} test cases indexados")


if __name__ == "__main__":
    main()
