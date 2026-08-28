# -*- coding: utf-8 -*-
"""Replace hardcoded colours with design-system tokens.

Design system v1, step 3. Re-runnable and idempotent: running it twice
changes nothing the second time, so it can be used to sweep whatever
drifts back in.

    python tools/sweep_colours.py --dry-run     # report only
    python tools/sweep_colours.py               # write

Three output shapes, because the platform styles itself three ways:

  * a Tailwind arbitrary class   bg-[#141210]      -> bg-sb-surface-2
  * a CSS or inline-style value  color:#e8c667     -> color:var(--sb-gold-bright)
  * an SVG attribute or JS       fill="#c9a24a"    -> fill="#C9A24A"

The third case keeps a literal because `fill="var(--x)"` is not valid as
an SVG presentation attribute - only as a CSS declaration. So the rule the
CI check enforces is "every hex is a token hex", not "no hex exists".

WHAT IS DELIBERATELY NOT SWEPT
------------------------------
Not every colour in this repo is chrome. Three kinds are data or are
covered by a standing decision, and tokenising them would be a bug:

  * Stage colours. static/js/lights*.js and the cue swatches carry the
    colours an operator picked for the lamps. #FF0000 there means the
    bar goes red, not "critical".
  * Artwork and cover palettes (artwork_config.py, discover_config.py).
    Same reason: those are output, not interface.
  * The Rack and EQ instrument surfaces (_gear.html, rack.html,
    rackdsp.js, artist-eq.css). DESIGN_SYSTEM.md already rules on this:
    the engraved legends and chassis darks are an instrument face, and
    flattening them onto the UI ramp costs the hardware look. They keep
    their palette and the CI check allowlists it.

Third-party brand marks (Spotify green, Apple Music red) are never
swept either - a brand colour is a fact about someone else's brand.
"""
import io
import os
import colorsys
import re
import sys
import glob
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- the tokens -----------------------------------------------------------
TOKENS = {
    "ground": "#0B0A08",
    "surface-1": "#131110",
    "surface-2": "#1A1714",
    "surface-3": "#221D18",
    "line": "#2A241C",
    "line-strong": "#3A3226",
    "ink": "#F2ECE0",
    "ink-2": "#A99B84",
    "ink-3": "#91836A",
    "gold": "#C9A24A",
    "gold-bright": "#E8B950",
    "gold-deep": "#8A6E30",
    "on-gold": "#14100A",
    "good": "#79B473",
    "warn": "#E8843F",
    "crit": "#E05C4A",
    "info": "#7FA8E8",
}

# --- hexes that are somebody else's brand, or are data -------------------
KEEP = {
    "#1db954",  # Spotify
    "#fa243c",  # Apple Music
    "#ff0000",  # YouTube
    "#005eb8",  # Deezer
    "#635bff",  # Stripe
    "#ff5500",  # SoundCloud
    "#000000", "#ffffff",  # structural: masks, print, pure-white rules
    # The stage-colour picker's own hue wheel (light-studio.css). These
    # are the lamp, not the interface - snapping them to the ramp would
    # leave the colour picker unable to pick a colour.
    "#ff0000", "#00ff00", "#0000ff", "#00ffff", "#ff00ff", "#ffff00",
}

# --- files whose colours are data or a ruled-on exception ----------------
SKIP_FILES = {
    "static/js/lights.js",
    "static/js/lights-engine.js",
    "static/js/lights-remote.js",
    "static/js/rackdsp.js",
    "static/css/artist-eq.css",
    "templates/_gear.html",
    "templates/rack.html",
    "artwork_config.py",
    "discover_config.py",
    "network_config.py",   # Mintable Moments gradient pairs - artwork, not chrome
    "lights_store.py",     # gap_color is a lamp colour, not a surface
    "epk_config.py",       # bg_color is the artist's cover colour
}

# --- the reviewed map ----------------------------------------------------
# Everything appearing three or more times, plus every stock Tailwind hex
# the platform had drifted into. Grouped by what the colour was doing.
EXPLICIT = {}


def _add(token, *hexes):
    for h in hexes:
        EXPLICIT[h.lower()] = token


