"""The public header: brand first, and no login wall in front of the
product story.

The old one led with "ARTIST INFRASTRUCTURE" over a small dark wordmark,
pointed Platform at /overview and the free-scan CTA at /recovery - both
of which bounce a signed-out visitor into a password field for asking
what the product is. These hold the replacement.
"""

import os
import re

from app import create_app


def _anon():
    return create_app().test_client()


def _home():
    return _anon().get("/").get_data(as_text=True)


def test_the_lockup_is_the_vector_logo_plus_live_text():
    body = _home()
    assert "streetbanker-logo-light.svg" in body
    # The descriptor is text, not baked into the image.
    assert "The Artist<br>Operating System" in body
    assert os.path.exists("static/img/streetbanker-logo-light.svg")
    # The originals are untouched.
    for original in ("static/img/streetbanker-logo.svg",
                     "static/img/streetbanker-logo-dark.svg"):
        assert os.path.exists(original), original


def test_the_light_logo_keeps_the_original_geometry():
    """Same brackets, same wordmark, same spacing - only the fill differs.
    A redrawn logo is a different logo."""
    light = open("static/img/streetbanker-logo-light.svg", encoding="utf-8").read()
    dark = open("static/img/streetbanker-logo-dark.svg", encoding="utf-8").read()
    paths = lambda svg: re.findall(r'd="([^"]+)"', svg)
    assert paths(light) == paths(dark)
    assert 'viewBox="0 0 920 250"' in light
    assert ".street banker" in light          # the period is part of it
    assert 'font-size="104"' in light and 'letter-spacing="-2"' in light
    assert 'stroke-width="18"' in light


def test_navigation_reaches_real_places():
    body = _home()
    for label in ("Platform", "AI Artist Twin", "Creative + Rollout",
                  "Royalty Sweep", "For Labels"):
        assert label in body, label
    # Every same-page target exists in the document, and every hash link
    # is written /#name rather than #name - the header renders on eleven
    # public pages, and a bare #platform on /rollout scrolls to nothing.
    for anchor in ("platform", "artist-twin-section", "creative-studio",
                   "royalty-sweep"):
        assert 'id="%s"' % anchor in body, anchor
        assert 'href="/#%s"' % anchor in body, anchor


def test_no_navigation_item_bounces_a_visitor_to_login():
    """A public visitor asking what the product is must not be handed a
    password field. Every non-anchor destination in the header answers
    for itself, signed out."""
    app_obj = create_app()
    body = app_obj.test_client().get("/").get_data(as_text=True)
    header = body[body.index('<header class="sbh"'):body.index("</header>")]
    hrefs = set(re.findall(r'href="([^"]+)"', header))
    client = app_obj.test_client()
    for href in hrefs:
        if href.startswith("#") or href == "/login":
            continue
        response = client.get(href)
        assert response.status_code == 200, (href, response.status_code)


def test_the_cta_says_what_it_does():
    body = _home()
    assert "Run a Free Catalog Sweep" in body
    assert 'href="/catalog-sweep"' in body
    assert "Free Sweep" in body                     # the phone's short form
    for vague in ("Start Free", "Get Started", "Learn More", "Explore Now"):
        assert vague not in body, vague


def test_the_sweep_entry_is_open_to_a_stranger():
    client = _anon()
    page = client.get("/catalog-sweep")
    assert page.status_code == 200                  # not a redirect to login
    body = page.get_data(as_text=True)
    assert "Tell us what to look at" in body
    for field in ('name="catalog"', 'name="url"', 'name="role"'):
        assert field in body, field
    for role in ("artist", "songwriter", "producer", "manager", "label"):
        assert 'value="%s"' % role in body, role


def test_the_sweep_result_never_claims_a_scan_ran():
    client = _anon()
    body = client.post("/catalog-sweep", data={
        "catalog": "Synthwave Surfer", "role": "producer",
        "url": "https://open.spotify.com/artist/x"}).get_data(as_text=True)
    assert "Preliminary catalog coverage check" in body
    assert "No scan has run" in body
    assert "read a platform" in body                # says what it did not do
    # An account is offered after the explanation, never demanded before it.
    assert "/signup" in body
    for lie in ("we found", "we scanned", "issues detected", "uncollected royalties found"):
        assert lie.lower() not in body.lower(), lie


