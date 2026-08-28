"""Press Desk — one artist's media list, announcements and pitches.

Three things these tests care about more than the rest:

  Nobody sees anybody else's list. A press list is the most portable
  asset an artist has, and the failure mode is silent: a route that
  forgets its WHERE user_id clause returns somebody else's contacts and
  looks perfectly normal doing it.

  A refusal to send is a feature. The shared test sender delivers only to
  the account owner's inbox, so a pitch sent through it reports success
  and reaches no journalist. These tests pin the refusal, because the
  tempting "fix" is to let it through.

  Nothing is invented. There is no seeded contact, no example outlet and
  no sample coverage. An empty desk renders empty.
"""
import os
import re
import uuid

import pytest

import app as appmod
import db as store
import press_desk
import press_store

PASSWORD = "press-secret-1"


@pytest.fixture(scope="module")
def flask_app():
    return appmod.create_app()


def _artist(flask_app, label="Press Artist"):
    """A signed-in artist client, plus their user row."""
    email = "press-%s@example.net" % uuid.uuid4().hex[:8]
    client = flask_app.test_client()
    client.post("/signup", data={"name": label, "email": email,
                                 "password": PASSWORD})
    client.post("/login", data={"email": email, "password": PASSWORD})
    return client, store.get_user_by_email(email)


def _contact(client, **fields):
    data = {"name": "Dee Okafor", "outlet": "Nightdrive Mag",
            "role": "Writer", "email": "dee-%s@example.com" % uuid.uuid4().hex[:6]}
    data.update(fields)
    client.post("/press-desk/contacts/new", data=data)
    return data


def _announcement(client, user, **fields):
    data = {"title": "New single", "kind": "Single",
            "headline": "Artist announces Nightdrive",
            "body": "First paragraph.\n\nSecond paragraph.",
            "listen_url": "https://example.com/listen"}
    data.update(fields)
    client.post("/press-desk/announcements/new", data=data)
    return press_store.list_releases(user["id"])[0]


def _pitch(client, user, release, contact_ids, mode="own_inbox"):
    client.post("/press-desk/pitch/new", data={
        "release_id": release["id"], "contact_ids": contact_ids,
        "subject": "{artist} — {title}",
        "body": "Hi {name}, for {outlet}: {link}", "mode": mode})
    return press_store.list_pitches(user["id"])[0]


# --- the walls --------------------------------------------------------------

def test_the_desk_is_private(flask_app):
    anon = flask_app.test_client()
    for path in ("/press-desk", "/press-desk/contacts",
                 "/press-desk/announcements", "/press-desk/coverage",
                 "/press-desk/pitch/new"):
        response = anon.get(path)
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"], path


def test_every_desk_page_opens_for_its_artist(flask_app):
    client, _ = _artist(flask_app)
    for path in ("/press-desk", "/press-desk/contacts",
                 "/press-desk/contacts/new", "/press-desk/contacts/import",
                 "/press-desk/announcements", "/press-desk/announcements/new",
                 "/press-desk/pitch/new", "/press-desk/coverage"):
        assert client.get(path).status_code == 200, path


def test_an_empty_desk_is_empty(flask_app):
    """No seeded contact, no example outlet, no sample coverage."""
    client, user = _artist(flask_app)
    assert press_store.list_contacts(user["id"]) == []
    assert press_store.list_releases(user["id"]) == []
    assert press_store.list_coverage(user["id"]) == []
    assert press_store.desk_stats(user["id"]) == {
        "contacts": 0, "releases": 0, "pitched": 0,
        "opened": 0, "replied": 0, "coverage": 0}
    body = client.get("/press-desk/contacts").get_data(as_text=True)
    assert "Nothing here yet" in body


