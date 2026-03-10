import json
from abc import ABC, abstractmethod
from typing import Any

try:
    from redis import Redis

    redis_installed = True
except ImportError:
    redis_installed = False

try:
    import psycopg
    from psycopg import sql

    postgres_installed = True
except ImportError:
    postgres_installed = False


class BaseStorage(ABC):
    """Abstract base class for state storage backends."""

    @abstractmethod
    def get_state(self, user_id: int) -> str | None:
        pass

    @abstractmethod
    def set_state(self, user_id: int, state: str) -> None:
        pass

    @abstractmethod
    def get_data(self, user_id: int) -> dict[str, Any]:
        pass

    @abstractmethod
    def set_data(self, user_id: int, data: dict[str, Any]) -> None:
        pass

    @abstractmethod
    def update_data(self, user_id: int, **kwargs: Any) -> None:
        pass

    @abstractmethod
    def delete(self, user_id: int) -> None:
        pass


class MemoryStorage(BaseStorage):
    """In-memory state storage.

    Data is lost on restart. Suitable for development.
    """

    def __init__(self) -> None:
        self._states: dict[int, str] = {}
        self._data: dict[int, dict[str, Any]] = {}

    def get_state(self, user_id: int) -> str | None:
        return self._states.get(user_id)

    def set_state(self, user_id: int, state: str) -> None:
        self._states[user_id] = state

    def get_data(self, user_id: int) -> dict[str, Any]:
        return self._data.get(user_id, {}).copy()

    def set_data(self, user_id: int, data: dict[str, Any]) -> None:
        self._data[user_id] = data

    def update_data(self, user_id: int, **kwargs: Any) -> None:
        if user_id not in self._data:
            self._data[user_id] = {}
        self._data[user_id].update(kwargs)

    def delete(self, user_id: int) -> None:
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
    ) -> None:
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

    def set_state(self, user_id: int, state: str) -> None:
        self.redis.set(self._state_key(user_id), state)

    def get_data(self, user_id: int) -> dict[str, Any]:
        data = self.redis.get(self._data_key(user_id))
        return json.loads(data) if data else {}

    def set_data(self, user_id: int, data: dict[str, Any]) -> None:
        self.redis.set(self._data_key(user_id), json.dumps(data))

    def update_data(self, user_id: int, **kwargs: Any) -> None:
        current = self.get_data(user_id)
        current.update(kwargs)
        self.set_data(user_id, current)

    def delete(self, user_id: int) -> None:
        self.redis.delete(self._state_key(user_id))
        self.redis.delete(self._data_key(user_id))


class PostgresStorage(BaseStorage):
    """PostgreSQL-backed state storage using psycopg3 (synchronous).

    Persistent storage with full transaction support. Suitable for production.

    Requires the ``postgres`` extra: ``pip install vk-bot[postgres]``.

    Args:
        dsn: PostgreSQL connection string,
            e.g. ``postgresql://user:pass@localhost/dbname``.
        table_prefix: Prefix for the tables created by this storage.
    """

    def __init__(self, dsn: str, table_prefix: str = "vk_bot") -> None:
        if not postgres_installed:
            raise ImportError(
                "psycopg is not installed. Install with: pip install vk-bot[postgres]"
            )
        self._dsn = dsn
        self._table_prefix = table_prefix
        self._conn: psycopg.Connection | None = None

    @property
    def _states_table(self) -> str:
        return f"{self._table_prefix}_states"

    @property
    def _data_table(self) -> str:
        return f"{self._table_prefix}_data"

    def _get_conn(self) -> "psycopg.Connection":
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._dsn)
            self._init_tables()
        return self._conn

    def _init_tables(self) -> None:
        conn = self._conn
        if conn is None:
            raise RuntimeError("Database connection is not initialized")
        with conn.transaction():
            conn.execute(
                sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    user_id BIGINT PRIMARY KEY,
                    state   TEXT NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """).format(sql.Identifier(self._states_table))
            )
            conn.execute(
                sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    user_id BIGINT PRIMARY KEY,
                    data    JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    updated_at TIMESTAMPTZ DEFAULT now()
                )
                """).format(sql.Identifier(self._data_table))
            )

    def close(self) -> None:
        """Close the database connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def get_state(self, user_id: int) -> str | None:
        conn = self._get_conn()
        with conn.transaction():
            row = conn.execute(
                sql.SQL("SELECT state FROM {} WHERE user_id = %s").format(
                    sql.Identifier(self._states_table)
                ),
                (user_id,),
            ).fetchone()
        return row[0] if row else None

    def set_state(self, user_id: int, state: str) -> None:
        conn = self._get_conn()
        with conn.transaction():
            conn.execute(
                sql.SQL("""
                INSERT INTO {} (user_id, state, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (user_id)
                DO UPDATE SET state = EXCLUDED.state, updated_at = now()
                """).format(sql.Identifier(self._states_table)),
                (user_id, state),
            )

    def get_data(self, user_id: int) -> dict[str, Any]:
        conn = self._get_conn()
        with conn.transaction():
            row = conn.execute(
                sql.SQL("SELECT data FROM {} WHERE user_id = %s").format(
                    sql.Identifier(self._data_table)
                ),
                (user_id,),
            ).fetchone()
        return dict(row[0]) if row else {}

    def set_data(self, user_id: int, data: dict[str, Any]) -> None:
        conn = self._get_conn()
        with conn.transaction():
            conn.execute(
                sql.SQL("""
                INSERT INTO {} (user_id, data, updated_at)
                VALUES (%s, %s::jsonb, now())
                ON CONFLICT (user_id)
                DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                """).format(sql.Identifier(self._data_table)),
                (user_id, json.dumps(data)),
            )

    def update_data(self, user_id: int, **kwargs: Any) -> None:
        current = self.get_data(user_id)
        current.update(kwargs)
        self.set_data(user_id, current)

    def delete(self, user_id: int) -> None:
        conn = self._get_conn()
        with conn.transaction():
            conn.execute(
                sql.SQL("DELETE FROM {} WHERE user_id = %s").format(
                    sql.Identifier(self._states_table)
                ),
                (user_id,),
            )
            conn.execute(
                sql.SQL("DELETE FROM {} WHERE user_id = %s").format(
                    sql.Identifier(self._data_table)
                ),
                (user_id,),
            )
