"""Build the Section 10 photograph derivatives.

    python tools/clean_distribution_photo.py path/to/photograph.png [--already-clean]

No clean production photograph came with the brief, only the layout
mockup, and on this one the rasterised copy sits in the middle of the
still life rather than above it - so the picture cannot simply be cropped
out from under it.

What is removed: the rasterised headline copy, the DISTRIBUTE NOW button
and the VIEW DISTRIBUTION GUIDE link, all of which are built as live
markup in the section; a strip of tape reading STREET BANKER DELIVERED
and an SB stencil, which are branding drawn into a photograph; and the
written items on the release checklist, because the section prints an
example checklist of its own and two of them would be the same words
twice.

What stays: the road cases, the album-masters book, the release passport,
the stems drive, the cables, the notebook, and the tape reading MASTERS
DON'T SLEEP and GOIN' GLOBAL. Those are the room.

Each cleared area is repainted in the surface's own colour - the median of
its brighter pixels, which is the tape or the paper with the ink taken
out - and given a little grain back.
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFilter

try:
    import pillow_avif  # noqa: F401
    HAVE_AVIF = True
except ImportError:                      # pragma: no cover
    HAVE_AVIF = False

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "static", "img")

PHOTO = (0, 314, 1402, 776)          # the still life inside the mockup
FEATHER = 3
GRAIN_SOURCE = (700, 400)            # dark table, no lettering over it

# (box, grain amount)
ZONES = [
    ((466, 0, 954, 30), 0.20),       # rasterised supporting copy
    ((566, 28, 840, 110), 0.16),     # rasterised DISTRIBUTE NOW button
    ((568, 108, 830, 148), 0.16),    # rasterised guide link
    ((78, 128, 322, 224), 0.26),     # tape: STREET BANKER DELIVERED
    ((1104, 400, 1210, 462), 0.22),  # SB stencil
    ((1126, 202, 1314, 372), 0.24),  # release checklist heading and items
]

# Desktop keeps the whole bench; the phone keeps the passport, the
# masters, the stems and the checklist.
CROPS = {
    "wide": ((0, 0, 1402, 476), [760, 1180, 1402]),
    # The phone crop is taller on purpose: at the bench's own 3:1 the
    # still life is a 117px strip on a 375px screen.
    "close": ((380, 40, 1120, 462), [480, 740]),
}


def _mask(size, feather):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(
        [feather, feather, size[0] - feather - 1, size[1] - feather - 1], fill=255)
    return m.filter(ImageFilter.GaussianBlur(feather * 0.8))


def _surface_colour(photo, box):
    px = photo.load()
    pixels = [px[x, y] for x in range(box[0], box[2]) for y in range(box[1], box[3])]
    pixels.sort(key=lambda p: sum(p))
    keep = pixels[int(len(pixels) * 0.55):int(len(pixels) * 0.85)] or pixels
    return tuple(sum(p[c] for p in keep) // len(keep) for c in range(3))


def _repaint(photo, box):
    """A flat patch of the surface's own colour, shaded towards the tone
    at each edge so it still sits in the light of the scene."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    flat = _surface_colour(photo, box)
    left = _surface_colour(photo, (max(0, x0 - 10), y0, x0 + 2, y1))
    right = _surface_colour(photo, (x1 - 2, y0, min(photo.width, x1 + 10), y1))
    out = Image.new("RGB", (w, h))
    op = out.load()
    for i in range(w):
        u = (i + 0.5) / w
        edge = tuple(left[c] * (1 - u) + right[c] * u for c in range(3))
        column = tuple(int(round(flat[c] * 0.72 + edge[c] * 0.28)) for c in range(3))
        for j in range(h):
            op[i, j] = column
    return out.filter(ImageFilter.GaussianBlur(1.2))


def _grain(photo, size, amount):
    w, h = size
    sx, sy = GRAIN_SOURCE
    patch = photo.crop((sx, sy, sx + w, sy + h))
    base = patch.filter(ImageFilter.GaussianBlur(3))
    pp, bp = patch.load(), base.load()
    out = Image.new("RGB", size)
    op = out.load()
    for j in range(h):
        for i in range(w):
            op[i, j] = tuple(int(round((pp[i, j][c] - bp[i, j][c]) * amount)) + 128
                             for c in range(3))
    return out


def clean(photo):
    for box, amount in ZONES:
        w, h = box[2] - box[0], box[3] - box[1]
        patch = _repaint(photo, box)
        grain = _grain(photo, (w, h), amount)
        pp, gp = patch.load(), grain.load()
        for j in range(h):
            for i in range(w):
                pp[i, j] = tuple(max(0, min(255, pp[i, j][c] + gp[i, j][c] - 128))
                                 for c in range(3))
        photo.paste(patch, (box[0], box[1]), _mask((w, h), FEATHER))
    return photo


def write(photo, name, crop, widths):
    piece = photo.crop(crop)
    pw, ph = piece.size
    print("%s: %d x %d (ratio %.3f)" % (name, pw, ph, pw / ph))
    for width in widths:
        if width > pw:
            print("  skipping %d: the source is %dpx wide" % (width, pw))
            continue
        scaled = piece if width == pw else piece.resize(
            (width, round(ph * width / pw)), Image.LANCZOS)
        stem = os.path.join(OUT, "distro-%s-%d" % (name, width))
        scaled.save(stem + ".jpg", quality=86, optimize=True, progressive=True)
        scaled.save(stem + ".webp", quality=82, method=6)
        if HAVE_AVIF:
            scaled.save(stem + ".avif", quality=60)
        print("  wrote", stem, scaled.size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("--already-clean", action="store_true",
                        help="the source is the photograph, not the mockup")
    args = parser.parse_args()

    im = Image.open(args.source).convert("RGB")
    photo = im if args.already_clean else clean(im.crop(PHOTO))
    for name, (crop, widths) in CROPS.items():
        write(photo, name, crop, widths)


if __name__ == "__main__":
    main()