def test_the_header_is_one_component_used_by_both_public_pages():
    for path in ("/", "/catalog-sweep"):
        body = _anon().get(path).get_data(as_text=True)
        assert 'id="sb-header"' in body, path
        assert 'id="sb-header-drawer"' in body, path


def test_accessibility_scaffolding():
    body = _home()
    assert 'class="sbh-skip" href="#main"' in body   # skip link
    assert 'id="main"' in body                       # ...with a target
    assert '<header class="sbh"' in body
    assert 'aria-label="Product"' in body            # the nav is named
    assert 'aria-expanded="false"' in body           # accurate at rest
    assert 'aria-controls="sb-header-drawer"' in body
    assert 'role="dialog"' in body and 'aria-modal="true"' in body
    assert 'aria-label="Street Banker menu"' in body


def test_the_header_assets_exist_and_are_versioned():
    body = _home()
    for asset in ("/static/css/public-header.css", "/static/js/public-header.js"):
        assert asset in body, asset
        assert os.path.exists(asset.lstrip("/")), asset
    # The service worker caches /static first, so a changed asset needs a
    # new cache version or returning visitors keep the old header. Pinned
    # to the release that shipped it and allowed to move forward only.
    sw = open("static/js/sw.js", encoding="utf-8").read()
    version = re.search(r'VERSION = "sb-v(\d+)"', sw)
    assert version and int(version.group(1)) >= 84, sw[:200]


def test_the_header_holds_its_own_space():
    """Sticky, and sized in CSS rather than by whatever is inside it - a
    bar that measures itself is a bar that shifts the page."""
    css = open("static/css/public-header.css", encoding="utf-8").read()
    assert "position: sticky" in css
    assert "--sbh-height: 86px" in css
    assert "--sbh-height-mobile: 70px" in css
    assert "prefers-reduced-motion" in css
    assert "env(safe-area-inset" in css


# --- login: one credential form, and a box that remembers its own state ----

def test_the_login_page_has_exactly_one_credential_form():
    """Two forms posting email+password to /login is what stops a browser
    offering to save the real sign-in: the password manager cannot tell
    which pair belongs to the account, and would sometimes save the demo
    address instead."""
    body = _anon().get("/login").get_data(as_text=True)
    forms = re.findall(r"<form[^>]*>", body)
    to_login = [f for f in forms if 'action="/login"' in f]
    assert len(to_login) == 1, to_login
    # The demo workspace form is still there - it just is not a login.
    assert 'action="/demo-open"' in body
    assert 'name="demo_password"' in body
    assert 'name="demo_workspace"' in body


def test_the_real_form_is_labelled_for_a_password_manager():
    body = _anon().get("/login").get_data(as_text=True)
    assert 'autocomplete="username"' in body
    assert 'autocomplete="current-password"' in body
    assert 'name="remember"' in body


def test_demo_open_only_opens_demo_accounts():
    app_obj = create_app()
    # Right password, real demo workspace: in.
    good = app_obj.test_client()
    good.post("/demo-open", data={"demo_workspace": "demo-artist@streetbanker.io",
                                  "demo_password": "sweep"})
    with good.session_transaction() as sess:
        assert sess.get("user_id")
    # Wrong password: not in.
    bad = app_obj.test_client()
    bad.post("/demo-open", data={"demo_workspace": "demo-artist@streetbanker.io",
                                 "demo_password": "wrong"})
    with bad.session_transaction() as sess:
        assert not sess.get("user_id")
    # A real account cannot be opened through the demo door, whatever is
    # typed into it.
    other = app_obj.test_client()
    other.post("/demo-open", data={"demo_workspace": "someone@real.com",
                                   "demo_password": "sweep"})
    with other.session_transaction() as sess:
        assert not sess.get("user_id")


