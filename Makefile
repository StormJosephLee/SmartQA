.PHONY: help install init-db run-api run-ui ingest test format compose-up compose-down

help:
	@echo "install   安装依赖"
	@echo "init-db   初始化数据库与 pgvector 扩展"
	@echo "run-api   启动 API (http://localhost:8000/docs)"
	@echo "run-ui    启动 Streamlit (http://localhost:8501)"
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
