"""Street Banker Links data layer: campaigns, destinations, events, fans,
consents, and link variants. Tables are created in db.init_db(); this module
holds the queries so the campaign engine stays separate from the core store.
"""

import json
import uuid

from db import get_db, _now

# --- Campaigns -----------------------------------------------------------------

_EDITABLE = ("title", "artist_name", "release_type", "campaign_type",
             "release_date", "cover_url", "description")


def create_campaign(user_id, slug, fields):
    campaign_id = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO ml_campaigns (id, user_id, slug, title, artist_name, release_type,"
            " campaign_type, status, release_date, cover_url, description, settings, created, updated)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (campaign_id, user_id, slug, fields.get("title") or "Untitled",
             fields.get("artist_name") or "", fields.get("release_type") or "Single",
             fields.get("campaign_type") or "release", "draft",
             fields.get("release_date") or "", fields.get("cover_url") or "",
             fields.get("description") or "",
             json.dumps(fields.get("settings") or {}), now, now),
        )
    return campaign_id


def update_campaign(campaign_id, user_id, fields):
    sets, vals = [], []
    for key in _EDITABLE:
        if key in fields:
            sets.append("%s = ?" % key)
            vals.append(fields[key] or "")
    if "settings" in fields:
        sets.append("settings = ?")
        vals.append(json.dumps(fields["settings"] or {}))
    if "status" in fields:
        sets.append("status = ?")
        vals.append(fields["status"])
    if fields.get("published_at"):
        sets.append("published_at = ?")
        vals.append(fields["published_at"])
    if "archived_at" in fields:
        sets.append("archived_at = ?")
        vals.append(fields["archived_at"])
    if not sets:
        return False
    sets.append("updated = ?")
    vals.extend([_now(), campaign_id, user_id])
    with get_db() as db:
        cur = db.execute(
            "UPDATE ml_campaigns SET %s WHERE id = ? AND user_id = ?" % ", ".join(sets), vals)
    return cur.rowcount > 0


def _row(row):
    d = dict(row)
    d["settings"] = json.loads(d.get("settings") or "{}")
    return d


def get_campaign(campaign_id, user_id=None):
    q = "SELECT * FROM ml_campaigns WHERE id = ?"
    args = [campaign_id]
    if user_id is not None:
        q += " AND user_id = ?"
        args.append(user_id)
    with get_db() as db:
        row = db.execute(q, args).fetchone()
    return _row(row) if row else None


def get_campaign_by_slug(slug):
    with get_db() as db:
        row = db.execute("SELECT * FROM ml_campaigns WHERE slug = ?", (slug,)).fetchone()
    return _row(row) if row else None


def list_campaigns(user_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM ml_campaigns WHERE user_id = ? ORDER BY updated DESC",
                          (user_id,)).fetchall()
    return [_row(r) for r in rows]


def duplicate_campaign(campaign_id, user_id, new_slug):
    src = get_campaign(campaign_id, user_id)
    if src is None:
        return None
    fields = {k: src[k] for k in _EDITABLE}
    fields["title"] = src["title"] + " (copy)"
    fields["settings"] = src["settings"]
    new_id = create_campaign(user_id, new_slug, fields)
    set_destinations(new_id, get_destinations(campaign_id))
    return new_id


# --- Destinations ----------------------------------------------------------------

def set_destinations(campaign_id, destinations):
    """Replace the campaign's destination set."""
    with get_db() as db:
        db.execute("DELETE FROM ml_destinations WHERE campaign_id = ?", (campaign_id,))
        for d in destinations:
            db.execute(
                "INSERT INTO ml_destinations (id, campaign_id, service_key, service_name,"
                " url, sort_order, is_active) VALUES (?,?,?,?,?,?,1)",
                (uuid.uuid4().hex, campaign_id, d["service_key"], d["service_name"],
                 d["url"], d.get("sort_order", 0)),
            )


def get_destinations(campaign_id, active_only=False):
    q = "SELECT * FROM ml_destinations WHERE campaign_id = ?"
    if active_only:
        q += " AND is_active = 1"
    q += " ORDER BY sort_order, service_name"
    with get_db() as db:
        rows = db.execute(q, (campaign_id,)).fetchall()
    return [dict(r) for r in rows]


