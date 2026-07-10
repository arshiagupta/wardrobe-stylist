"""
Phase 5: thin web API wrapping the existing backend logic
=============================================================
One Flask app, one real route: POST /api/style. Wraps
gap_fill.fill_gaps_for_request, which itself wraps recommender.py (the
ranking AI call), shopping_search.py (Serper + deterministic filters)
and constraint_engine.py (hard filtering). No new business logic lives
here, this file only translates HTTP into the existing Python
functions and back.

Static files (the page itself, wardrobe photos) are served by Vercel's
CDN from the public/ directory in production, not by Flask (Vercel's
own guidance: do not use Flask's static_folder in production). In
production those requests never reach this Flask app at all, so
static_folder being set here is inert there, it only matters for the
local-dev-only "/" route below, gated on the VERCEL env var Vercel
sets automatically so it never registers in production.

`app` must be a genuine top-level assignment, not defined inside an
if/else: Vercel's Flask detector does a static scan for exactly that
and fails the build otherwise (found the hard way, session 6).
"""
import os
import traceback

from flask import Flask, request, jsonify

import gap_fill

app = Flask(__name__, static_folder="public", static_url_path="")

if not os.environ.get("VERCEL"):
    @app.route("/")
    def _local_index():
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
