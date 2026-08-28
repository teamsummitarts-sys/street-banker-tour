"""Team-Up Board foundation: UTF-8 repair, structured fields, in-platform
threads, lifecycle, filters, saved searches, verified chips, doorways."""
import uuid
from datetime import date, timedelta

import pytest

import app as appmod
import board_store as bs
import board_taxonomy as tx
import db as store

PASSWORD = "board-pass-123"


@pytest.fixture(scope="module")
def flask_app():
    return appmod.create_app()


def _user(flask_app, label="Board User"):
    email = "tb-%s@example.net" % uuid.uuid4().hex[:8]
    client = flask_app.test_client()
    client.post("/signup", data={"name": label, "email": email, "password": PASSWORD})
    client.post("/login", data={"email": email, "password": PASSWORD})
    return client, store.get_user_by_email(email)


# --- encoding ---------------------------------------------------------------

def test_repair_text_fixes_the_known_manglings():
    assert bs.repair_text("co-headliner %97 Southeast run") == "co-headliner — Southeast run"
    assert bs.repair_text("%93quoted%94 and it%92s") == "“quoted” and it’s"
    assert bs.repair_text("dash %E2%80%94 encoded") == "dash — encoded"
    assert bs.repair_text("mojibake â€” here, cafÃ©") == "mojibake — here, café"
    assert bs.repair_text("raw \x97 control") == "raw — control"
    # clean text is untouched, and the repair is idempotent
    for s in ("plain ascii", "already — right", "100% real numbers", "50%-60% door split", "Ünïcödé ok"):
        assert bs.repair_text(s) == s, s
    assert bs.repair_text(bs.repair_text("a %97 b")) == "a — b"


def test_repair_all_text_repairs_rows(flask_app):
    client, user = _user(flask_app)
    lid = store.add_board_listing(user["id"], "artist", "co-headliner %97 Southeast run", "SE", "Oct", "indie", "draw 150 %96 200")
    changes = bs.repair_all_text(apply=False)
    assert any(c[1] == lid and c[2] == "title" and c[4] == "co-headliner — Southeast run" for c in changes)
    assert bs.get_listing(lid)["title"] == "co-headliner %97 Southeast run"       # dry run wrote nothing
    bs.repair_all_text(apply=True)
    l = bs.get_listing(lid)
    assert l["title"] == "co-headliner — Southeast run" and l["details"] == "draw 150 – 200"
    page = client.get("/tour-board/%s" % lid).get_data(as_text=True)
    assert "co-headliner — Southeast run" in page and "%97" not in page


# --- taxonomy ---------------------------------------------------------------

def test_parsers():
    assert tx.parse_region("Southeast US") == ("us-southeast", "exact")
    assert tx.parse_region("Charlotte, NC")[0] == "metro-charlotte"
    assert tx.parse_region("Boone, NC") == ("us-southeast", "state")
    assert tx.parse_region("New York")[0] == "metro-nyc" and tx.parse_region("the PNW")[0] == "us-pnw"
    assert tx.parse_region("Mars colony") == (None, None)
    assert tx.parse_window("Sep–Oct 2026") == ("2026-09-01", "2026-10-31")
    assert tx.parse_window("Oct 12-15, 2026") == ("2026-10-12", "2026-10-15")
    assert tx.parse_window("October 2026") == ("2026-10-01", "2026-10-31")
    assert tx.parse_window("Fall 2026") == ("2026-09-01", "2026-11-30")
    assert tx.parse_window("2026-10-03 to 2026-10-05") == ("2026-10-03", "2026-10-05")
    assert tx.parse_window("whenever") == (None, None)
    codes, left = tx.parse_genres("Synthwave / indie, hip hop & something odd")
    assert codes == ["synthwave", "indie", "hiphop"] and left == ["something odd"]
    assert tx.parse_draw("We draw 150-200 in Charlotte") == (150, 200)
    assert tx.parse_draw("Cap 250, guarantee + door") == (None, None)
    assert tx.region_distance_km("metro-atlanta", "metro-charlotte") > 300
    assert tx.regions_related("metro-nashville", "us-southeast") and not tx.regions_related("metro-nashville", "us-pnw")


