import json
import logging
import pathlib
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, BinaryIO

from vk_bot.exception import VKAPIError
from vk_bot.http_client import HttpClient
from vk_bot.types import Update

logger = logging.getLogger(__name__)

API_URL = "https://api.vk.com/method/"
API_VERSION = "5.131"


def _to_bytes_io(data: str | bytes | BinaryIO, name: str) -> BytesIO:
    if isinstance(data, str):
        bytes_io = BytesIO(pathlib.Path(data).read_bytes())
    elif isinstance(data, bytes):
        bytes_io = BytesIO(data)
    elif isinstance(data, BytesIO):
        bytes_io = data
    else:
        bytes_io = BytesIO(data.read())
    bytes_io.seek(0)
    bytes_io.name = name
    return bytes_io


@dataclass
class LongPollServer:
    server: str
    key: str
    ts: str
    pts: int | None = None


class ApiClient:
    """VK API client. Does not depend on HTTP transport."""

    def __init__(self, token: str, http: HttpClient) -> None:
        self.token = token
        self.http = http

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _make_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        http_method: str = "GET",
    ) -> dict[str, Any]:
        url = API_URL + method
        request_params = params.copy() if params else {}
        request_params.update({"access_token": self.token, "v": API_VERSION})

        if http_method.upper() == "GET":
            data = self.http.get(url, params=request_params)
        elif files:
            data = self.http.post(
                url,
                params=request_params,
                files=files,
                timeout=self.http.timeout * 2,
            )
        else:
            data = self.http.post(url, data=request_params)

        if "error" in data:
            error = data["error"]
            raise VKAPIError(
                error_code=error.get("error_code", 0),
                error_msg=error.get("error_msg", "Unknown error"),
                request_params=request_params,
            )

        result: dict[str, Any] = data.get("response", {})
        return result

    def get_me(self) -> dict[str, Any]:
        result: Any = self._make_request("users.get")
        return result[0] if result else {}

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        reply_to: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        params = {
            "peer_id": chat_id,
            "message": text,
            "random_id": int(time.time() * 1000),
            **kwargs,
        }

        if reply_markup and isinstance(reply_markup, dict):
            params["keyboard"] = json.dumps(reply_markup)

        if reply_to:
            params["reply_to"] = reply_to

        return self._make_request("messages.send", params)

    def reply_to_message(
        self, message: dict[str, Any], text: str, **kwargs: Any
    ) -> dict[str, Any]:
        chat_id = message.get("peer_id") or message.get("user_id")
        reply_to = message.get("id")
        return self.send_message(chat_id, text, reply_to=reply_to, **kwargs)

    def send_photo(
        self,
        chat_id: int,
        photo: str | bytes | BinaryIO,
        caption: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        upload_server = self.get_messages_upload_server(peer_id=chat_id)
        uploaded = self.upload_photo_to_server(upload_server["upload_url"], photo)
        saved_photos = self.save_uploaded_photo(
            uploaded["photo"], uploaded["server"], uploaded["hash"]
        )

        if not saved_photos:
            raise ValueError("Failed to save photo")

        photo_info = saved_photos[0]
        attachment = f"photo{photo_info['owner_id']}_{photo_info['id']}"

        params = {
            "peer_id": chat_id,
            "attachment": attachment,
            "random_id": int(time.time() * 1000),
            **kwargs,
        }

        if caption:
            params["message"] = caption

        return self._make_request("messages.send", params)

    def get_messages_upload_server(self, peer_id: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if peer_id:
            params["peer_id"] = peer_id
        return self._make_request("photos.getMessagesUploadServer", params)

    def upload_photo_to_server(
        self, upload_url: str, photo: str | bytes | BinaryIO
    ) -> dict[str, Any]:
        file = _to_bytes_io(photo, "photo.jpg")
        return self.http.post(
            upload_url, files={"photo": file}, timeout=self.http.timeout * 2
        )

    def save_uploaded_photo(
        self, photo: str, server: int, hash: str
    ) -> list[dict[str, Any]]:
        params = {"photo": photo, "server": server, "hash": hash}
        return self._make_request("photos.saveMessagesPhoto", params)

    def send_document(
        self,
        chat_id: int,
        document: str | bytes | BinaryIO,
        title: str | None = None,
        caption: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        upload_server = self.get_docs_upload_server(peer_id=chat_id)
        uploaded = self.upload_document_to_server(upload_server["upload_url"], document)
        saved_docs = self.save_uploaded_document(uploaded["file"], title=title)

        if not saved_docs:
            raise ValueError("Failed to save document")

        doc_info = saved_docs["doc"]
        attachment = f"doc{doc_info['owner_id']}_{doc_info['id']}"

        params = {
            "peer_id": chat_id,
            "attachment": attachment,
            "random_id": int(time.time() * 1000),
            **kwargs,
        }

        if caption:
            params["message"] = caption

        return self._make_request("messages.send", params)

    def get_docs_upload_server(self, peer_id: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if peer_id:
            params["peer_id"] = peer_id
        return self._make_request("docs.getMessagesUploadServer", params)

    def upload_document_to_server(
        self, upload_url: str, document: str | bytes | BinaryIO
    ) -> dict[str, Any]:
        file = _to_bytes_io(document, "document.dat")
        return self.http.post(
            upload_url, files={"file": file}, timeout=self.http.timeout * 2
        )

    def save_uploaded_document(
        self, file_data: str, title: str | None = None
    ) -> list[dict[str, Any]]:
        params = {"file": file_data}
        if title:
            params["title"] = title
        return self._make_request("docs.save", params)

    def get_group_id(self) -> int:
        result = self._make_request("groups.getById")
        groups = result if isinstance(result, list) else result.get("groups", [])
        if not groups:
            raise ValueError(
                "Unable to get group_id. Check that the token is a community token."
            )
        group_id: int = groups[0]["id"]
        return group_id

    def get_long_poll_server(self, group_id: int) -> LongPollServer:
        result = self._make_request("groups.getLongPollServer", {"group_id": group_id})
        return LongPollServer(
            server=result["server"],
            key=result["key"],
            ts=result["ts"],
            pts=result.get("pts"),
        )

    def get_long_poll_updates(
        self, server: str, key: str, ts: str, wait: int | None = None
    ) -> dict[str, Any]:
        if wait is None:
            wait = self.http.long_poll_timeout

        url = f"{server}?act=a_check&key={key}&ts={ts}&wait={wait}"
        return self.http.get(url, timeout=wait + 5)

    def answer_callback_query(
        self,
        event_id: str,
        user_id: int,
        peer_id: int,
        event_data: str | None = None,
    ) -> dict[str, Any]:
        """Send a response to a callback button press.

        Uses VK API method ``messages.sendMessageEventAnswer``.

        Args:
            event_id: Callback event ID.
            user_id: User who pressed the button.
            peer_id: Peer where the button was pressed.
            event_data: JSON-encoded event data (snackbar, link, etc.).
        """
        params: dict[str, Any] = {
            "event_id": event_id,
            "user_id": user_id,
            "peer_id": peer_id,
        }
        if event_data is not None:
            params["event_data"] = event_data
        return self._make_request("messages.sendMessageEventAnswer", params)


def process_updates(raw_updates: dict[str, Any]) -> list[Update]:
    """Extract and validate updates from Bots Long Poll API response.

    Bots Long Poll API returns events as JSON objects with
    ``type``, ``object``, ``group_id`` and ``event_id`` fields.
    Each update is validated through the :class:`~vk_bot.types.Update` model.

    Args:
        raw_updates: Raw JSON response from Long Poll server.

    Returns:
        List of validated :class:`~vk_bot.types.Update` objects.
    """
    updates_data = raw_updates.get("updates", [])
    updates: list[Update] = []
    for update_data in updates_data:
        try:
            updates.append(Update(**update_data))
        except Exception as e:
            logger.warning("Error parsing update: %s", e)
    return updates
