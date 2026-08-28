"""Beats — the audio a producer drops in, and the private links that carry it.

The registry, licences and cleared list are covered elsewhere. This file
is about what the audit pass added: bulk upload with browser-side
analysis, the stored file, and a link that sends one beat to one artist.
"""
import io
import json
import os
import uuid

import pytest

import app as appmod
import blob_store
import db as store

PASSWORD = "beats-pass-123"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def flask_app():
    return appmod.create_app()


def _producer(flask_app, label="Producer"):
    email = "bt-%s@example.net" % uuid.uuid4().hex[:8]
    client = flask_app.test_client()
    client.post("/signup", data={"name": label, "email": email, "password": PASSWORD})
    client.post("/login", data={"email": email, "password": PASSWORD})
    return client, store.get_user_by_email(email)


def _wav(seconds=1, rate=8000):
    """A real RIFF header with silence behind it. The server does not
    decode audio, so the bytes only have to be a plausible file."""
    n = seconds * rate
    head = (b"RIFF" + (36 + n * 2).to_bytes(4, "little") + b"WAVEfmt " +
            (16).to_bytes(4, "little") + (1).to_bytes(2, "little") +
            (1).to_bytes(2, "little") + rate.to_bytes(4, "little") +
            (rate * 2).to_bytes(4, "little") + (2).to_bytes(2, "little") +
            (16).to_bytes(2, "little") + b"data" + (n * 2).to_bytes(4, "little"))
    return head + b"\x00\x00" * n


def _upload(client, beat_id, name="beat.wav", data=None, **fields):
    payload = {"file": (io.BytesIO(data if data is not None else _wav()), name, "audio/wav")}
    payload.update({k: str(v) for k, v in fields.items()})
    return client.post("/beats/%s/audio" % beat_id, data=payload,
                       content_type="multipart/form-data")


