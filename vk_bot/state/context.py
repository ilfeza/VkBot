from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vk_bot.state.fsm import FSMRegistry, VKBotFSM

if TYPE_CHECKING:
    from vk_bot import VKBot


@dataclass
class StateContext:
    """User state context.

    Provides a convenient interface for managing FSM states
    and user data within handlers.

    Args:
        bot: VKBot instance.
        user_id: User ID.
        fsm_name: Finite state machine name.
    """

    bot: "VKBot"
    user_id: int
    fsm_name: str = "default"

    _manager: Any = field(init=False, repr=False)
    fsm: "VKBotFSM" = field(init=False)

    def __post_init__(self):
        self._manager = self.bot.state_manager
        self.fsm = FSMRegistry.get_or_create(self.fsm_name)

    @property
    def current(self) -> str | None:
        return self._manager.get_state(self.user_id)

    def set(self, state: str) -> bool:
        current = self.current

        if not self.fsm.can_transition(current, state, self):
            raise ValueError(f"Transition from '{current}' to '{state}' not allowed")

        self.fsm.transition(current, state, self)
        self._manager.set_state(self.user_id, state)
        return True

    def get(self) -> str | None:
        return self.current

    def finish(self):
        self._manager.reset(self.user_id)
        if self.fsm.current_state:
            self.fsm.transition(self.fsm.current_state, None, self)
        self.fsm.current_state = None

    @property
    def data(self) -> dict[str, Any]:
        return self._manager.get_data(self.user_id)

    def update(self, **kwargs):
        self._manager.update_data(self.user_id, **kwargs)

    def clear_data(self):
        self._manager.set_data(self.user_id, {})

    def is_state(self, state: str) -> bool:
        return self.current == state

    def is_in_group(self, group: str) -> bool:
        if not self.current:
            return False
        return self.fsm.is_in_group(group)

    def get_next_states(self) -> list:
        return self.fsm.get_next_states(self.current, self)

    def __getitem__(self, key: str) -> Any:
        return self.data.get(key)

    def __setitem__(self, key: str, value: Any):
        self.update(**{key: value})

    def __contains__(self, key: str) -> bool:
        return key in self.data
