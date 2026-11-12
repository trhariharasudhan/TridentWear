"""Step 2: put the real TridentWear mark on every garment photo.

* embroidery(): small gold chest/pocket logo with satin-stitch texture, raised shadow
  and the fabric's own fold shading so it sits *in* the cloth, not on top of it.
* print_(): screen-print look for big graphics (Signal tee front, Wordmark tee backs).
Output: frontend/assets/images/products/<slug>-{front,back}.webp (+ 480w variants).
"""
import os
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageOps

CUT = os.environ.get('PHOTOS_CUT', 'scripts/photos/cut')
OUT = 'frontend/assets/images/products'
FONT = os.environ.get('BRICOLAGE_TTF', 'scripts/photos/bricolage.ttf')
GOLD_HI, GOLD_LO = np.array([222, 189, 120]), np.array([160, 124, 56])
AMBER = np.array([255, 196, 72])
POCKET = {}
LOGO = Image.open(os.environ.get('LOGO_MASK', 'scripts/photos/logo-mask.png')).getchannel('A')


def font(size, wght=800, wdth=85, opsz=96):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_axes([opsz, wght, wdth])
    return f


def logo_mask(width):
    h = round(LOGO.height * width / LOGO.width)
    return LOGO.resize((width, h), Image.LANCZOS)


def shading(base, box):
    """Fabric fold shading under a region, normalised around 1.0."""
    lum = np.asarray(base.convert('L').crop(box), dtype=np.float32) + 1
    blur = np.asarray(Image.fromarray(lum.astype(np.uint8)).filter(ImageFilter.GaussianBlur(14)), dtype=np.float32) + 1
    return np.clip(lum / blur.mean() * 0.55 + (lum / blur) * 0.45, 0.72, 1.18)


def composite(base, layer_rgb, alpha, xy, shadow=True):
    x, y = xy
    w, h = alpha.size
    box = (x, y, x + w, y + h)
    shade = shading(base, box)[..., None]
    rgb = np.clip(layer_rgb * shade, 0, 255).astype(np.uint8)
    layer = Image.fromarray(rgb, 'RGB').convert('RGBA')
    garment_alpha = base.getchannel('A').crop(box)
    a = Image.fromarray(np.minimum(np.asarray(alpha), np.asarray(garment_alpha)))
    layer.putalpha(a)
    if shadow:  # raised thread: soft shadow down-right, faint highlight up-left
        sh = Image.new('RGBA', base.size, (0, 0, 0, 0))
        sh.paste(Image.new('RGBA', a.size, (0, 0, 0, 110)), (x + 1, y + 2), a)
        base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(1.6)))
        hl = Image.new('RGBA', base.size, (0, 0, 0, 0))
        hl.paste(Image.new('RGBA', a.size, (255, 255, 255, 60)), (x - 1, y - 1), a)
        base.alpha_composite(hl.filter(ImageFilter.GaussianBlur(0.8)))
    base.alpha_composite(layer, (x, y))


def embroidery(base, cx, cy, width):
    m = logo_mask(width)
    w, h = m.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = (xx / w * 0.6 + yy / h * 0.4)[..., None]                    # metallic gradient
    rgb = GOLD_HI * (1 - t) + GOLD_LO * t
    satin = 1 + 0.10 * np.sin((xx * 0.8 + yy * 0.8) * 1.9)[..., None]  # satin-stitch lines
    composite(base, rgb * satin, m, (round(cx - w / 2), round(cy - h / 2)))


def print_(base, art: Image.Image, cx, cy, ink=None, opacity=0.94):
    """art: L-mode mask of the graphic. Ink defaults to amber; slight grain like plastisol."""
    w, h = art.size
    rng = np.random.default_rng(7)
    grain = 1 + rng.normal(0, 0.035, (h, w, 1)).astype(np.float32)
    rgb = np.broadcast_to((ink if ink is not None else AMBER), (h, w, 3)) * grain
    a = Image.fromarray((np.asarray(art, dtype=np.float32) * opacity).astype(np.uint8))
    composite(base, rgb, a, (round(cx - w / 2), round(cy - h / 2)), shadow=False)


