"""Street Banker Signal - the blueprint.

NAME: this file is `signal_hub.py`, never `signal.py`. The repo root is on
sys.path under both gunicorn and pytest, and a module called `signal` there
shadows the standard library's `signal` - which gunicorn's arbiter and
Werkzeug's reloader both import at startup. The blueprint is still named
"signal" and still serves /signal.

Server-rendered, progressive enhancement: every filter is a GET parameter and
every action is a form post that redirects. Nothing on these pages needs
JavaScript to work.

Access composes with what the app already has rather than replacing it:
  * the global before_request login wall already covers /signal/*;
  * /signal is in neither plans._ARTIST_PATHS nor _PRO_PATHS, so it is not
    plan-gated;
  * membership is a row in signal_members, seeded from the Operator Desk
    roster and the OWNER_EMAILS env - no person's name appears in this file.
"""
import csv
import io
import json
from datetime import date, datetime, timedelta, timezone

from flask import (Blueprint, redirect, render_template, request, session,
                   url_for, jsonify, Response, abort)

import db as store
import signal_ingest as ingest
import signal_providers as providers
import signal_scoring as scoring
import signal_store as sstore

bp = Blueprint("signal", __name__, url_prefix="/signal")

_base_url = lambda: ""
_is_owner_email = lambda email: False


# --- identity and access ----------------------------------------------------

def _me():
    uid = session.get("user_id")
    return store.get_user(uid) if uid else None


def _login():
    return redirect(url_for("login", next=request.path))


def _member(app_user, org=None):
    """The Signal seat for this login, or None.

    An owner (by the app's own OWNER_EMAILS predicate) is enrolled on first
    sight so the product is never locked out of itself. Everyone else needs a
    roster row an owner controls.
    """
    if app_user is None:
        return None, None
    org = org or sstore.default_org()
    email = (app_user.get("email") or "").strip().lower()
    m = sstore.get_member(org["id"], email)
    if m is None and _is_owner_email(email):
        sstore.upsert_member(org["id"], email, app_user.get("name") or "Owner",
                             "owner", source="env", user_id=app_user.get("id"))
        m = sstore.get_member(org["id"], email)
    if m is None:
        # a seat on the Operator Desk carries into Signal
        sstore.sync_desk_roster(org["id"])
        m = sstore.get_member(org["id"], email)
    return org, m


def require(permission="view"):
    """Server-side check before every handler. The decorator is the
    boundary; a template hiding a button is only cosmetic."""
    def wrap(fn):
        def guarded(*args, **kwargs):
            app_user = _me()
            if app_user is None:
                return _login()
            org, member = _member(app_user)
            if member is None:
                return render_template("signal/denied.html", **_ctx(None, None, denied=True)), 403
            if not sstore.can(member, permission):
                return render_template("signal/denied.html",
                                       **_ctx(org, member, denied=True,
                                              reason="Your role does not allow that.")), 403
            sstore.touch_member(member["id"])
            return fn(org, member, *args, **kwargs)
        guarded.__name__ = fn.__name__
        return guarded
    return wrap


def _ctx(org, member, **extra):
    reg = providers.registry()
    base = {
        "org": org,
        "me": member,
        "sg_can": (lambda perm: sstore.can(member, perm)),
        "demo_mode": reg.is_demo(),
        "unread_alerts": sstore.unread_alert_count(org["id"]) if org else 0,
        "score_labels": scoring.SCORE_LABELS,
        "score_version": scoring.SCORE_VERSION,
        "nav_items": [
            ("/signal", "Dashboard"),
            ("/signal/breaking", "Breaking Now"),
            ("/signal/briefs", "Audio Briefs"),
            ("/signal/early", "Early Signal"),
            ("/signal/cities", "City Ignition"),
            ("/signal/undervalued", "Undervalued Infrastructure"),
            ("/signal/deal-ready", "Deal Ready"),
            ("/signal/watchlists", "Watchlists"),
            ("/signal/mandates", "Mandates"),
            ("/signal/alerts", "Alerts"),
        ],
        "here": request.path,
    }
    base.update(extra)
    return base


