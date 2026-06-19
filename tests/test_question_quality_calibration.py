from __future__ import annotations
import json, sqlite3
from pathlib import Path
from scripts.audit_question_quality import build_report, inspect_question, normalize_text
from scripts.audit_question_bank import load_canonical_inventory
from scripts.abandon_in_progress_sessions import run

REPO_ROOT = Path(__file__).resolve().parent.parent

def test_quality_audit_controlled_calculations() -> None:
    q={"id":"x","question":" Что НЕ является  примером? ","options":["коротко","средний ответ","очень длинный правильный ответ с большим количеством уточняющих слов","ещё вариант"],"correct_option_index":2}
    m=inspect_question(q)
    assert normalize_text(" А\u00a0Б ")=="а б"
    assert m["unique_longest_correct"] is True
    assert m["high_severity_length_cue"] is True
    assert m["negative_exception_wording"] is True

def test_global_canonical_quality_thresholds_and_rapport_resolution() -> None:
    report=build_report()
    g=report["global"]
    assert g["approved_question_count"] == 575
    assert g["unique_longest_correct_rate"] <= 0.60
    assert g["high_severity_length_cue_count"] == 0
    assert g["duplicate_normalized_stems"] == {}
    inv,_=load_canonical_inventory(); by_id={r["external_id"]:r for r in inv}
    assert "что такое раппорт в консультировании?" not in {normalize_text(by_id["m3_psychological_consulting_031"]["question_text"])}

def test_changelog_references_active_canonical_question_ids() -> None:
    inv,_=load_canonical_inventory(); active={r["external_id"] for r in inv if r["status"]=="approved"}
    changelog=json.loads((REPO_ROOT/"docs/audits/question_bank_calibration_changelog.json").read_text())
    ids=[i["question_id"] for i in changelog["items"]]
    assert changelog["metadata"]["changed_question_count"] == len(ids)
    assert len(ids)==len(set(ids))
    assert set(ids) <= active
    for item in changelog["items"]:
        assert {"question_id","topic_id","issue_type","change_summary","source_ref","validation_basis"} <= set(item)

def test_abandon_in_progress_sessions_dry_run_and_apply(tmp_path: Path) -> None:
    db=tmp_path/"q.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript((REPO_ROOT/"sql/schema.sql").read_text())
        conn.execute("INSERT INTO users (telegram_user_id, username, first_name) VALUES (1,'u','f')")
        uid=conn.execute("SELECT id FROM users").fetchone()[0]
        conn.execute("INSERT INTO quiz_sessions (user_id,status,score) VALUES (?, 'in_progress', 7)",(uid,))
        conn.execute("INSERT INTO quiz_sessions (user_id,status,score,finished_at) VALUES (?, 'finished', 3, CURRENT_TIMESTAMP)",(uid,))
        conn.execute("INSERT INTO quiz_sessions (user_id,status,score,finished_at) VALUES (?, 'abandoned', 2, CURRENT_TIMESTAMP)",(uid,))
    dry=run(str(db), False)
    assert dry["before_count"] == 1 and dry["after_count"] == 1 and dry["abandoned_count"] == 0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM quiz_sessions WHERE status='in_progress'").fetchone()[0] == 1
    applied=run(str(db), True)
    assert applied["before_count"] == 1 and applied["after_count"] == 0 and applied["abandoned_count"] == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM quiz_sessions WHERE status='in_progress'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM quiz_sessions WHERE status='finished'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM quiz_sessions WHERE status='abandoned'").fetchone()[0] == 2
        assert conn.execute("SELECT score FROM quiz_sessions ORDER BY id").fetchall() == [(7,), (3,), (2,)]
