"""The producers desk: paperwork that can be checked, not detection.

The category's whole temptation is claiming to find uses of a beat
across the internet. Nothing here does that - Content ID belongs to
YouTube and cross-platform matching needs a paid fingerprinting vendor -
so these tests hold the line in both directions: the module says so
plainly, and the parts that ARE real (a signed licence, a cleared list a
stranger can check, a usage case) actually work.
"""

import uuid

import acr_provider
import db as store
import producers
from app import create_app


def _account(app_obj, name="P"):
    client = app_obj.test_client()
    email = "beat%s@x.com" % uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": name, "email": email,
                                 "password": "secret1", "account_type": "artist"})
    return client, email


def _uid(client):
    with client.session_transaction() as sess:
        return sess["user_id"]


def _beat(client, title="Night Drive Type Beat"):
    client.post("/beats", data={"title": title, "bpm": "140",
                                "song_key": "F#m", "tags": "trap"})
    return store.list_beats(_uid(client))[0]


def test_the_desk_says_it_does_not_scan(monkeypatch):
    for key in ("ACRCLOUD_HOST", "ACRCLOUD_ACCESS_KEY", "ACRCLOUD_ACCESS_SECRET"):
        monkeypatch.delenv(key, raising=False)
    assert acr_provider.configured() is False
    app_obj = create_app()
    client, _ = _account(app_obj)
    body = client.get("/beats").get_data(as_text=True)
    assert "Nothing here scans for you" in body
    assert "Content ID" in body          # named, and disclaimed
    assert "when somebody logs it" in body


def test_a_licence_is_signed_once_by_the_other_side():
    app_obj = create_app()
    producer, _ = _account(app_obj, "Producer")
    with app_obj.app_context():
        beat = _beat(producer)
        producer.post("/beats/" + beat["id"], data={
            "action": "licence", "licensee_name": "Ava Kane",
            "licensee_email": "ava@artist.com", "licence_type": "exclusive",
            "territory": "Worldwide", "term": "perpetual", "fee": "1500",
            "producer_split": "50", "terms": "One commercial release."})
        licence = store.list_beat_licences(beat["id"])[0]
    stranger = app_obj.test_client()          # no account, and none needed
    page = stranger.get("/licence/" + licence["token"])
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Exclusive" in body and "1,500.00" in body
    stranger.post("/licence/" + licence["token"], data={"signed_by": "Ava Kane"})
    with app_obj.app_context():
        signed = store.get_beat_licence_by_token(licence["token"])
    assert signed["status"] == "signed" and signed["signed_by"] == "Ava Kane"
    # Single use: a second signature cannot overwrite the first.
    stranger.post("/licence/" + licence["token"], data={"signed_by": "Someone Else"})
    with app_obj.app_context():
        assert store.get_beat_licence_by_token(licence["token"])["signed_by"] == "Ava Kane"


def test_the_cleared_page_answers_three_ways():
    """Cleared, not listed, and no-list-yet. The third is the one that
    matters: a producer who has not written the list has not thereby
    made every use an infringement."""
    app_obj = create_app()
    producer, _ = _account(app_obj)
    with app_obj.app_context():
        beat = _beat(producer)
        assert producers.clearance_for(beat["id"], "anything")["state"] == "unknown"
        producer.post("/beats/" + beat["id"], data={
            "action": "clear", "kind": "channel",
            "value": "youtube.com/@avakane", "note": "exclusive"})
        assert producers.clearance_for(beat["id"], "youtube.com/@avakane")["state"] == "cleared"
        assert producers.clearance_for(beat["id"], "somebody-else")["state"] == "not_listed"
    anon = app_obj.test_client()
    cleared = anon.get("/cleared/%s?q=youtube.com/@avakane" % beat["id"]).get_data(as_text=True)
    assert "Listed as cleared" in cleared
    unlisted = anon.get("/cleared/%s?q=nobody" % beat["id"]).get_data(as_text=True)
    assert "Not on the list" in unlisted
    assert "may still be licensed" in unlisted    # never states infringement


def test_the_public_page_leaks_no_deal_terms():
    """A label checks whether a use is covered. It has no business
    reading the fee, the terms text or the licensee's address."""
    app_obj = create_app()
    producer, _ = _account(app_obj)
    with app_obj.app_context():
        beat = _beat(producer)
        producer.post("/beats/" + beat["id"], data={
            "action": "licence", "licensee_name": "Ava Kane",
            "licensee_email": "private@artist.com", "licence_type": "lease",
            "fee": "2750", "terms": "Confidential side agreement."})
        licence = store.list_beat_licences(beat["id"])[0]
        producer.post("/beats/" + beat["id"], data={
            "action": "clear", "kind": "release", "value": "Neon Nights",
            "licence_id": licence["id"]})
    body = app_obj.test_client().get("/cleared/" + beat["id"]).get_data(as_text=True)
    assert "Neon Nights" in body
    assert "private@artist.com" not in body
    assert "2,750" not in body and "2750" not in body
    assert "Confidential side agreement" not in body


def test_a_usage_case_is_worked_not_detected():
    app_obj = create_app()
    producer, _ = _account(app_obj)
    with app_obj.app_context():
        beat = _beat(producer)
        producer.post("/beats/" + beat["id"], data={
            "action": "use", "url": "https://youtube.com/watch?v=x",
            "platform": "YouTube", "notes": "Uncredited"})
        use = store.list_beat_uses(_uid(producer), beat["id"])[0]
        assert use["found_via"] == "manual"       # never claimed otherwise
        producer.post("/beats/" + beat["id"], data={
            "action": "use_status", "use_id": use["id"],
            "status": "resolved", "resolved_amount": "400"})
        worked = store.list_beat_uses(_uid(producer), beat["id"])[0]
    assert worked["status"] == "resolved" and worked["resolved_amount"] == 400
    body = producer.get("/beats").get_data(as_text=True)
    assert "$400.00" in body                       # counted as recovered


def test_beats_belong_to_the_account_that_registered_them():
    app_obj = create_app()
    mine, _ = _account(app_obj, "Mine")
    theirs, _ = _account(app_obj, "Theirs")
    with app_obj.app_context():
        beat = _beat(mine, "Mine Only")
    assert theirs.get("/beats/" + beat["id"]).status_code == 404
    assert "Mine Only" not in theirs.get("/beats").get_data(as_text=True)


def test_the_licensee_sees_their_side_of_the_licence():
    app_obj = create_app()
    producer, _ = _account(app_obj, "Producer")
    licensee, licensee_email = _account(app_obj, "Licensee")
    with app_obj.app_context():
        beat = _beat(producer, "Shared Beat")
        producer.post("/beats/" + beat["id"], data={
            "action": "licence", "licensee_email": licensee_email,
            "licence_type": "lease", "fee": "200"})
    body = licensee.get("/beats").get_data(as_text=True)
    assert "Licences granted to you" in body
    assert "Shared Beat" in body
