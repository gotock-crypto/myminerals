# 💎 MyMinerals — AI Telegram Content Pipeline

Автономный контентный pipeline для Telegram-канала о минералах и камнях.

Проект генерирует публикации с помощью LLM, подбирает **реальные фотографии минералов** из внешних источников и автоматически публикует материал в Telegram.

## Что делает pipeline

```text
Scheduler
   ↓
Mineral selection
   ↓
Fact context
   ↓
LLM — готовый Telegram-пост
   ↓
Real image discovery
   ├── Google Images
   └── Wikimedia Commons
   ↓
Image validation / ranking / deduplication
   ↓
Telegram
   ├── 📷 photo
   └── 📝 full text
```

### Контент

LLM пишет **весь текст целиком одним вызовом**. Формат рассчитан на Telegram-публикацию с медиа, поэтому промпт просит писать компактно, содержательно и без лишней воды.

В посте остаются два основных раздела:

- 🔹 **Основные характеристики** — минералогические и справочные сведения.
- 🔮 **Эзотерические свойства** — традиционные представления о камне с явным отделением их от научных фактов.

Текст не обрезается под лимит caption: фотография публикуется отдельным сообщением, а полный текст — следующим сообщением.

### Изображения

Pipeline ищет **реальные фотографии**, а не генерирует изображения.

При поиске:

- приоритет у natural / mineral / rough / crystal specimen;
- украшения, иллюстрации, рендеры и каталожные изображения штрафуются;
- Wikimedia Commons может использоваться как лицензированный источник;
- URL, источник, лицензия, SHA-256 и perceptual hash сохраняются в SQLite;
- повторно использованные или визуально похожие изображения штрафуются.

> Наличие изображения в Google Images не означает наличие права на перепубликацию. Для production-использования рекомендуется отдавать приоритет источникам с понятной лицензией.

## Стек

- Python 3.12+
- python-telegram-bot
- Requests
- Pillow
- SQLite
- Groq / OpenAI-compatible API
- Mistral API
- Google Images / Custom Search (если настроен)
- Wikimedia Commons API

## Конфигурация

Скопировать `.env.example` в `.env` и заполнить секреты:

```bash
cp .env.example .env
```

Ключевые параметры:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=@myminerals
ADMIN_CHAT_ID=

GROQ_API_KEY=
GROQ_MODEL=qwen/qwen3.6-27b

MISTRAL_API_KEY=
MISTRAL_MODEL=mistral-small-latest

GOOGLE_CSE_API_KEY=
GOOGLE_CSE_ID=
GOOGLE_HTML_ENABLED=1

WIKIMEDIA_ENABLED=1
STRICT_LICENSE=0

LOCAL_TZ=Europe/Moscow
POST_TIMES=09:00,18:00
AUTO_ENABLED=0
```

## Локальный запуск

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m py_compile main.py
python main.py
```

Тест в Telegram:

```text
/test аметист
```

## Production / systemd

Пример service unit находится в `minerals-bot.service`.

```bash
sudo cp minerals-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable minerals-bot
sudo systemctl start minerals-bot
```

Логи:

```bash
journalctl -u minerals-bot -f
```

## Безопасность

Секреты хранятся только в `.env` и **не должны попадать в Git**.

База `minerals.db` также является локальным runtime-артефактом и не входит в репозиторий.
