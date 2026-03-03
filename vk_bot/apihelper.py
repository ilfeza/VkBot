import json
import pathlib
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, BinaryIO

from vk_bot.exception import VKAPIError
from vk_bot.http_client import HttpClient
from vk_bot.types import Update

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
    ) -> dict:
        url = API_URL + method
        request_params = params.copy() if params else {}
        request_params.update(
            {"access_token": self.token, "v": API_VERSION}
        )

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

        return data.get("response", {})

    def get_me(self) -> dict:
        result = self._make_request("users.get")
        return result[0] if result else {}

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict | None = None,
        reply_to: int | None = None,
        **kwargs,
    ) -> dict:
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

    def reply_to_message(self, message: dict, text: str, **kwargs) -> dict:
        chat_id = message.get("peer_id") or message.get("user_id")
        reply_to = message.get("id")
        return self.send_message(chat_id, text, reply_to=reply_to, **kwargs)

    def send_photo(
        self,
        chat_id: int,
        photo: str | bytes | BinaryIO,
        caption: str | None = None,
        **kwargs,
    ) -> dict:
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

    def get_messages_upload_server(self, peer_id: int | None = None) -> dict:
        params: dict[str, Any] = {}
        if peer_id:
            params["peer_id"] = peer_id
        return self._make_request("photos.getMessagesUploadServer", params)

    def upload_photo_to_server(
        self, upload_url: str, photo: str | bytes | BinaryIO
    ) -> dict:
        file = _to_bytes_io(photo, "photo.jpg")
        return self.http.post(
            upload_url, files={"photo": file}, timeout=self.http.timeout * 2
        )

    def save_uploaded_photo(self, photo: str, server: int, hash: str) -> list:
        params = {"photo": photo, "server": server, "hash": hash}
        return self._make_request("photos.saveMessagesPhoto", params)

    def send_document(
        self,
        chat_id: int,
        document: str | bytes | BinaryIO,
        title: str | None = None,
        caption: str | None = None,
        **kwargs,
    ) -> dict:
        upload_server = self.get_docs_upload_server(peer_id=chat_id)
        uploaded = self.upload_document_to_server(
            upload_server["upload_url"], document
        )
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

    def get_docs_upload_server(self, peer_id: int | None = None) -> dict:
        params = {}
        if peer_id:
            params["peer_id"] = peer_id
        return self._make_request("docs.getMessagesUploadServer", params)

    def upload_document_to_server(
        self, upload_url: str, document: str | bytes | BinaryIO
    ) -> dict:
        file = _to_bytes_io(document, "document.dat")
        return self.http.post(
            upload_url, files={"file": file}, timeout=self.http.timeout * 2
        )

    def save_uploaded_document(
        self, file_data: str, title: str | None = None
    ) -> list:
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
        return groups[0]["id"]

    def get_long_poll_server(self, group_id: int) -> LongPollServer:
        result = self._make_request(
            "groups.getLongPollServer", {"group_id": group_id}
        )
        return LongPollServer(
            server=result["server"],
            key=result["key"],
            ts=result["ts"],
            pts=result.get("pts"),
        )

    def get_long_poll_updates(
        self, server: str, key: str, ts: str, wait: int | None = None
    ) -> dict:
        if wait is None:
            wait = self.http.long_poll_timeout

        url = f"{server}?act=a_check&key={key}&ts={ts}&wait={wait}"
        return self.http.get(url, timeout=wait + 5)


def parse_update(update_data: list) -> dict | None:
    if not update_data:
        return None

    event_type = update_data[0]

    if event_type == 4:
        return {
            "type": "message_new",
            "object": {
                "id": update_data[1],
                "flags": update_data[2],
                "peer_id": update_data[3],
                "timestamp": update_data[4],
                "text": update_data[5] if len(update_data) > 5 else "",
                "attachments": update_data[6] if len(update_data) > 6 else [],
            },
        }
    if event_type == 8:
        return {
            "type": "user_online",
            "object": {"user_id": update_data[1], "timestamp": update_data[2]},
        }

    return None


def process_updates(raw_updates: dict) -> list[Update]:
    """Extract updates from Bots Long Poll response.

    Returns events as-is since Bots Long Poll API returns
    ready-to-use JSON objects with type and object fields.
    """
    updates_data = raw_updates.get("updates", [])
    updates = []
    for update_data in updates_data:
        try:
            update = Update(**update_data)
            updates.append(update)
        except Exception as e:
            print(f"Error parsing update: {e}")
    return raw_updates.get("updates", [])


def create_keyboard(buttons: list[list[dict]], one_time: bool = False) -> dict:
    return {"buttons": buttons, "one_time": one_time}


def create_inline_keyboard(buttons: list[list[dict]]) -> dict:
    return {"inline": True, "buttons": buttons}


def extract_attachment_id(attachment: str) -> tuple[int | None, int | None]:
    if "_" not in attachment:
        return None, None

    type_part, id_part = attachment.split("_", 1)
    import re

    match = re.search(r"\d+$", type_part)
    owner_id = int(match.group()) if match else int(type_part)

    media_id = int(id_part.split("_")[0])
    return owner_id, media_id


def is_group_chat(peer_id: int) -> bool:
    return peer_id > 2000000000


def get_user_id_from_peer(peer_id: int) -> int:
    if is_group_chat(peer_id):
        return peer_id - 2000000000
    return peer_id
