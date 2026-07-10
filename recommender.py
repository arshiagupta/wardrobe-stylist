"""
Phase 3: styling recommender with gap detection
=================================================
What this does: takes an occasion, a vibe and a budget, filters the wardrobe
through constraint_engine.filter_wardrobe (deterministic, zero AI cost), then
makes ONE AI call to rank and explain outfits from the surviving items.

Two things stay deterministic, in code, never left to the model:
1. Hard filtering (formality/season/gender/profile blockers) - constraint_engine.py.
2. Occasion -> formality translation (OCCASION_FORMALITY_MAP below) and gap
   detection (detect_gaps) - whether a full outfit can even be assembled from
   what survived filtering. The model is only asked to rank, pair and explain
   items it is handed, and to word each gap using detect_gaps' finding. It
   never decides what counts as missing.

Any item id the model references that was not actually in the filtered list
is dropped and flagged (validate_outfit_ids), never trusted at face value.

get_outfits() does the work and returns structured data, used by both this
file's own main() (Phase 3 terminal output) and gap_fill.py (Phase 4, which
turns each outfit's "gaps" list into real shopping searches).

How to run
----------
python recommender.py --occasion "work dinner" --vibe "minimal, a bit edgy" --budget 60 --season summer

--season is optional (omit for "any season"). --budget is optional context
passed to the model for gap-fill sizing (Phase 4 uses it as a real per-item
price ceiling).
"""

import argparse
import json
import os
import sys
import time

from constraint_engine import load_wardrobe, load_profile, filter_wardrobe

# ---------------- configuration ----------------
MODEL = "gemini-3.1-flash-lite"      # verified working against this key, session 5 (Phase 1)
PRICE_PER_M_INPUT = 0.25             # USD per 1M input tokens, ai.google.dev/gemini-api/docs/pricing
PRICE_PER_M_OUTPUT = 1.50            # USD per 1M output tokens, ai.google.dev/gemini-api/docs/pricing
COST_CAP_USD = 0.05                  # sanity ceiling for a single ranking call, not expected to bind
MAX_RETRIES = 3

FORMALITY_LEVELS = ["casual", "smart casual", "business", "formal"]
SEASON_LEVELS = ["summer", "winter", "all season", "transitional"]
CATEGORY_BUCKETS = ["top", "bottom", "dress", "outerwear", "footwear", "accessory"]

# Deterministic occasion -> formality lookup (architecture principle 1: hard
# logic in code, not prompts). First matching keyword wins, case-insensitive
# substring match. Add more phrases here as real occasions come up. Anything
# that matches nothing falls back to no formality filter (shows every level),
# printed as a visible warning, never a silent guess.
OCCASION_FORMALITY_MAP = [
    (["black tie", "gala", "wedding", "formal event"], "formal"),
    (["interview", "business meeting", "boardroom"], "business"),
    (["work", "office", "dinner", "date", "smart casual", "brunch date"], "smart casual"),
    (["casual", "everyday", "weekend", "hangout", "brunch", "gym", "errand"], "casual"),
]


def map_occasion_to_formality(occasion):
    o = (occasion or "").strip().lower()
    for keywords, formality in OCCASION_FORMALITY_MAP:
        for kw in keywords:
            if kw in o:
                return formality
    return None


def bucket_items(items):
    buckets = {c: [] for c in CATEGORY_BUCKETS}
    for it in items:
        cat = it.get("category")
        if cat in buckets:
            buckets[cat].append(it)
    return buckets


def detect_gaps(buckets, formality, season):
    """Deterministic completeness check: can a full outfit be assembled at
    all from what passed filtering? Returns precise gap strings, e.g.
    'no smart casual bottoms'. Only reports categories that are actually
    empty, never a stylistic judgement call."""
    gaps = []
    label = " ".join(x for x in [formality, season] if x) or "any"

    has_dress = bool(buckets["dress"])
    has_top = bool(buckets["top"])
    has_bottom = bool(buckets["bottom"])
    has_footwear = bool(buckets["footwear"])

    if not has_dress:
        if not has_top and not has_bottom:
            gaps.append(f"no {label} tops, bottoms or dresses - an outfit cannot be built at all")
        elif not has_top:
            gaps.append(f"no {label} tops (no dress alternative either)")
        elif not has_bottom:
            gaps.append(f"no {label} bottoms (no dress alternative either)")

    if not has_footwear:
        gaps.append(f"no {label} footwear")

    return gaps


