CREATE TABLE IF NOT EXISTS candidates (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, phone TEXT, experience_years INTEGER NOT NULL DEFAULT 0, resume_url TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidate_skills (candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE, skill TEXT NOT NULL, PRIMARY KEY(candidate_id, skill));
CREATE INDEX IF NOT EXISTS idx_candidate_skills_skill ON candidate_skills(skill);
