"""kb_service 路径转换的单元测试。"""

from pathlib import Path

from core.config import ROOT_DIR
from services.kb_service import resolve_source_uri, to_source_uri


def test_to_source_uri_returns_relative():
    p = ROOT_DIR / "storage" / "uploads" / "abc123.pdf"
    assert to_source_uri(p) == "storage/uploads/abc123.pdf"


def test_to_source_uri_keeps_outside_paths_absolute():
    """不在项目根下的路径（如自定义存储目录）保留原样，不强行转换。"""
    outside = Path("/opt/smartqa-outside/x.pdf")
    assert to_source_uri(outside) == str(outside)


def test_round_trip_recovers_absolute_path():
    p = ROOT_DIR / "storage" / "uploads" / "abc123.pdf"
    assert resolve_source_uri(to_source_uri(p)) == p


def test_resolve_absolute_passthrough():
    """旧数据的绝对路径格式直接使用，保证删除文件等操作兼容。"""
    assert resolve_source_uri("/tmp/x.pdf") == Path("/tmp/x.pdf")


def test_resolve_relative_ignores_cwd(tmp_path, monkeypatch):
    """相对路径必须基于项目根解析，与进程启动目录无关。"""
    monkeypatch.chdir(tmp_path)
    assert resolve_source_uri("storage/uploads/abc.pdf") == ROOT_DIR / "storage/uploads/abc.pdf"
