"""Prompt 模板加载：config/prompts/*.yaml（配置与代码分离）。"""

from __future__ import annotations

from functools import lru_cache

import yaml

from core.config import CONFIG_DIR

PROMPT_DIR = CONFIG_DIR / "prompts"


@lru_cache
def load_prompt_file(name: str) -> dict:
    path = PROMPT_DIR / f"{name}.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fp:
        return yaml.safe_load(fp) or {}


def prompt(name: str, key: str, default: str = "") -> str:
    return load_prompt_file(name).get(key, default)
