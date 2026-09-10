"""Deadline + Intake Monitor for REACH.

Re-checks the official/public source pages already attached to campaign targets
and records only submission-relevant changes: open/closed state, explicit
deadlines, route/login/captcha changes, and cost/requirements changes.

The monitor is intentionally conservative. A page change never automatically
qualifies an outlet, sends outreach, or rewrites a target status. It produces an
evidence-backed event for the artist to act on.
"""

import hashlib
import json
import re
from datetime import date, datetime
from urllib.parse import urlsplit

from . import (audit, campaigns, clock, db, entities, evidence, extractor,
               fetcher, netguard, rbac, sanitizer)
from .errors import FetchBlocked, ValidationError

_schema_ready_path = None

WINDOW_OPENED = "WINDOW_OPENED"
WINDOW_CLOSED = "WINDOW_CLOSED"
DEADLINE_FOUND = "DEADLINE_FOUND"
DEADLINE_CHANGED = "DEADLINE_CHANGED"
ROUTE_CHANGED = "ROUTE_CHANGED"
REQUIREMENTS_CHANGED = "REQUIREMENTS_CHANGED"
COST_CHANGED = "COST_CHANGED"
SOURCE_UNREACHABLE = "SOURCE_UNREACHABLE"
SOURCE_RECOVERED = "SOURCE_RECOVERED"

URGENT = "URGENT"
IMPORTANT = "IMPORTANT"
INFO = "INFO"

MONITORED_TARGET_STATUSES = (
    campaigns.DISCOVERED,
    campaigns.ENRICHING,
    campaigns.UNVERIFIED,
    campaigns.QUALIFIED,
    campaigns.READY,
    campaigns.DRAFTED,
    campaigns.NEEDS_APPROVAL,
    campaigns.APPROVED,
    campaigns.QUEUED,
    campaigns.FOLLOW_UP_DUE,
)

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8,
    "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

# Only explicit deadline language is accepted. A random date in a footer or
# article is never treated as a campaign deadline.
_DEADLINE_PREFIX = re.compile(
    r"\b(?:deadline|submit(?:\s+by)?|submissions?\s+(?:close|closes|closing)|"
    r"closing\s+date|entries\s+close|applications?\s+close|apply\s+by)\b",
    re.I,
)
_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
_US_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
_MONTH_DATE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(20\d{2})\b",
    re.I,
)


def _ensure_schema():
    global _schema_ready_path
    current = db.current_path()
    if _schema_ready_path == current:
        return
    db.execute(
        "CREATE TABLE IF NOT EXISTS intake_monitor_snapshot ("
        "id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, target_id TEXT NOT NULL, "
        "campaign_id TEXT NOT NULL, outlet_id TEXT NOT NULL, source_url TEXT NOT NULL, "
        "fetch_status TEXT NOT NULL, http_status INTEGER, content_hash TEXT, "
        "submissions_open TEXT, submission_excerpt TEXT, deadline_date TEXT, "
        "deadline_excerpt TEXT, route_fingerprint TEXT, requirements_fingerprint TEXT, "
        "requires_login INTEGER NOT NULL DEFAULT 0, requires_captcha INTEGER NOT NULL DEFAULT 0, "
        "cost_model TEXT, cost_amount REAL, cost_currency TEXT, fetched_at TEXT NOT NULL)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS ix_intake_snapshot_target "
        "ON intake_monitor_snapshot(tenant_id, target_id, fetched_at DESC)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS intake_monitor_event ("
        "id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, target_id TEXT NOT NULL, "
        "campaign_id TEXT NOT NULL, outlet_id TEXT NOT NULL, snapshot_id TEXT NOT NULL, "
        "kind TEXT NOT NULL, severity TEXT NOT NULL, summary TEXT NOT NULL, "
        "before_json TEXT, after_json TEXT, source_url TEXT NOT NULL, excerpt TEXT, "
        "created_at TEXT NOT NULL, acknowledged_at TEXT)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS ix_intake_event_open "
        "ON intake_monitor_event(tenant_id, acknowledged_at, created_at DESC)"
    )
    _schema_ready_path = current


def _hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _deadline(text):
    """Return an explicit deadline date and bounded evidence excerpt, if present."""
    text = " ".join((text or "").split())
    if not text:
        return None, None
    for prefix in _DEADLINE_PREFIX.finditer(text):
        start = max(0, prefix.start() - 45)
        end = min(len(text), prefix.end() + 110)
        window = text[prefix.start():end]
        parsed = None
        match = _ISO_DATE.search(window)
        if match:
            parsed = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if parsed is None:
            match = _US_DATE.search(window)
            if match:
                parsed = (int(match.group(3)), int(match.group(1)), int(match.group(2)))
        if parsed is None:
            match = _MONTH_DATE.search(window)
            if match:
                parsed = (int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)))
        if parsed is None:
            continue
        try:
            deadline = date(*parsed).isoformat()
        except ValueError:
            continue
        excerpt = text[start:end]
        return deadline, excerpt
    return None, None


