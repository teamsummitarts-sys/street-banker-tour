"""Section 4 — one system, six departments.

One photograph, six coded slices. The things worth holding still: the
picture stays one file and one description, the six labels stay in order,
the tone stays subtle, and no department hands a signed-out reader a
password field for asking what it does.
"""

import os
import re

from PIL import Image

from app import create_app


def _anon():
    return create_app().test_client()


def _home():
    return _anon().get("/").get_data(as_text=True)


def _section(body=None):
    body = body or _home()
    start = body.index('id="departments"')
    return body[start:start + body[start:].index("</section>")]


def _css():
    return open("static/css/departments.css", encoding="utf-8").read()


# --- the section, and the sections around it -----------------------------

def test_the_section_sits_after_the_eq_and_displaces_nothing():
    body = _home()
    assert 'id="departments"' in body
    assert body.index('id="artist-eq"') < body.index('id="departments"')
    assert body.index('id="departments"') < body.index('id="lanes"')
    # Everything that was on the page before it is still on it.
    for kept in ["Choose your lane.", "Built for artist control.",
                 "TUNE YOUR ARTIST SYSTEM.", "sbhero-veil", "Run a Royalty Sweep",
                 "Your catalog is the "]:
        assert kept in body, kept


def test_the_copy_is_the_approved_copy():
    eq = _section()
    assert "One system. Six departments." in eq
    assert "Everything behind the artist, working together." in eq
    # The headline that was dropped stays dropped.
    assert "Every part of your career" not in _home()
    departments = [
        ("01", "AI Artist Twin", "Evaluate and plan."),
        ("02", "Creative Studio", "Build the visual world."),
        ("03", "Rollout Engine", "Turn the release into a campaign."),
        ("04", "Royalty Sweep", "Find potential missing income."),
        ("05", "Rights", "Protect ownership and metadata."),
        ("06", "Fan Intelligence", "Understand and grow the audience."),
    ]
    names = re.findall(r'sbdept-name">([^<]+)<', eq)
    descs = re.findall(r'sbdept-desc">([^<]+)<', eq)
    nums = re.findall(r'sbdept-num">([^<]+)<', eq)
    assert nums == [d[0] for d in departments]
    assert names == [d[1] for d in departments]
    assert descs == [d[2] for d in departments]
    # One line each: the brief asks for a line, not a paragraph.
    for d in descs:
        assert len(d) <= 40 and d.count(".") == 1, d


def test_it_is_one_photograph_and_one_description():
    eq = _section()
    assert eq.count("<img") == 1, "six slices, one picture"
    alt = re.search(r'alt="([^"]+)"', eq).group(1)
    assert alt == ("Band performing inside a raw studio with artwork and "
                   "equipment surrounding the musicians.")
    for marketing in ("street banker", "department", "royalty", "system",
                      "platform", "artist os"):
        assert marketing not in alt.lower(), marketing
    # Sized up front, so the section never shifts the page while it loads.
    assert 'width="1553" height="676"' in eq
    assert 'loading="lazy"' in eq and 'decoding="async"' in eq


def test_the_picture_ships_in_three_formats_and_four_sizes():
    eq = _section()
    for fmt in ("image/avif", "image/webp"):
        assert 'type="%s"' % fmt in eq, fmt
    for width in (900, 1200, 1553):
        for ext in ("avif", "webp", "jpg"):
            asset = "static/img/departments-%d.%s" % (width, ext)
            assert os.path.exists(asset), asset
            assert "departments-%d.%s %dw" % (width, ext, width) in eq
    assert "sizes=" in eq


def test_every_derivative_is_the_same_photograph_at_the_same_ratio():
    """Six slices reconstruct one image only if every size is the same
    crop: a derivative at a different ratio would put the drummer in two
    slices at one width and one at another."""
    ratios = []
    for width in (900, 1200, 1553):
        for ext in ("avif", "webp", "jpg"):
            with Image.open("static/img/departments-%d.%s" % (width, ext)) as im:
                assert im.size[0] == width, (width, ext, im.size)
                ratios.append(round(im.size[0] / im.size[1], 3))
    # Whole-pixel heights make the ratios differ in the third decimal;
    # anything past that would be a different crop.
    assert max(ratios) - min(ratios) < 0.01, ratios
    assert 2.2 < ratios[0] < 2.4          # the wide editorial panorama


# --- destinations ---------------------------------------------------------

def test_no_department_hands_a_stranger_a_login():
    """A reader asking what a department does must not meet a password
    field. Routes answer signed out; anchors exist on the page."""
    body = _home()
    eq = _section(body)
    hrefs = re.findall(r'class="sbdept-dept" href="([^"]+)"', eq)
    assert len(hrefs) == 6
    client = _anon()
    for href in hrefs:
        if href.startswith("#"):
            assert 'id="%s"' % href[1:] in body, href
        else:
            response = client.get(href)
            assert response.status_code == 200, (href, response.status_code)
            assert "/login" not in response.headers.get("Location", "")


def test_fan_intelligence_is_the_one_department_that_leaves_the_page():
    """Five departments point at the homepage section that covers them.

    Fan Intelligence has no homepage section, so it goes to its public
    example workspace rather than to nothing or to a login wall."""
    eq = _section()
    assert 'href="/product-tour/smart-link#fans"' in eq
    assert _anon().get("/product-tour/smart-link").status_code == 200


