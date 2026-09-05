"""Removable, account-gated Noise Lab Phase 1 browser audio surface.

Importing this package does not initialize a database, register a provider or
change a host. The host injects its existing authenticated-user resolver.
There is deliberately no server recording, generation or patch-write route.
"""
import os

from flask import Blueprint, current_app, jsonify, render_template, url_for


def create_blueprint(current_user):
    """Create an independent module instance; no process-global identity state."""
    bp = Blueprint(
        "noise_lab", __name__, url_prefix="/noise-lab",
        template_folder="templates", static_folder="static", static_url_path="assets",
    )

    @bp.before_request
    def require_enabled_account():
        value = current_app.config.get("NOISE_LAB_ENABLED", False)
        if value is not True and value != "1":
            return jsonify(error="Noise Lab is not enabled."), 404
        user = current_user()
        if not isinstance(user, dict) or not user.get("id"):
            return jsonify(error="Sign in to your V2 account to open Noise Lab."), 401

    @bp.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Cookie"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; worker-src 'self'; "
            "style-src 'self'; font-src 'self'; img-src 'self' data:; "
            "media-src 'self' blob:; connect-src 'self'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
        )
        response.headers["Permissions-Policy"] = "microphone=(), camera=(), geolocation=()"
        return response

    @bp.get("/")
    def index():
        return render_template(
            "noise_lab/index.html", return_url="/team",
            lab_assets_url=url_for("noise_lab.static", filename=""),
        )

    @bp.get("/capabilities")
    def capabilities():
        return jsonify(
            phase=1, ai_generation=False, cloud_patch_storage=False,
            audio_uploads=False, local_audio_processing=True,
            local_recipe_download=True, device_verification="unverified",
        )

    return bp


def init(app, current_user):
    """Register in V2 only; enabling this route is explicit and defaults off."""
    app.config.setdefault("NOISE_LAB_ENABLED", os.environ.get("NOISE_LAB_ENABLED", "0"))
    app.register_blueprint(create_blueprint(current_user))
