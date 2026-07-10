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

Static files (public/index.html, public/photos/*.svg) are NOT served
by this Flask app in production and never should be: confirmed by
directly logging the deployed function's own filesystem (session 6)
that Vercel does not bundle public/ into the function at all, it is a
reserved, CDN-only directory regardless of the general "Python
functions include everything" default. vercel.json's rewrite is
scoped to "/api/(.*)" only, so "/" and "/photos/*" fall through to
Vercel's native static hosting instead of reaching this function. The
route and static_folder config below exist purely so `python
api/index.py` still serves the full page for local testing; in
production they are simply never reached, which is fine.
"""
import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from flask import Flask, request, jsonify

import gap_fill

app = Flask(__name__, static_folder=os.path.join(PROJECT_ROOT, "public"), static_url_path="")


@app.route("/", methods=["GET"])
def index():
    return app.send_static_file("index.html")


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

    try:
        outcome = gap_fill.fill_gaps_for_request(occasion, vibe, budget, season)
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
        items = [
            {
                "id": iid,
                "display_name": items_by_id[iid]["display_name"],
                "image": f"/photos/{iid}.svg",
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
