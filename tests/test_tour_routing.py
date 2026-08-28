"""TOUR — reading a real routing sheet, and the parts of a van run that
had no home: support lineup, buyouts, VIP, and fuel.

Every fixture here is from the DEVORA / PRAYERS 2026 routing the module
was built against, because the shapes that broke the importer were the
shapes a real sheet actually arrives in.
"""
import os

import pytest

import app as appmod
import db as store
import tour_engine as eng
import tour_store as ts

PASSWORD = "tour-pass-123"


@pytest.fixture(scope="module")
def flask_app():
    return appmod.create_app()


def _user(flask_app, label="Tour Manager"):
    import uuid
    email = "tr-%s@example.net" % uuid.uuid4().hex[:8]
    c = flask_app.test_client()
    c.post("/signup", data={"name": label, "email": email, "password": PASSWORD})
    c.post("/login", data={"email": email, "password": PASSWORD})
    return c, store.get_user_by_email(email)


def _tour(client, **over):
    data = {"name": "Test Run", "artist_name": "Test Artist", "start_date": "2030-05-01",
            "end_date": "2030-05-10", "home_tz": "America/New_York", "currency": "USD"}
    data.update(over)
    r = client.post("/tours/new", data=data)
    assert r.status_code == 302
    return r.headers["Location"].rstrip("/").split("/")[-1]


def _show(client, tour_id, date_, venue, city="Nashville, TN"):
    r = client.post("/tours/%s/days/add" % tour_id,
                    data={"date": date_, "kind": "show", "venue": venue, "city": city,
                          "tz": "America/Chicago"})
    assert r.status_code == 302
    return r.headers["Location"].split("/shows/")[1].split("?")[0]



# --- the shapes a routing sheet arrives in ----------------------------------

def test_two_digit_years_and_tab_columns():
    """A table copied out of Word or a spreadsheet is tab separated and
    dated '10/14/26'. Both used to fail every line with 'no date at the
    start', which is a wall, not an error message."""
    rows, problems = eng.parse_pasted(
        "10/14/26\tIowa City, IA\tGabe's\n"
        "11/11/26\tTucson, AZ\t191 Toole / Club Congress Plaza")
    assert not problems
    assert rows[0]["date"] == "2026-10-14"
    assert rows[0]["city"] == "Iowa City, IA" and rows[0]["venue"] == "Gabe's"
    # A slash inside a venue name is not a separator.
    assert rows[1]["venue"] == "191 Toole / Club Congress Plaza"
    # The window: 00-68 is this century, 69-99 last.
    assert eng._to_iso("1/2/26") == "2026-01-02"
    assert eng._to_iso("1/2/99") == "1999-01-02"


def test_city_and_venue_in_either_order():
    """One sheet lists 'City - Venue', the next 'Venue - City'. The state
    suffix decides, not the column it landed in."""
    a, _ = eng.parse_pasted("10/14/26 - Iowa City, IA - Gabe's")
    b, _ = eng.parse_pasted("October 14 - Wednesday - Gabe's - Iowa City, IA",
                            default_year=2026)
    assert a[0]["city"] == b[0]["city"] == "Iowa City, IA"
    assert a[0]["venue"] == b[0]["venue"] == "Gabe's"
    # A weekday beside the date says nothing the date does not.
    assert "Wednesday" not in (b[0]["city"] + b[0]["venue"])


def test_a_hyphen_inside_a_name_is_not_a_separator():
    """'X-Ray Arcade' and 'Sold-Out Room' would be torn in half by a
    naive dash split; only a SPACED hyphen separates columns."""
    rows, _ = eng.parse_pasted("10/15/26 - Cudahy, WI - X-Ray Arcade")
    assert rows[0]["venue"] == "X-Ray Arcade"


def test_a_month_name_with_no_year_takes_the_tours_year():
    """A routing email writes 'October 14', never 'October 14, 2026'."""
    rows, problems = eng.parse_pasted("October 14 - Wednesday - OFF", default_year=2026)
    assert not problems and rows[0]["date"] == "2026-10-14" and rows[0]["kind"] == "off"
    # With no tour to ask, it says so instead of guessing a year.
    rows2, problems2 = eng.parse_pasted("October 14 - Wednesday - OFF")
    assert not rows2 and problems2 and "add a year" in problems2[0]


