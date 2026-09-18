import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot import handlers, storage
from bot.config import TELEGRAM_BOT_TOKEN

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


def main():
    storage.init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("keywords", handlers.set_keywords))
    app.add_handler(CommandHandler("location", handlers.set_location))
    app.add_handler(CommandHandler("cv", handlers.cv_status))
    app.add_handler(CommandHandler("search", handlers.run_search))
    app.add_handler(MessageHandler(filters.Document.ALL, handlers.handle_cv_upload))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_plain_text)
    )

    logging.info("Bot starting (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
