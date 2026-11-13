"""Compose Telegram bot callbacks with KhoAI persistence and services."""
from __future__ import annotations
import logging
from .bot import TelegramBot, TelegramContext, load_config
from .persistence_schema import ensure_telegram_schema
from .persistence_queries import build_query_callbacks
from .persistence_delivery import build_delivery_callbacks

logger = logging.getLogger("khoai.telegram")


def build_telegram_bot(backend_services) -> TelegramBot | None:
    """Build the bot from explicitly supplied persistence/application services."""
    config = load_config()
    if config is None:
        return None

    ensure_telegram_schema(backend_services, config)
    callbacks = {
        **build_query_callbacks(backend_services),
        **build_delivery_callbacks(backend_services),
    }
    context = TelegramContext(
        callbacks["status"], callbacks["alerts"], callbacks["acknowledge"],
        callbacks["acknowledge_all"], callbacks["snapshot"], callbacks["event_evidence"],
        callbacks["discover_events"], callbacks["due_items"], callbacks["mark_text"],
        callbacks["retry_text"], callbacks["mark_photo"], callbacks["lease"],
        callbacks["retry_permanent"], callbacks["ops_status"], callbacks["runtime_state"],
    )
    return TelegramBot(config, context)
