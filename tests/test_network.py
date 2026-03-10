from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from tenacity import wait_none

from vk_bot.apihelper import (
    API_URL,
    API_VERSION,
    ApiClient,
    LongPollServer,
    process_updates,
)
from vk_bot.config import HttpConfig
from vk_bot.exception import VKAPIError
from vk_bot.http_client import _RETRY_STATUSES, HttpClient  # noqa: PLC2701


@pytest.fixture
def mock_httpx_client() -> MagicMock:
    return MagicMock(spec=httpx.Client)


@pytest.fixture
def http_client(mock_httpx_client: MagicMock) -> HttpClient:
    cfg = HttpConfig(retries=1, timeout=30, long_poll_timeout=25)
    with (
        patch("vk_bot.http_client.httpx.HTTPTransport"),
        patch("vk_bot.http_client.httpx.Client", return_value=mock_httpx_client),
    ):
        return HttpClient(config=cfg)


@pytest.fixture
def mock_http() -> MagicMock:
    mock = MagicMock(spec=HttpClient)
    mock.timeout = 30
    mock.long_poll_timeout = 25
    return mock


@pytest.fixture
def api(mock_http: MagicMock) -> ApiClient:
    return ApiClient(token="test-token", http=mock_http)


def _make_response(
    status_code: int = 200,
    json_data: dict[str, Any] | None = None,
    *,
    raise_for_status: Exception | None = None,
    json_error: Exception | None = None,
) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    if raise_for_status:
        resp.raise_for_status.side_effect = raise_for_status
    else:
        resp.raise_for_status.return_value = None
    if json_error:
        resp.json.side_effect = json_error
    else:
        resp.json.return_value = json_data or {"ok": True}
    return resp


class TestHttpClientErrors:
    def test_non_retryable_http_error(
        self, http_client: HttpClient, mock_httpx_client: MagicMock
    ) -> None:
        resp = _make_response(
            status_code=403,
            raise_for_status=httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock()
            ),
        )
        mock_httpx_client.request.return_value = resp
        with pytest.raises(ConnectionError, match="Network error"):
            http_client.get("https://example.com")

    def test_connect_error(
        self, http_client: HttpClient, mock_httpx_client: MagicMock
    ) -> None:
        mock_httpx_client.request.side_effect = httpx.ConnectError("fail")
        with pytest.raises(ConnectionError, match="Network error"):
            http_client.get("https://example.com")

    def test_json_decode_error(
        self, http_client: HttpClient, mock_httpx_client: MagicMock
    ) -> None:
        import json as _json

        resp = _make_response(json_error=_json.JSONDecodeError("bad", "", 0))
        mock_httpx_client.request.return_value = resp
        with pytest.raises(ConnectionError, match="Invalid JSON"):
            http_client.get("https://example.com")


class TestHttpClientRetries:
    @staticmethod
    def _make_client(mock_httpx_client: MagicMock) -> HttpClient:
        cfg = HttpConfig(retries=2)
        with (
            patch("vk_bot.http_client.httpx.HTTPTransport"),
            patch("vk_bot.http_client.httpx.Client", return_value=mock_httpx_client),
        ):
            return HttpClient(config=cfg)

    @pytest.mark.parametrize("status", sorted(_RETRY_STATUSES))
    def test_retryable_status_then_success(
        self, status: int, mock_httpx_client: MagicMock
    ) -> None:
        client = self._make_client(mock_httpx_client)
        fail_resp = _make_response(status_code=status)
        fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status), request=MagicMock(), response=fail_resp
        )
        ok_resp = _make_response(json_data={"ok": True})
        mock_httpx_client.request.side_effect = [fail_resp, ok_resp]

        with patch("vk_bot.http_client.wait_exponential", return_value=wait_none()):
            result = client.get("https://example.com")

        assert result == {"ok": True}
        assert mock_httpx_client.request.call_count == 2

    def test_connect_error_then_success(self, mock_httpx_client: MagicMock) -> None:
        client = self._make_client(mock_httpx_client)
        ok_resp = _make_response(json_data={"data": 1})
        mock_httpx_client.request.side_effect = [
            httpx.ConnectError("connection refused"),
            ok_resp,
        ]

        with patch("vk_bot.http_client.wait_exponential", return_value=wait_none()):
            result = client.get("https://example.com")

        assert result == {"data": 1}
        assert mock_httpx_client.request.call_count == 2

    def test_retries_exhausted(self, mock_httpx_client: MagicMock) -> None:
        client = self._make_client(mock_httpx_client)
        fail_resp = _make_response(status_code=500)
        fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=fail_resp
        )
        mock_httpx_client.request.return_value = fail_resp

        with (
            patch("vk_bot.http_client.wait_exponential", return_value=wait_none()),
            pytest.raises(ConnectionError, match="Network error"),
        ):
            client.get("https://example.com")

        assert mock_httpx_client.request.call_count == 2


