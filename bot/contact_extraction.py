"""Pull out the bits a Danish jobcenter/kommune log usually asks for
(contact person, phone, email) from a vacancy's free-text description.

This information is almost never in a structured field -- it's buried in
a sentence like "Har du spørgsmål, kontakt Thorvald Kodal på ... eller
+45 42 52 79 99" -- so a regex is fragile for the name in particular.
Gemini extraction is more robust; falls back to "ikke angivet" per field
when nothing is found (never invents a name/number). Danish, not Russian,
since this ends up printed in the vacancy PDF alongside Danish labels.
"""

import json
import logging

from bot.gemini_client import generate_with_retry, truncate
from bot.sources import Vacancy

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_CHARS = 4000

NOT_FOUND = "ikke angivet"

PROMPT_TEMPLATE = """Найди в тексте вакансии контактное лицо для вопросов по этой позиции: имя, телефон, email.

ТЕКСТ ВАКАНСИИ:
---
{description}
---

Правила:
- Если что-то не упомянуто в тексте — верни для этого поля ровно строку "{not_found}", не придумывай
- Телефон и email копируй буквально как в тексте, ничего не меняя
- Если указано несколько контактов, выбери первого/основного
- Само имя/телефон/email копируй как есть (обычно они и так на датском/латинице), но не переводи их

Ответь СТРОГО в виде JSON:
{{"contact_name": "<имя или {not_found}>", "contact_phone": "<телефон или {not_found}>", "contact_email": "<email или {not_found}>"}}
"""


class ContactInfo:
    def __init__(self, name: str, phone: str, email: str):
        self.name = name
        self.phone = phone
        self.email = email


def extract_contact_info(vacancy: Vacancy) -> ContactInfo:
    prompt = PROMPT_TEMPLATE.format(
        description=truncate(vacancy.description, MAX_DESCRIPTION_CHARS),
        not_found=NOT_FOUND,
    )
    try:
        response = generate_with_retry(prompt, json_mode=True)
        data = json.loads(response.text)
        return ContactInfo(
            name=str(data.get("contact_name") or NOT_FOUND),
            phone=str(data.get("contact_phone") or NOT_FOUND),
            email=str(data.get("contact_email") or NOT_FOUND),
        )
    except Exception:
        logger.exception("Contact extraction failed for %s", vacancy.url)
        return ContactInfo(name=NOT_FOUND, phone=NOT_FOUND, email=NOT_FOUND)
