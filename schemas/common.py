from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str = Field(..., examples=["INPUT_FORBIDDEN"])
    message: str
    detail: str | None = None
