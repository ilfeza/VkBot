from collections.abc import Iterator

from dishka import Provider, Scope, from_context, provide

from vk_bot.apihelper import ApiClient
from vk_bot.config import HttpConfig, Token
from vk_bot.http_client import HttpClient


class VkBotProvider(Provider):
    """Provider for VK Bot dependencies."""

    scope = Scope.APP

    token = from_context(provides=Token)
    http_config = from_context(provides=HttpConfig)

    @provide
    def http_client(self, config: HttpConfig) -> Iterator[HttpClient]:
        client = HttpClient(config)
        yield client
        client.close()

    @provide
    def api_client(self, token: Token, http: HttpClient) -> ApiClient:
        return ApiClient(token=token, http=http)