def test_remember_this_device_is_on_unless_it_was_turned_off():
    """Unticked, a sign-in lasts only until the browser closes — and a
    box nobody noticed meant signing in again every visit, which reads as
    the feature being broken. It ships ticked; the script restores only an
    explicit opt-out, so somebody who turned it off stays turned off."""
    js = open("static/js/login-session-recall.js", encoding="utf-8").read()
    assert "sbRemember" in js
    assert 'localStorage.getItem("sbRemember") === "0"' in js
    assert "remember.checked = false" in js

    body = _anon().get("/login").get_data(as_text=True)
    box = re.search(r'<input[^>]*id="lsr-remember"[^>]*>', body).group(0)
    assert 'name="remember"' in box
    assert "checked" in box, box


def test_the_session_cookie_is_configured_for_a_real_return_visit():
    """31 days when asked for, Lax so a click from an email keeps you
    signed in, and Secure only where the site is actually on TLS."""
    import os
    app_obj = create_app()
    assert app_obj.permanent_session_lifetime.days == 31
    assert app_obj.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app_obj.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app_obj.config["SESSION_COOKIE_SECURE"] is False      # local http
    os.environ["RENDER"] = "true"
    try:
        assert create_app().config["SESSION_COOKIE_SECURE"] is True
    finally:
        os.environ.pop("RENDER", None)


# --- section 2: the hero ----------------------------------------------------

def test_the_hero_is_live_html_over_a_photograph():
    """Nothing in the reference is flattened into the image: the eyebrow,
    headline, copy, buttons and the product panel are all markup."""
    body = _home()
    assert 'class="sbhero"' in body
    assert "BUILD THE RELEASE." in body and "OWN THE MOMENT." in body
    assert "STREET BANKER · THE ARTIST OPERATING SYSTEM" in body
    assert "creative tools, rollout intelligence" in body
    assert body.count("<h1") == 1


def test_the_hero_ships_a_responsive_image_set():
    """Two crops - wide for desktop, band-first for phones - in three
    formats, so a phone never pulls the desktop frame."""
    body = _home()
    for asset in ("hero-band-wide-1342.avif", "hero-band-wide-1100.webp",
                  "hero-band-wide-900.jpg", "hero-band-tall-640.avif",
                  "hero-band-tall-900.webp"):
        assert asset in body, asset
        assert os.path.exists("static/img/" + asset), asset
    assert 'media="(max-width: 1023px)"' in body      # the phone crop
    assert 'sizes="100vw"' in body
    assert 'width="1342" height="775"' in body        # no layout shift
    assert 'fetchpriority="high"' in body


def test_the_hero_ctas_go_somewhere_public():
    body = _home()
    assert 'href="#platform"' in body                 # the product story
    assert 'href="/catalog-sweep"' in body            # the sweep entry
    client = _anon()
    assert client.get("/catalog-sweep").status_code == 200
    assert 'id="platform"' in body


def test_the_hero_product_panel_is_labelled_as_an_example():
    """A panel of live UI, not a screenshot, and not a claim about
    anybody's account."""
    body = _home()
    assert "Release Readiness" in body
    assert "Example workspace" in body
    assert "A real account scores this from its own tracks and statements" in body
    # No invented money or customer numbers anywhere in the hero.
    hero = body[body.index('class="sbhero"'):body.index("<!-- 3.")]
    assert "$" not in hero
    for invented in ("artists served", "recovered for", "customers", "% growth"):
        assert invented.lower() not in hero.lower(), invented


def test_the_hero_is_accessible():
    body = _home()
    assert 'aria-labelledby="sbhero-title"' in body
    assert ('alt="Four-piece band in the dark backline of a venue: the '
            'frontman in a denim jacket up front, flanked by two masked '
            'members and a hooded bandmate."' in body)
    assert 'aria-label="Example of the Release Readiness panel"' in body
    css = open("static/css/hero.css", encoding="utf-8").read()
    assert "prefers-reduced-motion" in css
    assert ".sbhero a:focus-visible" in css
    # Sized so it sits under the sticky bar rather than behind it.
    assert "calc(100svh - var(--sbh-height))" in css


