"""Reverse lookup: on-screen text -> route name.

The practical question this answers is "I am looking at this screen, what
route name does analytics report for it?". Matching runs in three tiers so
that an exact hit is never buried under fuzzy ones.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .parser import Route

EXACT = "exact"
CONTAINS = "contains"
NORMALIZED = "normalized"
TIER_ORDER = (EXACT, CONTAINS, NORMALIZED)


@dataclass
class Match:
    tier: str
    key: str
    text: str
    route: Route

    @property
    def rank(self) -> int:
        return TIER_ORDER.index(self.tier)


def normalize(s: str) -> str:
    """Strip whitespace, punctuation and width differences.

    Interpolated copy ("You have {{count}} items left.") never matches the
    rendered string character for character, and CJK text mixes full-width
    and half-width punctuation. Normalizing both sides makes those hit.
    """
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE).casefold()


def lookup(query: str, routes: list[Route], i18n: dict[str, str],
           limit: int = 20) -> list[Match]:
    """Find routes whose screens contain ``query``.

    ``i18n`` maps keys to text; each route carries the keys found in its
    component, so a text hit is attributed to every route that uses that key.
    """
    q, qn = query.strip(), normalize(query)
    if not q:
        return []

    by_key: dict[str, list[Route]] = {}
    for r in routes:
        for k in r.text_keys:
            by_key.setdefault(k, []).append(r)

    out: list[Match] = []
    seen: set[tuple[str, str, str]] = set()
    for key, text in i18n.items():
        if key not in by_key:
            continue
        if text == q:
            tier = EXACT
        elif q in text:
            tier = CONTAINS
        elif qn and qn in normalize(text):
            tier = NORMALIZED
        else:
            continue
        for r in by_key[key]:
            ident = (tier, key, r.route)
            if ident in seen:
                continue
            seen.add(ident)
            out.append(Match(tier=tier, key=key, text=text, route=r))

    out.sort(key=lambda m: (m.rank, m.route.route))
    return out[:limit]
