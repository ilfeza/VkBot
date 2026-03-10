from __future__ import annotations

import pytest

from vk_bot import VKBot
from vk_bot.state.context import StateContext
from vk_bot.state.fsm import FSMRegistry, VKBotFSM
from vk_bot.state.group import StatesGroup
from vk_bot.state.manager import State


@pytest.fixture(autouse=True)
def clean_fsm_registry():
    FSMRegistry.clear()
    yield
    FSMRegistry.clear()


def test_define_states_group():
    class Form(StatesGroup):
        name = State()
        age = State("custom_age")

    assert Form.name == "Form:name"
    assert Form.age == "custom_age"
    assert Form.get_state("name") == "Form:name"
    assert "Form:name" in Form.get_all_states()
    assert Form.is_in_group("Form:name") is True
    assert "Form:name" in Form()


def test_state_str_repr_names():
    s = State()
    assert not str(s)
    assert repr(s) == "State(None)"

    class OtherForm(StatesGroup):
        a = State()

    s2 = OtherForm._states["a"]
    s2._name = None
    StatesGroup.__init_subclass__.__func__(OtherForm)

    assert OtherForm.get_state("unknown") is None
    assert OtherForm.is_in_group("unknown") is False
    inst = OtherForm()
    assert ("unknown" in inst) is False
    assert list(inst) == [OtherForm._states["a"]]
    assert repr(inst) == "<StatesGroup 'OtherForm'>"


def test_fsm_machine_setup_and_transitions():
    fsm = VKBotFSM("auth")
    assert fsm.name == "auth"

    with pytest.raises(RuntimeError):
        fsm.add_state("checking")
    with pytest.raises(RuntimeError):
        fsm.add_transition("started", "checking")

    assert fsm.get_next_states("started") == []

    fsm.set_initial("started")
    assert fsm.machine is not None

    log = []
    fsm.add_state("checking", group="login", on_enter=lambda ctx: log.append("enter"))
    fsm.add_state("active", on_exit=lambda ctx: log.append("exit"))

    assert fsm.is_in_group("checking", "login") is True
    assert fsm.is_in_group("active", "login") is False

    fsm.add_transition("started", "checking", action=lambda ctx: log.append("action"))
    fsm.add_transition("checking", "active", condition=lambda ctx: True)
    fsm.add_transition("checking", "failed", condition=lambda ctx: False)

    assert fsm.can_transition("started", "checking") is True
    assert fsm.can_transition("checking", "active") is True
    assert fsm.can_transition("checking", "failed") is False
    assert fsm.can_transition("started", "unknown") is False

    fsm.execute_transition("started", "checking")
    assert log == ["action", "enter"]

    log3 = []
    fsm.add_state("testexit", on_exit=lambda ctx: log3.append("exit_called"))
    fsm.add_state("any")
    fsm.add_transition("testexit", "any")

    fsm.execute_transition("testexit", "any")
    assert log3 == ["exit_called"]

    log2 = []
    fsm.add_state("testnone", on_enter=lambda ctx: log2.append("enter"))
    fsm.add_transition("started", "testnone")
    fsm.execute_transition(None, "testnone")
    assert log2 == ["enter"]

    fsm.add_state("target")
    fsm.add_transition("checking", "target")
    fsm.machine.add_transition("alt_to_target", "checking", "target")
    assert fsm.get_next_states("checking") == ["active", "failed", "target"]


def test_fsm_registry_and_machine():
    fsm = FSMRegistry.get_or_create("new")
    assert FSMRegistry.get_or_create("new") is fsm
    fsm2 = VKBotFSM("custom")
    FSMRegistry.register("custom", fsm2)
    assert FSMRegistry.get_or_create("custom") is fsm2
    FSMRegistry.clear()
    assert "custom" not in FSMRegistry._instances

    fsm3 = VKBotFSM()
    assert fsm3.can_transition(None, "anything") is True
    assert fsm3.can_transition("fromanything", "anything") is True


def test_state_context_integration_flow(bot: VKBot):
    class Flow(StatesGroup):
        init = State()
        step1 = State()
        done = State()

    fsm = VKBotFSM("my_flow")
    fsm.set_initial(Flow.init)
    fsm.add_state(Flow.step1, group="mygroup").add_transition(Flow.init, Flow.step1)
    fsm.add_state(Flow.done).add_transition(Flow.step1, Flow.done)
    FSMRegistry.register("my_flow", fsm)

    ctx = StateContext(bot, user_id=1, fsm_name="my_flow")

    assert ctx.get() is None
    assert ctx.data == {}
    assert ctx.is_in_group("mygroup") is False
    assert ctx.get_next_states() == []

    assert ctx.set(Flow.step1) is True
    assert ctx.current == Flow.step1
    assert ctx.is_state(Flow.step1) is True
    assert ctx.is_in_group("mygroup") is True

    ctx.update(username="john")
    assert ctx["username"] == "john"
    ctx["age"] = 30
    assert "age" in ctx
    assert "unknown" not in ctx
    assert ctx["unknown"] is None
    assert ctx.data == {"username": "john", "age": 30}

    assert Flow.done in ctx.get_next_states()

    with pytest.raises(ValueError, match="not allowed"):
        ctx.set("unknown_state")

    ctx.clear_data()
    assert ctx.data == {}
    assert ctx.current == Flow.step1

    ctx.finish()
    assert ctx.get() is None

    ctx.finish()
    assert ctx.get() is None
