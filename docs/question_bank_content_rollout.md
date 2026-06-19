# Question bank content rollout with unfinished sessions

This is an explicit operator procedure for replacing question content while unfinished sessions may exist.

1. Create a production SQLite snapshot before any content replacement.
2. Run the read-only parity audit: `python scripts/audit_question_bank.py --db-path <snapshot-or-production-db>`.
3. Run a dry-run abandoned-session report: `python scripts/abandon_in_progress_sessions.py --db-path <production-db>`.
4. If the report is acceptable, explicitly close unfinished sessions: `python scripts/abandon_in_progress_sessions.py --db-path <production-db> --apply`.
5. Deploy and reseed question content using the normal content deployment procedure.
6. Rerun the read-only parity audit against the reseeded database.
7. Smoke-test a new quiz in both the Telegram bot and Mini App.

Closing unfinished sessions prevents users from returning to changed option sets after a content replacement. Historical answers remain untouched: the script does not delete rows and does not alter answers, score, completed sessions, abandoned sessions, users, questions, or options. The script is never called automatically by application startup or CI; it is an explicit operator action only.
