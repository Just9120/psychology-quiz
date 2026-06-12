from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db import upsert_approved_questions


def resolve_db_path() -> str:
    load_dotenv()
    return os.getenv("DB_PATH", "/data/quiz.sqlite3").strip() or "/data/quiz.sqlite3"


def validate_question(item: dict[str, Any], index: int, source_name: str) -> tuple[bool, str | None]:
    required = ["id", "category", "question", "options", "correct_option_index", "status"]
    for field in required:
        if field not in item:
            return False, f"{source_name} элемент #{index}: отсутствует обязательное поле '{field}'"

    if not isinstance(item["options"], list) or len(item["options"]) < 2:
        return False, (
            f"{source_name} элемент #{index}: поле 'options' должно содержать минимум 2 варианта"
        )

    correct_option_index = item["correct_option_index"]
    if not isinstance(correct_option_index, int):
        return False, f"{source_name} элемент #{index}: 'correct_option_index' должен быть целым числом"

    if correct_option_index < 0 or correct_option_index >= len(item["options"]):
        return (
            False,
            f"{source_name} элемент #{index}: 'correct_option_index' выходит за границы массива 'options'",
        )

    return True, None


def load_questions_from_file(file_path: Path) -> list[dict[str, Any]]:
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("JSON должен содержать массив вопросов")

    valid_items: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            errors.append(f"{file_path.name} элемент #{idx}: должен быть объектом")
            continue

        ok, error = validate_question(item, idx, file_path.name)
        if not ok and error:
            errors.append(error)
            continue

        valid_items.append(item)

    if errors:
        joined = "\n".join(errors)
        raise ValueError(f"Найдены ошибки валидации:\n{joined}")

    return valid_items


def load_questions_from_folder(folder_path: Path) -> tuple[list[dict[str, Any]], int]:
    if not folder_path.exists() or not folder_path.is_dir():
        raise FileNotFoundError(f"Не найдена директория с вопросами: {folder_path}")

    json_files = sorted(folder_path.glob("*.json"), key=lambda p: p.name)
    if not json_files:
        raise FileNotFoundError(f"В директории нет JSON-файлов с вопросами: {folder_path}")

    all_questions: list[dict[str, Any]] = []
    for file_path in json_files:
        all_questions.extend(load_questions_from_file(file_path))

    return all_questions, len(json_files)


def discover_module_dirs(questions_root: Path) -> list[Path]:
    if not questions_root.exists() or not questions_root.is_dir():
        raise FileNotFoundError(f"Не найдена директория с вопросами: {questions_root}")

    module_dirs = sorted(
        (path for path in questions_root.iterdir() if path.is_dir() and path.name.startswith("module")),
        key=lambda path: path.name,
    )
    if not module_dirs:
        raise FileNotFoundError(f"Не найдены module-директории с вопросами: {questions_root}")

    return module_dirs


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    questions_root = repo_root / "content" / "questions"

    db_path = Path(resolve_db_path())
    if not db_path.exists():
        print(f"[ERROR] База данных не найдена: {db_path}")
        print("[HINT] Сначала выполните инициализацию схемы: python scripts/init_db.py")
        return 1

    try:
        module_dirs = discover_module_dirs(questions_root)
        questions: list[dict[str, Any]] = []
        processed_files = 0
        for module_dir in module_dirs:
            module_questions, module_files = load_questions_from_folder(module_dir)
            questions.extend(module_questions)
            processed_files += module_files
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] Ошибка загрузки вопросов: {exc}")
        return 1

    approved_total = sum(1 for question in questions if question.get("status") == "approved")

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            stats = upsert_approved_questions(conn, questions)
    except sqlite3.Error as exc:
        print(f"[ERROR] Ошибка SQLite при загрузке вопросов: {exc}")
        return 1

    processed_modules = ", ".join(module_dir.name for module_dir in module_dirs)
    print(f"[OK] Директории обработаны: {processed_modules}")
    print(f"[OK] Файлов обработано: {processed_files}")
    print(f"[OK] Одобренных вопросов найдено: {approved_total}")
    print(f"[OK] Категорий создано/обновлено: {stats['categories']}")
    print(f"[OK] Вопросов создано/обновлено: {stats['upserted_questions']}")
    print("[OK] Загрузка вопросов в БД завершена успешно")
    return 0


if __name__ == "__main__":
    sys.exit(main())
