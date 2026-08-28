"""Street Banker Signal - storage.

TENANCY BOUNDARY (read this before adding a table)
--------------------------------------------------
Two layers, and the split is deliberate:

*Shared intelligence* - canonical artists, releases, public metrics and
public evidence. This is derived from public/provider data and is NOT owned
by any customer, so it carries no organization_id. It is the layer Street
Banker owns and improves for everyone.

*Tenant-owned* - anything that reveals what a customer is DOING: watchlists,
mandates, alerts, notes, and the link between an artist and a lead on the
Operator Desk. Every one of these tables carries `organization_id`, and every
query in this module filters on it. A customer must never learn which artists
another customer is looking at.

The rule: if a row would tell you a competitor's strategy, it is tenant-owned.

EVIDENCE
--------
Signal never asserts a distributor, manager or rights status as bare fact.
Every claim lands in `signal_evidence` with a source, an excerpt, a
confidence, a first/last-seen date and a status. The UI reads the status,
never a raw boolean. "We could not find a registration" is stored as
`potential_gap`, never as `unregistered`.
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone

from db import get_db, _now

# --- vocabulary -------------------------------------------------------------

ROLES = ["owner", "admin", "anr", "scout", "analyst", "deal", "viewer"]
ROLE_LABELS = {
    "owner": "Owner",
    "admin": "Admin",
    "anr": "A&R Executive",
    "scout": "Scout",
    "analyst": "Analyst",
    "deal": "Deal Team",
    "viewer": "Viewer",
}
# Permission -> roles holding it. The decorator and the templates read this
# one table, so a template can never offer a button the server would refuse.
PERMS = {
    "view":          {"owner", "admin", "anr", "scout", "analyst", "deal", "viewer"},
    "watch":         {"owner", "admin", "anr", "scout", "analyst"},
    "mandate_edit":  {"owner", "admin", "anr"},
    "push_to_desk":  {"owner", "admin", "anr", "scout"},
    "alert_edit":    {"owner", "admin", "anr"},
    "provider_admin": {"owner", "admin"},
    "manage_members": {"owner"},
}

# How a seat on the Operator Desk maps into a Signal role. Access is granted
# by a row in a roster, never by a name in code.
DESK_ROLE_MAP = {"owner": "owner", "admin": "admin", "member": "scout", "viewer": "viewer"}

DISTRIBUTOR_CLASSES = [
    "DIY / Self-Service", "Independent Distributor", "Selective Indie Services",
    "Independent Label", "Enterprise Distribution", "Major-Affiliated Distribution",
    "Major Label", "Artist-Owned Distribution", "Unknown", "Needs Research",
]
# Higher = more infrastructure behind the artist. The gap between momentum and
# this number is the whole point of the Distribution Gap score.
DISTRIBUTOR_SOPHISTICATION = {
    "DIY / Self-Service": 1, "Artist-Owned Distribution": 2,
    "Independent Distributor": 3, "Selective Indie Services": 4,
    "Independent Label": 5, "Enterprise Distribution": 7,
    "Major-Affiliated Distribution": 8, "Major Label": 9,
    "Unknown": 3, "Needs Research": 3,
}

EVIDENCE_STATUSES = ["verified", "high_confidence", "probable", "potential_gap",
                     "conflicting", "needs_verification", "unknown", "stale",
                     "manually_confirmed", "manually_rejected"]
EVIDENCE_STATUS_LABELS = {
    "verified": "Verified", "high_confidence": "High confidence",
    "probable": "Probable", "potential_gap": "Potential gap",
    "conflicting": "Conflicting", "needs_verification": "Needs verification",
    "unknown": "Unknown", "stale": "Stale",
    "manually_confirmed": "Manually confirmed", "manually_rejected": "Manually rejected",
}

CLAIM_DISTRIBUTOR = "distributor"
CLAIM_LABEL = "label"
CLAIM_CONTACT = "contact"
CLAIM_RIGHTS = "rights"

# Source type -> how much it is worth. An official roster outranks a
# directory; an unverified comment is never used at all.
SOURCE_WEIGHT = {
    "official_site": 0.95, "management_roster": 0.95, "agency_roster": 0.92,
    "label_page": 0.9, "publisher_page": 0.9, "verified_social": 0.8,
    "press_release": 0.78, "interview": 0.6, "festival_listing": 0.55,
    "venue_listing": 0.55, "release_metadata": 0.85, "work_registry": 0.8,
    "directory": 0.35, "internal": 0.9,
}

STALE_AFTER_DAYS = 90

STAGE_CAREER = ["Emerging", "Developing", "Established"]


def _uid():
    return uuid.uuid4().hex


def _dump(v):
    return json.dumps(v if v is not None else {})


def _load(t, default=None):
    try:
        return json.loads(t) if t else (default if default is not None else {})
    except (ValueError, TypeError):
        return default if default is not None else {}


def _row(r):
    return dict(r) if r is not None else None


def normalize_name(name):
    """Loose identity key: case, punctuation and spacing are noise."""
    out, prev_space = [], False
    for ch in (name or "").lower():
        if ch.isalnum():
            out.append(ch)
            prev_space = False
        elif not prev_space:
            out.append(" ")
            prev_space = True
    return "".join(out).strip()[:160]


# --- schema -----------------------------------------------------------------

def init_signal():
    with get_db() as db:
        db.executescript("""
            /* ---------- tenant-owned ---------- */
            CREATE TABLE IF NOT EXISTS signal_orgs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_members (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                user_id TEXT,
                email TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                last_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS signal_watchlists (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                name TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_watch_items (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                watchlist_id TEXT NOT NULL,
                artist_id TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                added_by TEXT NOT NULL,
                added_at TEXT NOT NULL,
                first_score REAL,
                first_score_version TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS signal_mandates (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                name TEXT NOT NULL,
                criteria TEXT NOT NULL DEFAULT '{}',
                active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_alert_rules (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                name TEXT NOT NULL,
                trigger_kind TEXT NOT NULL,
                threshold REAL NOT NULL DEFAULT 0,
                channel TEXT NOT NULL DEFAULT 'in_app',
                active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_alerts (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                artist_id TEXT,
                rule_id TEXT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL DEFAULT 'info',
                created_at TEXT NOT NULL,
                read_at TEXT
            );
            CREATE TABLE IF NOT EXISTS signal_desk_links (
                id TEXT PRIMARY KEY,
                organization_id TEXT NOT NULL,
                artist_id TEXT NOT NULL,
                lead_id TEXT NOT NULL,
                snapshot TEXT NOT NULL DEFAULT '{}',
                score_version TEXT NOT NULL DEFAULT '',
                why_now TEXT NOT NULL DEFAULT '',
                added_by TEXT NOT NULL,
                added_at TEXT NOT NULL
            );

            /* ---------- shared intelligence (no organization_id by design) ---------- */
            CREATE TABLE IF NOT EXISTS signal_artists (
                id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                genre TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                region TEXT NOT NULL DEFAULT '',
                career_stage TEXT NOT NULL DEFAULT '',
                monthly_listeners INTEGER NOT NULL DEFAULT 0,
                image_url TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                socials TEXT NOT NULL DEFAULT '{}',
                identity_confidence REAL NOT NULL DEFAULT 0.5,
                status TEXT NOT NULL DEFAULT 'active',
                first_seen_at TEXT NOT NULL,
                last_updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_artist_ids (
                id TEXT PRIMARY KEY,
                artist_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_releases (
                id TEXT PRIMARY KEY,
                artist_id TEXT NOT NULL,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL DEFAULT '',
                release_type TEXT NOT NULL DEFAULT 'Single',
                release_date TEXT NOT NULL DEFAULT '',
                upc TEXT NOT NULL DEFAULT '',
                label_text TEXT NOT NULL DEFAULT '',
                distributor_name TEXT NOT NULL DEFAULT '',
                distributor_class TEXT NOT NULL DEFAULT 'Unknown',
                copyright_line TEXT NOT NULL DEFAULT '',
                track_count INTEGER NOT NULL DEFAULT 0,
                provider TEXT NOT NULL DEFAULT '',
                provider_release_id TEXT NOT NULL DEFAULT '',
                first_observed_at TEXT NOT NULL,
                last_observed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_metrics (
                id TEXT PRIMARY KEY,
                artist_id TEXT NOT NULL,
                metric TEXT NOT NULL,
                metric_date TEXT NOT NULL,
                value REAL NOT NULL DEFAULT 0,
                provider TEXT NOT NULL DEFAULT '',
                captured_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_city_metrics (
                id TEXT PRIMARY KEY,
                artist_id TEXT NOT NULL,
                city TEXT NOT NULL,
                region TEXT NOT NULL DEFAULT '',
                country TEXT NOT NULL DEFAULT '',
                listeners INTEGER NOT NULL DEFAULT 0,
                change_28d_pct REAL NOT NULL DEFAULT 0,
                provider TEXT NOT NULL DEFAULT '',
                captured_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_evidence (
                id TEXT PRIMARY KEY,
                subject_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                claim_type TEXT NOT NULL,
                claim_key TEXT NOT NULL DEFAULT '',
                claim_value TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '{}',
                source_type TEXT NOT NULL DEFAULT '',
                source_label TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                excerpt TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'needs_verification',
                provider TEXT NOT NULL DEFAULT '',
                first_observed_at TEXT NOT NULL,
                last_verified_at TEXT NOT NULL,
                verified_by TEXT NOT NULL DEFAULT '',
                verified_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS signal_scores (
                id TEXT PRIMARY KEY,
                artist_id TEXT NOT NULL,
                score_key TEXT NOT NULL,
                value REAL NOT NULL DEFAULT 0,
                version TEXT NOT NULL,
                cohort TEXT NOT NULL DEFAULT '',
                explanation TEXT NOT NULL DEFAULT '{}',
                data_quality TEXT NOT NULL DEFAULT 'ok',
                computed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_provider_runs (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                capability TEXT NOT NULL DEFAULT '',
                ok INTEGER NOT NULL DEFAULT 1,
                ms INTEGER NOT NULL DEFAULT 0,
                cost REAL NOT NULL DEFAULT 0,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sig_members_org ON signal_members(organization_id, email);
            CREATE INDEX IF NOT EXISTS idx_sig_watch_org ON signal_watch_items(organization_id, artist_id);
            CREATE INDEX IF NOT EXISTS idx_sig_alerts_org ON signal_alerts(organization_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_sig_desk_org ON signal_desk_links(organization_id, artist_id);
            CREATE INDEX IF NOT EXISTS idx_sig_ids ON signal_artist_ids(provider, provider_id);
            CREATE INDEX IF NOT EXISTS idx_sig_rel_artist ON signal_releases(artist_id, release_date);
            CREATE INDEX IF NOT EXISTS idx_sig_metrics ON signal_metrics(artist_id, metric, metric_date);
            CREATE INDEX IF NOT EXISTS idx_sig_city ON signal_city_metrics(artist_id);
            CREATE INDEX IF NOT EXISTS idx_sig_ev ON signal_evidence(subject_type, subject_id, claim_type);
            CREATE INDEX IF NOT EXISTS idx_sig_scores ON signal_scores(artist_id, score_key, computed_at);
            CREATE INDEX IF NOT EXISTS idx_sig_runs ON signal_provider_runs(provider, created_at);
        """)
    ensure_default_org()


# --- organizations and membership -------------------------------------------

DEFAULT_ORG_SLUG = "street-banker"


def ensure_default_org():
    with get_db() as db:
        row = db.execute("SELECT * FROM signal_orgs WHERE slug = ?", (DEFAULT_ORG_SLUG,)).fetchone()
        if row:
            return _row(row)
        oid = _uid()
        db.execute("INSERT INTO signal_orgs (id, name, slug, is_default, created_at) VALUES (?,?,?,1,?)",
                   (oid, "Street Banker", DEFAULT_ORG_SLUG, _now()))
        row = db.execute("SELECT * FROM signal_orgs WHERE id = ?", (oid,)).fetchone()
    return _row(row)


def default_org():
    return ensure_default_org()


def list_orgs():
    with get_db() as db:
        return [_row(r) for r in db.execute("SELECT * FROM signal_orgs ORDER BY created_at").fetchall()]


def create_org(name, slug):
    slug = normalize_name(slug or name).replace(" ", "-")[:60] or _uid()[:8]
    with get_db() as db:
        if db.execute("SELECT 1 FROM signal_orgs WHERE slug=?", (slug,)).fetchone():
            return None
        oid = _uid()
        db.execute("INSERT INTO signal_orgs (id, name, slug, is_default, created_at) VALUES (?,?,?,0,?)",
                   (oid, (name or "Organization").strip()[:120], slug, _now()))
    return oid


def get_member(organization_id, email):
    email = (email or "").strip().lower()
    if not email or not organization_id:
        return None
    with get_db() as db:
        row = db.execute("SELECT * FROM signal_members WHERE organization_id=? AND lower(email)=? "
                         "AND status='active'", (organization_id, email)).fetchone()
    return _row(row)


def member_orgs(email):
    """Every org this person is an active member of, newest first."""
    email = (email or "").strip().lower()
    if not email:
        return []
    with get_db() as db:
        rows = db.execute(
            "SELECT o.*, m.role AS member_role FROM signal_members m "
            "JOIN signal_orgs o ON o.id = m.organization_id "
            "WHERE lower(m.email)=? AND m.status='active' ORDER BY o.is_default DESC, o.created_at",
            (email,)).fetchall()
    return [_row(r) for r in rows]


def upsert_member(organization_id, email, name, role, source="manual", user_id=None):
    email = (email or "").strip().lower()
    if not email or role not in ROLES:
        return None
    now = _now()
    with get_db() as db:
        row = db.execute("SELECT id FROM signal_members WHERE organization_id=? AND lower(email)=?",
                         (organization_id, email)).fetchone()
        if row:
            db.execute("UPDATE signal_members SET name=?, role=?, status='active', user_id=COALESCE(?, user_id) "
                       "WHERE id=?", ((name or "").strip()[:120], role, user_id, row["id"]))
            return row["id"]
        mid = _uid()
        db.execute("INSERT INTO signal_members (id, organization_id, user_id, email, name, role, status, source, created_at) "
                   "VALUES (?,?,?,?,?,?, 'active', ?, ?)",
                   (mid, organization_id, user_id, email, (name or "").strip()[:120], role, source, now))
    return mid


def list_members(organization_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM signal_members WHERE organization_id=? ORDER BY created_at",
                          (organization_id,)).fetchall()
    return [_row(r) for r in rows]


def set_member_role(organization_id, member_id, role):
    if role not in ROLES:
        return False
    with get_db() as db:
        cur = db.execute("UPDATE signal_members SET role=? WHERE id=? AND organization_id=?",
                         (role, member_id, organization_id))
    return cur.rowcount > 0


def remove_member(organization_id, member_id):
    with get_db() as db:
        cur = db.execute("UPDATE signal_members SET status='removed' WHERE id=? AND organization_id=?",
                         (member_id, organization_id))
    return cur.rowcount > 0


def touch_member(member_id):
    with get_db() as db:
        db.execute("UPDATE signal_members SET last_seen=? WHERE id=?", (_now(), member_id))


def sync_desk_roster(organization_id=None):
    """Mirror the Operator Desk roster into the default Signal org.

    Access to Signal is granted by a row in a roster that an owner controls -
    not by a name written into the source. Anyone already trusted on the Desk
    gets the matching Signal role; a Desk seat that is revoked stops
    refreshing here and can be removed by an owner.
    """
    try:
        import desk_store
    except ImportError:
        return 0
    org = default_org() if organization_id is None else {"id": organization_id}
    n = 0
    for u in desk_store.list_users():
        if (u.get("status") or "active") != "active":
            continue
        role = DESK_ROLE_MAP.get(u.get("role") or "viewer", "viewer")
        if upsert_member(org["id"], u.get("email"), u.get("name") or "", role, source="desk"):
            n += 1
    return n


def can(member, permission):
    return bool(member) and member.get("role") in PERMS.get(permission, ())


# --- canonical entities ------------------------------------------------------

def upsert_artist(provider, provider_artist_id, fields):
    """Resolve a provider artist to a canonical row.

    Identity is by (provider, provider_id) first - that is exact. Only when
    the provider is new do we fall back to the normalized name, and then the
    row keeps a lower identity_confidence so the UI can say so.
    """
    now = _now()
    name = (fields.get("name") or "").strip()[:200]
    norm = normalize_name(name)
    with get_db() as db:
        hit = db.execute("SELECT artist_id FROM signal_artist_ids WHERE provider=? AND provider_id=?",
                         (provider, provider_artist_id)).fetchone()
        artist_id = hit["artist_id"] if hit else None
        confidence = 0.99 if hit else 0.6
        if artist_id is None and norm:
            by_name = db.execute("SELECT id FROM signal_artists WHERE normalized_name=?", (norm,)).fetchone()
            if by_name:
                artist_id = by_name["id"]
                confidence = 0.72          # name match only - say so, do not claim certainty
        if artist_id is None:
            artist_id = _uid()
            db.execute(
                "INSERT INTO signal_artists (id, canonical_name, normalized_name, genre, country, city, region, "
                "career_stage, monthly_listeners, image_url, website, socials, identity_confidence, status, "
                "first_seen_at, last_updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'active', ?,?)",
                (artist_id, name, norm, fields.get("genre") or "", fields.get("country") or "",
                 fields.get("city") or "", fields.get("state") or fields.get("region") or "",
                 fields.get("career_stage") or "", int(fields.get("monthly_listeners") or 0),
                 fields.get("image_url") or "", fields.get("website") or "",
                 _dump(fields.get("socials") or {}), confidence, now, now))
        else:
            db.execute(
                "UPDATE signal_artists SET canonical_name=?, genre=?, country=?, city=?, region=?, career_stage=?, "
                "monthly_listeners=?, image_url=COALESCE(NULLIF(?,''), image_url), "
                "website=COALESCE(NULLIF(?,''), website), socials=?, last_updated_at=?, "
                "identity_confidence=MAX(identity_confidence, ?) WHERE id=?",
                (name, fields.get("genre") or "", fields.get("country") or "", fields.get("city") or "",
                 fields.get("state") or fields.get("region") or "", fields.get("career_stage") or "",
                 int(fields.get("monthly_listeners") or 0), fields.get("image_url") or "",
                 fields.get("website") or "", _dump(fields.get("socials") or {}), now, confidence, artist_id))
        if not hit:
            db.execute("INSERT INTO signal_artist_ids (id, artist_id, provider, provider_id, created_at) "
                       "VALUES (?,?,?,?,?)", (_uid(), artist_id, provider, provider_artist_id, now))
    return artist_id


def get_artist(artist_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM signal_artists WHERE id=?", (artist_id,)).fetchone()
    if row is None:
        return None
    d = _row(row)
    d["socials"] = _load(d.get("socials"), {})
    return d


def list_artists(limit=500):
    with get_db() as db:
        rows = db.execute("SELECT * FROM signal_artists WHERE status='active' "
                          "ORDER BY monthly_listeners DESC LIMIT ?", (limit,)).fetchall()
    return [_row(r) for r in rows]


def artist_provider_id(artist_id, provider):
    with get_db() as db:
        row = db.execute("SELECT provider_id FROM signal_artist_ids WHERE artist_id=? AND provider=?",
                         (artist_id, provider)).fetchone()
    return row["provider_id"] if row else None


def replace_releases(artist_id, provider, releases):
    now = _now()
    with get_db() as db:
        db.execute("DELETE FROM signal_releases WHERE artist_id=? AND provider=?", (artist_id, provider))
        for rel in releases:
            db.execute(
                "INSERT INTO signal_releases (id, artist_id, title, normalized_title, release_type, release_date, "
                "upc, label_text, distributor_name, distributor_class, copyright_line, track_count, provider, "
                "provider_release_id, first_observed_at, last_observed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_uid(), artist_id, (rel.get("title") or "")[:200], normalize_name(rel.get("title")),
                 rel.get("release_type") or "Single", rel.get("release_date") or "", rel.get("upc") or "",
                 rel.get("label_text") or "", rel.get("distributor_name") or "",
                 rel.get("distributor_class") or "Unknown", rel.get("copyright_line") or "",
                 int(rel.get("track_count") or 0), provider, rel.get("provider_release_id") or "", now, now))


def list_releases(artist_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM signal_releases WHERE artist_id=? ORDER BY release_date DESC",
                          (artist_id,)).fetchall()
    return [_row(r) for r in rows]


def replace_metrics(artist_id, provider, points):
    now = _now()
    with get_db() as db:
        db.execute("DELETE FROM signal_metrics WHERE artist_id=? AND provider=?", (artist_id, provider))
        db.executemany(
            "INSERT INTO signal_metrics (id, artist_id, metric, metric_date, value, provider, captured_at) "
            "VALUES (?,?,?,?,?,?,?)",
            [(_uid(), artist_id, p.get("metric") or "", p.get("date") or "", float(p.get("value") or 0),
              provider, now) for p in points])


def metric_series(artist_id, metric):
    with get_db() as db:
        rows = db.execute("SELECT metric_date, value FROM signal_metrics WHERE artist_id=? AND metric=? "
                          "ORDER BY metric_date", (artist_id, metric)).fetchall()
    return [(r["metric_date"], r["value"]) for r in rows]


def replace_city_metrics(artist_id, provider, cities):
    now = _now()
    with get_db() as db:
        db.execute("DELETE FROM signal_city_metrics WHERE artist_id=? AND provider=?", (artist_id, provider))
        db.executemany(
            "INSERT INTO signal_city_metrics (id, artist_id, city, region, country, listeners, change_28d_pct, "
            "provider, captured_at) VALUES (?,?,?,?,?,?,?,?,?)",
            [(_uid(), artist_id, c.get("city") or "", c.get("region") or "", c.get("country") or "",
              int(c.get("listeners") or 0), float(c.get("change_28d_pct") or 0), provider, now)
             for c in cities])


def list_city_metrics(artist_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM signal_city_metrics WHERE artist_id=? ORDER BY listeners DESC",
                          (artist_id,)).fetchall()
    return [_row(r) for r in rows]


# --- evidence ---------------------------------------------------------------

def add_evidence(subject_type, subject_id, claim_type, claim_key, claim_value,
                 source_type, source_label, source_url, excerpt, confidence,
                 status=None, provider="", detail=None):
    """Record a claim WITH its receipt. Never write a claim without one."""
    now = _now()
    status = status or status_for_confidence(confidence)
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM signal_evidence WHERE subject_type=? AND subject_id=? AND claim_type=? "
            "AND claim_key=? AND claim_value=? AND source_type=?",
            (subject_type, subject_id, claim_type, claim_key, claim_value, source_type)).fetchone()
        if row:
            db.execute("UPDATE signal_evidence SET confidence=?, status=CASE WHEN status IN "
                       "('manually_confirmed','manually_rejected') THEN status ELSE ? END, "
                       "last_verified_at=?, excerpt=?, source_url=? WHERE id=?",
                       (confidence, status, now, excerpt or "", source_url or "", row["id"]))
            return row["id"]
        eid = _uid()
        db.execute(
            "INSERT INTO signal_evidence (id, subject_type, subject_id, claim_type, claim_key, claim_value, detail, "
            "source_type, source_label, source_url, excerpt, confidence, status, provider, first_observed_at, "
            "last_verified_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, subject_type, subject_id, claim_type, claim_key or "", claim_value or "", _dump(detail or {}),
             source_type or "", source_label or "", source_url or "", excerpt or "", float(confidence or 0),
             status, provider, now, now))
    return eid


def status_for_confidence(confidence):
    c = float(confidence or 0)
    if c >= 0.9:
        return "verified"
    if c >= 0.75:
        return "high_confidence"
    if c >= 0.55:
        return "probable"
    if c > 0:
        return "needs_verification"
    return "unknown"


def list_evidence(subject_type, subject_id, claim_type=None):
    q = "SELECT * FROM signal_evidence WHERE subject_type=? AND subject_id=?"
    args = [subject_type, subject_id]
    if claim_type:
        q += " AND claim_type=?"
        args.append(claim_type)
    q += " ORDER BY confidence DESC, last_verified_at DESC"
    with get_db() as db:
        rows = db.execute(q, args).fetchall()
    out = []
    for r in rows:
        d = _row(r)
        d["detail"] = _load(d.get("detail"), {})
        d["status_label"] = EVIDENCE_STATUS_LABELS.get(d["status"], d["status"])
        d["is_stale"] = _is_stale(d.get("last_verified_at"))
        out.append(d)
    return out


def _is_stale(ts):
    if not ts:
        return True
    try:
        when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when) > timedelta(days=STALE_AFTER_DAYS)


def set_evidence_verification(evidence_id, status, actor):
    """A human overrules the machine. Recorded as such, with who and when."""
    if status not in ("manually_confirmed", "manually_rejected", "needs_verification"):
        return False
    with get_db() as db:
        cur = db.execute("UPDATE signal_evidence SET status=?, verified_by=?, verified_at=? WHERE id=?",
                         (status, (actor or "")[:120], _now(), evidence_id))
    return cur.rowcount > 0


# --- scores ------------------------------------------------------------------

def save_score(artist_id, score_key, value, version, cohort, explanation, data_quality="ok"):
    with get_db() as db:
        db.execute("INSERT INTO signal_scores (id, artist_id, score_key, value, version, cohort, explanation, "
                   "data_quality, computed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (_uid(), artist_id, score_key, float(value), version, cohort or "",
                    _dump(explanation or {}), data_quality, _now()))


def latest_scores(artist_id):
    """The newest value per score key. History is never overwritten, so
    'what did we know at the time' stays answerable."""
    with get_db() as db:
        rows = db.execute(
            "SELECT s.* FROM signal_scores s JOIN (SELECT score_key, MAX(computed_at) AS m FROM signal_scores "
            "WHERE artist_id=? GROUP BY score_key) x ON x.score_key=s.score_key AND x.m=s.computed_at "
            "WHERE s.artist_id=?", (artist_id, artist_id)).fetchall()
    out = {}
    for r in rows:
        d = _row(r)
        d["explanation"] = _load(d.get("explanation"), {})
        out[d["score_key"]] = d
    return out


def scores_for_artists(artist_ids, score_key):
    if not artist_ids:
        return {}
    marks = ",".join("?" * len(artist_ids))
    with get_db() as db:
        rows = db.execute(
            "SELECT s.artist_id, s.value, s.version, s.explanation FROM signal_scores s JOIN "
            "(SELECT artist_id, MAX(computed_at) AS m FROM signal_scores WHERE score_key=? AND artist_id IN (%s) "
            "GROUP BY artist_id) x ON x.artist_id=s.artist_id AND x.m=s.computed_at WHERE s.score_key=?" % marks,
            [score_key] + list(artist_ids) + [score_key]).fetchall()
    return {r["artist_id"]: {"value": r["value"], "version": r["version"],
                             "explanation": _load(r["explanation"], {})} for r in rows}


def score_history(artist_id, score_key, limit=50):
    with get_db() as db:
        rows = db.execute("SELECT value, version, computed_at FROM signal_scores WHERE artist_id=? AND score_key=? "
                          "ORDER BY computed_at DESC LIMIT ?", (artist_id, score_key, limit)).fetchall()
    return [_row(r) for r in rows]


# --- watchlists (tenant-owned) ----------------------------------------------

def ensure_watchlist(organization_id, name, actor):
    with get_db() as db:
        row = db.execute("SELECT * FROM signal_watchlists WHERE organization_id=? AND name=?",
                         (organization_id, name)).fetchone()
        if row:
            return row["id"]
        wid = _uid()
        db.execute("INSERT INTO signal_watchlists (id, organization_id, name, created_by, created_at) "
                   "VALUES (?,?,?,?,?)", (wid, organization_id, name[:120], actor or "", _now()))
    return wid


def list_watchlists(organization_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT w.*, (SELECT COUNT(*) FROM signal_watch_items i WHERE i.watchlist_id=w.id) AS item_count "
            "FROM signal_watchlists w WHERE w.organization_id=? ORDER BY w.created_at", (organization_id,)).fetchall()
    return [_row(r) for r in rows]


def add_to_watchlist(organization_id, watchlist_id, artist_id, actor, note="", score=None, version=""):
    with get_db() as db:
        own = db.execute("SELECT 1 FROM signal_watchlists WHERE id=? AND organization_id=?",
                         (watchlist_id, organization_id)).fetchone()
        if not own:
            return None
        row = db.execute("SELECT id FROM signal_watch_items WHERE organization_id=? AND watchlist_id=? AND artist_id=?",
                         (organization_id, watchlist_id, artist_id)).fetchone()
        if row:
            return row["id"]
        iid = _uid()
        db.execute("INSERT INTO signal_watch_items (id, organization_id, watchlist_id, artist_id, note, added_by, "
                   "added_at, first_score, first_score_version) VALUES (?,?,?,?,?,?,?,?,?)",
                   (iid, organization_id, watchlist_id, artist_id, note[:400], actor or "", _now(),
                    score, version or ""))
    return iid


def watch_items(organization_id, watchlist_id=None):
    q = ("SELECT i.*, a.canonical_name, a.genre, a.city, a.country, a.monthly_listeners, w.name AS watchlist_name "
         "FROM signal_watch_items i JOIN signal_artists a ON a.id=i.artist_id "
         "JOIN signal_watchlists w ON w.id=i.watchlist_id WHERE i.organization_id=?")
    args = [organization_id]
    if watchlist_id:
        q += " AND i.watchlist_id=?"
        args.append(watchlist_id)
    q += " ORDER BY i.added_at DESC"
    with get_db() as db:
        return [_row(r) for r in db.execute(q, args).fetchall()]


def is_watched(organization_id, artist_id):
    with get_db() as db:
        row = db.execute("SELECT 1 FROM signal_watch_items WHERE organization_id=? AND artist_id=?",
                         (organization_id, artist_id)).fetchone()
    return bool(row)


def remove_watch_item(organization_id, item_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM signal_watch_items WHERE id=? AND organization_id=?",
                         (item_id, organization_id))
    return cur.rowcount > 0


# --- mandates (tenant-owned) -------------------------------------------------

def create_mandate(organization_id, name, criteria, actor):
    mid = _uid()
    now = _now()
    with get_db() as db:
        db.execute("INSERT INTO signal_mandates (id, organization_id, name, criteria, active, created_by, "
                   "created_at, updated_at) VALUES (?,?,?,?,1,?,?,?)",
                   (mid, organization_id, (name or "Mandate").strip()[:120], _dump(criteria or {}),
                    actor or "", now, now))
    return mid


def list_mandates(organization_id, active_only=False):
    q = "SELECT * FROM signal_mandates WHERE organization_id=?"
    if active_only:
        q += " AND active=1"
    q += " ORDER BY created_at DESC"
    with get_db() as db:
        rows = db.execute(q, (organization_id,)).fetchall()
    out = []
    for r in rows:
        d = _row(r)
        d["criteria"] = _load(d.get("criteria"), {})
        out.append(d)
    return out


def get_mandate(organization_id, mandate_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM signal_mandates WHERE id=? AND organization_id=?",
                         (mandate_id, organization_id)).fetchone()
    if row is None:
        return None
    d = _row(row)
    d["criteria"] = _load(d.get("criteria"), {})
    return d


def update_mandate(organization_id, mandate_id, name=None, criteria=None, active=None):
    sets, args = [], []
    if name is not None:
        sets.append("name=?"); args.append(name.strip()[:120])
    if criteria is not None:
        sets.append("criteria=?"); args.append(_dump(criteria))
    if active is not None:
        sets.append("active=?"); args.append(1 if active else 0)
    if not sets:
        return False
    sets.append("updated_at=?"); args.append(_now())
    args.extend([mandate_id, organization_id])
    with get_db() as db:
        cur = db.execute("UPDATE signal_mandates SET %s WHERE id=? AND organization_id=?" % ", ".join(sets), args)
    return cur.rowcount > 0


def delete_mandate(organization_id, mandate_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM signal_mandates WHERE id=? AND organization_id=?",
                         (mandate_id, organization_id))
    return cur.rowcount > 0


# --- alerts (tenant-owned) ---------------------------------------------------

ALERT_TRIGGERS = {
    "momentum_above": "SB Momentum rises above",
    "distribution_gap_above": "Distribution Gap rises above",
    "deal_readiness_above": "Deal Readiness rises above",
    "rights_health_below": "Rights Health falls below",
    "new_release": "A watched artist releases something",
    "distributor_change": "A watched artist's distributor appears to change",
}


def create_alert_rule(organization_id, name, trigger_kind, threshold, channel, actor):
    if trigger_kind not in ALERT_TRIGGERS:
        return None
    rid = _uid()
    with get_db() as db:
        db.execute("INSERT INTO signal_alert_rules (id, organization_id, name, trigger_kind, threshold, channel, "
                   "active, created_by, created_at) VALUES (?,?,?,?,?,?,1,?,?)",
                   (rid, organization_id, (name or "Alert").strip()[:120], trigger_kind,
                    float(threshold or 0), channel or "in_app", actor or "", _now()))
    return rid


def list_alert_rules(organization_id, active_only=False):
    q = "SELECT * FROM signal_alert_rules WHERE organization_id=?"
    if active_only:
        q += " AND active=1"
    q += " ORDER BY created_at DESC"
    with get_db() as db:
        return [_row(r) for r in db.execute(q, (organization_id,)).fetchall()]


def delete_alert_rule(organization_id, rule_id):
    with get_db() as db:
        cur = db.execute("DELETE FROM signal_alert_rules WHERE id=? AND organization_id=?",
                         (rule_id, organization_id))
    return cur.rowcount > 0


def raise_alert(organization_id, kind, title, body="", artist_id=None, rule_id=None, severity="info"):
    """Idempotent per (org, artist, kind, title) inside a day, so a sweep
    that runs on every page view cannot spam the same finding."""
    # The UTC date, because created_at below is stamped with _now(), which is
    # UTC. date.today() is the LOCAL date, and every evening in any timezone
    # west of UTC the two disagree: the row said tomorrow, the check asked
    # about today, nothing ever matched, and each sweep raised a duplicate.
    today = _now()[:10]
    with get_db() as db:
        dupe = db.execute("SELECT 1 FROM signal_alerts WHERE organization_id=? AND kind=? AND title=? "
                          "AND COALESCE(artist_id,'')=? AND substr(created_at,1,10)=?",
                          (organization_id, kind, title, artist_id or "", today)).fetchone()
        if dupe:
            return None
        aid = _uid()
        db.execute("INSERT INTO signal_alerts (id, organization_id, artist_id, rule_id, kind, title, body, "
                   "severity, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (aid, organization_id, artist_id, rule_id, kind, title[:200], body[:1000], severity, _now()))
    return aid


def list_alerts(organization_id, limit=100, unread_only=False):
    q = ("SELECT al.*, a.canonical_name FROM signal_alerts al "
         "LEFT JOIN signal_artists a ON a.id = al.artist_id WHERE al.organization_id=?")
    if unread_only:
        q += " AND al.read_at IS NULL"
    q += " ORDER BY al.created_at DESC LIMIT ?"
    with get_db() as db:
        return [_row(r) for r in db.execute(q, (organization_id, limit)).fetchall()]


def unread_alert_count(organization_id):
    with get_db() as db:
        row = db.execute("SELECT COUNT(*) AS n FROM signal_alerts WHERE organization_id=? AND read_at IS NULL",
                         (organization_id,)).fetchone()
    return row["n"] if row else 0


def mark_alerts_read(organization_id):
    with get_db() as db:
        db.execute("UPDATE signal_alerts SET read_at=? WHERE organization_id=? AND read_at IS NULL",
                   (_now(), organization_id))


# --- Operator Desk link (tenant-owned) --------------------------------------

def link_to_desk(organization_id, artist_id, lead_id, snapshot, score_version, why_now, actor):
    """Preserve exactly what Signal believed at the moment of the hand-off.
    This is what makes 'was the original recommendation right?' answerable."""
    with get_db() as db:
        row = db.execute("SELECT id FROM signal_desk_links WHERE organization_id=? AND artist_id=?",
                         (organization_id, artist_id)).fetchone()
        if row:
            return row["id"]
        lid = _uid()
        db.execute("INSERT INTO signal_desk_links (id, organization_id, artist_id, lead_id, snapshot, "
                   "score_version, why_now, added_by, added_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (lid, organization_id, artist_id, lead_id, _dump(snapshot or {}),
                    score_version or "", (why_now or "")[:600], actor or "", _now()))
    return lid


def desk_link_for(organization_id, artist_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM signal_desk_links WHERE organization_id=? AND artist_id=?",
                         (organization_id, artist_id)).fetchone()
    if row is None:
        return None
    d = _row(row)
    d["snapshot"] = _load(d.get("snapshot"), {})
    return d


def desk_link_by_lead(lead_id):
    """Reverse lookup: which artist produced this Operator Desk lead.

    Not organisation-scoped on purpose - the caller is the Desk, which has
    already authorised the viewer against its own roster, and a lead maps to
    exactly one artist.
    """
    if not lead_id:
        return None
    with get_db() as db:
        row = db.execute(
            "SELECT l.*, a.canonical_name FROM signal_desk_links l "
            "JOIN signal_artists a ON a.id = l.artist_id WHERE l.lead_id = ?",
            (lead_id,)).fetchone()
    if row is None:
        return None
    d = _row(row)
    d["snapshot"] = _load(d.get("snapshot"), {})
    return d


def list_desk_links(organization_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT l.*, a.canonical_name FROM signal_desk_links l "
            "JOIN signal_artists a ON a.id=l.artist_id WHERE l.organization_id=? ORDER BY l.added_at DESC",
            (organization_id,)).fetchall()
    out = []
    for r in rows:
        d = _row(r)
        d["snapshot"] = _load(d.get("snapshot"), {})
        out.append(d)
    return out


# --- provider usage / health -------------------------------------------------

def record_provider_run(provider, capability, ok, ms, cost=0.0, detail=""):
    with get_db() as db:
        db.execute("INSERT INTO signal_provider_runs (id, provider, capability, ok, ms, cost, detail, created_at) "
                   "VALUES (?,?,?,?,?,?,?,?)",
                   (_uid(), provider, capability or "", 1 if ok else 0, int(ms or 0), float(cost or 0),
                    (detail or "")[:300], _now()))


def provider_usage(days=30):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with get_db() as db:
        rows = db.execute(
            "SELECT provider, COUNT(*) AS runs, SUM(ok) AS ok_runs, AVG(ms) AS avg_ms, SUM(cost) AS cost "
            "FROM signal_provider_runs WHERE created_at >= ? GROUP BY provider ORDER BY runs DESC",
            (since,)).fetchall()
    out = []
    for r in rows:
        d = _row(r)
        d["error_rate"] = 0.0 if not d["runs"] else round(1 - (d["ok_runs"] or 0) / float(d["runs"]), 3)
        d["avg_ms"] = int(d["avg_ms"] or 0)
        d["cost"] = round(d["cost"] or 0, 4)
        out.append(d)
    return out


def data_freshness():
    """When each shared table was last written. Drives the staleness banner.

    Returned as a list, not a dict, so templates iterate it directly rather
    than reaching for .items() - dict-method access in a template is how this
    codebase once shipped a built-in method onto a public page.
    """
    out = []
    with get_db() as db:
        for label, table, col in (("Artists", "signal_artists", "last_updated_at"),
                                  ("Metrics", "signal_metrics", "captured_at"),
                                  ("Releases", "signal_releases", "last_observed_at"),
                                  ("Evidence", "signal_evidence", "last_verified_at"),
                                  ("Scores", "signal_scores", "computed_at")):
            row = db.execute("SELECT MAX(%s) AS m, COUNT(*) AS n FROM %s" % (col, table)).fetchone()
            out.append({"label": label, "last": row["m"] or "", "rows": row["n"] or 0,
                        "stale": _is_stale(row["m"]) if row["m"] else True})
    return out


def counts():
    with get_db() as db:
        return {
            "artists": db.execute("SELECT COUNT(*) AS n FROM signal_artists").fetchone()["n"],
            "releases": db.execute("SELECT COUNT(*) AS n FROM signal_releases").fetchone()["n"],
            "evidence": db.execute("SELECT COUNT(*) AS n FROM signal_evidence").fetchone()["n"],
            "metrics": db.execute("SELECT COUNT(*) AS n FROM signal_metrics").fetchone()["n"],
        }
