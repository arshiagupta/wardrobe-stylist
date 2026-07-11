"""
Phase 5: placeholder images for the public deploy
=====================================================
Builder's choice (session 6): no real wardrobe photos in a public
GitHub repo, since they are photos of the builder's actual belongings,
not something to publish just because the code is public. This
generates one simple SVG per wardrobe item instead: a flat colour card
(from colour_primary) labelled with category and display name, clearly
marked as a placeholder so nobody mistakes it for a real product
photo. Real photos stay in wardrobe/photos/, local-only, gitignored.

Run once, or again whenever wardrobe.json changes (safe to rerun, it
always overwrites all placeholders from the current wardrobe.json).

Run: python generate_placeholders.py
"""
import json
import os

WARDROBE_PATH = os.path.join("wardrobe", "wardrobe.json")
OUT_DIR = os.path.join("webapp", "photos")

COLOUR_HEX = {
    "cream": "#F0E6D2", "red": "#B03A3A", "blue": "#3B5A8A", "pink": "#D98CA0",
    "black": "#1C1C1C", "white": "#F2F2F2", "brown": "#6B4A32", "grey": "#8C8C8C",
    "gray": "#8C8C8C", "green": "#4A7A5A", "yellow": "#D9C24A", "orange": "#C97A3A",
    "purple": "#7A5A9A", "navy": "#22304A", "beige": "#D8C9AE", "gold": "#B8963C",
    "silver": "#B9B9B9",
}
DARK_TEXT_ON = {"cream", "white", "yellow", "beige", "silver", "grey", "gray"}
DEFAULT_HEX = "#9A9A9A"


def text_colour_for(colour_name):
    return "#1C1C1C" if colour_name in DARK_TEXT_ON else "#F5F5F5"


def wrap_text(text, max_chars=18):
    words = text.split()
    lines, current = [], ""
    for w in words:
        candidate = (current + " " + w).strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = w
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def escape_xml(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def make_svg(item):
    colour_name = (item.get("colour_primary") or "").lower()
    bg = COLOUR_HEX.get(colour_name, DEFAULT_HEX)
    fg = text_colour_for(colour_name)
    category = (item.get("category") or "item").upper()
    lines = wrap_text(item.get("display_name") or item["id"])
    tspans = "".join(
        f'<tspan x="150" dy="{0 if i == 0 else 26}">{escape_xml(line)}</tspan>'
        for i, line in enumerate(lines)
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 400">
  <rect width="300" height="400" fill="{bg}"/>
  <text x="150" y="40" text-anchor="middle" font-family="sans-serif" font-size="14"
        letter-spacing="2" fill="{fg}" opacity="0.85">{category}</text>
  <text x="150" y="200" text-anchor="middle" font-family="sans-serif" font-size="18"
        fill="{fg}">{tspans}</text>
  <text x="150" y="380" text-anchor="middle" font-family="sans-serif" font-size="11"
        fill="{fg}" opacity="0.6">(placeholder image, not the real photo)</text>
</svg>"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(WARDROBE_PATH, "r", encoding="utf-8") as f:
        wardrobe = json.load(f)["items"]

    for item in wardrobe:
        svg = make_svg(item)
        out_path = os.path.join(OUT_DIR, f"{item['id']}.svg")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(svg)

    print(f"generated {len(wardrobe)} placeholder images in {OUT_DIR}")


if __name__ == "__main__":
    main()