def _route_shape(extracted):
    links = []
    for item in extracted.get("submission_links") or []:
        if isinstance(item, dict):
            links.append({
                "href": item.get("href"),
                "text": item.get("text"),
            })
    contacts = []
    for item in extracted.get("contacts") or []:
        if isinstance(item, dict) and item.get("role_based"):
            contacts.append(item.get("value"))
    return {
        "links": links[:8],
        "contacts": sorted({item for item in contacts if item})[:8],
        "requires_login": bool(extracted.get("requires_login")),
        "requires_captcha": bool(extracted.get("requires_captcha")),
    }


def _requirements_shape(extracted, deadline_date):
    # Deliberately exclude generic page text. Only submission-specific evidence
    # participates, which keeps normal editorial/homepage updates from creating noise.
    forms = []
    for form in extracted.get("forms") or []:
        if not isinstance(form, dict):
            continue
        forms.append({
            "action": form.get("action"),
            "method": form.get("method"),
            "inputs": sorted(str(item) for item in (form.get("inputs") or []))[:20],
        })
    return {
        "submission_state": extracted.get("submissions_open"),
        "submission_excerpt": extracted.get("submissions_excerpt"),
        "deadline": deadline_date,
        "cost_model": extracted.get("cost_model"),
        "cost_amount": extracted.get("cost_amount"),
        "cost_currency": extracted.get("cost_currency"),
        "forms": forms[:4],
        "route": _route_shape(extracted),
    }


def _target(target_id):
    principal = rbac.current_principal()
    row = campaigns.get_target(target_id)
    if row is None or row["tenant_id"] != principal.tenant_id:
        raise ValidationError("Unknown campaign target")
    if row["status"] not in MONITORED_TARGET_STATUSES:
        raise ValidationError("This opportunity is not currently monitored")
    if not row["outlet_url"]:
        raise ValidationError("This opportunity has no public source URL to monitor")
    return row


def latest_snapshot(target_id):
    _ensure_schema()
    return db.query_one(
        "SELECT * FROM intake_monitor_snapshot WHERE tenant_id = ? AND target_id = ? "
        "ORDER BY fetched_at DESC, rowid DESC LIMIT 1",
        (rbac.current_principal().tenant_id, target_id),
    )


def due(target_id, hours=24):
    row = latest_snapshot(target_id)
    if row is None:
        return True
    age_days = clock.days_since(row["fetched_at"])
    return age_days is None or age_days * 24 >= hours


def _insert_snapshot(target, **values):
    snapshot_id = db.new_id("ims")
    payload = {
        "id": snapshot_id,
        "tenant_id": target["tenant_id"],
        "target_id": target["id"],
        "campaign_id": target["campaign_id"],
        "outlet_id": target["outlet_id"],
        "source_url": target["outlet_url"],
        "fetch_status": values.get("fetch_status") or evidence.FETCH_ERROR,
        "http_status": values.get("http_status"),
        "content_hash": values.get("content_hash"),
        "submissions_open": values.get("submissions_open"),
        "submission_excerpt": values.get("submission_excerpt"),
        "deadline_date": values.get("deadline_date"),
        "deadline_excerpt": values.get("deadline_excerpt"),
        "route_fingerprint": values.get("route_fingerprint"),
        "requirements_fingerprint": values.get("requirements_fingerprint"),
        "requires_login": 1 if values.get("requires_login") else 0,
        "requires_captcha": 1 if values.get("requires_captcha") else 0,
        "cost_model": values.get("cost_model"),
        "cost_amount": values.get("cost_amount"),
        "cost_currency": values.get("cost_currency"),
        "fetched_at": clock.now_iso(),
    }
    db.insert("intake_monitor_snapshot", payload)
    return db.query_one("SELECT * FROM intake_monitor_snapshot WHERE id = ?", (snapshot_id,))


def _days_until(value):
    if not value:
        return None
    try:
        target = date.fromisoformat(value)
    except ValueError:
        return None
    return (target - clock.now().date()).days


