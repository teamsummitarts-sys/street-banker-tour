# -*- coding: utf-8 -*-
"""Move hand-rolled headings, labels and machine values onto the system.

Design system v1, the second half of steps 2 and 3. Re-runnable and
idempotent.

    python tools/adopt_components.py --dry-run
    python tools/adopt_components.py

The colour and size sweeps got every page onto the tokens and the type
scale. They did not change what a page *says with* those values, and
three of the brief's requirements live there:

  * "Headings: Archivo, font-stretch 106-118%, uppercase, weight 700-800"
    -- 89 page titles were `text-2xl font-semibold uppercase
    tracking-tight`, which is the right size on the wrong face with none
    of the width axis.

  * "IBM Plex Mono for ALL machine values ... always tabular-nums"
    -- 395 elements carried `tabular-nums` and 5 carried the mono face.

  * Section heads were seven different spellings of the same 12px
    letterspaced uppercase label.

WHAT IT DOES NOT DO
-------------------
Large numerals keep the display face. The spec draws `.kpi-num` in
Archivo and only the timecode, the table numerics and the inline deltas
in Plex - a 38px metric is a headline, not a machine value. So the mono
rule applies at body sizes and below, which is where columns actually
need to line up.

Colour classes are always preserved. `sb-label` sets ink-3; a label that
was gold stays gold because its `text-*` utility outranks the component
layer.
"""
import io
import os
import re
import sys
import glob
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP = {
    "templates/_gear.html",
    "templates/rack.html",
    "templates/artwork.html",
    "templates/_sb.html",
}

# --- page titles ---------------------------------------------------------
# The size was already right; the face, the width axis and the weight were
# not. Layout classes on the same element are kept.
TITLE_TOKENS = {"text-2xl", "text-3xl", "font-semibold", "font-bold",
                "font-black", "uppercase", "tracking-tight", "leading-tight"}

# --- section labels ------------------------------------------------------
# Seven spellings of one thing: 12px, uppercase, letterspaced.
LABEL_SIZES = {"text-xs", "text-[10px]", "text-[11px]", "text-[12px]"}
LABEL_WEIGHTS = {"font-medium", "font-semibold", "font-bold", "font-black"}
# .1em through .39em. Anything tighter is emphasis, not a label.
TRACKING = re.compile(r'^tracking-\[0?\.[1-3][0-9]?em\]$')

# A label is text. If the element also paints a box it is a chip or a
# button, and `sb-label` would strip its weight and repaint it ink-3.
BOXY = ("rounded", "bg-", "border", "px-", "py-", "p-", "ring-", "shadow")

COLOUR = re.compile(r'^(?:text|decoration)-(?!xs$|sm$|base$|lg$|xl$|\dxl$|left$|right$|center$|wrap$|balance$|nowrap$)')


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def split(cls):
    return [c for c in cls.split() if c]


def do_title(classes):
    """`text-2xl font-semibold uppercase tracking-tight` -> `sb-h1`."""
    toks = split(classes)
    if any(c.startswith("sb-h") or c == "sb-display" for c in toks):
        return None
    if not ({"text-2xl", "text-3xl"} & set(toks)):
        return None
    if "uppercase" not in toks:
        return None
    kept = [c for c in toks if c not in TITLE_TOKENS]
    return " ".join(["sb-h1"] + kept)


def do_label(classes):
    """Any 12px uppercase letterspaced run -> `sb-label`, colour kept."""
    toks = split(classes)
    if "sb-label" in toks:
        return None
    if "uppercase" not in toks:
        return None
    if not (set(toks) & LABEL_SIZES):
        return None
    if not any(TRACKING.match(c) for c in toks):
        return None
    if any(c.startswith(BOXY) for c in toks):
        return None
    kept = []
    for c in toks:
        if c in LABEL_SIZES or c in LABEL_WEIGHTS or c == "uppercase":
            continue
        if TRACKING.match(c):
            continue
        kept.append(c)
    return " ".join(["sb-label"] + kept)


def do_mono(classes):
    """`tabular-nums` at body size or below -> the mono face.

    A 38px metric stays on Archivo: the spec draws `.kpi-num` in the
    display face and reserves Plex for the values that have to form
    columns."""
    toks = split(classes)
    if "tabular-nums" not in toks:
        return None
    if any(c in ("sb-num", "font-mono") for c in toks):
        return None
    big = {"text-lg", "text-xl", "text-2xl", "text-3xl", "text-4xl",
           "text-5xl", "text-6xl", "text-7xl", "text-8xl", "text-9xl"}
    if set(toks) & big:
        return None
    if any(re.match(r'^text-\[(\d+(?:\.\d+)?)px\]$', c)
           and float(re.match(r'^text-\[(\d+(?:\.\d+)?)px\]$', c).group(1)) >= 17
           for c in toks):
        return None
    return " ".join(["sb-num" if c == "tabular-nums" else c for c in toks])


def main():
    dry = "--dry-run" in sys.argv
    counts = collections.Counter()
    touched = collections.Counter()

    for p in sorted(glob.glob(os.path.join(ROOT, "templates", "**", "*.html"),
                              recursive=True)):
        if rel(p) in SKIP:
            continue
        s = orig = io.open(p, encoding="utf8", errors="ignore").read()

        # headings first, so a title is never also read as a label
        def title_sub(m):
            new = do_title(m.group(2))
            if not new:
                return m.group(0)
            counts["page title -> sb-h1"] += 1
            touched[rel(p)] += 1
            return '%sclass="%s"' % (m.group(1), new)

        s = re.sub(r'(<h1[^>]*?)class="([^"{]*)"', title_sub, s)

        def label_sub(m):
            new = do_label(m.group(1))
            if not new:
                return m.group(0)
            counts["label -> sb-label"] += 1
            touched[rel(p)] += 1
            return 'class="%s"' % new

        s = re.sub(r'class="([^"{]*)"', label_sub, s)

        def mono_sub(m):
            new = do_mono(m.group(1))
            if not new:
                return m.group(0)
            counts["machine value -> sb-num"] += 1
            touched[rel(p)] += 1
            return 'class="%s"' % new

        s = re.sub(r'class="([^"{]*)"', mono_sub, s)

        if s != orig and not dry:
            io.open(p, "w", encoding="utf8", newline="").write(s)

    print("%s %d templates" % ("WOULD CHANGE" if dry else "CHANGED", len(touched)))
    for k, n in counts.most_common():
        print("  %5d  %s" % (n, k))
    print("\nbusiest:")
    for p, n in touched.most_common(12):
        print("  %5d  %s" % (n, p))


if __name__ == "__main__":
    main()
