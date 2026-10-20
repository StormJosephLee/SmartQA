"""Embedding 端到端冒烟：抓真实错误并打出来分析。"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("EMBEDDING_BASE_URL", "http://localhost:8123/v1")
os.environ.setdefault("EMBEDDING_API_KEY", "test")
os.environ.setdefault("EMBEDDING_MODEL", "BAAI/bge-m3")
os.environ.setdefault("LLM_API_KEY", "test")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:8123/v1")
os.environ.setdefault("LLM_MAX_RETRIES", "3")
os.environ.setdefault("LLM_RETRY_BACKOFF", "0.2")
os.environ.setdefault("LOG_LEVEL", "INFO")

from core.config import get_settings  # noqa: E402
from core.errors import BizError  # noqa: E402
from llm.embedding import Embedder, get_embedder  # noqa: E402

results = []


def case(name):
    def deco(fn):
        async def wrapper():
            t0 = time.perf_counter()
            try:
                info = await fn() or ""
                results.append((name, "OK", f"{info}  [{int((time.perf_counter()-t0)*1000)}ms]", ""))
            except BizError as be:
                results.append(
                    (name, "BIZ", f"{be.code} | {be.message}",
                     "".join(traceback.format_exception(type(be), be, be.__traceback__))[-400:])
                )
            except Exception as exc:
                results.append(
                    (name, "ERR", f"{type(exc).__name__}: {exc}",
                     "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-600:])
                )
        return wrapper
    return deco


# 真实调用：mock
@case("real_default")
async def t1():
    e = Embedder()
    v = await e.embed_query("hello")
    return f"dim={len(v)}"

@case("real_256")
async def t2():
    e = Embedder(dimensions=256)
    v = await e.embed_query("hi")
    return f"dim={len(v)}"

@case("real_0")
async def t3():
    e = Embedder(dimensions=0)
    v = await e.embed_query("hi")
    return f"dim={len(v)}"

@case("real_batch")
async def t4():
    e = Embedder()
    vs = await e.embed_documents(["a","b","c","d","e"])
    return f"batch={len(vs)} each={len(vs[0])}"

@case("real_empty")
async def t5():
    e = Embedder()
    vs = await e.embed_documents([])
    return f"empty -> {vs}"

@case("real_concurrent_10")
async def t6():
    e = Embedder()
    vs = await asyncio.gather(*[e.embed_query(f"q{i}") for i in range(10)])
    return f"{len(vs)} 并发均成功"

@case("real_singleton")
async def t7():
    a, b = get_embedder(), get_embedder()
    return "singleton ok" if a is b else f"不同实例 a={id(a)} b={id(b)}"


# 真实失败路径：模拟上游
import httpx
from openai import AsyncOpenAI


def make_client(handler):
    return AsyncOpenAI(
        api_key="t", base_url="http://mock/v1", timeout=5, max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@case("mock_500_always")
async def t8():
    async def h(req):
        return httpx.Response(500, json={"error": "Service load is too high, please try again later"})
    e = Embedder(base_url="http://mock/v1", api_key="t")
    e._client = make_client(h)
    return await e.embed_query("x")  # 应当抛 BizError


@case("mock_500_500_200")
async def t9():
    state = {"n": 0}
    async def h(req):
        state["n"] += 1
        if state["n"] <= 2:
            return httpx.Response(500, json={"error": "Service load is too high, please try again later"})
        return httpx.Response(200, json={"object":"list","data":[{"object":"embedding","index":0,"embedding":[0.1]*1024}]})
    e = Embedder(base_url="http://mock/v1", api_key="t")
    e._client = make_client(h)
    v = await e.embed_query("x")
    return f"第{state['n']}次成功 dim={len(v)}"


@case("mock_400_客户端错误")
async def t10():
    async def h(req):
        return httpx.Response(400, json={"error": "Invalid input: too long"})
    e = Embedder(base_url="http://mock/v1", api_key="t")
    e._client = make_client(h)
    return await e.embed_query("x")


@case("mock_400_dims_unsupported")
async def t11():
    state = {"n": 0}
    async def h(req):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(400, json={"error": "unsupported parameter: dimensions"})
        # 第二次不带 dimensions，返回 1024 维
        return httpx.Response(200, json={"object":"list","data":[{"object":"embedding","index":0,"embedding":[0.1]*1024}]})
    e = Embedder(dimensions=256, base_url="http://mock/v1", api_key="t")
    e._client = make_client(h)
    v = await e.embed_query("x")
    return f"第{state['n']}次成功 dim={len(v)} dim_supported={e._dimensions_supported}"


@case("mock_conn_refused")
async def t12():
    e = Embedder(base_url="http://127.0.0.1:1/v1", api_key="t")
    return await e.embed_query("x")


@case("mock_short_vector_with_dim_request")
async def t13():
    async def h(req):
        # 客户端要求 dimensions=1024，服务端忽略了
        return httpx.Response(200, json={"object":"list","data":[{"object":"embedding","index":0,"embedding":[0.1]*512}]})
    e = Embedder(dimensions=1024, base_url="http://mock/v1", api_key="t")
    e._client = make_client(h)
    v = await e.embed_query("x")
    return f"got dim={len(v)} expected={e.expected_dim}"


@case("mock_429_rate_limit")
async def t14():
    state = {"n": 0}
    async def h(req):
        state["n"] += 1
        if state["n"] <= 2:
            return httpx.Response(429, json={"error": "Too Many Requests"})
        return httpx.Response(200, json={"object":"list","data":[{"object":"embedding","index":0,"embedding":[0.1]*1024}]})
    e = Embedder(base_url="http://mock/v1", api_key="t")
    e._client = make_client(h)
    v = await e.embed_query("x")
    return f"第{state['n']}次成功"


@case("real_pipeline_ingest")
async def t15():
    """完整跑 rag.pipeline.ingest_document（用 sqlite 内存 + 真实 mock embedding）"""
    import os
    # 切到 sqlite
    os.environ["POSTGRES_HOST"] = "none"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine("sqlite:///:memory:")
    # 简化：直接造表
    from sqlalchemy import Column, Integer, String, Text
    from sqlalchemy.orm import DeclarativeBase
    class _D(DeclarativeBase):
        __tablename__ = "documents"
        id = Column(String(64), primary_key=True)
        kb_id = Column(String(64))
        title = Column(String(256))
        source_uri = Column(String(512))
        status = Column(String(32), default="pending")
        chunk_count = Column(Integer, default=0)
        error = Column(Text, default="")
    _D.__table__.create(engine)
    Sm = sessionmaker(bind=engine)

    # 临时文件
    from pathlib import Path
    tmp = Path("/tmp/smartqa_smoke.md")
    tmp.write_text("## 智能问答系统\n\n" + ("检索增强生成。 " * 100), encoding="utf-8")
    s = Sm()
    s.add(_D(id="d1", kb_id="kb_default", title="t.md", source_uri=str(tmp)))
    s.commit()
    # 走简化版 ingest：解析+分块+embedding（不入 chunks 表因为 pgvector）
    from rag.pipeline import build_chunks
    from llm.embedding import get_embedder
    d = s.get(_D, "d1")
    chunks = build_chunks(d, tmp)  # type: ignore[arg-type]
    emb = get_embedder()
    vectors = await emb.embed_documents([c.content for c in chunks[:3]])
    return f"chunks={len(chunks)} embedded_3 dim={len(vectors[0])}"


@case("real_ingest_then_status")
async def t16():
    """用真实 Embedder 模拟一次 ingest_document 端到端，验证 Document.error 落库。"""
    os.environ["POSTGRES_HOST"] = "none"
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import Column, Integer, String, Text
    from sqlalchemy.orm import DeclarativeBase
    engine = create_engine("sqlite:///:memory:")

    class _D(DeclarativeBase):
        __tablename__ = "documents"
        id = Column(String(64), primary_key=True)
        kb_id = Column(String(64))
        title = Column(String(256))
        source_uri = Column(String(512))
        status = Column(String(32), default="pending")
        chunk_count = Column(Integer, default=0)
        error = Column(Text, default="")
    _D.__table__.create(engine)
    Sm = sessionmaker(bind=engine)

    from pathlib import Path
    tmp = Path("/tmp/smartqa_smoke2.md")
    tmp.write_text("# x\n\n" + ("内容。" * 50), encoding="utf-8")
    s = Sm()
    s.add(_D(id="d2", kb_id="kb_default", title="t2.md", source_uri=str(tmp)))
    s.commit()
    d = s.get(_D, "d2")
    # 模拟 ingest_document 失败：把 embedder 指向 1 端口
    from llm.embedding import Embedder
    import llm.embedding as mod
    mod.settings.embedding_base_url = "http://127.0.0.1:1/v1"
    mod._embedder = None  # reset
    try:
        from rag.pipeline import build_chunks
        chunks = build_chunks(d, tmp)  # type: ignore[arg-type]
        emb = Embedder()
        await emb.embed_documents([c.content for c in chunks[:2]])
        d.status = "ready"
    except BizError as be:
        d.status = "failed"
        d.error = be.message[:500]
        s.commit()
        s.close()
        return f"成功捕获并落库: status={d.status} error[:80]={d.error[:80]!r}"
    finally:
        tmp.unlink(missing_ok=True)
    return "未触发失败"


async def main():
    s = get_settings()
    print(f"=== Embedding 冒烟 ===")
    print(f"  base_url = {s.embedding_base_url}")
    print(f"  model    = {s.embedding_model}")
    print(f"  dim      = {s.embedding_dim}  (requested via {s.embedding_dimensions!r})")
    print(f"  retries  = {s.llm_max_retries}  backoff = {s.llm_retry_backoff}s")
    print()

    funcs = [v for k, v in globals().items() if k.startswith("t") and callable(v)]
    for fn in funcs:
        await fn()

    print(f"=== 结果 {len(results)} 项 ===")
    by = {"OK": [], "BIZ": [], "ERR": []}
    for n, st, info, tb in results:
        by[st].append((n, info, tb))

    for n, info, tb in by["ERR"]:
        print(f"\n[ERR] {n}\n  info: {info}\n  tail-trace: {tb}")
    for n, info, tb in by["BIZ"]:
        print(f"\n[BIZ] {n}\n  info: {info}")
    for n, info, _ in by["OK"]:
        print(f"[OK]  {n}  {info}")

    print(f"\n汇总: OK={len(by['OK'])} BIZ={len(by['BIZ'])} ERR={len(by['ERR'])}")


if __name__ == "__main__":
    asyncio.run(main())
