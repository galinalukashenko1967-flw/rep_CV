"""Shared RSS search for Jobindex.dk and IT-jobbank.dk (same underlying platform)."""

import re

import feedparser
import requests

from bot.config import HTTP_USER_AGENT
from bot.sources import Vacancy

AREA_RE = re.compile(r'jix_robotjob--area">([^<]*)<')


def search(base_url: str, source_name: str, keyword: str, timeout: int = 20) -> list[Vacancy]:
    url = f"{base_url}/jobsoegning.rss"
    resp = requests.get(
        url,
        params={"q": keyword},
        headers={"User-Agent": HTTP_USER_AGENT},
        timeout=timeout,
    )
    resp.raise_for_status()

    feed = feedparser.parse(resp.content)
    vacancies = []
    for entry in feed.entries:
        raw_title = entry.get("title", "").strip()
        # Jobindex/IT-jobbank titles are usually "Job title, Company name"
        if "," in raw_title:
            title, company = raw_title.rsplit(",", 1)
            title, company = title.strip(), company.strip()
        else:
            title, company = raw_title, ""

        description = entry.get("description", "") or entry.get("summary", "")
        area_match = AREA_RE.search(description)
        location = area_match.group(1).strip() if area_match else ""

        vacancies.append(
            Vacancy(
                source=source_name,
                title=title,
                company=company,
                location=location,
                url=entry.get("link", ""),
                description=description,
            )
        )
    return vacancies


def search_jobindex(keyword: str) -> list[Vacancy]:
    return search("https://www.jobindex.dk", "Jobindex", keyword)


def search_itjobbank(keyword: str) -> list[Vacancy]:
    return search("https://www.it-jobbank.dk", "IT-jobbank", keyword)
