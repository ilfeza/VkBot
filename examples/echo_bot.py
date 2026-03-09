import os

from vk_bot import VKBot, types

bot = VKBot(os.getenv("VK_TOKEN", "YOUR_TOKEN"))


@bot.message_handler()
def send_echo(message: types.Message):
    bot.send_message(message.from_id, message.text or "")


if __name__ == "__main__":
    bot.polling()
