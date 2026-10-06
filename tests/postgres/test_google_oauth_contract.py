"""OAuth uses the same durable authorization contract on real PostgreSQL."""
from tests.test_owner_google_oauth import (
    flow,
    test_google_explicit_owner_link_then_stable_subject_login,
    test_google_link_revalidates_initiating_owner_session,
    test_google_does_not_register_or_bind_by_matching_email,
    test_google_failed_exchange_consumes_proof_and_unlink_invalidates_link,
)
