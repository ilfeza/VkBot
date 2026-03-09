# vk-bot

[![test](https://github.com/SarkisDarbinyan/vk-bot/actions/workflows/test.yml/badge.svg?event=push)](https://github.com/SarkisDarbinyan/vk-bot/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/SarkisDarbinyan/vk-bot/branch/master/graph/badge.svg)](https://codecov.io/gh/SarkisDarbinyan/vk-bot)
[![Python Version](https://img.shields.io/pypi/pyversions/vk-bot.svg)](https://pypi.org/project/vk-bot/)
[![wemake-python-styleguide](https://img.shields.io/badge/style-wemake-000000.svg)](https://github.com/wemake-services/wemake-python-styleguide)

This is how python package should look like!

## Features

- Fully typed with annotations and checked with mypy, [PEP561 compatible](https://www.python.org/dev/peps/pep-0561/)
- Add yours!

## Installation

```bash
pip install vk-bot
```

## Example

```python
from vk_bot import VKBot

bot = VKBot("GROUP_TOKEN")


@bot.message_handler()
def send_echo(message):
    bot.send_message(message.from_id, message.text)


bot.polling()
```

See more in the [examples/](examples/) directory.

## License

[MIT](https://github.com/SarkisDarbinyan/vk-bot/blob/master/LICENSE)

## Credits

This project was generated with [`wemake-python-package`](https://github.com/wemake-services/wemake-python-package). Current template version is: [e3cab866e50d526b65f72bde238102e44526d8fd](https://github.com/wemake-services/wemake-python-package/tree/e3cab866e50d526b65f72bde238102e44526d8fd). See what is [updated](https://github.com/wemake-services/wemake-python-package/compare/e3cab866e50d526b65f72bde238102e44526d8fd...master) since then.
