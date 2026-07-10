"""
Phase 4 eval: deterministic pieces only, pure code, zero network/AI calls.
Run: python test_gap_fill.py
"""
from gap_fill import build_query, is_valid_position

PASSED = 0
FAILED = []


def check(name, condition):
    global PASSED
    if condition:
        PASSED += 1
    else:
        FAILED.append(name)


def run():
    # --- build_query: deterministic gender fold-in ---
    check("1 adds women's prefix when absent",
          build_query("black strappy heeled sandals") == "women's black strappy heeled sandals")
    check("2 does not double-prefix when already present",
          build_query("women's block heels") == "women's block heels")
    check("3 case-insensitive check for existing gender word",
          build_query("Women's Block Heels") == "Women's Block Heels")
    check("4 empty gap text returns empty string, not a bare prefix", build_query("") == "")

    # --- is_valid_position: the hallucination guard on the model's pick ---
    candidates = [{"title": "a"}, {"title": "b"}, {"title": "c"}]
    check("5 in-range position is valid", is_valid_position(1, candidates) is True)
    check("6 position 0 is valid (not falsy-rejected)", is_valid_position(0, candidates) is True)
    check("7 negative position is invalid", is_valid_position(-1, candidates) is False)
    check("8 out-of-range position is invalid", is_valid_position(3, candidates) is False)
    check("9 non-integer string position is invalid", is_valid_position("1", candidates) is False)
    check("10 None position is invalid", is_valid_position(None, candidates) is False)
    check("11 float position is invalid, must be an exact int", is_valid_position(1.0, candidates) is False)
    check("12 empty candidate list makes every position invalid", is_valid_position(0, []) is False)

    print(f"passed: {PASSED}/{PASSED + len(FAILED)}")
    if FAILED:
        print("failed cases:")
        for name in FAILED:
            print(f"  - {name}")


if __name__ == "__main__":
    run()
