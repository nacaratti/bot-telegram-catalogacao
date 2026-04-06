# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SisCatLaMP** is an async Telegram bot for laboratory/warehouse inventory management. It uses LLMs (Google Gemini + OpenAI fallback) to interpret natural language messages, extract item details, and persist them to SQLite.

## Running the Bot

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in credentials
python main.py
```

Required environment variables (`.env`):
- `BOT_TOKEN` — Telegram bot token
- `GEMINI_API_KEY` — Google Gemini API key
- `OPENAI_API_KEY` — OpenAI API key (fallback)

There are no lint or test commands configured.

## Architecture

```
main.py → bot_handlers.py → ai_agent.py → database.py / models.py
                         ↘ media_processor.py (audio/image)
```

**main.py** — Entry point. Loads env, initializes DB, starts Aiogram polling.

**bot_handlers.py** — All Telegram handlers (commands, text, voice, photo). Uses Aiogram FSM to track per-user state across message turns. States: `waiting_confirmation`, `waiting_description_edit`. Inline keyboard buttons drive the confirmation/edit/cancel flow.

**ai_agent.py** — Core LLM logic. Calls Gemini (`process_with_gemini`) or falls back to OpenAI (`process_with_openai`). Classifies intent as one of:
- `CADASTRO` — new item to register (extracts structured fields)
- `CORRECAO` — user is editing a pending item in FSM state
- `PERGUNTA` — inventory question answered via `consultar_estoque()` SQL tool

The Pydantic `ItemSchema` is used for structured output from the LLM. `consultar_estoque()` runs read-only SQL against the live DB (blocks DROP/DELETE/UPDATE/ALTER/INSERT).

**media_processor.py** — `process_audio()` transcribes OGG voice messages with OpenAI Whisper. `process_image()` compresses photos to WebP via FFmpeg.

**database.py / models.py** — SQLAlchemy setup. Single `Item` table with fields: `tipo, descricao, quantidade, patrimonio, local, foto_path, usuario_id, data_registro`.

**parser.py** — Regex fallback parser; not used in the current flow (LLM handles parsing).

## User Flow

1. User sends text, voice, or photo to the bot.
2. Voice → Whisper transcription; Photo → FFmpeg compression, caption forwarded.
3. LLM detects intent and extracts item fields into `ItemSchema`.
4. Bot sends a summary with inline buttons: Confirm / Edit Description / Add Photo / Cancel.
5. Confirm → item saved to `inventory.db`.

## File Storage

- `media/fotos/` — compressed WebP photos (persisted)
- `media/audio_tmp/` — temporary OGG/WAV files (ephemeral)
- `inventory.db` — SQLite database
