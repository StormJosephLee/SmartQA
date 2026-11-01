"""长期记忆单元测试（不含需要真实 Postgres/pgvector 的部分）。"""

import pytest
from fastapi.testclient import TestClient

from main import app
from memory import long_term

client = TestClient(app)


class _Mem:
    """替代 ORM 对象的轻量替身。"""

    def __init__(self, kind: str, content: str):
        self.kind = kind
        self.content = content


class _FakeLLM:
    def __init__(self, reply: str | Exception):
        self._reply = reply
        self.called = False

    async def complete(self, messages, model=None, temperature=0.2):
        self.called = True
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


@pytest.mark.parametrize(
    "raw,expected",
    [
        # 规整 JSON 数组
        ('[{"kind":"fact","content":"用户是后端"}]', [("fact", "用户是后端")]),
        # markdown 代码块包裹
        ('```json\n[{"kind":"profile","content":"小红"}]\n```', [("profile", "小红")]),
        # 只有 json 前缀，没有反引号
        ("json [{\"kind\":\"preference\",\"content\":\"回答简洁\"}]", [("preference", "回答简洁")]),
        # 前后夹带废话
        ("好的，我提取到：[]，以上。", []),
        # 显式空数组
        ("[]", []),
        # 完全不是 JSON
        ("我无法提取", []),
        # 单个对象而非数组
        ('{"kind":"fact","content":"x"}', []),
        # kind 缺省应回落为 fact
        ('[{"content":"只有内容"}]', [("fact", "只有内容")]),
        # 混入非法元素应被跳过
        ('[123, {"content":"有效"}]', [("fact", "有效")]),
    ],
)
def test_parse_memories_is_tolerant(raw, expected):
    items = long_term._parse_memories(raw)
    assert [(i["kind"], i["content"]) for i in items] == expected


def test_render_context_empty_input():
    assert long_term.render_context([]) == ""
    assert long_term.render_context(None) == ""


def test_render_context_includes_every_item():
    text = long_term.render_context([_Mem("preference", "回答用中文"), _Mem("fact", "住在上海")])
    assert "[preference] 回答用中文" in text
    assert "[fact] 住在上海" in text
    # 头部引导语 + 每条记忆各占一行
    assert len(text.splitlines()) == 3


def test_allowed_kinds_contains_fact():
    kinds = long_term.allowed_kinds()
    assert kinds
    assert "fact" in kinds


def test_enabled_reads_config():
    assert isinstance(long_term.enabled(), bool)


@pytest.mark.asyncio
async def test_extract_memories_parses_llm_reply(monkeypatch):
    fake = _FakeLLM('```json\n[{"kind":"fact","content":"用户住在上海"}]\n```')
    monkeypatch.setattr(long_term, "get_llm", lambda: fake)
    items = await long_term.extract_memories("我住上海", "好的")
    assert fake.called
    assert items == [{"content": "用户住在上海", "kind": "fact"}]


@pytest.mark.asyncio
async def test_extract_memories_swallows_llm_failure(monkeypatch):
    monkeypatch.setattr(long_term, "get_llm", lambda: _FakeLLM(RuntimeError("upstream down")))
    assert await long_term.extract_memories("x", "y") == []


@pytest.mark.asyncio
async def test_extract_skipped_when_disabled(monkeypatch):
    def fake_cfg(key, default=None):
        return False if key.endswith("extract_enabled") else default

    monkeypatch.setattr(long_term, "cfg", fake_cfg)
    fake = _FakeLLM("[]")
    monkeypatch.setattr(long_term, "get_llm", lambda: fake)
    assert await long_term.extract_memories("x", "y") == []
    assert not fake.called


def test_memory_api_requires_token():
    resp = client.get("/api/v1/memory")
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"


def test_memory_delete_requires_token():
    resp = client.delete("/api/v1/memory/mem_1")
    assert resp.status_code == 401
