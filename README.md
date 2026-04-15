# psychology-quiz

Telegram-бот викторины для студентов-психологов. Проект запускается как отдельный Docker Compose сервис на Ubuntu-сервере, использует **long polling** (без webhook), базу данных SQLite и хранит рабочие данные в смонтированной директории `/data`.

## Цель проекта

Собрать простой, читаемый и расширяемый каркас бота для учебной викторины по психологии.

## Объем v1

Текущая версия (v1) покрывает только **модуль 1**:

- Введение в профессию
- Общая психология
- Физиология человека
- Физиология ВНД

В v1 реализованы:

- базовый Telegram-бот с командами `/start`, `/help`, `/ping`, `/quiz`
- инициализация SQLite-схемы
- загрузка одобренных вопросов из JSON в SQLite
- сценарий викторины на серию вопросов по выбранной категории (до 10 за сессию)

## Явно вне scope

- Контент или сценарии, связанные с **PM (Project Management)**, в проект не входят.
- Бот использует только учебный контент по психологии и исключает Obsidian PM layer.
- Web UI отсутствует.
- Webhook отсутствует.
- RAG/внешние retrieval-механизмы отсутствуют.

## Структура хранения данных

- Путь к БД задается через `DB_PATH`.
- По умолчанию: `/data/quiz.sqlite3`.
- В Docker Compose директория `./data` монтируется в контейнер как `/data`, поэтому БД и runtime-данные сохраняются между перезапусками.

### Вопросы модуля 1

Вопросы хранятся по категориям в папке `content/questions/module1/`:

- `obschaya_psihologiya.json`
- `vvedenie_v_professiyu.json`
- `fiziologiya_cheloveka.json`
- `fiziologiya_vnd.json`

Скрипт `scripts/seed_questions.py` автоматически читает все `*.json` из этой папки в алфавитном порядке, валидирует вопросы и загружает в БД только записи со статусом `approved`.
Практико-ориентированные вопросы распределяются по тематическим файлам категорий, а не выделяются в отдельную категорию викторины.

## Локальный запуск (без Docker)

1. Создайте и заполните `.env`:

```bash
cp .env.example .env
# Укажите BOT_TOKEN (обязательно)
```

2. Создайте виртуальное окружение и установите зависимости:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

3. Инициализируйте БД:

```bash
python scripts/init_db.py
```

4. Загрузите одобренные вопросы в БД:

```bash
python scripts/seed_questions.py
```

5. Запустите бота:

```bash
python -m app.main
```

## Запуск на Ubuntu сервере через Docker Compose

1. Установите Docker Engine и Docker Compose Plugin.
2. В корне проекта создайте `.env` из примера и заполните переменные.
3. Выполните последовательность запуска:

```bash
docker compose run --rm psych_quiz_bot python scripts/init_db.py
docker compose run --rm psych_quiz_bot python scripts/seed_questions.py
docker compose up -d
```

4. Посмотрите логи:

```bash
docker compose logs -f psych_quiz_bot
```

## Команды бота

- `/start` — приветствие
- `/help` — список команд
- `/ping` — проверка доступности (`pong`)
- `/quiz` — запуск викторины: выбор категории → сессия до 10 вопросов без повторов → итоговый результат

## Docker Compose (кратко)

- Сервис: `psych_quiz_bot`
- Перезапуск: `unless-stopped`
- `./data:/data` — хранение runtime-данных и SQLite
- `./content:/app/content:ro` — контент только для чтения
- Порты не публикуются (бот работает через исходящие запросы long polling)
