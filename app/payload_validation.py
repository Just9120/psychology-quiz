"""Shared validation before either client adapter opens a write transaction."""


def is_sqlite_integer(value: object, *, minimum: int = 0) -> bool:
    # bool is an int subclass; oversized JSON integers cannot bind to SQLite.
    return type(value) is int and minimum <= value <= 2**63 - 1


def valid_quiz_setup(payload: dict) -> bool:
    mode = payload.get("quiz_mode")
    count = payload.get("question_count")
    difficulty = payload.get("difficulty")
    categories = payload.get("category_ids")
    kinds = payload.get("content_kinds")
    return (
        isinstance(mode, str) and mode in {"single", "selected_mix", "all", "adaptive"}
        and (count is None or (type(count) is int and count in {5, 10, 15}))
        and isinstance(difficulty, str) and difficulty in {"any", "easy", "medium", "hard"}
        and isinstance(categories, list)
        and all(is_sqlite_integer(item, minimum=1) for item in categories)
        and ("content_kinds" not in payload or
             isinstance(kinds, list) and bool(kinds)
             and all(type(kind) is str and kind in {"theory", "glossary", "case"} for kind in kinds)
             and len(kinds) == len(set(kinds)))
    )
