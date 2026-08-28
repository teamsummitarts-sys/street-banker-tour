"""TOUR — data layer for the touring operating system.

Extends the existing Tour Hub rather than replacing it. `tour_shows` stays
the Show entity (every existing route, test, Money Queue feed and public
/showday page keeps working); this module adds a `tours` grouping above
it and the entities a tour actually runs on beneath it: days, schedule,
venues, advance items, travel, lodging and rooms, people, guests, VIP,
files, money, expenses, merch, marketing, content, set lists, share
links, imports, changes and acknowledgements.

Conventions, same as the rest of db.py:

  Ownership is a user_id column on every row — the TOUR OWNER's id, even
  on rows a member created. Membership and scopes live in tour_members
  and are enforced in tour_os.py, never here: this layer takes tour_id
  and trusts the caller resolved access.

  IDs are uuid4 hex, timestamps are UTC ISO seconds from db._now(),
  list-shaped fields are JSON text, anything aggregated is a real column.

  Times of day are stored as the venue's LOCAL "HH:MM" next to a date and
  an IANA timezone name on the show/day. Nothing here converts; the
  engine does, with zoneinfo, and says which zone it is showing.

  Nothing is seeded. Demo data lives behind seed_demo_tour() and is only
  ever called for demo accounts by the app, never at init.
"""
import json
import re
import uuid

from db import get_db, _now

# --- vocabularies -----------------------------------------------------------

TOUR_STATUSES = ["planning", "live", "wrapped", "cancelled"]

DAY_KINDS = ["show", "travel", "rehearsal", "off", "production", "promo",
             "press", "appearance", "private", "festival", "other"]

SCHEDULE_CATEGORIES = ["call", "travel", "load_in", "soundcheck", "doors",
                       "support", "set", "curfew", "press", "meeting", "meal",
                       "hotel", "vip", "meet_greet", "aftershow", "bus_call",
                       "other"]
SCHEDULE_PRECISION = ["exact", "approx", "tbd"]

# Who may see an entry. Enforced in tour_os.py against the viewer's
# scopes and person record; stored here as the author's intent.
VISIBILITY = ["all", "management", "private"]

ADVANCE_CATEGORIES = {
    "general": [("promoter", "Promoter"), ("buyer", "Buyer"),
                ("venue_contact", "Venue contact"), ("capacity", "Capacity"),
                ("ticketing", "Ticketing"), ("show_times", "Show times"),
                ("curfew", "Curfew")],
    "production": [("load_in", "Load-in"), ("dock", "Dock"), ("stage", "Stage"),
                   ("power", "Power"), ("sound", "Sound"), ("lighting", "Lighting"),
                   ("backline", "Backline"), ("labor", "Labor"), ("rigging", "Rigging"),
                   ("parking", "Parking"), ("bus_parking", "Bus parking")],
    "artist": [("dressing_rooms", "Dressing rooms"), ("showers", "Showers"),
               ("laundry", "Laundry"), ("wifi", "Wi-Fi"),
               ("hospitality", "Hospitality"), ("catering", "Catering"),
               # A buyout is a number per person, agreed in advance and
               # argued about at settlement if nobody wrote it down.
               ("buyout", "Buyout (per person)"),
               ("security", "Security")],
    # A VIP package is sold to the public before anyone has confirmed where
    # it happens or how those ticket holders get in early. Each of these is
    # a question somebody asks on the day if it is not answered here.
    "vip": [("vip_location", "VIP location"), ("vip_time", "VIP start time"),
            ("vip_capacity", "VIP capacity"), ("vip_entry", "VIP early-entry path"),
            ("vip_host", "VIP host / runner")],
    "travel": [("airport", "Airport"), ("driver", "Driver"), ("pickup", "Pickup"),
               ("hotel", "Hotel"), ("hotel_contact", "Hotel contact"),
               ("parking_travel", "Parking"),
               # The parts of a drive that cost money or time and are never
               # on the deal memo.
               ("fuel_stop", "Nearest fuel stop"), ("tolls", "Tolls on the route"),
               ("departure", "Planned departure")],
    "business": [("settlement_location", "Settlement location"),
                 ("settlement_contact", "Settlement contact"),
                 ("tax_paperwork", "Tax paperwork"),
                 ("payment_method", "Payment method"),
                 ("merch_percentage", "Merch percentage"),
                 ("ticket_comps", "Ticket comps"),
                 ("guest_allotment", "Guest-list allotment")],
}
ADVANCE_STATUSES = ["incomplete", "complete", "waiting", "na"]

TRAVEL_MODES = ["air", "ground", "bus", "rail"]
TRAVEL_STATUSES = ["planned", "confirmed", "changed", "cancelled"]
ROOM_KINDS = ["standard", "early_checkin", "late_checkout", "day_room",
              "bus_room", "crew_room"]

PEOPLE_CATEGORIES = ["Artist", "Management", "Tour Management", "Production",
                     "Band", "DJ", "Dancers", "Crew", "Security", "Drivers",
                     "Promoters", "Agents", "Venue", "Label", "Marketing",
                     "Photographer", "Videographer", "VIP", "Merch", "Guests",
                     "Other"]

GUEST_CATEGORIES = ["Personal", "Industry", "Label", "Media", "Influencer",
                    "Sponsor", "Promoter", "Artist", "VIP", "Other"]
GUEST_STATUSES = ["request", "pending", "approved", "denied", "checked_in",
                  "no_show"]

DEAL_TYPES = ["flat", "guarantee_vs_pct", "pct_only", "festival", "private",
              "custom"]
SETTLEMENT_STATUSES = ["open", "settled", "disputed"]
EXPENSE_CATEGORIES = ["production", "travel", "hotel", "ground", "catering",
                      "crew", "marketing", "merch", "fees", "other"]

FILE_CATEGORIES = ["contract", "rider", "stage_plot", "tech_pack", "insurance",
                   "venue_map", "itinerary", "invoice", "tax", "settlement",
                   "rooming", "production", "photo", "other"]

CONTENT_DEFAULTS = ["arrival", "city_establishing", "venue_exterior", "marquee",
                    "crowd_line", "backstage", "soundcheck", "artist_prep",
                    "merch", "vip", "opening_moment", "hero_performance",
                    "crowd_reaction", "behind_the_scenes", "post_show",
                    "city_message"]
CONTENT_STATUSES = ["planned", "captured", "uploaded", "selected", "edited",
                    "approved", "published"]

SEVERITIES = ["info", "important", "critical"]
CHANGE_SOURCES = ["manual", "import", "extract", "api"]

# Every scope below "band" is one SHOW handed to one person for one job.
# "band" is the exception: a band member needs the whole run — where they
# are on the 14th, what time the van leaves on the 15th — and needs it
# without the money, the room list or anyone's phone number.
SHARE_SCOPES = ["day_sheet", "photographer", "guest_checkin", "venue_guest_list",
                "driver", "setlist", "production", "vip_checkin", "rooming",
                "band"]
TOUR_WIDE_SCOPES = ("band",)

# Permission scopes. `admin` implies everything; owner always has admin.
SCOPES = ["view", "edit", "schedule", "travel", "hotel", "people", "advance",
          "production", "guests", "vip", "marketing", "content", "merch",
          "financials", "files", "admin"]

ROLE_PRESETS = {
    "tour_manager": SCOPES,
    "production": ["view", "edit", "schedule", "advance", "production", "files"],
    "artist": ["view", "schedule", "guests", "content", "files"],
    "crew": ["view", "schedule", "files"],
    "driver": ["view", "schedule", "travel"],
    "photographer": ["view", "schedule", "content", "files"],
    "management": ["view", "edit", "schedule", "people", "guests", "vip",
                   "marketing", "financials", "files"],
    "accountant": ["view", "financials", "files"],
    "viewer": ["view"],
}


def _new_id():
    return uuid.uuid4().hex


def _j(value):
    return json.dumps(value if value is not None else [])


def _load(text, default):
    try:
        value = json.loads(text or "null")
    except (ValueError, TypeError):
        return default
    return value if isinstance(value, type(default)) else default


# --- schema -----------------------------------------------------------------

