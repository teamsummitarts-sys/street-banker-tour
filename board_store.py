"""Team-Up Board — data layer.

Keeps the original `tour_board` table and URLs, and adds:

  structure   region_code/region_text, window_start/window_end, genres
              (JSON list of taxonomy codes), draw_min/draw_max, plus a
              parse flag for rows migrated from free text that could
              not be fully understood;
  lifecycle   status open|closed|filled|expired, expires_at (60 days),
              renew tokens, filled_via (a thread id = "Matched on the
              Board"), updated;
  threads     in-platform reply threads (board_threads / board_messages)
              with unread counters for both sides - email is only a
              notification channel now, never the place the reply lives;
  watches     saved searches that alert by notification + email;
  repair      a UTF-8 clean-up for text that arrived mangled
              (Windows-1252 bytes percent-encoded, or UTF-8 read as
              Latin-1) - run once at init, idempotent, and exposed as a
              tool with a dry run.

Everything here is plain SQLite through db.get_db(); timestamps are UTC
ISO like the rest of the app.
"""
import json
import re
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone, date

from db import get_db, _now
import board_taxonomy as tx

EXPIRE_DAYS = 60
RENEW_NOTICE_DAYS = 3
LISTING_STATUSES = ("open", "closed", "filled", "expired")
KINDS = ("artist", "venue")
KIND_LABELS = {"artist": "Artist seeks partners", "venue": "Venue seeks artists"}


# --- schema -----------------------------------------------------------------

def init_board():
    with get_db() as db:
        for col in ("region_code TEXT NOT NULL DEFAULT ''", "region_text TEXT NOT NULL DEFAULT ''",
                    "window_start TEXT NOT NULL DEFAULT ''", "window_end TEXT NOT NULL DEFAULT ''",
                    "genres TEXT NOT NULL DEFAULT '[]'", "draw_min INTEGER", "draw_max INTEGER",
                    "parse_flag TEXT NOT NULL DEFAULT ''", "expires_at TEXT NOT NULL DEFAULT ''",
                    "renew_token TEXT NOT NULL DEFAULT ''", "renew_notice_at TEXT NOT NULL DEFAULT ''",
                    "filled_via TEXT NOT NULL DEFAULT ''", "filled_at TEXT NOT NULL DEFAULT ''",
                    "updated TEXT NOT NULL DEFAULT ''", "structured INTEGER NOT NULL DEFAULT 0"):
            try:
                db.execute("ALTER TABLE tour_board ADD COLUMN %s" % col)
            except Exception:
                pass
        db.executescript("""
            CREATE TABLE IF NOT EXISTS board_threads (
                id TEXT PRIMARY KEY,
                listing_id TEXT NOT NULL,
                poster_id TEXT NOT NULL,
                replier_id TEXT NOT NULL,
                created TEXT NOT NULL,
                last_at TEXT NOT NULL,
                poster_unread INTEGER NOT NULL DEFAULT 0,
                replier_unread INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'open',
                UNIQUE(listing_id, replier_id)
            );
            CREATE TABLE IF NOT EXISTS board_messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                from_user_id TEXT NOT NULL,
                body TEXT NOT NULL,
                created TEXT NOT NULL,
                legacy_reply_id TEXT
            );
            CREATE TABLE IF NOT EXISTS board_watches (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT '',
                region_code TEXT NOT NULL DEFAULT '',
                genres TEXT NOT NULL DEFAULT '[]',
                window_start TEXT NOT NULL DEFAULT '',
                window_end TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL,
                last_alert_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS board_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                listing_id TEXT NOT NULL DEFAULT '',
                created TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_board_threads_listing ON board_threads(listing_id);
            CREATE INDEX IF NOT EXISTS idx_board_threads_replier ON board_threads(replier_id);
            CREATE INDEX IF NOT EXISTS idx_board_messages_thread ON board_messages(thread_id, created);
            CREATE INDEX IF NOT EXISTS idx_board_watches_user ON board_watches(user_id);
        """)
    repair_all_text()
    migrate_legacy_listings()
    migrate_legacy_replies()


# --- encoding repair ----------------------------------------------------------

# Windows-1252 code points 0x80-0x9F that show up when a typographic
# character is turned into a single byte and then percent-encoded or read
# through the wrong codec. Only the ones that appear in prose.
_CP1252 = {0x80: "€", 0x82: "‚", 0x84: "„", 0x85: "…", 0x91: "‘", 0x92: "’",
           0x93: "“", 0x94: "”", 0x95: "•", 0x96: "–", 0x97: "—", 0x99: "™",
           0xa0: " ", 0xa9: "©", 0xae: "®"}
