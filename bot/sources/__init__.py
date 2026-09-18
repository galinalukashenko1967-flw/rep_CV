from dataclasses import dataclass


@dataclass
class Vacancy:
    source: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""

    def dedup_key(self) -> str:
        return f"{self.title.strip().lower()}|{self.company.strip().lower()}"


def dedupe(vacancies: list[Vacancy]) -> list[Vacancy]:
    seen = set()
    result = []
    for v in vacancies:
        key = v.dedup_key()
        if key in seen:
            continue
        seen.add(key)
        result.append(v)
    return result