# grounds: four drifting blacks, some cool, some warm, no elevation logic
_add("ground",
     "#0a0a0a", "#0a0a09", "#0a0a0b", "#090908", "#080807", "#0b0a08",
     "#0b0b0c", "#0b0a09", "#0b0b0a", "#0c0b08", "#0c0a09", "#0c0b09",
     "#0d0c0a", "#0d0c09", "#0d0d0f", "#070708", "#08080a", "#0a0908",
     "#0f0e0c", "#0f0e0b", "#0e0d0a", "#0e0d0b", "#0d0c0b", "#101010",
     "#111111", "#0f172a")
# surface 1: cards and the sidebar
_add("surface-1",
     "#111113", "#100f0c", "#121210", "#111013", "#131010", "#11110f",
     "#12100c", "#0f0f11", "#0e0e10", "#111114", "#131110", "#100f0e",
     "#141416", "#0b0b0e")
# surface 2: the warm money/signal panel and the raised card
_add("surface-2",
     "#141210", "#141209", "#14120e", "#151310", "#15130f", "#17150f",
     "#1b1813", "#1a1712", "#18181b", "#1a1a1c", "#1a1714", "#15130c",
     "#17171a", "#161612")
# surface 3: hover ground, chips, wells
_add("surface-3",
     "#221d18", "#26262a", "#232327", "#2a2a2e", "#2b2b2e", "#2c2820",
     "#2a251d", "#262626", "#242024")
# lines
_add("line", "#2a241c", "#2e2920", "#2d2820")
_add("line-strong",
     "#3a3226", "#3a3424", "#3a3426", "#3a352c", "#4a463e", "#4c4536",
     "#4a4438", "#4a4234", "#3f3a30")
# ink
_add("ink",
     "#eee8dc", "#f7f5f0", "#eee9df", "#efe9dc", "#ede7da", "#f2eee6",
     "#faf8f3", "#fbf9f4", "#efece5", "#e8e6e1", "#eceae3", "#f4f1ea",
     "#f2ece0", "#f5f5f4", "#fafaf9", "#f3f4f6", "#e5e7eb", "#f9fafb")
_add("ink-2",
     "#a7a198", "#a29b90", "#b3a684", "#c9bd9c", "#9e978c", "#a8a39a",
     "#c2bbae", "#b3ac9e", "#d7d1c6", "#dcd6c9", "#d9d6cc", "#cfc6b0",
     "#d8cdb4", "#ded8cb", "#a99e88", "#a99b84", "#d1d5db", "#d6d3d1",
     "#9ca3af", "#a8a29e")
_add("ink-3",
     "#7e786f", "#8a7c5d", "#5a544a", "#6b6459", "#797369", "#8b857b",
     "#6d6450", "#6b665b", "#5c564c", "#6b6355", "#8a8069", "#8a8a92",
     "#6b7280", "#6e6350", "#78716c", "#737373", "#71717a")
# gold: one ramp, three roles
_add("gold", "#c9a24a", "#c9a86a", "#a77b4a")
_add("gold-bright",
     "#e8c667", "#d8b25a", "#e5c878", "#eac97c", "#eecd7c", "#e6c675",
     "#e1c48f", "#e0c48c", "#dcc08a", "#f2dc96", "#e2c692", "#fde047",
     "#eab308", "#f59e0b", "#ffb347", "#e8b950", "#facc15", "#fbbf24",
     "#f0dcae", "#fff4d0", "#f3ead2")
_add("gold-deep",
     "#a8862f", "#8a6d1f", "#a37c2a", "#7c6220", "#7a5c17", "#5c4a1e",
     "#6b5c3d", "#8a6e30", "#b45309", "#92400e")
# dark ink that sits on brass
_add("on-gold", "#1c1302", "#161207", "#14100a", "#1a170d", "#131002")
# state
_add("good",
     "#22c55e", "#4ade80", "#7fcf8a", "#7ee083", "#16a34a", "#10b981",
     "#34d399", "#79b473", "#064e3b", "#065f46")
_add("crit",
     "#ef4444", "#ff2d2d", "#b91c1c", "#7f1d1d", "#b23227", "#f0a58e",
     "#dc2626", "#e05c4a", "#f87171", "#831843", "#991b1b")
