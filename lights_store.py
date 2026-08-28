"""Light Studio library — named shows with versions.

`light_shows` (one working copy per user, db.py) stays exactly as it was:
the page loads it, autosave writes it, the old /lights/save keeps working.
This adds the library on top: many named shows per account, each linked
to a catalog track and optionally a tour date, with a version snapshot
taken on every explicit save (autosave updates in place and takes none).
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

from db import get_db, _now

MAX_VERSIONS = 20


def init_lights():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS light_show_library (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                track_id TEXT,
                tour_show_id TEXT,
                data TEXT NOT NULL,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS light_show_versions (
                id TEXT PRIMARY KEY,
                show_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                data TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                saved_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS light_rigs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                venue_key TEXT NOT NULL DEFAULT '',
                data TEXT NOT NULL,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS light_remotes (
                code TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                phone_seen TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS light_remote_cmds (
                id TEXT PRIMARY KEY,
                code TEXT NOT NULL,
                kind TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_lrem_user ON light_remotes(user_id);
            CREATE INDEX IF NOT EXISTS idx_lremc ON light_remote_cmds(code, created);
            CREATE TABLE IF NOT EXISTS light_setlists (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                gap_color TEXT NOT NULL DEFAULT '#1a1712',
                gap_intensity INTEGER NOT NULL DEFAULT 12,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS light_setlist_items (
                id TEXT PRIMARY KEY,
                setlist_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                show_id TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                advance TEXT NOT NULL DEFAULT 'manual',
                gap_seconds REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS light_shares (
                token TEXT PRIMARY KEY,
                show_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                permission TEXT NOT NULL DEFAULT 'read',
                label TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS light_comments (
                id TEXT PRIMARY KEY,
                show_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                parent_id TEXT NOT NULL DEFAULT '',
                t REAL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created TEXT NOT NULL,
                resolved INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_lsh_show ON light_shares(show_id, revoked);
            CREATE INDEX IF NOT EXISTS idx_lc_show ON light_comments(show_id, created);
            CREATE INDEX IF NOT EXISTS idx_lset_user ON light_setlists(user_id, updated);
            CREATE INDEX IF NOT EXISTS idx_lseti ON light_setlist_items(setlist_id, position);
            CREATE INDEX IF NOT EXISTS idx_lsl_user ON light_show_library(user_id, updated);
            CREATE INDEX IF NOT EXISTS idx_lsv_show ON light_show_versions(show_id, saved_at);
            CREATE INDEX IF NOT EXISTS idx_lr_user ON light_rigs(user_id, updated);
            CREATE INDEX IF NOT EXISTS idx_lr_venue ON light_rigs(user_id, venue_key);
        """)


def _row(r):
    d = dict(r)
    try:
        d["data"] = json.loads(d.get("data") or "{}")
    except ValueError:
        d["data"] = {}
    d["cue_count"] = len((d["data"] or {}).get("cues") or [])
    return d


def list_shows(user_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM light_show_library WHERE user_id = ? ORDER BY updated DESC",
                          (user_id,)).fetchall()
    return [_row(r) for r in rows]


def get_show(user_id, show_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM light_show_library WHERE id = ? AND user_id = ?",
                         (show_id, user_id)).fetchone()
    return _row(row) if row else None


