# -*- coding: utf-8 -*-
"""The design system, enforced.

Design system v1 (22 Aug 2026) replaced an absence of decisions with a
fixed set: one gold ramp, one ink ramp, eight type steps with a 12px
floor, two radii plus a pill. None of that survives contact with a busy
repo unless something fails when it drifts, so this is that something.

    python -m pytest tests/test_design_system.py -q

Four rules:

  1. Every colour literal is a token value. Not "no hex exists" - an SVG
     presentation attribute cannot take var(), so fill="#C9A24A" has to
     stay a literal - but every literal must be one of the seventeen
     token values, or explicitly allowlisted below.
  2. No font-size below 12px.
  3. No border-radius outside {6px, 10px, 999px} (plus 0 and 50%).
  4. ink-2 and ink-3 clear WCAG AA on every surface, measured.

WHAT IS ALLOWLISTED, AND WHY
----------------------------
Three kinds of colour in this repo are not interface chrome, and
tokenising them would be a bug rather than a fix:

  * Stage colours (static/js/lights*.js, lights_store.py). #FF0000 there
    means the bar goes red, not "critical".
  * Artwork and cover palettes (artwork_config.py, discover_config.py,
    network_config.py, artwork.html). Output, not interface.
  * The Rack and EQ instrument faces. DESIGN_SYSTEM.md rules on this
    already: "Small type is engraving, not body copy. The 8-10px sizes
    on the Rack and the EQ are scale markings on an instrument." A
    blanket raise would cost the hardware look and fix nothing.

Third-party brand marks are allowlisted too - Spotify's green is a fact
about Spotify, not a decision this system gets to make.
"""
import io
import os
import re
import glob
import collections

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- the tokens, read from the source rather than restated ---------------
TOKEN_CSS = os.path.join(HERE, "tools", "tailwind-input.css")


def _tokens():
    s = io.open(TOKEN_CSS, encoding="utf8").read()
    return {m.group(1).lower()
            for m in re.finditer(r'--sb-[a-z0-9-]+:\s*(#[0-9a-fA-F]{6})', s)}


TOKENS = _tokens()

ALLOWED_HEX = TOKENS | {
    # structural: masks, print, pure-white hairlines
    "#000000", "#ffffff", "#fff", "#000",
    # third-party brand marks
    "#1db954",  # Spotify
    "#fa243c",  # Apple Music
    "#ff0000",  # YouTube
    "#005eb8",  # Deezer
    "#635bff",  # Stripe
    "#ff5500",  # SoundCloud
    # The stage-colour picker's own hue wheel (light-studio.css). These
    # are the lamp, not the interface - a hue slider made of tokens
    # cannot pick a hue.
    "#00ff00", "#0000ff", "#00ffff", "#ff00ff", "#ffff00",
}

# Files whose colours are data, or are a ruled-on exception.
EXEMPT = {
    "static/js/lights.js",
    "static/js/lights-engine.js",
    "static/js/lights-remote.js",
    "static/js/rackdsp.js",
    "static/css/artist-eq.css",
    "static/css/tailwind.css",          # generated
    "tools/tailwind-input.css",         # the token source itself
    "templates/_gear.html",
    "templates/rack.html",
    "templates/artwork.html",
    "artwork_config.py",
    "discover_config.py",
    "network_config.py",
    "lights_store.py",
    "epk_config.py",      # the artist's cover colour, not a surface
}

# The component library runs a handful of mono micro-labels below 12px
# exactly as the spec draws them (badge 11px, table header 11.5px,
# transport caption 10.5px). Those are reviewed; ad-hoc ones are not.
TYPE_EXEMPT = EXEMPT | {"tools/tailwind-input.css"}

RADII = {"0", "0px", "50%", "6px", "10px", "999px",
         "var(--sb-r-control)", "var(--sb-r-panel)", "var(--sb-r-pill)",
         "inherit", "initial", "unset"}

# The negative lookahead keeps href="#add-show" out of the colour set:
# "#add" is a perfectly good three-digit hex on its own, and \b does not
# stop at a hyphen.
HEX = re.compile(r'#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z_-])')


