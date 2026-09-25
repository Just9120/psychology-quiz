"""Run the same actor/review/achievement contracts against real PostgreSQL."""

from tests.test_achievements import (
    test_private_achievements_from_completed_editions_and_review_events,
    test_corrected_glossary_error_requires_answer_from_due_queue,
    test_achievements_api_requires_personal_identity,
)
from tests.test_learning_goals import (
    test_weekly_units_are_personal_durable_and_event_based,
    test_invalid_goal_never_mutates_target,
)
from tests.test_repetition import (
    test_due_queue_is_personal_and_resets_after_question_edit,
    test_adaptive_keeps_random_candidate_scope_and_reserves_new_material,
    test_review_attempt_counts_only_accepted_queue_answers_once,
    test_glossary_due_review_counts_one_answer_and_keeps_other_actors_private,
    test_topic_reset_removes_only_review_events_for_deleted_answers,
)
