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
- регистрация Telegram commands menu при запуске приложения
- постоянная reply keyboard в private chat (`🎯 Начать викторину`, `ℹ️ Помощь`)
- инициализация SQLite-схемы
- загрузка одобренных вопросов из JSON в SQLite
- сценарий викторины с выбором режима, количества и сложности

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

## Команды и меню

### Команды

- `/start` — приветствие
- `/help` — список команд
- `/ping` — проверка доступности (`pong`)
- `/quiz` — запуск викторины

### Telegram UI

- Telegram commands menu регистрируется автоматически при старте бота.
- В private chat бот показывает постоянную reply keyboard:
  - `🎯 Начать викторину`
  - `ℹ️ Помощь`

## Актуальный flow викторины

Точка входа: `/quiz` (или кнопка `🎯 Начать викторину`).

1. Выбор режима:
   - `Одна тема`
   - `🎲 Микс тем`

2. Если выбран `Одна тема`:
   - выбор категории
   - выбор количества вопросов:
     - `5`
     - `10`
     - `15`
     - `Все доступные`
   - выбор сложности:
     - `Любые`
     - `Только easy`
     - `Только medium`
     - `Только hard`

3. Если выбран `🎲 Микс тем`:
   - выбор количества вопросов (`5`, `10`, `15`, `Все доступные`)
   - выбор сложности (`Любые`, `Только easy`, `Только medium`, `Только hard`)
   - запуск случайной сессии по всем активным темам

4. После каждого ответа:
   - показывается результат (`Верно ✅` / `Неверно ❌`)
   - показывается пояснение
   - доступна кнопка `Дальше`

5. После завершения викторины:
   - `🔁 Пройти еще раз`
   - `🎯 Новая викторина`
   - `ℹ️ Помощь`

## UX вариантов ответа

- Полный список вариантов ответа показывается в тексте вопроса.
- Варианты маркируются буквами `A/B/C/D` (и далее по алфавиту при необходимости).
- Inline-кнопки для выбора ответа тоже показываются в буквенном формате (`A/B/C/D`).
- Внутри приложения обработка выбора остается индексной; для пользователя интерфейс остается буквенным и единообразным.

## Deployment и operations

Ниже — три типовых сценария для сервера с Docker Compose.

### A) Менялся только код (без пересида вопросов)

```bash
git pull
docker compose build psych_quiz_bot
docker compose up -d psych_quiz_bot
docker compose logs -f psych_quiz_bot
```

### B) Полный цикл (код + обновление/проверка вопросов)

Используйте, когда менялись `content/questions/*` или нужно гарантированно пересобрать данные после обновления.

```bash
git pull
docker compose build psych_quiz_bot
docker compose run --rm psych_quiz_bot python scripts/init_db.py
docker compose run --rm psych_quiz_bot python scripts/seed_questions.py
docker compose up -d psych_quiz_bot
docker compose logs -f psych_quiz_bot
```

### C) Чистый прогон на новой SQLite

Используйте для полностью чистой проверки (например, после миграции окружения или при диагностике локальных артефактов БД).

```bash
rm -f ./data/quiz.sqlite3
docker compose run --rm psych_quiz_bot python scripts/init_db.py
docker compose run --rm psych_quiz_bot python scripts/seed_questions.py
docker compose up -d psych_quiz_bot
docker compose logs -f psych_quiz_bot
```

## Docker Compose (кратко)

- Сервис: `psych_quiz_bot`
- Перезапуск: `unless-stopped`
- `./data:/data` — хранение runtime-данных и SQLite
- `./content:/app/content:ro` — контент только для чтения
- Порты не публикуются (бот работает через исходящие запросы long polling)
