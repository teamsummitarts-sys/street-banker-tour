"""Street Banker V2 Company OS domain model.

This module deliberately contains no Flask or database code.  The ten desks,
their two permanent capabilities, and the deterministic first-pass planning
engine live here so routes, templates, and tests all read the same product
truth.
"""

from __future__ import annotations

from datetime import date, timedelta


TEAM = (
    {
        "key": "manager",
        "seat": "01",
        "name": "Your Manager",
        "role": "Executive Manager",
        "initials": "MG",
        "focus": "Sets direction, assigns the company, and controls approvals.",
        "href": "/team",
        "capabilities": (
            {
                "key": "brief_to_plan",
                "name": "Brief-to-Plan",
                "description": "Turn one outcome into accountable work across the company.",
                "output": "Approved operating plan",
                "href": "/team?desk=manager&feature=brief_to_plan",
            },
            {
                "key": "executive_review",
                "name": "Executive Review",
                "description": "Review specialist outputs and return one decision to the owner.",
                "output": "Executive decision brief",
                "href": "/team?desk=manager&feature=executive_review",
            },
        ),
    },
    {
        "key": "a_and_r",
        "seat": "02",
        "name": "Your A&R",
        "role": "A&R Director",
        "initials": "AR",
        "focus": "Makes repertoire and release decisions from the music and the market.",
        "href": "/catalog",
        "capabilities": (
            {
                "key": "track_evaluation",
                "name": "Track Evaluation",
                "description": "Evaluate the recording, positioning, audience fit, and gaps.",
                "output": "Track evaluation",
                "href": "/catalog",
            },
            {
                "key": "release_decision",
                "name": "Release Decision",
                "description": "Make a documented Go, Revise, or Hold recommendation.",
                "output": "A&R decision memo",
                "href": "/releases/autopilot",
            },
        ),
    },
    {
        "key": "marketing",
        "seat": "03",
        "name": "Your Marketer",
        "role": "Marketing Director",
        "initials": "MK",
        "focus": "Builds demand and connects every campaign action to a target.",
        "href": "/rollout-studio",
        "capabilities": (
            {
                "key": "campaign_architect",
                "name": "Campaign Architect",
                "description": "Build the channel, content, audience, and timing plan.",
                "output": "Campaign calendar",
                "href": "/rollout-studio",
            },
            {
                "key": "conversion_tracker",
                "name": "Conversion Tracker",
                "description": "Measure movement from attention to owned audience and revenue.",
                "output": "Conversion report",
                "href": "/stats",
            },
        ),
    },
    {
        "key": "publicist",
        "seat": "04",
        "name": "Your Publicist",
        "role": "Publicity Director",
        "initials": "PR",
        "focus": "Shapes the story and manages accountable media outreach.",
        "href": "/press-desk",
        "capabilities": (
            {
                "key": "story_builder",
                "name": "Story Builder",
                "description": "Turn the release into a clear press narrative and package.",
                "output": "Approved press package",
                "href": "/press-desk",
            },
            {
                "key": "outreach_desk",
                "name": "Outreach Desk",
                "description": "Track pitches, follow-ups, responses, and coverage.",
                "output": "Outreach report",
                "href": "/press-desk",
            },
        ),
    },
    {
        "key": "tour_manager",
        "seat": "05",
        "name": "Your Tour Manager",
        "role": "Tour Director",
        "initials": "TM",
        "focus": "Turns live opportunities into routed, advanced, profitable shows.",
        "href": "/tours",
        "capabilities": (
            {
                "key": "route_profit",
                "name": "Route & Profit",
                "description": "Model routing, travel, guarantees, costs, and break-even.",
                "output": "Route and profit plan",
                "href": "/tours",
            },
            {
                "key": "show_advance",
                "name": "Show Advance",
                "description": "Close venue, production, travel, guest, and settlement details.",
                "output": "Show advance pack",
                "href": "/tours",
            },
        ),
    },
    {
        "key": "accountant",
        "seat": "06",
        "name": "Your Royalty Accountant",
        "role": "Revenue Director",
        "initials": "RA",
        "focus": "Turns statements into reconciled revenue and recovery actions.",
        "href": "/statements",
        "capabilities": (
            {
                "key": "statement_sweep",
                "name": "Statement Sweep",
                "description": "Reconcile statement rows, sources, periods, and discrepancies.",
                "output": "Statement discrepancy report",
                "href": "/statements",
            },
            {
                "key": "recovery_cases",
                "name": "Recovery Cases",
                "description": "Open, evidence, and track missing-money recovery work.",
                "output": "Recovery queue",
                "href": "/royalty-recovery/cases",
            },
        ),
    },
    {
        "key": "attorney",
        "seat": "07",
        "name": "Your Rights Attorney",
        "role": "Rights & Deal Director",
        "initials": "RT",
        "focus": "Identifies ownership and deal issues before they become expensive.",
        "href": "/deal-room",
        "disclaimer": "Issue identification and preparation, not legal representation.",
        "capabilities": (
            {
                "key": "ownership_readiness",
                "name": "Ownership Readiness",
                "description": "Check splits, permissions, identifiers, and clearance gaps.",
                "output": "Rights-readiness checklist",
                "href": "/tracks",
            },
            {
                "key": "deal_risk",
                "name": "Deal Risk",
                "description": "Surface commercial and ownership terms requiring counsel.",
                "output": "Deal-risk brief",
                "href": "/deal-room",
            },
        ),
    },
    {
        "key": "creative_director",
        "seat": "08",
        "name": "Your Creative Director",
        "role": "Creative Director",
        "initials": "CD",
        "focus": "Keeps the visual system coherent from first asset through campaign.",
        "href": "/artwork",
        "capabilities": (
            {
                "key": "visual_identity",
                "name": "Visual Identity",
                "description": "Lock the release world, rules, hierarchy, and visual direction.",
                "output": "Visual identity lock",
                "href": "/artwork",
            },
            {
                "key": "asset_approval",
                "name": "Asset Approval",
                "description": "Review, version, approve, and package campaign assets.",
                "output": "Approved asset package",
                "href": "/vault",
            },
        ),
    },
    {
        "key": "producer_engineer",
        "seat": "09",
        "name": "Your Producer",
        "role": "Studio Director",
        "initials": "PE",
        "focus": "Moves recordings from creative intent to delivery-ready masters.",
        "href": "/rack",
        "capabilities": (
            {
                "key": "mix_readiness",
                "name": "Mix Readiness",
                "description": "Evaluate balance, dynamics, translation, and delivery gaps.",
                "output": "Mix-readiness report",
                "href": "/rack",
            },
            {
                "key": "production_brief",
                "name": "Production Brief",
                "description": "Turn creative direction into a precise production handoff.",
                "output": "Production handoff",
                "href": "/remix-lab",
            },
        ),
    },
    {
        "key": "assistant",
        "seat": "10",
        "name": "Your Executive Assistant",
        "role": "Operations Coordinator",
        "initials": "EA",
        "focus": "Closes the loop on deadlines, decisions, documents, and follow-up.",
        "href": "/actions",
        "capabilities": (
            {
                "key": "approval_desk",
                "name": "Approval Desk",
                "description": "Surface decisions, deadlines, blockers, and overdue reviews.",
                "output": "Daily approval agenda",
                "href": "/actions",
            },
            {
                "key": "follow_up",
                "name": "Follow-Up",
                "description": "Track documents, responses, owners, and the next promised action.",
                "output": "Closed-loop follow-up report",
                "href": "/documents",
            },
        ),
    },
)

