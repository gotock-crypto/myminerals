# Minerals Bot

Telegram-бот для автоматической подготовки и публикации содержательных постов о минералах, кристаллах и камнях.

## Что делает бот

Бот объединяет четыре независимых этапа:

1. **Выбор минерала и темы** — используется локальный список минералов и типов контента.
2. **Редакционный агент** — готовит текст в три прохода:
   - **Pass 1 — Groq**: авторский черновик;
   - **Pass 2 — Mistral**: фактчек и список исправлений;
   - **Pass 3 — Mistral**: финальный редактор, который собирает готовый Telegram-пост.
3. **Поиск изображения** — отдельный от генерации текста этап. Основной источник — Wikimedia Commons; при наличии настроек могут использоваться Google Custom Search и HTML-поиск.
4. **Публикация в Telegram** — фотография и полный текст отправляются отдельными сообщениями. Это позволяет не терять текст из-за ограничения подписи к фотографии.

## Редакционный pipeline

```text
Минерал + тема + источник
          │
          ▼
┌─────────────────────────┐
│ PASS 1 — Автор          │
│ Groq / Qwen             │
│ Черновик поста           │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ PASS 2 — Фактчекер       │
│ Mistral                  │
│ Ошибки и исправления     │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ PASS 3 — Финальный       │
│ редактор / Mistral       │
│ Готовый Telegram-пост    │
└────────────┬────────────┘
             │
             ▼
      Локальный validator
             │
             ▼
       Telegram publish
```

Модели работают с обычным текстовым ответом. Provider-side JSON mode для редакционных проходов не требуется: это позволяет использовать OpenAI-compatible endpoints без зависимости от их поддержки `response_format`.

## Требования

- Python 3.10+
- Telegram Bot API
- Groq API — рекомендуется для первого прохода
- Mistral API — используется для фактчека и финального редактирования
- Интернет-доступ с сервера для Wikipedia / Wikimedia Commons и, при необходимости, Google Search

## Установка

```bash
git clone https://github.com/gotock-crypto/myminerals.git
cd myminerals
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Создайте `.env` на сервере. Не добавляйте реальные секреты в Git.

Минимальная конфигурация:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=@myminerals
ADMIN_CHAT_ID=
LOCAL_TZ=Europe/Moscow
POST_TIMES=09:00,18:00
AUTO_ENABLED=0

GROQ_API_KEY=
GROQ_MODEL=qwen/qwen3.6-27b
MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-small-latest
LLM_TIMEOUT=90
LLM_MAX_TOKENS=1800
```

Полный шаблон параметров находится в [`.env.example`](.env.example).

## Конфигурация LLM

### Groq

```dotenv
GROQ_API_KEY=...
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=qwen/qwen3.6-27b
```

Groq является предпочтительным провайдером для первого прохода. Если он недоступен, код может использовать другой настроенный provider.

### Mistral

```dotenv
MISTRAL_API_KEY=...
MISTRAL_BASE_URL=https://api.mistral.ai/v1
MISTRAL_MODEL=mistral-small-latest
```

Mistral используется как основной provider для второго и третьего проходов.

## Проверка фактов

В проекте есть отдельный фактчек-контур. Он может использовать внешние источники и проверяет утверждения перед публикацией.

```dotenv
FACT_CHECK_ENABLED=1
FACT_CHECK_THRESHOLD=0.72
```

Эзотерическая часть поста отделяется от научно подтверждённых свойств и сопровождается обязательной оговоркой:

> Традиционные представления, не научно доказанные свойства.

Бот не должен превращать эзотерические традиции в медицинские или научные утверждения.

## Формат поста

Редактор формирует компактный русскоязычный Telegram-пост. В стандартной структуре используются:

- `🔹 Основные характеристики`
- `🌍 Где встречается`
- `✨ Интересный факт`
- `💎 Применение`
- `🔮 Эзотерические свойства`

Финальный текст проходит локальную проверку структуры, длины, обязательного disclaimer и запрещённых медицинских формулировок.

## Изображения

