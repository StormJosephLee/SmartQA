# 新人上手指南

> 目标：30 分钟内让一个新同学把代码跑起来，并理解整体结构。

## 1. 准备环境（5 min）
- Python 3.11+
- Docker Desktop
- 任意 LLM 的 API Key（OpenAI 兼容协议即可）

## 2. 拉代码与初始化（10 min）
```bash
git clone <repo> && cd SmartQA
python3.11 -m venv .venv && source .venv/bin/activate
cp .env.example .env
# 编辑 .env，至少填 LLM_API_KEY
pip install -r requirements.txt
docker compose up -d postgres redis
python scripts/init_db.py
```

## 3. 启动并验证（5 min）
```bash
# 终端 1
make run-api
# 终端 2
make run-ui
```
访问：
- API 文档：http://localhost:8000/docs
- 聊天界面：http://localhost:8501

## 4. 5 分钟读懂架构
- **core/** 负责配置、日志、错误码、JWT 等横切能力
- **llm/** 负责把各家模型统一成 OpenAI 兼容调用
- **api/** 只做协议适配 → 业务全在 **services/**
- **rag/** 负责"找到相关知识"
- **agents/** 负责"决定怎么用知识"
- **memory/** 负责"记住对话"
- **guardrails/** 负责"输入输出安全"
- **observability/** 负责"看得到全过程"
- **ui/** 是 Streamlit 界面；**db/** **schemas/** 分别是 ORM 与 DTO

详细见 [architecture.md](./architecture.md)。

## 5. 第一个 PR 建议
- 修一个 docs/ 里的错别字（熟悉 Git Flow）
- 给某个 service 加一个单元测试（熟悉测试）
- 把 .env.example 里的注释补全（熟悉配置）

## 6. 常用命令速查
| 目的 | 命令 |
|---|---|
| 起服务 | `make run-api` / `make run-ui` |
| 入库文档 | `make ingest`（批量）或 `POST /api/v1/knowledge/upload`（单文件） |
| 跑测试 | `make test` |
| 格式化 | `make format` |
| 初始化 DB | `make init-db` |

## 7. 求助
- 看 [faq.md](./faq.md)
- 群里 @架构组
- 提 issue 选 `question` 模板
