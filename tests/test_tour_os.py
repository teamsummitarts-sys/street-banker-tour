"""TOUR — the module that runs the road.

Two layers. tour_engine is tested as plain functions (readiness is
arithmetic, the extractor proposes, the importers parse, money is
derived). tour_os is tested through the Flask client: a tour is created,
filled, shared, and read by a second account whose permissions are
narrow — and the tests check what that account CANNOT see, in every
surface: pages, exports, Ask Tour, search, share links, file downloads.
"""
import io
import os
import re
import uuid
from datetime import date, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import app as appmod
import command_center
import db as store
import tour_engine as eng
import tour_store as ts

PASSWORD = "tour-pass-123"


@pytest.fixture(scope="module")
def flask_app():
    return appmod.create_app()


def _user(flask_app, label="Tour Owner", plan=None):
    email = "tour-%s@example.net" % uuid.uuid4().hex[:8]
    client = flask_app.test_client()
    client.post("/signup", data={"name": label, "email": email, "password": PASSWORD})
    client.post("/login", data={"email": email, "password": PASSWORD})
    user = store.get_user_by_email(email)
    if plan:
        store.set_user_plan(user["id"], plan)
    return client, user


def _tour(client, **over):
    data = {"name": "Test Run", "artist_name": "Test Artist", "start_date": "2030-05-01",
            "end_date": "2030-05-10", "home_tz": "America/New_York", "currency": "USD"}
    data.update(over)
    r = client.post("/tours/new", data=data)
    assert r.status_code == 302
    return r.headers["Location"].rstrip("/").split("/")[-1]


def _show(client, tour_id, date_, venue, city="Nashville, TN"):
    r = client.post("/tours/%s/days/add" % tour_id,
                    data={"date": date_, "kind": "show", "venue": venue, "city": city, "tz": "America/Chicago"})
    assert r.status_code == 302
    return r.headers["Location"].split("/shows/")[1].split("?")[0]


# --- engine -----------------------------------------------------------------

def test_engine_time_and_mode():
    assert eng.fmt_time("17:05") == "5:05 PM"
    assert eng.fmt_time("00:30") == "12:30 AM"
    assert eng.fmt_time("garbage") == "garbage"
    assert eng.valid_tz("America/Chicago") and not eng.valid_tz("Mars/Olympus")
    tour = {"status": "planning", "start_date": "2030-05-01", "end_date": "2030-05-10", "home_tz": "UTC", "mode_override": ""}
    assert eng.tour_mode(tour, [], today="2030-04-01") == "planning"
    assert eng.tour_mode(tour, [], today="2030-05-03") == "live"
    assert eng.tour_mode(dict(tour, mode_override="planning"), [], today="2030-05-03") == "planning"
    shows = [{"date": "2030-05-02"}, {"date": "2030-05-04"}]
    assert eng.show_status_line(tour, shows, today="2030-05-04") == "ON TOUR — SHOW 2 OF 2"
    assert eng.show_status_line(tour, shows, today="2030-04-04") == "PLANNING — 2 DATES"


def test_engine_readiness_is_checklist_arithmetic():
    show = {"status": "hold", "deposit_required": "", "deposit_received": "", "venue_id": None, "promoter": "",
            "guest_cutoff": "", "guest_allocation": "", "ticket_url": "", "marketing": {}, "readiness_config": []}
    rows = []
    for cat, items in ts.ADVANCE_CATEGORIES.items():
        for key, label in items:
            rows.append({"item_key": key, "category": cat, "label": label, "status": "incomplete", "value": ""})
    r = eng.show_readiness(show, rows, [], [], [], {}, [], 0)
    assert r["pct"] == 0 and r["done"] == 0
    # deposit not required and no VIP => not applicable, excluded from the score
    assert {c["key"] for c in r["checks"] if c["state"] is None} == {"deposit", "vip"}
    show2 = dict(show, status="confirmed", promoter="Someone", guest_cutoff="4pm", guest_allocation="20",
                 ticket_url="https://x", deposit_required="500", deposit_received="500")
    for row in rows:
        row["status"] = "complete"
    lodging = [{"status": "confirmed", "property": "H"}]
    # airport is advanced (complete, not n/a) so a confirmed flight is expected
    travel = [{"mode": "ground", "status": "confirmed"}, {"mode": "air", "status": "confirmed"}]
    files = [{"category": "contract"}]
    content = [{"assignee": "Alex"}]
    r2 = eng.show_readiness(show2, rows, travel, lodging, files, {}, content, 1)
    assert r2["pct"] == 100, [c for c in r2["checks"] if c["state"] is not True]


def test_engine_extractor_proposes_and_attributes():
    text = ("Load in 3:00 PM\nSoundcheck at 5pm\nDoors 7:00 PM\nHotel: Hampton Inn Downtown, 123 Main St\n"
            "WiFi: venue-guest / pass123\nPromoter: Jane Buyer jane@example.com 615-555-0100\n"
            "Show date: 2030-05-02\nNothing useful here")
    out = eng.extract(text)
    by_key = {(p["kind"], p["key"]): p for p in out["proposals"]}
    assert by_key[("time", "load_in")]["value"] == "15:00"
    assert by_key[("time", "soundcheck")]["value"] == "17:00"
    assert by_key[("time", "doors")]["value"] == "19:00"
    assert by_key[("fact", "hotel")]["value"].startswith("Hampton Inn")
    assert by_key[("fact", "wifi")]["value"].startswith("venue-guest")
    assert by_key[("contact", "email")]["value"] == "jane@example.com"
    assert by_key[("date", "date")]["value"] == "2030-05-02"
    assert by_key[("time", "load_in")]["line"] == 1 and by_key[("time", "load_in")]["source"] == "Load in 3:00 PM"
    assert out["high"] >= 5
    assert eng.extract("")["count"] == 0


