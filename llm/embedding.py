"""Embedding 适配层：OpenAI 兼容协议（/embeddings）。"""

from __future__ import annotations

from collections.abc import Sequence

from openai import AsyncOpenAI

from core.config import get_settings
from core.errors import llm_upstream
from core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class Embedder:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self._client = AsyncOpenAI(
            api_key=api_key or settings.embedding_api_key or settings.llm_api_key or "EMPTY",
            base_url=base_url or settings.embedding_base_url or settings.llm_base_url,
            timeout=settings.llm_timeout,
        )
        self.model = model or settings.embedding_model

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            resp = await self._client.embeddings.create(model=self.model, input=list(texts))
        except Exception as exc:  # noqa: BLE001
            raise llm_upstream(f"Embedding 服务异常: {exc}") from exc
        vectors = [item.embedding for item in resp.data]
        self._check_dim(vectors)
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_documents([text])
        return vectors[0] if vectors else []

    def _check_dim(self, vectors: list[list[float]]) -> None:
        if vectors and len(vectors[0]) != settings.embedding_dim:
            logger.warning(
                "embedding dim mismatch: got %d, config %d —— 请同步 .env EMBEDDING_DIM",
                len(vectors[0]),
                settings.embedding_dim,
            )


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
