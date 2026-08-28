"""Transactional email via Resend — release-day notes to captured fans.

Env-gated like every other provider: without RESEND_API_KEY nothing
sends and nothing pretends to. The default sender is Resend's shared
test address (delivers only to the account owner's own inbox) until
EMAIL_FROM is set to an address on a domain verified in Resend.
`_http` is the seam tests monkeypatch.
"""

import base64
import hashlib
import hmac
import json
import os
import urllib.request

import sandbox

_TIMEOUT = 12


def configured():
    # A sandbox deployment reports no provider even if a key is present,
    # so every path here degrades the way it already does without one. An
    # experiment must not be able to mail a real person.
    if sandbox.active():
        return False
    return bool(os.environ.get("RESEND_API_KEY"))


def sender():
    return os.environ.get("EMAIL_FROM") or "Street Banker <onboarding@resend.dev>"


def _http(url, payload, headers):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        body = resp.read()
        return json.loads(body.decode("utf-8")) if body else {}


def send(to, subject, html, attachments=None):
    """One email (optional attachments: [{filename, content-b64}]).
    True only when Resend accepted it."""
    if not configured() or not to:
        return False
    payload = {"from": sender(), "to": [to], "subject": subject, "html": html}
    if attachments:
        payload["attachments"] = attachments
    try:
        out = _http("https://api.resend.com/emails", payload, {
            "Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
            "Content-Type": "application/json",
        })
        return bool(out.get("id"))
    except Exception:
        return False


# --- Inbound: the statement drop-box -------------------------------------------
# Resend receives email for a domain and fires an email.received webhook
# (metadata only); attachments download via the receiving API.

def inbound_configured():
    return bool(os.environ.get("RESEND_WEBHOOK_SECRET")
                and os.environ.get("RESEND_INBOUND_DOMAIN"))


def inbound_address(token):
    domain = os.environ.get("RESEND_INBOUND_DOMAIN", "")
    return "%s@%s" % (token, domain) if domain else ""


def verify_webhook(headers, body):
    """Svix-style signature check for Resend webhooks."""
    secret = os.environ.get("RESEND_WEBHOOK_SECRET", "")
    msg_id = headers.get("svix-id", "")
    timestamp = headers.get("svix-timestamp", "")
    signatures = headers.get("svix-signature", "")
    if not (secret and msg_id and timestamp and signatures):
        return False
    key = base64.b64decode(secret.split("_", 1)[-1])
    signed = "%s.%s.%s" % (msg_id, timestamp,
                           body.decode("utf-8") if isinstance(body, bytes) else body)
    expected = base64.b64encode(
        hmac.new(key, signed.encode(), hashlib.sha256).digest()).decode()
    for part in signatures.split(" "):
        if part.split(",", 1)[-1] == expected:
            return True
    return False


def _http_get(url, headers=None):
    """GET seam (JSON or raw bytes) — tests monkeypatch this."""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def list_received_attachments(email_id):
    raw = _http_get("https://api.resend.com/emails/receiving/%s/attachments" % email_id,
                    {"Authorization": "Bearer " + os.environ["RESEND_API_KEY"]})
    return json.loads(raw.decode("utf-8")).get("data", [])


def download_attachment(download_url):
    return _http_get(download_url)


def using_shared_test_sender():
    """True while EMAIL_FROM is unset. Resend's onboarding@resend.dev only
    delivers to the account owner's own inbox, so every send LOOKS like it
    worked and nobody else ever receives one. Worth naming loudly."""
    return "resend.dev" in sender()


def _api_get(path):
    """Read-only call to the Resend API. Returns (data, error)."""
    if not configured():
        return None, "RESEND_API_KEY not set"
    req = urllib.request.Request(
        "https://api.resend.com" + path,
        headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
                 "Accept": "application/json",
                 "User-Agent": "StreetBanker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read()
            return (json.loads(raw.decode("utf-8")) if raw else {}), None
    except Exception as exc:
        detail = str(exc)
        if hasattr(exc, "read"):
            try:
                detail += " " + exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
        return None, detail


def domain_status():
    """Every domain on the Resend account with the DNS records each still
    needs. Read-only: this asks what is there, it changes nothing.

    The point is to hand over the exact records to paste rather than send
    someone hunting through a dashboard for them.
    """
    listing, err = _api_get("/domains")
    if err:
        return {"error": err, "domains": []}
    out = []
    for d in (listing.get("data") or []):
        detail, derr = _api_get("/domains/" + d.get("id", ""))
        records = []
        for r in ((detail or {}).get("records") or []):
            records.append({
                "type": r.get("type"), "name": r.get("name"),
                "value": r.get("value"), "ttl": r.get("ttl"),
                "priority": r.get("priority"),
                "status": r.get("status"), "purpose": r.get("record"),
            })
        out.append({
            "id": d.get("id"), "name": d.get("name"),
            "status": d.get("status"), "region": d.get("region"),
            "records": records, "record_error": derr,
        })
    return {"error": None, "domains": out}


def release_email_html(campaign_title, artist_name, listen_url, cover_url=""):
    """Branded release-day note. Plain, readable, one clear button."""
    cover = ('<img src="%s" alt="" width="120" style="border-radius:var(--sb-r-panel);display:block;margin:0 auto 16px;">'
             % cover_url) if cover_url else ""
    return (
        '<div style="background:#0B0A08;padding:32px 16px;font-family:Arial,sans-serif;">'
        '<div style="max-width:480px;margin:0 auto;background:#131110;border:1px solid #8A6E30;'
        'border-radius:var(--sb-r-panel);padding:32px;text-align:center;">'
        + cover +
        '<p style="color:#C9A24A;font-size:12px;letter-spacing:3px;margin:0;">OUT NOW</p>'
        '<h1 style="color:#F2ECE0;font-size:24px;margin:8px 0 4px;">%s</h1>'
        '<p style="color:#A99B84;font-size:14px;margin:0 0 24px;">%s</p>'
        '<a href="%s" style="display:inline-block;background:#E8B950;color:#14100A;'
        'font-weight:bold;font-size:14px;padding:12px 28px;border-radius:var(--sb-r-panel);'
        'text-decoration:none;">Listen Now</a>'
        '<p style="color:#91836A;font-size:12px;margin:24px 0 0;">You asked to be notified '
        'about this release. Links open your preferred platform.</p>'
        '</div></div>'
    ) % (campaign_title, artist_name, listen_url)
