"""Explain an official letter (from kommune, SKAT, a bank etc.) in plain
Ukrainian -- not a literal translation, but "what does this actually mean
and what do I need to do", grounded only in what the letter itself says.
Explicitly not legal/official advice.
"""

from google.genai import types

from bot.gemini_client import generate_with_retry

DISCLAIMER_INSTRUCTION = (
    'В кінці ОБОВ\'ЯЗКОВО додай окремим рядком: '
    '"Це пояснення від ШІ для орієнтування, не офіційна юридична консультація. '
    'Для важливих рішень звертайтеся до kommune/фахівця."'
)

COMMON_RULES = f"""Не роби буквальний переклад рядок-в-рядок -- поясни простими словами УКРАЇНСЬКОЮ мовою:
1. Від кого цей лист і про що він
2. Що конкретно потрібно зробити (якщо потрібно) -- які дії, до якого терміну
3. Що буде, якщо нічого не робити (якщо це вказано або випливає з листа)
4. Важливі дати/суми/номери справ, згадані в листі

Правила:
- Спирайся ТІЛЬКИ на те, що реально написано в листі -- не вигадуй і не додумуй
- Якщо щось незрозуміло або неоднозначно -- так і скажи, не вгадуй
- {DISCLAIMER_INSTRUCTION}
- Пиши простими словами, без канцеляриту
"""

PROMPT_TEXT = f"""Ти допомагаєш українцю в Данії зрозуміти офіційний лист (від kommune, SKAT, банку тощо), який він отримав.

{COMMON_RULES}

ТЕКСТ ЛИСТА:
---
{{text}}
---
"""

PROMPT_IMAGE = f"""Ти допомагаєш українцю в Данії зрозуміти офіційний лист (від kommune, SKAT, банку тощо), який він сфотографував. Спочатку прочитай текст на фото, потім поясни його.

{COMMON_RULES}

Якщо текст на фото нерозбірливий або обрізаний -- прямо скажи це замість здогадок.
"""

MAX_TEXT_CHARS = 8000


def explain_letter_text(text: str) -> str:
    prompt = PROMPT_TEXT.format(text=text[:MAX_TEXT_CHARS])
    response = generate_with_retry(prompt, json_mode=False)
    return response.text.strip()


def explain_letter_image(image_bytes: bytes, mime_type: str) -> str:
    response = generate_with_retry(
        contents=[PROMPT_IMAGE, types.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
        json_mode=False,
    )
    return response.text.strip()
