-- Additive learning-state migration. Existing actors, answers and snapshots remain unchanged.
ALTER TABLE questions ADD COLUMN kind TEXT NOT NULL DEFAULT 'theory'
    CHECK(kind IN ('theory','glossary','case'));
ALTER TABLE questions ADD COLUMN case_content TEXT;
CREATE TABLE user_learning_goals (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_kind TEXT NOT NULL CHECK(goal_kind IN ('study','review','reading')),
    weekly_target BIGINT NOT NULL CHECK(weekly_target > 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(user_id,goal_kind)
);
CREATE TABLE user_achievements (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    achievement_kind TEXT NOT NULL,
    evidence_key TEXT NOT NULL,
    earned_at TEXT NOT NULL,
    PRIMARY KEY(user_id,achievement_kind,evidence_key)
);
CREATE INDEX user_achievements_owner ON user_achievements(user_id,earned_at);
CREATE TABLE user_review_events (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    answer_kind TEXT NOT NULL CHECK(answer_kind IN ('quiz','glossary')),
    answer_key TEXT NOT NULL,
    answered_at TEXT NOT NULL,
    PRIMARY KEY(user_id,answer_kind,answer_key)
);
CREATE INDEX user_review_events_owner_time ON user_review_events(user_id,answered_at);
CREATE TABLE user_review_sessions (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_kind TEXT NOT NULL CHECK(session_kind IN ('quiz','glossary')),
    session_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    PRIMARY KEY(session_kind,session_key)
);
CREATE INDEX user_review_sessions_owner ON user_review_sessions(user_id,session_kind);
