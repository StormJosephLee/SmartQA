.PHONY: help install init-db run-api run-ui stop stop-all ingest test format compose-up compose-down

help:
	@echo "install   安装依赖"
	@echo "init-db   初始化数据库与 pgvector 扩展"
	@echo "run-api   启动 API (http://localhost:8000/docs)"
	@echo "run-ui    启动 Streamlit (http://localhost:8501)"
	@echo "stop      停止 API 与 UI（保留 PG/Redis 容器）"
	@echo "stop-all  停止 API/UI 并关闭 PG/Redis 容器"
	@echo "ingest    批量入库 data/raw 下的文档"
	@echo "test      运行单元测试"
	@echo "format    ruff 格式化与修复"
	@echo "compose-up/compose-down  启停 PG/Redis"

install:
	pip install -r requirements-dev.txt

init-db:
	python scripts/init_db.py

run-api:
	uvicorn main:app --reload --port 8000

run-ui:
	streamlit run ui/streamlit_app.py --server.port 8501

# 说明：模式里的 [a] 是常见的自匹配规避写法，避免 pkill -f 把执行本命令的 shell 自己也杀掉。
# 行首的 - 表示即使没有匹配到进程也不中断。
stop:
	-pkill -f "uvicorn main:[a]pp"
	-pkill -f "streamlit ru[n]"
	-pkill -f "mock_ll[m].py"
	@echo "已停止 API / UI（PG/Redis 仍在运行，用 make stop-all 一并停止）"

stop-all: stop compose-down
	@echo "已停止全部服务"

ingest:
	python scripts/ingest.py

test:
	pytest -q

format:
	ruff check . --fix
	ruff format .

compose-up:
	docker compose up -d postgres redis

compose-down:
	docker compose down