def _files():
    out = []
    for pat in ("templates/**/*.html", "static/css/*.css",
                "static/js/*.js", "*.py"):
        out += glob.glob(os.path.join(HERE, pat), recursive=True)
    return [p for p in out if _rel(p) not in EXEMPT
            and not _rel(p).startswith("tests/")
            and not _rel(p).startswith("tools/")]


def _rel(p):
    return os.path.relpath(p, HERE).replace("\\", "/")


def _read(p):
    return io.open(p, encoding="utf8", errors="ignore").read()


# --- 1. every colour literal is a token value ---------------------------

def test_no_raw_hex_outside_the_token_set():
    offenders = collections.defaultdict(list)
    for p in _files():
        src = _read(p)
        lines = src.split("\n")
        for m in HEX.finditer(src):
            h = m.group(0).lower()
            if len(h) == 4:
                h = "#" + "".join(c * 2 for c in h[1:])
            if h in ALLOWED_HEX:
                continue
            # An `# sb-keep` marker on the line, or within the three
            # lines above it, opts a colour out: it is data rather than
            # chrome. The Light Studio gel book earned this - it lives in
            # app.py beside ordinary UI colours, and snapping it onto the
            # ramp made "Cold blue" and "Violet haze" the same colour.
            ln = src.count("\n", 0, m.start())
            if any("sb-keep" in lines[j]
                   for j in range(max(0, ln - 6), ln + 1)):
                continue
            offenders[_rel(p)].append("%s:%d" % (h, ln + 1))
    assert not offenders, (
        "%d file(s) carry colour literals that are not design tokens.\n"
        "Run `python tools/sweep_colours.py` to map them, or add a "
        "deliberate exception to ALLOWED_HEX / EXEMPT with a reason.\n%s"
        % (len(offenders),
           "\n".join("  %s: %s" % (f, ", ".join(v[:6]))
                     for f, v in sorted(offenders.items())[:12])))


def test_the_two_deleted_colours_stay_deleted():
    """#F59E0B is Tailwind's amber-500, which shipped alongside the real
    brand gold; #22C55E is stock Tailwind green. Both are gone, and the
    theme repoints the class names so they cannot come back by writing
    `text-amber-500` either."""
    banned = {"#f59e0b": "Tailwind amber-500, not the brand gold",
              "#22c55e": "stock Tailwind green, not the state green",
              "#0a0a0a": "one of the four drifting blacks",
              "#111113": "one of the four drifting blacks",
              "#17171a": "one of the four drifting blacks",
              "#141210": "one of the four drifting blacks"}
    found = []
    for p in _files():
        s = _read(p).lower()
        for h, why in banned.items():
            if h in s:
                found.append("%s in %s (%s)" % (h, _rel(p), why))
    assert not found, "deleted colours are back:\n  " + "\n  ".join(found[:12])


def test_the_tailwind_theme_repoints_the_stock_families():
    """The templates say `text-amber-500` in hundreds of places. The
    theme is what makes that land on the brand gold instead of
    Tailwind's orange, so no stock family may resolve to a stock value.

    Checked against whatever the build actually generated rather than a
    fixed list: a class nobody uses gets purged, and a purged class is
    not a regression."""
    css = _read(os.path.join(HERE, "static", "css", "tailwind.css"))

    # Tailwind's own values for the families the theme takes over. If any
    # of these survive, the theme is not being applied.
    STOCK = {"245 158 11": "amber-500", "34 197 94": "green-500",
             "239 68 68": "red-500", "59 130 246": "blue-500",
             "107 114 128": "gray-500", "251 191 36": "amber-400",
             "74 222 128": "green-400", "156 163 175": "gray-400"}
    found = [name for rgb, name in STOCK.items() if rgb in css]
    assert not found, (
        "stock Tailwind palette values are still in the build (%s) - the "
        "theme is not repointing the families" % ", ".join(sorted(found)))

    # And spot-check that a family the templates DO use landed on a token.
    m = re.search(r'\.text-amber-500\{[^}]*\}', css)
    assert m and "201 162 74" in m.group(0), \
        "text-amber-500 is not the brand gold: %s" % (m.group(0) if m else None)


