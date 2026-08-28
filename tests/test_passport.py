"""Section 11 — Metadata Passport + Rights.

What has to hold: the seven categories and every word about them are
markup rather than pixels, the hotspots land on their own areas of the
blueprint, the example is labelled an example, the completeness figure is
completion and named for it, and nothing claims a conflict has been
verified.
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
    start = body.index('id="metadata-passport"')
    return body[start:start + body[start:].index("</section>")]


def _css():
    return open("static/css/passport.css", encoding="utf-8").read()


# --- placement and copy ---------------------------------------------------

def test_the_section_sits_after_distribution_and_displaces_nothing():
    body = _home()
    assert body.index('id="global-distribution"') < body.index('id="metadata-passport"')
    assert body.index('id="metadata-passport"') < body.index("Built for artist control.")
    for kept in ["Built for artist control.", "Your catalog is the ",
                 "Your music. Everywhere.", "Find what&#39;s yours.",
                 "Choose your lane."]:
        assert kept in body, kept


def test_the_copy_is_the_approved_copy():
    eq = _section()
    assert "Metadata Passport + Rights" in eq and ">11<" in eq
    assert "One release." in eq and "Every detail connected." in eq
    assert ("Organise credits, splits, identifiers, ownership, agreements, "
            "assets, versions and release history in one living record." in eq)
    assert "Open Metadata Passport" in eq
    assert "See how it connects" in eq
    assert "Your credits. Your rights. Your record." in eq
    assert "control what is confirmed, shared or submitted" in eq


# --- the seven records ----------------------------------------------------

def test_seven_categories_in_order_with_live_copy():
    from passport_config import CATEGORIES

    eq = _section()
    nums = re.findall(r'sbmp-cat-num">([^<]+)<', eq)
    labels = re.findall(r'sbmp-cat-label">([^<]+)<', eq)
    assert nums == ["01", "02", "03", "04", "05", "06", "07"]
    assert labels == ["Credits", "Ownership", "Identifiers", "Versions",
                      "Agreements", "Assets", "Release History"]
    # Every description, every "why", every action is in the document -
    # the writing in the photograph is set dressing.
    for cat in CATEGORIES:
        assert cat["short"] in eq, cat["slug"]
        # The long fields moved to /metadata with the detail panel.
        assert cat["why"][:40] not in eq, cat["slug"]
        # `action` and `stored` were part of the detail panel and moved
        # to /metadata with it.
        assert cat["action"][:40] not in eq, cat["slug"]
        for item in cat["stored"][:3]:
            assert item not in eq, (cat["slug"], item)


def test_the_blueprint_carries_no_controls():
    """The photograph is a picture, not a control surface.

    It used to carry seven transparent hotspots on desktop. They asked a
    visitor to hunt for targets on a photograph, and the row of seven
    named buttons beneath does the same job for pointer and keyboard
    alike. The zone geometry stays in the config - it is still the record
    of where each category sits in the scene - so it is still checked for
    sanity here even though nothing renders it.
    """
    from passport_config import CATEGORIES

    boxes = []
    for cat in CATEGORIES:
        left, top, right, bottom = cat["zone"]
        assert 0 <= left < right <= 1 and 0 <= top < bottom <= 1, cat["slug"]
        assert right - left > 0.15 and bottom - top > 0.15, cat["slug"]
        boxes.append((cat["slug"], left, top, right, bottom))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            overlap = (a[1] < b[3] and b[1] < a[3] and a[2] < b[4] and b[2] < a[4])
            assert not overlap, (a[0], b[0])
    eq = _section()
    assert 'class="sbmp-zone"' not in eq
    assert "sbmp-zones" not in eq
    css = _css()
    assert ".sbmp-zone" not in css                # no dead rules either
    js = open("static/js/passport.js", encoding="utf-8").read()
    assert "sbmp-zone" not in js


def test_the_example_detail_is_not_on_the_homepage():
    """It was the longest block on the page and repeated in full what the
    seven one-line descriptions already say in short. It lives on
    /metadata, which the Open Metadata Passport button opens."""
    eq = _section()
    assert eq.count('class="sbmp-panel"') == 0
    assert 'class="sbmp-detail"' not in eq
    assert "What is stored" not in eq

    from app import create_app
    body = create_app().test_client().get("/metadata").get_data(as_text=True)
    from passport_config import CATEGORIES
    for cat in CATEGORIES:
        assert cat["why"][:40] in body, cat["slug"]

def _retired_only_one_detail_is_open():
    eq = _section()
    assert eq.count('class="sbmp-panel"') == 7
    # Six hidden, one open, server-side - so it reads with no script.
    assert eq.count("sbmp-panel\" data-panel=") == 7
    assert eq.count(" hidden>") >= 6
    js = open("static/js/passport.js", encoding="utf-8").read()
    assert 'p.setAttribute("hidden", "")' in js
    assert 'aria-pressed' in eq


# --- the example, and what it never claims --------------------------------

def test_the_passport_is_labelled_an_example():
    eq = _section()
    assert "Example metadata passport" not in eq   # moved to /metadata
    body = _anon().get("/metadata").get_data(as_text=True)
    assert "From the example passport" in body
    assert "Nothing here has been verified" in body


def test_completeness_is_completion_and_named_for_it():
    from passport_config import HEALTH_LABEL, HEALTH_STATUSES, completeness

    assert HEALTH_LABEL == "Metadata completeness"
    for banned in ("Hit Score", "Success Score", "Artist Value",
                   "Revenue Score"):
        assert banned.lower() not in HEALTH_LABEL.lower(), banned
    assert HEALTH_STATUSES == ["Incomplete", "Needs Review",
                               "Conflicts Detected", "Ready for Confirmation",
                               "Complete", "Verified"]
    # Deterministic: it is a count of categories with nothing outstanding.
    assert completeness() == 29

    # It is no longer shown on the homepage. A percentage on a marketing
    # page invites reading as a score for the artist rather than a count
    # of filled fields on a worked example. The helper and its wording
    # stay for the product pages.
    eq = _section()
    assert "Metadata completeness" not in eq
    assert "sbmp-health" not in eq


def test_nothing_predicts_and_no_conflict_is_called_verified():
    from passport_config import CATEGORIES, ISSUES, HEALTH_NOTE, get_passport_config

    cfg = get_passport_config()
    prose = " ".join(
        [cfg["support"], cfg["trust_copy"], HEALTH_NOTE] +
        [c["why"] for c in CATEGORIES] + [c["action"] for c in CATEGORIES] +
        [i["action"] for i in ISSUES]).lower()
    for banned in ("guarantee", "we predict", "predicts your", "chart position",
                   "hit score", "valuation of", "will earn", "success score"):
        assert banned not in prose, banned
    # And the disclaimer that uses the word is actually present.
    assert "not a prediction" in prose
    # Every example issue is open or waiting - none is claimed as verified.
    for issue in ISSUES:
        assert issue["status"] in ("Open", "Awaiting Signature"), issue["issue"]
        assert issue["severity"] in ("High", "Medium", "Low"), issue["issue"]
        assert issue["evidence"], issue["issue"]


def test_the_connected_example_shows_five_consequences():
    from passport_config import CONNECTED

    eq = _section()
    assert 'id="sbmp-connect" hidden' in eq          # hidden, not absent
    assert 'aria-controls="sbmp-connect"' in eq
    assert CONNECTED["trigger"] == "A songwriter is added under Credits."
    assert CONNECTED["trigger"] in eq
    areas = [a for a, _e in CONNECTED["effects"]]
    assert areas == ["Ownership", "Identifiers", "Agreements", "Versions",
                     "Release History"]
    for _area, effect in CONNECTED["effects"]:
        assert effect[:35] in eq
    assert "One entry, five consequences" in eq


# --- the photograph -------------------------------------------------------

def test_the_approved_photograph_is_used_unaltered():
    """The brief locks this composition, so there is no cleaning tool for
    it: the picture ships as supplied, and the writing inside it is art
    direction that nothing on the page depends on."""
    assert not os.path.exists("tools/clean_passport_photo.py")
    eq = _section()
    assert eq.count("<img") == 1
    alt = re.search(r'alt="([^"]+)"', eq).group(1)
    assert alt == ("One album release arranged at the centre of a floor "
                   "blueprint connecting credits, ownership, identifiers, "
                   "versions, agreements, assets and release history.")
    # Every category name is markup as well as pixels.
    for label in ("Credits", "Ownership", "Identifiers", "Versions",
                  "Agreements", "Assets", "Release History"):
        assert eq.count(label) >= 1, label       # the record, once


def test_two_crops_ship_in_three_formats():
    eq = _section()
    assert eq.count('media="(max-width: 767px)"') == 3
    for width in (520, 1037):
        assert "passport-close-%d" % width in eq, width
    for width in (900, 1300, 1672):
        assert "passport-wide-%d" % width in eq, width
    assert 'width="1672" height="941"' in eq         # no layout shift
    assert 'loading="lazy"' in eq
    for name, widths in (("wide", (900, 1300, 1672)), ("close", (520, 1037))):
        seen = []
        for width in widths:
            for ext in ("avif", "webp", "jpg"):
                asset = "static/img/passport-%s-%d.%s" % (name, width, ext)
                assert os.path.exists(asset), asset
                with Image.open(asset) as im:
                    assert im.size[0] == width, (asset, im.size)
                    seen.append(round(im.size[0] / im.size[1], 3))
        assert max(seen) - min(seen) < 0.01, (name, seen)
    # The phone crop is a genuinely tighter frame on the release.
    with Image.open("static/img/passport-wide-1672.jpg") as wide, \
            Image.open("static/img/passport-close-1037.jpg") as close:
        assert wide.size[0] / wide.size[1] > 1.7
        assert close.size[0] / close.size[1] < 1.5


# --- destinations ---------------------------------------------------------

def test_the_cta_explains_before_it_asks_for_an_account():
    eq = _section()
    href = re.search(r'class="sbmp-cta" href="([^"]+)"', eq).group(1)
    assert href == "/metadata"
    client = _anon()
    page = client.get("/metadata")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'id="used"' in body
    assert body.index("The seven records") < body.index("/signup")
    # The gated passport itself is still gated.
    assert client.get("/metadata-passport").status_code == 302


def test_the_public_page_says_what_happens_to_the_information():
    from passport_config import USE

    body = _anon().get("/metadata").get_data(as_text=True)
    for heading, _b in USE:
        assert heading in body, heading
    for honest in ("A collaborator sees the release they were invited to",
                   "only when you submit it", "Nothing is overwritten silently",
                   "export it, or remove it"):
        assert honest in body, honest


def test_the_standards_language_claims_no_certification():
    from passport_config import STANDARDS

    assert "not DDEX-certified today" in STANDARDS
    assert "future DDEX integration" in STANDARDS
    body = _anon().get("/metadata").get_data(as_text=True)
    assert STANDARDS[:50] in body
    for banned in ("ddex certified", "ddex-compliant", "officially certified"):
        assert banned not in body.lower(), banned


# --- interaction, accessibility, analytics -------------------------------

def test_the_motion_is_restrained():
    css = _css()
    for banned in ("@keyframes", "animation:", "parallax", "scale(1.",
                   "rotate("):
        assert banned not in css, banned
    for ms in re.findall(r"transition:[^;]*?(\d+)ms", css):
        assert 150 <= int(ms) <= 250, ms
    assert "prefers-reduced-motion" in css
    # The only thing over the photograph is the heading and its scrim,
    # and the scrim is a gradient rather than a panel.
    assert "border: 1px solid transparent" not in css
    assert ".sbmp-scrim" in css
    assert "linear-gradient" in css


def test_the_dark_system_is_the_one_in_the_brief():
    css = _css()
    for token in (
                  "var(--sb-ground)",
                  "var(--sb-surface-1)",
                  "var(--sb-gold)",
                  "var(--sb-ink)",
                  "var(--sb-ink-2)",
                  "var(--sb-good)",
                  "rgb(201 168 106 / 0.22)"
               ):
        assert token in css, token
    for banned in ("background: #fff", "background: white"):
        assert banned not in css, banned


def test_accessibility_scaffolding():
    eq = _section()
    assert 'aria-labelledby="sbmp-heading"' in eq
    assert '<h2 class="sbmp-title" id="sbmp-heading">' in eq
    # Seven, not fourteen: the blueprint no longer duplicates the row of
    # named buttons as hotspots.
    # They were buttons that swapped a detail panel. The panel is gone,
    # so they are records rather than seven controls that do nothing.
    assert eq.count('aria-pressed="false"') == 0
    assert 'aria-controls="sbmp-detail"' not in eq
    assert '<button type="button" class="sbmp-cat"' not in eq
    # The completeness bar carried role="img" with a spoken label. Both
    # went with the block; there is no meter on the homepage to describe.
    assert 'role="img"' not in eq
    # The heading over the photograph is real markup, not baked pixels.
    assert 'class="sbmp-over"' in eq
    assert 'aria-hidden="true"' in eq              # the scrim is decorative
    css = _css()
    assert "outline: 2px solid var(--mp-brass)" in css
    assert "min-height: 46px" in css
    # The hotspots and their screen-reader labels are gone together; the
    # named buttons carry visible text, so nothing needs a hidden label.


def test_the_analytics_carry_no_release_information():
    js = open("static/js/passport.js", encoding="utf-8").read()
    # The completeness summary is off the homepage, and so is its event.
    assert "passport_health_opened" not in js
    for event in ("passport_section_viewed", "passport_open_clicked", "passport_connected_example_viewed",
                  "passport_trust_link_clicked"):
        assert '"%s"' % event in js, event
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    for sensitive in ("isrc", "iswc", "ipi", "split", "owner", "agreement",
                      "email", "user_id", "localStorage"):
        assert sensitive not in code.lower(), sensitive


def test_the_assets_are_linked_and_the_cache_version_moved():
    body = _home()
    assert "/static/css/passport.css" in body
    assert "/static/js/passport.js" in body
    sw = open("static/js/sw.js", encoding="utf-8").read()
    version = re.search(r'VERSION = "sb-v(\d+)"', sw)
    assert version and int(version.group(1)) >= 94
