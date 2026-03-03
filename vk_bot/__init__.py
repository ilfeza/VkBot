__version__ = "0.2.0"

import json
import re
import time
from collections.abc import Callable
from typing import Any

from vk_bot import apihelper, exception, types, util
from vk_bot.apihelper import ApiClient
from vk_bot.config import HttpConfig, Token
from vk_bot.handlers import CallbackQueryHandler, MessageHandler, MiddlewareHandler
from vk_bot.http_client import HttpClient
from vk_bot.state.context import StateContext
from vk_bot.state.fsm import FSMRegistry, VKBotFSM
from vk_bot.state.group import StatesGroup
from vk_bot.state.manager import StateManager
from vk_bot.state.storage import (
    BaseStorage,
    MemoryStorage,
    PostgresStorage,
    RedisStorage,
)


class VKBot:
    """Main bot class for VK API interaction.

    Provides an interface for sending messages, handling Long Poll
    events, and managing user states (FSM).

    Args:
        token: VK community token.
        group_id: Community ID. Resolved automatically if not provided.
        state_storage: State storage backend (defaults to MemoryStorage).
        http_config: HTTP transport configuration (proxy, timeouts, retries).
    """

    def __init__(
        self,
        token: str | None = None,
        group_id: int | None = None,
        state_storage: BaseStorage | None = None,
        http_config: HttpConfig | None = None,
    ):
        if not token:
            raise ValueError("token must be provided")
        self.api = ApiClient(token=Token(token), http=HttpClient(http_config))

        self._group_id = group_id
        self._me: types.User | None = None
        self.message_handlers: list[MessageHandler] = []
        self.callback_query_handlers: list[CallbackQueryHandler] = []
        self.middleware_handlers: list[MiddlewareHandler] = []
        self.lp_server: apihelper.LongPollServer | None = None
        self._polling = False
        self.state_manager = StateManager(state_storage or MemoryStorage())

    @property
    def token(self) -> str:
        return str(self.api.token)

    @property
    def group_id(self) -> int:
        if self._group_id is None:
            self._group_id = self.api.get_group_id()
        return self._group_id

    @property
    def me(self) -> types.User:
        if not self._me:
            data = self.api.get_me()
            self._me = types.User(**data)
        return self._me

    def get_state(self, user_id: int) -> str | None:
        return self.state_manager.get_state(user_id)

    def set_state(self, user_id: int, state: str):
        self.state_manager.set_state(user_id, state)

    def get_state_data(self, user_id: int) -> dict[str, Any]:
        return self.state_manager.get_data(user_id)

    def update_state_data(self, user_id: int, **kwargs):
        self.state_manager.update_data(user_id, **kwargs)

    def reset_state(self, user_id: int):
        self.state_manager.reset(user_id)

    def _get_state_context(self, user_id: int) -> StateContext:
        return StateContext(self, user_id)

    def message_handler(
        self,
        commands: list[str] | None = None,
        regexp: str | None = None,
        func: Callable | None = None,
        content_types: list[str] | None = None,
        chat_types: list[str] | None = None,
        state: str | list[str] | None = None,
    ):
        """Decorator for registering incoming message handlers.

        Args:
            commands: List of commands (without '/'), e.g. ['start', 'help'].
            regexp: Regular expression for text filtering.
            func: Custom filter function (takes Message, returns bool).
            content_types: Content types ('text', 'photo', 'doc', etc.).
            chat_types: Chat types ('private', 'group').
            state: FSM state(s) that trigger this handler.
        """

        def decorator(handler):
            handler_obj = MessageHandler(
                callback=handler,
                commands=commands,
                regexp=regexp,
                func=func,
                content_types=content_types,
                chat_types=chat_types,
                state=state,
            )
            self.message_handlers.append(handler_obj)
            return handler

        return decorator

    def callback_query_handler(
        self,
        func: Callable | None = None,
        data: str | re.Pattern | None = None,
        state: str | list[str] | None = None,
    ):
        """Decorator for handling callback events (inline button presses).

        Handles ``message_event`` type events from VK API.

        Args:
            func: Custom filter function (takes CallbackQuery).
            data: String or regex pattern for callback_data filtering.
            state: FSM state(s) that trigger this handler.
        """

        def decorator(handler):
            handler_obj = CallbackQueryHandler(
                callback=handler, func=func, data=data, state=state
            )
            self.callback_query_handlers.append(handler_obj)
            return handler

        return decorator

    def middleware_handler(self, update_types: list[str] | None = None):
        """Decorator for registering middleware.

        Middleware is called before handlers. If it returns False,
        event processing is stopped.

        Args:
            update_types: Event types to filter (None = all).
        """

        def decorator(handler):
            handler_obj = MiddlewareHandler(callback=handler, update_types=update_types)
            self.middleware_handlers.append(handler_obj)
            return handler

        return decorator

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: types.ReplyKeyboardMarkup
        | types.InlineKeyboardMarkup
        | None = None,
        reply_to: int | None = None,
        **kwargs,
    ) -> dict:
        """Send a text message to a user or chat.

        Uses VK API method ``messages.send``.

        Args:
            chat_id: User or conversation ID.
            text: Message text.
            reply_markup: Keyboard (ReplyKeyboardMarkup or InlineKeyboardMarkup).
            reply_to: ID of the message to reply to.
            **kwargs: Additional VK API parameters.

        Returns:
            VK API response.
        """
        markup_dict = reply_markup.to_dict() if reply_markup else None
        return self.api.send_message(
            chat_id,
            text,
            reply_markup=markup_dict,
            reply_to=reply_to,
            **kwargs,
        )

    def reply_to(self, message: types.Message, text: str, **kwargs) -> dict:
        """Reply to a message (automatically uses chat_id and reply_to)."""
        return self.send_message(message.chat.id, text, reply_to=message.id, **kwargs)

    def send_photo(
        self,
        chat_id: int,
        photo: str | bytes | object,
        caption: str | None = None,
        reply_markup: types.ReplyKeyboardMarkup
        | types.InlineKeyboardMarkup
        | None = None,
        **kwargs,
    ) -> dict:
        """Send a photo.

        Uploads via ``photos.getMessagesUploadServer`` and sends.

        Args:
            chat_id: User or conversation ID.
            photo: File path, bytes, or file-like object.
            caption: Photo caption.
            reply_markup: Keyboard.
        """
        markup_dict = reply_markup.to_dict() if reply_markup else None
        return self.api.send_photo(
            chat_id,
            photo,
            caption=caption,
            reply_markup=markup_dict,
            **kwargs,
        )

    def send_document(
        self,
        chat_id: int,
        document: str | bytes | object,
        caption: str | None = None,
        reply_markup: types.ReplyKeyboardMarkup
        | types.InlineKeyboardMarkup
        | None = None,
        **kwargs,
    ) -> dict:
        """Send a document.

        Uploads via ``docs.getMessagesUploadServer`` and sends.

        Args:
            chat_id: User or conversation ID.
            document: File path, bytes, or file-like object.
            caption: Document caption.
            reply_markup: Keyboard.
        """
        markup_dict = reply_markup.to_dict() if reply_markup else None
        return self.api.send_document(
            chat_id,
            document,
            caption=caption,
            reply_markup=markup_dict,
            **kwargs,
        )

    def answer_callback_query(
        self,
        callback_query_id: str,
        user_id: int,
        peer_id: int,
        event_data: dict[str, Any] | None = None,
        text: str | None = None,
    ) -> dict:
        params = {
            "event_id": callback_query_id,
            "user_id": user_id,
            "peer_id": peer_id,
        }

        if event_data is not None:
            params["event_data"] = json.dumps(event_data)
        elif text:
            params["event_data"] = json.dumps({"type": "show_snackbar", "text": text})

        return self.api._make_request(
            "messages.sendMessageEventAnswer", params
        )

    def polling(self, non_stop: bool = True, interval: int = 1):
        """Start Long Poll server polling.

        Uses Bots Long Poll API to receive events.

        Args:
            non_stop: If True, restarts on errors.
            interval: Delay between retries on error (seconds).
        """
        self._polling = True

        while self._polling:
            try:
                if not self.lp_server:
                    self.lp_server = self.api.get_long_poll_server(
                        self.group_id
                    )

                raw_updates = self.api.get_long_poll_updates(
                    self.lp_server.server, self.lp_server.key, self.lp_server.ts
                )

                parsed_updates = apihelper.process_updates(raw_updates)

                for update_data in parsed_updates:
                    self._process_update(update_data)

                if "ts" in raw_updates:
                    self.lp_server.ts = raw_updates["ts"]

            except exception.VKAPIError:
                self.lp_server = None
                if not non_stop:
                    raise
                time.sleep(interval)

            except Exception as e:
                print(f"Polling error: {e}")
                if not non_stop:
                    raise
                time.sleep(interval)

    def get_fsm(self, user_id: int, fsm_name: str = "default") -> VKBotFSM:
        state = self.get_state(user_id)
        fsm = FSMRegistry.get_or_create(fsm_name)
        fsm.current_state = state
        return fsm

    def set_fsm_state(self, user_id: int, state: str, fsm_name: str = "default"):
        fsm = self.get_fsm(user_id, fsm_name)
        fsm.transition(fsm.current_state, state, None)
        self.set_state(user_id, state)

    def _process_update(self, update_data: dict):
        update = types.Update(
            **update_data
        )

        for middleware in self.middleware_handlers:
            if middleware.check(update):
                result = middleware.process(self, update)
                if result is False:
                    return

        if update.message:
            user_id = update.message.from_id
            current_state = self.get_state(user_id)
            state_context = self._get_state_context(user_id)

            for handler in self.message_handlers:
                if handler.check(update, current_state):
                    if handler.accepts_state:
                        handler.callback(update.message, state_context)
                    else:
                        handler.callback(update.message)
                    break

        elif update.callback_query:
            user_id = update.callback_query.from_id
            current_state = self.get_state(user_id)
            state_context = self._get_state_context(user_id)

            for handler in self.callback_query_handlers:
                if handler.check(update, current_state):
                    if handler.accepts_state:
                        handler.callback(update.callback_query, state_context)
                    else:
                        handler.callback(update.callback_query)
                    break

    def stop_polling(self):
        self._polling = False


__all__ = [
    "ApiClient",
    "FSMRegistry",
    "HttpConfig",
    "MemoryStorage",
    "PostgresStorage",
    "RedisStorage",
    "StateContext",
    "StateManager",
    "StatesGroup",
    "VKBot",
    "VKBotFSM",
    "exception",
    "types",
    "util",
]