def test_the_page_carries_the_new_surfaces(flask_app):
    client, user = _producer(flask_app)
    page = client.get("/beats").get_data(as_text=True)
    for el_id in ("bt-root", "bt-live", "bt-state", "bt-drop", "bt-files", "bt-queue",
                  "bt-open-drawer", "bt-drawer", "bt-scrim", "bt-drawer-close",
                  "bt-tab-catalog", "bt-tab-licences", "bt-tab-api",
                  "bt-panel-catalog", "bt-panel-licences", "bt-panel-api"):
        assert 'id="%s"' % el_id in page, el_id
    assert "beats.css?v=2" in page and "beats.js?v=1" in page and "tempokey.js" in page
    # The ceiling the page prints must be the one the app enforces.
    assert "window.__btMaxMb = %d;" % (store.MAX_BEAT_BYTES // (1024 * 1024)) in page
    # The drop zone must be there when the account is EMPTY — that is when
    # dropping a folder of audio is worth the most.
    assert "bt-drop" in page and "Nothing registered yet" in page

    # The state line stays visible; only its explanation folds away. It is
    # the truest sentence on the page, not fine print.
    assert "Nothing here scans for you" in page
    head = page.split('id="bt-state"')[1].split("</details>")[0]
    assert "<summary>Nothing here scans for you</summary>" in head
    assert "does not listen to audio or crawl platforms" in head

    # The locked tab says it is not built rather than implying a paywall.
    api = page.split('id="bt-panel-api"')[1].split("</section>")[0]
    assert "Not built." in api and "none of it is scheduled" in api
    for fake in ("Upgrade", "Coming soon", "Enable", "Connect now"):
        assert fake not in api, fake


def test_every_element_the_script_reaches_for_is_on_the_page(flask_app):
    """beats.js boots in one pass; a missing id throws and the drop zone
    goes dead without logging anything."""
    import re
    client, user = _producer(flask_app)
    page = client.get("/beats").get_data(as_text=True)
    js = open(os.path.join(ROOT, "static", "js", "beats.js"), encoding="utf-8").read()
    ids = sorted(set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', js)))
    assert len(ids) > 5
    # Ids the script guards with `if ($("x"))` may legitimately be absent.
    missing = [i for i in ids if ('id="%s"' % i) not in page and ('$("%s")' % i) not in
               " ".join(l for l in js.split("\n") if "if ($(" in l)]
    assert not missing, missing


def test_upload_stores_the_file_and_keeps_the_producers_own_numbers(flask_app):
    client, user = _producer(flask_app)
    beat_id = client.post("/beats/register", json={"title": "Cold Corner"}).get_json()["id"]

    r = _upload(client, beat_id, "Cold Corner.wav", duration=14.0, sample_rate=22050,
                bpm=120.0, bpm_confidence=0.98, bpm_alternates="60/240",
                song_key="E minor", key_fit=0.48,
                peaks=json.dumps([0.1, 0.9, 0.4, 0.7])).get_json()
    assert r["ok"]
    a = r["audio"]
    assert a["bpm"] == 120.0 and a["song_key"] == "E minor" and a["peaks"] == [0.1, 0.9, 0.4, 0.7]
    assert a["bpm_alternates"] == "60/240"
    # The storage path is an R2 key or a disk location; it never travels.
    assert "path" not in a and "uploads" not in json.dumps(a) and "r2:" not in json.dumps(a)
    # A measurement fills an EMPTY registry field...
    assert r["filled"] == {"bpm": "120", "song_key": "E minor"}

    # ...but never overwrites a number the producer typed. A typed value is
    # a decision; a measured one is a guess.
    beat2 = client.post("/beats/register", json={"title": "Typed"}).get_json()["id"]
    store.update_beat(user["id"], beat2, {"bpm": "83", "song_key": "F# minor"})
    r2 = _upload(client, beat2, bpm=140.0, song_key="C major").get_json()
    assert r2["filled"] == {}
    kept = store.get_beat(beat2, user["id"])
    assert kept["bpm"] == "83" and kept["song_key"] == "F# minor"
    assert store.get_beat_audio(beat2)["bpm"] == 140.0     # the measurement is still recorded

    # Re-uploading replaces rather than stacks: a beat is one recording.
    _upload(client, beat_id, "Take two.wav", bpm=121.0)
    assert store.get_beat_audio(beat_id)["filename"] == "Take two.wav"
    with store.get_db() as db:
        n = db.execute("SELECT COUNT(*) AS n FROM beat_audio WHERE beat_id=?", (beat_id,)).fetchone()["n"]
    assert n == 1

    # The file streams back to its owner and to nobody else.
    got = client.get("/beats/%s/stream" % beat_id)
    assert got.status_code in (200, 206, 302)
    other, _ = _producer(flask_app, "Rival")
    assert other.get("/beats/%s/stream" % beat_id).status_code == 404
    assert other.post("/beats/%s/audio" % beat_id, data={}).status_code == 404


def test_the_size_ceiling_is_one_the_app_can_actually_enforce(flask_app):
    """MAX_CONTENT_LENGTH rejects an oversize request before routing, so a
    beat ceiling above it would be a number this code prints and never
    enforces — the producer gets a bare 413 instead of a sentence."""
    assert store.MAX_BEAT_BYTES < flask_app.config["MAX_CONTENT_LENGTH"], (
        "MAX_BEAT_BYTES must stay under MAX_CONTENT_LENGTH or the message lies")
    js = open(os.path.join(ROOT, "static", "js", "beats.js"), encoding="utf-8").read()
    assert "file.size > MAX_BYTES" in js, "oversize files must fail before they upload"


def test_upload_refuses_what_it_should(flask_app):
    client, user = _producer(flask_app)
    beat_id = client.post("/beats/register", json={"title": "Guarded"}).get_json()["id"]

    assert client.post("/beats/%s/audio" % beat_id, data={},
                       content_type="multipart/form-data").status_code == 400
    # Not audio.
    bad = client.post("/beats/%s/audio" % beat_id,
                      data={"file": (io.BytesIO(b"MZ\x90\x00"), "payload.exe",
                                     "application/x-msdownload")},
                      content_type="multipart/form-data")
    assert bad.status_code == 415
    # Over the ceiling.
    big = client.post("/beats/%s/audio" % beat_id,
                      data={"file": (io.BytesIO(b"\x00" * (store.MAX_BEAT_BYTES + 10)),
                                     "huge.wav", "audio/wav")},
                      content_type="multipart/form-data")
    assert big.status_code == 413
    # A registry row is required first.
    assert client.post("/beats/nope/audio", data={}).status_code == 404
    # Nonsense measurements are dropped rather than stored.
    ok = _upload(client, beat_id, bpm="NaN", duration="-4", key_fit="Infinity",
                 peaks="not json").get_json()
    assert ok["ok"] and ok["audio"]["bpm"] is None
    assert ok["audio"]["duration"] is None and ok["audio"]["peaks"] == []
    # An untitled bulk registration is refused rather than filed blank.
    assert client.post("/beats/register", json={"title": "   "}).status_code == 400
    # Signed out, the global login wall catches it before the route runs.
    assert flask_app.test_client().post("/beats/register", json={"title": "x"}).status_code in (302, 401)


def test_a_private_link_carries_one_beat_and_dies_when_told(flask_app):
    client, user = _producer(flask_app, "Ship Probe")
    other, _ = _producer(flask_app, "Rival")
    beat_id = client.post("/beats/register", json={"title": "Second Pass"}).get_json()["id"]
    client.post("/beats/register", json={"title": "A beat they were NOT sent"})
    _upload(client, beat_id, duration=14.0, bpm=120.0, song_key="E minor",
            peaks=json.dumps([0.2, 0.8, 0.5]))

    made = client.post("/beats/%s/share" % beat_id,
                       json={"label": "Rina (A&R)", "days": 30}).get_json()
    assert made["ok"] and len(made["token"]) == 32 and made["token"] in made["url"]
    token = made["token"]

    listener = flask_app.test_client()
    page = listener.get("/beat/%s" % token)
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "Second Pass" in html and "Sent by Ship Probe" in html and "120" in html
    for leak in ("A beat they were NOT sent", user["email"], "/beats/", "Clearance CSV",
                 "Issue licence", "uploads", "r2:"):
        assert leak not in html, leak

    # It plays, and the play is counted once — a page load is not interest.
    assert listener.get("/beat/%s/stream" % token).status_code in (200, 206, 302)
    assert store.list_beat_shares(user["id"], beat_id)[0]["plays"] == 1

    # Another account cannot mint a link for a beat that is not theirs...
    assert other.post("/beats/%s/share" % beat_id, json={}).status_code == 404
    # ...nor revoke one.
    assert other.post("/beat-link/%s/revoke" % token, json={}).status_code == 404
    assert listener.get("/beat/%s" % token).status_code == 200
    # The owner can, and then it is dead in both directions.
    assert client.post("/beat-link/%s/revoke" % token, json={}).get_json()["ok"]
    dead = listener.get("/beat/%s" % token)
    assert dead.status_code == 404 and "no longer live" in dead.get_data(as_text=True)
    assert listener.get("/beat/%s/stream" % token).status_code == 404


def test_a_lapsed_link_stops_working_on_its_own(flask_app):
    """A link mailed out in March must not still play the beat in August."""
    from datetime import datetime, timedelta, timezone
    client, user = _producer(flask_app)
    beat_id = client.post("/beats/register", json={"title": "Lapsing"}).get_json()["id"]
    _upload(client, beat_id)
    token = client.post("/beats/%s/share" % beat_id, json={"days": 7}).get_json()["token"]
    assert store.get_beat_share(token) is not None
    stale = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with store.get_db() as db:
        db.execute("UPDATE beat_shares SET expires=? WHERE token=?", (stale, token))
    assert store.get_beat_share(token) is None
    listener = flask_app.test_client()
    assert listener.get("/beat/%s" % token).status_code == 404
    assert listener.get("/beat/%s/stream" % token).status_code == 404
    # "never" really means never, not "today".
    forever = client.post("/beats/%s/share" % beat_id, json={"days": 0}).get_json()["token"]
    assert store.get_beat_share(forever)["expires"] == ""


def test_deleting_a_beat_takes_its_audio_and_links_with_it(flask_app):
    client, user = _producer(flask_app)
    beat_id = client.post("/beats/register", json={"title": "Doomed"}).get_json()["id"]
    _upload(client, beat_id)
    token = client.post("/beats/%s/share" % beat_id, json={}).get_json()["token"]
    assert store.get_beat_audio(beat_id) is not None

    client.post("/beats/%s/delete" % beat_id)
    assert store.get_beat_audio(beat_id) is None
    assert store.get_beat_share(token) is None
    assert flask_app.test_client().get("/beat/%s" % token).status_code == 404


def test_blob_store_handles_a_nested_key_on_disk(tmp_path):
    """A key is a path because that is how it wants to live in a bucket.
    The disk fallback used to open() it flat, so every nested key raised
    FileNotFoundError while R2 accepted the same key happily."""
    d = str(tmp_path)
    path = blob_store.save("beats/u1/track.wav", b"hello", "audio/wav", uploads_dir=d)
    assert path == "/uploads/beats/u1/track.wav"
    assert os.path.exists(os.path.join(d, "beats", "u1", "track.wav"))
    # remove() used to basename() it, delete nothing, and report success.
    assert blob_store.remove(path, uploads_dir=d) is True
    assert not os.path.exists(os.path.join(d, "beats", "u1", "track.wav"))
    # A stored path can never reach outside the uploads directory.
    with pytest.raises(ValueError):
        blob_store.safe_local_path("/uploads/../../etc/passwd", d)


def test_the_licence_presets_say_what_each_shape_gives_away(flask_app):
    """A producer signing a work for hire is giving up the back end. If
    the wording does not say so, the generator is worse than a blank box."""
    js = open(os.path.join(ROOT, "static", "js", "beat-detail.js"), encoding="utf-8").read()
    for shape in ("lease", "premium", "exclusive", "work_for_hire", "free"):
        assert shape + ":" in js, shape
    assert "gives up the back end" in js
    assert "Licences already granted before this date stay in force" in js
    assert "not legal advice" in open(
        os.path.join(ROOT, "templates", "beat_detail.html"), encoding="utf-8").read()
    # Nothing the producer typed reaches the share page through innerHTML.
    # (The play glyph does — it is a literal entity written in this repo.)
    share_js = open(os.path.join(ROOT, "static", "js", "beat-share.js"), encoding="utf-8").read()
    import re
    total = share_js.count(".innerHTML")
    # A bare double-quoted literal and nothing else: no variable, no
    # concatenation, so nothing a producer typed can ride in as markup.
    # (The literal is an HTML entity, so it contains a ";" of its own.)
    literal = len(re.findall(r'\.innerHTML\s*=\s*"[^"]*"\s*;', share_js))
    assert total and literal == total, "%d of %d innerHTML writes are not literals" % (
        total - literal, total)


def test_a_failed_upload_does_not_litter_the_catalogue(flask_app):
    """A bulk drop registers a row per file before the bytes go up. If the
    upload then fails, that row exists only as an empty beat — so the
    script deletes it, and the queue says what went wrong."""
    js = open(os.path.join(ROOT, "static", "js", "beats.js"), encoding="utf-8").read()
    body = js.split("function send(")[1].split("function upload(")[0]
    assert "/delete" in body and "throw err" in body, body
    # And the delete route it calls really does take the row away.
    client, user = _producer(flask_app)
    beat_id = client.post("/beats/register", json={"title": "Orphan"}).get_json()["id"]
    assert store.get_beat(beat_id, user["id"]) is not None
    client.post("/beats/%s/delete" % beat_id)
    assert store.get_beat(beat_id, user["id"]) is None


def test_a_dialog_never_opens_with_focus_left_outside_it(flask_app):
    """type=hidden is an input and cannot take focus. The licence modal's
    first input is its `action` field, so a naive
    querySelector("input, ...") opened the dialog and left the keyboard
    on the button behind it — found in the browser, not by a test."""
    for name in ("beat-detail.js", "beats.js"):
        js = open(os.path.join(ROOT, "static", "js", name), encoding="utf-8").read()
        if "querySelectorAll(\"input" not in js and "querySelector(\"input" not in js:
            continue
        assert 'el.type !== "hidden"' in js, name
        assert "offsetParent !== null" in js, name
    detail = open(os.path.join(ROOT, "static", "js", "beat-detail.js"), encoding="utf-8").read()
    assert 'modal.querySelector("input, select, textarea").focus()' not in detail
