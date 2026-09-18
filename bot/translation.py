"""Translate the generated ansøgning and the vacancy description into
Ukrainian, so the person can actually verify what they're about to send
is accurate before submitting the Danish original, and edit a plain-text
draft on their own computer if they want to.
"""

from bot.gemini_client import generate_with_retry, truncate

MAX_CHARS = 6000

PROMPT_TEMPLATE = """Переклади наступний текст українською мовою. Переклад має бути точним за змістом, без скорочень і без додавання нічого від себе -- це переклад для перевірки, а не переказ.

ТЕКСТ:
---
{text}
---

Дай у відповіді ЛИШЕ переклад, без пояснень до чи після.
"""


def translate_to_ukrainian(text: str) -> str:
    prompt = PROMPT_TEMPLATE.format(text=truncate(text, MAX_CHARS))
    response = generate_with_retry(prompt, json_mode=False)
    return response.text.strip()
