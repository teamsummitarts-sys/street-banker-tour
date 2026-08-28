"""Example tour for development and the demo showcase account.

Never called at init, never for a production workspace: tour_os only
reaches it from POST /tours/seed-demo, which 404s for any account that is
not the demo account. Everything here is fictional — venues, people,
numbers — and labelled as the example tour.

    python tour_seed.py <email>     # from a dev shell, seeds that user
"""
import sys
from datetime import date, timedelta

import db as store
import tour_store as ts


def seed(user_id, start=None):
    start = start or (date.today() + timedelta(days=10))
    d = lambda n: (start + timedelta(days=n)).isoformat()
    tour_id = ts.create_tour(user_id, {
        "name": "Example Run (seed data)", "artist_name": "Example Artist",
        "start_date": d(0), "end_date": d(6), "home_tz": "America/New_York",
        "currency": "USD", "notes": "Fictional example data loaded for the demo account."})
    shows = []
    for n, venue, city, tz, cap in [
            (0, "The Basement East", "Nashville, TN", "America/Chicago", "400"),
            (2, "Terminal West", "Atlanta, GA", "America/New_York", "600"),
            (4, "Cat's Cradle", "Carrboro, NC", "America/New_York", "750"),
            (6, "9:30 Club", "Washington, DC", "America/New_York", "1200")]:
        sid = store.add_tour_show(user_id, d(n), venue, city, "")
        ts.attach_show(tour_id, sid, tz)
        store.update_tour_show_status(user_id, sid, "confirmed")
        ts.update_show_ext(tour_id, sid, {
            "capacity": cap, "promoter": "Example Presents", "guest_allocation": "20",
            "guest_cutoff": "Day of show, 4 PM", "deal_type": "guarantee_vs_pct",
            "guarantee": "2500", "backend_pct": "80", "deposit_required": "1250",
            "deposit_received": "1250" if n < 4 else "", "ticket_url": "https://example.com/tickets",
            "tickets_sold": str(int(cap) // 2), "currency": "USD"})
        shows.append(ts.get_show(tour_id, sid))
    ts.add_day(tour_id, user_id, d(1), "travel", "Drive to Atlanta", "Atlanta, GA")
    ts.add_day(tour_id, user_id, d(3), "off", "Day off", "Carrboro, NC")
    ts.add_day(tour_id, user_id, d(5), "travel", "Drive to DC", "Washington, DC")
    for s in shows:
        ts.copy_standard_day(tour_id, user_id, s)
        ts.add_schedule_item(tour_id, user_id, {"show_id": s["id"], "day_date": s["date"],
                                                "title": "Lobby call", "category": "call",
                                                "start_time": "13:30", "location": "Hotel lobby"})
        ts.ensure_advance_items(tour_id, user_id, s["id"])
        for key, val in [("load_in", "3:00 PM dock on the alley side"), ("wifi", "venue-guest / example"),
                         ("parking", "Bus on the street, permit at the box office"),
                         ("catering", "Hot meal for 8 at 5:30 PM"), ("settlement_location", "Production office, after the show"),
                         ("promoter", "Example Presents · buyer@example.com")]:
            ts.set_advance_item(tour_id, s["id"], key, {"value": val, "status": "complete"})
        ts.ensure_content_plan(tour_id, user_id, s["id"])
    people = {}
    for name, role, cat, email, phone in [
            ("Example Artist", "Artist", "Artist", "artist@example.com", ""),
            ("Jordan Lee", "Tour manager", "Tour Management", "tm@example.com", "+1 555 0100"),
            ("Sam Rivera", "FOH engineer", "Production", "foh@example.com", "+1 555 0101"),
            ("Casey Morgan", "Driver", "Drivers", "driver@example.com", "+1 555 0102"),
            ("Alex Kim", "Photographer", "Photographer", "photo@example.com", "")]:
        people[name] = ts.add_person(tour_id, user_id, {"name": name, "role": role, "category": cat,
                                                         "email": email, "phone": phone})
    ts.add_travel(tour_id, user_id, {"day_date": d(1), "mode": "ground", "vehicle": "Sprinter", "driver": "Casey Morgan",
                                     "phone": "+1 555 0102", "pickup": "Hotel, Nashville", "destination": "Hotel, Atlanta",
                                     "dep_time": "10:00", "dep_tz": "America/Chicago", "status": "confirmed"})
    ts.add_travel(tour_id, user_id, {"day_date": d(0), "mode": "air", "carrier": "Example Air", "number": "EX 123",
                                     "dep_loc": "JFK", "arr_loc": "BNA", "dep_time": "07:45", "dep_tz": "America/New_York",
                                     "arr_time": "09:30", "arr_tz": "America/Chicago", "confirmation": "EXMPL1",
                                     "status": "confirmed", "travelers": [people["Example Artist"], people["Jordan Lee"]]})
    for n, prop, city in [(0, "Example Hotel Downtown", "Nashville, TN"), (2, "Example Suites Midtown", "Atlanta, GA"),
                          (4, "Example Inn Chapel Hill", "Chapel Hill, NC"), (6, "Example Hotel U Street", "Washington, DC")]:
        lid = ts.add_lodging(tour_id, user_id, {"property": prop, "address": "100 Example St", "city": city,
                                                "checkin": d(n), "checkout": d(n + 1), "confirmation": "HTL%d" % n,
                                                "status": "confirmed", "wifi": "hotel-guest"})
        for i, (name, pid) in enumerate(people.items()):
            ts.set_room(tour_id, user_id, lid, {"person_id": pid, "room_number": str(400 + i)})
    for s in shows[:2]:
        ts.add_guest(tour_id, user_id, s["id"], {"name": "Taylor Example", "count": 2, "category": "Industry",
                                                 "company": "Example Records", "status": "approved", "requested_by": "Jordan Lee"})
        ts.add_guest(tour_id, user_id, s["id"], {"name": "Riley Example", "count": 1, "category": "Media",
                                                 "company": "Example Weekly", "status": "pending", "requested_by": "Alex Kim"})
    ts.add_product(tour_id, user_id, {"name": "Tour tee", "price": "35", "tour_inventory": "300", "low_stock_at": "40"})
    ts.add_product(tour_id, user_id, {"name": "Poster", "price": "20", "tour_inventory": "150", "low_stock_at": "20"})
    sl = ts.create_setlist(tour_id, user_id, "Main set", None)
    ts.replace_setlist_items(tour_id, user_id, sl, [{"title": "Opener (example)", "duration": "3:40"},
                                                    {"title": "Second song (example)", "duration": "4:10"},
                                                    {"title": "Closer (example)", "section": "encore"}])
    ts.log_change(tour_id, user_id, {"id": user_id, "name": "seed"}, "tour", tour_id, "Example Run",
                  "seeded", "", "example data", "info")
    return tour_id


if __name__ == "__main__":      # pragma: no cover
    if len(sys.argv) != 2:
        print("usage: python tour_seed.py <email>")
        sys.exit(1)
    store.init_db()
    ts.init_tour()
    user = store.get_user_by_email(sys.argv[1])
    if user is None:
        print("no such user")
        sys.exit(1)
    print(seed(user["id"]))
