"""Artist-facing Comparable Artist Watch routes and template context."""

from flask import jsonify, redirect, request, url_for

from . import artist_profile, campaigns, comparable_watch, rbac
from .errors import ValidationError
from .web import bp, bootstrap


def _selected_artist_id(artists):
    requested = (request.args.get("artist_id") or request.form.get("artist_id") or "").strip()
    if requested and any(row["id"] == requested for row in artists):
        return requested
    return artists[0]["id"] if artists else ""


@bp.app_context_processor
def _comparable_watch_template_context():
    """Inject Radar-only watch state without coupling the main web module to it."""
    if request.endpoint != "reach.all_opportunities":
        return {}
    bootstrap()
    principal = rbac.current_principal()
    artists = artist_profile.list_artists(principal.tenant_id)
    artist_id = _selected_artist_id(artists)
    state = comparable_watch.summary(artist_id) if artist_id else {
        "latest": None,
        "previous": None,
        "new": [],
        "all": [],
        "due": True,
        "comparables": [],
        "provider_live": False,
    }
    return {
        "comparable_watch_state": state,
        "comparable_watch_artists": artists,
        "comparable_watch_artist_id": artist_id,
        "comparable_watch_campaigns": campaigns.list_campaigns(principal.tenant_id, limit=25),
    }


@bp.route("/radar/comparable-watch/run", methods=["POST"])
def comparable_watch_run():
    bootstrap()
    artist_id = (request.form.get("artist_id") or "").strip()
    try:
        comparable_watch.run_now(artist_id)
    except ValidationError as exc:
        return redirect(url_for(
            "reach.all_opportunities",
            artist_id=artist_id,
            watch_error=str(exc)[:180],
        ))
    return redirect(url_for("reach.all_opportunities", artist_id=artist_id, watch="complete"))


@bp.route("/radar/comparable-watch/<signal_id>/dismiss", methods=["POST"])
def comparable_watch_dismiss(signal_id):
    bootstrap()
    try:
        comparable_watch.dismiss(signal_id)
    except ValidationError as exc:
        if request.is_json:
            return jsonify({"ok": False, "error": str(exc)}), 404
        return redirect(url_for("reach.all_opportunities", watch_error=str(exc)[:180]))
    if request.is_json:
        return jsonify({"ok": True})
    return redirect(request.referrer or url_for("reach.all_opportunities"))


@bp.route("/radar/comparable-watch/<signal_id>/promote", methods=["POST"])
def comparable_watch_promote(signal_id):
    bootstrap()
    campaign_id = (request.form.get("campaign_id") or "").strip()
    try:
        target_id = comparable_watch.promote(signal_id, campaign_id)
    except ValidationError as exc:
        if request.is_json:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return redirect(url_for("reach.all_opportunities", watch_error=str(exc)[:180]))
    if request.is_json:
        return jsonify({"ok": True, "target_id": target_id})
    return redirect(url_for("reach.all_opportunities", watch="promoted"))