def validate_outfit_ids(outfits, valid_ids):
    """The model may only reference items that actually passed filtering.
    Any hallucinated id is dropped and flagged, never trusted."""
    cleaned = []
    for outfit in outfits:
        kept, dropped = [], []
        for iid in outfit.get("item_ids", []) or []:
            (kept if iid in valid_ids else dropped).append(iid)
        cleaned.append({**outfit, "item_ids": kept, "dropped_hallucinated_ids": dropped})
    return cleaned


def compact_item(it):
    """Trim each item to what the model needs for ranking/pairing. Keeps the
    prompt (and cost) small; full records stay in wardrobe.json."""
    return {
        "id": it["id"],
        "display_name": it["display_name"],
        "category": it["category"],
        "subcategory": it.get("subcategory"),
        "colour_primary": it.get("colour_primary"),
        "colour_secondary": it.get("colour_secondary"),
        "formality": it.get("formality"),
        "season": it.get("season"),
        "pattern": it.get("pattern"),
        "fit": it.get("fit"),
        "material": it.get("material"),
        "style_tags": it.get("style_tags"),
        "needs_review": it.get("needs_review", False),
    }


def build_prompt(occasion, vibe, budget, formality, season, items, gaps):
    items_json = json.dumps([compact_item(i) for i in items], ensure_ascii=False, indent=2)
    gaps_text = "; ".join(gaps) if gaps else "none - a full outfit can be assembled from the items below"
    formality_text = formality or "not determined from the occasion text, consider all formality levels"
    season_text = season or "any"
    budget_text = f"£{budget:.0f}" if budget is not None else "not specified"

    return f"""You are a wardrobe stylist. Occasion: "{occasion}" (mapped formality: {formality_text}).
Season preference: {season_text}. Requested vibe/style: "{vibe or 'not specified'}".
Budget available for any gap-fill purchase later: {budget_text} (context only, do not reason about it beyond that).

Below is the full list of wardrobe items that ALREADY PASSED deterministic hard
filtering in code (blockers and formality/season/gender all already applied).
Only reference items from this list, by id. Never invent an id or an item.

{items_json}

Known structural gaps already detected in code (do not contradict these, word
them naturally into any outfit they affect): {gaps_text}

Task: propose up to 6 distinct outfit ideas ranked by how well they suit the
occasion and vibe, best first. Each outfit is normally either (a dress +
footwear) or (a top + bottom + footwear). Reusing an item across more than one
outfit is fine if the wardrobe is small, do not fabricate items to avoid it.
If a needed category is structurally missing per the gaps above, still build
the outfit from what exists and list each missing piece as its own separate,
precise, purchasable description in "gaps" (e.g. two separate entries, one for
trousers and one for shoes, if both are missing, never one combined sentence).
Otherwise "gaps" must be an empty list. If fewer than 6 genuinely distinct
outfits are possible, return fewer rather than padding with near-duplicates.

Return ONLY JSON, no markdown fences, in exactly this shape:
{{
  "outfits": [
    {{
      "rank": 1,
      "item_ids": ["w_xxxxxxxxxx"],
      "reason": "one or two sentence styling explanation",
      "gaps": ["precise missing-item description", "..."]
    }}
  ]
}}"""


