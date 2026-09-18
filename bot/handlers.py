import logging

from telegram import Document, Update
from telegram.ext import ContextTypes

from bot import storage
from bot.config import UPLOADS_DIR
from bot.search import search_all

logger = logging.getLogger(__name__)

WELCOME = (
    "Привет! Я ищу вакансии на Jobindex.dk, Jobnet.dk и IT-jobbank.dk "
    "по вашим ключевым словам.\n\n"
    "Как начать:\n"
    "1. /keywords продавец, маркетинг, бухгалтер — ваши ключевые слова через запятую\n"
    "2. Пришлите файл вашего CV (PDF или Word) — просто отправьте документ в чат\n"
    "3. /location Aarhus — необязательно, чтобы отфильтровать по городу\n"
    "4. /search — запустить поиск\n\n"
    "Команды: /keywords /location /cv /search /help"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage.ensure_user(update.effective_user.id)
    await update.message.reply_text(WELCOME)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME)


async def _save_keywords(update: Update, telegram_id: int, text: str):
    keywords = [k.strip() for k in text.split(",") if k.strip()]
    storage.set_keywords(telegram_id, keywords)
    await update.message.reply_text(
        "Сохранил ключевые слова: " + ", ".join(keywords)
    )


async def set_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    text = " ".join(context.args) if context.args else ""
    if not text:
        current = storage.get_keywords(telegram_id)
        if current:
            await update.message.reply_text(
                "Текущие ключевые слова: " + ", ".join(current)
            )
        else:
            await update.message.reply_text(
                "Пришлите ключевые слова через запятую, например:\n"
                "/keywords продавец, маркетинг, бухгалтер"
            )
        return

    await _save_keywords(update, telegram_id, text)


async def handle_plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Free-text messages (no leading "/command") are treated as a
    # keywords update - this is how most people will naturally reply
    # after the bot asks them to send comma-separated keywords.
    telegram_id = update.effective_user.id
    text = (update.message.text or "").strip()
    if not text:
        return
    await _save_keywords(update, telegram_id, text)


async def set_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    text = " ".join(context.args) if context.args else ""
    storage.set_location(telegram_id, text)
    if text:
        await update.message.reply_text(f"Буду фильтровать по городу: {text}")
    else:
        await update.message.reply_text("Фильтр по городу снят — ищу по всей Дании.")


async def handle_cv_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    document: Document = update.message.document

    allowed_ext = (".pdf", ".doc", ".docx")
    filename = document.file_name or "cv"
    if not filename.lower().endswith(allowed_ext):
        await update.message.reply_text(
            "Пришлите CV в формате PDF или Word (.pdf, .doc, .docx)."
        )
        return

    user_dir = UPLOADS_DIR / str(telegram_id)
    user_dir.mkdir(exist_ok=True)
    dest_path = user_dir / filename

    tg_file = await document.get_file()
    await tg_file.download_to_drive(custom_path=str(dest_path))

    storage.set_cv_path(telegram_id, str(dest_path))
    await update.message.reply_text(f"CV сохранил: {filename}")


async def cv_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = storage.get_user(update.effective_user.id)
    if user and user.get("cv_path"):
        await update.message.reply_text(f"Загруженное CV: {user['cv_path'].split('/')[-1]}")
    else:
        await update.message.reply_text("CV ещё не загружено — пришлите файл документом.")


def format_vacancy(index: int, v) -> str:
    parts = [f"{index}. {v.title}"]
    meta = " | ".join(p for p in [v.company, v.location, v.source] if p)
    if meta:
        parts.append(meta)
    parts.append(v.url)
    return "\n".join(parts)


async def run_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    keywords = storage.get_keywords(telegram_id)
    if not keywords:
        await update.message.reply_text(
            "Сначала задайте ключевые слова: /keywords SQL, reporting"
        )
        return

    user = storage.get_user(telegram_id)
    location = (user or {}).get("location") or None

    await update.message.reply_text(
        f"Ищу по словам: {', '.join(keywords)}"
        + (f" в {location}" if location else " по всей Дании")
        + " ..."
    )

    vacancies = search_all(keywords, location)

    urls = [v.url for v in vacancies if v.url]
    unseen_urls = storage.filter_unseen(telegram_id, urls)
    new_vacancies = [v for v in vacancies if v.url in unseen_urls or not v.url]

    if not new_vacancies:
        await update.message.reply_text(
            "Новых вакансий не нашлось (или все уже присылал раньше)."
        )
        return

    MAX_RESULTS = 20
    to_send = new_vacancies[:MAX_RESULTS]

    for i in range(0, len(to_send), 5):
        chunk = to_send[i : i + 5]
        text = "\n\n".join(
            format_vacancy(i + j + 1, v) for j, v in enumerate(chunk)
        )
        await update.message.reply_text(text, disable_web_page_preview=True)

    storage.mark_seen(telegram_id, [v.url for v in to_send if v.url])

    if len(new_vacancies) > MAX_RESULTS:
        await update.message.reply_text(
            f"...и ещё {len(new_vacancies) - MAX_RESULTS}. "
            f"Уточните ключевые слова или город, чтобы сузить список."
        )
