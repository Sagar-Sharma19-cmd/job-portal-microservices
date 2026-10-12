# Candidate Service

Runs on port 8001 and owns candidate profiles and skills. The service does not read another service's database or make HTTP calls.

From the repository root, install requirements once, then run:

```bash
cd candidate-service
python run.py
```

All API requests except `/health`, `/docs`, `/redoc`, and `/openapi.json` need `X-Internal-Token: t16-internal-secret` in development.

Endpoints: `POST /api/v1/candidates`, `GET /api/v1/candidates`, `GET /api/v1/candidates/{id}`, `PATCH /api/v1/candidates/{id}`, and `GET /api/v1/candidates/{id}/eligibility`.

Run tests from this directory with `pytest`.
