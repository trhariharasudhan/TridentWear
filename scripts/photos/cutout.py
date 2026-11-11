"""Step 1: background removal + normalise every garment onto a 900x1080 transparent canvas."""
import sys, glob, os
from PIL import Image
from rembg import remove, new_session
sess = new_session('isnet-general-use')
SRC = os.environ.get('PHOTOS_RAW', '_photos_raw')
OUT = os.environ.get('PHOTOS_CUT', 'scripts/photos/cut')
W, H, MAXW, MAXH = 900, 1080, 800, 960
for p in sorted(glob.glob(f'{SRC}/*.png')):
    name = os.path.basename(p)[:-4]
    out = f'{OUT}/{name}.png'
    if os.path.exists(out): continue
    im = Image.open(p).convert('RGB')
    rgba = remove(im, session=sess, post_process_mask=True)
    a = rgba.getchannel('A').point(lambda v: 0 if v < 8 else v)
    rgba.putalpha(a)
    box = a.getbbox(); g = rgba.crop(box)
    s = min(MAXW / g.width, MAXH / g.height)
    g = g.resize((round(g.width * s), round(g.height * s)), Image.LANCZOS)
    canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    canvas.paste(g, ((W - g.width) // 2, (H - g.height) // 2), g)
    canvas.save(out); print(name, g.size, flush=True)
