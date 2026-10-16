# 端到端数据流

> 跟着"一次问答"走一遍系统。

## 1. 时序图
```mermaid
sequenceDiagram
    autonumber
    participant U as 用户
    participant W as Web/Streamlit
    participant N as Nginx
    participant A as FastAPI
    participant S as ChatService
    participant G as Guardrails
    participant M as Memory
    participant AG as QAAgent
    participant R as HybridRetriever
    participant V as VectorStore
    participant L as LLM
    participant DB as PostgreSQL

    U->>W: 提问
    W->>N: POST /api/v1/chat/stream
    N->>A: 转发 + 注入 TraceId
    A->>S: chat_stream(req)
    S->>G: input_filter.check
    S->>M: load(session_id)
    M-->>S: history
    S->>AG: run(question, history)
    AG->>R: retrieve(question)
    R->>V: vector_search(qv, k=20)
    V-->>R: vec_hits
    R->>R: rrf_fuse + rerank
    R-->>AG: top_n=5
    AG->>L: stream(prompt)
    L-->>AG: tokens
    AG-->>S: answer + citations
    S->>G: output_filter.check
    S->>M: save(session, q, a)
    S->>DB: persist_message
    S-->>A: SSE events
    A-->>W: text/event-stream
    W-->>U: 渲染答案 + 引用
```

## 2. 关键路径上的数据形态
| 阶段 | 数据形态 |
|---|---|
| 客户端 | `ChatRequest{ session_id, message, stream }` |
| 检索 | `list[Chunk]{ id, content, score, meta }` |
| Prompt | `[{role:system, content}, {role:user, content:q}, {role:user, content:ctx}]` |
| 流式事件 | `event: token` / `event: citation` / `event: done` |
| 持久化 | `messages{ role, content, citations(json), tokens, latency }` |

## 3. 失败路径
| 失败点 | 兜底策略 |
|---|---|
| LLM 超时 | 重试 2 次 → 切更小模型 → 报错 |
| 检索为空 | 直接 LLM 回答，并标注"无引用" |
| 工具异常 | 跳过该步，标注失败原因继续 |
| Redis 挂 | 退化到无记忆模式（不阻断） |
| PG 写失败 | 异步重试 + 死信队列 |