def call_model(client, types_mod, prompt):
    from google.genai import errors

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.models.generate_content(
                model=MODEL,
                contents=[prompt],
                config=types_mod.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.4,
                ),
            )
        except errors.APIError as e:
            if e.code != 429 and e.code < 500:
                raise  # permanent 4xx, retrying just re-bills a guaranteed failure
            last_err = e
            wait = 5 * attempt
            print(f"    attempt {attempt} failed ({e}), retrying in {wait}s")
            time.sleep(wait)
        except Exception as e:  # noqa: BLE001 - network/transient, worth retrying
            last_err = e
            wait = 5 * attempt
            print(f"    attempt {attempt} failed ({e}), retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"ranking call failed after {MAX_RETRIES} attempts: {last_err}")


def get_outfits(occasion, vibe, budget, season):
    """Does the full Phase 3 pipeline and returns everything both main()
    (terminal printing) and gap_fill.py (Phase 4) need. Makes at most one
    AI call. Returns a dict; see the keys set below."""
    formality = map_occasion_to_formality(occasion)

    wardrobe = load_wardrobe()
    profile = load_profile()
    request = {}
    if formality:
        request["formality"] = formality
    if season:
        request["season"] = season

    passing, excluded = filter_wardrobe(wardrobe, profile, request)
    buckets = bucket_items(passing)
    gaps = detect_gaps(buckets, formality, season)
    valid_ids = {it["id"] for it in passing}
    items_by_id = {it["id"]: it for it in passing}

    result = {
        "formality": formality,
        "wardrobe_count": len(wardrobe),
        "passing_count": len(passing),
        "excluded_count": len(excluded),
        "structural_gaps": gaps,
        "items_by_id": items_by_id,
        "outfits": [],
        "cost": 0.0,
        "in_tok": 0,
        "out_tok": 0,
    }
    if not passing:
        return result

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        sys.exit("Missing dependency. Run: pip install google-genai")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is not set.")

    prompt = build_prompt(occasion, vibe, budget, formality, season, passing, gaps)
    client = genai.Client(api_key=api_key)
    resp = call_model(client, types, prompt)

    usage = getattr(resp, "usage_metadata", None)
    in_tok = getattr(usage, "prompt_token_count", 0) or 0
    out_tok = getattr(usage, "candidates_token_count", 0) or 0
    cost = (in_tok / 1e6) * PRICE_PER_M_INPUT + (out_tok / 1e6) * PRICE_PER_M_OUTPUT

    text = (resp.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        sys.exit(f"Model did not return valid JSON: {e}\nRaw text:\n{text}")

    outfits = validate_outfit_ids(parsed.get("outfits", []), valid_ids)
    for o in outfits:
        o["gaps"] = [g for g in (o.get("gaps") or []) if isinstance(g, str) and g.strip()]

    result["outfits"] = outfits
    result["cost"] = cost
    result["in_tok"] = in_tok
    result["out_tok"] = out_tok
    return result


def main():
    parser = argparse.ArgumentParser(description="Phase 3 styling recommender")
    parser.add_argument("--occasion", required=True, help="free text, e.g. 'work dinner'")
    parser.add_argument("--vibe", default="", help="free text style descriptors, e.g. 'minimal, edgy'")
    parser.add_argument("--budget", type=float, default=None, help="GBP, context only in this phase")
    parser.add_argument("--season", default=None, choices=SEASON_LEVELS, help="optional, omit for any season")
    args = parser.parse_args()

    formality_preview = map_occasion_to_formality(args.occasion)
    if formality_preview is None:
        print(f"Could not map occasion '{args.occasion}' to a formality level. "
              f"Showing all formality levels instead of filtering (fallback, not a guess).")

    result = get_outfits(args.occasion, args.vibe, args.budget, args.season)

    print(f"occasion: {args.occasion!r} -> formality: {result['formality'] or 'any (unmapped)'}")
    print(f"season: {args.season or 'any'} | vibe: {args.vibe!r} | budget: {args.budget}")
    print(f"wardrobe items: {result['wardrobe_count']} | passing filters: {result['passing_count']} "
          f"| excluded: {result['excluded_count']}")
    if result["structural_gaps"]:
        print("detected gaps (code, deterministic):")
        for g in result["structural_gaps"]:
            print(f"  - {g}")
    else:
        print("no structural gaps detected: a full outfit can be built from the filtered wardrobe.")

    if not result["outfits"]:
        if result["passing_count"] == 0:
            print("\nNo items passed filtering, nothing to rank. Stopping before any AI call.")
        return

    items_by_id = result["items_by_id"]
    print(f"\n================ {len(result['outfits'])} outfit(s), "
          f"cost ${result['cost']:.5f} ================")
    for outfit in result["outfits"]:
        names = [items_by_id[i]["display_name"] for i in outfit["item_ids"] if i in items_by_id]
        print(f"\nrank {outfit.get('rank')}: {', '.join(names) if names else '(no valid items)'}")
        print(f"  reason: {outfit.get('reason')}")
        for gap in outfit.get("gaps", []):
            print(f"  gap: {gap}")
        if outfit.get("dropped_hallucinated_ids"):
            print(f"  WARNING dropped hallucinated ids not in filtered wardrobe: {outfit['dropped_hallucinated_ids']}")

    print(f"\ntokens in/out: {result['in_tok']}/{result['out_tok']} | est cost: ${result['cost']:.5f}")


if __name__ == "__main__":
    main()
