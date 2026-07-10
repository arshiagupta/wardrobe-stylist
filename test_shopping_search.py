"""
Phase 4 eval: deterministic pieces only, pure code, zero network calls.
Run: python test_shopping_search.py
"""
from shopping_search import parse_price, filter_by_merchant_whitelist, filter_by_budget

PASSED = 0
FAILED = []


def check(name, condition):
    global PASSED
    if condition:
        PASSED += 1
    else:
        FAILED.append(name)


def result(source="Zara UK", price="£35.99", title="test item"):
    return {"title": title, "source": source, "price": price,
            "link": "x", "imageUrl": "x", "productId": "1", "position": 1}


def run():
    # --- parse_price ---
    check("1 parses GBP symbol", parse_price("£35.99") == 35.99)
    check("2 parses USD symbol", parse_price("$15.96") == 15.96)
    check("3 parses comma thousands", parse_price("£1,299.00") == 1299.00)
    check("4 empty string returns None", parse_price("") is None)
    check("5 None returns None", parse_price(None) is None)
    check("6 no digits returns None", parse_price("Free") is None)

    # --- filter_by_merchant_whitelist ---
    results = [result(source="Zara UK"), result(source="Nordstrom"), result(source="H&M GB")]
    passing, excluded = filter_by_merchant_whitelist(results)
    check("7 whitelisted merchants pass", len(passing) == 2)
    check("8 non-whitelisted merchant excluded with a reason", len(excluded) == 1 and "reason" in excluded[0])
    check("9 excluded item is the Nordstrom one", excluded[0]["item"]["source"] == "Nordstrom")

    # --- filter_by_budget ---
    results2 = [result(price="£20.00"), result(price="£99.00"), result(price="not a price")]
    passing2, excluded2 = filter_by_budget(results2, max_budget=50)
    check("10 under-budget item passes", len(passing2) == 1 and passing2[0]["price"] == "£20.00")
    check("11 over-budget item excluded", any("over budget" in e["reason"] for e in excluded2))
    check("12 unparseable price excluded, not silently kept",
          any("could not be parsed" in e["reason"] for e in excluded2))
    check("13 max_budget=None skips budget filtering entirely",
          filter_by_budget(results2, max_budget=None) == (results2, []))

    print(f"passed: {PASSED}/{PASSED + len(FAILED)}")
    if FAILED:
        print("failed cases:")
        for name in FAILED:
            print(f"  - {name}")


if __name__ == "__main__":
    run()
