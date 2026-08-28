"""Build the Section 9 photograph derivatives.

    python tools/clean_sweep_photo.py path/to/photograph.png [--already-clean]

The separate production photograph did not come through with the brief -
only the layout mockup did - so the asset is the picture band inside that
mockup, with the writing the brief rules out cleared.

What goes, and why: a song-registration form filled in with invented
writers, a publisher called "Street Banker Publishing" and the
registration number SR-00941-1993; archive boxes, hard drives and a test
pressing labelled SB; and a cassette stack labelled SB_1992_Sessions.
Fake artist names, fake organisations, nonsensical registration numbers
and repeated Street Banker branding are all named in the brief as things
this photograph must not carry.

What stays: the studio log, the split sheet, the lyric notebook and the
loose cassette labels. The brief allows environmental tape labels and
handwritten catalog notes as texture, and nothing in the section depends
on reading one - every workflow stage, status and figure is markup.

Each cleared area is repainted in the surface's own colour - the median
of its brighter pixels, which is the label or the paper with the ink
taken out - and given a little grain back. A label reads as blank tape
and the form reads as an unfilled form, rather than as a blurred
rectangle or a bright block.
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

PHOTO = (0, 190, 1672, 745)          # the picture band inside the mockup
# A wide feather leaves the ends of a label untouched - at six pixels
# the mask only reached full strength in the middle of a plate and the
# lettering survived at both ends.
FEATHER = 3
GRAIN_SOURCE = (612, 300)            # aged paper, no lettering over it

# (box, grain amount) - each one a whole label plate or written field, so
# the repaint has the plate's own margin to blend into.
ZONES = [
    ((151, 33, 365, 82), 0.30),      # archive box label, SB
    ((171, 97, 337, 146), 0.30),    # archive box label, SB
    ((436, 174, 564, 292), 0.26),    # cassette stack, SB_1992 / SB_1993
    ((1052, 104, 1203, 148), 0.24),  # hard drive label, SB
    ((1052, 149, 1203, 193), 0.24),  # hard drive label, SB
    ((1052, 194, 1203, 240), 0.24),  # hard drive label, SB
    ((1452, 178, 1538, 216), 0.22),  # test pressing, SB-001
    ((692, 422, 898, 516), 0.22),    # registration form, filled values
    ((612, 497, 868, 546), 0.22),    # registration number and signature
]

# Desktop keeps the whole table; the phone keeps the deck, the drives and
# the documents in the middle of it.
CROPS = {
    "wide": ((0, 0, 1672, 555), [900, 1400, 1672]),
    "close": ((430, 90, 1290, 555), [430, 860]),
}


def _mask(size, feather):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(
        [feather, feather, size[0] - feather - 1, size[1] - feather - 1], fill=255)
    return m.filter(ImageFilter.GaussianBlur(feather * 0.8))


def _surface_colour(photo, box):
    """The label or paper with the ink taken out: the median of the
    brighter half of the box, which on dark ink over a pale plate is the
    plate itself."""
    px = photo.load()
    pixels = [px[x, y] for x in range(box[0], box[2])
              for y in range(box[1], box[3])]
    pixels.sort(key=lambda p: sum(p))
    keep = pixels[int(len(pixels) * 0.55):int(len(pixels) * 0.85)] or pixels
    return tuple(sum(p[c] for p in keep) // len(keep) for c in range(3))


def _fill_from_edges(photo, box):
    """A flat patch of the surface's own colour, shaded a little towards
    the tone at each edge so it still sits in the light of the scene."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    flat = _surface_colour(photo, box)
    px = photo.load()
    left = _surface_colour(photo, (max(0, x0 - 8), y0, x0 + 2, y1))
    right = _surface_colour(photo, (x1 - 2, y0, min(photo.width, x1 + 8), y1))
    out = Image.new("RGB", (w, h))
    op = out.load()
    for i in range(w):
        u = (i + 0.5) / w
        edge = tuple(left[c] * (1 - u) + right[c] * u for c in range(3))
        column = tuple(int(round(flat[c] * 0.75 + edge[c] * 0.25)) for c in range(3))
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
        stem = os.path.join(OUT, "sweep-%s-%d" % (name, width))
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
