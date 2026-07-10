"""
Phase 1: wardrobe vision extraction
====================================
What this does: reads clothing photos from ./wardrobe/photos, sends each NEW photo
once to a Gemini vision model, gets back structured tier 1 + tier 2 attributes,
validates them in code and caches everything to ./wardrobe/wardrobe.json.
Already-processed photos (matched by file content hash) are never re-billed.

How to run
----------
1. pip install google-genai
2. Get an API key at https://aistudio.google.com (Get API key). Then:
      Mac/Linux:   export GEMINI_API_KEY="your-key-here"
      Windows PS:  $env:GEMINI_API_KEY="your-key-here"
3. Create folder ./wardrobe/photos and drop 5-10 clothing photos in it
   (jpg, png, webp, heic all fine, one dominant garment per photo works best).
4. python extract_wardrobe.py
5. Paste the full terminal output back into the chat.

Guardrails (edit at top of file if needed)
------------------------------------------
MAX_ITEMS_PER_RUN caps how many NEW photos get billed in one run.
COST_CAP_USD stops the run if estimated spend for this run exceeds the cap.
Prices below are a meter, not a promise. Verify current rates at
https://ai.google.dev/gemini-api/docs/pricing and update the two constants.
"""

import hashlib
import json
import os
import sys
import time
import uuid

# ---------------- configuration ----------------
MODEL = "gemini-3.1-flash-lite"     # verified working against this key, session 5
PRICE_PER_M_INPUT = 0.25            # USD per 1M input tokens, ai.google.dev/gemini-api/docs/pricing
PRICE_PER_M_OUTPUT = 1.50           # USD per 1M output tokens, ai.google.dev/gemini-api/docs/pricing
MAX_ITEMS_PER_RUN = 10              # hard cap on new photos billed per run
COST_CAP_USD = 2.00                 # hard cap on estimated spend per run
SLEEP_BETWEEN_CALLS = 5             # seconds, stays under free-tier rate limits
MAX_RETRIES = 3

PHOTO_DIR = os.path.join("wardrobe", "photos")
CACHE_PATH = os.path.join("wardrobe", "wardrobe.json")

MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
}

# ---------------- allowed values (deterministic validation) ----------------
CATEGORIES = {"top", "bottom", "dress", "outerwear", "footwear", "accessory"}
FORMALITY = {"casual", "smart casual", "business", "formal"}
SEASONS = {"summer", "winter", "all season", "transitional"}
GENDERS = {"womenswear", "menswear", "unisex"}
PATTERNS = {"solid", "striped", "floral", "check", "graphic", "colour block", "other"}
FITS = {"slim", "regular", "relaxed", "oversized"}

PROMPT = """You are a fashion attribute extractor. Look at this single clothing item photo.
Return ONLY a JSON object, no markdown fences, with exactly these keys:

{
  "display_name": "short human label, e.g. 'navy straight-leg jeans'",
  "category": "one of: top, bottom, dress, outerwear, footwear, accessory",
  "subcategory": "short free text, e.g. 'jeans', 'midi skirt', 'trainers'",
  "article_type": "specific type, e.g. 'straight-leg jeans', 'wrap dress'",
  "colour_primary": "one lowercase basic colour word",
  "colour_secondary": "second colour or null",
  "formality": "one of: casual, smart casual, business, formal",
  "season": "one of: summer, winter, all season, transitional",
  "gender": "one of: womenswear, menswear, unisex",
  "pattern": "one of: solid, striped, floral, check, graphic, colour block, other, or null if unclear",
  "fit": "one of: slim, regular, relaxed, oversized, or null if unclear",
  "material": "best visual guess e.g. 'denim', 'knit', 'leather', or null",
  "length_attributes": {"sleeve": "e.g. long/short/sleeveless or null",
                        "hem": "e.g. mini/midi/maxi/ankle/cropped or null",
                        "rise": "e.g. high/mid/low or null"},
  "style_tags": ["up to 5 lowercase tags, e.g. 'minimal', 'boho', 'workwear'"],
  "multiple_items_detected": false
}

If the photo shows more than one garment, describe the dominant one and set
multiple_items_detected to true. If a field cannot be judged from the photo, use null.
Do not invent attributes you cannot see."""


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"items": [], "run_log": []}


def save_cache(cache):
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def coerce_enum(value, allowed):
    """Deterministic guard: model output outside the allowed set becomes null."""
    if isinstance(value, str) and value.strip().lower() in allowed:
        return value.strip().lower()
    return None


def validate(raw, filename, file_hash):
    """Enforce the shared schema in code. Anything off-spec is nulled and flagged."""
    needs_review = False
    la = raw.get("length_attributes") or {}
    if not isinstance(la, dict):
        la = {}

    item = {
        "id": "w_" + file_hash[:10],
        "source": "wardrobe",
        "image_ref": filename,
        "file_hash": file_hash,
        "display_name": raw.get("display_name") or filename,
        "category": coerce_enum(raw.get("category"), CATEGORIES),
        "subcategory": raw.get("subcategory"),
        "article_type": raw.get("article_type"),
        "colour_primary": (raw.get("colour_primary") or "").strip().lower() or None,
        "colour_secondary": raw.get("colour_secondary"),
        "formality": coerce_enum(raw.get("formality"), FORMALITY),
        "season": coerce_enum(raw.get("season"), SEASONS),
        "gender": coerce_enum(raw.get("gender"), GENDERS),
        "price": None,
        "currency": None,
        "price_method": None,
        "pattern": coerce_enum(raw.get("pattern"), PATTERNS),
        "fit": coerce_enum(raw.get("fit"), FITS),
        "material": raw.get("material"),
        "length_attributes": {
            "sleeve": la.get("sleeve"),
            "hem": la.get("hem"),
            "rise": la.get("rise"),
        },
        "style_tags": [t.lower() for t in (raw.get("style_tags") or [])
                       if isinstance(t, str)][:5],
        "multiple_items_detected": bool(raw.get("multiple_items_detected", False)),
    }

    # tier 1 fields that constraints may reference must be populated
    for field in ("category", "colour_primary", "formality", "season", "gender"):
        if item[field] is None:
            needs_review = True
    if item["multiple_items_detected"]:
        needs_review = True
    item["needs_review"] = needs_review
    return item


