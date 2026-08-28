"""The "since your last visit" strip needs a last visit.

It previously had none - no column existed - and reported five
constants: "+$482.15 new royalties collected", two payouts, five tasks
completed, a catalog value increase. Identical on a first login and a
hundredth. These hold the replacement: a real window, real rows in it,
and honest words when there is nothing to report.
"""

import io
import uuid

from app import create_app


def _fresh_client(app_obj=None):
    app_obj = app_obj or create_app()
    client = app_obj.test_client()
    client.post("/signup", data={"name": "S",
                                 "email": "since%s@x.com" % uuid.uuid4().hex[:8],
                                 "password": "secret1", "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    return client


def _user_id(client):
    with client.session_transaction() as sess:
        return sess["user_id"]


def test_first_visit_says_so_instead_of_showing_zeros():
    client = _fresh_client()
    body = client.get("/overview").get_data(as_text=True)
    assert "first visit" in body
    # None of the constants the old strip quoted.
    assert "482.15" not in body
    assert "Tasks completed" not in body


def test_a_quiet_window_is_reported_as_quiet():
    app_obj = create_app()
    client = _fresh_client(app_obj)
    client.get("/overview")            # first visit: stamps it
    with client.session_transaction() as sess:
        sess.pop("seen_rolled", None)  # a later session
    body = client.get("/overview").get_data(as_text=True)
    assert "Nothing new since then" in body


def test_the_strip_counts_rows_created_in_the_window():
    app_obj = create_app()
    client = _fresh_client(app_obj)
    client.get("/overview")            # open the window
    with client.session_transaction() as sess:
        sess.pop("seen_rolled", None)
    csv_data = (b"Track Title,Store,Net Revenue,Sales Period\n"
                b"Midnight Drive,Spotify,120.50,2026-04\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv_data), "s.csv")},
                content_type="multipart/form-data")
    body = client.get("/overview").get_data(as_text=True)
    assert "120.50" in body and "new statement" in body
    assert "Nothing new since then" not in body


def test_the_window_does_not_close_behind_a_refresh():
    """Reading and writing one stamp would make the strip empty itself
    on reload. prev_seen moves once per session, so it does not."""
    app_obj = create_app()
    client = _fresh_client(app_obj)
    client.get("/overview")
    with client.session_transaction() as sess:
        sess.pop("seen_rolled", None)
    csv_data = (b"Track Title,Store,Net Revenue,Sales Period\n"
                b"Neon Dreams,Spotify,60.00,2026-05\n")
    client.post("/statements", data={"statement": (io.BytesIO(csv_data), "s.csv")},
                content_type="multipart/form-data")
    first = client.get("/overview").get_data(as_text=True)
    second = client.get("/overview").get_data(as_text=True)
    assert "60.00" in first and "60.00" in second


def test_engine_counts_only_this_account():
    app_obj = create_app()
    mine = _fresh_client(app_obj)
    theirs = _fresh_client(app_obj)
    import db as store
    import since_engine
    with app_obj.app_context():
        mine_id, theirs_id = _user_id(mine), _user_id(theirs)
        store.roll_seen(mine_id)
        store.roll_seen(mine_id)       # second roll gives a real window
        since = store.get_prev_seen(mine_id)
        store.notify(theirs_id, "fan", "Their event", "", "/fans")
        view = since_engine.build(mine_id, since)
    assert view["quiet"] is True
    assert view["items"] == []


def test_engine_reports_a_won_case_and_the_amount_recovered():
    app_obj = create_app()
    client = _fresh_client(app_obj)
    import db as store
    import since_engine
    with app_obj.app_context():
        uid = _user_id(client)
        store.roll_seen(uid)
        store.roll_seen(uid)
        since = store.get_prev_seen(uid)
        case_id = store.create_recovery_case(uid, {
            "title": "Unattributed revenue on Spotify", "category": "unmatched",
            "estimated_amount": 120.0})
        store.update_recovery_case(uid, case_id,
                                   {"status": "won", "payout_result": 96.5})
        view = since_engine.build(uid, since)
    labels = " ".join(i["label"] for i in view["items"])
    values = " ".join(i["value"] for i in view["items"])
    assert "recovered" in labels and "96.50" in values


def test_signing_in_again_opens_a_new_window():
    """The roll is once per session, so it has to reset at sign-in or a
    returning artist would never see a second window."""
    import uuid as _uuid
    app_obj = create_app()
    client = app_obj.test_client()
    email = "again%s@x.com" % _uuid.uuid4().hex[:8]
    client.post("/signup", data={"name": "A", "email": email,
                                 "password": "secret1", "account_type": "artist"})
    client.post("/plan/switch", data={"plan": "pro"})
    client.get("/overview")
    client.post("/logout")
    client.post("/login", data={"email": email, "password": "secret1"})
    body = client.get("/overview").get_data(as_text=True)
    assert "first visit" not in body
    assert "Since " in body
