CREATE TABLE user_data_deletion_challenges (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_digest TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
