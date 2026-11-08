import sqlite3
from contextlib import closing
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
        ("m1_gp_032", "m1_gp_050"),
        ("m1_intro_008", "m1_intro_019"),
    ):
        assert groups[first] & groups[second]
        assert diverse_first([(1, first), (2, second)], 1) == [1]
        assert diverse_first([(1, first), (2, second)], None) == [1, 2]


def test_distinct_learning_objectives_are_not_deferred_as_duplicates():
    distinct_pairs = (
        ("m2_exp_022", "m2_exp_023"),  # internal versus external validity
        ("m2_exp_023", "m2_exp_094"),  # transfer definition versus balancing design goals
        ("m2_qual_008", "m2_qual_034"),  # observation versus researcher reflexivity
        ("m3_psychological_consulting_009", "m3_psychological_consulting_045"),
        ("m3_psychological_consulting_055", "m3_psychological_consulting_066"),
        ("m1_gp_048", "m1_gp_047"),  # one observation versus testing contrary evidence
        ("m2_exp_015", "m2_exp_098"),  # manipulated/outcome roles versus control/confounding
        ("m3_psychological_consulting_009", "m3_psychological_consulting_031"),
        ("m3_psychological_consulting_008", "m3_psychological_consulting_027"),
    )
    for first, second in distinct_pairs:
        assert diverse_first([(1, first), (2, second)], 2) == [1, 2]
    assert diverse_first([(1, "m2_exp_098"), (3, "m2_exp_023")], 2) == [1, 3]
    # The richer control/confounding task replaces the identification-only duplicate.
    import json
    from pathlib import Path
    from app.content_publication import load_policy
    items = json.loads(Path("content/questions/module2/osnovy_eksperimentalnoy_psihologii.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in items}
    assert load_policy().can_publish("questions", by_id["m2_exp_098"])
    assert by_id["m2_exp_110"]["status"] == "retired"
    assert not load_policy().can_publish("questions", by_id["m2_exp_110"])
    assert "m2_exp_110" not in memberships()


def test_request_concepts_separate_definition_unrealistic_goal_and_case_formulation():
    # Consolidation keeps distinct objectives and retires duplicate future draws.
    assert diverse_first([
        (1, "m3_psychological_consulting_030"),
        (2, "case_goal_own_actions_001"),
        (3, "m3_psychological_consulting_096"),
    ], 3) == [1, 2, 3]
    import json
    from pathlib import Path
    items = json.loads(Path("content/questions/module3/psychological_consulting.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in items}
    for retired in ("m3_psychological_consulting_024", "m3_psychological_consulting_040"):
        assert by_id[retired]["status"] == "retired"
        assert retired not in memberships()


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


@pytest.mark.parametrize("second_topic", [{6, 7, 8, 9, 10}, {6}])
def test_selected_mix_balances_leaves_within_one_discipline(monkeypatch, second_topic):
    first, second = "t_123456789abc", "t_abcdef123456"
    scopes = {first: {1, 2, 3, 4, 5}, second: second_topic}
    monkeypatch.setattr("app.quiz_service.question_scopes", lambda _: (
        [{"category_id": 10, "topics": [{"id": first}, {"id": second}]}], scopes,
    ))
    monkeypatch.setattr("app.quiz_overlap.memberships", lambda: {
        "q2": frozenset({1}), "q7": frozenset({1}),
    })
    with closing(sqlite3.connect(":memory:")) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE categories(id integer primary key, slug text, name text);
            INSERT INTO categories VALUES (10,'a','A');
            CREATE TABLE questions(id integer primary key, category_id integer,
                external_id text, kind text, status text, difficulty text);
        """)
        conn.executemany("INSERT INTO questions VALUES (?,10,?,?,'approved','easy')", [
            (qid, f"q{qid}", "case" if qid == 6 else "theory") for qid in range(1, 11)
        ])
        chosen = set(prepare_quiz(conn, {
            "quiz_mode": "selected_mix", "category_ids": [10], "topic_ids": [first, second],
            "question_count": 5, "difficulty": "any", "content_kinds": ["case", "theory"],
        }).question_ids)
    counts = sorted(len(chosen & ids) for ids in scopes.values())
    assert counts == ([2, 3] if len(second_topic) >= 5 else [1, 4])
    assert 6 in chosen
    assert not {2, 7}.issubset(chosen)