def test_ticket_links_attach_to_the_date_above_them():
    text = ("October 14 - Wednesday - Gabe's - Iowa City, IA\n"
            "Ticket Link: https://www.axs.com/events/1547852/prayers-tickets\n"
            "\n"
            "October 18 - Sunday - Zanzabar - Louisville, KY\n"
            "Ticket Link: **waiting on link**\n"
            "\n"
            "November 6 - Friday - Elysium - Austin, TX\n"
            "GA Ticket Link: https://example.com/ga\n"
            "VIP Ticket Link: https://example.com/vip")
    rows, problems = eng.parse_pasted(text, default_year=2026)
    assert not problems and len(rows) == 3          # links are not rows of their own
    assert rows[0]["ticket_url"].endswith("prayers-tickets")
    # "waiting on link" is a fact about the date, not a URL to store.
    assert rows[1].get("ticket_pending") and not rows[1].get("ticket_url")
    # A show with a separate VIP on-sale keeps both.
    assert rows[2]["ticket_url"] == "https://example.com/ga"
    assert rows[2]["extra_links"] == [("VIP", "https://example.com/vip")]
    # A link with nothing above it is reported rather than dropped.
    _, orphan = eng.parse_pasted("Ticket Link: https://example.com/x")
    assert orphan and "no date above it" in orphan[0]


def test_a_deal_sheet_imports_with_its_deal():
    """Tabs, a header row, and commas inside the values — a merch rate of
    '90/10, 100% CD/DVD, Artist Sells' would tear a comma-split apart."""
    sheet = (
        "DAY\tDATE\tCITY\tVENUE\tCAPACITY\tSTATUS\tDEVORA $$\tMERCH RATE\n"
        "Sunday\tOctober 11, 2026\tSTART\t\t\t\t\t\n"
        "Tuesday\tOctober 13, 2026\tSt. Paul, MN\tTurf Club\t350\t3H Challenged\tTBC\t100%, Artist Sells\n"
        "Wednesday\tOctober 21, 2026\tColumbus, OH\tSkully's\t500\tCONFIRMED\t15% NBOR capped at $500\t100%, Artist Sells\n"
        "Tuesday\tOctober 20, 2026\tOFF\t\t\t\t\t\n"
        "Thursday\tNovember 26, 2026\tEND\t\t\t\t\t")
    rows, problems = eng.parse_csv_rows(sheet)
    assert not problems and len(rows) == 5
    by_date = {r["date"]: r for r in rows}
    # START / OFF / END live in the CITY column on a routing grid. Read as
    # venue-less shows they became empty dates on the calendar.
    assert by_date["2026-10-11"]["kind"] == "off" and not by_date["2026-10-11"]["city"]
    assert by_date["2026-10-20"]["kind"] == "off"
    assert by_date["2026-11-26"]["kind"] == "off"
    st = by_date["2026-10-13"]
    assert st["kind"] == "show" and st["venue"] == "Turf Club" and st["capacity"] == "350"
    assert st["status"] == "3H Challenged" and st["fee"] == "TBC"
    col = by_date["2026-10-21"]
    assert col["fee"] == "15% NBOR capped at $500"
    assert col["merch"] == "100%, Artist Sells"


def test_a_comma_csv_still_parses():
    """The delimiter is picked from the header, so the old comma files
    that worked before must go on working."""
    rows, problems = eng.parse_csv_rows(
        "date,city,venue\n2026-10-14,Iowa City,Gabe's")
    assert not problems and rows[0]["venue"] == "Gabe's"


# --- fuel -------------------------------------------------------------------

ASSUMPTIONS = {"fuel_mpg": "16", "fuel_price": "3.75", "fuel_reserve_pct": "10",
               "stated_miles": "9775"}


def test_fuel_matches_the_itinerarys_own_arithmetic():
    """The tour document states ~9,775 miles, ~611 gallons and ~$2,291
    before a 10% reserve. If this function disagrees with the sheet the
    tour manager is already using, one of them is wrong on the road."""
    p = eng.fuel_plan(ASSUMPTIONS)
    assert p["ready"] and p["miles"] == 9775
    assert round(p["gallons"]) == 611
    assert round(p["fuel_cost"]) == 2291
    assert round(p["reserve"]) == 229
    assert round(p["total"]) == 2520
    assert round(eng.fuel_per_show(p, 35), 2) == 72.00


