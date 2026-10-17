"""SmartQA Web 聊天界面（MVP，spec.md 10.1 要求 Streamlit）。

启动：make run-ui  →  http://localhost:8501
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
import streamlit as st

API_BASE = os.getenv("SMARTQA_API_BASE", "http://localhost:8000")
st.set_page_config(page_title="SmartQA", page_icon="💬", layout="wide")


def _headers() -> dict[str, str]:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def login(username: str, password: str) -> bool:
    try:
        resp = httpx.post(
            f"{API_BASE}/api/v1/auth/login",
            json={"username": username, "password": password},
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        st.sidebar.error(f"无法连接 API：{exc}")
        return False
    if resp.status_code != 200:
        st.sidebar.error(f"登录失败：{resp.text[:200]}")
        return False
    st.session_state["token"] = resp.json()["access_token"]
    return True


def upload(file: Any, kb_id: str) -> None:
    files = {"file": (file.name, file.getvalue())}
    resp = httpx.post(
        f"{API_BASE}/api/v1/knowledge/upload",
        files=files,
        data={"kb_id": kb_id},
        headers=_headers(),
        timeout=60,
    )
    if resp.status_code == 200:
        st.sidebar.success(f"已上传，后台入库中：{resp.json()['id']}")
    else:
        st.sidebar.error(f"上传失败：{resp.text[:200]}")


def ask_stream(question: str, use_rag: bool, use_agent: bool, session_id: str | None) -> None:
    payload = {
        "message": question,
        "session_id": session_id,
        "use_rag": use_rag,
        "use_agent": use_agent,
    }
    with httpx.stream(
        "POST",
        f"{API_BASE}/api/v1/chat/stream",
        json=payload,
        headers=_headers(),
        timeout=120,
    ) as resp:
        if resp.status_code != 200:
            st.error(f"请求失败 {resp.status_code}: {resp.read().decode()[:200]}")
            return
        event: str | None = None
        placeholder = st.empty()
        answer = ""
        citations: list[dict] = []
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "citation":
                    citations = data
                elif event == "token":
                    answer += data["delta"]
                    placeholder.markdown(answer + "▌")
                elif event == "done":
                    st.session_state["session_id"] = data["session_id"]
                    st.caption(f"tokens={data['tokens']} latency={data['latency_ms']}ms")
                elif event == "error":
                    st.error(data.get("message", "生成失败"))
        placeholder.markdown(answer or "（无内容）")
        if citations:
            with st.expander(f"引用来源（{len(citations)}）"):
                for i, cite in enumerate(citations, start=1):
                    st.markdown(
                        f"[{i}] **{cite.get('source', '')}** · p{cite.get('page', 0)} · "
                        f"score={cite.get('score', 0)}\n\n> {cite.get('snippet', '')}"
                    )


# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.title("SmartQA")
    if "token" not in st.session_state:
        st.subheader("登录")
        username = st.text_input("用户名", value="admin")
        password = st.text_input("密码", type="password", value="admin123")
        if st.button("登录"):
            if login(username, password):
                st.rerun()
    else:
        st.success("已登录")
        if st.button("退出"):
            st.session_state.pop("token")
            st.rerun()

        st.divider()
        st.subheader("知识库")
        kb_id = st.text_input("知识库 ID", value="kb_default")
        uploaded = st.file_uploader("上传文档", type=["pdf", "docx", "xlsx", "md", "txt"])
        if uploaded and st.button("开始上传"):
            upload(uploaded, kb_id)

        st.divider()
        st.session_state["use_rag"] = st.checkbox("启用 RAG", value=True)
        st.session_state["use_agent"] = st.checkbox("启用 Agent（工具调用）", value=False)

# ---------------- 主区 ----------------
st.header("SmartQA 智能问答")

if "token" not in st.session_state:
    st.info("请先在左侧登录")
    st.stop()

messages = st.session_state.setdefault("messages", [])
for msg in messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("输入你的问题，例如：公司年假几天？"):
    messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        ask_stream(
            prompt,
            use_rag=bool(st.session_state.get("use_rag", True)),
            use_agent=bool(st.session_state.get("use_agent", False)),
            session_id=st.session_state.get("session_id"),
        )
    if messages and messages[-1]["role"] == "user":
        messages.append({"role": "assistant", "content": "（见上方回答）"})
