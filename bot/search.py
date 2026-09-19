import logging

from bot.sources import Vacancy, dedupe
from bot.sources.jobindex_rss import search_itjobbank, search_jobindex
from bot.sources.jobnet import search as search_jobnet

logger = logging.getLogger(__name__)

SOURCE_FUNCS = [search_jobindex, search_jobnet, search_itjobbank]


def search_keyword(keyword: str) -> list[Vacancy]:
    results: list[Vacancy] = []
    needle = keyword.strip().lower()
    for func in SOURCE_FUNCS:
        try:
            found = func(keyword)
        except Exception:
            # A source going down (blocked, changed API, network hiccup)
            # should not take the whole search down with it.
            logger.exception("Source %s failed for keyword %r", func.__module__, keyword)
            continue
        # Some sources' own search (Jobindex's RSS in particular) is fuzzy
        # enough to return vacancies that don't contain the keyword at all
        # (e.g. searching "maler" returned a bookkeeper posting) -- drop
        # anything that doesn't actually mention it, rather than trusting
        # the source's relevance judgment.
        if needle:
            found = [
                v for v in found
                if needle in f"{v.title} {v.description}".lower()
            ]
        results.extend(found)
    return results


def search_all(keywords: list[str], location: str | None = None) -> list[Vacancy]:
    all_results: list[Vacancy] = []
    for keyword in keywords:
        all_results.extend(search_keyword(keyword))

    vacancies = dedupe(all_results)

    if location:
        needle = location.strip().lower()
        vacancies = [v for v in vacancies if needle in v.location.lower()]

    return vacancies