def test_one_artist_never_sees_another_artists_desk(flask_app):
    """The failure this is here to catch returns real data and looks
    completely normal while doing it."""
    mine, me = _artist(flask_app, "Owner")
    _contact(mine, name="Private Contact", outlet="My Outlet")
    release = _announcement(mine, me)
    contact_id = press_store.list_contacts(me["id"])[0]["id"]
    pitch = _pitch(mine, me, release, [contact_id])
    mine.post("/press-desk/coverage", data={"outlet": "My Outlet"})

    theirs, them = _artist(flask_app, "Stranger")
    assert press_store.list_contacts(them["id"]) == []
    assert press_store.list_releases(them["id"]) == []
    assert press_store.list_coverage(them["id"]) == []

    # Not just filtered out of lists — unreachable by direct id.
    assert theirs.get("/press-desk/pitch/%s" % pitch["id"]).status_code == 404
    assert theirs.get("/press-desk/announcements/%s"
                      % release["id"]).status_code == 404
    assert theirs.get("/press-desk/contacts/%s/edit"
                      % contact_id).status_code == 404
    assert press_store.get_contact(them["id"], contact_id) is None
    assert press_store.get_release(them["id"], release["id"]) is None

    # And a forged write cannot reach across either.
    theirs.post("/press-desk/contacts/%s/delete" % contact_id)
    assert press_store.get_contact(me["id"], contact_id) is not None
    body = theirs.get("/press-desk/contacts").get_data(as_text=True)
    assert "Private Contact" not in body


# --- who can be pitched -----------------------------------------------------

def test_do_not_contact_and_bounced_are_enforced_in_the_store(flask_app):
    """Ticked in a forged form, they still do not go out. The check lives
    where the recipients are built, not in the template that hides them."""
    client, user = _artist(flask_app)
    _contact(client, name="Willing", outlet="Yes Mag")
    _contact(client, name="Refused", outlet="No Mag", status="do-not-contact")
    _contact(client, name="Bounced", outlet="Dead Mag", status="bounced")
    release = _announcement(client, user)
    every_id = [c["id"] for c in press_store.list_contacts(user["id"])]
    assert len(every_id) == 3

    pitch = _pitch(client, user, release, every_id)
    recipients = press_store.pitch_recipients(user["id"], pitch["id"])
    assert len(recipients) == 1
    assert recipients[0]["contact_name"] == "Willing"


def test_a_contact_with_no_email_is_skipped_and_named(flask_app):
    client, user = _artist(flask_app)
    _contact(client, name="No Address", outlet="Silent Mag", email="")
    release = _announcement(client, user)
    contact_id = press_store.list_contacts(user["id"])[0]["id"]
    pitch_id, prepared, skipped = press_store.create_pitch(
        user["id"], release["id"], [contact_id], "s", "b", "own_inbox",
        "Artist", "https://example.test")
    assert prepared == 0
    assert skipped and "no email address" in skipped[0][1]


def test_a_pitch_cannot_exceed_the_recipient_cap(flask_app):
    client, user = _artist(flask_app)
    release = _announcement(client, user)
    ids = []
    for index in range(press_store.MAX_RECIPIENTS + 3):
        press_store.add_contact(user["id"], {
            "name": "Writer %d" % index, "outlet": "Outlet %d" % index,
            "email": "w%d-%s@example.com" % (index, uuid.uuid4().hex[:4])})
    ids = [c["id"] for c in press_store.list_contacts(user["id"])]
    pitch_id, prepared, skipped = press_store.create_pitch(
        user["id"], release["id"], ids, "s", "b", "own_inbox",
        "Artist", "https://example.test")
    assert prepared == press_store.MAX_RECIPIENTS
    # The overflow is reported rather than silently dropped.
    assert any("past the" in why for _who, why in skipped)


# --- the message ------------------------------------------------------------

def test_each_recipient_gets_their_own_words_and_their_own_link(flask_app):
    client, user = _artist(flask_app, "Real Artist")
    _contact(client, name="Dee Okafor", outlet="Nightdrive Mag")
    _contact(client, name="June Halloway", outlet="Gravel Weekly")
    release = _announcement(client, user, headline="Nightdrive is out")
    ids = [c["id"] for c in press_store.list_contacts(user["id"])]
    pitch = _pitch(client, user, release, ids)

    recipients = press_store.pitch_recipients(user["id"], pitch["id"])
    assert len(recipients) == 2
    tokens = {r["token"] for r in recipients}
    assert len(tokens) == 2                      # never a shared link
    for r in recipients:
        assert r["token"] in r["body"]
        assert "{name}" not in r["body"]         # nothing left unfilled
        assert "{outlet}" not in r["body"]
        assert "{link}" not in r["body"]
        assert "Real Artist" in r["subject"]
        assert "Nightdrive is out" in r["subject"]
    by_outlet = {r["outlet"]: r["body"] for r in recipients}
    assert "Hi Dee, for Nightdrive Mag" in by_outlet["Nightdrive Mag"]
    assert "Hi June, for Gravel Weekly" in by_outlet["Gravel Weekly"]


