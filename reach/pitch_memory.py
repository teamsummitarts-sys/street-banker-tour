"""Pitch Memory for REACH.

Shows what this account has actually sent to the same outlet before, across
campaigns. It is deliberately read-only: history can warn about repeated
framing, but it never rewrites a pitch or invents a relationship.
"""

import re

from . import campaigns, clock, db, rbac
from .errors import ValidationError

_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "your", "you", "our",
    "are", "was", "were", "have", "has", "had", "but", "not", "one", "into",
    "about", "here", "there", "would", "could", "should", "their", "they", "them",
    "its", "it's", "new", "track", "music", "submission", "consideration",
}


def _owned_target(target_id):
    target = campaigns.get_target(target_id)
    principal = rbac.current_principal()
    if target is None or target["tenant_id"] != principal.tenant_id:
        raise ValidationError("Unknown campaign target")
    return target


def _tokens(subject, body):
    words = {
        word.casefold()
        for word in _WORD_RE.findall(f"{subject or ''} {body or ''}")
        if len(word) >= 3
    }
    return words - _STOP


def similarity(left_subject, left_body, right_subject, right_body):
    """Stable lexical similarity for duplicate-framing warnings."""
    left = _tokens(left_subject, left_body)
    right = _tokens(right_subject, right_body)
    if not left or not right:
        return 0.0
    union = left | right
    return round(len(left & right) / len(union), 3) if union else 0.0


def history_for_target(target_id, limit=8):
    """Prior *sent* pitches to the same outlet/domain, newest first."""
    target = _owned_target(target_id)
    principal = rbac.current_principal()
    outlet_domain = target["outlet_domain"]

    rows = db.query(
        "SELECT d.id AS draft_id, d.subject, d.body, d.language, d.created_at AS drafted_at, "
        "t.id AS target_id, t.campaign_id, c.name AS campaign_name, "
        "r.title AS recording_title, a.name AS artist_name, o.name AS outlet_name, o.domain AS outlet_domain, "
        "(SELECT s.sent_at FROM approval ap JOIN submission s ON s.approval_id = ap.id "
        " WHERE ap.draft_id = d.id AND s.target_id = t.id AND s.sent_at IS NOT NULL "
        " ORDER BY s.sent_at DESC LIMIT 1) AS sent_at, "
        "(SELECT rs.kind FROM response rs JOIN submission sx ON sx.id = rs.submission_id "
        " JOIN approval ax ON ax.id = sx.approval_id WHERE ax.draft_id = d.id "
        " ORDER BY rs.received_at DESC LIMIT 1) AS response_kind, "
        "(SELECT COUNT(*) FROM placement p WHERE p.target_id = t.id) AS placement_count "
        "FROM outreach_draft d "
        "JOIN campaign_target t ON t.id = d.target_id "
        "JOIN campaign c ON c.id = t.campaign_id "
        "JOIN recording r ON r.id = c.recording_id "
        "JOIN artist a ON a.id = r.artist_id "
        "JOIN outlet o ON o.id = t.outlet_id "
        "WHERE d.tenant_id = ? AND t.id != ? "
        "AND (t.outlet_id = ? OR (? IS NOT NULL AND o.domain = ?)) "
        "AND EXISTS (SELECT 1 FROM approval ap2 JOIN submission s2 ON s2.approval_id = ap2.id "
        " WHERE ap2.draft_id = d.id AND s2.target_id = t.id AND s2.sent_at IS NOT NULL) "
        "ORDER BY sent_at DESC, d.created_at DESC LIMIT ?",
        (principal.tenant_id, target_id, target["outlet_id"], outlet_domain, outlet_domain, limit),
    )
    return [dict(row) for row in rows]


def summary(target_id, current_draft=None, limit=8):
    history = history_for_target(target_id, limit=limit)
    current_subject = current_draft["subject"] if current_draft else None
    current_body = current_draft["body"] if current_draft else None

    strongest = None
    if current_draft:
        for row in history:
            score = similarity(current_subject, current_body, row["subject"], row["body"])
            row["similarity"] = score
            if strongest is None or score > strongest["score"]:
                strongest = {"score": score, "item": row}

    warning = None
    if strongest and strongest["score"] >= 0.72:
        warning = {
            "level": "HIGH",
            "score": strongest["score"],
            "text": "This draft is very similar to a pitch previously sent to this outlet.",
            "prior": strongest["item"],
        }
    elif strongest and strongest["score"] >= 0.50:
        warning = {
            "level": "MEDIUM",
            "score": strongest["score"],
            "text": "This draft reuses a substantial amount of prior framing for this outlet.",
            "prior": strongest["item"],
        }

    latest = history[0] if history else None
    days_since = None
    if latest and latest.get("sent_at"):
        days_since = clock.days_since(latest["sent_at"])
        if days_since is not None:
            days_since = max(0, round(days_since))

    positive = [row for row in history if row.get("response_kind") == "ACCEPT" or row.get("placement_count")]
    declined = [row for row in history if row.get("response_kind") == "DECLINE"]
    return {
        "history": history,
        "prior_pitch_count": len(history),
        "latest": latest,
        "days_since_latest": days_since,
        "warning": warning,
        "positive_count": len(positive),
        "declined_count": len(declined),
    }
