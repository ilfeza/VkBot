from unittest.mock import MagicMock, patch

from dishka import make_container

from vk_bot.config import HttpConfig, Token
from vk_bot.di import VkBotProvider


class TestVkBotProvider:
    def test_http_client_closed_on_container_close(self) -> None:
        token = Token("test-token")
        config = HttpConfig()
        mock_client = MagicMock()

        with patch("vk_bot.di.HttpClient", return_value=mock_client):
            container = make_container(
                VkBotProvider(), context={Token: token, HttpConfig: config}
            )
            from vk_bot.http_client import HttpClient

            resolved = container.get(HttpClient)
            assert resolved is mock_client
            mock_client.close.assert_not_called()

            container.close()

        mock_client.close.assert_called_once()

    def test_api_client_provider(self) -> None:
        token = Token("test-token")
        config = HttpConfig()

        mock_http = MagicMock()
        mock_api = MagicMock()

        with (
            patch("vk_bot.di.HttpClient", return_value=mock_http),
            patch("vk_bot.di.ApiClient", return_value=mock_api) as api_cls,
        ):
            container = make_container(
                VkBotProvider(), context={Token: token, HttpConfig: config}
            )
            from vk_bot.apihelper import ApiClient

            with container() as req:
                result = req.get(ApiClient)

            assert result is mock_api
            api_cls.assert_called_once_with(token=token, http=mock_http)
            container.close()
            mock_http.close.assert_called_once()
