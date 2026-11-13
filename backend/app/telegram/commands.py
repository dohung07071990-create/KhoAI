"""Compatibility facade for Telegram command, callback, and polling mixins."""
from .command_handlers import TelegramCommandHandlersMixin
from .callbacks import TelegramCallbackMixin
from .polling import TelegramPollingMixin

class TelegramCommandMixin(
    TelegramCommandHandlersMixin, TelegramCallbackMixin, TelegramPollingMixin
):
    """Backward-compatible composition of Telegram command responsibilities."""

