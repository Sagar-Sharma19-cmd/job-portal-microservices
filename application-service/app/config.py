import os
from pathlib import Path

from dotenv import load_dotenv


SERVICE_NAME = "application-service"
PORT = int(os.getenv("APPLICATION_SERVICE_PORT", "8003"))

SERVICE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SERVICE_DIR.parent

load_dotenv(ROOT_DIR / ".env")

INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "t16-internal-secret")

DEFAULT_DB_PATH = SERVICE_DIR / "data" / "application.db"
DB_PATH = os.getenv("DB_PATH", str(DEFAULT_DB_PATH))