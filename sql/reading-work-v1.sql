CREATE TABLE user_literature_work_progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    work_id TEXT NOT NULL CHECK(length(trim(work_id)) > 0),
    reading_status TEXT NOT NULL CHECK(reading_status IN ('not_started','in_progress','read','deferred')),
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    last_opened_at TEXT,
    source_literature_id TEXT NOT NULL CHECK(length(trim(source_literature_id)) > 0),
    PRIMARY KEY(user_id,work_id)
);
CREATE INDEX user_literature_work_progress_owner_updated
    ON user_literature_work_progress(user_id,updated_at);
