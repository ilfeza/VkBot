"""FSM graph definition — stateless, shared between all users.

``VKBotFSM`` stores only the transition graph: allowed transitions,
conditions, state groups, and enter/exit callbacks.

Per-user state is **never** stored here. It is managed exclusively by
:class:`~vk_bot.state.manager.StateManager` and the underlying storage backend.
"""

from collections.abc import Callable
from typing import Any

from transitions import Machine


class VKBotFSM:
    """Finite-state-machine graph shared across all users.

    Use :meth:`set_initial`, :meth:`add_state`, :meth:`add_transition` to
    define the graph, then let :class:`~vk_bot.state.context.StateContext`
    drive per-user transitions.

    Args:
        name: Identifier used by :class:`FSMRegistry`.
    """

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self.machine: Machine | None = None
        self._initial: str | None = None
        self._state_groups: dict[str, list[str]] = {}
        self._conditions: dict[tuple[str, str], list[Callable[..., Any]]] = {}
        self._actions: dict[tuple[str, str], list[Callable[..., Any]]] = {}
        self._on_enter: dict[str, list[Callable[..., Any]]] = {}
        self._on_exit: dict[str, list[Callable[..., Any]]] = {}

    def set_initial(self, state: str) -> "VKBotFSM":
        """Set the initial state and create the internal Machine graph.

        Must be called before :meth:`add_state` or :meth:`add_transition`.

        Args:
            state: Name of the initial state.
        """
        self._initial = state
        self.machine = Machine(
            model=[],
            states=[state],
            initial=state,
            auto_transitions=False,
        )
        return self

    def add_state(
        self,
        state: str,
        group: str | None = None,
        on_enter: Callable[..., Any] | None = None,
        on_exit: Callable[..., Any] | None = None,
        **kwargs: Any,
    ) -> "VKBotFSM":
        """Register a state in the graph.

        Args:
            state: State name.
            group: Optional group name for grouping related states.
            on_enter: Callback invoked when entering this state.
            on_exit: Callback invoked when exiting this state.
        """
        if self.machine is None:
            raise RuntimeError("Call set_initial() before add_state()")
        self.machine.add_state(state)

        if group:
            self._state_groups.setdefault(group, []).append(state)
        if on_enter is not None:
            self._on_enter.setdefault(state, []).append(on_enter)
        if on_exit is not None:
            self._on_exit.setdefault(state, []).append(on_exit)
        return self

    def add_transition(
        self,
        from_state: str,
        to_state: str,
        condition: Callable[..., Any] | None = None,
        action: Callable[..., Any] | None = None,
        **kwargs: Any,
    ) -> "VKBotFSM":
        """Register an allowed transition between two states.

        Args:
            from_state: Source state.
            to_state: Destination state.
            condition: Callable ``(context) -> bool``; transition is blocked
                if it returns ``False``.
            action: Callable invoked during the transition.
        """
        if self.machine is None:
            raise RuntimeError("Call set_initial() before add_transition()")
        trigger = f"to_{to_state}"
        self.machine.add_transition(trigger, from_state, to_state)

        key = (from_state, to_state)
        if condition is not None:
            self._conditions.setdefault(key, []).append(condition)
        if action is not None:
            self._actions.setdefault(key, []).append(action)
        return self

    def can_transition(
        self, from_state: str | None, to_state: str, context: Any = None
    ) -> bool:
        """Return ``True`` if the transition ``from_state → to_state`` is allowed.

        A transition is allowed when it exists in the graph *and* all
        registered conditions evaluate to ``True``.

        If ``from_state`` is ``None`` or no Machine has been defined, every
        transition is permitted (open FSM).
        """
        if from_state is None or self.machine is None:
            return True
        if not self.machine.get_transitions(source=from_state, dest=to_state):
            return False
        conditions = self._conditions.get((from_state, to_state), [])
        return all(cond(context) for cond in conditions)

    def get_next_states(self, from_state: str, context: Any = None) -> list[str]:
        """Return the list of states reachable from ``from_state``.

        Deduplicates destinations so each state appears at most once.
        """
        if self.machine is None:
            return []
        seen: list[str] = []
        for trans in self.machine.get_transitions(source=from_state):
            if trans.dest not in seen:
                seen.append(trans.dest)
        return seen

    def is_in_group(self, state: str, group: str) -> bool:
        """Return ``True`` if ``state`` belongs to ``group``.

        Args:
            state: The current state string (read from storage by the caller).
            group: Group name to check membership in.
        """
        return state in self._state_groups.get(group, [])

    def execute_transition(
        self,
        from_state: str | None,
        to_state: str,
        context: Any = None,
    ) -> None:
        """Execute callbacks associated with a transition.

        Runs (in order): on_exit of ``from_state``, transition ``action``,
        on_enter of ``to_state``.

        Does **not** store any state — the caller is responsible for
        persisting the new state to storage.

        Args:
            from_state: Current state (``None`` for the very first transition).
            to_state: Destination state.
            context: Arbitrary context object forwarded to each callback.
        """
        if from_state is not None:
            for cb in self._on_exit.get(from_state, []):
                cb(context)
        for cb in self._actions.get((from_state, to_state), []):
            cb(context)
        for cb in self._on_enter.get(to_state, []):
            cb(context)


class FSMRegistry:
    """Global registry of named :class:`VKBotFSM` instances.

    One FSM graph is defined per logical flow (e.g. ``"registration"``).
    It is shared between all users; **it does not store per-user state**.
    """

    _instances: dict[str, VKBotFSM] = {}

    @classmethod
    def get_or_create(cls, name: str) -> VKBotFSM:
        """Return an existing FSM by name or create a fresh one."""
        if name not in cls._instances:
            cls._instances[name] = VKBotFSM(name)
        return cls._instances[name]

    @classmethod
    def register(cls, name: str, fsm: VKBotFSM) -> None:
        """Manually register a pre-built FSM under ``name``."""
        cls._instances[name] = fsm

    @classmethod
    def clear(cls) -> None:
        """Remove all registered FSMs (primarily used in tests)."""
        cls._instances.clear()
