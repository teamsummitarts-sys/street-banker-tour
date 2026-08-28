"""Street Banker Command Center + global Actions.

The operating-system spine: unified scores computed live from the real
modules (Links, Rollout Engine, Fan CRM, Catalog, EPK), derived health
alerts that always point at a destination, a persistent action/task
system, and the registry of every OS module with an honest Live/Preview
status. Scores are derived fresh on every load rather than snapshotted —
no stale numbers, no fake data.
"""

import uuid
from datetime import date, datetime, timezone

from db import get_db, _now
import links_engine
import links_store as mls
import rollout_store as ros

# --- Actions -------------------------------------------------------------------

ACTION_CATEGORIES = ["release", "metadata", "smart_link", "rollout", "fan_growth",
                     "royalty_recovery", "sync", "rights", "report", "general"]
ACTION_PRIORITIES = ["high", "medium", "low"]
ACTION_STATUSES = ["new", "in_progress", "complete", "dismissed"]


def create_action(user_id, title, category="general", priority="medium",
                  description="", entity_type="", entity_id="", due_date=""):
    aid = uuid.uuid4().hex
    now = _now()
    with get_db() as db:
        db.execute(
            "INSERT INTO street_actions (id, user_id, title, category, priority,"
            " description, entity_type, entity_id, due_date, status, created, updated)"
            " VALUES (?,?,?,?,?,?,?,?,?,'new',?,?)",
            (aid, user_id, title[:200],
             category if category in ACTION_CATEGORIES else "general",
             priority if priority in ACTION_PRIORITIES else "medium",
             description[:600], entity_type[:40], entity_id[:64],
             due_date[:10], now, now))
    return aid


def set_action_status(action_id, user_id, status):
    if status not in ACTION_STATUSES:
        return False
    with get_db() as db:
        cur = db.execute(
            "UPDATE street_actions SET status = ?, updated = ?,"
            " completed_at = CASE WHEN ? = 'complete' THEN ? ELSE completed_at END"
            " WHERE id = ? AND user_id = ?",
            (status, _now(), status, _now(), action_id, user_id))
    return cur.rowcount > 0


def list_actions(user_id, status=None):
    q = "SELECT * FROM street_actions WHERE user_id = ?"
    args = [user_id]
    if status:
        q += " AND status = ?"
        args.append(status)
    q += (" ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,"
          " created DESC")
    with get_db() as db:
        rows = db.execute(q, args).fetchall()
    return [dict(r) for r in rows]


def open_actions(user_id, limit=5):
    return [a for a in list_actions(user_id)
            if a["status"] in ("new", "in_progress")][:limit]


# --- Module registry: honest Live / Preview states ------------------------------

# (route, name, blurb, status, disclaimer_or_None)
_NOT_LEGAL = "Workflow support only — not legal advice. Have an attorney review agreements."
_NOT_FINANCIAL = "Estimates only — not financial advice."

