from __future__ import annotations

import builtins
import importlib
import json
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vk_bot.state import storage as _storage_mod
from vk_bot.state.manager import StateManager
from vk_bot.state.storage import (
    BaseStorage,
    MemoryStorage,
    PostgresStorage,
    RedisStorage,
)


class TestBaseStorage:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseStorage()  # type: ignore[abstract]

    def test_pass_bodies_via_super(self):
        class _Impl(BaseStorage):
            def get_state(self, user_id: int) -> str | None:
                return super().get_state(user_id)  # type: ignore[safe-super]

            def set_state(self, user_id: int, state: str) -> None:
                super().set_state(user_id, state)  # type: ignore[safe-super]

            def get_data(self, user_id: int) -> dict[str, Any]:
                r = super().get_data(user_id)  # type: ignore[safe-super]
                return r if r is not None else {}

            def set_data(self, user_id: int, data: dict[str, Any]) -> None:
                super().set_data(user_id, data)  # type: ignore[safe-super]

            def update_data(self, user_id: int, **kwargs: Any) -> None:
                super().update_data(user_id, **kwargs)  # type: ignore[safe-super]

            def delete(self, user_id: int) -> None:
                super().delete(user_id)  # type: ignore[safe-super]

        impl = _Impl()
        assert impl.get_state(1) is None
        impl.set_state(1, "x")
        assert impl.get_data(1) == {}
        impl.set_data(1, {})
        impl.update_data(1, k="v")
        impl.delete(1)


class TestMemoryStorage:
    def test_get_state_missing(self, memory: MemoryStorage):
        assert memory.get_state(1) is None

    def test_set_and_get_state(self, memory: MemoryStorage):
        memory.set_state(1, "active")
        assert memory.get_state(1) == "active"

    def test_get_data_default_empty(self, memory: MemoryStorage):
        assert memory.get_data(99) == {}

    def test_get_data_returns_copy(self, memory: MemoryStorage):
        memory.set_data(1, {"key": "val"})
        copy = memory.get_data(1)
        copy["extra"] = True
        assert "extra" not in memory.get_data(1)

    def test_set_and_get_data(self, memory: MemoryStorage):
        memory.set_data(1, {"a": 1})
        assert memory.get_data(1) == {"a": 1}

    def test_update_data_existing_user(self, memory: MemoryStorage):
        memory.set_data(1, {"a": 1})
        memory.update_data(1, b=2)
        assert memory.get_data(1) == {"a": 1, "b": 2}

    def test_update_data_new_user(self, memory: MemoryStorage):
        memory.update_data(1, x=42)
        assert memory.get_data(1) == {"x": 42}

    def test_delete_clears(self, memory: MemoryStorage):
        memory.set_state(1, "s")
        memory.set_data(1, {"k": "v"})
        memory.delete(1)
        assert memory.get_state(1) is None
        assert memory.get_data(1) == {}

    def test_delete_nonexistent(self, memory: MemoryStorage):
        memory.delete(999)


@pytest.mark.skipif(not _storage_mod.redis_installed, reason="redis not installed")
class TestRedisStorage:
    @staticmethod
    def _make() -> tuple[RedisStorage, MagicMock]:
        mock_cls = MagicMock()
        with patch("vk_bot.state.storage.Redis", mock_cls):
            storage = RedisStorage()
        return storage, mock_cls.return_value

    def test_init_params(self):
        mock_cls = MagicMock()
        with patch("vk_bot.state.storage.Redis", mock_cls):
            RedisStorage(host="h", port=1234, db=5, password="pw")
        mock_cls.assert_called_once_with(
            host="h", port=1234, db=5, password="pw", decode_responses=True
        )

    def test_key_helpers(self):
        storage, _ = self._make()
        assert storage._state_key(7) == "vkbot:state:7"
        assert storage._data_key(7) == "vkbot:data:7"

    def test_get_state(self):
        storage, client = self._make()
        client.get.return_value = "waiting"
        assert storage.get_state(1) == "waiting"
        client.get.assert_called_with("vkbot:state:1")

    def test_set_state(self):
        storage, client = self._make()
        storage.set_state(1, "running")
        client.set.assert_called_with("vkbot:state:1", "running")

    def test_get_data_found(self):
        storage, client = self._make()
        client.get.return_value = json.dumps({"a": 1})
        assert storage.get_data(1) == {"a": 1}

    def test_get_data_not_found(self):
        storage, client = self._make()
        client.get.return_value = None
        assert storage.get_data(1) == {}

    def test_set_data(self):
        storage, client = self._make()
        storage.set_data(1, {"b": 2})
        client.set.assert_called_with("vkbot:data:1", json.dumps({"b": 2}))

    def test_update_data(self):
        storage, client = self._make()
        client.get.return_value = json.dumps({"a": 1})
        storage.update_data(1, b=2)
        client.set.assert_called_with("vkbot:data:1", json.dumps({"a": 1, "b": 2}))

    def test_delete(self):
        storage, client = self._make()
        storage.delete(1)
        assert client.delete.call_count == 2
        client.delete.assert_any_call("vkbot:state:1")
        client.delete.assert_any_call("vkbot:data:1")

    def test_import_error_guard(self):
        import vk_bot.state.storage as mod

        orig = mod.redis_installed
        mod.redis_installed = False
        try:
            with pytest.raises(ImportError, match="Redis is not installed"):
                RedisStorage()
        finally:
            mod.redis_installed = orig


