"""Cheap, deterministic keyword-overlap matching -- no LLM involved.

This is a stand-in for real CV-aware matching (which needs an Anthropic
API key to reason about seniority, domain fit, language requirements,
etc. -- see README). Until that's wired up, this gives an honest, if
naive, signal: which of the person's own search keywords actually show
up in the vacancy's title/description (in English or Danish), as a
percentage.
"""

from dataclasses import dataclass

from bot.sources import Vacancy

# Danish job ads often use different words than an English search keyword.
# This is a small, hand-picked list for common job-search terms -- not a
# real translator. It only helps recall for terms already in this dict;
# anything else still needs an exact text match (or, eventually, the LLM
# matching this file's docstring keeps pointing at).
SYNONYMS: dict[str, list[str]] = {
    "reporting": ["rapportering", "rapport"],
    "rapportering": ["reporting", "rapport"],
    "database": ["database", "databaser"],
    "testing": ["test", "afprøvning", "tester"],
    "data quality": ["datakvalitet"],
    "datakvalitet": ["data quality"],
    "sales": ["salg", "sælger"],
    "salg": ["sales", "sælger"],
    "marketing": ["marketing", "markedsføring"],
    "accountant": ["bogholder", "revisor"],
    "bogholder": ["accountant", "regnskab"],
    "customer service": ["kundeservice"],
    "kundeservice": ["customer service"],
    "developer": ["udvikler"],
    "udvikler": ["developer"],
    "analyst": ["analytiker"],
    "analytiker": ["analyst"],
}


@dataclass
class MatchResult:
    percent: int
    matched_keywords: list[str]


def _keyword_variants(keyword: str) -> list[str]:
    key = keyword.strip().lower()
    return [key] + SYNONYMS.get(key, [])


def compute_match(vacancy: Vacancy, keywords: list[str]) -> MatchResult:
    if not keywords:
        return MatchResult(percent=0, matched_keywords=[])

    haystack = f"{vacancy.title} {vacancy.description}".lower()
    matched = [
        k for k in keywords
        if k.strip() and any(variant in haystack for variant in _keyword_variants(k))
    ]
    percent = round(100 * len(matched) / len(keywords))
    return MatchResult(percent=percent, matched_keywords=matched)
