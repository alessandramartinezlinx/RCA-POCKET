"""
sync_jira_browser.py — Sincroniza issues do Jira via browser (login manual).

Fluxo:
  1. Abre o Jira no browser (Playwright)
  2. Aguarda o usuário fazer login manualmente
  3. Usa a sessão autenticada para chamar a REST API do Jira
  4. Normaliza as issues e salva no cache local
  5. Gera a planilha Excel automaticamente

Uso:
  python sync_jira_browser.py              # extração completa
  python sync_jira_browser.py --no-excel   # só atualiza o cache, sem gerar Excel

Pré-requisitos:
  pip install playwright pyyaml
  playwright install chromium
"""
import json
import sys
import yaml
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
CONFIG_FILE = Path("rca_config.yaml")
CACHE_FILE = Path("data/issues_cache.json")
SYNC_FILE = Path("data/last_sync.txt")
EXPORT_FILE = Path("data/jira_export_browser.json")  # backup do JSON bruto

with open(CONFIG_FILE, encoding="utf-8") as f:
    config = yaml.safe_load(f)

BASE_URL = config["jira"]["base_url"].rstrip("/")
FILTER_ID = config["jira"]["filter_id"]
FIELDS = config["jira"]["fields"]
MAX_RESULTS = config["jira"]["max_results_per_page"]

# JQL — mesma usada pelo jira_client.py
JQL = f"filter={FILTER_ID} ORDER BY updated ASC"


def build_api_url(start_at: int = 0, fields_override: str = None) -> str:
    """Monta a URL da REST API de busca do Jira."""
    fields_csv = fields_override or ",".join(FIELDS)
    return (
        f"{BASE_URL}/rest/api/2/search"
        f"?jql={JQL}"
        f"&fields={fields_csv}"
        f"&maxResults={MAX_RESULTS}"
        f"&startAt={start_at}"
    )


def discover_person_fields(page) -> dict:
    """
    Busca 1 issue com todos os campos para descobrir customfields de pessoa.
    Retorna dict com nomes de campos encontrados.
    """
    print("\n🔍 Descobrindo campos customizados de pessoa ...")

    # Busca metadados de campos do Jira
    field_names = {}
    fields_meta = page.evaluate(f"""
        async () => {{
            const resp = await fetch("{BASE_URL}/rest/api/2/field", {{
                headers: {{ "Accept": "application/json" }}
            }});
            if (!resp.ok) return [];
            return await resp.json();
        }}
    """)
    if fields_meta:
        for f in fields_meta:
            field_names[f.get("id", "")] = f.get("name", "")

    # Busca 1 issue com TODOS os campos
    url = (
        f"{BASE_URL}/rest/api/2/search"
        f"?jql={JQL}&fields=*all&maxResults=1"
    )
    result = page.evaluate(f"""
        async () => {{
            const resp = await fetch("{url}", {{
                headers: {{ "Accept": "application/json" }}
            }});
            if (!resp.ok) return null;
            return await resp.json();
        }}
    """)

    if not result or not result.get("issues"):
        print("   ⚠️  Não conseguiu buscar campos. Usando padrões.")
        return {}

    issue = result["issues"][0]
    fields = issue.get("fields", {})
    found = {}

    # Procura campos de pessoa (dict com displayName)
    for k, v in fields.items():
        if k.startswith("customfield_") and v and isinstance(v, dict) and "displayName" in v:
            name = field_names.get(k, k)
            found[k] = {"name": name, "value": v["displayName"]}

    if found:
        print("   Campos de pessoa encontrados:")
        for k, info in found.items():
            print(f"     {k:25s} = {info['name']:35s} → {info['value']}")

    # Identifica campos específicos
    dev_field = None
    qa_field = None
    for k, info in found.items():
        name_lower = info["name"].lower()
        if "responsável" in name_lower and "desenvolvimento" in name_lower:
            dev_field = k
        elif "responsável" in name_lower and "qa" in name_lower:
            qa_field = k

    if dev_field:
        print(f"\n   ✅ Responsável Dev: {dev_field} ({field_names.get(dev_field, '')})")
    if qa_field:
        print(f"   ✅ Responsável QA:  {qa_field} ({field_names.get(qa_field, '')})")

    return {"dev_field": dev_field, "qa_field": qa_field, "all_person_fields": found}


def fetch_all_issues(page) -> list:
    """Busca todas as issues paginando via fetch() no browser."""
    all_issues = []
    start_at = 0

    while True:
        url = build_api_url(start_at)
        print(f"  [API] Buscando startAt={start_at} ...")

        # Executa fetch dentro do browser (usa cookies de sessão)
        result = page.evaluate(f"""
            async () => {{
                const resp = await fetch("{url}", {{
                    headers: {{ "Accept": "application/json" }}
                }});
                if (!resp.ok) {{
                    return {{ error: resp.status, text: await resp.text() }};
                }}
                return await resp.json();
            }}
        """)

        if isinstance(result, dict) and "error" in result:
            status = result["error"]
            detail = result.get("text", "")[:200]
            raise RuntimeError(f"Jira retornou HTTP {status}: {detail}")

        issues = result.get("issues", [])
        total = result.get("total", 0)
        all_issues.extend(issues)

        print(f"  [API] Recebidas {len(issues)} issues (total: {total})")

        start_at += len(issues)
        if start_at >= total or not issues:
            break

    return all_issues


