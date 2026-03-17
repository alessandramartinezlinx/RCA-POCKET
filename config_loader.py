"""Carrega rca_config.yaml com override opcional por máquina."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


BASE_CONFIG = "rca_config.yaml"
LOCAL_CONFIG = "rca_config.local.yaml"


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = deepcopy(base)
        for key, value in override.items():
            if key in merged:
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    return deepcopy(override)


def load_config(base_path: str | Path | None = None) -> dict:
    base_dir = Path(base_path).parent if base_path else Path(__file__).parent
    config_path = base_dir / BASE_CONFIG
    local_config_path = base_dir / LOCAL_CONFIG

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if local_config_path.exists():
        with open(local_config_path, encoding="utf-8") as f:
            local_config = yaml.safe_load(f) or {}
        config = _deep_merge(config, local_config)

    return config
