"""
Phase 5: thin web API wrapping the existing backend logic
=============================================================
One Flask app, one real route: POST /api/style. Wraps
gap_fill.fill_gaps_for_request, which itself wraps recommender.py (the
ranking AI call), shopping_search.py (Serper + deterministic filters)
and constraint_engine.py (hard filtering). No new business logic lives
here, this file only translates HTTP into the existing Python
functions and back.

Lives at api/index.py, not the project root: Vercel's own official
Flask example uses this exact structure. `app` must be a genuine
top-level assignment, not defined inside an if/else: Vercel's Flask
detector does a static scan for exactly that and fails the build
otherwise (found by deploying, session 6).

Since this file lives in api/, not the project root, its sibling
modules (gap_fill, recommender, constraint_engine, shopping_search)
are not automatically importable, Vercel does not add the project
root to sys.path for you. Added explicitly below, a documented
workaround for this exact situation.

Static files live in webapp/, not public/: confirmed by directly
logging the deployed function's own filesystem (session 6) that
Vercel never bundles a directory literally named public/ into a
function, it is treated as reserved, CDN-only, regardless of the
general "Python functions include everything" default. Naming it
anything else means it bundles normally like every other project
file, and this Flask app can serve it directly through the blanket
rewrite in vercel.json ("/(.*)" -> /api/index), the same way it
already correctly reads wardrobe/wardrobe.json.
"""
import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from flask import Flask, request, jsonify

import gap_fill
import extract_wardrobe

# Upload guardrail: the frontend downscales each photo to ~1024px JPEG (~200KB)
# before sending, so a real upload is well under this. The ceiling is a spam
# backstop, not the normal size. Vercel also caps request bodies independently.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_MIME = {"image/jpeg", "image/png", "image/webp"}

app = Flask(__name__, static_folder=os.path.join(PROJECT_ROOT, "webapp"), static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


@app.route("/", methods=["GET"])
def index():
    return app.send_static_file("index.html")


@app.route("/api/extract", methods=["POST"])
def extract():
    """Multi-user upload: one clothing photo in, a LIST of wardrobe items out
    (a worn photo showing a top + skirt + shoes becomes several items). The
    result is returned to the caller's browser and stored there in localStorage,
    never written to any server file. Cost is metered once per photo, regardless
    of how many items came out, so the page can show a running total."""
    f = request.files.get("photo")
    if f is None:
        return jsonify({"error": "no photo uploaded (expected form field 'photo')"}), 400

    mime = (f.mimetype or "").lower()
    if mime not in ALLOWED_UPLOAD_MIME:
        return jsonify({"error": f"unsupported image type {mime or 'unknown'!r}; "
                                 f"use JPEG, PNG or WebP"}), 400

    img_bytes = f.read()
    if not img_bytes:
        return jsonify({"error": "uploaded file was empty"}), 400

    try:
        items, cost, in_tok, out_tok = extract_wardrobe.extract_items_from_bytes(
            img_bytes, mime, filename=(f.filename or "upload"))
    except RuntimeError as e:
        # missing SDK or API key: a config problem, not the user's fault
        return jsonify({"error": str(e)}), 500
    except Exception as e:  # noqa: BLE001 - never leak a bare 500 with no message
        traceback.print_exc()
        return jsonify({"error": f"extraction failed: {e}"}), 500

    return jsonify({
        "items": items,
        "cost_usd": round(cost, 6),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
    })


@app.route("/api/style", methods=["POST"])
def style():
    body = request.get_json(silent=True) or {}
    occasion = (body.get("occasion") or "").strip()
    if not occasion:
        return jsonify({"error": "occasion is required"}), 400

    vibe = body.get("vibe") or ""
    season = body.get("season") or None
    budget_raw = body.get("budget")
    try:
        budget = float(budget_raw) if budget_raw not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "budget must be a number"}), 400

    # Multi-user (7A): the wardrobe comes from the caller's own browser
    # (localStorage), never from a server file. An empty or missing wardrobe is
    # valid, it just means the visitor has not uploaded any clothes yet, and the
    # pipeline safely returns no outfits without making any AI call.
    wardrobe = body.get("wardrobe")
    if wardrobe is None:
        wardrobe = []
    if not isinstance(wardrobe, list):
        return jsonify({"error": "wardrobe must be a list of items"}), 400

    # Profile (7B) comes from the caller's browser too. None is fine (falls back to
    # the neutral server profile). Gender in it never filters the user's own items,
    # it only steers new-buy searches and styling language.
    profile = body.get("profile")
    if profile is not None and not isinstance(profile, dict):
        return jsonify({"error": "profile must be an object"}), 400

    # "Style this item" mode (7C): an optional wardrobe item id to build every
    # outfit around.
    anchor_id = body.get("anchor_id")
    if anchor_id is not None and not isinstance(anchor_id, str):
        return jsonify({"error": "anchor_id must be a string"}), 400

    try:
        outcome = gap_fill.fill_gaps_for_request(
            occasion, vibe, budget, season, wardrobe=wardrobe, profile=profile, anchor_id=anchor_id)
    except SystemExit as e:
        # get_outfits()/fill_gaps_for_request() call sys.exit on a missing API
        # key. Translate that into a proper error response, not a hard crash.
        return jsonify({"error": str(e)}), 500
    except Exception as e:  # noqa: BLE001 - never leak a bare 500 with no message
        traceback.print_exc()
        return jsonify({"error": f"unexpected error: {e}"}), 500

    items_by_id = outcome["items_by_id"]
    response = {
        "formality": outcome["formality"],
        "wardrobe_count": outcome["wardrobe_count"],
        "passing_count": outcome["passing_count"],
        "structural_gaps": outcome["structural_gaps"],
        "outfits": [],
        "ranking_cost_usd": round(outcome["cost"], 5),
        "gap_fill_cost_usd": round(outcome["gap_fill_total_cost"], 5),
        "total_cost_usd": round(outcome["cost"] + outcome["gap_fill_total_cost"], 5),
        "live_searches_used": outcome["live_searches_used"],
    }
    for outfit in outcome["outfits"]:
        # No server-side image path: the visitor's own photo thumbnails live in
        # their browser, keyed by item id. The frontend renders them from there,
        # so the server never stores or serves anyone's clothing photos.
        items = [
            {
                "id": iid,
                "display_name": items_by_id[iid]["display_name"],
                "needs_review": items_by_id[iid].get("needs_review", False),
            }
            for iid in outfit["item_ids"] if iid in items_by_id
        ]
        response["outfits"].append({
            "rank": outfit.get("rank"),
            "items": items,
            "reason": outfit.get("reason"),
            "gap_fills": outfit.get("gap_fills", []),
        })

    return jsonify(response)


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)), debug=True)
