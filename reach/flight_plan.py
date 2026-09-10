"""Campaign Flight Plan — a derived, evidence-first forward plan for REACH.

The flight plan does not invent campaign dates or percentages. It turns existing
campaign state, release timing, intake-monitor events, approval work, follow-ups
and readiness records into a concise answer to four questions:

* What should I do now?
* What is coming in the next seven days?
* What timing does REACH actually know?
* What is blocking progress?

No state is mutated here. This module is a read model only.
"""

import json
from datetime import date

from . import (campaigns, catalog, clock, db, humanactions, intake_monitor,
               outcomes, profile, rbac, sender)


STAGES = ["Discover", "Review", "Outreach", "Results"]


def _date_value(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _days_until(raw):
    value = _date_value(raw)
    return (value - clock.now().date()).days if value else None


def _campaign_events(campaign_id, limit=50):
    """Open intake-monitor events for one campaign, most urgent first."""
    intake_monitor._ensure_schema()
    principal = rbac.current_principal()
    return db.query(
        "SELECT e.*, o.name AS outlet_name, o.domain AS outlet_domain "
        "FROM intake_monitor_event e "
        "JOIN outlet o ON o.id = e.outlet_id "
        "WHERE e.tenant_id = ? AND e.campaign_id = ? AND e.acknowledged_at IS NULL "
        "ORDER BY CASE e.severity WHEN 'URGENT' THEN 0 WHEN 'IMPORTANT' THEN 1 ELSE 2 END, "
        "e.created_at DESC LIMIT ?",
        (principal.tenant_id, campaign_id, limit),
    )


def _deadline_from_event(event):
    if event["kind"] not in (intake_monitor.DEADLINE_FOUND, intake_monitor.DEADLINE_CHANGED):
        return None
    try:
        after = json.loads(event["after_json"] or "{}")
    except (TypeError, ValueError):
        return None
    return after.get("deadline")


def _status_counts(campaign_id):
    return campaigns.status_counts(campaign_id)


def _stage(counts):
    """Four-lane public stage derived only from current target occupancy."""
    if sum(counts.get(s, 0) for s in (
        campaigns.RESPONDED, campaigns.FOLLOW_UP_DUE, campaigns.ACCEPTED,
        campaigns.PLACED, campaigns.DECLINED,
    )):
        return "Results"
    if sum(counts.get(s, 0) for s in (
        campaigns.SENT, campaigns.SUBMITTED, campaigns.DELIVERED,
        campaigns.APPROVED, campaigns.QUEUED,
    )):
        return "Outreach"
    if sum(counts.get(s, 0) for s in (
        campaigns.QUALIFIED, campaigns.READY, campaigns.DRAFTED,
        campaigns.NEEDS_APPROVAL,
    )):
        return "Review"
    return "Discover"


def _action(kind, title, detail, priority=50, target_id=None, count=None):
    return {
        "kind": kind,
        "title": title,
        "detail": detail,
        "priority": priority,
        "target_id": target_id,
        "count": count,
    }


def _next_actions(campaign, counts, events, tasks, follow_ups):
    actions = []

    urgent_events = [row for row in events if row["severity"] == intake_monitor.URGENT]
    if urgent_events:
        event = urgent_events[0]
        actions.append(_action(
            "intake_event",
            event["summary"],
            "A monitored submission source changed and needs review.",
            priority=100,
            target_id=event["target_id"],
            count=len(urgent_events),
        ))

    drafted = counts.get(campaigns.DRAFTED, 0) + counts.get(campaigns.NEEDS_APPROVAL, 0)
    if drafted:
        actions.append(_action(
            "review",
            f"Approve {drafted} prepared message{'s' if drafted != 1 else ''}",
            "Prepared outreach is waiting for human review.",
            priority=90,
            count=drafted,
        ))

    if tasks:
        actions.append(_action(
            "needs_you",
            f"Complete {len(tasks)} manual action{'s' if len(tasks) != 1 else ''}",
            "Forms, logins or other steps Reach will not automate are waiting.",
            priority=85,
            count=len(tasks),
        ))

    if follow_ups:
        actions.append(_action(
            "responses",
            f"Follow up with {len(follow_ups)} outlet{'s' if len(follow_ups) != 1 else ''}",
            "These contacts have reached their follow-up window.",
            priority=80,
            count=len(follow_ups),
        ))

    qualified = counts.get(campaigns.QUALIFIED, 0)
    if qualified:
        actions.append(_action(
            "opportunities",
            f"Review {qualified} qualified opportunit{'ies' if qualified != 1 else 'y'}",
            "Decide what deserves a pitch before generating more outreach.",
            priority=70,
            count=qualified,
        ))

    ready = counts.get(campaigns.READY, 0)
    if ready:
        actions.append(_action(
            "review",
            f"Prepare outreach for {ready} ready opportunit{'ies' if ready != 1 else 'y'}",
            "Verified opportunities are ready for the review/outreach lane.",
            priority=65,
            count=ready,
        ))

    target_total = sum(counts.values())
    if target_total == 0:
        actions.append(_action(
            "discover",
            "Run discovery",
            "Reach has no campaign targets yet.",
            priority=60,
        ))
    elif _stage(counts) == "Discover":
        actions.append(_action(
            "discover",
            "Continue discovery",
            "The campaign is still building and verifying its opportunity set.",
            priority=55,
        ))

    if not actions:
        actions.append(_action(
            "overview",
            "Review campaign results",
            "No immediate intervention is required; review current movement and outcomes.",
            priority=20,
        ))

    return sorted(actions, key=lambda item: -item["priority"])[:3]


def _upcoming(campaign, recording, events):
    items = []
    today = clock.now().date()

    def add(kind, raw_date, title, detail=None, target_id=None, severity="INFO"):
        value = _date_value(raw_date)
        if not value:
            return
        days = (value - today).days
        if 0 <= days <= 7:
            items.append({
                "kind": kind,
                "date": value.isoformat(),
                "days": days,
                "title": title,
                "detail": detail,
                "target_id": target_id,
                "severity": severity,
            })

    add("release", recording["release_date"], "Release date", recording["title"])
    add("campaign_end", campaign["end_date"], "Campaign end date", campaign["name"])
    add("campaign_start", campaign["start_date"], "Campaign start date", campaign["name"])

    seen_deadlines = set()
    for event in events:
        deadline = _deadline_from_event(event)
        if not deadline:
            continue
        key = (event["target_id"], deadline)
        if key in seen_deadlines:
            continue
        seen_deadlines.add(key)
        add(
            "deadline",
            deadline,
            f"Submission deadline — {event['outlet_name'] or event['outlet_domain']}",
            event["summary"],
            target_id=event["target_id"],
            severity=event["severity"],
        )

    return sorted(items, key=lambda item: (item["date"], 0 if item["severity"] == "URGENT" else 1))


def _timing(campaign, recording):
    result = []
    for kind, label, value in (
        ("release", "Release", recording["release_date"]),
        ("campaign_start", "Campaign starts", campaign["start_date"]),
        ("campaign_end", "Campaign ends", campaign["end_date"]),
    ):
        days = _days_until(value)
        if value:
            if days is None:
                detail = "Date on file"
            elif days > 0:
                detail = f"{days} day{'s' if days != 1 else ''} away"
            elif days == 0:
                detail = "Today"
            else:
                detail = f"{abs(days)} day{'s' if abs(days) != 1 else ''} ago"
            result.append({"kind": kind, "label": label, "date": str(value)[:10], "detail": detail})
    return result


def _blockers(campaign, recording, profile_state, events, tasks, sender_state, counts):
    blockers = []
    if not catalog.active_attestation(recording["id"]):
        blockers.append({"kind": "rights", "severity": "BLOCK", "text": "Rights attestation is not active."})
    if not profile_state["ready"]:
        blockers.append({
            "kind": "profile",
            "severity": "BLOCK",
            "text": "Track profile is missing required fields: " + ", ".join(profile_state["missing_required"]),
        })
    if campaign["status"] == campaigns.PAUSED:
        blockers.append({"kind": "paused", "severity": "BLOCK", "text": "Campaign is paused."})

    closed = [row for row in events if row["kind"] == intake_monitor.WINDOW_CLOSED]
    if closed:
        blockers.append({
            "kind": "intake",
            "severity": "WARNING",
            "text": f"{len(closed)} monitored submission window{'s are' if len(closed) != 1 else ' is'} currently flagged closed.",
        })
    if tasks:
        blockers.append({
            "kind": "human",
            "severity": "ACTION",
            "text": f"{len(tasks)} manual action{'s' if len(tasks) != 1 else ''} require human completion.",
        })

    outreach_waiting = sum(counts.get(s, 0) for s in (
        campaigns.READY, campaigns.DRAFTED, campaigns.NEEDS_APPROVAL,
        campaigns.APPROVED, campaigns.QUEUED,
    ))
    if outreach_waiting and not sender_state["ready"]:
        blockers.append({
            "kind": "sender",
            "severity": "WARNING",
            "text": "Outreach is waiting, but sender setup is not ready.",
        })
    return blockers


def build(campaign_id):
    """Build the current flight plan for one owned campaign."""
    principal = rbac.current_principal()
    campaign = campaigns.get(campaign_id)
    if campaign is None or campaign["tenant_id"] != principal.tenant_id:
        return None
    recording = catalog.get_recording(campaign["recording_id"])
    profile_id = profile.get_or_create(recording["id"])
    profile_state = profile.completeness(profile_id)
    counts = _status_counts(campaign_id)
    events = _campaign_events(campaign_id)
    tasks = humanactions.queue(campaign_id)
    follow_ups = [row for row in outcomes.follow_ups_due() if row["campaign_id"] == campaign_id]
    sender_state = sender.health_summary()

    stage = _stage(counts)
    stage_index = STAGES.index(stage)
    return {
        "campaign_id": campaign_id,
        "stage": stage,
        "stage_index": stage_index,
        "stages": STAGES,
        "now": _next_actions(campaign, counts, events, tasks, follow_ups),
        "upcoming": _upcoming(campaign, recording, events),
        "timing": _timing(campaign, recording),
        "blockers": _blockers(campaign, recording, profile_state, events, tasks, sender_state, counts),
        "counts": counts,
        "release_date_known": bool(recording["release_date"]),
        "release_days": _days_until(recording["release_date"]),
        "open_intake_events": len(events),
        "open_tasks": len(tasks),
        "follow_ups_due": len(follow_ups),
    }