class TestRedisImportBranch:
    def test_flag_false_when_redis_unavailable(self):
        import vk_bot.state.storage as mod

        saved: dict[str, Any] = {}
        for key in list(sys.modules):
            if key == "redis" or key.startswith("redis."):
                saved[key] = sys.modules.pop(key)

        real_import = builtins.__import__

        def _block(name: str, *a: Any, **kw: Any):  # type: ignore[no-untyped-def]
            if name == "redis" or name.startswith("redis."):
                raise ImportError("blocked for test")
            return real_import(name, *a, **kw)

        builtins.__import__ = _block  # type: ignore[assignment]
        try:
            importlib.reload(mod)
            assert mod.redis_installed is False
        finally:
            builtins.__import__ = real_import  # type: ignore[assignment]
            sys.modules.update(saved)
            importlib.reload(mod)


@pytest.mark.skipif(not _storage_mod.postgres_installed, reason="psycopg not installed")
class TestPostgresStorage:
    def test_import_error_when_not_installed(self):
        import vk_bot.state.storage as mod

        orig = mod.postgres_installed
        mod.postgres_installed = False
        try:
            with pytest.raises(ImportError, match="psycopg is not installed"):
                PostgresStorage("postgresql://localhost/test")
        finally:
            mod.postgres_installed = orig

    def test_all_methods_with_mocked_psycopg(self):
        import vk_bot.state.storage as mod

        mock_psycopg = MagicMock()
        mock_sql = MagicMock()
        mock_psycopg.sql = mock_sql

        mock_conn = MagicMock()
        mock_conn.closed = False
        mock_psycopg.connect.return_value = mock_conn

        orig_p = sys.modules.get("psycopg")
        orig_s = sys.modules.get("psycopg.sql")
        sys.modules["psycopg"] = mock_psycopg
        sys.modules["psycopg.sql"] = mock_sql

        try:
            importlib.reload(mod)
            assert mod.postgres_installed is True

            pg_cls = mod.PostgresStorage

            stor = pg_cls("postgresql://host/db", table_prefix="pfx")
            assert stor._dsn == "postgresql://host/db"
            assert stor._table_prefix == "pfx"
            assert stor._conn is None
            assert stor._states_table == "pfx_states"
            assert stor._data_table == "pfx_data"

            mock_result = MagicMock()
            mock_conn.execute.return_value = mock_result
            assert stor._get_conn() is mock_conn

            mock_psycopg.connect.reset_mock()
            assert stor._get_conn() is mock_conn
            mock_psycopg.connect.assert_not_called()

            mock_result.fetchone.return_value = ("active",)
            assert stor.get_state(1) == "active"
            mock_result.fetchone.return_value = None
            assert stor.get_state(2) is None

            stor.set_state(1, "waiting")

            mock_result.fetchone.return_value = ({"k": "v"},)
            assert stor.get_data(1) == {"k": "v"}
            mock_result.fetchone.return_value = None
            assert stor.get_data(2) == {}

            stor.set_data(1, {"new": True})
            mock_result.fetchone.return_value = ({"a": 1},)
            stor.update_data(1, b=2)
            stor.delete(1)

            stor._conn = MagicMock(closed=False)
            stor.close()
            assert stor._conn is None

            stor.close()

            closed_mock = MagicMock(closed=True)
            stor._conn = closed_mock
            stor.close()
            closed_mock.close.assert_not_called()

            stor._conn = MagicMock(closed=True)
            new_conn = MagicMock(closed=False)
            new_conn.execute.return_value = mock_result
            mock_psycopg.connect.return_value = new_conn
            assert stor._get_conn() is new_conn

        finally:
            if orig_p is not None:
                sys.modules["psycopg"] = orig_p
            else:
                sys.modules.pop("psycopg", None)
            if orig_s is not None:
                sys.modules["psycopg.sql"] = orig_s
            else:
                sys.modules.pop("psycopg.sql", None)
            importlib.reload(mod)


class TestStateManager:
    def test_default_storage(self):
        mgr = StateManager()
        assert isinstance(mgr.storage, MemoryStorage)

    def test_custom_storage(self):
        mock = MagicMock(spec=BaseStorage)
        assert StateManager(storage=mock).storage is mock

    def test_get_state_none(self, manager: StateManager):
        assert manager.get_state(1) is None

    def test_set_and_get_state(self, manager: StateManager):
        manager.set_state(1, "s1")
        assert manager.get_state(1) == "s1"

    def test_get_data_empty(self, manager: StateManager):
        assert manager.get_data(1) == {}

    def test_set_and_get_data(self, manager: StateManager):
        manager.set_data(1, {"k": "v"})
        assert manager.get_data(1) == {"k": "v"}

    def test_update_data(self, manager: StateManager):
        manager.set_data(1, {"a": 1})
        manager.update_data(1, b=2)
        assert manager.get_data(1) == {"a": 1, "b": 2}

    def test_reset(self, manager: StateManager):
        manager.set_state(1, "x")
        manager.set_data(1, {"k": "v"})
        manager.reset(1)
        assert manager.get_state(1) is None
        assert manager.get_data(1) == {}
