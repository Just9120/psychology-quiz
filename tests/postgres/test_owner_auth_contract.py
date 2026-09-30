"""Owner-only access must also reject persisted legacy actors on PostgreSQL."""
from tests.test_web_auth import (
    test_legacy_student_accounts_sessions_and_invitations_cannot_bypass_owner_access,
)
