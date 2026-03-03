import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class User(BaseModel):
    """VK user object.

    Corresponds to the ``user`` object in VK API.
    """

    id: int
    first_name: str = ""
    last_name: str = ""
    is_closed: bool = False
    can_access_closed: bool = True
    photo_100: str | None = None
    online: bool = False

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def mention(self) -> str:
        return f"[id{self.id}|{self.first_name}]"


class Chat(BaseModel):
    id: int
    type: str = "private"
    title: str | None = None
    photo_100: str | None = None

    @classmethod
    def from_peer_id(cls, peer_id: int) -> "Chat":
        if peer_id > 2000000000:
            return cls(id=peer_id, type="group", title=f"Chat {peer_id - 2000000000}")
        return cls(id=peer_id, type="private")


class Photo(BaseModel):
    id: int
    owner_id: int
    access_key: str | None = None
    sizes: list[dict] = Field(default_factory=list)

    @property
    def attachment(self) -> str:
        base = f"photo{self.owner_id}_{self.id}"
        if self.access_key:
            base += f"_{self.access_key}"
        return base

    @property
    def url(self) -> str | None:
        if not self.sizes:
            return None
        max_size = max(self.sizes, key=lambda x: x.get("width", 0) * x.get("height", 0))
        return max_size.get("url")


class Document(BaseModel):
    id: int
    owner_id: int
    title: str = ""
    size: int = 0
    ext: str = ""
    url: str | None = None
    access_key: str | None = None

    @property
    def attachment(self) -> str:
        base = f"doc{self.owner_id}_{self.id}"
        if self.access_key:
            base += f"_{self.access_key}"
        return base


class Video(BaseModel):
    id: int
    owner_id: int
    title: str = ""
    description: str = ""
    duration: int = 0
    access_key: str | None = None

    @property
    def attachment(self) -> str:
        base = f"video{self.owner_id}_{self.id}"
        if self.access_key:
            base += f"_{self.access_key}"
        return base


class Audio(BaseModel):
    id: int
    owner_id: int
    artist: str = ""
    title: str = ""
    duration: int = 0
    url: str | None = None

    @property
    def attachment(self) -> str:
        return f"audio{self.owner_id}_{self.id}"


class Message(BaseModel):
    """Incoming message.

    Corresponds to the ``message`` object in ``message_new`` VK API event.
    """

    id: int
    date: datetime
    peer_id: int
    from_id: int
    text: str = ""
    out: bool = False
    important: bool = False
    deleted: bool = False
    attachments: list[dict] = Field(default_factory=list)
    reply_message: "Message | None" = None
    fwd_messages: list["Message"] = Field(default_factory=list)
    payload: dict | None = None
    action: dict | None = None
    _from_user: User | None = None
    _chat: Chat | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def chat(self) -> Chat:
        if not self._chat:
            self._chat = Chat.from_peer_id(self.peer_id)
        return self._chat

    @property
    def from_user(self) -> User | None:
        return self._from_user

    @property
    def content_type(self) -> str:
        if self.text:
            return "text"
        if self.attachments:
            return self.attachments[0].get("type", "unknown")
        if self.action:
            return f"action_{self.action.get('type')}"
        return "unknown"

    @property
    def is_private(self) -> bool:
        return self.peer_id == self.from_id

    def get_photos(self) -> list[Photo]:
        photos = []
        for att in self.attachments:
            if att.get("type") == "photo":
                photo_data = att.get("photo", {})
                photos.append(
                    Photo(
                        id=photo_data.get("id"),
                        owner_id=photo_data.get("owner_id"),
                        access_key=photo_data.get("access_key"),
                        sizes=photo_data.get("sizes", []),
                    )
                )
        return photos

    def get_documents(self) -> list[Document]:
        docs = []
        for att in self.attachments:
            if att.get("type") == "doc":
                doc_data = att.get("doc", {})
                docs.append(
                    Document(
                        id=doc_data.get("id"),
                        owner_id=doc_data.get("owner_id"),
                        title=doc_data.get("title", ""),
                        size=doc_data.get("size", 0),
                        ext=doc_data.get("ext", ""),
                        url=doc_data.get("url"),
                        access_key=doc_data.get("access_key"),
                    )
                )
        return docs