# --- 2. the 12px floor ---------------------------------------------------

def test_no_font_size_below_twelve_px():
    offenders = collections.defaultdict(list)
    for p in _files():
        if _rel(p) in TYPE_EXEMPT:
            continue
        s = _read(p)
        for m in re.finditer(r'font-size\s*:\s*(\d+(?:\.\d+)?)px', s):
            if float(m.group(1)) < 12:
                offenders[_rel(p)].append(m.group(1) + "px")
        # sizes hiding inside the `font:` shorthand
        for m in re.finditer(r'font\s*:[^;}]*?\b(\d+(?:\.\d+)?)px/', s):
            if float(m.group(1)) < 12:
                offenders[_rel(p)].append(m.group(1) + "px (shorthand)")
        # Tailwind arbitrary values
        for m in re.finditer(r'\btext-\[(\d+(?:\.\d+)?)px\]', s):
            if float(m.group(1)) < 12:
                offenders[_rel(p)].append("text-[%spx]" % m.group(1))
    assert not offenders, (
        "type below the 12px floor. Letterspaced 12px mono reads smaller "
        "than it measures - use it (or `sb-label`) instead.\n%s"
        % "\n".join("  %s: %s" % (f, ", ".join(sorted(set(v))[:6]))
                    for f, v in sorted(offenders.items())[:12]))


# --- 3. two radii plus a pill -------------------------------------------

def test_radius_is_one_of_three_values():
    offenders = collections.defaultdict(list)
    for p in _files():
        s = _read(p)
        for m in re.finditer(r'border-radius\s*:\s*([^;\n}"\']+)', s):
            v = m.group(1).strip().rstrip(";")
            if " " in v:          # compound corners, e.g. "0 10px 10px 0"
                parts = [x for x in v.split() if x not in RADII]
                if parts:
                    offenders[_rel(p)].append(v)
                continue
            if v not in RADII:
                offenders[_rel(p)].append(v)
        for m in re.finditer(r'\brounded(?:-[trbl]{1,2})?-\[([^\]]+)\]', s):
            offenders[_rel(p)].append("rounded-[%s]" % m.group(1))
    assert not offenders, (
        "corner radii outside {6px control, 10px panel, 999px pill}:\n%s"
        % "\n".join("  %s: %s" % (f, ", ".join(sorted(set(v))[:6]))
                    for f, v in sorted(offenders.items())[:12]))


# --- 4. contrast, measured rather than asserted -------------------------

