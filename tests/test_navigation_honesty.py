"""Navigation invariants: is it reachable, and does the nav tell the truth?

Written after an audit found a shipped product with a route, a template, a
gate and tests — and no way for any user to discover it. Every check here is
a generalisation of a real defect, not a hypothetical:

  * /audio-studio had no entry on any of the four nav surfaces
  * hubs.py described a connected Remix Lab as "Preview today"
  * LIVE_KEYS was a flat literal, so four surfaces badged a live page as
    "example data, not yours"
  * four Command Center tiles pointed at /links/builder, which is a 404
  * the Voice Vault lane advertised itself and then refused 100% of the time
"""
import re

import pytest

import hubs


@pytest.fixture(scope="module")
def application():
    import app as appmod
    return appmod.app


def _hub_items():
    for _key, _name, _desc, items in hubs.HUBS:
        for item in items:
            yield item


# --- reachability ----------------------------------------------------------

def test_every_hub_href_resolves_to_a_real_route(application):
    """A nav entry pointing at a 404 is worse than no entry: it is the app
    telling somebody a page exists."""
    rules = {str(r) for r in application.url_map.iter_rules()}
    missing = []
    for key, href, _icon, label, _desc in _hub_items():
        if href.startswith(("http://", "https://", "#")):
            continue
        # Rules with converters cannot be matched by string equality.
        if href not in rules and not any(
                re.match("^" + re.sub(r"<[^>]+>", "[^/]+", rule) + "$", href)
                for rule in rules if "<" in rule):
            missing.append("%s -> %s" % (label, href))
    assert not missing, "hub entries pointing nowhere: %s" % missing


def test_the_audio_studio_is_in_the_navigation():
    """Four of the eight Audio Intelligence products live only at
    /audio-studio. Without a hub entry they are reachable by URL alone."""
    hrefs = [item[1] for item in _hub_items()]
    assert "/audio-studio" in hrefs


def test_no_template_links_to_a_route_that_does_not_exist(application):
    """Catches the /links/builder class of defect: a plausible-looking href
    that was never a route. Scoped to the app's own absolute paths."""
    import glob
    import os

    rules = {str(r) for r in application.url_map.iter_rules()}
    patterned = [r for r in rules if "<" in r]

    def resolves(path):
        if path in rules:
            return True
        return any(re.match("^" + re.sub(r"<[^>]+>", "[^/]+", rule) + "$", path)
                   for rule in patterned)

    # Only literal hrefs with no Jinja in them, and only ones that look like
    # app routes rather than assets or anchors.
    href_re = re.compile(r'href="(/[a-z0-9][a-z0-9\-/]*)"')
    broken = []
    for path in glob.glob(os.path.join("templates", "**", "*.html"), recursive=True):
        with open(path, encoding="utf-8", errors="replace") as handle:
            body = handle.read()
        for match in href_re.finditer(body):
            href = match.group(1)
            if href.startswith(("/static/", "/uploads/")):
                continue
            if not resolves(href) and not resolves(href.rstrip("/")):
                broken.append("%s -> %s" % (os.path.basename(path), href))

    assert not broken, "templates link to non-routes: %s" % sorted(set(broken))[:12]


# --- the nav telling the truth ---------------------------------------------

def test_live_keys_is_computed_not_frozen(monkeypatch):
    """LIVE_KEYS as a literal cannot describe a flag-gated page. Remix Lab
    was live and four surfaces still called it sample data."""
    monkeypatch.delenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", raising=False)
    assert "remix-lab" not in hubs.live_keys()

    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", "1")
    assert "remix-lab" in hubs.live_keys()


def test_no_hub_description_promises_a_state_it_cannot_know():
    """A static one-liner cannot say whether a flag-gated engine is on. Remix
    Lab's said "Preview today" and went on saying it after it was connected."""
    for _key, _href, _icon, label, desc in _hub_items():
        lowered = (desc or "").lower()
        for claim in ("preview today", "coming soon", "not connected",
                      "not yet built"):
            assert claim not in lowered, \
                "%s claims a deployment state in a static string: %r" % (label, desc)


def test_the_audio_studio_is_not_badged_live_until_a_lane_is_on(monkeypatch):
    """Its lanes each need their own flag. The umbrella alone is not enough,
    and badging it live would promise what every lane would refuse."""
    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    for lane_flag in ("GLOBAL_RELEASE_PACK_ENABLED", "CAMPAIGN_AUDIO_TOOLKIT_ENABLED",
                      "SOUND_EFFECTS_ENABLED", "STEM_SEPARATION_ENABLED",
                      "VOICE_ISOLATION_ENABLED", "DUBBING_ENABLED"):
        monkeypatch.delenv(lane_flag, raising=False)
    assert "audio-studio" not in hubs.live_keys()

    monkeypatch.setenv("CAMPAIGN_AUDIO_TOOLKIT_ENABLED", "1")
    monkeypatch.setenv("SOUND_EFFECTS_ENABLED", "1")
    assert "audio-studio" in hubs.live_keys()


# --- a lane that cannot complete must not offer itself ---------------------

def test_the_voice_vault_never_advertises_as_available(monkeypatch):
    """gate() wants a voice_owner consent row and record_consent() has no
    caller anywhere, so the lane would refuse every submission it accepted."""
    import audio_studio

    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("ARTIST_VOICE_VAULT_ENABLED", "1")
    monkeypatch.setenv("VOICE_CLONING_ENABLED", "1")

    vault = [l for l in audio_studio._lanes_for_render() if l["key"] == "voice_vault"][0]
    assert not vault["on"], "a lane that always refuses is offering itself"


def test_the_consent_gap_that_holds_it_off_is_still_real():
    """The guard exists because nothing records consent. If a consent flow is
    ever built, this test fails and the lane should be re-enabled - that is
    the point of it."""
    import ast
    import glob

    # Parsed, not grepped. A text search matches the comment in
    # audio_studio.py that EXPLAINS the gap, so it reported the guard's own
    # docstring as the thing that closes it.
    callers = []
    for path in glob.glob("*.py"):
        if path == "audio_store.py":
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                tree = ast.parse(handle.read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (func.attr if isinstance(func, ast.Attribute)
                    else getattr(func, "id", None))
            if name == "record_consent":
                callers.append(path)
                break

    assert not callers, (
        "record_consent now has callers (%s) - if voice_owner consent can be "
        "recorded, remove 'voice_vault' from audio_studio._CONSENT_FLOW_MISSING"
        % callers)


# --- the admin page must not imply a dead switch works ---------------------

def test_flags_that_gate_nothing_are_marked_as_such():
    """An operator setting a switch, seeing it read 'on', and getting no
    behaviour change is worse served than by no switch at all."""
    import audio_admin

    rows = audio_admin._flag_rows()
    assert rows, "no flags reported"
    assert all("wired" in row for row in rows)

    unwired = {row["name"] for row in rows if not row["wired"]}
    # Whatever the current set is, every member must genuinely gate nothing.
    import audio_policy
    import audio_studio
    gated = {spec["flag"] for spec in audio_policy.FEATURES.values()}
    gated |= {lane[2] for lane in audio_studio.LANES}
    gated |= {"AUDIO_INTELLIGENCE_ENABLED", "ELEVENLABS_ENABLED"}
    assert not (unwired & gated), \
        "flags marked unwired that actually gate something: %s" % (unwired & gated)
