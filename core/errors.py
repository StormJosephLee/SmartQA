"""统一错误码（对应 api.md 通用约定：{"code": "BIZ_XXX", "message": "..."}）。"""

from __future__ import annotations

from typing import Any

# 业务错误码
INPUT_FORBIDDEN = "INPUT_FORBIDDEN"
OUTPUT_FORBIDDEN = "OUTPUT_FORBIDDEN"
RATE_LIMIT = "RATE_LIMIT"
LLM_UPSTREAM = "LLM_UPSTREAM"
UNAUTHORIZED = "UNAUTHORIZED"
FORBIDDEN = "FORBIDDEN"
NOT_FOUND = "NOT_FOUND"
INTERNAL = "INTERNAL"


class BizError(Exception):
    """业务异常：由全局异常处理器转成 JSON 响应。"""

    def __init__(self, code: str, message: str, status_code: int = 400, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


def unauthorized(message: str = "Token 缺失或失效") -> BizError:
    return BizError(UNAUTHORIZED, message, status_code=401)


def forbidden(message: str = "无权访问该知识库") -> BizError:
    return BizError(FORBIDDEN, message, status_code=403)


def not_found(message: str = "资源不存在") -> BizError:
    return BizError(NOT_FOUND, message, status_code=404)


def llm_upstream(
    message: str = "模型服务异常",
    *,
    status_code: int = 502,
    detail: Any = None,
) -> BizError:
    return BizError(LLM_UPSTREAM, message, status_code=status_code, detail=detail)
