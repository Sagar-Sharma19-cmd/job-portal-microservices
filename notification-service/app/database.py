from contextlib import contextmanager
from pathlib import Path
import sqlite3

from app.config import DB_PATH

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.sql"


@contextmanager
def get_conn():
    """Open one database connection and safely finish its transaction."""
    connection = None

    try:
        # Create the database directory when running the service for the first time.
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row

        yield connection
        connection.commit()
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()


def init_db():
    """Create this service's tables and indexes if they do not exist."""
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with get_conn() as connection:
        connection.executescript(schema)