def save_show(user_id, show_id, name, data, track_id=None, tour_show_id=None,
              version=True, note=""):
    """Upsert. Returns the id. A version row is written only when
    `version` is true (explicit saves); autosave passes False."""
    name = (name or "Untitled show").strip()[:120]
    blob = json.dumps(data if isinstance(data, dict) else {})
    now = _now()
    with get_db() as db:
        existing = None
        if show_id:
            existing = db.execute("SELECT id FROM light_show_library WHERE id=? AND user_id=?",
                                  (show_id, user_id)).fetchone()
        if existing:
            db.execute("UPDATE light_show_library SET name=?, track_id=?, tour_show_id=?, data=?, "
                       "updated=? WHERE id=? AND user_id=?",
                       (name, track_id or None, tour_show_id or None, blob, now, show_id, user_id))
        else:
            show_id = uuid.uuid4().hex
            db.execute("INSERT INTO light_show_library (id, user_id, name, track_id, tour_show_id, "
                       "data, created, updated) VALUES (?,?,?,?,?,?,?,?)",
                       (show_id, user_id, name, track_id or None, tour_show_id or None, blob, now, now))
        if version:
            db.execute("INSERT INTO light_show_versions (id, show_id, user_id, data, note, saved_at) "
                       "VALUES (?,?,?,?,?,?)",
                       (uuid.uuid4().hex, show_id, user_id, blob, (note or "")[:200], now))
            # keep the newest MAX_VERSIONS
            ids = [r["id"] for r in db.execute(
                "SELECT id FROM light_show_versions WHERE show_id=? ORDER BY saved_at DESC",
                (show_id,)).fetchall()]
            for old in ids[MAX_VERSIONS:]:
                db.execute("DELETE FROM light_show_versions WHERE id=?", (old,))
    return show_id


def delete_show(user_id, show_id):
    with get_db() as db:
        db.execute("DELETE FROM light_show_versions WHERE show_id=? AND user_id=?", (show_id, user_id))
        # A deleted show takes its links and its notes with it. get_share
        # already refuses a token whose show is gone, but leaving the rows
        # behind would mean a re-used id could resurrect old notes.
        db.execute("DELETE FROM light_shares WHERE show_id=? AND user_id=?", (show_id, user_id))
        db.execute("DELETE FROM light_comments WHERE show_id=? AND user_id=?", (show_id, user_id))
        cur = db.execute("DELETE FROM light_show_library WHERE id=? AND user_id=?", (show_id, user_id))
    return cur.rowcount > 0


def list_versions(user_id, show_id):
    with get_db() as db:
        rows = db.execute("SELECT id, note, saved_at, data FROM light_show_versions "
                          "WHERE show_id=? AND user_id=? ORDER BY saved_at DESC",
                          (show_id, user_id)).fetchall()
    out = []
    for r in rows:
        try:
            cues = len(json.loads(r["data"]).get("cues") or [])
        except (ValueError, AttributeError):
            cues = 0
        out.append({"id": r["id"], "note": r["note"], "saved_at": r["saved_at"], "cue_count": cues})
    return out


# --- phone remote (epic 3) ---------------------------------------------
# A second operator on a phone. The laptop stays the source of truth: the
# phone can only send a short list of commands, and the laptop polls for
# them. The pairing code in the URL is the authorisation - it is a secret,
# it is single-show, and it expires - so a bandmate can pick it up without
# an account.

REMOTE_TTL_HOURS = 12
# "ping" is a keep-alive: allowed so the phone can prove the link is
# alive, ignored by the laptop so it never disturbs the show.
REMOTE_COMMANDS = ("blackout", "restore", "play", "stop", "tap", "look", "next", "prev", "ping")


def start_remote(user_id):
    code = uuid.uuid4().hex
    with get_db() as db:
        db.execute("DELETE FROM light_remotes WHERE user_id = ?", (user_id,))   # one at a time
        db.execute("INSERT INTO light_remotes (code, user_id, created, last_seen, phone_seen) "
                   "VALUES (?,?,?,?,'')", (code, user_id, _now(), _now()))
    return code