# --- shared board machinery -------------------------------------------------

def _rows_for(org, artist_ids=None, limit=200):
    """Assemble the row every board renders: artist + its latest scores +
    the current distribution reading + whether this org is already on it."""
    artists = sstore.list_artists(limit=limit)
    if artist_ids is not None:
        keep = set(artist_ids)
        artists = [a for a in artists if a["id"] in keep]
    ids = [a["id"] for a in artists]
    mom = sstore.scores_for_artists(ids, scoring.MOMENTUM)
    gap = sstore.scores_for_artists(ids, scoring.DISTRIBUTION_GAP)
    rights = sstore.scores_for_artists(ids, scoring.RIGHTS_HEALTH)
    deal = sstore.scores_for_artists(ids, scoring.DEAL_READINESS)
    quality = sstore.scores_for_artists(ids, scoring.MOMENTUM_QUALITY)
    rows = []
    for a in artists:
        m = mom.get(a["id"]) or {}
        expl = m.get("explanation") or {}
        rows.append({
            "artist": a,
            "momentum": round(m.get("value") or 0),
            "quality": round((quality.get(a["id"]) or {}).get("value") or 0),
            "gap": round((gap.get(a["id"]) or {}).get("value") or 0),
            "rights": round((rights.get(a["id"]) or {}).get("value") or 0),
            "deal": round((deal.get(a["id"]) or {}).get("value") or 0),
            "change_7d": expl.get("change_7d"),
            "change_28d": expl.get("change_28d"),
            "change_90d": expl.get("change_90d"),
            "shape": expl.get("shape") or "",
            "anomaly": scoring.anomaly_status(expl.get("anomaly_penalty") or 0),
            "distribution": (expl.get("distribution") or {}),
            "watched": sstore.is_watched(org["id"], a["id"]),
            "on_desk": bool(sstore.desk_link_for(org["id"], a["id"])),
        })
    return rows


def _distribution_for(rows):
    """Attach the distribution reading from the gap score explanation."""
    ids = [r["artist"]["id"] for r in rows]
    gaps = sstore.scores_for_artists(ids, scoring.DISTRIBUTION_GAP)
    for r in rows:
        expl = (gaps.get(r["artist"]["id"]) or {}).get("explanation") or {}
        r["distribution"] = expl.get("distribution") or {}
    return rows


# --- pages ------------------------------------------------------------------

@bp.route("")
@bp.route("/")
@require("view")
def dashboard(org, member):
    ingest.ensure_universe()
    ingest.sweep(org["id"])
    rows = _distribution_for(_rows_for(org))
    breaking = sorted([r for r in rows if (r["change_7d"] or 0) > 3],
                      key=lambda r: -(r["change_7d"] or 0))[:6]
    gaps = sorted(rows, key=lambda r: -r["gap"])[:6]
    rights = sorted([r for r in rows if r["rights"] and r["rights"] < 60],
                    key=lambda r: r["rights"])[:6]
    return render_template("signal/dashboard.html", **_ctx(
        org, member, breaking=breaking, gaps=gaps, rights=rights,
        counts=sstore.counts(), freshness=sstore.data_freshness(),
        alerts=sstore.list_alerts(org["id"], limit=8),
        desk_links=sstore.list_desk_links(org["id"])[:6]))


@bp.route("/breaking")
@require("view")
def breaking(org, member):
    ingest.ensure_universe()
    rows = _distribution_for(_rows_for(org))
    rows = [r for r in rows if (r["change_7d"] or 0) > 0]
    rows.sort(key=lambda r: -(r["change_7d"] or 0))
    return render_template("signal/board.html", **_ctx(
        org, member, board_title="Breaking Now",
        board_lede="Artists whose audience materially changed in the last seven days. "
                   "Sorted by 7-day movement; every number opens its own explanation.",
        rows=rows, sort_col="change_7d"))


