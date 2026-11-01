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


_MEMORY_KINDS = ("fact", "profile", "preference", "instruction")
_KIND_LABEL = {
    "fact": "事实",
    "profile": "画像",
    "preference": "偏好",
    "instruction": "指令",
}


def _api(method: str, path: str, **kw: Any):
    """统一 API 调用；失败时在侧边栏提示并返回 None。"""
    try:
        resp = httpx.request(method, f"{API_BASE}{path}", headers=_headers(), timeout=15, **kw)
    except Exception as exc:  # noqa: BLE001
        st.sidebar.error(f"无法连接 API：{exc}")
        return None
    if resp.status_code >= 400:
        st.sidebar.error(f"操作失败 {resp.status_code}：{resp.text[:200]}")
        return None
    return resp


def render_memory_panel() -> None:
    """侧边栏「记忆」面板：查看 / 添加 / 删除长期记忆（memory_design.md#6）。"""
    resp = _api("GET", "/api/v1/memory")
    if resp is None:
        return
    body = resp.json()
    if not body.get("enabled", True):
        st.caption("⚠️ 服务端已关闭长期记忆（memory.long_term_enabled=false）")

    items = body.get("items", [])
    st.caption(f"共 {len(items)} 条")
    if not items:
        st.caption("暂无记忆。对话中提到身份、偏好等信息后会自动沉淀。")

    for item in items:
        left, right = st.columns([0.84, 0.16])
        with left:
            kind = _KIND_LABEL.get(item["kind"], item["kind"])
            pin = "📌 " if item.get("pinned") else ""
            st.markdown(f"{pin}[{kind}] {item['content']}")
            updated = str(item.get("updated_at") or "")[:16].replace("T", " ")
            st.caption(f"命中 {item.get('hit_count', 0)} 次 · {updated}")
        with right:
            if st.button("🗑", key=f"mem_del_{item['id']}", help="删除这条记忆"):
                if _api("DELETE", f"/api/v1/memory/{item['id']}") is not None:
                    st.toast("已删除该条记忆")
                    st.rerun()

    with st.form("memory_add", clear_on_submit=True):
        st.text_input("新记忆内容", key="mem_new_content", max_chars=500)
        st.selectbox("类别", _MEMORY_KINDS, key="mem_new_kind")
        st.checkbox("置顶（永不被淘汰）", key="mem_new_pinned")
        if st.form_submit_button("添加记忆"):
            content = (st.session_state.get("mem_new_content") or "").strip()
            if not content:
                st.warning("内容不能为空")
            elif (
                _api(
                    "POST",
                    "/api/v1/memory",
                    json={
                        "content": content,
                        "kind": st.session_state.get("mem_new_kind", "fact"),
                        "pinned": bool(st.session_state.get("mem_new_pinned")),
                    },
                )
                is not None
            ):
                st.toast("已添加记忆")
                st.rerun()

    if st.checkbox("确认清空全部记忆", key="mem_clear_confirm"):
        if st.button("🚨 清空", type="primary"):
            cleared = _api("DELETE", "/api/v1/memory")
            if cleared is not None:
                st.toast(f"已清空 {cleared.json().get('cleared', 0)} 条")
                st.session_state.pop("mem_clear_confirm", None)
                st.rerun()


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

        st.divider()
        # 默认折叠：仅在打开时才请求 API，避免每次 rerun 都拉取
        if st.toggle("🧠 长期记忆", value=False, key="show_memory"):
            render_memory_panel()

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
