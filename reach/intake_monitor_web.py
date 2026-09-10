"""Artist-facing Deadline + Intake Monitor routes and context."""

from flask import current_app, jsonify, redirect, request, url_for

from . import intake_monitor, intake_monitor_scheduler
from .errors import ValidationError
from .web import bp, bootstrap


@bp.before_app_request
def _ensure_intake_monitor_scheduler():
    intake_monitor_scheduler.start(current_app._get_current_object())


@bp.app_context_processor
def _intake_monitor_template_context():
    if request.endpoint not in ("reach.all_opportunities", "reach.index"):
        return {}
    bootstrap()
    return {"intake_monitor_state": intake_monitor.summary()}


@bp.route("/radar/intake-monitor/run", methods=["POST"])
def intake_monitor_run():
    bootstrap()
    result = intake_monitor.scan_due(limit=25, force=True)
    if request.is_json:
        return jsonify({"ok": True, **result})
    return redirect(url_for(
        "reach.all_opportunities",
        intake="complete",
        events=result.get("events", 0),
    ))


@bp.route("/radar/intake-monitor/<event_id>/ack", methods=["POST"])
def intake_monitor_ack(event_id):
    bootstrap()
    try:
        intake_monitor.acknowledge(event_id)
    except ValidationError as exc:
        if request.is_json:
            return jsonify({"ok": False, "error": str(exc)}), 404
        return redirect(url_for("reach.all_opportunities", intake_error=str(exc)[:180]))
    if request.is_json:
        return jsonify({"ok": True})
    return redirect(request.referrer or url_for("reach.all_opportunities"))
