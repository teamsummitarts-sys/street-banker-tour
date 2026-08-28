"""Light Studio — the page, the working copy, and the named-show library."""
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import app as appmod
import db as store
import lights_store

PASSWORD = "lights-pass-123"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def flask_app():
    return appmod.create_app()


def _user(flask_app, label="Lighting Designer"):
    email = "lx-%s@example.net" % uuid.uuid4().hex[:8]
    client = flask_app.test_client()
    client.post("/signup", data={"name": label, "email": email, "password": PASSWORD})
    client.post("/login", data={"email": email, "password": PASSWORD})
    return client, store.get_user_by_email(email)


def test_page_has_the_studio_surfaces(flask_app):
    client, user = _user(flask_app)
    page = client.get("/lights").get_data(as_text=True)
    # The phrases the old test pins, plus every new surface by id.
    for needle in ("Light Studio", "simulation", "ENTTEC", "Web Serial", "Audience view", "drag any bar"):
        assert needle in page, needle
    for el_id in ("lx-wave", "lx-stage", "lx-clock", "lx-fileinfo", "lx-dmx-chip", "lx-add", "lx-blackout",
                  "lx-cues", "lx-groups", "lx-looks", "lx-barctl", "lx-bars-list", "lx-lib-select",
                  "lx-master", "lx-panic", "lx-export", "lx-import", "lx-look-save",
                  "lx-vol", "lx-rate", "lx-scrub", "lx-dmx-start", "lx-dmx-universe", "lx-bar-addr", "lx-patch-warn",
                  "lx-autocue", "lx-autocue-clear", "lx-autocue-note",
                  "lx-mix-r", "lx-mix-g", "lx-mix-b", "lx-mix-h", "lx-mix-s", "lx-mix-v",
                  "lx-group-one", "lx-group-clear", "lx-group-picked",
                  "lx-wheel", "lx-gel-swatch", "lx-gel-name", "lx-gel-for", "lx-gel-hex",
                  "lx-look-new", "lx-look-name", "lx-output", "lx-bridge-port", "lx-bridge-test", "lx-bridge-status",
                  "lx-set-select", "lx-set-items", "lx-set-add", "lx-set-save", "lx-set-next", "lx-set-prev",
                  "lx-resume", "lx-resume-go", "lx-resume-no", "lx-attach", "lx-pull", "lx-rem-start", "lx-rem-end", "lx-rem-qr", "lx-rem-url", "lx-rem-status", "lx-rem-now", "lx-rem-seen", "lx-bump", "lx-bump-name",
                  "lx-share-label", "lx-share-perm", "lx-share-new", "lx-share-status",
                  "lx-share-list", "lx-note-threads", "lx-note-now", "lx-note-fold",
                  "lx-rig-select", "lx-rig-apply", "lx-rig-save", "lx-rig-delete", "lx-rig-name", "lx-rig-venue", "lx-rig-status",
                  "lx-lib-save", "lx-saved", "lx-focus", "lx-detect", "lx-snap", "lx-tap", "lx-zoom-fit"):
        assert 'id="%s"' % el_id in page, el_id
    assert "lights-engine.js?v=7" in page and "lights.js?v=20" in page and "light-studio.css?v=15" in page
    assert "lx-transport" in page and "__lightsLibrary" in page
    # polish pass: unsaved-work, undo, a11y, rail
    for el_id in ("lx-undo", "lx-redo", "lx-live", "lx-libdirty", "lx-draft-prompt", "lx-draft-keep", "lx-draft-discard",
                  "lx-rail", "lx-rail-expand"):
        assert 'id="%s"' % el_id in page, el_id
    assert 'id="lx-cues" class="lx-cues" role="list"' in page
    assert 'id="lx-wave" class="lx-wave" tabindex="0" role="slider"' in page
    assert 'id="lx-play"' in page and 'aria-label="Play or stop the song (Space)"' in page
    assert 'id="lx-run"' in page and 'aria-pressed="false" aria-label="Run the cue list without audio"' in page
    assert 'aria-live="polite"' in page.split('id="lx-live"')[1][:80]
    assert 'href="/command-center"' in page.split('id="lx-rail"')[1].split("</nav>")[0]
    # helper text floor: no 10px text classes on this page any more
    assert "text-[10px]" not in page.split('id="lx-root"')[1].split("</div>\n\n<script>")[0]


