"""Rollout Engine data layer: rollout campaigns, creative assets, and the
generated post schedule. Posts link to Street Banker Links variants so every
piece of content is individually trackable."""

import json
import uuid

from db import get_db, _now


def create_campaign(user_id, fields):
    cid = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO ro_campaigns (id, user_id, ml_campaign_id, title, artist_name,"
            " release_date, rollout_length, goal, platforms, tone, status, settings, created, updated)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, user_id, fields.get("ml_campaign_id"), fields.get("title") or "Untitled Rollout",
             fields.get("artist_name") or "", fields.get("release_date") or "",
             int(fields.get("rollout_length") or 14), fields.get("goal") or "presaves",
             json.dumps(fields.get("platforms") or []), fields.get("tone") or "premium",
             "draft", json.dumps(fields.get("settings") or {}), now, now))
    return cid


def _row(row):
    d = dict(row)
    d["platforms"] = json.loads(d.get("platforms") or "[]")
    d["settings"] = json.loads(d.get("settings") or "{}")
    return d


def get_campaign(cid, user_id=None):
    q = "SELECT * FROM ro_campaigns WHERE id = ?"
    args = [cid]
    if user_id is not None:
        q += " AND user_id = ?"
        args.append(user_id)
    with get_db() as db:
        row = db.execute(q, args).fetchone()
    return _row(row) if row else None


def list_campaigns(user_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM ro_campaigns WHERE user_id = ? ORDER BY updated DESC",
                          (user_id,)).fetchall()
    return [_row(r) for r in rows]


def set_status(cid, status):
    with get_db() as db:
        db.execute("UPDATE ro_campaigns SET status = ?, updated = ? WHERE id = ?",
                   (status, _now(), cid))


def add_asset(campaign_id, asset_type, file_path="", lyrics_text=""):
    aid = uuid.uuid4().hex
    with get_db() as db:
        db.execute(
            "INSERT INTO ro_assets (id, campaign_id, asset_type, file_path, lyrics_text, created)"
            " VALUES (?,?,?,?,?,?)",
            (aid, campaign_id, asset_type, file_path, lyrics_text, _now()))
    return aid


def list_assets(campaign_id):
    with get_db() as db:
        rows = db.execute("SELECT * FROM ro_assets WHERE campaign_id = ? ORDER BY created",
                          (campaign_id,)).fetchall()
    return [dict(r) for r in rows]


def add_post(campaign_id, post):
    pid = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO ro_posts (id, campaign_id, variant_id, platform, post_type, phase,"
            " caption, hashtags, cta, asset_id, edit_plan, scheduled_date, status, created, updated)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, campaign_id, post.get("variant_id"), post["platform"],
             post.get("post_type") or "post", post["phase"], post.get("caption") or "",
             post.get("hashtags") or "", post.get("cta") or "", post.get("asset_id"),
             json.dumps(post["edit_plan"]) if post.get("edit_plan") else None,
             post.get("scheduled_date") or "", "draft", now, now))
    return pid


def list_posts(campaign_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM ro_posts WHERE campaign_id = ? ORDER BY scheduled_date, created",
            (campaign_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["edit_plan"] = json.loads(d["edit_plan"]) if d.get("edit_plan") else None
        out.append(d)
    return out


def get_post(post_id):
    with get_db() as db:
        row = db.execute("SELECT * FROM ro_posts WHERE id = ?", (post_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["edit_plan"] = json.loads(d["edit_plan"]) if d.get("edit_plan") else None
    return d


def update_post(post_id, fields):
    allowed = ("caption", "hashtags", "cta", "scheduled_date", "status",
               "published_url", "asset_id")
    sets, vals = [], []
    for key in allowed:
        if key in fields:
            sets.append("%s = ?" % key)
            # asset_id may be cleared to NULL; text columns coerce to "".
            vals.append(fields[key] if key == "asset_id"
                        else (fields[key] or ""))
    if not sets:
        return False
    sets.append("updated = ?")
    vals.extend([_now(), post_id])
    with get_db() as db:
        cur = db.execute("UPDATE ro_posts SET %s WHERE id = ?" % ", ".join(sets), vals)
    return cur.rowcount > 0


def clear_posts(campaign_id):
    with get_db() as db:
        db.execute("DELETE FROM ro_posts WHERE campaign_id = ?", (campaign_id,))


def post_status_counts(campaign_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT status, COUNT(*) AS n FROM ro_posts WHERE campaign_id = ? GROUP BY status",
            (campaign_id,)).fetchall()
    return {r["status"]: r["n"] for r in rows}