def _lum(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
         for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _token(name):
    s = io.open(TOKEN_CSS, encoding="utf8").read()
    m = re.search(r'--sb-%s:\s*(#[0-9a-fA-F]{6})' % re.escape(name), s)
    assert m, "token --sb-%s not found" % name
    return m.group(1)


def test_every_ink_clears_aa_on_every_surface():
    """ink-2 and ink-3 both carry body-sized and label-sized text, so
    both need 4.5:1 - the large-text 3:1 allowance does not apply to a
    12px label. This is the test that caught the spec's own #6E6350 at
    2.84:1 on surface-3."""
    surfaces = {n: _token(n) for n in
                ("ground", "surface-1", "surface-2", "surface-3")}
    fails = []
    for ink in ("ink", "ink-2", "ink-3"):
        for sname, shex in surfaces.items():
            r = _ratio(_token(ink), shex)
            if r < 4.5:
                fails.append("%s on %s = %.2f:1" % (ink, sname, r))
    assert not fails, "below WCAG AA (4.5:1):\n  " + "\n  ".join(fails)


def test_state_and_brand_colours_clear_aa_on_every_surface():
    surfaces = [_token(n) for n in
                ("ground", "surface-1", "surface-2", "surface-3")]
    fails = []
    for name in ("gold", "gold-bright", "good", "warn", "crit", "info"):
        for s in surfaces:
            r = _ratio(_token(name), s)
            if r < 4.5:
                fails.append("%s on %s = %.2f:1" % (name, s, r))
    assert not fails, "below WCAG AA (4.5:1):\n  " + "\n  ".join(fails)


def test_the_paper_surface_clears_aa():
    """Signal and the Operator Desk are the platform's one light surface -
    internal desks meant to read as paper. The colour sweep initially
    flattened them onto the dark ramp (paper became --sb-ink, body text
    became --sb-surface-2), which happened to look right and said
    something false. They have their own tokens now, and those need the
    same contrast floor as everything else."""
    fails = []
    for ink in ("paper-ink", "paper-ink-2", "paper-ink-3", "paper-gold"):
        for ground in ("paper", "paper-panel"):
            r = _ratio(_token(ink), _token(ground))
            if r < 4.5:
                fails.append("%s on %s = %.2f:1" % (ink, ground, r))
    assert not fails, "paper below WCAG AA (4.5:1):\n  " + "\n  ".join(fails)


def test_text_on_the_gold_button_clears_aa():
    r = _ratio(_token("on-gold"), _token("gold"))
    assert r >= 4.5, "on-gold on gold = %.2f:1" % r


# --- the pieces that make the system reachable at all -------------------

def test_the_typefaces_are_loaded_everywhere_a_head_exists():
    missing = []
    for p in glob.glob(os.path.join(HERE, "templates", "**", "*.html"),
                       recursive=True):
        if _rel(p) == "templates/_fonts.html":
            continue          # the partial itself; its comment says <head>
        s = _read(p)
        if "<head>" in s and "_fonts.html" not in s:
            missing.append(_rel(p))
    assert not missing, (
        "templates with their own <head> and no webfonts: %s" % missing)


def test_no_template_has_an_unterminated_tag():
    """A sweep that rewrites a tag has to put the closing `>` back.

    `tools/gold_discipline.py` did not, and thirteen demoted chips became
    `<span class="..."</span>` - unterminated tags that swallow whatever
    follows them, including the unread notification count. Nothing throws;
    the content just vanishes.

    NARROW ON PURPOSE, AND NOT THE GENERAL CHECK. This only sees a tag
    whose `class` is the LAST attribute, which was the exact shape
    gold_discipline produced. The v1 colour sweep broke the same way one
    attribute later - `<div class="..." style="width: 40%;"</div>` - and
    this regex passed all nineteen of them, because `class="..."` there is
    followed by a space. The structural walk that catches any shape is
    `tests/test_template_markup.py`; keep this one for the regression it
    names, but do not read it as coverage."""
    bad = re.compile(r'<(\w+)([^<>]*?)class="([^"{}]*)"(?![\s>/])')
    offenders = []
    for p in glob.glob(os.path.join(HERE, "templates", "**", "*.html"),
                       recursive=True):
        s = _read(p)
        for m in bad.finditer(s):
            # `class="x"{% if %} ... {% endif %}>` is valid Jinja, and a
            # class attribute built inside a JS string is not markup.
            after = s[m.end():m.end() + 3]
            if after.startswith(("{%", "{{")):
                continue
            before = s[max(0, m.start() - 120):m.start()]
            if "'" in before.split("\n")[-1] or '"' in before.split("\n")[-1]:
                continue
            offenders.append("%s:%d" % (_rel(p),
                                        s.count("\n", 0, m.start()) + 1))
    assert not offenders, "unterminated tags: %s" % offenders


def test_every_class_a_script_selects_still_exists():
    """A class can be a JavaScript hook as easily as a style.

    `tools/adopt_controls.py` rebuilt button class lists from an allowlist
    of layout utilities, which threw away everything it did not
    recognise - including `kit-copy` and `add-to-catalog`, the classes
    those pages' scripts use to find their buttons. The features went
    dead and nothing logged. If a script selects a class, something in
    the tree has to be able to put that class on an element.

    WIDENED, AND EVERY WIDENING WAS EARNED BY A MISS
    ------------------------------------------------
    The first version matched only a selector string that ENDED at the
    class name - `querySelectorAll(".song-row")` - and then looked the
    name up in the raw text of every template. Both halves let the same
    dead selector through, and they covered for each other:

      * `document.querySelector(`.song-row[data-song-id="${id}"]`)` was
        invisible three times over. The pattern `querySelectorAll?`
        makes only the final `l` optional, so it matched
        `querySelectorAll(` and the nonexistent `querySelectorAl(` but
        never a singular `querySelector(`. The argument is a template
        literal, not a quoted string. And the class name is followed by
        an attribute filter rather than by the closing quote the
        pattern demanded.
      * Because that occurrence never matched, it was never stripped out
        of the corpus either. So `song-row` was still sitting in the text
        the check searched, and the plain `.song-row` selector three
        dozen lines above it passed - by finding its own dead sibling.

    Hence: parse class names out of the WHOLE selector, whatever follows
    them, and check them against the classes the markup can actually
    CARRY - class attributes, classList writes, className assignments -
    instead of against raw file text, where a selector string counts as
    evidence of itself. The carry set has no such circularity to strip:
    a `querySelector` call is not a place a class can be applied, so it
    never enters the set to begin with.
    """
    # Selectors that were already dead before this migration - the markup
    # they target was removed at some point and the handler was left
    # behind. Recorded rather than silently passed; they are pre-existing
    # dead code, not something a sweep broke.
    #
    # The three `.vlv-*` elements lost their markup in the Rack refinish
    # (cac5d4d) while every read of them stayed null-guarded. (`song-row`,
    # `song-view-btn`, `smart-rec-row` and `alert-card` belonged here too.
    # They were the song drawer's only entry points, so the drawer could
    # not be opened from any page; it has been deleted along with them.)
    ALREADY_DEAD = {"vlv-fil", "vlv-halo", "vlv-plate"}

    # The selector argument, whichever quote style it uses - backticks
    # included, which is where the template-literal case hid.
    SEL_CALL = re.compile(r'querySelector(?:All)?\(\s*(["\'`])(.*?)\1', re.S)
    # Attribute VALUES are not selector syntax, and a dot inside one
    # (`[data-x="a.b"]`) is not a class. Drop them before reading classes.
    ATTR_VAL = re.compile(r'''=\s*(["'])(?:(?!\1).)*\1''', re.S)
    CLASS_IN_SEL = re.compile(r'\.(-?[A-Za-z_][\w-]*)')

    # The four ways a class actually gets onto an element.
    CLASS_ATTR = re.compile(r'class\s*=\s*(["\'])(.*?)\1', re.S)
    CLASS_LIST = re.compile(
        r'classList\s*\.\s*(?:add|remove|toggle|replace)\s*\((.*?)\)', re.S)
    CLASS_NAME = re.compile(r'className\s*\+?=\s*(["\'`])(.*?)\1', re.S)
    SET_ATTR = re.compile(
        r'setAttribute\(\s*(["\'])class\1\s*,\s*(["\'`])(.*?)\2', re.S)
    STR_LIT = re.compile(r'(["\'`])(.*?)\1', re.S)
    TOKEN = re.compile(r'[A-Za-z_][\w-]*')

    def _selected(src):
        for m in SEL_CALL.finditer(src):
            for c in CLASS_IN_SEL.finditer(ATTR_VAL.sub("=", m.group(2))):
                yield c.group(1)

    # Look across the whole template tree and the scripts, not per file: a
    # partial can render the element a different template's script binds
    # to, which is how `.check-row` works.
    sources = []
    for pat in ("templates/**/*.html", "static/js/*.js"):
        for f in glob.glob(os.path.join(HERE, pat), recursive=True):
            sources.append((_rel(f), _read(f)))

    carried = set()
    for _, s in sources:
        for m in CLASS_ATTR.finditer(s):
            carried.update(TOKEN.findall(m.group(2)))
        for m in CLASS_LIST.finditer(s):
            for lit in STR_LIT.finditer(m.group(1)):
                carried.update(TOKEN.findall(lit.group(2)))
        for m in CLASS_NAME.finditer(s):
            carried.update(TOKEN.findall(m.group(2)))
        for m in SET_ATTR.finditer(s):
            carried.update(TOKEN.findall(m.group(3)))

    missing = []
    for rel, s in sources:
        for name in _selected(s):
            if name not in ALREADY_DEAD and name not in carried:
                entry = "%s selects .%s" % (rel, name)
                if entry not in missing:
                    missing.append(entry)
    assert not missing, (
        "scripts select classes nothing in the markup can carry - no "
        "class attribute, classList write or className assignment ever "
        "applies them, so the handler binds to nothing and no error is "
        "logged: %s" % missing)


def test_every_page_that_reads_a_token_also_defines_it():
    """`var(--sb-ink)` on a page that never loaded the token layer is not
    a fallback - it is invalid at computed-value time, and the type drops
    to the browser's serif. Eleven templates with their own <head> hit
    exactly this when the module stylesheets moved onto tokens, including
    the login page, so it is worth a test rather than a memory."""
    broken = []
    for p in glob.glob(os.path.join(HERE, "templates", "**", "*.html"),
                       recursive=True):
        s = _read(p)
        if "<head>" not in s or "tailwind.css" in s:
            continue
        needs = "var(--sb-" in s
        for sheet in re.findall(r'/static/css/([a-z0-9-]+\.css)', s):
            f = os.path.join(HERE, "static", "css", sheet)
            if os.path.exists(f) and "var(--sb-" in _read(f):
                needs = True
        if needs:
            broken.append(_rel(p))
    assert not broken, (
        "these pages read design tokens but never load the file that "
        "defines them, so every token reference on them is dead: %s"
        % broken)


def test_the_component_macros_never_nest_an_anchor_in_an_anchor():
    """An <a> inside an <a> is not HTML. The parser closes the outer one
    at the inner one's open tag, and whatever followed falls out of the
    component into the page - which is how the KPI tile's first-step link
    ended up floating in the grid beside its tile on Command Center.

    Render every macro variant that takes an href together with an inner
    link, and walk the result with a real HTML parser rather than a regex."""
    from html.parser import HTMLParser
    from jinja2 import Environment, FileSystemLoader

    class Depth(HTMLParser):
        def __init__(self):
            super().__init__()
            self.open_a = 0
            self.nested = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                if self.open_a:
                    self.nested.append(dict(attrs).get("class", "?"))
                self.open_a += 1

        def handle_endtag(self, tag):
            if tag == "a" and self.open_a:
                self.open_a -= 1

    env = Environment(loader=FileSystemLoader(os.path.join(HERE, "templates")))
    out = env.from_string('''
      {% import "_sb.html" as sb %}
      {{ sb.kpi("Smart link score", href="/links", first="Create your first campaign", first_href="/links/builder") }}
      {{ sb.kpi("Fans", value=12, href="/links/fans", delta="3 hot", direction="up") }}
      {{ sb.kpi("Catalog health", first="Add a track", first_href="/catalog") }}
      {{ sb.module_card("Light Studio", "2 shows", "/lights") }}
      {% call sb.priority("T", "b", severity="crit") %}{{ sb.btn("Fix", href="/x", variant="primary") }}{% endcall %}
    ''').render()
    d = Depth()
    d.feed(out)
    assert not d.nested, "anchors nested inside anchors: %s" % d.nested


def test_the_focus_ring_and_reduced_motion_guard_are_global():
    css = _read(os.path.join(HERE, "static", "css", "tailwind.css"))
    assert "focus-visible" in css and "--sb-focus" in css, \
        "the platform-wide focus ring is missing from the build"
    assert "prefers-reduced-motion" in css, \
        "the reduced-motion guard is missing from the build"


def test_the_component_library_is_in_the_build():
    css = _read(os.path.join(HERE, "static", "css", "tailwind.css"))
    for cls in ("sb-btn", "sb-badge", "sb-kpi", "sb-prio", "sb-mod",
                "sb-tbl", "sb-field", "sb-transport", "sb-cue", "sb-rail",
                "sb-label", "sb-num"):
        assert "." + cls in css, "%s is not in the built stylesheet" % cls
