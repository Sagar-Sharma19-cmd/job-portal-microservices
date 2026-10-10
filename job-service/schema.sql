CREATE TABLE IF NOT EXISTS employers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id INTEGER NOT NULL REFERENCES employers(id),
    title TEXT NOT NULL,
    location TEXT NOT NULL,
    salary_min INTEGER NOT NULL,
    salary_max INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    skills TEXT NOT NULL,
    max_applications INTEGER NOT NULL,
    status TEXT NOT NULL,
    deadline TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS slot_reservations (
    application_id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status
ON jobs(status);

CREATE INDEX IF NOT EXISTS idx_slot_reservations_job_id
ON slot_reservations(job_id);