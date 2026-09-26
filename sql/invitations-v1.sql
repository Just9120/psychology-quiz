-- Invite-only PWA access. Tokens are stored as digests and are never public assets.
CREATE TABLE pwa_invitations (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    promo_shown_at BIGINT,
    token_digest TEXT UNIQUE,
    expires_at BIGINT,
    consumed_at BIGINT,
    invited_email TEXT,
    account_id BIGINT UNIQUE REFERENCES web_accounts(id) ON DELETE SET NULL,
    CHECK ((token_digest IS NULL AND (expires_at IS NULL OR consumed_at IS NOT NULL))
        OR (token_digest IS NOT NULL AND expires_at IS NOT NULL AND consumed_at IS NULL))
);
CREATE INDEX pwa_invitations_expiry ON pwa_invitations(expires_at);
CREATE UNIQUE INDEX pwa_invitations_email ON pwa_invitations(invited_email) WHERE invited_email IS NOT NULL;
