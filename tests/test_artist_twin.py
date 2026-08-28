"""Section 5 — the AI Artist Twin.

The load-bearing claims: the example is labelled as an example, the
photograph and the interface are separate layers, the reasoning is
readable, nothing forecasts, and a stranger can find out what the thing
does - and what happens to their music - without an account.
"""

import os
import re

from app import create_app


def _anon():
    return create_app().test_client()


def _home():
    return _anon().get("/").get_data(as_text=True)


def _section(body=None):
    body = body or _home()
    start = body.index('id="artist-twin-section"')
    return body[start:start + body[start:].index("</section>")]


def _css():
    return open("static/css/artist-twin.css", encoding="utf-8").read()


# --- placement and copy ---------------------------------------------------

def test_the_section_sits_after_the_departments_and_displaces_nothing():
    body = _home()
    assert body.index('id="departments"') < body.index('id="artist-twin-section"')
    assert body.index('id="artist-twin-section"') < body.index('id="lanes"')
    for kept in ["One system. Six departments.", "TUNE YOUR ARTIST SYSTEM.",
                 "Choose your lane.", "Built for artist control.",
                 "sbhero-veil", "Your catalog is the "]:
        assert kept in body, kept


def test_the_copy_is_the_approved_copy():
    eq = _section()
    assert "AI Artist Twin" in eq
    assert "Know the artist." in eq and "Test the move." in eq
    assert ("The Artist Twin learns your music, visuals, audience, catalog and "
            "goals" in eq)
    assert "Example Artist Twin assessment" in eq
    assert ("Your Artist Twin supports your decisions. It does not replace your "
            "judgement." in eq)


def test_five_rows_in_order_each_with_a_status():
    eq = _section()
    titles = re.findall(r'sbtw-row-title">([^<]+)<', eq)
    assert titles == ["Release Readiness", "Brand Alignment", "Artwork Strength",
                      "Audience Fit", "Recommended Next Move"]
    statuses = [s.strip() for s in
                re.findall(r'sbtw-status[^"]*">\s*<span class="sbtw-dot"[^>]*></span>([^<]+)', eq)]
    assert statuses == ["Good", "Strong", "Solid", "Good", "Suggested"]
    # The word carries the status; the dot only repeats it.
    assert eq.count('class="sbtw-dot" aria-hidden="true"') == 5


# --- the two layers -------------------------------------------------------

def test_the_photograph_and_the_interface_are_separate_layers():
    eq = _section()
    assert eq.count("<img") == 1
    photo = eq[eq.index("<figure"):eq.index("</figure>")]
    # Nothing from the assessment is inside the picture's markup, and the
    # picture is not a background behind the panel.
    for word in ("Release Readiness", "sbtw-row", "sbtw-status", "Confidence"):
        assert word not in photo, word
    assert "background-image" not in _css().split(".sbtw-photo")[1][:400]


def test_the_alt_text_describes_the_room_and_sells_nothing():
    eq = _section()
    alt = re.search(r'alt="([^"]+)"', eq).group(1)
    assert alt == ("Artist reviewing release photographs and campaign materials "
                   "while team members move through a creative studio.")
    words = set(re.findall(r"[a-z]+", alt.lower()))
    for marketing in ("ai", "twin", "assessment", "intelligence", "banker",
                      "premium", "powerful"):
        assert marketing not in words, marketing


def test_the_photograph_ships_in_three_formats_and_three_sizes():
    eq = _section()
    for fmt in ("image/avif", "image/webp"):
        assert 'type="%s"' % fmt in eq, fmt
    for width in (480, 700, 893):
        for ext in ("avif", "webp", "jpg"):
            asset = "static/img/artist-twin-%d.%s" % (width, ext)
            assert os.path.exists(asset), asset
            assert "artist-twin-%d.%s %dw" % (width, ext, width) in eq
    assert 'width="893" height="941"' in eq        # no layout shift
    assert 'loading="lazy"' in eq


# --- what it promises -----------------------------------------------------

def test_it_forecasts_nothing():
    from artist_twin_config import get_artist_twin_config

    cfg = get_artist_twin_config()
    prose = " ".join(
        [cfg["support"], cfg["microcopy"]] +
        [v for row in cfg["assessment"]
         for k, v in row.items() if k in ("summary", "observation", "why",
                                          "missing", "action")] +
        [step for goal in cfg["goals"] for step in goal["route"]])
    for banned in ("guarantee", "guaranteed", "will chart", "hit probability",
                   "predict", "certain", "%", "$", "projected", "forecast"):
        assert banned not in prose.lower(), banned
    # Confidence is three words, never a number.
    for row in cfg["assessment"]:
        assert row["confidence"] in ("Low", "Moderate", "Strong"), row["id"]


def test_every_row_shows_its_working():
    from artist_twin_config import get_artist_twin_config

    eq = _section()
    for row in get_artist_twin_config()["assessment"]:
        for field in ("observation", "why", "missing", "action"):
            assert row[field], (row["id"], field)
        assert row["observation"][:40] in eq, row["id"]
    for label in ("What the Twin observed", "Why it matters", "Confidence",
                  "Missing inputs", "Recommended action"):
        assert eq.count(label) == 5, label


def test_the_example_is_labelled_before_the_rows():
    eq = _section()
    assert eq.index("Example Artist Twin assessment") < eq.index("Release Readiness")


def test_the_source_strip_says_what_it_reads_from():
    eq = _section()
    sources = re.findall(r'sbtw-source-name">([^<]+)<', eq)
    assert sources == ["Music", "Visuals", "Audience", "Catalog",
                       "Campaign History", "Goals"]
    states = re.findall(r'sbtw-source-state">([^<]+)<', eq)
    assert set(states) <= {"Connected", "Added", "Needs Input"}
    assert "Needs Input" in states          # an honest example is not all green


