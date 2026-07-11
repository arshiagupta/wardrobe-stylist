"""
Phase 3 eval: deterministic pieces only, pure code, zero AI cost.
The AI ranking/wording itself is not unit-tested here, there is nothing
deterministic to assert about prose. What IS tested: occasion -> formality
mapping, gap detection, and the hallucinated-id guard, since those are the
parts the architecture requires to stay deterministic, not model-trusted.
Run: python test_recommender.py
"""
from recommender import map_occasion_to_formality, bucket_items, detect_gaps, validate_outfit_ids

PASSED = 0
FAILED = []


def check(name, condition):
    global PASSED
    if condition:
        PASSED += 1
    else:
        FAILED.append(name)


def item(category, **overrides):
    base = {"id": "w_test", "display_name": "test item", "category": category}
    base.update(overrides)
    return base


def run():
    # --- occasion -> formality mapping ---
    check("1 'work dinner' maps to smart casual",
          map_occasion_to_formality("work dinner") == "smart casual")
    check("2 'black tie gala' maps to formal",
          map_occasion_to_formality("black tie gala") == "formal")
    check("3 'job interview' maps to business",
          map_occasion_to_formality("job interview") == "business")
    check("4 'weekend hangout' maps to casual",
          map_occasion_to_formality("weekend hangout") == "casual")
    check("5 unmapped phrase returns None (no silent guess)",
          map_occasion_to_formality("cousin's mehndi") is None)
    check("6 mapping is case-insensitive",
          map_occasion_to_formality("WORK Dinner") == "smart casual")
    check("7 empty string returns None",
          map_occasion_to_formality("") is None)
    check("7b 'formal wear' maps to formal (session 7 fix)",
          map_occasion_to_formality("formal wear") == "formal")
    check("7c 'informal gathering' maps to casual, not tricked by the 'formal' substring",
          map_occasion_to_formality("informal gathering") == "casual")
    check("7d 'work meeting' maps to business",
          map_occasion_to_formality("work meeting") == "business")
    check("7e 'cocktail party' maps to formal",
          map_occasion_to_formality("cocktail party") == "formal")

    # --- bucket_items ---
    items = [item("top", id="t1"), item("bottom", id="b1"), item("footwear", id="f1")]
    buckets = bucket_items(items)
    check("8 bucket_items groups by category",
          len(buckets["top"]) == 1 and len(buckets["bottom"]) == 1 and len(buckets["footwear"]) == 1
          and len(buckets["dress"]) == 0)

    # --- detect_gaps ---
    full = bucket_items([item("top"), item("bottom"), item("footwear")])
    check("9 no gaps when top+bottom+footwear all present",
          detect_gaps(full, "casual", "summer") == [])

    dress_only = bucket_items([item("dress"), item("footwear")])
    check("10 dress alone (no top/bottom needed) has no gap",
          detect_gaps(dress_only, "formal", None) == [])

    no_bottom = bucket_items([item("top"), item("footwear")])
    gaps = detect_gaps(no_bottom, "smart casual", None)
    check("11 missing bottom (no dress fallback) is named precisely",
          len(gaps) == 1 and "bottoms" in gaps[0] and "smart casual" in gaps[0])

    no_footwear = bucket_items([item("top"), item("bottom")])
    gaps2 = detect_gaps(no_footwear, "casual", "summer")
    check("12 missing footwear is named precisely",
          any("footwear" in g for g in gaps2))

    nothing = bucket_items([])
    gaps3 = detect_gaps(nothing, "formal", None)
    check("13 empty wardrobe reports both the outfit gap and the footwear gap",
          len(gaps3) == 2)

    # menswear (7C): dresses are never mentioned as a missing item or alternative
    mens = detect_gaps(bucket_items([item("top"), item("footwear")]), "casual", None, gender="menswear")
    check("13b menswear missing bottom names bottoms, never dresses",
          len(mens) == 1 and "bottoms" in mens[0] and "dress" not in mens[0])
    womens = detect_gaps(bucket_items([item("top"), item("footwear")]), "casual", None, gender="womenswear")
    check("13c womenswear still offers the dress alternative wording",
          "dress" in womens[0])

    # --- validate_outfit_ids ---
    outfits = [{"rank": 1, "item_ids": ["w_real1", "w_fake2"], "reason": "x", "gap": None}]
    cleaned = validate_outfit_ids(outfits, valid_ids={"w_real1"})
    check("14 hallucinated id is dropped, not trusted",
          cleaned[0]["item_ids"] == ["w_real1"] and cleaned[0]["dropped_hallucinated_ids"] == ["w_fake2"])

    check("15 no hallucination means no drops recorded",
          validate_outfit_ids(
              [{"rank": 1, "item_ids": ["w_real1"], "reason": "x", "gap": None}],
              valid_ids={"w_real1"},
          )[0]["dropped_hallucinated_ids"] == [])

    print(f"passed: {PASSED}/{PASSED + len(FAILED)}")
    if FAILED:
        print("failed cases:")
        for name in FAILED:
            print(f"  - {name}")


if __name__ == "__main__":
    run()
