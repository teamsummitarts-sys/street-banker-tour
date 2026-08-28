"""Section 10 — Global Distribution.

This one is mostly a claims test. The reference image carried eight
statements this codebase cannot support, and the load-bearing job of the
section is to say what is true instead: Street Banker prepares and
validates, the partner delivers, and nothing on the page says otherwise.
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
    start = body.index('id="global-distribution"')
    return body[start:start + body[start:].index("</section>")]


def _css():
    return open("static/css/distribution.css", encoding="utf-8").read()


# --- placement and copy ---------------------------------------------------

def test_the_section_sits_after_the_sweep_and_displaces_nothing():
    body = _home()
    assert body.index('id="royalty-sweep-section"') < body.index('id="global-distribution"')
    assert body.index('id="global-distribution"') < body.index("Built for artist control.")
    for kept in ["Built for artist control.", "Your catalog is the ",
                 "Find what&#39;s yours.", "Plan it.", "Choose your lane."]:
        assert kept in body, kept


def test_the_copy_is_the_approved_copy():
    eq = _section()
    assert "Global Distribution" in eq and ">10<" in eq
    assert "Your music. Everywhere." in eq and "On your terms." in eq
    assert ("Prepare and deliver your release to supported platforms while "
            "keeping control of your masters, metadata, timing, territories "
            "and release information." in eq)
    assert "Distribute now" in eq
    assert "View distribution guide" in eq
    assert "Your masters. Your metadata. Your release plan." in eq
    assert "Ready to release?" not in eq
    assert "Start a release" not in eq        # closing block removed


# --- the claims audit -----------------------------------------------------

def test_the_unsupported_claims_from_the_reference_are_absent():
    """Eight statements were drawn into the reference image. Nothing in
    this codebase or in the terms on file supports any of them, so none
    of them is on the page or on the guide."""
    pages = _section() + _anon().get("/distribution").get_data(as_text=True)
    text = re.sub(r"<[^>]+>", " ", pages).lower()
    for claim in ("200+ countries", "every major platform", "keep 100%",
                  "you own your masters", "real time reports",
                  "real-time reports", "no hidden fees", "free to get started",
                  "no credit card", "cancel anytime", "100% of your"):
        assert claim not in text, claim


def test_it_says_who_actually_delivers():
    from distro_config import PARTNER

    eq = _section()
    assert "Symphonic Distribution" in PARTNER["line"]
    assert PARTNER["line"][:60] in eq
    body = _anon().get("/distribution").get_data(as_text=True)
    assert "Street Banker does not hold a direct connection to a streaming platform" in body
    assert "Delivery is the partner" in body


def test_the_integration_statuses_are_honest():
    from distro_config import INTEGRATIONS

    statuses = {s for _n, s in INTEGRATIONS}
    assert statuses <= {"Connected", "Supported", "Delivered through partner",
                        "Integration ready", "Coming soon"}
    # Nothing claims a direct connection this app does not hold.
    assert "Connected" not in statuses
    assert ("Direct platform connections from Street Banker", "Coming soon") in INTEGRATIONS
    body = _anon().get("/distribution").get_data(as_text=True)
    for name, status in INTEGRATIONS:
        assert name in body, name
        assert status in body, status


def test_no_fabricated_figures_anywhere_in_the_section():
    eq = _section()
    text = re.sub(r"<[^>]+>", " ", eq)
    text = re.sub(r"&#?\w+;", " ", text)
    for banned in ("$", "%", "artists trust", "testimonial", "as seen in"):
        assert banned not in text, banned
    # The only digits are the section number and the capability numbers.
    assert set(re.findall(r"\d+", text)) <= {"10", "01", "02", "03", "04", "05"}


# --- structure ------------------------------------------------------------

def test_the_shape_is_photograph_partner_capabilities():
    """The heading is over the bench, not above it.

    The example release checklist that used to sit between the workflow
    and the closing block is gone: it is the same list /release-check
    serves, where a visitor can actually tick it, so a static copy here
    said the same thing twice and said it worse.
    """
    eq = _section()
    # The header is now inside the figure.
    assert eq.index('class="sbds-photo"') < eq.index('class="sbds-head"')
    assert eq.index('class="sbds-head"') < eq.index("</figure>")
    for earlier, later in [('class="sbds-photo"', 'class="sbds-partner"'),
                           ('class="sbds-partner"', 'class="sbds-caps"')]:
        assert eq.index(earlier) < eq.index(later), (earlier, later)
    # Three blocks are off the homepage: the release checklist, the
    # five-stage workflow and the "Ready to release?" closing block. All
    # of them are on /distribution, which the guide button opens.
    for gone in ('class="sbds-check"', 'class="sbds-flow"', 'class="sbds-final"'):
        assert gone not in eq, gone

    css = _css()
    assert "text-align: center" in css
    # Centred over the picture, per the brief - not to one side.
    assert ".sbds-over" in css and "align-items: center" in css
    assert ".sbds-scrim" in css
    assert ".sbds-check" not in css              # no dead rules


def test_five_capabilities_with_the_reviewed_wording():
    from distro_config import CAPABILITIES

    eq = _section()
    nums = re.findall(r'sbds-cap-num">([^<]+)<', eq)
    names = re.findall(r'sbds-cap-name">([^<]+)<', eq)
    assert nums == ["01", "02", "03", "04", "05"]
    assert names == ["Platform Delivery", "Ownership Control", "Release Control",
                     "Reporting", "Splits and Credits"]
    for _num, _name, detail in CAPABILITIES:
        assert detail[:40] in eq, detail[:40]
    # Ownership is qualified, not promised.
    ownership = next(d for _n, name, d in CAPABILITIES if name == "Ownership Control")
    assert "according to your agreement" in ownership


def test_the_workflow_lives_on_the_guide_page_not_the_homepage():
    from distro_config import WORKFLOW

    eq = _section()
    assert [s for s, _ in WORKFLOW] == ["Prepare", "Validate", "Deliver",
                                        "Monitor", "Maintain"]
    # Not on the homepage any more: the live detail line and the
    # screen-reader fallback printed every stage twice.
    for step, detail in WORKFLOW:
        assert ">%s<" % step not in eq, step
    assert 'class="sbds-flow-fallback"' not in eq

    # Still complete on /distribution.
    from app import create_app
    body = create_app().test_client().get("/distribution").get_data(as_text=True)
    for step, detail in WORKFLOW:
        assert step in body, step
        assert detail[:40] in body, step


def test_the_checklist_is_not_duplicated_on_the_homepage():
    """It lives at /release-check, where it is interactive."""
    eq = _section()
    assert "Example release checklist" not in eq
    assert 'class="sbds-check' not in eq
    js = open("static/js/distribution.js", encoding="utf-8").read()
    assert "sbds-check" not in js
    assert "distribution_checklist_viewed" not in js
    # And the button that opens the real one still points at it.
    from distro_config import PRIMARY_CTA
    assert PRIMARY_CTA["href"] == "/release-check"


def _retired_test_the_checklist_is_labelled_an_example_and_nothing_is_ticked():
    from distro_config import CHECKLIST, READINESS

    eq = _section()
    assert "Example release checklist" in eq
    assert READINESS[0] == "Setup Incomplete"
    assert "nothing has been entered yet" in eq
    items = [item for _group, items in CHECKLIST for item in items]
    assert len(items) == 21
    for item in items:
        assert item in eq, item
    # Readiness is completion, and the page says so.
    assert "Readiness is completion" in eq
    assert "says nothing about how a release will perform" in eq
    # Empty boxes, not ticks: a tick would be a claim about a real release.
    css = _css()
    assert ".sbds-check-group li::before" in css
    assert "border: 1px solid rgb(201 168 106 / 0.5)" in css


# --- the photograph -------------------------------------------------------

def test_one_still_life_with_no_people_and_no_rasterised_copy():
    eq = _section()
    assert eq.count("<img") == 1
    alt = re.search(r'alt="([^"]+)"', eq).group(1)
    assert alt == ("Road cases and release materials arranged around a release "
                   "passport, audio masters, stems drive, cables and release "
                   "checklist.")
    words = set(re.findall(r"[a-z]+", alt.lower()))
    for banned in ("street", "banker", "distribution", "global", "everywhere"):
        assert banned not in words, banned
    tool = open("tools/clean_distribution_photo.py", encoding="utf-8").read()
    for cleared in ("rasterised supporting copy", "DISTRIBUTE NOW button",
                    "guide link", "STREET BANKER DELIVERED", "SB stencil",
                    "release checklist"):
        assert cleared in tool, cleared


def test_two_crops_chosen_by_the_browser():
    eq = _section()
    assert eq.count('media="(max-width: 767px)"') == 3
    for width in (480, 740):
        assert "distro-close-%d" % width in eq, width
    for width in (760, 1180, 1402):
        assert "distro-wide-%d" % width in eq, width
    assert 'width="1402" height="462"' in eq        # no layout shift
    assert 'loading="lazy"' in eq


def test_both_crops_ship_in_three_formats():
    for name, widths in (("wide", (760, 1180, 1402)), ("close", (480, 740))):
        seen = []
        for width in widths:
            for ext in ("avif", "webp", "jpg"):
                asset = "static/img/distro-%s-%d.%s" % (name, width, ext)
                assert os.path.exists(asset), asset
                with Image.open(asset) as im:
                    assert im.size[0] == width, (asset, im.size)
                    seen.append(round(im.size[0] / im.size[1], 3))
        assert max(seen) - min(seen) < 0.01, (name, seen)
    # The phone crop is a genuinely different, taller composition.
    with Image.open("static/img/distro-wide-1402.jpg") as wide, \
            Image.open("static/img/distro-close-740.jpg") as close:
        assert wide.size[0] / wide.size[1] > 2.5
        assert close.size[0] / close.size[1] < 2.0


# --- destinations ---------------------------------------------------------

def test_every_cta_is_public_and_explains_before_it_asks():
    eq = _section()
    hrefs = [re.search(r'class="sbds-cta" href="([^"]+)"', eq).group(1),
             re.search(r'class="sbds-guide" href="([^"]+)"', eq).group(1)]
    assert 'class="sbds-final-cta"' not in eq       # closing block removed
    # Two CTAs, and they must not share a destination: they once did,
    # which made "Distribute now" do exactly what the guide button did.
    # Two CTAs now - the closing "Start a release" went with its block -
    # and they must not share a destination, which they once did.
    assert hrefs == ["/release-check", "/distribution#guide"]
    assert hrefs[0] != hrefs[1]
    client = _anon()
    page = client.get("/distribution")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'id="guide"' in body                     # the anchor exists
    assert body.index("The five stages") < body.index("/signup")
    # The gated release tooling is still gated.
    for gated in ("/releases", "/metadata-passport", "/releases/clean-release"):
        assert client.get(gated).status_code == 302, gated


def test_the_guide_covers_what_a_release_needs():
    from distro_config import GUIDE

    body = _anon().get("/distribution").get_data(as_text=True)
    titles = [t for t, _b in GUIDE]
    for needed in ("Audio", "Artwork", "Metadata", "Credits", "Ownership",
                   "ISRC and UPC", "Release date", "Territories",
                   "Delivery timelines", "Changes after delivery", "Reporting",
                   "Takedowns and updates"):
        assert needed in titles, needed
        assert needed in body, needed
    assert "Delivery is a queue, not a switch" in body


# --- interaction, accessibility, analytics -------------------------------

def test_the_motion_is_restrained():
    css = _css()
    for banned in ("@keyframes", "animation:", "parallax", "scale(1."):
        assert banned not in css, banned
    for ms in re.findall(r"transition:[^;]*?(\d+)ms", css):
        assert 150 <= int(ms) <= 250, ms
    assert "prefers-reduced-motion" in css


def test_the_dark_system_is_the_one_in_the_brief():
    css = _css()
    for token in (
                  "var(--sb-ground)",
                  "var(--sb-surface-1)",
                  "var(--sb-gold)",
                  "var(--sb-ink)",
                  "var(--sb-ink-2)",
                  "rgb(201 168 106 / 0.22)"
               ):
        assert token in css, token
    for banned in ("background: #fff", "background: white"):
        assert banned not in css, banned


def test_accessibility_scaffolding():
    eq = _section()
    assert 'aria-labelledby="sbds-heading"' in eq
    assert '<h2 class="sbds-title" id="sbds-heading">' in eq
    # The workflow's aria-describedby and live region went with it.
    assert 'aria-describedby="sbds-flow-detail"' not in eq
    assert 'aria-live' not in eq
    css = _css()
    assert "outline: 2px solid var(--ds-brass)" in css
    assert "min-height: 52px" in css               # primary CTA target
    # The 40px workflow-stage target went with the workflow. The two
    # CTAs that remain carry their own min-height.
    assert "min-height" in css


def test_the_analytics_carry_no_release_information():
    js = open("static/js/distribution.js", encoding="utf-8").read()
    for event in ("distribution_section_viewed", "distribute_now_clicked",
                  "distribution_guide_clicked",
                  ):
        assert '"%s"' % event in js, event
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    for sensitive in ("isrc", "upc", "contributor", "owner", "email",
                      "user_id", "localStorage", "audio"):
        assert sensitive not in code.lower(), sensitive


def test_the_assets_are_linked_and_the_cache_version_moved():
    body = _home()
    assert "/static/css/distribution.css" in body
    assert "/static/js/distribution.js" in body
    sw = open("static/js/sw.js", encoding="utf-8").read()
    version = re.search(r'VERSION = "sb-v(\d+)"', sw)
    assert version and int(version.group(1)) >= 93
