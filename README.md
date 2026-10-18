# SmartQA

企业级智能问答助手：RAG + Agent，基于企业私有知识给出带引用的答案。

- 规范单一事实源：[`spec/spec.md`](./spec/spec.md)
- 文档中心：[`docs/README.md`](./docs/README.md)

## 技术栈

Python 3.11+ · FastAPI · LangGraph · PostgreSQL(pgvector) · Redis · Streamlit · Langfuse（可选）

## 目录结构（顶层多包）

| 目录 | 职责 |
|---|---|
| `api/` | 协议适配、参数校验、错误码 |
| `core/` | 配置、日志脱敏、错误码、JWT、中间件 |
| `llm/` | LLM / Embedding / Rerank 的 OpenAI 兼容适配层 |
| `services/` | 业务流程编排与事务边界 |
| `agents/` | LangGraph 状态机、节点、工具 |
| `rag/` | 解析、分块、向量库、混合检索 |
| `memory/` | 短期会话记忆（Redis，可降级） |
| `guardrails/` | 输入/输出安全 |
| `observability/` | Trace 埋点 |
| `db/` | ORM 模型与会话 |
| `schemas/` | Pydantic DTO |
| `config/` | settings.yaml 与 prompts |
| `scripts/` | init_db / ingest |
| `ui/` | Streamlit 界面 |
| `tests/` | 单元测试 |

## 快速开始

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # 至少填 LLM_API_KEY / EMBEDDING_API_KEY
docker compose up -d postgres redis
python scripts/init_db.py

make run-api                  # http://localhost:8000/docs
make run-ui                   # http://localhost:8501
# 停止：make stop（保留 PG/Redis）或 make stop-all（一并停掉）
```

> `.env` 中统一使用 `${VAR:-默认值}` 形式，未设置时回落到默认值；
> 生效优先级为 **OS 环境变量 > `.env` 文件 > 代码默认值**，因此密钥无需写进 `.env`。

## 常用命令

| 目的 | 命令 |
|---|---|
| 起 API / UI | `make run-api` / `make run-ui` |
| 停止服务 | `make stop` / `make stop-all` |
| 初始化数据库 | `make init-db` |
| 批量入库 `data/raw/` | `make ingest` |
| 跑测试 | `make test` |
| 格式化 | `make format` |

## 无 API Key 也能跑通（离线冒烟）

`scripts/mock_llm.py` 提供一个 OpenAI 兼容的假模型服务（`/v1/chat/completions` 含流式、`/v1/embeddings`）：

```bash
.venv/bin/python scripts/mock_llm.py --port 8100
LLM_BASE_URL=http://localhost:8100/v1 EMBEDDING_BASE_URL=http://localhost:8100/v1 \
LLM_API_KEY=test EMBEDDING_API_KEY=test .venv/bin/uvicorn main:app --port 8000
```

> 注意：本机若已有 PostgreSQL 占用 5432，可复用现有实例（需先建库并 `CREATE EXTENSION vector`），
> 或把 `docker-compose.yml` 的端口映射改为 `5433:5432` 并同步 `.env` 的 `POSTGRES_PORT`。

## 接口一览

统一前缀 `/api/v1`，鉴权 `Authorization: Bearer <token>`。

- `POST /auth/login`、`GET /auth/me`
- `POST /chat`、`POST /chat/stream`（SSE：`citation`/`token`/`done`）
- `POST /knowledge/upload`、`GET /knowledge/list`、`DELETE /knowledge/{doc_id}`
- `GET /admin/stats`、`GET /admin/config`
- `GET /health`

## 当前进度

- [x] P0 骨架
- [x] P1 RAG
- [x] P2 Agent
- [ ] P3 工程化（JWT/RBAC 强化、Langfuse、评估集）
- [ ] P4 集成（IM、多租户）
