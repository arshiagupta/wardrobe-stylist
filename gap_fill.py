"""
Phase 4: gap fill - turns a recommender.py outfit gap into a real,
purchasable product suggestion
=====================================================================
For each outfit's "gaps" (a list of precise single-item descriptions,
e.g. "black strappy heeled sandals"), this:

1. Builds a Serper query, folding in "women's" deterministically since
   profile.json fixes this wardrobe to womenswear and Serper returns
   no gender field to filter on (session 6 finding: menswear items
   otherwise leak through uncaught).
2. Runs it through shopping_search.search_shopping (deterministic
   merchant whitelist + budget filter already applied there).
3. One small AI call picks the single best candidate for the outfit's
   vibe and infers best-effort tier 2 style attributes. The model may
   only reference a candidate by its "position" number; any position
   it invents or that is out of range is dropped, never trusted
   (is_valid_position, same discipline as recommender.py's
   validate_outfit_ids).

MAX_SEARCHES_PER_REQUEST (shared with shopping_search.py, 3, locked
session 3) is enforced across the WHOLE request, all outfits combined,
not per outfit. Once reached, remaining gaps are marked skipped with a
clear reason, never silently dropped. Cache hits in shopping_search.py
don't count against the cap.

How to run
----------
python gap_fill.py --occasion "work dinner" --vibe "smart and polished but not stiff" --budget 60
"""
import argparse
import json
import os
import sys
import time

import recommender
from recommender import SEASON_LEVELS
from shopping_search import search_shopping, MAX_SEARCHES_PER_REQUEST, SearchBudgetExceeded

MODEL = "gemini-3.1-flash-lite"
PRICE_PER_M_INPUT = 0.25
PRICE_PER_M_OUTPUT = 1.50
MAX_CANDIDATES_IN_PROMPT = 8
MAX_RETRIES = 3
GENDER_PREFIX = "women's"

PATTERNS = {"solid", "striped", "floral", "check", "graphic", "colour block", "other"}
FITS = {"slim", "regular", "relaxed", "oversized"}


def build_query(gap_text, gender_prefix=GENDER_PREFIX):
    g = (gap_text or "").strip()
    if not g:
        return g
    marker = gender_prefix.split("'")[0].lower()  # "women's" -> "women"
    if marker not in g.lower():
        return f"{gender_prefix} {g}"
    return g


def gender_to_prefix(gender):
    """Map a stated gender preference to a Serper query prefix (7B). Neutral,
    mixed or unknown -> no prefix, so new-buy searches span genders. Gender NEVER
    filters the user's own uploaded items, it only steers what NEW products are
    searched for and the styling language."""
    g = (gender or "").strip().lower()
    if g in ("womenswear", "women", "women's", "female", "woman", "feminine"):
        return "women's"
    if g in ("menswear", "men", "men's", "male", "man", "masculine"):
        return "men's"
    return ""


def is_valid_position(position, candidates):
    return isinstance(position, int) and 0 <= position < len(candidates)


def compact_candidate(r, position):
    return {"position": position, "title": r.get("title"), "source": r.get("source"), "price": r.get("price")}