MODULES = [
    ("/links", "Smart Links 2.0", "Campaigns, pre-saves, fan capture, variants, QR, attribution.", "live", None),
    ("/rollout-studio", "Rollout Engine", "Generated social rollouts with per-post tracked links.", "live", None),
    ("/links/fans", "Fan CRM", "Owned fan data with consent logs and intent scoring.", "live", None),
    ("/epk", "Press Office / EPK", "Editable press kit with public share link and media assets.", "live", None),
    ("/releases/autopilot", "Release Autopilot", "One release in, the full operating plan out.", "live", None),
    ("/releases/clean-release", "Clean Release Checklist", "Rights-, metadata-, and promo-readiness before you ship.", "live", None),
    ("/royalty-recovery/cases", "Royalty Recovery Cases", "Turn recovery insights into tracked cases with evidence and deadlines.", "live", None),
    ("/royalty-recovery/mlc", "MLC / Unmatched Recovery", "Find and claim unmatched mechanical royalties with claim packets.", "preview", None),
    ("/sync/clearance-packs", "Sync Clearance Packs", "One-click supervisor-safe pitch packages with clearance status.", "live", None),
    ("/sync/deal-simulator", "Sync Deal Simulator", "Evaluate sync terms, flag buyouts, draft counteroffers.", "live", _NOT_LEGAL),
    ("/deal-room", "Deal Room", "Splits, producer and feature agreements, document vault, deal board.", "live", _NOT_LEGAL),
    ("/revenue-os", "Revenue OS", "Real income from statements against tracked spend.", "live", _NOT_FINANCIAL),
    ("/capital-score", "Capital Readiness Score", "Funding readiness built from catalog health and income consistency.", "live", _NOT_FINANCIAL),
    ("/fraud-sentinel", "Fraud Sentinel", "Artificial streaming and shady playlist risk monitoring.", "preview", None),
    ("/metadata-passport", "Metadata Passport", "Identifier and credit completeness per track, with a clean export.", "live", None),
    ("/ai-rights", "AI Rights & Likeness", "Voice/likeness policies, do-not-train notices, takedown tracking.", "preview", _NOT_LEGAL),
    ("/pulse", "Artist Pulse", "Live Spotify followers, popularity, top tracks, and Deezer fans.", "live", None),
    ("/trust-score", "Trust Score", "One verifiable readiness score for partners, labels, and supervisors.", "live", None),
    ("/artist-twin", "Artist Twin", "A private writing agent using only data you approve.", "live", None),
    ("/opportunities", "Opportunity Feed", "Matched sync briefs, playlists, grants, and collaborations.", "preview", None),
    ("/voice-of-fan", "Voice of Fan", "Fan comments and behavior turned into campaign intelligence.", "preview", None),
    ("/spend-optimizer", "Spend Optimizer", "Where to put a limited release budget — and what to avoid.", "live", _NOT_FINANCIAL),
    ("/fan-club", "Fan Club", "Paid monthly memberships through Stripe with a members-only drops area, wired into the Fan CRM.", "live", None),
    ("/portal", "Partner Portal", "Team members see role-scoped, read-only views of your business.", "live", None),
    ("/tour", "Tour Hub", "Your show pipeline: holds through settled, all in one table.", "live", None),
    ("/stage-plot", "Stage Plot", "Design your stage plot and auto-build the input list venues ask for.", "live", None),
    ("/tour-board", "Team-Up Board", "Artists seeking tour partners and venues seeking acts \u2014 real listings only.", "live", None),
    ("/rack", "The Rack", "Real browser DSP: 12-band EQ, tube stage, cab & mic sim, compressor, WAV export \u2014 nothing is uploaded.", "live", None),
    ("/roster", "Label Mode", "Roster seats for the Label tier: invite artists, see the whole roster's real numbers.", "live", None),
    ("/referrals", "Referrals", "Give a month, get $9: your link, your signups, credits on your Stripe balance.", "live", None),
    ("/lights", "Light Studio", "Cue your light show to the song — stage preview plus real DMX out to an ENTTEC interface.", "live", None),
    ("/tracks", "Track Passports", "Per-track rights and metadata spine: passport, clean-release score, royalty lanes, lockbox.", "live", None),
    ("/royalty-lanes", "Royalty Lanes", "Nine lanes per song: claimed, connected, missing, or needs action — from your real statements.", "live", None),
    ("/money-queue", "Money Queue", "What is costing you money, criticals first — every action names its fix and its basis.", "live", None),
    ("/certified", "Street Banker Certified", "Six rungs from Verified to Upstream Ready, every one computed from your real record.", "live", None),
]

MODULE_BY_ROUTE = {route: (route, name, blurb, status, disc)
                   for route, name, blurb, status, disc in MODULES}

