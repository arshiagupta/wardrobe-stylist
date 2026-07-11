"""
Phase 4: live shopping retrieval and deterministic filtering
===============================================================
Wraps Serper.dev's Google Shopping endpoint. Two things stay
deterministic, in code, never left to the model (architecture
principle 1, same discipline as constraint_engine.py):

1. Merchant whitelist - only Zara, H&M and Mango pass, checked by
   substring match against Serper's 'source' field.
2. Budget filter - parsed from Serper's price string into a float,
   compared against the request's budget with plain arithmetic.

A query cache (wardrobe/shopping_cache.json) means an identical live
search is never repeated, free-tier quota is spent once per distinct
query. MAX_SEARCHES_PER_REQUEST caps NEW live calls per styling
request at 3 (locked session 3), cache hits don't count against it.

Known scope limitation, logged session 6: Serper's shopping endpoint
returns a Google Shopping product page as the "link" field, not a
direct retailer URL (confirmed: only 7 fields exist in the raw
response, and a guessed /product endpoint to resolve one 404s). A
competing paid provider, SerpApi, documents a direct_link field for
this exact need, but switching provider was judged too large a pivot
for the remaining timebox given Serper was already locked in session 3
for cost reasons. Shipped as-is: the link is genuinely clickable and
almost certainly leads to the retailer via one extra Google-hosted
page, not a direct URL. README must state this plainly.

Also logged session 6: Google's 'gl' country parameter needs the ISO
3166-1 alpha-2 code. "gb" for the United Kingdom, NOT "uk". Passing
"uk" does not error, it silently falls back to US-anchored results,
discovered only by inspecting the raw response body.

How to run (self-test with a couple of real free-tier calls)
--------------------------------------------------------------
python shopping_search.py
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

SERPER_ENDPOINT = "https://google.serper.dev/shopping"
API_KEY_ENV = "SERPER_API_KEY"
COUNTRY = "gb"                        # Google 'gl' param, ISO 3166-1 alpha-2. NOT "uk", see note above.
NUM_RESULTS = 10
MAX_SEARCHES_PER_REQUEST = 2          # lowered 3 -> 2 session 7 (builder: 1-2 new buys max, trims cost)
MAX_RETRIES = 3
CACHE_PATH = os.path.join("wardrobe", "shopping_cache.json")

MERCHANT_WHITELIST = ["zara", "h&m", "mango"]  # substring match, case-insensitive, against Serper's 'source' field


class SearchBudgetExceeded(Exception):
    pass


def _load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache):
    """Best-effort. Vercel's deployed filesystem is read-only outside /tmp,
    so on the live site this silently becomes a no-op: MAX_SEARCHES_PER_REQUEST
    is the real safety net regardless, caching is a local-dev/cost nicety."""
    tmp = CACHE_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass


def parse_price(price_str):
    """'£35.99' -> 35.99. Returns None if it can't be parsed, never guesses
    a number rather than admit it doesn't know."""
    if not price_str:
        return None
    match = re.search(r"[\d,]+\.?\d*", price_str)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def filter_by_merchant_whitelist(results, whitelist=MERCHANT_WHITELIST):
    passing, excluded = [], []
    for r in results:
        source = (r.get("source") or "").lower()
        if any(w in source for w in whitelist):
            passing.append(r)
        else:
            excluded.append({"item": r, "reason": f"merchant '{r.get('source')}' not in whitelist"})
    return passing, excluded


def filter_by_budget(results, max_budget):
    if max_budget is None:
        return results, []
    passing, excluded = [], []
    for r in results:
        price = parse_price(r.get("price"))
        if price is None:
            excluded.append({"item": r, "reason": "price could not be parsed"})
        elif price > max_budget:
            excluded.append({"item": r, "reason": f"price {price} over budget {max_budget}"})
        else:
            passing.append(r)
    return passing, excluded


def call_serper(api_key, query, gl=COUNTRY, num=NUM_RESULTS):
    body = json.dumps({"q": query, "gl": gl, "num": num}).encode("utf-8")
    req = urllib.request.Request(
        SERPER_ENDPOINT, data=body, method="POST",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
    )
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise  # permanent 4xx, retrying just repeats a guaranteed failure
            last_err = e
        except Exception as e:  # noqa: BLE001 - network/transient, worth retrying
            last_err = e
        wait = 3 * attempt
        print(f"    attempt {attempt} failed ({last_err}), retrying in {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"Serper call failed after {MAX_RETRIES} attempts: {last_err}")


def search_shopping(query, max_budget=None, search_count=None):
    """search_count: a single-element list used as a shared counter across
    multiple calls within one styling request, so MAX_SEARCHES_PER_REQUEST
    is enforced per request, not just per call. Cache hits are free and
    don't consume the counter."""
    cache = _load_cache()
    cache_key = query.strip().lower()

    if cache_key in cache:
        raw = cache[cache_key]
        cached = True
    else:
        if search_count is not None and search_count[0] >= MAX_SEARCHES_PER_REQUEST:
            raise SearchBudgetExceeded(
                f"MAX_SEARCHES_PER_REQUEST ({MAX_SEARCHES_PER_REQUEST}) reached for this styling request")
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            sys.exit(f"{API_KEY_ENV} is not set.")
        raw = call_serper(api_key, query)
        if search_count is not None:
            search_count[0] += 1
        cache[cache_key] = raw
        _save_cache(cache)
        cached = False

    results = raw.get("shopping", [])
    merchant_passing, merchant_excluded = filter_by_merchant_whitelist(results)
    budget_passing, budget_excluded = filter_by_budget(merchant_passing, max_budget)

    return {
        "query": query,
        "cached": cached,
        "raw_count": len(results),
        "passing": budget_passing,
        "excluded": merchant_excluded + budget_excluded,
    }


if __name__ == "__main__":
    counter = [0]
    for q, budget in [("Zara black ankle boots", 60), ("H&M white t-shirt", 15)]:
        print(f"\nquery: {q!r} (budget {budget})")
        result = search_shopping(q, max_budget=budget, search_count=counter)
        print(f"  cached: {result['cached']} | raw: {result['raw_count']} | "
              f"passing whitelist+budget: {len(result['passing'])} | excluded: {len(result['excluded'])}")
        for p in result["passing"][:3]:
            print(f"    - {p['title']} | {p['source']} | {p['price']}")
        for e in result["excluded"][:3]:
            print(f"    x {e['item'].get('title')}: {e['reason']}")
    print(f"\nlive searches used this run: {counter[0]}/{MAX_SEARCHES_PER_REQUEST}")
