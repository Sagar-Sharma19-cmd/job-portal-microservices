from pathlib import Path
import os
from dotenv import load_dotenv

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]

# .env is in the repository root, one level above job_service/
load_dotenv(REPO_ROOT / ".env.example")

SERVICE_NAME = "job-service"

PORT = int(os.getenv("PORT", "8002"))

DB_PATH = os.getenv(
    "DB_PATH",
    str(SERVICE_ROOT / "data" / "job.db"),
)

INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "")