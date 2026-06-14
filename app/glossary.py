from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

GLOSSARY_UNAVAILABLE_TEXT = "Глоссарий временно недоступен. Попробуйте позже."
GLOSSARY_PAGE_SIZE = 6
GLOSSARY_TOPICS: tuple[tuple[str, str], ...] = (
    ("kachestvennye_metody_issledovaniya", "Качественные методы исследования"),
)
GLOSSARY_TOPIC_CALLBACK_TOKENS = {"kmi": "kachestvennye_metody_issledovaniya"}
GLOSSARY_TOPIC_ID_TO_TOKEN = {topic_id: token for token, topic_id in GLOSSARY_TOPIC_CALLBACK_TOKENS.items()}
_REPO_ROOT = Path(__file__).resolve().parent.parent
_GLOSSARY_DIR = _REPO_ROOT / "content" / "glossary"


@dataclass(frozen=True)
class GlossaryEntry:
    id: str
    topic_id: str
    term: str
    aliases: tuple[str, ...]
    short_definition: str
    definition: str
    examples: tuple[str, ...]
    difficulty: str
    source_refs: tuple[str, ...]


def _string_list(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        stripped = item.strip()
        if stripped:
            items.append(stripped)
    return tuple(items)


def load_glossary_entries(topic_id: str) -> list[GlossaryEntry] | None:
    if topic_id not in {topic for topic, _ in GLOSSARY_TOPICS}:
        return None

    try:
        raw = json.loads((_GLOSSARY_DIR / f"{topic_id}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, list):
        return None

    entries: list[GlossaryEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        entry_id = item.get("id")
        entry_topic_id = item.get("topic_id")
        term = item.get("term")
        short_definition = item.get("short_definition")
        definition = item.get("definition")
        difficulty = item.get("difficulty")
        aliases = _string_list(item.get("aliases"))
        examples = _string_list(item.get("examples"))
        source_refs = _string_list(item.get("source_refs"))
        if not all(isinstance(value, str) and value.strip() for value in (entry_id, entry_topic_id, term, short_definition, definition, difficulty)):
            return None
        if entry_topic_id != topic_id or aliases is None or examples is None or source_refs is None:
            return None
        entries.append(
            GlossaryEntry(
                id=entry_id.strip(),
                topic_id=entry_topic_id.strip(),
                term=term.strip(),
                aliases=aliases,
                short_definition=short_definition.strip(),
                definition=definition.strip(),
                examples=examples,
                difficulty=difficulty.strip(),
                source_refs=source_refs,
            )
        )
    return entries


def build_glossary_topics_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(title, callback_data=f"gls:topic:{GLOSSARY_TOPIC_ID_TO_TOKEN[topic_id]}:0")] for topic_id, title in GLOSSARY_TOPICS]
    )


def format_glossary_topics_text() -> str:
    return "Глоссарий по психологии\nВыберите тему:"


def build_glossary_terms_keyboard(topic_id: str, entries: list[GlossaryEntry], page: int) -> InlineKeyboardMarkup:
    safe_page = max(0, page)
    start = safe_page * GLOSSARY_PAGE_SIZE
    page_entries = entries[start : start + GLOSSARY_PAGE_SIZE]
    keyboard = [
        [InlineKeyboardButton(entry.term, callback_data=f"gls:term:{GLOSSARY_TOPIC_ID_TO_TOKEN[topic_id]}:{entry.id}:{safe_page}")]
        for entry in page_entries
    ]
    nav_row = []
    if safe_page > 0:
        nav_row.append(InlineKeyboardButton("Назад", callback_data=f"gls:topic:{GLOSSARY_TOPIC_ID_TO_TOKEN[topic_id]}:{safe_page - 1}"))
    if start + GLOSSARY_PAGE_SIZE < len(entries):
        nav_row.append(InlineKeyboardButton("Далее", callback_data=f"gls:topic:{GLOSSARY_TOPIC_ID_TO_TOKEN[topic_id]}:{safe_page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("Назад к темам", callback_data="gls:topics")])
    return InlineKeyboardMarkup(keyboard)


def format_glossary_terms_text(topic_title: str, page: int, total_entries: int) -> str:
    total_pages = max(1, (total_entries + GLOSSARY_PAGE_SIZE - 1) // GLOSSARY_PAGE_SIZE)
    safe_page = min(max(0, page), total_pages - 1)
    return f"<b>{escape(topic_title)}</b>\n\nВыберите термин. Страница {safe_page + 1} из {total_pages}."


def find_glossary_entry(entries: list[GlossaryEntry], entry_id: str) -> GlossaryEntry | None:
    return next((entry for entry in entries if entry.id == entry_id), None)


def format_glossary_entry_text(entry: GlossaryEntry) -> str:
    lines = [
        f"<b>{escape(entry.term)}</b>",
        "",
    ]
    if entry.aliases:
        lines.append(f"<b>Также:</b> {escape(', '.join(entry.aliases))}")
        lines.append("")
    lines.extend(
        [
            f"<b>Кратко:</b> {escape(entry.short_definition)}",
            "",
            f"<b>Определение:</b> {escape(entry.definition)}",
        ]
    )
    if entry.examples:
        lines.append("")
        lines.append("<b>Примеры:</b>")
        lines.extend(f"• {escape(example)}" for example in entry.examples)
    lines.extend(
        [
            "",
            f"<b>Сложность:</b> {escape(entry.difficulty)}",
            f"<b>Источники:</b> {escape('; '.join(entry.source_refs))}",
        ]
    )
    return "\n".join(lines)


def build_glossary_entry_keyboard(topic_id: str, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Назад к списку терминов", callback_data=f"gls:topic:{GLOSSARY_TOPIC_ID_TO_TOKEN[topic_id]}:{max(0, page)}")],
            [InlineKeyboardButton("Назад к темам", callback_data="gls:topics")],
            [InlineKeyboardButton("Главное меню", callback_data="gls:main")],
        ]
    )


def topic_title(topic_id: str) -> str | None:
    return dict(GLOSSARY_TOPICS).get(topic_id)


def callback_token_to_topic_id(token: str) -> str | None:
    return GLOSSARY_TOPIC_CALLBACK_TOKENS.get(token)
