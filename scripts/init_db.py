#!/usr/bin/env python3
"""python scripts/init_db.py —— 初始化 PG/扩展/表与默认数据。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.logging import setup_logging  # noqa: E402
from db.init_db import init_db  # noqa: E402

if __name__ == "__main__":
    setup_logging()
    init_db()
    print("OK: database ready")
