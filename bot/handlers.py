import logging

from telegram import Document, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot import storage
from bot.config import UPLOADS_DIR
from bot.search import search_all

logger = logging.getLogger(__name__)

BTN_SEARCH = "🔍 Искать вакансии"
BTN_KEYWORDS = "🔑 Ключевые слова"
BTN_LOCATION = "📍 Город"
BTN_CV = "📄 Моё CV"
BTN_CANCEL = "❌ Отмена"

# Required before the Search button appears at all.
REQUIRED_FOR_SEARCH = (BTN_KEYWORDS, BTN_CV)


def _is_ready_for_search(telegram_id: int) -> bool:
    user = storage.get_user(telegram_id) or {}
    has_keywords = bool(storage.get_keywords(telegram_id))
    has_cv = bool(user.get("cv_path"))
    return has_keywords and has_cv


def build_keyboard(telegram_id: int) -> ReplyKeyboardMarkup:
    rows = [[BTN_KEYWORDS, BTN_LOCATION], [BTN_CV]]
    if _is_ready_for_search(telegram_id):
        rows.insert(0, [BTN_SEARCH])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


# Shown instead of the main menu while the bot is waiting for a specific
# free-text reply (keywords / city), so there's always an obvious way out
# if the person changes their mind instead of typing anything.
CANCEL_KEYBOARD = ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)


def _missing_requirements(telegram_id: int) -> list[str]:
    missing = []
    if not storage.get_keywords(telegram_id):
        missing.append(BTN_KEYWORDS)
    user = storage.get_user(telegram_id) or {}
    if not user.get("cv_path"):
        missing.append(BTN_CV)
    return missing


WELCOME = (
    "Привет! Я ищу вакансии на Jobindex.dk, Jobnet.dk и IT-jobbank.dk "
    "по вашим ключевым словам.\n\n"
    "Пользуйтесь кнопками внизу экрана:\n"
    f"{BTN_KEYWORDS} — задать свои ключевые слова через запятую\n"
    f"{BTN_LOCATION} — необязательно, отфильтровать по городу\n"
    f"{BTN_CV} — загрузить/проверить своё CV (PDF или Word — просто отправьте файл)\n\n"
    f"Кнопка {BTN_SEARCH} появится, когда заполните ключевые слова и CV."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    storage.ensure_user(telegram_id)
    context.user_data.pop("awaiting", None)
    await update.message.reply_text(WELCOME, reply_markup=build_keyboard(telegram_id))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        WELCOME, reply_markup=build_keyboard(update.effective_user.id)
    )


async def _reply_with_next_step(update: Update, telegram_id: int, done_message: str):
    missing = _missing_requirements(telegram_id)
    if missing:
        done_message += "\n\nОсталось заполнить: " + ", ".join(missing)
    await update.message.reply_text(
        done_message, reply_markup=build_keyboard(telegram_id)
    )


async def _save_keywords(update: Update, telegram_id: int, text: str):
    keywords = [k.strip() for k in text.split(",") if k.strip()]
    storage.set_keywords(telegram_id, keywords)
    await _reply_with_next_step(
        update, telegram_id, "Сохранил ключевые слова: " + ", ".join(keywords)
    )


async def _prompt_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    current = storage.get_keywords(telegram_id)
    if current:
        message = (
            "Текущие ключевые слова: "
            + ", ".join(current)
            + "\n\nЧтобы изменить — пришлите новые через запятую, или нажмите Отмена."
        )
    else:
        message = (
            "Пришлите ключевые слова через запятую, например:\n"
            "продавец, маркетинг, бухгалтер\n\n"
            "Или нажмите Отмена, если передумали."
        )
    await update.message.reply_text(message, reply_markup=CANCEL_KEYBOARD)
    context.user_data["awaiting"] = "keywords"


async def set_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    text = " ".join(context.args) if context.args else ""
    if not text:
        await _prompt_keywords(update, context)
        return
    await _save_keywords(update, telegram_id, text)


async def _save_location(update: Update, telegram_id: int, text: str):
    storage.set_location(telegram_id, text)
    message = (
        f"Буду фильтровать по городу: {text}"
        if text
        else "Фильтр по городу снят — ищу по всей Дании."
    )
    await _reply_with_next_step(update, telegram_id, message)


async def _prompt_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user = storage.get_user(telegram_id)
    current = (user or {}).get("location") or ""
    if current:
        message = (
            f"Сейчас фильтр по городу: {current}\n\n"
            "Пришлите новое название города, слово 'нет' (искать по всей Дании), "
            "или нажмите Отмена, чтобы оставить как есть."
        )
    else:
        message = (
            "Пришлите название города, например: Aarhus\n\n"
            "Или нажмите Отмена, если не хотите ограничивать город "
            "(тогда буду искать по всей Дании)."
        )
    await update.message.reply_text(message, reply_markup=CANCEL_KEYBOARD)
    context.user_data["awaiting"] = "location"


async def set_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    text = " ".join(context.args) if context.args else ""
    if not text:
        await _prompt_location(update, context)
        return
    await _save_location(update, telegram_id, text)


async def handle_plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    text = (update.message.text or "").strip()
    if not text:
        return

    if text == BTN_CANCEL:
        context.user_data.pop("awaiting", None)
        await update.message.reply_text(
            "Хорошо, отменил.", reply_markup=build_keyboard(telegram_id)
        )
        return
    if text == BTN_SEARCH:
        await run_search(update, context)
        return
    if text == BTN_KEYWORDS:
        await _prompt_keywords(update, context)
        return
    if text == BTN_LOCATION:
        await _prompt_location(update, context)
        return
    if text == BTN_CV:
        await cv_status(update, context)
        return

    awaiting = context.user_data.pop("awaiting", None)
    if awaiting == "location":
        if text.lower() in ("нет", "no", "-"):
            text = ""
        await _save_location(update, telegram_id, text)
        return

    # Default: any other free-text message (including the first message
    # after tapping "Ключевые слова") is treated as a keywords update.
    await _save_keywords(update, telegram_id, text)


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
    await _reply_with_next_step(update, telegram_id, f"CV сохранил: {filename}")


async def cv_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user = storage.get_user(telegram_id)
    if user and user.get("cv_path"):
        message = f"Загруженное CV: {user['cv_path'].split('/')[-1]}"
    else:
        message = "CV ещё не загружено — пришлите файл документом (PDF или Word)."
    await _reply_with_next_step(update, telegram_id, message)


def format_vacancy(index: int, v) -> str:
    parts = [f"{index}. {v.title}"]
    meta = " | ".join(p for p in [v.company, v.location, v.source] if p)
    if meta:
        parts.append(meta)
    parts.append(v.url)
    return "\n".join(parts)


async def run_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    missing = _missing_requirements(telegram_id)
    if missing:
        await update.message.reply_text(
            "Сначала заполните: " + ", ".join(missing),
            reply_markup=build_keyboard(telegram_id),
        )
        return

    keywords = storage.get_keywords(telegram_id)
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
            "Новых вакансий не нашлось (или все уже присылал раньше).",
            reply_markup=build_keyboard(telegram_id),
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

    footer = (
        f"...и ещё {len(new_vacancies) - MAX_RESULTS}. "
        f"Уточните ключевые слова или город, чтобы сузить список."
        if len(new_vacancies) > MAX_RESULTS
        else "Это все новые вакансии на сейчас."
    )
    await update.message.reply_text(footer, reply_markup=build_keyboard(telegram_id))