_PCT_BYTE = re.compile(r"%([89ab][0-9a-f])", re.I)
_PCT_UTF8 = re.compile(r"(?:%[cdef][0-9a-f](?:%[89ab][0-9a-f]){1,3})", re.I)
_MOJIBAKE = re.compile(r"[ÂÃâ][-¿€‚„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ]")


def repair_text(s):
    """Return s with known mangling undone. Idempotent; leaves anything it
    does not recognise alone."""
    if not s or not isinstance(s, str):
        return s
    out = s
    # 1. percent-encoded UTF-8 sequences that were never decoded: %E2%80%94 -> —
    def _utf8(m):
        try:
            return urllib.parse.unquote(m.group(0), encoding="utf-8", errors="strict")
        except Exception:
            return m.group(0)
    out = _PCT_UTF8.sub(_utf8, out)
    # 2. single percent-encoded Windows-1252 bytes: %97 -> —
    out = _PCT_BYTE.sub(lambda m: _CP1252.get(int(m.group(1), 16), m.group(0)), out)
    # 3. UTF-8 read as Latin-1/cp1252: â€” -> —, Ã© -> é
    if _MOJIBAKE.search(out):
        try:
            fixed = out.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
            if fixed and len(fixed) <= len(out):
                out = fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                fixed = out.encode("latin-1", errors="strict").decode("utf-8", errors="strict")
                if fixed and len(fixed) <= len(out):
                    out = fixed
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    # 4. a stray raw C1 control char (0x97 as a code point) that some paths leave behind
    out = "".join(_CP1252.get(ord(ch), ch) if 0x80 <= ord(ch) <= 0x9f else ch for ch in out)
    return out


def repair_all_text(apply=True):
    """Repair every text column on the board. Returns the rows that would
    change (or did), as (table, id, field, before, after)."""
    changes = []
    with get_db() as db:
        for table, fields in (("tour_board", ("title", "region", "window", "genre", "details", "region_text")),
                              ("tour_board_replies", ("message", "contact")),
                              ("board_messages", ("body",))):
            cols = [r["name"] for r in db.execute("PRAGMA table_info(%s)" % table)]
            use = [f for f in fields if f in cols]
            if not use:
                continue
            for row in db.execute("SELECT id, %s FROM %s" % (", ".join(use), table)).fetchall():
                for f in use:
                    before = row[f]
                    after = repair_text(before)
                    if after != before:
                        changes.append((table, row["id"], f, before, after))
                        if apply:
                            db.execute("UPDATE %s SET %s = ? WHERE id = ?" % (table, f), (after, row["id"]))
    return changes


# --- migrations ---------------------------------------------------------------

def structure_from_text(region, window, genre, details):
    """Best-effort structure from the old free-text fields."""
    code, conf = tx.parse_region(region)
    ws, we = tx.parse_window(window)
    gcodes, left = tx.parse_genres(genre)
    dmin, dmax = tx.parse_draw(details)
    flags = []
    if region and not code:
        flags.append("region")
    if window and not ws:
        flags.append("window")
    if genre and not gcodes:
        flags.append("genre")
    return {"region_code": code or "", "region_text": region or "", "window_start": ws or "", "window_end": we or "",
            "genres": gcodes, "draw_min": dmin, "draw_max": dmax, "parse_flag": ",".join(flags)}


def migrate_legacy_listings():
    """Backfill the structured columns for rows posted before they existed.

    Expiry is measured from the migration, not from `created`: a listing
    posted six months ago would otherwise be born already expired and drop
    off the board the moment this ships. Legacy rows also need a renew
    token, or the one renewal email they get carries a dead link and burns
    the single notice they are allowed."""
    now = _now()
    grace = (datetime.now(timezone.utc) + timedelta(days=EXPIRE_DAYS)).isoformat(timespec="seconds")
    with get_db() as db:
        rows = db.execute("SELECT * FROM tour_board WHERE structured = 0").fetchall()
        for r in rows:
            s = structure_from_text(r["region"], r["window"], r["genre"], r["details"])
            created = r["created"] or now
            natural = (_parse_ts(created) + timedelta(days=EXPIRE_DAYS)).isoformat(timespec="seconds")
            expires = max(natural, grace)
            db.execute("UPDATE tour_board SET region_code=?, region_text=?, window_start=?, window_end=?, genres=?, "
                       "draw_min=?, draw_max=?, parse_flag=?, expires_at=COALESCE(NULLIF(expires_at,''), ?), "
                       "renew_token=CASE WHEN renew_token='' THEN ? ELSE renew_token END, "
                       "updated=COALESCE(NULLIF(updated,''), created), structured=1 WHERE id=?",
                       (s["region_code"], s["region_text"], s["window_start"], s["window_end"], json.dumps(s["genres"]),
                        s["draw_min"], s["draw_max"], s["parse_flag"], expires, uuid.uuid4().hex, r["id"]))