def test_engine_importers_and_dedupe():
    rows, problems = eng.parse_csv_rows("date,city,venue,type\n2030-05-02,Nashville,The Basement,show\n"
                                        "5/3/2030,Atlanta,Terminal West,\nbad,,,\n2030-05-04,Carrboro,,off day")
    assert [r["date"] for r in rows] == ["2030-05-02", "2030-05-03", "2030-05-04"]
    assert rows[2]["kind"] == "off" and rows[1]["kind"] == "show"
    assert len(problems) == 1 and "Line 4" in problems[0]
    ics = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20300505\nSUMMARY:Show\n"
           "LOCATION:Cat's Cradle\\, Carrboro\\, NC\nEND:VEVENT\nBEGIN:VEVENT\nDTSTART:20300506T100000Z\n"
           "SUMMARY:Travel day\nEND:VEVENT\nEND:VCALENDAR")
    rows, problems = eng.parse_ics(ics)
    assert rows[0]["venue"] == "Cat's Cradle" and rows[0]["city"] == "Carrboro, NC" and rows[0]["date"] == "2030-05-05"
    assert rows[1]["kind"] == "travel"
    rows, problems = eng.parse_pasted("2030-05-07 — Richmond, VA | The National\n2030-05-08 travel day\nno date here")
    assert rows[0]["city"] == "Richmond, VA" and rows[0]["venue"] == "The National"
    assert rows[1]["kind"] == "travel" and len(problems) == 1
    existing = [{"date": "2030-05-07", "venue": "The National", "city": "Richmond, VA"}]
    deduped = eng.dedupe_against([{"date": "2030-05-07", "venue": "the national", "kind": "show"},
                                  {"date": "2030-05-07", "venue": "Other Room", "kind": "show"},
                                  {"date": "2030-05-09", "venue": "X", "kind": "show"}], existing, [])
    assert [r["verdict"] for r in deduped] == ["duplicate", "conflict", "new"]


def test_engine_money_never_fabricates():
    blank = {"deal_type": "flat"}
    m = eng.show_money(blank, [])
    assert m["has_numbers"] is False and m["estimated_net"] == 0
    show = {"deal_type": "guarantee_vs_pct", "guarantee": "2500", "backend_pct": "80", "adjusted_gross": "5000",
            "merch_gross": "1000", "venue_merch_cut": "20", "vip_gross": "", "deposit_required": "1250",
            "deposit_received": "", "collected": "", "settlement_amount": ""}
    m = eng.show_money(show, [{"amount": "300"}])
    assert m["backend"] == 4000 and m["earned"] == 4000      # 80% of 5000 beats the 2500 guarantee
    assert m["merch_net"] == 800 and m["expenses"] == 300
    assert m["estimated_net"] == 4000 + 800 - 300
    assert m["deposit_outstanding"] is True
    fin = eng.tour_finance([dict(show, id="a", date="2030-05-01", city="A", venue="V", settlement_status="open"),
                            dict(blank, id="b", date="2030-05-02", city="B", venue="W")], {"a": [{"amount": "300"}]}, "USD")
    assert fin["shows_with_numbers"] == 1 and fin["projected_net"] == 4500
    assert fin["deposits_outstanding"] == 1


def test_engine_change_severity_and_ask():
    assert eng.classify_change("schedule", "start_time") == "important"
    assert eng.classify_change("lodging", "property") == "critical"
    assert eng.classify_change("travel", "status") == "critical"
    assert eng.classify_change("schedule", "notes") == "info"
    ctx = {"shows": [{"id": "s1", "date": "2030-05-02", "city": "Nashville, TN", "venue": "The Basement"}],
           "today": "2030-05-02", "today_utc": "2030-05-02",
           "schedule": [{"day_date": "2030-05-02", "category": "call", "title": "Lobby call", "start_time": "13:30",
                         "location": "Lobby", "precision": "exact", "confirmed": 1, "updated": "x", "show_id": "s1"}],
           "travel": [], "lodging": [], "readiness": {}, "attention": [], "changes": [], "guests": {},
           "money_allowed": False, "finance": None, "advance": {}, "people": []}
    a = eng.ask("What time is lobby call today?", ctx)
    assert a["found"] and "1:30 PM" in a["answer"] and a["sources"]
    b = eng.ask("Where are we staying in Nashville?", ctx)
    assert not b["found"] and "No hotel has been entered" in b["answer"]
    c = eng.ask("Which deposits are outstanding?", ctx)
    assert not c["found"] and "not in your permissions" in c["answer"]
    d = eng.ask("what is the next flight", ctx)
    assert "has not been entered" in d["answer"]


# --- routes: owner ----------------------------------------------------------

