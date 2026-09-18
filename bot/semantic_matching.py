"""Real CV-vs-vacancy matching via Gemini, as opposed to the plain
keyword-overlap fallback in bot/matching.py.

Scores the whole batch of vacancies from one search in a single API call
(rather than one call per vacancy) so this stays fast and friendly to the
free-tier rate limits.
"""

import json
import logging
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from bot.config import GEMINI_API_KEY
from bot.sources import Vacancy

logger = logging.getLogger(__name__)

MODEL = "gemini-3.5-flash-lite"

# Keep prompts a reasonable size: a long vacancy description or CV can
# otherwise blow up token usage across a whole batch for little benefit.
MAX_DESCRIPTION_CHARS = 1500
MAX_CV_CHARS = 6000

_client = None


def is_configured() -> bool:
    return bool(GEMINI_API_KEY)


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


class SemanticMatch:
    def __init__(self, percent: int, reasoning: str):
        self.percent = percent
        self.reasoning = reasoning


PROMPT_TEMPLATE = """Ты помогаешь соискателю в Дании оценить, насколько вакансии подходят под его резюме — не по формальному совпадению слов, а по сути: реальные задачи, уровень позиции, требуемый опыт, язык объявления против уровня языка соискателя.

РЕЗЮМЕ СОИСКАТЕЛЯ:
---
{cv_text}
---

ВАКАНСИИ (оцени каждую независимо):
{vacancies_block}

Для каждой вакансии дай:
- percent: целое число 0-100, насколько реально этот человек подходит на эту позицию с этим CV (учитывай суть работы, а не только ключевые слова; если позиция требует другой специализации несмотря на схожие слова — ставь низкий процент)
- reasoning: одно короткое предложение на русском, объясняющее оценку (что совпадает или чего не хватает)

Ответь СТРОГО в виде JSON-массива объектов, по одному на каждую вакансию, в том же порядке:
[{{"percent": <int>, "reasoning": "<строка>"}}, ...]
"""


def _generate_with_retry(client, prompt: str, retries: int = 3):
    """Gemini's free tier returns transient 503s ("high demand") fairly
    often -- retry with backoff before giving up, rather than surfacing
    that as a hard failure for what's usually a one-shot glitch."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            return client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
        except genai_errors.ServerError as exc:
            last_error = exc
            logger.warning("Gemini call attempt %s failed: %s", attempt + 1, exc)
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
    raise last_error


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "..."


def semantic_match_batch(
    cv_text: str, vacancies: list[Vacancy]
) -> list[SemanticMatch]:
    if not vacancies:
        return []

    vacancies_block = "\n\n".join(
        f"[{i}] {v.title}\nКомпания: {v.company}\nМесто: {v.location}\n"
        f"Описание: {_truncate(v.description, MAX_DESCRIPTION_CHARS)}"
        for i, v in enumerate(vacancies)
    )

    prompt = PROMPT_TEMPLATE.format(
        cv_text=_truncate(cv_text, MAX_CV_CHARS),
        vacancies_block=vacancies_block,
    )

    client = _get_client()
    response = _generate_with_retry(client, prompt)

    data = json.loads(response.text)
    results = []
    for i in range(len(vacancies)):
        if i < len(data):
            item = data[i]
            results.append(
                SemanticMatch(
                    percent=int(item.get("percent", 0)),
                    reasoning=str(item.get("reasoning", "")),
                )
            )
        else:
            results.append(SemanticMatch(percent=0, reasoning=""))
    return results
