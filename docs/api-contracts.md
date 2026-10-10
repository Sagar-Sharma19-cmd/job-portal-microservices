# API Contracts — Team 16 Job Portal

**Status: DRAFT v0.1** — to be confirmed at the kickoff call, then frozen.
After freezing, any change needs a PR to this file approved by the lead.

All services code against this document. If your code and this document disagree, this document wins.

---

## 1. Common conventions (every service)

### Ports and service names

| Service name (used in registry) | Port | Base path |
| --- | --- | --- |
| `api-gateway` | 8000 | `/api/v1/...`, `/api/v2/...`, `/gateway/...` |
| `service-registry` | 8761 | `/registry/...` |
| `candidate-service` | 8001 | `/api/v1/candidates` |
| `job-service` | 8002, 8012 | `/api/v1/employers`, `/api/v1/jobs`, `/api/v2/jobs` |
| `application-service` | 8003 | `/api/v1/applications`, `/api/v1/sagas` |
| `recruitment-service` | 8004 | `/api/v1/screenings`, `/api/v1/interviews` |
| `notification-service` | 8005 | `/api/v1/notifications` |

### Headers

| Header | Sent by | Purpose |
| --- | --- | --- |
| `X-API-Key` | Client → Gateway | Auth placeholder. Gateway returns 401 if missing or wrong |
| `X-Internal-Token` | Gateway → services, service → service | Proves the call came through our system. Services return 401 without it |
| `X-Request-ID` | Gateway creates it; every service forwards it | Traces one request across services and logs |
| `Content-Type: application/json` | Everyone | All bodies are JSON |

`/health` and `/docs` do not need `X-Internal-Token`.

### Data formats

- IDs: integers, assigned by the owning service's database.
- Timestamps: ISO 8601 in UTC, e.g. `2026-10-07T10:30:00Z`.
- Money: integers in rupees (`600000`), with `currency: "INR"`.
- Enums: UPPER_SNAKE_CASE strings (`OPEN`, `SUBMITTED`).
- Field names: snake_case.

### Error format (all services, all errors)

```json
{
  "error": {
    "code": "JOB_FULL",
    "message": "Job 7 has no application slots left",
    "request_id": "c1f2a9e0-...",
    "details": {}
  }
}
```

### Status codes

| Code | When |
| --- | --- |
| 200 | Successful read or update |
| 201 | Resource created |
| 204 | Deleted or cancelled, no body |
| 400 | Validation failed (`VALIDATION_ERROR`) |
| 401 | Missing or wrong `X-API-Key` / `X-Internal-Token` (`UNAUTHORIZED`) |
| 404 | Resource not found (`<THING>_NOT_FOUND`) |
| 409 | Business conflict: duplicate, job full, invalid status change |
| 502 | A dependency returned something invalid (`BAD_UPSTREAM_RESPONSE`) |
| 503 | A dependency is down or its circuit is open (`<SERVICE>_UNAVAILABLE`) |
| 504 | A dependency timed out (`<SERVICE>_TIMEOUT`) |

> FastAPI returns 422 for validation errors by default. Each service must override this to return 400 in
> our error format (the service template will do this for you).

### Endpoints every service has

**`GET /health`** → 200

```json
{ "service": "job-service", "instance_id": "job-service-8002", "status": "UP", "db": "UP" }
```

**`GET /internal/circuits`** (only services that call others: gateway, application, recruitment) → 200

```json
{ "job-service": { "state": "CLOSED", "failures": 0, "opened_at": null } }
```

---

## 2. Service Registry (`service-registry`, 8761) — owner: Sai

| Method | Path | Purpose | Success | Errors |
| --- | --- | --- | --- | --- |
| POST | `/registry/register` | Register an instance | 201 | 400 |
| PUT | `/registry/heartbeat/{instance_id}` | Keep instance alive | 200 | 404 if expired (service must re-register) |
| DELETE | `/registry/instances/{instance_id}` | Deregister on shutdown | 204 | — |
| GET | `/registry/services` | All services and instances | 200 | — |
| GET | `/registry/services/{service_name}` | Healthy instances of one service | 200 | 404 `SERVICE_NOT_FOUND` if none alive |

Register request:

```json
{ "service_name": "job-service", "instance_id": "job-service-8002", "host": "127.0.0.1", "port": 8002 }
```

