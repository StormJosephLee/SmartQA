# 接口规范

> 统一前缀：`/api/v1`  
> 鉴权：除 `/auth/*`、`/health` 外，需 `Authorization: Bearer <token>`

## 通用约定
- 请求/响应均为 JSON，UTF-8
- 时间戳：ISO 8601
- 错误：`{"code": "BIZ_XXX", "message": "..."}`
- 流式：`text/event-stream`（SSE）

---

## 1. 健康检查
### `GET /health`
```json
{ "status": "ok", "app": "SmartQA", "env": "dev" }
```

---

## 2. 问答

### `POST /api/v1/chat`（非流式）
**请求**：
```json
{
  "session_id": "uuid",
  "user_id": "u_001",
  "message": "公司年假几天？",
  "stream": false,
  "use_rag": true,
  "use_agent": false
}
```
**响应 200**：
```json
{
  "message_id": "uuid",
  "session_id": "uuid",
  "answer": "根据《员工手册》第3.2条，年假为 5–15 天……",
  "citations": [
    {"source": "handbook.pdf", "page": 12, "score": 0.86, "snippet": "年假 5–15 天"}
  ],
  "tokens": 312,
  "latency_ms": 1240
}
```

### `POST /api/v1/chat/stream`（SSE）
事件序列：
```
event: citation
data: [{"source": "handbook.pdf", "page": 12, "score": 0.86}]

event: token
data: {"delta": "根据"}

event: token
data: {"delta": "员工"}

event: done
data: {"message_id": "uuid", "tokens": 312}
```

**错误码**：
| code | http | 含义 |
|---|---|---|
| `INPUT_FORBIDDEN` | 400 | 输入含敏感/注入内容 |
| `RATE_LIMIT` | 429 | 调用频率超限 |
| `LLM_UPSTREAM` | 502 | 模型服务异常 |
| `UNAUTHORIZED` | 401 | Token 缺失或失效 |
| `FORBIDDEN` | 403 | 无权访问该知识库 |

---

## 3. 知识库

### `POST /api/v1/knowledge/upload`
- `multipart/form-data: file`
- 限制：单文件 ≤ 50MB
- 响应：`KBDocument{ id, kb_id, title, source_uri, status, chunk_count, created_at }`

### `GET /api/v1/knowledge/list?page=1&size=20`
- 响应：`{ page, size, total, items: [KBDocument] }`

### `DELETE /api/v1/knowledge/{doc_id}`
- 响应：`{ "deleted": "doc_id" }`

---

## 4. 认证

### `POST /api/v1/auth/login`
**请求**：
```json
{ "username": "zhangsan", "password": "***" }
```
**响应**：
```json
{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 43200 }
```

### `GET /api/v1/auth/me`
- 响应：`{ id, name, role, dept }`

---

## 5. 管理

### `GET /api/v1/admin/stats`
```json
{ "users": 32, "sessions": 1280, "messages": 9421, "tokens_today": 312000 }
```

### `GET /api/v1/admin/config`
- 返回当前 LLM/Embedding 模型等运行期配置
