"""Local-only E2E harness. Temporary synthetic DB/mail; never imported by runtime."""
from contextlib import closing, ExitStack
from pathlib import Path
import os
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import Request
import uvicorn
from app.db import get_connection, upsert_approved_questions
from app import curriculum
from app.attempt_content import capture_question
from app.identity_schema import migrate_identity_schema
from app.auth_schema import migrate_auth_schema
from app.glossary_schema import migrate_glossary_schema
from app.miniapp_fastapi import create_app
from app.web_config import WebSettings
from app.postgres_import import import_snapshot
from scripts.postgres_test_support import isolated_postgres_target

EMAIL = "owner@example.test"
PASSWORD = "A synthetic browser passphrase"


class Mailbox:
    def __init__(self):
        self.messages = []

    def send(self, email, purpose, token):
        self.messages.append({"purpose": purpose, "token": token})


def main():
    with tempfile.TemporaryDirectory(prefix="pwa-e2e-") as directory, ExitStack() as stack:
        path = str(Path(directory) / "synthetic.sqlite3")
        postgres_path = stack.enter_context(isolated_postgres_target(os.environ["POSTGRES_TEST_DSN"])) if os.environ.get("POSTGRES_TEST_DSN") else None
        mailbox = Mailbox()
        settings = WebSettings("http://127.0.0.1:4173", EMAIL, "smtp.example.test", 465,
                               EMAIL, "synthetic-only", EMAIL, False)
        app = create_app(db_path=postgres_path or path, bot_token="123:synthetic-e2e", web_settings=settings, web_mailer=mailbox)

        def reset(seed=True):
            nonlocal path
            path = str(Path(directory) / "synthetic.sqlite3")
            Path(path).unlink(missing_ok=True)
            mailbox.messages.clear()
            with closing(get_connection(path)) as conn, conn:
                conn.executescript((ROOT / "sql/schema.sql").read_text(encoding="utf-8"))
                upsert_approved_questions(conn, [
                    {"id": f"test-{i}", "category": "Основы психологии" if i < 5 else "Психология развития",
                     "source_ref": "synthetic", "difficulty": "easy", "status": "approved",
                     "question": f"Учебный вопрос {i + 1}: что помогает закрепить знания?",
                     "explanation": "Повторение помогает восстановить и укрепить связь с изученным материалом.",
                     "options": ["Осмысленное повторение", "Только скорость", "Случайный выбор", "Отсутствие практики"],
                     "correct_option_index": 0} for i in range(7)
                ], authoritative=True)
            with closing(get_connection(path)) as conn:
                migrate_identity_schema(conn)
                migrate_auth_schema(conn)
                with conn:
                    migrate_glossary_schema(conn)
                # The harness supplies its own reviewed taxonomy for synthetic
                # editions; production catalog and user data are never changed.
                data = {"schema_version": 1,
                        "disciplines": {"basics": {"title": "Основы психологии"}, "development": {"title": "Психология развития"}},
                        "topics": {"t_111111111111": {"title": "Память и повторение", "discipline_id": "basics"},
                                   "t_222222222222": {"title": "Учебная практика", "discipline_id": "development"}}, "editions": {}}
                for row in conn.execute('SELECT id,external_id FROM questions'):
                    _, digest = capture_question(conn, row['id'])
                    index = int(row['external_id'].split('-')[1])
                    if index != 4:  # One deliberate source gap, visible in UI.
                        data['editions'][digest] = {'topic_id': 't_111111111111' if index < 5 else 't_222222222222'}
                curriculum.load_catalog = lambda: data
            if postgres_path:
                with closing(get_connection(postgres_path)) as conn, conn:
                    if conn.execute("SELECT to_regclass('postgres_storage')").fetchone()[0] is not None:
                        from app.postgres_schema import TABLES, verify_schema
                        verify_schema(conn)
                        conn.execute("TRUNCATE " + ",".join(TABLES) + " RESTART IDENTITY")
                        conn.execute("UPDATE postgres_storage SET import_manifest=NULL WHERE singleton=1")
                import_snapshot(Path(path), postgres_path)
                path = postgres_path
            app.state.web_auth.db_path = path
            if seed:
                app.state.web_auth.request_mail(EMAIL, "register")
                app.state.web_auth.set_password(mailbox.messages[-1]["token"], PASSWORD, "register")

        # Controls exist only in this test process, bound to loopback; no runtime flag.
        @app.post("/__test/reset")
        async def reset_fixture(request: Request):
            reset((await request.json()).get("seed", True))
            return {"ok": True}

        @app.get("/__test/mail")
        def mail_fixture():
            return {"messages": mailbox.messages}

        @app.post("/__test/telegram-confirm")
        async def telegram_fixture(request: Request):
            code = (await request.json())["code"]
            auth = app.state.web_auth
            user = SimpleNamespace(id=4242, username="synthetic_learner", first_name="Учебный", last_name="аккаунт")
            auth.propose_telegram_link(code, user)
            auth.confirm_telegram_link(code, 4242)
            return {"ok": True}

        @app.get("/__test/health")
        def health():
            return {"ok": True}

        reset()
        uvicorn.run(app, host="127.0.0.1", port=8085, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