def test_tour_lifecycle_owner(flask_app):
    client, owner = _user(flask_app)
    assert client.get("/tours").status_code == 200
    tid = _tour(client)
    home = client.get("/tours/%s" % tid)
    assert home.status_code == 200 and b"PLANNING" in home.data
    sid = _show(client, tid, "2030-05-02", "The Basement East")
    # The show is a real tour_shows row: the old hub still reads it
    assert store.get_tour_show(owner["id"], sid)["venue"] == "The Basement East"
    assert client.get("/tour").status_code == 200
    # Every Show Command tab renders for the owner
    for tab, _label in __import__("tour_os").SHOW_TABS:
        r = client.get("/tours/%s/shows/%s?tab=%s" % (tid, sid, tab))
        assert r.status_code == 200, (tab, r.status_code)
    # Standard day stamps the seven items; readiness moves with the data
    client.post("/tours/%s/shows/%s/standard-day" % (tid, sid))
    assert len(ts.list_schedule(tid, show_id=sid)) == 7
    r = client.post("/tours/%s/shows/%s/advance-bulk" % (tid, sid), data={
        "status__catering": "complete", "value__catering": "Hot meal x8",
        "status__hospitality": "complete", "status__dressing_rooms": "complete"})
    assert r.status_code == 302
    adv = {a["item_key"]: a for a in ts.list_advance(tid, sid)}
    assert adv["catering"]["status"] == "complete" and adv["catering"]["value"] == "Hot meal x8"
    # Every tour-level page renders
    for path in ("", "/my-day", "/calendar", "/calendar?view=list", "/shows", "/schedule", "/travel", "/hotels",
                 "/venues", "/people", "/guests", "/money", "/merch", "/marketing", "/content", "/tasks",
                 "/files", "/changes", "/ask", "/map", "/import", "/exports", "/share", "/team", "/settings",
                 "/search?q=base", "/itinerary", "/calendar.ics", "/itinerary.csv", "/people.csv",
                 "/travel.csv", "/money.csv"):
        r = client.get("/tours/%s%s" % (tid, path))
        assert r.status_code == 200, (path, r.status_code)
    # Unknown tour is a 404, not a 500 or a redirect
    assert client.get("/tours/%s" % uuid.uuid4().hex).status_code == 404


def test_schedule_edits_log_changes_and_notify(flask_app):
    client, owner = _user(flask_app)
    tid = _tour(client)
    sid = _show(client, tid, "2030-05-02", "Room A")
    client.post("/tours/%s/schedule/add" % tid, data={"show_id": sid, "title": "Soundcheck", "category": "soundcheck",
                                                     "start_time": "17:00"})
    item = ts.list_schedule(tid, show_id=sid)[0]
    before = store.unread_notifications(owner["id"])
    client.post("/tours/%s/schedule/%s/edit" % (tid, item["id"]), data={"start_time": "18:00", "title": "Soundcheck"})
    changes = ts.list_changes(tid)
    move = [c for c in changes if c["field"] == "start_time"]
    assert move and move[0]["before"] == "17:00" and move[0]["after"] == "18:00" and move[0]["severity"] == "important"
    assert move[0]["actor_name"] == owner["name"]
    # The actor is not notified about their own edit
    assert store.unread_notifications(owner["id"]) == before
    page = client.get("/tours/%s/changes" % tid)
    assert b"17:00" in page.data and b"18:00" in page.data


def test_import_csv_previews_then_creates_and_skips_duplicates(flask_app):
    client, owner = _user(flask_app)
    tid = _tour(client)
    _show(client, tid, "2030-05-02", "The Basement East")
    csv_text = ("date,city,venue,type\n2030-05-02,Nashville,The Basement East,show\n"
                "2030-05-03,Atlanta,Terminal West,show\n2030-05-04,,Day off,off\n")
    r = client.post("/tours/%s/import" % tid, data={"source": "csv", "text": csv_text, "action": "preview"})
    assert r.status_code == 200
    assert b"already on tour" in r.data and b"new" in r.data
    assert len(ts.list_shows(tid)) == 1          # preview wrote nothing
    r = client.post("/tours/%s/import" % tid, data={"source": "csv", "text": csv_text, "action": "confirm",
                                                  "pick": ["0", "1", "2"]})
    assert r.status_code == 302
    shows = ts.list_shows(tid)
    assert [s["venue"] for s in shows] == ["The Basement East", "Terminal West"]
    assert len([d for d in ts.list_days(tid) if d["kind"] == "off"]) == 1
    hist = ts.list_imports(tid)
    # `updated`/`filled` count dates that were already on the tour and got
    # their missing deal fields filled in; a plain create run leaves both 0.
    assert hist and hist[0]["summary"]["created"] == {
        "shows": 1, "days": 1, "skipped": 1, "updated": 0, "filled": 0}
    # .ics upload goes through the same review
    ics = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20300506\nSUMMARY:Show\n"
           "LOCATION:The National\\, Richmond\\, VA\nEND:VEVENT\nEND:VCALENDAR").encode()
    r = client.post("/tours/%s/import" % tid, data={"action": "preview", "file": (io.BytesIO(ics), "tour.ics")},
                    content_type="multipart/form-data")
    assert r.status_code == 200 and b"The National" in r.data


