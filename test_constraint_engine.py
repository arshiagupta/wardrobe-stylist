"""
Phase 2 eval: 10-15 constraint test cases, pure code, zero AI cost.
Run: python test_constraint_engine.py
Each case is a plain assert; failures print which case broke and why.
"""
from constraint_engine import filter_wardrobe, load_wardrobe, load_profile

PASSED = 0
FAILED = []


def item(**overrides):
    base = {
        "display_name": "test item", "category": "top", "subcategory": "blouse",
        "article_type": "blouse", "colour_primary": "blue", "colour_secondary": None,
        "formality": "casual", "season": "all season", "gender": "womenswear",
        "pattern": "solid", "style_tags": [], "needs_review": False,
    }
    base.update(overrides)
    return base


def check(name, condition):
    global PASSED
    if condition:
        PASSED += 1
    else:
        FAILED.append(name)


def run():
    empty_profile = {"blocked_categories": [], "blocked_article_types": [],
                      "blocked_colours": [], "blocked_patterns": [],
                      "blocked_style_tags": [], "exclude_needs_review": False}

    # 1. exact-blocked category excludes the item
    profile = {**empty_profile, "blocked_categories": ["footwear"]}
    items = [item(category="footwear", display_name="sneakers")]
    passing, excluded = filter_wardrobe(items, profile)
    check("1 blocked_category excludes", len(passing) == 0 and len(excluded) == 1)

    # 2. category blocker does not touch a different category
    profile = {**empty_profile, "blocked_categories": ["footwear"]}
    items = [item(category="top")]
    passing, excluded = filter_wardrobe(items, profile)
    check("2 blocked_category leaves others alone", len(passing) == 1)

    # 3. article_type blocker matches by substring ("crop top" catches a variant)
    profile = {**empty_profile, "blocked_article_types": ["crop top"]}
    items = [item(article_type="cropped crop top", display_name="crop top")]
    passing, excluded = filter_wardrobe(items, profile)
    check("3 blocked_article_type substring match", len(excluded) == 1
          and "blocked_article_type:crop top" in excluded[0]["reasons"])

    # 4. article_type blocker does not exclude an unrelated item
    profile = {**empty_profile, "blocked_article_types": ["crop top"]}
    items = [item(article_type="straight-leg jeans")]
    passing, excluded = filter_wardrobe(items, profile)
    check("4 blocked_article_type leaves others alone", len(passing) == 1)

    # 5. article_type blocker also checks subcategory
    profile = {**empty_profile, "blocked_article_types": ["crop top"]}
    items = [item(article_type="sleeveless top", subcategory="crop top")]
    passing, excluded = filter_wardrobe(items, profile)
    check("5 blocker checks subcategory too", len(excluded) == 1)

    # 6. colour blocker on primary colour
    profile = {**empty_profile, "blocked_colours": ["red"]}
    items = [item(colour_primary="red")]
    passing, excluded = filter_wardrobe(items, profile)
    check("6 blocked_colour on primary", len(excluded) == 1)

    # 7. colour blocker on secondary colour too
    profile = {**empty_profile, "blocked_colours": ["red"]}
    items = [item(colour_primary="white", colour_secondary="red")]
    passing, excluded = filter_wardrobe(items, profile)
    check("7 blocked_colour on secondary", len(excluded) == 1)

    # 8. pattern blocker
    profile = {**empty_profile, "blocked_patterns": ["floral"]}
    items = [item(pattern="floral")]
    passing, excluded = filter_wardrobe(items, profile)
    check("8 blocked_pattern excludes", len(excluded) == 1)

    # 9. style_tag blocker
    profile = {**empty_profile, "blocked_style_tags": ["clubwear"]}
    items = [item(style_tags=["clubwear", "edgy"])]
    passing, excluded = filter_wardrobe(items, profile)
    check("9 blocked_style_tag excludes", len(excluded) == 1)

    # 10. needs_review excluded when exclude_needs_review is True
    profile = {**empty_profile, "exclude_needs_review": True}
    items = [item(needs_review=True)]
    passing, excluded = filter_wardrobe(items, profile)
    check("10 needs_review excluded when flag True", len(passing) == 0)

    # 11. needs_review kept when exclude_needs_review is False
    profile = {**empty_profile, "exclude_needs_review": False}
    items = [item(needs_review=True)]
    passing, excluded = filter_wardrobe(items, profile)
    check("11 needs_review kept when flag False", len(passing) == 1)

    # 12. an item failing two different blockers still gets both reasons, once
    profile = {**empty_profile, "blocked_categories": ["footwear"], "blocked_colours": ["grey"]}
    items = [item(category="footwear", colour_primary="grey")]
    passing, excluded = filter_wardrobe(items, profile)
    check("12 multiple reasons captured on one item",
          len(excluded) == 1 and len(excluded[0]["reasons"]) == 2)

    # 13. empty profile passes a normal item through unchanged
    items = [item()]
    passing, excluded = filter_wardrobe(items, empty_profile)
    check("13 empty profile passes normal item", len(passing) == 1 and len(excluded) == 0)

    # 14. request formality filter excludes a mismatched item
    items = [item(formality="casual")]
    passing, excluded = filter_wardrobe(items, empty_profile, request={"formality": "formal"})
    check("14 request formality mismatch excludes", len(passing) == 0)

    # 15. request season filter treats "all season" items as always matching
    items = [item(season="all season")]
    passing, excluded = filter_wardrobe(items, empty_profile, request={"season": "winter"})
    check("15 all-season item matches any requested season", len(passing) == 1)

    # 16. avoid_terms (7B): free-text avoid matches by substring and excludes
    profile = {**empty_profile, "avoid_terms": ["crop top"]}
    items = [item(display_name="black crop top", article_type="crop top")]
    passing, excluded = filter_wardrobe(items, profile)
    check("16 avoid_terms matches and excludes",
          len(excluded) == 1 and "avoid:crop top" in excluded[0]["reasons"])

    # 17. avoid_terms matches a colour word, leaves unrelated items alone
    profile = {**empty_profile, "avoid_terms": ["neon"]}
    keep = item(colour_primary="blue", display_name="blue jeans")
    drop = item(colour_primary="neon green", display_name="neon top")
    passing, excluded = filter_wardrobe([keep, drop], profile)
    check("17 avoid_terms colour match, others pass", len(passing) == 1 and len(excluded) == 1)

    # 18. avoid_terms matches inside style_tags
    profile = {**empty_profile, "avoid_terms": ["boho"]}
    items = [item(style_tags=["boho", "relaxed"])]
    passing, excluded = filter_wardrobe(items, profile)
    check("18 avoid_terms matches a style tag", len(excluded) == 1)

    # 19. no avoid_terms (missing key) changes nothing
    items = [item()]
    passing, excluded = filter_wardrobe(items, empty_profile)
    check("19 no avoid_terms leaves item alone", len(passing) == 1)

    # 20. integration check: the real extracted wardrobe plus the real profile.json
    # actually runs against Phase 1's real output
    real_items = load_wardrobe()
    real_profile = load_profile()
    passing, excluded = filter_wardrobe(real_items, real_profile)
    crop_top_hits = [e for e in excluded
                     if any(r.startswith("blocked_article_type") for r in e["reasons"])]
    check("20 real wardrobe.json loads and runs without error", len(real_items) > 0)
    print(f"    (info) real wardrobe: {len(passing)} pass, {len(excluded)} excluded, "
          f"{len(crop_top_hits)} caught by the crop-top blocker")

    print(f"\n{PASSED}/{PASSED + len(FAILED)} passed")
    if FAILED:
        print("FAILED:")
        for name in FAILED:
            print(f"  - {name}")
        raise SystemExit(1)


if __name__ == "__main__":
    run()
