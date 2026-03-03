import inspect
import re
from collections.abc import Callable
from re import Pattern

from vk_bot import types
from vk_bot.util import extract_command


class Handler:
    def __init__(self, callback: Callable, **filters):
        self.callback = callback
        self.filters = filters

        sig = inspect.signature(callback)
        self.accepts_state = len(sig.parameters) >= 2

    def check(self, update: types.Update) -> bool:
        return True


class MessageHandler(Handler):
    def __init__(
        self,
        callback: Callable,
        commands: list[str] | None = None,
        regexp: str | Pattern | None = None,
        func: Callable | None = None,
        content_types: list[str] | None = None,
        chat_types: list[str] | None = None,
        state: str | list[str] | None = None,
        **kwargs,
    ):
        super().__init__(callback, **kwargs)

        self.commands = [cmd.lower() for cmd in commands] if commands else None
        self.regexp = re.compile(regexp) if isinstance(regexp, str) else regexp
        self.func = func
        self.content_types = content_types or ["text"]
        self.chat_types = chat_types
        self.state = state

    def check(self, update: types.Update, current_state: str | None = None) -> bool:
        if not update.message:
            return False

        message = update.message

        if self.state is not None:
            if isinstance(self.state, list):
                if current_state not in self.state:
                    return False
            elif self.state != current_state:
                return False

        if self.chat_types and message.chat.type not in self.chat_types:
            return False

        if message.content_type not in self.content_types:
            return False

        if self.func and not self.func(message):
            return False

        if self.commands:
            if not message.text:
                return False

            cmd, _ = extract_command(message.text)
            if not cmd or cmd not in self.commands:
                return False

        if self.regexp:
            if not message.text:
                return False
            if not self.regexp.search(message.text):
                return False

        return True


class CallbackQueryHandler(Handler):
    def __init__(
        self,
        callback: Callable,
        func: Callable | None = None,
        data: str | Pattern | None = None,
        state: str | list[str] | None = None,
        **kwargs,
    ):
        super().__init__(callback, **kwargs)
        self.func = func
        self.data = re.compile(data) if isinstance(data, str) else data
        self.state = state

    def check(self, update: types.Update, current_state: str | None = None) -> bool:
        if not update.callback_query:
            return False

        cb = update.callback_query

        if self.state is not None:
            if isinstance(self.state, list):
                if current_state not in self.state:
                    return False
            elif self.state != current_state:
                return False

        if self.func and not self.func(cb):
            return False

        if self.data:
            if not cb.data:
                return False
            if not self.data.search(cb.data):
                return False
        return True


class ChatMemberHandler(Handler):
    def __init__(
        self,
        callback: Callable,
        func: Callable | None = None,
        event_types: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(callback, **kwargs)
        self.func = func
        self.event_types = event_types or [
            "group_join",
            "group_leave",
            "group_change_settings",
        ]

    def check(self, update: types.Update) -> bool:
        if update.type not in self.event_types:
            return False

        if self.func and not self.func(update):
            return False

        return True


class MiddlewareHandler(Handler):
    def __init__(self, callback: Callable, update_types: list[str] | None = None):
        super().__init__(callback)
        self.update_types = update_types

    def check(self, update: types.Update) -> bool:
        if self.update_types and update.type not in self.update_types:
            return False
        return True

    def process(self, bot, update: types.Update):
        return self.callback(bot, update)
