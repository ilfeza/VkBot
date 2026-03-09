import json
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from vk_bot.config import HttpConfig

_RETRY_STATUSES = {429, 500, 502, 503, 504}


class HttpClient:
    """HTTP client with retries, timeouts and proxy support."""

    def __init__(self, config: HttpConfig | None = None) -> None:
        config = config or HttpConfig()
        self._config = config
        transport = httpx.HTTPTransport(retries=0)
        self._client = httpx.Client(
            headers={"User-Agent": config.user_agent},
            transport=transport,
            proxy=config.proxy,
        )

    @property
    def timeout(self) -> int:
        return self._config.timeout

    @property
    def long_poll_timeout(self) -> int:
        return self._config.long_poll_timeout

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(self._config.retries),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
                retry=retry_if_exception(self._is_retryable),
                reraise=True,
            ):
                with attempt:
                    response = self._client.request(method, url, **kwargs)
                    response.raise_for_status()
                    result: dict[str, Any] = response.json()
                    return result
        except httpx.HTTPError as e:
            raise ConnectionError(f"Network error: {e}") from e
        except json.JSONDecodeError as e:
            raise ConnectionError(f"Invalid JSON response: {e}") from e

    @staticmethod
    def _is_retryable(exc: BaseException) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in _RETRY_STATUSES
        return isinstance(exc, httpx.ConnectError)

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET", url, params=params, timeout=timeout or self._config.timeout
        )

    def post(
        self,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            url,
            data=data,
            params=params,
            files=files,
            timeout=timeout or self._config.timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
