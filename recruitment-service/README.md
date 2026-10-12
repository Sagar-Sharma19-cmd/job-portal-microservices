# Recruitment Service

Runs on port 8004. It owns screenings and interviews; Application Service remains the only owner of application status. A decision therefore uses the shared `call_service()` client to request a status update from Application Service.

From the repository root, install requirements once, then run:

```bash
cd recruitment-service
python run.py
```

All API requests except `/health`, `/docs`, `/redoc`, and `/openapi.json` need `X-Internal-Token: t16-internal-secret` in development.

Endpoints: `POST`, `GET`, and `DELETE /api/v1/screenings`; `POST /api/v1/screenings/{id}/interviews`; `PATCH /api/v1/interviews/{id}`; `POST /api/v1/screenings/{id}/decision`; and `GET /internal/circuits`.

Run tests from this directory with `pytest`.
