"""
Phase 2: profile + constraint engine
=====================================
Pure code, zero AI cost. Filters wardrobe items against two things:

1. profile.json  - the builder's standing hard blockers (e.g. "no crop tops"),
                    checked against every item regardless of context.
2. request dict  - optional per-styling-request wants (formality, season,
                    gender), checked only when that key is present.

Only references tier 1 fields (category, article_type, subcategory,
colour_primary/secondary, pattern, style_tags, formality, season, gender),
which are the fields the schema guarantees are meaningful. Never trusts
tier 2 fields for hard filtering (architecture principle 5, context-full.md).

Every exclusion carries a reason string, so a rejection is always explainable,
never a silent drop.
"""
import json
import os

WARDROBE_PATH = os.path.join("wardrobe", "wardrobe.json")
PROFILE_PATH = os.path.join("wardrobe", "profile.json")


def load_wardrobe(path=WARDROBE_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["items"]


def load_profile(path=PROFILE_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _norm(s):
    return str(s).strip().lower() if s is not None else None


def _equals_any(value, blocked_list):
    v = _norm(value)
    if v is None:
        return None
    for b in blocked_list:
        if _norm(b) == v:
            return b
    return None


def _contains_any(value, blocked_list):
    v = _norm(value)
    if not v:
        return None
    for b in blocked_list:
        if _norm(b) in v:
            return b
    return None


def profile_reasons(item, profile):
    """Reasons a single item is blocked by the builder's standing profile."""
    reasons = []

    if profile.get("exclude_needs_review", True) and item.get("needs_review"):
        reasons.append("needs_review")

    hit = _equals_any(item.get("category"), profile.get("blocked_categories", []))
    if hit:
        reasons.append(f"blocked_category:{hit}")

    for field in ("article_type", "subcategory"):
        hit = _contains_any(item.get(field), profile.get("blocked_article_types", []))
        if hit:
            reasons.append(f"blocked_article_type:{hit}")

    for field in ("colour_primary", "colour_secondary"):
        hit = _equals_any(item.get(field), profile.get("blocked_colours", []))
        if hit:
            reasons.append(f"blocked_colour:{hit}")

    hit = _equals_any(item.get("pattern"), profile.get("blocked_patterns", []))
    if hit:
        reasons.append(f"blocked_pattern:{hit}")

    blocked_tags = {_norm(t) for t in profile.get("blocked_style_tags", [])}
    for tag in item.get("style_tags") or []:
        if _norm(tag) in blocked_tags:
            reasons.append(f"blocked_style_tag:{tag}")

    # Free-text avoid list (7B): the user's own "things I never want" typed in the
    # profile. Deterministic substring match across every descriptive field, so a
    # term like "neon", "crop top" or "floral" is caught wherever it appears. This
    # is a hard guarantee, the same discipline as the blocked_* lists. Keep terms
    # specific: a broad word like "top" will exclude every top, by design.
    for term in profile.get("avoid_terms", []):
        nt = _norm(term)
        if not nt:
            continue
        fields = [item.get("display_name"), item.get("article_type"), item.get("subcategory"),
                  item.get("colour_primary"), item.get("colour_secondary"),
                  item.get("pattern"), item.get("material")]
        fields.extend(item.get("style_tags") or [])
        for f in fields:
            nf = _norm(f)
            if nf and nt in nf:
                reasons.append(f"avoid:{term}")
                break

    return reasons


def request_reasons(item, request):
    """Reasons a single item doesn't match this specific styling request.
    request is optional; any key left out is not checked."""
    if not request:
        return []
    reasons = []

    want_formality = request.get("formality")
    if want_formality and item.get("formality") != _norm(want_formality):
        reasons.append(f"formality_mismatch:wants {want_formality}, item is {item.get('formality')}")

    want_season = request.get("season")
    if want_season and item.get("season") not in (_norm(want_season), "all season"):
        reasons.append(f"season_mismatch:wants {want_season}, item is {item.get('season')}")

    want_gender = request.get("gender")
    if want_gender and item.get("gender") not in (_norm(want_gender), "unisex"):
        reasons.append(f"gender_mismatch:wants {want_gender}, item is {item.get('gender')}")

    return reasons


def filter_wardrobe(items, profile, request=None):
    """Returns (passing_items, excluded) where excluded is a list of
    {"item": item, "reasons": [...]} so every rejection stays explainable."""
    passing = []
    excluded = []
    for item in items:
        reasons = profile_reasons(item, profile) + request_reasons(item, request)
        if reasons:
            excluded.append({"item": item, "reasons": reasons})
        else:
            passing.append(item)
    return passing, excluded


if __name__ == "__main__":
    wardrobe = load_wardrobe()
    profile = load_profile()
    passing, excluded = filter_wardrobe(wardrobe, profile)
    print(f"wardrobe items: {len(wardrobe)}")
    print(f"pass profile blockers: {len(passing)}")
    print(f"excluded: {len(excluded)}")
    for e in excluded:
        print(f"  - {e['item']['display_name']}: {e['reasons']}")
