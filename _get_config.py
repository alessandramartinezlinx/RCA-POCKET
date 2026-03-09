"""Helper interno: imprime um valor do rca_config.yaml para uso no run.bat."""
import sys
import yaml

try:
    with open("rca_config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    section = sys.argv[1] if len(sys.argv) > 1 else "excel"
    key     = sys.argv[2] if len(sys.argv) > 2 else "sharepoint_url"
    print(cfg.get(section, {}).get(key, ""))
except Exception:
    print("")