# --- what the brief rules out --------------------------------------------

def test_the_section_carries_no_icons_no_cta_and_no_figures():
    eq = _section()
    assert "<svg" not in eq, "the typography and the divisions are enough"
    assert "<button" not in eq
    for banned in ("Get started", "Start free", "Book a demo", "Learn more"):
        assert banned.lower() not in eq.lower(), banned
    # No invented numbers: the only digits in the section are the six
    # department numbers and the picture's own dimensions.
    text = re.sub(r"<[^>]+>", " ", eq)
    assert not re.search(r"\$\s*\d|\d+%|\d+x\b", text), text[:300]


def test_the_tone_stays_a_wash_rather_than_a_filter():
    """Six coloured panels would stop the photograph reading as one
    picture. Every wash is a low-alpha layer, and nothing is filtered."""
    eq = _section()
    alphas = [float(a) for a in
              re.findall(r"--sbdept-wash: rgba\([\d, ]+,\s*([\d.]+)\)", eq)]
    assert len(alphas) == 6
    assert all(0 < a <= 0.10 for a in alphas), alphas
    css = _css()
    for banned in ("hue-rotate", "sepia", "saturate(", "duotone", "mix-blend-mode: color"):
        assert banned not in css, banned


# --- layout, interaction, accessibility ----------------------------------

def test_the_slices_are_coded_rather_than_cut():
    css = _css()
    # Desktop: one grid, six columns, the picture across row one.
    assert "grid-template-columns: repeat(var(--sbdept-count, 6), 1fr)" in css
    assert "grid-row: 1 / 3" in css
    assert "grid-template-rows: subgrid" in css      # exact row register
    assert "aspect-ratio: 1553 / 4056" in css        # and the fallback
    # Below 1024 the same six links become windows onto the same file,
    # laid out as a grid. Each card keeps its own sixth regardless of how
    # wide the card is, because the window is positioned by index.
    assert "background-size: 600% auto" in css
    assert "background-position: calc(var(--sbdept-i) * 20%) center" in css
    assert "departments-1200.jpg" in css             # one source, not six

    mobile = css[css.index("@media (max-width: 1023px)"):
                 css.index("@media (prefers-reduced-motion")]

    # It was a horizontal snap scroller showing one department at a time.
    assert "scroll-snap-type: x" not in mobile
    assert "overflow-x: auto" not in mobile
    assert "80vw" not in mobile

    # Grid, and specifically not inline-block: inline-block siblings
    # inherit the whitespace between their tags, so two 50%-wide cards do
    # not fit on one row and the sixth drops to a line of its own. That
    # exact mistake shipped once.
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in mobile
    assert "inline-block" not in mobile
    assert "width: 50%" not in mobile
    assert "min-width: 0" in mobile                  # long labels cannot widen a track
    assert "repeat(3, minmax(0, 1fr))" in css        # three across on a tablet

    # The scroller bled to the right edge, so the wrapper dropped its
    # right padding. A grid inside that gutter would sit off-centre.
    assert "padding-right: 0" not in mobile


def test_the_interaction_has_three_ways_in_and_survives_without_script():
    css = _css()
    for state in (".sbdept-dept:hover .sbdept-wash",
                  ".sbdept-dept:focus-visible .sbdept-wash",
                  ".sbdept-dept.is-active .sbdept-wash"):
        assert state in css, state
    assert ".sbdept-grid:has(.sbdept-dept:hover)" in css
    assert ".sbdept-grid[data-active]" in css        # the same, without :has()
    assert "outline: 2px solid var(--sbdept-brass)" in css
    assert "prefers-reduced-motion" in css
    # Transitions stay inside the range the brief allows.
    for ms in re.findall(r"transition:[^;]*?(\d+)ms", css):
        assert 150 <= int(ms) <= 250, ms


def test_the_decoration_is_hidden_and_the_labels_are_not():
    eq = _section()
    assert eq.count('class="sbdept-window" aria-hidden="true"') == 6
    assert '<h2 class="sbdept-eyebrow" id="sbdept-heading">' in eq
    assert 'aria-labelledby="sbdept-heading"' in eq
    # Six real links, each with its own text - not six buttons with an
    # image and a tooltip.
    assert eq.count('class="sbdept-dept"') == 6
    assert "role=" not in eq


def test_the_analytics_report_departments_and_nothing_else():
    js = open("static/js/departments.js", encoding="utf-8").read()
    for event in ("departments_section_viewed", "department_focused",
                  "department_clicked", "departments_swiped"):
        assert '"%s"' % event in js, event
    for sensitive in ("email", "user_id", "userId", "name:", "localStorage"):
        assert sensitive not in js, sensitive


def test_the_assets_are_linked_and_the_cache_version_moved():
    body = _home()
    assert "/static/css/departments.css" in body
    assert "/static/js/departments.js" in body
    for asset in ("static/css/departments.css", "static/js/departments.js"):
        assert os.path.exists(asset), asset
    sw = open("static/js/sw.js", encoding="utf-8").read()
    version = re.search(r'VERSION = "sb-v(\d+)"', sw)
    assert version and int(version.group(1)) >= 86