def migrate_legacy_replies():
    """Old email-style replies become the first message of a thread."""
    with get_db() as db:
        rows = db.execute("SELECT r.*, b.user_id AS poster_id FROM tour_board_replies r JOIN tour_board b ON b.id = r.listing_id "
                          "WHERE r.id NOT IN (SELECT legacy_reply_id FROM board_messages WHERE legacy_reply_id IS NOT NULL)").fetchall()
        for r in rows:
            t = db.execute("SELECT id FROM board_threads WHERE listing_id=? AND replier_id=?", (r["listing_id"], r["from_user_id"])).fetchone()
            if t:
                tid = t["id"]
            else:
                tid = uuid.uuid4().hex
                db.execute("INSERT INTO board_threads (id, listing_id, poster_id, replier_id, created, last_at, poster_unread, replier_unread) "
                           "VALUES (?,?,?,?,?,?,0,0)", (tid, r["listing_id"], r["poster_id"], r["from_user_id"], r["created"], r["created"]))
            body = r["message"] + ("\n\n(contact given: %s)" % r["contact"] if r["contact"] else "")
            db.execute("INSERT INTO board_messages (id, thread_id, from_user_id, body, created, legacy_reply_id) VALUES (?,?,?,?,?,?)",
                       (uuid.uuid4().hex, tid, r["from_user_id"], body[:2000], r["created"], r["id"]))