_add("warn",
     "#ff7a00", "#ff4a1c", "#f5871f", "#a05a2c", "#7c2d12", "#f97316",
     "#ea580c", "#e8843f", "#fb923c", "#e07a3c")
_add("info",
     "#3b82f6", "#1e3a8a", "#0e7490", "#1e1b4b", "#8b5cf6", "#60a5fa",
     "#7fa8e8", "#2563eb", "#0ea5e9", "#38bdf8", "#a78bfa")

# --- Tailwind arbitrary class -> named token class ------------------------
# A token's own value maps to itself, so a re-run reports nothing.
for _t, _h in TOKENS.items():
    EXPLICIT.setdefault(_h.lower(), _t)

CLASS_TOKEN = {t: "sb-" + t for t in TOKENS}

# utility prefixes that take a colour
PREFIXES = ("bg", "text", "border", "border-t", "border-b", "border-l",
            "border-r", "border-x", "border-y", "ring", "ring-offset",
            "outline", "fill", "stroke", "from", "via", "to", "shadow",
            "decoration", "caret", "accent", "divide", "placeholder")

# The negative lookahead keeps href="#add-show" and #fade-in out of
# the colour set - "#add" is a valid three-digit hex on its own.
_HEX = r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z_-])'


def norm(h):
    h = h.lower()
    if len(h) == 4:
        h = "#" + "".join(c * 2 for c in h[1:])
    return h


def _rgb(h):
    h = norm(h).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# The elevation ladder and the ink ramp - what a NEUTRAL can become.
_NEUTRAL_TOKENS = ("ground", "surface-1", "surface-2", "surface-3",
                   "line", "line-strong", "ink-3", "ink-2", "ink", "on-gold")
# The accent and state families - what a CHROMATIC colour can become.
_CHROMA_TOKENS = ("gold", "gold-bright", "gold-deep",
                  "good", "warn", "crit", "info")


def _hsl(h):
    r, g, b = [x / 255.0 for x in _rgb(h)]
    return colorsys.rgb_to_hls(r, g, b)


def _nearest(h):
    """Snap a colour with no entry in the reviewed map to the closest
    token.

    The reviewed map covers the ~90% of literals that appear three or
    more times. The tail is one-offs - a grey that drifted three shades
    cool, a green somebody typed from memory - and hand-classifying 137
    of those buys nothing this does not.

    The split matters more than the metric. A near-neutral is asking
    "which rung of the elevation ladder am I on?", which is a lightness
    question. A chromatic colour is asking "which state am I?", which is
    a hue question. Judging both by RGB distance is how #3F6C45, a
    green, comes out as gold-deep.
    """
    hue, light, sat = _hsl(h)
    # Absolute chroma, not HLS saturation. #E4DFD5 is a near-white cream
    # with 6% chroma but 22% "saturation", and saturation sends it to the
    # gold ramp; chroma correctly calls it an ink.
    r, g, b = _rgb(h)
    chroma = (max(r, g, b) - min(r, g, b)) / 255.0
    chromatic = chroma >= 0.12
    pool = _CHROMA_TOKENS if chromatic else _NEUTRAL_TOKENS

    best, bestd = None, None
    for name in pool:
        th, tl, ts = _hsl(TOKENS[name])
        if chromatic:
            # circular hue distance dominates; lightness breaks ties
            dh = abs(hue - th)
            dh = min(dh, 1.0 - dh)
            d = (dh * 4.0) ** 2 + (light - tl) ** 2
        else:
            d = (light - tl) ** 2 + (sat - ts) ** 2 * 0.15
        if bestd is None or d < bestd:
            best, bestd = name, d
    return best


SNAPPED = collections.Counter()


def token_for(h):
    t = EXPLICIT.get(norm(h))
    if t:
        return t
    t = _nearest(h)
    SNAPPED[(norm(h), t)] += 1
    return t


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


# A line (or the line above it) carrying this marker is left alone. For
# colours that are data sitting inside a file that is otherwise chrome -
# the Light Studio gel book lives in app.py next to ordinary UI colours,
# and snapping it onto the ramp made two different gels the same colour.
KEEP_MARK = "sb-keep"


