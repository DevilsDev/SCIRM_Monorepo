"""Regulatory watch matching: whole words, ignoring case and punctuation, regulatory sources only."""

from libs.intel import watchlist


def signal(**extra):
    return {"source": "ema_dhpc", "title": "EMA safety communication: Jentadueto", "summary": "",
            "raw": {"substances": ["linagliptin", "metformin hydrochloride"]}, **extra}


def test_terms_match_whole_words_in_the_title_summary_and_substances():
    assert watchlist.matching_terms(signal(), ["Metformin", "linagliptin", "jentadueto"]) == \
        ["Metformin", "linagliptin", "jentadueto"]
    assert watchlist.matching_terms(signal(), ["metformina", "gliptin", "insulin"]) == []
    assert watchlist.matching_terms(signal(title="Recall: METFORMIN-HCl 500 mg"), ["metformin hcl"]) == ["metformin hcl"]


def test_only_regulatory_sources_are_watched():
    assert watchlist.matching_terms(signal(source="gdacs"), ["metformin"]) == []


def test_terms_need_three_letters_or_digits():
    assert watchlist.clean_term("  Human   normal immunoglobulins ") == "Human normal immunoglobulins"
    for bad in ("ab", "--", "  "):
        try:
            watchlist.clean_term(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_sql_prefilters_use_the_first_word():
    assert watchlist.like_patterns(["Metformin hydrochloride", "rifampicin", "Rifampicin"]) == ["%metformin%", "%rifampicin%"]
