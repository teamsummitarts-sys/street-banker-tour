"""Press Desk data layer — media contacts, announcements, pitches and
the coverage they produce.

Per-artist and private. Everything here is keyed by user_id and read
only through press_desk.py, which resolves the artist from the session
before any of these functions are reached.

Four decisions worth stating, because they shape everything else:

  One token per recipient, not per artist. The EPK already has a share
  link, but `epk_shares` is keyed by user_id - one token, overwritten
  whenever it is regenerated. A press desk needs to know that Nightdrive
  opened the pitch and Indie Wave did not, so each recipient gets its own
  token in `press_recipients` and its own public page. Nothing here
  touches the EPK's own token.

  Preparing and sending are separate. A pitch is built, personalised and
  saved first; sending is a second, explicit act. That is not ceremony -
  it means the desk is fully useful with no email provider attached at
  all, because the artist can send the prepared messages from their own
  inbox, which is where a reply to a journalist should land anyway.

  Do-not-contact is enforced here, not in the template. A contact marked
  do-not-contact is dropped while recipients are being built, so no route
  and no form can pitch them by accident.

  Nothing is invented. There is no seeded example contact and no sample
  outlet: an empty desk renders empty. A press list that looks populated
  before the artist has added anyone teaches them to trust numbers that
  are not theirs.
"""
import csv
import io
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from db import get_db

# --- vocabularies -----------------------------------------------------------

CONTACT_ROLES = ["Writer", "Editor", "Blogger", "Podcaster", "Radio",
                 "Playlist curator", "Photographer", "Publicist", "Other"]

# active is the only status that can be pitched. The other two are the
# two ways a contact stops being pitchable, and they are different: one
# is a decision, the other is a fact about the address.
CONTACT_STATUSES = ["active", "do-not-contact", "bounced"]
CONTACT_STATUS_LABELS = {
    "active": "Active",
    "do-not-contact": "Do not contact",
    "bounced": "Bounced",
}

RELEASE_KINDS = ["Single", "Album / EP", "Music video", "Tour dates",
                 "Signing / deal", "Award / milestone", "General announcement"]

RELEASE_STATUSES = ["draft", "ready", "sent"]

# The lifecycle of one pitched recipient. `prepared` means the message
# exists and has not left; `sent` means it went, by whichever route.
RECIPIENT_STATUSES = ["prepared", "sent", "opened", "replied", "covered",
                      "passed", "failed"]
RECIPIENT_LABELS = {
    "prepared": "Prepared",
    "sent": "Sent",
    "opened": "Opened",
    "replied": "Replied",
    "covered": "Covered",
    "passed": "Passed",
    "failed": "Failed to send",
}

COVERAGE_KINDS = ["Review", "Feature", "Interview", "Premiere", "Mention",
                  "Playlist add", "Radio play", "Other"]

# How a pitch leaves the building.
MODE_OWN_INBOX = "own_inbox"
MODE_PLATFORM = "platform"
SEND_MODES = [MODE_OWN_INBOX, MODE_PLATFORM]

# A single pitch cannot exceed this. Not a technical limit - a brake. A
# press list worth having is small and chosen; a four-figure send is the
# behaviour that gets a sending domain blocked.
MAX_RECIPIENTS = 100

# The only placeholders the personaliser understands. Deliberately few:
# every one of them resolves from data the desk already holds, so a
# prepared message can never contain an unfilled blank.
PLACEHOLDERS = [
    ("{name}", "The contact's first name"),
    ("{outlet}", "Their publication or show"),
    ("{artist}", "Your artist name"),
    ("{title}", "The announcement headline"),
    ("{link}", "That contact's own tracked link"),
]

_PLACEHOLDER_RE = re.compile(
    r"\{(name|outlet|artist|title|link)\}")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id():
    return uuid.uuid4().hex


def _token():
    return uuid.uuid4().hex[:20]


def _dump(value):
    return json.dumps(value or [])


def _load(text):
    try:
        value = json.loads(text or "[]")
        return value if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


# --- schema -----------------------------------------------------------------