def _event(target, snapshot, kind, severity, summary, before=None, after=None, excerpt=None):
    event_id = db.new_id("ime")
    db.insert("intake_monitor_event", {
        "id": event_id,
        "tenant_id": target["tenant_id"],
        "target_id": target["id"],
        "campaign_id": target["campaign_id"],
        "outlet_id": target["outlet_id"],
        "snapshot_id": snapshot["id"],
        "kind": kind,
        "severity": severity,
        "summary": summary[:500],
        "before_json": json.dumps(before, default=str) if before is not None else None,
        "after_json": json.dumps(after, default=str) if after is not None else None,
        "source_url": snapshot["source_url"],
        "excerpt": (excerpt or "")[:1400] or None,
        "created_at": clock.now_iso(),
        "acknowledged_at": None,
    })
    audit.record(
        "intake_monitor.change_detected",
        entity_type="campaign_target",
        entity_id=target["id"],
        payload={"event_id": event_id, "kind": kind, "severity": severity},
    )
    return event_id


def _compare(target, previous, current):
    created = []
    outlet_name = target["outlet_name"] or target["outlet_domain"] or "Opportunity"

    if previous is None:
        days = _days_until(current["deadline_date"])
        if current["deadline_date"] and days is not None and days >= 0:
            severity = URGENT if days <= 7 else IMPORTANT if days <= 30 else INFO
            created.append(_event(
                target, current, DEADLINE_FOUND, severity,
                f"{outlet_name} lists a submission deadline of {current['deadline_date']}",
                after={"deadline": current["deadline_date"]},
                excerpt=current["deadline_excerpt"],
            ))
        return created

    previous_ok = previous["fetch_status"] == evidence.FETCH_OK
    current_ok = current["fetch_status"] == evidence.FETCH_OK
    if previous_ok and not current_ok:
        created.append(_event(
            target, current, SOURCE_UNREACHABLE, IMPORTANT,
            f"Reach could not re-check {outlet_name}'s submission source",
            before={"fetch_status": previous["fetch_status"]},
            after={"fetch_status": current["fetch_status"]},
        ))
        return created
    if not previous_ok and current_ok:
        created.append(_event(
            target, current, SOURCE_RECOVERED, INFO,
            f"{outlet_name}'s submission source is reachable again",
            before={"fetch_status": previous["fetch_status"]},
            after={"fetch_status": current["fetch_status"]},
        ))
    if not current_ok:
        return created

    old_state = previous["submissions_open"]
    new_state = current["submissions_open"]
    if old_state != new_state and new_state == extractor.OPEN:
        created.append(_event(
            target, current, WINDOW_OPENED, URGENT,
            f"{outlet_name} appears to have opened submissions",
            before={"submissions_open": old_state},
            after={"submissions_open": new_state},
            excerpt=current["submission_excerpt"],
        ))
    elif old_state != new_state and new_state == extractor.CLOSED:
        created.append(_event(
            target, current, WINDOW_CLOSED, URGENT,
            f"{outlet_name} appears to have closed submissions",
            before={"submissions_open": old_state},
            after={"submissions_open": new_state},
            excerpt=current["submission_excerpt"],
        ))

    if previous["deadline_date"] != current["deadline_date"]:
        if current["deadline_date"]:
            days = _days_until(current["deadline_date"])
            severity = URGENT if days is not None and 0 <= days <= 7 else IMPORTANT
            kind = DEADLINE_FOUND if not previous["deadline_date"] else DEADLINE_CHANGED
            created.append(_event(
                target, current, kind, severity,
                f"{outlet_name} lists a submission deadline of {current['deadline_date']}",
                before={"deadline": previous["deadline_date"]},
                after={"deadline": current["deadline_date"]},
                excerpt=current["deadline_excerpt"],
            ))
        elif previous["deadline_date"]:
            created.append(_event(
                target, current, DEADLINE_CHANGED, INFO,
                f"The previously detected deadline for {outlet_name} is no longer present",
                before={"deadline": previous["deadline_date"]},
                after={"deadline": None},
                excerpt=current["submission_excerpt"],
            ))

    if previous["route_fingerprint"] and current["route_fingerprint"] \
            and previous["route_fingerprint"] != current["route_fingerprint"]:
        created.append(_event(
            target, current, ROUTE_CHANGED, IMPORTANT,
            f"{outlet_name}'s submission route changed",
            before={"route": previous["route_fingerprint"]},
            after={"route": current["route_fingerprint"]},
            excerpt=current["submission_excerpt"],
        ))

    old_cost = (previous["cost_model"], previous["cost_amount"], previous["cost_currency"])
    new_cost = (current["cost_model"], current["cost_amount"], current["cost_currency"])
    if old_cost != new_cost and previous["cost_model"] is not None:
        created.append(_event(
            target, current, COST_CHANGED, IMPORTANT,
            f"{outlet_name}'s submission cost information changed",
            before={"model": old_cost[0], "amount": old_cost[1], "currency": old_cost[2]},
            after={"model": new_cost[0], "amount": new_cost[1], "currency": new_cost[2]},
            excerpt=current["submission_excerpt"],
        ))

    # Requirements fingerprint includes route/cost/deadline. Avoid a duplicate
    # catch-all event when one of those explicit changes already explains it.
    explicit = {ROUTE_CHANGED, COST_CHANGED, DEADLINE_FOUND, DEADLINE_CHANGED,
                WINDOW_OPENED, WINDOW_CLOSED}
    explicit_created = {
        db.query_one("SELECT kind FROM intake_monitor_event WHERE id = ?", (eid,))["kind"]
        for eid in created
    }
    if (previous["requirements_fingerprint"] and current["requirements_fingerprint"]
            and previous["requirements_fingerprint"] != current["requirements_fingerprint"]
            and not (explicit_created & explicit)):
        created.append(_event(
            target, current, REQUIREMENTS_CHANGED, IMPORTANT,
            f"{outlet_name}'s submission requirements changed",
            before={"requirements": previous["requirements_fingerprint"]},
            after={"requirements": current["requirements_fingerprint"]},
            excerpt=current["submission_excerpt"],
        ))
    return created


