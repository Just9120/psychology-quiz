CREATE TABLE glossary_sessions (
    id TEXT PRIMARY KEY NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL,
    topic_title TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('in_progress','completed','abandoned')),
    snapshot TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX glossary_sessions_owner ON glossary_sessions(user_id,created_at,id);
CREATE UNIQUE INDEX glossary_one_active ON glossary_sessions(user_id) WHERE status='in_progress';
