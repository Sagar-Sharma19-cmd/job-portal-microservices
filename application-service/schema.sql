CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    status_reason TEXT,
    saga_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sagas (
    saga_id TEXT PRIMARY KEY,
    application_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saga_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    saga_id TEXT NOT NULL REFERENCES sagas(saga_id),
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_applications_candidate
ON applications(candidate_id);

CREATE INDEX IF NOT EXISTS idx_applications_job
ON applications(job_id);

CREATE INDEX IF NOT EXISTS idx_saga_steps_saga
ON saga_steps(saga_id);