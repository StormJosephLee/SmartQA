#!/usr/bin/env python3
"""python scripts/ingest.py —— 批量入库 data/raw 下的文档到默认知识库。"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.logging import setup_logging  # noqa: E402
from db.models import Document  # noqa: E402
from db.session import SessionLocal  # noqa: E402
from rag.pipeline import ingest_document  # noqa: E402

RAW_DIR = ROOT / "data" / "raw"
DEFAULT_KB_ID = "kb_default"


async def main() -> int:
    if not RAW_DIR.exists():
        print(f"目录不存在: {RAW_DIR}")
        return 1
    files = [p for p in RAW_DIR.rglob("*") if p.is_file() and not p.name.startswith(".")]
    if not files:
        print("没有待入库文件")
        return 0
    ok = 0
    with SessionLocal() as session:
        for path in files:
            doc = Document(kb_id=DEFAULT_KB_ID, title=path.name, source_uri=str(path), status="pending")
            session.add(doc)
            session.commit()
            try:
                count = await ingest_document(session, doc, path)
                print(f"[OK] {path.name} chunks={count}")
                ok += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[FAIL] {path.name}: {exc}")
    print(f"done: {ok}/{len(files)}")
    return 0


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(asyncio.run(main()))
