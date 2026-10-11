# Notification Service

Team 16's Notification Service for the Job Portal & Recruitment System.

## Responsibilities

- Store candidate notifications in its own SQLite database.
- Print a log line to simulate sending each notification.
- List notifications, optionally filtered by recipient.

No real emails are sent. This service does not call other services and is
not part of the application saga.

## Requirements

Python 3.11+ and the shared virtual environment with:

- FastAPI
- Uvicorn
- sqlite3 (Python standard library)
- requests
- python-dotenv
- pytest

## Configuration

The service reads shared configuration from the repository-root `.env`.
If that file is absent, it also supports `.env.example`.

Relevant settings:

- `INTERNAL_TOKEN`: internal API authentication token.
- `PORT`: defaults to `8005`.
- `DB_PATH`: optional database path override.

The default database is `notification-service/data/notification.db`.

## Run

From the repository root, activate the shared virtual environment, then:

```bash
cd notification-service
python run.py