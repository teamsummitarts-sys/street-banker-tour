"""Section 8 — Rollout Engine.

The load-bearing claims: the photograph runs the full width and the copy
sits over it rather than beside it, the example campaign is labelled an
example everywhere, the copy never says Street Banker publishes for you,
and a stranger can read what it does without an account.
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
    start = body.index('id="rollout-engine"')
    return body[start:start + body[start:].index("</section>")]


def _css():
    return open("static/css/rollout.css", encoding="utf-8").read()


# --- placement and copy ---------------------------------------------------

def test_the_section_sits_after_creative_studio_and_displaces_nothing():
    body = _home()
    assert body.index('id="creative-studio"') < body.index('id="rollout-engine"')
    assert body.index('id="rollout-engine"') < body.index('id="royalty-sweep-section"')
    for kept in ["Build the", "Choose your lane.", "Find what&#39;s yours.",
                 "Built for artist control.", "Your catalog is the ",
                 "One system. Six departments."]:
        assert kept in body, kept


def test_the_copy_is_the_approved_copy():
    eq = _section()
    assert "Rollout Engine" in eq
    assert ">08<" in eq
    for line in ("Plan it.", "Launch it.", "Live it."):
        assert ">%s<" % line in eq, line
    assert ("From release calendars to content drops and tour routing—build "
            "your rollout and hit every moment that matters." in eq)
    assert "Open Rollout Engine" in eq
    assert "See a sample rollout" in eq


def test_four_capabilities_each_with_one_line():
    from rollout_config import CAPABILITIES

    eq = _section()
    labels = re.findall(r'sbro-cap-label">([^<]+)<', eq)
    assert labels == ["Release Calendar", "Content Schedule", "Tour Routing",
                      "Impact Tracking"]
    for cap in CAPABILITIES:
        assert cap["line"] in eq, cap["id"]
        assert len(cap["line"]) < 90, cap["id"]
    # Labels with rules, not four cards with icons.
    assert eq.count("<svg") == 1              # the CTA arrow, nothing else


def test_the_workflow_is_five_stages_with_its_detail_in_the_document():
    from rollout_config import WORKFLOW

    eq = _section()
    assert [s for s, _ in WORKFLOW] == ["Plan", "Build", "Schedule", "Launch",
                                        "Adapt"]
    for step, detail in WORKFLOW:
        assert ">%s<" % step in eq, step
        assert detail[:40] in eq, step
    assert 'class="sbro-flow-fallback"' in eq   # readable with no script
    assert 'aria-live="polite"' in eq


# --- the example campaign -------------------------------------------------

def test_the_sample_is_labelled_an_example_and_dated_in_offsets():
    from rollout_config import SAMPLE, STATUSES

    eq = _section()
    assert 'id="sbro-sample" hidden' in eq       # hidden, not absent
    assert 'aria-controls="sbro-sample"' in eq
    assert "Example campaign" in eq
    assert "21-day rollout" in eq
    assert "not a schedule: nothing here is anyone" in eq   # Jinja escapes the '

    days = re.findall(r'sbro-day">([^<]+)<', eq)
    assert len(days) == 8
    # Offsets from release day, never a date somebody could read as real.
    for day in days:
        assert day.startswith("Day "), day
        assert not re.search(r"\d{4}|/|Jan|Feb|Mar", day), day
    for _day, item, status in SAMPLE["items"]:
        assert item in eq, item
        assert status in STATUSES, status


def test_the_statuses_are_markup_not_pixels():
    from rollout_config import STATUSES

    eq = _section()
    assert STATUSES == ["Idea", "Drafting", "Awaiting Asset",
                        "Awaiting Approval", "Approved", "Scheduled",
                        "Published", "Completed"]
    shown = set(re.findall(r'sbro-status[^"]*">([^<]+)<', eq))
    assert shown <= set(STATUSES)
    assert len(shown) >= 5                       # a real spread, not all green
    css = _css()
    # The word carries the status; colour only repeats it.
    assert ".sbro-status--approved" in css and ".sbro-status--scheduled" in css


# --- honesty --------------------------------------------------------------

def test_it_never_claims_to_publish_for_you():
    from rollout_config import TOUR_SECTIONS

    body = _anon().get("/rollout").get_data(as_text=True)
    headings = [h for h, _ in TOUR_SECTIONS]
    assert headings == ["In the app today", "Schedule-ready, not published for you",
                        "Coming soon"]
    for honest in ("Nothing posts itself", "integration-ready",
                   "Approval required", "not live yet"):
        assert honest in body, honest
    text = (body + _section()).lower()
    for banned in ("posts automatically", "publishes for you", "fully automated",
                   "hands-free", "set it and forget it"):
        assert banned not in text, banned


def test_no_fabricated_numbers_anywhere_in_the_section():
    eq = _section()
    text = re.sub(r"<[^>]+>", " ", eq)
    for banned in ("$", "%", "artists trust", "testimonial", "as seen in",
                   "streams", "followers gained"):
        assert banned not in text, banned
    # The only digits are the section number, the plan length and the day
    # offsets of the labelled example. Entities are stripped first, or the
    # 39 in an escaped apostrophe reads as a figure.
    text = re.sub(r"&#?\w+;", " ", text)
    numbers = set(re.findall(r"\d+", text))
    assert numbers <= {"08", "21", "0", "1", "6", "7", "10", "14", "18"}, numbers


# --- the photograph -------------------------------------------------------

def test_one_photograph_full_bleed_under_the_copy():
    eq = _section()
    assert eq.count("<img") == 1
    css = _css()
    # No hard split: the picture fills the stage and the copy sits on it.
    assert ".sbro-photo { position: absolute; inset: 0; }" in css
    assert "linear-gradient(to right," in css     # the veil inside the picture
    assert 'class="sbro-veil" aria-hidden="true"' in eq
    # The gradient starts inside the photograph, not at its edge.
    veil = css[css.index(".sbro-veil {"):]
    veil = veil[:veil.index("}")]
    assert "42%" in veil and "78%" in veil


def test_two_crops_chosen_by_the_browser():
    eq = _section()
    assert eq.count('media="(max-width: 767px)"') == 3
    for width in (400, 600):
        assert "rollout-close-%d" % width in eq, width
    for width in (560, 940):
        assert "rollout-wide-%d" % width in eq, width
    assert 'width="940" height="710"' in eq       # no layout shift
    assert 'loading="lazy"' in eq


def test_both_crops_ship_in_three_formats():
    for name, widths in (("wide", (560, 940)), ("close", (400, 600))):
        seen = []
        for width in widths:
            for ext in ("avif", "webp", "jpg"):
                asset = "static/img/rollout-%s-%d.%s" % (name, width, ext)
                assert os.path.exists(asset), asset
                with Image.open(asset) as im:
                    assert im.size[0] == width, (asset, im.size)
                    seen.append(round(im.size[0] / im.size[1], 3))
        assert max(seen) - min(seen) < 0.01, (name, seen)


def test_the_alt_text_describes_the_room_and_sells_nothing():
    eq = _section()
    alt = re.search(r'alt="([^"]+)"', eq).group(1)
    assert alt == ("Artist and touring crew updating printed release calendars "
                   "backstage while equipment moves through a small venue.")
    words = set(re.findall(r"[a-z]+", alt.lower()))
    for marketing in ("rollout", "engine", "street", "banker", "campaign"):
        assert marketing not in words, marketing


def test_the_photograph_carries_no_functional_text():
    """The supplied frame had a routing sheet with dates out of order and
    "PHILADEPHIA PA", a sticky note reading FALL COMES UK TOUR BY 10PM and
    two floor posters printed STREET BANKER. The tool clears all of it."""
    tool = open("tools/clean_rollout_photo.py", encoding="utf-8").read()
    for cleared in ("sticky note", "tour routing sheet", "floor poster",
                    "month label"):
        assert cleared in tool, cleared
    # Nothing in the section depends on reading the wall.
    eq = _section()
    for word in ("Release Calendar", "Content Schedule", "Tour Routing",
                 "Impact Tracking", "Plan it."):
        assert word in eq, word


# --- destinations ---------------------------------------------------------

def test_the_cta_explains_before_it_asks_for_an_account():
    eq = _section()
    href = re.search(r'class="sbro-cta" href="([^"]+)"', eq).group(1)
    assert href == "/rollout"
    client = _anon()
    page = client.get("/rollout")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert body.index("How it runs") < body.index("/signup")
    assert "Example campaign" in body
    # The gated tool is still gated.
    assert client.get("/rollout-studio").status_code == 302


def test_the_public_tour_lists_the_plan_lengths_it_really_has():
    from rollout_config import PLAN_LENGTHS

    body = _anon().get("/rollout").get_data(as_text=True)
    assert PLAN_LENGTHS == ["14-day", "21-day", "30-day", "60-day", "90-day"]
    for length in PLAN_LENGTHS:
        assert length in body, length


# --- interaction, accessibility, analytics -------------------------------

def test_the_interaction_is_restrained_and_survives_without_script():
    css = _css()
    for banned in ("@keyframes", "animation:", "parallax", "scale(1."):
        assert banned not in css, banned
    for ms in re.findall(r"transition:[^;]*?(\d+)ms", css):
        assert 150 <= int(ms) <= 250, ms
    assert "prefers-reduced-motion" in css
    for state in (".sbro-cap:hover", ".sbro-cap:focus-visible",
                  ".sbro-cap.is-active", ".sbro-stage-btn:hover"):
        assert state in css, state
    js = open("static/js/rollout.js", encoding="utf-8").read()
    assert "function releaseCaps()" in js         # focus outlives hover


def test_accessibility_scaffolding():
    eq = _section()
    assert 'aria-labelledby="sbro-heading"' in eq
    assert '<h2 class="sbro-title" id="sbro-heading">' in eq
    assert 'aria-describedby="sbro-flow-detail"' in eq
    assert 'aria-expanded="false"' in eq
    css = _css()
    assert "outline: 2px solid var(--ro-brass)" in css
    assert "min-height: 46px" in css              # capability tap target
    assert "min-height: 40px" in css              # workflow stage target


def test_the_dark_system_holds_and_the_section_is_its_own():
    css = _css()
    for token in (
                  "var(--sb-ground)",
                  "var(--sb-gold)",
                  "var(--sb-ink)"
               ):
        assert token in css, token
    eq = _section()
    text = re.sub(r"<[^>]+>", " ", eq).lower()
    # Not Section 6's rack, not Section 5's assessment, and none of the
    # touring vocabulary other sections own. ("merch table" stays in the
    # list as a generic guard - Section 7's own picture is a portrait
    # now, but the phrase must still not wander in here.)
    for borrowed in ("vu", "fader", "mastering", "merch table", "confidence",
                     "what the twin observed"):
        assert borrowed not in text, borrowed


def test_the_analytics_report_stages_and_nothing_else():
    js = open("static/js/rollout.js", encoding="utf-8").read()
    for event in ("rollout_section_viewed", "rollout_engine_opened",
                  "rollout_sample_opened", "rollout_capability_selected",
                  "rollout_stage_selected", "rollout_sample_item_opened"):
        assert '"%s"' % event in js, event
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    for sensitive in ("email", "user_id", "localStorage", "release_date"):
        assert sensitive not in code, sensitive


def test_the_assets_are_linked_and_the_cache_version_moved():
    body = _home()
    assert "/static/css/rollout.css" in body
    assert "/static/js/rollout.js" in body
    sw = open("static/js/sw.js", encoding="utf-8").read()
    version = re.search(r'VERSION = "sb-v(\d+)"', sw)
    assert version and int(version.group(1)) >= 91
