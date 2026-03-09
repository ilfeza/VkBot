from __future__ import annotations

import builtins
import importlib
import json
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from vk_bot import VKBot
from vk_bot.state.context import StateContext
from vk_bot.state.fsm import FSMRegistry, VKBotFSM
from vk_bot.state.group import StatesGroup
from vk_bot.state.manager import State, StateManager
from vk_bot.state.storage import (
    BaseStorage,
    MemoryStorage,
    PostgresStorage,
    RedisStorage,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    FSMRegistry.clear()
    yield
    FSMRegistry.clear()


@pytest.fixture
def memory() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def manager() -> StateManager:
    return StateManager()


class TestBaseStorage:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseStorage()  # type: ignore[abstract]

    def test_pass_bodies_via_super(self):
        class _Impl(BaseStorage):
            def get_state(self, user_id: int) -> str | None:
                return super().get_state(user_id)

            def set_state(self, user_id: int, state: str) -> None:
                super().set_state(user_id, state)

            def get_data(self, user_id: int) -> dict[str, Any]:
                r = super().get_data(user_id)
                return r if r is not None else {}

            def set_data(self, user_id: int, data: dict[str, Any]) -> None:
                super().set_data(user_id, data)

            def update_data(self, user_id: int, **kwargs: Any) -> None:
                super().update_data(user_id, **kwargs)

            def delete(self, user_id: int) -> None:
                super().delete(user_id)

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


class TestPostgresStorage:
    def test_import_error_when_not_installed(self):
        with pytest.raises(ImportError, match="psycopg is not installed"):
            PostgresStorage("postgresql://localhost/test")

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


class TestState:
    def test_init_no_name(self):
        assert State()._name is None

    def test_init_with_name(self):
        assert State("custom")._name == "custom"

    def test_set_name_auto(self):
        state = State()

        class Owner:
            pass

        state.__set_name__(Owner, "field")
        assert state._name == "Owner:field"

    def test_set_name_preserves_existing(self):
        state = State("keep")

        class Owner:
            pass

        state.__set_name__(Owner, "field")
        assert state._name == "keep"

    def test_descriptor_get_class(self):
        class Bag:
            waiting = State()

        assert Bag.waiting == "Bag:waiting"

    def test_descriptor_get_instance(self):
        class Bag:
            waiting = State()

        assert Bag().waiting == "Bag:waiting"

    def test_str_with_name(self):
        assert str(State("s1")) == "s1"

    def test_str_without_name(self):
        assert not str(State())

    def test_repr_with_name(self):
        assert repr(State("t")) == "State(t)"

    def test_repr_none(self):
        assert repr(State()) == "State(None)"


class TestStatesGroup:
    def test_auto_names(self):
        class Reg(StatesGroup):
            name = State()
            age = State()

        assert Reg.name == "Reg:name"
        assert Reg.age == "Reg:age"

    def test_preserves_custom_name(self):
        class Grp(StatesGroup):
            custom = State("my_name")

        assert Grp.custom == "my_name"

    def test_get_state_found(self):
        class Grp(StatesGroup):
            name = State()

        assert Grp.get_state("name") == "Grp:name"

    def test_get_state_not_found(self):
        class Grp(StatesGroup):
            name = State()

        assert Grp.get_state("missing") is None

    def test_get_all_states(self):
        class Grp(StatesGroup):
            a = State()
            b = State()

        assert set(Grp.get_all_states()) == {"Grp:a", "Grp:b"}

    def test_is_in_group(self):
        class Grp(StatesGroup):
            x = State()

        assert Grp.is_in_group("Grp:x") is True
        assert Grp.is_in_group("Other:y") is False

    def test_contains(self):
        class Grp(StatesGroup):
            x = State()

        inst = Grp()
        assert ("Grp:x" in inst) is True
        assert ("nope" in inst) is False

    def test_iter(self):
        class Grp(StatesGroup):
            a = State()
            b = State()

        assert all(isinstance(s, State) for s in Grp())

    def test_repr(self):
        class Grp(StatesGroup):
            a = State()

        assert repr(Grp()) == "<StatesGroup 'Grp'>"

    def test_init_subclass_names_unnamed_state(self):
        class Grp(StatesGroup):
            s = State()

        state_obj = Grp._states["s"]
        assert state_obj._name == "Grp:s"

        state_obj._name = None
        StatesGroup.__init_subclass__.__func__(Grp)  # type: ignore[attr-defined]
        assert state_obj._name == "Grp:s"


class TestVKBotFSM:
    def test_init_defaults(self):
        fsm = VKBotFSM()
        assert fsm.name == "default"
        assert fsm.machine is None

    def test_init_custom_name(self):
        assert VKBotFSM("alt").name == "alt"


    def test_set_initial(self):
        fsm = VKBotFSM()
        result = fsm.set_initial("start")
        assert result is fsm
        assert fsm.machine is not None

    def test_set_initial_stores_initial(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        assert fsm._initial == "init"


    def test_add_state_no_machine(self):
        with pytest.raises(RuntimeError, match="set_initial"):
            VKBotFSM().add_state("s1")

    def test_add_state_returns_self(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        assert fsm.add_state("s1") is fsm

    def test_add_state_with_group(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1", group="g")
        fsm.add_state("s2", group="g")
        assert fsm._state_groups["g"] == ["s1", "s2"]

    def test_add_state_without_group(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        assert not fsm._state_groups

    def test_add_state_with_on_enter(self):
        calls: list[str] = []
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1", on_enter=lambda ctx: calls.append("enter"))
        assert "s1" in fsm._on_enter

    def test_add_state_with_on_exit(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1", on_exit=lambda ctx: None)
        assert "s1" in fsm._on_exit


    def test_add_transition_no_machine(self):
        with pytest.raises(RuntimeError, match="set_initial"):
            VKBotFSM().add_transition("a", "b")

    def test_add_transition_returns_self(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        assert fsm.add_transition("init", "s1") is fsm

    def test_add_transition_registers_condition(self):
        cond = lambda ctx: True  # noqa: E731
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1", condition=cond)
        assert cond in fsm._conditions[("init", "s1")]

    def test_add_transition_registers_action(self):
        action = lambda ctx: None  # noqa: E731
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1", action=action)
        assert action in fsm._actions[("init", "s1")]

    def test_add_transition_no_condition(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1")
        assert ("init", "s1") not in fsm._conditions


    def test_can_transition_from_none(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        assert fsm.can_transition(None, "any") is True

    def test_can_transition_no_machine(self):
        assert VKBotFSM().can_transition("a", "b") is True

    def test_can_transition_allowed(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1")
        assert fsm.can_transition("init", "s1") is True

    def test_can_transition_no_route(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        assert fsm.can_transition("init", "unknown") is False

    def test_can_transition_condition_passes(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1", condition=lambda ctx: True)
        assert fsm.can_transition("init", "s1") is True

    def test_can_transition_condition_fails(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1", condition=lambda ctx: False)
        assert fsm.can_transition("init", "s1") is False


    def test_get_next_states_no_machine(self):
        assert VKBotFSM().get_next_states("init") == []

    def test_get_next_states(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_state("s2")
        fsm.add_transition("init", "s1")
        fsm.add_transition("init", "s2")
        result = fsm.get_next_states("init")
        assert "s1" in result
        assert "s2" in result

    def test_get_next_states_deduplicates(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1")
        assert fsm.machine is not None
        fsm.machine.add_transition("alt", "init", "s1")
        assert fsm.get_next_states("init").count("s1") == 1


    def test_is_in_group_true(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1", group="grp")
        assert fsm.is_in_group("s1", "grp") is True

    def test_is_in_group_false_wrong_state(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1", group="grp")
        assert fsm.is_in_group("init", "grp") is False

    def test_is_in_group_unknown_group(self):
        fsm = VKBotFSM()
        assert fsm.is_in_group("any", "nonexistent") is False


    def test_execute_transition_runs_on_exit(self):
        log: list[str] = []
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("init", on_exit=lambda ctx: log.append("exit:init"))
        fsm.add_state("s1")
        fsm.add_transition("init", "s1")
        fsm.execute_transition("init", "s1")
        assert "exit:init" in log

    def test_execute_transition_runs_on_enter(self):
        log: list[str] = []
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1", on_enter=lambda ctx: log.append("enter:s1"))
        fsm.add_transition("init", "s1")
        fsm.execute_transition("init", "s1")
        assert "enter:s1" in log

    def test_execute_transition_runs_action(self):
        log: list[str] = []
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1", action=lambda ctx: log.append("action"))
        fsm.execute_transition("init", "s1")
        assert "action" in log

    def test_execute_transition_callback_order(self):
        """on_exit → action → on_enter."""
        log: list[str] = []
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("init", on_exit=lambda ctx: log.append("exit"))
        fsm.add_state("s1", on_enter=lambda ctx: log.append("enter"))
        fsm.add_transition("init", "s1", action=lambda ctx: log.append("action"))
        fsm.execute_transition("init", "s1")
        assert log == ["exit", "action", "enter"]

    def test_execute_transition_from_none_skips_on_exit(self):
        log: list[str] = []
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1", on_enter=lambda ctx: log.append("enter"))
        fsm.execute_transition(None, "s1")
        assert log == ["enter"]

    def test_execute_transition_does_not_store_state(self):
        """FSM must not gain a current_state attribute after execute_transition."""
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1")
        fsm.execute_transition("init", "s1")
        assert not hasattr(fsm, "current_state")

    def test_execute_transition_no_callbacks_is_noop(self):
        fsm = VKBotFSM()
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.execute_transition("init", "s1")  # must not raise


class TestFSMRegistry:
    def test_get_or_create_new(self):
        fsm = FSMRegistry.get_or_create("new")
        assert isinstance(fsm, VKBotFSM)
        assert fsm.name == "new"

    def test_get_or_create_existing(self):
        first = FSMRegistry.get_or_create("x")
        assert FSMRegistry.get_or_create("x") is first

    def test_register(self):
        custom = VKBotFSM("c")
        FSMRegistry.register("c", custom)
        assert FSMRegistry.get_or_create("c") is custom

    def test_clear(self):
        FSMRegistry.get_or_create("tmp")
        FSMRegistry.clear()
        fresh = FSMRegistry.get_or_create("tmp")
        assert fresh.name == "tmp"


# StateContext

class TestStateContext:
    def test_post_init(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        assert ctx._manager is bot.state_manager
        assert isinstance(ctx.fsm, VKBotFSM)

    def test_current_none(self, bot: VKBot):
        assert StateContext(bot=bot, user_id=1).current is None

    def test_set_returns_true(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        assert ctx.set("active") is True
        assert ctx.current == "active"

    def test_set_transition_not_allowed(self, bot: VKBot):
        fsm = VKBotFSM("strict")
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1")
        FSMRegistry.register("strict", fsm)

        ctx = StateContext(bot=bot, user_id=1, fsm_name="strict")
        ctx.set("s1")
        with (
            patch.object(ctx.fsm, "can_transition", return_value=False),
            pytest.raises(ValueError, match="not allowed"),
        ):
            ctx.set("init")

    def test_set_calls_execute_transition(self, bot: VKBot):
        """execute_transition must be called so callbacks fire."""
        log: list[str] = []
        fsm = VKBotFSM("cb")
        fsm.set_initial("init")
        fsm.add_state("s1", on_enter=lambda ctx: log.append("enter"))
        FSMRegistry.register("cb", fsm)

        ctx = StateContext(bot=bot, user_id=1, fsm_name="cb")
        ctx.set("s1")
        assert "enter" in log

    def test_get(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        assert ctx.get() is None
        ctx.set("s")
        assert ctx.get() == "s"

    def test_finish_resets_storage(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        ctx.set("active")
        ctx.update(key="val")
        ctx.finish()
        assert ctx.current is None
        assert ctx.data == {}

    def test_finish_without_current_state(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        ctx.finish()
        assert ctx.current is None

    def test_data_property(self, bot: VKBot):
        assert StateContext(bot=bot, user_id=1).data == {}

    def test_update(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        ctx.update(name="Alice", age=30)
        assert ctx.data == {"name": "Alice", "age": 30}

    def test_clear_data(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        ctx.update(a=1)
        ctx.clear_data()
        assert ctx.data == {}

    def test_is_state(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        assert ctx.is_state("x") is False
        ctx.set("x")
        assert ctx.is_state("x") is True

    def test_is_in_group_no_state(self, bot: VKBot):
        assert StateContext(bot=bot, user_id=1).is_in_group("grp") is False

    def test_is_in_group_true(self, bot: VKBot):
        fsm = VKBotFSM("g1")
        fsm.set_initial("init")
        fsm.add_state("s1", group="grp")
        FSMRegistry.register("g1", fsm)

        ctx = StateContext(bot=bot, user_id=1, fsm_name="g1")
        ctx.set("s1")
        assert ctx.is_in_group("grp") is True

    def test_is_in_group_false(self, bot: VKBot):
        fsm = VKBotFSM("g2")
        fsm.set_initial("init")
        fsm.add_state("s1", group="grp")
        FSMRegistry.register("g2", fsm)

        ctx = StateContext(bot=bot, user_id=1, fsm_name="g2")
        ctx.set("s1")
        assert ctx.is_in_group("other") is False

    def test_is_in_group_reads_from_storage(self, bot: VKBot):
        """is_in_group must use storage state, not fsm.current_state."""
        fsm = VKBotFSM("isolation_grp")
        fsm.set_initial("init")
        fsm.add_state("s1", group="grp")
        FSMRegistry.register("isolation_grp", fsm)

        ctx_a = StateContext(bot=bot, user_id=1, fsm_name="isolation_grp")
        ctx_b = StateContext(bot=bot, user_id=2, fsm_name="isolation_grp")

        ctx_a.set("s1")    # user A in group "grp"
        ctx_b.set("init")  # user B NOT in group "grp"

        assert ctx_a.is_in_group("grp") is True
        assert ctx_b.is_in_group("grp") is False  # must not see user A's state

    def test_get_next_states(self, bot: VKBot):
        fsm = VKBotFSM("n1")
        fsm.set_initial("init")
        fsm.add_state("s1")
        fsm.add_transition("init", "s1")
        FSMRegistry.register("n1", fsm)

        ctx = StateContext(bot=bot, user_id=1, fsm_name="n1")
        ctx.set("init")
        assert "s1" in ctx.get_next_states()

    def test_get_next_states_no_current(self, bot: VKBot):
        assert StateContext(bot=bot, user_id=1).get_next_states() == []

    def test_getitem(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        ctx.update(key="val")
        assert ctx["key"] == "val"
        assert ctx["missing"] is None

    def test_setitem(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        ctx["x"] = 42
        assert ctx.data["x"] == 42

    def test_contains(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1)
        ctx.update(k=1)
        assert ("k" in ctx) is True
        assert ("nope" in ctx) is False

    def test_custom_fsm_name(self, bot: VKBot):
        ctx = StateContext(bot=bot, user_id=1, fsm_name="alt")
        assert ctx.fsm.name == "alt"

    def test_two_users_state_isolation(self, bot: VKBot):
        """Demonstrate the fix: two users on the same FSM cannot affect each other."""
        fsm = VKBotFSM("shared")
        fsm.set_initial("idle")
        fsm.add_state("step1", group="flow")
        fsm.add_state("step2", group="flow")
        FSMRegistry.register("shared", fsm)

        ctx_a = StateContext(bot=bot, user_id=100, fsm_name="shared")
        ctx_b = StateContext(bot=bot, user_id=200, fsm_name="shared")

        ctx_a.set("step1")
        ctx_b.set("step2")

        # Each user's state lives in storage, never mixed
        assert ctx_a.current == "step1"
        assert ctx_b.current == "step2"
        assert ctx_a.is_in_group("flow") is True
        assert ctx_b.is_in_group("flow") is True
        # Finish user A — user B is unaffected
        ctx_a.finish()
        assert ctx_a.current is None
        assert ctx_b.current == "step2"
