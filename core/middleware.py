"""中间件：X-Trace-Id 透传与全局异常处理（architecture.md#1 全链路可观测）。"""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.errors import INTERNAL, BizError
from core.logging import bind_trace, get_logger, mask_pii, reset_trace

logger = get_logger(__name__)


class TraceIdMiddleware(BaseHTTPMiddleware):
    """请求进入即生成/透传 X-Trace-Id，并统一捕获异常出口。

    trace_id 同时写入 contextvars（core.logging._TRACE_ID），使下游所有
    logger 调用自动带上 trace=<id>（observability.md §7）。
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        request.state.trace_id = trace_id
        token = bind_trace(trace_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except BizError as exc:
            logger.warning("biz error: %s %s", exc.code, mask_pii(exc.message))
            response = JSONResponse(
                status_code=exc.status_code,
                content={"code": exc.code, "message": exc.message, "detail": exc.detail},
            )
        except Exception as exc:  # noqa: BLE001 兜底，避免栈信息泄漏给客户端
            logger.exception("unhandled error: %s", exc)
            response = JSONResponse(
                status_code=500,
                content={"code": INTERNAL, "message": "服务内部错误"},
            )
        cost_ms = int((time.perf_counter() - start) * 1000)
        response.headers["X-Trace-Id"] = trace_id
        logger.info(
            "%s %s -> %s (%dms)", request.method, request.url.path, response.status_code, cost_ms
        )
        reset_trace(token)
        return response


def register_exception_handlers(app: FastAPI) -> None:
    """BizError 统一出口（中间件已兜底，此处保证直接抛出场景一致）。"""

    @app.exception_handler(BizError)
    async def _handler(request: Request, exc: BizError):  # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        )