def test_a_stated_estimate_is_never_dressed_up_as_a_routed_total():
    """The difference matters at settlement: one is a number somebody
    typed before any address existed, the other is the drive."""
    est = eng.fuel_plan(ASSUMPTIONS)
    assert est["miles_source"] == "estimate"

    # A part-entered route would read as a total and be short by every
    # leg nobody filled in, so the estimate keeps winning until it is done.
    part = eng.fuel_plan(ASSUMPTIONS, [{"miles": "310"}, {"miles": ""}, {"miles": "290"}])
    assert part["miles_source"] == "estimate" and part["miles"] == 9775
    assert part["legs_entered"] == 2 and part["legs_total"] == 3

    full = eng.fuel_plan(ASSUMPTIONS, [{"miles": "310"}, {"miles": "265"}, {"miles": "290"}])
    assert full["miles_source"] == "routed" and full["miles"] == 865


def test_fuel_refuses_to_invent_a_missing_assumption():
    p = eng.fuel_plan({"stated_miles": "9775"})
    assert not p["ready"] and p["total"] is None
    assert p["missing"] == ["miles per gallon", "price per gallon"]
    # No mileage at all is the same answer, not a zero.
    q = eng.fuel_plan({"fuel_mpg": "16", "fuel_price": "3.75"})
    assert "mileage" in q["missing"] and q["gallons"] is None
    # Nonsense in, nothing out — never a division by zero or a NaN total.
    for bad in ({"fuel_mpg": "0"}, {"fuel_mpg": "abc"}, {"fuel_mpg": "-4"}):
        r = eng.fuel_plan(dict(ASSUMPTIONS, **bad))
        assert not r["ready"] and r["total"] is None
    # A tour with no shows divides by nothing rather than by zero.
    assert eng.fuel_per_show(eng.fuel_plan(ASSUMPTIONS), 0) is None


# --- the advance items a van run needs --------------------------------------

def test_the_advance_carries_buyout_vip_and_the_drive():
    """Each of these is a question somebody asks on the day if it was not
    answered in the advance."""
    keys = {k for items in ts.ADVANCE_CATEGORIES.values() for k, _ in items}
    for key in ("buyout", "vip_location", "vip_time", "vip_capacity", "vip_entry",
                "vip_host", "fuel_stop", "tolls", "departure"):
        assert key in keys, key
    assert "vip" in ts.ADVANCE_CATEGORIES
    # The label says a buyout is per person, because that is the number
    # that gets argued about at settlement.
    labels = dict(ts.ADVANCE_CATEGORIES["artist"])
    assert "per person" in labels["buyout"]


def test_a_show_records_who_else_is_on_the_bill():
    """A package tour's support changes date to date, so the lineup
    belongs on the show and not on the tour."""
    assert "support" in ts.EXT_FIELDS
    assert "vip_ticket_url" in ts.EXT_FIELDS
    # Where a value came from, for when two sheets disagreed.
    assert "source_note" in ts.EXT_FIELDS


# --- sharing the run with the band ------------------------------------------

def test_a_band_link_carries_the_run_and_not_the_deal(flask_app):
    """Every other share scope is one show handed over for one job. A band
    member's question is "where am I on the 14th", so this one is the whole
    tour — and that makes what it leaves out the important part."""
    client, owner = _user(flask_app)
    tid = _tour(client)
    sid = _show(client, tid, "2030-05-02", "The Basement East")
    ts.update_show_ext(tid, sid, {
        "capacity": "400", "guarantee": "2500", "support": "DEVORA, CHRIZ AMAYA",
        "settlement_amount": "3100", "merch_gross": "1800"})
    client.post("/tours/%s/schedule/add" % tid, data={
        "show_id": sid, "title": "Load in", "category": "load_in", "start_time": "15:00"})
    client.post("/tours/%s/hotels/add" % tid, data={
        "show_id": sid, "checkin": "2030-05-02", "property": "Hotel Indigo",
        "address": "301 Union St", "confirmation": "CONF-99887",
        "reservation_name": "Tour Manager", "payment": "AMEX 1004"})
    client.post("/tours/%s/travel/add" % tid, data={
        "show_id": sid, "day_date": "2030-05-02", "mode": "ground",
        "dep_time": "12:30", "dep_loc": "Hotel", "arr_loc": "Venue",
        "driver": "Marcus", "phone": "615-555-0134", "confirmation": "VAN-77"})

    r = client.post("/tours/%s/share/new" % tid, data={"scope": "band"})
    assert r.status_code == 302
    link = [l for l in ts.list_share_links(tid) if l["scope"] == "band"][0]
    # Tour-wide: it must not be pinned to one date.
    assert not link["show_id"]

    page = flask_app.test_client().get("/tour-share/%s" % link["token"])
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    # The run itself travels.
    assert "The Basement East" in html and "Load in" in html
    assert "Hotel Indigo" in html and "301 Union St" in html
    assert "DEVORA, CHRIZ AMAYA" in html
    assert "12:30" in html or "12:30 PM" in html

    # The deal, the rooms and the phone numbers do not.
    for private in ("2500", "3100", "1800", "CONF-99887", "615-555-0134",
                    "VAN-77", "AMEX 1004", "Tour Manager"):
        assert private not in html, private
    for word in ("Guarantee", "Settlement", "Merch", "Guest list"):
        assert word not in html, word
    # And the page says so, so nobody assumes it was an oversight.
    assert "not on this page" in html


