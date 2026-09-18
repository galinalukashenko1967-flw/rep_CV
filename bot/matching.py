"""Cheap, deterministic keyword-overlap matching -- no LLM involved.

This is a stand-in for real CV-aware matching (which needs an Anthropic
API key to reason about seniority, domain fit, language requirements,
etc. -- see README). Until that's wired up, this gives an honest, if
naive, signal: which of the person's own search keywords actually show
up in the vacancy's title/description, as a percentage.
"""

from dataclasses import dataclass

from bot.sources import Vacancy


@dataclass
class MatchResult:
    percent: int
    matched_keywords: list[str]


def compute_match(vacancy: Vacancy, keywords: list[str]) -> MatchResult:
    if not keywords:
        return MatchResult(percent=0, matched_keywords=[])

    haystack = f"{vacancy.title} {vacancy.description}".lower()
    matched = [k for k in keywords if k.strip() and k.strip().lower() in haystack]
    percent = round(100 * len(matched) / len(keywords))
    return MatchResult(percent=percent, matched_keywords=matched)