TEAM_BY_KEY = {member["key"]: member for member in TEAM}
FEATURE_BY_KEY = {
    feature["key"]: feature
    for member in TEAM
    for feature in member["capabilities"]
}

OBJECTIVE_TYPE_LABELS = {
    "release": "Release",
    "campaign": "Campaign",
    "tour": "Tour",
    "revenue": "Revenue",
    "rights": "Rights",
    "creative": "Creative",
    "general": "Company",
}

_TYPE_KEYWORDS = (
    ("tour", ("tour", "show", "venue", "route", "ticket", "concert", "festival")),
    ("revenue", ("royalty", "statement", "money", "payment", "revenue", "income", "payout")),
    ("rights", ("split", "rights", "deal", "contract", "clearance", "ownership", "publishing")),
    ("campaign", ("campaign", "marketing", "audience", "fans", "press", "publicity", "content")),
    ("creative", ("artwork", "creative", "visual", "brand", "identity", "merch")),
    ("release", ("release", "single", "album", "song", "track", "master", "launch")),
)


def capability(member_key, capability_key):
    """Return one capability only when it belongs to the requested desk."""
    member = TEAM_BY_KEY.get(member_key)
    if member is None:
        return None
    return next(
        (item for item in member["capabilities"]
         if item["key"] == capability_key),
        None,
    )


