from pathlib import Path
import os

from dotenv import load_dotenv

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parent

# Load the shared environment file; retain compatibility with the repo's example file.
load_dotenv(REPO_ROOT / ".env")
if not (REPO_ROOT / ".env").exists():
    load_dotenv(REPO_ROOT / ".env.example")

SERVICE_NAME = "notification-service"
PORT = int(os.getenv("PORT", "8005"))

DB_PATH = os.getenv(
    "DB_PATH",
    str(SERVICE_ROOT / "data" / "notification.db"),
)

INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "")