"""Campaign Debrief — measured learning from a REACH campaign.

This is a read model over persisted campaign, outreach, response, placement and
relationship records. It reports observed patterns and explicitly avoids causal
claims: a channel with a higher response rate is an observed result, not proof
that the channel caused the outcome.
"""

from . import analytics, campaigns, catalog, db, rbac
from .errors import ValidationError


def _campaign(campaign_id):
    campaign = campaigns.get(campaign_id)
    principal = rbac.current_principal()
    if campaign is None or campaign["tenant_id"] != principal.tenant_id:
        raise ValidationError("Unknown campaign")
    return campaign


def _scalar(sql, params=()):
    row = db.query_one(sql, params)
    return row["n"] if row else 0


def _rate(numerator, denominator):
    return round(numerator / denominator * 100) if denominator else None


def _channel_rows(campaign_id):
    rows = db.query(
        "SELECT COALESCE(o.kind,'UNKNOWN') AS label, "
        "COUNT(DISTINCT t.id) AS targeted, "
        "COUNT(DISTINCT CASE WHEN s.sent_at IS NOT NULL THEN t.id END) AS sent, "
        "COUNT(DISTINCT r.id) AS responses, "
        "COUNT(DISTINCT CASE WHEN r.kind = 'ACCEPT' THEN r.id END) AS accepted, "
        "COUNT(DISTINCT p.id) AS placements, "
        "COUNT(DISTINCT CASE WHEN r.kind = 'DECLINE' THEN r.id END) AS declined "
        "FROM campaign_target t JOIN outlet o ON o.id = t.outlet_id "
        "LEFT JOIN submission s ON s.target_id = t.id "
        "LEFT JOIN response r ON r.target_id = t.id "
        "LEFT JOIN placement p ON p.target_id = t.id "
        "WHERE t.campaign_id = ? GROUP BY COALESCE(o.kind,'UNKNOWN') "
        "ORDER BY placements DESC, responses DESC, sent DESC, targeted DESC",
        (campaign_id,),
    )
    result = []
    for row in rows:
        item = dict(row)
        item["response_rate"] = _rate(item["responses"], item["sent"])
        item["placement_rate"] = _rate(item["placements"], item["sent"])
        result.append(item)
    return result


def _territory_rows(campaign_id):
    rows = db.query(
        "SELECT COALESCE(NULLIF(o.territory,''),'UNKNOWN') AS label, "
        "COUNT(DISTINCT t.id) AS targeted, "
        "COUNT(DISTINCT CASE WHEN s.sent_at IS NOT NULL THEN t.id END) AS sent, "
        "COUNT(DISTINCT r.id) AS responses, "
        "COUNT(DISTINCT p.id) AS placements "
        "FROM campaign_target t JOIN outlet o ON o.id = t.outlet_id "
        "LEFT JOIN submission s ON s.target_id = t.id "
        "LEFT JOIN response r ON r.target_id = t.id "
        "LEFT JOIN placement p ON p.target_id = t.id "
        "WHERE t.campaign_id = ? GROUP BY COALESCE(NULLIF(o.territory,''),'UNKNOWN') "
        "ORDER BY placements DESC, responses DESC, sent DESC, targeted DESC LIMIT 12",
        (campaign_id,),
    )
    result = []
    for row in rows:
        item = dict(row)
        item["response_rate"] = _rate(item["responses"], item["sent"])
        item["placement_rate"] = _rate(item["placements"], item["sent"])
        result.append(item)
    return result


def _rejection_rows(campaign_id):
    return [dict(row) for row in db.query(
        "SELECT COALESCE(NULLIF(rejection_reason,''),'Unspecified') AS reason, COUNT(*) AS n "
        "FROM campaign_target WHERE campaign_id = ? AND rejection_reason IS NOT NULL "
        "GROUP BY COALESCE(NULLIF(rejection_reason,''),'Unspecified') ORDER BY n DESC, reason",
        (campaign_id,),
    )]


def _relationship_wins(campaign_id):
    return [dict(row) for row in db.query(
        "SELECT o.id AS outlet_id, o.name AS outlet_name, o.kind AS outlet_kind, "
        "o.territory, t.id AS target_id, "
        "COUNT(DISTINCT CASE WHEN r.kind = 'ACCEPT' THEN r.id END) AS accepts, "
        "COUNT(DISTINCT p.id) AS placements, "
        "MAX(r.received_at) AS last_response_at "
        "FROM campaign_target t JOIN outlet o ON o.id = t.outlet_id "
        "LEFT JOIN response r ON r.target_id = t.id "
        "LEFT JOIN placement p ON p.target_id = t.id "
        "WHERE t.campaign_id = ? GROUP BY o.id, o.name, o.kind, o.territory, t.id "
        "HAVING accepts > 0 OR placements > 0 "
        "ORDER BY placements DESC, accepts DESC, last_response_at DESC LIMIT 12",
        (campaign_id,),
    )]


