# -*- coding: utf-8 -*-
"""Map every ad-hoc font size and corner radius onto the design system.

Design system v1, step 4. Re-runnable and idempotent.

    python tools/normalise_type.py --dry-run
    python tools/normalise_type.py

TYPE
----
Eight steps, and 12px is the floor:

    12    label     mono, .13em, uppercase   -> text-xs
    13.5  small                              -> text-sm
    15    body                               -> text-base
    17    h3                                 -> text-lg
    19    card title                         -> text-xl
    22    h2                                 -> text-2xl
    28    h1                                 -> text-3xl
    32    numeric   mono, tabular            -> text-4xl
    40    display                            -> text-5xl

The platform had eight sizes between 9px and 24px - a page title only
24px while labels sat at 9px. Illegible at the bottom, no authority at
the top, no ratio connecting them. Anything under 12px moves to 12px:
letterspaced 12px mono reads smaller than it measures, which is how the
9px labels retire without the page feeling louder.

RADIUS
------
Two values plus a pill. <=7px becomes the 6px control radius, 8-16px
becomes the 10px panel radius, 999px/9999px becomes the pill. 50% is
left alone - a circle is a shape, not a radius, and the Rack's round
knobs need it.

NOT SWEPT
---------
The same instrument allowlist as the colour sweep. DESIGN_SYSTEM.md:
"Small type is engraving, not body copy. The 8-10px sizes on the Rack
and the EQ are scale markings on an instrument - frequency labels, dB
ticks. They are correct at that size." Raising those would cost the
hardware look and fix nothing.

tools/tailwind-input.css is also exempt: it is the design system source,
and the component library deliberately runs a few mono micro-labels at
10.5-11.5px exactly as the spec draws them (badge 11px, table header
11.5px, transport caption 10.5px).
"""
import io
import os
import re
import sys
import glob
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_FILES = {
    "templates/_gear.html",
    "templates/rack.html",
    "static/js/rackdsp.js",
    "static/css/artist-eq.css",
    "static/css/tailwind.css",
    "tools/tailwind-input.css",
}

# px -> Tailwind step. Everything under the floor lands on it.
STEP = [
    (12.0, "xs"), (13.5, "sm"), (15.0, "base"), (17.0, "lg"),
    (19.0, "xl"), (22.0, "2xl"), (28.0, "3xl"), (32.0, "4xl"),
    (40.0, "5xl"), (52.0, "6xl"), (64.0, "7xl"), (74.0, "8xl"),
    (88.0, "9xl"),
]
FLOOR = 12.0
# Above this the number is display art (a hero numeral), not type on the
# scale; leaving it alone is the smaller lie.
ART = 88.0


def step_for(px):
    """Nearest step at or above the floor."""
    if px < FLOOR:
        return "xs", FLOOR
    best = min(STEP, key=lambda s: abs(s[0] - px))
    return best[1], best[0]


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def radius_for(v):
    v = v.strip()
    m = re.fullmatch(r'(\d+(?:\.\d+)?)px', v)
    if not m:
        return None
    px = float(m.group(1))
    if px == 0:
        return None
    if px >= 999:
        return "var(--sb-r-pill)"
    if px <= 7:
        return "var(--sb-r-control)"
    if px <= 16:
        return "var(--sb-r-panel)"
    return "var(--sb-r-panel)"


def sweep(s, path):
    counts = collections.Counter()

    # --- Tailwind text-[Npx] -> the scale ------------------------------
    def t_sub(m):
        px = float(m.group(1))
        if px > ART:
            return m.group(0)
        name, landed = step_for(px)
        counts["text %gpx -> text-%s (%gpx)" % (px, name, landed)] += 1
        return "text-" + name

    s = re.sub(r'\btext-\[(\d+(?:\.\d+)?)px\]', t_sub, s)

    # --- Tailwind rounded-[..] -> the two values ------------------------
    def r_sub(m):
        side, val = m.group(1) or "", m.group(2)
        px = None
        mm = re.fullmatch(r'(\d+(?:\.\d+)?)px', val.strip())
        if mm:
            px = float(mm.group(1))
        else:
            mm = re.fullmatch(r'(\d+(?:\.\d+)?)rem', val.strip())
            if mm:
                px = float(mm.group(1)) * 16
        if px is None:
            return m.group(0)
        if px >= 999:
            cls, landed = "rounded%s-full" % side, 999
        elif px <= 7:
            cls, landed = "rounded%s" % side, 6
        else:
            cls, landed = "rounded%s-lg" % side, 10
        counts["radius %s -> %s (%gpx)" % (val, cls, landed)] += 1
        return cls

    s = re.sub(r'\brounded(-[trbl]{1,2})?-\[([^\]]+)\]', r_sub, s)

    # --- CSS / inline-style font-size ----------------------------------
    def cf_sub(m):
        px = float(m.group(2))
        if px >= FLOOR or px > ART:
            return m.group(0)
        counts["css font-size %gpx -> 12px" % px] += 1
        return "%s12px" % m.group(1)

    s = re.sub(r'(font-size\s*:\s*)(\d+(?:\.\d+)?)px', cf_sub, s)

    # --- CSS / inline-style border-radius ------------------------------
    def cr_sub(m):
        head, val = m.group(1), m.group(2)
        tok = radius_for(val)
        if not tok:
            return m.group(0)
        counts["css radius %s -> %s" % (val.strip(), tok)] += 1
        return head + tok

    s = re.sub(r'(border-radius\s*:\s*)([^;\n}"\']+)', cr_sub, s)
    return s, counts


def main():
    dry = "--dry-run" in sys.argv
    files = []
    for pat in ("templates/**/*.html", "static/css/*.css",
                "static/js/*.js", "*.py"):
        files += glob.glob(os.path.join(ROOT, pat), recursive=True)
    files = [f for f in files if rel(f) not in SKIP_FILES
             and not rel(f).startswith("tests/")]

    total = collections.Counter()
    changed = collections.Counter()
    for p in sorted(files):
        s = io.open(p, encoding="utf8", errors="ignore").read()
        new, counts = sweep(s, rel(p))
        if new != s:
            total.update(counts)
            changed[rel(p)] = sum(counts.values())
            if not dry:
                io.open(p, "w", encoding="utf8", newline="").write(new)

    print("%s %d files, %d values normalised"
          % ("WOULD CHANGE" if dry else "CHANGED", len(changed), sum(total.values())))
    print("\nby rule:")
    for k, n in total.most_common(30):
        print("  %5d  %s" % (n, k))
    print("\nbusiest files:")
    for p, n in changed.most_common(15):
        print("  %5d  %s" % (n, p))


if __name__ == "__main__":
    main()
