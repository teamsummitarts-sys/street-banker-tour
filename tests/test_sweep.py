"""Section 9 — Royalty Sweep.

The load-bearing claims: nothing is guaranteed, found or recovered; the
example case is labelled an example and carries no figure; the sources
say honestly which are live and which are not; and the photograph carries
no invented registration.
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
    start = body.index('id="royalty-sweep-section"')
    return body[start:start + body[start:].index("</section>")]


def _css():
    return open("static/css/sweep.css", encoding="utf-8").read()


# --- placement and copy ---------------------------------------------------

def test_the_section_replaces_the_old_sweep_band_and_keeps_its_anchor():
    body = _home()
    assert 'id="royalty-sweep"' in body                  # the header links at it
    assert body.index('id="rollout-engine"') < body.index('id="royalty-sweep-section"')
    assert body.index('id="royalty-sweep-section"') < body.index("Built for artist control.")
    # The old band is gone, and its photograph with it.
    assert "FIND WHAT YOU EARNED." not in body
    assert "FIX WHAT IS MISSING." not in body
    assert "sb-band-sweep.jpg" not in body
    # Everything below is untouched.
    for kept in ["Built for artist control.", "Your catalog is the ",
                 "closing-wide-1672", "Plan it.", "Choose your lane."]:
        assert kept in body, kept


def test_the_copy_is_the_approved_copy():
    eq = _section()
    assert "Royalty Sweep" in eq
    assert "Find what&#39;s yours." in eq or "Find what's yours." in eq
    assert "Keep what&#39;s earned." in eq or "Keep what's earned." in eq
    assert ("Connect the catalog, trace missing registrations and income "
            "sources, and turn every potential gap into a trackable recovery "
            "case." in eq)
    assert "Run a Royalty Sweep" in eq
    assert "See how the sweep works" in eq
    assert "Your catalog. Your data. Your approval." in eq
    assert "Every finding requires verification before submission." in eq


def test_the_shape_is_photograph_with_the_heading_over_it_then_the_stages():
    """Heading, primary CTA and trust line sit on the picture.

    Not the left-image/right-copy split of Sections 7 and 8, and no
    longer a centred header stacked above the frame.
    """
    eq = _section()
    # The header is inside the figure.
    assert eq.index('class="sbsw-photo"') < eq.index('class="sbsw-head"')
    assert eq.index('class="sbsw-head"') < eq.index("</figure>")
    assert eq.index('class="sbsw-cta"') < eq.index("</figure>")
    assert eq.index('class="sbsw-trust"') < eq.index("</figure>")
    # The stages and the example stay below it.
    assert eq.index("</figure>") < eq.index('class="sbsw-flow"')
    # The disclosure button stays with the panel it opens, rather than
    # riding up onto the picture and revealing something off-screen.
    assert eq.index("</figure>") < eq.index('class="sbsw-example-btn"')
    assert eq.index('class="sbsw-example-btn"') < eq.index('id="sbsw-example"')

    css = _css()
    assert "text-align: center" in css
    # Picture, scrim and copy in one grid cell, so the frame grows to hold
    # the copy rather than the copy shrinking to fit a 3:1 band.
    assert "grid-area: 1 / 1" in css
    assert ".sbsw-scrim" in css
    assert "aspect-ratio: 1672 / 555" in css


def test_five_stages_numbered_and_described():
    from sweep_config import WORKFLOW

    eq = _section()
    nums = re.findall(r'sbsw-num">([^<]+)<', eq)
    names = re.findall(r'sbsw-stage-name">([^<]+)<', eq)
    assert nums == ["01", "02", "03", "04", "05"]
    assert names == ["Detect", "Match", "Verify", "Claim", "Track"]
    for _num, _name, detail in WORKFLOW:
        assert detail[:40] in eq, detail[:40]
    # Thin dividers, not five cards.
    assert "<svg" in eq and eq.count("<svg") == 1      # the CTA arrow only
    css = _css()
    assert ".sbsw-stage + .sbsw-stage { border-left:" in css


# --- the language ---------------------------------------------------------

def test_nothing_is_guaranteed_found_or_free():
    from sweep_config import get_sweep_config, METHOD

    cfg = get_sweep_config()
    prose = " ".join(
        [cfg["support"], cfg["trust"], cfg["trust_copy"]] +
        [d for _n, _s, d in cfg["workflow"]] +
        [v for _k, v in cfg["example"]["fields"]] +
        [cfg["example"]["action"], cfg["example"]["note"]] +
        [b for _t, b in METHOD]).lower()
    for banned in ("guaranteed recovery", "free money", "instant payout",
                   "we found your money", "100% success", "claim everything",
                   "guarantee", "risk-free"):
        assert banned not in prose, banned
    # The careful words are actually used.
    for careful in ("potential", "possible", "requires verification",
                    "estimated value range"):
        assert careful in prose, careful


def test_no_money_appears_anywhere_in_the_section():
    eq = _section()
    text = re.sub(r"<[^>]+>", " ", eq)
    text = re.sub(r"&#?\w+;", " ", text)
    for banned in ("$", "£", "€", "%", "USD"):
        assert banned not in text, banned
    # The only digits are the stage numbers.
    assert set(re.findall(r"\d+", text)) <= {"01", "02", "03", "04", "05"}


def test_the_example_case_is_labelled_and_carries_no_figure():
    from sweep_config import EXAMPLE

    eq = _section()
    assert 'id="sbsw-example" hidden' in eq          # hidden, not absent
    assert 'aria-controls="sbsw-example"' in eq
    assert "Example recovery opportunity" in eq
    assert "Needs Information" in eq
    for label, value in EXAMPLE["fields"]:
        assert label in eq, label
        assert value[:30] in eq, label
    for item in EXAMPLE["needed"]:
        assert item in eq, item
    assert "not an artist" in eq and "carries no figure" in eq
    assert "Moderate" in eq                          # confidence, not a score


def test_the_sources_say_which_are_live():
    from sweep_config import SOURCES

    statuses = {s for _n, s in SOURCES}
    assert statuses <= {"Connected", "Upload Supported", "Integration Ready",
                        "Coming Soon"}
    # Nothing claims a live connection this app does not hold.
    assert "Connected" not in statuses
    body = _anon().get("/royalty-sweep").get_data(as_text=True)
    for name, status in SOURCES:
        assert name in body, name
        assert status in body, status
    assert "Nothing" in body and "claims a live connection" in body


# --- the photograph -------------------------------------------------------

def test_one_archival_photograph_with_no_people():
    eq = _section()
    assert eq.count("<img") == 1
    alt = re.search(r'alt="([^"]+)"', eq).group(1)
    assert alt == ("Archive table covered with master tapes, hard drives, test "
                   "pressings, notebooks and music-rights documents.")
    words = set(re.findall(r"[a-z]+", alt.lower()))
    for banned in ("royalty", "sweep", "street", "banker", "recovery", "artist"):
        assert banned not in words, banned


def test_two_crops_chosen_by_the_browser():
    eq = _section()
    assert eq.count('media="(max-width: 767px)"') == 3
    for width in (430, 860):
        assert "sweep-close-%d" % width in eq, width
    for width in (900, 1400, 1672):
        assert "sweep-wide-%d" % width in eq, width
    assert 'width="1672" height="555"' in eq          # no layout shift
    assert 'loading="lazy"' in eq


def test_both_crops_ship_in_three_formats():
    for name, widths in (("wide", (900, 1400, 1672)), ("close", (430, 860))):
        seen = []
        for width in widths:
            for ext in ("avif", "webp", "jpg"):
                asset = "static/img/sweep-%s-%d.%s" % (name, width, ext)
                assert os.path.exists(asset), asset
                with Image.open(asset) as im:
                    assert im.size[0] == width, (asset, im.size)
                    seen.append(round(im.size[0] / im.size[1], 3))
        assert max(seen) - min(seen) < 0.01, (name, seen)


def test_the_photograph_carries_no_invented_registration():
    """The supplied frame had a song-registration form filled in with
    invented writers, a publisher called Street Banker Publishing and the
    number SR-00941-1993, plus SB labels on the boxes, the drives, the
    cassettes and the test pressing. The tool clears all of it."""
    tool = open("tools/clean_sweep_photo.py", encoding="utf-8").read()
    for cleared in ("archive box label", "hard drive label", "cassette stack",
                    "test pressing", "registration form", "registration number"):
        assert cleared in tool, cleared
    assert "SR-00941-1993" in tool                    # named, so it stays named
    eq = _section()
    # Nothing in the section depends on reading the table.
    for word in ("Detect", "Match", "Verify", "Claim", "Track",
                 "Run a Royalty Sweep"):
        assert word in eq, word


# --- destinations ---------------------------------------------------------

def test_the_cta_opens_a_public_preliminary_check():
    eq = _section()
    href = re.search(r'class="sbsw-cta" href="([^"]+)"', eq).group(1)
    assert href == "/catalog-sweep"
    client = _anon()
    page = client.get("/catalog-sweep")
    assert page.status_code == 200
    assert "Tell us what to look at" in page.get_data(as_text=True)
    # The result of the intake is labelled a preliminary check, not a scan.
    body = client.post("/catalog-sweep", data={
        "catalog": "Example Artist", "role": "artist",
        "url": "https://open.spotify.com/artist/x"}).get_data(as_text=True)
    assert "Preliminary catalog coverage check" in body
    assert "No scan has run" in body
    for lie in ("we scanned", "we found", "uncollected royalties found"):
        assert lie.lower() not in body.lower(), lie
    # The gated recovery workspace is still gated.
    assert client.get("/recovery").status_code == 302


def test_the_methodology_page_is_public_and_explains_the_estimate():
    body = _anon().get("/royalty-sweep").get_data(as_text=True)
    for heading in ("What gets reviewed", "What counts as a potential opportunity",
                    "How estimates are calculated", "How cases are verified",
                    "Which steps need a person", "How your data is handled"):
        assert heading in body, heading
    assert "It does not find money" in body
    assert "estimated value range" in body
    assert "requires verification" in body
    assert "not used to train models without your explicit permission" in body


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
    for banned in ("background: #fff", "background: white", "border-radius: 999px"):
        assert banned not in css, banned


def test_accessibility_scaffolding():
    eq = _section()
    assert 'aria-labelledby="sbsw-heading"' in eq
    assert '<h2 class="sbsw-title" id="sbsw-heading">' in eq
    assert 'aria-expanded="false"' in eq
    css = _css()
    assert "outline: 2px solid var(--sw-brass)" in css
    assert "min-height: 54px" in css                  # the CTA target
    assert ":focus-within" in css                     # stage emphasis by keyboard


def test_the_analytics_report_stages_and_nothing_else():
    js = open("static/js/sweep.js", encoding="utf-8").read()
    for event in ("sweep_section_viewed", "sweep_run_clicked",
                  "sweep_example_case_opened", "sweep_stage_selected",
                  "sweep_methodology_clicked"):
        assert '"%s"' % event in js, event
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    for sensitive in ("email", "user_id", "localStorage", "statement",
                      "catalog", "amount"):
        assert sensitive not in code, sensitive


def test_the_assets_are_linked_and_the_cache_version_moved():
    body = _home()
    assert "/static/css/sweep.css" in body
    assert "/static/js/sweep.js" in body
    sw = open("static/js/sw.js", encoding="utf-8").read()
    version = re.search(r'VERSION = "sb-v(\d+)"', sw)
    assert version and int(version.group(1)) >= 92