def test_advance_inbox_proposes_then_applies_only_ticked(flask_app):
    client, owner = _user(flask_app)
    tid = _tour(client)
    sid = _show(client, tid, "2030-05-02", "Room B")
    text = "Load in 3:00 PM\nDoors 7pm\nHotel: Example Inn, 1 Main St\nWiFi: guest / 1234"
    r = client.post("/tours/%s/shows/%s/inbox" % (tid, sid), data={"action": "extract", "text": text})
    assert r.status_code == 200 and b"proposal" in r.data
    assert ts.list_schedule(tid, show_id=sid) == []        # nothing written yet
    # apply load-in and hotel, leave doors and wifi
    r = client.post("/tours/%s/shows/%s/inbox" % (tid, sid), data={
        "action": "apply", "text": text, "pick": ["0", "2"],
        "kind_0": "time", "key_0": "load_in", "value_0": "15:00", "source_0": "Load in 3:00 PM",
        "kind_1": "time", "key_1": "doors", "value_1": "19:00", "source_1": "Doors 7pm",
        "kind_2": "fact", "key_2": "hotel", "value_2": "Example Inn, 1 Main St", "source_2": "Hotel: Example Inn",
        "kind_3": "fact", "key_3": "wifi", "value_3": "guest / 1234", "source_3": "WiFi: guest / 1234"})
    assert r.status_code == 302
    sched = ts.list_schedule(tid, show_id=sid)
    assert [s["category"] for s in sched] == ["load_in"] and sched[0]["start_time"] == "15:00"
    adv = {a["item_key"]: a for a in ts.list_advance(tid, sid)}
    assert adv["hotel"]["value"] == "Example Inn, 1 Main St" and adv["hotel"]["status"] == "complete"
    assert adv["wifi"]["value"] == ""
    # Provenance: the change log says the extractor did it
    assert any(c["source"] == "extract" for c in ts.list_changes(tid))
    # PDFs are refused honestly (no extraction library), not silently emptied
    r = client.post("/tours/%s/shows/%s/inbox" % (tid, sid), data={"action": "extract", "file": (io.BytesIO(b"%PDF-1.4"), "advance.pdf")},
                    content_type="multipart/form-data")
    assert r.status_code == 200 and b"PDF text extraction is not installed" in r.data


def test_guest_list_allocation_and_share_checkin(flask_app):
    client, owner = _user(flask_app)
    tid = _tour(client)
    sid = _show(client, tid, "2030-05-02", "Room C")
    client.post("/tours/%s/shows/%s/ext" % (tid, sid), data={"guest_allocation": "2", "guest_cutoff": "4 PM"})
    client.post("/tours/%s/shows/%s/guests/add" % (tid, sid), data={"name": "A Guest", "count": "2", "status": "approved"})
    # Over allocation: approved request is held as pending, not silently approved
    client.post("/tours/%s/shows/%s/guests/add" % (tid, sid), data={"name": "B Guest", "count": "1", "status": "approved"})
    rows = {g["name"]: g for g in ts.list_guests(tid, sid)}
    assert rows["A Guest"]["status"] == "approved" and rows["B Guest"]["status"] == "pending"
    summary = ts.guest_summary(tid, sid, "2")
    assert summary["used"] == 2 and summary["remaining"] == 0 and summary["pending"] == 1
    # Venue export carries approved names only
    csv_out = client.get("/tours/%s/shows/%s/guests.csv" % (tid, sid)).get_data(as_text=True)
    assert "A Guest" in csv_out and "B Guest" not in csv_out
    # Door check-in via a share link, with no account
    client.post("/tours/%s/share/new" % tid, data={"scope": "guest_checkin", "show_id": sid})
    token = ts.list_share_links(tid)[0]["token"]
    anon = flask_app.test_client()
    page = anon.get("/tour-share/%s" % token)
    assert page.status_code == 200 and b"A Guest" in page.data and b"B Guest" not in page.data
    anon.post("/tour-share/%s" % token, data={"action": "checkin", "guest_id": rows["A Guest"]["id"]})
    assert ts.get_guest(tid, rows["A Guest"]["id"])["status"] == "checked_in"
    # A pending guest cannot be checked in through the door link
    anon.post("/tour-share/%s" % token, data={"action": "checkin", "guest_id": rows["B Guest"]["id"]})
    assert ts.get_guest(tid, rows["B Guest"]["id"])["status"] == "pending"


def test_share_links_are_scoped_password_and_revocable(flask_app):
    client, owner = _user(flask_app)
    tid = _tour(client)
    sid = _show(client, tid, "2030-05-02", "Room D")
    client.post("/tours/%s/shows/%s/money" % (tid, sid), data={"guarantee": "7777", "deal_type": "flat"})
    client.post("/tours/%s/hotels/add" % tid, data={"show_id": sid, "property": "Secret Suites", "checkin": "2030-05-02",
                                                   "confirmation": "CONF-9999", "visibility": "management"})
    client.post("/tours/%s/schedule/add" % tid, data={"show_id": sid, "title": "Doors", "category": "doors", "start_time": "19:00"})
    client.post("/tours/%s/schedule/add" % tid, data={"show_id": sid, "title": "Private mgmt meeting", "category": "meeting",
                                                     "start_time": "12:00", "visibility": "private"})
    client.post("/tours/%s/share/new" % tid, data={"scope": "day_sheet", "show_id": sid, "password": "letmein"})
    link = ts.list_share_links(tid)[0]
    anon = flask_app.test_client()
    r = anon.get("/tour-share/%s" % link["token"])
    assert r.status_code == 200 and b"password" in r.data.lower() and b"Doors" not in r.data
    r = anon.post("/tour-share/%s" % link["token"], data={"password": "wrong"})
    assert r.status_code == 401
    r = anon.post("/tour-share/%s" % link["token"], data={"password": "letmein"})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Doors" in body
    assert "7777" not in body                      # money never on a share link
    assert "Private mgmt meeting" not in body      # private rows never on a share link
    assert "Secret Suites" not in body             # management-only hotel never on a share link
    assert "CONF-9999" not in body
    # Revoked => gone
    client.post("/tours/%s/share/%s/revoke" % (tid, link["id"]))
    assert anon.get("/tour-share/%s" % link["token"]).status_code == 404
    # A link cannot be minted for the whole tour: unknown scope is refused
    client.post("/tours/%s/share/new" % tid, data={"scope": "everything", "show_id": sid})
    assert all(l["scope"] != "everything" for l in ts.list_share_links(tid))


