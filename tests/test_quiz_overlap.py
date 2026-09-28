import sqlite3
import pytest

from app.quiz_overlap import balanced_diverse_first, balanced_kinds_diverse_first, diverse_first, memberships
from app.quiz_service import prepare_quiz


def test_finite_quiz_defers_reviewed_concept_overlap_without_losing_count():
    first = next(iter(memberships()))
    duplicate = None
    for candidate, groups in memberships().items():
        if candidate != first and groups & memberships()[first]:
            duplicate = candidate
            break
    assert duplicate is not None
    unrelated = next(candidate for candidate, groups in memberships().items()
                     if not groups & memberships()[first])
    candidates = [(1, first), (2, duplicate), (3, unrelated)]

    assert diverse_first(candidates, 2) == [1, 3]
    assert diverse_first(candidates, 3) == [1, 3, 2]
    assert diverse_first(candidates, None) == [1, 2, 3]


def test_reviewed_question_pairs_share_overlap_without_removing_all_mode():
    groups = memberships()
    for first, second in (
        ("m1_gp_048", "m1_gp_056"),
        ("m1_intro_043", "m3_psychological_consulting_030"),
    ):
        assert groups[first] & groups[second]
        assert diverse_first([(1, first), (2, second)], 1) == [1]
        assert diverse_first([(1, first), (2, second)], None) == [1, 2]


def test_distinct_learning_objectives_are_not_deferred_as_duplicates():
    distinct_pairs = (
        ("m2_exp_022", "m2_exp_023"),  # internal versus external validity
        ("m2_exp_023", "m2_exp_048"),  # definition versus tradeoff
        ("m2_qual_015", "m2_qual_047"),  # consent versus de-identification
        ("m3_psychological_consulting_009", "m3_psychological_consulting_045"),
        ("m3_psychological_consulting_055", "m3_psychological_consulting_066"),
    )
    for first, second in distinct_pairs:
        assert diverse_first([(1, first), (2, second)], 2) == [1, 2]
    assert diverse_first([
        (1, "m2_exp_048"), (2, "m2_exp_100"), (3, "m2_exp_023")
    ], 2) == [1, 3]


def test_request_concepts_separate_definition_unrealistic_goal_and_case_formulation():
    assert diverse_first([
        (1, "m3_psychological_consulting_005"),
        (2, "m3_psychological_consulting_094"),
        (3, "m3_psychological_consulting_096"),
    ], 3) == [1, 2, 3]
    assert diverse_first([
        (1, "m3_psychological_consulting_024"),
        (2, "m3_psychological_consulting_040"),
        (3, "m3_psychological_consulting_096"),
    ], 2) == [1, 3]


def test_selected_mix_keeps_a_topic_with_later_distinct_concepts(monkeypatch):
    monkeypatch.setattr("app.quiz_overlap.memberships", lambda: {
        "shared": frozenset({1}), "other-a": frozenset({2}),
        "third-a": frozenset({3}), "distinct-b": frozenset({4}),
    })
    buckets = {
        10: [(3, "third-a"), (2, "other-a"), (1, "shared")],
        20: [(6, "distinct-b"), (5, "shared"), (4, "shared")],
    }
    assert balanced_diverse_first(buckets, [10, 20], 3) == [1, 6, 2]
    assert balanced_diverse_first(buckets, [10, 20], None) == [1, 4, 2, 5, 3, 6]
    assert balanced_diverse_first(buckets, [10, 20], 6) == [1, 6, 2, 3, 4, 5]


def test_mixed_kinds_keep_topic_balance_and_skip_avoidable_overlap(monkeypatch):
    monkeypatch.setattr("app.quiz_overlap.memberships", lambda: {
        "shared-a": frozenset({1}), "shared-b": frozenset({1}),
        "unique-b": frozenset({2}),
    })
    candidates = [
        (1, "shared-a", 10, "theory"),
        (2, "shared-b", 20, "theory"),
        (3, "unique-b", 20, "glossary"),
        (4, "case-c", 30, "case"),
        (5, "another-a", 10, "theory"),
        (6, "another-b", 20, "theory"),
    ]
    selected = balanced_kinds_diverse_first(candidates, [10, 20, 30],
                                             ["theory", "glossary", "case"], 5)
    assert len(selected) == len(set(selected)) == 5
    assert {candidates[qid - 1][3] for qid in selected} == {"theory", "glossary", "case"}
    assert 2 not in selected or 1 not in selected
    categories = [candidates[qid - 1][2] for qid in selected]
    assert max(categories.count(topic) for topic in (10, 20, 30)) <= 2

    bank_wide = [(qid, external_id, 0, kind)
                 for qid, external_id, _, kind in candidates if kind in {"theory", "glossary"}]
    assert balanced_kinds_diverse_first(bank_wide, [0], ["theory", "glossary"], 3) == [1, 3, 5]


def test_short_mix_reserves_only_kind_from_narrow_topic():
    candidates = [
        (1, "a-theory", 10, "theory"),
        (2, "a-glossary", 10, "glossary"),
        (3, "a-case", 10, "case"),
        (4, "b-theory", 20, "theory"),
    ]
    assert balanced_kinds_diverse_first(
        candidates, [10, 20], ["theory", "glossary", "case"], 3,
    ) == [4, 2, 3]


@pytest.mark.parametrize("filter_kinds", [True, False])
def test_selected_mix_with_content_kinds_uses_balanced_concept_selection(monkeypatch, filter_kinds):
    monkeypatch.setattr("app.quiz_overlap.memberships", lambda: {
        "shared-a": frozenset({1}), "shared-b": frozenset({1})})
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript("""
            CREATE TABLE categories(id integer primary key, slug text, name text);
            CREATE TABLE questions(id integer primary key, category_id integer,
                external_id text, kind text, status text, difficulty text);
            INSERT INTO categories VALUES (10,'a','A'),(20,'b','B');
            INSERT INTO questions VALUES
                (1,10,'shared-a','theory','approved','easy'),
                (2,10,'a2','theory','approved','easy'),
                (3,10,'a3','theory','approved','easy'),
                (4,10,'a4','theory','approved','easy'),
                (5,20,'shared-b','theory','approved','easy'),
                (6,20,'b2','glossary','approved','easy'),
                (7,20,'b3','glossary','approved','easy');
        """)
        setup = {"quiz_mode": "selected_mix", "category_ids": [10, 20],
                 "question_count": 5, "difficulty": "any",
                 "content_kinds": ["theory", "glossary"]}
        if not filter_kinds:
            setup.pop("content_kinds")
        chosen = prepare_quiz(conn, setup).question_ids
        rows = [conn.execute("SELECT category_id,kind FROM questions WHERE id=?", (qid,)).fetchone()
                for qid in chosen]
        assert len(chosen) == len(set(chosen)) == 5
        assert not {1, 5}.issubset(chosen)
        assert {row["kind"] for row in rows} == {"theory", "glossary"}
        assert sorted(sum(row["category_id"] == topic for row in rows) for topic in (10, 20)) == [2, 3]
    finally:
        conn.close()
