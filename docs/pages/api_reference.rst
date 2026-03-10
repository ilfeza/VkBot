API Reference
==============

Автоматически сгенерированная документация из исходного кода.
Для руководств с примерами смотрите соответствующие разделы документации.

VKBot
-----

.. autoclass:: vk_bot.VKBot
   :members:
   :undoc-members:
   :show-inheritance:

Types
-----

.. automodule:: vk_bot.types
   :members:
   :undoc-members:
   :show-inheritance:

FSM
---

Transitions
~~~~~~~~~~~

.. autoclass:: vk_bot.state.fsm.VKBotFSM
   :members:
   :undoc-members:

.. autoclass:: vk_bot.state.fsm.FSMRegistry
   :members:
   :undoc-members:

StatesGroup
~~~~~~~~~~~

.. autoclass:: vk_bot.state.group.StatesGroup
   :members:
   :undoc-members:

.. autoclass:: vk_bot.state.manager.State
   :members:
   :undoc-members:

StateContext
~~~~~~~~~~~~

.. autoclass:: vk_bot.state.context.StateContext
   :members:
   :undoc-members:

Storage
-------

.. autoclass:: vk_bot.state.storage.BaseStorage
   :members:
   :undoc-members:

.. autoclass:: vk_bot.state.storage.MemoryStorage
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: vk_bot.state.storage.RedisStorage
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: vk_bot.state.storage.PostgresStorage
   :members:
   :undoc-members:
   :show-inheritance:

HttpConfig
----------

.. autoclass:: vk_bot.config.HttpConfig
   :members:
   :undoc-members:

Exceptions
----------

.. autoclass:: vk_bot.exception.VKAPIError
   :members:
   :undoc-members:

Utilities
---------

.. automodule:: vk_bot.util
   :members:
   :undoc-members:

Handlers
--------

.. autofunction:: vk_bot.handlers.extract_command

.. autofunction:: vk_bot.handlers.extract_mentions

.. autofunction:: vk_bot.handlers.is_group_event

