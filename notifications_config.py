"""Config-driven data for the Notifications inbox.

Composes a notification feed from the same action-center items surfaced
elsewhere (connection alerts, leaks, payouts) plus a couple of system
notices, with per-item read state tracked in a module-level set so
mark-as-read persists for the session.
"""

from royalty_data import (
    get_action_center,
    get_royalty_leak_alerts,
    get_platform_balances,
    get_recent_payouts,
    get_kpis,
    get_platform_catalog,
)

_read_ids = set()

SEVERITY_TONE = {
    "critical": "border-red-500/20 bg-red-500/10 text-red-400",
    "high": "border-red-500/20 bg-red-500/10 text-red-400",
    "warning": "border-amber-500/20 bg-amber-500/10 text-amber-400",
    "medium": "border-amber-500/20 bg-amber-500/10 text-amber-400",
    "info": "border-blue-500/20 bg-blue-500/10 text-blue-400",
    "success": "border-green-500/20 bg-green-500/10 text-green-400",
}


def _build():
    balances = get_platform_balances()
    payouts = get_recent_payouts()
    kpis = get_kpis()
    catalog = get_platform_catalog()
    action_center = get_action_center(get_royalty_leak_alerts(balances, payouts, kpis, catalog), payouts)
    items = []
    for i, a in enumerate(action_center):
        items.append({
            "id": "ntf-ac-%d" % i,
            "category": "Alert" if a["kind"] == "alert" else a["kind"].title(),
            "title": a["title"],
            "description": a["description"],
            "severity": a.get("severity", "info"),
            "route": a.get("route"),
        })
    # A couple of standing system notices.
    items.append({"id": "ntf-sys-welcome", "category": "System",
                  "title": "Weekly summary is ready", "description": "Your royalty summary for this week is available in Reports.",
                  "severity": "info", "route": "/reports"})
    items.append({"id": "ntf-sys-payout", "category": "Payout",
                  "title": "Next payout scheduled", "description": "Your next payout is on its way — see the calendar on Royalties.",
                  "severity": "success", "route": "/royalties"})
    return items


def get_notifications_data():
    items = _build()
    for it in items:
        it["read"] = it["id"] in _read_ids
        it["tone"] = SEVERITY_TONE.get(it["severity"], SEVERITY_TONE["info"])
    unread = sum(1 for it in items if not it["read"])
    return {
        "notifications": items,
        "unread": unread,
        "total": len(items),
    }


def mark_notification_read(notification_id):
    _read_ids.add(notification_id)


def mark_all_read(ids):
    _read_ids.update(ids)


def reset_notifications_state():
    _read_ids.clear()
