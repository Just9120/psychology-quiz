-- Run only after the separately gated PG18.6 pgvector image transition,
-- verified backup/restore rehearsal and absence checks for this namespace.
-- The public application schema and all learning state remain untouched.
BEGIN;
CREATE SCHEMA private_search AUTHORIZATION psychology_app;
REVOKE ALL ON SCHEMA private_search FROM PUBLIC;
CREATE EXTENSION vector WITH SCHEMA private_search VERSION '0.8.6';
COMMIT;
