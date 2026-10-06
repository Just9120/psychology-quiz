CREATE TABLE IF NOT EXISTS web_google_identities (
    subject TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL UNIQUE REFERENCES web_accounts(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS web_oauth_challenges (
    state_digest TEXT PRIMARY KEY,
    browser_digest TEXT NOT NULL,
    nonce TEXT NOT NULL,
    pkce_verifier TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK(purpose IN ('login','link')),
    account_id INTEGER REFERENCES web_accounts(id) ON DELETE CASCADE,
    session_digest TEXT REFERENCES web_sessions(digest) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL,
    CHECK((purpose='login' AND account_id IS NULL AND session_digest IS NULL)
       OR (purpose='link' AND account_id IS NOT NULL AND session_digest IS NOT NULL))
);
