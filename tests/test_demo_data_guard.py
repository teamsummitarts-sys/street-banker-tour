"""What a brand-new artist sees, and whether it is honest.

Every other test in this suite logs in as demo@streetbanker.io. That
account is *meant* to be full of sample data - it is the showcase. So the
suite has been exercising the one path where fabricated numbers are
harmless, and almost never the path where they are dangerous: a real
artist who signed up ten seconds ago, has uploaded nothing, and has no
way to tell which figures on screen are theirs.

The standing rule is that demo data, estimates, simulations and
integration-ready features must be clearly labelled. These tests hold the
line on a fresh, empty, non-demo account.
"""
import os
import re

from app import create_app

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Words that count as telling the user the number is not theirs. Kept
# deliberately broad - the point is to catch pages with NO disclosure at
# all, not to police wording.
DISCLOSURE = re.compile(
    r"sample data|demo data|example data|placeholder"
    r"|estimate|estimated|projection|projected|illustrative"
    r"|preview|not yet connected|nothing connected|no source linked"
    r"|upload a (royalty )?statement|connect .{0,24}to see"
    r"|signal only|not an appraisal|not financial advice"
    r"|not a guarantee|once you connect|when you connect",
    re.I,
)

_counter = [0]


def fresh_artist(app_obj=None):
    """A real account with an empty world: no statements, no catalog, no
    connections. This is the state every paying user starts in."""
    app_obj = app_obj or create_app()
    client = app_obj.test_client()
    _counter[0] += 1
    email = "guard%d@example.com" % _counter[0]
    r = client.post("/signup", data={
        "name": "Guard Test",
        "email": email,
        "password": "guardpw123",
    })
    assert r.status_code == 302, "signup failed: %s" % r.status_code
    return client, app_obj


def _artist_get_routes(app_obj):
    """Every plain GET page an artist can reach - no parameters, no
    downloads, no logout, no redirect-only endpoints."""
    skip = ("/logout", "/static/", "/sw.js", "/manifest",
            "/health", "/healthz", "/robots.txt")
    out = []
    for rule in app_obj.url_map.iter_rules():
        if "GET" not in rule.methods or "<" in rule.rule:
            continue
        if any(rule.rule.startswith(s) or rule.rule == s for s in skip):
            continue
        out.append(rule.rule)
    return sorted(out)


def test_a_fresh_account_can_load_every_page_without_erroring():
    """The suite logs in as demo everywhere else. An empty account takes
    different branches - empty lists, None totals, no catalog - and those
    branches are the ones that have never been walked."""
    client, app_obj = fresh_artist()
    broken = []
    for path in _artist_get_routes(app_obj):
        try:
            r = client.get(path)
        except Exception as exc:                       # pragma: no cover
            broken.append((path, "raised %s: %s" % (type(exc).__name__, exc)))
            continue
        if r.status_code >= 500:
            broken.append((path, r.status_code))
    assert not broken, (
        "%d page(s) break for a brand-new artist:\n%s"
        % (len(broken), "\n".join("  %s -> %s" % b for b in broken)))


# --- the EPK identity ----------------------------------------------------

# Distinctive strings from epk_config._EPK_PROFILE. If any of these reach a
# real artist, the showcase identity is leaking again.
SHOWCASE = [
    "Synthwave-driven pop",
    "Indie Wave",
    "Nightdrive Mag",
    "Street Banker Management",
    "booking@streetbanker.co",
    "press@streetbanker.co",
    "multi-million-stream",
]


def test_a_real_artist_is_never_handed_the_showcase_identity():
    """_EPK_PROFILE is a fictional artist: a bio claiming a multi-million
    stream catalog, a management company, booking and press addresses, and
    two pull-quotes credited to publications that do not exist. It used to
    be the default for every account."""
    client, _ = fresh_artist()
    for path in ("/epk", "/artist-profile"):
        body = client.get(path).get_data(as_text=True)
        leaked = [s for s in SHOWCASE if s in body]
        assert not leaked, "%s hands a real artist: %s" % (path, leaked)


def test_saving_an_untouched_epk_does_not_adopt_someone_elses_press():
    """The worst version of this bug: the editor prefilled its form from
    the showcase, so an artist who opened /epk and pressed Save Draft
    without typing persisted invented press quotes as their own - and
    published them on a public URL they would send to labels.

    Placeholders show the shape; only values submit. This proves it."""
    import db as store

    client, app_obj = fresh_artist()
    email = "guard%d@example.com" % _counter[0]
    user = store.get_user_by_email(email)

    r = client.post("/epk/save", json={
        "tagline": "", "bio": "", "location": "", "genres": [],
        "socials": [], "press": [],
        "contact": {"booking": "", "management": "", "press": ""},
    })
    assert r.status_code == 200, r.status_code

    saved = (store.get_epk(user["id"]) or {}).get("data") or {}
    blob = str(saved)
    leaked = [s for s in SHOWCASE if s in blob]
    assert not leaked, \
        "an untouched save adopted the showcase identity: %s" % leaked


# --- deleted modules stay deleted ---------------------------------------

# Seven config modules were imported by app.py but never called, and each
# held fabricated figures aimed at exactly the numbers artists care about:
# connections_config claimed "84% connection health", sources marked
# "Connected - Live Data", and "$4,820 missing royalties found" - none of
# it real, none of it labelled. They were one route line away from
# shipping. Three of them even had matching unlabelled templates already
# written. The real pages for these routes read per-user statement data
# through royalty_types instead.
DELETED_MODULES = [
    "connections_config", "neighboring_rights_config", "tax_config",
    "stats_config", "publishing_config", "mechanicals_config",
    "territories_config",
]

DELETED_TEMPLATES = [
    "neighboring_rights.html", "mechanicals.html", "publishing.html",
]


def test_the_unreachable_mock_modules_are_gone():
    """Not a style rule. Re-adding one of these puts a fabricated
    'missing royalties' dollar figure one import away from a real
    artist's screen."""
    import importlib

    back = []
    for name in DELETED_MODULES:
        if os.path.exists(os.path.join(HERE, name + ".py")):
            back.append(name)
            continue
        try:
            importlib.import_module(name)
        except ImportError:
            pass
        else:                                          # pragma: no cover
            back.append(name + " (importable)")
    assert not back, (
        "mock config modules are back: %s. If a page needs this data, read "
        "it per-user through royalty_types, or label it with "
        "partials/data_label.html." % back)


def test_the_orphan_mock_templates_are_gone():
    present = [t for t in DELETED_TEMPLATES
               if os.path.exists(os.path.join(HERE, "templates", t))]
    assert not present, "unlabelled mock templates are back: %s" % present


# --- the network directory ----------------------------------------------

def test_every_network_profile_page_says_it_is_not_a_real_person():
    """Each of the 22 profiles carries a Verified badge, a follower count
    and an Available dot, then offers Connect / Send a Pitch / Enquire
    About Shows. network_config.pitch() appends to an in-memory list -
    nothing is delivered. The index said so; the page where someone
    decides to write the pitch did not."""
    import network_config

    client, _ = fresh_artist()
    unlabelled = []
    for p in network_config._PROFILES:
        r = client.get("/network/%s" % p["id"])
        if r.status_code != 200:
            continue
        body = r.get_data(as_text=True)
        if "not a real person" not in body:
            unlabelled.append(p["id"])
    assert not unlabelled, (
        "%d profile page(s) present an invented contact with no label: %s"
        % (len(unlabelled), unlabelled[:6]))
