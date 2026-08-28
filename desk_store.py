"""Operator Desk data layer — leads, notes, tasks, events, deals, files,
activity, and the desk's own user roster.

Internal-only. Nothing in these tables is ever rendered on a public page
or to an artist account: access is decided in operator_desk.py against
the desk_users roster, not against the app's user table, and the two are
linked only by email.

Design notes:

  Own tables, shared database. Everything is prefixed desk_ and lives in
  the same SQLite file as the app (db.get_db), so the existing backup
  path covers it and there is no second database to lose.

  Lists are JSON columns. Opportunity types, tags, attendees and
  mentions are small lists on a row that is always read whole - a join
  table would add joins and nothing else at this scale.

  Every mutation that matters is logged. log_activity() records who,
  what, which record and when; the Owner reads it on /operator-desk/
  activity. Accountability is a feature here, not overhead: three people
  sharing a pipeline need to see who moved what.

  Access is by email, assignment is by name. The roster (desk_users)
  authorizes logins by email. Assignment fields carry team member names
  (LJ, Warren, Jovan, Other) so a lead can be assigned to somebody whose
  login has not been linked yet.
"""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from db import get_db

# --- vocabularies -----------------------------------------------------------
ROLES = ["owner", "admin", "member", "viewer"]
ROLE_LABELS = {"owner": "Owner", "admin": "Admin",
               "member": "Team Member", "viewer": "Viewer"}

TEAM_NAMES = ["LJ", "Warren", "Jovan", "Other"]

CONTACT_ROLES = ["Artist", "Manager", "Producer", "Label", "Estate",
                 "Publisher", "Investor", "Brand", "Other"]

OPPORTUNITY_TYPES = ["Distribution", "Development", "Partnership",
                     "Royalty Sweep", "Catalog Recovery", "Growth Capital",
                     "Deal Desk", "Sync/Licensing", "Merch/Physical",
                     "Direct-to-Fan", "Other"]

PIPELINE_STAGES = ["New Lead", "Contacted", "Discovery Scheduled",
                   "Discovery Complete", "Needs Internal Review",
                   "Offer / Terms Drafting", "Contract Sent",
                   "Contract Signed", "Onboarding", "Active", "Passed",
                   "Dormant"]

PRIORITIES = ["Low", "Medium", "High", "Urgent"]

LEAD_SOURCES = ["Website application", "Referral", "Instagram",
                "Industry contact", "Event/show", "Manager outreach",
                "Partner intro", "Manual entry", "Other"]

NOTE_TYPES = ["General Note", "Call Note", "Meeting Note", "Show Note",
              "Management Note", "Deal Note", "Catalog Note", "Release Note",
              "Red Flag", "Follow-Up", "Opportunity", "Internal Only"]

TASK_STATUSES = ["To Do", "In Progress", "Waiting", "Complete", "Cancelled"]
TASK_CATEGORIES = ["Follow-Up", "Contract", "Release", "Catalog", "Finance",
                   "Marketing", "Meeting", "Research", "Other"]

EVENT_TYPES = ["Show", "Meeting", "Studio Session", "Dinner", "Call",
               "Conference", "Showcase", "Other"]

DEAL_TYPES = ["Distribution", "Development", "Partnership", "Catalog",
              "Royalty Sweep", "Growth Capital", "Sync", "Brand", "Other"]
DEAL_STATUSES = ["Reviewing", "Structuring", "Terms Drafted", "Sent",
                 "Negotiating", "Signed", "Passed"]

FILE_CATEGORIES = ["Royalty statement", "Contract", "Split sheet",
                   "Pitch deck", "Release plan", "Catalog spreadsheet",
                   "Artwork", "Show flyer", "Press kit", "Notes", "Other"]

SUGGESTED_TAGS = ["Hot Lead", "Catalog Opportunity", "Manager Connected",
                  "Needs Royalty Sweep", "Needs Deal Review", "Touring",
                  "Has Traction", "Needs Capital", "Sync Potential",
                  "High Risk", "Follow Up After Release", "VIP",
                  "Do Not Contact"]

LEGAL_NOTE = ("Business guidance and deal strategy support should be "
              "reviewed with qualified legal counsel where appropriate.")

