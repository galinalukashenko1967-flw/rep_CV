import asyncio
import logging

from telegram import Document, ReplyKeyboardMarkup, Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes

from bot import cv_parser, storage
from bot.config import UPLOADS_DIR
from bot.letter_generation import generate_cover_letter
from bot.matching import compute_match
from bot.search import search_all
from bot.semantic_matching import is_configured as semantic_matching_configured
from bot.semantic_matching import semantic_match_batch

logger = logging.getLogger(__name__)

# Last search results per user, so "/apply 3" can look up which vacancy
# that refers to without re-running the search. In-memory only: lost on
# restart, but a fresh /search is cheap, so that's an acceptable trade-off
# for not needing another DB table just for this.
LAST_RESULTS: dict[int, list] = {}


async def send_with_retry(update: Update, text: str, retries: int = 2, **kwargs):
    """update.message.reply_text, but survives a flaky connection to Telegram.

    A single dropped connection (seen in practice as httpx.ConnectTimeout /
    telegram.error.TimedOut) used to kill the whole /search silently, with
    the user never finding out anything failed. Retry a couple of times
    with a short backoff before giving up.
    """
    last_error = None
    for attempt in range(retries + 1):
        try:
            return await update.message.reply_text(text, **kwargs)
        except (TimedOut, NetworkError) as exc:
            last_error = exc
            logger.warning("send_with_retry: attempt %s failed: %s", attempt + 1, exc)
            if attempt < retries:
                await asyncio.sleep(2 * (attempt + 1))
    raise last_error

BTN_SEARCH = "🔍 Искать вакансии"
BTN_KEYWORDS = "🔑 Ключевые слова"
BTN_LOCATION = "📍 Город"
BTN_CV = "📄 Моё CV"
BTN_CANCEL = "❌ Отмена"
BTN_ALL_DENMARK = "🌍 Вся Дания"
BTN_RESET_SEEN = "🔄 Показать вакансии заново"

# Required before the Search button appears at all.
REQUIRED_FOR_SEARCH = (BTN_KEYWORDS, BTN_CV)


def _is_ready_for_search(telegram_id: int) -> bool:
    user = storage.get_user(telegram_id) or {}
    has_keywords = bool(storage.get_keywords(telegram_id))
    has_cv = bool(user.get("cv_path"))
    return has_keywords and has_cv


def build_keyboard(telegram_id: int) -> ReplyKeyboardMarkup:
    rows = [[BTN_KEYWORDS, BTN_LOCATION], [BTN_CV], [BTN_RESET_SEEN]]
    if _is_ready_for_search(telegram_id):
        rows.insert(0, [BTN_SEARCH])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


# Shown instead of the main menu while the bot is waiting for a specific
# free-text reply (keywords / city), so there's always an obvious way out
# if the person changes their mind instead of typing anything.
CANCEL_KEYBOARD = ReplyKeyboardMarkup([[BTN_CANCEL]], resize_keyboard=True)

# Shown specifically while waiting for a city: Cancel alone only means
# "leave the current filter as it was" (confusing when the person actually
# wants to switch TO nationwide search), so offer that as its own button.
LOCATION_KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_ALL_DENMARK], [BTN_CANCEL]], resize_keyboard=True
)


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
            f"Пришлите новое название города, нажмите «{BTN_ALL_DENMARK}» "
            "(снять фильтр совсем), или «Отмена», чтобы оставить как есть."
        )
    else:
        message = (
            "Пришлите название города, например: Aarhus\n\n"
            f"Уже и так ищу по всей Дании — «{BTN_ALL_DENMARK}» и «Отмена» "
            "здесь делают то же самое."
        )
    await update.message.reply_text(message, reply_markup=LOCATION_KEYBOARD)
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
    if text == BTN_ALL_DENMARK:
        context.user_data.pop("awaiting", None)
        await _save_location(update, telegram_id, "")
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
    if text == BTN_RESET_SEEN:
        await reset_seen(update, context)
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

    try:
        cv_text = cv_parser.extract_text(str(dest_path))
        storage.set_cv_text(telegram_id, cv_text)
    except Exception as exc:
        logger.warning("Could not extract CV text for %s: %s", telegram_id, exc)
        storage.set_cv_text(telegram_id, None)
        await _reply_with_next_step(
            update,
            telegram_id,
            f"CV сохранил: {filename}\n\n"
            "Не удалось прочитать текст из файла (для смыслового "
            "сравнения с вакансиями) — попробуйте пересохранить его как "
            "обычный PDF или .docx.",
        )
        return

    await _reply_with_next_step(update, telegram_id, f"CV сохранил: {filename}")


async def cv_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    user = storage.get_user(telegram_id)
    if user and user.get("cv_path"):
        message = f"Загруженное CV: {user['cv_path'].split('/')[-1]}"
    else:
        message = "CV ещё не загружено — пришлите файл документом (PDF или Word)."
    await _reply_with_next_step(update, telegram_id, message)


async def reset_seen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    count = storage.clear_seen(telegram_id)
    await update.message.reply_text(
        f"Готово, забыл {count} уже показанных вакансий — "
        "следующий поиск покажет их снова.",
        reply_markup=build_keyboard(telegram_id),
    )