def build_pick_prompt(gap_text, other_item_names, vibe, budget, candidates):
    candidates_json = json.dumps(candidates, ensure_ascii=False, indent=2)
    context = ", ".join(other_item_names) if other_item_names else "nothing else specified"
    budget_text = f"up to £{budget:.0f}" if isinstance(budget, (int, float)) else "not specified"

    return f"""You are a wardrobe stylist choosing ONE product to fill a specific gap in an outfit.

Gap to fill: "{gap_text}"
Worn together with: {context}
Overall vibe: "{vibe or 'not specified'}"
Budget: {budget_text}

Candidates below already passed a deterministic retailer whitelist and budget
filter in code. Only choose by "position" from this exact list, never invent one.

{candidates_json}

Task: pick the candidate that best fills the gap and suits the vibe and the
other items. If none are a good enough match, set "position" to null and say
why in "reason". Infer these as a best-effort visual guess from the title
alone, mark honestly, they are not guaranteed accurate:
pattern (one of: solid, striped, floral, check, graphic, colour block, other),
fit (one of: slim, regular, relaxed, oversized), material, style_tags (up to 5,
lowercase).

Return ONLY JSON, no markdown fences:
{{
  "position": 3,
  "reason": "one sentence on why this fits",
  "pattern": "...", "fit": "...", "material": "...", "style_tags": ["..."]
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
                    temperature=0.3,
                ),
            )
        except errors.APIError as e:
            if e.code != 429 and e.code < 500:
                raise
            last_err = e
            wait = 5 * attempt
            print(f"    attempt {attempt} failed ({e}), retrying in {wait}s")
            time.sleep(wait)
        except Exception as e:  # noqa: BLE001 - network/transient, worth retrying
            last_err = e
            wait = 5 * attempt
            print(f"    attempt {attempt} failed ({e}), retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"gap-fill pick call failed after {MAX_RETRIES} attempts: {last_err}")


def pick_product_for_gap(client, types_mod, gap_text, other_item_names, vibe, budget, candidates):
    """candidates: raw Serper result dicts, already whitelist+budget filtered.
    Returns (pick_dict, cost, in_tok, out_tok). pick_dict always has
    'picked': True/False, never trusts a position outside the list handed in."""
    trimmed = candidates[:MAX_CANDIDATES_IN_PROMPT]
    compact = [compact_candidate(r, i) for i, r in enumerate(trimmed)]
    prompt = build_pick_prompt(gap_text, other_item_names, vibe, budget, compact)

    resp = call_model(client, types_mod, prompt)
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
        return {"picked": False, "reason": f"model did not return valid JSON: {e}"}, cost, in_tok, out_tok

    position = parsed.get("position")
    if position is None:
        return {"picked": False, "reason": parsed.get("reason", "no good match")}, cost, in_tok, out_tok

    if not is_valid_position(position, trimmed):
        return ({"picked": False,
                 "reason": f"model referenced invalid position {position!r}, dropped (hallucination guard)"},
                cost, in_tok, out_tok)

    chosen = trimmed[position]
    pattern = parsed.get("pattern") if parsed.get("pattern") in PATTERNS else None
    fit = parsed.get("fit") if parsed.get("fit") in FITS else None
    style_tags = [t.lower() for t in (parsed.get("style_tags") or []) if isinstance(t, str)][:5]

    pick = {
        "picked": True,
        "title": chosen.get("title"),
        "source": chosen.get("source"),
        "price": chosen.get("price"),
        "image": chosen.get("imageUrl"),
        "link": chosen.get("link"),
        "reason": parsed.get("reason"),
        "pattern": pattern,
        "fit": fit,
        "material": parsed.get("material"),
        "style_tags": style_tags,
    }
    return pick, cost, in_tok, out_tok


def fill_gaps_for_request(occasion, vibe, budget, season, wardrobe=None, profile=None):
    outcome = recommender.get_outfits(occasion, vibe, budget, season, wardrobe=wardrobe, profile=profile)
    outcome["gap_fill_total_cost"] = 0.0
    outcome["live_searches_used"] = 0

    # Budget-gated (builder rule, session 7): with no budget, never run a paid
    # product search. Any gap the model named (a missing category, or a stylistic
    # replacement it flagged) is surfaced as a text note only, no Serper, no cost.
    if not budget or budget <= 0:
        for outfit in outcome["outfits"]:
            outfit["gap_fills"] = [
                {"gap": g, "picked": False,
                 "reason": "styling note only - set a budget above 0 to get a shoppable suggestion"}
                for g in (outfit.get("gaps") or [])
            ]
        return outcome

    if not any(o.get("gaps") for o in outcome["outfits"]):
        return outcome

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        sys.exit("Missing dependency. Run: pip install google-genai")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=api_key)

    search_count = [0]
    gap_fill_cost = 0.0
    items_by_id = outcome["items_by_id"]

    # Gender steers only the NEW-BUY search wording. profile None (CLI) keeps the
    # old women's default; the web always passes a profile, whose neutral/mixed
    # value resolves to no prefix.
    gender_prefix = GENDER_PREFIX
    if profile is not None:
        gender_prefix = gender_to_prefix(profile.get("gender"))

    for outfit in outcome["outfits"]:
        gaps = outfit.get("gaps") or []
        filled = []
        other_item_names = [items_by_id[i]["display_name"] for i in outfit["item_ids"] if i in items_by_id]

        for gap_text in gaps:
            query = build_query(gap_text, gender_prefix)
            try:
                search_result = search_shopping(query, max_budget=budget, search_count=search_count)
            except SearchBudgetExceeded as e:
                filled.append({"gap": gap_text, "picked": False, "reason": str(e)})
                continue

            candidates = search_result["passing"]
            if not candidates:
                filled.append({
                    "gap": gap_text, "picked": False,
                    "reason": f"no whitelisted/in-budget candidates for query {query!r} "
                              f"({search_result['raw_count']} raw results, all excluded)",
                })
                continue

            pick, cost, in_tok, out_tok = pick_product_for_gap(
                client, types, gap_text, other_item_names, vibe, budget, candidates)
            gap_fill_cost += cost
            pick["gap"] = gap_text
            filled.append(pick)

        outfit["gap_fills"] = filled

    outcome["gap_fill_total_cost"] = gap_fill_cost
    outcome["live_searches_used"] = search_count[0]
    return outcome


def main():
    parser = argparse.ArgumentParser(description="Phase 4 gap fill")
    parser.add_argument("--occasion", required=True)
    parser.add_argument("--vibe", default="")
    parser.add_argument("--budget", type=float, default=None)
    parser.add_argument("--season", default=None, choices=SEASON_LEVELS)
    args = parser.parse_args()

    outcome = fill_gaps_for_request(args.occasion, args.vibe, args.budget, args.season)
    items_by_id = outcome["items_by_id"]

    print(f"occasion: {args.occasion!r} -> formality: {outcome['formality'] or 'any (unmapped)'}")
    print(f"wardrobe items: {outcome['wardrobe_count']} | passing filters: {outcome['passing_count']}")
    if outcome["structural_gaps"]:
        print("structural gaps (deterministic):")
        for g in outcome["structural_gaps"]:
            print(f"  - {g}")

    for outfit in outcome["outfits"]:
        names = [items_by_id[i]["display_name"] for i in outfit["item_ids"] if i in items_by_id]
        print(f"\nrank {outfit.get('rank')}: {', '.join(names) if names else '(no valid items)'}")
        print(f"  reason: {outfit.get('reason')}")
        for fill in outfit.get("gap_fills", []):
            gap = fill.get("gap")
            if fill.get("picked"):
                print(f"  gap-fill for '{gap}': {fill['title']} | {fill['source']} | {fill['price']}")
                print(f"    link: {fill['link']}")
                print(f"    styling note: {fill.get('reason')}")
            else:
                print(f"  gap-fill for '{gap}': NOT FILLED - {fill.get('reason')}")

    print(f"\nranking cost: ${outcome['cost']:.5f} | gap-fill AI cost: ${outcome['gap_fill_total_cost']:.5f}")
    print(f"total AI cost this run: ${outcome['cost'] + outcome['gap_fill_total_cost']:.5f}")
    print(f"live Serper searches used: {outcome['live_searches_used']}/{MAX_SEARCHES_PER_REQUEST}")


if __name__ == "__main__":
    main()
