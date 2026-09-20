"""The same user-level progress contracts on a real migrated PostgreSQL DB."""
from tests.test_progress import (
    test_empty_counts_and_partial_history_isolation,
    test_history_pagination_and_historical_topic_daily_aggregates,
    test_last_answer_per_edition_and_retired_content,
    test_training_cas_preserves_active_and_replay_and_uses_only_own_errors,
    test_pagination_and_detail_reject_non_ids,
    test_detail_and_error_pagination,
    test_legacy_backfill_is_not_proof_of_current_correctness,
    test_concurrent_training_retries_create_one_attempt,
    test_daily_window_does_not_truncate_totals,
    test_legacy_correct_answer_cannot_resolve_captured_mistake,
)
from tests.test_web_progress import (
    test_progress_api_shared_telegram_history_and_guards,
    test_empty_training_and_bad_payload_do_not_create_attempt,
)
