"""
Importa JSON exportado via browser (API Jira /rest/api/2/search)
e converte para o formato de cache do rca-pocket.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from config_loader import load_config as load_project_config
from jira_client import normalize_issue

EXPORT_FILE = Path("data/jira_export_browser.json")
CACHE_FILE = Path("data/issues_cache.json")
SYNC_FILE = Path("data/last_sync.txt")

# Carrega config
config = load_project_config()

# Carrega export do browser
with open(EXPORT_FILE, encoding="utf-8") as f:
    data = json.load(f)

issues_raw = data.get("issues", [])
total = data.get("total", len(issues_raw))
print(f"[INFO] {total} issues encontradas no export do browser")

# Normaliza cada issue
normalized = []
for issue in issues_raw:
    try:
        n = normalize_issue(issue, config)
        normalized.append(n)
        print(f"  {n['key']} | {n['prioridade']} | {n['status']} | {n['resumo'][:60]}")
    except Exception as e:
        print(f"  ERRO ao normalizar {issue.get('key', '?')}: {e}")

# Salva no formato de cache
cache_data = {
    "synced_at": datetime.now(timezone.utc).isoformat(),
    "total": len(normalized),
    "issues": normalized,
}

with open(CACHE_FILE, "w", encoding="utf-8") as f:
    json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)

SYNC_FILE.write_text(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

print(f"\n✅ {len(normalized)} issues importadas e salvas em {CACHE_FILE}")
print(f"   Sync timestamp: {SYNC_FILE.read_text().strip()}")
