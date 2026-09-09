"""Standalone REACH plans, entitlements, usage, and ecosystem discounts."""

import os
from datetime import datetime, timezone

from flask import session

from . import db
from .errors import ReachError
from . import rbac


class SubscriptionRequired(ReachError):
    kind = "SUBSCRIPTION_REQUIRED"


PLAN_ORDER = ("preview", "solo", "manager", "roster", "enterprise")
PLANS = {
    "preview": {
        "name": "Preview", "monthly": 0, "annual": 0,
        "tagline": "Explore the real workflow before you subscribe.",
        "limits": {"active_campaigns": 1, "research_runs": 2,
                   "approved_outreach": 0},
        "features": ("One active campaign", "Two research runs each month",
                     "Evidence and qualification preview", "No outbound approvals"),
    },
    "solo": {
        "name": "Solo", "monthly": 29, "annual": 290,
        "tagline": "For one independent artist moving one release at a time.",
        "limits": {"active_campaigns": 3, "research_runs": 50,
                   "approved_outreach": 100},
        "features": ("Three active campaigns", "50 research runs each month",
                     "100 approved outreach actions", "Save evidence-backed campaign history"),
    },
    "manager": {
        "name": "Manager", "monthly": 79, "annual": 790,
        "tagline": "For managers coordinating a focused artist roster.",
        "limits": {"active_campaigns": 15, "research_runs": 250,
                   "approved_outreach": 500},
        "features": ("15 active campaigns", "250 research runs each month",
                     "500 approved outreach actions", "Cross-campaign relationship visibility"),
    },
    "roster": {
        "name": "Roster", "monthly": 199, "annual": 1990,
        "tagline": "For teams operating a larger release pipeline.",
        "limits": {"active_campaigns": 50, "research_runs": 1000,
                   "approved_outreach": 2000},
        "features": ("50 active campaigns", "1,000 research runs each month",
                     "2,000 approved outreach actions", "Priority onboarding and support"),
    },
    "enterprise": {
        "name": "Enterprise", "monthly": None, "annual": None,
        "tagline": "A governed deployment for complex organizations.",
        "limits": {"active_campaigns": None, "research_runs": None,
                   "approved_outreach": None},
        "features": ("Custom operating limits", "Security and workflow review",
                     "Migration planning", "Contracted support"),
    },
}

