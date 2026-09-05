"""Removable, account-gated Noise Lab browser audio and settings surface.

Importing this package does not initialize a database, register a provider or
change a host. The host injects its existing authenticated-user resolver.
There is no server recording or patch-write route. Generation accepts text only.
"""
import os
import secrets

from flask import Blueprint, current_app, g, jsonify, render_template, request, session, url_for

from .generation import (Allowance, GenerationError, GENERATION_VERSION, MODEL,
                         parse_response, request_settings, response_usage, strict_json)


def create_blueprint(current_user):
    """Create an independent module instance; no process-global identity state."""
    bp = Blueprint(
        "noise_lab", __name__, url_prefix="/noise-lab",
        template_folder="templates", static_folder="static", static_url_path="assets",
    )
    allowance = Allowance()

    def enabled(value):
        return value is True or value == '1'

    def configured():
        return enabled(current_app.config.get('NOISE_LAB_AI_ENABLED')) and bool(
            current_app.config.get('OPENAI_API_KEY', '').strip())

    def generation_status():
        return dict(configured=configured(), verified_live=allowance.verified_live,
                    model=MODEL, version=GENERATION_VERSION,
                    usage=allowance.snapshot(g.noise_lab_account),
                    limits_scope='server_process_until_restart',
                    account_limit=20, service_limit=100, cooldown_seconds=10)

    def csrf_token():
        saved = session.get('noise_lab_csrf')
        if not isinstance(saved, dict) or saved.get('account') != g.noise_lab_account:
            saved = {'account': g.noise_lab_account, 'token': secrets.token_urlsafe(32)}
            session['noise_lab_csrf'] = saved
        return saved['token']

    @bp.before_request
    def require_enabled_account():
        value = current_app.config.get("NOISE_LAB_ENABLED", False)
        if value is not True and value != "1":
            return jsonify(error="Noise Lab is not enabled."), 404
        user = current_user()
        if not isinstance(user, dict) or not user.get("id"):
            return jsonify(error="Sign in to your V2 account to open Noise Lab."), 401
        g.noise_lab_account = str(user['id'])

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
            lab_csrf=csrf_token(),
        )

    @bp.get("/capabilities")
    def capabilities():
        return jsonify(
            phase=2, ai_generation=configured(), cloud_patch_storage=False,
            audio_uploads=False, local_audio_processing=True,
            local_recipe_download=True, device_verification="unverified",
            generation=generation_status(),
        )

    @bp.post('/api/generate')
    def generate():
        # Bind CSRF to the authenticated account; never accept identity from JSON.
        saved = session.get('noise_lab_csrf', {})
        token = request.headers.get('X-Noise-Lab-CSRF', '')
        if (not isinstance(saved, dict) or saved.get('account') != g.noise_lab_account
                or not isinstance(saved.get('token'), str) or len(token) > 128 or not token.isascii()
                or not secrets.compare_digest(saved['token'], token)
                or request.headers.get('Sec-Fetch-Site') == 'cross-site'
                or ('Origin' in request.headers and request.headers['Origin'] != request.host_url.rstrip('/'))):
            return jsonify(error='session_check', message='Reload Noise Lab after signing in again.'), 403
        if not request.is_json:
            return jsonify(error='json_required'), 415
        if request.content_length is not None and request.content_length > 4096:
            return jsonify(error='request_too_large'), 413
        raw = request.stream.read(4097)
        if len(raw) > 4096: return jsonify(error='request_too_large'), 413
        try:
            data = strict_json(raw)
            if (type(data) is not dict or set(data) != {'prompt'} or
                    not isinstance(data['prompt'], str) or not 1 <= len(data['prompt'].strip()) <= 500):
                raise ValueError()
            prompt = data['prompt'].strip()
        except (ValueError, GenerationError):
            return jsonify(error='invalid_prompt', message='Enter a description from 1 to 500 characters.'), 400
        if not configured():
            return jsonify(error='unconfigured', message='AI generation is unavailable. Choose a manual preset.'), 503
        try:
            allowance.reserve(g.noise_lab_account)
        except GenerationError as error:
            response = jsonify(error=error.code, generation=generation_status())
            if error.retry_after: response.headers['Retry-After'] = str(error.retry_after)
            return response, error.status
        usage, success, live, failure = None, False, False, None
        try:
            # Test injection is never configurable through requests or environment.
            provider = current_app.config.get('NOISE_LAB_PROVIDER') if current_app.testing else None
            result = provider(prompt) if provider else request_settings(prompt, current_app.config['OPENAI_API_KEY'])
            usage = response_usage(result)
            recipe = parse_response(result)
            success, live = True, provider is None
        except GenerationError as error:
            failure = error
        except Exception:
            # Never return or log the prompt, key, provider response or exception.
            failure = GenerationError('provider_unavailable')
        finally:
            allowance.finish(g.noise_lab_account, success, usage, live)
        if failure:
            return jsonify(error=failure.code, message='No new patch was applied. Try a manual preset.',
                           generation=generation_status()), failure.status
        return jsonify(recipe=recipe, generationVersion=GENERATION_VERSION,
                       generation=generation_status())

    return bp


def init(app, current_user):
    """Register in V2 only; enabling this route is explicit and defaults off."""
    app.config.setdefault("NOISE_LAB_ENABLED", os.environ.get("NOISE_LAB_ENABLED", "0"))
    app.config.setdefault('NOISE_LAB_AI_ENABLED', os.environ.get('NOISE_LAB_AI_ENABLED', '1'))
    app.config.setdefault('OPENAI_API_KEY', os.environ.get('OPENAI_API_KEY', ''))
    app.register_blueprint(create_blueprint(current_user))