def get_destination(dest_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM ml_destinations WHERE id = ?", (dest_id,)).fetchone()
    return dict(row) if row else None


# --- Events ------------------------------------------------------------------------

def track(campaign_id, event_type, variant_id=None, service_key=None,
          fan_id=None, referrer=None, utm_source=None):
    with get_db() as db:
        db.execute(
            "INSERT INTO ml_events (campaign_id, variant_id, event_type, service_key,"
            " fan_id, referrer, utm_source, created) VALUES (?,?,?,?,?,?,?,?)",
            (campaign_id, variant_id, event_type, service_key, fan_id,
             (referrer or "")[:300], (utm_source or "")[:100], _now()),
        )


def event_counts(campaign_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT event_type, COUNT(*) AS n FROM ml_events WHERE campaign_id = ?"
            " GROUP BY event_type", (campaign_id,)).fetchall()
    return {r["event_type"]: r["n"] for r in rows}


def breakdown(campaign_id, column, event_type=None, limit=8):
    if column not in ("service_key", "referrer", "utm_source", "variant_id"):
        raise ValueError(column)
    q = ("SELECT {col} AS k, COUNT(*) AS n FROM ml_events WHERE campaign_id = ?"
         " AND {col} IS NOT NULL AND {col} != ''").format(col=column)
    args = [campaign_id]
    if event_type:
        q += " AND event_type = ?"
        args.append(event_type)
    q += " GROUP BY {col} ORDER BY n DESC LIMIT {lim}".format(col=column, lim=int(limit))
    with get_db() as db:
        rows = db.execute(q, args).fetchall()
    return [(r["k"], r["n"]) for r in rows]


def timeline(campaign_id, days=14):
    with get_db() as db:
        rows = db.execute(
            "SELECT substr(created, 1, 10) AS day, COUNT(*) AS n FROM ml_events"
            " WHERE campaign_id = ? AND event_type = 'page_view'"
            " GROUP BY day ORDER BY day DESC LIMIT ?", (campaign_id, days)).fetchall()
    return list(reversed([(r["day"], r["n"]) for r in rows]))


def account_event_counts(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT e.event_type, COUNT(*) AS n FROM ml_events e"
            " JOIN ml_campaigns c ON c.id = e.campaign_id WHERE c.user_id = ?"
            " GROUP BY e.event_type", (user_id,)).fetchall()
    return {r["event_type"]: r["n"] for r in rows}


# --- Fans + consents --------------------------------------------------------------

def upsert_fan(user_id, email, campaign_id, name=""):
    """Create or refresh a fan record; returns the fan id."""
    email = email.lower().strip()
    now = _now()
    with get_db() as db:
        row = db.execute("SELECT id FROM ml_fans WHERE user_id = ? AND email = ?",
                         (user_id, email)).fetchone()
        if row:
            db.execute(
                "UPDATE ml_fans SET last_campaign_id = ?, updated = ?,"
                " name = CASE WHEN name = '' THEN ? ELSE name END WHERE id = ?",
                (campaign_id, now, name.strip(), row["id"]))
            return row["id"]
        fan_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO ml_fans (id, user_id, email, name, first_campaign_id,"
            " last_campaign_id, created, updated) VALUES (?,?,?,?,?,?,?,?)",
            (fan_id, user_id, email, name.strip(), campaign_id, campaign_id, now, now))
        return fan_id


_FAN_COUNTERS = ("total_visits", "total_clicks", "total_presaves", "total_captures")


def bump_fan(fan_id, field, amount=1):
    if field not in _FAN_COUNTERS:
        raise ValueError(field)
    with get_db() as db:
        db.execute("UPDATE ml_fans SET %s = %s + ?, updated = ? WHERE id = ?" % (field, field),
                   (amount, _now(), fan_id))


def set_fan_intent(fan_id, score, level):
    with get_db() as db:
        db.execute("UPDATE ml_fans SET intent_score = ?, intent_level = ? WHERE id = ?",
                   (score, level, fan_id))


def get_fan(fan_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM ml_fans WHERE id = ?", (fan_id,)).fetchone()
    return dict(row) if row else None


def list_fans(user_id, query=""):
    q = "SELECT * FROM ml_fans WHERE user_id = ?"
    args = [user_id]
    if query:
        q += " AND (email LIKE ? OR name LIKE ?)"
        args.extend(["%" + query + "%"] * 2)
    q += " ORDER BY intent_score DESC, updated DESC"
    with get_db() as db:
        rows = db.execute(q, args).fetchall()
    return [dict(r) for r in rows]


def campaign_fans(campaign_id):
    """Fans who consented on this campaign (deduped, with email)."""
    with get_db() as db:
        rows = db.execute(
            "SELECT DISTINCT f.* FROM ml_fans f "
            "JOIN ml_consents c ON c.fan_id = f.id "
            "WHERE c.campaign_id = ? AND f.email != ''", (campaign_id,)).fetchall()
    return [dict(r) for r in rows]


def add_consent(fan_id, campaign_id, consent_type, consent_text):
    with get_db() as db:
        db.execute(
            "INSERT INTO ml_consents (fan_id, campaign_id, consent_type, consent_text, created)"
            " VALUES (?,?,?,?,?)",
            (fan_id, campaign_id, consent_type, (consent_text or "")[:500], _now()))


def list_consents(fan_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM ml_consents WHERE fan_id = ? ORDER BY created",
                          (fan_id,)).fetchall()
    return [dict(r) for r in rows]


# --- Variants -----------------------------------------------------------------------

def create_variant(campaign_id, name, slug, utm_source="", utm_medium=""):
    variant_id = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO ml_variants (id, campaign_id, name, slug, utm_source, utm_medium,"
            " is_active, created) VALUES (?,?,?,?,?,?,1,?)",
            (variant_id, campaign_id, name, slug, utm_source, utm_medium, _now()))
    return variant_id


def get_variant_by_slug(slug):
    with get_db() as db:
        row = db.execute("SELECT * FROM ml_variants WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def list_variants(campaign_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM ml_variants WHERE campaign_id = ? ORDER BY created",
                          (campaign_id,)).fetchall()
    return [dict(r) for r in rows]


def variant_stats(campaign_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT variant_id, event_type, COUNT(*) AS n FROM ml_events"
            " WHERE campaign_id = ? AND variant_id IS NOT NULL"
            " GROUP BY variant_id, event_type", (campaign_id,)).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["variant_id"], {})[r["event_type"]] = r["n"]
    return out
