from typing import NewType

from pydantic import BaseModel

Token = NewType("Token", str)


class HttpConfig(BaseModel):
    """HTTP transport settings."""

    user_agent: str = "VK Bot Python/0.1"
    timeout: int = 30
    long_poll_timeout: int = 25
    retries: int = 3
    proxy: str | None = None
