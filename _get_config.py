"""Helper interno: imprime um valor da config para uso no run.bat."""
import sys
from config_loader import load_config

try:
    cfg = load_config()
    section = sys.argv[1] if len(sys.argv) > 1 else "excel"
    key     = sys.argv[2] if len(sys.argv) > 2 else "sharepoint_url"
    print(cfg.get(section, {}).get(key, ""))
except Exception:
    print("")