def test_a_band_link_is_revocable_like_every_other_share(flask_app):
    client, owner = _user(flask_app)
    tid = _tour(client)
    _show(client, tid, "2030-05-02", "Room A")
    client.post("/tours/%s/share/new" % tid, data={"scope": "band"})
    link = [l for l in ts.list_share_links(tid) if l["scope"] == "band"][0]
    reader = flask_app.test_client()
    assert reader.get("/tour-share/%s" % link["token"]).status_code == 200
    client.post("/tours/%s/share/%s/revoke" % (tid, link["id"]))
    assert reader.get("/tour-share/%s" % link["token"]).status_code == 404


def test_every_writable_show_field_can_be_read_back(flask_app):
    """list_shows names its columns one by one, so a field added to
    EXT_FIELDS and to the table but forgotten in that SELECT is writable
    and permanently unreadable — it just returns None and nobody notices
    until a page renders blank. `support` did exactly that."""
    client, owner = _user(flask_app)
    tid = _tour(client)
    sid = _show(client, tid, "2030-05-02", "Room A")
    skip = {"venue_id", "marketing", "readiness_config"}     # set by other paths
    probe = {f: "probe-%s" % f for f in ts.EXT_FIELDS if f not in skip}
    probe["deal_type"] = "flat"                              # constrained vocabularies
    probe["settlement_status"] = "open"
    ts.update_show_ext(tid, sid, probe)
    got = ts.get_show(tid, sid)
    missing = [f for f in probe if f not in got or got.get(f) is None]
    assert not missing, "written but unreadable: %s" % missing


# --- the import has to keep the deal, not just the dates --------------------

def test_importing_a_deal_sheet_keeps_the_deal(flask_app):
    """The confirm step used to apply promoter and capacity and throw the
    rest away — so a sheet carrying fees, merch rates, ticket links and
    hold statuses imported as 36 bare holds."""
    import tour_os
    client, owner = _user(flask_app)
    tid = _tour(client)
    sheet = ("DATE\tCITY\tVENUE\tCAPACITY\tSTATUS\tFEE\tMERCH RATE\tSUPPORT\tTICKET LINK\n"
             "2030-05-02\tChicago, IL\tBottom Lounge\t700\tCONFIRMED\t$500\t"
             "100%, Artist Sells\tDEVORA, CHRIZ AMAYA\thttps://example.com/tix\n"
             "2030-05-03\tColumbus, OH\tSkully's\t500\tCONFIRMED\t15% NBOR capped at $500\t"
             "90/10, 100% CD/DVD\tDEVORA\t\n"
             "2030-05-04\tSt. Paul, MN\tTurf Club\t350\t3H Challenged\tTBC\t\t\t\n")
    r = client.post("/tours/%s/import" % tid,
                    data={"source": "csv", "text": sheet, "action": "confirm",
                          "pick": ["0", "1", "2"]})
    assert r.status_code == 302
    shows = {s["venue"]: s for s in ts.list_shows(tid)}
    assert len(shows) == 3

    # A plain amount is a number; a sentence is kept verbatim beside it.
    assert shows["Bottom Lounge"]["guarantee"] == "500"
    assert shows["Skully's"]["fee_note"] == "15% NBOR capped at $500"
    assert not shows["Skully's"]["guarantee"]
    assert shows["Turf Club"]["fee_note"] == "TBC"

    # A merch rate is a sentence on every real sheet.
    assert shows["Bottom Lounge"]["merch_rate"] == "100%, Artist Sells"
    assert shows["Skully's"]["merch_rate"] == "90/10, 100% CD/DVD"

    assert shows["Bottom Lounge"]["support"] == "DEVORA, CHRIZ AMAYA"
    assert shows["Bottom Lounge"]["ticket_url"] == "https://example.com/tix"
    assert shows["Bottom Lounge"]["capacity"] == "700"

    # The sheet says which dates are real. A confirmed show must not
    # import as a hold, and a hold must keep the level it was written at.
    assert shows["Bottom Lounge"]["status"] == "confirmed"
    assert shows["Turf Club"]["status"] == "hold"
    assert shows["Turf Club"]["source_note"] == "3H Challenged"


