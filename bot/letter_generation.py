"""Generate a cover letter (ansøgning) for one specific vacancy via Gemini,
grounded in the person's real CV -- same approach used manually earlier in
this project: highlight genuine overlap, name real gaps honestly instead of
inventing experience that isn't in the CV.
"""

from bot.gemini_client import MAX_CV_CHARS, generate_with_retry, truncate
from bot.sources import Vacancy

MAX_DESCRIPTION_CHARS = 4000

PROMPT_TEMPLATE = """Ты помогаешь соискателю в Дании написать ansøgning (сопроводительное письмо) под конкретную вакансию, на основе его настоящего резюме.

РЕЗЮМЕ СОИСКАТЕЛЯ:
---
{cv_text}
---

ВАКАНСИЯ:
Название: {title}
Компания: {company}
Место: {location}
Описание: {description}

Напиши ansøgning на {language}. Требования:
- Опирайся ТОЛЬКО на реальные факты из резюме — не выдумывай навыки, инструменты или опыт, которых там нет
- Если в вакансии требуется что-то, чего нет в резюме — честно, но кратко упомяни это как готовность быстро научиться, а не скрывай
- Подчеркни то, что реально совпадает: конкретный опыт, инструменты, отрасль
- Обычная деловая структура письма: обращение, 3-4 абзаца по сути, прощание
- Не используй общие фразы без содержания ("я командный игрок" и т.п.) — только конкретика из резюме
- Ответь только текстом письма, без пояснений до или после
"""


def _pick_language(vacancy: Vacancy) -> str:
    # Crude heuristic: Danish job ads use these words constantly; English
    # ones (like Collectia's) explicitly say so. Good enough for a first
    # draft -- the person reviews and edits before sending anyway.
    danish_markers = ("stilling", "erfaring", "du har", "vi søger", "ansøgning")
    text = f"{vacancy.title} {vacancy.description}".lower()
    if any(m in text for m in danish_markers):
        return "датском (Dansk)"
    return "английском (English)"


def generate_cover_letter(cv_text: str, vacancy: Vacancy) -> str:
    prompt = PROMPT_TEMPLATE.format(
        cv_text=truncate(cv_text, MAX_CV_CHARS),
        title=vacancy.title,
        company=vacancy.company,
        location=vacancy.location,
        description=truncate(vacancy.description, MAX_DESCRIPTION_CHARS),
        language=_pick_language(vacancy),
    )

    response = generate_with_retry(prompt, json_mode=False)
    return response.text.strip()