def _parse_ts(s):
    try:
        d = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def ago(ts, now=None):
    """'just now', '5 minutes ago', '3 hours ago', 'yesterday', '5 days
    ago', '5 weeks ago', '3 months ago'."""
    now = now or datetime.now(timezone.utc)
    secs = int((now - _parse_ts(ts)).total_seconds())
    if secs < 90:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return ("1 minute ago" if mins == 1 else "%d minutes ago" % mins)
    hours = mins // 60
    if hours < 24:
        return ("1 hour ago" if hours == 1 else "%d hours ago" % hours)
    days = hours // 24
    if days == 1:
        return "yesterday"
    if days < 14:
        return "%d days ago" % days
    weeks = days // 7
    if days < 60:
        return "%d weeks ago" % weeks
    # months = days // 30, so days 360-364 give 12 and used to fall through
    # to the years branch, which then reported "0 years ago". Switch on days.
    months = days // 30
    if days < 365:
        return "%d months ago" % max(2, months)
    return "%d years ago" % (days // 365)


# --- listings -----------------------------------------------------------------

def _row(r):
    if r is None:
        return None
    d = dict(r)
    try:
        d["genres"] = json.loads(d.get("genres") or "[]")
    except ValueError:
        d["genres"] = []
    d["genre_labels"] = [tx.genre_label(g) for g in d["genres"]]
    d["region_label"] = tx.region_label(d.get("region_code")) or d.get("region_text") or d.get("region") or ""
    d["kind_label"] = KIND_LABELS.get(d.get("kind"), d.get("kind"))
    d["ago"] = ago(d["created"]) if d.get("created") else ""
    d["window_label"] = window_label(d.get("window_start"), d.get("window_end")) or d.get("window") or ""
    d["matched"] = bool(d.get("filled_via"))
    d["is_expired"] = d.get("status") == "open" and bool(d.get("expires_at")) and d["expires_at"] < _now()
    d["effective_status"] = "expired" if d["is_expired"] else d.get("status")
    return d


def window_label(start, end):
    if not start:
        return ""
    try:
        s = date.fromisoformat(start[:10]); e = date.fromisoformat((end or start)[:10])
    except ValueError:
        return start
    if s == e:
        return s.strftime("%b %d, %Y").replace(" 0", " ")
    if s.year == e.year and s.month == e.month:
        return "%s %d–%d, %d" % (s.strftime("%b"), s.day, e.day, s.year)
    if s.year == e.year:
        return "%s – %s %d" % (s.strftime("%b %d").replace(" 0", " "), e.strftime("%b %d").replace(" 0", " "), s.year)
    return "%s – %s" % (s.strftime("%b %d, %Y").replace(" 0", " "), e.strftime("%b %d, %Y").replace(" 0", " "))


def _clean_fields(f):
    """Normalise a posted form into stored columns. Returns (fields,
    coaching) where coaching is a list of gentle nudges, never blockers."""
    region_text = (f.get("region_text") or f.get("region") or "").strip()[:80]
    region_code = (f.get("region_code") or "").strip()
    if region_code and not tx.region_label(region_code):
        region_code = ""
    if not region_code and region_text:
        region_code = tx.parse_region(region_text)[0] or ""
    ws = (f.get("window_start") or "").strip()[:10]
    we = (f.get("window_end") or "").strip()[:10] or ws
    for v in (ws, we):
        if v and not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            ws, we = "", ""
            break
    if ws and we and we < ws:
        ws, we = we, ws
    window_text = (f.get("window") or "").strip()[:80]
    if not ws and window_text:
        ws, we = tx.parse_window(window_text)
        ws, we = ws or "", we or ""
    genres = [g for g in (f.get("genres") or []) if tx.genre_label(g) != g or g in dict(tx.genre_options())]
    genres = [g for g in genres if g in dict(tx.genre_options())]
    genre_text = (f.get("genre") or "").strip()[:120]
    if genre_text:
        more, left = tx.parse_genres(genre_text)
        for g in more:
            if g not in genres:
                genres.append(g)
    else:
        left = []
    details = (f.get("details") or "").strip()[:1000]
    dmin, dmax = None, None
    for k in ("draw_min", "draw_max"):
        v = (f.get(k) or "").strip().replace(",", "")
        if v.isdigit():
            if k == "draw_min":
                dmin = int(v)
            else:
                dmax = int(v)
    if dmin is None and dmax is None:
        dmin, dmax = tx.parse_draw(details)
    if dmin is not None and dmax is None:
        dmax = dmin
    if dmin is not None and dmax is not None and dmax < dmin:
        dmin, dmax = dmax, dmin
    coaching = []
    kind = f.get("kind")
    if kind == "artist" and dmin is None:
        coaching.append("Add a draw range — real numbers get real replies.")
    if kind == "venue" and not re.search(r"\b(cap|capacity|room|holds)\b", details.lower()) and not re.search(r"\d{2,4}", details):
        coaching.append("Say the room capacity and the deal — acts reply to specifics.")
    if not ws:
        coaching.append("A date window (even a month) lets people search by when.")
    if not region_code:
        coaching.append("Pick a region or metro from the list so the right people can filter to you.")
    flags = []
    if region_text and not region_code:
        flags.append("region")
    if left:
        flags.append("genre")
    return ({"region_code": region_code, "region_text": region_text or tx.region_label(region_code),
             "window_start": ws or "", "window_end": we or "", "genres": genres, "genre_text": genre_text,
             "draw_min": dmin, "draw_max": dmax, "details": details, "parse_flag": ",".join(flags),
             "window_text": window_text}, coaching)


def add_listing(user_id, kind, title, fields):
    """fields: dict as posted (see _clean_fields). Returns (id, coaching)."""
    if kind not in KINDS:
        return (None, ["Pick who you are — an artist seeking partners, or a venue seeking artists."])
    if not (title or "").strip():
        return (None, ["A headline is required."])
    clean, coaching = _clean_fields(dict(fields, kind=kind))
    lid = uuid.uuid4().hex
    now = _now()
    expires = (datetime.now(timezone.utc) + timedelta(days=EXPIRE_DAYS)).isoformat(timespec="seconds")
    with get_db() as db:
        db.execute(
            "INSERT INTO tour_board (id, user_id, kind, title, region, window, genre, details, status, created, "
            "region_code, region_text, window_start, window_end, genres, draw_min, draw_max, parse_flag, expires_at, "
            "renew_token, updated, structured) VALUES (?,?,?,?,?,?,?,?,'open',?,?,?,?,?,?,?,?,?,?,?,?,1)",
            (lid, user_id, kind, title.strip()[:120], clean["region_text"][:80], (clean["window_text"] or window_label(clean["window_start"], clean["window_end"]))[:80],
             (clean["genre_text"] or ", ".join(tx.genre_label(g) for g in clean["genres"]))[:60], clean["details"], now,
             clean["region_code"], clean["region_text"], clean["window_start"], clean["window_end"], json.dumps(clean["genres"]),
             clean["draw_min"], clean["draw_max"], clean["parse_flag"], expires, uuid.uuid4().hex, now))
    event("listing_posted", user_id, lid)
    return (lid, coaching)


def update_listing(user_id, lid, title, fields):
    cur = get_listing(lid)
    if cur is None or cur["user_id"] != user_id:
        return (False, [])
    clean, coaching = _clean_fields(dict(fields, kind=cur["kind"]))
    with get_db() as db:
        db.execute(
            "UPDATE tour_board SET title=?, region=?, window=?, genre=?, details=?, region_code=?, region_text=?, "
            "window_start=?, window_end=?, genres=?, draw_min=?, draw_max=?, parse_flag=?, updated=? WHERE id=? AND user_id=?",
            ((title or cur["title"]).strip()[:120], clean["region_text"][:80],
             (clean["window_text"] or window_label(clean["window_start"], clean["window_end"]))[:80],
             (clean["genre_text"] or ", ".join(tx.genre_label(g) for g in clean["genres"]))[:60], clean["details"],
             clean["region_code"], clean["region_text"], clean["window_start"], clean["window_end"], json.dumps(clean["genres"]),
             clean["draw_min"], clean["draw_max"], clean["parse_flag"], _now(), lid, user_id))
    return (True, coaching)


def get_listing(lid):
    with get_db() as db:
        row = db.execute("SELECT b.*, u.name AS poster_name FROM tour_board b JOIN users u ON u.id = b.user_id WHERE b.id = ?",
                         (lid,)).fetchone()
    return _row(row)


def list_listings(kind=None, region=None, genre=None, start=None, end=None, sort="newest", limit=200, include_expired=False):
    """Open listings with filters. Region matching: exact code, or the
    listing sits inside the requested region (metro in region), or the
    listing says 'US — anywhere'."""
    q = ("SELECT b.*, u.name AS poster_name FROM tour_board b JOIN users u ON u.id = b.user_id WHERE b.status = 'open'")
    args = []
    if not include_expired:
        q += " AND (b.expires_at = '' OR b.expires_at >= ?)"; args.append(_now())
    if kind in KINDS:
        q += " AND b.kind = ?"; args.append(kind)
    if genre:
        q += " AND b.genres LIKE ?"; args.append('%"' + genre + '"%')
    if start:
        q += " AND (b.window_end = '' OR b.window_end >= ?)"; args.append(start)
    if end:
        q += " AND (b.window_start = '' OR b.window_start <= ?)"; args.append(end)
    if region:
        # Region matching is a taxonomy relationship (a metro sits inside a
        # region, "US - anywhere" matches everything), so it cannot be a
        # plain SQL comparison. Resolve the related codes first and filter
        # in SQL: filtering in Python after LIMIT would silently return an
        # empty board once there are more than `limit` open listings.
        related = [c for c, _label, _kind in tx.region_options() if tx.regions_related(c, region)]
        if not related:
            return []
        q += " AND b.region_code IN (%s)" % ",".join("?" * len(related))
        args.extend(related)
    q += " ORDER BY " + ("CASE WHEN b.window_start = '' THEN 1 ELSE 0 END, b.window_start ASC, b.created DESC" if sort == "soonest" else "b.created DESC")
    q += " LIMIT ?"; args.append(limit)
    with get_db() as db:
        rows = [_row(r) for r in db.execute(q, args).fetchall()]
    return rows


def list_own(user_id):
    with get_db() as db:
        rows = db.execute("SELECT b.*, u.name AS poster_name FROM tour_board b JOIN users u ON u.id = b.user_id "
                          "WHERE b.user_id = ? ORDER BY b.created DESC", (user_id,)).fetchall()
    return [_row(r) for r in rows]


def set_status(user_id, lid, status, filled_via=""):
    if status not in LISTING_STATUSES:
        return False
    with get_db() as db:
        cur = db.execute("UPDATE tour_board SET status=?, updated=?, filled_via=CASE WHEN ?='filled' THEN ? ELSE filled_via END, "
                         "filled_at=CASE WHEN ?='filled' THEN ? ELSE filled_at END WHERE id=? AND user_id=?",
                         (status, _now(), status, filled_via or "", status, _now(), lid, user_id))
    if cur.rowcount:
        event("listing_" + status, user_id, lid)
    return cur.rowcount > 0


def renew(lid, user_id=None, token=None):
    """Extend an open (or lapsed) listing for another EXPIRE_DAYS. Either
    the owner (user_id) or the emailed token authorises it.

    A token arrives by GET from an email client, which may prefetch it, so
    it may only extend a listing that is still meant to be up. It must not
    resurrect one the owner deliberately closed or marked filled - only the
    owner, signed in, can reopen those."""
    cur = get_listing(lid)
    if cur is None:
        return False
    by_owner = bool(user_id and cur["user_id"] == user_id)
    by_token = bool(token and cur.get("renew_token") and token == cur["renew_token"])
    if not (by_owner or by_token):
        return False
    if by_token and not by_owner and cur.get("status") != "open":
        return False
    expires = (datetime.now(timezone.utc) + timedelta(days=EXPIRE_DAYS)).isoformat(timespec="seconds")
    with get_db() as db:
        db.execute("UPDATE tour_board SET status='open', expires_at=?, renew_notice_at='', renew_token=?, updated=? WHERE id=?",
                   (expires, uuid.uuid4().hex, _now(), lid))
    event("listing_renewed", cur["user_id"], lid)
    return True


def delete_listing(user_id, lid):
    with get_db() as db:
        cur = db.execute("DELETE FROM tour_board WHERE id=? AND user_id=?", (lid, user_id))
        if cur.rowcount:
            db.execute("DELETE FROM tour_board_replies WHERE listing_id=?", (lid,))
            db.execute("DELETE FROM board_messages WHERE thread_id IN (SELECT id FROM board_threads WHERE listing_id=?)", (lid,))
            db.execute("DELETE FROM board_threads WHERE listing_id=?", (lid,))
    return cur.rowcount > 0


def expiring_soon(within_days=RENEW_NOTICE_DAYS):
    """Open listings past or within `within_days` of expiry that have not
    had a renew notice yet. The caller sends the email and marks them."""
    cutoff = (datetime.now(timezone.utc) + timedelta(days=within_days)).isoformat(timespec="seconds")
    with get_db() as db:
        rows = db.execute("SELECT b.*, u.name AS poster_name, u.email AS poster_email FROM tour_board b JOIN users u ON u.id = b.user_id "
                          "WHERE b.status='open' AND b.expires_at != '' AND b.expires_at <= ? AND b.renew_notice_at = ''", (cutoff,)).fetchall()
    return [dict(_row(r), poster_email=r["poster_email"]) for r in rows]


def mark_renew_notice(lid):
    with get_db() as db:
        db.execute("UPDATE tour_board SET renew_notice_at=? WHERE id=?", (_now(), lid))


# --- threads --------------------------------------------------------------------

def start_or_get_thread(listing, replier_id):
    with get_db() as db:
        row = db.execute("SELECT id FROM board_threads WHERE listing_id=? AND replier_id=?", (listing["id"], replier_id)).fetchone()
        if row:
            return row["id"]
        tid = uuid.uuid4().hex
        now = _now()
        db.execute("INSERT INTO board_threads (id, listing_id, poster_id, replier_id, created, last_at) VALUES (?,?,?,?,?,?)",
                   (tid, listing["id"], listing["user_id"], replier_id, now, now))
    return tid


def add_message(thread_id, from_user_id, body):
    t = get_thread(thread_id)
    if t is None or from_user_id not in (t["poster_id"], t["replier_id"]) or not (body or "").strip():
        return None
    mid = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute("INSERT INTO board_messages (id, thread_id, from_user_id, body, created) VALUES (?,?,?,?,?)",
                   (mid, thread_id, from_user_id, body.strip()[:2000], now))
        if from_user_id == t["poster_id"]:
            db.execute("UPDATE board_threads SET last_at=?, replier_unread=replier_unread+1 WHERE id=?", (now, thread_id))
        else:
            db.execute("UPDATE board_threads SET last_at=?, poster_unread=poster_unread+1 WHERE id=?", (now, thread_id))
    event("message_sent", from_user_id, t["listing_id"])
    return mid


def get_thread(thread_id):
    with get_db() as db:
        row = db.execute("SELECT t.*, b.title AS listing_title, b.kind AS listing_kind, b.status AS listing_status, b.filled_via, "
                         "p.name AS poster_name, r.name AS replier_name FROM board_threads t "
                         "JOIN tour_board b ON b.id = t.listing_id JOIN users p ON p.id = t.poster_id JOIN users r ON r.id = t.replier_id "
                         "WHERE t.id = ?", (thread_id,)).fetchone()
    return dict(row) if row else None


def thread_messages(thread_id):
    with get_db() as db:
        rows = db.execute("SELECT m.*, u.name AS from_name FROM board_messages m JOIN users u ON u.id = m.from_user_id "
                          "WHERE m.thread_id = ? ORDER BY m.created", (thread_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r); d["ago"] = ago(d["created"]); out.append(d)
    return out


def mark_read(thread_id, user_id):
    with get_db() as db:
        db.execute("UPDATE board_threads SET poster_unread = CASE WHEN poster_id=? THEN 0 ELSE poster_unread END, "
                   "replier_unread = CASE WHEN replier_id=? THEN 0 ELSE replier_unread END WHERE id=?", (user_id, user_id, thread_id))


def threads_for_listing(listing_id):
    with get_db() as db:
        rows = db.execute("SELECT t.*, r.name AS replier_name, "
                          "(SELECT body FROM board_messages m WHERE m.thread_id = t.id ORDER BY m.created DESC LIMIT 1) AS last_body, "
                          "(SELECT COUNT(*) FROM board_messages m WHERE m.thread_id = t.id) AS message_count "
                          "FROM board_threads t JOIN users r ON r.id = t.replier_id WHERE t.listing_id = ? ORDER BY t.last_at DESC",
                          (listing_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r); d["ago"] = ago(d["last_at"]); out.append(d)
    return out


def inbox(user_id):
    """Threads where I am poster or replier, newest activity first, with my
    unread count on each."""
    with get_db() as db:
        rows = db.execute(
            "SELECT t.*, b.title AS listing_title, b.kind AS listing_kind, b.status AS listing_status, b.user_id AS listing_owner, "
            "p.name AS poster_name, r.name AS replier_name, "
            "(SELECT body FROM board_messages m WHERE m.thread_id = t.id ORDER BY m.created DESC LIMIT 1) AS last_body, "
            "(SELECT COUNT(*) FROM board_messages m WHERE m.thread_id = t.id) AS message_count "
            "FROM board_threads t JOIN tour_board b ON b.id = t.listing_id JOIN users p ON p.id = t.poster_id JOIN users r ON r.id = t.replier_id "
            "WHERE t.poster_id = ? OR t.replier_id = ? ORDER BY t.last_at DESC", (user_id, user_id)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["my_unread"] = d["poster_unread"] if d["poster_id"] == user_id else d["replier_unread"]
        d["other_name"] = d["replier_name"] if d["poster_id"] == user_id else d["poster_name"]
        d["i_am_poster"] = d["poster_id"] == user_id
        d["ago"] = ago(d["last_at"])
        out.append(d)
    return out


def unread_total(user_id):
    with get_db() as db:
        row = db.execute("SELECT COALESCE(SUM(CASE WHEN poster_id=? THEN poster_unread ELSE 0 END),0) + "
                         "COALESCE(SUM(CASE WHEN replier_id=? THEN replier_unread ELSE 0 END),0) AS n FROM board_threads "
                         "WHERE poster_id=? OR replier_id=?", (user_id, user_id, user_id, user_id)).fetchone()
    return int(row["n"] or 0)


def reply_counts(listing_ids):
    if not listing_ids:
        return {}
    marks = ",".join("?" * len(listing_ids))
    with get_db() as db:
        rows = db.execute("SELECT listing_id, COUNT(*) AS n, SUM(poster_unread) AS unread FROM board_threads "
                          "WHERE listing_id IN (%s) GROUP BY listing_id" % marks, list(listing_ids)).fetchall()
    return {r["listing_id"]: {"threads": r["n"], "unread": int(r["unread"] or 0)} for r in rows}


# compat: the old test/read path still asks for "replies" on a listing
def list_board_replies(listing_id):
    with get_db() as db:
        rows = db.execute("SELECT m.*, u.name AS from_name FROM board_messages m JOIN board_threads t ON t.id = m.thread_id "
                          "JOIN users u ON u.id = m.from_user_id WHERE t.listing_id = ? AND m.from_user_id = t.replier_id ORDER BY m.created",
                          (listing_id,)).fetchall()
    return [dict(r, message=r["body"]) for r in rows]


# --- saved searches -------------------------------------------------------------

def add_watch(user_id, kind="", region_code="", genres=None, window_start="", window_end=""):
    wid = uuid.uuid4().hex
    with get_db() as db:
        db.execute("INSERT INTO board_watches (id, user_id, kind, region_code, genres, window_start, window_end, created) VALUES (?,?,?,?,?,?,?,?)",
                   (wid, user_id, kind if kind in KINDS else "", region_code or "", json.dumps([g for g in (genres or []) if g]),
                    window_start or "", window_end or "", _now()))
    return wid


def list_watches(user_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM board_watches WHERE user_id=? ORDER BY created DESC", (user_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["genres"] = json.loads(d.get("genres") or "[]")
        d["label"] = watch_label(d)
        out.append(d)
    return out


def watch_label(w):
    bits = []
    if w.get("kind"):
        bits.append("venues" if w["kind"] == "venue" else "artists")
    if w.get("region_code"):
        bits.append(tx.region_label(w["region_code"]))
    if w.get("genres"):
        bits.append(" / ".join(tx.genre_label(g) for g in w["genres"]))
    if w.get("window_start"):
        bits.append(window_label(w["window_start"], w.get("window_end")))
    return " · ".join(bits) or "everything"


def delete_watch(user_id, wid):
    with get_db() as db:
        db.execute("DELETE FROM board_watches WHERE id=? AND user_id=?", (wid, user_id))


def matching_watches(listing):
    """Saved searches (other people's) that this new listing satisfies."""
    with get_db() as db:
        rows = db.execute("SELECT * FROM board_watches WHERE user_id != ?", (listing["user_id"],)).fetchall()
    hits = []
    for r in rows:
        w = dict(r); w["genres"] = json.loads(w.get("genres") or "[]")
        if w["kind"] and w["kind"] != listing["kind"]:
            continue
        if w["region_code"] and not (listing.get("region_code") and tx.regions_related(listing["region_code"], w["region_code"])):
            continue
        if w["genres"] and not set(w["genres"]) & set(listing.get("genres") or []):
            continue
        if w["window_start"] and listing.get("window_end") and listing["window_end"] < w["window_start"]:
            continue
        if w["window_end"] and listing.get("window_start") and listing["window_start"] > w["window_end"]:
            continue
        w["label"] = watch_label(w)
        hits.append(w)
    return hits


def touch_watch(wid):
    with get_db() as db:
        db.execute("UPDATE board_watches SET last_alert_at=? WHERE id=?", (_now(), wid))


# --- events & stats -------------------------------------------------------------

def event(kind, user_id="", listing_id=""):
    with get_db() as db:
        db.execute("INSERT INTO board_events (kind, user_id, listing_id, created) VALUES (?,?,?,?)", (kind, user_id or "", listing_id or "", _now()))


def stats():
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
    with get_db() as db:
        posts = db.execute("SELECT COUNT(*) AS n FROM tour_board WHERE created >= ?", (since,)).fetchone()["n"]
        msgs = db.execute("SELECT COUNT(*) AS n FROM board_messages WHERE created >= ?", (since,)).fetchone()["n"]
        filled = db.execute("SELECT COUNT(*) AS n FROM tour_board WHERE status='filled' AND filled_via != ''").fetchone()["n"]
        open_n = db.execute("SELECT COUNT(*) AS n FROM tour_board WHERE status='open' AND (expires_at='' OR expires_at >= ?)", (_now(),)).fetchone()["n"]
    return {"posts_30d": posts, "messages_30d": msgs, "matched": filled, "open": open_n}


# --- verified chips ---------------------------------------------------------------

def verified_chips(user_id):
    """Facts from the poster's own platform records, labelled by source.
    Nothing self-reported sneaks in here: that lives on the listing and is
    marked as such in the template."""
    chips = []
    with get_db() as db:
        rows = db.execute("SELECT city, status, date FROM tour_shows WHERE user_id = ?", (user_id,)).fetchall()
        slug_row = db.execute("SELECT slug FROM epk_profiles WHERE user_id = ?", (user_id,)).fetchone()
    played = [r for r in rows if r["status"] in ("played", "settled")]
    if played:
        chips.append({"key": "shows", "label": "%d show%s played" % (len(played), "" if len(played) == 1 else "s"), "source": "Tour Hub"})
        cities = {}
        for r in played:
            c = (r["city"] or "").strip()
            if c:
                cities[c] = cities.get(c, 0) + 1
        if cities:
            home = max(cities.items(), key=lambda kv: kv[1])
            if home[1] >= 2:
                chips.append({"key": "home", "label": "home market " + home[0], "source": "most-played city"})
    upcoming = [r for r in rows if r["status"] in ("confirmed", "advanced") and r["date"] >= _now()[:10]]
    if upcoming:
        chips.append({"key": "upcoming", "label": "%d confirmed date%s ahead" % (len(upcoming), "" if len(upcoming) == 1 else "s"), "source": "Tour Hub"})
    return {"chips": chips, "slug": (slug_row["slug"] if slug_row and slug_row["slug"] else "")}
