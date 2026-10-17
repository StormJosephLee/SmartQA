from rag.bm25 import tokenize
from rag.retriever import rrf_fuse
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
