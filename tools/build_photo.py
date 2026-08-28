"""Build the homepage derivatives from one real photograph.

Every section photograph on this site ships as three formats at several
widths, with the master's intrinsic size declared in the markup so the
browser reserves the box before a byte arrives. This does that from a
single original, so replacing a picture is one command rather than
eighteen exports.

    python tools/build_photo.py incoming/artist-photos/hero-crowd.jpg hero-wide
    python tools/build_photo.py incoming/artist-photos/hero-crowd.jpg hero-tall --focus 0.42,0.30

`--focus` is the point in the original that must survive the crop, as
fractions of width and height: the face, the hands, whatever the frame is
actually about. Centre-cropping decides that for itself and usually
decides wrong. The crop is taken as large as the target aspect allows and
then slid so the focus point sits at the same relative position, clamped
to the edges.

Nothing here retouches, repairs or alters content. It crops, resizes and
encodes. If an image needs more than that, it is the wrong image.
"""
import argparse
import os
import sys

from PIL import Image

# Target aspect and widths per slot, matching what the templates already
# declare. Keep these in step with docs/IMAGE_ASSET_MANIFEST.md.
SLOTS = {
    "hero-wide":      {"stem": "hero-band-wide",  "aspect": 1342 / 775, "widths": [900, 1100, 1342]},
    "hero-tall":      {"stem": "hero-band-tall",  "aspect": 900 / 1200, "widths": [640, 900]},
    "creative-wide":  {"stem": "creative-wide",   "aspect": 830 / 980,  "widths": [520, 830]},
    "creative-close": {"stem": "creative-close",  "aspect": 600 / 520,  "widths": [400, 600]},
    "rollout-wide":   {"stem": "rollout-wide",    "aspect": 940 / 710,  "widths": [560, 940]},
    "rollout-close":  {"stem": "rollout-close",   "aspect": 600 / 630,  "widths": [400, 600]},
}

OUT_DIR = os.path.join("static", "img")

# Quality: high enough that a real photograph does not visibly degrade at
# the widths these are displayed at, low enough that the page stays light.
QUALITY = {"jpg": 84, "webp": 82, "avif": 62}


def crop_to_aspect(im, aspect, focus):
    """Largest crop at `aspect`, slid so `focus` keeps its position."""
    w, h = im.size
    if w / h > aspect:
        ch = h
        cw = int(round(h * aspect))
    else:
        cw = w
        ch = int(round(w / aspect))

    fx, fy = focus
    # Put the focus point at the same relative spot inside the crop that
    # it occupies in the original, then clamp so we never leave the frame.
    left = int(round(fx * w - fx * cw))
    top = int(round(fy * h - fy * ch))
    left = max(0, min(left, w - cw))
    top = max(0, min(top, h - ch))
    return im.crop((left, top, left + cw, top + ch))


def build(source, slot, focus, dry_run=False):
    spec = SLOTS[slot]
    im = Image.open(source)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")

    cropped = crop_to_aspect(im, spec["aspect"], focus)
    master_w = max(spec["widths"])
    master_h = int(round(master_w / spec["aspect"]))

    print("%s -> %s" % (source, spec["stem"]))
    print("  original %dx%d, cropped %dx%d, master %dx%d"
          % (im.size + cropped.size + (master_w, master_h)))

    if cropped.width < master_w:
        print("  WARNING: the crop is %dpx wide but the master needs %dpx. "
              "It will be upscaled and will look soft." % (cropped.width, master_w))

    written = []
    for width in spec["widths"]:
        height = int(round(width / spec["aspect"]))
        resized = cropped.resize((width, height), Image.LANCZOS)
        for fmt in ("jpg", "webp", "avif"):
            path = os.path.join(OUT_DIR, "%s-%d.%s" % (spec["stem"], width, fmt))
            if dry_run:
                written.append(path)
                continue
            kwargs = {"quality": QUALITY[fmt]}
            if fmt == "jpg":
                kwargs.update(optimize=True, progressive=True)
            resized.save(path, **kwargs)
            written.append("%s (%d KB)" % (path, os.path.getsize(path) // 1024))
    for line in written:
        print("  " + line)
    print("  declare width=\"%d\" height=\"%d\" in the template" % (master_w, master_h))
    return master_w, master_h


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="the original photograph, full resolution")
    p.add_argument("slot", choices=sorted(SLOTS), help="which homepage slot to build")
    p.add_argument("--focus", default="0.5,0.5",
                   help="point that must survive the crop, as x,y fractions "
                        "(default 0.5,0.5 = centre)")
    p.add_argument("--dry-run", action="store_true",
                   help="report the crop and the files without writing them")
    args = p.parse_args()

    if not os.path.exists(args.source):
        sys.exit("no such file: %s" % args.source)
    try:
        fx, fy = (float(v) for v in args.focus.split(","))
    except ValueError:
        sys.exit("--focus wants two numbers, e.g. 0.42,0.30")
    if not (0 <= fx <= 1 and 0 <= fy <= 1):
        sys.exit("--focus values are fractions between 0 and 1")

    build(args.source, args.slot, (fx, fy), args.dry_run)


if __name__ == "__main__":
    main()
