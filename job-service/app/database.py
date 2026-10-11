from contextlib import contextmanager
from pathlib import Path
import sqlite3

from .config import DB_PATH


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.sql"


@contextmanager
def get_conn():
    """
    Open a SQLite connection with Row objects.

    The transaction is committed when the caller finishes successfully
    and rolled back automatically if an exception occurs.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create the service's tables and indexes if they do not exist."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    with get_conn() as conn:
        conn.executescript(
            SCHEMA_PATH.read_text(encoding="utf-8")
        )