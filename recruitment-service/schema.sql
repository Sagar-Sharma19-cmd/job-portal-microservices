CREATE TABLE IF NOT EXISTS screenings (id INTEGER PRIMARY KEY AUTOINCREMENT, application_id INTEGER NOT NULL UNIQUE, job_id INTEGER NOT NULL, candidate_id INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS interviews (id INTEGER PRIMARY KEY AUTOINCREMENT, screening_id INTEGER NOT NULL REFERENCES screenings(id), round INTEGER NOT NULL, scheduled_at TEXT NOT NULL, result TEXT, feedback TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_screenings_job_id ON screenings(job_id);
