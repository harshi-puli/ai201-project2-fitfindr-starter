"""
Tests for the three FitFindr tools.

Run with:
    pytest tests/

The search_listings tests are pure (no network). The suggest_outfit and
create_fit_card tests target the failure modes: the create_fit_card guard
returns before any LLM call, and suggest_outfit's empty-wardrobe path falls
back to a non-empty string even if the LLM call fails — so both assertions hold
whether or not a network/API key is available.
"""

from tools import search_listings, suggest_outfit, create_fit_card


# ── Tool 1: search_listings ─────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Nonsense query with impossible filters → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_results_sorted_by_relevance():
    # More specific query keywords should rank the best match first.
    results = search_listings("y2k butterfly baby tee", size=None, max_price=50)
    assert len(results) > 0
    assert "Baby Tee" in results[0]["title"]


def test_search_size_filter_case_insensitive():
    # "m" should match a size string like "S/M".
    results = search_listings("tee", size="m", max_price=100)
    assert all("m" in str(item["size"]).lower() for item in results)


# ── Tool 2: suggest_outfit ──────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe_returns_string():
    # Failure mode: empty wardrobe must NOT crash; returns non-empty advice.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, {"items": []})
    assert isinstance(result, str)
    assert result.strip() != ""


# ── Tool 3: create_fit_card ─────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_guard():
    # Failure mode: empty outfit string → informative message, no exception.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("", item)
    assert isinstance(result, str)
    assert result.strip() != ""
    assert "outfit" in result.lower()


def test_create_fit_card_whitespace_outfit_guard():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("   \n  ", item)
    assert isinstance(result, str)
    assert result.strip() != ""
