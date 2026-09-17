import json
import hmac
import math
import os
import re
import time
import urllib.parse
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone

from flask import (Flask, Response, abort, g, jsonify, redirect, render_template,
                   request, session, url_for)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

import db as store
import company_os
import demo_seed
import acr_provider
import documents_engine
import inbox_engine
import board
import lights_store
import operator_desk
import audio_admin
import audio_providers
import audio_studio
import audio_store
import audio_webhooks
import partner_os
import partner_store
# NB: signal_hub, not signal - a module named `signal` in the repo root would
# shadow the standard library module that gunicorn and Werkzeug import.
import signal_hub
import press_desk
import tour_os
import producers
import recovery_engine
import report_builder
import sandbox
import shopify_buy
import since_engine
import tutor
import valuation_engine
from reach.web import bp as reach_bp

# The address this product answers to in anything that outlives the
# request that made it - emails, and the user-agent we identify as to
# third parties.
#
# Everything else builds links from request.url_root, which follows
# whichever host the visitor arrived on. That is right for share links:
# a fan who opened a smart link on one domain should get the same domain
# back. It is wrong for email, because a link in an inbox has no request
# behind it, and because Host is attacker-controlled input - a forged
# Host on a password-reset request would mail a real token pointing at
# somebody else's server.
#
# Render's edge currently refuses unconfigured hosts (a forged Host gets
# a 403 and never reaches this process), so that is not exploitable
# today. This does not depend on that holding.
#
# Set PUBLIC_BASE_URL to this isolated V2 service in every deployed
# environment.  Falling back to the V1 host is more than a bad link: it can
# send password resets, invites, and shared work back into a different
# product.  Development gets an explicit localhost default; deployed boots
# are validated again inside create_app(), after tests/configuration have had
# a chance to set their environment.
_V1_HOSTS = {"street-banker.onrender.com"}


def _resolved_public_base_url():
    app_env = (os.environ.get("APP_ENV") or "development").strip().lower()
    raw = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if not raw:
        if app_env in ("staging", "production"):
            raise RuntimeError(
                "PUBLIC_BASE_URL is required for the deployed V2 service")
        return "http://127.0.0.1:5000"
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RuntimeError("PUBLIC_BASE_URL must be an absolute http(s) URL")
    # A fully-qualified DNS name may legally end in a dot. Canonicalize it
    # before enforcing the hard V1/V2 boundary so an equivalent spelling
    # cannot bypass the service guard.
    host = (parsed.hostname or "").rstrip(".").lower()
    if host in _V1_HOSTS:
        raise RuntimeError("PUBLIC_BASE_URL must not point at the V1 service")
    return raw


PUBLIC_BASE_URL = _resolved_public_base_url()

# The host partner subdomains hang off: foxglove.street-banker.onrender.com
# resolves the partner with slug "foxglove". Set PARTNER_ROOT_DOMAIN on a
# deployment that owns a shorter apex. A partner with its own custom
# domain never touches this - that is matched first, exactly.
_PARTNER_ROOT = (os.environ.get("PARTNER_ROOT_DOMAIN")
                 or PUBLIC_BASE_URL.split("//")[-1].split("/")[0]).strip().lower()


def _signup_mode():
    """Return a known registration mode, failing closed when deployed."""
    app_env = (os.environ.get("APP_ENV") or "development").strip().lower()
    raw = (os.environ.get("SIGNUP_MODE") or "").strip().lower()
    if app_env in ("staging", "production"):
        return raw if raw in ("owner_only", "closed") else "closed"
    if raw in ("open", "owner_only", "closed"):
        return raw
    return "open"


def _private_owner_emails():
    """Return the explicit login allowlist for a closed comparison build.

    The historical source-level owner hashes still grant the product plan in
    development, but they must not silently expand who can enter a private V2
    deployment. Closed mode therefore trusts only the deployment's explicit
    owner settings.
    """
    configured = {
        email.strip().lower()
        for email in (os.environ.get("OWNER_EMAILS") or "").split(",")
        if email.strip()
    }
    bootstrap_email = (os.environ.get("OWNER_BOOTSTRAP_EMAIL") or "").strip().lower()
    if bootstrap_email:
        configured.add(bootstrap_email)
    return configured


def _valid_werkzeug_password_hash(value):
    """Validate the encoded form before a closed deployment can boot.

    Prefix and length checks are insufficient: a malformed value such as
    ``scrypt:xxxxx`` looks secret-like but can never authenticate an owner.
    This accepts the two versioned formats Werkzeug generates for this app
    and bounds their parameters so validation itself stays cheap.
    """
    if not isinstance(value, str) or not 1 <= len(value) <= 512:
        return False
    parts = value.split("$")
    if len(parts) != 3:
        return False
    method, salt, digest = parts
    if (re.fullmatch(r"[A-Za-z0-9]{8,64}", salt) is None
            or re.fullmatch(r"[0-9a-f]+", digest) is None):
        return False
    parameters = method.split(":")
    try:
        if len(parameters) == 4 and parameters[0] == "scrypt":
            n, r, p = (int(value) for value in parameters[1:])
            return (
                16384 <= n <= 1048576
                and n & (n - 1) == 0
                and 1 <= r <= 32
                and 1 <= p <= 16
                and len(digest) == 128
            )
        if len(parameters) == 3 and parameters[0] == "pbkdf2":
            algorithm = parameters[1]
            iterations = int(parameters[2])
            digest_length = {"sha256": 64, "sha512": 128}.get(algorithm)
            return (
                digest_length is not None
                and 100000 <= iterations <= 10000000
                and len(digest) == digest_length
            )
    except (TypeError, ValueError):
        return False
    return False


def _demo_password():
    """Return the configured demo secret, or None when demos are disabled.

    The familiar local ``sweep`` account remains a development fixture for
    the established test suite.  It can never become a deployed credential.
    """
    if _signup_mode() == "closed":
        return None
    app_env = (os.environ.get("APP_ENV") or "development").strip().lower()
    configured = os.environ.get("DEMO_PASSWORD") or ""
    if app_env in ("staging", "production"):
        return configured if len(configured) >= 12 and configured != "sweep" else None
    return configured or "sweep"


def public_url(path=""):
    return PUBLIC_BASE_URL + "/" + path.lstrip("/") if path else PUBLIC_BASE_URL


def _safe_local_redirect(target, default):
    """Return a same-site path or the supplied safe default.

    Login links legitimately carry paths such as ``/team/join/<token>``.  A
    full URL, protocol-relative URL or backslash-containing browser oddity is
    never a valid post-login destination.
    """
    target = (target or "").strip()
    parsed = urllib.parse.urlsplit(target)
    if (not target.startswith("/") or target.startswith("//")
            or parsed.scheme or parsed.netloc or "\\" in target):
        return default
    return target

# Accounts that get the top plan without paying: the owner's own.
#
# Stored as SHA-256, not plaintext, because this repo is on GitHub and an
# email in source is an email in a scraper's list. Add more without a
# deploy by setting OWNER_EMAILS to a comma-separated list.
#
# This grants a PLAN. It is not an authentication bypass - the password
# check still has to pass first, and nothing here touches login, billing
# integrity, or the demo account.
_OWNER_EMAIL_HASHES = {
    "9bc043ae1f94a567c427d016bd0f42293a724c71e59b5b6b6c9ad3bf869e8c30",
    "aa35acb84a0b782e5bdf902478d53127d9fc68f885493cd231fbe98b1f5ad020",
}
OWNER_PLAN = "label"          # top of plans.TIER_RANK


def _is_owner_email(email):
    import hashlib
    email = (email or "").strip().lower()
    if not email:
        return False
    extra = {e.strip().lower()
             for e in (os.environ.get("OWNER_EMAILS") or "").split(",")
             if e.strip()}
    if email in extra:
        return True
    digest = hashlib.sha256(email.encode()).hexdigest()
    return digest in _OWNER_EMAIL_HASHES


def _grant_owner_plan(user):
    """Put an owner account on the top plan. Idempotent, and a no-op for
    everybody else."""
    if not user or not _is_owner_email(user.get("email")):
        return False
    if (user.get("plan") or "") != OWNER_PLAN:
        store.set_user_plan(user["id"], OWNER_PLAN)
        return True
    return False
import touring
import artist_os
import hubs as hub_defs
from statements_engine import (analyze as analyze_statement, parse_statement,
                               build_royalty_summary)

from landing_config import get_landing_config
from artist_eq_config import get_artist_eq_config
from departments_config import get_departments_config
from artist_twin_config import get_artist_twin_config
from lanes_config import get_lanes_config
from creative_config import get_creative_config
from rollout_config import get_rollout_config
from sweep_config import get_sweep_config
from distro_config import get_distro_config
from passport_config import get_passport_config, completeness as passport_completeness
from closing_config import get_closing_config
from release_signal import get_release_signal_config
import capability_status
import blob_store
import stemsplit_provider as stemsplit
import hours_engine
import backup_store
import convert_engine
import audio_readiness
import epk_config
import rollout_learning
import score_history
import firstrun

def _hours_float(value, default=0.0):
    """Form numbers, forgivingly: a blank or a typo becomes the default
    rather than a 500, and nothing negative ever reaches the database."""
    try:
        return max(0.0, float(str(value).strip()))
    except (TypeError, ValueError):
        return default

from catalog_config import get_account, get_catalog_data
from reports_config import get_reports_data
from epk_config import get_epk_data, normalize_epk_overrides
from artwork_config import get_artwork_data, suggest_from_prompt
from links_config import get_links_data, create_smart_link
from sync_config import get_sync_data
from funding_config import get_funding_data
from disputes_config import get_disputes_data, advance_dispute
from audience_config import get_audience_data
from playlists_config import get_playlists_data
from notifications_config import (
    get_notifications_data,
    mark_notification_read,
    mark_all_read,
)
from search_config import search as global_search
from billing_config import get_billing_data
from benchmark_config import get_benchmark_data
from capital_config import get_capital_data
from label_config import get_label_data, get_service, BRAND as LABEL_BRAND
from community_config import (
    get_marketplace_data,
    post_request,
    get_fan_label_data,
    vote_demo,
    get_fan_dashboard_data,
)
from discover_config import get_discover_data, like_track, follow_artist
import music_apis
from music_apis import (itunes_search, odesli_lookup, ordered_platform_links,
                        deezer_track_metadata, musicbrainz_credits, press_mentions)
import links_engine
import links_store as mls
import press_store
import rollout_engine
import rollout_store as ros
import social_providers
import command_center as cc
import qualification
import sync_simulator
import trust_score
import bandsintown_provider as bandsintown
import capital_engine
import stripe_provider as stripe_billing
import royalty_types
import insights_engine
import email_provider as emailer
import spotify_provider as spotify
import artist_twin as twin
import plans
import sb_suite_sso as suite_sso   # Street Banker hands the artist across; this side verifies
from network_config import (
    get_network_data,
    get_profile,
    get_playlist,
    get_moment,
    connect as network_connect_action,
    pitch as network_pitch_action,
    submit_to_playlist,
    enquire_show,
    claim_moment,
)

from royalty_data import (
    add_split,
    advance_claim,
    assess_advance_eligibility,
    complete_registration_step,
    estimate_catalog_value,
    get_action_center,
    get_overview_health,
    get_royalties_overview,
    get_valuation_overview,
    platform_logo_key,
    recent_payout_rows,
    get_recovery_summary,
    generate_report,
    get_catalog_value_tracker,
    get_claims,
    get_dashboard_story,
    get_documents_vault,
    get_earnings_trend,
    get_fixes_queue,
    get_kpis,
    get_missing_royalty_findings,
    get_platform_balances,
    get_platform_catalog,
    get_recent_payouts,
    get_registration_wizard,
    get_rights_conflicts,
    get_royalty_forecast,
    get_royalty_goal,
    get_royalty_leak_alerts,
    get_since_last_login_summary,
    get_smart_recommendations,
    get_song,
    get_songs,
    get_top_royalty_leaks,
    get_payout_calendar,
    get_upcoming_releases,
    WIZARD_TARGETS,
    WIZARD_TARGET_LABELS,
    live_song,
    metadata_completion_score,
    money_left_on_table,
    registration_checklist_score,
    reject_claim,
    remove_split,
    royalty_progress,
    set_connection_status,
    set_fix_status,
    song_check_status,
    song_missing_issues,
    split_total_percentage,
    splits_fully_confirmed,
    toggle_split_confirmed,
    total_royalties,
    upcoming_payout_total,
)


def _account_with_user(account):
    """Overlay the signed-in user's identity on the sidebar account chip.
    Safe outside a request context (tests call this directly)."""
    try:
        user_id = session.get("user_id")
    except RuntimeError:
        return account
    if not user_id:
        return account
    user = store.get_user(user_id)
    if not user:
        return account
    initials = "".join(p[0] for p in user["name"].split()[:2]).upper() or "?"
    # catalog_config.get_account() is mock data. Overlaying only identity
    # used to let its two invented figures through to the sidebar, which
    # base.html renders on every authenticated page: a hardcoded
    # "Next payout: $2,500 in 6 days" and a hardcoded "Pro Plan". Both
    # read as the user's own. The plan is knowable, so use the real one;
    # the payout is not, so send None and let the template omit the line
    # rather than invent a figure.
    plan_key = (user.get("plan") or "artist") if hasattr(user, "get") else "artist"
    return {**account, "name": user["name"], "initials": initials,
            "email": user["email"], "role": "Artist Account",
            "plan": plans.PLAN_NAMES.get(plan_key, "Artist"),
            "next_payout": None, "next_payout_in": None}


def _session_is_demo():
    """Whether the current request belongs to the showcase account.

    build_dashboard_context() feeds roughly sixty renders and takes no
    user argument, so it reads the session itself - the same trick
    _account_with_user already uses. Safe outside a request context;
    tests call these directly.
    """
    try:
        user_id = session.get("user_id")
    except RuntimeError:
        return False
    if not user_id:
        return False
    user = store.get_user(user_id)
    if not user:
        return False
    # _is_demo_email lives inside create_app(), so it is out of scope
    # here. Same rule, stated once more rather than reached for.
    email = (user["email"] or "").strip().lower()
    return (email == "demo@streetbanker.io"
            or (email.startswith("demo-")
                and email.endswith("@streetbanker.io")))


def _internal_tools():
    """Which internal tools this login can actually open.

    Checked against the real rosters, so the sidebar never offers a link
    that would answer 403. Reads the session itself for the same reason
    _session_is_demo does: build_dashboard_context feeds ~60 renders and
    takes no user argument, and current_user() is a closure inside
    create_app that module level cannot see.
    """
    try:
        user_id = session.get("user_id")
    except RuntimeError:                   # outside a request context (tests)
        return []
    if not user_id:
        return []
    user = store.get_user(user_id)
    if not user:
        return []
    email = (user.get("email") or "").strip().lower()
    if not email:
        return []
    owner = _is_owner_email(email)
    out = []
    try:
        import desk_store
        seat = desk_store.get_user_by_email(email)
        if owner or (seat and (seat.get("status") or "active") == "active"):
            out.append({"href": "/operator-desk/", "label": "Operator Desk"})
    except Exception:                      # a missing table must not break every page
        pass
    try:
        import signal_store as _sig
        org = _sig.default_org()
        if owner or _sig.get_member(org["id"], email):
            out.append({"href": "/signal", "label": "Signal"})
    except Exception:
        pass
    # Owner only, and offered even when audio is switched off: a page whose
    # whole job is explaining why a surface is refusing is most useful
    # exactly when it is refusing.
    if owner:
        out.append({"href": "/admin/audio", "label": "Audio Intelligence"})
    return out


def build_dashboard_context():
    # royalty_data's module-level seed data is the showcase's, not the
    # signed-in artist's. Handing it to a real account produced
    # "Total Royalties Collected $23,217.64" on an empty dashboard and a
    # catalogue of five recordings with ISRCs belonging to nobody.
    demo = _session_is_demo()
    balances = get_platform_balances() if demo else []
    payouts = get_recent_payouts()
    kpis = get_kpis()
    total = total_royalties(balances) if demo else 0.0
    goal = get_royalty_goal()
    catalog = get_platform_catalog()

    # Same reasoning: _SONGS is five invented recordings. On /identifiers
    # they rendered as the artist's own catalogue, complete with ISRCs.
    songs = [live_song(s) for s in get_songs()] if demo else []
    songs_summary = [
        {
            "song": s,
            "missing_count": len(song_missing_issues(s)),
            "connected_platform_count": len(s.platform_earnings),
            "splits_confirmed": splits_fully_confirmed(s),
            "split_total": split_total_percentage(s),
        }
        for s in songs
    ]
    payout_calendar = get_payout_calendar()
    claims = get_claims(catalog)
    alerts = get_royalty_leak_alerts(balances, payouts, kpis, catalog)
    smart_recommendations = get_smart_recommendations(alerts, songs)
    missing_findings = get_missing_royalty_findings(catalog)

    earnings_trend = get_earnings_trend()
    catalog_value = estimate_catalog_value(earnings_trend)
    advance_eligibility = assess_advance_eligibility(
        earnings_trend, payout_calendar, catalog_value["mid"], total
    )

    documents_vault = get_documents_vault(songs)
    value_tracker = get_catalog_value_tracker(earnings_trend)

    return {
        # Templates that still carry showcase-only sections check this
        # rather than guessing from whichever seeded value they happen to
        # render.
        "is_showcase": demo,
        # Internal tools (Operator Desk, Signal) are roster-gated and were
        # reachable only by typing the URL. They get a footer group in the
        # sidebar, shown only to people who actually hold a seat - offering
        # everyone a link that answers 403 is worse than no link.
        "internal_tools": _internal_tools(),
        "story": get_dashboard_story(total, missing_findings, catalog_value, smart_recommendations),
        "money_left": money_left_on_table(missing_findings),
        "recovery_summary": get_recovery_summary(catalog, songs, earnings_trend),
        "fixes_queue": get_fixes_queue(catalog, songs, missing_findings),
        "top_leaks": get_top_royalty_leaks(missing_findings),
        "documents_vault": documents_vault,
        "releases": get_upcoming_releases(),
        "forecast": get_royalty_forecast(earnings_trend),
        "value_tracker": value_tracker,
        "since_last_login": get_since_last_login_summary(catalog, songs, value_tracker["pct_change"], catalog_value["mid"]),
        "account": _account_with_user(get_account()),
        "overview_health": get_overview_health(catalog, songs),
        "action_center": get_action_center(alerts, payouts),
        "recent_payout_rows": recent_payout_rows(),
        "royalties_overview": get_royalties_overview(
            balances, catalog, payout_calendar, earnings_trend, recent_payout_rows()
        ),
        "valuation_overview": get_valuation_overview(
            earnings_trend, catalog_value, advance_eligibility, value_tracker
        ),
        "logo_key": platform_logo_key,
        "conflicts": get_rights_conflicts(songs),
        "registration_wizards": [get_registration_wizard(s) for s in songs],
        "wizard_targets": WIZARD_TARGETS,
        "wizard_target_labels": WIZARD_TARGET_LABELS,
        "alerts": alerts,
        "smart_recommendations": smart_recommendations,
        "total": total,
        "goal": goal,
        "progress": royalty_progress(total, goal),
        "earnings_trend": earnings_trend,
        "payouts": payouts,
        "songs_summary": songs_summary,
        "payout_calendar": payout_calendar,
        "upcoming_payout_total": round(upcoming_payout_total(payout_calendar), 2),
        "claims": claims,
        "catalog_value": catalog_value,
        "advance_eligibility": advance_eligibility,
    }


def build_song_detail(song_id):
    song = get_song(song_id)
    if song is None:
        return None
    song = live_song(song)
    payouts = [p for p in get_recent_payouts() if p.song == song.title]
    status = song_check_status(song)
    return {
        "id": song.id,
        "title": song.title,
        "isrc": song.isrc,
        "iswc": song.iswc,
        "upc": song.upc,
        "master_owner": song.master_owner,
        "writers": song.writers,
        "producers": song.producers,
        "publisher": song.publisher,
        "lyrics_on_file": song.lyrics_on_file,
        "alternate_titles": song.alternate_titles,
        "total_earned": round(song.total_earned, 2),
        "streams": song.streams,
        "platform_earnings": song.platform_earnings,
        "splits": [
            {"collaborator": sp.collaborator, "role": sp.role, "percentage": sp.percentage, "confirmed": sp.confirmed}
            for sp in song.splits
        ],
        "split_total": split_total_percentage(song),
        "splits_confirmed": splits_fully_confirmed(song),
        "monthly_trend": song.monthly_trend,
        "check_status": status,
        "missing_issues": song_missing_issues(song),
        "metadata_score": round(metadata_completion_score(song) * 100),
        "registration_score": round(registration_checklist_score(song) * 100),
        "recent_payouts": [
            {"platform": p.platform, "status": p.status, "amount": p.amount} for p in payouts
        ],
    }


def create_app():
    app = Flask(__name__)
    app.register_blueprint(reach_bp)
    # V2 may use a disposable local key during development, but a deployed
    # environment must fail closed instead of silently accepting a known
    # fallback session secret.
    app_env = (os.environ.get("APP_ENV") or "development").strip().lower()
    secret_key = os.environ.get("SECRET_KEY")
    if app_env in ("staging", "production") and not secret_key:
        raise RuntimeError("SECRET_KEY is required in staging and production")
    app.config["SECRET_KEY"] = secret_key or "street-banker-v2-local-development-only"
    @app.get("/healthz")
    def healthz():
        """Public liveness probe for Render and deployment verification."""
        return jsonify({"ok": True, "service": "street-banker-v2"})

    global PUBLIC_BASE_URL, _PARTNER_ROOT
    PUBLIC_BASE_URL = _resolved_public_base_url()
    _PARTNER_ROOT = (os.environ.get("PARTNER_ROOT_DOMAIN")
                     or urllib.parse.urlsplit(PUBLIC_BASE_URL).hostname
                     or "").strip().lower()
    if _signup_mode() == "closed":
        private_owners = _private_owner_emails()
        if len(private_owners) != 1:
            raise RuntimeError(
                "Closed V2 requires exactly one explicitly configured owner email")
        if app_env in ("staging", "production"):
            bootstrap_email = (
                os.environ.get("OWNER_BOOTSTRAP_EMAIL") or ""
            ).strip().lower()
            bootstrap_hash = os.environ.get(
                "OWNER_BOOTSTRAP_PASSWORD_HASH") or ""
            valid_hash = _valid_werkzeug_password_hash(bootstrap_hash)
            if (bootstrap_email not in private_owners or not valid_hash
                    or len(bootstrap_hash) < 50):
                raise RuntimeError(
                    "Closed deployed V2 requires the sole owner bootstrap email "
                    "and a Werkzeug password hash")
    # Session cookie: 31 days when "remember this device" is ticked, and
    # Lax + Secure in production. Without SameSite set explicitly, a
    # browser applies its own default and the cookie can be dropped on a
    # cross-site return - arriving from an email link, say, which is
    # exactly how somebody comes back to a dashboard.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Secure only where the site is actually served over TLS. Render sets
    # RENDER=true; keying off SECRET_KEY instead would silently break
    # local sign-in the moment somebody set a key over http.
    app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("RENDER"))
    # Request-body ceiling. Statements are small CSVs, but TOUR files -
    # riders, tech packs, venue maps, receipt photos - are routinely over
    # 8 MB, and Werkzeug enforces this cap before any handler's own check,
    # so it must be at least tour_os.MAX_UPLOAD (25 MB). Large parts are
    # spooled to disk by the form parser, not held in memory.
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    # Trig helpers for the homepage's analog VU-meter / knob SVGs.
    app.jinja_env.globals.update(cos=math.cos, sin=math.sin, pi=math.pi)
    # The public header reads its links from landing_config. A callable
    # rather than a context processor, so an authenticated page that never
    # renders the header never pays to build the landing config - and so
    # the partial cannot collide with Flask's own `config` in templates
    # that do not pass the landing one.
    app.jinja_env.globals["public_nav"] = lambda: get_landing_config()["nav"]
    # Capability status, resolved against the running deployment. One
    # source of truth for every public surface - see capability_status.py.
    app.jinja_env.globals["cap"] = capability_status.resolve
    # Stored paths come in two shapes - "/uploads/..." on disk and
    # "r2:<key>" in the bucket. Templates print media_url(path) and do
    # not care which; the bucket stays private and the URL expires.
    app.jinja_env.globals["media_url"] = blob_store.url_for
    app.jinja_env.filters["media_url"] = blob_store.url_for

    def _js_json(value):
        """JSON for embedding inside an inline <script>.

        json.dumps does not escape "<", so a user-supplied string containing
        "</script>" would close the tag and everything after it would be
        parsed as HTML - stored XSS on any page that echoes a name the user
        typed. These four escapes are ordinary JSON string escapes, so the
        parsed value is byte-for-byte identical; U+2028/U+2029 are escaped
        too because they are literal line terminators in JavaScript.
        Accepts an object or an already-serialised JSON string. A string
        that is NOT valid JSON is serialised rather than trusted: passing
        one through raw would drop bare text into a <script>, which is the
        exact injection this filter exists to stop. (Found the hard way —
        a bare hex token landed as `x = 691ae30b…;` and took the whole
        inline script down with a syntax error. A name would have been
        worse than a syntax error.)
        """
        if isinstance(value, str):
            try:
                json.loads(value)
                text = value
            except ValueError:
                text = json.dumps(value)
        else:
            text = json.dumps(value)
        return Markup(text.replace("<", "\\u003c").replace(">", "\\u003e")
                          .replace("&", "\\u0026")
                          .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))

    app.jinja_env.filters["js_json"] = _js_json

    store.init_db()
    # Seed showcase accounts only when a valid demo secret exists.  Local
    # development keeps its historical fixture; deployed V2 never falls back
    # to a password published in source.
    _DEMO_ACCOUNTS = [
        ("demo@streetbanker.io", "Synthwave Surfer", "label"),
        ("demo-pro@streetbanker.io", "Synthwave Surfer (Pro)", "pro"),
        ("demo-artist@streetbanker.io", "Synthwave Surfer (Artist)", "artist"),
        ("demo-fan@streetbanker.io", "Demo Fan", "fan"),
    ]
    demo_password = _demo_password()
    for _email, _name, _plan in (_DEMO_ACCOUNTS if demo_password else ()):
        if store.get_user_by_email(_email) is None:
            store.create_user(
                _email, _name, generate_password_hash(demo_password))
        _acct = store.get_user_by_email(_email)
        if (_acct.get("plan") or "artist") != _plan:
            store.set_user_plan(_acct["id"], _plan)
        with store.get_db() as _db:
            _db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                        (generate_password_hash(demo_password), _acct["id"]))
        # Real statements for the non-fan demos, so the showcase runs on
        # the same engines an artist's account does. Idempotent, and it
        # never touches an account that already has rows.
        if _plan != "fan":
            demo_seed.seed_statements(_acct["id"])

    # The comparison service currently runs on disposable storage.  A
    # password *hash* in Render can recreate the single approved owner after
    # a restart without storing plaintext in source or reopening signup.
    # Existing accounts are never overwritten.
    bootstrap_email = (os.environ.get("OWNER_BOOTSTRAP_EMAIL") or "").strip().lower()
    bootstrap_hash = os.environ.get("OWNER_BOOTSTRAP_PASSWORD_HASH") or ""
    if bootstrap_email or bootstrap_hash:
        if (not bootstrap_email or not bootstrap_hash
                or not _is_owner_email(bootstrap_email)):
            raise RuntimeError(
                "Owner bootstrap requires an allowlisted email and password hash")
        if store.get_user_by_email(bootstrap_email) is None:
            store.create_user(
                bootstrap_email,
                (os.environ.get("OWNER_BOOTSTRAP_NAME") or "Street Banker").strip()
                or "Street Banker",
                bootstrap_hash,
            )

    # Owner accounts get the top plan at boot as well as at login, so an
    # existing long-lived session does not have to sign out and back in
    # for it to take effect.
    for _u in store.list_users():
        _grant_owner_plan(_u)

    def current_user():
        user_id = session.get("user_id")
        user = store.get_user(user_id) if user_id else None
        if user is not None and session.get("sb_suite_sso"):
            # Street Banker opened this session (sb_suite_sso): the account
            # of record has already vouched for this person, so the
            # closed-mode owner allowlist, which exists to keep strangers
            # out of a private comparison build, does not apply.
            return user
        if (user is not None and _signup_mode() == "closed"
                and user.get("email", "").strip().lower()
                not in _private_owner_emails()):
            # Access policy is evaluated on every request, not only at login.
            # This invalidates a signed cookie from an older demo or
            # collaborator configuration even when the session secret did not
            # rotate with the deployment.
            session.pop("user_id", None)
            return None
        return user

    @app.route("/auth/street-banker")
    def street_banker_handoff():
        """Arrive from Street Banker already signed in (sb_suite_sso).

        Street Banker is the account of record. It sends a short-lived
        signed token naming the person and the suite they chose; this
        verifies it, finds or creates the matching account here by email,
        and starts the session. Nobody signs in twice and no password ever
        crosses between the services. A token that fails is refused with
        the reason and a way back, never a silent loop.
        """
        accepted = {k.strip() for k in (os.environ.get("SUITE_KEYS") or "tour").split(",") if k.strip()}
        street_banker = (os.environ.get("STREET_BANKER_URL") or "https://app.streetbankermusic.com").rstrip("/")

        def refused(reason, status):
            return render_template("suite_handoff.html", reason=reason,
                                   street_banker=street_banker), status

        if not suite_sso.configured():
            return refused("This suite is not connected to Street Banker sign-in yet.", 503)
        try:
            who = suite_sso.verify(request.args.get("token"), accepted)
        except suite_sso.HandoffRejected as e:
            words = {"expired": "The sign-in link has expired. Open the suite from Street Banker again.",
                     "wrong suite": "That link was for a different suite.",
                     "no token": "This address needs a link from Street Banker."}
            return refused(words.get(e.reason, "The sign-in link could not be verified."), 401)
        user = store.get_user_by_email(who["email"])
        if user is None:
            name = who.get("name") or who["email"].split("@")[0]
            # A local row so this suite's data has an owner. The password is
            # unusable on purpose: sign-in happens at Street Banker.
            user_id = store.create_user(who["email"], name, generate_password_hash(os.urandom(32).hex()))
            user = store.get_user(user_id) if user_id else store.get_user_by_email(who["email"])
        if user is None:
            return refused("The account could not be created here.", 500)
        if who.get("plan") in plans.PLAN_NAMES and (user.get("plan") or "") != who["plan"]:
            store.set_user_plan(user["id"], who["plan"])
        _grant_owner_plan(user)
        session.permanent = True
        session["user_id"] = user["id"]
        session["sb_suite_sso"] = True
        session["sb_suite"] = who["suite"]
        session.pop("seen_rolled", None)
        return redirect(suite_sso.safe_next(request.args.get("next"), suite_sso.suite_home(who["suite"])))

    def login_required_redirect():
        return redirect(url_for("login", next=request.path))

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        error = None
        signup_mode = _signup_mode()
        if signup_mode == "closed" and request.method == "GET":
            return redirect(url_for("login", signup="closed"))
        if request.method == "GET" and request.args.get("ref"):
            session["ref_code"] = request.args.get("ref")[:16]
        if request.method == "POST":
            name = (request.form.get("name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            owner_email = _is_owner_email(email)

            # The private comparison build has one approved owner.  Do not
            # make that owner remember whether Render kept or reset its
            # disposable database: the same form creates a missing account
            # or signs the existing owner in when the password matches.
            if signup_mode == "owner_only" and owner_email and not name:
                name = "Street Banker"

            if not name or "@" not in email or len(password) < 6:
                error = "Please provide a valid email and a password of 6+ characters."
                if signup_mode != "owner_only":
                    error = "Please provide a name, a valid email, and a password of 6+ characters."
            elif signup_mode == "closed":
                return render_template(
                    "signup.html",
                    error="Street Banker V2 registration is closed.",
                    preselect="artist",
                    owner_only=False,
                ), 403
            elif signup_mode == "owner_only" and not owner_email:
                error = "Street Banker V2 registration is owner-only."
            else:
                existing = store.get_user_by_email(email)
                if (existing is not None and signup_mode == "owner_only"
                        and owner_email
                        and check_password_hash(existing["password_hash"], password)):
                    _grant_owner_plan(existing)
                    session["user_id"] = existing["id"]
                    session.pop("seen_rolled", None)
                    return redirect(url_for("team"))
                if existing is not None:
                    error = ("Your owner account already exists. Use the current "
                             "password here or choose Sign in below."
                             if signup_mode == "owner_only" and owner_email
                             else "An account with that email already exists.")
                else:
                    user_id = store.create_user(
                        email, name, generate_password_hash(password))
                    if user_id is None:
                        error = "An account with that email already exists."
                    else:
                        _grant_owner_plan(store.get_user(user_id))
                        ref = session.pop("ref_code", None) or request.form.get("ref")
                        referrer = store.user_by_ref_code(ref) if ref else None
                        if referrer and referrer["id"] != user_id:
                            store.set_referred_by(user_id, referrer["id"])
                            store.notify(referrer["id"], "network", "Referral signed up",
                                         "%s joined from your link. Your $9 credit "
                                         "applies when they start a paid plan." % email,
                                         "/referrals")
                        if request.form.get("account_type") == "fan":
                            store.set_user_plan(user_id, "fan")
                            session["user_id"] = user_id
                            return redirect("/discover")
                        session["user_id"] = user_id
                        return redirect(url_for("team"))
        # /signup?as=fan preselects the fan side. The login page offers a
        # fan account as a distinct choice, and it landed on a form with
        # Artist already ticked - a link that names a destination has to
        # arrive there.
        preselect = "fan" if request.args.get("as") == "fan" else "artist"
        return render_template("signup.html", error=error, preselect=preselect,
                               owner_only=signup_mode == "owner_only")

    @app.route("/demo-open", methods=["POST"])
    def demo_open():
        """Open a demo workspace with the shared demo password.

        Split out of /login so the login page carries exactly one form
        that posts a credential pair. It shared the /login action and the
        email/password field names, which is what stopped browsers
        offering to save a real sign-in on this page - and sometimes had
        them save the demo address instead of the artist's own.
        """
        if _demo_password() is None:
            return redirect("/login?demo=unavailable")
        email = (request.form.get("demo_workspace") or "").strip().lower()
        password = request.form.get("demo_password") or ""
        allowed = {"demo@streetbanker.io", "demo-pro@streetbanker.io",
                   "demo-artist@streetbanker.io", "demo-fan@streetbanker.io"}
        if email not in allowed:
            return redirect("/login")
        user = store.get_user_by_email(email)
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session.pop("seen_rolled", None)
            if (user.get("plan") or "artist") == "fan":
                return redirect("/discover")
            return redirect("/walkthrough")
        return redirect("/login?demo=wrong")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            # Closed V2 is a one-owner comparison environment. Even if an old
            # disposable database still contains a demo or collaborator row,
            # that account cannot authenticate unless its address is in the
            # deployment's explicit owner allowlist.
            login_allowed = (
                _signup_mode() != "closed"
                or email in _private_owner_emails()
            )
            user = store.get_user_by_email(email) if login_allowed else None
            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                # A fresh sign-in is a fresh visit: let the Overview
                # strip roll its window again on the next dashboard view.
                session.pop("seen_rolled", None)
                # The owner does not pay to use their own product. This
                # grants the top plan, nothing more - the password check
                # above still had to pass, and every other protection is
                # untouched.
                _grant_owner_plan(user)
                # "Remember this device": a real 31-day session, only when
                # asked for. Unchecked keeps the browser-session cookie.
                if request.form.get("remember"):
                    session.permanent = True
                is_demo = (email == "demo@streetbanker.io"
                           or email.startswith("demo-") and email.endswith("@streetbanker.io"))
                if (user.get("plan") or "artist") == "fan":
                    default = "/discover"
                elif is_demo:
                    # The demo IS the walkthrough — land partners on the tour.
                    default = "/walkthrough"
                elif _is_owner_email(user.get("email")):
                    default = "/team"
                else:
                    default = "/command-center"
                return redirect(_safe_local_redirect(request.args.get("next"), default))
            error = "Incorrect email or password."
        return render_template(
            "login.html", error=error,
            # Tour-rack state: was demo access just requested, and is this
            # browser already a known lead (cookie set by /demo-access)?
            demo_state=request.args.get("demo"),
            demo_lead=request.cookies.get("sb_demo_lead"),
            demo_available=_demo_password() is not None,
            registration_closed=_signup_mode() == "closed")

    # One lead per IP per half-minute is plenty; this only guards the
    # public capture form against dumb floods, not determined abuse.
    _demo_access_seen = {}

    @app.route("/demo-access", methods=["POST"])
    def demo_access():
        """Demo password is earned, not shown: leave an email, the lead is
        stored in the owner's inbox, and if the mailer is live the password
        goes out automatically. A cookie marks the browser as a known lead
        so the tour rack switches to its password state."""
        if _demo_password() is None:
            return redirect("/login?demo=unavailable#tour-rack")
        # Honeypot: real visitors never see this field.
        if request.form.get("company"):
            return redirect("/login#tour-rack")
        email = (request.form.get("email") or "").strip().lower()
        workspace = (request.form.get("workspace") or "artist").strip().lower()
        if workspace not in ("artist", "pro", "label", "fan"):
            workspace = "artist"
        if not email or "@" not in email or len(email) > 254:
            return redirect("/login?demo=error#tour-rack")
        ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "?")
              .split(",")[0].strip())
        now = time.time()
        if now - _demo_access_seen.get(ip, 0) < 30:
            resp = redirect("/login?demo=pending#tour-rack")
            resp.set_cookie("sb_demo_lead", email, max_age=90 * 24 * 3600,
                            httponly=True, samesite="Lax")
            return resp
        _demo_access_seen[ip] = now

        sent = False
        if emailer.configured():
            try:
                pw = _demo_password()
                emailer.send(
                    email,
                    "Your Street Banker demo access",
                    "<p>Thanks for your interest in Street Banker.</p>"
                    "<p>Your demo password: <strong>%s</strong></p>"
                    "<p>Sign in at <a href='%s/login'>%s/login</a>, pick the "
                    "<strong>%s</strong> workspace in Tour Street Banker, and "
                    "enter the password.</p>"
                    "<p>The demo is illustrative sample data - no account is "
                    "created and nothing is shared.</p>"
                    % (pw, PUBLIC_BASE_URL,
                       PUBLIC_BASE_URL.split("//", 1)[-1], workspace.title()))
                sent = True
            except Exception:
                sent = False
        store.add_inbox("demo-access", {
            "email": email, "workspace": workspace, "password_sent": sent,
            "requested": datetime.now().isoformat(timespec="seconds")})
        resp = redirect("/login?demo=%s#tour-rack" % ("sent" if sent else "pending"))
        resp.set_cookie("sb_demo_lead", email, max_age=90 * 24 * 3600,
                        httponly=True, samesite="Lax")
        return resp

    def _clean_signal_profile(raw):
        """Server-side validation of an Artist Signal Profile.

        Only known priority keys, clamped 0-10; only known module names;
        strings length-capped. Returns the canonical dict or None - raw
        client JSON is never stored or echoed."""
        from artist_eq_config import get_artist_eq_config

        if not isinstance(raw, dict):
            return None
        cfg = get_artist_eq_config()
        keys = [c["key"] for c in cfg["channels"]]
        labels = {c["key"]: c["label"] for c in cfg["channels"]}
        prio_in = raw.get("priorities")
        if not isinstance(prio_in, dict):
            return None
        priorities = {}
        for k in keys:
            try:
                v = int(round(float(prio_in.get(k))))
            except (TypeError, ValueError):
                return None
            priorities[k] = max(0, min(10, v))

        def _s(value, cap):
            return str(value)[:cap] if isinstance(value, str) else ""

        known_lanes = [l["name"] for l in cfg["lanes"]]
        lane = _s(raw.get("recommendedLane"), 64)
        if lane not in known_lanes:
            lane = ""
        known_modules = {name for options in cfg["modules"].values()
                         for name, _slug in options}
        modules = [m for m in (raw.get("recommendedModules") or [])
                   if isinstance(m, str) and m in known_modules][:4]
        actions = [_s(a, 120) for a in (raw.get("firstActions") or [])
                   if isinstance(a, str)][:3]
        top = sorted(keys, key=lambda k: -priorities[k])[:3]
        return {
            "version": 1,
            "createdAt": _s(raw.get("createdAt"), 40),
            "updatedAt": _s(raw.get("updatedAt"), 40),
            "preset": _s(raw.get("preset"), 32) or "Custom Mix",
            "priorities": priorities,
            "topPriorities": [labels[k] for k in top],
            "recommendedLane": lane,
            "recommendedModules": modules,
            "firstActions": actions,
            "source": "homepage_artist_eq",
        }

    @app.route("/api/artist-signal-profile", methods=["GET", "POST"])
    def artist_signal_profile_api():
        """The saved EQ mix, associated with the signed-in account so the
        Command Center and Artist Twin can read it server-side."""
        user = current_user()
        if user is None:
            return jsonify({"error": "auth required"}), 401
        if request.method == "GET":
            return jsonify({"profile": store.get_artist_signal_profile(user["id"])})
        clean = _clean_signal_profile(request.get_json(silent=True))
        if clean is None:
            return jsonify({"error": "invalid profile"}), 400
        store.set_artist_signal_profile(user["id"], clean)
        return jsonify({"ok": True})

    @app.route("/webhooks/resend", methods=["POST"])
    def resend_webhook():
        """Statement drop-box: Resend inbound email -> parsed statements.
        Env-gated; every request is signature-verified."""
        if not emailer.inbound_configured():
            abort(404)
        body = request.get_data()
        if not emailer.verify_webhook(request.headers, body):
            return jsonify({"ok": False, "error": "bad signature"}), 401
        event = request.get_json(silent=True) or {}
        if event.get("type") != "email.received":
            return jsonify({"ok": True, "ignored": True})
        data = event.get("data") or {}
        # The recipient's local part is the account's ingest token.
        user_id = None
        for rcpt in (data.get("to") or []):
            token = str(rcpt).split("@")[0].lower().strip()
            user_id = store.user_by_ingest_token(token)
            if user_id:
                break
        if user_id is None:
            return jsonify({"ok": True, "ignored": True})
        ingested, errors = 0, []
        try:
            attachments = emailer.list_received_attachments(data.get("email_id")
                                                            or data.get("id") or "")
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502
        for att in attachments:
            name = att.get("filename") or "statement.csv"
            if not (name.lower().endswith(".csv")
                    or "csv" in (att.get("content_type") or "")):
                continue
            try:
                content = emailer.download_attachment(att.get("download_url") or "")
            except Exception:
                errors.append(name)
                continue
            err = _ingest_statement(user_id, name, content, via="email")
            if err:
                errors.append("%s: %s" % (name, err))
            else:
                ingested += 1
        if errors and not ingested:
            store.notify(user_id, "statement", "Emailed statement failed to parse",
                         "; ".join(errors)[:300], "/statements")
        return jsonify({"ok": True, "ingested": ingested, "errors": errors})

    def _reset_serializer():
        from itsdangerous import URLSafeTimedSerializer
        return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="pw-reset")

    @app.route("/forgot", methods=["GET", "POST"])
    def forgot_password():
        sent, error = False, None
        if request.method == "POST":
            if not emailer.configured():
                error = ("Password reset email isn't enabled on this server yet. "
                         "Contact the site owner to reset your password.")
            else:
                email = (request.form.get("email") or "").strip().lower()
                reset_allowed = (
                    _signup_mode() != "closed"
                    or email in _private_owner_emails()
                )
                user = (store.get_user_by_email(email)
                        if "@" in email and reset_allowed else None)
                if user:
                    token = _reset_serializer().dumps(user["id"])
                    # Pinned, not request-derived. This is the one link
                    # where trusting the Host header would hand a valid
                    # reset token to whoever set it.
                    link = public_url("/reset/" + token)
                    emailer.send(
                        email, "Reset your Street Banker password",
                        '<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;">'
                        "<h2>Reset your password</h2>"
                        "<p>Someone (hopefully you) asked to reset the password for this "
                        "Street Banker account. The link works for 1 hour.</p>"
                        '<p><a href="%s" style="display:inline-block;background:#E8B950;'
                        'color:#14100A;font-weight:bold;padding:12px 24px;border-radius:10px;'
                        'text-decoration:none;">Choose a new password</a></p>'
                        "<p style=\"color:#91836A;font-size:12px;\">If you didn't ask for this, "
                        "ignore this email — your password is unchanged.</p></div>" % link)
                # Same response either way: never confirm whether an email exists.
                sent = True
        return render_template("forgot.html", sent=sent, error=error)

    @app.route("/reset/<token>", methods=["GET", "POST"])
    def reset_password(token):
        from itsdangerous import BadSignature, SignatureExpired
        try:
            user_id = _reset_serializer().loads(token, max_age=3600)
        except (BadSignature, SignatureExpired):
            return render_template("reset.html", invalid=True, error=None)
        user = store.get_user(user_id)
        if (user is None
                or (_signup_mode() == "closed"
                    and user.get("email", "").lower()
                    not in _private_owner_emails())):
            return render_template("reset.html", invalid=True, error=None)
        error = None
        if request.method == "POST":
            password = request.form.get("password") or ""
            if len(password) < 6:
                error = "Use a password of 6+ characters."
            else:
                store.set_user_password(user_id, generate_password_hash(password))
                session["user_id"] = user_id
                if _signup_mode() == "closed":
                    return redirect("/team")
                return redirect("/command-center" if (user.get("plan") or "artist") != "fan"
                                else "/discover")
        return render_template("reset.html", invalid=False, error=error)

    @app.route("/terms")
    def terms():
        return render_template("legal.html", title="Terms of Service",
                               updated="September 11, 2026", sections=[
            ("The service", "Street Banker provides software tools for independent artists and music teams. The Street Banker product family includes Street Banker, Royalty Sweep, Reach, The Room, and Noise Lab. Features and availability may vary by product, account, plan, and release state. We provide software, not legal, financial, tax, accounting, or collection services."),
            ("Your account", "You're responsible for your account credentials and for the accuracy of the data you upload. You must be 13 or older (16 in the EU) to create an account."),
            ("Your content", "You keep all rights to the music, artwork, statements, and other material you upload. You grant us only the license needed to store, process, and display it back to you and to the people you share it with (public press kits, smart links, sync packs)."),
            ("Fan data", "Fan emails and pre-save data captured through your campaigns belong to your account. You agree to use them lawfully — including honoring the consent language shown at capture and applicable anti-spam law."),
            ("Acceptable use", "No unlawful content, no infringing uploads, no abusing the platform to send spam, and no attempts to breach or overload the service."),
            ("Paid plans", "Paid tiers unlock additional features. Fees, billing cadence, and cancellation terms are shown at checkout. You can cancel anytime; access continues through the paid period."),
            ("Estimates and simulations", "Catalog valuations, recovery estimates, deal simulations, and scores are informational estimates computed from your data. They are not offers, appraisals, or professional advice."),
            ("Termination", "You can request account deletion at any time through Support. We may suspend accounts that violate these terms."),
            ("Support and account requests", "For account access, billing, cancellation, privacy, data-rights, or content requests, contact support@streetbankermusic.com. We may need to verify your account before acting on a request."),
            ("Warranty & liability", "The service is provided as-is. To the maximum extent permitted by law, our liability is limited to the amount you paid us in the 12 months before a claim."),
            ("Changes", "We'll post updates to these terms here and note the date above. Continued use after changes means acceptance."),
        ])

    @app.route("/privacy")
    def privacy():
        return render_template("legal.html", title="Privacy Policy",
                               updated="September 11, 2026", sections=[
            ("What we collect", "Account data (name, email, hashed password), the content you upload (including audio projects, statements, artwork, documents, links, and metadata), campaign analytics (link clicks, referrers), and — when you connect them — data from services you authorize, like Spotify artist stats."),
            # The pre-save sentence is resolved against the running
            # deployment rather than asserted. With Spotify credentials
            # unset the flow falls back to notify-me and no token is ever
            # requested - claiming we encrypt one would be false.
            ("Fan data you capture", "When a fan subscribes on your campaign pages, we store their email with a consent record, on your behalf. Artists control this data; we process it. " + (
                "Where a fan pre-saves, they authorize Spotify directly; that token is encrypted at rest and deleted once the release-day save completes."
                if capability_status.is_live("spotify_presave")
                else "Spotify pre-save is not connected on this deployment: pre-save buttons collect a notify-me address instead, and no Spotify token is requested, stored or processed.")),
            ("What we don't do", "We don't sell personal data. We don't use your uploads to train AI models. We don't read fan tokens for anything beyond the save and the consented email."),
            ("Service providers", "We use Render (hosting), Stripe (payments), Resend (email delivery), and public music APIs (Spotify, Deezer, iTunes, Odesli, MusicBrainz, Bandsintown) to provide features you invoke. Each receives only what's needed for that feature."),
            ("Cookies", "We use a single session cookie to keep you signed in. No advertising trackers."),
            ("Retention & deletion", "Your data stays while your account is active. Request account deletion through Support and we remove your data within 30 days, except records we must keep by law."),
            ("Your rights", "Depending on where you live (GDPR, CCPA), you can request access, correction, export, or deletion of your personal data through Support."),
            ("Security", "Passwords are hashed, fan tokens are encrypted, and data lives on access-controlled infrastructure. No system is perfect; we'll notify affected users of any breach as required by law."),
            ("Contact", "Privacy questions and requests: support@streetbankermusic.com."),
        ])

    @app.route("/support")
    def support():
        return render_template("support.html", title="Support")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.pop("user_id", None)
        session.pop("signed_in", None)
        return redirect(url_for("login"))

    # --- Statements: real CSV ingestion + recovery findings -------------------

    def _ingest_statement(user_id, filename, data, via=""):
        """Parse + save + notify. Returns an error string or None."""
        parsed = parse_statement(data, filename)
        if parsed["error"]:
            return parsed["error"]
        store.save_statement(user_id, filename, parsed["rows"])
        finding = analyze_statement(parsed["rows"])
        tag = (" (via email drop-box)" if via == "email" else "")
        if finding and (finding["unmatched_revenue"] or finding["coverage_gaps"]):
            store.notify(user_id, "recovery",
                         "Recovery findings in %s%s" % (filename, tag),
                         "$%.2f unmatched revenue and %d coverage gap(s) detected."
                         % (finding["unmatched_revenue"], len(finding["coverage_gaps"])),
                         "/recovery")
        else:
            store.notify(user_id, "statement",
                         "Statement processed: %s%s" % (filename, tag),
                         "%d rows parsed, no recovery flags." % len(parsed["rows"]),
                         "/statements")
        return None

    @app.route("/statements/dropbox-test", methods=["POST"])
    def dropbox_test():
        """Round-trip self-test: email a sample CSV to your own drop-box.
        It comes back through Resend's webhook like any distributor email."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        if not emailer.inbound_configured():
            return jsonify({"ok": False, "error": "Drop-box not configured."}), 400
        import base64 as _b64
        addr = emailer.inbound_address(store.get_or_create_ingest_token(user["id"]))
        csv = ("title,source,amount,period,territory\n"
               "Drop-box Test,Street Banker Self-Test,0.01,%s,US\n"
               % date.today().strftime("%Y-%m"))
        sent = emailer.send(addr, "Street Banker drop-box self-test",
                            "<p>Sample statement attached — this email should "
                            "round-trip into your Statements automatically.</p>",
                            attachments=[{"filename": "dropbox-test.csv",
                                          "content": _b64.b64encode(csv.encode()).decode()}])
        return jsonify({"ok": sent, "address": addr,
                        "error": None if sent else "Resend did not accept the email."})

    @app.route("/statements", methods=["GET", "POST"])
    def statements():
        user = current_user()
        if user is None:
            return login_required_redirect()
        error = None
        if request.method == "POST":
            f = request.files.get("statement")
            if f is None or not f.filename:
                error = "Choose a CSV file to upload."
            else:
                error = _ingest_statement(user["id"], f.filename, f.read())
                if error is None:
                    return redirect(url_for("statements"))
        ctx = build_dashboard_context()
        ctx["user"] = user
        ctx["error"] = error
        ctx["drop_box"] = (emailer.inbound_address(
            store.get_or_create_ingest_token(user["id"]))
            if emailer.inbound_configured() else None)
        ctx["uploads"] = store.get_statements(user["id"])
        rows = store.get_statement_rows(user["id"])
        ctx["analysis"] = analyze_statement(
            [{"title": r["title"], "source": r["source"], "amount": r["amount"], "period": r["period"]}
             for r in rows]
        )
        return render_template("statements.html", active_page="statements", **ctx)

    # --- Spotify pre-save OAuth (env-gated; notify-me fallback otherwise) ------

    def _send_release_emails(campaign):
        """Once per campaign, on the first page view after release: email
        every consented fan the listen link. Env-gated on RESEND_API_KEY."""
        if (not emailer.configured() or links_engine.is_prerelease(campaign)
                or (campaign.get("settings") or {}).get("release_email_sent")):
            return
        # Claim the flag before sending so concurrent page views can't double-send.
        settings = dict(campaign.get("settings") or {})
        settings["release_email_sent"] = True
        mls.update_campaign(campaign["id"], campaign["user_id"],
                            {"settings": settings})
        listen_url = request.url_root.rstrip("/") + "/l/" + campaign["slug"]
        html = emailer.release_email_html(
            campaign["title"], campaign.get("artist_name") or "",
            listen_url, campaign.get("cover_url") or "")
        sent = sum(1 for f in mls.campaign_fans(campaign["id"])
                   if emailer.send(f["email"], "%s is out now" % campaign["title"], html))
        if sent:
            store.notify(campaign["user_id"], "fan",
                         "Release emails sent: %s" % campaign["title"],
                         "%d fan%s notified with the listen link." % (sent, "" if sent == 1 else "s"),
                         "/links/%s/analytics" % campaign["id"])

    def _process_due_presaves(campaign):
        """Lazy release-day conversion: whenever a released campaign page is
        hit, complete a small batch of pending pre-saves. No cron needed."""
        _send_release_emails(campaign)
        if not spotify.configured() or links_engine.is_prerelease(campaign):
            return
        dest = next((d for d in mls.get_destinations(campaign["id"])
                     if d["service_key"] == "spotify"), None)
        track_id = spotify.track_id_from_url(dest["url"]) if dest else None
        for p in store.pending_spotify_presaves(campaign["id"]):
            if not track_id:
                store.resolve_spotify_presave(p["id"], "retry", "No Spotify track URL on campaign")
                continue
            try:
                grant = spotify.refresh_access_full(
                    spotify.decrypt_token(p["refresh_token_enc"]))
                access = grant.get("access_token")
                if access and spotify.save_track(access, track_id):
                    store.resolve_spotify_presave(p["id"], "completed")
                    store.notify(campaign["user_id"], "fan",
                                 "Pre-save delivered: %s" % campaign["title"],
                                 "Saved to a fan's Spotify library on release.",
                                 "/links/%s/analytics" % campaign["id"])
                else:
                    store.resolve_spotify_presave(p["id"], "retry", "Save failed")
            except Exception as exc:
                detail = str(exc)
                if hasattr(exc, "read"):
                    try:
                        detail += " " + exc.read().decode("utf-8", "replace")[:120]
                    except Exception:
                        pass
                try:
                    detail += " scope=" + (grant.get("scope") or "none")
                except Exception:
                    pass
                store.resolve_spotify_presave(p["id"], "retry", detail)

    @app.route("/mail/diag")
    def mail_diag():
        """Why aren't emails reaching anyone? Reports the SHAPE of the mail
        setup and, read-only, what Resend says about the account's domains -
        including the exact DNS records each still needs, so nobody has to
        go hunting for them. Requires a signed-in account; no secret ever
        leaves this endpoint."""
        user = current_user()
        if user is None:
            return jsonify({"error": "auth required"}), 401
        info = {
            "configured": emailer.configured(),
            "sender": emailer.sender(),
            "using_shared_test_sender": emailer.using_shared_test_sender(),
            "email_from_set": bool(os.environ.get("EMAIL_FROM")),
            "inbound_domain": os.environ.get("RESEND_INBOUND_DOMAIN", ""),
            "webhook_secret_set": bool(os.environ.get("RESEND_WEBHOOK_SECRET")),
        }
        if emailer.configured() and request.args.get("domains") == "1":
            info["resend"] = emailer.domain_status()
        return jsonify(info)

    def _r2_check():
        """Write, sign, read back and delete one tiny object.

        Presence booleans only prove four variables are set. This is the
        thing that actually fails when a key is wrong, the bucket name is
        misspelled or the account id belongs to a different tenant.
        """
        if not blob_store.configured():
            return {"configured": False, "note": "R2 vars not set; uploads go to disk"}
        key = "_diag/roundtrip-%d.txt" % int(datetime.now(timezone.utc).timestamp())
        payload = b"street-banker r2 round trip"
        result = {"configured": True}
        try:
            result["put"] = bool(blob_store.put(key, payload, "text/plain"))
        except Exception as exc:
            result["put"] = False
            result["put_error"] = type(exc).__name__
            result["put_reason"] = str(getattr(exc, "reason", exc))[:180]
            # S3 puts a machine-readable <Code> in the error body and it
            # names the failure exactly: InvalidAccessKeyId,
            # SignatureDoesNotMatch, NoSuchBucket, AccessDenied. Throwing
            # that away and reporting "Unauthorized" loses the answer.
            body = getattr(exc, "read", None)
            if callable(body):
                try:
                    raw = exc.read().decode("utf-8", "replace")[:600]
                    result["s3_error_body"] = raw
                    code = re.search(r"<Code>([^<]+)</Code>", raw)
                    msg = re.search(r"<Message>([^<]+)</Message>", raw)
                    if code:
                        result["s3_code"] = code.group(1)
                    if msg:
                        result["s3_message"] = msg.group(1)[:200]
                except Exception:
                    pass
            result["why"] = blob_store.diagnose()
            return result
        try:
            got = blob_store.fetch(blob_store.PREFIX + key)
            result["get"] = got == payload
            if got is not None and got != payload:
                result["get_note"] = "read back %d bytes, expected %d" % (len(got), len(payload))
        except Exception as exc:
            result["get"] = False
            result["get_error"] = type(exc).__name__
        try:
            result["delete"] = bool(blob_store.delete(key))
        except Exception as exc:
            result["delete"] = False
            result["delete_error"] = type(exc).__name__
        result["ok"] = bool(result.get("put") and result.get("get") and result.get("delete"))
        return result

    @app.route("/presave/diag")
    def presave_diag():
        # Owner-only config check: reports WHICH credentials the running
        # process can see (presence booleans only, never values).
        user = current_user()
        if user is None or not _is_owner_email(user.get("email")):
            abort(404)
        return jsonify({
            "SPOTIFY_CLIENT_ID": bool(os.environ.get("SPOTIFY_CLIENT_ID")),
            "SPOTIFY_CLIENT_SECRET": bool(os.environ.get("SPOTIFY_CLIENT_SECRET")),
            "SPOTIFY_REDIRECT_URI": bool(os.environ.get("SPOTIFY_REDIRECT_URI")),
            "configured": spotify.configured(),
            "DATABASE_PATH_set": bool(os.environ.get("DATABASE_PATH")),
            "db_path_in_use": store.db_path(),
            "v": 13,
            "presave_states": _presave_states(user["id"]),
            "stripe_activity": _stripe_activity(),
            "STRIPE_SECRET_KEY": bool(os.environ.get("STRIPE_SECRET_KEY")),
            "STRIPE_WEBHOOK_SECRET": bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
            "webhook_secret_stored": bool(store.get_kv("stripe_webhook_secret")),
            "RESEND_WEBHOOK_SECRET": bool(os.environ.get("RESEND_WEBHOOK_SECRET")),
            "RESEND_INBOUND_DOMAIN": os.environ.get("RESEND_INBOUND_DOMAIN", ""),
            "RESEND_API_KEY": bool(os.environ.get("RESEND_API_KEY")),
            "email_configured": emailer.configured(),
            "email_sender": emailer.sender(),
            "var_data_is_real_mount": os.path.ismount("/var/data"),
            "R2_ACCOUNT_ID": bool(os.environ.get("R2_ACCOUNT_ID")),
            "R2_BUCKET": bool(os.environ.get("R2_BUCKET")),
            "R2_ACCESS_KEY_ID": bool(os.environ.get("R2_ACCESS_KEY_ID")),
            "R2_SECRET_ACCESS_KEY": bool(os.environ.get("R2_SECRET_ACCESS_KEY")),
            # Not a secret - it is a public CDN hostname if it is set at all.
            "R2_PUBLIC_BASE_URL": os.environ.get("R2_PUBLIC_BASE_URL", ""),
            "r2_check": _r2_check(),
            "app_token_check": _app_token_check(),
            "search_check": _search_check(),
            "artist_check": _probe("/artists/3TVXtAsR1Inumwj472S9r4"),
            "toptracks_check": _probe(
                "/artists/3TVXtAsR1Inumwj472S9r4/top-tracks?market=US"),
        })

    def _probe(path):
        """Owner-only: raw API attempt, reporting the exact failure."""
        try:
            spotify._api(path, spotify.app_token())
            return "ok"
        except Exception as exc:
            detail = ""
            if hasattr(exc, "read"):
                try:
                    detail = " body=" + exc.read().decode("utf-8", "replace")[:150]
                except Exception:
                    pass
            return "%s: %s%s" % (type(exc).__name__, exc, detail)

    def _presave_states(user_id):
        """Owner-only: status/retries/error per pre-save on own campaigns."""
        out = []
        with store.get_db() as conn:
            rows = conn.execute(
                "SELECT sp.status, sp.retry_count, sp.error, mc.slug "
                "FROM spotify_presaves sp JOIN ml_campaigns mc ON mc.id = sp.campaign_id "
                "WHERE mc.user_id = ? ORDER BY sp.created DESC LIMIT 10",
                (user_id,)).fetchall()
        for r in rows:
            out.append({"slug": r["slug"], "status": r["status"],
                        "retries": r["retry_count"], "error": (r["error"] or "")[:120]})
        return out

    def _stripe_activity():
        """Owner-only: proof the billing webhook fired — counts only."""
        with store.get_db() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM users WHERE stripe_customer_id IS NOT NULL "
                "AND stripe_customer_id != ''").fetchone()
            plans_row = conn.execute(
                "SELECT plan, COUNT(*) AS n FROM users WHERE stripe_customer_id IS NOT NULL "
                "AND stripe_customer_id != '' GROUP BY plan").fetchall()
        return {"customers": row["n"],
                "plans": {r["plan"]: r["n"] for r in plans_row}}

    def _app_token_check():
        """Owner-only: does the client-credentials grant actually work?
        Reports the failure class, never the credentials themselves."""
        try:
            return "ok" if spotify.app_token() else "no token in response"
        except Exception as exc:
            return "%s: %s" % (type(exc).__name__, exc)

    def _search_check():
        """Owner-only: raw /v1/search attempt, reporting the exact failure."""
        try:
            data = spotify._api("/search?q=drake&type=artist&limit=1",
                                spotify.app_token())
            items = (data.get("artists") or {}).get("items", [])
            return "ok: %d items" % len(items)
        except Exception as exc:
            detail = ""
            if hasattr(exc, "read"):
                try:
                    detail = " body=" + exc.read().decode("utf-8", "replace")[:200]
                except Exception:
                    pass
            return "%s: %s%s" % (type(exc).__name__, exc, detail)

    @app.route("/presave/retry-reset", methods=["POST"])
    def presave_retry_reset():
        """Owner tool: re-arm pending/failed pre-saves on own campaigns after
        fixing an external cause (e.g. Spotify allowlist)."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        with store.get_db() as conn:
            cur = conn.execute(
                "UPDATE spotify_presaves SET retry_count = 0, status = 'pending' "
                "WHERE status != 'completed' AND campaign_id IN "
                "(SELECT id FROM ml_campaigns WHERE user_id = ?)", (user["id"],))
        return jsonify({"ok": True, "reset": cur.rowcount})

    @app.route("/presave/<slug>/start")
    def presave_start(slug):
        campaign = mls.get_campaign_by_slug(slug)
        if campaign is None or campaign["status"] != "live" or not spotify.configured():
            return redirect("/l/" + slug)
        nonce = uuid.uuid4().hex
        session["presave_nonce"] = nonce
        return redirect(spotify.auth_url("%s.%s" % (slug, nonce)))

    @app.route("/presave/callback")
    def presave_callback():
        state = request.args.get("state") or ""
        slug = state.split(".")[0] if "." in state else ""
        campaign = mls.get_campaign_by_slug(slug) if slug else None
        if campaign is None or not spotify.configured():
            return redirect("/")
        if state.split(".")[-1] != session.pop("presave_nonce", None):
            return redirect("/l/%s?presave=error" % slug)
        if request.args.get("error") or not request.args.get("code"):
            return redirect("/l/%s?presave=denied" % slug)
        try:
            tokens = spotify.exchange_code(request.args["code"])
            me = spotify.get_me(tokens["access_token"])
        except Exception:
            return redirect("/l/%s?presave=error" % slug)
        email = (me.get("email") or "").lower()
        presave_id = store.add_spotify_presave(
            campaign["id"], me.get("id") or "unknown", email,
            spotify.encrypt_token(tokens.get("refresh_token") or ""))
        if presave_id is None:
            return redirect("/l/%s?presave=already" % slug)
        # The OAuth consent screen covered email sharing; log it into the CRM.
        if email:
            fan_id = mls.upsert_fan(campaign["user_id"], email, campaign["id"],
                                    me.get("display_name") or "")
            mls.add_consent(fan_id, campaign["id"], "spotify_presave",
                            "Authorized Spotify pre-save (library save + email).")
            mls.bump_fan(fan_id, "total_presaves")
            fan = mls.get_fan(fan_id)
            score, level = links_engine.calculate_fan_intent(fan)
            mls.set_fan_intent(fan_id, score, level)
            mls.track(campaign["id"], "presave_notify", fan_id=fan_id)
        else:
            mls.track(campaign["id"], "presave_notify")
        store.notify(campaign["user_id"], "fan",
                     "Spotify pre-save: %s" % (email or me.get("id") or "a fan"),
                     "Via \u201c%s\u201d \u2014 track saves to their library on release day." % campaign["title"],
                     "/links/fans")
        # Already released? Deliver immediately.
        if not links_engine.is_prerelease(campaign):
            _process_due_presaves(campaign)
        return redirect("/l/%s?presave=done" % slug)

    # --- Smart links: real redirects + click tracking --------------------------

    def _ml_variant_id(campaign_id):
        """Resolve ?v= variant slug to an id for event attribution."""
        vslug = (request.args.get("v") or request.form.get("v") or "").strip()
        if not vslug:
            return None
        variant = mls.get_variant_by_slug(vslug)
        return variant["id"] if variant and variant["campaign_id"] == campaign_id else None

    @app.route("/l/<slug>")
    def smart_link_redirect(slug):
        # Street Banker Links campaigns share the /l/ namespace with quick links.
        campaign = mls.get_campaign_by_slug(slug)
        if campaign is not None:
            if campaign.get("archived_at"):
                return render_template("link_campaign_unavailable.html"), 410
            owner_preview = (campaign["status"] != "live"
                             and session.get("user_id") == campaign["user_id"])
            if campaign["status"] != "live" and not owner_preview:
                abort(404)
            variant_id = _ml_variant_id(campaign["id"])
            if not owner_preview:
                mls.track(campaign["id"], "page_view", variant_id=variant_id,
                          referrer=request.referrer,
                          utm_source=request.args.get("utm_source"))
                if request.args.get("src") == "qr":
                    mls.track(campaign["id"], "qr_scan", variant_id=variant_id)
                _process_due_presaves(campaign)
            owner_epk = store.get_epk(campaign["user_id"]) or {}
            return render_template(
                "link_campaign.html", c=campaign,
                store_url=((owner_epk.get("data") or {}).get("store_url") or ""),
                spotify_presave=spotify.configured(),
                presave_state=(request.args.get("presave") or ""),
                destinations=mls.get_destinations(campaign["id"], active_only=True),
                prerelease=links_engine.is_prerelease(campaign),
                status=links_engine.effective_status(campaign),
                variant_slug=(request.args.get("v") or ""),
                owner_preview=owner_preview,
                service_logo=dict((k, l) for k, _, l in links_engine.SERVICES))
        link = store.get_db_link(slug)
        if link is None:
            return redirect(url_for("links"))
        store.log_click(slug)
        meta = link.get("meta")
        if meta and meta.get("links"):
            return render_template("link_landing.html", link=link, meta=meta,
                                   platform_links=ordered_platform_links(meta["links"]))
        return redirect(link["target"])

    @app.route("/l/<slug>/go/<dest_id>")
    def ml_go(slug, dest_id):
        campaign = mls.get_campaign_by_slug(slug)
        dest = mls.get_destination(dest_id)
        if campaign is None or dest is None or dest["campaign_id"] != campaign["id"]:
            abort(404)
        mls.track(campaign["id"], "service_click", variant_id=_ml_variant_id(campaign["id"]),
                  service_key=dest["service_key"], referrer=request.referrer)
        target = dest["url"]
        if not target.startswith(("http://", "https://")):
            abort(400)
        return redirect(target)

    @app.route("/l/<slug>/subscribe", methods=["POST"])
    def ml_subscribe(slug):
        campaign = mls.get_campaign_by_slug(slug)
        if campaign is None or campaign["status"] != "live":
            return jsonify({"ok": False, "error": "This link is not accepting signups."}), 404
        email = (request.form.get("email") or "").strip().lower()
        name = (request.form.get("name") or "").strip()
        if "@" not in email or "." not in email.split("@")[-1]:
            return jsonify({"ok": False, "error": "Enter a valid email address."}), 400
        settings = campaign.get("settings") or {}
        consent_text = settings.get("consent_text") or (
            "I agree to receive updates about this release.")
        prerelease = links_engine.is_prerelease(campaign)
        fan_id = mls.upsert_fan(campaign["user_id"], email, campaign["id"], name)
        consent_type = "presave_notify" if prerelease else "email_marketing"
        mls.add_consent(fan_id, campaign["id"], consent_type, consent_text)
        event = "presave_notify" if prerelease else "email_capture"
        mls.track(campaign["id"], event, variant_id=_ml_variant_id(campaign["id"]),
                  fan_id=fan_id)
        mls.bump_fan(fan_id, "total_presaves" if prerelease else "total_captures")
        fan = mls.get_fan(fan_id)
        score, level = links_engine.calculate_fan_intent(fan)
        mls.set_fan_intent(fan_id, score, level)
        message = ("You're locked in — we'll remind you the moment it drops."
                   if prerelease else "You're on the list. Welcome to the inner circle.")
        store.notify(campaign["user_id"], "fan",
                     "%s: %s" % ("New pre-save" if prerelease else "New fan captured", email),
                     "Via “%s” — consent logged, intent scored." % campaign["title"],
                     "/links/fans")
        # Fan gate: the reward resolves through the owner's own vault listing,
        # and the link is only handed out after a real capture.
        reward = None
        gate_id = settings.get("gate_reward") or ""
        if gate_id:
            v = next((v for v in store.list_vault_files(campaign["user_id"])
                      if v["id"] == gate_id), None)
            if v:
                session["reward_ok_" + campaign["id"]] = v["id"]
                reward = {"url": url_for("ml_reward", slug=slug,
                                          vault_id=v["id"]),
                          "label": settings.get("gate_label")
                          or v["label"] or "Your unlock"}
        return jsonify({"ok": True, "message": message, "reward": reward})

    @app.route("/l/<slug>/reward/<vault_id>")
    def ml_reward(slug, vault_id):
        campaign = mls.get_campaign_by_slug(slug)
        if campaign is None or campaign["status"] != "live":
            abort(404)
        settings = campaign.get("settings") or {}
        if (settings.get("gate_reward") != vault_id
                or session.get("reward_ok_" + campaign["id"]) != vault_id):
            abort(404)
        vault_file = next((v for v in store.list_vault_files(campaign["user_id"])
                           if v["id"] == vault_id), None)
        if vault_file is None:
            abort(404)
        return _serve_asset_path(vault_file["path"], public=False)

    # --- Reports: real CSV download --------------------------------------------

    @app.route("/reports/royalty-report/download.csv")
    def royalty_report_csv():
        import csv as _csv
        import io as _io
        out = _io.StringIO()
        w = _csv.writer(out)
        user = current_user()
        rows = store.get_statement_rows(user["id"]) if user else []
        if rows:
            w.writerow(["Title", "Source", "Amount", "Period"])
            for r in rows:
                w.writerow([r["title"], r["source"], "%.2f" % r["amount"], r["period"]])
        else:
            # No uploaded data yet — export the demo catalog earnings.
            w.writerow(["Title", "Platform", "Earnings"])
            for s in get_songs():
                for platform, amount in (s.platform_earnings or {}).items():
                    w.writerow([s.title, platform, "%.2f" % amount])
        return Response(
            out.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=royalty-report.csv"},
        )

    # --- Inbox: persisted submissions ------------------------------------------

    @app.route("/inbox")
    def inbox():
        user = current_user()
        if user is None:
            return login_required_redirect()
        # Owner accounts also see the rows that belong to no account:
        # demo-access leads, and anything written before inbox rows had
        # an owner at all.
        is_owner = _is_owner_email(user.get("email"))
        rows = store.get_inbox(user["id"], unowned=is_owner)
        ctx = build_dashboard_context()
        ctx["inbox"] = inbox_engine.build(rows)
        ctx["inbox_is_owner"] = is_owner
        return render_template("inbox.html", active_page="inbox", **ctx)

    @app.route("/")
    def index():
        # Homepage content is fully config-driven (landing_config); the
        # command-desk figures are editable there, not injected live.
        config = get_landing_config()

        # A missing image leaves its slot empty rather than 500-ing. The
        # hero now ships a responsive set rather than one src, so it is
        # checked by its widest derivative - if that is missing the whole
        # set is.
        def _has_file(img, key="src"):
            if not img or not img.get(key):
                return False
            rel = img[key].split("/static/", 1)[-1].split("?", 1)[0]
            return os.path.exists(os.path.join(app.static_folder, rel))

        hero_img = config["hero"].get("image") or {}
        widest = "%s-%s.jpg" % (hero_img.get("wide", ""),
                                max(hero_img.get("wide_widths") or [0]))
        if not _has_file({"src": widest}):
            config["hero"] = {**config["hero"], "image": None}

        # The Artist EQ ships its data twice: once as a dict for Jinja to
        # render the plate from, once as JSON for the component script.
        eq = get_artist_eq_config()
        departments = get_departments_config()
        return render_template("landing.html", config=config, artist_eq=eq,
                               artist_eq_json=json.dumps(eq),
                               departments=departments,
                               departments_json=json.dumps(departments),
                               artist_twin=get_artist_twin_config(),
                               lanes=get_lanes_config(),
                               creative=get_creative_config(),
                               rollout=get_rollout_config(),
                               sweep=get_sweep_config(),
                               distro=get_distro_config(),
                               passport=get_passport_config(),
                               completeness=passport_completeness(),
                               closing=get_closing_config(),
                               release_signal=get_release_signal_config())

    def _real_royalty():
        """Real statement analysis for the signed-in user, or None."""
        user = current_user()
        if user is None:
            return None
        rows = store.get_statement_rows(user["id"])
        return build_royalty_summary(rows) if rows else None

    TUTOR_COOKIE = "sb_tutor"

    def _tutor_on():
        return request.cookies.get(TUTOR_COOKIE) == "1"

    def _tutor_panel(user):
        """The full walkthrough, when tutor mode is switched on.

        Same discipline as firstrun below: every flag is a real query, so
        a step is done when the thing exists and comes back if the thing
        is deleted. Steps whose route the plan cannot open are dropped -
        a walkthrough must never point at a locked door.
        """
        if user is None or (user.get("plan") or "") == "fan":
            return None
        if not _tutor_on():
            return None
        uid = user["id"]
        try:
            campaigns = mls.list_campaigns(uid)
            epk = store.get_epk(uid) or {}
            profile_data = epk.get("data") if isinstance(epk, dict) else None
            state = {
                "profile": bool((user.get("name") or "").strip()
                                or (profile_data and profile_data not in ("{}", {}))),
                "track": bool(store.list_os_tracks(uid)),
                "link": bool(campaigns) or bool(store.get_db_links(uid)),
                "rack": bool(store.get_rack_preset(uid)),
                "rate": bool(store.list_hours_rates(uid)),
                "campaign": bool(campaigns),
                "release_date": any((c.get("release_date") or "").strip()
                                    for c in campaigns),
                "publish": any(c.get("status") == "live" for c in campaigns),
                "press_contact": bool(press_store.list_contacts(uid)),
                "announcement": bool(press_store.list_releases(uid)),
                "statement": bool(store.get_statements(uid)),
            }
            plan = user.get("plan") or "artist"
            reachable = set()
            for skey, _n, _p, steps in tutor.STAGES:
                for key, _t, _w, href, _c in steps:
                    if plans.allowed(plan, plans.required_tier(href)):
                        reachable.add(key)
        except Exception:
            # A walkthrough is never worth breaking a page over.
            return None
        return tutor.build(state, reachable)

    @app.route("/tutor/toggle", methods=["POST"])
    def tutor_toggle():
        user = current_user()
        if user is None:
            return login_required_redirect()
        turning_on = request.form.get("on") == "1"
        response = redirect(request.form.get("back") or "/command-center")
        # A year: the choice should outlive the session, in this browser.
        response.set_cookie(TUTOR_COOKIE, "1" if turning_on else "0",
                            max_age=31536000, samesite="Lax",
                            secure=bool(os.environ.get("RENDER")))
        return response

    def _firstrun_panel(user):
        """The start-here checklist, or None once the account outgrows it.

        Every flag is a real query. Nothing here reads a "dismissed
        onboarding" bit: a step is done when the thing exists, so deleting
        the thing brings the step back. It is describing the account, not
        remembering a click.
        """
        if user is None or (user.get("plan") or "") == "fan":
            return None
        uid = user["id"]
        try:
            epk = store.get_epk(uid) or {}
            profile_data = epk.get("data") if isinstance(epk, dict) else None
            has_profile = bool(
                (user.get("name") or "").strip()
                or (profile_data and profile_data not in ("{}", {})))
            state = {
                "profile": has_profile,
                "track": bool(store.list_os_tracks(uid)),
                "link": bool(store.get_db_links(uid)),
                "rack": bool(store.get_rack_preset(uid)),
                "rate": bool(store.list_hours_rates(uid)),
            }
        except Exception:
            # A checklist is never worth breaking a page over.
            return None
        return firstrun.build(state)

    @app.route("/overview")
    def overview():
        # Money Left on the Table used to read from the same hardcoded
        # platform list as /recovery, so every account was told it was
        # owed $3,301.38. Hand the card the account's own scan instead.
        user = current_user()
        # Roll the visit stamp once per session, so the "since your last
        # visit" window does not close behind the reader on a refresh.
        since = None
        if user is not None:
            if not session.get("seen_rolled"):
                store.roll_seen(user["id"])
                session["seen_rolled"] = True
            since = store.get_prev_seen(user["id"])
        # The months this page charts and totals. A template should not be
        # choosing between a real trend and the showcase's hardcoded one -
        # and a {% set %} at the top of a template is invisible inside
        # {% block scripts %}, which is how the chart came to read seed
        # data on an account that had statements of its own.
        rr = _real_royalty()
        showcase = _session_is_demo()
        balances = get_platform_balances() if showcase else []
        return render_template("overview.html", active_page="overview",
                               since_visit=(since_engine.build(user["id"], since)
                                            if user is not None
                                            and not showcase else None),
                               real_royalty=rr,
                               months=(rr["monthly_trend"] if rr
                                       else (get_earnings_trend() if showcase else [])),
                               tracked=(rr["total"] if rr
                                        else (total_royalties(balances) if showcase else 0)),
                               recovery_view=(recovery_engine.build(user["id"])
                                              if user is not None
                                              and not showcase else None),
                               **build_dashboard_context())

    @app.route("/dashboard")
    def dashboard():
        return redirect("/overview")

    @app.route("/royalties")
    def royalties():
        return render_template("royalties.html", active_page="royalties",
                               real_royalty=_real_royalty(),
                               **build_dashboard_context())

    @app.route("/catalog")
    def catalog_page():
        ctx = build_dashboard_context()
        ctx["catalog"] = get_catalog_data()
        user = current_user()
        ctx["catalog_user"] = user
        ctx["my_tracks"] = store.get_catalog_tracks(user["id"]) if user else []
        # Group saved tracks into real releases keyed by UPC (or album title).
        releases = {}
        for t in ctx["my_tracks"]:
            m = t.get("meta") or {}
            key = m.get("upc") or m.get("album") or t.get("album") or t["title"]
            r = releases.setdefault(key, {
                "title": m.get("album") or t.get("album") or t["title"],
                "artist": t["artist"], "art": t["art"],
                "upc": m.get("upc") or "", "label": m.get("label") or "",
                "release_date": m.get("release_date") or "",
                "genre": m.get("genre") or "",
                "total_tracks": m.get("track_count") or 0,
                "saved_tracks": 0, "isrcs": [], "writers": [],
            })
            r["saved_tracks"] += 1
            if m.get("isrc"):
                r["isrcs"].append(m["isrc"])
            for w in m.get("writers") or []:
                if w not in r["writers"]:
                    r["writers"].append(w)
        ctx["my_releases"] = list(releases.values())
        # Aggregate real songwriter/publisher credits across saved tracks.
        writers, pubs = {}, {}
        for t in ctx["my_tracks"]:
            m = t.get("meta") or {}
            for name in m.get("writers") or []:
                writers[name] = writers.get(name, 0) + 1
            for name in m.get("publishers") or []:
                pubs.setdefault(name, {"kind": "Publisher", "songs": 0})["songs"] += 1
            if m.get("label"):
                pubs.setdefault(m["label"], {"kind": "Label", "songs": 0})["songs"] += 1
        ctx["my_writers"] = [{"name": n, "songs": c} for n, c in writers.items()]
        ctx["my_publishers"] = [{"name": n, **v} for n, v in pubs.items()]
        # Real accounts see only their own catalog — the rich sample data is
        # for the demo tour account and signed-out visitors only.
        if user and user["email"] != "demo@streetbanker.io":
            tracks = ctx["my_tracks"]
            n = len(tracks)
            with_isrc = sum(1 for t in tracks if (t.get("meta") or {}).get("isrc"))
            with_meta = sum(1 for t in tracks if t.get("meta"))
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            releases_n = len(ctx["my_releases"])
            c = ctx["catalog"]
            c["summary"] = {
                "total_tracks": n,
                "tracks_added_this_month": sum(1 for t in tracks if (t.get("added") or "").startswith(month)),
                "total_releases": releases_n, "releases_added_this_month": 0,
                "registered_tracks": with_isrc, "unregistered_tracks": n - with_isrc,
                "total_isrcs": with_isrc,
                "isrc_assignment_rate": round(100 * with_isrc / n, 1) if n else 0,
            }
            c["registered_pct"] = round(100 * with_isrc / n) if n else 0
            c["unregistered_pct"] = 100 - c["registered_pct"] if n else 0
            meta_pct = round(100 * with_meta / n) if n else 0
            isrc_pct = round(100 * with_isrc / n) if n else 0
            c["health"] = {
                "total": round((meta_pct + isrc_pct) / 2),
                "status": "Good" if isrc_pct >= 80 else ("Fair" if n else "Empty"),
                "bars": [{"label": "Metadata", "pct": meta_pct},
                         {"label": "ISRCs", "pct": isrc_pct}],
            }
            missing = n - with_isrc
            c["issues"] = ([{"id": "real_isrc", "title": "Missing ISRCs", "count": missing,
                             "severity": "critical", "filter_tab": "Tracks",
                             "filter_status": "Missing ISRC"}] if missing else [])
            c["catalog_value"] = {"estimated_value": 0, "monthly_change": 0,
                                  "trend": [{"month": m, "value": 0}
                                            for m in ("Jan", "Feb", "Mar", "Apr", "May")]}
            c["tracks"], c["releases"], c["songwriters"] = [], [], []
            c["publishers"], c["splits"] = [], []
            c["recently_added"] = [{"id": t["id"], "title": t["title"], "type": "Single",
                                    "date_added": (t.get("added") or "")[:10],
                                    "status": "Registered" if (t.get("meta") or {}).get("isrc") else "Pending"}
                                   for t in tracks[:5]]
        return render_template("catalog.html", active_page="catalog", **ctx)

    @app.route("/catalog/add", methods=["POST"])
    def catalog_add():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "sign_in"}), 401
        track = request.get_json(silent=True) or {}
        if not (track.get("title") or "").strip():
            return jsonify({"ok": False, "error": "A track title is required."}), 400
        track_id = store.add_catalog_track(user["id"], track)
        if track_id is None:
            return jsonify({"ok": False, "error": "Already in your catalog."}), 409
        # Best-effort metadata enrichment: ISRC/UPC/label from Deezer.
        # The track stays saved even when the lookup finds nothing.
        meta = deezer_track_metadata(track.get("title"), track.get("artist"))
        if meta:
            # Second hop: the ISRC unlocks songwriter/publisher credits.
            credits = musicbrainz_credits(meta.get("isrc"))
            if credits:
                meta.update(credits)
            store.set_catalog_track_meta(user["id"], track_id, meta)
        return jsonify({"ok": True, "id": track_id, "meta": meta})

    @app.route("/catalog/remove/<track_id>", methods=["POST"])
    def catalog_remove(track_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "sign_in"}), 401
        return jsonify({"ok": store.remove_catalog_track(user["id"], track_id)})

    @app.route("/connections")
    def connections():
        user = current_user()
        if user is None:
            return login_required_redirect()
        pulse_profile = store.get_pulse_profile(user["id"])
        statements = store.get_statements(user["id"])
        integrations = [
            {"name": "Spotify", "kind": "Live API",
             "on": spotify.pulse_configured(),
             "detail": ("Powers Artist Pulse, real pre-saves, and artist search."
                        if spotify.pulse_configured() else
                        "Server credentials not configured."),
             "action": ("/pulse", "Open Artist Pulse")},
            {"name": "Your Spotify profile", "kind": "Artist link",
             "on": bool(pulse_profile),
             "detail": ("Linked: %s — followers and popularity track daily."
                        % pulse_profile["artist_name"]) if pulse_profile
             else "Pick your artist on Artist Pulse to start tracking.",
             "action": ("/pulse", "Link on Artist Pulse")},
            {"name": "Deezer", "kind": "Public API",
             "on": True,
             "detail": "Fan counts and track identifiers — no key needed.",
             "action": ("/pulse", "See fan count")},
            {"name": "Email (Resend)", "kind": "Delivery",
             "on": emailer.configured(),
             "detail": ("Release-day fan emails, team invites, and password "
                        "resets send from %s." % emailer.sender())
             if emailer.configured() else "RESEND_API_KEY not set on the server.",
             "action": ("/links", "Campaigns that use it")},
            {"name": "Bandsintown", "kind": "Events API",
             "on": bandsintown.configured(),
             "detail": ("Tour dates flow onto your public EPK automatically."
                        if bandsintown.configured() else
                        "Awaiting app_id from Bandsintown support — tour dates "
                        "light up on the EPK the day it arrives."),
             "action": ("/epk", "EPK tour section")},
            {"name": "Royalty statements", "kind": "Your uploads",
             "on": bool(statements),
             "detail": ("%d statement%s uploaded — powering Royalties, Recovery, "
                        "Tax, and Capital." % (len(statements),
                                               "" if len(statements) == 1 else "s"))
             if statements else "Upload CSVs — they power the entire money engine.",
             "action": ("/statements", "Upload statements")},
            {"name": "iTunes / Odesli / MusicBrainz", "kind": "Public APIs",
             "on": True,
             "detail": "Catalog search, universal links, credits — no keys needed.",
             "action": ("/catalog", "Search the catalog")},
        ]
        # Not honest to pretend these connect today.
        unavailable = [
            ("Distributor analytics (DistroKid, TuneCore, CD Baby)",
             "Per-track stream counts and listener data need distributor feeds — no public API exists yet."),
            ("PRO / MLC registrations (ASCAP, BMI, MLC)",
             "Registration status requires society data access."),
        ]
        return render_template("connections.html", active_page="connections",
                               integrations=integrations, unavailable=unavailable,
                               **build_dashboard_context())

    @app.route("/recovery")
    def recovery():
        # One page for every account, including the showcase - the demo
        # has real statements now, so it is scanned by the same engine
        # rather than shown a hardcoded copy of what a scan looks like.
        user = current_user()
        return render_template(
            "recovery.html", active_page="recovery",
            recovery_view=recovery_engine.build(user["id"]) if user else None,
            **build_dashboard_context())

    @app.route("/valuation")
    def valuation():
        user = current_user()
        # The valuation is recorded by the Command Center, which computes
        # it from the same statements. Read it back here rather than
        # recompute, so both pages agree on what today's number was.
        trend = (score_history.summarise(
            "valuation", store.score_trend(user["id"], "valuation"))
            if user else None)
        return render_template(
            "valuation.html", active_page="valuation",
            valuation_view=valuation_engine.build(user["id"]) if user else None,
            trend=trend, **build_dashboard_context())

    @app.route("/reports")
    def reports():
        ctx = build_dashboard_context()
        ctx["reports_user"] = current_user()
        ctx["reports_data"] = get_reports_data(
            demo=_is_demo_email((ctx["reports_user"] or {}).get("email") or ""))
        return render_template("reports.html", active_page="reports", **ctx)

    @app.route("/reports/campaigns.csv")
    def report_campaigns_csv():
        user = current_user()
        if user is None:
            return login_required_redirect()
        import csv as _csv
        import io as _io
        out = _io.StringIO()
        w = _csv.writer(out)
        w.writerow(["Campaign", "Artist", "Status", "Release Date", "SB Score",
                    "Visits", "Service Clicks", "CTR %", "Pre-saves",
                    "Email Captures", "QR Scans", "Public URL"])
        for c in mls.list_campaigns(user["id"]):
            counts = mls.event_counts(c["id"])
            visits = counts.get("page_view", 0)
            clicks = counts.get("service_click", 0)
            score = links_engine.calculate_street_banker_score(
                c, mls.get_destinations(c["id"]))
            w.writerow([c["title"], c["artist_name"],
                        links_engine.effective_status(c), c["release_date"],
                        score["total"], visits, clicks,
                        round(100 * clicks / visits, 1) if visits else 0,
                        counts.get("presave_notify", 0),
                        counts.get("email_capture", 0), counts.get("qr_scan", 0),
                        request.host_url.rstrip("/") + "/l/" + c["slug"]])
        return Response(out.getvalue(), mimetype="text/csv", headers={
            "Content-Disposition": "attachment; filename=street-banker-campaigns.csv"})

    @app.route("/reports/recovery.csv")
    def report_recovery_csv():
        user = current_user()
        if user is None:
            return login_required_redirect()
        import csv as _csv
        import io as _io
        summary = build_royalty_summary(store.get_statement_rows(user["id"]))
        out = _io.StringIO()
        w = _csv.writer(out)
        w.writerow(["Finding", "Track", "Detail", "Amount / Estimate", "Type"])
        if summary:
            if summary["unmatched_revenue"]:
                w.writerow(["Unmatched revenue", "(rows with no title)",
                            "Money paid but not attributed — request corrected metadata",
                            summary["unmatched_revenue"], "Actual"])
            for g in summary["coverage_gaps"]:
                w.writerow(["Coverage gap", g["title"],
                            "Missing from: " + ", ".join(g["missing_sources"]),
                            g["estimated_value"], "Estimate"])
        return Response(out.getvalue(), mimetype="text/csv", headers={
            "Content-Disposition": "attachment; filename=street-banker-recovery-findings.csv"})

    @app.route("/reports/executive")
    def report_executive():
        user = current_user()
        if user is None:
            return login_required_redirect()
        campaigns = []
        for c in mls.list_campaigns(user["id"]):
            counts = mls.event_counts(c["id"])
            campaigns.append({**c, "visits": counts.get("page_view", 0),
                              "clicks": counts.get("service_click", 0),
                              "fans": counts.get("email_capture", 0)
                                      + counts.get("presave_notify", 0),
                              "eff_status": links_engine.effective_status(c)})
        campaigns.sort(key=lambda c: c["visits"], reverse=True)
        return render_template(
            "report_executive.html",
            user=user, summary=cc.get_summary(user["id"]),
            q=qualification.calculate(user["id"]),
            rr=build_royalty_summary(store.get_statement_rows(user["id"])),
            campaigns=campaigns,
            fans=mls.list_fans(user["id"]),
            today=datetime.now(timezone.utc).strftime("%B %d, %Y"))

    UPLOADS_DIR = os.path.join(os.path.dirname(store.db_path()), "uploads")
    try:
        os.makedirs(UPLOADS_DIR, exist_ok=True)
    except OSError:
        # DATABASE_PATH points at an unmounted disk — degrade to the local
        # instance dir (ephemeral) instead of crashing the deploy.
        UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "instance", "uploads")
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        print("WARNING: uploads dir unusable; falling back to", UPLOADS_DIR)

    def _asset_registry_enforced():
        env = (os.environ.get("APP_ENV") or "development").strip().lower()
        return (env in ("staging", "production")
                or os.environ.get("ENFORCE_ASSET_VISIBILITY") == "1")

    def _serve_asset_path(path, public=False):
        """Serve a path after its owning route has made the access decision."""
        if blob_store.is_remote(path):
            if not blob_store.configured():
                abort(404)
            target = (blob_store.url_for(path, ttl=300) if public
                      else blob_store.presigned_get(blob_store.key_of(path), ttl=300))
            return redirect(target)
        if not path or not path.startswith("/uploads/"):
            abort(404)
        from flask import send_from_directory
        return send_from_directory(UPLOADS_DIR, path[len("/uploads/"):])

    def _asset_url(path):
        asset = store.get_stored_asset(path) if path else None
        if asset and asset["visibility"] == "private":
            return url_for("stored_asset_media", asset_id=asset["id"])
        return blob_store.url_for(path)

    # Templates no longer expose the raw storage path for a registered private
    # upload. Public artwork keeps the existing URL shape for compatibility.
    app.jinja_env.globals["media_url"] = _asset_url
    app.jinja_env.filters["media_url"] = _asset_url

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        path = "/uploads/" + filename
        asset = store.get_stored_asset(path)
        if asset is None:
            if _asset_registry_enforced():
                abort(404)
            return _serve_asset_path(path, public=True)
        user = current_user()
        if (asset["visibility"] != "public"
                and (user is None or user["id"] != asset["user_id"])):
            abort(404)
        return _serve_asset_path(path, public=asset["visibility"] == "public")

    @app.route("/media/<asset_id>")
    def stored_asset_media(asset_id):
        asset = store.get_stored_asset_by_id(asset_id)
        if asset is None:
            abort(404)
        user = current_user()
        if (asset["visibility"] != "public"
                and (user is None or user["id"] != asset["user_id"])):
            abort(404)
        return _serve_asset_path(asset["path"],
                                 public=asset["visibility"] == "public")

    def _slugify(name):
        s = "".join(c if c.isalnum() else "-" for c in (name or "").lower())
        return "-".join(p for p in s.split("-") if p) or "artist"

    def _ensure_epk_slug(user):
        saved = store.get_epk(user["id"])
        if saved and saved.get("slug"):
            return saved["slug"]
        slug = _slugify(user["name"])
        while store.get_epk_by_slug(slug) is not None:
            slug = "%s-%s" % (_slugify(user["name"]), uuid.uuid4().hex[:4])
        store.set_epk_slug(user["id"], slug)
        return slug

    _EPK_ASSET_KINDS = [("press_photo", "Press Photo"), ("logo", "Logo"),
                        ("cover_art", "Cover Art"), ("live_photo", "Live Photo")]
    _EPK_KIND_LABELS = dict(_EPK_ASSET_KINDS)

    def _labeled_assets(assets):
        return [{**a, "label": _EPK_KIND_LABELS.get(a["kind"], a["kind"])}
                for a in assets if a["kind"] in _EPK_KIND_LABELS]

    @app.route("/epk")
    def epk():
        ctx = build_dashboard_context()
        user = current_user()
        overrides, photo, assets = None, None, []
        if user:
            saved = store.get_epk(user["id"])
            if saved:
                overrides, photo = saved["data"], saved["photo"]
            assets = _labeled_assets(store.get_epk_assets(user["id"]))
            ctx["epk_public_url"] = "/epk/" + _ensure_epk_slug(user)
        ctx["user"] = user
        ctx["asset_kinds"] = _EPK_ASSET_KINDS
        ctx["bandsintown_configured"] = bandsintown.configured()
        share = store.get_epk_share(user["id"]) if user else None
        ctx["pitch_share"] = share
        ctx["pitch_stats"] = (store.epk_share_stats(share["token"])
                              if share else {"views": 0, "plays": [],
                                             "last_view": ""})
        vault = store.list_vault_files(user["id"]) if user else []
        ctx["vault_audio"] = [v for v in vault
                              if v["path"].rsplit(".", 1)[-1].lower()
                              in ("wav", "mp3", "flac")]
        ctx["vault_images"] = [v for v in vault
                               if v["path"].rsplit(".", 1)[-1].lower()
                               in ("png", "jpg", "jpeg", "webp")]
        tour = bandsintown.upcoming_events((overrides or {}).get("bandsintown_artist"))
        ctx["epk"] = get_epk_data(ctx["account"], ctx["catalog_value"],
                                  overrides=overrides, photo=photo, assets=assets,
                                  tour_dates=tour,
                                  demo=_is_demo_email(user["email"]))
        return render_template("epk.html", active_page="epk", **ctx)

    @app.route("/epk/press/search")
    def epk_press_search():
        if current_user() is None:
            return jsonify({"ok": False, "results": []}), 401
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify({"ok": False, "results": []})
        return jsonify({"ok": True, "results": press_mentions(q)})

    @app.route("/epk/asset/<kind>", methods=["POST"])
    def epk_asset_upload(kind):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in to upload assets."}), 401
        if kind not in _EPK_KIND_LABELS:
            return jsonify({"ok": False, "error": "Unknown asset type."}), 400
        f = request.files.get("asset")
        if f is None or not f.filename:
            return jsonify({"ok": False, "error": "Choose an image file."}), 400
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in ("png", "jpg", "jpeg", "webp"):
            return jsonify({"ok": False, "error": "Use a PNG, JPG, or WebP image."}), 400
        fname = "epkasset_%s_%s.%s" % (user["id"], kind, ext)
        f.save(os.path.join(UPLOADS_DIR, fname))
        path = "/uploads/" + fname
        store.save_epk_asset(user["id"], kind, path)
        store.register_stored_asset(user["id"], path, "public", "epk_asset")
        return jsonify({"ok": True, "path": path})

    @app.route("/epk/asset/<kind>/visibility", methods=["POST"])
    def epk_asset_visibility(kind):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        public = bool((request.get_json(silent=True) or {}).get("public"))
        ok = store.set_epk_asset_public(user["id"], kind, public)
        asset = next((a for a in store.get_epk_assets(user["id"])
                      if a["kind"] == kind), None)
        if ok and asset:
            store.register_stored_asset(
                user["id"], asset["path"], "public" if public else "private",
                "epk_asset")
        return jsonify({"ok": ok})

    def _epk_real_stats(user_id):
        """Headline figures for a press kit, from the artist's own data.

        Returns [] when there is nothing real to show, and the press kit
        then renders no stats at all - which is the honest answer for an
        empty account, and better than borrowing the demo catalogue's
        numbers on a page that goes to a label.
        """
        try:
            return epk_config.real_stats(
                store.get_statement_rows(user_id),
                len(store.get_catalog_tracks(user_id) or []))
        except Exception:
            return []

    @app.route("/epk/<slug>")
    def epk_public(slug):
        prof = store.get_epk_by_slug(slug)
        if prof is None:
            abort(404)
        ctx = build_dashboard_context()
        name = prof["user_name"]
        initials = "".join(w[0] for w in name.split()[:2]).upper() or "SB"
        assets = _labeled_assets(store.get_epk_assets(prof["user_id"], public_only=True))
        tour = bandsintown.upcoming_events(prof["data"].get("bandsintown_artist"))
        real = _epk_real_stats(prof["user_id"])
        data = get_epk_data({"name": name, "initials": initials},
                            ctx["catalog_value"],
                            overrides=prof["data"], photo=prof["photo"],
                            assets=assets, tour_dates=tour,
                            # Whose kit this is decides whose defaults
                            # apply - a real artist's public EPK must
                            # never fall back to the showcase identity.
                            demo=_is_demo_email(
                                (store.get_user(prof["user_id"]) or {})
                                .get("email") or ""),
                            # None, not [] - an empty list would override
                            # the demo stats with nothing and delete the
                            # section. With no real figures the demo ones
                            # stay, and the page says outright that they
                            # are samples.
                            stats_override=(real or None))
        return render_template("epk_public.html", e=data, slug=slug)

    @app.route("/epk/share", methods=["POST"])
    def epk_share_save():
        """Private pitch link settings — audio resolves through the artist's
        own vault listing, same rule as every other share surface."""
        user = current_user()
        if user is None:
            return login_required_redirect()
        action = request.form.get("action") or "save"
        if action == "disable":
            store.delete_epk_share(user["id"])
            return redirect("/epk")
        share = store.get_epk_share(user["id"])
        token = (uuid.uuid4().hex[:20]
                 if (share is None or action == "regenerate")
                 else share["token"])
        pin = "".join(ch for ch in (request.form.get("pin") or "")
                      if ch.isdigit())[:8]
        if pin and len(pin) < 4:
            pin = ""
        expires = (request.form.get("expires") or "").strip()[:10]
        vault = {v["id"]: v for v in store.list_vault_files(user["id"])}
        audio = []
        for vid in request.form.getlist("audio")[:3]:
            v = vault.get(vid)
            if v and v["path"].rsplit(".", 1)[-1].lower() in ("wav", "mp3",
                                                              "flac"):
                audio.append({"path": v["path"],
                              "label": v["label"] or "Untitled"})
        store.upsert_epk_share(user["id"], token, pin, expires, audio)
        return redirect("/epk")

    @app.route("/pitch/<token>", methods=["GET", "POST"])
    def epk_pitch(token):
        share = store.get_epk_share_by_token(token)
        if share is None:
            abort(404)
        today = datetime.now(timezone.utc).date().isoformat()
        if share["expires"] and today > share["expires"]:
            return render_template("link_campaign_unavailable.html"), 410
        pin_key = "pitch_ok_" + token
        prof = store.get_epk(share["user_id"])
        owner = store.get_user(share["user_id"])
        if share["pin"] and not session.get(pin_key):
            if request.method == "POST":
                if (request.form.get("pin") or "").strip() == share["pin"]:
                    session[pin_key] = True
                    return redirect("/pitch/" + token)
                return render_template("sheet_public.html", mode="pin",
                                       token=token, bad_pin=True,
                                       gate_title="Private Press Kit",
                                       artist=(owner or {}).get("name", "")), 403
            return render_template("sheet_public.html", mode="pin",
                                   token=token, bad_pin=False,
                                   gate_title="Private Press Kit",
                                   artist=(owner or {}).get("name", ""))
        slug = (prof or {}).get("slug") or _ensure_epk_slug(owner)
        ctx = build_dashboard_context()
        name = (owner or {}).get("name", "Artist")
        initials = "".join(w[0] for w in name.split()[:2]).upper() or "SB"
        assets = _labeled_assets(store.get_epk_assets(share["user_id"],
                                                      public_only=True))
        tour = bandsintown.upcoming_events(
            ((prof or {}).get("data") or {}).get("bandsintown_artist"))
        data = get_epk_data({"name": name, "initials": initials},
                            ctx["catalog_value"],
                            overrides=(prof or {}).get("data"),
                            photo=(prof or {}).get("photo"),
                            assets=assets, tour_dates=tour,
                            demo=_is_demo_email((owner or {}).get("email") or ""))
        viewer = current_user()
        if viewer is None or viewer["id"] != share["user_id"]:
            first_today = not store.epk_viewed_today(token, today)
            store.log_epk_event(token, "view")
            if first_today:
                store.notify(share["user_id"], "pitch",
                             "Your pitch EPK was opened",
                             "First open today on the private link. "
                             "Play counts land on the EPK editor.", "/epk")
        pitch_audio = [dict(a, media_path=url_for("epk_pitch_media", token=token,
                                                  index=index))
                       for index, a in enumerate(share["audio"])]
        return render_template("epk_public.html", e=data, slug=slug,
                               pitch_token=token, pitch_audio=pitch_audio)

    @app.route("/pitch/<token>/media/<int:index>")
    def epk_pitch_media(token, index):
        share = store.get_epk_share_by_token(token)
        if share is None or index < 0 or index >= len(share["audio"]):
            abort(404)
        today = datetime.now(timezone.utc).date().isoformat()
        if share["expires"] and today > share["expires"]:
            abort(404)
        if share["pin"] and not session.get("pitch_ok_" + token):
            abort(404)
        return _serve_asset_path(share["audio"][index]["path"], public=False)

    @app.route("/pitch/<token>/play", methods=["POST"])
    def epk_pitch_play(token):
        share = store.get_epk_share_by_token(token)
        if share is None:
            abort(404)
        label = ((request.get_json(silent=True) or {}).get("label") or "")[:120]
        if label in [a["label"] for a in share["audio"]]:
            store.log_epk_event(token, "play", label)
            return jsonify({"ok": True})
        return jsonify({"ok": False}), 400

    @app.route("/epk/asset/<kind>/from-vault", methods=["POST"])
    def epk_asset_from_vault(kind):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        if kind not in _EPK_KIND_LABELS:
            return jsonify({"ok": False, "error": "Unknown asset type."}), 400
        vid = (request.get_json(silent=True) or {}).get("vault_id") or ""
        v = next((v for v in store.list_vault_files(user["id"])
                  if v["id"] == vid), None)
        if v is None or v["path"].rsplit(".", 1)[-1].lower() not in (
                "png", "jpg", "jpeg", "webp"):
            return jsonify({"ok": False, "error": "Pick an image from your "
                            "own Vault."}), 400
        store.save_epk_asset(user["id"], kind, v["path"])
        store.register_stored_asset(user["id"], v["path"], "public", "epk_asset")
        return jsonify({"ok": True, "path": v["path"]})

    @app.route("/epk/<slug>/kit.zip")
    def epk_kit_zip(slug):
        prof = store.get_epk_by_slug(slug)
        if prof is None:
            abort(404)
        assets = _labeled_assets(store.get_epk_assets(prof["user_id"], public_only=True))
        import io
        import zipfile
        buf = io.BytesIO()
        added = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for a in assets:
                name = os.path.basename(a["path"].split("?")[0])
                ext = name.rsplit(".", 1)[-1]
                arc = "%s-%s.%s" % (slug, a["kind"].replace("_", "-"), ext)
                if blob_store.is_remote(a["path"]):
                    blob = blob_store.fetch(a["path"])
                    if blob is not None:
                        zf.writestr(arc, blob)
                    continue
                fpath = os.path.join(UPLOADS_DIR, name)
                if os.path.exists(fpath):
                    zf.write(fpath, arc)
                    added += 1
        if not added:
            abort(404)
        buf.seek(0)
        return Response(buf.read(), mimetype="application/zip", headers={
            "Content-Disposition": "attachment; filename=%s-press-kit.zip" % slug})

    @app.route("/epk/save", methods=["POST"])
    def epk_save():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in to save your EPK."}), 401
        overrides = normalize_epk_overrides(request.get_json(silent=True) or {})
        store.save_epk(user["id"], overrides)
        return jsonify({"ok": True})

    @app.route("/epk/photo", methods=["POST"])
    def epk_photo():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in to upload a photo."}), 401
        f = request.files.get("photo")
        if f is None or not f.filename:
            return jsonify({"ok": False, "error": "Choose an image file."}), 400
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in ("png", "jpg", "jpeg", "webp"):
            return jsonify({"ok": False, "error": "Use a PNG, JPG, or WebP image."}), 400
        fname = "epk_%s.%s" % (user["id"], ext)
        f.save(os.path.join(UPLOADS_DIR, fname))
        photo_path = "/uploads/" + fname
        store.save_epk_photo(user["id"], photo_path)
        store.register_stored_asset(user["id"], photo_path, "public", "epk_photo")
        return jsonify({"ok": True, "photo": photo_path})

    @app.route("/epk/export", methods=["POST"])
    def epk_export():
        ctx = build_dashboard_context()
        user = current_user()
        data = get_epk_data(
            ctx["account"], ctx["catalog_value"],
            demo=_is_demo_email((user or {}).get("email") or ""))
        slug = data["name"].lower().replace(" ", "-")
        filename = f"{slug}-press-kit-{datetime.today().strftime('%Y%m%d')}.pdf"
        return jsonify({"ok": True, "filename": filename})

    @app.route("/artwork")
    def artwork():
        ctx = build_dashboard_context()
        ctx["artwork"] = get_artwork_data(ctx["account"])
        return render_template("artwork.html", active_page="artwork", **ctx)

    @app.route("/artwork/generate", methods=["POST"])
    def artwork_generate():
        payload = request.get_json(silent=True) or {}
        prompt = (payload.get("prompt") or "").strip()[:300]
        suggestion = suggest_from_prompt(prompt)
        image_url, seed = None, None
        if prompt:
            # Real AI image via Pollinations.ai — free community model, no key.
            # The browser loads the URL directly so slow generations never
            # tie up a server worker. A remix reuses the seed so the model
            # re-imagines the same concept with the requested changes.
            import random
            try:
                seed = int(payload.get("seed"))
            except (TypeError, ValueError):
                seed = random.randint(1, 10 ** 9)
            image_url = ("https://image.pollinations.ai/prompt/"
                         + urllib.parse.quote(prompt + ", album cover art, square, "
                                              "no text, high detail")
                         + "?width=1024&height=1024&nologo=true&seed=%d" % seed)
        return jsonify({"ok": True, "suggestion": suggestion,
                        "image_url": image_url, "seed": seed})

    @app.route("/artwork/upload", methods=["POST"])
    def artwork_upload():
        """Bring your own cover art into the designer."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in to upload artwork."}), 401
        f = request.files.get("art")
        if f is None or not f.filename:
            return jsonify({"ok": False, "error": "Choose an image file."}), 400
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in ("png", "jpg", "jpeg", "webp"):
            return jsonify({"ok": False, "error": "Use a PNG, JPG, or WebP image."}), 400
        fname = "artup_%s_%d.%s" % (user["id"],
                                    int(datetime.now(timezone.utc).timestamp()), ext)
        f.save(os.path.join(UPLOADS_DIR, fname))
        path = "/uploads/" + fname
        store.register_stored_asset(user["id"], path, "private", "artwork")
        return jsonify({"ok": True, "path": path})

    @app.route("/artwork/save", methods=["POST"])
    def artwork_save():
        """Pull a generated image into the user's uploads so it can be used
        as campaign cover art or an EPK asset."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in to save artwork."}), 401
        payload = request.get_json(silent=True) or {}
        url = (payload.get("url") or "").strip()
        if not url.startswith("https://image.pollinations.ai/"):
            return jsonify({"ok": False, "error": "Only generated images can be saved."}), 400
        try:
            data = music_apis.fetch_image_bytes(url)
        except Exception:
            return jsonify({"ok": False, "error": "Couldn't download the image — "
                                                  "generate it again and retry."}), 502
        if not data or len(data) > 8 * 1024 * 1024:
            return jsonify({"ok": False, "error": "Image missing or too large."}), 400
        fname = "aiart_%s_%d.jpg" % (user["id"], int(datetime.now(timezone.utc).timestamp()))
        with open(os.path.join(UPLOADS_DIR, fname), "wb") as f:
            f.write(data)
        path = "/uploads/" + fname
        store.register_stored_asset(user["id"], path, "private", "artwork")
        return jsonify({"ok": True, "path": path})

    def _ml_campaign_card(c):
        counts = mls.event_counts(c["id"])
        visits = counts.get("page_view", 0)
        clicks = counts.get("service_click", 0)
        dests = mls.get_destinations(c["id"])
        score = links_engine.calculate_street_banker_score(c, dests)
        status = links_engine.effective_status(c)
        # 7-day sparkline: real page-view counts, missing days filled with 0.
        tl = dict(mls.timeline(c["id"], days=7))
        spark = [tl.get((date.today() - timedelta(days=i)).isoformat(), 0)
                 for i in range(6, -1, -1)]
        return {**c, "visits": visits, "clicks": clicks,
                "ctr": round(100 * clicks / visits, 1) if visits else 0.0,
                "captures": counts.get("email_capture", 0),
                "presaves": counts.get("presave_notify", 0),
                "score": score["total"], "warnings": score["warnings"],
                "eff_status": status, "spark": spark,
                "spark_max": max(spark) or 1,
                "status_tone": links_engine.STATUS_TONES.get(status, "gray"),
                "dest_count": len(dests)}

    @app.route("/links")
    def links():
        ctx = build_dashboard_context()
        user = current_user()
        ctx["links_data"] = get_links_data(
            demo=_is_demo_email((user or {}).get("email") or ""))
        # Real, persisted links with genuine click counts sit above the demo
        # set - this account's links, and only this account's.
        ctx["real_links"] = store.get_db_links(user["id"]) if user else []
        ctx["links_user"] = user
        ctx["ml_campaigns"] = ([_ml_campaign_card(c) for c in mls.list_campaigns(user["id"])]
                               if user else [])
        return render_template("links.html", active_page="links", **ctx)

    def _ml_slug(title):
        base = _slugify(title)
        slug = base
        while (mls.get_campaign_by_slug(slug) is not None
               or store.get_db_link(slug) is not None
               or mls.get_variant_by_slug(slug) is not None):
            slug = "%s-%s" % (base, uuid.uuid4().hex[:4])
        return slug

    def _ml_form_fields():
        f = request.form
        settings = {
            "email_capture": bool(f.get("email_capture")),
            "consent_text": (f.get("consent_text") or "").strip()[:400],
            "privacy_url": (f.get("privacy_url") or "").strip()[:300],
            "cta_text": (f.get("cta_text") or "").strip()[:60],
            "accent": (f.get("accent") or "").strip()[:7],
            "gate_reward": (f.get("gate_reward") or "").strip()[:64],
            "gate_label": (f.get("gate_label") or "").strip()[:120],
        }
        uploaded = _ml_cover_upload()
        return {
            "title": (f.get("title") or "").strip()[:120],
            "artist_name": (f.get("artist_name") or "").strip()[:120],
            "release_type": f.get("release_type") if f.get("release_type") in links_engine.RELEASE_TYPES else "Single",
            "campaign_type": f.get("campaign_type") if f.get("campaign_type") in links_engine.CAMPAIGN_TYPE_NAMES else "release",
            "release_date": (f.get("release_date") or "").strip()[:10],
            "cover_url": uploaded or (f.get("cover_url") or "").strip()[:500],
            "description": (f.get("description") or "").strip()[:600],
            "settings": settings,
        }

    def _ml_form_destinations():
        out, order = [], 0
        for key, name, _logo in links_engine.SERVICES:
            url = (request.form.get("dest_" + key) or "").strip()[:500]
            if url and url.startswith(("http://", "https://")):
                out.append({"service_key": key, "service_name": name,
                            "url": url, "sort_order": order})
                order += 1
        return out

    @app.route("/links/autofill")
    def ml_autofill():
        """Paste one track URL -> Odesli resolves every platform + metadata."""
        if current_user() is None:
            return jsonify({"ok": False}), 401
        url = (request.args.get("url") or "").strip()
        meta = odesli_lookup(url)
        if not meta:
            return jsonify({"ok": False, "error": "Couldn't resolve that link — check the URL or fill services manually."})
        links = {}
        for odesli_key, service_key in links_engine.ODESLI_TO_SERVICE.items():
            if meta["links"].get(odesli_key):
                links[service_key] = meta["links"][odesli_key]
        return jsonify({"ok": True, "title": meta.get("title") or "",
                        "artist": meta.get("artist") or "",
                        "art": meta.get("art") or "", "links": links,
                        "found": len(links)})

    def _ml_cover_upload():
        """Optional cover art file upload; returns a served path or None."""
        f = request.files.get("cover_file")
        if f is None or not f.filename:
            return None
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in ("png", "jpg", "jpeg", "webp"):
            return None
        fname = "mlcover_%s.%s" % (uuid.uuid4().hex, ext)
        f.save(os.path.join(UPLOADS_DIR, fname))
        path = "/uploads/" + fname
        user = current_user()
        if user:
            store.register_stored_asset(user["id"], path, "public", "campaign_cover")
        return path

    @app.route("/links/new", methods=["GET", "POST"])
    def ml_new():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if request.method == "POST":
            fields = _ml_form_fields()
            if not fields["title"]:
                return render_template("links_builder.html", active_page="links",
                                       c=None, destinations=[], engine=links_engine,
                                       error="A campaign title is required.",
                                       vault_files=store.list_vault_files(user["id"]),
                                       **build_dashboard_context())
            cid = mls.create_campaign(user["id"], _ml_slug(fields["title"]), fields)
            mls.set_destinations(cid, _ml_form_destinations())
            return redirect("/links/%s/edit" % cid)
        return render_template("links_builder.html", active_page="links",
                               c=None, destinations=[], engine=links_engine,
                               error=None,
                               vault_files=store.list_vault_files(user["id"]),
                               prefill_title=(request.args.get("title") or "")[:80],
                               rack_facts=(request.args.get("rack") or "")[:160],
                               **build_dashboard_context())

    def _ml_owned(campaign_id):
        user = current_user()
        if user is None:
            return None, login_required_redirect()
        campaign = mls.get_campaign(campaign_id, user["id"])
        if campaign is None:
            return None, abort(404)
        return campaign, None

    @app.route("/links/<cid>/edit", methods=["GET", "POST"])
    def ml_edit(cid):
        campaign, err = _ml_owned(cid)
        if err:
            return err
        if request.method == "POST":
            mls.update_campaign(cid, campaign["user_id"], _ml_form_fields())
            mls.set_destinations(cid, _ml_form_destinations())
            campaign = mls.get_campaign(cid)
        dests = mls.get_destinations(cid)
        score = links_engine.calculate_street_banker_score(campaign, dests)
        return render_template("links_builder.html", active_page="links",
                               c=campaign, destinations=dests, engine=links_engine,
                               score=score, error=None,
                               vault_files=store.list_vault_files(campaign["user_id"]),
                               eff_status=links_engine.effective_status(campaign),
                               **build_dashboard_context())

    @app.route("/links/<cid>/publish", methods=["POST"])
    def ml_publish(cid):
        campaign, err = _ml_owned(cid)
        if err:
            return err
        mls.update_campaign(cid, campaign["user_id"],
                            {"status": "live", "published_at": store._now(),
                             "archived_at": None})
        store.notify(campaign["user_id"], "campaign",
                     "Campaign live: %s" % campaign["title"],
                     "Public page is up at /l/%s — start sharing variant links." % campaign["slug"],
                     "/l/" + campaign["slug"])
        return redirect("/links/%s/edit" % cid)

    @app.route("/links/<cid>/unpublish", methods=["POST"])
    def ml_unpublish(cid):
        campaign, err = _ml_owned(cid)
        if err:
            return err
        mls.update_campaign(cid, campaign["user_id"], {"status": "draft"})
        return redirect("/links/%s/edit" % cid)

    @app.route("/links/<cid>/archive", methods=["POST"])
    def ml_archive(cid):
        campaign, err = _ml_owned(cid)
        if err:
            return err
        mls.update_campaign(cid, campaign["user_id"],
                            {"status": "draft", "archived_at": store._now()})
        return redirect("/links")

    @app.route("/links/<cid>/duplicate", methods=["POST"])
    def ml_duplicate(cid):
        campaign, err = _ml_owned(cid)
        if err:
            return err
        new_id = mls.duplicate_campaign(cid, campaign["user_id"],
                                        _ml_slug(campaign["title"] + "-copy"))
        return redirect("/links/%s/edit" % new_id)

    @app.route("/links/<cid>/analytics")
    def ml_analytics(cid):
        campaign, err = _ml_owned(cid)
        if err:
            return err
        counts = mls.event_counts(cid)
        visits = counts.get("page_view", 0)
        clicks = counts.get("service_click", 0)
        variants = mls.list_variants(cid)
        vstats = mls.variant_stats(cid)
        dests = mls.get_destinations(cid)
        return render_template(
            "links_analytics.html", active_page="links", c=campaign,
            counts=counts, visits=visits, clicks=clicks,
            ctr=round(100 * clicks / visits, 1) if visits else 0.0,
            top_services_named=[(links_engine.SERVICE_NAMES.get(k, k), n)
                                for k, n in mls.breakdown(cid, "service_key", "service_click")],
            top_referrers=mls.breakdown(cid, "referrer"),
            top_utm=mls.breakdown(cid, "utm_source"),
            timeline=mls.timeline(cid),
            variants=variants, vstats=vstats,
            score=links_engine.calculate_street_banker_score(campaign, dests),
            eff_status=links_engine.effective_status(campaign),
            service_names=links_engine.SERVICE_NAMES,
            **build_dashboard_context())

    @app.route("/links/<cid>/variants", methods=["GET", "POST"])
    def ml_variants(cid):
        campaign, err = _ml_owned(cid)
        if err:
            return err
        if request.method == "POST":
            name = (request.form.get("name") or "").strip()[:80]
            if name:
                mls.create_variant(cid, name, _ml_slug(campaign["slug"] + "-" + name),
                                   utm_source=(request.form.get("utm_source") or "").strip()[:80],
                                   utm_medium=(request.form.get("utm_medium") or "").strip()[:80])
        return render_template(
            "links_variants.html", active_page="links", c=campaign,
            variants=mls.list_variants(cid), vstats=mls.variant_stats(cid),
            **build_dashboard_context())

    @app.route("/links/<cid>/qr.svg")
    def ml_qr(cid):
        campaign, err = _ml_owned(cid)
        if err:
            return err
        import io as _io
        import segno
        url = request.host_url.rstrip("/") + "/l/" + campaign["slug"] + "?src=qr"
        vslug = (request.args.get("v") or "").strip()
        if vslug:
            url += "&v=" + vslug
        buf = _io.BytesIO()
        segno.make(url, error="m").save(buf, kind="svg", scale=6,
                                        dark="#1A1714", light=None)
        return Response(buf.getvalue(), mimetype="image/svg+xml")

    # --- Plan tiers + product worlds -------------------------------------------

    def _palette_for(user):
        """The palette's destinations for this account."""
        idx = hub_defs.command_index()
        plan = (user or {}).get("plan") or ""
        if plan != "fan":
            return idx
        allowed = {k for k, _h, _i, _l, _d in hub_defs.COMMUNITY_GROUP[1]}
        allowed |= set(hub_defs.FAN_ACCOUNT_KEYS)
        return [e for e in idx if e["key"] in allowed]

    @app.context_processor
    def inject_hub_context():
        # The Ecosystem Hub model: one source of truth (hubs.py) feeds the
        # sidebar and the /desk/<hub> landing pages.
        return {"hubs_nav": hub_defs.HUBS, "hubs_label": hub_defs.LABEL_GROUP,
                "hubs_community": hub_defs.COMMUNITY_GROUP,
                "hubs_account": hub_defs.ACCOUNT_GROUP,
                "fan_account_keys": hub_defs.FAN_ACCOUNT_KEYS,
                "hub_icons": hub_defs.HUB_ICONS,
                # Flag-aware: a page whose engine is on must not be
                # badged "example data, not yours".
                "live_keys": hub_defs.live_keys(),
                # One flat list for the command palette, derived from the
                # same definitions - so it cannot list a page the nav has
                # dropped, or miss one the nav has gained. Filtered to the
                # SAME shell the sidebar shows: a fan account must not be
                # offered artist tooling it would only be refused at, and
                # the whole point of the fan shell is that those pages are
                # not part of their world.
                "command_index": _palette_for(current_user())}

    @app.route("/desk/<hub_key>")
    def hub_desk(hub_key):
        user = current_user()
        if user is None:
            return login_required_redirect()
        hub = hub_defs.get_hub(hub_key)
        if hub is None:
            abort(404)
        # The Command desk tiles carry live micro-dashboards — every number
        # below comes from the same engines that power the full pages.
        desk = {}
        if hub_key == "command":
            desk = {"growth": qualification.calculate(user["id"])["total"],
                    "trust": trust_score.calculate(user["id"])["total"],
                    "actions": cc.open_actions(user["id"], limit=3),
                    "insights": insights_engine.build_insights(user["id"])[:2]}
        elif hub_key == "launch":
            # Next drop + real blockers: campaign dates, track release dates,
            # and Clean Release verdicts all come from the user's own records.
            today = datetime.now(timezone.utc).date().isoformat()
            drops = sorted(
                [c for c in mls.list_campaigns(user["id"])
                 if (c.get("release_date") or "") >= today],
                key=lambda c: c["release_date"])
            tracks, ctx, summary, _cert = _os_full(user["id"])
            alerts = []
            for t in sorted([t for t in tracks
                             if (t.get("release_date") or "") >= today],
                            key=lambda t: t["release_date"]):
                clean = artist_os.clean_release(t, ctx)
                passport = artist_os.passport_report(t)
                if clean["blocked"]:
                    first_red = next((i["label"] for i in clean["items"]
                                      if i["state"] == "red"), "rights issue")
                    alerts.append({"level": "red", "track": t["title"],
                                   "date": t["release_date"],
                                   "text": "%s unresolved" % first_red})
                elif passport["pct"] < 100:
                    alerts.append({"level": "amber", "track": t["title"],
                                   "date": t["release_date"],
                                   "text": "passport %d%% complete"
                                           % passport["pct"]})
            desk = {"next_release": drops[0] if drops else None,
                    "reds": summary["reds"], "alerts": alerts[:4],
                    "flow": [("Track Passport", "/tracks"),
                             ("Clean Release", "/releases/clean-release"),
                             ("Schedule", "/releases"),
                             ("Smart Link", "/links"),
                             ("Rollout", "/rollout-studio"),
                             ("Pulse", "/pulse")]}
        return render_template("hub_desk.html", active_page="desk-" + hub_key,
                               hub=hub, desk=desk, **build_dashboard_context())

    @app.context_processor
    def inject_plan_context():
        user = None
        try:
            user = current_user()
        except RuntimeError:
            pass
        plan = (user.get("plan") or "artist") if user else None
        world = plans.world_for_path(request.path) or session.get("world")
        if plan == "fan":
            world = "fan"
        return {"user_plan": plan, "nav_world": world or "promote",
                "plan_worlds": plans.WORLDS, "plan_rank": plans.TIER_RANK,
                "plan_names": plans.PLAN_NAMES,
                "unread_ntf": store.unread_notifications(user["id"]) if user else 0}

    _PUBLIC_PREFIXES = ("/static/", "/reach/", "/uploads/", "/media/", "/l/", "/s/", "/epk/",
                        "/stem-src/",
                        # Company OS API routes return their own JSON 401/403
                        # responses; letting the generic plan wall redirect
                        # them would turn an API failure into a login page.
                        "/api/company-os",
                        "/services", "/favicon", "/presave/", "/reset/",
                        "/team/join/", "/webhooks/", "/club/", "/showday/",
                        "/rider/", "/roster/join/", "/sign/", "/sheet/", "/pitch/", "/@",
                        # A journalist who was sent an announcement reads it
                        # without an account. The token in the URL is the
                        # authorisation, and it identifies which recipient
                        # opened it. ("/press-desk" does not match this
                        # prefix - that one stays behind the wall.)
                        "/press/",
                        # The Light Studio phone remote. The unguessable code
                        # in the URL is the authorisation, like a share link,
                        # so a second operator can pick it up without an
                        # account. It carries buttons, never show data.
                        "/lights/remote/",
                        # A light show sent out for notes. Carries one show
                        # and no audio; the trailing slash keeps it from
                        # swallowing anything else under /lights.
                        "/lights/show/",
                        # A beat sent to one artist. One beat, no
                        # catalogue. The trailing slash matters: "/beats"
                        # and "/beats/<id>" stay behind the wall, and so
                        # does "/beat-link/<token>/revoke", which is the
                        # producer's control and not the recipient's.
                        "/beat/",
                        # A beat licence is read and signed by somebody who
                        # has no account here, and the cleared list exists to
                        # be checked by a label that never will.
                        "/licence/", "/cleared/",
                        # A TOUR share link - a day sheet for the local crew,
                        # a check-in list for the door - is read by somebody
                        # without an account. The token is the authorisation
                        # and it is scoped to one thing; /tours/ itself stays
                        # behind the wall.
                        "/tour-share/",
                        # The Team-Up Board's one-click renew link from the
                        # expiry email; single-use token, renews one listing.
                        "/board-renew/")
    _PUBLIC_EXACT = {"/", "/healthz", "/auth/street-banker", "/reach", "/login", "/signup", "/logout", "/submit", "/forgot",
                     "/catalog-sweep", "/demo-open", "/plan",
                     "/terms", "/privacy", "/support", "/sw.js", "/demo-access",
                     "/api/artist-signal-profile",
                     # A stranger asking what the Artist Twin does, and how
                     # their music would be treated, must not meet a password
                     # field first. /artist-twin itself stays gated.
                     "/artist-twin/start", "/ai", "/lanes",
                     "/creative-studio", "/rollout",
                     "/royalty-sweep", "/distribution",
                     "/metadata",
                     # The closing CTAs and the trust band. A guided start
                     # that demands an account before it will say anything
                     # is not a guided start, and a control policy nobody
                     # can read without signing in is not a policy.
                     "/start", "/artist-control",
                     "/product-tour", "/product-tour/smart-link",
                     "/about", "/contact", "/partners", "/release-check",
                     "/release-signal", "/remix-lab",
                     # Exact only. "/press" explains the desk to a stranger;
                     # "/press-desk" and everything under it stays gated,
                     # and "/press/<token>" is covered by the prefix above.
                     "/press"}

    def _is_public_path(path):
        if path in _PUBLIC_EXACT:
            return True
        return any(path.startswith(p) for p in _PUBLIC_PREFIXES)

    def _valid_backup_token():
        """A scheduler has no session, so the login wall would bounce it to
        /login and the backup would silently never run. This lets a request
        carrying the right token through - and ONLY that one path, only
        when a token is actually configured. The route re-checks; this is
        not a way in, it is a way past the redirect."""
        token = os.environ.get("BACKUP_TOKEN") or ""
        if not token or request.path != "/backup/run":
            return False
        presented = (request.headers.get("X-Backup-Token")
                     or request.form.get("token") or "")
        return hmac.compare_digest(presented, token)

    def resolve_partner():
        """Which reseller's front door is this request standing at?

        Order matters. The host is the strongest signal because it is the
        thing the artist actually typed, and a partner's own domain must
        never resolve to somebody else's tenant. The seat is the fallback
        for staff reaching the app on the plain address. None means
        Street Banker itself, which is every request today.

        Read-only and side-effect free: it sets g and returns nothing, so
        it cannot bounce a request. Enforcement belongs to the decorator.
        """
        g.partner = None
        g.partner_member = None
        host = (request.host or "").split(":")[0].lower()
        try:
            if not partner_store.any_partners():
                return          # no resellers on this instance: nothing to resolve
            p = partner_store.partner_by_domain(host)
            if p is None and host.endswith(_PARTNER_ROOT) and host != _PARTNER_ROOT:
                p = partner_store.partner_by_slug(host[:-len(_PARTNER_ROOT) - 1])
            if p is None:
                uid = session.get("user_id")
                seat = partner_store.member_for_user(uid) if uid else None
                if seat:
                    p = partner_store.get_partner(seat["partner_id"])
                    g.partner_member = seat
            if p and p.get("status") == "active":
                g.partner = p
                if g.partner_member is None:
                    uid = session.get("user_id")
                    user = store.get_user(uid) if uid else None
                    if user:
                        g.partner_member = partner_store.get_member(
                            p["id"], user_id=user["id"], email=user.get("email"))
        except Exception:
            # A partner table that is missing or mid-migration must not
            # take down every page. No tenant resolved is a safe answer.
            g.partner = None
            g.partner_member = None

    @app.before_request
    def _resolve_partner():
        """Registered BEFORE plan_gate, so g.partner is set by the time
        the login wall runs. Never returns a response - resolution
        must not be able to bounce a request."""
        resolve_partner()
        return None

    @app.before_request
    def plan_gate():
        user = current_user()
        if user is None:
            # Room invitations grant scoped project access, never a host login.
            if request.blueprint == 'song_builder':
                from song_builder.collaboration import allow_guest_gate
                if allow_guest_gate(app):
                    return None
            if _is_public_path(request.path) or _valid_backup_token():
                return None
            return redirect(url_for("login", next=request.path))
        tier = plans.required_tier(request.path)
        if tier and not plans.allowed(user.get("plan") or "artist", tier):
            return render_template("upgrade.html", required=tier,
                                   plans_list=plans.PLANS,
                                   **build_dashboard_context()), 402
        return None

    @app.route("/world/<world>")
    def switch_world(world):
        homes = {k: home for k, _, home, _ in plans.WORLDS}
        if world not in homes:
            abort(404)
        session["world"] = world
        return redirect(homes[world])

    def _is_demo_email(email):
        return (email == "demo@streetbanker.io"
                or (email.startswith("demo-") and email.endswith("@streetbanker.io")))

    @app.context_processor
    def _billing_flags():
        user = current_user()
        return {"stripe_live": stripe_billing.configured(),
                "is_demo_account": bool(user and _is_demo_email(user["email"]))}

    @app.route("/plan/switch", methods=["POST"])
    def plan_switch():
        user = current_user()
        if user is None:
            return login_required_redirect()
        plan = request.form.get("plan") or ""
        # With Stripe live, paid tiers go through real checkout — the demo
        # accounts keep instant switching so the tier demos still work.
        if (stripe_billing.configured() and plan in stripe_billing.PRICES
                and not _is_demo_email(user["email"])):
            return redirect("/billing")
        # Instant switches exist for the four explicit demo accounts and for
        # isolated automated tests.  A real account never receives a paid
        # entitlement merely because Stripe is absent.
        allow_unbilled = (_is_demo_email(user["email"])
                          or os.environ.get("ALLOW_UNBILLED_PLAN_SWITCH") == "1")
        if plan in plans.TIER_RANK and allow_unbilled:
            store.set_user_plan(user["id"], plan)
        return redirect(request.referrer or "/billing")

    @app.route("/billing/checkout", methods=["POST"])
    def billing_checkout():
        user = current_user()
        if user is None:
            return login_required_redirect()
        plan = request.form.get("plan") or ""
        if not stripe_billing.configured() or plan not in stripe_billing.PRICES:
            return redirect("/billing")
        coupon = (stripe_billing.ensure_referral_coupon()
                  if user.get("referred_by") and not user.get("stripe_subscription_id")
                  else None)
        session_obj = stripe_billing.create_checkout_session(
            user["id"], user["email"], plan, request.url_root.rstrip("/"),
            coupon=coupon)
        if not session_obj or not session_obj.get("url"):
            return render_template("billing_error.html",
                                   message="Stripe couldn't start checkout — try again "
                                           "in a minute or contact support.",
                                   **build_dashboard_context()), 502
        return redirect(session_obj["url"], code=303)

    @app.route("/billing/sync", methods=["POST"])
    def billing_sync():
        """Webhook-less fallback: claim a completed Stripe checkout by
        matching an active subscription to the signed-in account's email."""
        user = current_user()
        if user is None:
            return login_required_redirect()
        if not stripe_billing.configured():
            return redirect("/billing")
        found = stripe_billing.active_subscription_for_email(user["email"])
        if found:
            store.set_user_plan(user["id"], found["plan"])
            store.set_stripe_ids(user["id"], found["customer_id"],
                                 found["subscription_id"])
            store.notify(user["id"], "billing",
                         "Welcome to %s" % plans.PLAN_NAMES.get(found["plan"]),
                         "Subscription synced from Stripe — everything is unlocked.",
                         "/command-center")
            _settle_referrals(user["id"])
        return redirect("/billing" + ("?upgraded=1" if found else "?sync=none"))

    def _settle_referrals(new_payer_id):
        """After a real paid activation: credit this user's referrer, and pay
        out credits this user earned as a referrer before they had billing.
        A credit is only claimed as applied when Stripe accepted it."""
        payer = store.get_user(new_payer_id)
        if not payer:
            return
        ref_id = payer.get("referred_by")
        if ref_id and not payer.get("ref_credited"):
            referrer = store.get_user(ref_id)
            if referrer and referrer.get("stripe_customer_id"):
                if stripe_billing.credit_customer(
                        referrer["stripe_customer_id"], 900,
                        "Street Banker referral credit: %s" % payer["email"]):
                    store.mark_ref_credited(new_payer_id)
                    store.notify(ref_id, "billing", "Referral credit applied",
                                 "$9.00 landed on your Stripe balance \u2014 %s "
                                 "started a paid plan." % payer["email"], "/referrals")
        if payer.get("stripe_customer_id"):
            for u in store.list_uncredited_referrals(new_payer_id):
                if stripe_billing.credit_customer(
                        payer["stripe_customer_id"], 900,
                        "Street Banker referral credit: %s" % u["email"]):
                    store.mark_ref_credited(u["id"])
                    store.notify(new_payer_id, "billing", "Referral credit applied",
                                 "$9.00 credit for referring %s." % u["email"],
                                 "/referrals")

    @app.route("/referrals")
    def referrals():
        user = current_user()
        if user is None:
            return login_required_redirect()
        code = store.ensure_ref_code(user["id"])
        return render_template("referrals.html", active_page="referrals",
                               ref_link=(request.url_root.rstrip("/")
                                         + "/signup?ref=" + code),
                               stats=store.referral_stats(user["id"]),
                               stripe_live=stripe_billing.configured(),
                               **build_dashboard_context())

    @app.route("/billing/webhook-setup", methods=["POST"])
    def billing_webhook_setup():
        # Owner-only: the server creates the Stripe webhook endpoint itself
        # and keeps the signing secret in app_kv — no dashboard copy-paste.
        user = current_user()
        if user is None or (user.get("plan") or "") != "label":
            abort(404)
        result = stripe_billing.setup_webhook_endpoint(
            request.url_root.rstrip("/"))
        return redirect("/billing?webhook=" + ("ok" if result else "fail"))

    @app.route("/billing/portal", methods=["POST"])
    def billing_portal():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if not (stripe_billing.configured() and user.get("stripe_customer_id")):
            return redirect("/billing")
        session_obj = stripe_billing.create_portal_session(
            user["stripe_customer_id"], request.url_root.rstrip("/") + "/billing")
        if not session_obj or not session_obj.get("url"):
            return redirect("/billing")
        return redirect(session_obj["url"], code=303)

    @app.route("/webhooks/stripe", methods=["POST"])
    def stripe_webhook():
        if not stripe_billing.webhook_configured():
            abort(404)
        body = request.get_data()
        if not stripe_billing.verify_webhook(
                request.headers.get("Stripe-Signature", ""), body):
            return jsonify({"ok": False, "error": "bad signature"}), 401
        event = request.get_json(silent=True) or {}
        etype = event.get("type") or ""
        obj = (event.get("data") or {}).get("object") or {}
        if etype == "checkout.session.completed" and \
                (obj.get("metadata") or {}).get("kind") == "fan_club":
            meta = obj.get("metadata") or {}
            artist_id = meta.get("artist_id")
            email = (meta.get("member_email") or "").lower()
            if artist_id and store.get_user(artist_id) and email:
                new_id = store.add_club_member(artist_id, email, obj.get("customer"),
                                               obj.get("subscription"))
                fan_id = mls.upsert_fan(artist_id, email, None)
                if new_id:  # replayed events and rejoins shouldn't re-notify
                    mls.add_consent(fan_id, None, "fan_club",
                                    "Paid fan club membership via Stripe checkout.")
                    store.notify(artist_id, "fan", "New fan club member",
                                 "%s joined your fan club." % email, "/fan-club")
        elif (etype == "checkout.session.completed" and
              (obj.get("metadata") or {}).get("kind") == "reach"):
            meta = obj.get("metadata") or {}
            tenant_id = meta.get("tenant_id")
            plan = meta.get("plan")
            interval = meta.get("interval") or "monthly"
            from reach import subscriptions as reach_subscriptions
            if tenant_id and plan in reach_subscriptions.PLANS:
                reach_subscriptions.set_subscription(
                    plan, interval, status="active", tenant=tenant_id,
                    stripe_customer_id=obj.get("customer"),
                    stripe_subscription_id=obj.get("subscription"))
        elif etype == "checkout.session.completed":
            user_id = obj.get("client_reference_id")
            plan = (obj.get("metadata") or {}).get("plan")
            if user_id and store.get_user(user_id) and plan in stripe_billing.PRICES:
                store.set_user_plan(user_id, plan)
                store.set_stripe_ids(user_id, obj.get("customer"),
                                     obj.get("subscription"))
                store.notify(user_id, "billing",
                             "Welcome to %s" % plans.PLAN_NAMES.get(plan, plan),
                             "Your subscription is active — every %s feature is "
                             "unlocked." % plans.PLAN_NAMES.get(plan, plan),
                             "/command-center")
                _settle_referrals(user_id)
        elif etype == "customer.subscription.deleted":
            from reach import subscriptions as reach_subscriptions
            if reach_subscriptions.cancel_by_stripe_subscription(obj.get("id")):
                return jsonify({"ok": True})
            # Fan club cancellations next — they aren't plan subscriptions.
            artist_id = store.cancel_club_member_by_subscription(obj.get("id"))
            if artist_id:
                store.notify(artist_id, "fan", "Fan club member left",
                             "A membership was canceled — the fan stays in your CRM.",
                             "/fan-club")
                return jsonify({"ok": True})
            user = store.user_by_stripe_customer(obj.get("customer"))
            if user:
                store.set_user_plan(user["id"], "fan")
                store.set_stripe_ids(user["id"], user.get("stripe_customer_id"), None)
                store.notify(user["id"], "billing", "Subscription ended",
                             "Your plan moved to the free Fan tier. Your data is "
                             "untouched — resubscribe anytime to unlock it again.",
                             "/billing")
        elif etype == "invoice.payment_failed":
            from reach import subscriptions as reach_subscriptions
            reach_subscriptions.mark_payment_failed(obj.get("customer"))
            user = store.user_by_stripe_customer(obj.get("customer"))
            if user:
                store.notify(user["id"], "billing", "Payment failed",
                             "Stripe couldn't charge your card. Update it in "
                             "Manage Billing to keep your plan.", "/billing")
        return jsonify({"ok": True})

    # --- Artist OS: Command Center, Actions, Autopilot, Clean Release ----------

    @app.route("/command-center")
    def command_center_page():
        user = current_user()
        if user is None:
            return login_required_redirect()
        signal = store.get_artist_signal_profile(user["id"])
        signal_ctx = None
        if signal and isinstance(signal.get("priorities"), dict):
            from artist_eq_config import get_artist_eq_config
            channel_keys = [c["key"] for c in get_artist_eq_config()["channels"]]
            vals = [signal["priorities"].get(k, 5) for k in channel_keys]
            # simplified curve: one point per channel on a 300x60 canvas
            span = max(len(vals) - 1, 1)
            pts = " ".join("%d,%d" % (i * 300 // span, 60 - v * 6)
                           for i, v in enumerate(vals))
            updated = (signal.get("_updated") or "")[:10]
            stale = False
            try:
                stale = (datetime.now() -
                         datetime.fromisoformat(signal["_updated"])).days >= 60
            except Exception:
                pass
            signal_ctx = {"profile": signal, "points": pts,
                          "updated": updated, "stale": stale}
        tutor_panel = _tutor_panel(user)
        return render_template(
            "command_center.html", active_page="command-center",
            summary=cc.get_summary(user["id"]),
            cc_alerts=cc.build_alerts(user["id"]),
            cc_actions=cc.open_actions(user["id"]),
            modules=cc.MODULES,
            signal=signal_ctx,
            tutor=tutor_panel,
            # The tutor's first stage IS the firstrun checklist, so when
            # it is on the smaller panel steps aside rather than showing
            # the same five steps twice.
            firstrun=None if tutor_panel else _firstrun_panel(user),
            **build_dashboard_context())

    @app.route("/actions", methods=["GET", "POST"])
    def actions_page():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if request.method == "POST":
            f = request.form
            if f.get("action_id"):
                cc.set_action_status(f["action_id"], user["id"], f.get("status") or "new")
            elif (f.get("title") or "").strip():
                cc.create_action(user["id"], f["title"].strip(),
                                 category=f.get("category") or "general",
                                 priority=f.get("priority") or "medium",
                                 description=(f.get("description") or "").strip(),
                                 due_date=(f.get("due_date") or "").strip())
            return redirect("/actions")
        status_filter = request.args.get("status") or None
        all_actions = cc.list_actions(user["id"])
        done = len([a for a in all_actions if a["status"] == "complete"])
        active_n = len([a for a in all_actions
                        if a["status"] in ("new", "in_progress")])
        stats = {"total": len(all_actions), "complete": done,
                 "in_progress": len([a for a in all_actions
                                     if a["status"] == "in_progress"]),
                 "open": active_n,
                 "pct": round(100 * done / len(all_actions)) if all_actions else 0}
        return render_template(
            "actions.html", active_page="actions",
            actions=cc.list_actions(user["id"], status_filter),
            all_actions=all_actions, stats=stats,
            view=request.args.get("view") or "list",
            today=datetime.now(timezone.utc).date().isoformat(),
            status_filter=status_filter or "",
            categories=cc.ACTION_CATEGORIES, priorities=cc.ACTION_PRIORITIES,
            **build_dashboard_context())

    @app.route("/actions/from-alert", methods=["POST"])
    def action_from_alert():
        user = current_user()
        if user is None:
            return login_required_redirect()
        f = request.form
        cc.create_action(user["id"], (f.get("title") or "").strip()[:200],
                         category=f.get("category") or "general", priority="high",
                         description=(f.get("description") or "").strip())
        return redirect(request.referrer or "/command-center")

    def _release_checks(user, campaign):
        """Clean-release + autopilot share one derived checklist."""
        dests = mls.get_destinations(campaign["id"])
        keys = {d["service_key"] for d in dests}
        settings = campaign.get("settings") or {}
        rollouts = ros.list_campaigns(user["id"])
        has_rollout = any(r.get("ml_campaign_id") == campaign["id"] for r in rollouts)
        variants = mls.list_variants(campaign["id"])
        tracks = store.get_catalog_tracks(user["id"])
        title_l = campaign["title"].lower()
        track = next((t for t in tracks if t["title"].lower() == title_l), None)
        epk = store.get_epk(user["id"])
        checks = [
            ("Cover art set", bool(campaign.get("cover_url")),
             "Upload or auto-scan cover art in the campaign builder.", "/links/%s/edit" % campaign["id"], "release"),
            ("Release date set", bool(campaign.get("release_date")),
             "A date drives the pre-save countdown and auto-conversion.", "/links/%s/edit" % campaign["id"], "release"),
            ("Spotify destination", "spotify" in keys,
             "Add the Spotify link (auto-scan can find it).", "/links/%s/edit" % campaign["id"], "smart_link"),
            ("Apple Music destination", "apple_music" in keys or "itunes" in keys,
             "Add the Apple Music link.", "/links/%s/edit" % campaign["id"], "smart_link"),
            ("YouTube destination", "youtube" in keys or "youtube_music" in keys,
             "Add the YouTube link.", "/links/%s/edit" % campaign["id"], "smart_link"),
            ("Campaign published", campaign["status"] == "live",
             "Publish the campaign so the public page is live.", "/links/%s/edit" % campaign["id"], "smart_link"),
            ("Fan capture enabled", bool(settings.get("email_capture")),
             "Own the fan — enable email capture.", "/links/%s/edit" % campaign["id"], "fan_growth"),
            ("Consent copy set", bool(settings.get("consent_text")),
             "Consent text is stored with every signup.", "/links/%s/edit" % campaign["id"], "rights"),
            ("ISRC on catalog track", bool(track and (track.get("meta") or {}).get("isrc")),
             "Add the track to your catalog so identifiers auto-pull.", "/catalog", "metadata"),
            ("Rollout scheduled", has_rollout,
             "Generate the social rollout with tracked links per post.", "/rollout-studio/new", "rollout"),
            ("Promo variants created", bool(variants),
             "Create per-channel variants so every door is measured.", "/links/%s/variants" % campaign["id"], "smart_link"),
            ("Press kit ready", bool(epk and (epk.get("data") or epk.get("photo"))),
             "Update your EPK — press and promoters will ask for it.", "/epk", "release"),
        ]
        passed = sum(1 for _, ok, _, _, _ in checks if ok)
        return checks, round(100 * passed / len(checks))

    def _campaign_picker(user):
        return [c for c in mls.list_campaigns(user["id"]) if not c.get("archived_at")]

    @app.route("/releases/autopilot")
    def release_autopilot():
        user = current_user()
        if user is None:
            return login_required_redirect()
        campaigns = _campaign_picker(user)
        selected = request.args.get("campaign") or (campaigns[0]["id"] if campaigns else None)
        campaign = mls.get_campaign(selected, user["id"]) if selected else None
        checks, score = _release_checks(user, campaign) if campaign else ([], 0)
        today = datetime.now(timezone.utc).date().isoformat()
        stage = artist_os.autopilot_stage(
            (campaign or {}).get("release_date"), today)
        plan_days = request.args.get("days")
        plan_days = int(plan_days) if plan_days in ("14", "30", "60") else 14
        kit = plan = days_left = None
        if campaign:
            link_url = request.url_root.rstrip("/") + "/l/" + campaign["slug"]
            kit = artist_os.release_kit(user["name"], campaign["title"],
                                        campaign.get("release_date"), link_url)
            plan = artist_os.campaign_plan(plan_days, campaign["title"],
                                           campaign.get("release_date"))
            if campaign.get("release_date"):
                try:
                    days_left = (date.fromisoformat(
                        campaign["release_date"][:10]) -
                        datetime.now(timezone.utc).date()).days
                except ValueError:
                    pass
            # Flag plan windows the calendar has already closed — pure date
            # math against the campaign's own release date.
            plan["windows"] = [
                {"label": lbl, "sub": sub, "tasks": tasks,
                 "passed": days_left is not None and (
                     (lbl.endswith("days out") and
                      days_left < int(lbl.split(" ")[0])) or
                     (lbl == "Release day" and days_left < 0))}
                for lbl, sub, tasks in plan["windows"]]
        return render_template("release_autopilot.html", active_page="autopilot",
                               campaigns=campaigns, c=campaign, checks=checks,
                               score=score, stage=stage, stages=artist_os.STAGES,
                               kit=kit, plan=plan, plan_days=plan_days,
                               days_left=days_left,
                               **build_dashboard_context())

    @app.route("/releases/autopilot/kit.txt")
    def autopilot_kit_export():
        """The whole release kit + plan as one plain-text bundle for the
        team thread. Same generators, nothing added."""
        user = current_user()
        if user is None:
            return login_required_redirect()
        campaign = mls.get_campaign(request.args.get("campaign") or "",
                                    user["id"])
        if campaign is None:
            abort(404)
        plan_days = request.args.get("days")
        plan_days = int(plan_days) if plan_days in ("14", "30", "60") else 14
        link_url = request.url_root.rstrip("/") + "/l/" + campaign["slug"]
        kit = artist_os.release_kit(user["name"], campaign["title"],
                                    campaign.get("release_date"), link_url)
        plan = artist_os.campaign_plan(plan_days, campaign["title"],
                                       campaign.get("release_date"))
        lines = ["RELEASE KIT — %s" % campaign["title"],
                 "Drops: %s · Smart link: %s" % (
                     campaign.get("release_date") or "[set a date]", link_url),
                 "Generated by Street Banker from this campaign's real title,"
                 " date, and link. [Brackets] mark what only you know.", "",
                 "== CAPTIONS =="] + kit["captions"] + [
                "", "== SHORT-FORM IDEAS =="] + kit["shorts"] + [
                "", "== EMAIL ==", "Subject: " + kit["email"]["subject"], "",
                kit["email"]["body"], "", "== SMS ==", kit["sms"], "",
                "== PLAYLIST PITCH ==", kit["pitch"], "",
                "== %d-DAY PLAN ==" % plan_days]
        for w in plan["windows"]:
            lines += ["", "%s — %s" % (w[0], w[1])] + ["- " + t for t in w[2]]
        lines += ["", "== CREATOR BRIEF ==", plan["brief"], "",
                  "== AD TEST CONCEPTS =="] + ["- " + a for a in plan["ads"]]
        return Response("\n".join(lines), mimetype="text/plain; charset=utf-8",
                        headers={"Content-Disposition":
                                 "attachment; filename=release-kit-%s.txt"
                                 % campaign["slug"]})

    @app.route("/releases/clean-release")
    def clean_release():
        user = current_user()
        if user is None:
            return login_required_redirect()
        campaigns = _campaign_picker(user)
        selected = request.args.get("campaign") or (campaigns[0]["id"] if campaigns else None)
        campaign = mls.get_campaign(selected, user["id"]) if selected else None
        checks, score = _release_checks(user, campaign) if campaign else ([], 0)
        osctx = _os_ctx(user["id"])
        os_rows = [{"t": t, "clean": artist_os.clean_release(t, osctx)}
                   for t in store.list_os_tracks(user["id"])]
        # Category nodes: the checklist grouped into the real release path.
        cat_nodes = []
        for keys, label in (( ("release",), "Release assets"),
                            (("metadata",), "Metadata"),
                            (("smart_link",), "Distribution"),
                            (("fan_growth", "rights"), "Fans & rights"),
                            (("rollout",), "Rollout")):
            in_cat = [ck for ck in checks if ck[4] in keys]
            cat_nodes.append({"cat_keys": " ".join(keys), "label": label,
                              "total": len(in_cat),
                              "done": sum(1 for ck in in_cat if ck[1])})
        # Passport pull: fields a matching Track Passport could fill in the
        # catalog record — shown side-by-side, applied only on click.
        resolves = _passport_resolves(user["id"])
        # In-app ping: a dated track inside 14 days with open items gets one
        # notification (deduped by exact title, so it fires once per date).
        today = datetime.now(timezone.utc).date()
        known = {n["title"] for n in store.list_notifications(user["id"], 200)}
        for r in os_rows:
            rd = r["t"].get("release_date") or ""
            try:
                delta = (date.fromisoformat(rd[:10]) - today).days
            except ValueError:
                continue
            if 0 <= delta <= 14 and (r["clean"]["blocked"]
                                     or r["clean"]["score"] < 100):
                title = "Release risk: %s drops %s" % (r["t"]["title"], rd)
                if title not in known:
                    store.notify(user["id"], "release_risk", title,
                                 "Clean Release is at %d with %s open. "
                                 "Computed when the checklist ran — clear it "
                                 "before submission." % (
                                     r["clean"]["score"],
                                     "blockers" if r["clean"]["blocked"]
                                     else "open items"),
                                 "/releases/clean-release")
        return render_template("clean_release.html", active_page="clean-release",
                               campaigns=campaigns, c=campaign, checks=checks,
                               score=score, os_rows=os_rows,
                               cat_nodes=cat_nodes, resolves=resolves,
                               **build_dashboard_context())

    _RESOLVE_MAP = [("isrc", "isrc", "ISRC"), ("upc", "upc", "UPC"),
                    ("label", "label", "Label"),
                    ("songwriters", "writers", "Songwriters"),
                    ("publishers", "publishers", "Publishers")]

    def _passport_resolves(user_id):
        """Side-by-side diffs: passport fields that exist but are missing on
        the matching catalog record. Real values only, applied on click."""
        os_by_title = {t["title"].casefold(): t
                       for t in store.list_os_tracks(user_id)}
        out = []
        for ct in store.get_catalog_tracks(user_id):
            ost = os_by_title.get((ct["title"] or "").casefold())
            if ost is None:
                continue
            passport = ost.get("passport") or {}
            meta = ct.get("meta") or {}
            fields = [{"label": lbl, "value": passport[pk]}
                      for pk, mk, lbl in _RESOLVE_MAP
                      if passport.get(pk) and not meta.get(mk)]
            if fields:
                out.append({"catalog_id": ct["id"], "title": ct["title"],
                            "fields": fields})
        return out

    @app.route("/clean-release/resolve", methods=["POST"])
    def clean_release_resolve():
        """Apply one passport pull. Values are recomputed server-side from
        the user's own records — the form only names the catalog row."""
        user = current_user()
        if user is None:
            return login_required_redirect()
        target = request.form.get("catalog_id") or ""
        for ct in store.get_catalog_tracks(user["id"]):
            if ct["id"] != target:
                continue
            ost = next((t for t in store.list_os_tracks(user["id"])
                        if t["title"].casefold() ==
                        (ct["title"] or "").casefold()), None)
            if ost is None:
                break
            passport = ost.get("passport") or {}
            meta = dict(ct.get("meta") or {})
            for pk, mk, _lbl in _RESOLVE_MAP:
                if passport.get(pk) and not meta.get(mk):
                    meta[mk] = passport[pk]
            store.set_catalog_track_meta(user["id"], ct["id"], meta)
            break
        return redirect("/releases/clean-release")

    @app.route("/tracks/<track_id>/certificate")
    def clean_release_certificate(track_id):
        """Print-ready record of a 100-score Clean Release: what was checked,
        what was signed, and when this page was generated. It is a timestamped
        snapshot of Street Banker's own checks — not a legal document."""
        user = current_user()
        if user is None:
            return login_required_redirect()
        track = store.get_os_track(user["id"], track_id)
        if track is None:
            abort(404)
        ctx = _os_ctx(user["id"])
        clean = artist_os.clean_release(track, ctx)
        if clean["blocked"] or clean["score"] < 100:
            return redirect("/releases/clean-release")
        box = artist_os.lockbox_report(track)
        passport = track.get("passport") or {}
        return render_template("clean_certificate.html", user=user, t=track,
                               clean=clean, box=box, passport=passport,
                               generated=datetime.now(timezone.utc)
                               .strftime("%Y-%m-%d %H:%M UTC"))

    _PASSPORT_FIELDS = [("isrc", "ISRC"), ("upc", "UPC"), ("label", "Label"),
                        ("release_date", "Release date"), ("album", "Album"),
                        ("writers", "Songwriters"), ("publishers", "Publishers")]

    def _passport_rows(user_id):
        rows = []
        for t in store.get_catalog_tracks(user_id):
            meta = t.get("meta") or {}
            fields = [{"key": k, "label": lbl, "ok": bool(meta.get(k)),
                       "value": (", ".join(meta[k]) if isinstance(meta.get(k), list)
                                 else (meta.get(k) or ""))}
                      for k, lbl in _PASSPORT_FIELDS]
            done = sum(1 for f in fields if f["ok"])
            rows.append({"track": t, "fields": fields, "done": done,
                         "total": len(fields),
                         "pct": round(100 * done / len(fields))})
        return rows

    @app.route("/metadata-passport")
    def metadata_passport():
        user = current_user()
        if user is None:
            return login_required_redirect()
        rows = _passport_rows(user["id"])
        overall = round(sum(r["pct"] for r in rows) / len(rows)) if rows else 0
        os_rows = [{"t": t, "rep": artist_os.passport_report(t)}
                   for t in store.list_os_tracks(user["id"])]
        return render_template("metadata_passport.html", active_page="identifiers",
                               rows=rows, overall=overall, os_rows=os_rows,
                               field_labels=[lbl for _, lbl in _PASSPORT_FIELDS],
                               **build_dashboard_context())

    @app.route("/metadata-passport/export.csv")
    def metadata_passport_export():
        user = current_user()
        if user is None:
            return login_required_redirect()
        import csv as _csv
        import io as _io
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["title", "artist", "album", "isrc", "upc", "label",
                    "release_date", "writers", "publishers"])
        for t in store.get_catalog_tracks(user["id"]):
            m = t.get("meta") or {}
            w.writerow([t["title"], t["artist"], m.get("album") or t["album"],
                        m.get("isrc") or "", m.get("upc") or "",
                        m.get("label") or "", m.get("release_date") or "",
                        "; ".join(m.get("writers") or []),
                        "; ".join(m.get("publishers") or [])])
        return Response(buf.getvalue(), mimetype="text/csv", headers={
            "Content-Disposition": "attachment; filename=metadata-passport.csv"})

    # --- Fan Club: recurring fan memberships through Stripe ---------------------

    @app.route("/fan-club", methods=["GET", "POST"])
    def fan_club():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if request.method == "POST":
            try:
                price = max(1.0, min(float(request.form.get("price") or 5), 500.0))
            except ValueError:
                price = 5.0
            perks = [p.strip() for p in (request.form.get("perks") or "").splitlines()
                     if p.strip()][:8]
            store.save_fan_club(user["id"], (request.form.get("name") or "").strip(),
                                (request.form.get("blurb") or "").strip(),
                                round(price * 100), perks,
                                request.form.get("active") == "1")
            return redirect("/fan-club")
        club = store.get_fan_club(user["id"])
        members = store.list_club_members(user["id"])
        active_members = [m for m in members if m["status"] == "active"]
        slug = _ensure_epk_slug(user)
        return render_template("fan_club.html", active_page="fan-club-admin",
                               club=club, members=members,
                               drops=store.list_club_drops(user["id"]),
                               active_count=len(active_members),
                               mrr=round(len(active_members)
                                         * (club["price_cents"] if club else 0) / 100, 2),
                               club_url="/club/" + slug,
                               stripe_live=stripe_billing.configured(),
                               **build_dashboard_context())

    @app.route("/club/<slug>")
    def club_public(slug):
        prof = store.get_epk_by_slug(slug)
        club = store.get_fan_club(prof["user_id"]) if prof else None
        if prof is None or club is None or not club["active"]:
            abort(404)
        sid = request.args.get("session_id")
        if sid and request.args.get("joined"):
            # Trust only what Stripe says about the session, never the URL.
            sess = stripe_billing.get_checkout_session(sid)
            meta = (sess or {}).get("metadata") or {}
            if (sess and sess.get("payment_status") == "paid"
                    and meta.get("kind") == "fan_club"
                    and meta.get("artist_id") == prof["user_id"]
                    and meta.get("member_email")):
                email = meta["member_email"].lower()
                new_id = store.add_club_member(
                    prof["user_id"], email, sess.get("customer"),
                    sess.get("subscription"))
                fan_id = mls.upsert_fan(prof["user_id"], email, None)
                if new_id:
                    mls.add_consent(fan_id, None, "fan_club",
                                    "Paid fan club membership via Stripe checkout.")
                    store.notify(prof["user_id"], "fan", "New fan club member",
                                 "%s joined your fan club." % email, "/fan-club")
                session.permanent = True
                session["club_member_" + prof["user_id"]] = email
                return redirect("/club/" + slug + "/members")
        return render_template("club_public.html", club=club, slug=slug,
                               artist_name=prof["user_name"],
                               joined=bool(request.args.get("joined")),
                               stripe_live=stripe_billing.configured())

    @app.route("/club/<slug>/join", methods=["POST"])
    def club_join(slug):
        prof = store.get_epk_by_slug(slug)
        club = store.get_fan_club(prof["user_id"]) if prof else None
        if prof is None or club is None or not club["active"]:
            abort(404)
        email = (request.form.get("email") or "").strip().lower()
        if "@" not in email or not stripe_billing.configured():
            return redirect("/club/" + slug)
        session_obj = stripe_billing.create_club_checkout(
            prof["user_id"], club["name"], club["price_cents"], email, slug,
            request.url_root.rstrip("/"))
        if not session_obj or not session_obj.get("url"):
            return redirect("/club/" + slug)
        return redirect(session_obj["url"], code=303)

    def _club_serializer():
        from itsdangerous import URLSafeTimedSerializer
        return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="club-member")

    def _club_or_404(slug):
        prof = store.get_epk_by_slug(slug)
        club = store.get_fan_club(prof["user_id"]) if prof else None
        if prof is None or club is None:
            abort(404)
        return prof, club

    @app.route("/club/<slug>/members")
    def club_members_area(slug):
        # Members keep access while their subscription is active, even if the
        # artist later closes the club to new joins.
        prof, club = _club_or_404(slug)
        token = request.args.get("token")
        if token:
            from itsdangerous import BadSignature, SignatureExpired
            try:
                data = _club_serializer().loads(token, max_age=7 * 86400)
            except (BadSignature, SignatureExpired):
                data = None
            if data and data.get("artist_id") == prof["user_id"]:
                session.permanent = True
                session["club_member_" + prof["user_id"]] = data.get("email", "")
            return redirect("/club/" + slug + "/members")
        email = session.get("club_member_" + prof["user_id"])
        member = store.get_active_club_member(prof["user_id"], email) if email else None
        if member is None:
            return render_template("club_members.html", mode="gate", club=club,
                                   slug=slug, artist_name=prof["user_name"],
                                   email_live=emailer.configured(),
                                   sent=request.args.get("sent"),
                                   email_error=request.args.get("email_error"))
        return render_template("club_members.html", mode="feed", club=club,
                               slug=slug, artist_name=prof["user_name"],
                               member_email=email,
                               drops=store.list_club_drops(prof["user_id"]))

    @app.route("/club/<slug>/members/link", methods=["POST"])
    def club_members_link(slug):
        prof, club = _club_or_404(slug)
        email = (request.form.get("email") or "").strip().lower()
        member = (store.get_active_club_member(prof["user_id"], email)
                  if "@" in email else None)
        if member:
            token = _club_serializer().dumps(
                {"artist_id": prof["user_id"], "email": email})
            link = (request.url_root.rstrip("/") + "/club/" + slug
                    + "/members?token=" + token)
            ok = emailer.send(
                email, "Your %s access link" % (club["name"] or "fan club"),
                '<p>Tap to open the members area for <b>%s</b>:</p>'
                '<p><a href="%s">%s</a></p>'
                '<p style="color:#91836A;font-size:12px">The link works for 7 days '
                'and keeps you signed in on this device.</p>'
                % (club["name"] or "the fan club", link, link))
            if not ok:
                # Honesty first: the send failed (sandbox until a domain is
                # verified), so don't tell anyone to go check their inbox.
                return redirect("/club/" + slug + "/members?email_error=1")
        return redirect("/club/" + slug + "/members?sent=1")

    @app.route("/fan-club/drops", methods=["POST"])
    def fan_club_drop_post():
        user = current_user()
        if user is None:
            return login_required_redirect()
        title = (request.form.get("title") or "").strip()
        if not title:
            return redirect("/fan-club")
        body = (request.form.get("body") or "").strip()
        store.add_club_drop(user["id"], title, body,
                            (request.form.get("link_url") or "").strip())
        club = store.get_fan_club(user["id"])
        if not emailer.configured() or not club:
            return redirect("/fan-club?posted=1&email_off=1")
        import html as _html
        notified = failed = 0
        slug = _ensure_epk_slug(user)
        base = request.url_root.rstrip("/")
        for m in store.list_club_members(user["id"])[:200]:
            if m["status"] != "active":
                continue
            token = _club_serializer().dumps(
                {"artist_id": user["id"], "email": m["member_email"]})
            link = base + "/club/" + slug + "/members?token=" + token
            ok = emailer.send(
                m["member_email"],
                "%s: new members-only drop" % (club["name"] or "Fan club"),
                '<div style="font-family:sans-serif;max-width:480px">'
                '<p style="color:#8A6E30;font-weight:800;letter-spacing:2px;'
                'text-transform:uppercase;font-size:12px">%s</p>'
                '<h2 style="margin:6px 0 12px">%s</h2>%s'
                '<p style="margin-top:18px"><a href="%s" style="background:#E8B950;'
                'color:#14100A;padding:11px 20px;border-radius:10px;'
                'text-decoration:none;font-weight:800">Open the drop</a></p>'
                '<p style="color:#91836A;font-size:12px">This link signs you '
                'straight in and works for 7 days.</p></div>'
                % (_html.escape(user["name"] or "Your artist"),
                   _html.escape(title),
                   ('<p style="color:#3A3226">%s</p>' % _html.escape(body[:300])
                    if body else ""),
                   link))
            if ok:
                notified += 1
            else:
                failed += 1
        return redirect("/fan-club?posted=1&notified=%d&failed=%d"
                        % (notified, failed))

    @app.route("/fan-club/drops/<drop_id>/delete", methods=["POST"])
    def fan_club_drop_delete(drop_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        store.delete_club_drop(user["id"], drop_id)
        return redirect("/fan-club")

    # --- Label Mode: real roster seats for the Label tier -------------------------

    def _artist_snapshot(aid, today):
        rows = store.get_statement_rows(aid)
        return {
            "revenue": round(sum(r["amount"] for r in rows), 2),
            "statements": len(store.get_statements(aid)),
            "fans": len(mls.list_fans(aid)),
            "links": [c for c in mls.list_campaigns(aid)
                      if c["status"] == "live" and not c.get("archived_at")],
            "shows": [s for s in store.list_tour_shows(aid)
                      if s["date"] >= today and s["status"] in ("confirmed", "advanced")],
        }

    @app.route("/roster")
    def roster():
        user = current_user()
        if user is None:
            return login_required_redirect()
        members = store.list_roster(user["id"])
        today = datetime.now(timezone.utc).date().isoformat()
        stats, totals = [], {"revenue": 0.0, "fans": 0, "links": 0, "shows": 0}
        calendar = []
        for m in members:
            if m["status"] != "active" or not m["artist_user_id"]:
                continue
            snap = _artist_snapshot(m["artist_user_id"], today)
            _t, _c, osum, ocert = _os_full(m["artist_user_id"])
            for c in mls.list_campaigns(m["artist_user_id"]):
                rd = c.get("release_date") or ""
                if rd >= today:
                    calendar.append({"date": rd, "title": c["title"],
                                     "artist": m.get("artist_name") or m["email"]})
            stats.append({"m": m, "revenue": snap["revenue"], "fans": snap["fans"],
                          "links": len(snap["links"]), "shows": len(snap["shows"]),
                          "os": osum, "cert": ocert["level"]})
            totals["revenue"] = round(totals["revenue"] + snap["revenue"], 2)
            totals["fans"] += snap["fans"]
            totals["links"] += len(snap["links"])
            totals["shows"] += len(snap["shows"])
        calendar.sort(key=lambda c: c["date"])
        return render_template("roster.html", active_page="roster",
                               members=members, stats=stats, totals=totals,
                               calendar=calendar[:10],
                               **build_dashboard_context())

    @app.route("/roster/export.csv")
    def roster_export():
        user = current_user()
        if user is None:
            return login_required_redirect()
        import csv as _csv
        import io as _io
        today = datetime.now(timezone.utc).date().isoformat()
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["artist", "email", "statement_revenue", "fans", "live_links",
                    "upcoming_shows", "tracks", "passport_avg_pct",
                    "clean_release_avg", "red_rights_issues", "certification"])
        for m in store.list_roster(user["id"]):
            if m["status"] != "active" or not m["artist_user_id"]:
                continue
            snap = _artist_snapshot(m["artist_user_id"], today)
            _t, _c, osum, ocert = _os_full(m["artist_user_id"])
            w.writerow([m.get("artist_name") or "", m["email"], snap["revenue"],
                        snap["fans"], len(snap["links"]), len(snap["shows"]),
                        osum["tracks"], osum["passport_avg"], osum["clean_avg"],
                        osum["reds"], ocert["level"]])
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition":
                                 "attachment; filename=roster-report.csv"})

    @app.route("/roster/invite", methods=["POST"])
    def roster_invite():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if _signup_mode() == "closed":
            abort(403)
        email = (request.form.get("email") or "").strip().lower()
        if "@" in email and email != user["email"].lower():
            invite = store.add_roster_invite(user["id"], email)
            if invite and invite.get("invite_token") and emailer.configured():
                # Best-effort — the join link stays visible on the roster
                # either way, so a sandbox-blocked send loses nothing.
                link = (request.url_root.rstrip("/") + "/roster/join/"
                        + invite["invite_token"])
                emailer.send(email, "%s wants you on their roster" % user["name"],
                             '<p><b>%s</b> runs their label on Street Banker and '
                             'wants to add you to the roster (they see read-only '
                             'stats, never your login).</p>'
                             '<p><a href="%s">Accept the invite</a></p>'
                             % (user["name"], link))
        return redirect("/roster")

    @app.route("/roster/join/<token>", methods=["GET", "POST"])
    def roster_join(token):
        if _signup_mode() == "closed":
            abort(404)
        invite = store.get_roster_invite(token)
        if invite is None:
            return render_template("roster_join.html", invalid=True,
                                   invite=None, error=None, has_account=False)
        existing = store.get_user_by_email(invite["email"])
        signed_in = current_user()
        signed_in_as_invited = bool(
            existing and signed_in and existing["id"] == signed_in["id"])
        if request.method == "POST":
            if existing:
                if not signed_in_as_invited:
                    return render_template(
                        "roster_join.html", invalid=False, invite=invite,
                        has_account=True, signed_in_as_invited=False,
                        error="Sign in to the invited account before accepting."), 403
                artist_id = existing["id"]
            else:
                name = (request.form.get("name") or "").strip()
                password = request.form.get("password") or ""
                if not name or len(password) < 6:
                    return render_template(
                        "roster_join.html", invalid=False, invite=invite,
                        has_account=False, signed_in_as_invited=False,
                        error="Enter your name and a password of 6+ characters.")
                artist_id = store.create_user(invite["email"], name,
                                              generate_password_hash(password))
            store.accept_roster_invite(token, artist_id)
            store.notify(invite["label_id"], "team", "Roster invite accepted",
                         "%s is now on your roster." % invite["email"], "/roster")
            session["user_id"] = artist_id
            return redirect("/command-center")
        return render_template("roster_join.html", invalid=False, invite=invite,
                               has_account=existing is not None,
                               signed_in_as_invited=signed_in_as_invited, error=None)

    @app.route("/roster/artist/<artist_id>")
    def roster_artist(artist_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        member = store.get_roster_member(user["id"], artist_id)
        if member is None:
            abort(404)
        today = datetime.now(timezone.utc).date().isoformat()
        snap = _artist_snapshot(artist_id, today)
        return render_template("roster_artist.html", active_page="roster",
                               member=member, snap=snap,
                               **build_dashboard_context())

    @app.route("/roster/<member_id>/remove", methods=["POST"])
    def roster_remove(member_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        store.remove_roster_member(user["id"], member_id)
        return redirect("/roster")

    # --- Artist Hub: the one link-in-bio URL, assembled from real data -----------

    @app.route("/@<slug>")
    def artist_hub(slug):
        prof = store.get_epk_by_slug(slug)
        if prof is None:
            abort(404)
        uid = prof["user_id"]
        data = prof["data"]
        club = store.get_fan_club(uid)
        campaigns = [c for c in mls.list_campaigns(uid)
                     if c["status"] == "live" and not c.get("archived_at")]
        today = datetime.now(timezone.utc).date().isoformat()
        shows = [s for s in store.list_tour_shows(uid)
                 if s["date"] >= today and s["status"] in ("confirmed", "advanced")]
        return render_template("artist_hub.html", prof=prof, data=data,
                               artist_name=prof["user_name"], slug=slug,
                               club=(club if club and club["active"] else None),
                               campaigns=campaigns[:8], shows=shows[:8],
                               store_url=data.get("store_url", ""),
                               merch=data.get("merch", []))

    # --- Artist OS spine: tracks + engines ----------------------------------------

    def _os_ctx(user_id):
        """Real account signals only — every key names where it came from."""
        rows = store.get_statement_rows(user_id)
        campaigns = [c for c in mls.list_campaigns(user_id)
                     if c["status"] == "live" and not c.get("archived_at")]
        return {
            "statement_rows": len(rows),
            "statement_total": round(sum(r["amount"] for r in rows), 2),
            "lanes_with_data": artist_os.lanes_from_sources(
                r.get("source") for r in rows),
            "live_links": len(campaigns),
            "fans": len(mls.list_fans(user_id)),
            "club_members": len([m for m in store.list_club_members(user_id)
                                 if m["status"] == "active"]),
            "sync_active": bool(store.list_sync_packs(user_id)),
            # A future-dated campaign is what the scheduler and pitch
            # windows read; a rollout campaign means generated assets exist.
            "release_scheduled": any(
                (c.get("release_date") or "") >=
                datetime.now(timezone.utc).date().isoformat()
                for c in mls.list_campaigns(user_id)
                if not c.get("archived_at")),
            "rollout_assets": bool(ros.list_campaigns(user_id)),
        }

    def _os_summary(user_id, tracks, ctx):
        if not tracks:
            return {"tracks": 0, "passport_avg": 0, "clean_avg": 0, "reds": 0,
                    "lanes_connected": 0, "lockbox_ready": 0,
                    "fans": ctx["fans"], "statement_rows": ctx["statement_rows"]}
        reports = [artist_os.passport_report(t) for t in tracks]
        cleans = [artist_os.clean_release(t, ctx) for t in tracks]
        boxes = [artist_os.lockbox_report(t) for t in tracks]
        lanes = artist_os.lane_grid(tracks[0], ctx)
        return {
            "tracks": len(tracks),
            "passport_avg": round(sum(r["pct"] for r in reports) / len(reports)),
            "clean_avg": round(sum(c["score"] for c in cleans) / len(cleans)),
            "reds": sum(r["reds"] for r in reports),
            "lanes_connected": len([l for l in lanes if l["state"] == "connected"]),
            "lockbox_ready": len([b for b in boxes if b["caps"]["release"]]),
            "fans": ctx["fans"], "statement_rows": ctx["statement_rows"],
        }

    @app.route("/tracks")
    def os_tracks():
        user = current_user()
        if user is None:
            return login_required_redirect()
        tracks = store.list_os_tracks(user["id"])
        ctx = _os_ctx(user["id"])
        rows = [{"t": t,
                 "passport": artist_os.passport_report(t),
                 "clean": artist_os.clean_release(t, ctx),
                 "caps": artist_os.lockbox_report(t)["caps"]}
                for t in tracks]
        summary = _os_summary(user["id"], tracks, ctx)
        # Pipeline stages, each computed from real row state.
        pipeline = [
            ("In catalog", len(rows)),
            ("Metadata complete", len([r for r in rows
                                       if r["passport"]["pct"] == 100])),
            ("Rights signed", len([r for r in rows if r["caps"]["release"]])),
            ("Release-ready", len([r for r in rows
                                   if not r["clean"]["blocked"]
                                   and r["clean"]["score"] >= 80])),
        ]
        return render_template("os_tracks.html", active_page="tracks",
                               rows=rows, pipeline=pipeline,
                               cert=artist_os.certification(summary),
                               summary=summary,
                               **build_dashboard_context())

    # CSV column -> passport field, for catalog migrations.
    _CSV_PASSPORT = {"isrc": "isrc", "upc": "upc", "writers": "songwriters",
                     "songwriters": "songwriters", "producers": "producers",
                     "publishers": "publishers", "pro": "pro",
                     "label": "label", "master_owner": "master_owner"}

    @app.route("/tracks/import", methods=["POST"])
    def os_tracks_import():
        """Bulk CSV import: title required per row; known metadata columns
        land straight in each new passport."""
        user = current_user()
        if user is None:
            return login_required_redirect()
        f = request.files.get("csv")
        if f is None or not f.filename:
            return redirect("/tracks")
        import csv as _csv
        import io as _io
        try:
            text = f.read().decode("utf-8-sig", errors="replace")
            reader = _csv.DictReader(_io.StringIO(text))
            made = 0
            for row in reader:
                if made >= 200:
                    break
                low = {(k or "").strip().lower(): (v or "").strip()
                       for k, v in row.items()}
                title = low.get("title") or low.get("track") or low.get("track_title")
                if not title:
                    continue
                tid = store.add_os_track(user["id"], title[:120],
                                         (low.get("release") or low.get("album") or "")[:120],
                                         (low.get("release_date") or low.get("date") or "")[:10])
                passport = {pf: low[col] for col, pf in _CSV_PASSPORT.items()
                            if low.get(col)}
                if passport:
                    store.update_os_track_passport(user["id"], tid, passport)
                made += 1
        except (UnicodeDecodeError, _csv.Error):
            pass
        return redirect("/tracks")

    @app.route("/tracks/add", methods=["POST"])
    def os_tracks_add():
        user = current_user()
        if user is None:
            return login_required_redirect()
        title = (request.form.get("title") or "").strip()
        if title:
            store.add_os_track(user["id"], title,
                               (request.form.get("release_title") or "").strip(),
                               (request.form.get("release_date") or "").strip())
        return redirect("/tracks")

    @app.route("/tracks/<track_id>")
    def os_track_detail(track_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        track = store.get_os_track(user["id"], track_id)
        if track is None:
            abort(404)
        ctx = _os_ctx(user["id"])
        return render_template("os_track_detail.html", active_page="tracks",
                               track=track,
                               passport=artist_os.passport_report(track),
                               clean=artist_os.clean_release(track, ctx),
                               lanes=artist_os.lane_grid(track, ctx),
                               lockbox=artist_os.lockbox_report(track),
                               fields=artist_os.PASSPORT_FIELDS,
                               **build_dashboard_context())

    @app.route("/tracks/<track_id>/passport", methods=["POST"])
    def os_track_passport(track_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        track = store.get_os_track(user["id"], track_id)
        if track is None:
            abort(404)
        passport = track["passport"]
        for key, _label, _crit, _fix in artist_os.PASSPORT_FIELDS:
            passport[key] = (request.form.get(key) or "").strip()[:200]
        for extra in ("audio_ok", "artwork_ok"):
            passport[extra] = "1" if request.form.get(extra) else ""
        store.update_os_track_passport(user["id"], track_id, passport)
        return redirect("/tracks/" + track_id)

    @app.route("/royalty-lanes")
    def royalty_lanes():
        user = current_user()
        if user is None:
            return login_required_redirect()
        tracks = store.list_os_tracks(user["id"])
        ctx = _os_ctx(user["id"])
        rows = [{"t": t, "lanes": artist_os.lane_grid(t, ctx)} for t in tracks]
        claimed = len([l for r in rows for l in r["lanes"] if l["state"] == "claimed"])
        missing_est = round(sum(l["estimate"] or 0 for r in rows for l in r["lanes"]), 2)
        return render_template("royalty_lanes.html", active_page="royalty-lanes",
                               rows=rows, lanes=artist_os.LANES,
                               claimed=claimed, missing_est=missing_est, ctx=ctx,
                               **build_dashboard_context())

    @app.route("/money-queue")
    def money_queue():
        user = current_user()
        if user is None:
            return login_required_redirect()
        tracks = store.list_os_tracks(user["id"])
        ctx = _os_ctx(user["id"])
        queue = artist_os.action_queue([(t, ctx) for t in tracks])
        est_total = round(sum(a["impact"] or 0 for a in queue), 2)
        criticals = len([a for a in queue if a["critical"]])
        # Settled tour income: real walk-away totals from settled shows —
        # money already collected, shown beside the money still missing.
        tour_income, tour_settled = 0.0, 0
        for s in store.list_tour_shows(user["id"]):
            if s["status"] != "settled":
                continue
            try:
                st = json.loads(s.get("settlement") or "{}")
            except ValueError:
                continue
            if st:
                tour_income = round(
                    tour_income + touring.settlement_totals(st)["walk"], 2)
                tour_settled += 1
        return render_template("money_queue.html", active_page="money-queue",
                               queue=queue, est_total=est_total,
                               criticals=criticals, ctx=ctx,
                               tour_income=tour_income,
                               tour_settled=tour_settled,
                               **build_dashboard_context())

    def _os_full(user_id):
        tracks = store.list_os_tracks(user_id)
        ctx = _os_ctx(user_id)
        summary = _os_summary(user_id, tracks, ctx)
        return tracks, ctx, summary, artist_os.certification(summary)

    @app.route("/certified")
    def certified_page():
        user = current_user()
        if user is None:
            return login_required_redirect()
        tracks, ctx, summary, cert = _os_full(user["id"])
        return render_template("certified.html", active_page="certified",
                               cert=cert, summary=summary,
                               **build_dashboard_context())

    @app.route("/deal-room/onesheet")
    def deal_onesheet():
        user = current_user()
        if user is None:
            return login_required_redirect()
        tracks, ctx, summary, cert = _os_full(user["id"])
        reports = sorted(
            [{"t": t, "clean": artist_os.clean_release(t, ctx)} for t in tracks],
            key=lambda r: -r["clean"]["score"])
        pulse = store.list_pulse_snapshots(user["id"], limit=30)
        upcoming = [c for c in mls.list_campaigns(user["id"])
                    if (c.get("release_date") or "") >=
                    datetime.now(timezone.utc).date().isoformat()]
        lanes = artist_os.lane_grid(tracks[0], ctx) if tracks else []
        share = store.get_onesheet_share(user["id"])
        vault = store.list_vault_files(user["id"])
        vault_images = [v for v in vault if v["path"].rsplit(".", 1)[-1].lower()
                        in ("png", "jpg", "jpeg", "webp", "gif")]
        vault_audio = [v for v in vault if v["path"].rsplit(".", 1)[-1].lower()
                       in ("wav", "mp3", "flac")]
        views = (store.onesheet_view_stats(share["token"])
                 if share else {"total": 0, "recent": []})
        return render_template("deal_onesheet.html", user=user, cert=cert,
                               summary=summary, reports=reports[:6],
                               pulse=pulse, upcoming=upcoming[:5],
                               lanes_claimed=[l for l in lanes
                                              if l["state"] == "claimed"],
                               ctx=ctx, share=share, views=views,
                               vault_images=vault_images,
                               vault_audio=vault_audio,
                               today=datetime.now(timezone.utc).date().isoformat())

    @app.route("/onesheet/share", methods=["POST"])
    def onesheet_share_save():
        """Share settings: everything on the public sheet resolves through the
        artist's own vault listing — nothing else is reachable by id."""
        user = current_user()
        if user is None:
            return login_required_redirect()
        action = request.form.get("action") or "save"
        if action == "disable":
            store.delete_onesheet_share(user["id"])
            return redirect("/deal-room/onesheet")
        share = store.get_onesheet_share(user["id"])
        token = (uuid.uuid4().hex[:20] if (share is None or action == "regenerate")
                 else share["token"])
        pin = "".join(c for c in (request.form.get("pin") or "") if c.isdigit())[:8]
        if pin and len(pin) < 4:
            pin = ""
        vault = {v["id"]: v for v in store.list_vault_files(user["id"])}
        banner = ""
        pick = request.form.get("banner") or ""
        if pick in vault and vault[pick]["path"].rsplit(".", 1)[-1].lower() in (
                "png", "jpg", "jpeg", "webp", "gif"):
            banner = vault[pick]["path"]
        audio = []
        for vid in request.form.getlist("audio")[:3]:
            v = vault.get(vid)
            if v and v["path"].rsplit(".", 1)[-1].lower() in ("wav", "mp3", "flac"):
                audio.append({"path": v["path"],
                              "label": v["label"] or "Untitled"})
        store.upsert_onesheet_share(user["id"], token, pin, banner, audio)
        return redirect("/deal-room/onesheet")

    def _sheet_context(share):
        owner = store.get_user(share["user_id"])
        if owner is None:
            abort(404)
        tracks, ctx, summary, cert = _os_full(owner["id"])
        reports = sorted(
            [{"t": t, "clean": artist_os.clean_release(t, ctx)} for t in tracks],
            key=lambda r: -r["clean"]["score"])
        upcoming = [c for c in mls.list_campaigns(owner["id"])
                    if (c.get("release_date") or "") >=
                    datetime.now(timezone.utc).date().isoformat()]
        return owner, summary, cert, reports[:3], upcoming[:3]

    @app.route("/sheet/<token>", methods=["GET", "POST"])
    def sheet_public(token):
        share = store.get_onesheet_share_by_token(token)
        if share is None:
            abort(404)
        pin_ok_key = "sheet_ok_" + token
        if share["pin"] and not session.get(pin_ok_key):
            if request.method == "POST":
                if (request.form.get("pin") or "").strip() == share["pin"]:
                    session[pin_ok_key] = True
                    return redirect("/sheet/" + token)
                owner = store.get_user(share["user_id"])
                return render_template("sheet_public.html", mode="pin",
                                       token=token, bad_pin=True,
                                       artist=(owner or {}).get("name", "")), 403
            owner = store.get_user(share["user_id"])
            return render_template("sheet_public.html", mode="pin", token=token,
                                   bad_pin=False,
                                   artist=(owner or {}).get("name", ""))
        owner, summary, cert, reports, upcoming = _sheet_context(share)
        viewer = current_user()
        if viewer is None or viewer["id"] != owner["id"]:
            store.log_onesheet_view(token)
        return render_template("sheet_public.html", mode="sheet", token=token,
                               owner=owner, summary=summary, cert=cert,
                               reports=reports, upcoming=upcoming, share=share,
                               sent=request.args.get("sent") == "1",
                               today=datetime.now(timezone.utc).date().isoformat())

    @app.route("/sheet/<token>/media/<kind>/<int:index>")
    def sheet_media(token, kind, index):
        share = store.get_onesheet_share_by_token(token)
        if share is None:
            abort(404)
        if share["pin"] and not session.get("sheet_ok_" + token):
            abort(404)
        if kind == "banner" and index == 0 and share.get("banner"):
            path = share["banner"]
        elif kind == "audio" and 0 <= index < len(share["audio"]):
            path = share["audio"][index]["path"]
        else:
            abort(404)
        return _serve_asset_path(path, public=False)

    @app.route("/sheet/<token>/pitch", methods=["POST"])
    def sheet_pitch(token):
        share = store.get_onesheet_share_by_token(token)
        if share is None:
            abort(404)
        if (request.form.get("website") or "").strip():
            return redirect("/sheet/" + token)  # honeypot: silently drop bots
        name = (request.form.get("name") or "").strip()[:120]
        email = (request.form.get("email") or "").strip()[:200]
        message = (request.form.get("message") or "").strip()[:2000]
        if "@" not in email or not message:
            return redirect("/sheet/" + token)
        owner = store.get_user(share["user_id"])
        store.add_inbox("onesheet_pitch", {
            "artist_id": share["user_id"],
            "artist": (owner or {}).get("name", ""),
            "name": name, "email": email, "message": message},
            user_id=share["user_id"])
        store.notify(share["user_id"], "pitch",
                     "One-sheet pitch from %s" % (name or email),
                     message[:300], "/reports")
        return redirect("/sheet/" + token + "?sent=1")

    _LOCKBOX_KEYS = tuple(k for k, _l, _r in artist_os.LOCKBOX_DOCS)

    @app.route("/tracks/<track_id>/lockbox/<doc_key>", methods=["POST"])
    def os_lockbox_update(track_id, doc_key):
        user = current_user()
        if user is None:
            return login_required_redirect()
        track = store.get_os_track(user["id"], track_id)
        if track is None or doc_key not in _LOCKBOX_KEYS:
            abort(404)
        box = track["lockbox"]
        entry = box.get(doc_key) or {}
        action = request.form.get("action") or ""
        if action == "na":
            entry["not_applicable"] = not entry.get("not_applicable")
        elif action == "upload":
            f = request.files.get("file")
            if f and f.filename:
                fname = uuid.uuid4().hex + "-" + os.path.basename(f.filename)[-60:]
                f.save(os.path.join(UPLOADS_DIR, fname))
                entry["file"] = "/uploads/" + fname
                entry["not_applicable"] = False
        elif action in ("approver", "resend"):
            email = (request.form.get("email") or "").strip().lower()
            name = (request.form.get("name") or "").strip()
            if "@" in email:
                token = uuid.uuid4().hex
                approvals = entry.setdefault("approvals", [])
                existing = [a for a in approvals if a.get("email") == email]
                if action == "resend" and existing:
                    existing[0]["state"] = "pending"
                    existing[0]["token"] = token
                elif not existing:
                    approvals.append({"name": name[:80], "email": email,
                                      "state": "pending", "token": token})
                store.add_sign_token(token, user["id"], track_id, doc_key, email)
                if emailer.configured():
                    # Best-effort: the sign link also stays visible on the page.
                    doc_label = dict((k, l) for k, l, _r in artist_os.LOCKBOX_DOCS)[doc_key]
                    link = request.url_root.rstrip("/") + "/sign/" + token
                    emailer.send(email,
                                 "Signature needed: %s — %s" % (doc_label, track["title"]),
                                 '<p><b>%s</b> needs your sign-off on the %s for '
                                 '\u201c%s\u201d.</p><p><a href="%s">Review and sign</a></p>'
                                 % (user["name"], doc_label.lower(),
                                    track["title"], link))
        box[doc_key] = entry
        store.update_os_track_lockbox(user["id"], track_id, box)
        return redirect("/tracks/" + track_id)

    @app.route("/sign/<token>", methods=["GET", "POST"])
    def sign_document(token):
        row = store.get_sign_token(token)
        if row is None:
            return render_template("sign.html", invalid=True, row=None,
                                   doc_label=None, track=None, done=None)
        track = store.get_os_track(row["user_id"], row["track_id"])
        doc_label = dict((k, l) for k, l, _r in artist_os.LOCKBOX_DOCS).get(row["doc_key"])
        if track is None or doc_label is None:
            return render_template("sign.html", invalid=True, row=None,
                                   doc_label=None, track=None, done=None)
        entry = (track["lockbox"] or {}).get(row["doc_key"]) or {}
        approval = next((a for a in entry.get("approvals", [])
                         if a.get("email") == row["email"]), None)
        if request.method == "POST" and not row["used"] and approval:
            decision = request.form.get("decision")
            if decision in ("signed", "declined"):
                approval["state"] = decision
                store.update_os_track_lockbox(row["user_id"], row["track_id"],
                                              track["lockbox"])
                store.use_sign_token(token)
                store.notify(row["user_id"], "team",
                             "%s %s the %s" % (approval.get("name") or row["email"],
                                               decision, doc_label.lower()),
                             "Track: %s." % track["title"],
                             "/tracks/" + row["track_id"])
                return render_template("sign.html", invalid=False, row=row,
                                       doc_label=doc_label, track=track,
                                       done=decision)
        return render_template("sign.html", invalid=False, row=row,
                               doc_label=doc_label, track=track,
                               done=("signed" if row["used"] else None),
                               file_url=entry.get("file", ""))

    @app.route("/tracks/<track_id>/delete", methods=["POST"])
    def os_track_delete(track_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        store.delete_os_track(user["id"], track_id)
        return redirect("/tracks")

    # --- Tour Hub + Stage Plot ---------------------------------------------------

    _SHOW_STATUSES = ("hold", "confirmed", "advanced", "played", "settled")

    @app.route("/tour")
    def tour_hub():
        user = current_user()
        if user is None:
            return login_required_redirect()
        shows = store.list_tour_shows(user["id"])
        today = datetime.now(timezone.utc).date().isoformat()
        upcoming = [s for s in shows if s["date"] >= today]
        # Per-show walk-away from each saved settlement — same math the
        # settlement calculator shows, summed only where numbers exist.
        pnl = {"guarantee": 0.0, "door_share": 0.0, "merch_net": 0.0,
               "expenses": 0.0, "walk": 0.0, "count": 0, "settled": 0}
        for s in shows:
            try:
                st = json.loads(s.get("settlement") or "{}")
            except ValueError:
                st = {}
            s["walk"] = None
            if st and s["status"] in ("played", "settled"):
                totals = touring.settlement_totals(st)
                s["walk"] = totals["walk"]
                for k in ("guarantee", "door_share", "merch_net",
                          "expenses", "walk"):
                    pnl[k] = round(pnl[k] + totals[k], 2)
                pnl["count"] += 1
                if s["status"] == "settled":
                    pnl["settled"] += 1
        # Travel flags: consecutive upcoming dates in different cities with
        # 0-1 days between them. Date math only — we don't invent drive hours.
        flags = []
        route = []
        prev = None
        for s in upcoming:
            gap = None
            if prev is not None:
                try:
                    gap = (date.fromisoformat(s["date"][:10])
                           - date.fromisoformat(prev["date"][:10])).days
                except ValueError:
                    gap = None
                cities_differ = (prev["city"] and s["city"] and
                                 prev["city"].casefold() != s["city"].casefold())
                if gap is not None and gap <= 1 and cities_differ:
                    flags.append({"a": prev, "b": s, "gap": gap})
            route.append({"show": s, "gap": gap})
            prev = s
        return render_template("tour.html", active_page="tour",
                               shows=shows, statuses=_SHOW_STATUSES,
                               upcoming_count=len(upcoming),
                               confirmed_count=len([s for s in shows if s["status"]
                                                    in ("confirmed", "advanced")]),
                               next_show=(upcoming[0] if upcoming else None),
                               pnl=pnl, flags=flags, route=route,
                               board=(request.args.get("view") == "board"),
                               **build_dashboard_context())

    @app.route("/tour/add", methods=["POST"])
    def tour_add():
        user = current_user()
        if user is None:
            return login_required_redirect()
        date_str = (request.form.get("date") or "").strip()
        venue = (request.form.get("venue") or "").strip()
        if date_str and venue:
            store.add_tour_show(user["id"], date_str, venue,
                                (request.form.get("city") or "").strip(),
                                (request.form.get("notes") or "").strip())
        return redirect("/tour")

    @app.route("/tour/<show_id>/status", methods=["POST"])
    def tour_status(show_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        status = request.form.get("status") or ""
        if status in _SHOW_STATUSES:
            store.update_tour_show_status(user["id"], show_id, status)
        return redirect("/tour")

    @app.route("/tour/<show_id>/delete", methods=["POST"])
    def tour_delete(show_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        store.delete_tour_show(user["id"], show_id)
        return redirect("/tour")

    @app.route("/tour/<show_id>")
    def tour_show_detail(show_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        show = store.get_tour_show(user["id"], show_id)
        if show is None:
            abort(404)
        share_url = ((request.url_root.rstrip("/") + "/showday/" + show["share_token"])
                     if show.get("share_token") else None)
        rider_url = ((request.url_root.rstrip("/") + "/rider/" + show["share_token"])
                     if show.get("share_token") else None)
        return render_template("tour_show.html", active_page="tour", show=show,
                               rider_url=rider_url,
                               fields=touring.ADVANCE_FIELDS,
                               checklist=touring.checklist(show["advance"]),
                               prog=touring.progress(show["advance"]),
                               email_preview=touring.advance_email(
                                   show, show["advance"],
                                   user["name"] or "We", share_url),
                               share_url=share_url,
                               totals=touring.settlement_totals(show["settlement"]),
                               email_live=emailer.configured(),
                               statuses=_SHOW_STATUSES,
                               **build_dashboard_context())

    @app.route("/tour/<show_id>/advance", methods=["POST"])
    def tour_show_advance(show_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        advance = {k: (request.form.get(k) or "").strip()[:300]
                   for k in touring.FIELD_KEYS}
        store.save_show_advance(user["id"], show_id, advance)
        return redirect("/tour/" + show_id)

    @app.route("/tour/<show_id>/settlement", methods=["POST"])
    def tour_show_settlement(show_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        settlement = {k: (request.form.get(k) or "").strip()[:60]
                      for k in ("deal_type", "guarantee", "door_gross", "split_pct",
                                "merch_gross", "merch_cut_pct", "expenses", "notes")}
        store.save_show_settlement(user["id"], show_id, settlement)
        if request.form.get("mark_settled"):
            store.update_tour_show_status(user["id"], show_id, "settled")
        return redirect("/tour/" + show_id)

    @app.route("/tour/<show_id>/share", methods=["POST"])
    def tour_show_share(show_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        store.set_show_share_token(user["id"], show_id, uuid.uuid4().hex)
        return redirect("/tour/" + show_id)

    @app.route("/tour/<show_id>/send-advance", methods=["POST"])
    def tour_send_advance(show_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        show = store.get_tour_show(user["id"], show_id)
        if show is None:
            abort(404)
        to = (show["advance"].get("contact_email") or "").strip()
        if not (to and "@" in to and emailer.configured()):
            return redirect("/tour/" + show_id + "?email_fail=1")
        share_url = ((request.url_root.rstrip("/") + "/showday/" + show["share_token"])
                     if show.get("share_token") else None)
        mail = touring.advance_email(show, show["advance"],
                                     user["name"] or "The artist", share_url)
        import html as _html
        ok = emailer.send(to, mail["subject"],
                          '<pre style="font-family:inherit;white-space:pre-wrap">%s</pre>'
                          % _html.escape(mail["body"]))
        return redirect("/tour/" + show_id + ("?sent=1" if ok else "?email_fail=1"))

    @app.route("/showday/<token>")
    def showday(token):
        import json as _json
        show = store.get_show_by_share_token(token)
        if show is None:
            abort(404)
        adv = show["advance"]
        schedule = [(label, adv.get(key)) for key, label in (
            ("load_in", "Load-in"), ("soundcheck", "Soundcheck"), ("doors", "Doors"),
            ("set_time", "Set"), ("curfew", "Curfew")) if (adv.get(key) or "").strip()]
        plot = store.get_stage_plot(show["user_id"])
        return render_template("showday.html", show=show, adv=adv,
                               schedule=schedule,
                               plot_json=(_json.dumps(plot) if plot else "null"))

    @app.route("/rider/<token>")
    def tech_rider(token):
        # Public tech rider for venue staff: stage plot + input list, schedule,
        # backline, and the lighting rig — everything real, nothing invented.
        import json as _json
        show = store.get_show_by_share_token(token)
        if show is None:
            abort(404)
        adv = show["advance"]
        schedule = [(label, adv.get(key)) for key, label in (
            ("load_in", "Load-in"), ("soundcheck", "Soundcheck"), ("doors", "Doors"),
            ("set_time", "Set"), ("curfew", "Curfew")) if (adv.get(key) or "").strip()]
        plot = store.get_stage_plot(show["user_id"])
        lightshow = store.get_light_show(show["user_id"])
        lights = None
        if lightshow:
            lights = {"name": lightshow.get("name") or "",
                      "bars": int(lightshow.get("bars") or 0),
                      "chans": int(lightshow.get("chans") or 3),
                      "cues": len(lightshow.get("cues") or [])}
        return render_template("rider.html", show=show, adv=adv,
                               schedule=schedule, lights=lights,
                               plot_json=(_json.dumps(plot) if plot else "null"))

    @app.route("/lights")
    def lights():
        import json as _json
        user = current_user()
        if user is None:
            return login_required_redirect()
        saved = store.get_light_show(user["id"])
        library = {
            "shows": [{"id": s["id"], "name": s["name"], "cue_count": s["cue_count"],
                       "track_id": s["track_id"], "tour_show_id": s["tour_show_id"],
                       "updated": s["updated"]} for s in lights_store.list_shows(user["id"])],
            "rigs": _lights_rigs(user["id"]),
            "setlists": lights_store.list_setlists(user["id"]),
            "track_shows": lights_store.tracks_with_shows(user["id"]),
        }
        tracks = [{"id": t["id"], "title": t["title"]} for t in store.list_os_tracks(user["id"])]
        # venue_key lets the page pick the rig bound to the room without a
        # round trip when a show is linked to a tour date.
        tour_shows = [{"id": s["id"], "date": s["date"], "venue": s["venue"], "city": s.get("city") or "",
                       "venue_key": lights_store.venue_key(s["venue"])}
                      for s in store.list_tour_shows(user["id"])]
        return render_template("lights.html", active_page="lights",
                               saved_show=(_json.dumps(saved) if saved else "null"),
                               lights_library=_json.dumps(library),
                               lights_tracks=tracks, lights_tour_shows=tour_shows,
                               **build_dashboard_context())

    @app.route("/lights/save", methods=["POST"])
    def lights_save():
        """The working copy - one per account, what the page opens with.
        Autosave writes here; the library below is the named shows."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        store.save_light_show(user["id"], request.get_json(silent=True) or {})
        return jsonify({"ok": True})

    def _lights_shows(user_id):
        return [{"id": s["id"], "name": s["name"], "cue_count": s["cue_count"],
                 "track_id": s["track_id"], "tour_show_id": s["tour_show_id"],
                 "updated": s["updated"]} for s in lights_store.list_shows(user_id)]

    @app.route("/lights/library")
    def lights_library():
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        return jsonify({"ok": True, "shows": _lights_shows(user["id"])})

    @app.route("/lights/library/save", methods=["POST"])
    def lights_library_save():
        """Explicit save -> new version snapshot; autosave -> update in
        place. Track and tour-date links are validated against the
        caller's own rows; anything else is dropped, not stored."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        body = request.get_json(silent=True) or {}
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        track_id = (body.get("track_id") or "") or None
        if track_id and store.get_os_track(user["id"], track_id) is None:
            track_id = None
        tour_show_id = (body.get("tour_show_id") or "") or None
        if tour_show_id and store.get_tour_show(user["id"], tour_show_id) is None:
            tour_show_id = None
        show_id = lights_store.save_show(
            user["id"], body.get("id") or None, body.get("name") or data.get("name") or "Untitled show",
            data, track_id, tour_show_id, version=not body.get("autosave"),
            note=str(body.get("note") or "")[:200])
        return jsonify({"ok": True, "id": show_id, "shows": _lights_shows(user["id"]),
                        "versions": len(lights_store.list_versions(user["id"], show_id))})

    @app.route("/lights/library/<show_id>")
    def lights_library_get(show_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        s = lights_store.get_show(user["id"], show_id)
        if s is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "show": s})

    @app.route("/lights/library/<show_id>/versions")
    def lights_library_versions(show_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        if lights_store.get_show(user["id"], show_id) is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "versions": lights_store.list_versions(user["id"], show_id)})

    @app.route("/lights/library/<show_id>/restore", methods=["POST"])
    def lights_library_restore(show_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        body = request.get_json(silent=True) or {}
        v = lights_store.get_version(user["id"], body.get("version_id") or "")
        if v is None or v["show_id"] != show_id:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "data": v["data"]})

    @app.route("/lights/library/<show_id>/delete", methods=["POST"])
    def lights_library_delete(show_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        lights_store.delete_show(user["id"], show_id)
        return jsonify({"ok": True, "shows": _lights_shows(user["id"])})

    # --- sharing a show for notes (epic 5) ------------------------------
    # The designer sends one show and asks what people think. The link
    # carries that show and nothing else about the account, and no audio -
    # the song never left the designer's machine to begin with.

    # The reader needs the light show: cues, the rig they render on, the
    # looks and the patch. Everything else in a saved show is the
    # designer's own bookkeeping and has no business on a public link.
    _SHARED_SHOW_KEYS = ("cues", "bars", "chans", "looks", "sections", "stops",
                         "bpm", "beatOffset", "rigName", "dmxStart", "dmxUniverse", "dmxAddr")

    def _share_payload(share):
        """What a share link is allowed to reveal. Assembled field by
        field rather than handing over the row, so a column added to
        light_show_library later cannot quietly start travelling — and
        the show blob is filtered to a whitelist for the same reason:
        `trackId`, `tourShowId` and `libraryId` are account-internal ids
        that a tour manager has no reason to receive."""
        show = share["show"]
        data = show["data"] if isinstance(show["data"], dict) else {}
        return {
            "name": show["name"],
            "data": {k: data[k] for k in _SHARED_SHOW_KEYS if k in data},
            "updated": show["updated"],
            "cue_count": show["cue_count"],
            "permission": share["permission"],
        }

    @app.route("/lights/library/<show_id>/share", methods=["POST"])
    def lights_share_create(show_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        body = request.get_json(silent=True) or {}
        token = lights_store.create_share(user["id"], show_id,
                                          permission=body.get("permission") or "read",
                                          label=body.get("label") or "")
        if token is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "token": token,
                        "url": "%s/lights/show/%s" % (_remote_origin(), token),
                        "shares": lights_store.list_shares(user["id"], show_id)})

    @app.route("/lights/library/<show_id>/shares")
    def lights_share_list(show_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        return jsonify({"ok": True, "shares": lights_store.list_shares(user["id"], show_id),
                        "origin": _remote_origin()})

    @app.route("/lights/share/<token>/revoke", methods=["POST"])
    def lights_share_revoke(token):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        if not lights_store.revoke_share(user["id"], token):
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True})

    @app.route("/lights/show/<token>")
    def lights_share_page(token):
        """Public on purpose: the unguessable token is the authorisation,
        like every other share link on the platform. Standalone template —
        it must render for someone with no account."""
        share = lights_store.get_share(token)
        if share is None:
            return render_template("lights_share.html", gone=True, token=""), 404
        return render_template("lights_share.html", gone=False, token=token,
                               share=_share_payload(share),
                               comments=lights_store.list_comments(share["show_id"]))

    @app.route("/lights/show/<token>/comments")
    def lights_share_comments(token):
        share = lights_store.get_share(token)
        if share is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "comments": lights_store.list_comments(share["show_id"])})

    @app.route("/lights/show/<token>/comment", methods=["POST"])
    def lights_share_comment(token):
        share = lights_store.get_share(token)
        if share is None:
            return jsonify({"ok": False}), 404
        if share["permission"] != "comment":
            return jsonify({"ok": False, "error": "read-only"}), 403
        body = request.get_json(silent=True) or {}
        cid = lights_store.add_comment(share["show_id"], share["user_id"],
                                       body.get("author") or "", body.get("body") or "",
                                       t=body.get("t"), parent_id=body.get("parent_id") or "")
        if cid is None:
            return jsonify({"ok": False, "error": "empty"}), 400
        return jsonify({"ok": True, "id": cid,
                        "comments": lights_store.list_comments(share["show_id"])})

    @app.route("/lights/library/<show_id>/comments")
    def lights_comments_list(show_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        if lights_store.get_show(user["id"], show_id) is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "comments": lights_store.list_comments(show_id)})

    @app.route("/lights/library/<show_id>/comment", methods=["POST"])
    def lights_comment_add(show_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        if lights_store.get_show(user["id"], show_id) is None:
            return jsonify({"ok": False}), 404
        body = request.get_json(silent=True) or {}
        cid = lights_store.add_comment(show_id, user["id"], user.get("name") or "You",
                                       body.get("body") or "", t=body.get("t"),
                                       parent_id=body.get("parent_id") or "")
        if cid is None:
            return jsonify({"ok": False}), 400
        return jsonify({"ok": True, "id": cid, "comments": lights_store.list_comments(show_id)})

    @app.route("/lights/comments/<comment_id>/resolve", methods=["POST"])
    def lights_comment_resolve(comment_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        body = request.get_json(silent=True) or {}
        if not lights_store.resolve_comment(user["id"], comment_id, bool(body.get("resolved", True))):
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True})

    @app.route("/lights/comments/<comment_id>/delete", methods=["POST"])
    def lights_comment_delete(comment_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        if not lights_store.delete_comment(user["id"], comment_id):
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True})

    # Mirrors LOOKS in static/js/lights-engine.js — the phone shows the
    # names and swatches, the laptop owns what they actually do. Order is
    # the contract: the phone sends the index, not a colour.
    _LIGHT_REMOTE_LOOKS = [
        # sb-keep: stage gels, not interface. These are the colours the
        # lamps make; the design tokens have no business here.
        {"name": "Amber wash", "color": "#ffb347"}, {"name": "Cold blue", "color": "#3b82f6"},
        {"name": "Red alert", "color": "#ff2d2d"}, {"name": "White full", "color": "#ffffff"},
        {"name": "Violet haze", "color": "#8b5cf6"}, {"name": "Blackout", "color": "#000000"},
    ]

    def _remote_origin():
        """Where the phone should point.

        Unlike a share link, this one is scanned off the operator's own
        screen seconds after it is made, so it has to be the host the
        laptop is actually being served from — a local run, a self-hosted
        box, or the public site. PUBLIC_BASE_URL is only the fallback.
        """
        host = request.host
        if not host:
            return PUBLIC_BASE_URL
        scheme = request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip() or request.scheme
        return "%s://%s" % ("https" if scheme == "https" else "http", host)

    @app.route("/lights/remote/start", methods=["POST"])
    def lights_remote_start():
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        code = lights_store.start_remote(user["id"])
        return jsonify({"ok": True, "code": code,
                        "url": "%s/lights/remote/%s" % (_remote_origin(), code)})

    @app.route("/lights/remote/end", methods=["POST"])
    def lights_remote_end():
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        lights_store.end_remote(user["id"])
        return jsonify({"ok": True})

    @app.route("/lights/remote/poll")
    def lights_remote_poll():
        """The laptop drains whatever the phone has sent. The laptop stays
        the source of truth; this only carries button presses."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        return jsonify(dict(lights_store.drain_remote_commands(user["id"]), ok=True))

    @app.route("/lights/remote/<code>")
    def lights_remote_page(code):
        """The phone page. Public on purpose - the unguessable code in the
        URL is the authorisation, exactly like a share link, so a second
        operator can pick it up without an account. It carries no show
        data: only buttons."""
        session_row = lights_store.get_remote(code)
        if session_row is None:
            return render_template("lights_remote.html", code="", expired=True,
                                   looks=[]), 404
        return render_template("lights_remote.html", code=code, expired=False,
                               looks=[(i + 1, l["name"], l["color"]) for i, l in enumerate(_LIGHT_REMOTE_LOOKS)])

    @app.route("/lights/remote/<code>/cmd", methods=["POST"])
    def lights_remote_cmd(code):
        body = request.get_json(silent=True) or {}
        ok = lights_store.push_remote_command(code, body.get("kind") or "", body.get("value") or "")
        if not ok:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True})

    @app.route("/lights/remote/<code>/qr.svg")
    def lights_remote_qr(code):
        user = current_user()
        if user is None:
            return "", 401
        import segno
        import io as _io
        url = "%s/lights/remote/%s" % (PUBLIC_BASE_URL.rstrip("/"), code)
        buf = _io.BytesIO()
        segno.make(url, error="m").save(buf, kind="svg", scale=5, dark="#E8B950", light=None)
        return Response(buf.getvalue(), mimetype="image/svg+xml",
                        headers={"Cache-Control": "no-store"})

    @app.route("/lights/track/<track_id>/attach", methods=["POST"])
    def lights_track_attach(track_id):
        """Make the show travel with the song. Only the caller's own track."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        body = request.get_json(silent=True) or {}
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        entry = lights_store.attach_to_track(user["id"], track_id,
                                             body.get("name") or data.get("name") or "Untitled show",
                                             data, body.get("show_id") or "")
        if entry is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "attached": {"name": entry["name"], "cue_count": entry["cue_count"],
                                                 "saved_at": entry["saved_at"]},
                        "tracks": lights_store.tracks_with_shows(user["id"])})

    @app.route("/lights/track/<track_id>/show")
    def lights_track_show(track_id):
        """Pull the show attached to a track so it can be rendered on this
        account's own rig."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        entry = lights_store.show_on_track(user["id"], track_id)
        if entry is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "show": entry})

    @app.route("/lights/setlists")
    def lights_setlists():
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        return jsonify({"ok": True, "setlists": lights_store.list_setlists(user["id"])})

    @app.route("/lights/setlists/<setlist_id>")
    def lights_setlist_get(setlist_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        s = lights_store.get_setlist(user["id"], setlist_id)
        if s is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "setlist": s})

    @app.route("/lights/setlists/save", methods=["POST"])
    def lights_setlist_save():
        """Items referencing another account's show are dropped, not stored."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        body = request.get_json(silent=True) or {}
        items = body.get("items") if isinstance(body.get("items"), list) else []
        sid = lights_store.save_setlist(
            user["id"], body.get("id") or None, body.get("name") or "Setlist", items,
            gap_color=(body.get("gap_color") or "#1A1714")[:7],
            gap_intensity=body.get("gap_intensity") or 0)
        return jsonify({"ok": True, "id": sid, "setlists": lights_store.list_setlists(user["id"]),
                        "setlist": lights_store.get_setlist(user["id"], sid)})

    @app.route("/lights/setlists/<setlist_id>/delete", methods=["POST"])
    def lights_setlist_delete(setlist_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        lights_store.delete_setlist(user["id"], setlist_id)
        return jsonify({"ok": True, "setlists": lights_store.list_setlists(user["id"])})

    def _lights_rigs(user_id):
        return [{"id": r["id"], "name": r["name"], "venue_key": r["venue_key"], "data": r["data"]}
                for r in lights_store.list_rigs(user_id)]

    @app.route("/lights/rigs")
    def lights_rigs():
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        return jsonify({"ok": True, "rigs": _lights_rigs(user["id"])})

    @app.route("/lights/rigs/save", methods=["POST"])
    def lights_rigs_save():
        """A rig is layout + patch, not a show. Only the fields the studio
        knows how to render are stored; anything else is dropped."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        body = request.get_json(silent=True) or {}
        raw = body.get("data") if isinstance(body.get("data"), dict) else {}

        def _fracmap(m):
            out = {}
            if isinstance(m, dict):
                for k, v in list(m.items())[:10]:
                    if isinstance(v, list) and len(v) == 2:
                        try:
                            out[str(k)[:2]] = [min(0.97, max(0.03, float(v[0]))),
                                               min(0.92, max(0.04, float(v[1])))]
                        except (TypeError, ValueError):
                            pass
            return out

        def _rotmap(m):
            out = {}
            if isinstance(m, dict):
                for k, v in list(m.items())[:10]:
                    out[str(k)[:2]] = 90 if v == 90 else 0
            return out

        def _addrmap(m):
            out = {}
            if isinstance(m, dict):
                for k, v in list(m.items())[:10]:
                    try:
                        n = int(v)
                    except (TypeError, ValueError):
                        continue
                    if 1 <= n <= 512:
                        out[str(k)[:2]] = n
            return out

        try:
            bars = int(raw.get("bars") or 6)
        except (TypeError, ValueError):
            bars = 6
        try:
            start = int(raw.get("dmxStart") or 1)
        except (TypeError, ValueError):
            start = 1
        data = {"bars": max(2, min(10, bars)),
                "chans": 3 if raw.get("chans") == 3 else 4,
                "pos": _fracmap(raw.get("pos")), "rot": _rotmap(raw.get("rot")),
                "dmxStart": max(1, min(512, start)), "dmxAddr": _addrmap(raw.get("dmxAddr"))}
        rig_id, err = lights_store.save_rig(
            user["id"], body.get("id") or None, body.get("name") or "Untitled rig",
            data, str(body.get("venue") or "")[:120])
        if err:
            return jsonify({"ok": False, "error": err}), 400
        return jsonify({"ok": True, "id": rig_id, "rigs": _lights_rigs(user["id"])})

    @app.route("/lights/rigs/<rig_id>/delete", methods=["POST"])
    def lights_rigs_delete(rig_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        lights_store.delete_rig(user["id"], rig_id)
        return jsonify({"ok": True, "rigs": _lights_rigs(user["id"])})

    @app.route("/rack")
    def rack():
        import json as _json
        user = current_user()
        if user is None:
            return login_required_redirect()
        saved = store.get_rack_preset(user["id"])
        return render_template("rack.html", active_page="rack",
                               saved_rack=(_json.dumps(saved) if saved else "null"),
                               studio_split=stemsplit.configured(),
                               studio_modes=stemsplit.mode_list(),
                               server_convert=convert_engine.available(),
                               convert_formats=convert_engine.format_list(),
                               **build_dashboard_context())

    # ---- Studio Split: StemSplit.io quality tier for the Stem Deck -------
    # Env-gated on STEMSPLIT_API_KEY. The one Deck feature that uploads:
    # the track is parked under a token, StemSplit fetches it from the
    # public /stem-src URL, and finished stems stream back through us.
    # The key never reaches the browser.

    @app.route("/rack/studio-split/diag")
    def studio_split_diag():
        """Why isn't Studio Split showing up? Reports the SHAPE of the
        environment, never a value: which STEM-ish names exist, how long
        the key is, and whether it carries stray whitespace or quotes -
        the three things that silently break a pasted secret. Requires a
        signed-in account; no secret ever leaves this endpoint."""
        import json as _json
        user = current_user()
        if user is None:
            return jsonify({"error": "auth required"}), 401
        raw = os.environ.get("STEMSPLIT_API_KEY")
        names = sorted(k for k in os.environ
                       if "STEM" in k.upper() or "SPLIT" in k.upper())
        info = {
            "configured": stemsplit.configured(),
            "expected_name": "STEMSPLIT_API_KEY",
            "matching_env_names": names,
            "present": raw is not None,
        }
        if raw is not None:
            info.update({
                "length": len(raw),
                "has_surrounding_whitespace": raw != raw.strip(),
                "wrapped_in_quotes": len(raw) > 1 and raw[0] in "'\"",
                "starts_with_sk": raw.strip().startswith("sk_"),
            })
        if raw and request.args.get("probe") == "1":
            info["probe"] = stemsplit.probe()
        if request.args.get("encoders") == "1":
            # Can this box encode lossy audio at all? Decides whether MP3
            # export is a server job or has to happen in the browser.
            import shutil
            import subprocess
            found = {}
            for tool in ("ffmpeg", "avconv", "lame", "flac", "sox"):
                found[tool] = shutil.which(tool) or None
            if found.get("ffmpeg"):
                try:
                    out = subprocess.run(
                        [found["ffmpeg"], "-hide_banner", "-encoders"],
                        capture_output=True, text=True, timeout=20).stdout
                    found["ffmpeg_codecs"] = sorted(
                        c for c in ("libmp3lame", "aac", "flac", "libopus",
                                    "libvorbis", "alac", "pcm_s24le")
                        if c in out)
                except Exception as exc:
                    found["ffmpeg_codecs"] = "probe failed: %s" % exc
            info["encoders"] = found
        if raw and request.args.get("job"):
            # The whole job body, so we can see what the API actually
            # returns rather than what we assumed. Signatures are stripped
            # from the URLs - the path is the part that answers the
            # question, because it carries the file extension.
            import re as _re
            body, err = stemsplit._call(
                "GET", stemsplit.JOBS + "/" + request.args["job"])
            if err:
                info["job_raw"] = {"error": err}
            else:
                dumped = _json.dumps(body)
                info["job_raw"] = _json.loads(
                    _re.sub(r'\?[^"]*', "?<signature-stripped>", dumped))
        if raw and request.args.get("modes") == "1":
            # Which separation modes does this account actually have? Asked
            # against a source that cannot be fetched, so no audio is
            # separated and no credits are spent - see probe_output_types.
            info["output_types"] = stemsplit.probe_output_types()
        return jsonify(info)

    @app.route("/rack/studio-split", methods=["POST"])
    def studio_split_start():
        user = current_user()
        if user is None:
            return jsonify({"error": "auth required"}), 401
        if not stemsplit.configured():
            return jsonify({"error": "Studio Split isn't configured on this "
                            "server yet."}), 503
        f = request.files.get("audio")
        if f is None or not f.filename:
            return jsonify({"error": "no audio file"}), 400
        data = f.read()
        if len(data) > stemsplit.MAX_UPLOAD:
            return jsonify({"error": "file too large - bounce an MP3 first"}), 413
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in (".wav", ".mp3", ".flac", ".m4a"):
            return jsonify({"error": "use WAV, MP3, FLAC or M4A"}), 400
        mode = (request.form.get("mode") or "").strip().upper()
        if mode not in stemsplit.MODES:
            mode = stemsplit.DEFAULT_MODE
        token, path = stemsplit.park_source(data, ext)
        source_url = request.url_root.rstrip("/") + "/stem-src/" + token
        job_id, err = stemsplit.create_job(source_url, mode)
        if err:
            try:
                os.remove(path)
            except OSError:
                pass
            return jsonify({"error": "StemSplit rejected the job: " + err}), 502
        stemsplit.remember_source(job_id, path)
        # The lanes this mode yields travel with the job, so the deck never
        # has to keep its own copy of which stems go together.
        return jsonify({"job": job_id, "mode": mode,
                        "stems": stemsplit.mode_stems(mode)})

    @app.route("/stem-src/<token>")
    def stem_src(token):
        from flask import send_file

        path = stemsplit.source_path(token)
        if not path:
            return "", 404
        return send_file(path)

    @app.route("/rack/studio-split/<job_id>")
    def studio_split_status(job_id):
        user = current_user()
        if user is None:
            return jsonify({"error": "auth required"}), 401
        if not stemsplit.configured():
            return jsonify({"error": "not configured"}), 503
        status, err = stemsplit.job_status(job_id)
        if err:
            return jsonify({"error": err}), 502
        return jsonify(status)

    @app.route("/rack/studio-split/<job_id>/stem/<stem>")
    def studio_split_stem(job_id, stem):
        user = current_user()
        if user is None:
            return jsonify({"error": "auth required"}), 401
        if not stemsplit.configured():
            return jsonify({"error": "not configured"}), 503
        if stem not in stemsplit.STEMS:
            return jsonify({"error": "unknown stem"}), 400
        url, err = stemsplit.stem_url(job_id, stem)
        if err:
            return jsonify({"error": err}), 502
        upstream = stemsplit.open_stream(url)
        ctype = upstream.headers.get("Content-Type") or "audio/wav"
        resp = app.response_class(upstream, mimetype=ctype,
                                  direct_passthrough=True)
        # Name the file. Without this the browser saves it as "vocals"
        # with no extension, which nothing can open.
        resp.headers["Content-Disposition"] = (
            'attachment; filename="%s"'
            % stemsplit.stem_filename(stem, url, ctype))
        length = upstream.headers.get("Content-Length")
        if length:
            resp.headers["Content-Length"] = length   # so the bar moves
        return resp

    @app.route("/rack/convert", methods=["POST"])
    def rack_convert():
        """Compressed formats, encoded on the server.

        WAV and AIFF stay in the browser - they are already instant there
        and never leave the machine. This is for the ones a browser has no
        encoder for: MP3, FLAC, AAC, ALAC, Opus, Vorbis. It uploads, and
        the UI says so before the button is pressed.
        """
        user = current_user()
        if user is None:
            return jsonify({"error": "auth required"}), 401
        if not convert_engine.available():
            return jsonify({"error": "This server has no audio encoder "
                            "installed."}), 503
        f = request.files.get("audio")
        if f is None or not f.filename:
            return jsonify({"error": "no audio file"}), 400

        def num(name):
            try:
                return int(request.form.get(name) or 0)
            except ValueError:
                return 0

        data, name, err = convert_engine.convert(
            f.read(), f.filename,
            (request.form.get("format") or "").strip().lower(),
            bitrate=num("bitrate"), rate=num("rate"),
            channels=num("channels"), depth=num("depth"))
        if err:
            return jsonify({"error": err}), 400
        key = request.form["format"].strip().lower()
        fmt = convert_engine.FORMATS[key]
        resp = app.response_class(data, mimetype=fmt["mime"])
        resp.headers["Content-Disposition"] = \
            'attachment; filename="%s"' % name
        resp.headers["Content-Length"] = str(len(data))
        # If the codec could not take the rate that was asked for, the
        # file still arrives - but the panel has to say what changed
        # rather than quietly hand back something else.
        _, note = convert_engine.resolve_rate(key, num("rate"))
        if note:
            resp.headers["X-Convert-Note"] = note
        return resp

    @app.route("/rack/analysis", methods=["POST"])
    def rack_analysis():
        """The Rack reporting what it measured.

        Everything the meter computes has, until now, died with the tab.
        This is the arrow that was missing from the loop: the numbers
        persist, so Release Readiness can speak about the record rather
        than only about the paperwork around it.

        Nothing here is computed server-side - these are the browser's own
        measurements, and the only job is to store them faithfully.
        """
        user = current_user()
        if user is None:
            return jsonify({"error": "auth required"}), 401
        body = request.get_json(silent=True) or {}

        def num(key):
            v = body.get(key)
            try:
                f = float(v)
            except (TypeError, ValueError):
                return None
            # Reject anything that is not a real measurement.
            return f if f == f and abs(f) != float("inf") else None

        row = {
            "track_id": str(body.get("track_id") or "")[:80],
            "filename": str(body.get("filename") or "")[:200],
            "integrated": num("integrated"), "lra": num("lra"),
            "true_peak": num("true_peak"), "sample_peak": num("sample_peak"),
            "short_term_max": num("short_term_max"),
            "momentary_max": num("momentary_max"),
            "bpm": num("bpm"), "bpm_confidence": num("bpm_confidence"),
            "key": str(body.get("key") or "")[:40], "key_fit": num("key_fit"),
            "duration": num("duration"), "sample_rate": num("sample_rate"),
            "channels": num("channels"),
            "hook_15s": num("hook_15s"), "hook_30s": num("hook_30s"),
            "first_beat": num("first_beat"),
            "bar_seconds": num("bar_seconds"),
            "grid_confidence": num("grid_confidence"),
            "engine": str(body.get("engine") or "rack")[:60],
        }
        if row["integrated"] is None and row["true_peak"] is None:
            return jsonify({"error": "no measurements in this report"}), 400
        store.save_track_analysis(user["id"], row)
        saved = store.latest_track_analysis(user["id"])
        return jsonify({"ok": True, "assessment": audio_readiness.assess(saved)})

    # --- the rack preset library ----------------------------------------
    # /rack/save keeps ONE rack: the one that loads with the page. These
    # keep many, named, so a vocal chain and a drum bus can both exist.

    @app.route("/rack/library")
    def rack_library():
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        return jsonify({"ok": True, "presets": store.list_rack_presets(user["id"]),
                        "max": store.MAX_RACK_PRESETS})

    @app.route("/rack/library/save", methods=["POST"])
    def rack_library_save():
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "a preset needs a name"}), 400
        data = body.get("data")
        if not isinstance(data, dict) or not data:
            return jsonify({"ok": False, "error": "nothing to save"}), 400
        pid = store.save_rack_preset_named(user["id"], body.get("id") or "",
                                           name, data, body.get("note") or "")
        if pid is None:
            return jsonify({"ok": False,
                            "error": "that is %d presets — delete one first"
                                     % store.MAX_RACK_PRESETS}), 409
        return jsonify({"ok": True, "id": pid, "presets": store.list_rack_presets(user["id"])})

    @app.route("/rack/library/<preset_id>")
    def rack_library_get(preset_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        p = store.get_rack_preset_by_id(user["id"], preset_id)
        if p is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "preset": p})

    @app.route("/rack/library/<preset_id>/delete", methods=["POST"])
    def rack_library_delete(preset_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        if not store.delete_rack_preset(user["id"], preset_id):
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "presets": store.list_rack_presets(user["id"])})

    @app.route("/rack/save", methods=["POST"])
    def rack_save():
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        store.save_rack_preset(user["id"], request.get_json(silent=True) or {})
        return jsonify({"ok": True})

    @app.route("/sw.js")
    def service_worker():
        # Served from the root so the worker's scope covers the whole app.
        from flask import send_from_directory
        resp = send_from_directory(os.path.join(app.static_folder, "js"), "sw.js")
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.route("/stage-plot")
    def stage_plot():
        import json as _json
        user = current_user()
        if user is None:
            return login_required_redirect()
        plot = store.get_stage_plot(user["id"])
        return render_template("stage_plot.html", active_page="stage-plot",
                               saved_plot=(_json.dumps(plot) if plot else "null"),
                               **build_dashboard_context())

    @app.route("/stage-plot/save", methods=["POST"])
    def stage_plot_save():
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        data = request.get_json(silent=True) or {}
        store.save_stage_plot(user["id"], data)
        return jsonify({"ok": True})

    # --- Team-Up Board: artists seeking partners, venues seeking acts ------------
    # Moved to board.py (blueprint "board"): same URLs, structured fields,
    # in-platform reply threads, lifecycle, saved searches. Registered in
    # init at the bottom of create_app.

    # --- Partner Portal: team roles open real (read-only) doors ------------------

    @app.route("/portal")
    def portal():
        user = current_user()
        if user is None:
            return login_required_redirect()
        return render_template("portal.html", active_page="portal",
                               memberships=store.list_portal_memberships(user["id"]),
                               **build_dashboard_context())

    @app.route("/portal/<owner_id>")
    def portal_view(owner_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        membership = store.get_portal_membership(user["id"], owner_id)
        if membership is None:
            abort(404)
        role = membership["role"]
        money = None
        if role in ("manager", "accountant", "attorney"):
            rows = store.get_statement_rows(owner_id)
            money = {"total": round(sum(r["amount"] for r in rows), 2),
                     "rows": len(rows),
                     "statements": len(store.get_statements(owner_id))}
        promo = None
        if role in ("manager", "publicist", "assistant"):
            campaigns = [c for c in mls.list_campaigns(owner_id)
                         if not c.get("archived_at")]
            clicks = views = 0
            for c in campaigns:
                n = mls.event_counts(c["id"])
                views += n.get("page_view", 0) + n.get("pageview", 0)
                clicks += n.get("service_click", 0) + n.get("click", 0)
            promo = {"campaigns": len(campaigns), "views": views, "clicks": clicks,
                     "fans": len(mls.list_fans(owner_id))}
        return render_template("portal_view.html", active_page="portal",
                               m=membership, role=role, money=money, promo=promo,
                               trust=trust_score.calculate(owner_id)["total"],
                               growth=qualification.calculate(owner_id)["total"],
                               **build_dashboard_context())

    @app.route("/capital-score")
    def capital_score_page():
        user = current_user()
        if user is None:
            return login_required_redirect()
        cs = capital_engine.capital_score(user["id"])   # records itself
        return render_template("capital_score.html", active_page="command-center",
                               cs=cs,
                               trend=score_history.summarise(
                                   "capital",
                                   store.score_trend(user["id"], "capital")),
                               **build_dashboard_context())

    @app.route("/spend-optimizer")
    def spend_optimizer_page():
        user = current_user()
        if user is None:
            return login_required_redirect()
        try:
            budget = max(50.0, min(float(request.args.get("budget") or 500), 100000.0))
        except ValueError:
            budget = 500.0
        return render_template("spend_optimizer.html", active_page="command-center",
                               plan=capital_engine.spend_plan(user["id"], budget),
                               **build_dashboard_context())

    # Preview modules: registered honestly, one generic page each.
    def _module_preview(route):
        def view():
            module = cc.MODULE_BY_ROUTE[route]
            return render_template("module_preview.html",
                                   active_page="command-center", m=module,
                                   features=cc.PREVIEW_FEATURES.get(route, []),
                                   **build_dashboard_context())
        view.__name__ = "preview_" + route.strip("/").replace("/", "_").replace("-", "_")
        return view

    for _route, _name, _blurb, _status, _disc in cc.MODULES:
        if _status == "preview":
            app.add_url_rule(_route, view_func=_module_preview(_route))

    # --- Producers: beats, licences, cleared list, usage cases ----------------

    @app.route("/beats", methods=["GET", "POST"])
    def beats():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            if title:
                store.add_beat(user["id"], title,
                               (request.form.get("bpm") or "").strip(),
                               (request.form.get("song_key") or "").strip(),
                               (request.form.get("tags") or "").strip(),
                               (request.form.get("note") or "").strip())
            return redirect("/beats")
        ctx = build_dashboard_context()
        ctx["desk"] = producers.desk(user["id"])
        ctx["monitoring"] = acr_provider.status()
        rows = store.beat_audio_for(user["id"])
        ctx["audio"] = rows
        # The script needs peaks and durations; it must not need the
        # storage path, which is an R2 key or a disk location.
        ctx["audio_public"] = {k: _beat_audio_public(v) for k, v in rows.items()}
        ctx["max_beat_mb"] = store.MAX_BEAT_BYTES // (1024 * 1024)
        return render_template("beats.html", active_page="beats", **ctx)

    @app.route("/beats/register", methods=["POST"])
    def beat_register():
        """Create the registry row a dropped file hangs off. Separate from
        the form POST above because a bulk drop needs an id back, not a
        redirect."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        body = request.get_json(silent=True) or {}
        title = (body.get("title") or "").strip()[:200]
        if not title:
            return jsonify({"ok": False, "error": "a beat needs a title"}), 400
        return jsonify({"ok": True, "id": store.add_beat(user["id"], title)})

    @app.route("/beats/<beat_id>", methods=["GET", "POST"])
    def beat_detail(beat_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        beat = store.get_beat(beat_id, user["id"])
        if beat is None:
            abort(404)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "licence":
                store.add_beat_licence(beat_id, user["id"], {
                    "licensee_name": request.form.get("licensee_name"),
                    "licensee_email": request.form.get("licensee_email"),
                    "licence_type": (request.form.get("licence_type")
                                     if request.form.get("licence_type") in
                                     dict(producers.LICENCE_TYPES) else "lease"),
                    "territory": request.form.get("territory"),
                    "term": request.form.get("term"),
                    "fee": _hours_float(request.form.get("fee")),
                    "producer_split": _hours_float(
                        request.form.get("producer_split"), 50.0),
                    "terms": request.form.get("terms"),
                    "send": True})
            elif action == "clear" and (request.form.get("value") or "").strip():
                store.add_beat_clearance(
                    beat_id,
                    (request.form.get("kind")
                     if request.form.get("kind") in dict(producers.CLEARANCE_KINDS)
                     else "channel"),
                    request.form.get("value"), request.form.get("note") or "",
                    request.form.get("licence_id") or "")
            elif action == "unclear" and request.form.get("row_id"):
                store.delete_beat_clearance(beat_id, request.form["row_id"])
            elif action == "use":
                store.add_beat_use(beat_id, user["id"], {
                    "url": request.form.get("url"),
                    "platform": request.form.get("platform"),
                    "notes": request.form.get("notes")})
            elif action == "use_status" and request.form.get("use_id"):
                fields = {"status": request.form.get("status")
                          if request.form.get("status") in producers.USE_STATUSES
                          else "open"}
                if request.form.get("resolved_amount"):
                    fields["resolved_amount"] = _hours_float(
                        request.form.get("resolved_amount"))
                store.update_beat_use(user["id"], request.form["use_id"], fields)
            elif action == "revoke" and request.form.get("licence_id"):
                store.set_beat_licence_status(user["id"],
                                              request.form["licence_id"], "revoked")
            return redirect("/beats/" + beat_id)
        ctx = build_dashboard_context()
        ctx.update({
            "beat": beat,
            "licences": store.list_beat_licences(beat_id),
            "clearances": store.list_beat_clearances(beat_id),
            "uses": store.list_beat_uses(user["id"], beat_id),
            "summary": producers.beat_summary(beat_id),
            "licence_types": producers.LICENCE_TYPES,
            "clearance_kinds": producers.CLEARANCE_KINDS,
            "use_statuses": producers.USE_STATUSES,
            "monitoring": acr_provider.status(),
            "public_base": request.host_url.rstrip("/"),
            "audio": _beat_audio_public(store.get_beat_audio(beat_id)),
            "shares": store.list_beat_shares(user["id"], beat_id),
            "share_origin": _remote_origin(),
        })
        return render_template("beat_detail.html", active_page="beats", **ctx)

    # --- Beat audio, analysis, and private links -------------------------
    # The browser decodes the file, measures tempo and key with the same
    # detector the Rack uses (static/js/tempokey.js) and sends the numbers
    # up with the bytes. Nothing here listens to audio server-side, and no
    # third party is handed the beat to analyse it.

    _BEAT_AUDIO_TYPES = ("audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
                         "audio/wave", "audio/aiff", "audio/x-aiff", "audio/flac",
                         "audio/x-flac", "audio/mp4", "audio/aac", "audio/ogg",
                         "audio/webm", "application/octet-stream")

    def _beat_num(value, lo=None, hi=None):
        """A measurement or nothing. NaN and infinity are neither."""
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        if f != f or abs(f) == float("inf"):
            return None
        if lo is not None and f < lo:
            return None
        if hi is not None and f > hi:
            return None
        return f

    @app.route("/beats/<beat_id>/audio", methods=["POST"])
    def beat_audio_upload(beat_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        if store.get_beat(beat_id, user["id"]) is None:
            return jsonify({"ok": False}), 404
        f = request.files.get("file")
        if f is None or not f.filename:
            return jsonify({"ok": False, "error": "no file"}), 400
        data = f.read()
        if not data:
            return jsonify({"ok": False, "error": "empty file"}), 400
        if len(data) > store.MAX_BEAT_BYTES:
            return jsonify({"ok": False,
                            "error": "that file is %d MB; the ceiling is %d MB"
                                     % (len(data) // (1024 * 1024),
                                        store.MAX_BEAT_BYTES // (1024 * 1024))}), 413
        mime = (f.mimetype or "application/octet-stream")[:80]
        if mime not in _BEAT_AUDIO_TYPES:
            return jsonify({"ok": False, "error": "that is not an audio file"}), 415

        ext = os.path.splitext(f.filename)[1][:10] or ".audio"
        key = "beats/%s/%s%s" % (user["id"], uuid.uuid4().hex, ext)
        try:
            path = blob_store.save(key, data, mime, uploads_dir=UPLOADS_DIR)
        except RuntimeError:
            return jsonify({"ok": False, "error": "nowhere to store the file"}), 503

        # Replacing audio orphans the old object; drop it rather than pay
        # to keep a file nothing can reach.
        old = store.delete_beat_audio(user["id"], beat_id)
        if old and old != path:
            try:
                blob_store.remove(old, uploads_dir=UPLOADS_DIR)
            except Exception:
                pass

        peaks = request.form.get("peaks") or "[]"
        try:
            peaks = [max(0.0, min(1.0, float(x))) for x in json.loads(peaks)][:900]
        except (ValueError, TypeError):
            peaks = []
        store.save_beat_audio(user["id"], beat_id, {
            "filename": f.filename, "path": path, "mime": mime, "bytes": len(data),
            "duration": _beat_num(request.form.get("duration"), 0, 60 * 60 * 6),
            "peaks": peaks,
            "bpm": _beat_num(request.form.get("bpm"), 20, 400),
            "bpm_confidence": _beat_num(request.form.get("bpm_confidence"), 0, 1),
            "bpm_alternates": (request.form.get("bpm_alternates") or "")[:60],
            "song_key": (request.form.get("song_key") or "")[:40],
            "key_fit": _beat_num(request.form.get("key_fit"), -1, 1),
            "key_runner_up": (request.form.get("key_runner_up") or "")[:40],
            "sample_rate": _beat_num(request.form.get("sample_rate"), 1000, 400000),
        })
        # The measurement fills the registry fields only where the producer
        # left them empty. A number they typed is a decision; a number we
        # measured is a guess, and a guess must not overwrite a decision.
        beat = store.get_beat(beat_id, user["id"])
        audio = store.get_beat_audio(beat_id)
        fills = {}
        if not (beat["bpm"] or "").strip() and audio.get("bpm"):
            fills["bpm"] = str(int(round(audio["bpm"])))
        if not (beat["song_key"] or "").strip() and audio.get("song_key"):
            fills["song_key"] = audio["song_key"]
        if fills:
            store.update_beat(user["id"], beat_id, fills)
        return jsonify({"ok": True, "audio": _beat_audio_public(audio),
                        "filled": fills})

    def _beat_audio_public(audio):
        """What the page is allowed to know about a stored file. The
        storage path never travels — it is an R2 key or a disk location,
        and the browser reaches audio through /beats/<id>/stream."""
        if not audio:
            return None
        return {"filename": audio["filename"], "bytes": audio["bytes"],
                "duration": audio["duration"], "peaks": audio["peaks"],
                "bpm": audio["bpm"], "bpm_confidence": audio["bpm_confidence"],
                "bpm_alternates": audio["bpm_alternates"],
                "song_key": audio["song_key"], "key_fit": audio["key_fit"],
                "key_runner_up": audio["key_runner_up"],
                "sample_rate": audio["sample_rate"], "created": audio["created"]}

    def _stream_beat(audio):
        """Serve the stored bytes. R2 objects are handed over as a signed
        redirect so the file does not travel through this process twice."""
        path = audio["path"]
        if blob_store.is_remote(path):
            return redirect(blob_store.url_for(path))
        # The key is nested ("beats/<user>/<id>.wav"), so basename() would
        # look in the wrong place. send_from_directory takes the relative
        # path and refuses to leave UPLOADS_DIR itself.
        from flask import send_from_directory
        return send_from_directory(UPLOADS_DIR, path[len("/uploads/"):],
                                   mimetype=audio["mime"] or "audio/mpeg",
                                   conditional=True)

    @app.route("/beats/<beat_id>/stream")
    def beat_stream(beat_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        if store.get_beat(beat_id, user["id"]) is None:
            abort(404)
        audio = store.get_beat_audio(beat_id)
        if audio is None or not audio["path"]:
            abort(404)
        return _stream_beat(audio)

    @app.route("/beats/<beat_id>/audio/delete", methods=["POST"])
    def beat_audio_delete(beat_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        path = store.delete_beat_audio(user["id"], beat_id)
        if path is None:
            return jsonify({"ok": False}), 404
        try:
            blob_store.remove(path, uploads_dir=UPLOADS_DIR)
        except Exception:
            pass
        return jsonify({"ok": True})

    @app.route("/beats/<beat_id>/share", methods=["POST"])
    def beat_share_create(beat_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        body = request.get_json(silent=True) or {}
        token = store.create_beat_share(user["id"], beat_id,
                                        label=body.get("label") or "",
                                        days=body.get("days") or 0)
        if token is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "token": token,
                        "url": "%s/beat/%s" % (_remote_origin(), token),
                        "shares": store.list_beat_shares(user["id"], beat_id)})

    @app.route("/beats/<beat_id>/shares")
    def beat_share_list(beat_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        if store.get_beat(beat_id, user["id"]) is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "shares": store.list_beat_shares(user["id"], beat_id),
                        "origin": _remote_origin()})

    @app.route("/beat-link/<token>/revoke", methods=["POST"])
    def beat_share_revoke(token):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        if not store.revoke_beat_share(user["id"], token):
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True})

    @app.route("/beat/<token>")
    def beat_share_page(token):
        """Public on purpose: an artist listens to a beat somebody sent
        them without making an account. Standalone template, one beat,
        no catalogue."""
        share = store.get_beat_share(token)
        if share is None:
            return render_template("beat_share.html", gone=True), 404
        beat = share["beat"]
        audio = store.get_beat_audio(beat["id"])
        producer = store.get_user(beat["user_id"]) or {}
        return render_template(
            "beat_share.html", gone=False, token=token, beat=beat,
            audio=_beat_audio_public(audio), has_audio=bool(audio and audio["path"]),
            producer_name=producer.get("name") or "the producer",
            licence_types=producers.LICENCE_TYPES)

    @app.route("/beat/<token>/stream")
    def beat_share_stream(token):
        share = store.get_beat_share(token)
        if share is None:
            abort(404)
        audio = store.get_beat_audio(share["beat_id"])
        if audio is None or not audio["path"]:
            abort(404)
        # Count the play, not the page load: opening a link is not interest.
        if request.headers.get("Range", "").strip() in ("", "bytes=0-"):
            store.count_beat_share_play(token)
        return _stream_beat(audio)

    @app.route("/beats/<beat_id>/delete", methods=["POST"])
    def beat_delete(beat_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        store.delete_beat(user["id"], beat_id)
        return redirect("/beats")

    @app.route("/beats/<beat_id>/clearance.csv")
    def beat_clearance_csv(beat_id):
        """The cleared list as a file, for the label that asked for it."""
        user = current_user()
        if user is None:
            return login_required_redirect()
        beat = store.get_beat(beat_id, user["id"])
        if beat is None:
            abort(404)
        import csv as _csv
        import io as _io
        out = _io.StringIO()
        w = _csv.writer(out, lineterminator="\n")
        w.writerow(["Beat", "Cleared item", "Kind", "Licence", "Note", "Added"])
        licences = {l["id"]: l for l in store.list_beat_licences(beat_id)}
        for row in store.list_beat_clearances(beat_id):
            lic = licences.get(row["licence_id"] or "")
            w.writerow([beat["title"], row["value"], row["kind"],
                        ("%s (%s)" % (lic["licensee_name"] or lic["licensee_email"],
                                      lic["status"])) if lic else "",
                        row["note"], row["created"][:10]])
        return Response(out.getvalue(), mimetype="text/csv", headers={
            "Content-Disposition":
                'attachment; filename="cleared-%s.csv"' % beat_id[:8]})

    @app.route("/licence/<token>", methods=["GET", "POST"])
    def beat_licence_public(token):
        """The licensee's end: read the terms, sign once, keep the link."""
        licence = store.get_beat_licence_by_token(token)
        if licence is None:
            abort(404)
        signed = False
        if request.method == "POST":
            name = (request.form.get("signed_by") or "").strip()
            if name:
                signed = store.sign_beat_licence(token, name)
                if signed:
                    store.notify(licence["producer_id"], "recovery",
                                 "Licence signed: %s" % licence["beat_title"],
                                 "%s signed the %s licence." % (
                                     name, producers.licence_label(
                                         licence["licence_type"])),
                                 "/beats/%s" % licence["beat_id"])
                licence = store.get_beat_licence_by_token(token)
        return render_template("licence_public.html", licence=licence,
                               just_signed=signed,
                               type_label=producers.licence_label(
                                   licence["licence_type"]))

    @app.route("/cleared/<beat_id>")
    def beat_cleared_public(beat_id):
        """The page a label, distributor or supervisor checks.

        Public on purpose: its whole job is being checkable by somebody
        with no account here. It shows what the producer listed and the
        licence status behind it - never the fee, the terms text or the
        licensee's email.
        """
        beat = store.get_beat(beat_id)
        if beat is None:
            abort(404)
        query = (request.args.get("q") or "").strip()
        result = producers.clearance_for(beat_id, query) if query else None
        producer = store.get_user(beat["user_id"]) or {}
        rows = []
        licences = {l["id"]: l for l in store.list_beat_licences(beat_id)}
        for row in store.list_beat_clearances(beat_id):
            lic = licences.get(row["licence_id"] or "")
            rows.append({"value": row["value"], "kind": row["kind"],
                         "note": row["note"],
                         "licence_status": lic["status"] if lic else "",
                         "licence_type": producers.licence_label(
                             lic["licence_type"]) if lic else ""})
        return render_template("cleared_public.html", beat=beat, rows=rows,
                               query=query, result=result,
                               producer_name=producer.get("name") or "the producer")

    # --- OS Phase 2: recovery case management + deal room ----------------------

    _CASE_CATEGORIES = ["unmatched", "coverage_gap", "mechanical", "publishing",
                        "neighboring", "content_id", "distributor", "split_conflict",
                        "other"]
    _CASE_STATUSES = ["open", "submitted", "waiting", "won", "lost"]
    _DEAL_TYPES = ["split", "producer", "feature", "work_for_hire", "management",
                   "distribution", "label_services", "sync", "publishing_admin",
                   "advance", "merch", "touring", "brand"]
    _DEAL_STATUSES = ["draft", "sent", "negotiating", "signed", "expired", "cancelled"]

    @app.route("/royalty-recovery/cases", methods=["GET", "POST"])
    def recovery_cases():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if request.method == "POST":
            f = request.form
            if f.get("case_id"):
                fields = {}
                if f.get("status") in _CASE_STATUSES:
                    fields["status"] = f["status"]
                if "notes" in f:
                    fields["notes"] = (f.get("notes") or "").strip()[:600]
                if f.get("evidence_doc_id"):
                    fields["evidence_doc_id"] = f["evidence_doc_id"]
                if f.get("payout_result"):
                    try:
                        fields["payout_result"] = float(f["payout_result"])
                    except ValueError:
                        pass
                store.update_recovery_case(user["id"], f["case_id"], fields)
                case = store.get_recovery_case(user["id"], f["case_id"])
                if case and f.get("status") == "won":
                    store.notify(user["id"], "recovery",
                                 "Case won: %s" % case["title"],
                                 "Recovered $%.2f." % (case.get("payout_result") or 0),
                                 "/royalty-recovery/cases")
            elif (f.get("title") or "").strip():
                store.create_recovery_case(user["id"], {
                    "title": f["title"].strip(),
                    "category": f.get("category") if f.get("category") in _CASE_CATEGORIES else "other",
                    "estimated_amount": f.get("estimated_amount") or 0,
                    "confidence": f.get("confidence") or "medium",
                    "deadline": (f.get("deadline") or "").strip(),
                    "notes": (f.get("notes") or "").strip()})
            return redirect("/royalty-recovery/cases")
        cases = store.list_recovery_cases(user["id"])
        recovered = sum(c.get("payout_result") or 0 for c in cases if c["status"] == "won")
        pipeline = sum(c["estimated_amount"] for c in cases
                       if c["status"] in ("open", "submitted", "waiting"))
        docs = {d["id"]: d for d in store.list_documents(user["id"])}
        return render_template("recovery_cases.html", active_page="cases",
                               cases=cases, recovered=recovered, pipeline=pipeline,
                               docs=docs, doc_list=list(docs.values()),
                               categories=_CASE_CATEGORIES, statuses=_CASE_STATUSES,
                               **build_dashboard_context())

    @app.route("/royalty-recovery/cases/from-finding", methods=["POST"])
    def case_from_finding():
        user = current_user()
        if user is None:
            return login_required_redirect()
        f = request.form
        store.create_recovery_case(user["id"], {
            "title": (f.get("title") or "Statement finding").strip(),
            "category": f.get("category") if f.get("category") in _CASE_CATEGORIES else "other",
            "estimated_amount": f.get("amount") or 0,
            "confidence": "high" if f.get("category") == "unmatched" else "medium",
            "notes": (f.get("notes") or "").strip()})
        return redirect("/royalty-recovery/cases")

    @app.route("/deal-room", methods=["GET", "POST"])
    def deal_room():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if request.method == "POST":
            f = request.form
            if f.get("deal_id"):
                fields = {}
                if f.get("status") in _DEAL_STATUSES:
                    fields["status"] = f["status"]
                if "terms" in f:
                    fields["terms"] = (f.get("terms") or "").strip()[:600]
                if f.get("doc_id"):
                    fields["doc_id"] = f["doc_id"]
                store.update_deal(user["id"], f["deal_id"], fields)
                if f.get("status") == "signed":
                    store.notify(user["id"], "campaign", "Deal signed",
                                 "A deal moved to signed in your Deal Room.",
                                 "/deal-room")
            elif (f.get("title") or "").strip():
                store.create_deal(user["id"], {
                    "title": f["title"].strip(),
                    "deal_type": f.get("deal_type") if f.get("deal_type") in _DEAL_TYPES else "split",
                    "counterparty": (f.get("counterparty") or "").strip(),
                    "terms": (f.get("terms") or "").strip(),
                    "deadline": (f.get("deadline") or "").strip()})
            return redirect("/deal-room")
        deals = store.list_deals(user["id"])
        docs = {d["id"]: d for d in store.list_documents(user["id"])}
        return render_template("deal_room.html", active_page="deal-room",
                               deals=deals, docs=docs, doc_list=list(docs.values()),
                               deal_types=_DEAL_TYPES, deal_statuses=_DEAL_STATUSES,
                               **build_dashboard_context())

    @app.route("/deal-room/generate-split", methods=["POST"])
    def generate_split_agreement():
        user = current_user()
        if user is None:
            return login_required_redirect()
        f = request.form
        track = (f.get("track") or "Untitled Track").strip()[:120]
        parties = []
        for i in range(1, 5):
            name = (f.get("party%d_name" % i) or "").strip()
            share = (f.get("party%d_share" % i) or "").strip()
            if name and share:
                parties.append((name, share))
        if len(parties) < 2:
            return redirect("/deal-room")
        lines = [
            "SPLIT AGREEMENT (TEMPLATE)",
            "=" * 40, "",
            "Track: %s" % track,
            "Date: %s" % datetime.now(timezone.utc).strftime("%Y-%m-%d"), "",
            "The undersigned agree to the following ownership splits for the",
            "composition and/or master recording of the track named above:", "",
        ]
        for name, share in parties:
            lines.append("  %s ....... %s%%" % (name.ljust(30, " "), share))
        lines += ["", "Each party warrants their contribution is original.",
                  "Signatures:", ""]
        for name, _unused in parties:
            lines.append("  ______________________  (%s)   Date: __________" % name)
        lines += ["", "-" * 40,
                  "Generated by Street Banker Deal Room as a starting template.",
                  "NOT LEGAL ADVICE - have an attorney review before signing."]
        fname = "doc_%s.txt" % uuid.uuid4().hex
        with open(os.path.join(UPLOADS_DIR, fname), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        document_path = "/uploads/" + fname
        store.register_stored_asset(user["id"], document_path, "private", "document")
        doc_id = store.add_document(user["id"], "split-agreement-%s.txt" % _slugify(track),
                                    document_path, "Split Agreement",
                                    "Generated template - attorney review required")
        store.create_deal(user["id"], {
            "title": "Split: %s" % track, "deal_type": "split",
            "counterparty": ", ".join(n for n, _unused in parties),
            "terms": " / ".join("%s %s%%" % (n, sh) for n, sh in parties),
            "doc_id": doc_id})
        return redirect("/deal-room")

    _SYNC_AUDIO_EXTS = ("mp3", "wav", "m4a", "aiff", "aif", "flac")

    def _sync_audio_upload(field):
        f = request.files.get(field)
        if f is None or not f.filename:
            return ""
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in _SYNC_AUDIO_EXTS:
            return ""
        fname = "sync_%s.%s" % (uuid.uuid4().hex, ext)
        f.save(os.path.join(UPLOADS_DIR, fname))
        return "/uploads/" + fname

    @app.route("/sync/clearance-packs", methods=["GET", "POST"])
    def sync_packs():
        user = current_user()
        if user is None:
            return login_required_redirect()
        error = None
        if request.method == "POST":
            f = request.form
            if f.get("pack_id"):
                fields = {}
                if f.get("status") in ("active", "archived"):
                    fields["status"] = f["status"]
                for key in ("master_status", "publishing_status"):
                    if f.get(key) in ("cleared", "pending", "unconfirmed"):
                        fields[key] = f[key]
                store.update_sync_pack(user["id"], f["pack_id"], fields)
                return redirect("/sync/clearance-packs")
            title = (f.get("title") or "").strip()
            if not title:
                error = "A track title is required."
            else:
                main_url = _sync_audio_upload("main_audio")
                if not main_url:
                    error = "Upload the main audio (MP3, WAV, M4A, AIFF, or FLAC)."
                else:
                    slug = _ml_slug("sync-" + title)
                    store.create_sync_pack(user["id"], slug, {
                        "title": title,
                        "artist_name": (f.get("artist_name") or "").strip(),
                        "bpm": (f.get("bpm") or "").strip(),
                        "song_key": (f.get("song_key") or "").strip(),
                        "moods": (f.get("moods") or "").strip(),
                        "master_status": f.get("master_status") if f.get("master_status") in ("cleared", "pending", "unconfirmed") else "unconfirmed",
                        "publishing_status": f.get("publishing_status") if f.get("publishing_status") in ("cleared", "pending", "unconfirmed") else "unconfirmed",
                        "ownership_note": (f.get("ownership_note") or "").strip(),
                        "contact_email": (f.get("contact_email") or "").strip(),
                        "main_url": main_url,
                        "instrumental_url": _sync_audio_upload("instrumental_audio"),
                        "clean_url": _sync_audio_upload("clean_audio")})
                    return redirect("/sync/clearance-packs")
        return render_template("sync_packs.html", active_page="sync-packs",
                               packs=store.list_sync_packs(user["id"]), error=error,
                               **build_dashboard_context())

    @app.route("/s/<slug>")
    def sync_pack_public(slug):
        pack = store.get_sync_pack_by_slug(slug, count_view=True)
        if pack is None or pack["status"] != "active":
            abort(404)
        return render_template("sync_pack_public.html", p=pack)

    @app.route("/s/<slug>/request", methods=["POST"])
    def sync_pack_request(slug):
        pack = store.get_sync_pack_by_slug(slug)
        if pack is None or pack["status"] != "active":
            abort(404)
        f = request.form
        email = (f.get("email") or "").strip()
        message = (f.get("message") or "").strip()[:600]
        if "@" not in email:
            return jsonify({"ok": False, "error": "Enter a valid email."}), 400
        store.add_inbox("sync_request", {"pack": pack["title"], "slug": slug,
                                         "email": email, "message": message},
                        user_id=pack["user_id"])
        store.notify(pack["user_id"], "campaign",
                     "License request: %s" % pack["title"],
                     "%s asked about this track via your sync pack link." % email,
                     "/inbox")
        return jsonify({"ok": True,
                        "message": "Request sent - the rights holder will follow up."})

    @app.route("/sync/deal-simulator", methods=["GET", "POST"])
    def deal_simulator():
        user = current_user()
        if user is None:
            return login_required_redirect()
        result, inp = None, {}
        if request.method == "POST":
            f = request.form
            inp = {"fee": f.get("fee") or 0, "media": f.get("media"),
                   "term": f.get("term"), "territory": f.get("territory"),
                   "exclusive": bool(f.get("exclusive")),
                   "all_media": bool(f.get("all_media")),
                   "mfn": bool(f.get("mfn")), "buyout": bool(f.get("buyout"))}
            try:
                inp["fee"] = float(inp["fee"])
            except (TypeError, ValueError):
                inp["fee"] = 0
            result = sync_simulator.simulate(inp)
        return render_template("deal_simulator.html", active_page="deal-simulator",
                               result=result, inp=inp, sim=sync_simulator,
                               **build_dashboard_context())

    @app.route("/artist-twin", methods=["GET", "POST"])
    def artist_twin_page():
        user = current_user()
        if user is None:
            return login_required_redirect()
        settings = store.get_twin_settings(user["id"]) or {
            "sources": [k for k, _label in twin.SOURCES], "tone": "premium",
            "do_not_say": ""}
        generated = None
        if request.method == "POST":
            f = request.form
            if f.get("save_settings"):
                sources = [k for k, _label in twin.SOURCES if f.get("src_" + k)]
                tone = f.get("tone") if f.get("tone") in dict(twin.TONES) else "premium"
                store.save_twin_settings(user["id"], sources, tone,
                                         (f.get("do_not_say") or "").strip())
                return redirect("/artist-twin")
            kind = f.get("kind")
            if kind in twin.OUTPUT_KEYS:
                enabled = set(settings["sources"])
                facts, used = twin.gather_context(user["id"], enabled)
                do_not_say = [p.strip() for p in
                              (settings.get("do_not_say") or "").split(",") if p.strip()]
                text = twin.generate(kind, facts, settings.get("tone", "premium"),
                                     do_not_say)
                store.save_twin_generation(user["id"], kind, text, ", ".join(used))
                generated = {"kind": kind, "text": text, "used": used}
        os_tracks_list = store.list_os_tracks(user["id"])
        osctx = _os_ctx(user["id"])
        strategist = artist_os.twin_report(
            os_tracks_list, osctx,
            store.list_pulse_snapshots(user["id"], limit=30),
            artist_os.action_queue([(t, osctx) for t in os_tracks_list]),
            analysis=store.latest_track_analysis(user["id"]))
        # Artist Signal Profile: priorities the artist set on the homepage
        # EQ. Selected, not measured - the template labels it that way.
        signal = store.get_artist_signal_profile(user["id"])
        signal_ctx = None
        if signal and signal.get("topPriorities"):
            signal_ctx = {
                "top": signal["topPriorities"][:3],
                "lane": signal.get("recommendedLane") or "",
                "preset": signal.get("preset") or "Custom Mix",
                "updated": (signal.get("_updated") or "")[:10],
            }
        return render_template("artist_twin.html", active_page="artist-twin",
                               settings=settings, twin=twin, generated=generated,
                               strategist=strategist, signal=signal_ctx,
                               history=store.list_twin_generations(user["id"]),
                               **build_dashboard_context())

    _EXPENSE_CATEGORIES = ["production", "mixing_mastering", "artwork", "video",
                           "marketing_ads", "content", "street_team",
                           "playlist_press", "travel", "other"]

    @app.route("/revenue-os", methods=["GET", "POST"])
    def revenue_os():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if request.method == "POST":
            f = request.form
            if f.get("delete_id"):
                store.delete_expense(user["id"], f["delete_id"])
            elif (f.get("description") or "").strip() and f.get("amount"):
                try:
                    amount = float(f["amount"])
                except ValueError:
                    amount = 0
                if amount > 0:
                    store.add_expense(
                        user["id"],
                        f.get("category") if f.get("category") in _EXPENSE_CATEGORIES else "other",
                        f["description"].strip(), amount,
                        (f.get("spend_date") or "").strip())
            return redirect("/revenue-os")
        expenses = store.list_expenses(user["id"])
        total_expenses = sum(e["amount"] for e in expenses)
        by_category = {}
        for e in expenses:
            by_category[e["category"]] = by_category.get(e["category"], 0) + e["amount"]
        summary = build_royalty_summary(store.get_statement_rows(user["id"]))
        income = summary["total"] if summary else 0
        return render_template("revenue_os.html", active_page="revenue-os",
                               expenses=expenses, total_expenses=total_expenses,
                               by_category=sorted(by_category.items(),
                                                  key=lambda x: x[1], reverse=True),
                               income=income, net=round(income - total_expenses, 2),
                               summary=summary, categories=_EXPENSE_CATEGORIES,
                               **build_dashboard_context())

    @app.route("/trust-score")
    def trust_score_page():
        user = current_user()
        if user is None:
            return login_required_redirect()
        t = trust_score.calculate(user["id"])            # records itself
        return render_template("trust_score.html", active_page="trust-score",
                               t=t,
                               trend=score_history.summarise(
                                   "trust",
                                   store.score_trend(user["id"], "trust")),
                               **build_dashboard_context())

    @app.route("/pulse")
    def pulse_page():
        user = current_user()
        if user is None:
            return login_required_redirect()
        profile = store.get_pulse_profile(user["id"])
        pulse, deezer = None, None
        if profile and spotify.pulse_configured():
            pulse = spotify.artist_pulse(profile["artist_id"])
            if pulse:
                deezer = music_apis.deezer_artist_fans(pulse["name"])
                store.record_pulse_snapshot(user["id"], pulse["followers"],
                                            pulse["popularity"],
                                            (deezer or {}).get("fans", 0))
        snaps = store.list_pulse_snapshots(user["id"], limit=30)
        # Peers: pinned artists' PUBLIC Spotify numbers, snapshotted on the
        # same cadence — a real comparison, not a modeled one.
        peers = []
        for peer in store.list_pulse_peers(user["id"]):
            row = {"artist_id": peer["artist_id"], "name": peer["name"],
                   "image": peer["image"], "followers": None,
                   "popularity": None, "delta7": None}
            if spotify.pulse_configured():
                live = spotify.artist_pulse(peer["artist_id"])
                if live:
                    store.record_peer_snapshot(user["id"], peer["artist_id"],
                                               live["followers"],
                                               live["popularity"])
                    row["followers"] = live["followers"]
                    row["popularity"] = live["popularity"]
            history = store.list_peer_snapshots(user["id"], peer["artist_id"])
            week_ago = (datetime.now(timezone.utc).date()
                        - timedelta(days=7)).isoformat()
            base = next((s for s in history if s["day"] <= week_ago),
                        history[0] if history else None)
            if base and row["followers"] is not None and base["followers"]:
                row["delta7"] = row["followers"] - base["followers"]
            peers.append(row)
        my_delta7 = None
        if pulse and snaps:
            week_ago = (datetime.now(timezone.utc).date()
                        - timedelta(days=7)).isoformat()
            base = next((s for s in snaps if s["day"] <= week_ago), snaps[0])
            if base["followers"]:
                my_delta7 = pulse["followers"] - base["followers"]
        # Milestone: the largest round follower number crossed between the
        # oldest snapshot on file and today — detection, not prediction.
        milestone = None
        if pulse and snaps and len(snaps) > 1:
            start = min(s["followers"] for s in snaps if s["followers"]) \
                if any(s["followers"] for s in snaps) else 0
            for level in (1000000, 500000, 100000, 50000, 10000, 5000,
                          1000, 500, 100):
                if start < level <= pulse["followers"]:
                    milestone = level
                    break
        return render_template("pulse.html", active_page="pulse",
                               pulse_configured=spotify.pulse_configured(),
                               profile=profile, pulse=pulse, deezer=deezer,
                               snaps=snaps, peers=peers, my_delta7=my_delta7,
                               milestone=milestone,
                               **build_dashboard_context())

    @app.route("/pulse/peer/add", methods=["POST"])
    def pulse_peer_add():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        p = request.get_json(silent=True) or {}
        artist_id = (p.get("id") or "").strip()[:64]
        name = (p.get("name") or "").strip()[:120]
        if not artist_id or not name:
            return jsonify({"ok": False, "error": "Pick an artist from the "
                            "search results."}), 400
        profile = store.get_pulse_profile(user["id"])
        if profile and profile["artist_id"] == artist_id:
            return jsonify({"ok": False, "error": "That's you — pin someone "
                            "to compare against."}), 400
        if len(store.list_pulse_peers(user["id"])) >= 3:
            return jsonify({"ok": False, "error": "Three peers max — remove "
                            "one first."}), 400
        store.add_pulse_peer(user["id"], artist_id, name,
                             (p.get("image") or "").strip()[:300])
        return jsonify({"ok": True})

    @app.route("/pulse/peer/<artist_id>/remove", methods=["POST"])
    def pulse_peer_remove(artist_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        store.delete_pulse_peer(user["id"], artist_id)
        return jsonify({"ok": True})

    @app.route("/pulse/search")
    def pulse_search():
        if current_user() is None:
            return jsonify({"ok": False, "results": []}), 401
        return jsonify({"ok": True,
                        "results": spotify.search_artists(request.args.get("q"))})

    @app.route("/pulse/select", methods=["POST"])
    def pulse_select():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        p = request.get_json(silent=True) or {}
        artist_id = (p.get("id") or "").strip()[:64]
        name = (p.get("name") or "").strip()[:120]
        if not artist_id or not name:
            return jsonify({"ok": False, "error": "Pick an artist from the search results."}), 400
        store.save_pulse_profile(user["id"], artist_id, name,
                                 (p.get("image") or "").strip()[:300])
        return jsonify({"ok": True})

    @app.route("/pulse/clear", methods=["POST"])
    def pulse_clear():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        store.clear_pulse_profile(user["id"])
        return jsonify({"ok": True})

    @app.route("/walkthrough")
    def walkthrough():
        user = current_user()
        if user is None:
            return login_required_redirect()
        return render_template("walkthrough.html", active_page="command-center",
                               user_plan=(user.get("plan") or "artist"),
                               **build_dashboard_context())

    @app.route("/walkthrough/sample-statement.csv")
    def walkthrough_sample_csv():
        rows = ["Track Title,Store,Net Revenue,Sales Period",
                "Midnight Drive,Spotify,412.83,2026-04",
                "Midnight Drive,Apple Music,208.11,2026-04",
                "Midnight Drive,Spotify,391.20,2026-05",
                "Neon Dreams,Spotify,146.55,2026-04",
                "Neon Dreams,Spotify,171.32,2026-05",
                "Digital Paradise,Apple Music,88.90,2026-05",
                ",Spotify,64.27,2026-05",
                ",Apple Music,21.50,2026-04"]
        return Response("\n".join(rows) + "\n", mimetype="text/csv", headers={
            "Content-Disposition": "attachment; filename=sample-statement.csv"})

    # --- Release OS: qualification, artist profile, vault, review queue --------

    @app.route("/qualification")
    def qualification_page():
        user = current_user()
        if user is None:
            return login_required_redirect()
        # calculate() records today's reading itself, so the trend below
        # always includes it.
        q = qualification.calculate(user["id"])
        return render_template("qualification.html", active_page="qualification",
                               q=q,
                               trend=score_history.summarise(
                                   "qualification",
                                   store.score_trend(user["id"], "qualification")),
                               **build_dashboard_context())

    @app.route("/artist-profile")
    def artist_profile():
        user = current_user()
        if user is None:
            return login_required_redirect()
        saved = store.get_epk(user["id"]) or {}
        assets = [{**a, "label": a["kind"].replace("_", " ").title()}
                  for a in store.get_epk_assets(user["id"], public_only=False)]
        ctx = build_dashboard_context()
        epk_data = get_epk_data(ctx["account"], ctx["catalog_value"],
                                overrides=saved.get("data"), photo=saved.get("photo"),
                                assets=assets,
                                demo=_is_demo_email(user["email"]))
        campaigns = []
        for c in mls.list_campaigns(user["id"]):
            counts = mls.event_counts(c["id"])
            campaigns.append({**c, "visits": counts.get("page_view", 0),
                              "clicks": counts.get("service_click", 0),
                              "fans": counts.get("email_capture", 0)
                                      + counts.get("presave_notify", 0),
                              "eff_status": links_engine.effective_status(c)})
        return render_template("artist_profile.html", active_page="profile",
                               e=epk_data, q=qualification.calculate(user["id"]),
                               campaigns=campaigns,
                               fan_count=len(mls.list_fans(user["id"])),
                               **ctx)

    @app.route("/vault")
    def asset_vault():
        user = current_user()
        if user is None:
            return login_required_redirect()
        items = []
        for v in store.list_vault_files(user["id"]):
            items.append({"name": v["label"] or "Vault file",
                          "type": v["kind"].replace("_", " ").title(),
                          "path": v["path"], "date": v["created"][:10],
                          "usage": "Vault upload — yours to deploy",
                          "status": "Archived", "manage": "/vault",
                          "vid": v["id"]})
        for a in store.get_epk_assets(user["id"]):
            items.append({"name": a["kind"].replace("_", " ").title(), "type": "Press asset",
                          "path": a["path"], "date": a["updated"][:10],
                          "usage": "EPK downloads + press outreach",
                          "status": "Public" if a["public"] else "Private",
                          "manage": "/epk"})
        epk = store.get_epk(user["id"]) or {}
        if epk.get("photo"):
            items.append({"name": "Artist Photo", "type": "Press asset",
                          "path": epk["photo"], "date": "", "usage": "EPK hero + profile",
                          "status": "Public", "manage": "/epk"})
        for c in mls.list_campaigns(user["id"]):
            if c.get("cover_url"):
                items.append({"name": c["title"], "type": "Cover art",
                              "path": c["cover_url"], "date": c["updated"][:10],
                              "usage": "Smart link + social cards",
                              "status": links_engine.effective_status(c),
                              "manage": "/links/%s/edit" % c["id"]})
        for r in ros.list_campaigns(user["id"]):
            for a in ros.list_assets(r["id"]):
                if a["asset_type"] == "lyrics":
                    items.append({"name": "%s — Lyrics" % r["title"], "type": "Lyrics",
                                  "path": "", "date": a["created"][:10],
                                  "usage": "Lyric posts + video overlays",
                                  "status": "In rollout",
                                  "manage": "/rollout-studio/%s" % r["id"]})
                else:
                    items.append({"name": "%s — %s" % (r["title"], a["asset_type"].title()),
                                  "type": a["asset_type"].title(),
                                  "path": a["file_path"], "date": a["created"][:10],
                                  "usage": "Rollout content + edit plans",
                                  "status": "In rollout",
                                  "manage": "/rollout-studio/%s" % r["id"]})
        return render_template("vault.html", active_page="vault", items=items,
                               **build_dashboard_context())

    VAULT_KINDS = ("cover_art", "master", "stems", "press_photo", "video", "file")
    VAULT_EXTS = ("png", "jpg", "jpeg", "webp", "gif", "wav", "mp3", "flac",
                  "zip", "pdf", "mp4", "mov")

    @app.route("/vault/upload", methods=["POST"])
    def vault_upload():
        """The real vault door: any release asset in, tagged and listed."""
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in to use the vault."}), 401
        f = request.files.get("file")
        if f is None or not f.filename:
            return jsonify({"ok": False, "error": "Choose a file."}), 400
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in VAULT_EXTS:
            return jsonify({"ok": False,
                            "error": "Use an image, audio, video, zip, or PDF file."}), 400
        kind = request.form.get("kind") or "file"
        if kind not in VAULT_KINDS:
            kind = "file"
        label = (request.form.get("label") or f.filename.rsplit(".", 1)[0])[:120]
        fname = "vault_%s_%d.%s" % (user["id"],
                                    int(datetime.now(timezone.utc).timestamp() * 1000),
                                    ext)
        # The object store when it is configured, the disk when it is
        # not. blob_store.save returns the path to record either way:
        # "r2:<key>" or "/uploads/<name>". Nothing below branches on it.
        path = blob_store.save(fname, f.read(),
                               content_type=f.mimetype,
                               uploads_dir=UPLOADS_DIR)
        store.register_stored_asset(user["id"], path, "private", "vault")
        store.add_vault_file(user["id"], path, label, kind)
        return jsonify({"ok": True, "path": path})

    @app.route("/vault/<file_id>/delete", methods=["POST"])
    def vault_delete(file_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        path = store.delete_vault_file(user["id"], file_id)
        # Handles both shapes: deletes the object, or unlinks the file.
        if path and (blob_store.is_remote(path)
                     or path.startswith("/uploads/vault_")):
            blob_store.remove(path, uploads_dir=UPLOADS_DIR)
        if path:
            store.delete_stored_asset(user["id"], path)
        return redirect("/vault")

    @app.route("/vault/zip", methods=["POST"])
    def vault_zip():
        # Batch download: only paths that genuinely belong to this user's
        # vault are honored — the vault listing itself is the allowlist.
        user = current_user()
        if user is None:
            return login_required_redirect()
        wanted = set(request.form.getlist("paths"))
        allowed = set()
        for v in store.list_vault_files(user["id"]):
            allowed.add(v["path"])
        for a in store.get_epk_assets(user["id"]):
            allowed.add(a["path"])
        epk = store.get_epk(user["id"]) or {}
        if epk.get("photo"):
            allowed.add(epk["photo"])
        for c in mls.list_campaigns(user["id"]):
            if c.get("cover_url"):
                allowed.add(c["cover_url"])
        for r in ros.list_campaigns(user["id"]):
            for a in ros.list_assets(r["id"]):
                if a.get("file_path"):
                    allowed.add(a["file_path"])
        import io as _io
        import zipfile
        buf = _io.BytesIO()
        added = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in wanted & allowed:
                name = os.path.basename(p.split("?")[0])
                if blob_store.is_remote(p):
                    # Pull the object back through the presigned URL. A
                    # failure skips that one file rather than losing the
                    # whole archive.
                    blob = blob_store.fetch(p)
                    if blob is not None:
                        zf.writestr(name, blob)
                        added += 1
                    continue
                if not p.startswith("/uploads/"):
                    continue
                fpath = os.path.join(UPLOADS_DIR, name)
                if os.path.exists(fpath):
                    zf.write(fpath, name)
                    added += 1
        if not added:
            return redirect("/vault")
        buf.seek(0)
        return Response(buf.read(), mimetype="application/zip", headers={
            "Content-Disposition": "attachment; filename=vault-assets.zip"})

    @app.route("/admin/review")
    def admin_review():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if not _is_owner_email(user.get("email")):
            abort(404)
        with store.get_db() as db:
            rows = db.execute(
                "SELECT id, name, email, plan, created FROM users"
                " WHERE plan != 'fan' ORDER BY created").fetchall()
        queue = []
        for row in rows:
            q = qualification.calculate(row["id"])
            queue.append({"name": row["name"], "email": row["email"],
                          "plan": row["plan"], "total": q["total"],
                          "badges": q["badges"],
                          "missing": [n for n, _, _ in q["needs_work"]][:3],
                          "recommendation": q["recommendation"]})
        queue.sort(key=lambda a: a["total"], reverse=True)
        return render_template("admin_review.html", active_page="review",
                               queue=queue, **build_dashboard_context())

    # --- Rollout Engine: social rollout campaigns wired into Links ------------

    def _ro_owned(cid):
        user = current_user()
        if user is None:
            return None, login_required_redirect()
        campaign = ros.get_campaign(cid, user["id"])
        if campaign is None:
            abort(404)
        return campaign, None

    def _ro_post_attribution(campaign):
        """Per-post visits/clicks/fans pulled from ml_events via each
        post's Links variant."""
        posts = ros.list_posts(campaign["id"])
        stats = (mls.variant_stats(campaign["ml_campaign_id"])
                 if campaign.get("ml_campaign_id") else {})
        for p in posts:
            st = stats.get(p["variant_id"], {})
            p["visits"] = st.get("page_view", 0)
            p["clicks"] = st.get("service_click", 0)
            p["fans"] = st.get("email_capture", 0) + st.get("presave_notify", 0)
        return posts

    def _rollout_learning(user_id):
        """What past rollouts converted, from variants that outlive them.

        clear_posts wipes ro_posts on every regenerate but never touches
        ml_variants, so the platform and phase attribution survives - the
        whole history is already there, no migration needed.
        """
        try:
            return rollout_learning.report(
                mls.list_campaigns(user_id), mls.list_variants,
                mls.variant_stats)
        except Exception:
            # A learned suggestion is never worth breaking a page over.
            return {"platforms": {}, "phases": {}, "measured": False}

    @app.route("/rollout-studio")
    def rollout_dashboard():
        user = current_user()
        ctx = build_dashboard_context()
        cards = []
        if user:
            for c in ros.list_campaigns(user["id"]):
                counts = ros.post_status_counts(c["id"])
                posts = _ro_post_attribution(c)
                cards.append({**c, "counts": counts,
                              "total_posts": sum(counts.values()),
                              "clicks": sum(p["clicks"] for p in posts),
                              "fans": sum(p["fans"] for p in posts)})
        return render_template("rollout_dashboard.html", active_page="rollout",
                               campaigns=cards, rollout_user=user, **ctx)

    @app.route("/rollout-studio/new", methods=["GET", "POST"])
    def rollout_new():
        user = current_user()
        if user is None:
            return login_required_redirect()
        ml_campaigns = mls.list_campaigns(user["id"])
        if request.method == "POST":
            f = request.form
            platforms = [k for k, _, _ in rollout_engine.PLATFORMS if f.get("pf_" + k)]
            if not platforms:
                # Nothing ticked. Rather than a fixed default, start from
                # the platforms this artist's past rollouts actually
                # converted on - and fall back to the fixed list when
                # there is not enough traffic to say.
                platforms = rollout_learning.suggested_platforms(
                    _rollout_learning(user["id"]),
                    [k for k, _, _ in rollout_engine.PLATFORMS],
                    ["instagram_reels", "tiktok", "x"])
            ml_id = f.get("ml_campaign_id") or None
            if ml_id and mls.get_campaign(ml_id, user["id"]) is None:
                ml_id = None
            cid = ros.create_campaign(user["id"], {
                "title": (f.get("title") or "").strip()[:120],
                "artist_name": (f.get("artist_name") or "").strip()[:120],
                "release_date": (f.get("release_date") or "").strip()[:10],
                "rollout_length": f.get("rollout_length") or 14,
                "goal": f.get("goal") if f.get("goal") in dict(rollout_engine.CAMPAIGN_GOALS) else "presaves",
                "tone": f.get("tone") if f.get("tone") in dict(rollout_engine.TONES) else "premium",
                "platforms": platforms,
                "ml_campaign_id": ml_id,
            })
            # Creative uploads: art + optional video, plus lyrics text.
            for field, kind in (("art_file", "image"), ("video_file", "video")):
                up = request.files.get(field)
                if up and up.filename:
                    ext = up.filename.rsplit(".", 1)[-1].lower()
                    allowed = ("png", "jpg", "jpeg", "webp") if kind == "image" else ("mp4", "mov", "webm")
                    if ext in allowed:
                        fname = "ro_%s_%s.%s" % (cid, kind, ext)
                        up.save(os.path.join(UPLOADS_DIR, fname))
                        ros.add_asset(cid, kind, file_path="/uploads/" + fname)
            lyrics = (f.get("lyrics") or "").strip()[:8000]
            if lyrics:
                ros.add_asset(cid, "lyrics", lyrics_text=lyrics)
            return redirect("/rollout-studio/%s" % cid)
        return render_template("rollout_new.html", active_page="rollout",
                               engine=rollout_engine, ml_campaigns=ml_campaigns,
                               **build_dashboard_context())

    @app.route("/rollout-studio/<cid>/generate", methods=["POST"])
    def rollout_generate(cid):
        campaign, err = _ro_owned(cid)
        if err:
            return err
        assets = ros.list_assets(cid)
        lyrics = next((a["lyrics_text"] for a in assets if a["asset_type"] == "lyrics"), "")
        video = next((a["id"] for a in assets if a["asset_type"] == "video"), None)
        image = next((a["id"] for a in assets if a["asset_type"] == "image"), None)
        ros.clear_posts(cid)
        posts = rollout_engine.generate_rollout(campaign, lyrics=lyrics,
                                                video_asset_id=video, image_asset_id=image)
        for p in posts:
            # One tracked Links variant per post — the attribution backbone.
            if campaign.get("ml_campaign_id"):
                vname = rollout_engine.variant_name(p["platform"], p["phase"],
                                                    p["scheduled_date"])
                vslug = _ml_slug(vname.replace("_", "-"))
                p["variant_id"] = mls.create_variant(
                    campaign["ml_campaign_id"], vname, vslug,
                    utm_source=p["platform"], utm_medium="rollout")
            ros.add_post(cid, p)
        ros.set_status(cid, "generated")
        store.notify(campaign["user_id"], "rollout",
                     "Rollout generated: %s" % campaign["title"],
                     "%d posts drafted across the release arc — review and approve." % len(posts),
                     "/rollout-studio/%s/posts" % cid)
        return redirect("/rollout-studio/%s" % cid)

    @app.route("/rollout-studio/<cid>")
    def rollout_overview(cid):
        campaign, err = _ro_owned(cid)
        if err:
            return err
        posts = _ro_post_attribution(campaign)
        assets = ros.list_assets(cid)
        ml_campaign = (mls.get_campaign(campaign["ml_campaign_id"])
                       if campaign.get("ml_campaign_id") else None)
        variants = ({v["id"]: v for v in mls.list_variants(campaign["ml_campaign_id"])}
                    if campaign.get("ml_campaign_id") else {})
        return render_template("rollout_overview.html", active_page="rollout",
                               c=campaign, posts=posts, assets=assets,
                               ml_campaign=ml_campaign, variants=variants,
                               direction=rollout_engine.creative_direction(campaign),
                               next_action=(
                                   rollout_learning.next_action_line(
                                       _rollout_learning(user["id"]))
                                   if posts and all(
                                       p["status"] != "draft" for p in posts)
                                   else None)
                               or rollout_engine.next_action(campaign, posts, assets),
                               counts=ros.post_status_counts(cid),
                               phase_names=rollout_engine.PHASE_NAMES,
                               platform_names=rollout_engine.PLATFORM_NAMES,
                               **build_dashboard_context())

    @app.route("/rollout-studio/<cid>/posts", methods=["GET", "POST"])
    def rollout_posts(cid):
        campaign, err = _ro_owned(cid)
        if err:
            return err
        if request.method == "POST":
            post = ros.get_post(request.form.get("post_id") or "")
            if post and post["campaign_id"] == cid:
                action = request.form.get("action")
                if action == "approve":
                    ros.update_post(post["id"], {"status": "approved"})
                elif action == "reject":
                    ros.update_post(post["id"], {"status": "rejected"})
                elif action == "posted":
                    ros.update_post(post["id"], {
                        "status": "posted",
                        "published_url": (request.form.get("published_url") or "").strip()[:300]})
                elif action == "save":
                    ros.update_post(post["id"], {
                        "caption": (request.form.get("caption") or "").strip()[:2200],
                        "hashtags": (request.form.get("hashtags") or "").strip()[:300],
                        "scheduled_date": (request.form.get("scheduled_date") or "").strip()[:10]})
            return redirect("/rollout-studio/%s/posts" % cid)
        posts = _ro_post_attribution(campaign)
        variants = ({v["id"]: v for v in mls.list_variants(campaign["ml_campaign_id"])}
                    if campaign.get("ml_campaign_id") else {})
        ml_campaign = (mls.get_campaign(campaign["ml_campaign_id"])
                       if campaign.get("ml_campaign_id") else None)
        # Per-platform recasts: rule-built from each post's own caption,
        # the campaign's real tracked link, and the Twin's do-not-say list.
        user = current_user()
        twin_cfg = store.get_twin_settings(user["id"]) if user else None
        avoid = [p.strip() for p in
                 ((twin_cfg or {}).get("do_not_say") or "").split(",")
                 if p.strip()]
        assets = {a["id"]: a for a in ros.list_assets(cid)}
        for p in posts:
            v = variants.get(p["variant_id"])
            link = (request.url_root.rstrip("/") + "/l/" + ml_campaign["slug"]
                    + "?v=" + v["slug"]) if (v and ml_campaign) else ""
            p["casts"] = rollout_engine.platform_casts(
                p["caption"], p["hashtags"], campaign["title"], link, avoid)
            p["asset"] = assets.get(p["asset_id"])
        return render_template("rollout_posts.html", active_page="rollout",
                               c=campaign, posts=posts, variants=variants,
                               ml_campaign=ml_campaign, avoid_count=len(avoid),
                               phase_names=rollout_engine.PHASE_NAMES,
                               platform_names=rollout_engine.PLATFORM_NAMES,
                               **build_dashboard_context())

    @app.route("/rollout-studio/<cid>/storyboard", methods=["GET", "POST"])
    def rollout_storyboard(cid):
        campaign, err = _ro_owned(cid)
        if err:
            return err
        user = current_user()
        if request.method == "POST":
            # Attach a Vault asset to a post: the file is referenced from the
            # user's own vault listing — nothing else is reachable by id.
            post = ros.get_post(request.form.get("post_id") or "")
            vid = request.form.get("vault_id") or ""
            if post and post["campaign_id"] == cid:
                if vid == "":
                    ros.update_post(post["id"], {"asset_id": None})
                else:
                    v = next((v for v in store.list_vault_files(user["id"])
                              if v["id"] == vid), None)
                    if v:
                        ext = v["path"].rsplit(".", 1)[-1].lower()
                        atype = ("video" if ext in ("mp4", "mov")
                                 else "image" if ext in ("png", "jpg", "jpeg",
                                                         "webp", "gif")
                                 else "file")
                        aid = ros.add_asset(cid, atype, v["path"])
                        ros.update_post(post["id"], {"asset_id": aid})
            return redirect("/rollout-studio/%s/storyboard" % cid)
        posts = _ro_post_attribution(campaign)
        assets = {a["id"]: a for a in ros.list_assets(cid)}
        for p in posts:
            p["asset"] = assets.get(p["asset_id"])
        vault = store.list_vault_files(user["id"])
        return render_template("rollout_storyboard.html", active_page="rollout",
                               c=campaign, posts=posts, vault=vault,
                               phase_names=rollout_engine.PHASE_NAMES,
                               platform_names=rollout_engine.PLATFORM_NAMES,
                               **build_dashboard_context())

    @app.route("/rollout-studio/<cid>/calendar")
    def rollout_calendar(cid):
        campaign, err = _ro_owned(cid)
        if err:
            return err
        posts = ros.list_posts(cid)
        by_date = {}
        for p in posts:
            by_date.setdefault(p["scheduled_date"], []).append(p)
        return render_template("rollout_calendar.html", active_page="rollout",
                               c=campaign, by_date=sorted(by_date.items()),
                               phase_names=rollout_engine.PHASE_NAMES,
                               platform_names=rollout_engine.PLATFORM_NAMES,
                               **build_dashboard_context())

    @app.route("/rollout-studio/<cid>/performance")
    def rollout_performance(cid):
        campaign, err = _ro_owned(cid)
        if err:
            return err
        posts = _ro_post_attribution(campaign)
        ranked = sorted(posts, key=lambda p: (p["fans"], p["clicks"], p["visits"]),
                        reverse=True)
        by_platform = {}
        for p in posts:
            agg = by_platform.setdefault(p["platform"], {"visits": 0, "clicks": 0, "fans": 0})
            for k in agg:
                agg[k] += p[k]
        return render_template("rollout_performance.html", active_page="rollout",
                               c=campaign, posts=ranked, by_platform=by_platform,
                               totals={"visits": sum(p["visits"] for p in posts),
                                       "clicks": sum(p["clicks"] for p in posts),
                                       "fans": sum(p["fans"] for p in posts)},
                               phase_names=rollout_engine.PHASE_NAMES,
                               platform_names=rollout_engine.PLATFORM_NAMES,
                               **build_dashboard_context())

    @app.route("/rollout-studio/<cid>/socials")
    def rollout_socials(cid):
        campaign, err = _ro_owned(cid)
        if err:
            return err
        return render_template("rollout_socials.html", active_page="rollout",
                               c=campaign, providers=social_providers.provider_status(),
                               **build_dashboard_context())

    @app.route("/links/fans")
    def ml_fans():
        user = current_user()
        if user is None:
            return login_required_redirect()
        q = (request.args.get("q") or "").strip()
        fans = mls.list_fans(user["id"], q)
        campaigns = {c["id"]: c["title"] for c in mls.list_campaigns(user["id"])}
        return render_template("links_fans.html", active_page="links",
                               fans=fans, q=q, campaign_titles=campaigns,
                               intent_tones=links_engine.INTENT_TONES,
                               **build_dashboard_context())

    @app.route("/links/fans/export.csv")
    def ml_fans_export():
        user = current_user()
        if user is None:
            return login_required_redirect()
        import csv as _csv
        import io as _io
        out = _io.StringIO()
        w = _csv.writer(out)
        w.writerow(["Email", "Name", "Visits", "Clicks", "Pre-saves", "Captures",
                    "Intent Score", "Intent Level", "First Seen", "Last Active"])
        for f in mls.list_fans(user["id"]):
            w.writerow([f["email"], f["name"], f["total_visits"], f["total_clicks"],
                        f["total_presaves"], f["total_captures"], f["intent_score"],
                        f["intent_level"], f["created"], f["updated"]])
        return Response(out.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=street-banker-fans.csv"})

    @app.route("/links/create", methods=["POST"])
    def links_create():
        payload = request.get_json(silent=True) or {}
        link = create_smart_link(payload.get("title", ""), payload.get("platforms", []))
        if link is None:
            return jsonify({"ok": False, "error": "A title and at least one platform are required."}), 400
        # Universal link: if the artist pasted a track URL, resolve every
        # platform via Odesli and serve a branded all-platform landing page.
        meta = odesli_lookup(payload.get("source_url", ""))
        from urllib.parse import quote
        target = (meta or {}).get("page") or \
            "https://open.spotify.com/search/" + quote(payload.get("title", "").strip())
        user = current_user()
        slug = store.create_db_link(link["slug"], user["id"] if user else None,
                                    link["title"], target, link["platforms"], meta=meta)
        link["slug"] = slug
        link["url"] = request.host_url.rstrip("/") + "/l/" + slug
        link["real"] = True
        link["universal"] = bool(meta)
        link["platform_count"] = len((meta or {}).get("links", {}))
        return jsonify({"ok": True, "link": link})

    def _royalty_type_page(bucket, active):
        user = current_user()
        if user is None:
            return login_required_redirect()
        return render_template("royalty_type.html", active_page=active,
                               rt=royalty_types.type_report(user["id"], bucket),
                               **build_dashboard_context())

    @app.route("/publishing")
    def publishing():
        return _royalty_type_page("publishing", "publishing")

    @app.route("/neighboring-rights")
    def neighboring_rights():
        return _royalty_type_page("neighboring", "neighboring")

    @app.route("/sync")
    def sync():
        ctx = build_dashboard_context()
        ctx["sync"] = get_sync_data()
        return render_template("sync.html", active_page="sync", **ctx)

    @app.route("/territories")
    def territories():
        user = current_user()
        if user is None:
            return login_required_redirect()
        return render_template("territories.html", active_page="territories",
                               tr=royalty_types.territory_report(user["id"]),
                               **build_dashboard_context())

    @app.route("/mechanicals")
    def mechanicals():
        return _royalty_type_page("mechanical", "mechanicals")

    @app.route("/insights")
    def insights():
        user = current_user()
        if user is None:
            return login_required_redirect()
        return render_template("insights.html", active_page="insights",
                               items=insights_engine.build_insights(user["id"]),
                               **build_dashboard_context())

    @app.route("/benchmark")
    def benchmark():
        ctx = build_dashboard_context()
        ctx["benchmark"] = get_benchmark_data()
        return render_template("benchmark.html", active_page="benchmark", **ctx)

    def _ago(created):
        try:
            then = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if then.tzinfo is None:
                then = then.replace(tzinfo=timezone.utc)
            mins = int((datetime.now(timezone.utc) - then).total_seconds() // 60)
        except (ValueError, AttributeError):
            return ""
        if mins < 60:
            return "just now" if mins < 2 else "%dm ago" % mins
        if mins < 60 * 48:
            return "%dh ago" % (mins // 60)
        return "%dd ago" % (mins // (60 * 24))

    COLLAB_ROLES = ["Vocalist", "Producer", "Songwriter", "Mixing / Mastering",
                    "Instrumentalist", "Visuals / Cover Art"]

    @app.route("/marketplace")
    def marketplace():
        user = current_user()
        if user is None:
            return login_required_redirect()
        kind = request.args.get("kind") or None
        role = request.args.get("role") or None
        genre = (request.args.get("genre") or "").strip() or None
        reqs = store.list_collab_requests(kind, role, genre)
        today = datetime.now(timezone.utc).date().isoformat()
        trust_cache = {}
        for r in reqs:
            r["ago"] = _ago(r["created"])
            if r["user_id"] not in trust_cache:
                trust_cache[r["user_id"]] = trust_score.calculate(r["user_id"])["total"]
            r["trust"] = trust_cache[r["user_id"]]
            r["expired"] = bool(r["closes"]) and r["closes"] < today
        reqs = [r for r in reqs if not r["expired"]]
        own = store.list_own_collab_requests(user["id"])
        return render_template(
            "marketplace.html", active_page="marketplace",
            requests=reqs, kind=kind or "", role=role or "", genre=genre or "",
            roles=COLLAB_ROLES, user=user,
            saves=store.list_collab_saves(user["id"]),
            own=own,
            replies_by_req={r["id"]: store.list_collab_replies(r["id"]) for r in own},
            **build_dashboard_context())

    @app.route("/marketplace/post", methods=["POST"])
    def marketplace_post():
        user = current_user()
        if user is None:
            return login_required_redirect()
        kind = request.form.get("kind") or ""
        role = (request.form.get("role") or "").strip()
        title = (request.form.get("title") or "").strip()
        if kind in ("bid", "split", "fun") and role and title:
            store.add_collab_request(
                user["id"], role,
                (request.form.get("genre") or "").strip(), kind, title,
                (request.form.get("details") or "").strip(),
                (request.form.get("terms") or "").strip(),
                (request.form.get("ref_url") or "").strip(),
                (request.form.get("closes") or "").strip())
        return redirect("/marketplace")

    @app.route("/marketplace/<req_id>/apply", methods=["POST"])
    def marketplace_apply(req_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        req = store.get_collab_request(req_id)
        message = (request.form.get("message") or "").strip()
        contact = (request.form.get("contact") or "").strip()
        if (req is None or req["status"] != "open"
                or req["user_id"] == user["id"] or not message
                or "@" not in contact):
            return redirect("/marketplace")
        store.add_collab_reply(req_id, user["id"], message, contact,
                               (request.form.get("proposal") or "").strip(),
                               (request.form.get("ref_url") or "").strip())
        store.notify(req["user_id"], "network",
                     "New application on your collab request",
                     "%s applied to “%s” — reach them at %s."
                     % (user["name"] or "A member", req["title"], contact),
                     "/marketplace")
        if emailer.configured():
            import html as _html
            owner = store.get_user(req["user_id"])
            if owner:
                emailer.send(
                    owner["email"], "New application on your collab request",
                    "<p><b>%s</b> applied to “%s”:</p><p>%s</p>"
                    "<p>Reach them at <a href=\"mailto:%s\">%s</a>.</p>"
                    % (_html.escape(user["name"] or "A member"),
                       _html.escape(req["title"]),
                       _html.escape(message[:500]), _html.escape(contact),
                       _html.escape(contact)))
        return redirect("/marketplace?applied=1")

    @app.route("/marketplace/<req_id>/save", methods=["POST"])
    def marketplace_save(req_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        if store.get_collab_request(req_id):
            store.toggle_collab_save(user["id"], req_id)
        return redirect("/marketplace")

    @app.route("/marketplace/<req_id>/close", methods=["POST"])
    def marketplace_close(req_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        store.close_collab_request(user["id"], req_id)
        return redirect("/marketplace")

    @app.route("/marketplace/<req_id>/delete", methods=["POST"])
    def marketplace_delete(req_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        store.delete_collab_request(user["id"], req_id)
        return redirect("/marketplace")

    @app.route("/discover")
    def discover():
        ctx = build_dashboard_context()
        ctx["discover"] = get_discover_data(request.args)
        # Real music search: iTunes catalog with artwork + 30s previews.
        q = (request.args.get("q") or "").strip()
        ctx["real_query"] = q
        ctx["real_results"] = itunes_search(q) if q else []
        return render_template("discover.html", active_page="discover", **ctx)

    @app.route("/discover/like/<track_id>", methods=["POST"])
    def discover_like_route(track_id):
        res = like_track(track_id)
        if res is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, **res})

    @app.route("/discover/follow/<artist_id>", methods=["POST"])
    def discover_follow_route(artist_id):
        return jsonify({"ok": True, **follow_artist(artist_id)})

    @app.route("/network")
    def network():
        user = current_user()
        ctx = build_dashboard_context()
        ctx["network"] = get_network_data(request.args)
        ctx["outreach"] = store.list_outreach(user["id"]) if user else []
        ctx["outreach_stages"] = store.OUTREACH_STAGES
        return render_template("network.html", active_page="network", **ctx)

    @app.route("/network/outreach/add", methods=["POST"])
    def outreach_add():
        user = current_user()
        if user is None:
            return login_required_redirect()
        contact = (request.form.get("contact") or "").strip()
        if contact:
            store.add_outreach(user["id"], contact,
                               (request.form.get("role") or "").strip(),
                               request.form.get("stage") or "saved",
                               (request.form.get("notes") or "").strip())
        return redirect("/network?tab=my")

    @app.route("/network/outreach/<item_id>/stage", methods=["POST"])
    def outreach_stage(item_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        store.set_outreach_stage(user["id"], item_id,
                                 request.form.get("stage") or "")
        return redirect("/network?tab=my")

    @app.route("/network/outreach/<item_id>/delete", methods=["POST"])
    def outreach_delete(item_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        store.delete_outreach(user["id"], item_id)
        return redirect("/network?tab=my")

    @app.route("/network/playlist/<playlist_id>")
    def network_playlist(playlist_id):
        pl = get_playlist(playlist_id)
        if pl is None:
            return redirect(url_for("network"))
        ctx = build_dashboard_context()
        ctx["playlist"] = pl
        ctx["curator"] = get_profile(pl["curator_id"])
        return render_template("network_playlist.html", active_page="network", **ctx)

    @app.route("/network/playlist/<playlist_id>/submit", methods=["POST"])
    def network_submit_route(playlist_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        data = request.get_json(silent=True) or {}
        entry = submit_to_playlist(playlist_id, data.get("song"), data.get("message"))
        if entry is None:
            return jsonify({"ok": False, "error": "This playlist isn't accepting submissions, or no track was selected."}), 400
        # A record of what this account sent, filed to this account.
        store.add_inbox("playlist_submission", entry, user_id=user["id"])
        return jsonify({"ok": True})

    @app.route("/network/<profile_id>")
    def network_profile(profile_id):
        profile = get_profile(profile_id)
        if profile is None:
            return redirect(url_for("network"))
        ctx = build_dashboard_context()
        ctx["profile"] = profile
        return render_template("network_profile.html", active_page="network", **ctx)

    @app.route("/network/<profile_id>/connect", methods=["POST"])
    def network_connect_route(profile_id):
        status = network_connect_action(profile_id)
        if status is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "status": status})

    @app.route("/network/<profile_id>/pitch", methods=["POST"])
    def network_pitch_route(profile_id):
        data = request.get_json(silent=True) or {}
        entry = network_pitch_action(profile_id, data.get("message"), data.get("song"))
        if entry is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True})

    @app.route("/network/<profile_id>/enquire", methods=["POST"])
    def network_enquire_route(profile_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        data = request.get_json(silent=True) or {}
        entry = enquire_show(profile_id, data.get("city"), data.get("date"), data.get("message"))
        if entry is None:
            return jsonify({"ok": False, "error": "This profile isn't taking booking enquiries."}), 400
        store.add_inbox("booking_enquiry", entry, user_id=user["id"])
        return jsonify({"ok": True})

    @app.route("/network/moment/<moment_id>")
    def network_moment(moment_id):
        moment = get_moment(moment_id)
        if moment is None:
            return redirect(url_for("network"))
        ctx = build_dashboard_context()
        ctx["moment"] = moment
        return render_template("network_moment.html", active_page="network", **ctx)

    @app.route("/network/moment/<moment_id>/claim", methods=["POST"])
    def network_claim_route(moment_id):
        serial = claim_moment(moment_id)
        if serial is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "serial": serial})

    @app.route("/fan-label")
    def fan_label():
        ctx = build_dashboard_context()
        ctx["fan_label"] = get_fan_label_data()
        return render_template("fan_label.html", active_page="fan-label", **ctx)

    @app.route("/fan-label/vote/<demo_id>", methods=["POST"])
    def fan_label_vote(demo_id):
        votes = vote_demo(demo_id)
        if votes is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "votes": votes})

    @app.route("/fans")
    def fans():
        """Real fan records for a real account; the showcase only for the demo.

        This page used to hand community_config's invented figures - 1,240
        superfans, a leaderboard of made-up handles and spend - to every
        account, under a line reading "the app doesn't track individual fans".
        Both halves were wrong: the numbers were nobody's, and the Fan CRM at
        /links/fans has held named fans with intent scores since smart links
        shipped.

        Same rule as the royalty dashboard, for the same reason: showcase data
        handed to a real artist reads as their own.
        """
        import fan_dashboard

        ctx = build_dashboard_context()
        user = current_user()
        if _session_is_demo() or user is None:
            ctx["fans"] = get_fan_dashboard_data()
            ctx["fans"]["is_real"] = False
        else:
            ctx["fans"] = fan_dashboard.fan_dashboard_for(user["id"])
        return render_template("fans.html", active_page="fans", **ctx)

    @app.route("/capital")
    def capital():
        ctx = build_dashboard_context()
        ctx["capital"] = get_capital_data()
        return render_template("capital.html", active_page="capital", **ctx)

    @app.route("/services")
    def services():
        ctx = build_dashboard_context()
        ctx["label"] = get_label_data()
        return render_template("services.html", active_page="services", **ctx)

    @app.route("/apparel")
    def apparel():
        # The label store, embedded when the store's own Buy Button
        # credentials are set and linked when they are not. No payment
        # code on this side either way.
        ctx = build_dashboard_context()
        ctx["label"] = get_label_data()
        ctx["shopify"] = shopify_buy.context()
        user = current_user()
        ctx["is_owner"] = bool(user and _is_owner_email(user.get("email")))
        return render_template("apparel.html", active_page="apparel", **ctx)

    @app.route("/services/<slug>")
    def service_detail(slug):
        service = get_service(slug)
        if service is None:
            return redirect(url_for("services"))
        ctx = build_dashboard_context()
        ctx["label"] = get_label_data()
        ctx["service"] = service
        return render_template("service_detail.html", active_page="services", **ctx)

    @app.route("/submit")
    def submit():
        ctx = build_dashboard_context()
        ctx["label"] = get_label_data()
        # Full-page designed image with clickable HTML overlays; the coded
        # page renders as the fallback until the file exists.
        ctx["submit_page_img"] = (
            "/static/img/submit-page.png"
            if os.path.exists(os.path.join(app.static_folder, "img", "submit-page.png"))
            else None
        )
        # Photoreal turntable crop (used by the coded fallback layout).
        ctx["turntable_img"] = (
            "/static/img/turntable.png"
            if os.path.exists(os.path.join(app.static_folder, "img", "turntable.png"))
            else None
        )
        return render_template("submit.html", active_page="submit", **ctx)

    @app.route("/audience")
    def audience():
        ctx = build_dashboard_context()
        ctx["audience"] = get_audience_data()
        return render_template("audience.html", active_page="audience", **ctx)

    @app.route("/playlists")
    def playlists():
        ctx = build_dashboard_context()
        ctx["playlists"] = get_playlists_data()
        return render_template("playlists.html", active_page="playlists", **ctx)

    @app.route("/stats")
    def stats():
        user = current_user()
        if user is None:
            return login_required_redirect()
        profile = store.get_pulse_profile(user["id"])
        pulse, deezer = None, None
        if profile and spotify.pulse_configured():
            pulse = spotify.artist_pulse(profile["artist_id"])
            if pulse:
                deezer = music_apis.deezer_artist_fans(pulse["name"])
                store.record_pulse_snapshot(user["id"], pulse["followers"],
                                            pulse["popularity"],
                                            (deezer or {}).get("fans", 0))
        snapshots = store.list_pulse_snapshots(user["id"])
        # Real engagement from tracked smart links.
        clicks = pageviews = presaves = 0
        for c in mls.list_campaigns(user["id"]):
            n = mls.event_counts(c["id"])
            pageviews += n.get("pageview", 0)
            clicks += n.get("click", 0)
            presaves += store.count_spotify_presaves(c["id"]).get("pending", 0) + \
                store.count_spotify_presaves(c["id"]).get("completed", 0)
        return render_template("stats.html", active_page="stats",
                               pulse_configured=spotify.pulse_configured(),
                               profile=profile, pulse=pulse, deezer=deezer,
                               snapshots=snapshots,
                               link_stats={"pageviews": pageviews, "clicks": clicks,
                                           "presaves": presaves},
                               **build_dashboard_context())

    @app.route("/funding")
    def funding():
        user = current_user()
        if user is None:
            return login_required_redirect()
        ctx = build_dashboard_context()
        # From the artist's own statements. This page used to quote a
        # suggested advance - with a Request button under it - scaled off
        # a hardcoded earnings trend identical for every account.
        elig = capital_engine.advance_eligibility(user["id"])
        ctx["advance_eligibility"] = elig
        ctx["funding"] = get_funding_data(elig)
        return render_template("funding.html", active_page="funding", **ctx)

    @app.route("/funding/request", methods=["POST"])
    def funding_request():
        payload = request.get_json(silent=True) or {}
        offer_id = (payload.get("offer_id") or "").strip()
        user = current_user()
        if user is None:
            return jsonify({"error": "auth required"}), 401
        data = get_funding_data(capital_engine.advance_eligibility(user["id"]))
        offer = next((o for o in data["offers"] if o["id"] == offer_id), None)
        if offer is None:
            return jsonify({"ok": False, "error": "Unknown offer."}), 400
        # Simulated only: record interest and return a reference. No money
        # moves and no application is actually submitted.
        reference = "REQ-" + offer_id.split("-")[-1].upper() + "-" + datetime.today().strftime("%Y%m%d")
        return jsonify({"ok": True, "reference": reference, "offer": offer["name"]})

    _DOC_TYPES = ["Split Agreement", "Producer Agreement", "Feature Agreement",
                  "Distribution", "Publishing", "Sync License", "Statement",
                  "Registration", "Other"]
    _DOC_EXTS = ("pdf", "doc", "docx", "txt", "csv", "png", "jpg", "jpeg", "webp")

    @app.route("/documents", methods=["GET", "POST"])
    def documents():
        user = current_user()
        error = None
        if request.method == "POST":
            if user is None:
                return login_required_redirect()
            f = request.files.get("document")
            if f is None or not f.filename:
                error = "Choose a file to upload."
            else:
                ext = f.filename.rsplit(".", 1)[-1].lower()
                if ext not in _DOC_EXTS:
                    error = "Use PDF, DOC/DOCX, TXT, CSV, or an image file."
                else:
                    fname = "doc_%s.%s" % (uuid.uuid4().hex, ext)
                    f.save(os.path.join(UPLOADS_DIR, fname))
                    path = "/uploads/" + fname
                    store.register_stored_asset(user["id"], path, "private", "document")
                    doc_type = request.form.get("doc_type") or "Other"
                    store.add_document(user["id"], f.filename, path,
                                       doc_type if doc_type in _DOC_TYPES else "Other",
                                       (request.form.get("note") or "").strip(),
                                       (request.form.get("track") or "").strip())
                    return redirect("/documents")
        ctx = build_dashboard_context()
        ctx["docs_user"] = user
        ctx["real_docs"] = store.list_documents(user["id"]) if user else []
        ctx["doc_types"] = _DOC_TYPES
        ctx["doc_error"] = error
        return render_template(
            "documents.html", active_page="documents",
            documents_view=documents_engine.build(user["id"]) if user else None,
            documents_per_track_types=documents_engine.PER_TRACK_TYPES,
            documents_catalog_types=documents_engine.CATALOG_TYPES, **ctx)

    @app.route("/documents/<doc_id>/delete", methods=["POST"])
    def document_delete(doc_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        path = store.delete_document(user["id"], doc_id)
        if path:
            try:
                os.remove(os.path.join(UPLOADS_DIR, os.path.basename(path)))
            except OSError:
                pass
            store.delete_stored_asset(user["id"], path)
        return redirect("/documents")

    @app.route("/identifiers")
    def identifiers():
        ctx = build_dashboard_context()
        user = current_user()
        ctx["ids_user"] = user
        tracks = store.get_catalog_tracks(user["id"]) if user else []
        rows = []
        for t in tracks:
            m = t.get("meta") or {}
            rows.append({"title": t["title"], "artist": t["artist"],
                         "isrc": m.get("isrc") or "", "upc": m.get("upc") or "",
                         "label": m.get("label") or "",
                         "release_date": m.get("release_date") or ""})
        ctx["real_ids"] = rows
        ctx["ids_with_isrc"] = sum(1 for r in rows if r["isrc"])
        ctx["ids_with_upc"] = sum(1 for r in rows if r["upc"])
        return render_template("identifiers.html", active_page="identifiers", **ctx)

    @app.route("/conflicts")
    def conflicts():
        return render_template("conflicts.html", active_page="conflicts", **build_dashboard_context())

    # Milestone presets are parameterized date math over each campaign's
    # own release date — nothing is stored, nothing is predicted.
    _SCHED_PRESETS = {"standard": ("Standard 30-day", 30),
                      "blitz": ("14-day blitz", 14),
                      "surprise": ("Surprise drop", 0)}

    def _scheduler_events(user_id, preset):
        today = date.today().isoformat()
        events = []
        warnings = []
        for c in mls.list_campaigns(user_id):
            if c.get("archived_at") or not c.get("release_date"):
                continue
            events.append({"date": c["release_date"], "kind": "release",
                           "lane": c["title"], "title": c["title"],
                           "detail": "%s release day" % (c.get("release_type") or "single"),
                           "href": "/links/%s" % c["id"],
                           "status": c["status"]})
            try:
                days_left = (date.fromisoformat(c["release_date"][:10])
                             - date.today()).days
            except ValueError:
                continue
            if 0 <= days_left < 21:
                warnings.append({
                    "campaign": c["title"], "days": days_left,
                    "level": "red" if days_left < 7 else "amber",
                    "text": ("inside the 7-day Spotify editorial minimum — "
                             "the pitch window is effectively closed"
                             if days_left < 7 else
                             "under the recommended 21-day runway — pitch "
                             "and pre-save windows are compressed"),
                    "href": "/releases/autopilot?campaign=%s" % c["id"]})
            if days_left > 0 and preset in _SCHED_PRESETS:
                plan_days = _SCHED_PRESETS[preset][1]
                if plan_days:
                    plan = artist_os.campaign_plan(plan_days, c["title"],
                                                   c["release_date"])
                    for lbl, sub, tasks in plan["windows"]:
                        if not lbl.endswith("days out"):
                            continue
                        offset = int(lbl.split(" ")[0])
                        mdate = (date.fromisoformat(c["release_date"][:10])
                                 - timedelta(days=offset)).isoformat()
                        if mdate < today:
                            continue
                        events.append({
                            "date": mdate, "kind": "milestone",
                            "lane": c["title"],
                            "title": "%s — %s" % (sub, c["title"]),
                            "detail": tasks[0],
                            "href": "/releases/autopilot?campaign=%s&days=%d"
                                    % (c["id"], plan_days),
                            "status": lbl})
        for r in ros.list_campaigns(user_id):
            for p in ros.list_posts(r["id"]):
                if not p.get("scheduled_date"):
                    continue
                events.append({"date": p["scheduled_date"], "kind": "post",
                               "lane": r["title"],
                               "title": "%s post — %s" % (p.get("platform", "").title(),
                                                          r["title"]),
                               "detail": (p.get("caption") or "")[:90],
                               "href": "/rollout-studio/%s" % r["id"],
                               "status": p["status"]})
        events.sort(key=lambda e: e["date"])
        return events, warnings

    @app.route("/releases")
    def releases():
        user = current_user()
        if user is None:
            return login_required_redirect()
        preset = request.args.get("preset") or "off"
        if preset not in _SCHED_PRESETS:
            preset = "off"
        today = date.today().isoformat()
        events, warnings = _scheduler_events(user["id"], preset)
        upcoming = [e for e in events if e["date"] >= today]
        past = [e for e in events if e["date"] < today][-15:]
        # Swimlanes: one horizontal track per campaign over the next 90 days.
        horizon = 90
        lanes = []
        for e in upcoming:
            try:
                off = (date.fromisoformat(e["date"][:10]) - date.today()).days
            except ValueError:
                continue
            if off > horizon:
                continue
            lane = next((l for l in lanes if l["name"] == e["lane"]), None)
            if lane is None:
                lane = {"name": e["lane"], "events": []}
                lanes.append(lane)
            lane["events"].append(dict(e, pct=round(off / horizon * 100, 1)))
        # Group upcoming by month for the calendar rail.
        months = []
        for e in upcoming:
            label = e["date"][:7]
            if not months or months[-1]["month"] != label:
                months.append({"month": label, "events": []})
            months[-1]["events"].append(e)
        return render_template("releases.html", active_page="releases",
                               months=months, past=past, lanes=lanes,
                               warnings=warnings, preset=preset,
                               presets=_SCHED_PRESETS,
                               total_upcoming=len(upcoming),
                               **build_dashboard_context())

    @app.route("/releases/calendar.ics")
    def releases_ics():
        """One-way iCalendar feed of the same derived events — import it
        into Google/Apple/Outlook. (Two-way sync would need their OAuth
        apps; this file is honest about being an export.)"""
        user = current_user()
        if user is None:
            return login_required_redirect()
        preset = request.args.get("preset") or "off"
        events, _w = _scheduler_events(user["id"], preset)
        def esc(s):
            return (s or "").replace("\\", "\\\\").replace(";", "\\;") \
                            .replace(",", "\\,").replace("\n", "\\n")
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
                 "PRODID:-//Street Banker//Release Scheduler//EN"]
        for i, e in enumerate(events):
            d = e["date"][:10].replace("-", "")
            lines += ["BEGIN:VEVENT",
                      "UID:sb-%s-%d@streetbanker" % (d, i),
                      "DTSTART;VALUE=DATE:" + d,
                      "SUMMARY:" + esc(e["title"]),
                      "DESCRIPTION:" + esc(e["detail"]),
                      "END:VEVENT"]
        lines.append("END:VCALENDAR")
        return Response("\r\n".join(lines), mimetype="text/calendar",
                        headers={"Content-Disposition":
                                 "attachment; filename=street-banker-releases.ics"})

    @app.route("/registration")
    def registration():
        return render_template("registration.html", active_page="registration", **build_dashboard_context())

    @app.route("/search")
    def search_route():
        ctx = build_dashboard_context()
        user = current_user()
        ctx["search_results"] = global_search(
            request.args.get("q", ""),
            user_id=(user or {}).get("id"),
            demo=_is_demo_email((user or {}).get("email") or ""))
        return render_template("search.html", active_page="search", **ctx)

    @app.route("/notifications")
    def notifications():
        ctx = build_dashboard_context()
        user = current_user()
        if user:
            items = store.list_notifications(user["id"])
            store.mark_notifications_read(user["id"])  # viewing clears the badge
            return render_template("notifications_real.html", active_page="notifications",
                                   items=items, **ctx)
        ctx["notifications_data"] = get_notifications_data()
        return render_template("notifications.html", active_page="notifications", **ctx)

    @app.route("/notifications/<notification_id>/read", methods=["POST"])
    def notification_read_route(notification_id):
        mark_notification_read(notification_id)
        return jsonify({"ok": True})

    @app.route("/notifications/read-all", methods=["POST"])
    def notifications_read_all_route():
        ids = [n["id"] for n in get_notifications_data()["notifications"]]
        mark_all_read(ids)
        return jsonify({"ok": True})

    @app.route("/tax")
    def tax():
        user = current_user()
        if user is None:
            return login_required_redirect()
        rows = store.get_statement_rows(user["id"])
        years = {}
        for r in rows:
            year = (r.get("period") or "")[:4]
            if not (len(year) == 4 and year.isdigit()):
                year = "Undated"
            y = years.setdefault(year, {"total": 0.0, "sources": {}, "rows": 0})
            y["total"] += r["amount"]
            y["rows"] += 1
            src = r.get("source") or "Unknown"
            y["sources"][src] = y["sources"].get(src, 0.0) + r["amount"]
        year_list = sorted([
            {"year": k, "total": round(v["total"], 2), "rows": v["rows"],
             "sources": sorted(v["sources"].items(), key=lambda s: -s[1]),
             "over_600": v["total"] >= 600}
            for k, v in years.items()], key=lambda y: y["year"], reverse=True)
        return render_template("tax.html", active_page="tax",
                               years=year_list,
                               grand_total=round(sum(y["total"] for y in year_list), 2),
                               **build_dashboard_context())

    @app.route("/billing")
    def billing():
        user = current_user()
        if user is None:
            return login_required_redirect()
        ctx = build_dashboard_context()
        ctx["billing"] = get_billing_data(ctx["account"])
        ctx["plan_cards"] = plans.PLANS
        ctx["user"] = user
        ctx["webhook_live"] = stripe_billing.webhook_configured()
        return render_template("billing.html", active_page="billing", **ctx)

    _TEAM_ROLE_OPTIONS = (
        ("manager", "Manager"),
        ("a_and_r", "A&R"),
        ("marketing", "Marketing"),
        ("publicist", "Publicist"),
        ("tour_manager", "Tour Manager"),
        ("accountant", "Accountant"),
        ("attorney", "Attorney"),
        ("creative_director", "Creative Director"),
        ("producer_engineer", "Producer / Engineer"),
        ("assistant", "Assistant"),
    )
    _TEAM_ROLES = tuple(key for key, _label in _TEAM_ROLE_OPTIONS)
    _TEAM_ROLE_LABELS = dict(_TEAM_ROLE_OPTIONS)
    _TEAM_SEAT_LIMIT = 10

    # One canonical definition drives routes, templates, and tests.
    _DIGITAL_TEAM = company_os.TEAM

    _COMPANY_INTENT = "company-os-v2"
    _COMPANY_STATUS_LABELS = {
        "proposed": "Proposed",
        "queued": "Assigned",
        "in_progress": "In progress",
        "blocked": "Blocked",
        "review": "Ready for review",
        "delivered": "Approved",
        "rejected": "Revision requested",
    }

    def _company_api_user():
        user = current_user()
        if user is None:
            return None, (jsonify({
                "ok": False, "error": "Sign in first."
            }), 401)
        if not _is_owner_email(user.get("email")):
            return None, (jsonify({
                "ok": False, "error": "Company OS is owner-only."
            }), 403)
        return user, None

    def _company_intent_error():
        supplied = request.headers.get("X-SB-Intent", "")
        if not hmac.compare_digest(supplied, _COMPANY_INTENT):
            return jsonify({
                "ok": False, "error": "Missing Company OS request intent."
            }), 403
        return None

    def _company_json(allow_status=False):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValueError("Send one JSON object.")
        forbidden = {
            "user_id", "owner_id", "actor_id", "actor_user_id",
            "created", "updated", "plan_status",
        }
        if not allow_status:
            forbidden.add("status")
        if forbidden.intersection(payload):
            raise ValueError("Ownership, status, and audit fields are server controlled.")
        return payload

    def _company_text(value, field, maximum, minimum=0, multiline=False):
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError("%s must be text." % field)
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("%s contains unsupported control characters." % field)
        clean = value.strip()
        if not multiline:
            clean = " ".join(clean.split())
        if len(clean) < minimum:
            raise ValueError("%s is too short." % field)
        if len(clean) > maximum:
            raise ValueError("%s is too long." % field)
        return clean

    def _company_version(payload):
        value = payload.get("expected_version")
        if isinstance(value, bool):
            raise ValueError("expected_version must be a non-negative integer.")
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValueError("expected_version must be a non-negative integer.")
        if value < 0:
            raise ValueError("expected_version must be a non-negative integer.")
        return value

    def _decorate_assignment(row):
        item = dict(row)
        desk = company_os.TEAM_BY_KEY.get(item.get("assignee")) or {}
        feature = company_os.capability(
            item.get("assignee"), item.get("capability")) or {}
        item["desk_name"] = desk.get("name", "Company desk")
        item["desk_role"] = desk.get("role", "Specialist")
        item["desk_initials"] = desk.get("initials", "SB")
        item["feature_name"] = feature.get("name", item.get("capability", ""))
        item["status_label"] = _COMPANY_STATUS_LABELS.get(
            item.get("status"), str(item.get("status") or "Not assigned").replace("_", " ").title())
        return item

    def _company_state(user_id):
        objectives = store.list_manager_objectives(user_id, limit=50)
        assignments = [
            _decorate_assignment(row)
            for row in store.list_manager_work_items(user_id, limit=500)
        ]
        deliverables = store.list_manager_deliverables(user_id, limit=500)
        activity = store.list_manager_activity(user_id, limit=100)
        # A newly proposed plan is the Manager's next decision even when an
        # older objective is already in progress. This keeps every new plan
        # reachable from the single-current-objective interface; after it is
        # approved, the next pending plan naturally moves into view.
        active_objective = next(
            (item for item in objectives
             if item.get("plan_status") == "pending"),
            next(
                (item for item in objectives
                 if item.get("status") not in ("delivered", "archived")),
                objectives[0] if objectives else None,
            ),
        )
        blocked = [item for item in assignments if item.get("status") == "blocked"]
        review = [item for item in assignments if item.get("status") == "review"]
        pending_deliverables = [
            item for item in deliverables
            if item.get("status") == "submitted" and item.get("work_item_id")
        ]
        pending_plans = [
            item for item in objectives if item.get("plan_status") == "pending"
        ]
        live_due = sorted(
            (item for item in assignments
             if item.get("status") not in ("delivered",)
             and item.get("due_date")),
            key=lambda item: item.get("due_date") or "9999-12-31",
        )
        mission_control = {
            "decisions_due": len(pending_plans) + len(pending_deliverables),
            "blocked_count": len(blocked),
            "review_count": len(review),
            "blocked": blocked[:5],
            "review": review[:5],
            "deliverables_for_review": pending_deliverables[:5],
            "plans_for_approval": pending_plans[:5],
            "next_deadline": live_due[0] if live_due else None,
        }
        return {
            "ok": True,
            "team": company_os.TEAM,
            "objectives": objectives,
            "assignments": assignments,
            "deliverables": deliverables,
            "activity": activity,
            "active_objective": active_objective,
            "mission_control": mission_control,
            "storage_is_ephemeral": bool(
                os.environ.get("RENDER")
                and os.environ.get("V2_DURABLE_STORAGE") != "1"),
        }

    def _company_result(result, user_id):
        payload = _company_state(user_id)
        if result:
            payload["objective"] = result.get("objective")
            payload["work_items"] = [
                _decorate_assignment(row)
                for row in result.get("work_items", [])
            ]
            if result.get("deliverable"):
                payload["deliverable"] = result["deliverable"]
        return payload

    def _company_error(exc):
        if isinstance(exc, store.ManagerNotFoundError):
            return jsonify({"ok": False, "error": str(exc)}), 404
        if isinstance(exc, store.ManagerConflictError):
            return jsonify({"ok": False, "error": str(exc)}), 409
        if isinstance(exc, (store.ManagerValidationError, ValueError)):
            return jsonify({"ok": False, "error": str(exc)}), 400
        raise exc

    @app.route("/team")
    def team():
        user = current_user()
        if user is None:
            return login_required_redirect()
        if (_signup_mode() != "open"
                and not _is_owner_email(user.get("email"))):
            abort(403)
        state = _company_state(user["id"])
        selected_key = request.args.get("desk", "manager")
        selected_desk = company_os.TEAM_BY_KEY.get(
            selected_key, company_os.TEAM_BY_KEY["manager"])
        selected_feature_key = request.args.get(
            "feature", selected_desk["capabilities"][0]["key"])
        selected_feature = company_os.capability(
            selected_desk["key"], selected_feature_key)
        if selected_feature is None:
            selected_feature = selected_desk["capabilities"][0]
        selected_assignments = [
            item for item in state["assignments"]
            if item.get("assignee") == selected_desk["key"]
        ]
        return render_template(
            "team.html",
            active_page="team",
            digital_team=_DIGITAL_TEAM,
            manager=_DIGITAL_TEAM[0],
            selected_desk=selected_desk,
            selected_feature=selected_feature,
            selected_assignments=selected_assignments,
            **state,
            **build_dashboard_context(),
        )

    @app.route("/api/company-os")
    def company_os_state():
        user, denied = _company_api_user()
        if denied:
            return denied
        return jsonify(_company_state(user["id"]))

    @app.route("/api/company-os/objectives", methods=["POST"])
    def company_os_objective_create():
        user, denied = _company_api_user()
        if denied:
            return denied
        intent_error = _company_intent_error()
        if intent_error:
            return intent_error
        try:
            payload = _company_json()
            title = _company_text(
                payload.get("title"), "Objective", 180, minimum=3)
            success = _company_text(
                payload.get("success_condition", ""),
                "Success condition", 500, minimum=3)
            project = _company_text(
                payload.get("project", ""), "Project", 100)
            target_date = (payload.get("target_date", "")
                           or payload.get("decision_deadline", "")
                           or payload.get("due_date", ""))
            target_date = _company_text(
                target_date, "Decision deadline", 10, minimum=10)
            try:
                date.fromisoformat(target_date)
            except ValueError:
                raise ValueError(
                    "Decision deadline must be a valid date.")
            priority = payload.get("priority", "normal")
            if priority not in ("low", "normal", "high", "critical"):
                raise ValueError("Choose a valid priority.")
            plan = company_os.build_operating_plan(
                title, success, target_date)
            result = store.create_manager_objective_plan(
                user["id"],
                title,
                "manager",
                plan["items"],
                success_condition=success,
                details=plan["summary"],
                due_date=target_date,
                project=project,
                objective_type=plan["objective_type"],
                routing={
                    "engine": "company-os-v2",
                    "priority": priority,
                    "desks": sorted({
                        item["assignee"] for item in plan["items"]
                    }),
                },
                plan_document=plan,
                actor_user_id=user["id"],
                source="engine",
            )
            return jsonify(_company_result(result, user["id"])), 201
        except Exception as exc:
            return _company_error(exc)

    @app.route(
        "/api/company-os/objectives/<objective_id>/approve-plan",
        methods=["POST"],
    )
    def company_os_objective_approve(objective_id):
        user, denied = _company_api_user()
        if denied:
            return denied
        intent_error = _company_intent_error()
        if intent_error:
            return intent_error
        try:
            payload = _company_json()
            result = store.approve_manager_plan(
                user["id"], objective_id,
                expected_version=_company_version(payload),
                actor_user_id=user["id"],
            )
            return jsonify(_company_result(result, user["id"]))
        except Exception as exc:
            return _company_error(exc)

    @app.route(
        "/api/company-os/assignments/<work_item_id>",
        methods=["PATCH"],
    )
    def company_os_assignment_update(work_item_id):
        user, denied = _company_api_user()
        if denied:
            return denied
        intent_error = _company_intent_error()
        if intent_error:
            return intent_error
        try:
            payload = _company_json(allow_status=True)
            status = payload.get("status")
            aliases = {
                "assigned": "queued",
                "ready_for_review": "review",
                "approved": "delivered",
            }
            status = aliases.get(status, status)
            if status not in (
                    "queued", "in_progress", "blocked", "review", "delivered"):
                raise ValueError("Choose a valid assignment state.")
            blocker = _company_text(
                payload.get("blocker", ""), "Blocker", 500,
                multiline=True)
            if status == "blocked" and not blocker:
                raise ValueError("Describe what is blocking this assignment.")
            result = store.transition_manager_work_item(
                user["id"], work_item_id, status,
                expected_version=_company_version(payload),
                blocker=blocker,
                actor_user_id=user["id"],
            )
            return jsonify(_company_result(result, user["id"]))
        except Exception as exc:
            return _company_error(exc)

    @app.route(
        "/api/company-os/assignments/<work_item_id>/deliverables",
        methods=["POST"],
    )
    def company_os_deliverable_create(work_item_id):
        user, denied = _company_api_user()
        if denied:
            return denied
        intent_error = _company_intent_error()
        if intent_error:
            return intent_error
        try:
            payload = _company_json()
            title = _company_text(
                payload.get("title"), "Deliverable title", 160, minimum=3)
            summary = _company_text(
                payload.get("summary", ""), "Deliverable summary", 5000,
                minimum=3, multiline=True)
            evidence_refs = payload.get("evidence_refs", [])
            if not isinstance(evidence_refs, list) or len(evidence_refs) > 20:
                raise ValueError("Evidence references must be a list of up to 20 items.")
            clean_refs = []
            for raw_ref in evidence_refs:
                ref = _company_text(
                    raw_ref, "Evidence reference", 500, minimum=1)
                clean_refs.append(ref)
            if not clean_refs:
                raise ValueError(
                    "Attach at least one real evidence link or owned record.")
            result = store.create_manager_deliverable(
                user["id"], work_item_id,
                kind="text",
                title=title,
                body=summary,
                metadata={"evidence_refs": clean_refs},
                source="owner",
                actor_user_id=user["id"],
                expected_version=_company_version(payload),
            )
            return jsonify(_company_result(result, user["id"])), 201
        except Exception as exc:
            return _company_error(exc)

    @app.route(
        "/api/company-os/deliverables/<deliverable_id>/review",
        methods=["POST"],
    )
    def company_os_deliverable_review(deliverable_id):
        user, denied = _company_api_user()
        if denied:
            return denied
        intent_error = _company_intent_error()
        if intent_error:
            return intent_error
        try:
            payload = _company_json()
            decision = payload.get("decision")
            if decision == "revision_requested":
                decision = "rejected"
            if decision not in ("approved", "rejected"):
                raise ValueError("Choose approve or request changes.")
            note = _company_text(
                payload.get("note", ""), "Review note", 1000,
                multiline=True)
            if decision == "rejected" and not note:
                raise ValueError("Explain the requested change.")
            result = store.decide_manager_deliverable(
                user["id"], deliverable_id, decision,
                expected_version=_company_version(payload),
                note=note,
                actor_user_id=user["id"],
            )
            return jsonify(_company_result(result, user["id"]))
        except Exception as exc:
            return _company_error(exc)

    @app.route("/team/manager/tasks", methods=["POST"])
    def manager_task_create():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        if _signup_mode() != "open":
            abort(404)
        payload = request.get_json(silent=True) or request.form
        title = " ".join((payload.get("title") or "").split())
        assignee = (payload.get("assignee") or "").strip()
        valid_assignees = {member["key"] for member in _DIGITAL_TEAM}
        if len(title) < 3:
            return jsonify({
                "ok": False,
                "error": "Give your manager a clear objective.",
            }), 400
        if len(title) > 180:
            return jsonify({
                "ok": False,
                "error": "Keep the objective under 180 characters.",
            }), 400
        if assignee not in valid_assignees:
            return jsonify({
                "ok": False,
                "error": "Choose one of your ten operating specialists.",
            }), 400
        task = store.create_manager_task(user["id"], title, assignee)
        specialist = next(
            member for member in _DIGITAL_TEAM
            if member["key"] == assignee)
        task["assignee_name"] = specialist["name"]
        task["assignee_role"] = specialist["role"]
        return jsonify({"ok": True, "task": task}), 201

    @app.route("/team/manager/tasks/<task_id>/status", methods=["POST"])
    def manager_task_status(task_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        if _signup_mode() != "open":
            abort(404)
        payload = request.get_json(silent=True) or request.form
        status = (payload.get("status") or "").strip()
        if status not in ("queued", "in_progress", "delivered"):
            return jsonify({
                "ok": False,
                "error": "Choose assigned, in progress, or delivered.",
            }), 400
        if not store.update_manager_task_status(
                user["id"], task_id, status):
            return jsonify({
                "ok": False,
                "error": "That objective was not found.",
            }), 404
        return jsonify({"ok": True, "status": status})

    @app.route("/team/invite", methods=["POST"])
    def team_invite():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        if _signup_mode() == "closed":
            return jsonify({
                "ok": False,
                "error": "Invites are disabled while V2 registration is closed.",
            }), 403
        if (_signup_mode() != "open"
                and not _is_owner_email(user.get("email"))):
            return jsonify({"ok": False, "error": "Company OS is owner-only."}), 403
        if _signup_mode() != "open":
            intent_error = _company_intent_error()
            if intent_error:
                return intent_error
        email = (request.form.get("email") or "").strip().lower()
        role = request.form.get("role") or "manager"
        if "@" not in email or role not in _TEAM_ROLES:
            return jsonify({"ok": False, "error": "Enter a valid email and pick a role."}), 400
        if email == user["email"]:
            return jsonify({"ok": False, "error": "That's you — no invite needed."}), 400
        invite = store.add_team_invite(
            user["id"], email, role, seat_limit=_TEAM_SEAT_LIMIT)
        if invite and invite.get("error") == "full":
            return jsonify({
                "ok": False,
                "error": "All 10 team seats are filled. Remove a member before inviting someone else.",
            }), 409
        if invite is None:
            return jsonify({"ok": False, "error": "That email is already on your team."}), 400
        link = request.url_root.rstrip("/") + "/team/join/" + invite["invite_token"]
        emailed = False
        if emailer.configured():
            emailed = emailer.send(
                email, "%s invited you to their Street Banker team" % user["name"],
                '<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;">'
                "<h2>You're invited</h2>"
                "<p><strong>%s</strong> added you to their Street Banker team as their "
                "<strong>%s</strong>.</p>"
                '<p><a href="%s" style="display:inline-block;background:#E8B950;color:#14100A;'
                'font-weight:bold;padding:12px 24px;border-radius:10px;text-decoration:none;">'
                "Accept the invite</a></p></div>" % (user["name"], role, link))
        return jsonify({"ok": True, "link": link, "emailed": emailed})

    @app.route("/team/join/<token>", methods=["GET", "POST"])
    def team_join(token):
        if _signup_mode() == "closed":
            abort(404)
        invite = store.get_team_invite(token)
        if invite is None:
            return render_template("team_join.html", invalid=True, invite=None, error=None)
        error = None
        existing = store.get_user_by_email(invite["email"])
        signed_in = current_user()
        signed_in_as_invited = bool(
            existing and signed_in and existing["id"] == signed_in["id"])
        if request.method == "POST":
            if existing:
                if not signed_in_as_invited:
                    return render_template(
                        "team_join.html", invalid=False, invite=invite,
                        has_account=True, signed_in_as_invited=False,
                        error="Sign in to the invited account before accepting."), 403
                member_id = existing["id"]
            else:
                name = (request.form.get("name") or "").strip()
                password = request.form.get("password") or ""
                if not name or len(password) < 6:
                    error = "Enter your name and a password of 6+ characters."
                    return render_template("team_join.html", invalid=False,
                                           invite=invite, has_account=False,
                                           signed_in_as_invited=False, error=error)
                member_id = store.create_user(invite["email"], name,
                                              generate_password_hash(password))
            store.accept_team_invite(token, member_id)
            store.notify(invite["owner_id"], "team",
                         "Team invite accepted",
                         "%s joined your team as %s." % (invite["email"], invite["role"]),
                         "/team")
            session["user_id"] = member_id
            return redirect("/command-center")
        return render_template("team_join.html", invalid=False, invite=invite,
                               has_account=existing is not None,
                               signed_in_as_invited=signed_in_as_invited, error=None)

    @app.route("/team/<member_id>/remove", methods=["POST"])
    def team_remove(member_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        if (_signup_mode() != "open"
                and not _is_owner_email(user.get("email"))):
            return jsonify({"ok": False}), 403
        if _signup_mode() != "open":
            intent_error = _company_intent_error()
            if intent_error:
                return intent_error
        return jsonify({"ok": store.remove_team_member(user["id"], member_id)})

    @app.route("/onboarding")
    def onboarding():
        catalog = get_platform_catalog()
        # Nothing is pre-checked. The status column on _DEFAULT_PLATFORMS is
        # seed data, and reading it here meant seven of these eight boxes -
        # Spotify, Apple Music, ASCAP, BMI, SESAC, SoundExchange, The MLC -
        # rendered ticked on the first screen a brand-new artist ever sees,
        # under the heading "Connect your sources". It told them their PRO
        # and MLC accounts were already linked, and flatly contradicted
        # /connections, which says "Not connectable yet - and we won't fake
        # them". The tick state was never submitted or persisted anywhere,
        # so it claimed those integrations while doing nothing at all.
        sources = [{"name": p.platform, "logo": platform_logo_key(p.platform),
                    "connected": False} for p in catalog[:8]]
        eq = get_artist_eq_config()
        return render_template(
            "onboarding.html", sources=sources,
            program_links_json=json.dumps({
                "modules": eq["module_routes"], "actions": eq["action_routes"]}))

    _DISPUTE_TYPES = ["missing payment", "wrong split", "content claim",
                      "takedown", "metadata error", "chargeback", "other"]
    _DISPUTE_STATUSES = ["open", "submitted", "resolved", "rejected"]

    # ---------- Hours desk ------------------------------------------------
    # Four things that all come down to time: what you worked, what you
    # charge, what other people worked for you, and how the day is laid out.
    # Every figure on the page is summed from stored rows.

    _HOURS_STARTER = [
        ("Mixing", 75.0, 0.0, True),
        ("Studio time", 40.0, 2.0, True),
        ("Vocal feature", 250.0, 2.0, True),
        ("Beat session", 60.0, 0.0, False),
    ]

    def _hours_ctx(user_id, day=None):
        entries = store.list_hours_entries(user_id)
        invoices = store.list_hours_invoices(user_id)
        bookings = store.list_hours_bookings(user_id)
        subs = store.list_hours_submissions(user_id)
        rates = store.list_hours_rates(user_id)
        today = hours_engine.parse_day(day)
        day_str = today.strftime("%Y-%m-%d")
        blocks = store.list_hours_blocks(user_id, day_str)
        for e in entries:
            e["value"] = hours_engine.entry_value(e)
            e["flags"] = hours_engine.flag_entry(e)
        return {
            "entries": entries,
            "invoices": invoices,
            "bookings": bookings,
            "submissions": subs,
            "rates": rates,
            "bookable": hours_engine.bookable_services(rates),
            "totals": hours_engine.session_totals(entries),
            "groups": hours_engine.group_by_client(entries),
            "invoice_totals": hours_engine.invoice_totals(invoices),
            "booking_totals": hours_engine.booking_totals(bookings),
            "sub_totals": hours_engine.submission_totals(subs),
            "summary": hours_engine.desk_summary(entries, invoices, bookings, subs),
            "plan": hours_engine.day_plan(blocks, bookings, day=day_str),
            "next_number": hours_engine.next_invoice_number(invoices),
            "plan_day": day_str,
            "week": hours_engine.week_days(),
            "today": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        }

    @app.route("/hours")
    def hours_desk():
        user = current_user()
        if user is None:
            return login_required_redirect()
        return render_template("hours.html", active_page="hours",
                               starter=_HOURS_STARTER,
                               **_hours_ctx(user["id"], request.args.get("day")),
                               **build_dashboard_context())

    @app.route("/hours/log", methods=["POST"])
    def hours_log():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        f = request.form
        hours = _hours_float(f.get("hours"))
        if hours <= 0:
            return jsonify({"ok": False,
                            "error": "Enter how many hours you worked."}), 400
        store.add_hours_entry(user["id"], f.get("day"), f.get("project"),
                              f.get("client"), f.get("service"), hours,
                              _hours_float(f.get("rate")), f.get("note"))
        return redirect(url_for("hours_desk"))

    @app.route("/hours/entry/<entry_id>/delete", methods=["POST"])
    def hours_entry_delete(entry_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        # Billed lines stay: removing one would leave its invoice claiming
        # hours that no longer exist anywhere.
        if not store.delete_hours_entry(user["id"], entry_id):
            return jsonify({"ok": False,
                            "error": "Already invoiced — that line stays."}), 400
        return redirect(url_for("hours_desk"))

    @app.route("/hours/invoice", methods=["POST"])
    def hours_invoice():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        ids = request.form.getlist("entry_id")
        inv = store.create_hours_invoice(
            user["id"], ids,
            request.form.get("number") or hours_engine.next_invoice_number(
                store.list_hours_invoices(user["id"])),
            request.form.get("client"), request.form.get("project"))
        if inv is None:
            return jsonify({"ok": False,
                            "error": "Nothing unbilled in that selection."}), 400
        # Leave a trail in the inbox: an invoice that went out with no record
        # of going out is how you end up chasing the wrong client.
        store.add_inbox("invoice", {
            "number": inv["number"], "client": inv["client"],
            "project": inv["project"], "hours": inv["hours"],
            "total": inv["total"]}, user_id=user["id"])
        return redirect(url_for("hours_desk"))

    @app.route("/hours/invoice/<invoice_id>/paid", methods=["POST"])
    def hours_invoice_paid(invoice_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        store.set_hours_invoice_paid(user["id"], invoice_id)
        return redirect(url_for("hours_desk"))

    @app.route("/hours/rate", methods=["POST"])
    def hours_rate():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        f = request.form
        if f.get("starter"):
            # One click to a usable rate card; every line still editable.
            for i, (svc, rate, mins, book) in enumerate(_HOURS_STARTER):
                store.set_hours_rate(user["id"], svc, rate, mins, book, "", i)
            return redirect(url_for("hours_desk"))
        if not (f.get("service") or "").strip():
            return jsonify({"ok": False, "error": "Name the service."}), 400
        store.set_hours_rate(user["id"], f.get("service"),
                             _hours_float(f.get("rate")),
                             _hours_float(f.get("min_hours")),
                             bool(f.get("bookable")), f.get("notes"),
                             len(store.list_hours_rates(user["id"])))
        return redirect(url_for("hours_desk"))

    @app.route("/hours/rate/<rate_id>/delete", methods=["POST"])
    def hours_rate_delete(rate_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        store.delete_hours_rate(user["id"], rate_id)
        return redirect(url_for("hours_desk"))

    @app.route("/hours/booking", methods=["POST"])
    def hours_booking():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        f = request.form
        svc = (f.get("service") or "").strip()
        # The rate comes from your own card, not from the form: a booking
        # form that lets the booker name the price is not a rate card.
        rate, mins = 0.0, 0.0
        for r in store.list_hours_rates(user["id"]):
            if r["service"] == svc and r["bookable"]:
                rate, mins = r["rate"], r["min_hours"]
                break
        else:
            return jsonify({"ok": False,
                            "error": "That service is not bookable."}), 400
        hours = _hours_float(f.get("hours"), 1.0)
        if mins and hours < mins:
            return jsonify({"ok": False, "error":
                            "%s has a %g hour minimum." % (svc, mins)}), 400
        store.add_hours_booking(user["id"], svc, f.get("who"), f.get("contact"),
                                f.get("day"), _hours_float(f.get("start_hour")),
                                hours, rate, f.get("note"))
        return redirect(url_for("hours_desk"))

    @app.route("/hours/booking/<booking_id>/<status>", methods=["POST"])
    def hours_booking_status(booking_id, status):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        if not store.set_hours_booking_status(user["id"], booking_id, status):
            return jsonify({"ok": False, "error": "Unknown status."}), 400
        return redirect(url_for("hours_desk"))

    @app.route("/hours/submission", methods=["POST"])
    def hours_submission():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        f = request.form
        if _hours_float(f.get("hours")) <= 0:
            return jsonify({"ok": False, "error": "Enter the hours."}), 400
        store.add_hours_submission(user["id"], f.get("who"), f.get("role"),
                                   f.get("day"), _hours_float(f.get("hours")),
                                   _hours_float(f.get("rate")), f.get("note"))
        return redirect(url_for("hours_desk"))

    @app.route("/hours/submission/<sub_id>/<decision>", methods=["POST"])
    def hours_submission_decide(sub_id, decision):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        if decision not in ("approve", "reject"):
            return jsonify({"ok": False, "error": "Unknown decision."}), 400
        store.decide_hours_submission(user["id"], sub_id, decision == "approve",
                                      request.form.get("reason"))
        return redirect(url_for("hours_desk"))

    @app.route("/hours/block", methods=["POST"])
    def hours_block():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        f = request.form
        if not (f.get("label") or "").strip():
            return jsonify({"ok": False, "error": "Name the block."}), 400
        day = f.get("day")
        store.add_hours_block(user["id"], day, _hours_float(f.get("start_hour"), 9),
                              _hours_float(f.get("hours"), 1), f.get("label"),
                              f.get("kind") or "work")
        return redirect(url_for("hours_desk", day=day))

    @app.route("/hours/block/<block_id>/<action>", methods=["POST"])
    def hours_block_action(block_id, action):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        if action == "done":
            store.toggle_hours_block(user["id"], block_id)
        elif action == "delete":
            store.delete_hours_block(user["id"], block_id)
        else:
            return jsonify({"ok": False, "error": "Unknown action."}), 400
        return redirect(url_for("hours_desk", day=request.form.get("day")))

    @app.route("/disputes")
    def disputes():
        user = current_user()
        if user is None:
            return login_required_redirect()
        items = store.list_disputes(user["id"])
        return render_template("disputes.html", active_page="disputes",
                               disputes=items, types=_DISPUTE_TYPES,
                               statuses=_DISPUTE_STATUSES,
                               open_count=sum(1 for d in items
                                              if d["status"] in ("open", "submitted")),
                               disputed_total=round(sum(
                                   d["amount"] for d in items
                                   if d["status"] in ("open", "submitted")), 2),
                               recovered_total=round(sum(
                                   d["amount"] for d in items
                                   if d["status"] == "resolved"), 2),
                               **build_dashboard_context())

    @app.route("/disputes/new", methods=["POST"])
    def dispute_new():
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        platform = (request.form.get("platform") or "").strip()
        dtype = request.form.get("dispute_type") or ""
        if not platform or dtype not in _DISPUTE_TYPES:
            return jsonify({"ok": False, "error": "Name the platform and pick a type."}), 400
        try:
            amount = max(0.0, float(request.form.get("amount") or 0))
        except ValueError:
            amount = 0.0
        store.add_dispute(user["id"], platform, dtype,
                          (request.form.get("description") or "").strip(), amount)
        return jsonify({"ok": True})

    @app.route("/disputes/<dispute_id>/status", methods=["POST"])
    def dispute_status(dispute_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False}), 401
        status = (request.get_json(silent=True) or {}).get("status") or ""
        if status not in _DISPUTE_STATUSES:
            return jsonify({"ok": False, "error": "Unknown status."}), 400
        ok = store.set_dispute_status(user["id"], dispute_id, status)
        if ok and status == "resolved":
            store.notify(user["id"], "money", "Dispute resolved",
                         "Marked resolved — log the payout in Revenue OS if money moved.",
                         "/disputes")
        return jsonify({"ok": ok})

    def _backup_allowed(user):
        """A full database export is an operator action, never a paid-tier perk."""
        return bool(user and _is_owner_email(user.get("email")))

    @app.route("/settings")
    def settings():
        return render_template("settings.html", active_page="settings",
                               can_backup=_backup_allowed(current_user()),
                               backup_state=_backup_state(),
                               **build_dashboard_context())

    def _snapshot_zip():
        """The archive itself: a consistent database copy plus uploads.

        Uses SQLite's backup API rather than copying the file, because a
        raw copy taken mid-write restores as a corrupt database - and a
        backup you cannot restore is worse than none, since you stop
        worrying about it.
        """
        import sqlite3 as _sq
        import tempfile
        import zipfile
        snap = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        snap.close()
        src = _sq.connect(store.db_path())
        dst = _sq.connect(snap.name)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        buf = tempfile.TemporaryFile()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snap.name, "streetbanker.db")
            for root, _dirs, files in os.walk(UPLOADS_DIR):
                for fname in files:
                    full = os.path.join(root, fname)
                    z.write(full, "uploads/" + os.path.relpath(full, UPLOADS_DIR))
        os.unlink(snap.name)
        buf.seek(0)
        return buf

    def _backup_state():
        """What the last off-box run did, for the settings page. Reads the
        stored record rather than claiming anything about right now."""
        import json as _json
        raw = store.get_kv("backup_last_run")
        last = {}
        if raw:
            try:
                last = _json.loads(raw)
            except ValueError:
                last = {}
        return {
            "offsite_configured": backup_store.configured(),
            "target": backup_store.target(),
            "scheduler_ready": bool(os.environ.get("BACKUP_TOKEN")),
            "last": last,
        }

    @app.route("/backup")
    def backup_download():
        from flask import send_file
        user = current_user()
        if not _backup_allowed(user):
            abort(404)
        buf = _snapshot_zip()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return send_file(buf, mimetype="application/zip", as_attachment=True,
                         download_name="streetbanker-backup-%s.zip" % stamp)

    @app.route("/backup/run", methods=["POST"])
    def backup_run():
        """Take a snapshot and push it off-box.

        Meant for a scheduler (Render Cron, GitHub Actions, cron-job.org)
        presenting BACKUP_TOKEN. An account that may already download the
        backup by hand can also trigger it, so it is testable without
        waiting for a schedule.

        Every outcome is recorded - including the failures. A backup system
        that only logs its successes is how people find out at restore time
        that it stopped working in March.
        """
        import json as _json
        token = os.environ.get("BACKUP_TOKEN") or ""
        presented = (request.headers.get("X-Backup-Token")
                     or request.form.get("token") or "")
        by_token = bool(token) and hmac.compare_digest(presented, token)
        if not (by_token or _backup_allowed(current_user())):
            abort(404)
        if not backup_store.configured():
            return jsonify({
                "ok": False,
                "error": "No off-box target configured. Set BACKUP_S3_ENDPOINT, "
                         "BACKUP_S3_BUCKET, BACKUP_S3_KEY and BACKUP_S3_SECRET.",
            }), 503
        started = datetime.now(timezone.utc)
        buf = _snapshot_zip()
        data = buf.read()
        buf.close()
        name = backup_store.object_name(started)
        ok, detail = backup_store.put(name, data)
        record = {
            "at": started.isoformat(),
            "ok": bool(ok),
            "bytes": len(data),
            "object": name,
            "detail": detail,
            "seconds": round((datetime.now(timezone.utc) - started)
                             .total_seconds(), 1),
        }
        store.set_kv("backup_last_run", _json.dumps(record))
        if not ok:
            # Route the alert to a real account. notify() keys rows by user,
            # so a None here would file it where nobody can read it — a
            # failure alarm nobody hears.
            owner_email = (os.environ.get("OWNER_EMAIL") or "").strip()
            owner = store.get_user_by_email(owner_email) if owner_email else None
            if owner:
                store.notify(owner["id"], "system", "Off-box backup failed",
                             detail[:200], "/settings")
        return jsonify({"ok": bool(ok), "run": record}), (200 if ok else 502)

    _SWEEP_ROLES = [("artist", "Artist"), ("songwriter", "Songwriter"),
                    ("producer", "Producer"), ("manager", "Manager"),
                    ("label", "Label")]

    @app.route("/plan")
    def artist_plan():
        """The Artist EQ's plan, recomputed server-side from the link.

        The console builds this URL from the six channel values, and this
        route runs the same functions in artist_eq_config that the browser
        mirrors - so the plan the visitor clicked is the plan they land
        on. Public: the whole point is that the recommendation is readable
        before anybody makes an account.
        """
        from artist_eq_config import CHANNELS, CHANNEL_KEYS, build_plan

        values = {}
        for key in CHANNEL_KEYS:
            raw = request.args.get(key)
            if raw is not None:
                values[key] = raw
        preset = (request.args.get("preset") or "").strip()[:40]
        plan = build_plan(values, preset)
        return render_template("plan.html", plan=plan, channels=CHANNELS)

    @app.route("/start")
    def guided_start():
        """BUILD MY STREET BANKER - the guided start, in public.

        The closing CTA carries the Artist EQ mix down the page as query
        parameters, so this opens on the plan those settings produce
        rather than on a default. Same build_plan the console and /plan
        already use, so the two surfaces cannot disagree. A visitor can
        change the mix here with the preset buttons; an account is asked
        for only when there is something to save.
        """
        from artist_eq_config import CHANNEL_KEYS, PRESETS, build_plan

        values, carried = {}, False
        for key in CHANNEL_KEYS:
            raw = request.args.get(key)
            if raw is not None:
                values[key] = raw
                carried = True
        preset = (request.args.get("preset") or "").strip()[:40]
        plan = build_plan(values, preset)
        return render_template("start_public.html", plan=plan,
                               presets=PRESETS, carried=carried)

    # About, Contact and Partner Network. The footer named all three and
    # had none of them: About went to /services, Contact went to /submit,
    # and Partner Network went to /network, which is behind the login wall.
    @app.route("/release-signal")
    def release_signal_page():
        """Release Signal, in public.

        No analysis provider is connected on this deployment, so the page
        explains what the read contains and does not accept an upload.
        Taking a file and returning an invented genre would be a fake
        scan, which is the one thing this feature must never do.
        """
        from release_signal import get_release_signal_config

        return render_template("release_signal.html",
                               rs=get_release_signal_config())

    @app.route("/remix-lab")
    def remix_lab():
        """Remix Lab - remix briefs from audio the artist owns, in preview.

        Public: the rights gate, the likeness screen and the worked
        example are exactly what a visitor needs to judge the tool.
        Generation is not connected and the page says so; nothing on it
        uploads or stores anything. When a backend lands, every
        reference string must pass remix_lab_config.check_reference_text
        server-side before a generation request is made - the browser
        copy of that screen is convenience, not enforcement.
        """
        from remix_lab_config import (get_remix_lab_config,
                                      get_remix_lab_client_config)

        return render_template(
            "remix_lab.html", remix=get_remix_lab_config(),
            remix_json=json.dumps(get_remix_lab_client_config()))

    @app.route("/remix-lab/brief", methods=["POST"])
    def remix_lab_brief():
        """Run a real remix brief on a track the artist owns.

        The page shipped saying generation was not connected. It now can be,
        because a MusicProvider exposes composition_plan() - tempo, section
        boundaries and an energy curve, measured rather than guessed.

        This is also the server-side likeness screen that remix_lab_config
        asked for in as many words: "the authoritative copy the server must
        call before any generation request leaves the building". It runs on
        every reference line before anything is uploaded or spent.
        """
        import audio_retention
        import audio_store as astore
        import audio_studio
        import audio_works as works
        import remix_lab_config as rlc
        import remix_lab_engine as rle

        user = current_user()
        if user is None:
            return redirect(url_for("login", next="/remix-lab"))
        if not rlc.engine_live():
            abort(404)

        def refuse(message, offending=None):
            return render_template("remix_lab_refused.html", message=message,
                                   offending=offending,
                                   warning=rlc.SAFETY_WARNING,
                                   examples=rlc.ALLOWED_EXAMPLES), 400

        # 1. The screen, first, on every reference line. Before the upload is
        #    read, before an asset exists, before anything is spent.
        references = [r.strip() for r in request.form.getlist("reference") if r.strip()]
        for line in references:
            offending = works.screen_reference(line)
            if offending:
                return refuse("That reference asks for an imitation of a real "
                              "person, so the brief was not run.", offending)

        # 2. Both rights confirmations, which the page has always required.
        if request.form.get("rights_own") != "1" or                 request.form.get("rights_likeness") != "1":
            return refuse("Both rights confirmations are needed before a track "
                          "is uploaded.")

        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return refuse("Choose the track you want a brief for.")
        ext = os.path.splitext(upload.filename)[1].lower()
        if ext not in set(rlc.UPLOAD_FORMATS):
            return refuse("Remix Lab reads %s."
                          % ", ".join(f.upper().lstrip(".") for f in rlc.UPLOAD_FORMATS))
        data = upload.read()
        if not data:
            return refuse("That file is empty.")
        if len(data) > rlc.UPLOAD_MAX_MB * 1024 * 1024:
            return refuse("That track is larger than the %d MB limit."
                          % rlc.UPLOAD_MAX_MB)

        # 3. Stored privately - never the public uploads tree. A master an
        #    artist uploaded is the most valuable file they own.
        path = audio_studio._save(
            "remix_%d%s" % (int(time.time() * 1000), ext), data,
            upload.mimetype or "audio/mpeg")
        asset_id = astore.create_asset(
            None, user["id"], path, file_name=upload.filename[:200],
            mime_type=upload.mimetype or "audio/mpeg", file_size=len(data),
            rights_status="confirmed",
            retention_days=audio_retention.retention_days(None, "source"))

        choices = {
            "lane": request.form.get("remixLane") or "",
            "targetUse": request.form.get("targetUse") or "",
            "energy": request.form.get("energy") or "",
            "tempoDirection": request.form.get("tempoDirection") or "",
            "vocalTreatment": request.form.get("vocalTreatment") or "",
            "instrumentation": request.form.get("instrumentation") or "",
            "riskLevel": request.form.get("riskLevel") or "",
        }

        item = works.create_work(
            user["id"], "remix_plan",
            title=upload.filename[:120],
            brief=" ".join(references)[:2000],
            options=choices, source_asset_id=asset_id)
        works.confirm_rights(item["id"], user.get("name") or user.get("email") or "")

        plan, error = {}, None
        try:
            _item, result = works.submit_work(item["id"])
            plan = result or {}
        except works.WorkRefusal as refusal:
            # The item carries the reason; the page shows it rather than a
            # stack trace, and the brief still composes from the choices with
            # every line marked as not measured.
            error = refusal.reason

        brief = rle.compose_brief(plan, choices, track_name=upload.filename)
        return render_template(
            "remix_lab_brief.html", rl=rlc.get_remix_lab_config(),
            brief=brief, plan=plan, choices=choices, error=error,
            grounded=rle.brief_is_grounded(brief),
            is_mock=bool(plan.get("is_mock")),
            track_name=upload.filename, work_id=item["id"])

    @app.route("/release-check")
    def release_check():
        """DISTRIBUTE NOW - the public release-readiness check.

        The distribution section had both of its buttons pointing at
        /distribution, so "Distribute now" and "View distribution guide"
        were the same click. This is the first one: tick what you have,
        see what the release still needs. Counted server-side so the page
        works with JavaScript off and the URL stays shareable.

        A completion count, never a judgement about the record.
        """
        from distro_config import CHECKLIST

        have = set(request.args.getlist("have"))
        total = sum(len(entries) for _, entries in CHECKLIST)
        # Only count ticks that correspond to a real requirement, so a
        # hand-edited query string cannot inflate the readout.
        valid = set()
        for group, entries in CHECKLIST:
            for entry in entries:
                slug = ("%s-%s" % (group, entry)).lower().replace(" ", "-").replace(",", "")
                valid.add(slug)
        have &= valid
        done = len(have)

        if done == total:
            state = "Delivery ready"
        elif done >= -(-total * 3 // 4):
            state = "Ready for review"
        elif done >= -(-total * 35 // 100):
            state = "Needs information"
        else:
            state = "Setup incomplete"

        return render_template("release_check.html", checklist=CHECKLIST,
                               have=have, done=done, total=total, state=state,
                               pct=round(100 * done / total) if total else 0)

    @app.route("/about")
    def about_page():
        from public_pages_config import get_about

        return render_template(
            "public_page.html", pg=get_about(), page_title="About",
            page_description=("What Street Banker is, why it exists, how it "
                              "makes money, and what it is not."))

    @app.route("/contact")
    def contact_page():
        from public_pages_config import get_contact

        return render_template(
            "public_page.html", pg=get_contact(), page_title="Contact",
            page_description=("How to reach Street Banker, and where each "
                              "kind of question actually goes."))

    @app.route("/partners")
    def partners_page():
        from public_pages_config import get_partners

        return render_template(
            "public_page.html", pg=get_partners(), page_title="Partner network",
            page_description=("Who delivers what: the distribution "
                              "partnership that exists today, and the "
                              "integrations we are looking for."))

    @app.route("/artist-control")
    def artist_control_policy():
        """The artist-control policy the trust band links to.

        Public by design: a promise a visitor has to make an account to
        read is not a promise. Ten statements, each one a commitment made
        somewhere else on the homepage.
        """
        from closing_config import POLICY

        return render_template("artist_control.html", policy=POLICY)

    # The public product tour. Named /product-tour rather than /tour
    # because /tour is the signed-in touring pipeline (/tour/<id>,
    # /tour/add, /tour/<id>/status) and has been for a long time.
    @app.route("/product-tour")
    def product_tour():
        """Twelve steps through one example release, no account anywhere."""
        from tour_config import get_tour_config

        return render_template("product_tour.html", tour=get_tour_config())

    @app.route("/product-tour/smart-link")
    def product_tour_smart_link():
        """The Smart Links, Fan Intelligence and artwork-generator proof.

        Everything here is a labelled example: the destination rows are
        not connected to a platform, the fan readings are invented for
        illustration, and the page collects nothing from the visitor.
        """
        from tour_config import (SMART_LINK, FAN_PANEL, CREATIVE_STEPS,
                                 CREATIVE_OUTPUTS, BRAND_MEMORY)

        return render_template("product_tour_smart_link.html",
                               sl=SMART_LINK, fi=FAN_PANEL,
                               creative_steps=CREATIVE_STEPS,
                               creative_outputs=CREATIVE_OUTPUTS,
                               brand=BRAND_MEMORY)

    @app.route("/artist-twin/start")
    def artist_twin_start():
        """The public Artist Twin entry.

        A visitor picks what they are working on and gets the route the
        Twin would take, plus what it would need to read. No account, no
        upload, and no claim that anything of theirs has been looked at -
        an account is offered at the end, when there is something to save.
        """
        from artist_twin_config import GOALS

        wanted = (request.args.get("goal") or "").strip()[:40]
        selected = next((g for g in GOALS if g["id"] == wanted), None)
        return render_template("artist_twin_start.html", goals=GOALS,
                               selected=selected)

    @app.route("/metadata")
    def passport_public():
        """The Metadata Passport, explained before an account is asked for.

        The seven records, what a conflict looks like, how one entry moves
        the others, and what happens to the information. Everything shown
        is the labelled example; nothing is anybody's release.
        """
        from passport_config import (CATEGORIES, CONNECTED, ISSUES, USE,
                                     STANDARDS)

        return render_template("passport_public.html", categories=CATEGORIES,
                               connected=CONNECTED, issues=ISSUES, use=USE,
                               standards=STANDARDS)

    @app.route("/distribution")
    def distribution_guide():
        """The distribution guide, in public.

        Who delivers, what a release package needs, what each stage does,
        and which parts are the partner's rather than Street Banker's.
        No account, and no claim that a release has been delivered.
        """
        from distro_config import (GUIDE, WORKFLOW, CHECKLIST, INTEGRATIONS,
                                   PARTNER)

        return render_template("distribution_public.html", guide=GUIDE,
                               workflow=WORKFLOW, checklist=CHECKLIST,
                               integrations=INTEGRATIONS, partner=PARTNER)

    @app.route("/royalty-sweep")
    def sweep_method():
        """How Royalty Sweep works, in public.

        What is read, what counts as an opportunity, how an estimate is
        arrived at, how a case is verified, which steps need a person and
        what happens to the data. No figures and no promises.
        """
        from sweep_config import METHOD, SOURCES

        return render_template("sweep_method.html", method=METHOD,
                               sources=SOURCES)

    @app.route("/rollout")
    def rollout_public():
        """Rollout Engine, explained before an account is asked for.

        The example campaign is printed in full and labelled as one, and
        the middle group says plainly that nothing posts itself.
        """
        from rollout_config import (TOUR_SECTIONS, WORKFLOW, SAMPLE, STATUSES,
                                    PLAN_LENGTHS)

        return render_template("rollout_public.html", sections=TOUR_SECTIONS,
                               workflow=WORKFLOW, sample=SAMPLE,
                               statuses=STATUSES, plan_lengths=PLAN_LENGTHS)

    @app.route("/creative-studio")
    def creative_studio_public():
        """Creative Studio, explained before an account is asked for.

        Grouped by what is true rather than by feature: what is in the
        app today, what is guided rather than automatic, and what is not
        built. A visitor should be able to decide against it from here.
        """
        from creative_config import CAPABILITIES, WORKFLOW, MEMORY_TITLE, MEMORY_COPY

        return render_template("creative_studio_public.html",
                               capabilities=CAPABILITIES, workflow=WORKFLOW,
                               memory_title=MEMORY_TITLE, memory_copy=MEMORY_COPY)

    @app.route("/press")
    def press_public():
        """The Press Desk, explained before an account is asked for.

        Sits at /press rather than /press-desk because /press-desk is the
        artist's own workspace and stays behind the wall. The two live in
        one namespace on purpose: /press says what the desk is, and
        /press/<token> is one announcement sent to one recipient.

        The sending status on this page is resolved from capability_status
        at request time, so it cannot promise a delivery route the running
        deployment has not been given credentials for.
        """
        from press_config import get_press_config

        return render_template("press_public.html", press=get_press_config())

    @app.route("/lanes")
    def lanes_public():
        """Find my lane, in public.

        One situation in, one lane out, with the reason printed next to
        it and all three lanes set out underneath - so the suggestion can
        be disagreed with rather than just accepted. No account.
        """
        from lanes_config import LANES, SITUATIONS

        wanted = (request.args.get("situation") or "").strip()[:40]
        picked = next((s for s in SITUATIONS if s["id"] == wanted), None)
        suggested = next((l for l in LANES if picked and l["slug"] == picked["lane"]),
                         None)
        return render_template("lanes_public.html", lanes=LANES,
                               situations=SITUATIONS, picked=picked,
                               suggested=suggested)

    @app.route("/ai")
    def ai_trust():
        """How Street Banker uses AI, in five statements, signed out."""
        from artist_twin_config import TRUST_POINTS

        return render_template("ai_trust.html", points=TRUST_POINTS)

    @app.route("/catalog-sweep", methods=["GET", "POST"])
    def catalog_sweep():
        """The free-sweep entry, open to a visitor with no account.

        The CTA used to point at /recovery, which is behind the login
        wall - so the first thing a stranger got for asking what a sweep
        is was a password field. This asks three questions and then says
        plainly what a sweep checks and what it cannot know yet. It does
        not claim a scan has run, because none has: the engine reads
        uploaded statements, and there are none until somebody uploads
        one.
        """
        form = {}
        error = None
        result = None
        if request.method == "POST":
            form = {
                "catalog": (request.form.get("catalog") or "").strip()[:120],
                "url": (request.form.get("url") or "").strip()[:400],
                "role": request.form.get("role") or "artist",
            }
            roles = dict(_SWEEP_ROLES)
            if not form["catalog"]:
                error = "Tell us which artist or catalog to look at."
            else:
                if form["role"] not in roles:
                    form["role"] = "artist"
                # A lead worth keeping, filed where demo-access requests
                # already go: platform-level, owner-visible, never on an
                # artist's own inbox page.
                try:
                    store.add_inbox("catalog_sweep", {
                        "catalog": form["catalog"], "url": form["url"],
                        "role": form["role"]})
                except Exception:
                    pass  # a lead record must never cost the visitor the page
                result = {
                    "catalog": form["catalog"],
                    "role_label": roles[form["role"]],
                    "checks": [
                        {"title": "Unattributed revenue",
                         "detail": "Rows on your statements that were paid "
                                   "with no track title on them. Actual "
                                   "money, missing its attribution."},
                        {"title": "Coverage gaps",
                         "detail": "Tracks earning on some sources and "
                                   "silent on others, priced at that "
                                   "track's own per-source average."},
                        {"title": "Royalty lanes per song",
                         "detail": "Nine income lanes, marked claimed or "
                                   "missing from what your statements show."},
                        {"title": "Catalog valuation",
                         "detail": "A 3-5x range on the run rate your own "
                                   "statement months produce."},
                    ],
                    "limits": [
                        "It does not read a platform, a PRO or The MLC "
                        "directly - no public feed exists for that.",
                        "It cannot see revenue from a source you have never "
                        "uploaded, and it will not guess at one.",
                        "Estimates are labelled as estimates everywhere they "
                        "appear, and separated from money already paid.",
                    ],
                }
        return render_template("catalog_sweep.html", form=form, error=error,
                               result=result, roles=_SWEEP_ROLES)

    @app.route("/scan/missing-royalties", methods=["POST"])
    def scan_missing_royalties():
        # Same split as /recovery: a real account is scanned against its
        # own statements, and gets an empty result when it has uploaded
        # none rather than the showcase's seventeen findings.
        user = current_user()
        if user is not None and not _session_is_demo():
            view = recovery_engine.build(user["id"])
            return jsonify({
                "ok": True,
                "count": view["finding_count"],
                "total_estimated": view["total_at_stake"],
                "findings": [{"id": f["id"], "source": f["source"],
                              "issue_type": f["issue_type"],
                              "estimated_value": f["amount"],
                              "confidence": f["confidence"],
                              "recommended_action": f["action"]}
                             for f in view["findings"]],
            })
        findings = get_missing_royalty_findings(get_platform_catalog())
        return jsonify({
            "ok": True,
            "count": len(findings),
            "total_estimated": round(sum(f.estimated_value for f in findings), 2),
            "findings": [asdict(f) for f in findings],
        })

    @app.route("/connections/<platform_id>/connect", methods=["POST"])
    def connect_platform(platform_id):
        entry = set_connection_status(platform_id, "connected")
        if entry is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "status": entry.status})

    @app.route("/connections/<platform_id>/disconnect", methods=["POST"])
    def disconnect_platform(platform_id):
        entry = set_connection_status(platform_id, "not_connected")
        if entry is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "status": entry.status})

    @app.route("/songs/<song_id>")
    def song_detail(song_id):
        detail = build_song_detail(song_id)
        if detail is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "song": detail})

    @app.route("/songs/<song_id>/splits", methods=["POST"])
    def add_split_route(song_id):
        data = request.get_json(silent=True) or {}
        collaborator = (data.get("collaborator") or "").strip()
        role = (data.get("role") or "").strip()
        try:
            percentage = float(data.get("percentage"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid percentage"}), 400
        if not collaborator or not role or percentage <= 0:
            return jsonify({"ok": False, "error": "Missing required fields"}), 400
        splits = add_split(song_id, collaborator, role, percentage)
        if splits is None:
            return jsonify({"ok": False}), 404
        song = live_song(get_song(song_id))
        return jsonify({
            "ok": True,
            "splits": [asdict(s) for s in splits],
            "split_total": split_total_percentage(song),
        })

    @app.route("/songs/<song_id>/splits/<int:index>/remove", methods=["POST"])
    def remove_split_route(song_id, index):
        splits = remove_split(song_id, index)
        if splits is None:
            return jsonify({"ok": False}), 404
        song = live_song(get_song(song_id))
        return jsonify({
            "ok": True,
            "splits": [asdict(s) for s in splits],
            "split_total": split_total_percentage(song),
        })

    @app.route("/songs/<song_id>/splits/<int:index>/toggle", methods=["POST"])
    def toggle_split_route(song_id, index):
        splits = toggle_split_confirmed(song_id, index)
        if splits is None:
            return jsonify({"ok": False}), 404
        song = live_song(get_song(song_id))
        return jsonify({
            "ok": True,
            "splits": [asdict(s) for s in splits],
            "split_total": split_total_percentage(song),
            "splits_confirmed": splits_fully_confirmed(song),
        })

    @app.route("/claims/<claim_id>/advance", methods=["POST"])
    def advance_claim_route(claim_id):
        new_status = advance_claim(claim_id, get_platform_catalog())
        if new_status is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "status": new_status})

    @app.route("/claims/<claim_id>/reject", methods=["POST"])
    def reject_claim_route(claim_id):
        new_status = reject_claim(claim_id, get_platform_catalog())
        if new_status is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "status": new_status})

    @app.route("/fixes/<item_id>/status", methods=["POST"])
    def update_fix_status(item_id):
        data = request.get_json(silent=True) or {}
        status = data.get("status")
        result = set_fix_status(item_id, status)
        if result is None:
            return jsonify({"ok": False}), 400
        return jsonify({"ok": True, "status": result})

    @app.route("/songs/<song_id>/registration-wizard")
    def registration_wizard(song_id):
        song = get_song(song_id)
        if song is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "wizard": get_registration_wizard(song)})

    @app.route("/songs/<song_id>/registration-wizard/<target>/complete", methods=["POST"])
    def complete_registration_wizard_step(song_id, target):
        wizard = complete_registration_step(song_id, target)
        if wizard is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "wizard": wizard})

    @app.route("/reports/<report_id>/generate", methods=["POST"])
    def generate_report_route(report_id):
        user = current_user()
        if user is None:
            return jsonify({"ok": False, "error": "Sign in first."}), 401
        # Build it for real before claiming it exists. When there is no
        # data the honest answer is the reason, not a header-row file -
        # an empty "Missing Money Report" reads as "nothing is missing".
        report = generate_report(report_id)
        if report is None:
            return jsonify({"ok": False, "error": "Unknown report."}), 404
        filename, body, reason = report_builder.build(report_id, user["id"])
        if filename is None:
            return jsonify({"ok": False, "error": reason}), 200
        report = {**report, "filename": filename, "rows": body.count("\n") - 1,
                  "download": "/reports/%s/download" % report_id}
        return jsonify({"ok": True, "report": report})

    @app.route("/reports/<report_id>/download")
    def download_report_route(report_id):
        user = current_user()
        if user is None:
            return login_required_redirect()
        # Rebuilt from live statement data rather than served from a
        # cache, so the file can never disagree with the page.
        filename, body, reason = report_builder.build(report_id, user["id"])
        if filename is None:
            abort(404, reason)
        return Response(
            body, mimetype="text/csv",
            headers={"Content-Disposition":
                     'attachment; filename="%s"' % filename})

    @app.route("/alerts/<alert_id>/resolve", methods=["POST"])
    def resolve_alert(alert_id):
        balances = get_platform_balances()
        payouts = get_recent_payouts()
        kpis = get_kpis()
        catalog = get_platform_catalog()
        alerts = get_royalty_leak_alerts(balances, payouts, kpis, catalog)
        alert = next((a for a in alerts if a.id == alert_id), None)
        if alert is None:
            return jsonify({"ok": False}), 404
        return jsonify({"ok": True, "message": alert.resolution_message})

    @app.after_request
    def _mark_sandbox(response):
        """Stamp every HTML page on a sandbox deployment.

        Registered unconditionally but inert unless SANDBOX is set, so
        production returns the identical bytes it returned before this
        existed. Skips streamed files and anything that is not HTML.
        """
        if not sandbox.active() or response.direct_passthrough:
            return response
        if (response.mimetype or "") != "text/html":
            return response
        try:
            html = response.get_data(as_text=True)
        except (UnicodeDecodeError, RuntimeError):
            return response
        marked = sandbox.mark(html)
        if marked != html:
            response.set_data(marked)
        return response

    operator_desk.init(app, is_owner_email=_is_owner_email)
    # Press links are baked into emails and read days later, so they are
    # built from the canonical address rather than whichever host the
    # request happened to arrive on.
    press_desk.init(app, base_url=lambda: PUBLIC_BASE_URL)
    # TOUR: invitation and share links are pasted into messages and read
    # later, so they too are built from the canonical address.
    tour_os.init(app, base_url=lambda: PUBLIC_BASE_URL)
    # Signal: the A&R / distribution / rights intelligence layer. Access is a
    # row in its own roster, seeded from the Operator Desk roster and the
    # owner predicate - no person's name lives in the module.
    signal_hub.init(app, base_url=lambda: PUBLIC_BASE_URL,
                    is_owner_email=_is_owner_email)
    lights_store.init_lights()
    # Partner OS: resellers who put their own name on this software.
    # users.partner_id is the spine - scoping the ACCOUNT to a partner
    # scopes everything the account owns without touching the tables
    # underneath, all of which are already scoped by user_id.
    partner_store.init_partners()
    partner_os.init(app)
    # Audio Intelligence: the provider seam plus its policy, jobs and
    # usage ledger. Adapters register themselves on import; the mock is
    # the default, so the app runs with no vendor and no key.
    audio_store.init_audio()
    audio_providers.bootstrap()   # adapters register here; mock is the default
    # Slow audio work answers on the vendor's clock. /webhooks/ is already a
    # public prefix, so this endpoint carries its own signature check and is
    # 404 unless the feature and a signing secret are both configured.
    audio_webhooks.init(app)
    # The operator's window on all of the above. Owner-gated on the same
    # predicate as every other internal surface; no name lives in code.
    audio_admin.init(app, is_owner_email=_is_owner_email,
                     current_user=current_user)
    # The artist-facing lanes: dubbing, campaign audio, stems, voice vault.
    # Every lane is off until its own flag is set, and the page says so per
    # lane rather than hiding what the product does.
    audio_studio.init(app, current_user=current_user)
    # Noise Lab Phase 1: an independently removable local-audio module.
    # NOISE_LAB_ENABLED=1 enables its account-gated route; default is off.
    # No recording uploads, AI calls, database migration or V1 dependencies.
    import noise_lab
    noise_lab.init(app, current_user=current_user)
    # Portable Song Builder: separately flagged, authenticated and stored.
    # Registration is default-off and does not initialize its database.
    import song_builder
    song_builder.init(app, current_user=current_user)
    # Team-Up Board: renew and thread links go into emails, so they are
    # built from the canonical address too.
    board.init(app, base_url=lambda: PUBLIC_BASE_URL)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
