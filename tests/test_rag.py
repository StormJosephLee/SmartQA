from rag.bm25 import tokenize
from rag.retriever import RetrievedChunk, rrf_fuse
from rag.splitter import split_text


def test_split_recursive_respects_size():
    text = "段落一。" * 500
    chunks = split_text(text, profile="default")
    assert chunks
    assert all(len(c) <= 512 + 64 for c in chunks)


def test_split_table_keeps_whole():
    table = "| a | b |\n| 1 | 2 |"
    assert split_text(table, profile="table") == [table]


def test_rrf_fuse_prefers_overlap():
    dense = [("a", 0.9), ("b", 0.8)]
    sparse = [("b", 3.0), ("c", 2.0)]
    fused = dict(rrf_fuse([dense, sparse], k=60))
    assert fused["b"] > fused["a"]
    assert fused["b"] > fused["c"]


def test_tokenize_mixed_language():
    tokens = tokenize("年假 Annual Leave 5天")
    assert "年" in tokens and "annual" in tokens


def test_source_prefers_title_over_storage_uri():
    """引用来源应显示可读标题，而非 uuid 重命名后的存储路径。"""
    chunk = RetrievedChunk(
        id="1",
        content="x",
        meta={"title": "员工手册.pdf", "source_uri": "storage/uploads/9f8e7d6c.pdf"},
    )
    assert chunk.source == "员工手册.pdf"


def test_source_falls_back_to_uri_basename():
    """无标题时只取存储路径的文件名，不暴露服务器目录结构。"""
    chunk = RetrievedChunk(id="1", content="x", meta={"source_uri": "/srv/uploads/9f8e7d6c.pdf"})
    assert chunk.source == "9f8e7d6c.pdf"


def test_source_empty_meta_returns_empty():
    assert RetrievedChunk(id="1", content="x", meta={}).source == ""
    blank = RetrievedChunk(id="1", content="x", meta={"title": "", "source_uri": ""})
    assert blank.source == ""