# Lead columns that are plain one-value text, in form/display order.
LEAD_TEXT_FIELDS = [
    ("artist_name", "Artist / Company Name"), ("contact_name", "Contact Name"),
    ("email", "Email"), ("phone", "Phone"), ("instagram", "Instagram"),
    ("tiktok", "TikTok"), ("youtube", "YouTube"), ("website", "Website"),
    ("city", "City"), ("state", "State"), ("country", "Country"),
    ("timezone", "Timezone"), ("genre", "Genre"),
    ("current_distributor", "Current distributor"),
    ("monthly_revenue_estimate", "Monthly streaming revenue estimate"),
    ("catalog_size", "Catalog size"),
    ("upcoming_release_date", "Upcoming release date"),
    ("existing_team", "Existing team"), ("manager_name", "Manager name"),
    ("attorney_name", "Attorney name"),
    ("producer_relationships", "Producer relationships"),
    ("label_affiliation", "Label/imprint affiliation"),
    ("publishing_status", "Publishing/admin status"),
    ("soundexchange_status", "SoundExchange status"),
    ("mlc_status", "MLC status"),
    ("content_id_status", "YouTube Content ID status"),
    ("splits_issues", "Known splits issues"),
    ("catalog_issues", "Known catalog issues"),
]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id():
    return uuid.uuid4().hex


def _dump(value):
    return json.dumps(value or [])


def _load(text):
    try:
        value = json.loads(text or "[]")
        return value if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


# --- schema -----------------------------------------------------------------