# Planned-feature bullets shown on preview pages, keyed by route.
PREVIEW_FEATURES = {
    "/royalty-recovery/cases": ["Case board with status, evidence, and deadlines", "Estimated amounts and confidence scores", "Recovery packet generator", "Results and payout tracking"],
    "/royalty-recovery/mlc": ["Unmatched recording search", "Claim checklist and packet generator", "Registration correction queue", "Deadline and status tracking"],
    "/sync/clearance-packs": ["Instrumental, clean, and stem uploads", "Master + publishing clearance status", "Private supervisor listening links", "Exportable PDF one-sheet"],
    "/sync/deal-simulator": ["Fee, term, territory, and exclusivity inputs", "Buyout and MFN risk flags", "Quote recommendations", "Counteroffer drafts"],
    "/deal-room": ["Split, producer, and feature agreement generators", "Document vault with revision history", "Advance offer comparison", "Recoupment simulator"],
    "/revenue-os": ["Income by source: streaming, publishing, sync, merch, tickets", "Expense and recoupment tracking", "Per-release break-even", "Campaign ROI tied to Links and Rollout spend"],
    "/capital-score": ["Score from royalty history and catalog health", "Funding strengths and risks", "Advance scenario modeling", "Cleanup actions that raise the score"],
    "/fraud-sentinel": ["Stream spike and geo anomaly warnings", "Playlist legitimacy scores", "Do-not-pitch flags", "Exportable evidence reports"],
    "/metadata-passport": ["ISRC / UPC / ISWC validation", "Credits and split completeness", "DDEX-ready export bundle", "Missing-data collaborator requests"],
    "/ai-rights": ["Voice and likeness policy registry", "Do-not-train notice generator", "AI-use disclosure labels", "Takedown case tracking"],
    "/trust-score": ["Metadata, splits, rights, and fraud inputs", "Partner-facing badge", "Blocking-factor breakdown", "Actions that raise the score"],
    "/artist-twin": ["Approved-sources list you control", "Captions, pitches, and reports in your voice", "Do-not-say list", "Outputs saved into Rollout and EPK"],
    "/opportunities": ["Sync briefs and playlist matches", "Grants and funding windows", "Fit scores and deadlines", "One-click submission workflows"],
    "/voice-of-fan": ["Fan comment and survey ingestion", "Which lyrics, cities, and CTAs resonate", "Buyer and live-show prospect signals", "Feeds Rollout recommendations"],
    "/spend-optimizer": ["Budget allocation across content, ads, street team", "Avoid-this-spend warnings", "ROI assumptions", "Release-day reserve planning"],
    "/fan-club": ["Free and paid membership tiers", "Early-access drops", "VIP segments from Fan CRM", "Member-only links and QR codes"],
    "/partner-portal": ["Scoped label and manager access", "Shared reports and dashboards", "API keys and access logs", "Revocable grants"],
}


# --- Derived health alerts --------------------------------------------------------

def _today():
    return date.today()