@bp.route("/early")
@require("view")
def early(org, member):
    """Smaller artists accelerating faster than their own cohort. The point
    is abnormal acceleration from a credible base - not raw size."""
    ingest.ensure_universe()
    rows = _distribution_for(_rows_for(org))
    picked = []
    for r in rows:
        a = r["artist"]
        if (a.get("monthly_listeners") or 0) > 250000:
            continue
        if r["momentum"] < 45:
            continue
        if (r["change_28d"] or 0) < 8:
            continue
        picked.append(r)
    picked.sort(key=lambda r: -(r["momentum"]))
    return render_template("signal/board.html", **_ctx(
        org, member, board_title="Early Signal",
        board_lede="Under 250k monthly listeners, accelerating across more than one period, "
                   "and scored against artists at the same career stage - not against superstars.",
        rows=picked, sort_col="momentum"))


@bp.route("/cities")
@require("view")
def cities(org, member):
    ingest.ensure_universe()
    rows = _rows_for(org)
    by_city = {}
    for r in rows:
        for c in sstore.list_city_metrics(r["artist"]["id"]):
            if (c.get("change_28d_pct") or 0) < 10:
                continue
            key = "%s, %s" % (c["city"], c.get("region") or c.get("country") or "")
            entry = by_city.setdefault(key, {"city": c["city"], "region": c.get("region") or "",
                                             "country": c.get("country") or "", "artists": []})
            entry["artists"].append({"artist": r["artist"], "change": c.get("change_28d_pct"),
                                     "listeners": c.get("listeners"), "momentum": r["momentum"]})
    ignitions = sorted(by_city.values(), key=lambda e: -len(e["artists"]))
    for e in ignitions:
        e["artists"].sort(key=lambda x: -(x["change"] or 0))
        e["count"] = len(e["artists"])
    return render_template("signal/cities.html", **_ctx(
        org, member, ignitions=ignitions[:20]))


@bp.route("/undervalued")
@require("view")
def undervalued(org, member):
    ingest.ensure_universe()
    rows = _distribution_for(_rows_for(org))
    rows = [r for r in rows if r["gap"] >= 55]
    rows.sort(key=lambda r: -r["gap"])
    return render_template("signal/board.html", **_ctx(
        org, member, board_title="Undervalued Infrastructure",
        board_lede="Where the audience is running ahead of the business behind it - "
                   "distribution, team, catalogue consistency or rights.",
        rows=rows, sort_col="gap"))


@bp.route("/deal-ready")
@require("view")
def deal_ready(org, member):
    ingest.ensure_universe()
    rows = _distribution_for(_rows_for(org))
    mandate_id = (request.args.get("mandate") or "").strip()
    mandate = sstore.get_mandate(org["id"], mandate_id) if mandate_id else None
    if mandate:
        rows = [r for r in rows if _mandate_match(r, mandate)[0]]
    rows = [r for r in rows if r["deal"] >= 45]
    rows.sort(key=lambda r: -r["deal"])
    return render_template("signal/board.html", **_ctx(
        org, member, board_title="Deal Ready",
        board_lede="Momentum quality, release cadence, contactability and rights health, "
                   "scored together. Filter by one of your mandates to see fit.",
        rows=rows, sort_col="deal", mandates=sstore.list_mandates(org["id"], active_only=True),
        active_mandate=mandate))


def _mandate_match(row, mandate):
    """Return (matched, reasons, misses) for one artist against a mandate."""
    c = mandate.get("criteria") or {}
    a = row["artist"]
    reasons, misses = [], []
    genres = [g.strip().lower() for g in (c.get("genres") or "").split(",") if g.strip()]
    if genres:
        if (a.get("genre") or "").lower() in genres:
            reasons.append("Genre %s is on the mandate" % a.get("genre"))
        else:
            misses.append("Genre %s is not on the mandate" % (a.get("genre") or "unknown"))
    if c.get("max_listeners"):
        if (a.get("monthly_listeners") or 0) <= int(c["max_listeners"]):
            reasons.append("Audience is inside the ceiling")
        else:
            misses.append("Audience above the mandate ceiling")
    if c.get("min_momentum"):
        if row["momentum"] >= float(c["min_momentum"]):
            reasons.append("SB Momentum %d clears the floor" % row["momentum"])
        else:
            misses.append("SB Momentum %d below the floor" % row["momentum"])
    if c.get("min_gap"):
        if row["gap"] >= float(c["min_gap"]):
            reasons.append("Distribution Gap %d clears the floor" % row["gap"])
        else:
            misses.append("Distribution Gap %d below the floor" % row["gap"])
    return (not misses), reasons, misses