def format_vacancy(index: int, v, percent: int, detail: str) -> str:
    parts = [f"{index}. {v.title}"]
    meta = " | ".join(p for p in [v.company, v.location, v.source] if p)
    if meta:
        parts.append(meta)
    parts.append(f"Совпадение: {percent}%" + (f" — {detail}" if detail else ""))
    parts.append(v.url)
    return "\n".join(parts)


# How many vacancies get sent to Gemini for real scoring per search. Bounds
# cost/latency/free-tier rate limits; the final list shown to the user is
# capped further (MAX_RESULTS below) once these are sorted.
SEMANTIC_BATCH_CAP = 30


def _score_vacancies(telegram_id: int, vacancies: list, keywords: list[str]):
    """Returns [(vacancy, percent, detail_string), ...].

    Prefers real semantic scoring via Gemini (bot/semantic_matching.py) when
    it's configured and the user has a parsed CV; falls back to plain
    keyword-overlap matching (bot/matching.py) otherwise.
    """
    cv_text = storage.get_cv_text(telegram_id) if semantic_matching_configured() else None

    if cv_text:
        candidates = vacancies[:SEMANTIC_BATCH_CAP]
        try:
            results = semantic_match_batch(cv_text, candidates)
            return [
                (v, r.percent, r.reasoning) for v, r in zip(candidates, results)
            ]
        except Exception:
            logger.exception(
                "Semantic matching failed for %s, falling back to keyword match",
                telegram_id,
            )

    scored = [(v, compute_match(v, keywords)) for v in vacancies]
    return [
        (v, m.percent, ("по словам: " + ", ".join(m.matched_keywords) if m.matched_keywords else ""))
        for v, m in scored
    ]


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

    await send_with_retry(
        update,
        f"Ищу по словам: {', '.join(keywords)}"
        + (f" в {location}" if location else " по всей Дании")
        + " ...",
    )

    vacancies = search_all(keywords, location)

    urls = [v.url for v in vacancies if v.url]
    unseen_urls = storage.filter_unseen(telegram_id, urls)
    new_vacancies = [v for v in vacancies if v.url in unseen_urls or not v.url]

    if not new_vacancies:
        await send_with_retry(
            update,
            "Новых вакансий не нашлось (или все уже присылал раньше). "
            f"Если хотите увидеть их снова — нажмите «{BTN_RESET_SEEN}».",
            reply_markup=build_keyboard(telegram_id),
        )
        return

    scored = _score_vacancies(telegram_id, new_vacancies, keywords)
    scored.sort(key=lambda triple: triple[1], reverse=True)

    MAX_RESULTS = 20
    to_send = scored[:MAX_RESULTS]
    LAST_RESULTS[telegram_id] = [v for v, percent, detail in to_send]

    sent_urls = []
    for i in range(0, len(to_send), 5):
        chunk = to_send[i : i + 5]
        text = "\n\n".join(
            format_vacancy(i + j + 1, v, percent, detail)
            for j, (v, percent, detail) in enumerate(chunk)
        )
        # If this raises after retries, mark_seen below still records
        # whatever went out in earlier chunks, so a retried /search
        # doesn't re-send vacancies the person already saw.
        await send_with_retry(update, text, disable_web_page_preview=True)
        sent_urls.extend(v.url for v, percent, detail in chunk if v.url)

    storage.mark_seen(telegram_id, sent_urls)

    footer = (
        f"...и ещё {len(new_vacancies) - MAX_RESULTS}. "
        f"Уточните ключевые слова или город, чтобы сузить список."
        if len(new_vacancies) > MAX_RESULTS
        else "Это все новые вакансии на сейчас."
    )
    footer += "\n\nЧтобы получить ansøgning под конкретную вакансию — напишите: /apply <номер>"
    await send_with_retry(update, footer, reply_markup=build_keyboard(telegram_id))


async def apply_to_vacancy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Укажите номер вакансии из последнего списка, например: /apply 3"
        )
        return

    index = int(context.args[0])
    results = LAST_RESULTS.get(telegram_id) or []
    if not results:
        await update.message.reply_text(
            "Сначала запустите поиск — нажмите 🔍 Искать вакансии."
        )
        return
    if not (1 <= index <= len(results)):
        await update.message.reply_text(
            f"Нет вакансии №{index} — в последнем списке их {len(results)}."
        )
        return

    cv_text = storage.get_cv_text(telegram_id)
    if not cv_text:
        await update.message.reply_text(
            "Не нашёл текст вашего CV — пришлите файл ещё раз через 📄 Моё CV."
        )
        return

    if not semantic_matching_configured():
        await update.message.reply_text(
            "Генерация писем сейчас недоступна (не настроен доступ к модели)."
        )
        return

    vacancy = results[index - 1]
    await send_with_retry(update, f"Пишу ansøgning для «{vacancy.title}»...")

    try:
        letter = generate_cover_letter(cv_text, vacancy)
    except Exception:
        logger.exception("Letter generation failed for %s / %s", telegram_id, vacancy.url)
        await update.message.reply_text(
            "Не получилось сгенерировать письмо (сбой на стороне модели). Попробуйте ещё раз."
        )
        return

    await send_with_retry(
        update,
        f"{vacancy.title} — {vacancy.company}\n{vacancy.url}\n\n{letter}",
        reply_markup=build_keyboard(telegram_id),
    )