def build_alerts(user_id):
    """Live-derived alerts from real module state. Every alert carries a
    destination link and enough context to become an action."""
    alerts = []
    campaigns = mls.list_campaigns(user_id)
    rollouts = ros.list_campaigns(user_id)
    rollout_ml_ids = {r.get("ml_campaign_id") for r in rollouts}
    for c in campaigns:
        if c.get("archived_at"):
            continue
        dests = mls.get_destinations(c["id"])
        settings = c.get("settings") or {}
        if c["status"] == "live" and not dests:
            alerts.append(("high", "“%s” is live with no destinations" % c["title"],
                           "Fans hit a dead page. Add streaming links now.",
                           "/links/%s/edit" % c["id"], "smart_link"))
        if c["status"] == "live" and not settings.get("email_capture"):
            alerts.append(("medium", "“%s” isn't capturing fans" % c["title"],
                           "Traffic without capture is rented attention. Enable email capture.",
                           "/links/%s/edit" % c["id"], "fan_growth"))
        if c.get("release_date"):
            try:
                days = (datetime.strptime(c["release_date"], "%Y-%m-%d").date() - _today()).days
            except ValueError:
                days = None
            if days is not None and 0 <= days <= 7 and c["id"] not in rollout_ml_ids:
                alerts.append(("high", "“%s” drops in %d day%s with no rollout" % (
                                   c["title"], days, "s" if days != 1 else ""),
                               "Generate a rollout so release week isn't silent.",
                               "/rollout-studio/new", "rollout"))
        if settings.get("email_capture") and not settings.get("consent_text"):
            alerts.append(("medium", "“%s” captures emails without consent copy" % c["title"],
                           "Add consent text — it's logged with every signup.",
                           "/links/%s/edit" % c["id"], "rights"))
    # Real statement findings: money on the table beats everything else.
    import db as store
    from statements_engine import build_royalty_summary
    rows = store.get_statement_rows(user_id)
    summary = build_royalty_summary(rows) if rows else None
    # The catalog valuation is computed here every time the Command
    # Center loads and was stored nowhere, so the one number an artist
    # most wants a trend on had no history at all. Guarded - a history
    # write must never break the page it was computed for.
    if summary and (summary.get("valuation") or {}).get("mid"):
        try:
            store.record_score(user_id, "valuation",
                               summary["valuation"]["mid"],
                               {"low": summary["valuation"]["low"],
                                "high": summary["valuation"]["high"],
                                "annualized": summary.get("annualized")})
        except Exception:
            pass
    if summary and summary["unmatched_revenue"]:
        alerts.insert(0, ("high", "$%.2f unmatched revenue in your statements" % summary["unmatched_revenue"],
                          "Rows with no track title — money paid but not attributed. Review and claim it.",
                          "/recovery", "royalty_recovery"))
    if summary and summary["coverage_gaps"]:
        alerts.append(("medium", "%d coverage gap%s across your royalty sources" % (
                           len(summary["coverage_gaps"]),
                           "s" if len(summary["coverage_gaps"]) != 1 else ""),
                       "Tracks earning on some sources but missing from others — est. $%.2f." % summary["gap_estimate_total"],
                       "/recovery", "royalty_recovery"))
    # Catalog metadata gaps
    tracks = mls_catalog_tracks(user_id)
    missing_isrc = [t for t in tracks if not (t.get("meta") or {}).get("isrc")]
    if missing_isrc:
        alerts.append(("medium", "%d catalog track%s missing an ISRC" % (
                           len(missing_isrc), "s" if len(missing_isrc) != 1 else ""),
                       "Missing identifiers leak royalties. Re-check metadata.",
                       "/catalog", "metadata"))
    return alerts


def mls_catalog_tracks(user_id):
    import db as store
    return store.get_catalog_tracks(user_id)


# --- Unified summary ---------------------------------------------------------------

def get_summary(user_id):
    campaigns = [c for c in mls.list_campaigns(user_id) if not c.get("archived_at")]
    scores = []
    upcoming = []
    for c in campaigns:
        dests = mls.get_destinations(c["id"])
        s = links_engine.calculate_street_banker_score(c, dests)
        scores.append(s["total"])
        if c.get("release_date"):
            try:
                days = (datetime.strptime(c["release_date"], "%Y-%m-%d").date() - _today()).days
            except ValueError:
                continue
            if days >= 0:
                upcoming.append({"title": c["title"], "days": days, "id": c["id"],
                                 "score": s["total"], "warnings": s["warnings"]})
    upcoming.sort(key=lambda u: u["days"])
    events = mls.account_event_counts(user_id)
    fans = mls.list_fans(user_id)
    rollouts = ros.list_campaigns(user_id)
    tracks = mls_catalog_tracks(user_id)
    with_isrc = sum(1 for t in tracks if (t.get("meta") or {}).get("isrc"))
    import qualification
    return {
        "qualification": qualification.calculate(user_id)["total"],
        "links_score": round(sum(scores) / len(scores)) if scores else 0,
        "campaign_count": len(campaigns),
        "visits": events.get("page_view", 0),
        "clicks": events.get("service_click", 0),
        "fan_count": len(fans),
        "hot_fans": sum(1 for f in fans if f["intent_level"] in ("Hot", "Superfan")),
        "rollout_count": len(rollouts),
        "catalog_count": len(tracks),
        "catalog_health": round(100 * with_isrc / len(tracks)) if tracks else 0,
        "upcoming": upcoming[:3],
        "next_release": upcoming[0] if upcoming else None,
    }
