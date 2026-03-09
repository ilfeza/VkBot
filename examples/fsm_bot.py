import logging
import os

from vk_bot import VKBot, types
from vk_bot.state.context import StateContext
from vk_bot.state.group import StatesGroup
from vk_bot.state.manager import State

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

bot = VKBot(token=os.getenv("VK_TOKEN", "YOUR_TOKEN"))


class RegistrationForm(StatesGroup):
    name = State()
    age = State()


@bot.message_handler(commands=["register"])
def cmd_register(message: types.Message, state: StateContext):
    state.set(RegistrationForm.name)
    bot.send_message(message.from_id, "Please enter your name:")


@bot.message_handler(state=RegistrationForm.name)
def process_name(message: types.Message, state: StateContext):
    state["name"] = message.text
    state.set(RegistrationForm.age)
    bot.send_message(message.from_id, "Please enter your age:")


@bot.message_handler(state=RegistrationForm.age)
def process_age(message: types.Message, state: StateContext):
    if not message.text or not message.text.isdigit():
        bot.send_message(message.from_id, "Age must be an integer. Please try again:")
        return

    state["age"] = int(message.text)
    name = state.data.get("name", "Unknown")
    age = state.data.get("age", 0)

    state.finish()
    bot.send_message(message.from_id, f"Registration complete. Name: {name}, Age: {age}.")


if __name__ == "__main__":
    bot.polling()
