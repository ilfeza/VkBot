from typing import Any


class VKAPIError(Exception):
    def __init__(
        self,
        error_code: int,
        error_msg: str,
        request_params: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code
        self.error_msg = error_msg
        self.request_params = request_params or {}
        super().__init__(f"[{error_code}] {error_msg}")
