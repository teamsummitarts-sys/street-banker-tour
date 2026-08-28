"""Section 6 — three lanes, one system.

The hardware is one photograph of one unit; the meaning is markup. What
has to hold: the three lanes in order with their real copy, the channels
lined up with their summaries, no dead link, no price, and a public way
to work out which lane fits without making an account.
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
    start = body.index('class="sblane"')
    return body[start:start + body[start:].index("</section>")]


def _css():
    return open("static/css/lanes.css", encoding="utf-8").read()


# --- placement and copy ---------------------------------------------------

def test_the_section_replaces_the_old_lanes_and_keeps_its_anchor():
    body = _home()
    assert 'id="lanes"' in body                     # Section 4 links at it
    assert body.index('id="artist-twin-section"') < body.index('id="lanes"')
    assert body.index('id="lanes"') < body.index('id="royalty-sweep-section"')
    # The old three-card strip is gone, and its images with it.
    assert "THE THREE STREET BANKER LANES" not in body
    assert "Three paths. One infrastructure." not in body
    for old in ("sb-lane-01.jpg", "sb-lane-02.jpg", "sb-lane-03.jpg"):
        assert old not in body, old
    # Everything below it is untouched.
    for kept in ["Find what&#39;s yours.", "Built for artist control.",
                 "Your catalog is the ", "closing-wide-1672"]:
        assert kept in body, kept


def test_the_copy_is_the_approved_copy():
    eq = _section()
    assert "Three lanes. One system." in eq
    assert "Choose your lane." in eq and "Build your career." in eq
    assert ("Street Banker meets artists where they are" in eq)
    nums = re.findall(r'sblane-num">([^<]+)<', eq)
    names = re.findall(r'sblane-name">([^<]+)<', eq)
    sublines = re.findall(r'sblane-subline">([^<]+)<', eq)
    assert nums == ["01", "02", "03"]
    assert names == ["Distribution", "Development", "Partnership"]
    assert sublines == ["Release the Record", "Build the Artist", "Build the Asset"]
    for phrase in ("delivery, release tools, metadata support, smart links",
                   "Artist Twin guidance, rollout planning, audience development",
                   "catalog strategy, higher-touch support"):
        assert phrase in eq, phrase


def test_the_lane_copy_is_live_text_not_only_pixels():
    """The unit is engraved with the lane names; that is the object. The
    working copy has to exist outside it or a phone reads nothing."""
    eq = _section()
    assert eq.count("<img") == 1
    for lane in ("Distribution", "Development", "Partnership"):
        assert eq.count(lane) >= 2, lane      # summary and comparison
    # Descriptions are in the markup, at a readable length.
    descs = re.findall(r'sblane-desc">([^<]+)<', eq)
    assert len(descs) == 3
    for d in descs:
        assert 80 < len(d) < 260, d


# --- the unit -------------------------------------------------------------

def test_it_is_one_unit_not_three_pictures():
    eq = _section()
    assert eq.count("<picture") == 1
    assert eq.count('class="sblane-channel"') == 3
    # The overlays are decorative; the channel is named in its summary.
    assert '<div class="sblane-channels" aria-hidden="true">' in eq
    alt = re.search(r'alt="([^"]+)"', eq).group(1)
    assert alt == ("Street Banker hardware-style unit with three channels "
                   "representing Distribution, Development and Partnership.")


def test_the_channels_are_cut_at_the_real_seams():
    """Equal thirds would put the highlight over the wrong channel: the
    panels on this unit are not equal, so the seams are measured."""
    from lanes_config import SEAMS

    assert len(SEAMS) == 2
    assert 0.30 < SEAMS[0] < 0.36 and 0.63 < SEAMS[1] < 0.69
    eq = _section()
    assert "--sblane-seam-1: %s" % SEAMS[0] in eq
    assert "--sblane-seam-2: %s" % SEAMS[1] in eq
    css = _css()
    # The summaries below use the same numbers, so they line up.
    assert "calc(var(--sblane-seam-1) * 100%)" in css
    assert "var(--sblane-seam-1, 0.337)" in css


def test_the_unit_ships_in_three_formats_and_three_sizes():
    eq = _section()
    for fmt in ("image/avif", "image/webp"):
        assert 'type="%s"' % fmt in eq, fmt
    ratios = []
    for width in (760, 1100, 1626):
        for ext in ("avif", "webp", "jpg"):
            asset = "static/img/lanes-unit-%d.%s" % (width, ext)
            assert os.path.exists(asset), asset
            assert "lanes-unit-%d.%s %dw" % (width, ext, width) in eq
            with Image.open(asset) as im:
                assert im.size[0] == width
                ratios.append(round(im.size[0] / im.size[1], 3))
    assert max(ratios) - min(ratios) < 0.01, ratios   # one crop at every size
    assert 'width="1626" height="892"' in eq          # no layout shift
    assert 'loading="lazy"' in eq


# --- destinations ---------------------------------------------------------

def test_no_lane_and_no_cta_hits_a_login_wall():
    eq = _section()
    hrefs = re.findall(r'class="sblane-link" href="([^"]+)"', eq)
    assert hrefs == ["/lanes#distribution", "/lanes#development",
                     "/lanes#partnership"]
    assert 'class="sblane-primary" href="/lanes"' in eq
    client = _anon()
    assert client.get("/lanes").status_code == 200
    # The anchors the summaries point at exist on that page.
    page = client.get("/lanes").get_data(as_text=True)
    for slug in ("distribution", "development", "partnership"):
        assert 'id="%s"' % slug in page, slug


def test_the_public_matcher_answers_and_explains_itself():
    client = _anon()
    body = client.get("/lanes").get_data(as_text=True)
    for label in ("Releasing my first music", "Actively growing an audience",
                  "I need royalty help", "I want hands-on development",
                  "Building long-term catalog value"):
        assert label in body, label
    assert "Suggested lane" not in body            # nothing picked yet

    picked = client.get("/lanes?situation=royalties").get_data(as_text=True)
    assert "Suggested lane" in picked
    assert "Distribution" in picked
    assert "Start by reading the statements you already have" in picked
    assert "a starting point, not a placement" in picked
    # All three stay on the page, so the suggestion can be argued with.
    assert picked.count('class="scroll-mt-28') == 3

    junk = client.get("/lanes?situation=%3Cscript%3E")
    assert junk.status_code == 200
    assert "<script>alert" not in junk.get_data(as_text=True)
    assert "Suggested lane" not in junk.get_data(as_text=True)


def test_every_situation_points_at_a_real_lane():
    from lanes_config import LANES, SITUATIONS

    slugs = {lane["slug"] for lane in LANES}
    assert len(SITUATIONS) == 5
    for s in SITUATIONS:
        assert s["lane"] in slugs, s["id"]
        assert s["why"], s["id"]
    # Every lane is reachable from at least one situation.
    assert {s["lane"] for s in SITUATIONS} == slugs


def test_the_comparison_stays_on_the_page():
    eq = _section()
    assert 'id="sblane-comparison"' in eq
    assert 'aria-controls="sblane-comparison"' in eq
    assert 'aria-expanded="false"' in eq
    assert "hidden" in eq.split('id="sblane-comparison"')[1][:40]
    assert eq.count('class="sblane-compare-col"') == 3
    js = open("static/js/lanes.js", encoding="utf-8").read()
    assert 'removeAttribute("hidden")' in js and 'setAttribute("hidden"' in js


# --- what the brief rules out --------------------------------------------

def test_it_is_not_a_pricing_table():
    eq = _section()
    text = re.sub(r"<[^>]+>", " ", eq)
    for banned in ("$", "/mo", "per month", "Free plan", "Most popular",
                   "Best value", "%"):
        assert banned not in text, banned
    assert "<table" not in eq
    # No invented proof.
    for banned in ("artists trust", "as seen in", "testimonial"):
        assert banned not in text.lower(), banned


def test_the_motion_is_restrained():
    css = _css()
    for banned in ("@keyframes", "animation:", "parallax", "scale(1.1)"):
        assert banned not in css, banned
    for ms in re.findall(r"transition:[^;]*?(\d+)ms", css):
        assert 150 <= int(ms) <= 250, ms
    assert "prefers-reduced-motion" in css


def test_the_dark_system_holds():
    css = _css()
    for token in (
                  "var(--sb-ground)",
                  "var(--sb-gold)",
                  "var(--sb-ink)"
               ):
        assert token in css, token
    assert "background: var(--ln-ink)" in css
    for bright in ("background: #fff", "background: white"):
        assert bright not in css, bright


# --- interaction, accessibility, analytics -------------------------------

def test_one_lane_at_a_time_and_focus_keeps_it():
    css = _css()
    assert '.sblane-unit[data-active] .sblane-channel' in css
    assert '.sblane-unit[data-active="development"] .sblane-channel:nth-child(2)' in css
    assert ".sblane-link:focus-visible" in css
    assert "outline: 2px solid var(--ln-brass)" in css
    js = open("static/js/lanes.js", encoding="utf-8").read()
    assert "unit.dataset.active = lane" in js
    assert "function release()" in js               # focus outlives hover


def test_accessibility_scaffolding():
    eq = _section()
    assert 'aria-labelledby="sblane-heading"' in eq
    assert '<h2 class="sblane-title" id="sblane-heading">' in eq
    assert eq.count("<h3") == 3                      # one per comparison column
    assert '<div class="sblane-channels" aria-hidden="true">' in eq
    css = _css()
    assert "min-height: 48px" in css                 # tap target on the CTAs
    assert "scroll-snap-type: x mandatory" in css    # the phone rail


def test_the_analytics_report_lanes_and_nothing_else():
    js = open("static/js/lanes.js", encoding="utf-8").read()
    for event in ("lanes_section_viewed", "lane_hovered", "lane_focused",
                  "lane_clicked", "find_my_lane_clicked",
                  "lane_comparison_opened"):
        assert '"%s"' % event in js, event
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    for sensitive in ("email", "user_id", "localStorage", "description"):
        assert sensitive not in code, sensitive


def test_the_assets_are_linked_and_the_cache_version_moved():
    body = _home()
    assert "/static/css/lanes.css" in body
    assert "/static/js/lanes.js" in body
    sw = open("static/js/sw.js", encoding="utf-8").read()
    version = re.search(r'VERSION = "sb-v(\d+)"', sw)
    assert version and int(version.group(1)) >= 89