# --- section 3: the Artist EQ ----------------------------------------------

def test_the_eq_has_six_channels_and_no_fake_frequencies():
    """The fifteen bands were engraved 25 Hz to 16 kHz, which made a
    business diagnostic read as a novelty plug-in."""
    import artist_eq_config as cfg
    body = _home()
    assert len(cfg.CHANNELS) == 6
    assert body.count('class="sbeq-range"') == 6
    for label in ("RELEASE", "CREATIVE", "AUDIENCE", "RIGHTS", "REVENUE", "GROWTH"):
        assert label in body, label
    for fake in ("25 Hz", "100 Hz", "1 kHz", "16 kHz"):
        assert fake not in body, fake


def test_the_eq_controls_are_native_and_described():
    body = _home()
    assert body.count('type="range"') == 6
    assert 'min="0" max="10" step="0.5"' in body
    assert body.count("aria-describedby=\"sbeq-desc-") == 6
    assert 'aria-labelledby="sbeq-heading"' in body
    assert 'aria-live="polite"' in body


def test_every_preset_produces_a_different_plan():
    """Six presets that all recommend the same thing would be six
    buttons pretending to be a diagnostic."""
    import artist_eq_config as cfg
    seen = {}
    for preset in cfg.PRESETS:
        if not preset["values"]:
            continue
        plan = cfg.build_plan(preset["values"], preset["id"])
        key = (plan["lane"]["id"], tuple(m["slug"] for m in plan["modules"]))
        seen.setdefault(key, []).append(preset["id"])
        assert 0 <= plan["score"] <= 100
        assert len(plan["modules"]) == cfg.MAX_MODULES
        assert len(plan["actions"]) == cfg.ACTION_COUNT
    assert len(seen) >= 3, seen


def test_the_score_is_bounded_and_deterministic():
    import artist_eq_config as cfg
    extremes = [
        ({k: 0 for k in cfg.CHANNEL_KEYS}, 0),
        ({k: 10 for k in cfg.CHANNEL_KEYS}, 100),
    ]
    for values, expected in extremes:
        assert cfg.readiness(values, None) == expected
    # Same input, same plan, every time - the browser and /plan both
    # compute it, and a drift would change the plan on click.
    values = {"release": 7, "creative": 3.5, "audience": 6, "rights": 9,
              "revenue": 8, "growth": 4}
    first = cfg.build_plan(values, "custom")
    for _ in range(3):
        assert cfg.build_plan(values, "custom") == first
    # Junk in the query string cannot move it out of range.
    assert 0 <= cfg.readiness({"release": "abc", "rights": 99}, None) <= 100


def test_the_score_never_claims_to_predict_anything():
    """The disclaimer has to be present and the claims absent - which
    means testing for claims rather than for the word "predict", since
    the disclaimer itself has to use that word."""
    body = _home()
    eq = body[body.index('id="artist-eq"'):]
    eq = eq[:eq.index("</section>")].lower()
    for claim in ("guaranteed", "will become a hit", "we predict",
                  "predicts your", "chart position", "sign you", "recover $"):
        assert claim not in eq, claim
    assert "predicts no hit" in eq                     # the console says it
    plan = _anon().get("/plan").get_data(as_text=True).lower()
    assert "does not predict a hit" in plan            # and so does the plan


def test_the_plan_page_is_public_and_recomputes_the_same_plan():
    import artist_eq_config as cfg
    values = {"release": 4, "creative": 3, "audience": 4, "rights": 10,
              "revenue": 10, "growth": 5}
    expected = cfg.build_plan(values, "missing-royalties")
    query = "&".join("%s=%s" % (k, v) for k, v in values.items())
    response = _anon().get("/plan?%s&preset=missing-royalties" % query)
    assert response.status_code == 200          # no login wall
    body = response.get_data(as_text=True)
    assert str(expected["score"]) in body
    assert expected["lane"]["name"] in body
    for module in expected["modules"]:
        assert module["name"] in body or module["name"].replace("&", "&amp;") in body
        assert 'id="%s"' % module["slug"] in body
    assert expected["setup_time"] in body


