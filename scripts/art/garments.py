"""
TridentWear sample product art generator.

Produces branded flat-lay garment SVGs (front + back) for every catalog
colourway, then rasterises them to transparent WebP with headless Chrome
(see render.js). Transparent cut-outs double as virtual try-on overlays.

    python scripts/art/garments.py            # writes SVGs to scripts/art/out/
    node   scripts/art/render.js              # rasterises to frontend/assets/images/products/

Re-run any time the catalog colourways change. Replace with real photography
once you shoot actual products — the frontend only needs the image paths.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
LOGO_SVG = (ROOT / "frontend" / "assets" / "brand" / "logo-mark.svg").read_text()
LOGO_VB = [float(v) for v in re.search(r'viewBox="([^"]+)"', LOGO_SVG).group(1).split()]
LOGO_D = re.search(r' d="([^"]+)"', LOGO_SVG).group(1)

GOLD = "#b8944e"

# ---------------------------------------------------------------- silhouettes
# Every silhouette lives in a 1000 x 1200 box. Points are hand-tuned.
SIL = {
    # drop-shoulder oversized tee
    "tee_oversized": {
        "front": "M412,118 C448,192 552,192 588,118 L772,168 C826,188 878,262 940,428 L806,500 C792,466 772,436 752,404 L764,1018 Q500,1040 236,1018 L248,404 C228,436 208,466 194,500 L60,428 C122,262 174,188 228,168 Z",
        "back": "M412,118 C448,140 552,140 588,118 L772,168 C826,188 878,262 940,428 L806,500 C792,466 772,436 752,404 L764,1018 Q500,1040 236,1018 L248,404 C228,436 208,466 194,500 L60,428 C122,262 174,188 228,168 Z",
        "neck_front": "M412,118 C448,192 552,192 588,118",
        "neck_back": "M412,118 C448,140 552,140 588,118",
        "inner": "M412,118 C448,140 552,140 588,118 C552,128 448,128 412,118 Z",
        "seams": ["M228,168 C238,250 244,330 248,404", "M772,168 C762,250 756,330 752,404",
                  "M74,436 L198,492", "M926,436 L802,492"],
        "hem": "M240,1000 Q500,1022 760,1000",
        "folds": ["M300,520 C360,600 330,720 300,820", "M700,520 C640,620 690,760 700,860",
                  "M250,420 C300,470 330,470 360,450", "M750,420 C700,470 670,470 640,450",
                  "M420,980 C470,940 540,940 590,985"],
        "chest": (640, 330), "logo_w": 70,
        "tryon": {"ls": [0.715, 0.165], "rs": [0.285, 0.165], "hip": [0.5, 0.80]},
    },
    # classic set-in sleeve tee
    "tee_classic": {
        "front": "M420,122 C452,190 548,190 580,122 L716,160 C770,182 832,262 884,382 L776,452 C760,412 738,372 712,336 L716,1012 Q500,1030 284,1012 L288,336 C262,372 240,412 224,452 L116,382 C168,262 230,182 284,160 Z",
        "back": "M420,122 C452,142 548,142 580,122 L716,160 C770,182 832,262 884,382 L776,452 C760,412 738,372 712,336 L716,1012 Q500,1030 284,1012 L288,336 C262,372 240,412 224,452 L116,382 C168,262 230,182 284,160 Z",
        "neck_front": "M420,122 C452,190 548,190 580,122",
        "neck_back": "M420,122 C452,142 548,142 580,122",
        "inner": "M420,122 C452,142 548,142 580,122 C548,131 452,131 420,122 Z",
        "seams": ["M284,160 C276,220 280,290 288,336", "M716,160 C724,220 720,290 712,336",
                  "M130,392 L230,444", "M870,392 L770,444"],
        "hem": "M288,994 Q500,1012 712,994",
        "folds": ["M330,470 C380,560 350,700 330,820", "M670,470 C620,580 660,740 672,860",
                  "M440,975 C480,940 540,940 580,978"],
        "chest": (618, 320), "logo_w": 62,
        "tryon": {"ls": [0.69, 0.14], "rs": [0.31, 0.14], "hip": [0.5, 0.80]},
    },
    # long-sleeve button-down / formal / overshirt
    "shirt_long": {
        "front": "M410,96 L590,96 L742,150 C790,170 820,214 836,280 L928,930 L836,958 L744,420 L736,1052 C700,1080 600,1118 500,1124 C400,1118 300,1080 264,1052 L256,420 L164,958 L72,930 L164,280 C180,214 210,170 258,150 Z",
        "back": "M410,96 L590,96 L742,150 C790,170 820,214 836,280 L928,930 L836,958 L744,420 L736,1052 C700,1080 600,1118 500,1124 C400,1118 300,1080 264,1052 L256,420 L164,958 L72,930 L164,280 C180,214 210,170 258,150 Z",
        "collar": "M410,96 L590,96 L604,150 L566,262 L500,206 L434,262 L396,150 Z",
        "collar_back": "M404,96 L596,96 L606,150 C560,166 440,166 394,150 Z",
        "placket": (500, 206, 1112),
        "buttons": [262, 372, 482, 592, 702, 812, 922, 1032],
        "seams": ["M258,150 C248,240 250,330 256,420", "M742,150 C752,240 750,330 744,420",
                  "M92,900 L176,926", "M908,900 L824,926"],
        "cuffs": ["M72,930 L164,958 L174,890 L88,866 Z", "M928,930 L836,958 L826,890 L912,866 Z"],
        "yoke": "M258,150 C380,196 620,196 742,150",
        "hem": None,
        "folds": ["M330,470 C370,600 350,760 340,900", "M670,470 C630,600 660,760 662,900",
                  "M180,480 C200,620 190,760 160,880", "M820,480 C800,620 810,760 840,880"],
        "pocket": (588, 300, 120, 140),
        "chest": (648, 352), "logo_w": 54,
        "tryon": {"ls": [0.70, 0.13], "rs": [0.30, 0.13], "hip": [0.5, 0.78]},
    },
    # short-sleeve camp-collar shirt
    "shirt_camp": {
        "front": "M404,104 L596,104 L736,150 C790,170 840,240 886,380 L780,446 C764,410 744,380 722,350 L726,1020 L274,1020 L278,350 C256,380 236,410 220,446 L114,380 C160,240 210,170 264,150 Z",
        "back": "M404,104 L596,104 L736,150 C790,170 840,240 886,380 L780,446 C764,410 744,380 722,350 L726,1020 L274,1020 L278,350 C256,380 236,410 220,446 L114,380 C160,240 210,170 264,150 Z",
        "collar": "M404,104 L596,104 L640,184 L560,300 L500,320 L440,300 L360,184 Z",
        "collar_back": "M400,104 L600,104 L610,152 C560,168 440,168 390,152 Z",
        "placket": (500, 320, 1012),
        "buttons": [372, 482, 592, 702, 812, 922],
        "seams": ["M264,150 C258,230 266,300 278,350", "M736,150 C742,230 734,300 722,350",
                  "M128,390 L226,438", "M872,390 L774,438"],
        "cuffs": [],
        "yoke": "M264,150 C390,190 610,190 736,150",
        "hem": "M280,1004 L720,1004",
        "folds": ["M340,480 C380,600 360,760 350,900", "M660,480 C620,600 650,760 652,900"],
        "pocket": (590, 340, 116, 130),
        "chest": (648, 392), "logo_w": 52,
        "tryon": {"ls": [0.72, 0.14], "rs": [0.28, 0.14], "hip": [0.5, 0.80]},
    },
}


def shade(hex_color: str, amt: float) -> str:
    """Lighten (amt>0) or darken (amt<0) a hex colour."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    if amt >= 0:
        r, g, b = (int(c + (255 - c) * amt) for c in (r, g, b))
    else:
        r, g, b = (int(c * (1 + amt)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def logo(x: float, y: float, w: float, color: str, opacity: float = 1.0) -> str:
    s = w / LOGO_VB[2]
    return (f'<g transform="translate({x - w / 2:.1f},{y - LOGO_VB[3] * s / 2:.1f}) scale({s:.4f})" '
            f'opacity="{opacity}"><path fill="{color}" d="{LOGO_D}"/></g>')


def wordmark(x, y, size, color, text="TRIDENTWEAR", spacing=6, weight=800):
    return (f'<text x="{x}" y="{y}" text-anchor="middle" font-family="Archivo, Inter, Arial, sans-serif" '
            f'font-weight="{weight}" font-size="{size}" letter-spacing="{spacing}" fill="{color}">{text}</text>')


def garment_svg(sil_key: str, base: str, view: str, graphic: str | None, accent: str) -> str:
    s = SIL[sil_key]
    body = s[view]
    dark = luminance(base) < 0.35
    hi, lo = shade(base, 0.10), shade(base, -0.18)
    seam = shade(base, -0.28 if not dark else 0.12)
    fold_col = "#000" if not dark else "#000"
    fold_op = 0.07 if not dark else 0.16
    stitch = shade(base, -0.35) if not dark else shade(base, 0.22)
    parts = []
    parts.append(f'''<defs>
  <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{hi}"/><stop offset=".55" stop-color="{base}"/><stop offset="1" stop-color="{lo}"/>
  </linearGradient>
  <radialGradient id="light" cx=".38" cy=".28" r=".75">
    <stop offset="0" stop-color="#fff" stop-opacity="{0.16 if dark else 0.22}"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
  </radialGradient>
  <filter id="blur" filterUnits="userSpaceOnUse" x="0" y="0" width="1000" height="1200"><feGaussianBlur stdDeviation="14"/></filter>
  <filter id="soft" filterUnits="userSpaceOnUse" x="0" y="0" width="1000" height="1200"><feGaussianBlur stdDeviation="3"/></filter>
  <filter id="grain" x="0" y="0" width="100%" height="100%">
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" result="n"/>
    <feColorMatrix type="saturate" values="0"/>
    <feComponentTransfer><feFuncA type="table" tableValues="0 {0.10 if dark else 0.07}"/></feComponentTransfer>
  </filter>
  <clipPath id="clip"><path d="{body}"/></clipPath>
</defs>''')
    parts.append(f'<path d="{body}" fill="url(#g)"/>')
    parts.append('<g clip-path="url(#clip)">')
    parts.append('<rect width="1000" height="1200" fill="url(#light)"/>')
    for f in s["folds"]:
        parts.append(f'<path d="{f}" stroke="{fold_col}" stroke-opacity="{fold_op}" stroke-width="60" fill="none" filter="url(#blur)" stroke-linecap="round"/>')
        parts.append(f'<path d="{f}" stroke="#fff" stroke-opacity="{0.06 if dark else 0.18}" stroke-width="10" fill="none" filter="url(#blur)" transform="translate(16,0)" stroke-linecap="round"/>')
    for sm in s["seams"]:
        parts.append(f'<path d="{sm}" stroke="{seam}" stroke-width="3" fill="none" opacity=".8"/>')
        parts.append(f'<path d="{sm}" stroke="{stitch}" stroke-width="1.6" stroke-dasharray="6 6" fill="none" transform="translate(7,2)" opacity=".7"/>')
    if s.get("hem"):
        parts.append(f'<path d="{s["hem"]}" stroke="{stitch}" stroke-width="2" stroke-dasharray="7 6" fill="none" opacity=".75"/>')
        parts.append(f'<path d="{s["hem"]}" stroke="{stitch}" stroke-width="2" stroke-dasharray="7 6" fill="none" opacity=".6" transform="translate(0,9)"/>')
    if s.get("yoke") and view == "back":
        parts.append(f'<path d="{s["yoke"]}" stroke="{seam}" stroke-width="3" fill="none" opacity=".85"/>')
    for c in s.get("cuffs", []):
        parts.append(f'<path d="{c}" fill="{shade(base, -0.06)}" stroke="{seam}" stroke-width="2.5"/>')
    parts.append('<rect width="1000" height="1200" filter="url(#grain)"/>')
    parts.append('</g>')

    is_shirt = sil_key.startswith("shirt")
    if not is_shirt:
        # inside of back neck + rib collar
        if view == "front":
            parts.append(f'<path d="{s["inner"]}" fill="{shade(base, -0.38)}"/>')
            parts.append(f'<path d="{s["neck_front"]}" stroke="{shade(base, -0.10)}" stroke-width="22" fill="none" stroke-linecap="round"/>')
            parts.append(f'<path d="{s["neck_front"]}" stroke="{stitch}" stroke-width="1.8" stroke-dasharray="6 5" fill="none" transform="translate(0,14)" opacity=".7"/>')
            # neck label peeking inside
            parts.append(f'<rect x="484" y="122" width="32" height="14" rx="2" fill="{GOLD}" opacity=".95"/>')
        else:
            parts.append(f'<path d="{s["neck_back"]}" stroke="{shade(base, -0.10)}" stroke-width="20" fill="none" stroke-linecap="round"/>')
    else:
        # collar, placket, buttons, pocket
        if view == "front":
            cx, top, bottom = s["placket"]
            parts.append(f'<rect x="{cx - 22}" y="{top}" width="44" height="{bottom - top}" fill="{shade(base, 0.03)}" stroke="{seam}" stroke-width="2"/>')
            parts.append(f'<path d="M{cx - 14},{top} L{cx - 14},{bottom}" stroke="{stitch}" stroke-dasharray="6 5" stroke-width="1.5" opacity=".7"/>')
            for by in s["buttons"]:
                parts.append(f'<circle cx="{cx}" cy="{by}" r="9" fill="{shade(base, -0.12) if not dark else shade(base, 0.25)}" stroke="{seam}" stroke-width="1.5"/>')
                parts.append(f'<circle cx="{cx - 3}" cy="{by}" r="1.6" fill="{seam}"/><circle cx="{cx + 3}" cy="{by}" r="1.6" fill="{seam}"/>')
            px, py, pw, ph = s["pocket"]
            parts.append(f'<path d="M{px},{py} L{px + pw},{py} L{px + pw},{py + ph - 18} L{px + pw / 2},{py + ph} L{px},{py + ph - 18} Z" fill="{shade(base, 0.02)}" stroke="{seam}" stroke-width="2.4"/>')
            parts.append(f'<path d="M{px + 8},{py + 10} L{px + pw - 8},{py + 10}" stroke="{stitch}" stroke-dasharray="5 5" stroke-width="1.5"/>')
            if sil_key == "shirt_long" and graphic == "overshirt":
                qx = 1000 - px - pw
                parts.append(f'<path d="M{qx},{py} L{qx + pw},{py} L{qx + pw},{py + ph - 18} L{qx + pw / 2},{py + ph} L{qx},{py + ph - 18} Z" fill="{shade(base, 0.02)}" stroke="{seam}" stroke-width="2.4"/>')
                parts.append(f'<rect x="{qx - 6}" y="{py - 8}" width="{pw + 12}" height="46" rx="6" fill="{shade(base, 0.05)}" stroke="{seam}" stroke-width="2.4"/>')
                parts.append(f'<rect x="{px - 6}" y="{py - 8}" width="{pw + 12}" height="46" rx="6" fill="{shade(base, 0.05)}" stroke="{seam}" stroke-width="2.4"/>')
            parts.append(f'<path d="{s["collar"]}" fill="{shade(base, 0.05)}" stroke="{seam}" stroke-width="2.6" stroke-linejoin="round"/>')
            parts.append(f'<path d="M500,{s["placket"][1]} L500,{s["placket"][1] - 40}" stroke="{seam}" stroke-width="2.4"/>')
            parts.append(f'<rect x="488" y="100" width="24" height="12" rx="2" fill="{GOLD}" opacity=".95"/>')
        else:
            parts.append(f'<path d="{s["collar_back"]}" fill="{shade(base, 0.05)}" stroke="{seam}" stroke-width="2.6"/>')
            parts.append(f'<path d="{s["yoke"]}" stroke="{seam}" stroke-width="3" fill="none"/>')
            if sil_key == "shirt_long":
                parts.append(f'<path d="M500,200 L500,250" stroke="{seam}" stroke-width="2.4"/>')  # box pleat

    # ---- branding
    mark_col = GOLD if dark or graphic else shade(base, -0.45)
    if view == "front":
        if graphic == "wordmark_front":
            parts.append(logo(500, 400, 170, accent))
            parts.append(wordmark(500, 560, 64, accent, "TRIDENT", 18, 900))
            parts.append(wordmark(500, 610, 22, accent, "WEAR THE STANDARD", 10, 600))
        elif graphic == "signal":
            parts.append(logo(500, 380, 120, accent))
            parts.append(f'<path d="M330,520 L670,520" stroke="{accent}" stroke-width="3"/>')
            parts.append(wordmark(500, 575, 40, accent, "TRIDENT / 001", 10, 800))
        else:
            cx, cy = s["chest"]
            parts.append(logo(cx, cy, s["logo_w"], mark_col if not is_shirt else (GOLD if dark else shade(base, -0.5))))
    else:
        # back: neck tape print + optional big back graphic
        parts.append(logo(500, 205 if not is_shirt else 230, 40, mark_col, 0.9))
        parts.append(wordmark(500, 260 if not is_shirt else 285, 15, mark_col, "TRIDENTWEAR", 6, 700))
        if graphic in ("wordmark_back", "wordmark_front", "signal"):
            parts.append(logo(500, 520, 260, accent))
            parts.append(wordmark(500, 752, 74, accent, "TRIDENT", 12, 900))
            parts.append(wordmark(500, 800, 20, accent, "EST. 2026 — MADE IN INDIA", 6, 600))
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1200" width="1000" height="1200">{"".join(parts)}</svg>'


def main() -> None:
    catalog = json.loads((Path(__file__).parent / "catalog.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = []
    for p in catalog:
        for view in ("front", "back"):
            name = f"{p['slug']}-{view}"
            svg = garment_svg(p["silhouette"], p["color_hex"], view, p.get("graphic"), p.get("accent", GOLD))
            (OUT / f"{name}.svg").write_text(svg)
            jobs.append(name)
    (OUT / "jobs.json").write_text(json.dumps(jobs))
    print(f"wrote {len(jobs)} svgs to {OUT}")


if __name__ == "__main__":
    main()
