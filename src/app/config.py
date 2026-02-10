"""Config from env and optional YAML/JSON file for policy and agent behavior."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from src.agent.policy import PolicyConfig


def _float_env(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _str_env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def load_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """Load config from env and optionally from file. File keys override env for policy."""
    cfg: Dict[str, Any] = {
        "policy": PolicyConfig(
            auto_approval_min_confidence=_float_env("SRE_AUTO_APPROVAL_MIN_CONFIDENCE", 0.75),
            env=_str_env("SRE_ENV", "local"),
        ),
        "use_llm": os.environ.get("GEMINI_API_KEY", "") != "",
        "memory_path": os.environ.get("SRE_MEMORY_PATH") or None,
    }
    path = config_path or os.environ.get("SRE_CONFIG_PATH")
    if path:
        path = Path(path)
        if path.exists():
            try:
                if path.suffix in (".yaml", ".yml"):
                    import yaml
                    with open(path, encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                elif path.suffix == ".json":
                    import json
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    data = {}
            except Exception:
                data = {}
            if "policy" in data:
                p = data["policy"]
                cfg["policy"] = PolicyConfig(
                    auto_approval_min_confidence=float(p.get("auto_approval_min_confidence", 0.75)),
                    env=str(p.get("env", "local")),
                )
            if "memory_path" in data:
                cfg["memory_path"] = data["memory_path"]
    return cfg