def text_art(lines, gap=10):
    """lines: [(text, size, wght, tracking_px)] -> centred L mask."""
    rendered = []
    for text, size, wght, track in lines:
        f = font(size, wght)
        widths = [f.getbbox(ch)[2] - f.getbbox(ch)[0] if ch != ' ' else size * 0.28 for ch in text]
        wtotal = int(sum(f.getlength(ch) for ch in text) + track * (len(text) - 1)) + 4
        asc, desc = f.getmetrics()
        img = Image.new('L', (wtotal, asc + desc), 0)
        d = ImageDraw.Draw(img)
        x = 2
        for ch in text:
            d.text((x, 0), ch, font=f, fill=255)
            x += f.getlength(ch) + track
        rendered.append(img.crop(img.getbbox()))
    W = max(r.width for r in rendered)
    H = sum(r.height for r in rendered) + gap * (len(rendered) - 1)
    out = Image.new('L', (W, H), 0)
    y = 0
    for r in rendered:
        out.paste(r, ((W - r.width) // 2, y)); y += r.height + gap
    return out


def stack(*parts, gap=18):
    W = max(p.width for p in parts); H = sum(p.height for p in parts) + gap * (len(parts) - 1)
    out = Image.new('L', (W, H), 0); y = 0
    for p in parts:
        out.paste(p, ((W - p.width) // 2, y)); y += p.height + gap
    return out


def save(img, slug):
    img.save(f'{OUT}/{slug}.webp', 'WEBP', quality=86, method=6)
    small = img.resize((480, 576), Image.LANCZOS)
    small.save(f'{OUT}/{slug}-480.webp', 'WEBP', quality=82, method=6)


def load(name):
    return Image.open(f'{CUT}/{name}.png').convert('RGBA')


def bbox(img):
    return img.getchannel('A').getbbox()


def chest(img, kind):
    l, t, r, b = bbox(img)
    w, h = r - l, b - t
    if kind == 'oversized':
        return 450 + w * 0.165, t + h * 0.245, round(w * 0.06)
    return 450 + w * 0.17, t + h * 0.245, round(w * 0.064)  # classic


def back_from(front: Image.Image):
    """Back view stand-in: mirror the front and close the scoop neck into a higher back neck."""
    back = ImageOps.mirror(front)
    a = np.asarray(back).copy()
    l, t, r, b = back.getchannel('A').getbbox()
    w = r - l
    # sample body colour just below the collar and paint the inner-neck opening with it
    cx = 450
    body = a[t + int((b - t) * 0.22), cx - 20:cx + 20, :3].reshape(-1, 3).mean(0)
    neck = Image.new('L', back.size, 0)
    d = ImageDraw.Draw(neck)
    nw = w * 0.17
    d.ellipse((cx - nw, t - (b - t) * 0.06, cx + nw, t + (b - t) * 0.085), fill=255)
    neck = neck.filter(ImageFilter.GaussianBlur(3))
    alpha_in = np.asarray(neck, dtype=np.float32)[..., None] / 255 * (a[..., 3:4] > 0)
    a[..., :3] = (a[..., :3] * (1 - alpha_in) + body * alpha_in).astype(np.uint8)
    # inner-neck shadows the ellipse missed (e.g. olive): dark pixels near the collar -> body colour
    region = (slice(t, t + int((b - t) * 0.16)), slice(int(cx - w * 0.22), int(cx + w * 0.22)))
    sub = a[region].astype(np.float32)
    lum = sub[..., :3].mean(-1)
    dark = (lum < body.mean() * 0.62) & (sub[..., 3] > 0)
    m = Image.fromarray((dark * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(2.5))
    k = np.asarray(m, dtype=np.float32)[..., None] / 255
    sub[..., :3] = sub[..., :3] * (1 - k) + body * 0.93 * k
    a[region] = sub.astype(np.uint8)
    return Image.fromarray(a, 'RGBA')


def main():
    os.makedirs(OUT, exist_ok=True)
    plain = {  # slug -> (cut source, kind)
        'essential-oversized-tee-jet-black': ('essential-oversized-tee-jet-black-front', 'oversized'),
        'essential-oversized-tee-bone-white': ('essential-oversized-tee-bone-white-front', 'oversized'),
        'essential-oversized-tee-charcoal': ('essential-oversized-tee-charcoal-front', 'oversized'),
        'essential-oversized-tee-olive': ('essential-oversized-tee-olive-front', 'oversized'),
        'heavyweight-classic-tee-navy': ('heavyweight-classic-tee-navy-front', 'classic'),
        'heavyweight-classic-tee-sand': ('heavyweight-classic-tee-sand-front', 'classic'),
        'heavyweight-classic-tee-maroon': ('heavyweight-classic-tee-maroon-front', 'classic'),
    }
    for slug, (src, kind) in plain.items():
        img = load(src)
        x, y, w = chest(img, kind)
        embroidery(img, x, y, w)
        save(img, f'{slug}-front')
        # back: plain back with small gold neck mark under the collar
        back = back_from(load(src))
        l, t, r, b = bbox(back)
        embroidery(back, 450, t + (b - t) * 0.13, round((r - l) * 0.045))
        save(back, f'{slug}-back')

    pockets = {'oxford-button-down-sky': ('oxford-button-down-sky-front', 592, 445, 38),
               'oxford-button-down-white': ('oxford-button-down-white-front', 586, 415, 38),
               'twill-overshirt-black': ('twill-overshirt-black-front', *POCKET.get('twill', (600, 470)), 40),
               'linen-camp-shirt-stone': ('linen-camp-shirt-stone-front', *POCKET.get('stone', (600, 452)), 38),
               'linen-camp-shirt-olive': ('linen-camp-shirt-olive-front', *POCKET.get('olive', (592, 468)), 38)}
    for slug, (src, x, y, w) in pockets.items():
        img = load(src)
        embroidery(img, x, y, w)
        save(img, f'{slug}-front')
    # formal shirt: no pocket -> small chest mark
    img = load('formal-slim-shirt-navy-front')
    l, t, r, b = bbox(img)
    embroidery(img, 450 + (r - l) * 0.2, t + (b - t) * 0.25, 34)
    save(img, 'formal-slim-shirt-navy-front')

    # Wordmark tees: same chest mark on the front, big wordmark across the back
    for slug, src in (('trident-wordmark-tee-black', 'essential-oversized-tee-jet-black-front'),
                      ('trident-wordmark-tee-white', 'essential-oversized-tee-bone-white-front')):
        img = load(src)
        x, y, w = chest(img, 'oversized')
        embroidery(img, x, y, w)
        save(img, f'{slug}-front')
        back = back_from(load(src))
        l, t, r, b = bbox(back)
        art = stack(logo_mask(round((r - l) * 0.10)),
                    text_art([('TridentWear', 50, 800, -1)]),
                    text_art([('Made in India', 17, 500, 1)]), gap=12)
        ink = np.array([214, 178, 104]) if 'black' in slug else np.array([24, 26, 34])
        print_(back, art, 450, t + (b - t) * 0.24, ink=ink)
        save(back, f'{slug}-back')

    # Violet Signal tee: front graphic + small back neck mark
    img = load('violet-signal-tee-front')
    l, t, r, b = bbox(img)
    art = stack(logo_mask(round((r - l) * 0.09)),
                text_art([('Signal / 001', 22, 650, 2)]), gap=10)
    print_(img, art, 450 + (r - l) * 0.165, t + (b - t) * 0.27)
    save(img, 'violet-signal-tee-front')
    back = back_from(load('violet-signal-tee-front'))
    l, t, r, b = bbox(back)
    embroidery(back, 450, t + (b - t) * 0.13, round((r - l) * 0.045))
    save(back, 'violet-signal-tee-back')


if __name__ == '__main__':
    main()
