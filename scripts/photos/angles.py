"""Place 3/4 (-q) and side (-s) angle cutouts at the same scale and top as the front photo,
so the studio turntable doesn't change the garment's size while it turns.
Usage: python scripts/photos/angles.py   (after cutout.py has produced <slug>-front/-q/-s.png in PHOTOS_CUT)"""
import glob, os
from PIL import Image
CUT = os.environ.get('PHOTOS_CUT', 'scripts/photos/cut')
OUT = 'frontend/assets/images/products'
for f in sorted(glob.glob(f'{CUT}/*-[qs].png')):
    name = os.path.basename(f)[:-4]; base, view = name[:-2], name[-1]
    fb = Image.open(f'{CUT}/{base}-front.png').getchannel('A').getbbox()
    im = Image.open(f).convert('RGBA'); a = im.getchannel('A').point(lambda v: 0 if v < 8 else v); im.putalpha(a)
    g = im.crop(a.getbbox()); fh = fb[3] - fb[1]
    g = g.resize((round(g.width * fh / g.height), fh), Image.LANCZOS)
    c = Image.new('RGBA', (900, 1080), (0, 0, 0, 0)); c.paste(g, ((900 - g.width) // 2, fb[1]), g)
    c.save(f'{OUT}/{base}-{view}.webp', 'WEBP', quality=86, method=6)
    c.resize((480, 576), Image.LANCZOS).save(f'{OUT}/{base}-{view}-480.webp', 'WEBP', quality=82, method=6)
    print(name, g.size)