def refresh_target(target_id, force=False):
    """Refresh one target and return its snapshot plus any new change events."""
    _ensure_schema()
    target = _target(target_id)
    if not force and not due(target_id):
        return {"target_id": target_id, "skipped": "NOT_DUE", "events": []}
    previous = latest_snapshot(target_id)
    source_url = target["outlet_url"]
    domain = netguard.registrable_domain(urlsplit(source_url).hostname or "")

    try:
        result = fetcher.fetch(source_url)
        cleaned = sanitizer.sanitize(result.text(), base_url=result.final_url)
        extracted = extractor.extract(cleaned, result.final_url, result.domain,
                                      http_status=result.status)
        if extracted.get("page_state") != extractor.PAGE_OK:
            snapshot = _insert_snapshot(
                target,
                fetch_status=evidence.FETCH_ERROR,
                http_status=result.status,
            )
            events = _compare(target, previous, snapshot)
            return {"target_id": target_id, "snapshot_id": snapshot["id"], "events": events}

        deadline_date, deadline_excerpt = _deadline(cleaned.get("visible_text"))
        route_shape = _route_shape(extracted)
        requirements_shape = _requirements_shape(extracted, deadline_date)
        document_id = evidence.record_source_document(
            url=result.final_url,
            domain=result.domain,
            provider="open_web_fetch",
            fetch_status=evidence.FETCH_OK,
            campaign_id=target["campaign_id"],
            http_status=result.status,
            mime=result.mime,
            byte_count=result.bytes,
            sanitized_text=cleaned.get("visible_text"),
            title=cleaned.get("title"),
            classification=extracted.get("classification"),
            robots_decision=result.robots_decision,
            stale_days=7,
        )
        snapshot = _insert_snapshot(
            target,
            fetch_status=evidence.FETCH_OK,
            http_status=result.status,
            content_hash=_hash(cleaned.get("visible_text") or ""),
            submissions_open=extracted.get("submissions_open"),
            submission_excerpt=extracted.get("submissions_excerpt"),
            deadline_date=deadline_date,
            deadline_excerpt=deadline_excerpt,
            route_fingerprint=_hash(route_shape),
            requirements_fingerprint=_hash(requirements_shape),
            requires_login=extracted.get("requires_login"),
            requires_captcha=extracted.get("requires_captcha"),
            cost_model=extracted.get("cost_model"),
            cost_amount=extracted.get("cost_amount"),
            cost_currency=extracted.get("cost_currency"),
        )

        # Keep the outlet's current explicit submission state fresh, but never
        # replace a known state with UNKNOWN.
        if extracted.get("submissions_open") in (extractor.OPEN, extractor.CLOSED):
            db.update("outlet", target["outlet_id"], {
                "submissions_open": extracted["submissions_open"],
                "updated_at": clock.now_iso(),
            })

        events = _compare(target, previous, snapshot)
        if previous is None or events:
            if extracted.get("submissions_open") in (extractor.OPEN, extractor.CLOSED):
                evidence.record(
                    "campaign_target", target_id, "submissions_open",
                    extracted["submissions_open"], result.final_url, result.domain,
                    "OFFICIAL", excerpt=extracted.get("submissions_excerpt"),
                    confidence=extracted.get("submissions_confidence") or 0.7,
                    source_document_id=document_id, stale_days=7,
                    verified_at=clock.now_iso(),
                )
            if deadline_date:
                evidence.record(
                    "campaign_target", target_id, "submission_deadline",
                    deadline_date, result.final_url, result.domain, "OFFICIAL",
                    excerpt=deadline_excerpt, confidence=0.85,
                    source_document_id=document_id, stale_days=7,
                    verified_at=clock.now_iso(),
                )
        return {"target_id": target_id, "snapshot_id": snapshot["id"], "events": events}
    except FetchBlocked as exc:
        evidence.record_source_document(
            url=source_url,
            domain=domain,
            provider="open_web_fetch",
            fetch_status=evidence.FETCH_BLOCKED,
            campaign_id=target["campaign_id"],
            block_reason=str(exc)[:500],
            stale_days=1,
        )
        snapshot = _insert_snapshot(target, fetch_status=evidence.FETCH_BLOCKED)
        events = _compare(target, previous, snapshot)
        return {"target_id": target_id, "snapshot_id": snapshot["id"], "events": events}


