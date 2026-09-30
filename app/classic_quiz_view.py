"""Pure Telegram quiz presentation, independent of attempt storage and handlers."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from app.bot_menu import START_QUIZ_BUTTON_TEXT
from app.quiz_text import option_index_to_label, render_reading_mode_text


QUESTION_COUNT_CHOICES = (
    (5, "5"),
    (10, "10"),
    (15, "15"),
    (None, "Все доступные"),
)

DIFFICULTY_CHOICES = (
    ("any", "Любые"),
    ("easy", "Лёгкие"),
    ("medium", "Средние"),
    ("hard", "Сложные"),
)

CLASSIC_REPLY_NEXT_TEXT = "Далее"

def build_question_count_keyboard(
    callback_prefix: str, category_id: int | None = None, *, difficulty: str | None = None,
) -> InlineKeyboardMarkup:
    mode_prefix = {"qcnt": "qmode", "qcntall": "qmodeall", "qcntselmix": "qmodeselmix"}[callback_prefix]
    mode = difficulty or "any"
    if mode not in {"any", "easy", "medium", "hard"}:
        raise ValueError("Unknown difficulty")
    scope = "" if category_id is None else f"{category_id}:"
    keyboard = []
    for count, label in QUESTION_COUNT_CHOICES:
        count_value = "all" if count is None else str(count)
        callback_data = f"{mode_prefix}:{scope}{count_value}:{mode}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton(
        "Настроить сложность (необязательно)" if difficulty is None else "Изменить сложность",
        callback_data=f"{callback_prefix}:{scope}choose",
    )])
    return InlineKeyboardMarkup(keyboard)

def build_difficulty_keyboard(callback_prefix: str, category_id: int | None = None, count_raw: str | None = None) -> InlineKeyboardMarkup:
    keyboard = []
    for mode, label in DIFFICULTY_CHOICES:
        callback_data = f"{callback_prefix}:{count_raw}:{mode}" if category_id is None else f"{callback_prefix}:{category_id}:{count_raw}:{mode}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback_data)])
    return InlineKeyboardMarkup(keyboard)

def build_category_keyboard(categories) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(str(row["name"]), callback_data=f"cat:{int(row['id'])}")] for row in categories])

def build_quiz_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Конкретная тема", callback_data="qzmode:single")], [InlineKeyboardButton("Микс из выбранных тем", callback_data="qzmode:selected_mix")], [InlineKeyboardButton("Все темы", callback_data="qzmode:all")]])

def build_selected_mix_keyboard(categories, selected_ids: set[int]) -> InlineKeyboardMarkup:
    keyboard = []
    for row in categories:
        category_id = int(row["id"])
        marker = "✅" if category_id in selected_ids else "☑️"
        keyboard.append([[InlineKeyboardButton(f"{marker} {row['name']}", callback_data=f"mixsel:toggle:{category_id}")][0]])
    keyboard.append([InlineKeyboardButton("Готово", callback_data="mixsel:done")])
    keyboard.append([InlineKeyboardButton("Сбросить", callback_data="mixsel:reset")])
    return InlineKeyboardMarkup(keyboard)

def build_quiz_finished_text(score: int, total_questions: int, homework_outcome=None) -> str:
    if homework_outcome is not None:
        mark = "Выполнено ✅" if homework_outcome["passed"] else "Пока не выполнено"
        return ("<b>Тест домашнего задания завершён</b>\n\n"
                f"<b>Результат:</b> {score} из {total_questions}. {mark}\n\n"
                "Отметка относится только к тесту, не к эссе или упражнению. "
                "Откройте /homework для просмотра заданий и повторной попытки.")
    return ("<b>Викторина завершена 🎉</b>\n\n" f"<b>Результат:</b> {score} из {total_questions}\n\n" f"Чтобы начать новую викторину, нажмите {START_QUIZ_BUTTON_TEXT} или отправьте /quiz.")

def build_classic_answer_reply_keyboard(options) -> ReplyKeyboardMarkup:
    buttons = [str(position) for position, _ in enumerate(options, start=1)]
    keyboard = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    keyboard.append(["Не знаю"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def build_classic_next_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[CLASSIC_REPLY_NEXT_TEXT]], resize_keyboard=True, one_time_keyboard=False)

def numeric_answer_label_for_option(options, option_index: int) -> str:
    for position, opt in enumerate(options, start=1):
        if int(opt["option_index"]) == option_index:
            return str(position)
    raise ValueError("option_index is not present in options")

def build_classic_reply_answer_detail_line(label: str, *, option_position_label: str, option_text: str, reading_mode: str) -> str:
    rendered_option_text = render_reading_mode_text(option_text, reading_mode)
    return f"<b>{label}:</b> {option_position_label} — {rendered_option_text}"

def build_classic_reply_feedback_text(result: dict) -> str:
    result_line = "<b>Верно ✅</b>" if result["is_correct"] else "<b>Неверно ❌</b>"
    answer_lines = [build_classic_reply_answer_detail_line("Ваш ответ", option_position_label=str(result["selected_option_label"]), option_text=str(result["selected_option_text"]), reading_mode=str(result["reading_mode"]))]
    if not result["is_correct"]:
        answer_lines.append(build_classic_reply_answer_detail_line("Правильный ответ", option_position_label=str(result["correct_option_label"]), option_text=str(result["correct_option_text"]), reading_mode=str(result["reading_mode"])))
    rendered_explanation = render_reading_mode_text(result["explanation"], result["reading_mode"])
    answer_lines_text = "\n".join(answer_lines)
    review = format_case_review_html(result.get("case_review"), result["reading_mode"])
    return f"{result_line}\n\n{answer_lines_text}\n\n<b>Пояснение:</b>\n{rendered_explanation}{review}\n\n<b>Прогресс:</b> {result['answered_questions']} из {result['total_questions']}"

def format_case_review_html(case: dict | None, reading_mode: str) -> str:
    if not case:
        return ""
    render = lambda value: render_reading_mode_text(value, reading_mode)
    conditions = "\n".join("• " + render(value) for value in case["conditions"])
    alternatives = "\n".join(f"{index}. {render(value)}" for index, value in enumerate(case["option_rationales"], 1))
    return (f"\n\n<b>Разбор кейса:</b> {render(case['approach'])}"
            f"\n<b>Условия:</b>\n{conditions}"
            f"\n<b>Варианты действий:</b>\n{alternatives}"
            f"\n<b>Неоднозначность:</b> {render(case['ambiguity'])}")

def parse_classic_reply_answer_number(text: str, option_count: int) -> int | None:
    cleaned = text.strip()
    if not cleaned.isdigit():
        return None
    answer_number = int(cleaned)
    if not 1 <= answer_number <= option_count:
        return None
    return answer_number - 1

def build_question_text_with_options(order_index: int, total_questions: int, question_text: str, options, reading_mode: str, *, numeric_labels: bool = False, show_answer_keyboard_hint: bool = False) -> str:
    formatted_options = "\n".join(f"{position if numeric_labels else option_index_to_label(int(opt['option_index']))}. {render_reading_mode_text(str(opt['option_text']), reading_mode)}" for position, opt in enumerate(options, start=1))
    hint = "\n\nОтветьте кнопкой с номером варианта внизу 👇" if show_answer_keyboard_hint else ""
    return f"<b>Вопрос {order_index} из {total_questions}</b>\n\n{render_reading_mode_text(question_text, reading_mode)}\n\n{formatted_options}{hint}"
