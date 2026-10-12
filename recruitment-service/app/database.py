import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app.config import DB_PATH
@contextmanager
def get_conn():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; conn.execute("PRAGMA foreign_keys = ON")
    try: yield conn; conn.commit()
    except Exception: conn.rollback(); raise
    finally: conn.close()
def init_db():
    with get_conn() as conn: conn.executescript((Path(__file__).parent.parent / "schema.sql").read_text(encoding="utf-8"))