def monitored_targets(limit=100):
    _ensure_schema()
    principal = rbac.current_principal()
    placeholders = ",".join("?" for _ in MONITORED_TARGET_STATUSES)
    sql = (
        "SELECT t.id, t.status, o.name AS outlet_name, o.domain AS outlet_domain, o.url AS outlet_url, "
        "c.name AS campaign_name FROM campaign_target t "
        "JOIN campaign c ON c.id = t.campaign_id "
        "JOIN outlet o ON o.id = t.outlet_id "
        "WHERE t.tenant_id = ? AND c.status NOT IN (?, ?) AND t.status IN (" + placeholders + ") "
        "AND o.url IS NOT NULL ORDER BY t.updated_at DESC LIMIT ?"
    )
    params = [principal.tenant_id, campaigns.COMPLETED, campaigns.CANCELLED]
    params.extend(MONITORED_TARGET_STATUSES)
    params.append(limit)
    return db.query(sql, tuple(params))


def scan_due(limit=25, force=False):
    checked = 0
    refreshed = 0
    created = 0
    failures = 0
    for row in monitored_targets(limit=limit):
        checked += 1
        if not force and not due(row["id"]):
            continue
        try:
            result = refresh_target(row["id"], force=True)
            refreshed += 1
            created += len(result.get("events") or [])
        except Exception as exc:
            failures += 1
            audit.record(
                "intake_monitor.refresh_failed",
                entity_type="campaign_target",
                entity_id=row["id"],
                payload={"error": str(exc)[:500]},
            )
    return {"checked": checked, "refreshed": refreshed, "events": created, "failures": failures}


def events(open_only=True, limit=50):
    _ensure_schema()
    principal = rbac.current_principal()
    sql = (
        "SELECT e.*, o.name AS outlet_name, o.domain AS outlet_domain, "
        "c.name AS campaign_name, t.status AS target_status "
        "FROM intake_monitor_event e "
        "JOIN outlet o ON o.id = e.outlet_id "
        "JOIN campaign c ON c.id = e.campaign_id "
        "JOIN campaign_target t ON t.id = e.target_id "
        "WHERE e.tenant_id = ?"
    )
    params = [principal.tenant_id]
    if open_only:
        sql += " AND e.acknowledged_at IS NULL"
    sql += (
        " ORDER BY CASE e.severity WHEN 'URGENT' THEN 0 WHEN 'IMPORTANT' THEN 1 ELSE 2 END, "
        "e.created_at DESC LIMIT ?"
    )
    params.append(limit)
    return db.query(sql, tuple(params))


def acknowledge(event_id):
    _ensure_schema()
    principal = rbac.current_principal()
    row = db.query_one(
        "SELECT * FROM intake_monitor_event WHERE id = ? AND tenant_id = ?",
        (event_id, principal.tenant_id),
    )
    if row is None:
        raise ValidationError("Unknown intake-monitor event")
    db.update("intake_monitor_event", event_id, {"acknowledged_at": clock.now_iso()})
    audit.record(
        "intake_monitor.acknowledged",
        entity_type="intake_monitor_event",
        entity_id=event_id,
        actor_kind=audit.ACTOR_USER,
    )
    return True


def summary():
    open_events = events(open_only=True, limit=50)
    urgent = [row for row in open_events if row["severity"] == URGENT]
    important = [row for row in open_events if row["severity"] == IMPORTANT]
    targets = monitored_targets(limit=100)
    due_count = sum(1 for row in targets if due(row["id"]))
    return {
        "events": open_events,
        "urgent": urgent,
        "important": important,
        "open_count": len(open_events),
        "urgent_count": len(urgent),
        "monitored_count": len(targets),
        "due_count": due_count,
    }
