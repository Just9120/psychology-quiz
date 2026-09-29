CREATE TABLE homework_attempts (
    session_id BIGINT PRIMARY KEY REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    assignment_id TEXT NOT NULL CHECK (length(trim(assignment_id)) > 0)
);

CREATE INDEX homework_attempts_assignment ON homework_attempts(assignment_id);