# --- routes: members and permission enforcement ------------------------------

def _member_join(flask_app, owner_client, tid, role, scopes, plan=None, label="Crew Member"):
    member_client, member = _user(flask_app, label, plan=plan)
    data = {"email": member["email"], "name": label, "role": role, "scopes": scopes}
    owner_client.post("/tours/%s/team/invite" % tid, data=data)
    m = ts.get_member_by_email(tid, member["email"])
    assert m and m["status"] == "invited" and m["invite_token"]
    r = member_client.get("/tours/join/%s" % m["invite_token"])
    assert r.status_code == 302
    assert ts.get_membership(tid, member["id"])["status"] == "active"
    return member_client, member


def test_member_without_financials_cannot_see_money_anywhere(flask_app):
    owner_client, owner = _user(flask_app)
    tid = _tour(owner_client)
    sid = _show(owner_client, tid, "2030-05-02", "Room E")
    owner_client.post("/tours/%s/shows/%s/money" % (tid, sid), data={"guarantee": "8888.25", "deal_type": "flat",
                                                                  "deposit_required": "4444.25"})
    owner_client.post("/tours/%s/files/upload" % tid, data={"entity_type": "show", "entity_id": sid, "category": "settlement",
                                                          "visibility": "all", "file": (io.BytesIO(b"secret numbers"), "settle.txt")},
                      content_type="multipart/form-data")
    money_file = ts.list_files(tid, category="settlement")[0]
    crew, member = _member_join(flask_app, owner_client, tid, "crew", ["view", "schedule"], plan="fan")
    # A fan-tier invitee can open the tour and My Day (plan gate does not block members)
    assert crew.get("/tours/%s" % tid).status_code == 200
    assert crew.get("/tours/%s/my-day" % tid).status_code == 200
    # Money pages: 403, not a leak
    assert crew.get("/tours/%s/money" % tid).status_code == 403
    assert crew.get("/tours/%s/money.csv" % tid).status_code == 403
    assert crew.get("/tours/%s/shows/%s?tab=money" % (tid, sid)).status_code == 403
    assert crew.get("/tours/%s/shows/%s/settlement-summary" % (tid, sid)).status_code == 403
    # Pages they can open carry no money strings
    for path in ("/tours/%s" % tid, "/tours/%s/shows/%s" % (tid, sid), "/tours/%s/shows/%s/day-sheet" % (tid, sid),
                 "/tours/%s/shows/%s?tab=overview" % (tid, sid), "/tours/%s/search?q=room" % tid):
        body = crew.get(path).get_data(as_text=True)
        assert "8888.25" not in body and "4444.25" not in body, path
    # Ask Tour refuses money questions for them
    r = crew.post("/tours/%s/ask" % tid, data={"q": "Which deposits are outstanding?"})
    assert b"not in your permissions" in r.data and b"4444.25" not in r.data
    # Money-category file is invisible and undownloadable
    assert crew.get("/tours/%s/files/%s/download" % (tid, money_file["id"])).status_code == 404
    # Owner still sees everything
    assert owner_client.get("/tours/%s/money" % tid).status_code == 200
    assert b"8888.25" in owner_client.get("/tours/%s/shows/%s?tab=money" % (tid, sid)).data
    # Owner grants financials => the same pages open
    m = ts.get_member_by_email(tid, member["email"])
    owner_client.post("/tours/%s/team/%s" % (tid, m["id"]), data={"action": "scopes", "role": "accountant",
                                                                "scopes": ["view", "financials"]})
    assert crew.get("/tours/%s/money" % tid).status_code == 200
    assert b"8888.25" in crew.get("/tours/%s/shows/%s?tab=money" % (tid, sid)).data
    # Removed => 404 everywhere, as if the tour did not exist
    owner_client.post("/tours/%s/team/%s" % (tid, m["id"]), data={"action": "remove"})
    assert crew.get("/tours/%s" % tid).status_code == 404
    assert crew.get("/tours/%s/my-day" % tid).status_code == 404