# --- destinations ---------------------------------------------------------

def test_neither_cta_meets_a_login_wall():
    eq = _section()
    href = re.search(r'class="sbtw-cta" href="([^"]+)"', eq).group(1)
    assert href == "/artist-twin/start"
    client = _anon()
    for path in ("/artist-twin/start", "/ai"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
    # The gated app route is still gated.
    assert _anon().get("/artist-twin").status_code == 302


def test_the_public_start_flow_offers_six_goals_and_promises_nothing():
    client = _anon()
    body = client.get("/artist-twin/start").get_data(as_text=True)
    for goal in ("Preparing a release", "Improving artwork", "Building a rollout",
                 "Growing an audience", "Reviewing rights",
                 "Checking royalty opportunities"):
        assert goal in body, goal
    assert "Nothing has been analyzed yet" in body
    assert "Where it would start" not in body        # nothing picked yet

    picked = client.get("/artist-twin/start?goal=artwork").get_data(as_text=True)
    assert "Where it would start" in picked
    assert "Compare directions at thumbnail size" in picked
    assert "not an assessment of your catalog" in picked
    assert "has read nothing about you" in picked
    # An account is offered after the explanation, never demanded before it.
    assert picked.index("Where it would start") < picked.index("/signup")
    # An unknown goal shows the picker again rather than inventing a route,
    # and nothing from the query string reaches the page.
    junk = client.get("/artist-twin/start?goal=%3Cscript%3Ealert(1)%3C/script%3E")
    assert junk.status_code == 200
    body = junk.get_data(as_text=True)
    assert "alert(1)" not in body
    assert "Where it would start" not in body


def test_the_ai_trust_page_is_public_and_short():
    body = _anon().get("/ai").get_data(as_text=True)
    for point in ("Your catalog stays yours.", "Your work is not training data.",
                  "The recommendations are estimates.",
                  "Nothing is published without you.", "You can change your mind."):
        assert point in body, point
    assert "not used to train models without your explicit" in body
    text = re.sub(r"<[^>]+>", " ", body[body.index("<main"):body.index("</main>")])
    assert len(text.split()) < 400, "this is a page, not a policy document"
    assert '/terms' in body and '/privacy' in body


# --- interface, interaction, accessibility --------------------------------

def test_the_rows_are_native_disclosures_with_honest_state():
    eq = _section()
    assert eq.count("<details") == 5
    assert eq.count("<summary") == 5
    assert eq.count('aria-expanded="false"') == 5   # accurate before script
    js = open("static/js/artist-twin.js", encoding="utf-8").read()
    assert 'setAttribute("aria-expanded"' in js
    assert "other.open = false" in js               # one at a time
    assert "sbtw-explain" in js


def test_the_panel_has_no_gauges_charts_or_predictions():
    eq = _section()
    css = _css()
    for banned in ("progress", "gauge", "chart", "canvas", "speedometer"):
        assert banned not in eq.lower(), banned
    for banned in ("@keyframes", "animation:", "parallax"):
        assert banned not in css, banned
    assert "prefers-reduced-motion" in css
    # Transitions stay short.
    for ms in re.findall(r"transition:[^;]*?(\d+)ms", css):
        assert 120 <= int(ms) <= 250, ms


def test_the_dark_system_is_the_one_in_the_brief():
    css = _css()
    for token in (
                  "var(--sb-ground)",
                  "var(--sb-surface-1)",
                  "var(--sb-surface-2)",
                  "rgb(201 168 106 / 0.26)",
                  "var(--sb-gold)",
                  "var(--sb-ink)",
                  "var(--sb-ink-2)",
                  "var(--sb-good)"
               ):
        assert token in css, token
    assert "background: var(--tw-ink)" in css
    for bright in ("#fff", "#FFF", "background: white"):
        assert bright not in css, bright


def test_accessibility_scaffolding():
    eq = _section()
    assert 'aria-labelledby="sbtw-heading"' in eq
    assert '<h2 class="sbtw-title" id="sbtw-heading">' in eq
    assert eq.count('aria-hidden="true"') >= 11      # icons, dots, chevrons
    assert 'aria-controls="sbtw-artwork-strength"' in eq
    css = _css()
    assert "outline: 2px solid var(--tw-brass)" in css
    assert ":focus-visible" in css
    assert "min-height: 44px" in css                 # touch target


def test_the_analytics_report_rows_and_nothing_else():
    js = open("static/js/artist-twin.js", encoding="utf-8").read()
    for event in ("artist_twin_section_viewed", "artist_twin_row_expanded",
                  "artist_twin_build_clicked", "artist_twin_reasoning_opened",
                  "artist_twin_ai_trust_clicked"):
        assert '"%s"' % event in js, event
    # Look at the code, not the comments: the events carry row ids only.
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    for sensitive in ("observation", "email", "user_id", "localStorage",
                      "summary:", "uploaded"):
        assert sensitive not in code, sensitive
    assert re.findall(r"track\(\"[a-z_]+\", \{([^}]*)\}", code) is not None


def test_the_assets_are_linked_and_the_cache_version_moved():
    body = _home()
    assert "/static/css/artist-twin.css" in body
    assert "/static/js/artist-twin.js" in body
    sw = open("static/js/sw.js", encoding="utf-8").read()
    version = re.search(r'VERSION = "sb-v(\d+)"', sw)
    assert version and int(version.group(1)) >= 88
