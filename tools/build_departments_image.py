"""Build the Section 4 photograph derivatives.

    python tools/build_departments_image.py path/to/photograph.jpg
    python tools/build_departments_image.py --from-composition path/to/mock.png

The first form is the one to use once the clean documentary photograph is
to hand: it only resizes and re-encodes, and touches nothing else.

The second form exists because the approved Section 4 composition arrived
without its source photograph. That composition already has the six
slices drawn into it - a black bar at each of the five seams, a slightly
different grade either side of each bar, and the eyebrow and label rows
above and below the picture - so this recovers a continuous photograph
from it:

  1. crop away the text bands, leaving only the picture
  2. repair each seam bar by mirroring the real texture either side of it
  3. close the brightness step at each seam with a cross-fade confined to
     40px, which removes the join without regrading the photograph

No global grading, no sharpening, no upscaling, no regeneration. Section 4
reads its slice geometry from CSS, so replacing the asset is the whole job:
the section needs no other change.
"""
import argparse
import math
import os

from PIL import Image

try:                                     # AVIF is optional, JPEG/WebP are not
    import pillow_avif                   # noqa: F401
    HAVE_AVIF = True
except ImportError:                      # pragma: no cover
    HAVE_AVIF = False

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "static", "img")
WIDTHS = [900, 1200, 1553]

# Where the picture sits inside the approved composition, and where the
# five slice bars were drawn across it.
BAND = (61, 123, 1614, 799)
SEAMS = [(305, 311), (580, 585), (838, 843), (1089, 1094), (1350, 1355)]
FEATHER = 1
RAMP = 40
SAMPLE = 24


def _median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else 1.0


def recover_from_composition(im):
    """Return the photograph inside a composition, seams closed."""
    px = im.load()
    y0, y1 = BAND[1] + 5, BAND[3] - 5

    steps = []
    for left, right in SEAMS:
        channels = []
        for c in range(3):
            ratios = []
            for y in range(y0, y1, 2):
                lo = sum(px[x, y][c] for x in range(left - SAMPLE - 2, left - 2)) / SAMPLE
                hi = sum(px[x, y][c] for x in range(right + 3, right + SAMPLE + 3)) / SAMPLE
                if lo > 6 and hi > 6:
                    ratios.append(lo / hi)
            channels.append(_median(ratios))
        steps.append(channels)

    # Mirror the real texture into the bar. A linear blend across nine
    # pixels of a textured wall reads as a smear; mirroring reads as wall.
    for left, right in SEAMS:
        a, b = left - FEATHER, right + FEATHER
        for y in range(BAND[1], BAND[3]):
            patched = []
            for x in range(a, b + 1):
                lsrc = px[int(a - 1 - (x - a)), y]
                rsrc = px[int(b + 1 + (b - x)), y]
                t = (x - a) / (b - a)
                blend = t * t * (3 - 2 * t)
                patched.append(tuple(
                    int(round(lsrc[c] + (rsrc[c] - lsrc[c]) * blend)) for c in range(3)))
            for x, value in zip(range(a, b + 1), patched):
                px[x, y] = value

    # Close the step. Each side fades towards the square root of the
    # measured ratio, so the two meet and both return to untouched.
    for (left, right), ratio in zip(SEAMS, steps):
        centre = (left + right) / 2
        half = [math.sqrt(r) for r in ratio]
        for x in range(int(centre - RAMP), int(centre + RAMP) + 1):
            distance = abs(x - centre) / RAMP
            ease = 0.5 * (1 + math.cos(math.pi * distance))
            gain = [1 + (1 / h - 1) * ease if x < centre else 1 + (h - 1) * ease
                    for h in half]
            for y in range(BAND[1], BAND[3]):
                r, g, b = px[x, y]
                px[x, y] = (min(255, int(round(r * gain[0]))),
                            min(255, int(round(g * gain[1]))),
                            min(255, int(round(b * gain[2]))))

    return im.crop(BAND)


def write_derivatives(photo):
    width, height = photo.size
    print("master: %d x %d (ratio %.3f)" % (width, height, width / height))
    for target in WIDTHS:
        if target > width:
            print("skipping %d: the source is only %dpx wide, and upscaling "
                  "invents detail" % (target, width))
            continue
        scaled = photo if target == width else photo.resize(
            (target, round(height * target / width)), Image.LANCZOS)
        stem = os.path.join(OUT, "departments-%d" % target)
        scaled.save(stem + ".jpg", quality=84, optimize=True, progressive=True)
        scaled.save(stem + ".webp", quality=80, method=6)
        if HAVE_AVIF:
            scaled.save(stem + ".avif", quality=58)
        print("wrote", stem, scaled.size)
    if not HAVE_AVIF:
        print("pillow-avif-plugin is not installed: the AVIF sources were "
              "left as they were.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("--from-composition", action="store_true",
                        help="the source is the approved mock, not the photograph")
    args = parser.parse_args()

    im = Image.open(args.source).convert("RGB")
    photo = recover_from_composition(im) if args.from_composition else im
    write_derivatives(photo)


if __name__ == "__main__":
    main()