class TestMakeRequest:
    def test_get_request(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {"response": {"id": 1}}
        result = api._make_request("users.get", {"user_ids": 123})

        url = mock_http.get.call_args.args[0]
        params = mock_http.get.call_args.kwargs["params"]
        assert url == API_URL + "users.get"
        assert params["access_token"] == "test-token"  # noqa: S105
        assert params["v"] == API_VERSION
        assert params["user_ids"] == 123
        assert result == {"id": 1}

    def test_post_with_files(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.post.return_value = {"response": {"uploaded": True}}
        files = {"photo": b"img"}
        result = api._make_request(
            "photos.upload", {"peer_id": 1}, files=files, http_method="POST"
        )

        kw = mock_http.post.call_args.kwargs
        assert kw["files"] is files
        assert result == {"uploaded": True}

    def test_error_response_raises(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {
            "error": {"error_code": 5, "error_msg": "User authorization failed"}
        }
        with pytest.raises(VKAPIError) as exc_info:
            api._make_request("users.get")

        assert exc_info.value.error_code == 5
        assert "authorization" in exc_info.value.error_msg

    def test_missing_response_key(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {"something": "else"}
        assert api._make_request("some.method") == {}


class TestSendMessage:
    def test_basic(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {"response": 12345}
        result = api.send_message(111, "hello")

        params = mock_http.get.call_args.kwargs["params"]
        assert params["peer_id"] == 111
        assert params["message"] == "hello"
        assert isinstance(params["random_id"], int)
        assert result == 12345

    def test_with_reply_markup(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {"response": 1}
        markup = {"buttons": [], "one_time": True}
        api.send_message(111, "hi", reply_markup=markup)

        params = mock_http.get.call_args.kwargs["params"]
        assert params["keyboard"] == json.dumps(markup)

    def test_with_reply_to(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {"response": 1}
        api.send_message(111, "hi", reply_to=42)

        params = mock_http.get.call_args.kwargs["params"]
        assert params["reply_to"] == 42


class TestReplyToMessage:
    def test_uses_peer_id(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {"response": 1}
        msg = {"peer_id": 2_000_000_001, "id": 100, "user_id": 111}
        api.reply_to_message(msg, "reply")

        params = mock_http.get.call_args.kwargs["params"]
        assert params["peer_id"] == 2_000_000_001

    def test_falls_back_to_user_id(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {"response": 1}
        msg = {"user_id": 111, "id": 50}
        api.reply_to_message(msg, "reply")

        params = mock_http.get.call_args.kwargs["params"]
        assert params["peer_id"] == 111


class TestSendPhoto:
    def test_full_flow(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.side_effect = [
            {"response": {"upload_url": "https://upload.vk.com/photo"}},
            {"response": [{"owner_id": -123, "id": 456}]},
            {"response": 789},
        ]
        mock_http.post.return_value = {"photo": "data", "server": 1, "hash": "abc"}

        result = api.send_photo(111, b"image-data", caption="nice photo")

        assert result == 789
        last_params = mock_http.get.call_args_list[-1].kwargs["params"]
        assert last_params["message"] == "nice photo"
        assert "photo-123_456" in last_params["attachment"]

    def test_empty_saved_photos_raises(
        self, api: ApiClient, mock_http: MagicMock
    ) -> None:
        mock_http.get.side_effect = [
            {"response": {"upload_url": "https://u"}},
            {"response": []},
        ]
        mock_http.post.return_value = {"photo": "d", "server": 1, "hash": "h"}

        with pytest.raises(ValueError, match="Failed to save photo"):
            api.send_photo(111, b"img")


class TestSendDocument:
    def test_full_flow(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.side_effect = [
            {"response": {"upload_url": "https://upload.vk.com/doc"}},
            {"response": {"doc": {"owner_id": -123, "id": 456}}},
            {"response": 789},
        ]
        mock_http.post.return_value = {"file": "file_data"}

        result = api.send_document(111, b"doc-data", title="test.pdf", caption="my doc")

        assert result == 789
        last_params = mock_http.get.call_args_list[-1].kwargs["params"]
        assert last_params["message"] == "my doc"
        assert "doc-123_456" in last_params["attachment"]

    def test_empty_saved_docs_raises(
        self, api: ApiClient, mock_http: MagicMock
    ) -> None:
        mock_http.get.side_effect = [
            {"response": {"upload_url": "https://u"}},
            {"response": []},
        ]
        mock_http.post.return_value = {"file": "f"}

        with pytest.raises(ValueError, match="Failed to save document"):
            api.send_document(111, b"doc")


class TestGetGroupId:
    def test_list_response(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {"response": [{"id": 12345}]}
        assert api.get_group_id() == 12345

    def test_dict_response_with_groups(
        self, api: ApiClient, mock_http: MagicMock
    ) -> None:
        mock_http.get.return_value = {"response": {"groups": [{"id": 67890}]}}
        assert api.get_group_id() == 67890

    def test_empty_groups_raises(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {"response": {"groups": []}}
        with pytest.raises(ValueError, match="Unable to get group_id"):
            api.get_group_id()


class TestLongPoll:
    def test_get_long_poll_server(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {
            "response": {
                "server": "https://lp.vk.com/wh123",
                "key": "abc123",
                "ts": "100",
                "pts": 42,
            }
        }
        result = api.get_long_poll_server(group_id=999)

        assert isinstance(result, LongPollServer)
        assert result.server == "https://lp.vk.com/wh123"
        assert result.key == "abc123"
        assert result.ts == "100"

        params = mock_http.get.call_args.kwargs["params"]
        assert params["group_id"] == 999

    def test_get_long_poll_updates(self, api: ApiClient, mock_http: MagicMock) -> None:
        mock_http.get.return_value = {"ts": "101", "updates": []}
        api.get_long_poll_updates("https://lp", "key", "100")

        url = mock_http.get.call_args.args[0]
        assert "wait=25" in url


def _make_raw_update(
    event_type: str = "message_new",
    text: str = "hello",
) -> dict[str, Any]:
    return {
        "type": event_type,
        "object": {
            "message": {
                "id": 1,
                "date": 1_700_000_000,
                "peer_id": 111,
                "from_id": 111,
                "text": text,
            }
        },
        "group_id": 123,
        "event_id": "evt1",
    }


class TestProcessUpdates:
    def test_valid_updates(self) -> None:
        raw = {"updates": [_make_raw_update()]}
        updates = process_updates(raw)
        assert len(updates) == 1
        assert updates[0].type == "message_new"

    def test_empty_updates(self) -> None:
        assert process_updates({"updates": []}) == []
        assert process_updates({}) == []

    def test_invalid_update_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        raw = {"updates": [{"bad": "data"}]}
        with caplog.at_level(logging.WARNING, logger="vk_bot.apihelper"):
            updates = process_updates(raw)

        assert updates == []
        assert any("Error parsing update" in r.message for r in caplog.records)

    def test_mixed_valid_and_invalid(self, caplog: pytest.LogCaptureFixture) -> None:
        raw = {"updates": [_make_raw_update(), {"bad": "data"}]}
        with caplog.at_level(logging.WARNING, logger="vk_bot.apihelper"):
            updates = process_updates(raw)

        assert len(updates) == 1
