"""
Phase 4, hour one: Serper.dev UK Google Shopping coverage check
=================================================================
Before building the real retrieval adapter, this checks a locked
assumption from session 3 that has never actually been tested: do
Zara, H&M and Mango show up in UK Google Shopping results through
Serper at all. Diagnostic only, not part of the product. Zero dollar
cost (free tier), still capped and logged, same discipline as every
other external call in this project.

Also applies the project's core lesson from the Gemini model saga to a
new API: print the raw response for the first query before trusting
any field name, verify the actual shape live instead of assuming it
from documentation.

Run: python verify_serper_coverage.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

API_KEY_ENV = "SERPER_API_KEY"
ENDPOINT = "https://google.serper.dev/shopping"
MAX_QUERIES = 6           # hard cap, this is a calibration check, not the real app
NUM_RESULTS = 10
COUNTRY = "gb"             # Google 'gl' parameter uses ISO 3166-1 alpha-2. "uk" is NOT valid: a first
                           # run with "uk" silently fell back to US-anchored results (Zara USA, USD
                           # prices, gl=us embedded in the returned links), no error was raised. "gb"
                           # is the correct code for the United Kingdom.

QUERIES = [
    "Zara midi skirt",
    "H&M blouse",
    "Mango trousers",
]


def call_serper(api_key, query):
    body = json.dumps({"q": query, "gl": COUNTRY, "num": NUM_RESULTS}).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=body, method="POST",
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        sys.exit(f"{API_KEY_ENV} is not set in this process' environment.")

    if len(QUERIES) > MAX_QUERIES:
        sys.exit(f"Query list exceeds MAX_QUERIES cap of {MAX_QUERIES}, trim it first.")

    print(f"Running {len(QUERIES)} queries against {ENDPOINT} (gl={COUNTRY})\n")
    first = True
    merchant_hits = {}

    for i, q in enumerate(QUERIES, 1):
        print(f"[{i}/{len(QUERIES)}] query: {q!r}")
        try:
            data = call_serper(api_key, q)
        except urllib.error.HTTPError as e:
            print(f"    FAILED: HTTP {e.code} {e.reason}")
            continue
        except Exception as e:  # noqa: BLE001
            print(f"    FAILED: {e}")
            continue

        if first:
            print("\n--- raw response for first query, to confirm actual field names ---")
            print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
            print("--- end raw sample ---\n")
            first = False

        results = data.get("shopping", [])
        sources = [r.get("source") for r in results if r.get("source")]
        print(f"    {len(results)} results, merchants seen: {sources}")
        for s in sources:
            merchant_hits[s] = merchant_hits.get(s, 0) + 1
        time.sleep(1)

    print("\n================ merchant coverage summary ================")
    for target in ["Zara", "H&M", "Mango"]:
        matches = {m: c for m, c in merchant_hits.items() if target.lower() in m.lower()}
        status = matches if matches else "NOT SEEN"
        print(f"{target}: {status}")

    print(f"\nall merchants seen across all queries: {merchant_hits}")


if __name__ == "__main__":
    main()