Lookup response:

```json
{
  "service_name": "job-service",
  "instances": [
    { "instance_id": "job-service-8002", "host": "127.0.0.1", "port": 8002, "last_heartbeat": "2026-10-07T10:30:05Z" },
    { "instance_id": "job-service-8012", "host": "127.0.0.1", "port": 8012, "last_heartbeat": "2026-10-07T10:30:07Z" }
  ]
}
```

Rules: heartbeat every 10 s; an instance with no heartbeat for 30 s is removed.

---

## 3. Candidate Service (`candidate-service`, 8001) — owner: Saloni

| Method | Path | Purpose | Success | Errors |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/candidates` | Register a candidate | 201 | 400, 409 `EMAIL_ALREADY_EXISTS` |
| GET | `/api/v1/candidates` | List; filter `?skill=Java` | 200 | — |
| GET | `/api/v1/candidates/{id}` | Get one | 200 | 404 `CANDIDATE_NOT_FOUND` |
| PATCH | `/api/v1/candidates/{id}` | Update some fields | 200 | 400, 404 |
| GET | `/api/v1/candidates/{id}/eligibility` | Is the profile complete enough to apply? | 200 | 404 |

Create request:

```json
{
  "name": "Ananya Rao",
  "email": "ananya@example.com",
  "phone": "9876543210",
  "experience_years": 1,
  "skills": ["Java", "SQL"],
  "resume_url": "https://example.com/resume/ananya.pdf"
}
```

Candidate response:

```json
{
  "id": 12,
  "name": "Ananya Rao",
  "email": "ananya@example.com",
  "phone": "9876543210",
  "experience_years": 1,
  "skills": ["Java", "SQL"],
  "resume_url": "https://example.com/resume/ananya.pdf",
  "created_at": "2026-10-07T10:30:00Z"
}
```

Eligibility response (eligible = has `resume_url` and at least one skill):

```json
{ "candidate_id": 12, "eligible": false, "missing": ["resume_url"] }
```

---

## 4. Job Service (`job-service`, 8002 / 8012) — owner: Sana

### Employers

| Method | Path | Purpose | Success | Errors |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/employers` | Create employer `{ "name", "location" }` | 201 | 400 |
| GET | `/api/v1/employers/{id}` | Get employer | 200 | 404 `EMPLOYER_NOT_FOUND` |

### Jobs

| Method | Path | Purpose | Success | Errors |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/jobs` | Create job (response in v1 shape) | 201 | 400, 404 `EMPLOYER_NOT_FOUND` |
| GET | `/api/v1/jobs` | List; filter `?status=OPEN&skill=Java` (v1 shape) | 200 | — |
| GET | `/api/v1/jobs/{id}` | Get job (v1 shape) | 200 | 404 `JOB_NOT_FOUND` |
| GET | `/api/v2/jobs` | List (v2 shape) | 200 | — |
| GET | `/api/v2/jobs/{id}` | Get job (v2 shape) | 200 | 404 |
| PATCH | `/api/v1/jobs/{id}` | Update, e.g. `{ "status": "CLOSED" }` | 200 | 400, 404 |

Create request:

```json
{
  "employer_id": 3,
  "title": "Java Developer",
  "location": "Bengaluru",
  "salary_min": 600000,
  "salary_max": 800000,
  "currency": "INR",
  "skills": ["Java", "SQL"],
  "max_applications": 5,
  "deadline": "2026-11-30"
}
```

**v1 response** (original, flat):

```json
{ "id": 7, "title": "Java Developer", "company": "Infosys", "location": "Bengaluru", "salary": "6-8 LPA", "skills": "Java, SQL", "status": "OPEN" }
```

v1 responses also carry the header `Deprecation: true`.

**v2 response** (structured):

```json
{
  "id": 7,
  "title": "Java Developer",
  "employer": { "id": 3, "name": "Infosys", "location": "Bengaluru" },
  "location": "Bengaluru",
  "salary": { "min": 600000, "max": 800000, "currency": "INR" },
  "skills": ["Java", "SQL"],
  "slots_remaining": 4,
  "status": "OPEN",
  "deadline": "2026-11-30"
}
```

Job status: `OPEN`, `CLOSED`. A job with no slots left stays `OPEN` but rejects reservations.

### Slot reservations (saga participant)

| Method | Path | Purpose | Success | Errors |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/jobs/{id}/reservations` | Reserve one slot for an application | 201 new, 200 if this `application_id` already reserved | 404, 409 `JOB_FULL`, 409 `JOB_CLOSED` |
| DELETE | `/api/v1/jobs/{id}/reservations/{application_id}` | **Compensation:** release the slot | 204 (also 204 if already released or never existed) | — |