@bp.route("/artist/<artist_id>")
@require("view")
def artist(org, member, artist_id):
    a = sstore.get_artist(artist_id)
    if a is None:
        abort(404)
    scores = sstore.latest_scores(artist_id)
    if not scores:
        scoring.score_artist(artist_id)
        scores = sstore.latest_scores(artist_id)
    features = scoring.artist_features(artist_id, a)
    rec = scoring.recommend(artist_id, features=features)
    tab = request.args.get("tab") or "overview"
    momentum_expl = (scores.get(scoring.MOMENTUM) or {}).get("explanation") or {}
    return render_template("signal/artist.html", **_ctx(
        org, member, a=a, scores=scores, tab=tab, rec=rec,
        releases=sstore.list_releases(artist_id),
        cities=sstore.list_city_metrics(artist_id),
        contacts=sstore.list_evidence("artist", artist_id, sstore.CLAIM_CONTACT),
        rights_evidence=sstore.list_evidence("artist", artist_id, sstore.CLAIM_RIGHTS),
        dist_evidence=sstore.list_evidence("artist", artist_id, sstore.CLAIM_DISTRIBUTOR),
        distribution=scoring.current_distribution(sstore.list_releases(artist_id)),
        momentum_expl=momentum_expl,
        cohort=scoring.cohort_of(a),
        percentile=scoring.cohort_percentile(a, (scores.get(scoring.MOMENTUM) or {}).get("value") or 0,
                                             scoring.MOMENTUM),
        watched=sstore.is_watched(org["id"], artist_id),
        desk_link=sstore.desk_link_for(org["id"], artist_id),
        has_desk_seat=_has_desk_seat(member),
        watchlists=sstore.list_watchlists(org["id"]),
        brief=_brief(a, scores, rec, features)))


def _brief(a, scores, rec, features):
    """The sourced research brief. Every sentence traces to a score or a
    piece of evidence held on this page - nothing is invented here."""
    m = (scores.get(scoring.MOMENTUM) or {})
    expl = m.get("explanation") or {}
    rh = (scores.get(scoring.RIGHTS_HEALTH) or {})
    why = []
    if expl.get("change_28d") is not None:
        why.append("Listening is %s%.1f%% over 28 days (%s)." % (
            "+" if expl["change_28d"] >= 0 else "", expl["change_28d"], (expl.get("shape") or "").lower()))
    rising = [c for c in features["cities"] if (c.get("change_28d_pct") or 0) > 10]
    if rising:
        why.append("%d market%s accelerating, led by %s." % (
            len(rising), "" if len(rising) == 1 else "s", rising[0]["city"]))
    if expl.get("anomaly_reasons"):
        why.append("Flagged for review: %s." % "; ".join(expl["anomaly_reasons"]).lower())
    return {
        "why_now": why or ["Not enough history yet to say why this artist is moving."],
        "quality": expl.get("shape") or "Unknown",
        "infrastructure": rec.get("distribution") or {},
        "opportunity": rec.get("lanes") or [],
        "risks": (expl.get("anomaly_reasons") or []) + (
            ["Rights Health is %d - questions to answer before any deal." % round(rh.get("value") or 0)]
            if (rh.get("value") or 100) < 60 else []),
        "recommendation": rec.get("action"),
        "best_contact": rec.get("best_contact"),
    }


@bp.route("/artist/<artist_id>/score/<score_key>")
@require("view")
def score_detail(org, member, artist_id, score_key):
    a = sstore.get_artist(artist_id)
    if a is None or score_key not in scoring.SCORE_LABELS:
        abort(404)
    s = sstore.latest_scores(artist_id).get(score_key)
    if s is None:
        abort(404)
    return render_template("signal/score.html", **_ctx(
        org, member, a=a, s=s, score_key=score_key,
        label=scoring.SCORE_LABELS[score_key],
        history=sstore.score_history(artist_id, score_key),
        percentile=scoring.cohort_percentile(a, s["value"], score_key)))


