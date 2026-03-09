from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vk_bot.state.fsm import FSMRegistry, VKBotFSM
from vk_bot.state.manager import StateManager

if TYPE_CHECKING:
    from vk_bot import VKBot


@dataclass(slots=True)
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

    _manager: StateManager = field(init=False, repr=False)
    fsm: "VKBotFSM" = field(init=False)

    def __post_init__(self) -> None:
        self._manager = self.bot.state_manager
        self.fsm = FSMRegistry.get_or_create(self.fsm_name)

    @property
    def current(self) -> str | None:
        """Current state of this user, read from storage."""
        return self._manager.get_state(self.user_id)

    def set(self, state: str) -> bool:
        """Transition the user to ``state``.

        Validates the transition against the FSM graph, executes any
        registered callbacks, then persists the new state to storage.

        Raises:
            ValueError: If the transition is not allowed by the graph.
        """
        current = self.current

        if not self.fsm.can_transition(current, state, self):
            raise ValueError(f"Transition from '{current}' to '{state}' not allowed")

        self.fsm.execute_transition(current, state, self)
        self._manager.set_state(self.user_id, state)
        return True

    def get(self) -> str | None:
        """Return the current state (alias for :attr:`current`)."""
        return self.current

    def finish(self) -> None:
        """Reset the user's state and clear all stored data."""
        self._manager.reset(self.user_id)

    @property
    def data(self) -> dict[str, Any]:
        """User data stored alongside the state."""
        return self._manager.get_data(self.user_id)

    def update(self, **kwargs: Any) -> None:
        """Merge ``kwargs`` into the user's stored data."""
        self._manager.update_data(self.user_id, **kwargs)

    def clear_data(self) -> None:
        """Clear all user data without resetting the state."""
        self._manager.set_data(self.user_id, {})

    def is_state(self, state: str) -> bool:
        """Return ``True`` if the user is currently in ``state``."""
        return self.current == state

    def is_in_group(self, group: str) -> bool:
        """Return ``True`` if the user's current state belongs to ``group``."""
        current = self.current
        if not current:
            return False
        return self.fsm.is_in_group(current, group)

    def get_next_states(self) -> list[str]:
        """Return all states reachable from the user's current state."""
        current = self.current
        if current is None:
            return []
        return self.fsm.get_next_states(current, self)

    def __getitem__(self, key: str) -> Any:
        return self.data.get(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.update(**{key: value})

    def __contains__(self, key: str) -> bool:
        return key in self.data