def test_the_import_never_stores_a_dangerous_ticket_link(flask_app):
    import tour_os
    assert tour_os._import_ext({"ticket_url": "javascript:alert(1)"}) == {}
    assert tour_os._import_ext({"ticket_url": "data:text/html,<script>"}) == {}
    assert tour_os._import_ext({"ticket_url": "https://ok.example/x"})["ticket_url"]


def test_hold_levels_a_real_sheet_writes(flask_app):
    import tour_os
    for raw, want in [("CONFIRMED", "confirmed"), ("confirmed", "confirmed"),
                      ("3H Challenged", "hold"), ("2H Challenged", "hold"),
                      ("1H", "hold"), ("HOLD", "hold"), ("Pencilled", "hold"),
                      ("Option", "hold"), ("Advanced", "advanced"),
                      ("Played", "played"), ("Settled", "settled"),
                      ("", None), (None, None), ("Cancelled", None)]:
        assert tour_os._import_status(raw) == want, raw


def test_a_re_sent_deal_sheet_fills_in_dates_you_already_have(flask_app):
    """Importing the same sheet twice used to be pointless: dedupe marked
    every row a duplicate and the confirm step skipped it. But a re-sent
    sheet is exactly how a hold becomes a confirmation — and it is how you
    recover when the first import predated the columns it carries."""
    client, owner = _user(flask_app)
    tid = _tour(client)

    # First pass: dates only, the way an early import lands.
    bare = ("DATE\tCITY\tVENUE\n"
            "2030-05-02\tChicago, IL\tBottom Lounge\n"
            "2030-05-03\tColumbus, OH\tSkully's\n")
    client.post("/tours/%s/import" % tid,
                data={"source": "csv", "text": bare, "action": "confirm", "pick": ["0", "1"]})
    shows = {s["venue"]: s for s in ts.list_shows(tid)}
    assert len(shows) == 2
    assert not shows["Bottom Lounge"]["guarantee"] and not shows["Bottom Lounge"]["merch_rate"]

    # Somebody then types a fee by hand on one of them, and advances it.
    ts.update_show_ext(tid, shows["Bottom Lounge"]["id"], {"guarantee": "750"})
    store.update_tour_show_status(owner["id"], shows["Bottom Lounge"]["id"], "advanced")

    # Second pass: the full sheet, same dates and venues.
    full = ("DATE\tCITY\tVENUE\tCAPACITY\tSTATUS\tFEE\tMERCH RATE\tSUPPORT\tTICKET LINK\n"
            "2030-05-02\tChicago, IL\tBottom Lounge\t700\tCONFIRMED\t$500\t"
            "100%, Artist Sells\tDEVORA\thttps://example.com/a\n"
            "2030-05-03\tColumbus, OH\tSkully's\t500\tCONFIRMED\t$350\t90/10\tDEVORA\t"
            "https://example.com/b\n")
    r = client.post("/tours/%s/import" % tid,
                    data={"source": "csv", "text": full, "action": "confirm",
                          "pick": ["0", "1"], "fill_existing": "1"})
    assert r.status_code == 302
    after = {s["venue"]: s for s in ts.list_shows(tid)}
    # No duplicates created.
    assert len(after) == 2

    # Empty fields filled on both.
    assert after["Skully's"]["guarantee"] == "350"
    assert after["Skully's"]["merch_rate"] == "90/10"
    assert after["Skully's"]["ticket_url"] == "https://example.com/b"
    assert after["Skully's"]["support"] == "DEVORA"
    assert after["Skully's"]["capacity"] == "500"
    assert after["Skully's"]["status"] == "confirmed"

    # The hand-typed fee is NOT overwritten by the sheet.
    assert after["Bottom Lounge"]["guarantee"] == "750"
    # ...but the fields it did not have are filled.
    assert after["Bottom Lounge"]["merch_rate"] == "100%, Artist Sells"
    assert after["Bottom Lounge"]["capacity"] == "700"
    # ...and a status never walks backwards: advanced stays advanced even
    # though the sheet says confirmed.
    assert after["Bottom Lounge"]["status"] == "advanced"


