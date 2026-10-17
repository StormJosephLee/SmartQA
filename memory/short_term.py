"""短期记忆：Redis 存会话历史，Redis 不可用时退化为内存（dataflow.md#3）。"""

from __future__ import annotations

import json
from typing import Any

from core.config import cfg, get_settings
from core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

TTL_SECONDS = 24 * 3600


class ShortTermMemory:
    def __init__(self) -> None:
        self._redis = None
        self._fallback: dict[str, list[dict[str, str]]] = {}
        self._degraded = False
        try:  # 延迟建立连接，首次失败即降级
            import redis

            self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis unavailable, memory degraded: %s", exc)
            self._redis = None

    @property
    def degraded(self) -> bool:
        return self._redis is None or self._degraded

    def _key(self, session_id: str) -> str:
        return f"smartqa:chat:{session_id}"

    def load(self, session_id: str) -> list[dict[str, str]]:
        max_turns = int(cfg("memory.max_turns", 10))
        if self._redis is not None and not self._degraded:
            try:
                raw = self._redis.get(self._key(session_id))
                if raw:
                    items: list[dict[str, Any]] = json.loads(raw)
                    return items[-max_turns * 2 :]
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis read failed, degrade to memory: %s", exc)
                self._degraded = True
        return self._fallback.get(session_id, [])[-max_turns * 2 :]

    def append(self, session_id: str, role: str, content: str) -> None:
        max_turns = int(cfg("memory.max_turns", 10))
        max_chars = int(cfg("memory.max_chars", 4000))
        history = self.load(session_id)
        history.append({"role": role, "content": content[:max_chars]})
        history = history[-max_turns * 2 :]

        if self._redis is not None and not self._degraded:
            try:
                self._redis.set(
                    self._key(session_id), json.dumps(history, ensure_ascii=False), ex=TTL_SECONDS
                )
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("redis write failed, degrade to memory: %s", exc)
                self._degraded = True
        self._fallback[session_id] = history

    def clear(self, session_id: str) -> None:
        if self._redis is not None and not self._degraded:
            try:
                self._redis.delete(self._key(session_id))
            except Exception:  # noqa: BLE001
                pass
        self._fallback.pop(session_id, None)


_memory: ShortTermMemory | None = None


def get_memory() -> ShortTermMemory:
    global _memory
    if _memory is None:
        _memory = ShortTermMemory()
    return _memory
