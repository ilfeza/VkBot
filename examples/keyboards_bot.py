import logging
import os

from vk_bot import VKBot, types

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

bot = VKBot(token=os.getenv("VK_TOKEN", "YOUR_TOKEN"))


@bot.message_handler(commands=["menu"])
def cmd_menu(message: types.Message):
    kb = types.ReplyKeyboardMarkup(one_time_keyboard=False)
    kb.add(
        types.KeyboardButton(text="Statistics", color="primary"),
        types.KeyboardButton(text="Settings", color="secondary"),
    )
    kb.add(
        types.KeyboardButton(text="Help", color="positive"),
        types.KeyboardButton(text="Close", color="negative"),
    )
    bot.send_message(message.from_id, "Main Menu:", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "Statistics")
def handle_statistics(message: types.Message):
    bot.send_message(message.from_id, "Users: 42\nMessages: 1337")


@bot.message_handler(func=lambda m: m.text == "Settings")
def handle_settings(message: types.Message):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(text="Notifications", callback_data="toggle_notifications"),
        types.InlineKeyboardButton(text="Theme", callback_data="toggle_theme"),
    )
    kb.add(types.InlineKeyboardButton(text="Back", callback_data="back_to_menu"))
    bot.send_message(message.from_id, "Settings Menu:", reply_markup=kb)


@bot.message_handler(func=lambda m: m.text == "Close")
def handle_close(message: types.Message):
    kb = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    bot.send_message(message.from_id, "Menu closed. Type /menu to open again.", reply_markup=kb)


@bot.message_handler(commands=["inline"])
def cmd_inline(message: types.Message):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton(text="Like", callback_data="btn_like"),
        types.InlineKeyboardButton(text="Dislike", callback_data="btn_dislike"),
    )
    kb.add(types.InlineKeyboardButton(text="Open Website", url="https://vk.com"))
    bot.send_message(message.from_id, "Rate this bot:", reply_markup=kb)


@bot.callback_query_handler(data="btn_like")
def on_like(callback: types.CallbackQuery):
    bot.answer_callback_query(
        callback.id, callback.from_id, callback.peer_id, text="Thank you for your rating."
    )


@bot.callback_query_handler(data="btn_dislike")
def on_dislike(callback: types.CallbackQuery):
    bot.answer_callback_query(
        callback.id, callback.from_id, callback.peer_id, text="Your feedback has been recorded."
    )


@bot.callback_query_handler(data="toggle_notifications")
def on_toggle_notifications(callback: types.CallbackQuery):
    bot.answer_callback_query(
        callback.id, callback.from_id, callback.peer_id, text="Notifications updated."
    )


@bot.callback_query_handler(data="toggle_theme")
def on_toggle_theme(callback: types.CallbackQuery):
    bot.answer_callback_query(
        callback.id, callback.from_id, callback.peer_id, text="Theme updated."
    )


@bot.callback_query_handler(data="back_to_menu")
def on_back(callback: types.CallbackQuery):
    bot.answer_callback_query(
        callback.id, callback.from_id, callback.peer_id, text="Returning to menu."
    )
    bot.send_message(callback.peer_id, "Use /menu for the main menu.")


@bot.message_handler()
def handle_fallback(message: types.Message):
    bot.send_message(message.from_id, "Use /menu or /inline.")


if __name__ == "__main__":
    bot.polling()