Reserve request: `{ "application_id": 41 }`

Reserve response:

```json
{ "job_id": 7, "application_id": 41, "status": "RESERVED", "slots_remaining": 3 }
```

Both operations are **idempotent**: calling them twice with the same `application_id` has the same effect
as calling once.

---

## 5. Application Service (`application-service`, 8003) — owner: Rishu

| Method | Path | Purpose | Success | Errors |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/applications` | Apply for a job (**starts the saga**) | 201 | see below |
| GET | `/api/v1/applications/{id}` | Get one | 200 | 404 `APPLICATION_NOT_FOUND` |
| GET | `/api/v1/applications` | List; filter `?candidate_id=&job_id=&status=` | 200 | — |
| PATCH | `/api/v1/applications/{id}/status` | Change status (used by Recruitment) | 200 | 400, 404, 409 `INVALID_STATUS_TRANSITION` |
| GET | `/api/v1/sagas/{saga_id}` | Saga log for the demo | 200 | 404 `SAGA_NOT_FOUND` |

Apply request: `{ "candidate_id": 12, "job_id": 7 }`

Apply success (201):

```json
{ "id": 41, "candidate_id": 12, "job_id": 7, "status": "SUBMITTED", "saga_id": "saga-41", "created_at": "2026-10-07T10:31:00Z" }
```

Apply failures (application is kept as `CANCELLED` so the saga is visible):

| Situation | Status | `error.code` |
| --- | --- | --- |
| Same candidate already applied to this job | 409 | `DUPLICATE_APPLICATION` |
| Candidate not found | 404 | `CANDIDATE_NOT_FOUND` |
| Candidate profile incomplete | 409 | `CANDIDATE_NOT_ELIGIBLE` |
| Job full or closed | 409 | `JOB_FULL` / `JOB_CLOSED` |
| Job, Candidate or Recruitment down / circuit open | 503 | `JOB_SERVICE_UNAVAILABLE` etc. |

Failure body includes the saga so it can be inspected:

```json
{
  "error": {
    "code": "RECRUITMENT_SERVICE_UNAVAILABLE",
    "message": "Application cancelled; slot released",
    "request_id": "c1f2a9e0-...",
    "details": { "application_id": 42, "saga_id": "saga-42", "status": "CANCELLED" }
  }
}
```

Status change request: `{ "status": "SHORTLISTED", "reason": "Strong SQL skills" }`

**Application status machine** (only Application Service changes status):

| From | Allowed to |
| --- | --- |
| `PENDING` | `SUBMITTED`, `COMPENSATING` |
| `COMPENSATING` | `CANCELLED` |
| `SUBMITTED` | `SHORTLISTED`, `REJECTED` |
| `SHORTLISTED` | `INTERVIEW`, `REJECTED` |
| `INTERVIEW` | `OFFERED`, `REJECTED` |
| `OFFERED`, `REJECTED`, `CANCELLED` | none (final) |

Saga response:

```json
{
  "saga_id": "saga-42",
  "application_id": 42,
  "status": "COMPENSATED",
  "steps": [
    { "step": "CREATE_APPLICATION", "status": "DONE", "at": "2026-10-07T10:32:00Z" },
    { "step": "RESERVE_JOB_SLOT", "status": "DONE", "at": "2026-10-07T10:32:00Z" },
    { "step": "CREATE_SCREENING", "status": "FAILED", "at": "2026-10-07T10:32:02Z", "error": "RECRUITMENT_SERVICE_UNAVAILABLE" },
    { "step": "RELEASE_JOB_SLOT", "status": "DONE", "at": "2026-10-07T10:32:02Z" },
    { "step": "CANCEL_APPLICATION", "status": "DONE", "at": "2026-10-07T10:32:02Z" }
  ]
}
```

Saga status: `STARTED`, `COMPLETED`, `COMPENSATING`, `COMPENSATED`, `COMPENSATION_PENDING`.

---

## 6. Recruitment Service (`recruitment-service`, 8004) — owner: Saloni

| Method | Path | Purpose | Success | Errors |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/screenings` | Create screening for an application (saga step) | 201 new, 200 if one already exists for this `application_id` | 400 |
| DELETE | `/api/v1/screenings/{application_id}` | **Compensation:** cancel screening | 204 (also 204 if already cancelled / not found) | — |
| GET | `/api/v1/screenings/{id}` | Get screening with its interviews | 200 | 404 `SCREENING_NOT_FOUND` |
| GET | `/api/v1/screenings` | List; filter `?job_id=&status=` | 200 | — |
| POST | `/api/v1/screenings/{id}/interviews` | Schedule interview round | 201 | 400, 404 |
| PATCH | `/api/v1/interviews/{id}` | Record result `{ "result": "PASS", "feedback": "..." }` | 200 | 400, 404 |
| POST | `/api/v1/screenings/{id}/decision` | Recruiter decision → updates Application status | 200 | 400, 404, 409, 503 `APPLICATION_SERVICE_UNAVAILABLE` |

