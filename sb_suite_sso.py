"""Street Banker suite sign-in: one account, every suite.

Street Banker (app.streetbankermusic.com) is the account system of record.
The suites (The Room, REACH, Tour, Noise Lab) run on their own services and
must never ask for a second password. So Street Banker hands the person
across: it mints a short-lived signed token naming who they are and which
suite they are going to, and the suite verifies it and starts its own
session. Nothing secret crosses the wire except the signature; the shared
secret itself lives only in each service's environment.

This file is identical in every app that takes part. Street Banker calls
``issue``; a suite calls ``verify``. Both need ``SUITE_SSO_SECRET`` set to
the same value. When it is not set, ``configured()`` is False and the caller
falls back to a plain link, so an unconfigured deployment degrades to the
old behaviour instead of breaking.

The token carries: the Street Banker user id, email, display name and plan,
the suite key it was minted for, and a nonce. It is valid for two minutes.
A suite checks the suite key, so a token minted for Tour cannot open REACH.
"""

import os
import secrets
import time

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SALT = "street-banker-suite-sso-v1"
MAX_AGE_SECONDS = 120

# Every suite Street Banker can hand someone to, with the environment
# variable that names its address and the address to use until that is set.
# The defaults are the services running today; the subdomains
# (theroom., reach., tour., noiselab.streetbankermusic.com) replace them by
# changing the variable, never the code.
SUITES = {
    "the-room": ("SUITE_URL_THE_ROOM", "https://street-banker-v2-workflows.onrender.com", "/song-builder/"),
    "reach": ("SUITE_URL_REACH", "https://street-banker-v2-workflows.onrender.com", "/reach/"),
    "noise-lab": ("SUITE_URL_NOISE_LAB", "https://street-banker-v2-workflows.onrender.com", "/noise-lab/"),
    "tour": ("SUITE_URL_TOUR", "https://street-banker-tour-open-preview-3.onrender.com", "/"),
    "motion": ("SUITE_URL_MOTION", "https://masterclip.onrender.com", "/"),
}

# The path on every suite that receives the hand-off.
LANDING_PATH = "/auth/street-banker"


def configured():
    return bool((os.environ.get("SUITE_SSO_SECRET") or "").strip())


def _serializer():
    secret = (os.environ.get("SUITE_SSO_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("SUITE_SSO_SECRET is not set")
    return URLSafeTimedSerializer(secret, salt=SALT)


def suite_base(key):
    """The suite's origin (scheme and host, no trailing slash), or None for
    a key Street Banker does not know."""
    entry = SUITES.get(key)
    if not entry:
        return None
    env_name, default, _home = entry
    return (os.environ.get(env_name) or default).strip().rstrip("/")


def suite_home(key):
    entry = SUITES.get(key)
    return entry[2] if entry else "/"


def issue(user, suite):
    """Mint a token for this Street Banker user, bound to one suite.

    ``user`` is the users-table row: id, email, name and plan are carried.
    Returns the token string."""
    if suite not in SUITES:
        raise ValueError("unknown suite: %r" % (suite,))
    payload = {
        "v": 1,
        "uid": str(user["id"]),
        "email": (user.get("email") or "").strip().lower(),
        "name": (user.get("name") or "").strip()[:120],
        "plan": (user.get("plan") or "artist"),
        "suite": suite,
        "nonce": secrets.token_urlsafe(12),
        "iat": int(time.time()),
    }
    return _serializer().dumps(payload)


def handoff_url(user, suite, next_path=None):
    """The full address Street Banker sends the browser to."""
    base = suite_base(suite)
    if base is None:
        raise ValueError("unknown suite: %r" % (suite,))
    from urllib.parse import urlencode
    query = {"token": issue(user, suite)}
    target = next_path if (next_path and next_path.startswith("/") and not next_path.startswith("//")) else suite_home(suite)
    query["next"] = target
    return base + LANDING_PATH + "?" + urlencode(query)


class HandoffRejected(Exception):
    """The token did not verify. ``reason`` is short and safe to show."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def verify(token, accepted_suites):
    """Check a token this suite received. Returns the payload dict.

    ``accepted_suites`` is the set of suite keys this service hosts; a
    token minted for any other suite is refused even though the signature
    is good, so one shared secret cannot be replayed across suites."""
    if not token:
        raise HandoffRejected("no token")
    try:
        payload = _serializer().loads(token, max_age=MAX_AGE_SECONDS)
    except SignatureExpired:
        raise HandoffRejected("expired")
    except BadSignature:
        raise HandoffRejected("bad signature")
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise HandoffRejected("unrecognised token")
    if payload.get("suite") not in set(accepted_suites):
        raise HandoffRejected("wrong suite")
    email = (payload.get("email") or "").strip().lower()
    if "@" not in email or not payload.get("uid"):
        raise HandoffRejected("incomplete token")
    return payload


def safe_next(value, fallback):
    """A next path we will redirect to: local, absolute, and not a
    scheme-relative URL that would send the person off this host."""
    if not value or not isinstance(value, str):
        return fallback
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return fallback
    return value