def test_prose_in_braces_survives_personalisation():
    """Only the five known placeholders are substituted — the rest is
    somebody's writing, not a variable."""
    out = press_store.personalise(
        "Hi {name}, the album {not_a_field} is out {title}",
        {"name": "Dee", "title": "Friday"})
    assert out == "Hi Dee, the album {not_a_field} is out Friday"


# --- the page a journalist opens --------------------------------------------

def test_the_press_page_opens_without_an_account(flask_app):
    client, user = _artist(flask_app)
    _contact(client)
    release = _announcement(client, user, headline="Nightdrive is out",
                            body="The news.\n\nThe detail.")
    ids = [c["id"] for c in press_store.list_contacts(user["id"])]
    pitch = _pitch(client, user, release, ids)
    token = press_store.pitch_recipients(user["id"], pitch["id"])[0]["token"]

    anon = flask_app.test_client()
    response = anon.get("/press/%s" % token)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Nightdrive is out" in body
    assert "The detail." in body
    # Sent to one person, and an embargo must not leak into a search index.
    assert 'content="noindex, nofollow"' in body
    assert anon.get("/press/%s" % ("0" * 20)).status_code == 404


def test_an_open_is_attributed_and_announced_exactly_once(flask_app):
    client, user = _artist(flask_app)
    _contact(client, name="Dee Okafor", outlet="Nightdrive Mag")
    release = _announcement(client, user)
    ids = [c["id"] for c in press_store.list_contacts(user["id"])]
    pitch = _pitch(client, user, release, ids)
    token = press_store.pitch_recipients(user["id"], pitch["id"])[0]["token"]

    before = len(store.list_notifications(user["id"]))
    anon = flask_app.test_client()
    anon.get("/press/%s" % token)
    first = press_store.get_recipient_by_token(token)
    assert first["open_count"] == 1
    assert first["status"] == "opened"
    assert first["opened_at"]

    notes = store.list_notifications(user["id"])
    assert len(notes) == before + 1
    assert "Nightdrive Mag opened your pitch" in notes[0]["title"]

    # A journalist re-reading it is not four more notifications.
    anon.get("/press/%s" % token)
    anon.get("/press/%s" % token)
    again = press_store.get_recipient_by_token(token)
    assert again["open_count"] == 3
    assert len(store.list_notifications(user["id"])) == before + 1


def test_an_embargo_is_shown_rather_than_hidden(flask_app):
    client, user = _artist(flask_app)
    _contact(client)
    release = _announcement(client, user, embargo_until="2099-01-01")
    ids = [c["id"] for c in press_store.list_contacts(user["id"])]
    pitch = _pitch(client, user, release, ids)
    token = press_store.pitch_recipients(user["id"], pitch["id"])[0]["token"]

    body = flask_app.test_client().get("/press/%s" % token).get_data(as_text=True)
    assert "Embargoed until 2099-01-01" in body
    assert "Please hold this" in body
    assert press_store.embargo_active(release) is True
    assert press_store.embargo_active({"embargo_until": "2000-01-01"}) is False
    assert press_store.embargo_active({"embargo_until": ""}) is False


# --- sending ----------------------------------------------------------------