def init_desk():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS desk_users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                last_login TEXT
            );
            CREATE TABLE IF NOT EXISTS desk_leads (
                id TEXT PRIMARY KEY,
                artist_name TEXT NOT NULL,
                contact_name TEXT, role TEXT, email TEXT, phone TEXT,
                instagram TEXT, tiktok TEXT, youtube TEXT, website TEXT,
                city TEXT, state TEXT, country TEXT, timezone TEXT,
                genre TEXT, current_distributor TEXT,
                monthly_revenue_estimate TEXT, catalog_size TEXT,
                upcoming_release_date TEXT, existing_team TEXT,
                manager_name TEXT, attorney_name TEXT,
                producer_relationships TEXT, label_affiliation TEXT,
                publishing_status TEXT, soundexchange_status TEXT,
                mlc_status TEXT, content_id_status TEXT,
                splits_issues TEXT, catalog_issues TEXT,
                opportunity_types TEXT NOT NULL DEFAULT '[]',
                pipeline_stage TEXT NOT NULL DEFAULT 'New Lead',
                priority TEXT NOT NULL DEFAULT 'Medium',
                lead_source TEXT, assigned_to TEXT,
                tags TEXT NOT NULL DEFAULT '[]',
                follow_up_date TEXT, follow_up_owner TEXT,
                follow_up_reason TEXT, follow_up_status TEXT,
                stage_changed_at TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS desk_notes (
                id TEXT PRIMARY KEY,
                lead_id TEXT NOT NULL,
                author_id TEXT, author_name TEXT NOT NULL,
                note_type TEXT NOT NULL, body TEXT NOT NULL,
                is_pinned INTEGER NOT NULL DEFAULT 0,
                is_internal INTEGER NOT NULL DEFAULT 1,
                next_step TEXT, follow_up_date TEXT,
                tagged_users TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS desk_tasks (
                id TEXT PRIMARY KEY,
                lead_id TEXT,
                title TEXT NOT NULL, description TEXT,
                assigned_to TEXT, created_by TEXT NOT NULL,
                due_date TEXT, priority TEXT NOT NULL DEFAULT 'Medium',
                status TEXT NOT NULL DEFAULT 'To Do',
                category TEXT NOT NULL DEFAULT 'Other',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS desk_events (
                id TEXT PRIMARY KEY,
                lead_id TEXT,
                event_name TEXT NOT NULL, event_type TEXT NOT NULL,
                date TEXT, time TEXT, venue TEXT, city TEXT,
                attendees TEXT NOT NULL DEFAULT '[]',
                notes TEXT, follow_up_needed INTEGER NOT NULL DEFAULT 0,
                assigned_to TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS desk_deals (
                id TEXT PRIMARY KEY,
                lead_id TEXT NOT NULL,
                deal_type TEXT NOT NULL,
                estimated_value TEXT, advance_discussed TEXT,
                distribution_fee TEXT, term TEXT, recoupment_notes TEXT,
                publishing_involved INTEGER NOT NULL DEFAULT 0,
                content_id_involved INTEGER NOT NULL DEFAULT 0,
                counsel_involved INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Reviewing',
                notes TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS desk_files (
                id TEXT PRIMARY KEY,
                lead_id TEXT,
                uploaded_by TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_type TEXT,
                category TEXT NOT NULL DEFAULT 'Other',
                is_internal INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS desk_activity (
                id TEXT PRIMARY KEY,
                user_id TEXT, user_name TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL, entity_id TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_desk_notes_lead
                ON desk_notes(lead_id);
            CREATE INDEX IF NOT EXISTS idx_desk_tasks_lead
                ON desk_tasks(lead_id);
            CREATE INDEX IF NOT EXISTS idx_desk_activity_created
                ON desk_activity(created_at);
        """)


# --- desk users -------------------------------------------------------------

def get_user_by_email(email):
    email = (email or "").strip().lower()
    if not email:
        return None
    with get_db() as db:
        row = db.execute("SELECT * FROM desk_users WHERE lower(email) = ?",
                         (email,)).fetchone()
    return dict(row) if row else None


def ensure_owner(email, name):
    """An app owner is always a desk Owner. Idempotent."""
    existing = get_user_by_email(email)
    if existing:
        if existing["role"] != "owner" or existing["status"] != "active":
            with get_db() as db:
                db.execute("UPDATE desk_users SET role='owner', "
                           "status='active' WHERE id = ?", (existing["id"],))
            existing = get_user_by_email(email)
        return existing
    with get_db() as db:
        db.execute("INSERT INTO desk_users (id, email, name, role, status, "
                   "created_at) VALUES (?, ?, ?, 'owner', 'active', ?)",
                   (_new_id(), email.strip().lower(), name or "Owner", _now()))
    return get_user_by_email(email)


def touch_login(user_id):
    with get_db() as db:
        db.execute("UPDATE desk_users SET last_login = ? WHERE id = ?",
                   (_now(), user_id))


def list_users():
    with get_db() as db:
        rows = db.execute("SELECT * FROM desk_users ORDER BY "
                          "CASE role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 "
                          "WHEN 'member' THEN 2 ELSE 3 END, name").fetchall()
    return [dict(r) for r in rows]


def add_user(email, name, role):
    if role not in ROLES:
        raise ValueError("unknown role")
    with get_db() as db:
        db.execute("INSERT INTO desk_users (id, email, name, role, status, "
                   "created_at) VALUES (?, ?, ?, ?, 'active', ?)",
                   (_new_id(), (email or "").strip().lower() or None,
                    name.strip(), role, _now()))


def set_user_role(user_id, role):
    if role not in ROLES:
        raise ValueError("unknown role")
    with get_db() as db:
        db.execute("UPDATE desk_users SET role = ? WHERE id = ?",
                   (role, user_id))


def set_user_status(user_id, status):
    with get_db() as db:
        db.execute("UPDATE desk_users SET status = ? WHERE id = ?",
                   ("active" if status == "active" else "disabled", user_id))


def set_user_email(user_id, email):
    with get_db() as db:
        db.execute("UPDATE desk_users SET email = ? WHERE id = ?",
                   ((email or "").strip().lower() or None, user_id))


def remove_user(user_id):
    with get_db() as db:
        db.execute("DELETE FROM desk_users WHERE id = ?", (user_id,))


# --- leads ------------------------------------------------------------------

def _lead_from_row(row):
    lead = dict(row)
    lead["opportunity_types"] = _load(lead.get("opportunity_types"))
    lead["tags"] = _load(lead.get("tags"))
    return lead


def create_lead(fields, opportunity_types, tags, actor):
    lead_id = _new_id()
    now = _now()
    columns = {k: (fields.get(k) or "").strip() for k, _ in LEAD_TEXT_FIELDS}
    columns["role"] = fields.get("role") or "Other"
    columns["pipeline_stage"] = (fields.get("pipeline_stage")
                                 if fields.get("pipeline_stage")
                                 in PIPELINE_STAGES else "New Lead")
    columns["priority"] = (fields.get("priority")
                           if fields.get("priority") in PRIORITIES
                           else "Medium")
    columns["lead_source"] = fields.get("lead_source") or "Manual entry"
    columns["assigned_to"] = fields.get("assigned_to") or ""
    names = ", ".join("%s" % c for c in columns)
    marks = ", ".join("?" for _ in columns)
    with get_db() as db:
        db.execute(
            "INSERT INTO desk_leads (id, %s, opportunity_types, tags, "
            "stage_changed_at, created_at, updated_at) "
            "VALUES (?, %s, ?, ?, ?, ?, ?)" % (names, marks),
            [lead_id] + list(columns.values())
            + [_dump(opportunity_types), _dump(tags), now, now, now])
    log_activity(actor, "lead_created", "lead", lead_id,
                 {"artist": columns["artist_name"]})
    return lead_id


def update_lead(lead_id, fields, opportunity_types, tags, actor):
    lead = get_lead(lead_id)
    if lead is None:
        return False
    columns = {k: (fields.get(k) or "").strip() for k, _ in LEAD_TEXT_FIELDS}
    columns["role"] = fields.get("role") or lead["role"] or "Other"
    columns["priority"] = (fields.get("priority")
                           if fields.get("priority") in PRIORITIES
                           else lead["priority"])
    columns["lead_source"] = fields.get("lead_source") or lead["lead_source"]
    columns["assigned_to"] = fields.get("assigned_to") or ""
    sets = ", ".join("%s = ?" % c for c in columns)
    with get_db() as db:
        db.execute(
            "UPDATE desk_leads SET %s, opportunity_types = ?, tags = ?, "
            "updated_at = ? WHERE id = ?" % sets,
            list(columns.values())
            + [_dump(opportunity_types), _dump(tags), _now(), lead_id])
    log_activity(actor, "lead_edited", "lead", lead_id,
                 {"artist": columns["artist_name"]})
    return True


def set_stage(lead_id, stage, actor):
    if stage not in PIPELINE_STAGES:
        return False
    lead = get_lead(lead_id)
    if lead is None:
        return False
    with get_db() as db:
        db.execute("UPDATE desk_leads SET pipeline_stage = ?, "
                   "stage_changed_at = ?, updated_at = ? WHERE id = ?",
                   (stage, _now(), _now(), lead_id))
    log_activity(actor, "stage_changed", "lead", lead_id,
                 {"from": lead["pipeline_stage"], "to": stage})
    return True


def set_follow_up(lead_id, date, owner, reason, status, actor):
    with get_db() as db:
        db.execute("UPDATE desk_leads SET follow_up_date = ?, "
                   "follow_up_owner = ?, follow_up_reason = ?, "
                   "follow_up_status = ?, updated_at = ? WHERE id = ?",
                   ((date or "").strip(), (owner or "").strip(),
                    (reason or "").strip(), (status or "").strip(),
                    _now(), lead_id))
    log_activity(actor, "follow_up_set", "lead", lead_id, {"date": date or ""})


def delete_lead(lead_id, actor):
    lead = get_lead(lead_id)
    if lead is None:
        return False
    with get_db() as db:
        for table in ("desk_notes", "desk_tasks", "desk_deals", "desk_files",
                      "desk_events"):
            db.execute("DELETE FROM %s WHERE lead_id = ?" % table, (lead_id,))
        db.execute("DELETE FROM desk_leads WHERE id = ?", (lead_id,))
    log_activity(actor, "lead_deleted", "lead", lead_id,
                 {"artist": lead["artist_name"]})
    return True


def get_lead(lead_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM desk_leads WHERE id = ?",
                         (lead_id,)).fetchone()
    return _lead_from_row(row) if row else None


def list_leads(search=None, stage=None, priority=None, assigned=None,
               source=None, opportunity=None, tag=None, quick=None,
               my_name=None):
    """Filtered lead list. Search is a LIKE across the fields people
    actually remember; notes are searched too so a phrase from a call is
    enough to find the artist again."""
    where, params = [], []
    if stage:
        where.append("pipeline_stage = ?"); params.append(stage)
    if priority:
        where.append("priority = ?"); params.append(priority)
    if assigned:
        where.append("assigned_to = ?"); params.append(assigned)
    if source:
        where.append("lead_source = ?"); params.append(source)
    if opportunity:
        where.append("opportunity_types LIKE ?")
        params.append("%%%s%%" % opportunity)
    if tag:
        where.append("tags LIKE ?"); params.append("%%%s%%" % tag)
    if search:
        like = "%%%s%%" % search.strip()
        where.append(
            "(artist_name LIKE ? OR contact_name LIKE ? OR city LIKE ? "
            "OR genre LIKE ? OR manager_name LIKE ? "
            "OR current_distributor LIKE ? OR tags LIKE ? "
            "OR id IN (SELECT lead_id FROM desk_notes WHERE body LIKE ?) "
            "OR id IN (SELECT lead_id FROM desk_tasks WHERE title LIKE ?))")
        params.extend([like] * 9)

    now = datetime.now(timezone.utc)
    if quick == "week":
        where.append("created_at >= ?")
        params.append((now - timedelta(days=7)).isoformat(timespec="seconds"))
    elif quick == "month":
        where.append("created_at >= ?")
        params.append((now - timedelta(days=31)).isoformat(timespec="seconds"))
    elif quick == "mine" and my_name:
        where.append("assigned_to = ?"); params.append(my_name)
    elif quick == "high":
        where.append("priority IN ('High', 'Urgent')")
    elif quick == "followup":
        where.append("(follow_up_date != '' AND follow_up_date IS NOT NULL "
                     "AND follow_up_date <= ?)")
        params.append(now.date().isoformat())
    elif quick == "deal":
        where.append("pipeline_stage IN ('Offer / Terms Drafting', "
                     "'Contract Sent', 'Contract Signed')")
    elif quick == "dormant":
        where.append("(pipeline_stage = 'Dormant' OR updated_at < ?)")
        params.append((now - timedelta(days=30)).isoformat(timespec="seconds"))

    sql = "SELECT * FROM desk_leads"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC"
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    return [_lead_from_row(r) for r in rows]


# --- notes ------------------------------------------------------------------

_MENTION = re.compile(r"@(LJ|Warren|Jovan)\b", re.IGNORECASE)


def mentions_in(body):
    """Case-normalized team names mentioned in a note body."""
    found = []
    for match in _MENTION.finditer(body or ""):
        for name in TEAM_NAMES:
            if name.lower() == match.group(1).lower() and name not in found:
                found.append(name)
    return found


def add_note(lead_id, actor, note_type, body, next_step=None,
             follow_up_date=None, is_pinned=False):
    note_id = _new_id()
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO desk_notes (id, lead_id, author_id, author_name, "
            "note_type, body, is_pinned, is_internal, next_step, "
            "follow_up_date, tagged_users, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)",
            (note_id, lead_id, actor["id"], actor["name"],
             note_type if note_type in NOTE_TYPES else "General Note",
             body, 1 if is_pinned else 0, (next_step or "").strip(),
             (follow_up_date or "").strip(), _dump(mentions_in(body)),
             now, now))
        db.execute("UPDATE desk_leads SET updated_at = ? WHERE id = ?",
                   (now, lead_id))
    log_activity(actor, "note_added", "note", note_id, {"lead": lead_id})
    return note_id


def toggle_pin(note_id, actor):
    with get_db() as db:
        row = db.execute("SELECT is_pinned FROM desk_notes WHERE id = ?",
                         (note_id,)).fetchone()
        if row is None:
            return False
        db.execute("UPDATE desk_notes SET is_pinned = ?, updated_at = ? "
                   "WHERE id = ?",
                   (0 if row["is_pinned"] else 1, _now(), note_id))
    return True


def list_notes(lead_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM desk_notes WHERE lead_id = ? "
            "ORDER BY is_pinned DESC, created_at DESC", (lead_id,)).fetchall()
    notes = []
    for row in rows:
        note = dict(row)
        note["tagged_users"] = _load(note.get("tagged_users"))
        notes.append(note)
    return notes


# --- tasks ------------------------------------------------------------------

def add_task(actor, title, description="", lead_id=None, assigned_to="",
             due_date="", priority="Medium", category="Other"):
    task_id = _new_id()
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO desk_tasks (id, lead_id, title, description, "
            "assigned_to, created_by, due_date, priority, status, category, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'To Do', ?, ?, ?)",
            (task_id, lead_id, title.strip(), (description or "").strip(),
             (assigned_to or "").strip(), actor["name"],
             (due_date or "").strip(),
             priority if priority in PRIORITIES else "Medium",
             category if category in TASK_CATEGORIES else "Other", now, now))
    log_activity(actor, "task_created", "task", task_id, {"title": title})
    return task_id


def set_task_status(task_id, status, actor):
    if status not in TASK_STATUSES:
        return False
    with get_db() as db:
        row = db.execute("SELECT title FROM desk_tasks WHERE id = ?",
                         (task_id,)).fetchone()
        if row is None:
            return False
        db.execute("UPDATE desk_tasks SET status = ?, updated_at = ? "
                   "WHERE id = ?", (status, _now(), task_id))
    if status == "Complete":
        log_activity(actor, "task_completed", "task", task_id,
                     {"title": row["title"]})
    return True


def list_tasks(view=None, my_name=None, lead_id=None):
    where, params = [], []
    today = datetime.now(timezone.utc).date().isoformat()
    if lead_id:
        where.append("lead_id = ?"); params.append(lead_id)
    if view == "my" and my_name:
        where.append("assigned_to = ?"); params.append(my_name)
        where.append("status NOT IN ('Complete', 'Cancelled')")
    elif view == "overdue":
        where.append("due_date != '' AND due_date < ? "
                     "AND status NOT IN ('Complete', 'Cancelled')")
        params.append(today)
    elif view == "week":
        week = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
        where.append("due_date != '' AND due_date <= ? "
                     "AND status NOT IN ('Complete', 'Cancelled')")
        params.append(week)
    elif view == "done":
        where.append("status = 'Complete'")
    elif view == "team" or view is None:
        pass
    sql = "SELECT * FROM desk_tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CASE WHEN due_date = '' THEN 1 ELSE 0 END, due_date"
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# --- events -----------------------------------------------------------------

def add_event(actor, event_name, event_type, date="", time="", venue="",
              city="", attendees=None, notes="", follow_up_needed=False,
              assigned_to="", lead_id=None):
    event_id = _new_id()
    with get_db() as db:
        db.execute(
            "INSERT INTO desk_events (id, lead_id, event_name, event_type, "
            "date, time, venue, city, attendees, notes, follow_up_needed, "
            "assigned_to, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?)",
            (event_id, lead_id, event_name.strip(),
             event_type if event_type in EVENT_TYPES else "Other",
             (date or "").strip(), (time or "").strip(),
             (venue or "").strip(), (city or "").strip(),
             _dump(attendees or []), (notes or "").strip(),
             1 if follow_up_needed else 0, (assigned_to or "").strip(),
             _now()))
    log_activity(actor, "event_created", "event", event_id,
                 {"name": event_name})
    return event_id


def list_events(lead_id=None):
    sql = ("SELECT desk_events.*, desk_leads.artist_name FROM desk_events "
           "LEFT JOIN desk_leads ON desk_leads.id = desk_events.lead_id")
    params = []
    if lead_id:
        sql += " WHERE desk_events.lead_id = ?"
        params.append(lead_id)
    sql += (" ORDER BY CASE WHEN desk_events.date = '' THEN 1 ELSE 0 END, "
            "desk_events.date")
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["attendees"] = _load(event.get("attendees"))
        events.append(event)
    return events


# --- deals ------------------------------------------------------------------

def add_deal(actor, lead_id, deal_type, **fields):
    deal_id = _new_id()
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO desk_deals (id, lead_id, deal_type, "
            "estimated_value, advance_discussed, distribution_fee, term, "
            "recoupment_notes, publishing_involved, content_id_involved, "
            "counsel_involved, status, notes, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (deal_id, lead_id,
             deal_type if deal_type in DEAL_TYPES else "Other",
             (fields.get("estimated_value") or "").strip(),
             (fields.get("advance_discussed") or "").strip(),
             (fields.get("distribution_fee") or "").strip(),
             (fields.get("term") or "").strip(),
             (fields.get("recoupment_notes") or "").strip(),
             1 if fields.get("publishing_involved") else 0,
             1 if fields.get("content_id_involved") else 0,
             1 if fields.get("counsel_involved") else 0,
             (fields.get("status") if fields.get("status") in DEAL_STATUSES
              else "Reviewing"),
             (fields.get("notes") or "").strip(), now, now))
    log_activity(actor, "deal_created", "deal", deal_id, {"lead": lead_id})
    return deal_id


def set_deal_status(deal_id, status, actor):
    if status not in DEAL_STATUSES:
        return False
    with get_db() as db:
        row = db.execute("SELECT status FROM desk_deals WHERE id = ?",
                         (deal_id,)).fetchone()
        if row is None:
            return False
        db.execute("UPDATE desk_deals SET status = ?, updated_at = ? "
                   "WHERE id = ?", (status, _now(), deal_id))
    log_activity(actor, "deal_status_changed", "deal", deal_id,
                 {"from": row["status"], "to": status})
    return True


def list_deals(lead_id=None):
    sql = ("SELECT desk_deals.*, desk_leads.artist_name FROM desk_deals "
           "LEFT JOIN desk_leads ON desk_leads.id = desk_deals.lead_id")
    params = []
    if lead_id:
        sql += " WHERE desk_deals.lead_id = ?"
        params.append(lead_id)
    sql += " ORDER BY desk_deals.updated_at DESC"
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# --- files ------------------------------------------------------------------

def add_file(actor, file_name, file_path, file_type, category,
             lead_id=None):
    file_id = _new_id()
    with get_db() as db:
        db.execute(
            "INSERT INTO desk_files (id, lead_id, uploaded_by, file_name, "
            "file_path, file_type, category, is_internal, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (file_id, lead_id, actor["name"], file_name, file_path,
             file_type or "",
             category if category in FILE_CATEGORIES else "Other", _now()))
    log_activity(actor, "file_uploaded", "file", file_id,
                 {"name": file_name, "lead": lead_id or ""})
    return file_id


def get_file(file_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM desk_files WHERE id = ?",
                         (file_id,)).fetchone()
    return dict(row) if row else None


def list_files(lead_id=None):
    sql = ("SELECT desk_files.*, desk_leads.artist_name FROM desk_files "
           "LEFT JOIN desk_leads ON desk_leads.id = desk_files.lead_id")
    params = []
    if lead_id:
        sql += " WHERE desk_files.lead_id = ?"
        params.append(lead_id)
    sql += " ORDER BY desk_files.created_at DESC"
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# --- activity ---------------------------------------------------------------

def log_activity(actor, action, entity_type, entity_id, metadata=None):
    with get_db() as db:
        db.execute(
            "INSERT INTO desk_activity (id, user_id, user_name, action, "
            "entity_type, entity_id, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (_new_id(), (actor or {}).get("id"),
             (actor or {}).get("name") or "system", action, entity_type,
             entity_id, json.dumps(metadata or {}), _now()))


def list_activity(limit=200):
    with get_db() as db:
        rows = db.execute("SELECT * FROM desk_activity "
                          "ORDER BY created_at DESC LIMIT ?",
                          (limit,)).fetchall()
    entries = []
    for row in rows:
        entry = dict(row)
        try:
            entry["metadata"] = json.loads(entry.get("metadata") or "{}")
        except ValueError:
            entry["metadata"] = {}
        entries.append(entry)
    return entries


# --- dashboard --------------------------------------------------------------

def dashboard_counts():
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    week = (now + timedelta(days=7)).date().isoformat()
    with get_db() as db:
        def one(sql, *params):
            return db.execute(sql, params).fetchone()[0]
        return {
            "new_leads": one("SELECT COUNT(*) FROM desk_leads "
                             "WHERE pipeline_stage = 'New Lead'"),
            "active_conversations": one(
                "SELECT COUNT(*) FROM desk_leads WHERE pipeline_stage IN "
                "('Contacted', 'Discovery Scheduled', 'Discovery Complete', "
                "'Needs Internal Review')"),
            "priority_opportunities": one(
                "SELECT COUNT(*) FROM desk_leads WHERE priority IN "
                "('High', 'Urgent') AND pipeline_stage NOT IN "
                "('Passed', 'Dormant')"),
            "upcoming_follow_ups": one(
                "SELECT COUNT(*) FROM desk_leads WHERE follow_up_date != '' "
                "AND follow_up_date IS NOT NULL AND follow_up_date BETWEEN "
                "? AND ?", today, week),
            "open_tasks": one("SELECT COUNT(*) FROM desk_tasks WHERE status "
                              "NOT IN ('Complete', 'Cancelled')"),
            "catalog_opportunities": one(
                "SELECT COUNT(*) FROM desk_leads WHERE (opportunity_types "
                "LIKE '%Catalog%' OR tags LIKE '%Catalog Opportunity%') "
                "AND pipeline_stage NOT IN ('Passed', 'Dormant')"),
            "partnership_deals": one(
                "SELECT COUNT(*) FROM desk_deals WHERE status NOT IN "
                "('Signed', 'Passed')"),
        }


def todays_follow_ups():
    today = datetime.now(timezone.utc).date().isoformat()
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM desk_leads WHERE follow_up_date != '' AND "
            "follow_up_date IS NOT NULL AND follow_up_date <= ? "
            "AND pipeline_stage NOT IN ('Passed', 'Dormant') "
            "ORDER BY follow_up_date", (today,)).fetchall()
    return [_lead_from_row(r) for r in rows]


def recently_updated(limit=5):
    with get_db() as db:
        rows = db.execute("SELECT * FROM desk_leads ORDER BY updated_at DESC "
                          "LIMIT ?", (limit,)).fetchall()
    return [_lead_from_row(r) for r in rows]


def warnings():
    """The four momentum leaks the brief names, computed rather than
    remembered."""
    now = datetime.now(timezone.utc)
    d7 = (now - timedelta(days=7)).isoformat(timespec="seconds")
    d14 = (now - timedelta(days=14)).isoformat(timespec="seconds")
    found = []
    with get_db() as db:
        for row in db.execute(
                "SELECT * FROM desk_leads WHERE priority IN ('High', "
                "'Urgent') AND (follow_up_date = '' OR follow_up_date IS "
                "NULL) AND pipeline_stage NOT IN ('Passed', 'Dormant')"):
            found.append((dict(row), "High-priority lead with no next "
                                     "follow-up"))
        for row in db.execute(
                "SELECT * FROM desk_leads WHERE updated_at < ? AND "
                "pipeline_stage NOT IN ('Passed', 'Dormant')", (d14,)):
            found.append((dict(row), "No activity for 14+ days"))
        for row in db.execute(
                "SELECT * FROM desk_leads WHERE pipeline_stage IN "
                "('Contract Sent', 'Offer / Terms Drafting') AND "
                "updated_at < ?", (d7,)):
            found.append((dict(row), "Contract stage with no update for "
                                     "7+ days"))
        for row in db.execute(
                "SELECT * FROM desk_leads WHERE pipeline_stage = "
                "'Discovery Complete' AND stage_changed_at < ?", (d7,)):
            found.append((dict(row), "Discovery complete but no decision "
                                     "logged"))
    return found


# --- seed -------------------------------------------------------------------

def seed_if_empty():
    """Five sample leads and the three team names, once. Every sample is
    tagged Sample and uses an obviously invented name, so it can be
    recognized and deleted without ceremony."""
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM desk_leads").fetchone()[0]:
            return False
        have_names = {r["name"] for r in
                      db.execute("SELECT name FROM desk_users")}
    for name in ("LJ", "Warren", "Jovan"):
        if name not in have_names:
            with get_db() as db:
                db.execute(
                    "INSERT INTO desk_users (id, email, name, role, status, "
                    "created_at) VALUES (?, NULL, ?, 'member', 'active', ?)",
                    (_new_id(), name, _now()))

    system = {"id": None, "name": "seed"}
    samples = [
        ({"artist_name": "Marisol Vega (sample)", "contact_name": "Marisol Vega",
          "role": "Artist", "city": "Charlotte", "state": "NC",
          "country": "USA", "genre": "Latin pop",
          "current_distributor": "Self-released",
          "priority": "High", "lead_source": "Event/show",
          "assigned_to": "LJ"},
         ["Distribution"], ["Sample", "Has Traction"]),
        ({"artist_name": "Ferryman Mgmt (sample)", "contact_name": "Dee Okafor",
          "role": "Manager", "city": "Atlanta", "state": "GA",
          "country": "USA", "genre": "R&B",
          "manager_name": "Dee Okafor", "priority": "Medium",
          "lead_source": "Referral", "assigned_to": "Warren"},
         ["Development", "Partnership"], ["Sample", "Manager Connected"]),
        ({"artist_name": "Cold Furnace Beats (sample)",
          "contact_name": "Ty Renner", "role": "Producer",
          "city": "Memphis", "state": "TN", "country": "USA",
          "genre": "Hip-hop", "catalog_size": "300+ instrumentals",
          "splits_issues": "Several uncredited placements",
          "priority": "High", "lead_source": "Industry contact",
          "assigned_to": "Jovan"},
         ["Catalog Recovery", "Royalty Sweep"],
         ["Sample", "Catalog Opportunity", "Needs Royalty Sweep"]),
        ({"artist_name": "Gravel Road Records (sample)",
          "contact_name": "June Halloway", "role": "Label",
          "city": "Nashville", "state": "TN", "country": "USA",
          "genre": "Americana", "catalog_size": "12 artists",
          "priority": "Medium", "lead_source": "Partner intro",
          "assigned_to": "LJ"},
         ["Distribution", "Partnership"], ["Sample"]),
        ({"artist_name": "Northbank Audio (sample)",
          "contact_name": "Priya Chandran", "role": "Investor",
          "city": "Chicago", "state": "IL", "country": "USA",
          "priority": "Urgent", "lead_source": "Manager outreach",
          "assigned_to": "Warren"},
         ["Growth Capital", "Deal Desk"], ["Sample", "Needs Deal Review"]),
    ]
    for fields, opportunities, tags in samples:
        create_lead(fields, opportunities, tags, system)
    return True
