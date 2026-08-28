# 💎 MyMinerals — 3-pass AI Telegram Content Pipeline

Автономный контентный pipeline для Telegram-канала о минералах и камнях.

## Архитектура контента

```text
Scheduler / /test
      ↓
Выбор минерала
      ↓
Русская Wikipedia — фактический контекст
      ↓
PASS 1 — Groq/Qwen — автор
      ↓
PASS 2 — Mistral — фактчекер
      ↓
PASS 3 — Mistral — финальный редактор
      ↓
Локальный валидатор
      ↓
Wikimedia Commons + Google Images
      ↓
Проверка изображения / ranking / deduplication
      ↓
Telegram
   ├── 📷 фото
   └── 📝 полный текст
```

### 3-pass editorial agent

Генерация не зависит от provider-side JSON mode: LLM получает обычный текстовый запрос и возвращает обычный текст. Это избегает проблем совместимости `response_format=json_object` с Groq/Qwen.

1. **Автор (Groq)** создаёт черновик.
2. **Фактчекер (Mistral)** проверяет факты, структуру, повторы, обрывы и безопасность формулировок.
3. **Финальный редактор (Mistral)** полностью переписывает материал в готовый Telegram-пост.
4. Локальный валидатор проверяет обязательные разделы, длину, финальную фразу и отсутствие reasoning/медицинских обещаний.

Если Groq недоступен или упирается в лимит, используется Mistral fallback. Для редакционных проходов предпочтительная схема — `Groq → Mistral → Mistral`, чтобы не расходовать TPM Groq на повторные попытки.

### Формат поста

Финальный пост содержит пять разделов:

- 🔹 **Основные характеристики**
- 🌍 **Где встречается**
- ✨ **Интересный факт**
- 💎 **Применение**
- 🔮 **Эзотерические свойства**

Эзотерические утверждения отделяются от научных фактов и завершаются фразой:

> Традиционные представления, не научно доказанные свойства.

Текст публикуется отдельным Telegram-сообщением после фотографии. Это исключает обрезание длинного текста из-за ограничения media caption.

## Изображения

Pipeline ищет реальные фотографии минералов, а не генерирует изображения.

При поиске:

- приоритет у natural / mineral / rough / crystal specimen;
- изображения проверяются по фактическим пикселям, размеру и формату;
- украшения, иллюстрации и нерелевантные изображения штрафуются;
- Wikimedia Commons используется как основной источник с понятной лицензией;
- Google Images может использоваться как дополнительный источник;
- URL, источник, лицензия, SHA-256 и perceptual hash сохраняются в SQLite;
- повторно использованные и визуально похожие изображения отбраковываются/штрафуются.

> Наличие изображения в Google Images само по себе не означает наличие права на перепубликацию. Для production-использования следует отдавать приоритет источникам с понятной лицензией.

## Стек

- Python 3.12+
- python-telegram-bot
- Requests
- Pillow
- SQLite
- Groq / OpenAI-compatible API
- Mistral API
- Google Images / Custom Search
- Wikimedia Commons API
- Wikipedia API

## Конфигурация

Секреты хранятся только в `.env` и не должны попадать в Git.

Основные параметры:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_ID=@myminerals
ADMIN_CHAT_ID=
LOCAL_TZ=Europe/Moscow
POST_TIMES=09:00,18:00
AUTO_ENABLED=0

GROQ_API_KEY=
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=qwen/qwen3.6-27b

MISTRAL_API_KEY=
MISTRAL_BASE_URL=https://api.mistral.ai/v1
MISTRAL_MODEL=mistral-small-latest

LLM_TIMEOUT=90
LLM_MAX_TOKENS=2200
FACT_CHECK_ENABLED=1
FACT_CHECK_THRESHOLD=0.72

GOOGLE_CSE_API_KEY=
GOOGLE_CSE_ID=
GOOGLE_HTML_ENABLED=1

WIKIMEDIA_ENABLED=1
STRICT_LICENSE=0
```

## Локальный запуск

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m py_compile main.py
python main.py
```

Тест:

```text
/test кварц
```

## Production / systemd

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

База `minerals.db` является локальным runtime-артефактом и не входит в репозиторий.