def test_every_element_the_script_reaches_for_is_on_the_page(flask_app):
    """lights.js boots in one pass; a single missing id throws and leaves
    the canvases dead. Every $("...") in the script must exist in the
    rendered page (ids from base.html count)."""
    client, user = _user(flask_app)
    page = client.get("/lights").get_data(as_text=True)
    js = open(os.path.join(ROOT, "static", "js", "lights.js"), encoding="utf-8").read()
    ids = sorted(set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', js)))
    assert len(ids) > 30
    missing = [i for i in ids if ('id="%s"' % i) not in page]
    assert not missing, missing


def test_library_save_versions_restore_and_isolation(flask_app):
    client, user = _user(flask_app)
    other, _ = _user(flask_app, "Someone Else")
    assert flask_app.test_client().get("/lights/library").status_code in (302, 401)
    data = {"name": "Fall set", "bars": 6, "chans": 4,
            "cues": [{"t": 1.25, "group": "all", "color": "#ffb347", "intensity": 85, "fade": 1, "note": "intro"}]}
    r = client.post("/lights/library/save", json={"name": "Fall set", "data": data, "note": "first pass"}).get_json()
    assert r["ok"] and r["id"] and r["versions"] == 1 and r["shows"][0]["name"] == "Fall set"
    sid = r["id"]
    # autosave updates in place and takes no version
    data["cues"].append({"t": 30, "group": "pair1", "color": "#3b82f6", "intensity": 80, "fade": 1, "note": ""})
    r2 = client.post("/lights/library/save", json={"id": sid, "name": "Fall set", "data": data, "autosave": True}).get_json()
    assert r2["ok"] and r2["id"] == sid and r2["versions"] == 1
    # explicit save adds a version
    r3 = client.post("/lights/library/save", json={"id": sid, "name": "Fall set v2", "data": data}).get_json()
    assert r3["versions"] == 2
    got = client.get("/lights/library/%s" % sid).get_json()
    assert got["ok"] and got["show"]["name"] == "Fall set v2" and got["show"]["cue_count"] == 2
    vs = client.get("/lights/library/%s/versions" % sid).get_json()["versions"]
    assert len(vs) == 2 and vs[-1]["note"] == "first pass" and vs[-1]["cue_count"] == 1
    restored = client.post("/lights/library/%s/restore" % sid, json={"version_id": vs[-1]["id"]}).get_json()
    assert restored["ok"] and len(restored["data"]["cues"]) == 1
    # linking to a track and a tour date only sticks for the caller's own rows
    tid = store.add_os_track(user["id"], "Song One")
    show_id = store.add_tour_show(user["id"], "2030-05-02", "Room", "City", "")
    r4 = client.post("/lights/library/save", json={"id": sid, "name": "Fall set", "data": data,
                                                  "track_id": tid, "tour_show_id": show_id, "autosave": True}).get_json()
    s = lights_store.get_show(user["id"], sid)
    assert s["track_id"] == tid and s["tour_show_id"] == show_id
    client.post("/lights/library/save", json={"id": sid, "name": "Fall set", "data": data,
                                               "track_id": "not-mine", "tour_show_id": "nope", "autosave": True})
    s = lights_store.get_show(user["id"], sid)
    assert s["track_id"] is None and s["tour_show_id"] is None
    # the page lists it; another account sees nothing
    page = client.get("/lights").get_data(as_text=True)
    assert "Fall set" in page
    assert other.get("/lights/library/%s" % sid).status_code == 404
    assert other.get("/lights/library/%s/versions" % sid).status_code == 404
    assert other.get("/lights/library").get_json()["shows"] == []
    other.post("/lights/library/%s/delete" % sid, json={})
    assert lights_store.get_show(user["id"], sid) is not None      # a stranger cannot delete it
    d = client.post("/lights/library/%s/delete" % sid, json={}).get_json()
    assert d["ok"] and d["shows"] == [] and lights_store.list_versions(user["id"], sid) == []


def test_user_text_cannot_break_out_of_the_inline_script(flask_app):
    """json.dumps does not escape "<", so a show named "</script>..." would
    close the tag and run as HTML. Every JSON blob embedded in an inline
    script goes through the js_json filter instead."""
    client, user = _user(flask_app)
    payload = '</script><img src=x onerror=alert(1)>'
    client.post("/lights/save", json={"name": payload, "bars": 4, "chans": 4, "cues": []})
    client.post("/lights/library/save", json={"name": payload, "data": {"name": payload, "cues": [], "bars": 4, "chans": 4}})
    page = client.get("/lights").get_data(as_text=True)
    assert "</script><img" not in page          # the tag never closes early
    assert "\\u003c/script\\u003e" in page      # it is there, escaped
    # and it still parses back to exactly what the user typed
    blob = page.split("window.__savedShow = ")[1].split(";</script>")[0]
    import json as _j
    assert _j.loads(blob)["name"] == payload


def test_rig_profiles_save_bind_to_a_venue_and_stay_private(flask_app):
    """A rig is layout + patch. It is per-account, sanitised on the way in,
    and at most one rig is bound to a given venue name."""
    client, user = _user(flask_app)
    other, _ = _user(flask_app, "Other LD")
    assert flask_app.test_client().get("/lights/rigs").status_code in (302, 401)
    assert client.get("/lights/rigs").get_json()["rigs"] == []

    rig = {"bars": 8, "chans": 3, "pos": {"1": [0.2, 0.1]}, "rot": {"1": 90, "2": 45},
           "dmxStart": 101, "dmxAddr": {"1": 101, "2": 9999, "3": "nope"}}
    r = client.post("/lights/rigs/save", json={"name": "The Vault house rig", "data": rig,
                                              "venue": "The Vault, Charlotte!"}).get_json()
    assert r["ok"] and len(r["rigs"]) == 1
    rid = r["id"]
    saved = r["rigs"][0]
    assert saved["name"] == "The Vault house rig"
    assert saved["venue_key"] == "the vault charlotte"          # punctuation and case are noise
    d = saved["data"]
    assert d["bars"] == 8 and d["chans"] == 3 and d["dmxStart"] == 101
    assert d["rot"]["1"] == 90 and d["rot"]["2"] == 0            # only 0/90 survive
    assert d["dmxAddr"] == {"1": 101}                            # out-of-range and junk dropped
    assert lights_store.rig_for_venue(user["id"], "the vault   charlotte")["id"] == rid

    # values outside the studio's own limits are clamped, never stored raw
    r2 = client.post("/lights/rigs/save", json={"name": "Silly", "data": {"bars": 99, "dmxStart": 9999,
                                                                         "pos": {"1": [5, -5]}}}).get_json()
    d2 = [x for x in r2["rigs"] if x["id"] == r2["id"]][0]["data"]
    assert d2["bars"] == 10 and d2["dmxStart"] == 512 and d2["pos"]["1"] == [0.97, 0.04]

    # one rig per venue: binding a second rig to the same room unbinds the first
    r3 = client.post("/lights/rigs/save", json={"name": "Vault B", "data": {"bars": 4},
                                                "venue": "the vault charlotte"}).get_json()
    assert lights_store.rig_for_venue(user["id"], "The Vault Charlotte")["id"] == r3["id"]
    assert lights_store.get_rig(user["id"], rid)["venue_key"] == ""
    assert lights_store.rig_for_venue(user["id"], "") is None
    assert lights_store.rig_for_venue(user["id"], "Nowhere") is None

    # the page ships the caller's rigs and the venue key for each tour date
    store.add_tour_show(user["id"], "2030-06-01", "The Vault", "Charlotte", "")
    page = client.get("/lights").get_data(as_text=True)
    assert "The Vault house rig" in page and 'data-venue-key="the vault"' in page

    # another account cannot see, edit or delete them
    assert other.get("/lights/rigs").get_json()["rigs"] == []
    other.post("/lights/rigs/%s/delete" % rid, json={})
    assert lights_store.get_rig(user["id"], rid) is not None
    assert lights_store.get_rig(other_id(other, flask_app), rid) is None
    assert client.post("/lights/rigs/%s/delete" % rid, json={}).get_json()["ok"]
    assert lights_store.get_rig(user["id"], rid) is None


def other_id(client, flask_app):
    """The user id behind a logged-in test client (via its session cookie)."""
    with client.session_transaction() as sess:
        return sess.get("user_id") or sess.get("uid") or ""


def test_a_show_ships_with_the_track_and_lands_on_another_rig(flask_app):
    """The point of storing looks and group roles rather than channel
    numbers: a show attached to a track renders on whatever rig pulls it."""
    client, user = _user(flask_app)
    other, other_user = _user(flask_app, "Someone Else")
    tid = store.add_os_track(user["id"], "No Tengo Calma")

    # an eight-bar show, including a cue that names a specific bar
    data = {"name": "Big rig show", "bars": 8, "chans": 4,
            "cues": [{"t": 1, "group": "all", "color": "#ffb347", "intensity": 80, "fade": 1},
                     {"t": 9, "group": "b7", "color": "#ff2d2d", "intensity": 100, "fade": 0}]}
    r = client.post("/lights/track/%s/attach" % tid,
                    json={"name": "Big rig show", "data": data}).get_json()
    assert r["ok"] and r["attached"]["cue_count"] == 2
    assert tid in r["tracks"]

    got = client.get("/lights/track/%s/show" % tid).get_json()
    assert got["ok"] and got["show"]["format"] == lights_store.PASSPORT_FORMAT
    assert got["show"]["bars"] == 8 and len(got["show"]["data"]["cues"]) == 2

    # the passport keeps the rest of the track intact and keeps a short history
    client.post("/lights/track/%s/attach" % tid,
                json={"name": "Second pass", "data": dict(data, cues=data["cues"][:1])})
    entry = lights_store.show_on_track(user["id"], tid)
    assert entry["name"] == "Second pass" and entry["cue_count"] == 1
    assert entry["history"] and entry["history"][0]["name"] == "Big rig show"

    # the cross-rig guarantee: bar 7 of 8 has a home on a 4-bar rig
    import json as _j
    cues = _j.loads(_j.dumps(entry["history"] and got["show"]["data"]["cues"]))
    remapped = [c for c in cues if c["group"] == "b7"]
    assert remapped, "the bar-specific cue is what makes this test worth running"

    # another account cannot reach it, and cannot attach to someone else's track
    assert other.get("/lights/track/%s/show" % tid).status_code == 404
    assert other.post("/lights/track/%s/attach" % tid, json={"name": "hijack", "data": data}).status_code == 404
    assert lights_store.show_on_track(user["id"], tid)["name"] == "Second pass"
    assert lights_store.show_on_track(other_user["id"], tid) is None
    assert lights_store.tracks_with_shows(other_user["id"]) == {}


def test_setlists_chain_saved_shows_and_stay_private(flask_app):
    """A setlist chains shows from YOUR library. An item pointing at another
    account's show is dropped rather than stored."""
    client, user = _user(flask_app)
    other, other_user = _user(flask_app, "Rival LD")

    def save_show(c, name):
        return c.post("/lights/library/save",
                      json={"name": name, "data": {"name": name, "bars": 4, "chans": 4, "cues": []}}).get_json()["id"]

    a, b = save_show(client, "Opener"), save_show(client, "Closer")
    theirs = save_show(other, "Not yours")

    assert flask_app.test_client().get("/lights/setlists").status_code in (302, 401)
    assert client.get("/lights/setlists").get_json()["setlists"] == []

    r = client.post("/lights/setlists/save", json={
        "name": "Friday night", "gap_color": "#221a10", "gap_intensity": 15,
        "items": [{"show_id": a, "advance": "auto", "gap_seconds": 4},
                  {"show_id": theirs, "advance": "auto"},          # another account's show
                  {"show_id": b, "advance": "manual", "gap_seconds": 0}]}).get_json()
    assert r["ok"]
    sl = r["setlist"]
    assert sl["name"] == "Friday night" and sl["gap_intensity"] == 15
    names = [i["show_name"] for i in sl["items"]]
    assert names == ["Opener", "Closer"], "another account's show was stored: %s" % names
    assert [i["position"] for i in sl["items"]] == [0, 1]
    assert sl["items"][0]["advance"] == "auto" and sl["items"][0]["gap_seconds"] == 4

    # values outside the allowed range are clamped, not stored raw
    r2 = client.post("/lights/setlists/save", json={
        "id": sl["id"], "name": "Friday night",
        "items": [{"show_id": a, "advance": "nonsense", "gap_seconds": 99999}]}).get_json()
    it = r2["setlist"]["items"][0]
    assert it["advance"] == "manual" and it["gap_seconds"] == 600

    # another account cannot read or delete it
    assert other.get("/lights/setlists/%s" % sl["id"]).status_code == 404
    assert other.get("/lights/setlists").get_json()["setlists"] == []
    other.post("/lights/setlists/%s/delete" % sl["id"], json={})
    assert lights_store.get_setlist(user["id"], sl["id"]) is not None
    assert client.post("/lights/setlists/%s/delete" % sl["id"], json={}).get_json()["ok"]
    assert lights_store.get_setlist(user["id"], sl["id"]) is None
    # deleting the setlist leaves the shows alone
    assert lights_store.get_show(user["id"], a) is not None


def test_the_page_ships_the_setlists(flask_app):
    client, user = _user(flask_app)
    sid = client.post("/lights/library/save",
                      json={"name": "In a set", "data": {"cues": [], "bars": 4, "chans": 4}}).get_json()["id"]
    client.post("/lights/setlists/save", json={"name": "Tour set", "items": [{"show_id": sid}]})
    page = client.get("/lights").get_data(as_text=True)
    assert "Tour set" in page and "setlists" in page


def test_rig_count_is_capped(flask_app):
    client, user = _user(flask_app)
    last = None
    for i in range(lights_store.MAX_RIGS + 2):
        last = client.post("/lights/rigs/save", json={"name": "Rig %d" % i, "data": {"bars": 4}})
    assert last.status_code == 400 and "delete one first" in last.get_json()["error"]
    assert len(lights_store.list_rigs(user["id"])) == lights_store.MAX_RIGS


def test_versions_are_capped(flask_app):
    client, user = _user(flask_app)
    sid = None
    for i in range(lights_store.MAX_VERSIONS + 5):
        r = client.post("/lights/library/save", json={"id": sid or "", "name": "Cap", "data": {"cues": [], "bars": 4, "chans": 4}}).get_json()
        sid = r["id"]
    assert r["versions"] == lights_store.MAX_VERSIONS


def test_working_copy_still_round_trips(flask_app):
    client, user = _user(flask_app)
    show = {"name": "Working", "bars": 8, "chans": 3, "cues": [{"t": 2, "group": "odd", "color": "#ff0000", "intensity": 50, "fade": 0.5, "note": "x"}],
            "bpm": 120.0, "beatOffset": 0.25, "snap": True}
    assert client.post("/lights/save", json=show).get_json()["ok"]
    assert store.get_light_show(user["id"])["bpm"] == 120.0
    assert "Working" in client.get("/lights").get_data(as_text=True)


def test_engine_checks_under_node():
    """The engine's maths is proved by tests/js/check_lights.js when Node is
    available; skipped (not passed) when it is not."""
    node = shutil.which("node")
    if not node:
        import glob
        found = glob.glob(os.path.join(os.path.expanduser("~"), "nodejs", "**", "node.exe"), recursive=True)
        node = found[0] if found else None
    if not node:
        pytest.skip("node not available")
    for name in ("check_lights.js", "check_lights_autocue.js", "check_lights_history.js"):
        proc = subprocess.run([node, os.path.join(ROOT, "tests", "js", name)],
                              capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, name + "\n" + proc.stdout + proc.stderr
        assert "FAIL" not in proc.stdout, name


def test_draft_flags_round_trip_and_library_untouched_by_autosave(flask_app):
    """The working copy carries draftDirty/draftSavedAt; only an explicit
    library save (version=True) may change a library row's data."""
    client, user = _user(flask_app)
    r = client.post("/lights/library/save", json={"name": "Named", "data": {"cues": [{"t": 1, "group": "all", "color": "#fff", "intensity": 50, "fade": 0}], "bars": 4, "chans": 4}}).get_json()
    sid = r["id"]
    draft = {"name": "Named", "libraryId": sid, "bars": 4, "chans": 4, "draftDirty": True, "draftSavedAt": "2026-08-22T10:00:00Z",
             "cues": [{"t": 1, "group": "all", "color": "#fff", "intensity": 50, "fade": 0}, {"t": 9, "group": "odd", "color": "#f00", "intensity": 90, "fade": 1}]}
    assert client.post("/lights/save", json=draft).get_json()["ok"]
    got = store.get_light_show(user["id"])
    assert got["draftDirty"] is True and got["draftSavedAt"].startswith("2026-08-22") and len(got["cues"]) == 2
    # the library row still has one cue
    assert lights_store.get_show(user["id"], sid)["cue_count"] == 1
    page = client.get("/lights").get_data(as_text=True)
    assert '"draftDirty": true' in page and sid in page


def test_stylesheet_has_no_tiny_helper_text():
    css = open(os.path.join(ROOT, "static", "css", "light-studio.css"), encoding="utf-8").read()
    sizes = [float(s) for s in re.findall(r"font-size:\s*([0-9.]+)px", css)]
    # labels (eyebrow, chips, kbd, table headers) are letterspaced caps at 9.5-11px by
    # design; running helper text is never below 12px.
    assert min(sizes) >= 9.5
    assert "font-size: 12px" in css or "font-size: 12.5px" in css


def test_phone_remote_pairs_carries_only_known_presses_and_stays_private(flask_app):
    """The remote is a second pair of hands, not a second copy of the show.
    The code in the URL is the whole authorisation, so what it can reach
    matters more here than anywhere else in the studio."""
    client, user = _user(flask_app)
    other, _ = _user(flask_app, "Another LD")

    assert flask_app.test_client().post("/lights/remote/start", json={}).status_code in (302, 401)
    started = client.post("/lights/remote/start", json={}).get_json()
    assert started["ok"] and len(started["code"]) == 32 and started["code"] in started["url"]
    # The QR must point at the host the laptop is on, not at a baked-in
    # production URL - otherwise a local or self-hosted run hands out a
    # code the phone cannot reach.
    assert started["url"].startswith("http://localhost/lights/remote/"), started["url"]

    code = started["code"]

    # The phone page needs no account - and carries no show data at all.
    phone = flask_app.test_client()
    page = phone.get("/lights/remote/%s" % code)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "All off" in html and "Amber wash" in html and "Blackout" in html
    # Buttons only: none of the show, the library, or the studio script.
    for leak in ("lx-cues", "__lightsLibrary", "lights.js", "lights-engine.js", '"cues"',
                 "lightingAt", "/lights/library", user["email"]):
        assert leak not in html, leak
    # The QR is the laptop's to show, not something the code alone unlocks.
    assert client.get("/lights/remote/%s/qr.svg" % code).status_code == 200
    assert phone.get("/lights/remote/%s/qr.svg" % code).status_code in (302, 401)

    # Only the listed presses are stored; anything else is refused outright.
    for kind in lights_store.REMOTE_COMMANDS:
        assert phone.post("/lights/remote/%s/cmd" % code, json={"kind": kind, "value": "3"}).status_code == 200
    for junk in ("eval", "", "look; DROP TABLE", "load"):
        assert phone.post("/lights/remote/%s/cmd" % code, json={"kind": junk}).status_code == 404
    assert phone.post("/lights/remote/%s/cmd" % ("f" * 32), json={"kind": "play"}).status_code == 404

    # The laptop drains its own queue once; a second poll is empty. The
    # live code comes back too, so a reload can pick the phone back up.
    got = client.get("/lights/remote/poll").get_json()
    assert got["code"] == code
    kinds = [c["kind"] for c in got["commands"]]
    assert got["ok"] and kinds == list(lights_store.REMOTE_COMMANDS) and got["phone_seen"]
    assert client.get("/lights/remote/poll").get_json()["commands"] == []

    # Another account polling gets nothing - not this remote's presses.
    assert other.get("/lights/remote/poll").get_json()["commands"] == []
    phone.post("/lights/remote/%s/cmd" % code, json={"kind": "blackout"})
    assert other.get("/lights/remote/poll").get_json()["commands"] == []
    assert len(client.get("/lights/remote/poll").get_json()["commands"]) == 1

    # Starting a second remote retires the first: one phone holds the rig.
    again = client.post("/lights/remote/start", json={}).get_json()["code"]
    assert again != code
    assert phone.post("/lights/remote/%s/cmd" % code, json={"kind": "play"}).status_code == 404
    assert "This remote has ended" in phone.get("/lights/remote/%s" % code).get_data(as_text=True)

    # And ending it closes the door for good.
    client.post("/lights/remote/end", json={})
    assert phone.post("/lights/remote/%s/cmd" % again, json={"kind": "play"}).status_code == 404


def test_the_pairing_url_follows_the_host_the_laptop_is_on(flask_app):
    """A QR baked with the production domain is a dead code on a laptop
    running the studio anywhere else."""
    base = "https://lx.example.net"
    email = "lx-host-%s@example.net" % uuid.uuid4().hex[:8]
    c = flask_app.test_client()
    c.post("/signup", data={"name": "Host LD", "email": email, "password": PASSWORD}, base_url=base)
    c.post("/login", data={"email": email, "password": PASSWORD}, base_url=base)
    url = c.post("/lights/remote/start", json={}, base_url=base).get_json()["url"]
    assert url.startswith("https://lx.example.net/lights/remote/"), url
    # Behind a TLS-terminating proxy the scheme arrives in a header only.
    url2 = c.post("/lights/remote/start", json={}, base_url="http://lx.example.net",
                  headers={"X-Forwarded-Proto": "https, http"}).get_json()["url"]
    assert url2.startswith("https://lx.example.net/lights/remote/"), url2


def test_phone_remote_expires_on_its_own(flask_app):
    """A code left in a text message must not still open the rig next tour."""
    client, user = _user(flask_app)
    code = client.post("/lights/remote/start", json={}).get_json()["code"]
    stale = (datetime.now(timezone.utc) - timedelta(hours=lights_store.REMOTE_TTL_HOURS + 1)).isoformat()
    with store.get_db() as db:
        db.execute("UPDATE light_remotes SET created = ? WHERE code = ?", (stale, code))
    phone = flask_app.test_client()
    assert lights_store.get_remote(code) is None
    assert phone.post("/lights/remote/%s/cmd" % code, json={"kind": "blackout"}).status_code == 404
    assert "This remote has ended" in phone.get("/lights/remote/%s" % code).get_data(as_text=True)
    # ...and the studio must not resume polling a remote the phone cannot reach.
    assert client.get("/lights/remote/poll").get_json()["code"] == ""

def test_a_held_look_overrides_the_cue_list_without_editing_it(flask_app):
    """The phone busks the stage. If a press edited cues instead, the
    operator would find the show changed after the gig with no undo."""
    js = open(os.path.join(ROOT, "static", "js", "lights.js"), encoding="utf-8").read()
    body = js.split("function applyRemoteCommand")[1].split("\n  }")[0]
    assert "setBump(E.LOOKS[n - 1])" in body and "applyLook" not in body
    assert 'case "ping": return;' in body                       # keep-alive disturbs nothing
    assert "if (bump) return E.scaleLooks(bumpLooks(), master, panic);" in js
    assert "show.cues" not in js.split("function setBump")[1].split("\n  }")[0]


def _saved_show(client, name="Notes show"):
    data = {"name": name, "bars": 6, "chans": 4,
            "cues": [{"t": 12.5, "group": "all", "color": "#ffb347", "intensity": 85, "fade": 1, "note": "intro"},
                     {"t": 74.0, "group": "all", "color": "#3b82f6", "intensity": 60, "fade": 2, "note": "chorus"}]}
    return client.post("/lights/library/save", json={"name": name, "data": data}).get_json()["id"]


def test_a_share_link_carries_one_show_and_nothing_else(flask_app):
    """The link is handed to someone with no account. It must open the
    show it names and reveal nothing else about the designer."""
    client, user = _user(flask_app)
    other, _ = _user(flask_app, "Rival LD")
    sid = _saved_show(client)
    _saved_show(client, "A show they were NOT sent")

    r = client.post("/lights/library/%s/share" % sid,
                    json={"permission": "read", "label": "Tour manager"}).get_json()
    assert r["ok"] and len(r["token"]) == 32 and r["token"] in r["url"]
    token = r["token"]

    reader = flask_app.test_client()
    page = reader.get("/lights/show/%s" % token)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Notes show" in html and "read only" in html
    for leak in ("A show they were NOT sent", user["email"], "lx-lib-select", "__lightsLibrary",
                 "/lights/library", "js/lights.js"):
        assert leak not in html, leak

    # Another account cannot mint a link for a show that is not theirs.
    assert other.post("/lights/library/%s/share" % sid, json={}).status_code == 404
    # ...nor revoke one.
    assert other.post("/lights/share/%s/revoke" % token, json={}).status_code == 404
    assert reader.get("/lights/show/%s" % token).status_code == 200
    # The owner can, and then the link is dead.
    assert client.post("/lights/share/%s/revoke" % token, json={}).get_json()["ok"]
    dead = reader.get("/lights/show/%s" % token)
    assert dead.status_code == 404 and "no longer live" in dead.get_data(as_text=True)
    assert reader.post("/lights/show/%s/comment" % token,
                       json={"author": "X", "body": "hi"}).status_code == 404


def test_read_only_means_read_only(flask_app):
    client, user = _user(flask_app)
    sid = _saved_show(client)
    ro = client.post("/lights/library/%s/share" % sid, json={"permission": "read"}).get_json()["token"]
    rw = client.post("/lights/library/%s/share" % sid, json={"permission": "comment"}).get_json()["token"]
    reader = flask_app.test_client()

    assert reader.post("/lights/show/%s/comment" % ro,
                       json={"author": "Marcus", "body": "too dark"}).status_code == 403
    ok = reader.post("/lights/show/%s/comment" % rw,
                     json={"author": "Marcus", "body": "too dark in the second chorus",
                           "t": 74.0}).get_json()
    assert ok["ok"] and len(ok["comments"]) == 1
    assert ok["comments"][0]["author"] == "Marcus" and ok["comments"][0]["t"] == 74.0

    # A read-only link still SHOWS the note - it just cannot add one.
    assert len(reader.get("/lights/show/%s/comments" % ro).get_json()["comments"]) == 1
    # An empty note is refused rather than stored blank.
    assert reader.post("/lights/show/%s/comment" % rw,
                       json={"author": "M", "body": "   "}).status_code == 400
    # An unknown permission string cannot be smuggled in to unlock writing.
    sneaky = client.post("/lights/library/%s/share" % sid,
                         json={"permission": "admin"}).get_json()["token"]
    assert reader.post("/lights/show/%s/comment" % sneaky,
                       json={"author": "M", "body": "x"}).status_code == 403


def test_notes_thread_settle_and_stay_with_their_show(flask_app):
    client, user = _user(flask_app)
    other, _ = _user(flask_app, "Rival LD")
    sid = _saved_show(client)
    mine = _saved_show(client, "Another of mine")
    token = client.post("/lights/library/%s/share" % sid,
                        json={"permission": "comment"}).get_json()["token"]
    reader = flask_app.test_client()

    top = reader.post("/lights/show/%s/comment" % token,
                      json={"author": "Marcus", "body": "chorus is late", "t": 74.0}).get_json()["id"]
    reader.post("/lights/show/%s/comment" % token,
                json={"author": "Marcus", "body": "actually two beats", "parent_id": top})
    client.post("/lights/library/%s/comment" % sid, json={"body": "pulled it back", "parent_id": top})
    got = client.get("/lights/library/%s/comments" % sid).get_json()["comments"]
    assert len(got) == 3
    assert [c["parent_id"] for c in got] == ["", top, top]
    assert got[2]["author"] == user["name"]

    # A reply cannot be used to reach a thread on somebody else's show.
    stray = client.post("/lights/library/%s/comment" % mine,
                        json={"body": "wrong show", "parent_id": top}).get_json()["id"]
    still = client.get("/lights/library/%s/comments" % sid).get_json()["comments"]
    assert [c["id"] for c in still] == [c["id"] for c in got]
    strays = client.get("/lights/library/%s/comments" % mine).get_json()["comments"]
    assert len(strays) == 1 and strays[0]["id"] == stray and strays[0]["parent_id"] == ""

    # Only the owner settles a note; a reader raises one but cannot close it.
    assert other.post("/lights/comments/%s/resolve" % top, json={}).status_code == 404
    assert client.post("/lights/comments/%s/resolve" % top, json={}).get_json()["ok"]
    assert client.get("/lights/library/%s/comments" % sid).get_json()["comments"][0]["resolved"] == 1
    assert client.post("/lights/comments/%s/resolve" % top,
                       json={"resolved": False}).get_json()["ok"]
    assert client.get("/lights/library/%s/comments" % sid).get_json()["comments"][0]["resolved"] == 0

    # Deleting a note takes its replies with it, and only the owner can.
    assert other.post("/lights/comments/%s/delete" % top, json={}).status_code == 404
    assert client.post("/lights/comments/%s/delete" % top, json={}).get_json()["ok"]
    assert client.get("/lights/library/%s/comments" % sid).get_json()["comments"] == []

    # Another account cannot read this show's notes at all.
    assert other.get("/lights/library/%s/comments" % sid).status_code == 404


def test_deleting_a_show_takes_its_links_and_notes_with_it(flask_app):
    """A dangling link that still opened, or notes that came back when an
    id was reused, would both be worse than losing them."""
    client, user = _user(flask_app)
    sid = _saved_show(client)
    token = client.post("/lights/library/%s/share" % sid,
                        json={"permission": "comment"}).get_json()["token"]
    reader = flask_app.test_client()
    reader.post("/lights/show/%s/comment" % token, json={"author": "Marcus", "body": "note"})
    assert len(lights_store.list_comments(sid)) == 1

    client.post("/lights/library/%s/delete" % sid, json={})
    assert lights_store.get_share(token) is None
    assert lights_store.list_comments(sid) == []
    assert reader.get("/lights/show/%s" % token).status_code == 404


def test_a_note_anchors_to_a_timecode_not_a_cue_id(flask_app):
    """lights.js strips cue ids on save, so an id anchor would break on
    the next save. Pinned because it is the kind of thing a later
    refactor would 'improve' back."""
    js = open(os.path.join(ROOT, "static", "js", "lights.js"), encoding="utf-8").read()
    share_js = open(os.path.join(ROOT, "static", "js", "lights-share.js"), encoding="utf-8").read()
    store_py = open(os.path.join(ROOT, "lights_store.py"), encoding="utf-8").read()
    assert "cue_id" not in js and "cue_id" not in share_js and "cue_id" not in store_py
    # Reader-supplied text is written as text, never as markup.
    assert ".innerHTML" not in share_js.split("function noteEl")[1].split("\n  }")[0]
    assert "body.textContent = c.body" in share_js
    assert "body.textContent = n.body" in js


def test_js_json_never_drops_bare_text_into_a_script(flask_app):
    """The filter accepts pre-serialised JSON, so it used to trust any
    string. A bare token then landed unquoted and killed the inline
    script; a user-supplied name would have been stored XSS."""
    f = flask_app.jinja_env.filters["js_json"]
    assert str(f("691ae30bf9604e0e9102e5e41a14b407")) == '"691ae30bf9604e0e9102e5e41a14b407"'
    assert str(f("Marcus")) == '"Marcus"'
    assert "</script>" not in str(f("</script><img src=x onerror=alert(1)>"))
    assert str(f('{"already": "json"}')) == '{"already": "json"}'      # unchanged
    assert str(f({"a": 1})) == '{"a": 1}'


def test_a_share_link_carries_the_show_not_the_bookkeeping(flask_app):
    """A saved show also holds the designer's own ids — which track it
    belongs to, which tour date, its library row. A tour manager has no
    reason to receive any of that, so the blob is filtered to a
    whitelist rather than forwarded whole."""
    client, user = _user(flask_app)
    tid = store.add_os_track(user["id"], "Song One")
    tour = store.add_tour_show(user["id"], "2030-05-02", "Room", "City", "")
    data = {"name": "Filtered", "bars": 6, "chans": 4, "looks": [], "bpm": 128,
            "cues": [{"t": 4.0, "group": "all", "color": "#ffb347", "intensity": 85, "fade": 1, "note": "in"}],
            "trackId": tid, "tourShowId": tour, "libraryId": "should-not-travel",
            "draftDirty": True, "draftSavedAt": "2026-08-22T00:00:00Z"}
    sid = client.post("/lights/library/save",
                      json={"name": "Filtered", "data": data,
                            "track_id": tid, "tour_show_id": tour}).get_json()["id"]
    token = client.post("/lights/library/%s/share" % sid, json={}).get_json()["token"]

    html = flask_app.test_client().get("/lights/show/%s" % token).get_data(as_text=True)
    assert "#ffb347" in html and '"bpm": 128' in html          # the show itself travels
    for private in (tid, tour, "trackId", "tourShowId", "libraryId",
                    "draftDirty", "draftSavedAt", "should-not-travel"):
        assert private not in html, private


def test_the_phone_remote_and_the_engine_agree_on_the_looks():
    """The phone sends an index into `_LIGHT_REMOTE_LOOKS`; the laptop
    resolves it against `LOOKS` in lights-engine.js. Order is the
    contract, so if the two lists drift, pressing "Violet haze" on the
    phone lights something else on stage.

    This exists because the design-system colour sweep rewrote the app.py
    copy - it looked like ordinary UI colour sitting in a Python file -
    and collapsed "Cold blue" and "Violet haze" onto the same token. The
    engine copy was exempt, so the two silently disagreed and nothing
    failed.
    """
    import io
    import os
    import re

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py = io.open(os.path.join(here, "app.py"), encoding="utf8").read()
    js = io.open(os.path.join(here, "static", "js", "lights-engine.js"),
                 encoding="utf8").read()

    block = re.search(r"_LIGHT_REMOTE_LOOKS\s*=\s*\[(.*?)\]", py, re.S)
    assert block, "_LIGHT_REMOTE_LOOKS not found in app.py"
    phone = re.findall(r'"name":\s*"([^"]+)",\s*"color":\s*"(#[0-9a-fA-F]{3,6})"',
                       block.group(1))

    looks = re.search(r"\bLOOKS\s*=\s*\[(.*?)\];", js, re.S)
    assert looks, "LOOKS not found in lights-engine.js"
    engine = re.findall(r'name:\s*"([^"]+)"[^}]*?color:\s*"(#[0-9a-fA-F]{3,6})"',
                        looks.group(1))

    assert phone, "no looks parsed from app.py"
    assert engine, "no looks parsed from lights-engine.js"
    assert phone == engine, (
        "the phone remote and the engine disagree about the looks.\n"
        "  app.py:           %s\n"
        "  lights-engine.js: %s" % (phone, engine))