def test_private_rows_phones_and_rooms_are_redacted_server_side(flask_app):
    owner_client, owner = _user(flask_app)
    tid = _tour(owner_client)
    sid = _show(owner_client, tid, "2030-05-02", "Room F")
    owner_client.post("/tours/%s/people/save" % tid, data={"name": "Artist Person", "category": "Artist",
                                                          "phone": "+1 555 0199", "emergency": "Mom 555-0198"})
    owner_client.post("/tours/%s/people/save" % tid, data={"name": "Public Driver", "category": "Drivers",
                                                          "phone": "+1 555 0177", "phone_public": "1"})
    artist = [p for p in ts.list_people(tid) if p["name"] == "Artist Person"][0]
    owner_client.post("/tours/%s/travel/add" % tid, data={"day_date": "2030-05-02", "mode": "air", "number": "EX 999",
                                                         "confirmation": "PNR-ARTIST", "visibility": "private",
                                                         "travelers": [artist["id"]]})
    owner_client.post("/tours/%s/travel/add" % tid, data={"day_date": "2030-05-02", "mode": "ground", "vehicle": "Sprinter",
                                                         "confirmation": "VAN-CONF", "travelers": ["all"]})
    owner_client.post("/tours/%s/hotels/add" % tid, data={"show_id": sid, "property": "Crew Hotel", "checkin": "2030-05-02",
                                                         "confirmation": "HOTEL-CONF"})
    lodging = ts.list_lodging(tid)[0]
    owner_client.post("/tours/%s/hotels/%s/rooms" % (tid, lodging["id"]), data={"person_id": artist["id"], "room_number": "1201"})
    crew, member = _member_join(flask_app, owner_client, tid, "crew", ["view", "schedule"])
    for path in ("/tours/%s/travel" % tid, "/tours/%s/shows/%s?tab=travel" % (tid, sid), "/tours/%s/my-day?date=2030-05-02" % tid,
                 "/tours/%s/search?q=EX" % tid, "/tours/%s/shows/%s/day-sheet" % (tid, sid)):
        body = crew.get(path).get_data(as_text=True)
        assert "EX 999" not in body and "PNR-ARTIST" not in body, path      # private leg, not theirs
        assert "VAN-CONF" not in body, path                                  # confirmation needs travel scope
    body = crew.get("/tours/%s/travel" % tid).get_data(as_text=True)
    assert "Sprinter" in body                                                # the shared leg is visible
    body = crew.get("/tours/%s/people" % tid).get_data(as_text=True)
    assert "555 0199" not in body and "555-0198" not in body                 # private phone + emergency hidden
    assert "555 0177" in body                                                # public phone shown
    body = crew.get("/tours/%s/hotels" % tid).get_data(as_text=True)
    assert "Crew Hotel" in body and "1201" not in body and "HOTEL-CONF" not in body
    # CSV exports that would expose them are closed to this scope
    assert crew.get("/tours/%s/travel.csv" % tid).status_code == 403
    assert crew.get("/tours/%s/people.csv" % tid).status_code == 403
    # A stranger (signed in, not a member) sees nothing at all
    stranger, _ = _user(flask_app, "Stranger")
    assert stranger.get("/tours/%s" % tid).status_code == 404
    assert stranger.get("/tours/%s/travel.csv" % tid).status_code == 404


def test_my_day_is_personal_and_next_is_real(flask_app):
    owner_client, owner = _user(flask_app)
    tid = _tour(owner_client, start_date=date.today().isoformat(), end_date=(date.today() + timedelta(days=5)).isoformat())
    today = date.today().isoformat()
    sid = _show(owner_client, tid, today, "Tonight Room")
    owner_client.post("/tours/%s/schedule/add" % tid, data={"show_id": sid, "title": "Doors", "category": "doors", "start_time": "23:58"})
    owner_client.post("/tours/%s/schedule/add" % tid, data={"show_id": sid, "title": "Crew only call", "category": "call",
                                                           "start_time": "09:00", "responsible": "Somebody Else"})
    r = owner_client.get("/tours/%s/my-day" % tid)
    assert r.status_code == 200 and b"Doors" in r.data
    home = owner_client.get("/tours/%s" % tid).get_data(as_text=True)
    assert "ON TOUR" in home
    crew, member = _member_join(flask_app, owner_client, tid, "crew", ["view"], label="Named Crew")
    body = crew.get("/tours/%s/my-day" % tid).get_data(as_text=True)
    assert "Doors" in body                       # for everyone
    assert "Crew only call" not in body          # responsible is somebody else by name


def test_files_are_private_and_download_is_gated(flask_app):
    owner_client, owner = _user(flask_app)
    tid = _tour(owner_client)
    r = owner_client.post("/tours/%s/files/upload" % tid, data={"entity_type": "tour", "category": "rider", "visibility": "all",
                                                              "file": (io.BytesIO(b"rider bytes"), "rider.txt")},
                          content_type="multipart/form-data")
    assert r.status_code == 302
    f = ts.list_files(tid)[0]
    assert f["path"].startswith("tour:") and "/uploads/" not in f["path"]
    r = owner_client.get("/tours/%s/files/%s/download" % (tid, f["id"]))
    assert r.status_code == 200 and r.data == b"rider bytes"
    stranger, _ = _user(flask_app, "Stranger")
    assert stranger.get("/tours/%s/files/%s/download" % (tid, f["id"])).status_code == 404
    anon = flask_app.test_client()
    assert anon.get("/tours/%s/files/%s/download" % (tid, f["id"])).status_code == 302   # login wall
    # Disallowed extension is refused
    owner_client.post("/tours/%s/files/upload" % tid, data={"entity_type": "tour", "category": "other",
                                                          "file": (io.BytesIO(b"x"), "evil.exe")}, content_type="multipart/form-data")
    assert len(ts.list_files(tid)) == 1