# --- actions ----------------------------------------------------------------

@bp.route("/artist/<artist_id>/watch", methods=["POST"])
@require("watch")
def watch(org, member, artist_id):
    if sstore.get_artist(artist_id) is None:
        abort(404)
    name = (request.form.get("watchlist") or "Priority").strip()[:120] or "Priority"
    wid = sstore.ensure_watchlist(org["id"], name, member["name"])
    scores = sstore.latest_scores(artist_id)
    m = (scores.get(scoring.MOMENTUM) or {})
    sstore.add_to_watchlist(org["id"], wid, artist_id, member["name"],
                            note=(request.form.get("note") or "")[:400],
                            score=m.get("value"), version=m.get("version") or "")
    return redirect(request.form.get("next") or url_for("signal.artist", artist_id=artist_id))


@bp.route("/watchlists")
@require("view")
def watchlists(org, member):
    return render_template("signal/watchlists.html", **_ctx(
        org, member, lists=sstore.list_watchlists(org["id"]),
        items=sstore.watch_items(org["id"])))


@bp.route("/watchlists/<item_id>/remove", methods=["POST"])
@require("watch")
def watch_remove(org, member, item_id):
    sstore.remove_watch_item(org["id"], item_id)
    return redirect(url_for("signal.watchlists"))


@bp.route("/artist/<artist_id>/operator-desk", methods=["POST"])
@require("push_to_desk")
def to_desk(org, member, artist_id):
    """Hand an artist to the Operator Desk that already exists.

    Creates (or finds) the lead, attaches the exact intelligence snapshot,
    writes a first note and a follow-up task, and starts watching. The
    snapshot is what makes 'was Signal right?' answerable later.
    """
    import desk_store
    a = sstore.get_artist(artist_id)
    if a is None:
        abort(404)
    # The Desk has its own roster. Someone can hold a Signal seat without one,
    # and sending them to a Desk page they cannot open is a dead end - so the
    # lead is still created (it belongs to the organisation, not to them) and
    # they are returned to the artist with the link surfaced instead.
    has_desk_seat = _has_desk_seat(member)
    existing = sstore.desk_link_for(org["id"], artist_id)
    if existing:
        if has_desk_seat:
            return redirect("/operator-desk/leads/%s" % existing["lead_id"])
        return redirect(url_for("signal.artist", artist_id=artist_id))

    scores = sstore.latest_scores(artist_id)
    features = scoring.artist_features(artist_id, a)
    rec = scoring.recommend(artist_id, features=features)
    dist = rec.get("distribution") or {}
    best = rec.get("best_contact") or {}
    # desk_store takes an actor DICT (it reads actor["id"] / ["name"]). Use
    # the real Desk seat when this person has one, so the Desk's own activity
    # log attributes the action to them rather than to a stranger.
    desk_actor = desk_store.get_user_by_email(member["email"]) or \
        {"id": None, "name": member["name"]}

    def sval(key):
        return round((scores.get(key) or {}).get("value") or 0)

    fields = {
        "artist_name": a["canonical_name"],
        "genre": a.get("genre") or "",
        "city": a.get("city") or "",
        "country": a.get("country") or "",
        "current_distributor": dist.get("name") or "",
        "website": a.get("website") or "",
        "contact_name": (best.get("value") or "") if best else "",
        "role": (best.get("role") or "") if best else "",
        "lead_source": "Street Banker Signal",
        "priority": "High" if rec.get("urgency") == "high" else "Medium",
        "assigned_to": member["name"],
    }
    lead_id = desk_store.create_lead(fields, rec.get("lanes") or [], ["signal"], desk_actor)

    why = " ".join(_brief(a, scores, rec, features)["why_now"])
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scores": {k: sval(k) for k in scoring.SCORE_LABELS},
        "distribution": dist,
        "best_contact": best,
        "recommendation": rec.get("action"),
        "lanes": rec.get("lanes"),
        "monthly_listeners": a.get("monthly_listeners"),
        "cohort": scoring.cohort_of(a),
    }
    desk_store.add_note(
        lead_id, desk_actor, "General Note",
        "Added from Street Banker Signal.\n\nWhy now: %s\n\nSB Momentum %d - Distribution Gap %d - "
        "Rights Health %d - Deal Readiness %d (score version %s).\nRecommendation: %s.\n\n%s" % (
            why or "n/a", sval(scoring.MOMENTUM), sval(scoring.DISTRIBUTION_GAP),
            sval(scoring.RIGHTS_HEALTH), sval(scoring.DEAL_READINESS), scoring.SCORE_VERSION,
            rec.get("action"), rec.get("disclaimer")),
        next_step=rec.get("action"))
    desk_store.add_task(
        desk_actor, "Follow up: %s" % a["canonical_name"],
        description="Signal recommended: %s" % rec.get("action"),
        lead_id=lead_id, assigned_to=member["name"],
        due_date=(date.today() + timedelta(days=3)).isoformat(),
        category="Follow-Up")

    sstore.link_to_desk(org["id"], artist_id, lead_id, snapshot, scoring.SCORE_VERSION,
                        why, member["name"])
    wid = sstore.ensure_watchlist(org["id"], "Operator Desk", member["name"])
    sstore.add_to_watchlist(org["id"], wid, artist_id, member["name"],
                            score=(scores.get(scoring.MOMENTUM) or {}).get("value"),
                            version=scoring.SCORE_VERSION)
    if not has_desk_seat:
        return redirect(url_for("signal.artist", artist_id=artist_id))
    return redirect("/operator-desk/leads/%s" % lead_id)


