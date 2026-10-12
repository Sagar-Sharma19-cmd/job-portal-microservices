import os
from pathlib import Path

from dotenv import load_dotenv

SERVICE_NAME = "candidate-service"
SERVICE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(SERVICE_DIR.parent / ".env")
PORT = int(os.getenv("CANDIDATE_PORT", "8001"))
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "t16-internal-secret")
DB_PATH = os.getenv("DB_PATH", str(SERVICE_DIR / "data" / "candidate.db"))
