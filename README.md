# Minerals Bot v3.0.0 — 3-pass Editorial Agent

Pipeline: Groq author -> Mistral fact checker -> Mistral final editor. Image search/picking stays separate. Telegram sends the photo and the complete text as separate messages, avoiding media-caption truncation.

Keep the existing `.env` on the server.