def normalize_and_save(issues_raw: list):
    """Normaliza issues e salva no cache."""
    from jira_client import normalize_issue

    print(f"\n📋 Normalizando {len(issues_raw)} issues ...")
    normalized = []
    for issue in issues_raw:
        try:
            n = normalize_issue(issue, config)
            normalized.append(n)
            vinc = n.get("qtd_vinculos", 0)
            print(f"  ✓ {n['key']:20s} | vinc={vinc:3d} | {n['prioridade']:12s} | {n['resumo'][:55]}")
        except Exception as e:
            print(f"  ✗ ERRO {issue.get('key', '?')}: {e}")

    # Salva cache
    cache_data = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "total": len(normalized),
        "issues": normalized,
        "meta": {"force_use_cache": True},
    }
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)

    SYNC_FILE.write_text(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    print(f"\n✅ {len(normalized)} issues salvas em {CACHE_FILE}")
    return normalized


def generate_excel_report():
    """Gera a planilha Excel."""
    print("\n📊 Gerando planilha Excel ...")
    from generate_excel import generate_excel as _gen
    _gen(config)


def main():
    skip_excel = "--no-excel" in sys.argv

    print("=" * 60)
    print("  RCA Pocket — Sync via Browser")
    print("=" * 60)
    print(f"  Jira:   {BASE_URL}")
    print(f"  Filter: {FILTER_ID}")
    print(f"  JQL:    {JQL}")
    print("=" * 60)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\n❌ Playwright não está instalado.")
        print("   Execute: pip install playwright && playwright install chromium")
        sys.exit(1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        # Abre a página de login do Jira
        login_url = f"{BASE_URL}/login.jsp"
        print(f"\n🌐 Abrindo Jira: {login_url}")
        print("   → Faça login manualmente no browser que abriu.")
        page.goto(login_url, wait_until="domcontentloaded")

        # Aguarda login via polling da API (independe da versão/UI do Jira)
        import time as _time
        print("   ⏳ Aguardando login (verificando a cada 5s, timeout 5min) ...")
        auth_check = None
        max_attempts = 60  # 60 x 5s = 5 minutos
        for attempt in range(1, max_attempts + 1):
            # Garante que o browser está no domínio do Jira antes do fetch
            current_url = page.url
            if not current_url.startswith(BASE_URL):
                try:
                    page.goto(f"{BASE_URL}/secure/Dashboard.jspa", wait_until="domcontentloaded", timeout=10000)
                except Exception:
                    pass

            try:
                auth_check = page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch("{BASE_URL}/rest/api/2/myself", {{
                                headers: {{ "Accept": "application/json" }}
                            }});
                            if (!resp.ok) return {{ ok: false, status: resp.status }};
                            const data = await resp.json();
                            return {{ ok: true, user: data.displayName || data.name }};
                        }} catch(e) {{
                            return {{ ok: false, status: 0, error: e.message }};
                        }}
                    }}
                """)
            except Exception as e:
                auth_check = {"ok": False, "status": 0, "error": str(e)}

            if auth_check and auth_check.get("ok"):
                break

            if attempt % 6 == 0:  # a cada 30s mostra status
                mins_left = (max_attempts - attempt) * 5 // 60
                print(f"   ⏳ Ainda aguardando login... ({mins_left}min restantes)")
            _time.sleep(5)

        if not auth_check or not auth_check.get("ok"):
            print("\n⚠️  Login não detectado automaticamente.")
            input("   Pressione ENTER quando estiver logado no Jira... ")
            # Navega para o Jira e re-verifica
            try:
                page.goto(f"{BASE_URL}/secure/Dashboard.jspa", wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
            try:
                auth_check = page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch("{BASE_URL}/rest/api/2/myself", {{
                                headers: {{ "Accept": "application/json" }}
                            }});
                            if (!resp.ok) return {{ ok: false, status: resp.status }};
                            const data = await resp.json();
                            return {{ ok: true, user: data.displayName || data.name }};
                        }} catch(e) {{
                            return {{ ok: false, status: 0, error: e.message }};
                        }}
                    }}
                """)
            except Exception as e:
                auth_check = {"ok": False, "status": 0, "error": str(e)}

            if not auth_check or not auth_check.get("ok"):
                err_detail = auth_check.get("error", "") or f"HTTP {auth_check.get('status', '?')}"
                print(f"   ❌ Falha na autenticação: {err_detail}")
                browser.close()
                sys.exit(1)

        user = auth_check.get("user", "?")
        print(f"   ✅ Logado como: {user}")

        # Descobre campos customizados de pessoa (dev/qa responsável)
        person_fields = discover_person_fields(page)
        extra_fields = []
        if person_fields.get("dev_field"):
            extra_fields.append(person_fields["dev_field"])
        if person_fields.get("qa_field"):
            extra_fields.append(person_fields["qa_field"])

        # Adiciona campos descobertos à lista de fields
        if extra_fields:
            global FIELDS
            FIELDS = list(FIELDS) + [f for f in extra_fields if f not in FIELDS]
            print(f"   📋 Campos adicionais: {', '.join(extra_fields)}")

        # Busca todas as issues
        print(f"\n🔎 Buscando issues (filter={FILTER_ID}) ...")
        issues_raw = fetch_all_issues(page)

        # Salva JSON bruto como backup
        export_data = {
            "total": len(issues_raw),
            "issues": issues_raw,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "exported_by": user,
            "person_fields": person_fields,
        }
        EXPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(EXPORT_FILE, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"   💾 JSON bruto salvo em {EXPORT_FILE}")

        browser.close()

    # Normaliza e salva no cache
    normalized = normalize_and_save(issues_raw)

    # Gera Excel
    if not skip_excel and normalized:
        generate_excel_report()

    print("\n" + "=" * 60)
    print("  ✅ Sincronização concluída!")
    print(f"     Issues: {len(normalized)}")
    print(f"     Cache:  {CACHE_FILE}")
    if not skip_excel:
        print(f"     Excel:  {config['excel']['arquivo_saida']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
