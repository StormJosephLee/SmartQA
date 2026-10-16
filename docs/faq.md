# 常见问题

### Q1: `pip install` 报错 `pg_config` not found
**A**: 需要安装 PostgreSQL 客户端开发库：
```bash
# macOS
brew install postgresql
# Ubuntu
sudo apt-get install libpq-dev
```

### Q2: Langfuse 集成失败
**A**: 检查 `.env` 中 `LANGFUSE_*` 是否配齐，且 `langfuse-server` 容器已起。
短期可在 `app/observability/tracing.py` 把 init 失败改为 warn，不影响主流程。

### Q3: 流式接口无输出
**A**: 
1. 确认 Nginx 关闭了 `proxy_buffering` 与 `proxy_cache`
2. 客户端使用 `EventSource` 或 `fetch + ReadableStream`

### Q4: pgvector 向量维度不匹配
**A**: `config/model.yaml` 的 `embedding.dim` 必须与 `init.sql` 中 `vector(N)` 一致。

### Q5: 检索召回为空
**A**:
1. 确认 `documents.status = 'ready'`
2. 跑 `python scripts/ingest_docs.py --path ./docs` 重新入库
3. 用 `psql` 直接查 `chunks` 看数据

### Q6: 怎么改 Prompt 不影响线上
**A**: 把 `config/prompts/*.yaml` 纳入版本；AB 测试通过 `model_config.yaml` 切换模板名。

### Q7: 如何导出某用户的所有对话（合规）
**A**: 走 `/api/v1/admin/export?user_id=...`（待实现），导出后给用户。