def _has_desk_seat(member):
    """Does this person hold a seat on the Operator Desk itself?

    Owners are auto-enrolled by the Desk on first sight, so they always
    effectively do.
    """
    import desk_store
    email = (member or {}).get("email") or ""
    if _is_owner_email(email):
        return True
    u = desk_store.get_user_by_email(email)
    return bool(u and (u.get("status") or "active") == "active")


# --- mandates ---------------------------------------------------------------

@bp.route("/mandates", methods=["GET", "POST"])
@require("view")
def mandates(org, member):
    if request.method == "POST":
        if not sstore.can(member, "mandate_edit"):
            abort(403)
        criteria = {
            "genres": (request.form.get("genres") or "").strip()[:200],
            "max_listeners": (request.form.get("max_listeners") or "").strip()[:12],
            "min_momentum": (request.form.get("min_momentum") or "").strip()[:6],
            "min_gap": (request.form.get("min_gap") or "").strip()[:6],
            "territories": (request.form.get("territories") or "").strip()[:200],
            "notes": (request.form.get("notes") or "").strip()[:500],
        }
        sstore.create_mandate(org["id"], request.form.get("name") or "Mandate",
                              criteria, member["name"])
        return redirect(url_for("signal.mandates"))
    return render_template("signal/mandates.html", **_ctx(
        org, member, mandates=sstore.list_mandates(org["id"])))


@bp.route("/mandates/<mandate_id>/delete", methods=["POST"])
@require("mandate_edit")
def mandate_delete(org, member, mandate_id):
    sstore.delete_mandate(org["id"], mandate_id)
    return redirect(url_for("signal.mandates"))


@bp.route("/mandates/<mandate_id>")
@require("view")
def mandate_detail(org, member, mandate_id):
    m = sstore.get_mandate(org["id"], mandate_id)
    if m is None:
        abort(404)
    rows = _distribution_for(_rows_for(org))
    matched, missed = [], []
    for r in rows:
        ok, reasons, misses = _mandate_match(r, m)
        r = dict(r, match_reasons=reasons, match_misses=misses)
        (matched if ok else missed).append(r)
    matched.sort(key=lambda r: -r["deal"])
    missed.sort(key=lambda r: len(r["match_misses"]))
    return render_template("signal/mandate.html", **_ctx(
        org, member, mandate=m, matched=matched, missed=missed[:10]))


# --- alerts -----------------------------------------------------------------