def detect_objective_type(title, success_condition=""):
    """Classify an objective with a transparent, deterministic keyword pass."""
    text = f"{title or ''} {success_condition or ''}".lower()
    scores = {
        kind: sum(1 for word in keywords if word in text)
        for kind, keywords in _TYPE_KEYWORDS
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "general"


_PLAN_TEMPLATES = {
    "release": (
        ("a_and_r", "release_decision", "Make the release decision",
         "Current master or private listening link",
         "A&R memo with a Go, Revise, or Hold decision", 2, 35),
        ("producer_engineer", "mix_readiness", "Confirm master readiness",
         "Final mix and reference notes",
         "Mix-readiness report with required production changes", 4, 28),
        ("attorney", "ownership_readiness", "Clear ownership for release",
         "Splits, contributors, samples, and available agreements",
         "Rights-readiness checklist with unresolved issues", 6, 21),
        ("creative_director", "visual_identity", "Lock the release identity",
         "Approved positioning, music, and available imagery",
         "Visual identity lock and asset requirements", 8, 18),
        ("marketing", "campaign_architect", "Build the release campaign",
         "Release date, audience, budget, and approved identity",
         "Campaign calendar with channels, timing, and targets", 10, 14),
        ("publicist", "story_builder", "Build the press story",
         "Release narrative, artist facts, credits, and approved assets",
         "Press package with narrative, angles, and announcement copy", 12, 10),
    ),
    "campaign": (
        ("marketing", "campaign_architect", "Build the campaign architecture",
         "Offer, audience, budget, channels, and deadline",
         "Campaign calendar with channel targets", 2, 21),
        ("creative_director", "asset_approval", "Define and approve campaign assets",
         "Campaign architecture and available source assets",
         "Versioned approved asset package", 4, 16),
        ("publicist", "outreach_desk", "Prepare accountable outreach",
         "Campaign story, proof points, contacts, and embargoes",
         "Outreach list, sequence, and reporting format", 6, 12),
        ("marketing", "conversion_tracker", "Lock campaign measurement",
         "Destination links and commercial success condition",
         "Conversion measurement plan and reporting cadence", 8, 7),
    ),
    "tour": (
        ("tour_manager", "route_profit", "Build the route and profit model",
         "Markets, dates, holds, guarantees, crew, and travel assumptions",
         "Route plan with show-level margin and break-even", 2, 30),
        ("marketing", "campaign_architect", "Build the ticket-demand plan",
         "Confirmed markets, capacities, onsale dates, and audience data",
         "Market-by-market ticket campaign", 4, 24),
        ("tour_manager", "show_advance", "Advance the confirmed shows",
         "Venue contacts, riders, party size, production, and settlement terms",
         "Show advance packs and unresolved production items", 6, 14),
        ("assistant", "follow_up", "Close tour follow-up",
         "Routing plan, holds, contracts, and responsible contacts",
         "Deadline and follow-up register", 8, 7),
    ),
    "revenue": (
        ("accountant", "statement_sweep", "Reconcile the available statements",
         "Source statements and the periods they cover",
         "Statement discrepancy report with source evidence", 2, 21),
        ("attorney", "ownership_readiness", "Check ownership against revenue",
         "Splits, registrations, agreements, and discrepancy report",
         "Rights gap list requiring documents or counsel", 4, 16),
        ("accountant", "recovery_cases", "Open supported recovery cases",
         "Discrepancy report and ownership evidence",
         "Prioritized recovery queue with evidence and next action", 6, 10),
        ("assistant", "follow_up", "Track recovery follow-up",
         "Recovery queue, contacts, promises, and response deadlines",
         "Closed-loop recovery follow-up report", 8, 5),
    ),
    "rights": (
        ("attorney", "ownership_readiness", "Audit ownership readiness",
         "Contributors, splits, identifiers, samples, and agreements",
         "Rights-readiness checklist with issue owners", 2, 18),
        ("accountant", "statement_sweep", "Cross-check rights against statements",
         "Rights checklist and available royalty statements",
         "Revenue exceptions linked to ownership gaps", 4, 14),
        ("attorney", "deal_risk", "Prepare the deal-risk review",
         "Proposed agreement, commercial terms, and ownership checklist",
         "Deal-risk brief identifying terms for qualified counsel", 6, 8),
        ("assistant", "follow_up", "Control document follow-up",
         "Missing documents, responsible parties, and response dates",
         "Document and signature follow-up register", 8, 4),
    ),
    "creative": (
        ("creative_director", "visual_identity", "Lock the visual direction",
         "Music, audience, positioning, references, and required formats",
         "Visual identity lock and production rules", 2, 18),
        ("marketing", "campaign_architect", "Connect identity to campaign use",
         "Visual identity lock, channel plan, and commercial objective",
         "Asset-use map by channel and campaign moment", 4, 14),
        ("creative_director", "asset_approval", "Build the approval board",
         "Produced assets, required formats, owners, and deadlines",
         "Versioned asset approval register", 6, 8),
        ("assistant", "approval_desk", "Run the final approval desk",
         "Approval register and every asset required for launch",
         "Final approval agenda and missing-deliverable list", 8, 3),
    ),
    "general": (
        ("manager", "brief_to_plan", "Define the operating brief",
         "Objective, success condition, decision deadline, and known constraints",
         "Operating brief with scope and accountable desks", 1, 14),
        ("assistant", "approval_desk", "Build the decision and deadline desk",
         "Operating brief and responsible contacts",
         "Decision agenda with deadlines, blockers, and owners", 3, 9),
        ("manager", "executive_review", "Return the executive decision",
         "Completed specialist work and unresolved decisions",
         "Executive review with recommendation and next move", 7, 2),
    ),
}


def _due_date(today, target_date, default_days, lead_days):
    if target_date:
        try:
            target = date.fromisoformat(target_date)
        except (TypeError, ValueError):
            target = None
        if target is not None:
            return max(today, target - timedelta(days=lead_days)).isoformat()
    return (today + timedelta(days=default_days)).isoformat()


def build_operating_plan(title, success_condition="", target_date="", today=None):
    """Build a proposed cross-desk plan from one owner objective.

    The output is intentionally proposed work. Nothing becomes assigned until
    the owner approves the objective through the Manager desk.
    """
    today = today or date.today()
    objective_type = detect_objective_type(title, success_condition)
    template = _PLAN_TEMPLATES[objective_type]
    items = []
    for sequence, (
            assignee, capability_key, item_title, required_input,
            expected_deliverable, default_days, lead_days) in enumerate(
                template, start=1):
        feature = capability(assignee, capability_key)
        items.append({
            "sequence": sequence,
            "assignee": assignee,
            "capability": capability_key,
            "title": item_title,
            "required_input": required_input,
            "expected_deliverable": expected_deliverable,
            "due_date": _due_date(
                today, target_date, default_days, lead_days),
            "status": "proposed",
            "desk_name": TEAM_BY_KEY[assignee]["name"],
            "feature_name": feature["name"],
        })

    if objective_type != "general":
        sequence = len(items) + 1
        items.append({
            "sequence": sequence,
            "assignee": "manager",
            "capability": "executive_review",
            "title": "Return the executive decision",
            "required_input": "Approved specialist deliverables and unresolved decisions",
            "expected_deliverable": "Executive decision brief with the next approved move",
            "due_date": _due_date(today, target_date, 14, 1),
            "status": "proposed",
            "desk_name": TEAM_BY_KEY["manager"]["name"],
            "feature_name": "Executive Review",
        })

    label = OBJECTIVE_TYPE_LABELS[objective_type]
    return {
        "objective_type": objective_type,
        "summary": (
            f"{label} plan: {len(items)} accountable assignments across "
            f"{len(set(item['assignee'] for item in items))} desks."
        ),
        "items": items,
    }


def validate_team():
    """Return product-definition failures; useful in tests and startup checks."""
    errors = []
    if len(TEAM) != 10:
        errors.append("Company OS must have exactly ten desks.")
    seen_members = set()
    seen_features = set()
    for member in TEAM:
        if member["key"] in seen_members:
            errors.append(f"Duplicate desk key: {member['key']}")
        seen_members.add(member["key"])
        if len(member["capabilities"]) != 2:
            errors.append(f"{member['key']} must have exactly two capabilities.")
        for feature in member["capabilities"]:
            if feature["key"] in seen_features:
                errors.append(f"Duplicate capability key: {feature['key']}")
            seen_features.add(feature["key"])
    if len(seen_features) != 20:
        errors.append("Company OS must have exactly twenty capabilities.")
    return errors


assert not validate_team(), "; ".join(validate_team())