def test_filling_in_is_opt_in(flask_app):
    """Without the box ticked the old behaviour stands, so an import can
    never quietly rewrite dates somebody did not mean to touch."""
    client, owner = _user(flask_app)
    tid = _tour(client)
    bare = "DATE\tCITY\tVENUE\n2030-05-02\tChicago, IL\tBottom Lounge\n"
    client.post("/tours/%s/import" % tid,
                data={"source": "csv", "text": bare, "action": "confirm", "pick": ["0"]})
    full = ("DATE\tCITY\tVENUE\tFEE\n2030-05-02\tChicago, IL\tBottom Lounge\t$500\n")
    client.post("/tours/%s/import" % tid,
                data={"source": "csv", "text": full, "action": "confirm", "pick": ["0"]})
    shows = ts.list_shows(tid)
    assert len(shows) == 1 and not shows[0]["guarantee"]


def test_a_four_digit_year_is_not_eaten_two_digits_at_a_time():
    r"""Regex alternation is ORDERED. `(?:\d{2}|20\d{2})` matched the
    two-digit branch first and succeeded, so the four-digit branch was
    dead code: "10/14/2026" parsed as "10/14/20" and left "26" behind as
    the venue name. Every routing sheet written with full years imported
    six years into the past, with nothing in `problems`, every row marked
    'new', and the preview pre-ticked.

    No test caught it because none of them pasted a four-digit year — the
    fixtures were all taken from one sheet that happened to use two."""
    for line, date_, venue in [
            ("10/14/2026 - Nashville, TN - The Basement", "2026-10-14", "The Basement"),
            ("1/2/2026 - Austin, TX - Elysium", "2026-01-02", "Elysium"),
            ("01/02/2026 - Austin, TX - Elysium", "2026-01-02", "Elysium"),
            ("12/31/2027 - Denver, CO - Meow Wolf", "2027-12-31", "Meow Wolf"),
            # the two-digit form must go on working
            ("10/14/26 - Nashville, TN - The Basement", "2026-10-14", "The Basement"),
            ("2026-10-14 - Nashville, TN - The Basement", "2026-10-14", "The Basement")]:
        rows, problems = eng.parse_pasted(line)
        assert not problems, (line, problems)
        assert rows[0]["date"] == date_, (line, rows[0]["date"])
        assert rows[0]["venue"] == venue, (line, rows[0]["venue"])
    # A whole sheet of full years must not land in the past.
    sheet = "\n".join("10/1%d/2026 - City %d, TN - Room %d" % (i, i, i) for i in range(1, 5))
    rows, problems = eng.parse_pasted(sheet)
    assert not problems
    assert all(r["date"].startswith("2026-") for r in rows), [r["date"] for r in rows]
    assert all(r["venue"].startswith("Room") for r in rows), [r["venue"] for r in rows]


def test_a_venue_with_travel_in_its_name_is_still_a_show():
    """`if "travel" in rl or "drive" in rl` was a substring test over every
    column joined together, and the not-a-show branch never assigns a
    venue — so a real date at Drive-In Theater became a venue-less travel
    day and quietly lost its room."""
    for line, kind, venue in [
            ("10/20/26 - Atlanta, GA - Drive-In Theater", "show", "Drive-In Theater"),
            ("10/20/26 - Nashville, TN - Traveller's Rest", "show", "Traveller's Rest"),
            ("10/20/26 - Chicago, IL - The Driver's Club", "show", "The Driver's Club"),
            # genuine travel days still read as travel
            ("10/20/26 - Travel to Atlanta", "travel", ""),
            ("10/20/26 - Drive to Chicago", "travel", ""),
            ("10/20/26 - Travel day", "travel", "")]:
        rows, problems = eng.parse_pasted(line)
        assert not problems, (line, problems)
        assert rows[0]["kind"] == kind, (line, rows[0]["kind"])
        assert rows[0]["venue"] == venue, (line, rows[0]["venue"])
