from __future__ import annotations

from vk_bot import types


def test_attachment_helpers_build_and_parse() -> None:
    assert types.build_attachment_string(-123, 456) == "-123_456"
    assert types.build_attachment_string(-123, 456, "secret") == "-123_456_secret"

    parsed = types.parse_attachment_string("photo-123_456_secret")
    assert parsed == ("photo", -123, 456, "secret")

    assert types.parse_attachment_string("invalid") == (None, None, None, None)


def test_media_attachment_properties_and_photo_url() -> None:
    photo = types.Photo(
        id=1,
        owner_id=-2,
        access_key="k",
        sizes=[
            {"width": 10, "height": 10, "url": "small"},
            {"width": 30, "height": 20, "url": "big"},
        ],
    )
    assert photo.attachment == "photo-2_1_k"
    assert photo.url == "big"
    assert types.Photo(id=2, owner_id=3).url is None

    doc = types.Document(id=7, owner_id=-8, access_key="dk")
    assert doc.attachment == "doc-8_7_dk"

    video = types.Video(id=10, owner_id=-11, access_key="vk")
    assert video.attachment == "video-11_10_vk"

    audio = types.Audio(id=12, owner_id=-13)
    assert audio.attachment == "audio-13_12"


def test_message_action_and_unknown_content_type_and_from_user_property() -> None:
    action_message = types.Message.model_validate(
        {
            "id": 1,
            "date": 1_700_000_000,
            "peer_id": 111,
            "from_id": 111,
            "text": "",
            "action": {"type": "chat_invite_user"},
        }
    )
    assert action_message.content_type == "action_chat_invite_user"
    assert action_message.from_user is None

    unknown_message = types.Message.model_validate(
        {
            "id": 2,
            "date": 1_700_000_000,
            "peer_id": 111,
            "from_id": 111,
            "text": "",
        }
    )
    assert unknown_message.content_type == "unknown"


def test_inline_keyboard_button_to_dict_all_branches() -> None:
    default_btn = types.InlineKeyboardButton(text="Plain")
    assert default_btn.to_dict() == {"action": {"type": "text", "label": "Plain"}}

    callback_btn = types.InlineKeyboardButton(text="Cb", callback_data="ok")
    callback_data = callback_btn.to_dict()["action"]
    assert callback_data["type"] == "callback"
    assert callback_data["payload"] == '{"data": "ok"}'

    link_btn = types.InlineKeyboardButton(text="Link", url="https://vk.com")
    link_data = link_btn.to_dict()["action"]
    assert link_data["type"] == "open_link"
    assert link_data["link"] == "https://vk.com"

    app_btn = types.InlineKeyboardButton(
        text="App",
        vk_app_id=123,
        owner_id=1,
        hash="abc",
    )
    app_data = app_btn.to_dict()["action"]
    assert app_data["type"] == "open_app"
    assert app_data["app_id"] == 123
    assert app_data["owner_id"] == 1
    assert app_data["hash"] == "abc"


def test_keyboard_markup_add_row_and_to_dict() -> None:
    reply = types.ReplyKeyboardMarkup()
    assert reply.add().to_dict() == {"buttons": [], "one_time": False}
    reply.row(types.KeyboardButton(text="A"))
    assert reply.to_dict()["buttons"] == [
        [{"action": {"type": "text", "label": "A"}, "color": "primary"}]
    ]

    inline = types.InlineKeyboardMarkup()
    assert inline.add().to_dict() == {"buttons": [], "inline": True}
    inline.row(types.InlineKeyboardButton(text="B"))
    assert inline.to_dict()["buttons"] == [[{"action": {"type": "text", "label": "B"}}]]


def test_callback_query_payload_branches_and_properties() -> None:
    invalid_json_payload = types.CallbackQuery(
        id="id1",
        from_id=1,
        peer_id=1,
        message_id=1,
        payload="not-json",
    )
    assert invalid_json_payload.payload == {"data": "not-json"}
    assert invalid_json_payload.data == "not-json"
    assert invalid_json_payload.message is None
    assert invalid_json_payload.from_user is None

    has_data = types.CallbackQuery(
        id="id2",
        from_id=1,
        peer_id=1,
        message_id=1,
        payload={"data": "from_payload"},
        data="explicit",
    )
    assert has_data.data == "explicit"


def test_update_unknown_type_and_empty_message_branch() -> None:
    unknown = types.Update(type="totally_new_type", object={})
    assert unknown.type == "totally_new_type"

    empty_message_update = types.Update(type="message_new", object={})
    assert empty_message_update.message is None
