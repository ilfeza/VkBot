from __future__ import annotations

from vk_bot import types


def test_user_from_dict_helpers() -> None:
    user = types.User.model_validate(
        {
            "id": 111222333,
            "first_name": "Ivan",
            "last_name": "Ivanov",
        },
    )

    assert user.full_name == "Ivan Ivanov"
    assert user.mention == "[id111222333|Ivan]"


def test_message_from_dict_text() -> None:
    message = types.Message.model_validate(
        {
            "id": 1,
            "date": 1_700_000_000,
            "peer_id": 111222333,
            "from_id": 111222333,
            "text": "hello",
            "attachments": [],
        },
    )

    assert message.text == "hello"
    assert message.content_type == "text"
    assert message.chat.type == "private"
    assert message.is_private is True


def test_message_from_dict_with_attachments() -> None:
    message = types.Message.model_validate(
        {
            "id": 4096,
            "date": 1_700_000_000,
            "peer_id": 2_000_000_001,
            "from_id": 111222333,
            "text": "",
            "attachments": [
                {
                    "type": "photo",
                    "photo": {
                        "id": 457239018,
                        "owner_id": 111222333,
                        "sizes": [{"width": 10, "height": 20, "url": "x"}],
                    },
                },
                {
                    "type": "doc",
                    "doc": {
                        "id": 457239019,
                        "owner_id": 111222333,
                        "title": "file.txt",
                    },
                },
            ],
        },
    )

    assert message.chat.type == "group"
    assert message.content_type == "photo"
    assert message.is_private is False
    assert message.get_photos()[0].attachment == "photo111222333_457239018"
    assert message.get_documents()[0].attachment == "doc111222333_457239019"


def test_callback_query_parses_payload_json_string() -> None:
    callback = types.CallbackQuery(
        id="123456_abcdef",
        from_id=111222333,
        peer_id=111222333,
        message_id=256,
        payload='{"data":"confirm"}',
    )

    assert callback.id == "123456_abcdef"
    assert callback.data == "confirm"
    assert callback.payload == {"data": "confirm"}


def test_update_lazy_parsing_message_and_callback() -> None:
    message_update = types.Update(
        update_id=1,
        type="message_new",
        object={
            "message": {
                "id": 4096,
                "date": 1_700_000_000,
                "peer_id": 111222333,
                "from_id": 111222333,
                "text": "hello",
            },
        },
    )
    callback_update = types.Update(
        update_id=2,
        type="message_event",
        object={
            "event_id": "123456_abcdef",
            "user_id": 111222333,
            "peer_id": 111222333,
            "conversation_message_id": 256,
            "payload": {"data": "ok"},
        },
    )

    assert message_update.message is not None
    assert message_update.message.text == "hello"
    assert callback_update.callback_query is not None
    assert callback_update.callback_query.data == "ok"
