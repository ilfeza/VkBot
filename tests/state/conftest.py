from __future__ import annotations

import pytest

from vk_bot.state.fsm import FSMRegistry
from vk_bot.state.manager import StateManager
from vk_bot.state.storage import MemoryStorage


@pytest.fixture(autouse=True)
def clean_fsm_registry():
    FSMRegistry.clear()
    yield
    FSMRegistry.clear()


@pytest.fixture
def memory() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def manager() -> StateManager:
    return StateManager()