Поиск изображений отделён от LLM-генерации. Для Wikimedia Commons бот проверяет размер и техническую пригодность изображения, сохраняет сведения об источнике и лицензии и использует дополнительные проверки дубликатов.

Основные параметры:

```dotenv
WIKIMEDIA_ENABLED=1
STRICT_LICENSE=0
IMAGE_MIN_WIDTH=700
IMAGE_MIN_HEIGHT=700
IMAGE_MIN_BYTES=25000
IMAGE_MAX_BYTES=12582912
IMAGE_TIMEOUT=25
IMAGE_CANDIDATES=24
IMAGE_DOWNLOAD_CANDIDATES=16
```

## База данных

По умолчанию используется SQLite-файл `minerals.db`.

В базе хранятся:

- настройки;
- список минералов;
- опубликованные и черновые посты;
- найденные изображения;
- URL источников и лицензии;
- хеши изображений для защиты от повторов;
- состояние планировщика.

Файл базы является runtime-данными и **не должен попадать в Git**.

## Автопубликация

Автопубликация управляется через `.env` и настройки бота:

```dotenv
AUTO_ENABLED=1
POST_TIMES=09:00,18:00
LOCAL_TZ=Europe/Moscow
```

Для ручного режима оставьте:

```dotenv
AUTO_ENABLED=0
```

## Systemd

Пример unit-файла находится в [`minerals-bot.service`](minerals-bot.service).

Типовая установка:

```bash
sudo cp minerals-bot.service /etc/systemd/system/minerals-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now minerals-bot
```

Проверка:

```bash
systemctl status minerals-bot --no-pager -l
journalctl -u minerals-bot -f
```

## Обновление существующего сервера

Если проект уже установлен в `/opt/minerals-bot/minerals_project`, безопасная схема обновления:

```bash
cd /opt/minerals-bot/minerals_project
systemctl stop minerals-bot
cp -a . ../minerals_project.backup-$(date +%Y%m%d-%H%M%S)
git fetch origin
git reset --hard origin/main
./venv/bin/pip install -r requirements.txt
./venv/bin/python -m py_compile main.py
systemctl start minerals-bot
systemctl status minerals-bot --no-pager -l
```

**Важно:** `.env` и `minerals.db` являются локальными runtime-данными. Перед обновлением убедитесь, что они не отслеживаются Git и не заменяются содержимым репозитория.

## Диагностика

### Сервис не запускается

```bash
systemctl status minerals-bot --no-pager -l
journalctl -u minerals-bot -n 100 --no-pager
```

### Проверка синтаксиса

```bash
./venv/bin/python -m py_compile main.py
```

### LLM-проблемы

Ищите в журнале:

```text
LLM success provider=...
```

Ошибки `400`, `401`, `429` и сетевые ошибки показывают, какой provider не прошёл запрос. При `429` обычно требуется уменьшить частоту/размер запросов или дождаться сброса лимита.

### Проверка публикации

```bash
journalctl -u minerals-bot -f
```

Успешная генерация должна пройти все три редакционных прохода, после чего бот публикует фото и полный текст отдельными сообщениями.

## Безопасность

Никогда не коммитьте:

- `.env`;
- API-ключи;
- Telegram Bot Token;
- `minerals.db`;
- локальные backup-каталоги;
- логи с секретами.

Для этого используйте `.gitignore`.

## Структура проекта

```text
.
├── main.py                 # основной Telegram-бот и pipeline
├── requirements.txt        # Python-зависимости
├── minerals-bot.service    # systemd unit
├── .env.example            # шаблон конфигурации
├── .gitignore              # исключения Git
├── README.md               # документация
└── minerals.db             # runtime SQLite, не хранить в Git
```

## Версия

**Minerals Bot v3.0.2 — 3-pass plain-text Editorial Agent**

Текущая редакционная архитектура: **Groq author → Mistral fact checker → Mistral final editor → validator → Telegram**.

## Лицензия

Проект распространяется по лицензии MIT. См. [`LICENSE`](LICENSE).
