from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = "8029685993:"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message

    print("=" * 50)
    print(f"Chat ID    : {chat.id}")
    print(f"Chat Type  : {chat.type}")
    print(f"Chat Title : {chat.title}")
    print(f"Username   : {user.username if user else None}")
    print(f"Text       : {message.text if message else None}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.ALL, handle_message))

    print("Listening for Telegram messages...")
    app.run_polling()


if __name__ == "__main__":
    main()