def init_press():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS press_contacts (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                outlet TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'Writer',
                email TEXT NOT NULL DEFAULT '',
                beat TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                socials TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                source TEXT NOT NULL DEFAULT '',
                last_contacted TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS press_releases (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'Single',
                headline TEXT NOT NULL DEFAULT '',
                subhead TEXT NOT NULL DEFAULT '',
                dateline TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                quote TEXT NOT NULL DEFAULT '',
                quote_source TEXT NOT NULL DEFAULT '',
                boilerplate TEXT NOT NULL DEFAULT '',
                contact_name TEXT NOT NULL DEFAULT '',
                contact_email TEXT NOT NULL DEFAULT '',
                embargo_until TEXT NOT NULL DEFAULT '',
                release_date TEXT NOT NULL DEFAULT '',
                listen_url TEXT NOT NULL DEFAULT '',
                epk_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS press_pitches (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                release_id TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                body_template TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT 'own_inbox',
                status TEXT NOT NULL DEFAULT 'draft',
                created TEXT NOT NULL,
                sent_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS press_recipients (
                id TEXT PRIMARY KEY,
                pitch_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                contact_id TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                subject TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'prepared',
                sent_at TEXT NOT NULL DEFAULT '',
                opened_at TEXT NOT NULL DEFAULT '',
                last_opened TEXT NOT NULL DEFAULT '',
                open_count INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS press_coverage (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                release_id TEXT NOT NULL DEFAULT '',
                contact_id TEXT NOT NULL DEFAULT '',
                outlet TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                headline TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'Review',
                published_on TEXT NOT NULL DEFAULT '',
                quote TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_press_contacts_user
                ON press_contacts(user_id);
            CREATE INDEX IF NOT EXISTS idx_press_releases_user
                ON press_releases(user_id);
            CREATE INDEX IF NOT EXISTS idx_press_recipients_pitch
                ON press_recipients(pitch_id);
            CREATE INDEX IF NOT EXISTS idx_press_coverage_user
                ON press_coverage(user_id);
        """)


# --- contacts ---------------------------------------------------------------

def _contact_row(row):
    contact = dict(row)
    contact["tags"] = _load(contact.get("tags"))
    return contact


def add_contact(user_id, fields, tags=None):
    contact_id = _new_id()
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO press_contacts (id, user_id, name, outlet, role, "
            "email, beat, city, country, website, socials, notes, tags, "
            "status, source, created, updated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (contact_id, user_id,
             (fields.get("name") or "").strip()[:120],
             (fields.get("outlet") or "").strip()[:120],
             fields.get("role") if fields.get("role") in CONTACT_ROLES
             else "Writer",
             (fields.get("email") or "").strip().lower()[:200],
             (fields.get("beat") or "").strip()[:200],
             (fields.get("city") or "").strip()[:80],
             (fields.get("country") or "").strip()[:80],
             (fields.get("website") or "").strip()[:300],
             (fields.get("socials") or "").strip()[:200],
             (fields.get("notes") or "").strip()[:2000],
             _dump(tags or []),
             fields.get("status") if fields.get("status") in CONTACT_STATUSES
             else "active",
             (fields.get("source") or "").strip()[:120], now, now))
    return contact_id


def update_contact(user_id, contact_id, fields, tags=None):
    existing = get_contact(user_id, contact_id)
    if existing is None:
        return False
    with get_db() as db:
        db.execute(
            "UPDATE press_contacts SET name=?, outlet=?, role=?, email=?, "
            "beat=?, city=?, country=?, website=?, socials=?, notes=?, "
            "tags=?, status=?, source=?, updated=? "
            "WHERE id=? AND user_id=?",
            ((fields.get("name") or "").strip()[:120],
             (fields.get("outlet") or "").strip()[:120],
             fields.get("role") if fields.get("role") in CONTACT_ROLES
             else existing["role"],
             (fields.get("email") or "").strip().lower()[:200],
             (fields.get("beat") or "").strip()[:200],
             (fields.get("city") or "").strip()[:80],
             (fields.get("country") or "").strip()[:80],
             (fields.get("website") or "").strip()[:300],
             (fields.get("socials") or "").strip()[:200],
             (fields.get("notes") or "").strip()[:2000],
             _dump(tags or []),
             fields.get("status") if fields.get("status") in CONTACT_STATUSES
             else existing["status"],
             (fields.get("source") or "").strip()[:120],
             _now(), contact_id, user_id))
    return True


def set_contact_status(user_id, contact_id, status):
    if status not in CONTACT_STATUSES:
        return False
    with get_db() as db:
        db.execute("UPDATE press_contacts SET status=?, updated=? "
                   "WHERE id=? AND user_id=?",
                   (status, _now(), contact_id, user_id))
    return True


def delete_contact(user_id, contact_id):
    with get_db() as db:
        db.execute("DELETE FROM press_contacts WHERE id=? AND user_id=?",
                   (contact_id, user_id))
    return True


def get_contact(user_id, contact_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM press_contacts "
                         "WHERE id=? AND user_id=?",
                         (contact_id, user_id)).fetchone()
    return _contact_row(row) if row else None


def list_contacts(user_id, search="", role="", status="", tag=""):
    where = ["user_id = ?"]
    params = [user_id]
    if role:
        where.append("role = ?"); params.append(role)
    if status:
        where.append("status = ?"); params.append(status)
    if tag:
        where.append("tags LIKE ?"); params.append("%%%s%%" % tag)
    if search:
        like = "%%%s%%" % search.strip()
        where.append("(name LIKE ? OR outlet LIKE ? OR email LIKE ? "
                     "OR beat LIKE ? OR city LIKE ? OR notes LIKE ?)")
        params.extend([like] * 6)
    sql = ("SELECT * FROM press_contacts WHERE %s ORDER BY outlet, name"
           % " AND ".join(where))
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    return [_contact_row(r) for r in rows]


def import_contacts_csv(user_id, text):
    """Bulk add from pasted CSV. Returns (added, skipped, problems).

    Skips rather than fails: one malformed row in a pasted list should
    not throw away the other forty. Every skip is reported with its line
    number so the artist can see exactly what did not go in - a silent
    partial import is how a press list quietly loses half a section.
    """
    added, skipped, problems = 0, 0, []
    existing = {c["email"] for c in list_contacts(user_id) if c["email"]}
    try:
        rows = list(csv.DictReader(io.StringIO(text.strip())))
    except (csv.Error, ValueError) as exc:
        return 0, 0, ["The file could not be read as CSV (%s)." % exc]
    if not rows:
        return 0, 0, ["No rows found. The first line must be a header."]

    for index, raw in enumerate(rows, start=2):
        row = {(k or "").strip().lower(): (v or "").strip()
               for k, v in raw.items() if k}
        name = row.get("name") or row.get("contact") or ""
        email = (row.get("email") or "").lower()
        outlet = row.get("outlet") or row.get("publication") or ""
        if not name and not outlet:
            skipped += 1
            problems.append("Line %d: no name and no outlet." % index)
            continue
        if email and "@" not in email:
            skipped += 1
            problems.append("Line %d: %r is not an email address." % (index, email))
            continue
        if email and email in existing:
            skipped += 1
            problems.append("Line %d: %s is already on the list." % (index, email))
            continue
        role = (row.get("role") or "").title()
        add_contact(user_id, {
            "name": name or outlet, "outlet": outlet,
            "role": role if role in CONTACT_ROLES else "Writer",
            "email": email, "beat": row.get("beat") or row.get("genre") or "",
            "city": row.get("city") or "", "country": row.get("country") or "",
            "website": row.get("website") or row.get("url") or "",
            "notes": row.get("notes") or "", "source": "CSV import",
        })
        if email:
            existing.add(email)
        added += 1
    return added, skipped, problems


# --- announcements ----------------------------------------------------------

def create_release(user_id, fields):
    release_id = _new_id()
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO press_releases (id, user_id, title, kind, headline, "
            "subhead, dateline, body, quote, quote_source, boilerplate, "
            "contact_name, contact_email, embargo_until, release_date, "
            "listen_url, epk_url, status, created, updated) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (release_id, user_id,
             (fields.get("title") or "Untitled announcement").strip()[:200],
             fields.get("kind") if fields.get("kind") in RELEASE_KINDS
             else "Single",
             (fields.get("headline") or "").strip()[:300],
             (fields.get("subhead") or "").strip()[:300],
             (fields.get("dateline") or "").strip()[:120],
             (fields.get("body") or "").strip()[:8000],
             (fields.get("quote") or "").strip()[:1000],
             (fields.get("quote_source") or "").strip()[:120],
             (fields.get("boilerplate") or "").strip()[:2000],
             (fields.get("contact_name") or "").strip()[:120],
             (fields.get("contact_email") or "").strip()[:200],
             (fields.get("embargo_until") or "").strip()[:10],
             (fields.get("release_date") or "").strip()[:10],
             (fields.get("listen_url") or "").strip()[:400],
             (fields.get("epk_url") or "").strip()[:400],
             "draft", now, now))
    return release_id


def update_release(user_id, release_id, fields):
    existing = get_release(user_id, release_id)
    if existing is None:
        return False
    with get_db() as db:
        db.execute(
            "UPDATE press_releases SET title=?, kind=?, headline=?, subhead=?, "
            "dateline=?, body=?, quote=?, quote_source=?, boilerplate=?, "
            "contact_name=?, contact_email=?, embargo_until=?, release_date=?, "
            "listen_url=?, epk_url=?, status=?, updated=? "
            "WHERE id=? AND user_id=?",
            ((fields.get("title") or existing["title"]).strip()[:200],
             fields.get("kind") if fields.get("kind") in RELEASE_KINDS
             else existing["kind"],
             (fields.get("headline") or "").strip()[:300],
             (fields.get("subhead") or "").strip()[:300],
             (fields.get("dateline") or "").strip()[:120],
             (fields.get("body") or "").strip()[:8000],
             (fields.get("quote") or "").strip()[:1000],
             (fields.get("quote_source") or "").strip()[:120],
             (fields.get("boilerplate") or "").strip()[:2000],
             (fields.get("contact_name") or "").strip()[:120],
             (fields.get("contact_email") or "").strip()[:200],
             (fields.get("embargo_until") or "").strip()[:10],
             (fields.get("release_date") or "").strip()[:10],
             (fields.get("listen_url") or "").strip()[:400],
             (fields.get("epk_url") or "").strip()[:400],
             fields.get("status") if fields.get("status") in RELEASE_STATUSES
             else existing["status"],
             _now(), release_id, user_id))
    return True


def get_release(user_id, release_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM press_releases WHERE id=? AND user_id=?",
                         (release_id, user_id)).fetchone()
    return dict(row) if row else None


def get_release_any(release_id):
    """Owner-blind read, for the public page reached through a token.
    The token is the authorisation; the caller has already resolved it."""
    with get_db() as db:
        row = db.execute("SELECT * FROM press_releases WHERE id=?",
                         (release_id,)).fetchone()
    return dict(row) if row else None


def list_releases(user_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM press_releases WHERE user_id=? "
                          "ORDER BY updated DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_release(user_id, release_id):
    with get_db() as db:
        pitches = db.execute("SELECT id FROM press_pitches "
                             "WHERE release_id=? AND user_id=?",
                             (release_id, user_id)).fetchall()
        for pitch in pitches:
            db.execute("DELETE FROM press_recipients WHERE pitch_id=?",
                       (pitch["id"],))
        db.execute("DELETE FROM press_pitches WHERE release_id=? AND user_id=?",
                   (release_id, user_id))
        db.execute("DELETE FROM press_releases WHERE id=? AND user_id=?",
                   (release_id, user_id))
    return True


def embargo_active(release, today=None):
    """True while an embargo date is in the future. The public page shows
    the embargo rather than hiding the announcement: a journalist who
    followed the link is supposed to read it and hold it."""
    until = (release or {}).get("embargo_until") or ""
    if not until:
        return False
    today = today or datetime.now(timezone.utc).date().isoformat()
    return until > today


# --- personalisation --------------------------------------------------------

def personalise(text, values):
    """Replace only the five known placeholders. Anything else in braces
    is left exactly as typed, because it is prose and not a variable."""
    def swap(match):
        return str(values.get(match.group(1), "") or "")
    return _PLACEHOLDER_RE.sub(swap, text or "")


def first_name(name):
    return (name or "").strip().split(" ")[0] if name else ""


# --- pitches ----------------------------------------------------------------

def create_pitch(user_id, release_id, contact_ids, subject, body_template,
                 mode, artist_name, link_base):
    """Build one pitch and its per-recipient messages.

    Returns (pitch_id, prepared_count, skipped). `skipped` names every
    contact that was left out and why, because a recipient silently
    dropped from a press send is a pitch the artist thinks went out.
    """
    release = get_release(user_id, release_id)
    if release is None:
        return None, 0, [("", "That announcement no longer exists.")]

    pitch_id = _new_id()
    now = _now()
    prepared, skipped = 0, []

    with get_db() as db:
        db.execute(
            "INSERT INTO press_pitches (id, user_id, release_id, subject, "
            "body_template, mode, status, created) VALUES (?,?,?,?,?,?,?,?)",
            (pitch_id, user_id, release_id, (subject or "").strip()[:300],
             (body_template or "").strip()[:8000],
             mode if mode in SEND_MODES else MODE_OWN_INBOX, "draft", now))

    for contact_id in contact_ids[:MAX_RECIPIENTS]:
        contact = get_contact(user_id, contact_id)
        if contact is None:
            continue
        # Both of these are enforced here rather than in the form: a
        # checkbox can be forged, and an address that has already bounced
        # should not be retried by a second campaign.
        if contact["status"] == "do-not-contact":
            skipped.append((contact["name"], "marked do not contact"))
            continue
        if contact["status"] == "bounced":
            skipped.append((contact["name"], "address previously bounced"))
            continue
        if not contact["email"]:
            skipped.append((contact["name"], "no email address on file"))
            continue

        token = _token()
        values = {
            "name": first_name(contact["name"]) or contact["outlet"],
            "outlet": contact["outlet"],
            "artist": artist_name,
            "title": release["headline"] or release["title"],
            "link": "%s/press/%s" % (link_base.rstrip("/"), token),
        }
        with get_db() as db:
            db.execute(
                "INSERT INTO press_recipients (id, pitch_id, user_id, "
                "contact_id, token, subject, body, status, created) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (_new_id(), pitch_id, user_id, contact_id, token,
                 personalise(subject, values)[:300],
                 personalise(body_template, values)[:8000],
                 "prepared", now))
        prepared += 1

    if len(contact_ids) > MAX_RECIPIENTS:
        skipped.append(("", "%d contacts past the %d-per-pitch limit were "
                            "not included"
                        % (len(contact_ids) - MAX_RECIPIENTS, MAX_RECIPIENTS)))

    with get_db() as db:
        db.execute("UPDATE press_pitches SET status='prepared' WHERE id=?",
                   (pitch_id,))
    return pitch_id, prepared, skipped


def get_pitch(user_id, pitch_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM press_pitches WHERE id=? AND user_id=?",
                         (pitch_id, user_id)).fetchone()
    return dict(row) if row else None


def list_pitches(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT p.*, r.title AS release_title, r.headline AS release_headline,"
            " (SELECT COUNT(*) FROM press_recipients WHERE pitch_id = p.id)"
            "   AS recipients,"
            " (SELECT COUNT(*) FROM press_recipients WHERE pitch_id = p.id"
            "   AND open_count > 0) AS opens"
            " FROM press_pitches p"
            " LEFT JOIN press_releases r ON r.id = p.release_id"
            " WHERE p.user_id = ? ORDER BY p.created DESC",
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def pitch_recipients(user_id, pitch_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT pr.*, c.name AS contact_name, c.outlet AS outlet,"
            " c.email AS email, c.role AS role"
            " FROM press_recipients pr"
            " LEFT JOIN press_contacts c ON c.id = pr.contact_id"
            " WHERE pr.pitch_id = ? AND pr.user_id = ?"
            " ORDER BY c.outlet, c.name", (pitch_id, user_id)).fetchall()
    return [dict(r) for r in rows]


def delete_pitch(user_id, pitch_id):
    with get_db() as db:
        db.execute("DELETE FROM press_recipients WHERE pitch_id=? AND user_id=?",
                   (pitch_id, user_id))
        db.execute("DELETE FROM press_pitches WHERE id=? AND user_id=?",
                   (pitch_id, user_id))
    return True


def get_recipient(user_id, recipient_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM press_recipients "
                         "WHERE id=? AND user_id=?",
                         (recipient_id, user_id)).fetchone()
    return dict(row) if row else None


def get_recipient_by_token(token):
    with get_db() as db:
        row = db.execute("SELECT * FROM press_recipients WHERE token=?",
                         (token,)).fetchone()
    return dict(row) if row else None


def mark_sent(recipient_id, ok=True):
    now = _now()
    with get_db() as db:
        db.execute("UPDATE press_recipients SET status=?, sent_at=? WHERE id=?",
                   ("sent" if ok else "failed", now if ok else "", recipient_id))
        if ok:
            row = db.execute("SELECT contact_id, user_id FROM press_recipients "
                             "WHERE id=?", (recipient_id,)).fetchone()
            if row:
                db.execute("UPDATE press_contacts SET last_contacted=? "
                           "WHERE id=? AND user_id=?",
                           (now, row["contact_id"], row["user_id"]))
    return True


def mark_opened(token):
    """Log an open. Returns the recipient row when this was the FIRST
    open, and None otherwise - the caller uses that to notify once rather
    than on every refresh."""
    row = get_recipient_by_token(token)
    if row is None:
        return None
    now = _now()
    first = row["open_count"] == 0
    with get_db() as db:
        db.execute(
            "UPDATE press_recipients SET open_count = open_count + 1, "
            "last_opened = ?, opened_at = CASE WHEN opened_at = '' THEN ? "
            "ELSE opened_at END, status = CASE WHEN status IN "
            "('prepared','sent') THEN 'opened' ELSE status END WHERE id = ?",
            (now, now, row["id"]))
    return get_recipient_by_token(token) if first else None


def set_recipient_status(user_id, recipient_id, status, note=""):
    if status not in RECIPIENT_STATUSES:
        return False
    with get_db() as db:
        db.execute("UPDATE press_recipients SET status=?, note=? "
                   "WHERE id=? AND user_id=?",
                   (status, (note or "").strip()[:600], recipient_id, user_id))
    return True


def mark_pitch_sent(user_id, pitch_id):
    with get_db() as db:
        db.execute("UPDATE press_pitches SET status='sent', sent_at=? "
                   "WHERE id=? AND user_id=?", (_now(), pitch_id, user_id))


# --- coverage ---------------------------------------------------------------

def add_coverage(user_id, fields):
    coverage_id = _new_id()
    with get_db() as db:
        db.execute(
            "INSERT INTO press_coverage (id, user_id, release_id, contact_id, "
            "outlet, url, headline, kind, published_on, quote, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (coverage_id, user_id,
             (fields.get("release_id") or "")[:64],
             (fields.get("contact_id") or "")[:64],
             (fields.get("outlet") or "").strip()[:120],
             (fields.get("url") or "").strip()[:400],
             (fields.get("headline") or "").strip()[:300],
             fields.get("kind") if fields.get("kind") in COVERAGE_KINDS
             else "Review",
             (fields.get("published_on") or "").strip()[:10],
             (fields.get("quote") or "").strip()[:600], _now()))
    return coverage_id


def list_coverage(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT cv.*, r.title AS release_title FROM press_coverage cv"
            " LEFT JOIN press_releases r ON r.id = cv.release_id"
            " WHERE cv.user_id=? ORDER BY cv.published_on DESC, cv.created DESC",
            (user_id,)).fetchall()
    return [dict(r) for r in rows]


def delete_coverage(user_id, coverage_id):
    with get_db() as db:
        db.execute("DELETE FROM press_coverage WHERE id=? AND user_id=?",
                   (coverage_id, user_id))
    return True


# --- the desk ---------------------------------------------------------------

def desk_stats(user_id):
    """Counts for the dashboard. Every one of them is a COUNT over this
    artist's own rows - there is no baseline, no benchmark and no
    invented figure anywhere on this desk."""
    with get_db() as db:
        def one(sql, *params):
            return db.execute(sql, (user_id,) + params).fetchone()[0]
        return {
            "contacts": one("SELECT COUNT(*) FROM press_contacts "
                            "WHERE user_id=? AND status='active'"),
            "releases": one("SELECT COUNT(*) FROM press_releases WHERE user_id=?"),
            "pitched": one("SELECT COUNT(*) FROM press_recipients "
                           "WHERE user_id=? AND status != 'prepared'"),
            "opened": one("SELECT COUNT(*) FROM press_recipients "
                          "WHERE user_id=? AND open_count > 0"),
            "replied": one("SELECT COUNT(*) FROM press_recipients "
                           "WHERE user_id=? AND status IN ('replied','covered')"),
            "coverage": one("SELECT COUNT(*) FROM press_coverage WHERE user_id=?"),
        }


def needs_follow_up(user_id, days=7):
    """Sent, opened, and then nothing - for `days`. The one query that
    turns a sent list into a next action."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=days)).isoformat(timespec="seconds")
    with get_db() as db:
        rows = db.execute(
            "SELECT pr.*, c.name AS contact_name, c.outlet AS outlet,"
            " r.title AS release_title"
            " FROM press_recipients pr"
            " LEFT JOIN press_contacts c ON c.id = pr.contact_id"
            " LEFT JOIN press_pitches p ON p.id = pr.pitch_id"
            " LEFT JOIN press_releases r ON r.id = p.release_id"
            " WHERE pr.user_id = ? AND pr.status IN ('sent','opened')"
            " AND pr.sent_at != '' AND pr.sent_at < ?"
            " ORDER BY pr.sent_at", (user_id, cutoff)).fetchall()
    return [dict(r) for r in rows]
