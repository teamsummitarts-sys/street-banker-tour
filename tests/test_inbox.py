"""The inbox belongs to somebody.

It shipped without an owner column and the page ran `SELECT * FROM
inbox`, so every signed-in account read every row: one artist's booking
enquiries, the pitch emails sent to their one-sheet, the addresses of
people who asked for demo access. These pin the fix - ownership on the
row, filtering in the query - and the crash that led to finding it.
"""

import json
import uuid

import db as store
from app import create_app


def _client(app_obj, name="I"):
    client = app_obj.test_client()
    client.post("/signup", data={"name": name,
                                 "email": "inbox%s@x.com" % uuid.uuid4().hex[:8],
                                 "password": "secret1", "account_type": "artist"})
    return client


def _user_id(client):
    with client.session_transaction() as sess:
        return sess["user_id"]


def test_one_account_cannot_read_anothers_inbox():
    app_obj = create_app()
    mine, theirs = _client(app_obj, "Mine"), _client(app_obj, "Theirs")
    with app_obj.app_context():
        store.add_inbox("onesheet_pitch",
                        {"name": "A&R Scout", "email": "scout@label.com",
                         "message": "Loved the record."},
                        user_id=_user_id(mine))
        store.add_inbox("booking_enquiry",
                        {"city": "Berlin", "date": "2026-09-01",
                         "message": "Private booking"},
                        user_id=_user_id(theirs))
    my_page = mine.get("/inbox").get_data(as_text=True)
    assert "scout@label.com" in my_page
    assert "Berlin" not in my_page and "Private booking" not in my_page
    their_page = theirs.get("/inbox").get_data(as_text=True)
    assert "Berlin" in their_page
    assert "scout@label.com" not in their_page


def test_platform_rows_are_not_shown_to_an_artist():
    app_obj = create_app()
    client = _client(app_obj)
    with app_obj.app_context():
        store.add_inbox("demo-access", {"email": "lead@prospect.io",
                                        "workspace": "label",
                                        "password_sent": True})
    body = client.get("/inbox").get_data(as_text=True)
    assert "lead@prospect.io" not in body
    assert "Nothing here yet" in body


def test_received_items_offer_a_reply_and_sent_items_do_not():
    app_obj = create_app()
    client = _client(app_obj)
    with app_obj.app_context():
        uid = _user_id(client)
        store.add_inbox("sync_request",
                        {"pack": "Night Drive", "email": "sup@studio.tv",
                         "message": "Trailer placement?"}, user_id=uid)
        store.add_inbox("playlist_submission",
                        {"song": "Neon Dreams", "message": "For consideration"},
                        user_id=uid)
    body = client.get("/inbox").get_data(as_text=True)
    assert "Received" in body and "Sent" in body
    assert "mailto:sup@studio.tv" in body
    assert "Neon Dreams" in body
    # Nothing to reply to on something this account sent.
    assert body.count("mailto:") == 1


def test_a_pitch_lands_in_the_pitched_artists_inbox():
    """End to end: a stranger pitches a shared one-sheet, and it arrives
    on that artist's page rather than on everyone's."""
    app_obj = create_app()
    artist = _client(app_obj, "Artist")
    artist.post("/plan/switch", data={"plan": "pro"})
    with app_obj.app_context():
        uid = _user_id(artist)
        token = uuid.uuid4().hex[:12]
        store.upsert_onesheet_share(uid, token)
    stranger = app_obj.test_client()
    stranger.post("/sheet/%s/pitch" % token,
                  data={"name": "Sync Agent", "email": "agent@music.tv",
                        "message": "Want this for a spot."})
    body = artist.get("/inbox").get_data(as_text=True)
    assert "Sync Agent" in body and "agent@music.tv" in body


def test_inbox_survives_a_double_encoded_payload():
    """Found by walking every GET route during the dead-code sweep: one
    row written already-encoded 500'd the page for everyone."""
    app_obj = create_app()
    client = _client(app_obj)
    with app_obj.app_context():
        uid = _user_id(client)
        store.add_inbox("sync_request",
                        json.dumps({"pack": "Old Row", "email": "lead@test.io"}),
                        user_id=uid)
        store.add_inbox("invoice", {"number": "INV-1", "client": "Real Dict",
                                    "hours": 3, "total": 300.0}, user_id=uid)
        assert all(isinstance(i["payload"], dict)
                   for i in store.get_inbox(uid))
    response = client.get("/inbox")
    assert response.status_code == 200
    assert "Real Dict" in response.get_data(as_text=True)