def test_sending_is_refused_when_no_provider_is_connected(flask_app, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    client, user = _artist(flask_app)
    _contact(client)
    release = _announcement(client, user)
    ids = [c["id"] for c in press_store.list_contacts(user["id"])]
    pitch = _pitch(client, user, release, ids, mode="platform")

    response = client.post("/press-desk/pitch/%s/send" % pitch["id"])
    assert response.status_code == 409
    assert "Nothing was sent" in response.get_data(as_text=True)
    for r in press_store.pitch_recipients(user["id"], pitch["id"]):
        assert r["status"] == "prepared"
        assert r["sent_at"] == ""


def test_sending_is_refused_on_the_shared_test_sender(flask_app, monkeypatch):
    """The trap this exists for: the shared sender delivers only to the
    account owner, so every send reports success and no journalist ever
    receives one. Refusing is the correct behaviour, not a limitation."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    assert press_desk.send_state()["platform"] is False
    assert "only delivers to the account owner" in press_desk.send_state()["detail"]

    client, user = _artist(flask_app)
    _contact(client)
    release = _announcement(client, user)
    ids = [c["id"] for c in press_store.list_contacts(user["id"])]
    pitch = _pitch(client, user, release, ids, mode="platform")

    sent = []
    monkeypatch.setattr(press_desk.emailer, "send",
                        lambda *a, **k: sent.append(a) or True)
    response = client.post("/press-desk/pitch/%s/send" % pitch["id"])
    assert response.status_code == 409
    assert sent == []               # nothing was even attempted


def test_sending_works_and_reports_each_recipient(flask_app, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("EMAIL_FROM", "Artist <press@artist.example>")
    assert press_desk.send_state()["platform"] is True

    client, user = _artist(flask_app)
    # Distinct domains, because the fake below decides success by address.
    _contact(client, name="Dee Okafor", outlet="Nightdrive Mag",
             email="dee@nightdrive.example")
    _contact(client, name="June Halloway", outlet="Gravel Weekly",
             email="june@gravel.example")
    release = _announcement(client, user)
    ids = [c["id"] for c in press_store.list_contacts(user["id"])]
    pitch = _pitch(client, user, release, ids, mode="platform")

    calls = []

    def fake_send(to, subject, html, attachments=None):
        calls.append({"to": to, "subject": subject, "html": html})
        return "gravel" not in to        # one succeeds, one fails

    monkeypatch.setattr(press_desk.emailer, "send", fake_send)
    response = client.post("/press-desk/pitch/%s/send" % pitch["id"])
    assert response.status_code == 302

    # One message per recipient — never one email with everybody on it.
    assert len(calls) == 2
    assert len({c["to"] for c in calls}) == 2
    for call in calls:
        assert "<p" in call["html"]          # readable, plain, no template
        assert "<img" not in call["html"]    # no tracking pixel

    outcomes = {r["outlet"]: r["status"]
                for r in press_store.pitch_recipients(user["id"], pitch["id"])}
    assert outcomes["Nightdrive Mag"] == "sent"
    assert outcomes["Gravel Weekly"] == "failed"      # not averaged away


def test_the_send_body_escapes_what_the_artist_typed(flask_app):
    html = press_desk._as_html("Hi <script>alert(1)</script>\n\nSecond")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert html.count("<p") == 2


# --- importing --------------------------------------------------------------

def test_csv_import_adds_what_it_can_and_names_what_it_skipped(flask_app):
    client, user = _artist(flask_app)
    added, skipped, problems = press_store.import_contacts_csv(user["id"], (
        "name,outlet,email,role\n"
        "Dee Okafor,Nightdrive Mag,dee@example.com,Writer\n"
        "June Halloway,Gravel Weekly,june@example.com,Editor\n"
        ",,nobody@example.com,Writer\n"
        "Bad Address,Some Mag,not-an-email,Writer\n"
        "Duplicate,Nightdrive Mag,dee@example.com,Writer\n"))
    assert added == 2
    assert skipped == 3
    assert len(problems) == 3
    # Every skip says which line and why — a silent partial import is how
    # half a press list quietly disappears.
    assert all(p.startswith("Line ") for p in problems)
    assert any("not an email" in p for p in problems)
    assert any("already on the list" in p for p in problems)
    names = {c["name"] for c in press_store.list_contacts(user["id"])}
    assert names == {"Dee Okafor", "June Halloway"}


def test_csv_import_refuses_nonsense_without_throwing(flask_app):
    _client, user = _artist(flask_app)
    added, skipped, problems = press_store.import_contacts_csv(user["id"], "")
    assert added == 0 and problems


# --- coverage ---------------------------------------------------------------

def test_coverage_is_logged_and_counted(flask_app):
    client, user = _artist(flask_app)
    release = _announcement(client, user)
    client.post("/press-desk/coverage", data={
        "outlet": "Nightdrive Mag", "kind": "Review",
        "headline": "A gleaming record", "release_id": release["id"],
        "url": "https://example.com/review",
        "quote": "Sounds bigger than its budget."})
    logged = press_store.list_coverage(user["id"])
    assert len(logged) == 1
    assert logged[0]["outlet"] == "Nightdrive Mag"
    assert logged[0]["release_title"] == "New single"
    assert press_store.desk_stats(user["id"])["coverage"] == 1

    body = client.get("/press-desk/coverage").get_data(as_text=True)
    assert "A gleaming record" in body
    client.post("/press-desk/coverage/%s/delete" % logged[0]["id"])
    assert press_store.list_coverage(user["id"]) == []


# --- honesty ----------------------------------------------------------------

def test_the_capability_register_tells_the_truth_about_sending(monkeypatch):
    import capability_status as caps

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    assert caps.resolve("press_sending")["status"] == caps.INTEGRATION_READY

    # A key alone is not enough: that is the shared-sender case.
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    assert caps.resolve("press_sending")["status"] == caps.INTEGRATION_READY

    monkeypatch.setenv("EMAIL_FROM", "Artist <press@artist.example>")
    assert caps.resolve("press_sending")["status"] == caps.LIVE
    # The desk itself works with or without a provider.
    assert caps.resolve("press_desk")["status"] == caps.LIVE


def test_the_desk_says_so_when_it_cannot_send(flask_app, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    client, _user = _artist(flask_app)
    body = client.get("/press-desk").get_data(as_text=True)
    assert "Sending from Street Banker is off" in body
    assert "No email provider is connected" in body


def test_the_public_page_explains_the_desk_without_an_account(flask_app):
    anon = flask_app.test_client()
    response = anon.get("/press")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Press Desk" in body
    assert "How it runs" in body
    # The workspace itself is still behind the wall.
    assert anon.get("/press-desk").status_code == 302


def test_the_public_page_prints_what_the_desk_cannot_do(flask_app):
    """The two things a press tool is usually sold on are the two this
    one does not provide. A page that will not say so is a sales page."""
    body = flask_app.test_client().get("/press").get_data(as_text=True)
    assert "What it does not do" in body
    assert "It is not a media database" in body
    assert "No journalist contacts come with it" in body
    assert "It cannot promise coverage" in body
    assert "No wire distribution" in body
    # And the honest reason the open count is lower than a rival's.
    assert "No open pixel" in body


def test_the_public_page_reads_its_sending_claim_from_the_environment(
        flask_app, monkeypatch):
    """Written copy would go stale the moment a key changed; this asks."""
    client = flask_app.test_client()

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    body = client.get("/press").get_data(as_text=True)
    assert "Integration ready" in body
    assert "no sending domain is configured" in body
    assert "Live</p>" not in body

    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("EMAIL_FROM", "Artist <press@artist.example>")
    body = client.get("/press").get_data(as_text=True)
    assert "Sending from Street Banker — Live" in body


def test_the_footer_sends_a_stranger_to_the_public_page(flask_app):
    """The Platform column is for links that answer a signed-out visitor.
    It points at /press, not at the gated workspace."""
    from landing_config import get_landing_config

    platform = [c for c in get_landing_config()["footer"]["columns"]
                if c["title"] == "Platform"][0]
    hrefs = {l["label"]: l["href"] for l in platform["links"]}
    assert hrefs["Press Desk"] == "/press"

    client = flask_app.test_client()
    assert client.get("/press").status_code == 200
    body = client.get("/").get_data(as_text=True)
    assert 'href="/press"' in body
    assert 'href="/press-desk"' not in body      # no gated link in the footer


def test_press_desk_is_in_the_nav_and_the_palette():
    import hubs

    keys = {k for _hk, _n, _t, items in hubs.HUBS for k, *_ in items}
    assert "press-desk" in keys
    entry = [e for e in hubs.command_index() if e["key"] == "press-desk"][0]
    assert entry["href"] == "/press-desk"
    assert entry["live"] is True


def test_no_press_page_leaks_a_python_object(flask_app):
    client, user = _artist(flask_app)
    _contact(client)
    release = _announcement(client, user)
    ids = [c["id"] for c in press_store.list_contacts(user["id"])]
    pitch = _pitch(client, user, release, ids)
    token = press_store.pitch_recipients(user["id"], pitch["id"])[0]["token"]

    pages = ["/press-desk", "/press-desk/contacts", "/press-desk/announcements",
             "/press-desk/announcements/%s" % release["id"],
             "/press-desk/pitch/new", "/press-desk/pitch/%s" % pitch["id"],
             "/press-desk/coverage", "/press/%s" % token]
    for path in pages:
        body = client.get(path).get_data(as_text=True)
        for leak in ("<built-in method", "&lt;built-in method", "object at 0x",
                     "dict_keys(", "<bound method", "&lt;bound method"):
            assert leak not in body, (path, leak)
