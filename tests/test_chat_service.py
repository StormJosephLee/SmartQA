from schemas.chat import ChatRequest
from services.chat_service import ChatService, estimate_tokens, sse


def test_estimate_tokens():
    assert estimate_tokens("") >= 1
    assert estimate_tokens("a" * 300) == 100


def test_sse_format():
    text = sse("token", {"delta": "你好"})
    assert text.startswith("event: token\n")
    assert text.endswith("\n\n")
    assert '"delta": "你好"' in text


def test_to_citations_maps_evidence():
    evidence = [
        {"content": "年假 5-15 天", "source": "handbook.pdf", "page": 12, "score": 0.86},
        {"content": "病假需提交证明", "source": "leave.md", "page": 0, "score": 0.5},
    ]
    citations = ChatService._to_citations(evidence)
    assert len(citations) == 2
    assert citations[0].source == "handbook.pdf"
    assert citations[0].page == 12
    assert citations[1].snippet.startswith("病假")


def test_chat_request_defaults():
    req = ChatRequest(message="你好")
    assert req.use_rag is True
    assert req.use_agent is False
    assert req.stream is False