def _remote_row(code):
    with get_db() as db:
        row = db.execute("SELECT * FROM light_remotes WHERE code = ?", (code,)).fetchone()
    if row is None:
        return None
    try:
        created = datetime.fromisoformat(row["created"].replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created > timedelta(hours=REMOTE_TTL_HOURS):
            return None
    except (ValueError, AttributeError):
        return None
    return dict(row)


def get_remote(code):
    return _remote_row(code)


def end_remote(user_id):
    with get_db() as db:
        db.execute("DELETE FROM light_remotes WHERE user_id = ?", (user_id,))


def push_remote_command(code, kind, value=""):
    """The phone sends one of a fixed set of commands. Anything else is
    refused rather than stored - the remote is not a general channel."""
    if kind not in REMOTE_COMMANDS:
        return None
    row = _remote_row(code)
    if row is None:
        return None
    with get_db() as db:
        db.execute("INSERT INTO light_remote_cmds (id, code, kind, value, created) VALUES (?,?,?,?,?)",
                   (uuid.uuid4().hex, code, kind, str(value or "")[:40], _now()))
        db.execute("UPDATE light_remotes SET phone_seen = ? WHERE code = ?", (_now(), code))
        # keep the queue short; the laptop drains it every poll
        db.execute("DELETE FROM light_remote_cmds WHERE code = ? AND id NOT IN "
                   "(SELECT id FROM light_remote_cmds WHERE code = ? ORDER BY created DESC LIMIT 40)",
                   (code, code))
    return True


def drain_remote_commands(user_id):
    """The laptop pulls whatever the phone has sent since it last looked.

    Also reports the live code, so a studio that was reloaded mid-set can
    pick the remote back up instead of leaving the phone pressing buttons
    into a queue nobody is draining.
    """
    with get_db() as db:
        row = db.execute("SELECT code, phone_seen FROM light_remotes WHERE user_id = ?", (user_id,)).fetchone()
        if row is None or _remote_row(row["code"]) is None:      # same expiry rule as the phone sees
            return {"code": "", "commands": [], "phone_seen": ""}
        rows = db.execute("SELECT id, kind, value, created FROM light_remote_cmds WHERE code = ? "
                          "ORDER BY created", (row["code"],)).fetchall()
        cmds = [dict(r) for r in rows]
        if cmds:
            db.execute("DELETE FROM light_remote_cmds WHERE code = ?", (row["code"],))
        db.execute("UPDATE light_remotes SET last_seen = ? WHERE code = ?", (_now(), row["code"]))
    return {"code": row["code"], "commands": cmds, "phone_seen": row["phone_seen"] or ""}


# --- sharing a show for notes (epic 5) ---------------------------------
# A designer sends the show to a manager, an MD or the artist and asks
# "what do you think of the second chorus". The link carries ONE show and
# nothing else about the account, and the audio never travels - it never
# leaves the designer's machine in the first place. What the reader gets
# is the cue list against a timeline and a stage that can run the cues.

SHARE_PERMISSIONS = ("read", "comment")
MAX_COMMENT_CHARS = 1200


def create_share(user_id, show_id, permission="read", label=""):
    """Returns the token, or None if the show is not this user's."""
    if permission not in SHARE_PERMISSIONS:
        permission = "read"
    if get_show(user_id, show_id) is None:
        return None
    token = uuid.uuid4().hex
    with get_db() as db:
        db.execute("INSERT INTO light_shares (token, show_id, user_id, permission, label, created, revoked) "
                   "VALUES (?,?,?,?,?,?,0)",
                   (token, show_id, user_id, permission, (label or "").strip()[:80], _now()))
    return token


def list_shares(user_id, show_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM light_shares WHERE user_id=? AND show_id=? AND revoked=0 "
                          "ORDER BY created DESC", (user_id, show_id)).fetchall()
    return [dict(r) for r in rows]


def get_share(token):
    """The link itself is the authorisation, so this deliberately takes no
    user - but a revoked link is dead, and so is one whose show was
    deleted underneath it."""
    if not token:
        return None
    with get_db() as db:
        row = db.execute("SELECT * FROM light_shares WHERE token=? AND revoked=0", (token,)).fetchone()
        if row is None:
            return None
        show = db.execute("SELECT * FROM light_show_library WHERE id=?", (row["show_id"],)).fetchone()
    if show is None:
        return None
    d = dict(row)
    d["show"] = _row(show)
    return d


def revoke_share(user_id, token):
    with get_db() as db:
        cur = db.execute("UPDATE light_shares SET revoked=1 WHERE token=? AND user_id=?", (token, user_id))
    return cur.rowcount > 0


def add_comment(show_id, user_id, author, body, t=None, parent_id=""):
    """`user_id` is the show's OWNER, so a comment is always filed against
    the owner's show whether the author is the owner or a reader holding a
    share link. Readers have no account, which is why the author is a
    plain name.

    A note anchors to a TIMECODE, never to a cue id: `payload()` in
    lights.js strips `_id` from every cue on save, so cue ids are
    regenerated on each load and would not survive the round trip. A
    second at 1:14 is still 1:14 after the cue there is deleted.
    """
    body = (body or "").strip()[:MAX_COMMENT_CHARS]
    if not body:
        return None
    cid = uuid.uuid4().hex
    try:
        t = None if t is None or t == "" else max(0.0, float(t))
    except (TypeError, ValueError):
        t = None
    with get_db() as db:
        if parent_id:
            # A reply must land on a thread of this same show, or it is
            # not a reply - it is a way to read someone else's comments.
            ok = db.execute("SELECT id FROM light_comments WHERE id=? AND show_id=?",
                            (parent_id, show_id)).fetchone()
            if ok is None:
                parent_id = ""
        db.execute("INSERT INTO light_comments (id, show_id, user_id, parent_id, t, author, body, "
                   "created, resolved) VALUES (?,?,?,?,?,?,?,?,0)",
                   (cid, show_id, user_id, parent_id, t,
                    (author or "Someone").strip()[:60] or "Someone", body, _now()))
    return cid


def list_comments(show_id):
    """Flat and ordered; the client nests by parent_id. Threads stay
    shallow on purpose - a note on a cue is not a forum."""
    with get_db() as db:
        rows = db.execute("SELECT id, show_id, parent_id, t, author, body, created, resolved "
                          "FROM light_comments WHERE show_id=? ORDER BY created", (show_id,)).fetchall()
    return [dict(r) for r in rows]


def resolve_comment(user_id, comment_id, resolved=True):
    """Only the show's owner settles a note - a reader can raise one but
    cannot decide it is dealt with."""
    with get_db() as db:
        cur = db.execute("UPDATE light_comments SET resolved=? WHERE id=? AND user_id=?",
                         (1 if resolved else 0, comment_id, user_id))
    return cur.rowcount > 0


def delete_comment(user_id, comment_id):
    with get_db() as db:
        row = db.execute("SELECT id FROM light_comments WHERE id=? AND user_id=?",
                         (comment_id, user_id)).fetchone()
        if row is None:
            return False
        db.execute("DELETE FROM light_comments WHERE id=? OR parent_id=?", (comment_id, comment_id))
    return True


# --- the show ships with the song (Track Passport) ---------------------
# A light show attached to a track travels with it: anyone with platform
# access to the track can pull it and render it on their OWN rig, because
# cues store looks and group roles rather than channel numbers.

LIGHT_SHOW_KEY = "light_show"
PASSPORT_FORMAT = 1


def attach_to_track(user_id, track_id, name, data, show_id=""):
    """Write the show into the track's passport, keeping a short history.

    Stored beside the rest of the passport rather than in place of it, and
    only ever for a track this account owns.
    """
    import db as _store
    track = _store.get_os_track(user_id, track_id)
    if track is None:
        return None
    passport = track.get("passport") or {}
    if not isinstance(passport, dict):
        passport = {}
    prev = passport.get(LIGHT_SHOW_KEY) or {}
    history = prev.get("history") or []
    if prev.get("data"):
        history.insert(0, {"saved_at": prev.get("saved_at"), "name": prev.get("name"),
                           "cue_count": len((prev.get("data") or {}).get("cues") or [])})
    entry = {
        "format": PASSPORT_FORMAT,
        "name": (name or "Untitled show")[:120],
        "show_id": show_id or "",
        "saved_at": _now(),
        "cue_count": len((data or {}).get("cues") or []),
        "bars": (data or {}).get("bars"),
        "data": data if isinstance(data, dict) else {},
        "history": history[:9],
    }
    passport[LIGHT_SHOW_KEY] = entry
    _store.update_os_track_passport(user_id, track_id, passport)
    return entry


def show_on_track(user_id, track_id):
    """The light show attached to a track, or None."""
    import db as _store
    track = _store.get_os_track(user_id, track_id)
    if track is None:
        return None
    passport = track.get("passport") or {}
    if not isinstance(passport, dict):
        return None
    entry = passport.get(LIGHT_SHOW_KEY)
    return entry if isinstance(entry, dict) and entry.get("data") else None


def tracks_with_shows(user_id):
    """Which of this account's tracks carry a light show. Drives the badge
    in the track picker."""
    import db as _store
    out = {}
    for t in _store.list_os_tracks(user_id):
        p = t.get("passport") or {}
        entry = p.get(LIGHT_SHOW_KEY) if isinstance(p, dict) else None
        if isinstance(entry, dict) and entry.get("data"):
            out[t["id"]] = {"name": entry.get("name") or "", "cue_count": entry.get("cue_count") or 0,
                            "saved_at": entry.get("saved_at") or ""}
    return out


# --- setlists ----------------------------------------------------------
# A setlist chains saved shows in order. Between songs the rig holds a
# "gap look" rather than going black, because a black stage between songs
# reads as a fault.

MAX_SETLIST_ITEMS = 60
ADVANCE_MODES = ("manual", "auto")


def list_setlists(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT s.*, (SELECT COUNT(*) FROM light_setlist_items i WHERE i.setlist_id = s.id) AS item_count "
            "FROM light_setlists s WHERE s.user_id = ? ORDER BY s.updated DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_setlist(user_id, setlist_id):
    """The setlist with its items resolved to library shows, in order."""
    with get_db() as db:
        row = db.execute("SELECT * FROM light_setlists WHERE id=? AND user_id=?",
                         (setlist_id, user_id)).fetchone()
        if row is None:
            return None
        items = db.execute(
            "SELECT i.*, l.name AS show_name FROM light_setlist_items i "
            "LEFT JOIN light_show_library l ON l.id = i.show_id "
            "WHERE i.setlist_id=? AND i.user_id=? ORDER BY i.position", (setlist_id, user_id)).fetchall()
    out = dict(row)
    out["items"] = [dict(i) for i in items]
    return out


def save_setlist(user_id, setlist_id, name, items, gap_color="#1a1712", gap_intensity=12):
    """Upsert a setlist and replace its items.

    Every show id is checked against this user's own library, so a setlist
    can never reference another account's show.
    """
    name = (name or "Setlist").strip()[:120]
    now = _now()
    with get_db() as db:
        if setlist_id and db.execute("SELECT 1 FROM light_setlists WHERE id=? AND user_id=?",
                                     (setlist_id, user_id)).fetchone():
            db.execute("UPDATE light_setlists SET name=?, gap_color=?, gap_intensity=?, updated=? "
                       "WHERE id=? AND user_id=?",
                       (name, gap_color, int(gap_intensity or 0), now, setlist_id, user_id))
        else:
            setlist_id = uuid.uuid4().hex
            db.execute("INSERT INTO light_setlists (id, user_id, name, gap_color, gap_intensity, created, updated) "
                       "VALUES (?,?,?,?,?,?,?)",
                       (setlist_id, user_id, name, gap_color, int(gap_intensity or 0), now, now))
        mine = {r["id"] for r in db.execute("SELECT id FROM light_show_library WHERE user_id=?",
                                            (user_id,)).fetchall()}
        db.execute("DELETE FROM light_setlist_items WHERE setlist_id=? AND user_id=?", (setlist_id, user_id))
        pos = 0
        for it in (items or [])[:MAX_SETLIST_ITEMS]:
            show_id = (it or {}).get("show_id") or ""
            if show_id not in mine:            # not this user's show: drop it
                continue
            advance = it.get("advance") if it.get("advance") in ADVANCE_MODES else "manual"
            try:
                gap = max(0.0, min(600.0, float(it.get("gap_seconds") or 0)))
            except (TypeError, ValueError):
                gap = 0.0
            db.execute("INSERT INTO light_setlist_items (id, setlist_id, user_id, show_id, position, advance, "
                       "gap_seconds) VALUES (?,?,?,?,?,?,?)",
                       (uuid.uuid4().hex, setlist_id, user_id, show_id, pos, advance, gap))
            pos += 1
    return setlist_id


def delete_setlist(user_id, setlist_id):
    with get_db() as db:
        db.execute("DELETE FROM light_setlist_items WHERE setlist_id=? AND user_id=?", (setlist_id, user_id))
        cur = db.execute("DELETE FROM light_setlists WHERE id=? AND user_id=?", (setlist_id, user_id))
    return cur.rowcount > 0


# --- rig profiles ------------------------------------------------------
# A rig is bar count, fixture type, layout and patch. Shows store looks and
# group roles, so the same show compiles onto any rig; a rig can be bound to
# a venue by name so picking a tour date at that venue selects it.

MAX_RIGS = 40


def venue_key(name):
    """Loose match on a venue name: case, spacing and punctuation are noise."""
    out = []
    prev_space = False
    for ch in (name or "").lower():
        if ch.isalnum():
            out.append(ch)
            prev_space = False
        elif not prev_space:
            out.append(" ")
            prev_space = True
    return "".join(out).strip()[:120]


def _rig_row(r):
    d = dict(r)
    try:
        d["data"] = json.loads(d.get("data") or "{}")
    except ValueError:
        d["data"] = {}
    return d


def list_rigs(user_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM light_rigs WHERE user_id = ? ORDER BY updated DESC",
                          (user_id,)).fetchall()
    return [_rig_row(r) for r in rows]


def get_rig(user_id, rig_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM light_rigs WHERE id = ? AND user_id = ?",
                         (rig_id, user_id)).fetchone()
    return _rig_row(row) if row else None


def save_rig(user_id, rig_id, name, data, venue=""):
    """Upsert a rig. Returns (id, error). Refuses to create past MAX_RIGS."""
    name = (name or "Untitled rig").strip()[:80]
    blob = json.dumps(data if isinstance(data, dict) else {})
    key = venue_key(venue)
    now = _now()
    with get_db() as db:
        existing = None
        if rig_id:
            existing = db.execute("SELECT id FROM light_rigs WHERE id=? AND user_id=?",
                                  (rig_id, user_id)).fetchone()
        if existing:
            db.execute("UPDATE light_rigs SET name=?, venue_key=?, data=?, updated=? "
                       "WHERE id=? AND user_id=?", (name, key, blob, now, rig_id, user_id))
        else:
            count = db.execute("SELECT COUNT(*) AS n FROM light_rigs WHERE user_id=?",
                               (user_id,)).fetchone()["n"]
            if count >= MAX_RIGS:
                return (None, "You have %d saved rigs — delete one first." % MAX_RIGS)
            rig_id = uuid.uuid4().hex
            db.execute("INSERT INTO light_rigs (id, user_id, name, venue_key, data, created, updated) "
                       "VALUES (?,?,?,?,?,?,?)", (rig_id, user_id, name, key, blob, now, now))
        # one rig per venue: the newest binding wins, older ones are unbound
        if key:
            db.execute("UPDATE light_rigs SET venue_key='' WHERE user_id=? AND venue_key=? AND id<>?",
                       (user_id, key, rig_id))
    return (rig_id, None)


def delete_rig(user_id, rig_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM light_rigs WHERE id=? AND user_id=?", (rig_id, user_id))
    return cur.rowcount > 0


def rig_for_venue(user_id, venue):
    """The rig bound to this venue name, or None. Used when a show is
    linked to a tour date so the layout follows the room."""
    key = venue_key(venue)
    if not key:
        return None
    with get_db() as db:
        row = db.execute("SELECT * FROM light_rigs WHERE user_id=? AND venue_key=? "
                         "ORDER BY updated DESC LIMIT 1", (user_id, key)).fetchone()
    return _rig_row(row) if row else None


def get_version(user_id, version_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM light_show_versions WHERE id=? AND user_id=?",
                         (version_id, user_id)).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["data"] = json.loads(d["data"])
    except ValueError:
        d["data"] = {}
    return d
