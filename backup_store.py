"""Off-box backup: get the snapshot somewhere the app cannot lose it.

/backup already makes a good snapshot - SQLite's backup API for a
consistent copy, plus the uploads directory, zipped. Its problem is that
it only happens when a human remembers to click it, and it lands on
whatever laptop did the clicking. Everything real in this app - invoices,
logged hours, statements, disputes - lives on one Render disk. One disk.

This uploads that snapshot to any S3-compatible bucket (Cloudflare R2,
Backblaze B2, Wasabi, S3 itself) so a lost disk is an inconvenience
rather than the end of somebody's books.

Env-gated like every other provider. Without credentials it does nothing
and says so - it never pretends a backup happened.

    BACKUP_S3_ENDPOINT   https://<account>.r2.cloudflarestorage.com
    BACKUP_S3_BUCKET     street-banker-backups
    BACKUP_S3_KEY        access key id
    BACKUP_S3_SECRET     secret access key
    BACKUP_S3_REGION     optional, defaults to "auto" (R2's value)
    BACKUP_TOKEN         shared secret a scheduler presents to trigger it

Signature Version 4 is implemented here directly. It is about sixty lines
of hashing and boto3 is forty megabytes; on a Starter dyno that trade is
not close.
"""

import datetime
import hashlib
import hmac
import os
import urllib.error
import urllib.request

_ALGO = "AWS4-HMAC-SHA256"


def configured():
    return all(os.environ.get(k) for k in (
        "BACKUP_S3_ENDPOINT", "BACKUP_S3_BUCKET",
        "BACKUP_S3_KEY", "BACKUP_S3_SECRET"))


def target():
    """Where backups go, for display. Never includes the credentials."""
    if not configured():
        return ""
    return "%s/%s" % (os.environ["BACKUP_S3_ENDPOINT"].rstrip("/"),
                      os.environ["BACKUP_S3_BUCKET"])


def _sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret, datestamp, region, service):
    k = _sign(("AWS4" + secret).encode("utf-8"), datestamp)
    k = _sign(k, region)
    k = _sign(k, service)
    return _sign(k, "aws4_request")


def put(key_name, data, content_type="application/zip"):
    """Upload one object. Returns (ok, detail) - never raises at the caller.

    The payload is hashed rather than sent unsigned: an unsigned-payload
    upload would be accepted by most providers, but signing it means a
    truncated or corrupted body is rejected at the far end instead of
    silently becoming a backup that will not restore.
    """
    if not configured():
        return False, "not configured"

    endpoint = os.environ["BACKUP_S3_ENDPOINT"].rstrip("/")
    bucket = os.environ["BACKUP_S3_BUCKET"]
    access = os.environ["BACKUP_S3_KEY"]
    secret = os.environ["BACKUP_S3_SECRET"]
    region = os.environ.get("BACKUP_S3_REGION") or "auto"
    service = "s3"

    if "://" not in endpoint:
        endpoint = "https://" + endpoint
    scheme, rest = endpoint.split("://", 1)
    host = rest.split("/", 1)[0]
    key_name = key_name.lstrip("/")
    canonical_uri = "/%s/%s" % (bucket, key_name)
    url = "%s://%s%s" % (scheme, host, canonical_uri)

    now = datetime.datetime.now(datetime.timezone.utc)
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(data).hexdigest()

    canonical_headers = ("content-type:%s\nhost:%s\nx-amz-content-sha256:%s\n"
                         "x-amz-date:%s\n"
                         % (content_type, host, payload_hash, amzdate))
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join([
        "PUT", canonical_uri, "", canonical_headers, signed_headers,
        payload_hash])

    scope = "%s/%s/%s/aws4_request" % (datestamp, region, service)
    string_to_sign = "\n".join([
        _ALGO, amzdate, scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()])
    signature = hmac.new(_signing_key(secret, datestamp, region, service),
                         string_to_sign.encode("utf-8"),
                         hashlib.sha256).hexdigest()
    authorization = ("%s Credential=%s/%s, SignedHeaders=%s, Signature=%s"
                     % (_ALGO, access, scope, signed_headers, signature))

    req = urllib.request.Request(url, data=data, method="PUT", headers={
        "Authorization": authorization,
        "Content-Type": content_type,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amzdate,
        "Content-Length": str(len(data)),
    })
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return (200 <= resp.status < 300,
                    "HTTP %s, %d bytes" % (resp.status, len(data)))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        return False, "HTTP %s %s" % (exc.code, body)
    except Exception as exc:
        return False, str(exc)


def object_name(when=None):
    """Dated key, newest-sortable, so a bucket listing reads as a history."""
    when = when or datetime.datetime.now(datetime.timezone.utc)
    return "street-banker/%s/streetbanker-%s.zip" % (
        when.strftime("%Y-%m"), when.strftime("%Y-%m-%dT%H%M%SZ"))
