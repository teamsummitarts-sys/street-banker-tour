"""Artist-facing identity and release-credit routes for REACH.

This module attaches routes to the existing REACH blueprint. It is imported
before that blueprint is registered with Flask, so the public profile screen
lives at /reach/artist-profile without creating a second application surface.
"""

from flask import abort, jsonify, redirect, render_template, request, url_for

from . import artist_profile, catalog, rbac, release_credits
from .errors import ValidationError
from .web import bp, bootstrap, _shell


def _payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict(flat=True)


@bp.app_context_processor
def _release_credit_template_globals():
    """Expose the release-scoped credit helper without coupling web.py to it."""
    return {"reach_featured_artists": release_credits.featured_artists}


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
                "artist_name": saved["artist_name"],
                "known_fields": saved["known_fields"],
                "total_fields": saved["total_fields"],
            })
        return redirect(url_for("reach.artist_profile_page", artist_id=artist_id, saved="1"))

    artists = artist_profile.list_artists(principal.tenant_id)
    create_new = request.args.get("new") == "1"
    selected_id = "" if create_new else (request.args.get("artist_id") or "").strip()
    if selected_id and not any(row["id"] == selected_id for row in artists):
        selected_id = ""
    if not selected_id and artists and not create_new:
        selected_id = artists[0]["id"]

    selected = artist_profile.display(selected_id, principal.tenant_id) if selected_id else None
    if selected:
        release_rows = []
        for row in selected.get("releases", []):
            item = dict(row)
            item["featured_artists"] = release_credits.featured_artists(
                row["id"], principal.tenant_id
            )
            release_rows.append(item)
        selected["releases"] = release_rows

    return render_template(
        "reach/artist_profile.html",
        artists=artists,
        artist_profile=selected,
        creating_new=create_new,
        saved=request.args.get("saved") == "1",
        **_shell(active="artist_profile"),
    )


@bp.route("/recordings/<recording_id>/credits", methods=["GET", "POST"])
def recording_credits(recording_id):
    """Read or replace guest artist billing for one release.

    Primary artist identity is edited in Artist Profile. Featured artists are
    deliberately release-scoped so a guest credit never becomes a default on
    unrelated songs.
    """
    bootstrap()
    principal = rbac.current_principal()
    recording = catalog.get_recording(recording_id)
    if recording is None or recording["tenant_id"] != principal.tenant_id:
        abort(404)
    if recording["is_sample"]:
        return jsonify({"ok": False, "error": "Sample releases cannot be edited"}), 400

    if request.method == "POST":
        values = _payload()
        featured = release_credits.set_featured_artists(
            recording_id, values.get("featured_artists"), principal.tenant_id
        )
    else:
        featured = release_credits.featured_artists(recording_id, principal.tenant_id)

    return jsonify({
        "ok": True,
        "recording_id": recording_id,
        "primary_artist": recording["artist_name"],
        "artist_id": recording["artist_id"],
        "featured_artists": featured,
        "credit_line": release_credits.credit_line(recording["artist_name"], featured),
        "artist_profile_url": url_for("reach.artist_profile_page", artist_id=recording["artist_id"]),
    })
