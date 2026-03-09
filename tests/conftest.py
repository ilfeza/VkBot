from collections.abc import Callable
from typing import Any

import pytest

from vk_bot import VKBot, types


@pytest.fixture
def bot() -> VKBot:
    return VKBot(token="test-token", group_id=987654321)


@pytest.fixture
def message_update_factory() -> Callable[..., types.Update]:
    def _factory(
        text: str = "hello",
        user_id: int = 111222333,
        peer_id: int | None = None,
        message_id: int = 4096,
        content: dict[str, Any] | None = None,
    ) -> types.Update:
        message = {
            "id": message_id,
            "date": 1_700_000_000,
            "peer_id": peer_id if peer_id is not None else user_id,
            "from_id": user_id,
            "text": text,
            "attachments": [],
        }
        if content:
            message.update(content)
        return types.Update(type="message_new", object={"message": message})

    return _factory


@pytest.fixture
def callback_update_factory() -> Callable[..., types.Update]:
    def _factory(
        data: str = "ok",
        user_id: int = 111222333,
        peer_id: int | None = None,
    ) -> types.Update:
        payload = {"data": data}
        return types.Update(
            type="message_event",
            object={
                "event_id": "evt-111222333-abcdef",
                "user_id": user_id,
                "peer_id": peer_id if peer_id is not None else user_id,
                "conversation_message_id": 100,
                "payload": payload,
            },
        )

    return _factory


@pytest.fixture
def mock_api_calls(bot, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls = {}

    def fake_make_request(*args, **kwargs):
        calls["_make_request"] = {"args": args, "kwargs": kwargs}
        return {"ok": True}

    def fake_send_photo(*args, **kwargs):
        calls["send_photo"] = {"args": args, "kwargs": kwargs}
        return {"ok": True}

    def fake_send_document(*args, **kwargs):
        calls["send_document"] = {"args": args, "kwargs": kwargs}
        return {"ok": True}

    monkeypatch.setattr(bot.api, "_make_request", fake_make_request)
    monkeypatch.setattr(bot.api, "send_photo", fake_send_photo)
    monkeypatch.setattr(bot.api, "send_document", fake_send_document)

    return calls