@bp.route("/alerts", methods=["GET"])
@require("view")
def alerts(org, member):
    ingest.evaluate_alerts(org["id"])
    items = sstore.list_alerts(org["id"], limit=200)
    sstore.mark_alerts_read(org["id"])
    return render_template("signal/alerts.html", **_ctx(
        org, member, alerts=items, rules=sstore.list_alert_rules(org["id"]),
        triggers=sorted(sstore.ALERT_TRIGGERS.items())))


@bp.route("/alerts/rules", methods=["POST"])
@require("alert_edit")
def alert_rule_add(org, member):
    sstore.create_alert_rule(org["id"], request.form.get("name") or "Alert",
                             request.form.get("trigger_kind") or "",
                             request.form.get("threshold") or 0,
                             request.form.get("channel") or "in_app", member["name"])
    return redirect(url_for("signal.alerts"))


@bp.route("/alerts/rules/<rule_id>/delete", methods=["POST"])
@require("alert_edit")
def alert_rule_delete(org, member, rule_id):
    sstore.delete_alert_rule(org["id"], rule_id)
    return redirect(url_for("signal.alerts"))


# --- admin ------------------------------------------------------------------

@bp.route("/admin/data-sources")
@require("provider_admin")
def data_sources(org, member):
    reg = providers.registry()
    return render_template("signal/data_sources.html", **_ctx(
        org, member, health=reg.health(), usage=sstore.provider_usage(),
        freshness=sstore.data_freshness(), counts=sstore.counts(),
        capability_labels=providers.CAPABILITY_LABELS,
        preferred=[(cap, (reg.for_capability(cap).label if reg.for_capability(cap) else "none"))
                   for cap in providers.ALL_CAPABILITIES]))


@bp.route("/admin/refresh", methods=["POST"])
@require("provider_admin")
def admin_refresh(org, member):
    ingest.refresh_universe(force=True)
    return redirect(url_for("signal.data_sources"))


@bp.route("/team", methods=["GET", "POST"])
@require("view")
def team(org, member):
    if request.method == "POST":
        if not sstore.can(member, "manage_members"):
            abort(403)
        action = request.form.get("action")
        if action == "role":
            sstore.set_member_role(org["id"], request.form.get("member_id") or "",
                                   request.form.get("role") or "viewer")
        elif action == "remove":
            sstore.remove_member(org["id"], request.form.get("member_id") or "")
        elif action == "add":
            sstore.upsert_member(org["id"], request.form.get("email") or "",
                                 request.form.get("name") or "",
                                 request.form.get("role") or "viewer")
        return redirect(url_for("signal.team"))
    sstore.sync_desk_roster(org["id"])
    return render_template("signal/team.html", **_ctx(
        org, member, members=sstore.list_members(org["id"]),
        roles=sstore.ROLES, role_labels=sstore.ROLE_LABELS))


# --- ask signal (structured, honest about what it cannot do) ----------------

@bp.route("/ask")
@require("view")
def ask(org, member):
    """Natural-language search that shows its work.

    The query is parsed into visible structured filters. Anything the parser
    did not understand is listed as unsupported rather than quietly dropped -
    a filter that silently does nothing is worse than one that says it cannot.
    """
    q = (request.args.get("q") or "").strip()
    filters, unsupported = _parse_ask(q)
    rows = []
    if q:
        rows = _distribution_for(_rows_for(org))
        rows = [r for r in rows if _ask_match(r, filters)]
        rows.sort(key=lambda r: -r["momentum"])
    return render_template("signal/ask.html", **_ctx(
        org, member, q=q, filters=filters, unsupported=unsupported, rows=rows,
        examples=[
            "independent alternative artists growing more than 20% over 28 days",
            "artists under 250000 listeners with a high distribution gap",
            "rock artists with rights health below 60",
        ]))


_ASK_GENRES = ["alternative", "indie rock", "indie", "hip-hop", "hip hop", "r&b", "pop",
               "americana", "synthwave", "latin", "punk", "soul", "rock"]


