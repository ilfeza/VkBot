from __future__ import annotations

import json
from datetime import datetime

from vk_bot import types


def test_send_message_uses_serialized_markup(bot, mock_api_calls) -> None:
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True).add(
        types.KeyboardButton(text="Start"),
    )

    bot.send_message(111222333, "Hello", reply_markup=markup, disable_mentions=1)

    call = mock_api_calls["_make_request"]
    assert call["args"][0] == "messages.send"

    params = call["args"][1]
    assert params["peer_id"] == 111222333
    assert params["message"] == "Hello"
    assert isinstance(params["random_id"], int)
    assert params["random_id"] > 0
    assert params["disable_mentions"] == 1

    expected_keyboard = json.dumps(markup.to_dict())
    assert params["keyboard"] == expected_keyboard


def test_reply_to_uses_message_peer_and_id(bot, mock_api_calls) -> None:
    message = types.Message(
        id=4096,
        date=datetime.now(),
        peer_id=2_000_000_001,
        from_id=111222333,
        text="original message",
    )

    bot.reply_to(message, "reply text")

    call = mock_api_calls["_make_request"]
    assert call["args"][0] == "messages.send"

    params = call["args"][1]
    assert params["peer_id"] == message.chat.id
    assert params["reply_to"] == message.id


def test_send_media_proxy_to_apihelper(bot, mock_api_calls) -> None:
    bot.send_photo(111222333, b"image-bytes", caption="photo caption")
    bot.send_document(111222333, b"doc-bytes", caption="document caption")

    photo_call = mock_api_calls["send_photo"]
    assert photo_call["args"][0] == 111222333
    assert photo_call["args"][1] == b"image-bytes"
    assert photo_call["kwargs"]["caption"] == "photo caption"

    doc_call = mock_api_calls["send_document"]
    assert doc_call["args"][0] == 111222333
    assert doc_call["args"][1] == b"doc-bytes"
    assert doc_call["kwargs"]["caption"] == "document caption"


def test_answer_callback_query_snackbar(bot, mock_api_calls) -> None:
    bot.answer_callback_query(
        callback_query_id="abcdef_123456",
        user_id=111222333,
        peer_id=2_000_000_001,
        text="Success",
    )

    call = mock_api_calls["_make_request"]
    assert call["args"][0] == "messages.sendMessageEventAnswer"

    params = call["args"][1]
    assert params["event_id"] == "abcdef_123456"
    assert params["user_id"] == 111222333
    assert params["peer_id"] == 2_000_000_001

    event_data = json.loads(params["event_data"])
    assert event_data == {"type": "show_snackbar", "text": "Success"}


def test_answer_callback_query_custom_event(bot, mock_api_calls) -> None:
    custom_data = {"type": "open_link", "link": "https://vk.com"}

    bot.answer_callback_query(
        callback_query_id="abcdef_123456",
        user_id=111222333,
        peer_id=2_000_000_001,
        event_data=custom_data,
    )

    call = mock_api_calls["_make_request"]
    params = call["args"][1]

    event_data = json.loads(params["event_data"])
    assert event_data == custom_data
