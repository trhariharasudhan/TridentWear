# Product photo pipeline

1. Generate plain garment photos (ghost mannequin, no logo, light grey background) with an
   image model and save them as `_photos_raw/<slug>-front.png` (see prompts in the PR notes).
2. `python scripts/photos/cutout.py` removes backgrounds (rembg `isnet-general-use`) and normalises
   each garment onto a 900x1080 transparent canvas in `scripts/photos/cut/`.
3. `python scripts/photos/brand.py` adds the real Trident mark (embroidered gold on the chest or
   pocket, screen print for graphic tees), builds back views, and writes
   `frontend/assets/images/products/<slug>-{front,back}.webp` plus `-480.webp` variants.

Needs: `pip install "rembg[cpu]" pillow numpy fonttools brotli`, and `bricolage.ttf`
(convert `frontend/assets/fonts/bricolage.woff2` with fontTools). These are AI-made stand-ins:
replace them with photos of the real samples before selling.