def call_vision(client, types_mod, img_bytes, mime):
    from google.genai import errors

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=[types_mod.Part.from_bytes(data=img_bytes, mime_type=mime),
                          PROMPT],
                config=types_mod.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            return resp
        except errors.APIError as e:
            # 4xx other than 429 is permanent (e.g. 404 model not found),
            # retrying just re-bills the same guaranteed failure.
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
    raise RuntimeError(f"vision call failed after {MAX_RETRIES} attempts: {last_err}")


def main():
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        sys.exit("Missing dependency. Run: pip install google-genai")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY is not set. See the instructions at the top of this file.")

    if not os.path.isdir(PHOTO_DIR):
        os.makedirs(PHOTO_DIR, exist_ok=True)
        sys.exit(f"Created {PHOTO_DIR}. Drop your clothing photos in it and rerun.")

    client = genai.Client(api_key=api_key)
    cache = load_cache()
    known_hashes = {it["file_hash"] for it in cache["items"]}

    photos = sorted(
        f for f in os.listdir(PHOTO_DIR)
        if os.path.splitext(f)[1].lower() in MIME_MAP
    )
    if not photos:
        sys.exit(f"No supported photos found in {PHOTO_DIR}.")

    run_cost = 0.0
    run_in_tokens = 0
    run_out_tokens = 0
    processed = 0
    skipped = 0
    failed = []

    print(f"Model: {MODEL} | cap: {MAX_ITEMS_PER_RUN} items / ${COST_CAP_USD:.2f}\n")

    for filename in photos:
        path = os.path.join(PHOTO_DIR, filename)
        file_hash = sha256_file(path)
        if file_hash in known_hashes:
            skipped += 1
            continue
        if processed >= MAX_ITEMS_PER_RUN:
            print(f"\nItem cap of {MAX_ITEMS_PER_RUN} reached, stopping. Rerun to continue.")
            break
        if run_cost >= COST_CAP_USD:
            print(f"\nCost cap of ${COST_CAP_USD:.2f} reached, stopping. Rerun to continue.")
            break

        print(f"[{processed + 1}] {filename}")
        with open(path, "rb") as f:
            img_bytes = f.read()
        mime = MIME_MAP[os.path.splitext(filename)[1].lower()]

        try:
            resp = call_vision(client, types, img_bytes, mime)
            text = (resp.text or "").strip()
            if text.startswith("```"):
                text = text.strip("`").removeprefix("json").strip()
            raw = json.loads(text)
        except Exception as e:  # noqa: BLE001
            print(f"    FAILED: {e}")
            failed.append(filename)
            continue

        usage = getattr(resp, "usage_metadata", None)
        in_tok = getattr(usage, "prompt_token_count", 0) or 0
        out_tok = getattr(usage, "candidates_token_count", 0) or 0
        item_cost = (in_tok / 1e6) * PRICE_PER_M_INPUT + (out_tok / 1e6) * PRICE_PER_M_OUTPUT

        item = validate(raw, filename, file_hash)
        item["extraction_meta"] = {
            "model": MODEL, "input_tokens": in_tok, "output_tokens": out_tok,
            "est_cost_usd": round(item_cost, 6),
        }
        cache["items"].append(item)
        known_hashes.add(file_hash)
        save_cache(cache)  # crash-safe, saved after every item

        run_cost += item_cost
        run_in_tokens += in_tok
        run_out_tokens += out_tok
        processed += 1
        flag = "  [needs review]" if item["needs_review"] else ""
        print(f"    -> {item['display_name']} | {item['category']} | "
              f"{item['colour_primary']} | ${item_cost:.5f}{flag}")
        time.sleep(SLEEP_BETWEEN_CALLS)

    cache["run_log"].append({
        "run_id": str(uuid.uuid4())[:8],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": MODEL,
        "items_processed": processed,
        "items_skipped_cached": skipped,
        "items_failed": failed,
        "input_tokens": run_in_tokens,
        "output_tokens": run_out_tokens,
        "est_run_cost_usd": round(run_cost, 6),
    })
    save_cache(cache)

    total_items = len(cache["items"])
    print("\n================ run summary ================")
    print(f"new items extracted : {processed}")
    print(f"cached items skipped: {skipped}")
    print(f"failures            : {len(failed)} {failed if failed else ''}")
    print(f"tokens in/out       : {run_in_tokens} / {run_out_tokens}")
    print(f"est run cost        : ${run_cost:.5f}")
    if processed:
        print(f"est cost per item   : ${run_cost / processed:.5f}")
    print(f"total items in wardrobe.json: {total_items}")
    needs = [i["display_name"] for i in cache["items"] if i.get("needs_review")]
    if needs:
        print(f"items needing manual review: {needs}")
    print("\nFirst extracted item for verification:")
    if cache["items"]:
        print(json.dumps(cache["items"][0], indent=2, ensure_ascii=False))
    print("\nPaste this entire terminal output back into the chat.")


if __name__ == "__main__":
    main()
