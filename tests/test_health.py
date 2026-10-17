from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_root_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "SmartQA"
    assert "X-Trace-Id" in resp.headers


def test_api_health():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["app"] == "SmartQA"


def test_chat_requires_token():
    resp = client.post("/api/v1/chat", json={"message": "你好"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "UNAUTHORIZED"