def _pitch_outcomes(campaign_id):
    """Sent pitch subjects with observed outcomes; no claim that wording caused them."""
    return [dict(row) for row in db.query(
        "SELECT d.subject, d.language, rec.title AS recording_title, o.name AS outlet_name, "
        "MAX(s.sent_at) AS sent_at, "
        "MAX(CASE WHEN r.kind = 'ACCEPT' THEN 1 ELSE 0 END) AS accepted, "
        "MAX(CASE WHEN r.kind = 'DECLINE' THEN 1 ELSE 0 END) AS declined, "
        "COUNT(DISTINCT p.id) AS placements "
        "FROM outreach_draft d "
        "JOIN campaign_target t ON t.id = d.target_id "
        "JOIN campaign c ON c.id = t.campaign_id "
        "JOIN recording rec ON rec.id = c.recording_id "
        "JOIN outlet o ON o.id = t.outlet_id "
        "JOIN approval a ON a.draft_id = d.id "
        "JOIN submission s ON s.approval_id = a.id AND s.target_id = t.id "
        "LEFT JOIN response r ON r.target_id = t.id "
        "LEFT JOIN placement p ON p.target_id = t.id "
        "WHERE t.campaign_id = ? AND s.sent_at IS NOT NULL "
        "GROUP BY d.id, d.subject, d.language, rec.title, o.name "
        "ORDER BY sent_at DESC LIMIT 20",
        (campaign_id,),
    )]


def _carry_forward(channels, relationship_wins, rejections, metrics):
    items = []

    eligible = [row for row in channels if row["sent"] >= 3 and row["response_rate"] is not None]
    if eligible:
        best = max(eligible, key=lambda row: (row["response_rate"], row["responses"]))
        items.append({
            "kind": "observed_channel",
            "title": f"{best['label'].replace('_',' ').title()} produced the strongest observed response rate",
            "detail": f"{best['responses']} responses from {best['sent']} sends ({best['response_rate']}%). Keep testing it; this is observed performance, not proof of causation.",
        })

    if relationship_wins:
        placements = sum(1 for row in relationship_wins if row["placements"])
        items.append({
            "kind": "relationships",
            "title": f"Carry forward {len(relationship_wins)} positive outlet relationship{'s' if len(relationship_wins) != 1 else ''}",
            "detail": f"These outlets accepted or placed the release. {placements} produced a verified placement." if placements else "These outlets recorded an acceptance and should retain their history for the next release.",
        })

    if rejections:
        top = rejections[0]
        if top["n"] >= 2:
            items.append({
                "kind": "rejection_pattern",
                "title": f"Review the recurring rejection pattern: {top['reason']}",
                "detail": f"This reason was recorded {top['n']} times. Treat it as a review signal, not an automated conclusion about the music.",
            })

    if metrics["submitted"] and not metrics["responses"]:
        items.append({
            "kind": "no_response",
            "title": "No responses are recorded yet",
            "detail": "Do not infer that the campaign failed. The current record only establishes that sends occurred and no response has been recorded.",
        })

    return items[:4]


def build(campaign_id):
    campaign = _campaign(campaign_id)
    recording = catalog.get_recording(campaign["recording_id"])
    metrics = analytics.campaign_metrics(campaign_id)
    channels = _channel_rows(campaign_id)
    territories = _territory_rows(campaign_id)
    rejections = _rejection_rows(campaign_id)
    wins = _relationship_wins(campaign_id)
    pitches = _pitch_outcomes(campaign_id)

    response_kinds = {
        row["kind"]: row["n"]
        for row in db.query(
            "SELECT r.kind, COUNT(*) AS n FROM response r "
            "JOIN campaign_target t ON t.id = r.target_id WHERE t.campaign_id = ? GROUP BY r.kind",
            (campaign_id,),
        )
    }
    delivered = _scalar(
        "SELECT COUNT(*) AS n FROM submission s JOIN campaign_target t ON t.id = s.target_id "
        "WHERE t.campaign_id = ? AND s.sent_at IS NOT NULL",
        (campaign_id,),
    )

    return {
        "campaign": campaign,
        "recording": recording,
        "metrics": metrics,
        "delivered": delivered,
        "response_kinds": response_kinds,
        "channels": channels,
        "territories": territories,
        "rejections": rejections,
        "relationship_wins": wins,
        "pitch_outcomes": pitches,
        "carry_forward": _carry_forward(channels, wins, rejections, metrics),
        "attribution": analytics.attribution_report(campaign_id),
        "has_activity": bool(metrics["discovered"] or delivered or metrics["responses"] or metrics["placed"]),
        "disclaimer": "Observed campaign results. Reach does not claim a channel, pitch or placement caused downstream performance without direct attribution evidence.",
    }
