"""
trigger_failures.py — deliberately trigger all three FitFindr failure modes.

Run from the project root for your demo video:
    python tests/trigger_failures.py

Each failure produces a specific, informative string — no Python exception.
"""

import os
import sys

# Allow running as `python tests/trigger_failures.py` from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import search_listings, suggest_outfit, create_fit_card
from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


def banner(text: str) -> None:
    print("\n" + "═" * 76)
    print(text)
    print("═" * 76)


# ── Failure 1: search_listings returns zero results ─────────────────────────
banner("FAILURE 1 — search_listings returns [] (impossible query, no exception)")
empty = search_listings("designer ballgown", size="XXS", max_price=5)
print("Direct call ->", empty)
assert empty == [], "expected an empty list"

print("\nFull agent response to the same impossible query:")
session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
print("  error    ->", session["error"])
print("  fit_card ->", session["fit_card"])
assert session["error"] and session["fit_card"] is None


# ── Failure 2: suggest_outfit with an empty wardrobe ────────────────────────
banner("FAILURE 2 — suggest_outfit with EMPTY wardrobe (general advice, no crash)")
item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
advice = suggest_outfit(item, get_empty_wardrobe())
print(advice)
assert isinstance(advice, str) and advice.strip()


# ── Failure 3: create_fit_card with an empty outfit string ──────────────────
banner("FAILURE 3 — create_fit_card with EMPTY outfit string (descriptive message)")
msg = create_fit_card("", item)
print(msg)
assert isinstance(msg, str) and msg.strip()

print("\n✅ All three failure modes recovered gracefully — zero exceptions raised.")
