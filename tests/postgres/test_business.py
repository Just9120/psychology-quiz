"""Run unchanged transport/business contracts against migrated PostgreSQL."""
from tests.test_quiz_service import (
    test_cross_client_conflicting_concurrent_answers_return_one_recorded_result,
    test_future_question_cannot_be_answered_before_current,
)
from tests.test_web_integration import (
    test_web_quiz_full_flow_retries_and_restart_state,
    test_bot_command_requires_private_chat_then_bound_callback,
)
from tests.test_web_auth import (
    test_email_proof_errors_never_create_account,
    test_non_owner_unknown_login_and_disabled_account_are_denied,
    test_csrf_origin_content_type_guards_prevent_state_changes,
    test_logout_recovery_expiry_and_process_restart_revoke_sessions,
    test_absolute_expiry_even_when_session_kept_active,
    test_login_rate_limit_survives_restart_and_expires,
    test_link_invalidated_by_lifecycle_and_session_binding,
    test_occupied_identity_and_cross_user_data_cannot_be_claimed,
    test_auth_api_errors_limits_and_logs_do_not_echo_secrets,
    test_disabled_web_routes_do_not_touch_database,
)
