"""Artist-facing profile routes for REACH.

This module attaches routes to the existing REACH blueprint. It is imported
before that blueprint is registered with Flask, so the public profile screen
lives at /reach/artist-profile without creating a second application surface.
"""

from flask import jsonify, redirect, render_template, request, url_for

from . import artist_profile, rbac
from .errors import ReachError, ValidationError
from .web import bp, bootstrap, _shell


def _payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict(flat=True)


@bp.route("/artist-profile", methods=["GET", "POST"])
def artist_profile_page():
    bootstrap()
    principal = rbac.current_principal()

    if request.method == "POST":
        values = _payload()
        artist_id = (values.get("artist_id") or "").strip()
        if artist_id:
            if artist_profile.get(artist_id, principal.tenant_id) is None:
                error = ValidationError("Unknown artist profile")
                if request.is_json:
                    return jsonify({"ok": False, "error": str(error)}), 404
                raise error
        else:
            artist_id = artist_profile.ensure_artist(
                values.get("artist_name"), principal.tenant_id
            )

        saved = artist_profile.save(artist_id, values, principal.tenant_id)
        if request.is_json:
            return jsonify({
                "ok": True,
                "artist_id": artist_id,
                "known_fields": saved["known_fields"],
                "total_fields": saved["total_fields"],
            })
        return redirect(url_for("reach.artist_profile_page", artist_id=artist_id, saved="1"))

    artists = artist_profile.list_artists(principal.tenant_id)
    selected_id = (request.args.get("artist_id") or "").strip()
    if selected_id and not any(row["id"] == selected_id for row in artists):
        selected_id = ""
    if not selected_id and artists:
        selected_id = artists[0]["id"]

    selected = artist_profile.display(selected_id, principal.tenant_id) if selected_id else None
    return render_template(
        "reach/artist_profile.html",
        artists=artists,
        artist_profile=selected,
        saved=request.args.get("saved") == "1",
        **_shell(active="artist_profile"),
    )
