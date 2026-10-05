"""Configuration loading for NutTx."""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def load_config(path: str = "config.toml") -> dict:
    p = Path(path)
    if not p.exists():
        return {
            "device": {"name": ""},
            "engine": {"preload": True, "sample_rate": 0, "channels": 1},
            "global": {"volume": 0.8},
            "keys": {},
            "overrides": {},
        }
    with open(p, "rb") as f:
        return tomllib.load(f)