def _parse_ask(q):
    """Deterministic parser. No model call, no invented fields - it only
    recognises filters Signal can actually apply."""
    import re
    text = (q or "").lower()
    filters, unsupported = {}, []
    if not text:
        return filters, unsupported

    m = re.search(r"(?:more than|over|above|>)\s*(\d+)\s*%", text)
    if m:
        filters["min_change_28d"] = float(m.group(1))
    m = re.search(r"under\s*([\d,]+)\s*(?:monthly\s*)?listeners", text)
    if m:
        filters["max_listeners"] = int(m.group(1).replace(",", ""))
    m = re.search(r"(?:momentum|sb momentum)\s*(?:above|over|>)\s*(\d+)", text)
    if m:
        filters["min_momentum"] = float(m.group(1))
    m = re.search(r"(?:distribution )?gap\s*(?:above|over|>)\s*(\d+)", text)
    if m:
        filters["min_gap"] = float(m.group(1))
    elif "distribution gap" in text or "undervalued" in text or "diy" in text:
        filters["min_gap"] = 60.0
    m = re.search(r"rights health (?:below|under|<)\s*(\d+)", text)
    if m:
        filters["max_rights"] = float(m.group(1))
    for g in _ASK_GENRES:
        if g in text:
            filters["genre"] = g
            break
    if "independent" in text or "unsigned" in text:
        filters["independent"] = True

    for phrase, why in (
        ("tiktok", "social platform metrics are not connected in this deployment"),
        ("shazam", "Shazam data is not connected in this deployment"),
        ("ticket", "ticketing demand is not connected in this deployment"),
        ("merch", "merch demand is not connected in this deployment"),
        ("playlist", "a playlist feed is not connected; playlist risk is inferred, not filterable"),
        ("manager", "filtering by management company needs the contact index, not yet built"),
        ("producer", "producer relationships are a phase-two engine"),
        ("songwriter", "songwriter relationships are a phase-two engine"),
    ):
        if phrase in text:
            unsupported.append(why)
    return filters, unsupported


def _ask_match(row, f):
    a = row["artist"]
    if f.get("max_listeners") and (a.get("monthly_listeners") or 0) > f["max_listeners"]:
        return False
    if f.get("min_change_28d") is not None and (row["change_28d"] or 0) < f["min_change_28d"]:
        return False
    if f.get("min_momentum") and row["momentum"] < f["min_momentum"]:
        return False
    if f.get("min_gap") and row["gap"] < f["min_gap"]:
        return False
    if f.get("max_rights") and row["rights"] and row["rights"] > f["max_rights"]:
        return False
    if f.get("genre") and f["genre"] not in (a.get("genre") or "").lower():
        return False
    if f.get("independent"):
        cls = (row.get("distribution") or {}).get("classification") or ""
        if cls in ("Major Label", "Major-Affiliated Distribution", "Enterprise Distribution"):
            return False
    return True


# --- export -----------------------------------------------------------------

@bp.route("/export/board.csv")
@require("view")
def export_board(org, member):
    rows = _distribution_for(_rows_for(org))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Artist", "Genre", "City", "Monthly listeners", "SB Momentum",
                "Momentum quality", "Distribution gap", "Rights health", "Deal readiness",
                "7d %", "28d %", "Distributor", "Classification", "Score version"])
    for r in rows:
        a = r["artist"]
        w.writerow([a["canonical_name"], a.get("genre") or "", a.get("city") or "",
                    a.get("monthly_listeners") or 0, r["momentum"], r["quality"], r["gap"],
                    r["rights"], r["deal"], r["change_7d"] or "", r["change_28d"] or "",
                    (r["distribution"] or {}).get("name") or "",
                    (r["distribution"] or {}).get("classification") or "",
                    scoring.SCORE_VERSION])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=signal-board.csv"})


# --- registration -----------------------------------------------------------

def init(app, base_url, is_owner_email):
    global _base_url, _is_owner_email
    _base_url = base_url
    _is_owner_email = is_owner_email
    sstore.init_signal()

    # Audio Briefs live in their own module but on THIS blueprint, so they
    # inherit the org guard and the roster check rather than growing a second
    # access system beside them. Routes must exist before registration.
    import audio_briefs
    import audio_signal
    audio_briefs.init_briefs()
    audio_signal.register(bp, require, _ctx, sstore)

    app.register_blueprint(bp)