def test_the_eq_background_carries_no_baked_text():
    """The supplied plate had the heading and every panel label painted
    into it. All of that is markup now, and the image is the room."""
    import os
    for asset in ("eq-room-1600.avif", "eq-room-1200.webp", "eq-room-900.jpg"):
        assert os.path.exists("static/img/" + asset), asset
    body = _home()
    assert "eq-room-1200.jpg" in body
    assert 'alt=""' in body                      # decorative, per the brief
    # The words are in the DOM, which is where a screen reader can reach
    # them - not inside a JPEG.
    for label in ("System readiness", "Recommended modules", "Top 3 actions",
                  "Choose your focus preset", "TUNE YOUR ARTIST SYSTEM."):
        assert label in body, label


def test_the_console_is_already_correct_before_any_script_runs():
    """Server-rendered from the same engine the browser uses: no empty
    lists, no placeholder score that the page then corrects."""
    from artist_eq_config import get_artist_eq_config, build_plan, default_values

    cfg = get_artist_eq_config()
    plan = build_plan(default_values(), cfg["default_preset"])
    body = _home()
    eq = body[body.index('id="artist-eq"'):]
    eq = eq[:eq.index("</section>")]
    assert '<span class="sbeq-score" id="sbeq-score">%d<' % plan["score"] in eq
    assert '<p class="sbeq-band" id="sbeq-band">%s<' % plan["band"] in eq
    assert plan["lane"]["name"] in eq and plan["lane"]["why"] in eq
    assert plan["setup_time"] in eq
    for module in plan["modules"]:
        assert module["name"].replace("&", "&amp;") in eq, module["name"]
    for action in plan["actions"]:
        assert action["label"] in eq, action["label"]
    # Six plotted points, drawn before the script smooths them.
    assert eq.count('r="2.6"') == 6
    # Every link out of the panel already carries the mix.
    assert "/plan?%s" % cfg["default_query"].replace("&", "&amp;") in eq


def test_the_plan_query_is_the_same_string_on_both_sides():
    """The server-rendered link and the one the browser rewrites have to
    agree, or the plan changes under the visitor on click."""
    from artist_eq_config import get_artist_eq_config, plan_query, default_values

    cfg = get_artist_eq_config()
    query = plan_query(default_values(), cfg["default_preset"])
    assert query.startswith("release=")           # channel order, not dict order
    assert query.endswith("preset=" + cfg["default_preset"])
    assert ".0" not in query                      # 10, never 10.0
    js = open("static/js/artist-eq.js", encoding="utf-8").read()
    assert 'k + "=" + encodeURIComponent(state.values[k])' in js
    assert 'params.push("preset="' in js
    assert _anon().get("/plan?" + query).status_code == 200


def test_the_saved_mix_still_reaches_the_account():
    """The EQ writes the profile the Command Center, Artist Twin and
    onboarding panel read - and only once the visitor has moved something,
    so an untouched section never overwrites a mix set on another day."""
    js = open("static/js/artist-eq.js", encoding="utf-8").read()
    assert 'localStorage.setItem("streetBankerArtistSignalProfile"' in js
    assert '"/api/artist-signal-profile"' in js
    assert 'credentials: "same-origin"' in js
    assert "if (interacted) { saveProfile(" in js
    for field in ("topPriorities", "recommendedLane", "recommendedModules",
                  "firstActions", "source"):
        assert field in js, field


def test_the_header_row_fits_a_1024_laptop():
    """Brand 195 + five nav items + the full CTA is wider than a 1024
    viewport, so the wide variants start at 1180 instead."""
    css = open("static/css/public-header.css", encoding="utf-8").read()
    wide = css[css.index("@media (min-width: 1180px)"):]
    assert "@media (min-width: 1180px)" in css
    assert ".sbh-cta-full { display: inline; }" in css
    # The short label is the default and only gives way above 1180.
    assert css.index(".sbh-cta-short { display: inline; }") < css.index(
        "@media (min-width: 1180px) {\n  .sbh-cta-full")
