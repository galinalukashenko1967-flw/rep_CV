"""Official list of Denmark's 99 municipalities (kommuner), from the
Danish government's own address API (api.dataforsyningen.dk/kommuner),
used to catch typos/old spellings when someone types a city and to
normalize it to the correct official name.

Danish spellings and colloquial Danish abbreviations only (e.g. "Kbh")
-- no English or Russian/Ukrainian names/transliterations.
"""

import difflib

MUNICIPALITIES = [
    "Aabenraa", "Aalborg", "Aarhus", "Albertslund", "Allerød", "Assens",
    "Ballerup", "Billund", "Bornholm", "Brøndby", "Brønderslev",
    "Christiansø", "Dragør", "Egedal", "Esbjerg", "Faaborg-Midtfyn",
    "Fanø", "Favrskov", "Faxe", "Fredensborg", "Fredericia",
    "Frederiksberg", "Frederikshavn", "Frederikssund", "Furesø",
    "Gentofte", "Gladsaxe", "Glostrup", "Greve", "Gribskov",
    "Guldborgsund", "Haderslev", "Halsnæs", "Hedensted", "Helsingør",
    "Herlev", "Herning", "Hillerød", "Hjørring", "Holbæk", "Holstebro",
    "Horsens", "Hvidovre", "Høje-Taastrup", "Hørsholm", "Ikast-Brande",
    "Ishøj", "Jammerbugt", "Kalundborg", "Kerteminde", "Kolding",
    "København", "Køge", "Langeland", "Lejre", "Lemvig", "Lolland",
    "Lyngby-Taarbæk", "Læsø", "Mariagerfjord", "Middelfart", "Morsø",
    "Norddjurs", "Nordfyns", "Nyborg", "Næstved", "Odder", "Odense",
    "Odsherred", "Randers", "Rebild", "Ringkøbing-Skjern", "Ringsted",
    "Roskilde", "Rudersdal", "Rødovre", "Samsø", "Silkeborg",
    "Skanderborg", "Skive", "Slagelse", "Solrød", "Sorø", "Stevns",
    "Struer", "Svendborg", "Syddjurs", "Sønderborg", "Thisted",
    "Tårnby", "Tønder", "Vallensbæk", "Varde", "Vejen", "Vejle",
    "Vesthimmerlands", "Viborg", "Vordingborg", "Ærø",
]

# Old spellings / common aliases people actually type that won't fuzzy-match
# well enough on their own (e.g. "Århus" vs "Aarhus" differ by more than
# difflib's default cutoff tolerates for a 6-letter word).
ALIASES = {
    "århus": "Aarhus",
    "aarhus c": "Aarhus",
    "aarhus n": "Aarhus",
    "aarhus v": "Aarhus",
    "aarhus sv": "Aarhus",
    "aarhus s": "Aarhus",
    "koebenhavn": "København",
    "kobenhavn": "København",
    "kbh": "København",
    "aalborg": "Aalborg",
    "ålborg": "Aalborg",
    "aabenraa": "Aabenraa",
    "åbenrå": "Aabenraa",
}


def resolve_city(text: str) -> tuple[str | None, list[str]]:
    """Returns (canonical_name, suggestions).

    canonical_name is set when there's a confident match (exact, alias, or
    a very close fuzzy match) -- use it as the corrected/normalized city.
    Otherwise canonical_name is None and suggestions lists a few
    close-but-not-confident candidates to show the person, so they can
    pick one or confirm their original spelling was intentional.
    """
    key = text.strip().lower()
    if not key:
        return None, []

    if key in ALIASES:
        return ALIASES[key], []

    for m in MUNICIPALITIES:
        if m.lower() == key:
            return m, []

    close = difflib.get_close_matches(key, [m.lower() for m in MUNICIPALITIES], n=3, cutoff=0.6)
    if close:
        best = close[0]
        canonical = next(m for m in MUNICIPALITIES if m.lower() == best)
        score = difflib.SequenceMatcher(None, key, best).ratio()
        if score >= 0.82:
            return canonical, []
        suggestions = [next(m for m in MUNICIPALITIES if m.lower() == c) for c in close]
        return None, suggestions

    return None, []