def test_tasks_ride_on_command_center_and_changes_ack(flask_app):
    owner_client, owner = _user(flask_app)
    tid = _tour(owner_client)
    sid = _show(owner_client, tid, "2030-05-02", "Room G")
    owner_client.post("/tours/%s/tasks/add" % tid, data={"show_id": sid, "title": "Advance the venue", "priority": "high"})
    actions = [a for a in command_center.list_actions(owner["id"]) if a["entity_type"] == "tour_show"]
    assert actions and actions[0]["entity_id"] == sid and actions[0]["title"] == "Advance the venue"
    assert b"Advance the venue" in owner_client.get("/tours/%s/tasks" % tid).data
    owner_client.post("/tours/%s/tasks/%s/status" % (tid, actions[0]["id"]), data={"status": "complete"})
    assert [a for a in command_center.list_actions(owner["id"]) if a["id"] == actions[0]["id"]][0]["status"] == "complete"
    # A critical change demands acknowledgement and tracks who gave it
    owner_client.post("/tours/%s/hotels/add" % tid, data={"show_id": sid, "property": "First Hotel", "checkin": "2030-05-02"})
    l = ts.list_lodging(tid)[0]
    crew, member = _member_join(flask_app, owner_client, tid, "crew", ["view"])
    owner_client.post("/tours/%s/hotels/%s/edit" % (tid, l["id"]), data={"property": "Moved Hotel"})
    crit = [c for c in ts.list_changes(tid) if c["severity"] == "critical" and c["field"] == "property"]
    assert crit and crit[0]["before"] == "First Hotel" and crit[0]["after"] == "Moved Hotel"
    assert store.unread_notifications(member["id"]) >= 1
    page = crew.get("/tours/%s" % tid)
    assert b"waiting for your acknowledgement" in page.data
    crew.post("/tours/%s/changes/%s/ack" % (tid, crit[0]["id"]))
    assert ts.ack_state(tid, [crit[0]["id"]], member["id"])[crit[0]["id"]] == "acknowledged"
    assert b"waiting for your acknowledgement" not in crew.get("/tours/%s" % tid).data
    roster = ts.ack_roster(tid, crit[0]["id"])
    assert any(a["viewer_id"] == member["id"] and a["state"] == "acknowledged" for a in roster)


def test_setlist_links_catalog_and_exports_respect_scope(flask_app):
    owner_client, owner = _user(flask_app)
    tid = _tour(owner_client)
    sid = _show(owner_client, tid, "2030-05-02", "Room H")
    store.add_os_track(owner["id"], "Known Song")
    owner_client.post("/tours/%s/shows/%s/setlist" % (tid, sid), data={"action": "new", "name": "Main"})
    sl = ts.list_setlists(tid, show_id=sid)[0]
    owner_client.post("/tours/%s/shows/%s/setlist" % (tid, sid), data={"action": "save", "setlist_id": sl["id"],
                                                                     "items": "Known Song (3:30)\nOther Song\nEncore: Last One"})
    got = ts.get_setlist(tid, sl["id"])
    assert [s["title"] for s in got["songs"]] == ["Known Song", "Other Song", "Last One"]
    assert got["songs"][0]["duration"] == "3:30" and got["songs"][2]["section"] == "encore"
    tracks = store.list_os_tracks(owner["id"])
    if tracks:
        assert got["songs"][0]["os_track_id"] == tracks[0]["id"]
    assert b"Known Song" in owner_client.get("/tours/%s/setlists/%s/print" % (tid, sl["id"])).data
    ics = owner_client.get("/tours/%s/calendar.ics" % tid).get_data(as_text=True)
    assert "BEGIN:VEVENT" in ics and "Room H" in ics
    assert b"Room H" in owner_client.get("/tours/%s/itinerary" % tid).data


def test_seed_is_demo_only_and_capabilities_are_honest(flask_app):
    client, owner = _user(flask_app)
    assert client.post("/tours/seed-demo").status_code == 404
    assert ts.list_tours(owner["id"]) == []
    import capability_status as cs
    assert cs.resolve("tour_os")["status"] == cs.LIVE
    assert cs.resolve("tour_map")["status"] == cs.INTEGRATION_READY
    import hubs
    hrefs = [h for _, _, _, items in hubs.HUBS for _, h, *_ in items]
    assert "/tours" in hrefs and "tours" in hubs.LIVE_KEYS


def test_fan_tier_cannot_own_but_join_is_open(flask_app):
    fan, user = _user(flask_app, "Fan", plan="fan")
    r = fan.post("/tours/new", data={"name": "Nope"})
    assert r.status_code == 402
    assert ts.list_tours(user["id"]) == []
    assert fan.get("/tours").status_code == 200