METRIC_LABELS = {
    "active_campaigns": "Active campaigns",
    "research_runs": "Research runs this month",
    "approved_outreach": "Approved outreach this month",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _period_key():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def tenant_id():
    return rbac.current_principal().tenant_id


def _default_plan():
    candidate = (os.environ.get("REACH_DEFAULT_PLAN") or "preview").strip().lower()
    return candidate if candidate in PLANS else "preview"


def subscription(tenant=None):
    tenant = tenant or tenant_id()
    row = db.query_one("SELECT * FROM reach_subscription WHERE tenant_id = ?", (tenant,))
    if row is None:
        now = _now()
        db.execute(
            "INSERT INTO reach_subscription "
            "(tenant_id, plan, billing_interval, status, created_at, updated_at) "
            "VALUES (?, ?, 'monthly', 'active', ?, ?)",
            (tenant, _default_plan(), now, now),
        )
        row = db.query_one("SELECT * FROM reach_subscription WHERE tenant_id = ?", (tenant,))
    return row


def set_subscription(plan, interval="monthly", status="active", tenant=None,
                     stripe_customer_id=None, stripe_subscription_id=None,
                     current_period_end=None):
    if plan not in PLANS:
        raise ReachError("That REACH plan does not exist")
    if interval not in ("monthly", "annual"):
        raise ReachError("Billing interval must be monthly or annual")
    tenant = tenant or tenant_id()
    now = _now()
    db.execute(
        "INSERT INTO reach_subscription "
        "(tenant_id, plan, billing_interval, status, stripe_customer_id, "
        "stripe_subscription_id, current_period_end, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(tenant_id) DO UPDATE SET plan=excluded.plan, "
        "billing_interval=excluded.billing_interval, status=excluded.status, "
        "stripe_customer_id=COALESCE(excluded.stripe_customer_id, reach_subscription.stripe_customer_id), "
        "stripe_subscription_id=COALESCE(excluded.stripe_subscription_id, reach_subscription.stripe_subscription_id), "
        "current_period_end=COALESCE(excluded.current_period_end, reach_subscription.current_period_end), "
        "updated_at=excluded.updated_at",
        (tenant, plan, interval, status, stripe_customer_id,
         stripe_subscription_id, current_period_end, now, now),
    )
    return subscription(tenant)


def cancel_by_stripe_subscription(subscription_id):
    if not subscription_id:
        return False
    cur = db.execute(
        "UPDATE reach_subscription SET status='canceled', plan='preview', "
        "stripe_subscription_id=NULL, updated_at=? WHERE stripe_subscription_id=?",
        (_now(), subscription_id),
    )
    return cur.rowcount > 0


def mark_payment_failed(customer_id):
    if not customer_id:
        return False
    cur = db.execute(
        "UPDATE reach_subscription SET status='past_due', updated_at=? "
        "WHERE stripe_customer_id=?", (_now(), customer_id))
    return cur.rowcount > 0


def usage(metric, tenant=None):
    tenant = tenant or tenant_id()
    if metric == "active_campaigns":
        row = db.query_one(
            "SELECT COUNT(*) AS n FROM campaign WHERE tenant_id=? "
            "AND status NOT IN ('COMPLETED', 'CANCELLED')", (tenant,))
        return int(row["n"] if row else 0)
    row = db.query_one(
        "SELECT quantity FROM reach_usage WHERE tenant_id=? AND period_key=? AND metric=?",
        (tenant, _period_key(), metric),
    )
    return int(row["quantity"] if row else 0)


def increment(metric, amount=1, tenant=None):
    if metric not in METRIC_LABELS or metric == "active_campaigns":
        raise ReachError("Unknown metered REACH action")
    tenant = tenant or tenant_id()
    now = _now()
    db.execute(
        "INSERT INTO reach_usage (tenant_id, period_key, metric, quantity, updated_at) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(tenant_id, period_key, metric) "
        "DO UPDATE SET quantity=quantity+excluded.quantity, updated_at=excluded.updated_at",
        (tenant, _period_key(), metric, int(amount), now),
    )
    return usage(metric, tenant)


def entitlement(metric, tenant=None):
    sub = subscription(tenant)
    plan_key = sub["plan"] if sub["plan"] in PLANS else "preview"
    limit = PLANS[plan_key]["limits"].get(metric)
    used = usage(metric, tenant)
    return {"metric": metric, "label": METRIC_LABELS[metric], "used": used,
            "limit": limit, "remaining": None if limit is None else max(0, limit - used),
            "allowed": limit is None or used < limit}


def require(metric, tenant=None):
    state = entitlement(metric, tenant)
    if not state["allowed"]:
        raise SubscriptionRequired(
            f"{state['label']} has reached this plan's limit. Your existing work is safe; "
            "choose a REACH plan to continue."
        )
    return state


def _signed_in_street_banker_user():
    try:
        user_id = session.get("user_id")
    except RuntimeError:
        return None
    if not user_id:
        return None
    try:
        import db as street_banker_db
        return street_banker_db.get_user(user_id)
    except Exception:
        return None


def passport(tenant=None):
    """Return only verified ecosystem eligibility; never trust a promo string."""
    tenant = tenant or tenant_id()
    user = _signed_in_street_banker_user()
    if user and user.get("stripe_subscription_id"):
        db.execute(
            "INSERT INTO reach_passport_product "
            "(tenant_id, product_key, status, source, verified_at) VALUES (?, 'street-banker', "
            "'active', 'v2-session', ?) ON CONFLICT(tenant_id, product_key) DO UPDATE SET "
            "status='active', source='v2-session', verified_at=excluded.verified_at",
            (tenant, _now()),
        )
    products = db.query(
        "SELECT product_key FROM reach_passport_product WHERE tenant_id=? AND status='active'",
        (tenant,),
    )
    count = len(products)
    discount = 25 if count >= 2 else (20 if count == 1 else 0)
    return {"verified": count > 0, "product_count": count, "discount_percent": discount,
            "products": [row["product_key"] for row in products]}


def dashboard(tenant=None):
    tenant = tenant or tenant_id()
    sub = subscription(tenant)
    key = sub["plan"] if sub["plan"] in PLANS else "preview"
    return {
        "subscription": dict(sub), "plan_key": key, "plan": PLANS[key],
        "usage": [entitlement(metric, tenant) for metric in METRIC_LABELS],
        "passport": passport(tenant), "period_key": _period_key(),
    }


def discounted_price(plan_key, interval, discount_percent):
    amount = PLANS[plan_key]["annual" if interval == "annual" else "monthly"]
    if amount is None:
        return None
    return round(amount * (100 - int(discount_percent or 0)) / 100, 2)
