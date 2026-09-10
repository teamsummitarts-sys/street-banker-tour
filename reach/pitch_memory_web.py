"""Artist-facing web seam for Pitch Memory."""

from flask import abort, jsonify, render_template

from . import campaigns, drafts, entities, pitch_memory
from .web import bp, _shell


@bp.app_context_processor
def _pitch_memory_helpers():
    return {"pitch_memory_summary": pitch_memory.summary}


def _target_or_404(campaign_id, target_id):
    campaign = campaigns.get(campaign_id)
    target = campaigns.get_target(target_id)
    if campaign is None or target is None or target["campaign_id"] != campaign_id:
        abort(404)
    return campaign, target


@bp.route("/campaigns/<campaign_id>/targets/<target_id>/pitch-memory")
def pitch_memory_page(campaign_id, target_id):
    campaign, target = _target_or_404(campaign_id, target_id)
    draft = drafts.for_target(target_id)
    return render_template(
        "reach/pitch_memory_page.html",
        campaign=campaign,
        target=target,
        outlet=entities.get_outlet(target["outlet_id"]),
        memory=pitch_memory.summary(target_id, draft),
        draft=draft,
        **_shell(campaign_id, "opportunities"),
    )


@bp.route("/campaigns/<campaign_id>/targets/<target_id>/pitch-memory.json")
def pitch_memory_json(campaign_id, target_id):
    _campaign, _target = _target_or_404(campaign_id, target_id)
    draft = drafts.for_target(target_id)
    memory = pitch_memory.summary(target_id, draft)
    return jsonify({
        "ok": True,
        "prior_pitch_count": memory["prior_pitch_count"],
        "days_since_latest": memory["days_since_latest"],
        "warning": memory["warning"],
        "positive_count": memory["positive_count"],
        "declined_count": memory["declined_count"],
        "history": memory["history"],
    })
