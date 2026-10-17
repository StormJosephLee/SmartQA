"""配置中心：环境变量（敏感）+ config/settings.yaml（可调参数）。

遵循 architecture.md#1 设计原则 1：配置与代码分离，零硬编码。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"


class Settings(BaseSettings):
    """环境变量配置（对应 .env.example）。"""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 应用
    app_env: str = "dev"
    log_level: str = "INFO"

    # LLM（OpenAI 兼容协议）
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_fallback_model: str = ""
    llm_timeout: int = 30
    llm_max_retries: int = 2

    # Embedding
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # Rerank（none | http）
    rerank_provider: str = "none"
    rerank_base_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = ""

    # 联网搜索（none | tavily | serper）
    web_search_provider: str = "none"
    web_search_api_key: str = ""

    # 存储
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "smartqa"
    postgres_password: str = "smartqa"
    postgres_db: str = "smartqa"
    redis_url: str = "redis://localhost:6379/0"

    # 鉴权
    jwt_secret: str = "change-me-please"
    jwt_ttl_hours: int = 12
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"

    # 可观测
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    # 工具安全
    agent_allowed_tools: str = "kb_search,web_search,calculator,db_query"
    db_readonly_views: str = ""

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def allowed_tools(self) -> list[str]:
        return [t.strip() for t in self.agent_allowed_tools.split(",") if t.strip()]

    @property
    def readonly_views(self) -> list[str]:
        return [v.strip() for v in self.db_readonly_views.split(",") if v.strip()]


class YamlConfig:
    """config/settings.yaml 的读取封装，支持点号路径取值。"""

    def __init__(self, data: dict[str, Any]):
        self._data = data or {}

    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self._data
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_yaml_config() -> YamlConfig:
    settings_file = CONFIG_DIR / "settings.yaml"
    if not settings_file.exists():
        return YamlConfig({})
    with settings_file.open(encoding="utf-8") as fp:
        return YamlConfig(yaml.safe_load(fp) or {})


def cfg(path: str, default: Any = None) -> Any:
    """便捷读取：cfg('retrieval.vector_top_k', 20)。"""
    return get_yaml_config().get(path, default)