def init_tour():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS tours (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                artist_name TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planning',
                start_date TEXT NOT NULL DEFAULT '',
                end_date TEXT NOT NULL DEFAULT '',
                home_tz TEXT NOT NULL DEFAULT 'UTC',
                currency TEXT NOT NULL DEFAULT 'USD',
                mode_override TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                settings TEXT NOT NULL DEFAULT '{}',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_members (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                email TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'crew',
                scopes TEXT NOT NULL DEFAULT '["view"]',
                status TEXT NOT NULL DEFAULT 'invited',
                invite_token TEXT UNIQUE,
                member_user_id TEXT,
                person_id TEXT,
                created TEXT NOT NULL,
                joined TEXT
            );
            CREATE TABLE IF NOT EXISTS tour_days (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'show',
                title TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                tz TEXT NOT NULL DEFAULT '',
                show_id TEXT,
                notes TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_show_ext (
                show_id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                venue_id TEXT,
                tz TEXT NOT NULL DEFAULT '',
                promoter TEXT NOT NULL DEFAULT '',
                capacity TEXT NOT NULL DEFAULT '',
                ticket_url TEXT NOT NULL DEFAULT '',
                ticket_status TEXT NOT NULL DEFAULT '',
                tickets_sold TEXT NOT NULL DEFAULT '',
                guest_allocation TEXT NOT NULL DEFAULT '',
                guest_cutoff TEXT NOT NULL DEFAULT '',
                deal_type TEXT NOT NULL DEFAULT 'flat',
                guarantee TEXT NOT NULL DEFAULT '',
                backend_pct TEXT NOT NULL DEFAULT '',
                bonus TEXT NOT NULL DEFAULT '',
                deposit_required TEXT NOT NULL DEFAULT '',
                deposit_received TEXT NOT NULL DEFAULT '',
                deposit_date TEXT NOT NULL DEFAULT '',
                ticket_gross TEXT NOT NULL DEFAULT '',
                adjusted_gross TEXT NOT NULL DEFAULT '',
                vip_gross TEXT NOT NULL DEFAULT '',
                merch_gross TEXT NOT NULL DEFAULT '',
                venue_merch_cut TEXT NOT NULL DEFAULT '',
                production_expenses TEXT NOT NULL DEFAULT '',
                local_expenses TEXT NOT NULL DEFAULT '',
                travel_allocation TEXT NOT NULL DEFAULT '',
                promoter_expenses TEXT NOT NULL DEFAULT '',
                settlement_amount TEXT NOT NULL DEFAULT '',
                collected TEXT NOT NULL DEFAULT '',
                settlement_status TEXT NOT NULL DEFAULT 'open',
                currency TEXT NOT NULL DEFAULT '',
                marketing TEXT NOT NULL DEFAULT '{}',
                readiness_config TEXT NOT NULL DEFAULT '[]',
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_schedule (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT,
                day_date TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                start_time TEXT NOT NULL DEFAULT '',
                end_time TEXT NOT NULL DEFAULT '',
                precision TEXT NOT NULL DEFAULT 'exact',
                location TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                contact_id TEXT,
                responsible TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'all',
                audience TEXT NOT NULL DEFAULT '[]',
                confirmed INTEGER NOT NULL DEFAULT 0,
                reminder_minutes INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_venues (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                region TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                lat TEXT NOT NULL DEFAULT '',
                lng TEXT NOT NULL DEFAULT '',
                tz TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                capacity TEXT NOT NULL DEFAULT '',
                venue_type TEXT NOT NULL DEFAULT '',
                loading TEXT NOT NULL DEFAULT '',
                parking TEXT NOT NULL DEFAULT '',
                bus_parking TEXT NOT NULL DEFAULT '',
                stage TEXT NOT NULL DEFAULT '',
                production_notes TEXT NOT NULL DEFAULT '',
                backstage TEXT NOT NULL DEFAULT '',
                dressing_rooms TEXT NOT NULL DEFAULT '',
                showers TEXT NOT NULL DEFAULT '',
                catering TEXT NOT NULL DEFAULT '',
                wifi TEXT NOT NULL DEFAULT '',
                settlement_location TEXT NOT NULL DEFAULT '',
                merch_location TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                contacts TEXT NOT NULL DEFAULT '[]',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_advance (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT NOT NULL,
                category TEXT NOT NULL,
                item_key TEXT NOT NULL,
                label TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'incomplete',
                value TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT '',
                due_date TEXT NOT NULL DEFAULT '',
                comments TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL,
                UNIQUE(show_id, item_key)
            );
            CREATE TABLE IF NOT EXISTS tour_travel (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT,
                day_date TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'ground',
                carrier TEXT NOT NULL DEFAULT '',
                number TEXT NOT NULL DEFAULT '',
                dep_loc TEXT NOT NULL DEFAULT '',
                arr_loc TEXT NOT NULL DEFAULT '',
                dep_time TEXT NOT NULL DEFAULT '',
                arr_time TEXT NOT NULL DEFAULT '',
                dep_tz TEXT NOT NULL DEFAULT '',
                arr_tz TEXT NOT NULL DEFAULT '',
                confirmation TEXT NOT NULL DEFAULT '',
                seat TEXT NOT NULL DEFAULT '',
                terminal TEXT NOT NULL DEFAULT '',
                driver TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                vehicle TEXT NOT NULL DEFAULT '',
                company TEXT NOT NULL DEFAULT '',
                pickup TEXT NOT NULL DEFAULT '',
                destination TEXT NOT NULL DEFAULT '',
                parking TEXT NOT NULL DEFAULT '',
                sleepers TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                travelers TEXT NOT NULL DEFAULT '["all"]',
                visibility TEXT NOT NULL DEFAULT 'all',
                status TEXT NOT NULL DEFAULT 'planned',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_lodging (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT,
                property TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                checkin TEXT NOT NULL DEFAULT '',
                checkout TEXT NOT NULL DEFAULT '',
                confirmation TEXT NOT NULL DEFAULT '',
                room_type TEXT NOT NULL DEFAULT '',
                reservation_name TEXT NOT NULL DEFAULT '',
                payment TEXT NOT NULL DEFAULT '',
                contact TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                parking TEXT NOT NULL DEFAULT '',
                wifi TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'all',
                status TEXT NOT NULL DEFAULT 'planned',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_rooms (
                id TEXT PRIMARY KEY,
                lodging_id TEXT NOT NULL,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                person_id TEXT,
                guest_name TEXT NOT NULL DEFAULT '',
                room_number TEXT NOT NULL DEFAULT '',
                room_kind TEXT NOT NULL DEFAULT 'standard',
                notes TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_people (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Crew',
                company TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                phone_private INTEGER NOT NULL DEFAULT 1,
                photo TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                emergency TEXT NOT NULL DEFAULT '',
                linked_contact_id TEXT,
                linked_user_id TEXT,
                shows TEXT NOT NULL DEFAULT '[]',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_guests (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT NOT NULL,
                name TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                company TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'Personal',
                requested_by TEXT NOT NULL DEFAULT '',
                approved_by TEXT NOT NULL DEFAULT '',
                ticket_type TEXT NOT NULL DEFAULT '',
                credentials TEXT NOT NULL DEFAULT '',
                backstage INTEGER NOT NULL DEFAULT 0,
                meet_greet INTEGER NOT NULL DEFAULT 0,
                aftershow INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                checked_in_at TEXT NOT NULL DEFAULT '',
                linked_contact_id TEXT,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_vip (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT NOT NULL,
                package TEXT NOT NULL,
                price TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 1,
                purchaser TEXT NOT NULL DEFAULT '',
                guest TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                meet_greet INTEGER NOT NULL DEFAULT 0,
                early_entry INTEGER NOT NULL DEFAULT 0,
                merch INTEGER NOT NULL DEFAULT 0,
                photo INTEGER NOT NULL DEFAULT 0,
                credentials TEXT NOT NULL DEFAULT '',
                schedule_time TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'sold',
                checked_in_at TEXT NOT NULL DEFAULT '',
                fulfilled INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_files (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                entity_type TEXT NOT NULL DEFAULT 'tour',
                entity_id TEXT NOT NULL DEFAULT '',
                file_name TEXT NOT NULL,
                path TEXT NOT NULL,
                file_type TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'other',
                visibility TEXT NOT NULL DEFAULT 'all',
                uploaded_by TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL DEFAULT 1,
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_expenses (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT,
                vendor TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'other',
                amount TEXT NOT NULL DEFAULT '',
                tax TEXT NOT NULL DEFAULT '',
                currency TEXT NOT NULL DEFAULT '',
                spend_date TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                receipt_file_id TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_merch_products (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                sku TEXT NOT NULL DEFAULT '',
                price TEXT NOT NULL DEFAULT '',
                tour_inventory TEXT NOT NULL DEFAULT '',
                low_stock_at TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_merch_counts (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                opening TEXT NOT NULL DEFAULT '',
                closing TEXT NOT NULL DEFAULT '',
                sold TEXT NOT NULL DEFAULT '',
                gross TEXT NOT NULL DEFAULT '',
                venue_pct TEXT NOT NULL DEFAULT '',
                taxes TEXT NOT NULL DEFAULT '',
                fees TEXT NOT NULL DEFAULT '',
                settled INTEGER NOT NULL DEFAULT 0,
                updated TEXT NOT NULL,
                UNIQUE(show_id, product_id)
            );
            CREATE TABLE IF NOT EXISTS tour_content (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT NOT NULL,
                item TEXT NOT NULL,
                assignee TEXT NOT NULL DEFAULT '',
                due_time TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planned',
                file_id TEXT,
                notes TEXT NOT NULL DEFAULT '',
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_setlists (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT,
                name TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_setlist_items (
                id TEXT PRIMARY KEY,
                setlist_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL,
                os_track_id TEXT,
                duration TEXT NOT NULL DEFAULT '',
                section TEXT NOT NULL DEFAULT 'main',
                notes TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS tour_changes (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                actor_id TEXT NOT NULL DEFAULT '',
                actor_name TEXT NOT NULL DEFAULT '',
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL DEFAULT '',
                entity_label TEXT NOT NULL DEFAULT '',
                field TEXT NOT NULL DEFAULT '',
                before TEXT NOT NULL DEFAULT '',
                after TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL DEFAULT 'info',
                source TEXT NOT NULL DEFAULT 'manual',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_acks (
                id TEXT PRIMARY KEY,
                change_id TEXT NOT NULL,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                viewer_id TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'delivered',
                at TEXT NOT NULL,
                UNIQUE(change_id, viewer_id)
            );
            CREATE TABLE IF NOT EXISTS tour_share_links (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                scope TEXT NOT NULL,
                show_id TEXT,
                token TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL DEFAULT '',
                expires TEXT NOT NULL DEFAULT '',
                revoked INTEGER NOT NULL DEFAULT 0,
                access_count INTEGER NOT NULL DEFAULT 0,
                last_access TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_imports (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                source TEXT NOT NULL,
                filename TEXT NOT NULL DEFAULT '',
                raw TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '{}',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tour_fan_captures (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                consent_text TEXT NOT NULL DEFAULT '',
                consented INTEGER NOT NULL DEFAULT 0,
                city TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tour_members_tour ON tour_members(tour_id);
            CREATE INDEX IF NOT EXISTS idx_tour_members_user ON tour_members(member_user_id);
            CREATE INDEX IF NOT EXISTS idx_tour_days_tour ON tour_days(tour_id, date);
            CREATE INDEX IF NOT EXISTS idx_tour_schedule_tour ON tour_schedule(tour_id, day_date);
            CREATE INDEX IF NOT EXISTS idx_tour_schedule_show ON tour_schedule(show_id);
            CREATE INDEX IF NOT EXISTS idx_tour_advance_show ON tour_advance(show_id);
            CREATE INDEX IF NOT EXISTS idx_tour_travel_tour ON tour_travel(tour_id, day_date);
            CREATE INDEX IF NOT EXISTS idx_tour_lodging_tour ON tour_lodging(tour_id, checkin);
            CREATE INDEX IF NOT EXISTS idx_tour_people_tour ON tour_people(tour_id);
            CREATE INDEX IF NOT EXISTS idx_tour_guests_show ON tour_guests(show_id);
            CREATE INDEX IF NOT EXISTS idx_tour_files_tour ON tour_files(tour_id, entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_tour_changes_tour ON tour_changes(tour_id, created);
            CREATE INDEX IF NOT EXISTS idx_tour_venues_user ON tour_venues(user_id, name);
        """)
        # The Show entity gains a tour_id and a timezone; everything else
        # about a show that TOUR adds lives in tour_show_ext so the
        # original table and its callers are untouched.
        for col in ("tour_id TEXT", "tz TEXT"):
            try:
                db.execute("ALTER TABLE tour_shows ADD COLUMN %s" % col)
            except Exception:
                pass
        # Added after the first release; ALTER is the migration.
        for col in ("support TEXT NOT NULL DEFAULT ''",
                    "source_note TEXT NOT NULL DEFAULT ''",
                    "vip_ticket_url TEXT NOT NULL DEFAULT ''",
                    "merch_rate TEXT NOT NULL DEFAULT ''",
                    "fee_note TEXT NOT NULL DEFAULT ''"):
            try:
                db.execute("ALTER TABLE tour_show_ext ADD COLUMN %s" % col)
            except Exception:
                pass
        for col in ("fuel_mpg TEXT NOT NULL DEFAULT ''",
                    "fuel_price TEXT NOT NULL DEFAULT ''",
                    "fuel_reserve_pct TEXT NOT NULL DEFAULT ''",
                    "stated_miles TEXT NOT NULL DEFAULT ''",
                    "vehicle TEXT NOT NULL DEFAULT ''"):
            try:
                db.execute("ALTER TABLE tours ADD COLUMN %s" % col)
            except Exception:
                pass
        for col in ("miles TEXT NOT NULL DEFAULT ''", "tolls TEXT NOT NULL DEFAULT ''"):
            try:
                db.execute("ALTER TABLE tour_travel ADD COLUMN %s" % col)
            except Exception:
                pass
        db.execute("CREATE INDEX IF NOT EXISTS idx_tour_shows_tour ON tour_shows(tour_id)")

    # The bill and its per-act line checks. Called from here rather than
    # given its own init hook, so a tour database is never half-migrated.
    init_lineup()


# --- tours ------------------------------------------------------------------

def create_tour(user_id, fields):
    tour_id = _new_id()
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO tours (id, user_id, name, artist_name, status, start_date, "
            "end_date, home_tz, currency, notes, created, updated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (tour_id, user_id, (fields.get("name") or "Untitled tour").strip()[:120],
             (fields.get("artist_name") or "").strip()[:120],
             fields.get("status") if fields.get("status") in TOUR_STATUSES else "planning",
             (fields.get("start_date") or "")[:10], (fields.get("end_date") or "")[:10],
             (fields.get("home_tz") or "UTC")[:60],
             (fields.get("currency") or "USD").upper()[:3],
             (fields.get("notes") or "")[:2000], now, now))
    return tour_id


def update_tour(tour_id, fields):
    tour = get_tour(tour_id)
    if tour is None:
        return False
    with get_db() as db:
        db.execute(
            "UPDATE tours SET name=?, artist_name=?, status=?, start_date=?, end_date=?, "
            "home_tz=?, currency=?, mode_override=?, notes=?, updated=? WHERE id=?",
            ((fields.get("name") or tour["name"]).strip()[:120],
             (fields.get("artist_name") if "artist_name" in fields else tour["artist_name"]).strip()[:120],
             fields.get("status") if fields.get("status") in TOUR_STATUSES else tour["status"],
             (fields.get("start_date") if "start_date" in fields else tour["start_date"])[:10],
             (fields.get("end_date") if "end_date" in fields else tour["end_date"])[:10],
             (fields.get("home_tz") or tour["home_tz"])[:60],
             (fields.get("currency") or tour["currency"]).upper()[:3],
             (fields.get("mode_override") if "mode_override" in fields else tour["mode_override"])[:10],
             (fields.get("notes") if "notes" in fields else tour["notes"])[:2000],
             _now(), tour_id))
    return True


FUEL_FIELDS = ("fuel_mpg", "fuel_price", "fuel_reserve_pct", "stated_miles", "vehicle")


def update_fuel(tour_id, fields):
    """The planning assumptions behind a fuel estimate, stored as typed.

    Kept apart from update_tour because these are ASSUMPTIONS, not facts
    about the tour: a tour manager changes the price of a gallon without
    touching the tour, and the number the app shows must always be
    traceable to the figures somebody entered.
    """
    if get_tour(tour_id) is None:
        return False
    sets, params = [], []
    for key in FUEL_FIELDS:
        if key in fields:
            sets.append("%s = ?" % key)
            params.append(str(fields.get(key) or "").strip()[:40])
    if not sets:
        return False
    params.append(tour_id)
    with get_db() as db:
        db.execute("UPDATE tours SET %s WHERE id = ?" % ", ".join(sets), params)
    return True


def get_tour(tour_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tours WHERE id = ?", (tour_id,)).fetchone()
    return dict(row) if row else None


def list_tours(user_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM tours WHERE user_id = ? "
                          "ORDER BY start_date DESC, created DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_tour(tour_id):
    tables = ["tour_members", "tour_days", "tour_schedule", "tour_advance",
              "tour_travel", "tour_lodging", "tour_rooms", "tour_people",
              "tour_guests", "tour_vip", "tour_files", "tour_expenses",
              "tour_merch_products", "tour_merch_counts", "tour_content",
              "tour_setlists", "tour_changes", "tour_acks", "tour_share_links",
              "tour_imports", "tour_fan_captures", "tour_show_ext"]
    with get_db() as db:
        for t in tables:
            db.execute("DELETE FROM %s WHERE tour_id = ?" % t, (tour_id,))
        db.execute("DELETE FROM tour_setlist_items WHERE setlist_id IN "
                   "(SELECT id FROM tour_setlists WHERE tour_id = ?)", (tour_id,))
        db.execute("UPDATE tour_shows SET tour_id = NULL WHERE tour_id = ?", (tour_id,))
        db.execute("DELETE FROM tours WHERE id = ?", (tour_id,))
    return True


# --- members ----------------------------------------------------------------

def add_member(tour_id, owner_id, email, name, role, scopes=None):
    """Invite by email. Returns the row (with invite_token) or None if that
    email is already on the tour."""
    email = (email or "").strip().lower()
    if not email:
        return None
    if get_member_by_email(tour_id, email):
        return None
    scopes = list(scopes) if scopes is not None else list(ROLE_PRESETS.get(role, ["view"]))
    scopes = [s for s in scopes if s in SCOPES] or ["view"]
    member_id = _new_id()
    token = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_members (id, tour_id, user_id, email, name, role, scopes, "
            "status, invite_token, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (member_id, tour_id, owner_id, email, (name or "")[:120], (role or "crew")[:40],
             _j(scopes), "invited", token, _now()))
    return get_member(tour_id, member_id)


def _member_row(row):
    if row is None:
        return None
    m = dict(row)
    m["scopes"] = _load(m.get("scopes"), [])
    return m


def get_member(tour_id, member_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_members WHERE id = ? AND tour_id = ?",
                         (member_id, tour_id)).fetchone()
    return _member_row(row)


def get_member_by_email(tour_id, email):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_members WHERE tour_id = ? AND lower(email) = ?",
                         (tour_id, (email or "").strip().lower())).fetchone()
    return _member_row(row)


def get_membership(tour_id, member_user_id):
    """The ACTIVE membership of a signed-in user on a tour, or None."""
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_members WHERE tour_id = ? AND member_user_id = ? "
                         "AND status = 'active'", (tour_id, member_user_id)).fetchone()
    return _member_row(row)


def get_invite(token):
    with get_db() as db:
        row = db.execute("SELECT m.*, t.name AS tour_name, t.artist_name FROM tour_members m "
                         "JOIN tours t ON t.id = m.tour_id WHERE m.invite_token = ? "
                         "AND m.status = 'invited'", (token,)).fetchone()
    return _member_row(row)


def accept_invite(token, member_user_id):
    with get_db() as db:
        cur = db.execute("UPDATE tour_members SET status='active', member_user_id=?, "
                         "joined=?, invite_token=NULL WHERE invite_token=? AND status='invited'",
                         (member_user_id, _now(), token))
    return cur.rowcount > 0


def list_members(tour_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM tour_members WHERE tour_id = ? AND status != 'removed' "
                          "ORDER BY created", (tour_id,)).fetchall()
    return [_member_row(r) for r in rows]


def set_member_scopes(tour_id, member_id, role, scopes):
    scopes = [s for s in (scopes or []) if s in SCOPES] or ["view"]
    with get_db() as db:
        db.execute("UPDATE tour_members SET role=?, scopes=? WHERE id=? AND tour_id=?",
                   ((role or "crew")[:40], _j(scopes), member_id, tour_id))
    return True


def link_member_person(tour_id, member_id, person_id):
    with get_db() as db:
        db.execute("UPDATE tour_members SET person_id=? WHERE id=? AND tour_id=?",
                   (person_id, member_id, tour_id))


def remove_member(tour_id, member_id):
    with get_db() as db:
        db.execute("UPDATE tour_members SET status='removed', invite_token=NULL "
                   "WHERE id=? AND tour_id=?", (member_id, tour_id))
    return True


def tours_shared_with(member_user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT t.*, m.role AS my_role, m.scopes AS my_scopes FROM tour_members m "
            "JOIN tours t ON t.id = m.tour_id WHERE m.member_user_id = ? AND m.status='active' "
            "ORDER BY t.start_date DESC", (member_user_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["my_scopes"] = _load(d.get("my_scopes"), [])
        out.append(d)
    return out


# --- days & shows -----------------------------------------------------------

def add_day(tour_id, user_id, date, kind="show", title="", city="", tz="",
            show_id=None, notes=""):
    day_id = _new_id()
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_days (id, tour_id, user_id, date, kind, title, city, tz, "
            "show_id, notes, created) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (day_id, tour_id, user_id, (date or "")[:10],
             kind if kind in DAY_KINDS else "other", (title or "")[:160],
             (city or "")[:80], (tz or "")[:60], show_id, (notes or "")[:2000], _now()))
    return day_id


def list_days(tour_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM tour_days WHERE tour_id = ? ORDER BY date, created",
                          (tour_id,)).fetchall()
    return [dict(r) for r in rows]


def get_day(tour_id, day_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_days WHERE id=? AND tour_id=?",
                         (day_id, tour_id)).fetchone()
    return dict(row) if row else None


def update_day(tour_id, day_id, fields):
    day = get_day(tour_id, day_id)
    if not day:
        return False
    with get_db() as db:
        db.execute("UPDATE tour_days SET date=?, kind=?, title=?, city=?, tz=?, notes=? "
                   "WHERE id=? AND tour_id=?",
                   ((fields.get("date") or day["date"])[:10],
                    fields.get("kind") if fields.get("kind") in DAY_KINDS else day["kind"],
                    (fields.get("title") if "title" in fields else day["title"])[:160],
                    (fields.get("city") if "city" in fields else day["city"])[:80],
                    (fields.get("tz") if "tz" in fields else day["tz"])[:60],
                    (fields.get("notes") if "notes" in fields else day["notes"])[:2000],
                    day_id, tour_id))
    return True


def delete_day(tour_id, day_id):
    with get_db() as db:
        db.execute("DELETE FROM tour_days WHERE id=? AND tour_id=?", (day_id, tour_id))


def attach_show(tour_id, show_id, tz=""):
    """Put an existing tour_shows row onto this tour, and make sure a day
    and an ext row exist for it."""
    with get_db() as db:
        db.execute("UPDATE tour_shows SET tour_id = ?, tz = COALESCE(NULLIF(?, ''), tz) "
                   "WHERE id = ?", (tour_id, tz, show_id))
        row = db.execute("SELECT * FROM tour_shows WHERE id = ?", (show_id,)).fetchone()
        if row is None:
            return False
        show = dict(row)
        day = db.execute("SELECT id FROM tour_days WHERE tour_id=? AND show_id=?",
                         (tour_id, show_id)).fetchone()
        if day is None:
            db.execute(
                "INSERT INTO tour_days (id, tour_id, user_id, date, kind, title, city, tz, "
                "show_id, notes, created) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (_new_id(), tour_id, show["user_id"], show["date"], "show", show["venue"],
                 show["city"], tz or "", show_id, "", _now()))
        ext = db.execute("SELECT show_id FROM tour_show_ext WHERE show_id=?",
                         (show_id,)).fetchone()
        if ext is None:
            db.execute("INSERT INTO tour_show_ext (show_id, tour_id, user_id, tz, updated) "
                       "VALUES (?,?,?,?,?)", (show_id, tour_id, show["user_id"], tz or "", _now()))
    return True


def detach_show(tour_id, show_id):
    with get_db() as db:
        db.execute("UPDATE tour_shows SET tour_id = NULL WHERE id = ? AND tour_id = ?",
                   (show_id, tour_id))
        db.execute("DELETE FROM tour_days WHERE tour_id=? AND show_id=?", (tour_id, show_id))


def list_shows(tour_id):
    """Shows on this tour with their ext fields merged, ordered by date."""
    with get_db() as db:
        rows = db.execute(
            "SELECT s.*, e.venue_id, e.tz AS ext_tz, e.promoter, e.capacity, e.ticket_url, "
            # Named one by one rather than e.*, so a column has to be added
            # here on purpose. That is a good rule and it has a cost: a
            # field written by update_show_ext but missed here reads back
            # as None forever, which is how `support` first behaved.
            "e.support, e.source_note, e.vip_ticket_url, e.merch_rate, e.fee_note, "
            "e.ticket_status, e.tickets_sold, e.guest_allocation, e.guest_cutoff, "
            "e.deal_type, e.guarantee, e.backend_pct, e.bonus, e.deposit_required, "
            "e.deposit_received, e.deposit_date, e.ticket_gross, e.adjusted_gross, "
            "e.vip_gross, e.merch_gross, e.venue_merch_cut, e.production_expenses, "
            "e.local_expenses, e.travel_allocation, e.promoter_expenses, "
            "e.settlement_amount, e.collected, e.settlement_status, e.currency, "
            "e.marketing, e.readiness_config "
            "FROM tour_shows s LEFT JOIN tour_show_ext e ON e.show_id = s.id "
            "WHERE s.tour_id = ? ORDER BY s.date, s.created", (tour_id,)).fetchall()
    out = []
    for i, r in enumerate(rows, start=1):
        d = dict(r)
        d["advance"] = _load(d.get("advance"), {}) if isinstance(d.get("advance"), str) else (d.get("advance") or {})
        d["settlement"] = _load(d.get("settlement"), {}) if isinstance(d.get("settlement"), str) else (d.get("settlement") or {})
        d["marketing"] = _load(d.get("marketing"), {})
        d["readiness_config"] = _load(d.get("readiness_config"), [])
        d["show_number"] = i
        d["tz"] = d.get("tz") or d.get("ext_tz") or ""
        out.append(d)
    return out


def get_show(tour_id, show_id):
    for s in list_shows(tour_id):
        if s["id"] == show_id:
            return s
    return None


def show_tour_id(show_id):
    with get_db() as db:
        row = db.execute("SELECT tour_id FROM tour_shows WHERE id=?", (show_id,)).fetchone()
    return row["tour_id"] if row else None


# `support` is the bill for this date, comma separated and in running
# order. It varies show to show on a package tour, which is exactly why it
# cannot live on the tour.  `source_note` records where a value came from
# when two sheets disagreed, so nobody has to re-litigate it later.
EXT_FIELDS = ["venue_id", "promoter", "capacity", "ticket_url", "ticket_status",
              "support", "source_note", "vip_ticket_url", "merch_rate", "fee_note",
              "tickets_sold", "guest_allocation", "guest_cutoff", "deal_type",
              "guarantee", "backend_pct", "bonus", "deposit_required",
              "deposit_received", "deposit_date", "ticket_gross", "adjusted_gross",
              "vip_gross", "merch_gross", "venue_merch_cut", "production_expenses",
              "local_expenses", "travel_allocation", "promoter_expenses",
              "settlement_amount", "collected", "settlement_status", "currency"]

MONEY_FIELDS = ["deal_type", "guarantee", "backend_pct", "bonus", "deposit_required",
                "deposit_received", "deposit_date", "ticket_gross", "adjusted_gross",
                "vip_gross", "merch_gross", "venue_merch_cut", "production_expenses",
                "local_expenses", "travel_allocation", "promoter_expenses",
                "settlement_amount", "collected", "settlement_status", "currency"]


def update_show_ext(tour_id, show_id, fields):
    """Update only the keys present in `fields`. Returns {field: (before,
    after)} for everything that actually changed, so the caller can log."""
    current = get_show(tour_id, show_id)
    if current is None:
        return None
    changed = {}
    sets, params = [], []
    for key in EXT_FIELDS:
        if key not in fields:
            continue
        new = (fields.get(key) or "").strip()[:300]
        if key == "deal_type" and new and new not in DEAL_TYPES:
            new = current.get("deal_type") or "flat"
        if key == "settlement_status" and new and new not in SETTLEMENT_STATUSES:
            new = current.get("settlement_status") or "open"
        if key == "ticket_url" and new and not re.match(r"^https?://", new, re.I):
            new = ""           # rendered as an href: only web links, never javascript:
        old = current.get(key) or ""
        if str(old) != new:
            changed[key] = (str(old), new)
        sets.append("%s = ?" % key); params.append(new)
    if "marketing" in fields and isinstance(fields["marketing"], dict):
        sets.append("marketing = ?"); params.append(json.dumps(fields["marketing"]))
    if "readiness_config" in fields and isinstance(fields["readiness_config"], list):
        sets.append("readiness_config = ?"); params.append(json.dumps(fields["readiness_config"]))
    if "tz" in fields:
        sets.append("tz = ?"); params.append((fields.get("tz") or "")[:60])
    if not sets:
        return changed
    sets.append("updated = ?"); params.append(_now())
    params += [show_id, tour_id]
    with get_db() as db:
        db.execute("UPDATE tour_show_ext SET %s WHERE show_id = ? AND tour_id = ?"
                   % ", ".join(sets), params)
        if "tz" in fields:
            db.execute("UPDATE tour_shows SET tz=? WHERE id=?",
                       ((fields.get("tz") or "")[:60], show_id))
    return changed


# --- schedule ---------------------------------------------------------------

def add_schedule_item(tour_id, user_id, fields):
    item_id = _new_id()
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_schedule (id, tour_id, user_id, show_id, day_date, title, "
            "category, start_time, end_time, precision, location, address, notes, "
            "contact_id, responsible, visibility, audience, confirmed, reminder_minutes, "
            "created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (item_id, tour_id, user_id, fields.get("show_id") or None,
             (fields.get("day_date") or "")[:10], (fields.get("title") or "Untitled")[:160],
             fields.get("category") if fields.get("category") in SCHEDULE_CATEGORIES else "other",
             (fields.get("start_time") or "")[:5], (fields.get("end_time") or "")[:5],
             fields.get("precision") if fields.get("precision") in SCHEDULE_PRECISION else "exact",
             (fields.get("location") or "")[:200], (fields.get("address") or "")[:300],
             (fields.get("notes") or "")[:2000], fields.get("contact_id") or None,
             (fields.get("responsible") or "")[:120],
             fields.get("visibility") if fields.get("visibility") in VISIBILITY else "all",
             _j(fields.get("audience") or []), 1 if fields.get("confirmed") else 0,
             int(fields.get("reminder_minutes") or 0), now, now))
    return item_id


def update_schedule_item(tour_id, item_id, fields):
    cur = get_schedule_item(tour_id, item_id)
    if cur is None:
        return None
    changed = {}
    merged = dict(cur)
    for key in ("title", "category", "start_time", "end_time", "precision", "location",
                "address", "notes", "responsible", "visibility", "day_date", "show_id",
                "contact_id"):
        if key in fields:
            val = fields.get(key)
            if key in ("category",) and val not in SCHEDULE_CATEGORIES:
                continue
            if key == "precision" and val not in SCHEDULE_PRECISION:
                continue
            if key == "visibility" and val not in VISIBILITY:
                continue
            val = (val or "") if key not in ("show_id", "contact_id") else (val or None)
            if str(cur.get(key) or "") != str(val or ""):
                changed[key] = (str(cur.get(key) or ""), str(val or ""))
            merged[key] = val
    if "confirmed" in fields:
        new_c = 1 if fields.get("confirmed") else 0
        if new_c != (cur.get("confirmed") or 0):
            changed["confirmed"] = (str(cur.get("confirmed") or 0), str(new_c))
        merged["confirmed"] = new_c
    if "audience" in fields:
        merged["audience"] = fields.get("audience") or []
    with get_db() as db:
        db.execute(
            "UPDATE tour_schedule SET show_id=?, day_date=?, title=?, category=?, start_time=?, "
            "end_time=?, precision=?, location=?, address=?, notes=?, contact_id=?, "
            "responsible=?, visibility=?, audience=?, confirmed=?, updated=? "
            "WHERE id=? AND tour_id=?",
            (merged.get("show_id"), (merged.get("day_date") or "")[:10],
             (merged.get("title") or "Untitled")[:160], merged.get("category") or "other",
             (merged.get("start_time") or "")[:5], (merged.get("end_time") or "")[:5],
             merged.get("precision") or "exact", (merged.get("location") or "")[:200],
             (merged.get("address") or "")[:300], (merged.get("notes") or "")[:2000],
             merged.get("contact_id"), (merged.get("responsible") or "")[:120],
             merged.get("visibility") or "all",
             _j(merged.get("audience") if isinstance(merged.get("audience"), list) else []),
             merged.get("confirmed") or 0, _now(), item_id, tour_id))
    return changed


def get_schedule_item(tour_id, item_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_schedule WHERE id=? AND tour_id=?",
                         (item_id, tour_id)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["audience"] = _load(d.get("audience"), [])
    return d


def list_schedule(tour_id, day_date=None, show_id=None):
    q = "SELECT * FROM tour_schedule WHERE tour_id = ?"
    params = [tour_id]
    if day_date:
        q += " AND day_date = ?"; params.append(day_date)
    if show_id:
        q += " AND show_id = ?"; params.append(show_id)
    q += " ORDER BY day_date, CASE WHEN start_time = '' THEN 1 ELSE 0 END, start_time, created"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["audience"] = _load(d.get("audience"), [])
        out.append(d)
    return out


def delete_schedule_item(tour_id, item_id):
    with get_db() as db:
        db.execute("DELETE FROM tour_schedule WHERE id=? AND tour_id=?", (item_id, tour_id))


STANDARD_DAY = [
    ("load_in", "Load-in", "15:00"), ("soundcheck", "Soundcheck", "17:00"),
    ("doors", "Doors", "19:00"), ("support", "Support", "20:00"),
    ("set", "Artist set", "21:15"), ("curfew", "Curfew", "23:00"),
    ("bus_call", "Bus call", "23:59"),
]


def copy_standard_day(tour_id, user_id, show, template=None):
    """Stamp the standard show-day template onto a show, skipping anything
    already there for that category. Returns the number added."""
    existing = {s["category"] for s in list_schedule(tour_id, show_id=show["id"])}
    added = 0
    for category, title, start in (template or STANDARD_DAY):
        if category in existing:
            continue
        add_schedule_item(tour_id, user_id, {
            "show_id": show["id"], "day_date": show["date"], "title": title,
            "category": category, "start_time": start, "precision": "approx",
            "location": show.get("venue") or ""})
        added += 1
    return added


# --- venues -----------------------------------------------------------------

VENUE_FIELDS = ["name", "address", "city", "region", "country", "lat", "lng", "tz",
                "phone", "website", "capacity", "venue_type", "loading", "parking",
                "bus_parking", "stage", "production_notes", "backstage",
                "dressing_rooms", "showers", "catering", "wifi",
                "settlement_location", "merch_location", "notes"]


def add_venue(user_id, fields):
    venue_id = _new_id()
    now = _now()
    vals = [(fields.get(k) or "").strip()[:600] for k in VENUE_FIELDS]
    if not vals[0]:
        return None
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_venues (id, user_id, %s, contacts, created, updated) "
            "VALUES (?,?,%s,?,?,?)" % (", ".join(VENUE_FIELDS), ",".join("?" * len(VENUE_FIELDS))),
            [venue_id, user_id] + vals + [_j(fields.get("contacts") or []), now, now])
    return venue_id


def update_venue(user_id, venue_id, fields):
    cur = get_venue(user_id, venue_id)
    if not cur:
        return None
    changed = {}
    vals = []
    for k in VENUE_FIELDS:
        new = (fields.get(k) if k in fields else cur.get(k)) or ""
        new = str(new).strip()[:600]
        if str(cur.get(k) or "") != new:
            changed[k] = (str(cur.get(k) or ""), new)
        vals.append(new)
    with get_db() as db:
        db.execute("UPDATE tour_venues SET %s, updated=? WHERE id=? AND user_id=?"
                   % ", ".join("%s=?" % k for k in VENUE_FIELDS),
                   vals + [_now(), venue_id, user_id])
    return changed


def get_venue(user_id, venue_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_venues WHERE id=? AND user_id=?",
                         (venue_id, user_id)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["contacts"] = _load(d.get("contacts"), [])
    return d


def list_venues(user_id, search=""):
    q = "SELECT * FROM tour_venues WHERE user_id = ?"
    params = [user_id]
    if search:
        q += " AND (name LIKE ? OR city LIKE ?)"
        params += ["%%%s%%" % search, "%%%s%%" % search]
    q += " ORDER BY name"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["contacts"] = _load(d.get("contacts"), [])
        out.append(d)
    return out


def find_venue_by_name(user_id, name, city=""):
    name = (name or "").strip().lower()
    for v in list_venues(user_id):
        if v["name"].strip().lower() == name and (not city or (v["city"] or "").lower() == city.lower()):
            return v
    return None


# --- advance ----------------------------------------------------------------

def ensure_advance_items(tour_id, user_id, show_id):
    """Every advance row for a show exists from the first visit, status
    incomplete. Idempotent."""
    with get_db() as db:
        have = {r["item_key"] for r in db.execute(
            "SELECT item_key FROM tour_advance WHERE show_id = ?", (show_id,))}
        now = _now()
        for category, items in ADVANCE_CATEGORIES.items():
            for key, label in items:
                if key in have:
                    continue
                db.execute(
                    "INSERT OR IGNORE INTO tour_advance (id, tour_id, user_id, show_id, "
                    "category, item_key, label, status, updated) VALUES (?,?,?,?,?,?,?,?,?)",
                    (_new_id(), tour_id, user_id, show_id, category, key, label,
                     "incomplete", now))


def list_advance(tour_id, show_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM tour_advance WHERE tour_id=? AND show_id=?",
                          (tour_id, show_id)).fetchall()
    by_key = {r["item_key"]: dict(r) for r in rows}
    ordered = []
    for category, items in ADVANCE_CATEGORIES.items():
        for key, label in items:
            row = by_key.get(key)
            if row:
                ordered.append(row)
    return ordered


def set_advance_item(tour_id, show_id, item_key, fields):
    cur = None
    for row in list_advance(tour_id, show_id):
        if row["item_key"] == item_key:
            cur = row
    if cur is None:
        return None
    status = fields.get("status") if fields.get("status") in ADVANCE_STATUSES else cur["status"]
    value = (fields.get("value") if "value" in fields else cur["value"]) or ""
    changed = {}
    if status != cur["status"]:
        changed["status"] = (cur["status"], status)
    if value.strip() != (cur["value"] or "").strip():
        changed["value"] = (cur["value"] or "", value.strip())
    with get_db() as db:
        db.execute("UPDATE tour_advance SET status=?, value=?, owner=?, due_date=?, "
                   "comments=?, updated=? WHERE id=?",
                   (status, value.strip()[:600],
                    (fields.get("owner") if "owner" in fields else cur["owner"] or "")[:120],
                    (fields.get("due_date") if "due_date" in fields else cur["due_date"] or "")[:10],
                    (fields.get("comments") if "comments" in fields else cur["comments"] or "")[:2000],
                    _now(), cur["id"]))
    return changed


def advance_progress(tour_id, show_id):
    rows = list_advance(tour_id, show_id)
    applicable = [r for r in rows if r["status"] != "na"]
    done = [r for r in applicable if r["status"] == "complete"]
    waiting = [r for r in applicable if r["status"] == "waiting"]
    pct = round(100 * len(done) / len(applicable)) if applicable else 0
    return {"done": len(done), "total": len(applicable), "waiting": len(waiting),
            "pct": pct,
            "missing": [r for r in applicable if r["status"] == "incomplete"]}


# --- travel -----------------------------------------------------------------

# `miles` is the routed drive for this leg. It is what turns a fuel
# estimate into a fuel figure, and it is entered by a person — nothing
# here calls a routing service or guesses a distance.
TRAVEL_FIELDS = ["show_id", "day_date", "mode", "carrier", "number", "dep_loc", "arr_loc",
                 "dep_time", "arr_time", "dep_tz", "arr_tz", "confirmation", "seat",
                 "terminal", "driver", "phone", "vehicle", "company", "pickup",
                 "destination", "parking", "sleepers", "miles", "tolls",
                 "notes", "visibility", "status"]


def _clean_travel(fields, cur=None):
    cur = cur or {}
    out = {}
    for k in TRAVEL_FIELDS:
        val = fields.get(k) if k in fields else cur.get(k)
        val = (val or "")
        if k == "mode" and val not in TRAVEL_MODES:
            val = cur.get("mode") or "ground"
        if k == "visibility" and val not in VISIBILITY:
            val = cur.get("visibility") or "all"
        if k == "status" and val not in TRAVEL_STATUSES:
            val = cur.get("status") or "planned"
        if k == "show_id":
            out[k] = val or None
        else:
            out[k] = str(val).strip()[:300]
    travelers = fields.get("travelers") if "travelers" in fields else cur.get("travelers")
    if not isinstance(travelers, list) or not travelers:
        travelers = ["all"]
    out["travelers"] = travelers
    return out


def add_travel(tour_id, user_id, fields):
    t = _clean_travel(fields)
    tid = _new_id()
    now = _now()
    cols = TRAVEL_FIELDS + ["travelers"]
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_travel (id, tour_id, user_id, %s, created, updated) "
            "VALUES (?,?,?,%s,?,?)" % (", ".join(cols), ",".join("?" * len(cols))),
            [tid, tour_id, user_id] + [t[k] if k != "travelers" else _j(t[k]) for k in cols]
            + [now, now])
    return tid


def update_travel(tour_id, travel_id, fields):
    cur = get_travel(tour_id, travel_id)
    if not cur:
        return None
    t = _clean_travel(fields, cur)
    changed = {k: (str(cur.get(k) or ""), str(t[k] or "")) for k in TRAVEL_FIELDS
               if str(cur.get(k) or "") != str(t[k] or "")}
    cols = TRAVEL_FIELDS + ["travelers"]
    with get_db() as db:
        db.execute("UPDATE tour_travel SET %s, updated=? WHERE id=? AND tour_id=?"
                   % ", ".join("%s=?" % k for k in cols),
                   [t[k] if k != "travelers" else _j(t[k]) for k in cols]
                   + [_now(), travel_id, tour_id])
    return changed


def get_travel(tour_id, travel_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_travel WHERE id=? AND tour_id=?",
                         (travel_id, tour_id)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["travelers"] = _load(d.get("travelers"), ["all"])
    return d


def list_travel(tour_id, day_date=None, show_id=None):
    q = "SELECT * FROM tour_travel WHERE tour_id = ?"
    params = [tour_id]
    if day_date:
        q += " AND day_date = ?"; params.append(day_date)
    if show_id:
        q += " AND show_id = ?"; params.append(show_id)
    q += " ORDER BY day_date, dep_time"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["travelers"] = _load(d.get("travelers"), ["all"])
        out.append(d)
    return out


def delete_travel(tour_id, travel_id):
    with get_db() as db:
        db.execute("DELETE FROM tour_travel WHERE id=? AND tour_id=?", (travel_id, tour_id))


# --- lodging & rooms --------------------------------------------------------

LODGING_FIELDS = ["show_id", "property", "address", "city", "checkin", "checkout",
                  "confirmation", "room_type", "reservation_name", "payment", "contact",
                  "phone", "parking", "wifi", "notes", "visibility", "status"]


def _clean_lodging(fields, cur=None):
    cur = cur or {}
    out = {}
    for k in LODGING_FIELDS:
        val = fields.get(k) if k in fields else cur.get(k)
        val = val or ""
        if k == "visibility" and val not in VISIBILITY:
            val = cur.get("visibility") or "all"
        if k == "status" and val not in TRAVEL_STATUSES:
            val = cur.get("status") or "planned"
        out[k] = (val or None) if k == "show_id" else str(val).strip()[:300]
    return out


def add_lodging(tour_id, user_id, fields):
    l = _clean_lodging(fields)
    if not l["property"]:
        return None
    lid = _new_id()
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_lodging (id, tour_id, user_id, %s, created, updated) "
            "VALUES (?,?,?,%s,?,?)" % (", ".join(LODGING_FIELDS), ",".join("?" * len(LODGING_FIELDS))),
            [lid, tour_id, user_id] + [l[k] for k in LODGING_FIELDS] + [now, now])
    return lid


def update_lodging(tour_id, lodging_id, fields):
    cur = get_lodging(tour_id, lodging_id)
    if not cur:
        return None
    l = _clean_lodging(fields, cur)
    changed = {k: (str(cur.get(k) or ""), str(l[k] or "")) for k in LODGING_FIELDS
               if str(cur.get(k) or "") != str(l[k] or "")}
    with get_db() as db:
        db.execute("UPDATE tour_lodging SET %s, updated=? WHERE id=? AND tour_id=?"
                   % ", ".join("%s=?" % k for k in LODGING_FIELDS),
                   [l[k] for k in LODGING_FIELDS] + [_now(), lodging_id, tour_id])
    return changed


def get_lodging(tour_id, lodging_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_lodging WHERE id=? AND tour_id=?",
                         (lodging_id, tour_id)).fetchone()
    return dict(row) if row else None


def list_lodging(tour_id, show_id=None, on_date=None):
    q = "SELECT * FROM tour_lodging WHERE tour_id = ?"
    params = [tour_id]
    if show_id:
        q += " AND show_id = ?"; params.append(show_id)
    if on_date:
        q += " AND checkin <= ? AND (checkout = '' OR checkout >= ?)"; params += [on_date, on_date]
    q += " ORDER BY checkin, property"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def delete_lodging(tour_id, lodging_id):
    with get_db() as db:
        db.execute("DELETE FROM tour_rooms WHERE lodging_id=? AND tour_id=?", (lodging_id, tour_id))
        db.execute("DELETE FROM tour_lodging WHERE id=? AND tour_id=?", (lodging_id, tour_id))


def set_room(tour_id, user_id, lodging_id, fields):
    room_id = fields.get("room_id") or _new_id()
    with get_db() as db:
        exists = db.execute("SELECT id FROM tour_rooms WHERE id=? AND tour_id=?",
                            (room_id, tour_id)).fetchone()
        vals = (fields.get("person_id") or None, (fields.get("guest_name") or "")[:120],
                (fields.get("room_number") or "")[:20],
                fields.get("room_kind") if fields.get("room_kind") in ROOM_KINDS else "standard",
                (fields.get("notes") or "")[:500], _now())
        if exists:
            db.execute("UPDATE tour_rooms SET person_id=?, guest_name=?, room_number=?, "
                       "room_kind=?, notes=?, updated=? WHERE id=?", vals + (room_id,))
        else:
            db.execute("INSERT INTO tour_rooms (id, lodging_id, tour_id, user_id, person_id, "
                       "guest_name, room_number, room_kind, notes, updated) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (room_id, lodging_id, tour_id, user_id) + vals)
    return room_id


def list_rooms(tour_id, lodging_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT r.*, p.name AS person_name FROM tour_rooms r "
            "LEFT JOIN tour_people p ON p.id = r.person_id "
            "WHERE r.lodging_id=? AND r.tour_id=? ORDER BY r.room_number, p.name",
            (lodging_id, tour_id)).fetchall()
    return [dict(r) for r in rows]


def delete_room(tour_id, room_id):
    with get_db() as db:
        db.execute("DELETE FROM tour_rooms WHERE id=? AND tour_id=?", (room_id, tour_id))


# --- people -----------------------------------------------------------------

PEOPLE_FIELDS = ["name", "role", "category", "company", "email", "phone", "photo",
                 "notes", "emergency"]


def add_person(tour_id, user_id, fields):
    name = (fields.get("name") or "").strip()
    if not name:
        return None
    pid = _new_id()
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_people (id, tour_id, user_id, name, role, category, company, "
            "email, phone, phone_private, photo, notes, emergency, linked_contact_id, "
            "linked_user_id, shows, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, tour_id, user_id, name[:120], (fields.get("role") or "")[:80],
             fields.get("category") if fields.get("category") in PEOPLE_CATEGORIES else "Crew",
             (fields.get("company") or "")[:120], (fields.get("email") or "").strip().lower()[:200],
             (fields.get("phone") or "")[:60], 0 if fields.get("phone_public") else 1,
             (fields.get("photo") or "")[:300], (fields.get("notes") or "")[:2000],
             (fields.get("emergency") or "")[:300], fields.get("linked_contact_id") or None,
             fields.get("linked_user_id") or None, _j(fields.get("shows") or []), now, now))
    return pid


def update_person(tour_id, person_id, fields):
    cur = get_person(tour_id, person_id)
    if not cur:
        return None
    merged = dict(cur)
    for k in PEOPLE_FIELDS:
        if k in fields:
            merged[k] = fields.get(k) or ""
    if merged.get("category") not in PEOPLE_CATEGORIES:
        merged["category"] = cur["category"]
    if "phone_public" in fields:
        merged["phone_private"] = 0 if fields.get("phone_public") else 1
    if "shows" in fields and isinstance(fields["shows"], list):
        merged["shows"] = fields["shows"]
    if "linked_contact_id" in fields:
        merged["linked_contact_id"] = fields.get("linked_contact_id") or None
    with get_db() as db:
        db.execute(
            "UPDATE tour_people SET name=?, role=?, category=?, company=?, email=?, phone=?, "
            "phone_private=?, photo=?, notes=?, emergency=?, linked_contact_id=?, shows=?, "
            "updated=? WHERE id=? AND tour_id=?",
            ((merged["name"] or "")[:120], (merged["role"] or "")[:80], merged["category"],
             (merged["company"] or "")[:120], (merged["email"] or "").strip().lower()[:200],
             (merged["phone"] or "")[:60], merged["phone_private"], (merged["photo"] or "")[:300],
             (merged["notes"] or "")[:2000], (merged["emergency"] or "")[:300],
             merged.get("linked_contact_id"), _j(merged.get("shows") or []), _now(),
             person_id, tour_id))
    return True


def get_person(tour_id, person_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_people WHERE id=? AND tour_id=?",
                         (person_id, tour_id)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["shows"] = _load(d.get("shows"), [])
    return d


def list_people(tour_id, category=None, search=""):
    q = "SELECT * FROM tour_people WHERE tour_id = ?"
    params = [tour_id]
    if category:
        q += " AND category = ?"; params.append(category)
    if search:
        q += " AND (name LIKE ? OR company LIKE ? OR role LIKE ?)"
        params += ["%%%s%%" % search] * 3
    q += " ORDER BY category, name"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["shows"] = _load(d.get("shows"), [])
        out.append(d)
    return out


def person_for_user(tour_id, member_user_id):
    """The person record that represents a signed-in member, via the
    membership's person_id or matching email."""
    m = get_membership(tour_id, member_user_id)
    if m is None:
        return None
    if m.get("person_id"):
        return get_person(tour_id, m["person_id"])
    for p in list_people(tour_id):
        if p["email"] and p["email"] == (m["email"] or "").lower():
            return p
    return None


def delete_person(tour_id, person_id):
    with get_db() as db:
        db.execute("DELETE FROM tour_people WHERE id=? AND tour_id=?", (person_id, tour_id))
        db.execute("UPDATE tour_members SET person_id=NULL WHERE person_id=? AND tour_id=?",
                   (person_id, tour_id))


# --- guests -----------------------------------------------------------------

GUEST_FIELDS = ["name", "email", "phone", "company", "title", "category", "requested_by",
                "approved_by", "ticket_type", "credentials", "notes", "status"]


def add_guest(tour_id, user_id, show_id, fields):
    name = (fields.get("name") or "").strip()
    if not name:
        return None
    gid = _new_id()
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_guests (id, tour_id, user_id, show_id, name, count, email, phone, "
            "company, title, category, requested_by, approved_by, ticket_type, credentials, "
            "backstage, meet_greet, aftershow, notes, status, linked_contact_id, created, updated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (gid, tour_id, user_id, show_id, name[:120], max(1, int(fields.get("count") or 1)),
             (fields.get("email") or "").strip().lower()[:200], (fields.get("phone") or "")[:60],
             (fields.get("company") or "")[:120], (fields.get("title") or "")[:120],
             fields.get("category") if fields.get("category") in GUEST_CATEGORIES else "Personal",
             (fields.get("requested_by") or "")[:120], (fields.get("approved_by") or "")[:120],
             (fields.get("ticket_type") or "")[:60], (fields.get("credentials") or "")[:120],
             1 if fields.get("backstage") else 0, 1 if fields.get("meet_greet") else 0,
             1 if fields.get("aftershow") else 0, (fields.get("notes") or "")[:1000],
             fields.get("status") if fields.get("status") in GUEST_STATUSES else "pending",
             fields.get("linked_contact_id") or None, now, now))
    return gid


def update_guest(tour_id, guest_id, fields):
    cur = get_guest(tour_id, guest_id)
    if not cur:
        return None
    merged = dict(cur)
    for k in GUEST_FIELDS:
        if k in fields:
            merged[k] = fields.get(k) or ""
    if merged.get("category") not in GUEST_CATEGORIES:
        merged["category"] = cur["category"]
    if merged.get("status") not in GUEST_STATUSES:
        merged["status"] = cur["status"]
    if "count" in fields:
        merged["count"] = max(1, int(fields.get("count") or 1))
    for flag in ("backstage", "meet_greet", "aftershow"):
        if flag in fields:
            merged[flag] = 1 if fields.get(flag) else 0
    checked = cur.get("checked_in_at") or ""
    if merged["status"] == "checked_in" and not checked:
        checked = _now()
    with get_db() as db:
        db.execute(
            "UPDATE tour_guests SET name=?, count=?, email=?, phone=?, company=?, title=?, "
            "category=?, requested_by=?, approved_by=?, ticket_type=?, credentials=?, "
            "backstage=?, meet_greet=?, aftershow=?, notes=?, status=?, checked_in_at=?, "
            "updated=? WHERE id=? AND tour_id=?",
            ((merged["name"] or "")[:120], merged["count"], (merged["email"] or "")[:200],
             (merged["phone"] or "")[:60], (merged["company"] or "")[:120],
             (merged["title"] or "")[:120], merged["category"], (merged["requested_by"] or "")[:120],
             (merged["approved_by"] or "")[:120], (merged["ticket_type"] or "")[:60],
             (merged["credentials"] or "")[:120], merged["backstage"], merged["meet_greet"],
             merged["aftershow"], (merged["notes"] or "")[:1000], merged["status"], checked,
             _now(), guest_id, tour_id))
    return {"status": (cur["status"], merged["status"])} if cur["status"] != merged["status"] else {}


def get_guest(tour_id, guest_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_guests WHERE id=? AND tour_id=?",
                         (guest_id, tour_id)).fetchone()
    return dict(row) if row else None


def list_guests(tour_id, show_id, status=None):
    q = "SELECT * FROM tour_guests WHERE tour_id=? AND show_id=?"
    params = [tour_id, show_id]
    if status:
        q += " AND status = ?"; params.append(status)
    q += " ORDER BY CASE status WHEN 'approved' THEN 0 WHEN 'pending' THEN 1 WHEN 'request' THEN 2 ELSE 3 END, name"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def guest_summary(tour_id, show_id, allocation=""):
    guests = list_guests(tour_id, show_id)
    used = sum(g["count"] for g in guests if g["status"] in ("approved", "checked_in"))
    pending = sum(g["count"] for g in guests if g["status"] in ("pending", "request"))
    checked = sum(g["count"] for g in guests if g["status"] == "checked_in")
    try:
        allocation_n = int(str(allocation).strip()) if str(allocation).strip() else None
    except ValueError:
        allocation_n = None
    return {"used": used, "pending": pending, "checked_in": checked,
            "allocation": allocation_n,
            "remaining": (allocation_n - used) if allocation_n is not None else None,
            "over": (allocation_n is not None and used > allocation_n)}


def delete_guest(tour_id, guest_id):
    with get_db() as db:
        db.execute("DELETE FROM tour_guests WHERE id=? AND tour_id=?", (guest_id, tour_id))


# --- VIP --------------------------------------------------------------------

def add_vip(tour_id, user_id, show_id, fields):
    package = (fields.get("package") or "").strip()
    if not package:
        return None
    vid = _new_id()
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_vip (id, tour_id, user_id, show_id, package, price, quantity, "
            "purchaser, guest, email, meet_greet, early_entry, merch, photo, credentials, "
            "schedule_time, notes, status, created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, tour_id, user_id, show_id, package[:120], (fields.get("price") or "")[:40],
             max(1, int(fields.get("quantity") or 1)), (fields.get("purchaser") or "")[:120],
             (fields.get("guest") or "")[:120], (fields.get("email") or "").strip().lower()[:200],
             1 if fields.get("meet_greet") else 0, 1 if fields.get("early_entry") else 0,
             1 if fields.get("merch") else 0, 1 if fields.get("photo") else 0,
             (fields.get("credentials") or "")[:120], (fields.get("schedule_time") or "")[:5],
             (fields.get("notes") or "")[:1000], "sold", _now()))
    return vid


def list_vip(tour_id, show_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM tour_vip WHERE tour_id=? AND show_id=? "
                          "ORDER BY schedule_time, package, guest", (tour_id, show_id)).fetchall()
    return [dict(r) for r in rows]


def set_vip_status(tour_id, vip_id, status, fulfilled=None):
    allowed = ("sold", "checked_in", "no_show", "refunded")
    if status not in allowed:
        return False
    with get_db() as db:
        if fulfilled is None:
            db.execute("UPDATE tour_vip SET status=?, checked_in_at=CASE WHEN ?='checked_in' "
                       "THEN ? ELSE checked_in_at END WHERE id=? AND tour_id=?",
                       (status, status, _now(), vip_id, tour_id))
        else:
            db.execute("UPDATE tour_vip SET status=?, fulfilled=?, checked_in_at=CASE WHEN "
                       "?='checked_in' THEN ? ELSE checked_in_at END WHERE id=? AND tour_id=?",
                       (status, 1 if fulfilled else 0, status, _now(), vip_id, tour_id))
    return True


def vip_summary(tour_id, show_id):
    rows = list_vip(tour_id, show_id)
    sold = sum(r["quantity"] for r in rows if r["status"] != "refunded")
    checked = sum(r["quantity"] for r in rows if r["status"] == "checked_in")
    no_show = sum(r["quantity"] for r in rows if r["status"] == "no_show")
    gross = 0.0
    for r in rows:
        try:
            gross += float(str(r["price"]).replace(",", "").replace("$", "") or 0) * r["quantity"]
        except ValueError:
            pass
    unfulfilled = len([r for r in rows if r["merch"] and not r["fulfilled"]])
    return {"sold": sold, "checked_in": checked, "no_show": no_show,
            "gross": round(gross, 2), "unfulfilled": unfulfilled}


# --- files ------------------------------------------------------------------

def add_file(tour_id, user_id, entity_type, entity_id, file_name, path, file_type,
             category, visibility, uploaded_by):
    fid = _new_id()
    with get_db() as db:
        prior = db.execute("SELECT MAX(version) AS v FROM tour_files WHERE tour_id=? AND "
                           "entity_type=? AND entity_id=? AND file_name=?",
                           (tour_id, entity_type, entity_id or "", file_name)).fetchone()
        version = (prior["v"] or 0) + 1
        db.execute(
            "INSERT INTO tour_files (id, tour_id, user_id, entity_type, entity_id, file_name, "
            "path, file_type, category, visibility, uploaded_by, version, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid, tour_id, user_id, entity_type, entity_id or "", file_name[:200], path,
             (file_type or "")[:20], category if category in FILE_CATEGORIES else "other",
             visibility if visibility in VISIBILITY else "all", (uploaded_by or "")[:120],
             version, _now()))
    return fid


def get_file(tour_id, file_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_files WHERE id=? AND tour_id=?",
                         (file_id, tour_id)).fetchone()
    return dict(row) if row else None


def list_files(tour_id, entity_type=None, entity_id=None, category=None, search=""):
    q = "SELECT * FROM tour_files WHERE tour_id = ?"
    params = [tour_id]
    if entity_type:
        q += " AND entity_type = ?"; params.append(entity_type)
    if entity_id:
        q += " AND entity_id = ?"; params.append(entity_id)
    if category:
        q += " AND category = ?"; params.append(category)
    if search:
        q += " AND file_name LIKE ?"; params.append("%%%s%%" % search)
    q += " ORDER BY created DESC"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def delete_file(tour_id, file_id):
    f = get_file(tour_id, file_id)
    with get_db() as db:
        db.execute("DELETE FROM tour_files WHERE id=? AND tour_id=?", (file_id, tour_id))
    return f


# --- expenses ---------------------------------------------------------------

def add_expense(tour_id, user_id, fields):
    eid = _new_id()
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_expenses (id, tour_id, user_id, show_id, vendor, category, amount, "
            "tax, currency, spend_date, notes, receipt_file_id, source, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, tour_id, user_id, fields.get("show_id") or None, (fields.get("vendor") or "")[:120],
             fields.get("category") if fields.get("category") in EXPENSE_CATEGORIES else "other",
             (fields.get("amount") or "")[:30], (fields.get("tax") or "")[:30],
             (fields.get("currency") or "")[:3].upper(), (fields.get("spend_date") or "")[:10],
             (fields.get("notes") or "")[:1000], fields.get("receipt_file_id") or None,
             fields.get("source") if fields.get("source") in CHANGE_SOURCES else "manual", _now()))
    return eid


def list_expenses(tour_id, show_id=None):
    q = "SELECT * FROM tour_expenses WHERE tour_id = ?"
    params = [tour_id]
    if show_id:
        q += " AND show_id = ?"; params.append(show_id)
    q += " ORDER BY spend_date DESC, created DESC"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def delete_expense(tour_id, expense_id):
    with get_db() as db:
        db.execute("DELETE FROM tour_expenses WHERE id=? AND tour_id=?", (expense_id, tour_id))


# --- merch ------------------------------------------------------------------

def add_product(tour_id, user_id, fields):
    name = (fields.get("name") or "").strip()
    if not name:
        return None
    pid = _new_id()
    with get_db() as db:
        db.execute("INSERT INTO tour_merch_products (id, tour_id, user_id, name, sku, price, "
                   "tour_inventory, low_stock_at, created) VALUES (?,?,?,?,?,?,?,?,?)",
                   (pid, tour_id, user_id, name[:120], (fields.get("sku") or "")[:60],
                    (fields.get("price") or "")[:30], (fields.get("tour_inventory") or "")[:20],
                    (fields.get("low_stock_at") or "")[:20], _now()))
    return pid


def list_products(tour_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM tour_merch_products WHERE tour_id=? ORDER BY name",
                          (tour_id,)).fetchall()
    return [dict(r) for r in rows]


def set_merch_count(tour_id, user_id, show_id, product_id, fields):
    with get_db() as db:
        vals = ((fields.get("opening") or "")[:20], (fields.get("closing") or "")[:20],
                (fields.get("sold") or "")[:20], (fields.get("gross") or "")[:30],
                (fields.get("venue_pct") or "")[:10], (fields.get("taxes") or "")[:30],
                (fields.get("fees") or "")[:30], 1 if fields.get("settled") else 0, _now())
        row = db.execute("SELECT id FROM tour_merch_counts WHERE show_id=? AND product_id=?",
                         (show_id, product_id)).fetchone()
        if row:
            db.execute("UPDATE tour_merch_counts SET opening=?, closing=?, sold=?, gross=?, "
                       "venue_pct=?, taxes=?, fees=?, settled=?, updated=? WHERE id=?",
                       vals + (row["id"],))
        else:
            db.execute("INSERT INTO tour_merch_counts (id, tour_id, user_id, show_id, product_id, "
                       "opening, closing, sold, gross, venue_pct, taxes, fees, settled, updated) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (_new_id(), tour_id, user_id, show_id, product_id) + vals)


def list_merch_counts(tour_id, show_id=None):
    q = ("SELECT c.*, p.name AS product_name, p.price, p.tour_inventory, p.low_stock_at "
         "FROM tour_merch_counts c JOIN tour_merch_products p ON p.id = c.product_id "
         "WHERE c.tour_id = ?")
    params = [tour_id]
    if show_id:
        q += " AND c.show_id = ?"; params.append(show_id)
    q += " ORDER BY p.name"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    return [dict(r) for r in rows]


# --- content ----------------------------------------------------------------

def ensure_content_plan(tour_id, user_id, show_id, items=None):
    items = items or CONTENT_DEFAULTS
    with get_db() as db:
        have = {r["item"] for r in db.execute(
            "SELECT item FROM tour_content WHERE show_id=?", (show_id,))}
        for item in items:
            if item in have:
                continue
            db.execute("INSERT INTO tour_content (id, tour_id, user_id, show_id, item, status, "
                       "updated) VALUES (?,?,?,?,?,?,?)",
                       (_new_id(), tour_id, user_id, show_id, item, "planned", _now()))


def list_content(tour_id, show_id=None):
    q = "SELECT * FROM tour_content WHERE tour_id = ?"
    params = [tour_id]
    if show_id:
        q += " AND show_id = ?"; params.append(show_id)
    q += " ORDER BY show_id, updated"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def set_content(tour_id, content_id, fields):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_content WHERE id=? AND tour_id=?",
                         (content_id, tour_id)).fetchone()
        if not row:
            return None
        cur = dict(row)
        status = fields.get("status") if fields.get("status") in CONTENT_STATUSES else cur["status"]
        db.execute("UPDATE tour_content SET assignee=?, due_time=?, status=?, file_id=?, notes=?, "
                   "updated=? WHERE id=?",
                   ((fields.get("assignee") if "assignee" in fields else cur["assignee"] or "")[:120],
                    (fields.get("due_time") if "due_time" in fields else cur["due_time"] or "")[:5],
                    status, fields.get("file_id") if "file_id" in fields else cur.get("file_id"),
                    (fields.get("notes") if "notes" in fields else cur["notes"] or "")[:1000],
                    _now(), content_id))
    return True


# --- set lists --------------------------------------------------------------

def create_setlist(tour_id, user_id, name, show_id=None, notes=""):
    sid = _new_id()
    now = _now()
    with get_db() as db:
        db.execute("INSERT INTO tour_setlists (id, tour_id, user_id, show_id, name, notes, "
                   "created, updated) VALUES (?,?,?,?,?,?,?,?)",
                   (sid, tour_id, user_id, show_id, (name or "Set list")[:120],
                    (notes or "")[:2000], now, now))
    return sid


def list_setlists(tour_id, show_id=None):
    q = "SELECT * FROM tour_setlists WHERE tour_id=?"
    params = [tour_id]
    if show_id:
        q += " AND show_id=?"; params.append(show_id)
    q += " ORDER BY updated DESC"
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def get_setlist(tour_id, setlist_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_setlists WHERE id=? AND tour_id=?",
                         (setlist_id, tour_id)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["songs"] = [dict(r) for r in db.execute(
            "SELECT * FROM tour_setlist_items WHERE setlist_id=? ORDER BY position",
            (setlist_id,))]
    return d


def replace_setlist_items(tour_id, user_id, setlist_id, items):
    with get_db() as db:
        db.execute("DELETE FROM tour_setlist_items WHERE setlist_id=?", (setlist_id,))
        for i, it in enumerate(items):
            title = (it.get("title") or "").strip()
            if not title:
                continue
            db.execute("INSERT INTO tour_setlist_items (id, setlist_id, user_id, position, title, "
                       "os_track_id, duration, section, notes) VALUES (?,?,?,?,?,?,?,?,?)",
                       (_new_id(), setlist_id, user_id, i, title[:160], it.get("os_track_id") or None,
                        (it.get("duration") or "")[:10],
                        it.get("section") if it.get("section") in ("main", "encore", "alternate") else "main",
                        (it.get("notes") or "")[:300]))
        db.execute("UPDATE tour_setlists SET updated=? WHERE id=?", (_now(), setlist_id))


def copy_setlist(tour_id, user_id, setlist_id, to_show_id):
    src = get_setlist(tour_id, setlist_id)
    if not src:
        return None
    new_id = create_setlist(tour_id, user_id, src["name"], to_show_id, src["notes"])
    replace_setlist_items(tour_id, user_id, new_id, src["songs"])
    return new_id


def delete_setlist(tour_id, setlist_id):
    with get_db() as db:
        db.execute("DELETE FROM tour_setlist_items WHERE setlist_id=?", (setlist_id,))
        db.execute("DELETE FROM tour_setlists WHERE id=? AND tour_id=?", (setlist_id, tour_id))


# --- changes & acknowledgements ---------------------------------------------

def log_change(tour_id, user_id, actor, entity_type, entity_id, entity_label, field,
               before, after, severity="info", source="manual"):
    cid = _new_id()
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_changes (id, tour_id, user_id, actor_id, actor_name, entity_type, "
            "entity_id, entity_label, field, before, after, severity, source, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, tour_id, user_id, (actor or {}).get("id") or "", (actor or {}).get("name") or "",
             entity_type, entity_id or "", (entity_label or "")[:200], field,
             str(before or "")[:600], str(after or "")[:600],
             severity if severity in SEVERITIES else "info",
             source if source in CHANGE_SOURCES else "manual", _now()))
    return cid


def list_changes(tour_id, since=None, severity_min=None, limit=200):
    q = "SELECT * FROM tour_changes WHERE tour_id = ?"
    params = [tour_id]
    if since:
        q += " AND created >= ?"; params.append(since)
    if severity_min == "important":
        q += " AND severity IN ('important','critical')"
    elif severity_min == "critical":
        q += " AND severity = 'critical'"
    q += " ORDER BY created DESC LIMIT ?"
    params.append(limit)
    with get_db() as db:
        rows = db.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def ack(tour_id, user_id, change_id, viewer_id, state):
    if state not in ("delivered", "viewed", "acknowledged"):
        return False
    with get_db() as db:
        row = db.execute("SELECT id, state FROM tour_acks WHERE change_id=? AND viewer_id=?",
                         (change_id, viewer_id)).fetchone()
        order = {"delivered": 0, "viewed": 1, "acknowledged": 2}
        if row:
            if order[state] > order.get(row["state"], 0):
                db.execute("UPDATE tour_acks SET state=?, at=? WHERE id=?", (state, _now(), row["id"]))
        else:
            db.execute("INSERT INTO tour_acks (id, change_id, tour_id, user_id, viewer_id, state, at) "
                       "VALUES (?,?,?,?,?,?,?)", (_new_id(), change_id, tour_id, user_id, viewer_id,
                                                  state, _now()))
    return True


def ack_state(tour_id, change_ids, viewer_id):
    if not change_ids:
        return {}
    marks = ",".join("?" * len(change_ids))
    with get_db() as db:
        rows = db.execute("SELECT change_id, state FROM tour_acks WHERE tour_id=? AND viewer_id=? "
                          "AND change_id IN (%s)" % marks, [tour_id, viewer_id] + list(change_ids)).fetchall()
    return {r["change_id"]: r["state"] for r in rows}


def ack_roster(tour_id, change_id):
    with get_db() as db:
        rows = db.execute("SELECT viewer_id, state, at FROM tour_acks WHERE tour_id=? AND change_id=?",
                          (tour_id, change_id)).fetchall()
    return [dict(r) for r in rows]


# --- share links ------------------------------------------------------------

def create_share_link(tour_id, user_id, scope, show_id=None, password_hash="", expires=""):
    if scope not in SHARE_SCOPES:
        return None
    sid = _new_id()
    token = uuid.uuid4().hex
    with get_db() as db:
        db.execute("INSERT INTO tour_share_links (id, tour_id, user_id, scope, show_id, token, "
                   "password_hash, expires, created) VALUES (?,?,?,?,?,?,?,?,?)",
                   (sid, tour_id, user_id, scope, show_id, token, password_hash or "",
                    (expires or "")[:10], _now()))
    return token


def get_share_link(token):
    with get_db() as db:
        row = db.execute("SELECT * FROM tour_share_links WHERE token=?", (token,)).fetchone()
    return dict(row) if row else None


def touch_share_link(token):
    with get_db() as db:
        db.execute("UPDATE tour_share_links SET access_count = access_count + 1, last_access=? "
                   "WHERE token=?", (_now(), token))


def list_share_links(tour_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM tour_share_links WHERE tour_id=? ORDER BY created DESC",
                          (tour_id,)).fetchall()
    return [dict(r) for r in rows]


def revoke_share_link(tour_id, link_id):
    with get_db() as db:
        db.execute("UPDATE tour_share_links SET revoked=1 WHERE id=? AND tour_id=?", (link_id, tour_id))


# --- imports ----------------------------------------------------------------

def record_import(tour_id, user_id, source, filename, raw, summary):
    iid = _new_id()
    with get_db() as db:
        db.execute("INSERT INTO tour_imports (id, tour_id, user_id, source, filename, raw, summary, "
                   "created) VALUES (?,?,?,?,?,?,?,?)",
                   (iid, tour_id, user_id, source[:40], (filename or "")[:200], (raw or "")[:20000],
                    json.dumps(summary or {}), _now()))
    return iid


def list_imports(tour_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM tour_imports WHERE tour_id=? ORDER BY created DESC",
                          (tour_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["summary"] = _load(d.get("summary"), {})
        out.append(d)
    return out


# --- fan capture (architecture) ---------------------------------------------

def add_fan_capture(tour_id, user_id, show_id, source, email="", phone="", consent_text="",
                    consented=False, city=""):
    cid = _new_id()
    with get_db() as db:
        db.execute("INSERT INTO tour_fan_captures (id, tour_id, user_id, show_id, source, email, "
                   "phone, consent_text, consented, city, created) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (cid, tour_id, user_id, show_id, (source or "manual")[:40],
                    (email or "").strip().lower()[:200], (phone or "")[:40],
                    (consent_text or "")[:400], 1 if consented else 0, (city or "")[:80], _now()))
    return cid


def fan_capture_summary(tour_id):
    with get_db() as db:
        row = db.execute("SELECT COUNT(*) AS n, SUM(consented) AS c FROM tour_fan_captures "
                         "WHERE tour_id=?", (tour_id,)).fetchone()
    return {"records": row["n"] or 0, "consented": row["c"] or 0}


# --- the bill, and a line check for each act on it ---------------------------
#
# On a package tour the running order is the organising fact of the whole day:
# load-in, line checks, changeovers, set times and curfew all hang off it, and
# it changes show to show. `tour_shows.support` already held it as a comma
# string, which is fine for printing a day sheet and useless for scheduling -
# there is nowhere to put "EX LOVER line-checks at 16:40".
#
# So the bill becomes rows. `support` is KEPT IN STEP from those rows rather
# than left to drift, because the band share link and the day sheet read it
# and a second source of truth that disagrees is worse than the string alone.

LINEUP_FIELDS = ["act_name", "running_order", "is_headliner", "line_check",
                 "set_start", "set_end", "notes"]


def init_lineup():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS tour_lineup (
                id TEXT PRIMARY KEY,
                tour_id TEXT NOT NULL,
                show_id TEXT NOT NULL,
                act_name TEXT NOT NULL,
                running_order INTEGER NOT NULL DEFAULT 0,
                is_headliner INTEGER NOT NULL DEFAULT 0,
                line_check TEXT NOT NULL DEFAULT '',
                set_start TEXT NOT NULL DEFAULT '',
                set_end TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tour_lineup_show
                ON tour_lineup(show_id, running_order);
        """)


def list_lineup(tour_id, show_id):
    """The bill in running order. Order 1 opens; the headliner is last."""
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM tour_lineup WHERE tour_id=? AND show_id=? "
            "ORDER BY running_order ASC, act_name ASC",
            (tour_id, show_id)).fetchall()
    return [dict(r) for r in rows]


def set_lineup(tour_id, show_id, act_names, headliner=None):
    """Replace the bill, KEEPING the times already set for acts that stay.

    Re-ordering a five-act bill is an everyday act on a package tour, and
    losing four line-check times because one opener was added is the kind of
    thing that makes somebody stop using the tool.
    """
    existing = {r["act_name"].strip().lower(): r for r in list_lineup(tour_id, show_id)}
    cleaned, seen = [], set()
    for name in act_names or []:
        name = (name or "").strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        cleaned.append(name)

    now = _now()
    with get_db() as db:
        db.execute("DELETE FROM tour_lineup WHERE tour_id=? AND show_id=?",
                   (tour_id, show_id))
        for position, name in enumerate(cleaned, start=1):
            prior = existing.get(name.lower(), {})
            db.execute(
                "INSERT INTO tour_lineup (id, tour_id, show_id, act_name, "
                "running_order, is_headliner, line_check, set_start, set_end, "
                "notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (_new_id(), tour_id, show_id, name, position,
                 1 if (headliner and name.strip().lower() == headliner.strip().lower())
                 else (1 if position == len(cleaned) and not headliner else 0),
                 prior.get("line_check") or "", prior.get("set_start") or "",
                 prior.get("set_end") or "", prior.get("notes") or "",
                 prior.get("created_at") or now))
    _sync_support(tour_id, show_id)
    return list_lineup(tour_id, show_id)


def update_lineup_act(tour_id, show_id, lineup_id, fields):
    sets, args = [], []
    for key in ("line_check", "set_start", "set_end", "notes", "act_name"):
        if key in fields:
            sets.append("%s = ?" % key)
            args.append((fields.get(key) or "").strip()[:200])
    if "running_order" in fields:
        try:
            sets.append("running_order = ?")
            args.append(int(fields["running_order"]))
        except (TypeError, ValueError):
            sets.pop()
    if not sets:
        return None
    args.extend([lineup_id, tour_id, show_id])
    with get_db() as db:
        db.execute("UPDATE tour_lineup SET %s WHERE id=? AND tour_id=? AND show_id=?"
                   % ", ".join(sets), args)
    _sync_support(tour_id, show_id)
    return list_lineup(tour_id, show_id)


def _sync_support(tour_id, show_id):
    """Write the bill back to tour_shows.support, in running order.

    The share link and the printed day sheet read that column. Letting the
    two drift would mean the band sees one running order and the production
    sheet another, on the same day, from the same tool.
    """
    # Through update_show_ext, not raw SQL: `support` lives on
    # tour_show_ext, and that function is the one place that knows it.
    names = [r["act_name"] for r in list_lineup(tour_id, show_id)]
    update_show_ext(tour_id, show_id, {"support": ", ".join(names)})


def seed_lineup_from_support(tour_id, show):
    """First open of a show that already has a comma-separated bill.

    Returns the rows, seeding them once from the string so existing tours
    carry their running order into the new view instead of appearing empty.
    """
    rows = list_lineup(tour_id, show["id"])
    if rows:
        return rows
    raw = (show.get("support") or "").strip()
    if not raw:
        return []
    names = [part.strip() for part in raw.split(",") if part.strip()]
    return set_lineup(tour_id, show["id"], names) if names else []


def lineup_schedule_items(tour_id, user_id, show):
    """Turn the line-check times into real schedule entries.

    Skips acts with no time set rather than inventing one - a line check
    nobody has advanced is not a 16:00 line check. Returns the number added.
    """
    rows = [r for r in list_lineup(tour_id, show["id"]) if (r.get("line_check") or "").strip()]
    if not rows:
        return 0
    existing = {(s.get("title") or "").strip().lower()
                for s in list_schedule(tour_id, show_id=show["id"])}
    added = 0
    for row in rows:
        title = "%s line check" % row["act_name"]
        if title.strip().lower() in existing:
            continue
        add_schedule_item(tour_id, user_id, {
            "show_id": show["id"], "day_date": show["date"], "title": title,
            "category": "soundcheck", "start_time": row["line_check"],
            "precision": "approx", "location": show.get("venue") or ""})
        added += 1
    return added


def lineup_warnings(rows, fmt_time=None):
    """What is wrong with this bill, in words a tour manager would use.

    Re-ordering a bill keeps each act's advanced line check, which is right -
    the time was agreed with that act, not with a slot. The consequence is
    that after a re-order the times can run backwards against the new order,
    and nobody would notice from a list that is sorted by order and shows the
    times as plain text.

    `fmt_time` is injected rather than imported. Every time in this product
    is displayed as "5:00 PM" by tour_engine.fmt_time, and a warning that
    said "17:00" beside a field showing "05:00 PM" would read as a different
    time. The engine imports this module, so importing it back would be a
    cycle - the caller passes the formatter instead.

    Returns [] when the bill is fine, so a caller can render nothing.
    """
    show_time = fmt_time or (lambda value: value)
    out = []
    timed = [r for r in rows if (r.get("line_check") or "").strip()]
    missing = [r for r in rows if not (r.get("line_check") or "").strip()]

    if missing and timed:
        names = ", ".join(r["act_name"] for r in missing[:4])
        out.append("No line check yet for %s." % names)

    # Out of sequence against the running order.
    previous = None
    for row in timed:
        current = (row.get("line_check") or "").strip()
        if previous and current < previous[1]:
            out.append("%s line-checks at %s, before %s at %s, but goes on later. "
                       "Re-ordering the bill keeps each act's time, so these may "
                       "need swapping."
                       % (row["act_name"], show_time(current),
                          previous[0], show_time(previous[1])))
            break
        previous = (row["act_name"], current)

    headliners = [r for r in rows if r.get("is_headliner")]
    if rows and not headliners:
        out.append("No act is marked as the headliner.")
    elif len(headliners) > 1:
        out.append("More than one act is marked as the headliner.")

    return out
