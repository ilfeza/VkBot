from collections.abc import Callable
from typing import Any

from transitions import Machine


class VKBotFSM:
    def __init__(self, name: str = "default"):
        self.name = name
        self.machine: Machine | None = None
        self.current_state: str | None = None
        self._state_groups: dict[str, list[str]] = {}

    def set_initial(self, state: str) -> "VKBotFSM":
        self.machine = Machine(model=self, states=[], initial=state)
        self.current_state = state
        return self

    def add_state(
        self,
        state: str,
        group: str | None = None,
        on_enter: Callable | None = None,
        on_exit: Callable | None = None,
        **kwargs,
    ) -> "VKBotFSM":
        if self.machine is None:
            raise RuntimeError("Call set_initial() before add_state()")
        self.machine.add_state(state, on_enter=on_enter, on_exit=on_exit)

        if group:
            if group not in self._state_groups:
                self._state_groups[group] = []
            self._state_groups[group].append(state)

        return self

    def add_transition(
        self,
        from_state: str,
        to_state: str,
        condition: Callable | None = None,
        action: Callable | None = None,
        **kwargs,
    ) -> "VKBotFSM":
        if self.machine is None:
            raise RuntimeError("Call set_initial() before add_transition()")
        trigger = f"to_{to_state}"
        conditions = [condition] if condition else None
        self.machine.add_transition(
            trigger, from_state, to_state,
            conditions=conditions,
            after=action,
        )
        return self

    def can_transition(self, from_state: str | None, to_state: str, context: Any = None) -> bool:
        if from_state is None or self.machine is None:
            return True

        for trans in self.machine.get_transitions(source=from_state, dest=to_state):
            if trans.conditions:
                for condition in trans.conditions:
                    if not condition(context):
                        return False
            return True
        return False

    def get_next_states(self, from_state: str, context: Any = None) -> list[str]:
        if self.machine is None:
            return []
        next_states = []
        for trans in self.machine.get_transitions(source=from_state):
            if trans.dest not in next_states:
                next_states.append(trans.dest)
        return next_states

    def transition(self, from_state: str | None, to_state: str, context: Any = None) -> bool:
        if to_state and self.machine is not None:
            trigger = f"to_{to_state}"
            if hasattr(self, trigger):
                getattr(self, trigger)()
            else:
                self.machine.add_transition("_temp", from_state, to_state)
                self._temp()

        self.current_state = to_state
        return True

    def reset(self) -> None:
        if self.machine is not None:
            self.current_state = self.machine.initial
            self.machine.set_state(self.current_state)
        else:
            self.current_state = None

    def is_state(self, state: str) -> bool:
        return self.current_state == state

    def is_in_group(self, group: str) -> bool:
        if not self.current_state:
            return False
        return self.current_state in self._state_groups.get(group, [])


class FSMRegistry:
    _instances: dict[str, VKBotFSM] = {}

    @classmethod
    def get_or_create(cls, name: str) -> VKBotFSM:
        if name not in cls._instances:
            cls._instances[name] = VKBotFSM(name)
        return cls._instances[name]

    @classmethod
    def register(cls, name: str, fsm: VKBotFSM) -> None:
        cls._instances[name] = fsm

    @classmethod
    def clear(cls) -> None:
        cls._instances.clear()