Create screening request: `{ "application_id": 41, "job_id": 7, "candidate_id": 12 }`

Screening response:

```json
{ "id": 9, "application_id": 41, "job_id": 7, "candidate_id": 12, "status": "ACTIVE", "interviews": [], "created_at": "2026-10-07T10:31:00Z" }
```

Screening status: `ACTIVE`, `CANCELLED`, `CLOSED`.

Interview request: `{ "round": 1, "scheduled_at": "2026-10-10T09:30:00Z" }`

Decision request: `{ "decision": "SHORTLISTED", "reason": "Strong SQL skills" }`
Allowed decisions: `SHORTLISTED`, `INTERVIEW`, `OFFERED`, `REJECTED`. Recruitment forwards this to
`PATCH /api/v1/applications/{application_id}/status` and returns Application's 409 if the transition is not allowed.

---

## 7. Notification Service (`notification-service`, 8005) — owner: Sana

| Method | Path | Purpose | Success | Errors |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/notifications` | Store and "send" a notification (logged, no real email) | 201 | 400 |
| GET | `/api/v1/notifications` | List; filter `?recipient_id=` | 200 | — |

Request:

```json
{ "recipient_id": 12, "type": "APPLICATION_SUBMITTED", "message": "Your application for Java Developer was submitted." }
```

Types: `APPLICATION_SUBMITTED`, `APPLICATION_CANCELLED`, `STATUS_CHANGED`, `INTERVIEW_SCHEDULED`.

Notification is **not** a saga step. If it is down, Application queues the message and retries.

---

## 8. API Gateway (`api-gateway`, 8000) — owner: Sai

| Client path | Routed to |
| --- | --- |
| `/api/{v1,v2}/candidates/**` | `candidate-service` |
| `/api/{v1,v2}/employers/**`, `/api/{v1,v2}/jobs/**` | `job-service` |
| `/api/v1/applications/**`, `/api/v1/sagas/**` | `application-service` |
| `/api/v1/screenings/**`, `/api/v1/interviews/**` | `recruitment-service` |
| `/api/v1/notifications/**` | `notification-service` |

Gateway's own endpoints: `GET /gateway/health` (status of every service), `GET /gateway/circuits`.

Gateway errors: 401 bad API key, 404 `ROUTE_NOT_FOUND`, 503 no healthy instance or circuit open
(with `Retry-After` header), 504 timeout.

---

## 9. Who calls whom

| Caller | Receiver | Call | Timeout | Breaker | Fallback |
| --- | --- | --- | --- | --- | --- |
| Gateway | All services | Forward client request | 3 s | Per service | 503 + `Retry-After` |
| Application | Candidate | `GET /candidates/{id}/eligibility` | 2 s | Yes | 503, saga not started |
| Application | Job | `POST` / `DELETE` reservations | 2 s | Yes | 503 before saga; retry for compensation |
| Application | Recruitment | `POST` / `DELETE` screenings | 2 s | Yes | Compensate earlier steps |
| Application | Notification | `POST /notifications` | 2 s | Yes | Queue and retry |
| Recruitment | Application | `PATCH /applications/{id}/status` | 2 s | Yes | 503 to recruiter |

---

## Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | 2026-10-06 | First draft |
