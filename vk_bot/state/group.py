from collections.abc import Iterator
from typing import Any

from vk_bot.state.manager import State


class StatesGroup:
    _states: dict[str, State]

    @classmethod
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        cls._states = {}
        for key, value in cls.__dict__.items():
            if isinstance(value, State):
                cls._states[key] = value
                if not value._name:
                    value._name = f"{cls.__name__}:{key}"

    @classmethod
    def get_state(cls, name: str) -> str | None:
        state = cls._states.get(name)
        return state._name if state else None

    @classmethod
    def get_all_states(cls) -> list[str]:
        return [state._name for state in cls._states.values() if state._name]

    @classmethod
    def is_in_group(cls, state: str) -> bool:
        return any(state == s._name for s in cls._states.values())

    def __contains__(self, item: str) -> bool:
        return any(state._name == item for state in self._states.values())

    def __iter__(self) -> Iterator[State]:
        return iter(self._states.values())

    def __repr__(self) -> str:
        return f"<StatesGroup '{self.__class__.__name__}'>"
