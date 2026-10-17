#!/usr/bin/env python3
"""离线冒烟用的假 OpenAI 兼容服务（仅本地开发/测试用，不接外部网络）。

提供：
- POST /v1/chat/completions（支持 stream）
- POST /v1/embeddings（基于字符哈希的确定性向量，保证"字面相近即相似"）

启动：
    .venv/bin/python scripts/mock_llm.py --port 8100
然后把环境变量指向它：
    LLM_BASE_URL=http://localhost:8100/v1 EMBEDDING_BASE_URL=http://localhost:8100/v1 \
    LLM_API_KEY=test EMBEDDING_API_KEY=test uvicorn main:app
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="SmartQA Mock LLM")

EMBED_DIM = 1024


def embed(text: str) -> list[float]:
    """字符哈希 → 稀疏向量 → L2 归一化，保证相同字符越多越相似。"""
    vec = [0.0] * EMBED_DIM
    for ch in (text or "").lower():
        digest = hashlib.md5(ch.encode("utf-8"), usedforsecurity=False).hexdigest()
        vec[int(digest[:8], 16) % EMBED_DIM] += 1.0
        vec[int(digest[8:16], 16) % EMBED_DIM] += 0.5
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec] if norm else vec


def _extract(prompt: str, key: str) -> str:
    match = re.search(rf"{key}[：:]\s*(.+)", prompt)
    return match.group(1).strip() if match else ""


def compose(prompt: str) -> str:
    if "规划器" in prompt:
        question = _extract(prompt, "问题") or "未知问题"
        # 命中算术问法时演示工具调用
        expr = re.search(r"([0-9\.\s\+\-\*\/\(\)]{3,})\s*等于多少", question)
        if expr:
            return json.dumps(
                {"action": "tool", "tool": "calculator", "args": {"expr": expr.group(1).strip()}},
                ensure_ascii=False,
            )
        return json.dumps({"action": "retrieve", "sub_query": question}, ensure_ascii=False)
    if "反思器" in prompt:
        return json.dumps({"sufficient": True}, ensure_ascii=False)

    # 优先使用工具结果（Agent 路径），其次使用知识片段（RAG 路径）
    if "工具结果：" in prompt:
        tools = prompt.split("工具结果：")[-1].split("对话历史：")[0].strip()
        if tools and tools != "（未调用工具）":
            summary = " ".join(tools.split())[:200]
            return f"我调用了工具，结果是：{summary}"
    evidence = prompt.split("证据：")[-1].split("工具结果：")[0].strip()
    if evidence and evidence != "知识库未覆盖此问题":
        summary = re.sub(r"\s+", " ", evidence)[:200]
        return f"根据知识片段：{summary}……（引用 [1]）"
    return "知识库未覆盖此问题"


def _chunk(model: str, content: str) -> str:
    payload = {
        "id": "chatcmpl-mock",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": model,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    model = body.get("model", "mock-model")
    prompt = messages[-1].get("content", "") if messages else ""
    content = compose(prompt)

    if body.get("stream"):
        async def gen():
            for token in re.findall(r".{1,8}", content, re.S):
                yield _chunk(model, token)
            yield _chunk(model, "")
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return JSONResponse(
        {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": len(content), "total_tokens": len(content) + 10},
        }
    )


@app.post("/v1/embeddings", response_model=None)
async def embeddings(request: Request):
    body = await request.json()
    raw_input = body.get("input")
    texts = [raw_input] if isinstance(raw_input, str) else list(raw_input or [])
    return JSONResponse(
        {
            "object": "list",
            "model": body.get("model", "mock-embedding"),
            "data": [
                {"object": "embedding", "index": i, "embedding": embed(t)} for i, t in enumerate(texts)
            ],
            "usage": {"prompt_tokens": sum(len(t) for t in texts), "total_tokens": sum(len(t) for t in texts)},
        }
    )


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
