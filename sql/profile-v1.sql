CREATE TABLE web_profile_names (
    account_id BIGINT PRIMARY KEY REFERENCES web_accounts(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 60)
);
