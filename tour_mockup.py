"""The Mock Up Tour: a full routing every new Tour account opens with.

Owner, 2026-09-17: the Tour service has no disk yet, "nothing now is needed
to be saved", so rather than one demo account that a restart would erase,
every account that arrives with no tours gets its own copy of this run. It
is a real van routing (44 days, 36 shows, off days, a festival, holds and
confirmations, flat fees and a percentage deal, six merch splits), imported
through the same parser and the same store calls as the Import page, so the
demo exercises exactly what a pasted deal sheet does.

The owner's words: "just name it mock up tour". No artist is named.
"""

import tour_engine as eng
import tour_store as ts
import db as store

NAME = "Mock Up Tour"

# Tab-separated, as the deal sheet arrived. START/END rows carry no city and
# are dropped by the parser; OFF rows become off days.
SHEET = "\n".join("\t".join(row) for row in [
    ("DAY", "DATE", "CITY", "VENUE", "CAPACITY", "STATUS", "GUARANTEE", "MERCH RATE"),
    ("Monday", "October 12, 2026", "OFF", "", "", "", "", ""),
    ("Tuesday", "October 13, 2026", "St. Paul, MN", "Turf Club", "350", "3H Challenged", "TBC", "100%, Artist Sells"),
    ("Wednesday", "October 14, 2026", "Iowa City, IA", "Gabe's", "400", "2H Challenged", "TBC", ""),
    ("Thursday", "October 15, 2026", "Milwaukee, WI", "X-Ray Arcade", "275", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Friday", "October 16, 2026", "Indianapolis, IN", "Turntable", "400", "CONFIRMED", "$350", "100%, Artist Sells"),
    ("Saturday", "October 17, 2026", "Chicago, IL", "Bottom Lounge", "700", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Sunday", "October 18, 2026", "Louisville, KY", "Zanzabar", "350", "3H Challenged", "$350", "100%, Artist Sells"),
    ("Monday", "October 19, 2026", "Cleveland, OH", "The Foundry Concert Club", "250", "1H", "$500", "100%, Artist Sells"),
    ("Tuesday", "October 20, 2026", "OFF", "", "", "", "", ""),
    ("Wednesday", "October 21, 2026", "Columbus, OH", "Skully's Music Diner", "500", "CONFIRMED", "15% NBOR capped at $500", "100%, Artist Sells"),
    ("Thursday", "October 22, 2026", "Ferndale, MI", "The Magic Bag", "450", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Friday", "October 23, 2026", "OFF", "", "", "", "", ""),
    ("Saturday", "October 24, 2026", "Rochester, NY", "Photo City Music Hall", "430", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Sunday", "October 25, 2026", "Pittsburgh, PA", "The Crafthouse", "350", "CONFIRMED", "$500", "90/10, 100% CD/DVD, Artist Sells"),
    ("Monday", "October 26, 2026", "OFF", "", "", "", "", ""),
    ("Tuesday", "October 27, 2026", "Philadelphia, PA", "Underground Arts", "650", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Wednesday", "October 28, 2026", "Providence, RI", "Alchemy", "280", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Thursday", "October 29, 2026", "Hamden, CT", "Space Ballroom", "300", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Friday", "October 30, 2026", "Brooklyn, NY", "The Sultan Room (1 of 2)", "280", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Saturday", "October 31, 2026", "Brooklyn, NY", "The Sultan Room (2 of 2)", "280", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Sunday", "November 1, 2026", "Washington, DC", "Pearl Street Warehouse", "300", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Monday", "November 2, 2026", "OFF", "", "", "", "", ""),
    ("Tuesday", "November 3, 2026", "Atlanta, GA", "Terminal West", "625", "CONFIRMED", "$300", "85/15, 100% CD/DVD, Artist Sells"),
    ("Wednesday", "November 4, 2026", "Baton Rouge, LA", "Chelsea's Live", "602", "CONFIRMED", "$300", "100%, Artist Sells"),
    ("Thursday", "November 5, 2026", "Houston, TX", "Numbers", "750", "CONFIRMED", "$350", "80/20, Artist Sells"),
    ("Friday", "November 6, 2026", "Austin, TX", "Elysium", "500", "CONFIRMED", "$350", "TBC"),
    ("Saturday", "November 7, 2026", "San Antonio, TX", "The Rock Box", "750", "CONFIRMED", "$350", "80/20, Artist Sells"),
    ("Sunday", "November 8, 2026", "Dallas, TX", "Trees", "700", "CONFIRMED", "$350", "90/10, 100% CD/DVD, Artist Sells"),
    ("Monday", "November 9, 2026", "OFF", "", "", "", "", ""),
    ("Tuesday", "November 10, 2026", "El Paso, TX", "Lowbrow Palace", "700", "CONFIRMED", "$350", "TBC"),
    ("Wednesday", "November 11, 2026", "Tucson, AZ", "Club Congress Plaza", "550", "CONFIRMED", "$350", "90/10, 100% CD/DVD, Artist Sells"),
    ("Thursday", "November 12, 2026", "Las Vegas, NV", "Swan Dive", "250", "CONFIRMED", "$350", "100%, Artist Sells"),
    ("Friday", "November 13, 2026", "San Diego, CA", "Music Box", "705", "CONFIRMED", "$350", "100%, Artist Sells"),
    ("Saturday", "November 14, 2026", "Huntington Beach, CA", "Darker Waves 2026 (festival, no support)", "", "CONFIRMED", "", "Festival"),
    ("Sunday", "November 15, 2026", "Fresno, CA", "Strummer's", "400", "CONFIRMED", "$500", "90/10, Artist Sells"),
    ("Monday", "November 16, 2026", "San Francisco, CA", "Great American Music Hall", "700", "CONFIRMED", "$500", "80/20, 100% CD/DVD, Artist Sells"),
    ("Tuesday", "November 17, 2026", "Sacramento, CA", "Harlow's", "475", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Wednesday", "November 18, 2026", "OFF", "", "", "", "", ""),
    ("Thursday", "November 19, 2026", "Tacoma, WA", "Airport Tavern", "500", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Friday", "November 20, 2026", "Portland, OR", "Star Theater", "500", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Saturday", "November 21, 2026", "Boise, ID", "Shrine Social Club", "700", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Sunday", "November 22, 2026", "Salt Lake City, UT", "Urban Lounge", "400", "CONFIRMED", "$500", "90/10, 100% CD/DVD, Artist Sells. Reverts to 100% at 400 paid attendance (sellout)."),
    ("Monday", "November 23, 2026", "OFF", "", "", "", "", ""),
    ("Tuesday", "November 24, 2026", "Denver, CO", "Meow Wolf", "478", "CONFIRMED", "$500", "100%, Artist Sells"),
    ("Wednesday", "November 25, 2026", "OFF", "", "", "", "", ""),
])


def ensure_for(user):
    """Give an account with no tours its own Mock Up Tour. Returns the tour id
    when one was created, else None. Never touches an account that already has
    a tour, so a real routing is never mixed with the demo."""
    if not user or ts.list_tours(user["id"]):
        return None
    # Imported lazily: tour_os imports the Flask app's pieces at module load.
    from tour_os import _import_ext, _import_status

    rows, _problems = eng.parse_csv_rows(SHEET)
    tour_id = ts.create_tour(user["id"], {
        "name": NAME, "status": "planning",
        "start_date": "2026-10-12", "end_date": "2026-11-25",
        "home_tz": "America/Chicago", "currency": "USD",
        "notes": "A demonstration routing. Every date here is an example to click through, not a booking of yours."})
    for r in rows:
        if r["kind"] == "show":
            sid = store.add_tour_show(user["id"], r["date"], r["venue"] or "TBA", r["city"], r["notes"])
            ts.attach_show(tour_id, sid, r["tz"] if eng.valid_tz(r["tz"]) else "")
            ext = _import_ext(r)
            if ext:
                ts.update_show_ext(tour_id, sid, ext)
            status = _import_status(r.get("status"))
            if status:
                store.update_tour_show_status(user["id"], sid, status)
        else:
            ts.add_day(tour_id, user["id"], r["date"], r["kind"], r["venue"] or r["kind"].title(),
                       r["city"], r["tz"] if eng.valid_tz(r["tz"]) else "", None, r["notes"])
    ts.record_import(tour_id, user["id"], "csv", "mock-up-tour.tsv", SHEET,
                     {"created": {"rows": len(rows)}, "problems": [], "rows": len(rows)})
    return tour_id
