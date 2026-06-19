from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import random
import unicodedata
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

GLOSSARY_UNAVAILABLE_TEXT = "Глоссарий временно недоступен. Попробуйте позже."
GLOSSARY_TOPICS: tuple[tuple[str, str], ...] = (
    ("vvedenie_v_professiyu", "Введение в профессию"),
    ("obschaya_psihologiya", "Общая психология"),
    ("fiziologiya_cheloveka", "Физиология человека"),
    ("fiziologiya_vnd", "Физиология ВНД"),
    ("psihofiziologiya", "Психофизиология"),
    ("osnovy_eksperimentalnoy_psihologii", "Основы экспериментальной психологии"),
    ("kachestvennye_metody_issledovaniya", "Качественные методы исследования"),
    ("psychological_consulting", "Психологическое консультирование"),
)
GLOSSARY_TOPIC_CALLBACK_TOKENS = {
    "vvp": "vvedenie_v_professiyu",
    "op": "obschaya_psihologiya",
    "fch": "fiziologiya_cheloveka",
    "vnd": "fiziologiya_vnd",
    "psyf": "psihofiziologiya",
    "kmi": "kachestvennye_metody_issledovaniya",
    "oep": "osnovy_eksperimentalnoy_psihologii",
    "pc": "psychological_consulting",
}
GLOSSARY_TOPIC_ID_TO_TOKEN = {topic_id: token for token, topic_id in GLOSSARY_TOPIC_CALLBACK_TOKENS.items()}
GLOSSARY_QUIZ_SESSION_KEY = "glossary_quiz_session"
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
    confusable_with: tuple[str, ...]


@dataclass(frozen=True)
class GlossaryQuizQuestion:
    entry: GlossaryEntry
    options: tuple[str, ...]
    correct_option_index: int


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
        confusable_with = _string_list(item.get("confusable_with"))
        if not all(isinstance(value, str) and value.strip() for value in (entry_id, entry_topic_id, term, short_definition, definition, difficulty)):
            return None
        if entry_topic_id != topic_id or aliases is None or examples is None or source_refs is None or confusable_with is None:
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
                confusable_with=confusable_with,
            )
        )
    return entries


def build_glossary_topics_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(title, callback_data=f"gls:topic:{GLOSSARY_TOPIC_ID_TO_TOKEN[topic_id]}")] for topic_id, title in GLOSSARY_TOPICS]
    )


def format_glossary_topics_text() -> str:
    return "<b>Глоссарий: тест по терминам</b>\nВыберите тему:"


def build_glossary_count_keyboard(topic_id: str, available_count: int) -> InlineKeyboardMarkup:
    token = GLOSSARY_TOPIC_ID_TO_TOKEN[topic_id]
    rows = [
        [InlineKeyboardButton("5", callback_data=f"glsq:count:{token}:5")],
        [InlineKeyboardButton("10", callback_data=f"glsq:count:{token}:10")],
        [InlineKeyboardButton("Все доступные", callback_data=f"glsq:count:{token}:all")],
        [InlineKeyboardButton("Назад к темам", callback_data="gls:topics")],
    ]
    return InlineKeyboardMarkup(rows)


def format_glossary_count_text(topic_title: str, available_count: int) -> str:
    return f"<b>{escape(topic_title)}</b>\n\nВыберите количество вопросов:\nДоступно терминов: {available_count}."


def _normalize_option_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _shuffled_candidates(candidates: list[GlossaryEntry], picker: Any) -> list[GlossaryEntry]:
    shuffled = list(candidates)
    picker.shuffle(shuffled)
    return shuffled