def _protected_lines(s):
    """Line numbers covered by a marker: the marker's own line and the
    six below it, which is enough to cover a short literal block."""
    out = set()
    for i, line in enumerate(s.splitlines()):
        if KEEP_MARK in line:
            out.update(range(i, i + 7))
    return out


def sweep_text(s, path):
    """Returns (new_text, Counter of hex -> count replaced)."""
    hits = collections.Counter()
    protected = _protected_lines(s)

    def _is_protected(idx):
        return s.count(chr(10), 0, idx) in protected

    is_css = path.endswith(".css")
    is_py = path.endswith(".py")

    # 1. Tailwind arbitrary colour classes, opacity suffix preserved.
    cls_re = re.compile(
        r'\b(' + "|".join(sorted(PREFIXES, key=len, reverse=True)) +
        r')-\[(' + _HEX + r')\](/\d{1,3})?')

    def cls_sub(m):
        pre, hexv, op = m.group(1), m.group(2), m.group(3) or ""
        if _is_protected(m.start()):
            return m.group(0)
        if norm(hexv) in KEEP:
            return m.group(0)
        t = token_for(hexv)
        if not t:
            return m.group(0)
        hits[norm(hexv)] += 1
        return "%s-%s%s" % (pre, CLASS_TOKEN[t], op)

    s = cls_re.sub(cls_sub, s)

    # 2. Remaining bare hexes.
    #    A CSS declaration - a .css file, a <style> block, or a style=""
    #    attribute - takes var(). An SVG presentation attribute cannot:
    #    fill="var(--x)" is not valid markup, only fill:var(--x) in CSS is.
    #    Those, plus JS and the Python class strings, take the canonical
    #    literal, which is what makes "every hex is a token hex" the rule
    #    the CI check can actually enforce.
    style_spans = [(m.start(), m.end()) for m in
                   re.finditer(r'<style\b[^>]*>.*?</style>', s, re.S | re.I)]

    def in_style_block(i):
        return any(a <= i < b for a, b in style_spans)

    def in_style_attr(i):
        j = s.rfind('style="', max(0, i - 400), i)
        return j != -1 and '"' not in s[j + 7:i]

    def bare_sub(m):
        hexv = m.group(0)
        if _is_protected(m.start()):
            return m.group(0)
        n = norm(hexv)
        if n in KEEP:
            return hexv
        t = token_for(hexv)
        if not t:
            return hexv
        hits[n] += 1
        i = m.start()
        css_context = is_css or (not is_py and (in_style_block(i) or in_style_attr(i)))
        if css_context:
            return "var(--sb-%s)" % t
        return TOKENS[t]

    s = re.sub(_HEX + r'\b', bare_sub, s)
    return s, hits


def main():
    dry = "--dry-run" in sys.argv
    files = []
    for pat in ("templates/**/*.html", "static/css/*.css",
                "static/js/*.js", "*.py"):
        files += glob.glob(os.path.join(ROOT, pat), recursive=True)
    files = [f for f in files
             if rel(f) not in SKIP_FILES
             and rel(f) != "static/css/tailwind.css"
             and not rel(f).startswith("tools/")
             and not rel(f).startswith("tests/")]

    total = collections.Counter()
    changed = []
    for p in sorted(files):
        s = io.open(p, encoding="utf8", errors="ignore").read()
        new, hits = sweep_text(s, rel(p))
        if new != s:
            changed.append((rel(p), sum(hits.values())))
            total.update(hits)
            if not dry:
                io.open(p, "w", encoding="utf8", newline="").write(new)

    print("%s %d files, %d colour literals -> tokens"
          % ("WOULD CHANGE" if dry else "CHANGED", len(changed), sum(total.values())))
    print("\ntop replacements:")
    for h, n in total.most_common(24):
        print("  %5d  %s -> --sb-%s" % (n, h, EXPLICIT.get(h, _nearest(h))))
    print("\nbusiest files:")
    for p, n in sorted(changed, key=lambda x: -x[1])[:18]:
        print("  %5d  %s" % (n, p))
    if SNAPPED:
        print("\nsnapped to the nearest token (no reviewed entry - these "
              "are the one-offs):")
        for (h, t), n in SNAPPED.most_common(50):
            print("  %5d  %s -> --sb-%s" % (n, h, t))


if __name__ == "__main__":
    main()
