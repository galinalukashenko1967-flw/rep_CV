"""Real CV-vs-vacancy matching via Gemini, as opposed to the plain
keyword-overlap fallback in bot/matching.py.

Scores the whole batch of vacancies from one search in a single API call
(rather than one call per vacancy) so this stays fast and friendly to the
free-tier rate limits.
"""

import json

from bot.gemini_client import MAX_CV_CHARS, generate_with_retry, is_configured, truncate
from bot.sources import Vacancy

__all__ = ["is_configured", "semantic_match_batch", "SemanticMatch"]

# Keep prompts a reasonable size: a long vacancy description can otherwise
# blow up token usage across a whole batch for little benefit.
MAX_DESCRIPTION_CHARS = 1500


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
- reasoning: одно короткое предложение НА УКРАИНСКОМ ЯЗЫКЕ (мова — українська), объясняющее оценку (что совпадает или чего не хватает)

ВАЖНО: не приписывай кандидату навыки или опыт, которых нет в резюме буквально. Общий опыт с технологией ≠ опыт в конкретной специализации/роли.

Пример неправильной оценки (так делать НЕЛЬЗЯ): в резюме написано "работал с SQL-базами данных, датаобработкой и отчётностью" — БЕЗ слова "администратор" и без задач вроде backup/recovery, patching, RMAN, Data Guard, RAC. Вакансия "Oracle Database Administrator" требует именно этих задач администрирования. Ставить здесь 80-85% и писать в reasoning "сильный опыт с администрированием" — ОШИБКА: кандидат никогда не администрировал базы данных, только работал с данными в них. Правильная оценка такой пары — 30-45%, и в reasoning нужно прямо написать, что это разные роли (администратор БД ≠ специалист по данным/отчётности), даже если оба "работают с Oracle/SQL".

Перед тем как поставить высокий процент (70+) для вакансии с словом "Administrator" или задачами администрирования в названии/описании — спроси себя: есть ли в резюме БУКВАЛЬНОЕ упоминание работы администратором БД или конкретных admin-задач? Если нет — процент должен быть заметно ниже.

Ответь СТРОГО в виде JSON-массива объектов, по одному на каждую вакансию, в том же порядке:
[{{"percent": <int>, "reasoning": "<строка>"}}, ...]
"""


def semantic_match_batch(
    cv_text: str, vacancies: list[Vacancy]
) -> list[SemanticMatch]:
    if not vacancies:
        return []

    vacancies_block = "\n\n".join(
        f"[{i}] {v.title}\nКомпания: {v.company}\nМесто: {v.location}\n"
        f"Описание: {truncate(v.description, MAX_DESCRIPTION_CHARS)}"
        for i, v in enumerate(vacancies)
    )

    prompt = PROMPT_TEMPLATE.format(
        cv_text=truncate(cv_text, MAX_CV_CHARS),
        vacancies_block=vacancies_block,
    )

    response = generate_with_retry(prompt, json_mode=True)

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