class KeyboardButton(BaseModel):
    """Reply keyboard button."""

    text: str
    color: str = "primary"

    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict:
        return {
            "action": {
                "type": "text",
                "label": self.text
            },
            "color": self.color
        }


class InlineKeyboardButton(BaseModel):
    """Inline keyboard button (callback, link, or VK App)."""

    text: str
    callback_data: str | None = None
    url: str | None = None
    vk_app_id: int | None = None
    owner_id: int | None = None
    hash: str | None = None

    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict:
        action = {"type": "text", "label": self.text}

        if self.callback_data:
            action["type"] = "callback"
            action["payload"] = json.dumps({"data": self.callback_data})
        elif self.url:
            action["type"] = "open_link"
            action["link"] = self.url
        elif self.vk_app_id:
            action["type"] = "open_app"
            action["app_id"] = self.vk_app_id
            if self.owner_id:
                action["owner_id"] = self.owner_id
            if self.hash:
                action["hash"] = self.hash

        return {"action": action}


class ReplyKeyboardMarkup(BaseModel):
    """Reply keyboard displayed below the input field.

    Corresponds to the ``keyboard`` object in VK API.
    """

    keyboard: list[list[KeyboardButton]] = Field(default_factory=list)
    one_time_keyboard: bool = False

    def add(self, *buttons: KeyboardButton):
        row = list(buttons)
        if row:
            self.keyboard.append(row)
        return self

    def row(self, *buttons: KeyboardButton):
        return self.add(*buttons)

    def to_dict(self) -> dict:
        return {
            "buttons": [[btn.to_dict() for btn in row] for row in self.keyboard],
            "one_time": self.one_time_keyboard,
        }


class InlineKeyboardMarkup(BaseModel):
    """Inline keyboard embedded in a message.

    Callback buttons send a ``message_event``.
    """

    keyboard: list[list[InlineKeyboardButton]] = Field(default_factory=list)

    def add(self, *buttons: InlineKeyboardButton):
        row = list(buttons)
        if row:
            self.keyboard.append(row)
        return self

    def row(self, *buttons: InlineKeyboardButton):
        return self.add(*buttons)

    def to_dict(self) -> dict:
        return {
            "buttons": [[btn.to_dict() for btn in row] for row in self.keyboard],
            "inline": True,
        }


class CallbackQuery(BaseModel):
    """Callback event from an inline button press.

    Corresponds to a ``message_event`` in VK API.
    """

    id: str
    from_id: int
    peer_id: int
    message_id: int
    payload: dict | None = None
    data: str | None = None
    _message: Message | None = None
    _from_user: User | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator('payload', mode='before')
    @classmethod
    def parse_payload(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {"data": v}
        return v

    @model_validator(mode='after')
    def extract_data_from_payload(self):
        if self.data is None and self.payload is not None and isinstance(self.payload, dict):
            self.data = self.payload.get('data')
        return self

    @property
    def message(self) -> Message | None:
        return self._message

    @property
    def from_user(self) -> User | None:
        return self._from_user


class Update(BaseModel):
    """Update from VK Long Poll server.

    Contains event type and data object.
    Supports lazy parsing of message and callback_query.
    """

    update_id: int = 0
    type: str
    object: dict
    _message: Message | None = None
    _callback_query: CallbackQuery | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    @field_validator('type')
    @classmethod
    def validate_type(cls, v):
        valid_types = {
            'message_new', 'message_read', 'message_typing_state', 'message_reply', 'message_edit', 'message_event',
            'message_allow', 'message_deny', 'photo_new', 'audio_new',
            'video_new', 'wall_post_new', 'wall_repost', 'group_join',
            'group_leave', 'user_online', 'user_offline'
        }
        if v not in valid_types:
            print(f"Info: Unknown update type: {v}")
        return v

    @property
    def message(self) -> Message | None:
        if self.type == "message_new" and self._message is None:
            message_data = self.object.get("message", {})
            if message_data:
                self._message = Message(**message_data)
        return self._message

    @property
    def callback_query(self) -> CallbackQuery | None:
        if self.type == "message_event" and not self._callback_query:
            self._callback_query = CallbackQuery(
                id=self.object.get("event_id"),
                from_id=self.object.get("user_id"),
                peer_id=self.object.get("peer_id"),
                message_id=self.object.get("conversation_message_id", 0),
                payload=self.object.get("payload"),
            )
        return self._callback_query
