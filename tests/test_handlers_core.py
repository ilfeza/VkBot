from __future__ import annotations

import pytest

from vk_bot import types
from vk_bot.handlers import (
    CallbackQueryHandler,
    ChatMemberHandler,
    Handler,
    MessageHandler,
    MiddlewareHandler,
    extract_command,
    extract_mentions,
    is_group_event,
)


def _message_update(text: str = "hello") -> types.Update:
    return types.Update(
        type="message_new",
        object={
            "message": {
                "id": 1,
                "date": 1_700_000_000,
                "peer_id": 111,
                "from_id": 111,
                "text": text,
                "attachments": [],
            }
        },
    )


def _callback_update(payload: dict | str | None = None) -> types.Update:
    return types.Update(
        type="message_event",
        object={
            "event_id": "evt-1",
            "user_id": 111,
            "peer_id": 111,
            "conversation_message_id": 10,
            "payload": payload,
        },
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", (None, None)),
        ("hello", (None, None)),
        ("/start", ("start", None)),
        ("/HeLp arg1 arg2", ("help", "arg1 arg2")),
    ],
)
def test_extract_command(text: str, expected: tuple[str | None, str | None]) -> None:
    assert extract_command(text) == expected


def test_extract_mentions_collects_and_deduplicates_ids() -> None:
    text = "Hi [id123|User] and @id123 and [id999|Other]"
    result = extract_mentions(text)
    assert set(result) == {123, 999}


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        ("group_join", True),
        ("group_officers_edit", True),
        ("message_new", False),
    ],
)
def test_is_group_event(event_type: str, expected: bool) -> None:
    assert is_group_event(event_type) is expected


def test_base_handler_accepts_state_detection_and_default_check() -> None:
    one_arg_handler = Handler(lambda message: None)
    two_args_handler = Handler(lambda message, state: None)

    assert one_arg_handler.accepts_state is False
    assert two_args_handler.accepts_state is True
    assert one_arg_handler.check(_message_update()) is True


def test_message_handler_rejects_non_message_update() -> None:
    handler = MessageHandler(lambda message: None)
    assert handler.check(_callback_update()) is False


def test_message_handler_state_filters() -> None:
    update = _message_update("hello")

    single_state_handler = MessageHandler(lambda message: None, state="s1")
    assert single_state_handler.check(update, current_state="s2") is False

    list_state_handler = MessageHandler(lambda message: None, state=["s1", "s2"])
    assert list_state_handler.check(update, current_state="s3") is False
    assert list_state_handler.check(update, current_state="s2") is True


def test_message_handler_command_with_empty_text() -> None:
    update = _message_update("")
    handler = MessageHandler(
        lambda message: None,
        commands=["start"],
        content_types=["unknown"],
    )
    assert handler.check(update) is False


def test_message_handler_regexp_with_empty_text() -> None:
    update = _message_update("")
    handler = MessageHandler(
        lambda message: None,
        regexp=r"^hello$",
        content_types=["unknown"],
    )
    assert handler.check(update) is False


def test_callback_query_handler_rejects_non_callback_update() -> None:
    handler = CallbackQueryHandler(lambda callback: None)
    assert handler.check(_message_update()) is False


def test_callback_query_handler_state_func_and_data_filters() -> None:
    update = _callback_update({"data": "ok"})

    state_single = CallbackQueryHandler(lambda callback: None, state="s1")
    assert state_single.check(update, current_state="s2") is False

    state_list = CallbackQueryHandler(lambda callback: None, state=["s1", "s2"])
    assert state_list.check(update, current_state="s3") is False

    with_func = CallbackQueryHandler(lambda callback: None, func=lambda cb: False)
    assert with_func.check(update) is False

    no_data_update = _callback_update({})
    data_required = CallbackQueryHandler(lambda callback: None, data=r"^ok$")
    assert data_required.check(no_data_update) is False

    non_matching = _callback_update({"data": "nope"})
    assert data_required.check(non_matching) is False
    assert data_required.check(update) is True


def test_chat_member_handler_branches() -> None:
    handler = ChatMemberHandler(lambda update: None)
    assert handler.check(types.Update(type="message_new", object={})) is False

    reject_by_func = ChatMemberHandler(lambda update: None, func=lambda upd: False)
    assert reject_by_func.check(types.Update(type="group_join", object={})) is False

    assert handler.check(types.Update(type="group_join", object={})) is True


def test_middleware_handler_update_type_filter() -> None:
    handler = MiddlewareHandler(lambda bot, update: True, update_types=["message_new"])
    assert handler.check(types.Update(type="group_join", object={})) is False
    assert handler.check(_message_update()) is True
