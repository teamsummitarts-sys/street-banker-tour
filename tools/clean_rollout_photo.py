"""Build the Section 8 photograph derivatives.

    python tools/clean_rollout_photo.py path/to/photograph.png [--already-clean]

The clean backstage photograph did not come through with the brief - only
the layout mockup did - so the production asset is taken from the part of
that mockup the overlay type never covers, and the generated writing
inside it is cleared.

What is cleared, and why: a routing sheet listing dates out of order and
"PHILADEPHIA PA", a sticky note reading "FALL COMES UK TOUR BY 10PM", two
floor posters printed STREET BANKER / LEGENDS NEVER DIE, and a malformed
month label. The brief for this section rules out nonsensical tour
routes, impossible dates, malformed generated writing and fake Street
Banker branding.

The calendars themselves stay: a grid with illegible marks on it is what
a venue wall looks like, and nothing in the section depends on reading
one. Each cleared area is filled from its own edges and given the grain
of a clean piece of the same surface back, so paper stays paper.

Nothing else is touched: the people, the room, the light, the road cases
and the movement blur are as supplied.
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

PHOTO = (0, 0, 940, 1086)        # the picture, left of the overlay type
FEATHER = 8
GRAIN_SOURCE = (620, 640)        # plain wall, no paper and no lettering

# (box, grain amount)
ZONES = [
    ((133, 93, 227, 197), 0.30),      # sticky note
    ((50, 438, 208, 648), 0.30),      # tour routing sheet
    ((141, 876, 254, 953), 0.28),     # floor poster lettering
    ((211, 1011, 389, 1082), 0.28),   # floor poster lettering
    ((336, 122, 402, 158), 0.30),     # malformed month label
]

# Desktop keeps the room; the phone keeps the person marking the calendar.
CROPS = {
    "wide": ((0, 110, 940, 820), [560, 940]),
    "close": ((60, 150, 660, 780), [400, 600]),
}


def _mask(size, feather):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(
        [feather, feather, size[0] - feather - 1, size[1] - feather - 1], fill=255)
    return m.filter(ImageFilter.GaussianBlur(feather * 0.8))


def _fill_from_edges(photo, box):
    """A smooth surface pinned to the pixels just outside the box."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    px = photo.load()
    left = [px[max(0, x0 - 1), y] for y in range(y0, y1)]
    right = [px[min(photo.width - 1, x1), y] for y in range(y0, y1)]
    top = [px[x, max(0, y0 - 1)] for x in range(x0, x1)]
    bottom = [px[x, min(photo.height - 1, y1)] for x in range(x0, x1)]
    out = Image.new("RGB", (w, h))
    op = out.load()
    for j in range(h):
        for i in range(w):
            u, v = (i + 0.5) / w, (j + 0.5) / h
            wh, wv = min(v, 1 - v) + 1e-6, min(u, 1 - u) + 1e-6
            total = wh + wv
            op[i, j] = tuple(
                int(round(((left[j][c] * (1 - u) + right[j][c] * u) * wh +
                           (top[i][c] * (1 - v) + bottom[i][c] * v) * wv) / total))
                for c in range(3))
    return out.filter(ImageFilter.GaussianBlur(2))


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
        fill = _fill_from_edges(photo, box)
        grain = _grain(photo, (w, h), amount)
        fp, gp = fill.load(), grain.load()
        for j in range(h):
            for i in range(w):
                fp[i, j] = tuple(max(0, min(255, fp[i, j][c] + gp[i, j][c] - 128))
                                 for c in range(3))
        photo.paste(fill, (box[0], box[1]), _mask((w, h), FEATHER))
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
        stem = os.path.join(OUT, "rollout-%s-%d" % (name, width))
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