def build_glossary_quiz_question(entries: list[GlossaryEntry], entry: GlossaryEntry, *, rng: random.Random | None = None) -> GlossaryQuizQuestion | None:
    correct_option = entry.short_definition.strip()
    correct_normalized = _normalize_option_text(correct_option)
    if not correct_option or not correct_normalized:
        return None

    topic_entries_by_id: dict[str, GlossaryEntry] = {}
    for candidate in entries:
        if candidate.topic_id != entry.topic_id or candidate.id in topic_entries_by_id:
            continue
        if not candidate.short_definition.strip():
            continue
        topic_entries_by_id[candidate.id] = candidate

    if entry.id not in topic_entries_by_id:
        return None

    picker = rng or random
    selected: list[GlossaryEntry] = []
    selected_ids = {entry.id}
    selected_option_texts = {correct_normalized}

    def add_from_tier(candidates: list[GlossaryEntry]) -> None:
        for candidate in _shuffled_candidates(candidates, picker):
            if len(selected) == 3:
                return
            option_text = candidate.short_definition.strip()
            normalized = _normalize_option_text(option_text)
            if (
                candidate.id in selected_ids
                or candidate.id == entry.id
                or not option_text
                or not normalized
                or normalized in selected_option_texts
            ):
                continue
            selected.append(candidate)
            selected_ids.add(candidate.id)
            selected_option_texts.add(normalized)

    tier_1 = [topic_entries_by_id[confusable_id] for confusable_id in entry.confusable_with if confusable_id in topic_entries_by_id and confusable_id != entry.id]
    tier_1_ids = {candidate.id for candidate in tier_1}
    tier_2 = [
        candidate
        for candidate in topic_entries_by_id.values()
        if candidate.id != entry.id and candidate.id not in tier_1_ids and entry.id in candidate.confusable_with
    ]
    tier_2_ids = {candidate.id for candidate in tier_2}
    tier_3 = [
        candidate
        for candidate in topic_entries_by_id.values()
        if candidate.id != entry.id and candidate.id not in tier_1_ids and candidate.id not in tier_2_ids
    ]

    add_from_tier(tier_1)
    add_from_tier(tier_2)
    add_from_tier(tier_3)

    if len(selected) != 3:
        return None

    options = [correct_option, *(candidate.short_definition.strip() for candidate in selected)]
    if len({_normalize_option_text(option) for option in options}) != 4:
        return None
    picker.shuffle(options)
    correct_index = next((index for index, option in enumerate(options) if _normalize_option_text(option) == correct_normalized), -1)
    if correct_index < 0:
        return None
    return GlossaryQuizQuestion(entry=entry, options=tuple(options), correct_option_index=correct_index)


def build_glossary_answer_keyboard(question: GlossaryQuizQuestion) -> ReplyKeyboardMarkup:
    buttons = [str(index) for index in range(1, len(question.options) + 1)]
    return ReplyKeyboardMarkup(
        [buttons[index : index + 2] for index in range(0, len(buttons), 2)],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def format_glossary_question_text(question: GlossaryQuizQuestion, order_index: int, total_questions: int) -> str:
    option_lines = "\n".join(f"{index}. {escape(option)}" for index, option in enumerate(question.options, start=1))
    return (
        f"<b>Вопрос {order_index} из {total_questions}</b>\n\n"
        "Что означает термин:\n"
        f"<b>{escape(question.entry.term)}</b>\n\n"
        f"{option_lines}\n\n"
        "Ответьте кнопкой с номером варианта внизу 👇"
    )


def build_glossary_feedback_keyboard(has_next: bool) -> ReplyKeyboardMarkup | None:
    if has_next:
        return ReplyKeyboardMarkup([["Далее"]], resize_keyboard=True, one_time_keyboard=False)
    return None


def format_glossary_feedback_text(question: GlossaryQuizQuestion, selected_option_index: int, answered_count: int, total_questions: int) -> str:
    selected_text = question.options[selected_option_index] if 0 <= selected_option_index < len(question.options) else ""
    correct_text = question.options[question.correct_option_index]
    is_correct = selected_option_index == question.correct_option_index
    lines = [
        "<b>Верно ✅</b>" if is_correct else "<b>Неверно ❌</b>",
        "",
        f"<b>Ваш ответ:</b> {selected_option_index + 1} — {escape(selected_text)}",
    ]
    if not is_correct:
        lines.append(f"<b>Правильный ответ:</b> {question.correct_option_index + 1} — {escape(correct_text)}")
    lines.extend(
        [
            "",
            f"<b>Краткое объяснение:</b> {escape(question.entry.definition)}",
            "",
            f"<b>Прогресс:</b> {answered_count} из {total_questions}",
        ]
    )
    return "\n".join(lines)


def format_glossary_result_text(score: int, total_questions: int) -> str:
    return f"<b>Тест завершён</b>\n\n<b>Результат:</b> {score} из {total_questions}"


def build_glossary_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Пройти ещё раз", callback_data="glsq:retry")],
            [InlineKeyboardButton("Назад к темам", callback_data="gls:topics")],
            [InlineKeyboardButton("Главное меню", callback_data="gls:main")],
        ]
    )


def topic_title(topic_id: str) -> str | None:
    return dict(GLOSSARY_TOPICS).get(topic_id)


def callback_token_to_topic_id(token: str) -> str | None:
    return GLOSSARY_TOPIC_CALLBACK_TOKENS.get(token)