# --- posting, structure, migration -----------------------------------------------

def test_post_structured_listing_and_coaching(flask_app):
    client, user = _user(flask_app)
    r = client.post("/tour-board/post", data={"kind": "artist", "title": "Co-headline run — Southeast",
                                             "region_text": "Southeast US", "region_code": "us-southeast",
                                             "window_start": "2030-10-01", "window_end": "2030-10-20",
                                             "genres": ["indie", "synthwave"], "details": "We draw 150-200. Split the door."})
    assert r.status_code == 302 and "/tour-board/" in r.headers["Location"]
    lid = r.headers["Location"].rsplit("/", 1)[1]
    l = bs.get_listing(lid)
    assert l["region_code"] == "us-southeast" and l["window_start"] == "2030-10-01" and l["genres"] == ["indie", "synthwave"]
    assert l["draw_min"] == 150 and l["draw_max"] == 200 and l["status"] == "open" and l["expires_at"]
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "Co-headline run — Southeast" in page and "draw 150–200 · self-reported" in page
    # free-text fallbacks still work (no JS, unknown region), and coaching nudges appear
    r = client.post("/tour-board/post", data={"kind": "artist", "title": "Anywhere, anytime", "region_text": "Planet Zorg",
                                             "window": "Sep–Oct 2030", "genre": "indie / polka"})
    lid2 = r.headers["Location"].rsplit("/", 1)[1]
    l2 = bs.get_listing(lid2)
    assert l2["region_code"] == "" and l2["region_text"] == "Planet Zorg" and l2["window_start"] == "2030-09-01"
    assert "genre" in l2["parse_flag"] and "region" in l2["parse_flag"] and l2["genres"] == ["indie"]
    page = client.get("/tour-board/%s" % lid2).get_data(as_text=True)
    assert "Add a draw range" in page and "real numbers get real replies" in page
    # a bad post is reported as NOT posted, with the real reason; the old GET URL still lands on the form
    r = client.post("/tour-board/post", data={"kind": "band", "title": "Wrong kind"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/tour-board?new=1")
    page = client.get("/tour-board?new=1").get_data(as_text=True)
    assert "Not posted." in page and "Pick who you are" in page and "Posted." not in page.replace("Not posted.", "")
    r = client.get("/tour-board/post?kind=venue")
    assert r.status_code == 302 and r.headers["Location"].endswith("/tour-board?new=1&kind=venue")
    # legacy migration: a pre-structure row gets parsed on init
    legacy = store.add_board_listing(user["id"], "venue", "Saturday slots open", "Charlotte, NC", "Oct 2030", "indie", "Cap 250")
    bs.migrate_legacy_listings()
    l3 = bs.get_listing(legacy)
    assert l3["region_code"] == "metro-charlotte" and l3["window_start"] == "2030-10-01" and l3["genres"] == ["indie"] and l3["structured"] == 1
    assert l3["expires_at"]


def test_board_page_is_listings_first_and_has_no_email_field(flask_app):
    client, user = _user(flask_app)
    page = client.get("/tour-board").get_data(as_text=True)
    assert "Team-Up Board" in page and 'details class="tb-post' in page
    assert page.index('class="tb-list"') > page.index("tb-post") or "No open listings" in page
    assert 'name="contact"' not in page and 'type="email"' not in page
    assert 'accept-charset="utf-8"' in page and 'datalist id="tb-regions"' in page
    assert "/tour-board/inbox" in page


# --- threads -----------------------------------------------------------------------

def test_in_platform_threads_inbox_and_unread(flask_app, monkeypatch):
    import email_provider as emailer_mod
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    outbox = []
    monkeypatch.setattr(emailer_mod, "send", lambda to, subject, html, attachments=None: outbox.append((to, subject, html)) or True)
    poster, pu = _user(flask_app, "Poster")
    r = poster.post("/tour-board/post", data={"kind": "venue", "title": "Saturday slots at The Vault", "region_code": "metro-charlotte",
                                              "region_text": "Charlotte, NC", "window_start": "2030-10-01", "window_end": "2030-10-31", "details": "Cap 250"})
    lid = r.headers["Location"].rsplit("/", 1)[1]
    replier, ru = _user(flask_app, "Road Dog")
    # poster cannot reply to own listing
    poster.post("/tour-board/%s/reply" % lid, data={"message": "self"})
    assert bs.threads_for_listing(lid) == []
    r = replier.post("/tour-board/%s/reply" % lid, data={"message": "We pull 200 in Charlotte, October works."})
    assert r.status_code == 302 and "/tour-board/thread/" in r.headers["Location"]
    tid = r.headers["Location"].split("/thread/")[1].split("?")[0]
    # poster notified with a thread link, email body carries no address of the replier
    notes = store.list_notifications(pu["id"])
    assert any("Team-Up" in n["title"] and n["link"] == "/tour-board/thread/%s" % tid for n in notes)
    assert outbox and outbox[-1][0] == pu["email"] and ru["email"] not in outbox[-1][2]
    # unread: poster 1, replier 0; the board shows the count to the poster only
    assert bs.unread_total(pu["id"]) == 1 and bs.unread_total(ru["id"]) == 0
    page = poster.get("/tour-board").get_data(as_text=True)
    assert "1 reply" in page and 'class="tb-unread">1' in page
    other_page = replier.get("/tour-board").get_data(as_text=True)
    assert "1 reply" not in other_page
    # thread view marks read, both sides can message, the other is notified
    page = poster.get("/tour-board/thread/%s" % tid).get_data(as_text=True)
    assert "We pull 200 in Charlotte" in page and bs.unread_total(pu["id"]) == 0
    poster.post("/tour-board/thread/%s" % tid, data={"message": "Oct 12 is open — what's your ticket price?"})
    assert bs.unread_total(ru["id"]) == 1
    inbox = replier.get("/tour-board/inbox").get_data(as_text=True)
    assert "Saturday slots at The Vault" in inbox and 'class="tb-unread">1' in inbox
    # a stranger cannot read the thread
    stranger, _ = _user(flask_app, "Stranger")
    assert stranger.get("/tour-board/thread/%s" % tid).status_code == 404
    # filled via the thread -> matched badge on the listing, replier notified
    poster.post("/tour-board/%s/fill" % lid, data={"thread_id": tid})
    l = bs.get_listing(lid)
    assert l["status"] == "filled" and l["filled_via"] == tid and l["matched"]
    assert "Matched on the Board" in poster.get("/tour-board/%s" % lid).get_data(as_text=True)
    assert any("Matched" in n["title"] for n in store.list_notifications(ru["id"]))
    # compat accessor still lists the replier's messages
    assert bs.list_board_replies(lid)[0]["message"].startswith("We pull 200")


# --- lifecycle ------------------------------------------------------------------------

def test_lifecycle_expiry_renew_edit(flask_app, monkeypatch):
    import email_provider as emailer_mod
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    outbox = []
    monkeypatch.setattr(emailer_mod, "send", lambda to, subject, html, attachments=None: outbox.append((to, subject, html)) or True)
    client, user = _user(flask_app)
    r = client.post("/tour-board/post", data={"kind": "artist", "title": "Expiring soon", "region_code": "us-midwest", "region_text": "Midwest"})
    lid = r.headers["Location"].rsplit("/", 1)[1]
    # force it past expiry
    with store.get_db() as db:
        db.execute("UPDATE tour_board SET expires_at = ? WHERE id = ?", ("2000-01-01T00:00:00", lid))
    # the board sweep sends one renew email with a token link, and hides it from the open board
    other, _ = _user(flask_app, "Other")
    page = other.get("/tour-board").get_data(as_text=True)
    assert "Expiring soon" not in page
    assert outbox and "Renew" in outbox[-1][1] and "/board-renew/%s?t=" % lid in outbox[-1][2]
    token = outbox[-1][2].split("board-renew/%s?t=" % lid)[1].split('"')[0]
    own_page = client.get("/tour-board").get_data(as_text=True)
    assert "Expiring soon" in own_page and "Renew for 60 days" in own_page
    # one-click renew from the email works signed out, and the token is single-use
    anon = flask_app.test_client()
    assert anon.get("/board-renew/%s?t=%s" % (lid, token)).status_code == 200
    l = bs.get_listing(lid)
    assert l["effective_status"] == "open" and l["expires_at"] > date.today().isoformat()
    assert anon.get("/board-renew/%s?t=%s" % (lid, token)).status_code == 404
    assert anon.get("/board-renew/%s?t=wrong" % lid).status_code == 404
    assert "Expiring soon" in other.get("/tour-board").get_data(as_text=True)
    # edit, close, reopen
    client.post("/tour-board/%s/edit" % lid, data={"title": "Edited title", "region_code": "us-midwest", "region_text": "Midwest", "window_start": "2030-05-01", "window_end": "2030-05-03"})
    assert bs.get_listing(lid)["title"] == "Edited title" and bs.get_listing(lid)["window_end"] == "2030-05-03"
    client.post("/tour-board/%s/close" % lid)
    assert bs.get_listing(lid)["status"] == "closed"
    assert "Edited title" not in other.get("/tour-board").get_data(as_text=True)
    client.post("/tour-board/%s/reopen" % lid)
    assert bs.get_listing(lid)["status"] == "open"
    # a stranger cannot edit or close
    other.post("/tour-board/%s/close" % lid)
    assert bs.get_listing(lid)["status"] == "open"
    assert other.get("/tour-board/%s/edit" % lid).status_code == 404


def test_an_explicit_state_beats_a_colliding_city_name():
    """City names collide across states and countries. When the poster names
    a state, believe the state - otherwise a New Hampshire venue files as UK
    and never appears in a US filter."""
    assert tx.parse_region("Manchester, NH") == (tx.US_STATE_REGION["nh"], "state")
    assert tx.parse_region("Portland, ME") == (tx.US_STATE_REGION["me"], "state")
    assert tx.parse_region("Charleston, WV") == (tx.US_STATE_REGION["wv"], "state")
    # a state that agrees with the metro keeps the more precise metro code
    assert tx.parse_region("Portland, OR")[0] == "metro-portland"
    assert tx.parse_region("Nashville, TN")[0] == "metro-nashville"
    # and a bare city with no state still resolves as before
    assert tx.parse_region("Manchester")[0] == "metro-manchester"


def test_a_word_that_merely_starts_like_a_month_is_not_a_date():
    """'may be flexible' must not become a May date window - that silently
    answers date filters the poster never opted into."""
    for phrase in ("may be flexible", "maybe next spring", "junction shows", "marching band"):
        start, end = tx.parse_window(phrase)
        assert not (start and start[5:7] in ("05", "06", "03")) or "spring" in phrase, (phrase, start, end)
    assert tx.parse_window("may be flexible") == (None, None)
    assert tx.parse_window("junction shows") == (None, None)
    # real months still parse
    assert tx.parse_window("May 2030") == ("2030-05-01", "2030-05-31")
    assert tx.parse_window("October 2030") == ("2030-10-01", "2030-10-31")
    assert tx.parse_window("Sept 2030") == ("2030-09-01", "2030-09-30")


def test_ago_never_says_zero_years():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)

    def at(days):
        return bs.ago((now - timedelta(days=days)).isoformat(), now=now)

    for d in (359, 360, 362, 364):
        assert "0 years" not in at(d) and "months ago" in at(d), (d, at(d))
    assert at(365).endswith("year ago") or at(365).endswith("years ago")
    assert bs.ago((now - timedelta(seconds=95)).isoformat(), now=now) == "1 minute ago"


def test_legacy_rows_survive_the_migration_and_can_be_renewed(flask_app):
    """A listing posted long before the lifecycle columns existed must not
    be born expired, and must get a working renew token - otherwise it
    silently drops off the board and its one renewal email 404s."""
    client, user = _user(flask_app)
    old = store.add_board_listing(user["id"], "artist", "Ancient listing", "SE", "Oct", "indie", "details")
    with store.get_db() as db:                       # look like a pre-feature row
        db.execute("UPDATE tour_board SET structured=0, expires_at='', renew_token='', created=? WHERE id=?",
                   ("2019-03-04T10:00:00", old))
    bs.migrate_legacy_listings()
    l = bs.get_listing(old)
    assert l["expires_at"] > date.today().isoformat(), "a six-year-old listing was born expired"
    assert l["renew_token"], "no renew token, so its renewal email would be a dead link"
    assert not l["is_expired"] and l["effective_status"] == "open"
    assert "Ancient listing" in client.get("/tour-board").get_data(as_text=True)
    # the token works, and only once
    anon = flask_app.test_client()
    assert anon.get("/board-renew/%s?t=%s" % (old, l["renew_token"])).status_code == 200
    assert anon.get("/board-renew/%s?t=%s" % (old, l["renew_token"])).status_code == 404


def test_a_renew_token_cannot_resurrect_a_closed_or_filled_listing(flask_app):
    """The token arrives by GET from a mail client that may prefetch it. It
    may extend a listing that is still meant to be up; it may not undo the
    owner's decision to close or fill one."""
    client, user = _user(flask_app)
    r = client.post("/tour-board/post", data={"kind": "artist", "title": "Closed one", "region_code": "us-midwest", "region_text": "Midwest"})
    lid = r.headers["Location"].rsplit("/", 1)[1]
    token = bs.get_listing(lid)["renew_token"]
    client.post("/tour-board/%s/close" % lid)
    anon = flask_app.test_client()
    assert anon.get("/board-renew/%s?t=%s" % (lid, token)).status_code == 404
    assert bs.get_listing(lid)["status"] == "closed", "a prefetched email link reopened a closed listing"
    # the owner, signed in, still can
    client.post("/tour-board/%s/reopen" % lid)
    assert bs.get_listing(lid)["status"] == "open"


def test_region_filter_is_applied_in_sql_not_after_the_limit(flask_app):
    """Region matching is a taxonomy relationship, so it used to be filtered
    in Python after LIMIT - which returns an empty board once there are more
    open listings than the limit."""
    client, user = _user(flask_app)
    for i in range(12):
        client.post("/tour-board/post", data={"kind": "artist", "title": "PNW filler %d" % i,
                                              "region_code": "metro-seattle", "region_text": "Seattle, WA"})
    client.post("/tour-board/post", data={"kind": "artist", "title": "THE ATLANTA ONE",
                                          "region_code": "metro-atlanta", "region_text": "Atlanta, GA"})
    # A limit smaller than the number of newer non-matching listings: under a
    # post-LIMIT filter the SQL would return five Seattle rows and the Python
    # pass would drop them all, so Atlanta could never appear.
    hits = [h["title"] for h in bs.list_listings(region="us-southeast", limit=5)]
    assert "THE ATLANTA ONE" in hits
    assert not any("PNW filler" in t for t in hits), hits
    assert "THE ATLANTA ONE" in [h["title"] for h in bs.list_listings(region="metro-atlanta", limit=5)]
    pnw = bs.list_listings(region="us-pnw", limit=5)
    assert pnw and all("PNW filler" in h["title"] for h in pnw)
    assert bs.list_listings(region="nonsense-region", limit=5) == []


# --- filters, sort, watches --------------------------------------------------------------

def test_filters_sort_and_saved_search_alerts(flask_app, monkeypatch):
    import email_provider as emailer_mod
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    outbox = []
    monkeypatch.setattr(emailer_mod, "send", lambda to, subject, html, attachments=None: outbox.append((to, subject, html)) or True)
    a, au = _user(flask_app, "A")
    b, bu = _user(flask_app, "B")
    a.post("/tour-board/post", data={"kind": "artist", "title": "FILTER nashville oct", "region_code": "metro-nashville", "region_text": "Nashville, TN",
                                     "window_start": "2031-10-10", "window_end": "2031-10-12", "genres": ["indie"]})
    a.post("/tour-board/post", data={"kind": "venue", "title": "FILTER seattle may", "region_code": "metro-seattle", "region_text": "Seattle, WA",
                                     "window_start": "2031-05-01", "window_end": "2031-05-03", "genres": ["metal"]})
    def titles(q):
        page = b.get("/tour-board" + q).get_data(as_text=True)
        return [t for t in ("FILTER nashville oct", "FILTER seattle may") if t in page.split("Your listings")[0]]
    assert titles("?kind=venue") == ["FILTER seattle may"]
    assert titles("?region=us-southeast") == ["FILTER nashville oct"]          # metro inside the region
    assert titles("?genre=metal") == ["FILTER seattle may"]
    assert titles("?from=2031-10-01&to=2031-10-31") == ["FILTER nashville oct"]
    page = b.get("/tour-board?sort=soonest").get_data(as_text=True).split("Your listings")[0]
    assert page.index("FILTER seattle may") < page.index("FILTER nashville oct")
    # B watches Southeast + indie; A posts a matching listing -> B notified + emailed
    b.post("/tour-board/watch", data={"kind": "", "region": "us-southeast", "genre": "indie"})
    assert bs.list_watches(bu["id"]) and "Southeast" in bs.list_watches(bu["id"])[0]["label"]
    outbox.clear()
    a.post("/tour-board/post", data={"kind": "artist", "title": "WATCH atlanta indie", "region_code": "metro-atlanta", "region_text": "Atlanta, GA", "genres": ["indie"]})
    assert any("WATCH atlanta indie" in n["body"] for n in store.list_notifications(bu["id"]))
    assert outbox and outbox[-1][0] == bu["email"] and "WATCH atlanta indie" in outbox[-1][2]
    # a non-matching post does not alert
    outbox.clear()
    a.post("/tour-board/post", data={"kind": "artist", "title": "WATCH portland metal", "region_code": "metro-portland", "region_text": "Portland, OR", "genres": ["metal"]})
    assert not outbox
    # unwatch
    wid = bs.list_watches(bu["id"])[0]["id"]
    b.post("/tour-board/watch/%s/delete" % wid)
    assert bs.list_watches(bu["id"]) == []


# --- verified chips & doorways ---------------------------------------------------------------

def test_verified_chips_come_from_platform_records(flask_app):
    client, user = _user(flask_app)
    assert bs.verified_chips(user["id"])["chips"] == []
    for d in ("2020-01-01", "2020-02-01", "2020-03-01"):
        sid = store.add_tour_show(user["id"], d, "Room", "Asheville, NC", "")
        store.update_tour_show_status(user["id"], sid, "played")
    chips = bs.verified_chips(user["id"])["chips"]
    labels = [c["label"] for c in chips]
    assert "3 shows played" in labels and "home market Asheville, NC" in labels
    r = client.post("/tour-board/post", data={"kind": "artist", "title": "CHIPS listing", "region_code": "us-southeast", "region_text": "Southeast US"})
    page = client.get(r.headers["Location"]).get_data(as_text=True)
    assert "✓ 3 shows played" in page and "home market Asheville, NC" in page


def test_prefilled_doorway_opens_the_form(flask_app):
    client, user = _user(flask_app)
    page = client.get("/tour-board?new=1&kind=artist&title=Support+slot+Oct+12&region=Nashville,+TN&from=2030-10-12&to=2030-10-12").get_data(as_text=True)
    assert 'value="Support slot Oct 12"' in page and 'value="metro-nashville"' in page and 'value="2030-10-12"' in page
    assert '<details class="tb-post tb-pane is-warm" open' in page
    # the TOUR calendar offers the doorway on off/travel days
    import tour_store as ts
    tid = ts.create_tour(user["id"], {"name": "Run", "home_tz": "UTC"})
    ts.add_day(tid, user["id"], "2030-06-02", "off", "Day off", "Asheville, NC")
    cal = client.get("/tours/%s/calendar?view=list&month=2030-06" % tid).get_data(as_text=True)
    assert "/tour-board?new=1" in cal and "Asheville" in cal