def test_live_audit_regressions(flask_app):
    """Each block pins a defect the live audit found after the first deploy.
    They are kept together because they share one seeded tour."""
    client, owner = _user(flask_app)
    tid = _tour(client)
    sid = _show(client, tid, "2030-05-02", "Audit Room")

    # 1. Team: 'Remove from tour' must not be shadowed by a hidden action.
    crew, member = _member_join(flask_app, client, tid, "crew", ["view"])
    html = client.get("/tours/%s/team" % tid).get_data(as_text=True)
    assert not re.search(r'<input[^>]*type="hidden"[^>]*name="action"', html)
    assert 'name="action" value="remove"' in html and 'name="action" value="scopes"' in html
    m = ts.get_member_by_email(tid, member["email"])
    client.post("/tours/%s/team/%s" % (tid, m["id"]), data={"action": "remove"})
    assert crew.get("/tours/%s" % tid).status_code == 404

    # 2. VIP: the check-in buttons must not carry the fulfilled inputs.
    client.post("/tours/%s/shows/%s/vip/add" % (tid, sid), data={"package": "M&G", "guest": "V Guest", "merch": "1"})
    html = client.get("/tours/%s/shows/%s?tab=vip" % (tid, sid)).get_data(as_text=True)
    forms = html.split("<form")
    checkin = [f for f in forms if 'value="checked_in"' in f]
    assert checkin and all("fulfilled" not in f for f in checkin)
    assert any('name="fulfilled_flag"' in f and 'value="checked_in"' not in f for f in forms)

    # 3. Money tab: the classic sheet is the GET show page, not the POST route.
    html = client.get("/tours/%s/shows/%s?tab=money" % (tid, sid)).get_data(as_text=True)
    assert ('href="/tour/%s"' % sid) in html and ('href="/tour/%s/settlement"' % sid) not in html

    # 4. A guests-only member may set allocation/cutoff via /ext and nothing else.
    gm, _g = _member_join(flask_app, client, tid, "viewer", ["view", "guests"], label="Guest Desk")
    r = gm.post("/tours/%s/shows/%s/ext" % (tid, sid),
                data={"guest_allocation": "12", "guest_cutoff": "5 PM", "promoter": "Sneaky", "status": "settled"})
    assert r.status_code == 302
    s = ts.get_show(tid, sid)
    assert s["guest_allocation"] == "12" and s["guest_cutoff"] == "5 PM"
    assert s["promoter"] == "" and s["status"] != "settled"

    # 5. The global request ceiling covers the module's upload limit.
    import tour_os
    assert flask_app.config["MAX_CONTENT_LENGTH"] >= tour_os.MAX_UPLOAD

    # 6. 'Unsettled' uses the tour-local date, not the server's.
    rows = [{"id": "a", "date": "2030-05-01", "settlement_status": "open", "deal_type": "flat", "guarantee": "100"}]
    assert len(eng.tour_finance(rows, {}, "USD", today="2030-05-02")["unsettled"]) == 1
    assert len(eng.tour_finance(rows, {}, "USD", today="2030-05-01")["unsettled"]) == 0

    # 7. The service worker caches tabbed and dated tour URLs too.
    sw = open(os.path.join(ROOT, "static", "js", "sw.js"), encoding="utf-8").read()
    assert "!url.search" not in sw and int(re.search(r'sb-v(\d+)', sw).group(1)) >= 117

    # 8. Travel list separates named travellers.
    for name in ("Alice Example", "Bob Example"):
        client.post("/tours/%s/people/save" % tid, data={"name": name, "category": "Crew"})
    ids = [p["id"] for p in ts.list_people(tid) if p["name"] in ("Alice Example", "Bob Example")]
    client.post("/tours/%s/travel/add" % tid, data={"day_date": "2030-05-02", "mode": "ground", "travelers": ids})
    html = client.get("/tours/%s/travel" % tid).get_data(as_text=True)
    assert "Alice Example, Bob Example" in html or "Bob Example, Alice Example" in html

    # 9. ticket_url is an href: only web schemes are stored.
    client.post("/tours/%s/shows/%s/marketing" % (tid, sid), data={"ticket_url": "javascript:alert(1)"})
    assert ts.get_show(tid, sid)["ticket_url"] == ""
    client.post("/tours/%s/shows/%s/marketing" % (tid, sid), data={"ticket_url": "https://tickets.example/x"})
    assert ts.get_show(tid, sid)["ticket_url"] == "https://tickets.example/x"

    # 10. Print CSS flattens app pages to ink on white.
    css = open(os.path.join(ROOT, "static", "css", "tour-os.css"), encoding="utf-8").read()
    assert "@media print" in css and ".to, .to *" in css

    # 11. The shared rooming list's CSV link works without an account.
    client.post("/tours/%s/hotels/add" % tid, data={"show_id": sid, "property": "Audit Hotel", "checkin": "2030-05-02"})
    lid = ts.list_lodging(tid)[0]["id"]
    client.post("/tours/%s/share/new" % tid, data={"scope": "rooming", "lodging_id": lid})
    tok = [l for l in ts.list_share_links(tid) if l["scope"] == "rooming"][0]["token"]
    r = flask_app.test_client().get("/tour-share/%s?format=csv" % tok)
    assert r.status_code == 200 and r.mimetype == "text/csv"

    # 12. An oversize upload gets the module's own page, not a bare 413.
    big = io.BytesIO(b"x" * (tour_os.MAX_UPLOAD + 1024 * 1024))
    r = client.post("/tours/%s/files/upload" % tid, data={"entity_type": "tour", "category": "other",
                                                        "file": (big, "huge.pdf")}, content_type="multipart/form-data")
    assert r.status_code == 413 and b"too large" in r.data


def test_tour_dir_falls_back_when_disk_path_unusable(monkeypatch, tmp_path):
    import tour_os
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    # A path UNDER a file cannot be created: the same OSError an unmounted disk raises.
    monkeypatch.setattr(tour_os.store, "db_path", lambda: str(blocker / "streetbanker.db"))
    d = tour_os._tour_dir()
    assert os.path.isdir(d) and d.endswith("tour_uploads")


def test_stale_invite_and_settings_delete(flask_app):
    client, owner = _user(flask_app)
    tid = _tour(client)
    assert client.get("/tours/join/%s" % uuid.uuid4().hex).status_code == 404
    # Delete needs the exact name
    client.post("/tours/%s/settings" % tid, data={"action": "delete", "confirm": "wrong"})
    assert ts.get_tour(tid) is not None
    sid = _show(client, tid, "2030-05-02", "Keep Me")
    client.post("/tours/%s/settings" % tid, data={"action": "delete", "confirm": "Test Run"})
    assert ts.get_tour(tid) is None
    # The show survives in the old hub, detached
    assert store.get_tour_show(owner["id"], sid)["venue"] == "Keep Me"
    assert store.get_tour_show(owner["id"], sid).get("tour_id") in (None, "")
