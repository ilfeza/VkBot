import json
from abc import ABC, abstractmethod
from typing import Any

try:
    from redis import Redis

    redis_installed = True
except ImportError:
    redis_installed = False

try:
    import asyncpg
    from asyncpg.pool import Pool
    postgres_installed = True
except ImportError:
    postgres_installed = False
    Pool = Any


class BaseStorage(ABC):
    """Abstract base class for state storage backends."""

    @abstractmethod
    def get_state(self, user_id: int) -> str | None:
        pass

    @abstractmethod
    def set_state(self, user_id: int, state: str):
        pass

    @abstractmethod
    def get_data(self, user_id: int) -> dict[str, Any]:
        pass

    @abstractmethod
    def set_data(self, user_id: int, data: dict[str, Any]):
        pass

    @abstractmethod
    async def update_data(self, user_id: int, **kwargs):
        pass

    @abstractmethod
    def delete(self, user_id: int):
        pass


class MemoryStorage(BaseStorage):
    """In-memory state storage.

    Data is lost on restart. Suitable for development.
    """

    def __init__(self):
        self._states = {}
        self._data = {}

    def get_state(self, user_id: int) -> str | None:
        return self._states.get(user_id)

    def set_state(self, user_id: int, state: str):
        self._states[user_id] = state

    def get_data(self, user_id: int) -> dict[str, Any]:
        return self._data.get(user_id, {}).copy()

    def set_data(self, user_id: int, data: dict[str, Any]):
        self._data[user_id] = data

    async def update_data(self, user_id: int, **kwargs):
        if user_id not in self._data:
            self._data[user_id] = {}
        self._data[user_id].update(kwargs)

    def delete(self, user_id: int):
        self._states.pop(user_id, None)
        self._data.pop(user_id, None)


class RedisStorage(BaseStorage):
    """Redis-backed state storage.

    Persistent storage. Suitable for production.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
    ):
        if not redis_installed:
            raise ImportError("Redis is not installed.")
        self.redis = Redis(
            host=host, port=port, db=db, password=password, decode_responses=True
        )

    def _state_key(self, user_id: int) -> str:
        return f"vkbot:state:{user_id}"

    def _data_key(self, user_id: int) -> str:
        return f"vkbot:data:{user_id}"

    def get_state(self, user_id: int) -> str | None:
        return self.redis.get(self._state_key(user_id))

    def set_state(self, user_id: int, state: str):
        self.redis.set(self._state_key(user_id), state)

    def get_data(self, user_id: int) -> dict[str, Any]:
        data = self.redis.get(self._data_key(user_id))
        return json.loads(data) if data else {}

    def set_data(self, user_id: int, data: dict[str, Any]):
        self.redis.set(self._data_key(user_id), json.dumps(data))

    async def update_data(self, user_id: int, **kwargs):
        pipe = self.redis.pipeline()
        key = self._data_key(user_id)

        current = await self.get_data(user_id)
        current.update(kwargs)

        pipe.set(key, json.dumps(current))
        pipe.execute()

    def delete(self, user_id: int):
        self.redis.delete(self._state_key(user_id))
        self.redis.delete(self._data_key(user_id))


class PostgresStorage(BaseStorage):
    def __init__(
        self,
        dsn: str,
        pool_min_size: int = 10,
        pool_max_size: int = 20,
        table_prefix: str = "vk_bot",
    ):
        if not postgres_installed:
            raise ImportError(
                "asyncpg is not installed. Install with: pip install vk-bot[postgres]"
            )

        self.dsn = dsn
        self.pool_min_size = pool_min_size
        self.pool_max_size = pool_max_size
        self.table_prefix = table_prefix
        self._pool: Pool | None = None

    async def _get_pool(self) -> Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=self.pool_min_size,
                max_size=self.pool_max_size,
            )
            await self._init_tables()
        return self._pool

    async def _init_tables(self):
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_states (
                    user_id BIGINT PRIMARY KEY,
                    state TEXT,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_prefix}_data (
                    user_id BIGINT PRIMARY KEY,
                    data JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)

    async def get_state(self, user_id: int) -> str | None:
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            result = await conn.fetchval(
                f"SELECT state FROM {self.table_prefix}_states WHERE user_id = $1",
                user_id,
            )
            return result

    async def set_state(self, user_id: int, state: str):
        pool = await self._get_pool()

        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(
                f"""
                INSERT INTO {self.table_prefix}_states (user_id, state, updated_at)
                VALUES ($1, $2, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id)
                DO UPDATE SET state = $2, updated_at = CURRENT_TIMESTAMP
                """,
                user_id,
                state,
            )

    async def update_data(self, user_id: int, **kwargs):
        pool = await self._get_pool()

        async with pool.acquire() as conn, conn.transaction():
            for key, value in kwargs.items():
                json_value = json.dumps(value)

                await conn.execute(
                    f"""
                    INSERT INTO {self.table_prefix}_data (user_id, data, updated_at)
                    VALUES ($1, $2::jsonb, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE
                    SET data = jsonb_set(
                        COALESCE({self.table_prefix}_data.data, '{{}}'::jsonb),
                        $3,
                        $4::jsonb,
                        true
                    ),
                    updated_at = CURRENT_TIMESTAMP
                    """,
                    user_id,
                    json.dumps({key: value}),
                    f"{{{key}}}",
                    json_value,
                )

    async def delete(self, user_id: int):
        pool = await self._get_pool()

        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(
                f"DELETE FROM {self.table_prefix}_states WHERE user_id = $1",
                user_id,
            )
            await conn.execute(
                f"DELETE FROM {self.table_prefix}_data WHERE user_id = $1",
                user_id,
            )

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None
