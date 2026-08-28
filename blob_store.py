"""Where uploaded files live.

Everything the app stores - vault audio, cover art, EPK photos, sync
packs, documents - has been landing on the Render disk next to the
SQLite database. That disk is 1 GB and shared with the database, so
audio is the line item that ends the arrangement: a handful of masters
fills it and takes the database down with it.

This puts an object store in front of that disk. Cloudflare R2 because
egress is free, which matters more than the storage price here - a fan
EPK player streams the same file repeatedly, and on S3 the bandwidth
bill outgrows the storage bill quickly.

DESIGN NOTES, in the order they will matter to whoever reads this next:

  Not configured means local disk, not broken. Set the four R2 env vars
  and new uploads go to the bucket; leave them unset and everything
  behaves exactly as it did. No feature disappears, nothing pretends.

  Old rows keep working. Paths already in the database look like
  "/uploads/vault_3_17...mp3" and still resolve to the disk. New objects
  are stored as "r2:<key>". Two shapes, one resolver, no migration
  required to deploy. A backfill can move the old ones later.

  Signed by hand rather than with boto3. SigV4 is hmac + hashlib, and
  boto3 would add ~50 MB to a Starter build for two API calls.

  Reads are presigned and short-lived. The bucket stays private, so a
  vault URL cannot be forwarded to somebody who should not have it -
  it expires. That is the whole reason not to make the bucket public.

Credentials come from the environment and are never logged:
  R2_ACCOUNT_ID, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
Optional: R2_PUBLIC_BASE_URL, if you attach a custom domain and want
plain public URLs for non-sensitive assets instead of signed ones.
"""

import datetime
import hashlib
import logging
import hmac
import os
import urllib.error
import urllib.parse
import urllib.request

import sandbox

log = logging.getLogger("blob_store")

REGION = "auto"
SERVICE = "s3"
ALGO = "AWS4-HMAC-SHA256"
DEFAULT_TTL = 3600          # an hour is long enough to play a track

# Marker for objects that live in the bucket. Anything else is a legacy
# "/uploads/..." disk path.
PREFIX = "r2:"


def _env(name):
    return (os.environ.get(name) or "").strip()


def configured():
    # Sandbox writes to its own ephemeral disk rather than the bucket
    # production reads from. Test uploads are not production objects.
    if sandbox.active():
        return False
    return all(_env(k) for k in ("R2_ACCOUNT_ID", "R2_BUCKET",
                                 "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"))


def _endpoint():
    return "https://%s.r2.cloudflarestorage.com" % _env("R2_ACCOUNT_ID")


def _host():
    return "%s.r2.cloudflarestorage.com" % _env("R2_ACCOUNT_ID")


def _quote(path):
    """S3 wants each segment percent-encoded, with the slashes intact."""
    return "/".join(urllib.parse.quote(p, safe="~") for p in path.split("/"))


def _sign(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret, datestamp):
    k = _sign(("AWS4" + secret).encode("utf-8"), datestamp)
    k = _sign(k, REGION)
    k = _sign(k, SERVICE)
    return _sign(k, "aws4_request")


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


# --- signing --------------------------------------------------------------

def _canonical(method, uri, query, headers, payload_hash):
    canon_headers = "".join("%s:%s\n" % (k, headers[k]) for k in sorted(headers))
    signed = ";".join(sorted(headers))
    return ("%s\n%s\n%s\n%s\n%s\n%s"
            % (method, uri, query, canon_headers, signed, payload_hash)), signed


def _auth_header(method, key, payload, content_type):
    """Header-style SigV4, used for PUT and DELETE where we hold the bytes."""
    now = _now()
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    uri = "/%s/%s" % (_env("R2_BUCKET"), _quote(key))
    payload_hash = hashlib.sha256(payload or b"").hexdigest()

    headers = {"host": _host(), "x-amz-content-sha256": payload_hash,
               "x-amz-date": amzdate}
    if content_type:
        headers["content-type"] = content_type

    canon, signed = _canonical(method, uri, "", headers, payload_hash)
    scope = "%s/%s/%s/aws4_request" % (datestamp, REGION, SERVICE)
    to_sign = "%s\n%s\n%s\n%s" % (ALGO, amzdate, scope,
                                  hashlib.sha256(canon.encode()).hexdigest())
    sig = hmac.new(_signing_key(_env("R2_SECRET_ACCESS_KEY"), datestamp),
                   to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = (
        "%s Credential=%s/%s, SignedHeaders=%s, Signature=%s"
        % (ALGO, _env("R2_ACCESS_KEY_ID"), scope, signed, sig))
    return headers, uri


def presigned_get(key, ttl=DEFAULT_TTL):
    """A time-limited URL. The bucket stays private."""
    now = _now()
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    uri = "/%s/%s" % (_env("R2_BUCKET"), _quote(key))
    scope = "%s/%s/%s/aws4_request" % (datestamp, REGION, SERVICE)

    params = {
        "X-Amz-Algorithm": ALGO,
        "X-Amz-Credential": "%s/%s" % (_env("R2_ACCESS_KEY_ID"), scope),
        "X-Amz-Date": amzdate,
        "X-Amz-Expires": str(int(ttl)),
        "X-Amz-SignedHeaders": "host",
    }
    query = "&".join("%s=%s" % (urllib.parse.quote(k, safe="~"),
                                urllib.parse.quote(params[k], safe="~"))
                     for k in sorted(params))
    canon, _ = _canonical("GET", uri, query, {"host": _host()},
                          "UNSIGNED-PAYLOAD")
    to_sign = "%s\n%s\n%s\n%s" % (ALGO, amzdate, scope,
                                  hashlib.sha256(canon.encode()).hexdigest())
    sig = hmac.new(_signing_key(_env("R2_SECRET_ACCESS_KEY"), datestamp),
                   to_sign.encode(), hashlib.sha256).hexdigest()
    return "%s%s?%s&X-Amz-Signature=%s" % (_endpoint(), uri, query, sig)


# --- the two calls the app makes -----------------------------------------

def put(key, data, content_type=None):
    headers, uri = _auth_header("PUT", key, data, content_type)
    req = urllib.request.Request(_endpoint() + uri, data=data,
                                 headers=headers, method="PUT")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return 200 <= resp.status < 300


def delete(key):
    headers, uri = _auth_header("DELETE", key, b"", None)
    req = urllib.request.Request(_endpoint() + uri, headers=headers,
                                 method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        return exc.code == 404          # already gone is a success


# --- what app.py actually calls ------------------------------------------

def save(fname, data, content_type=None, uploads_dir=None):
    """Store bytes and return the path to record in the database.

    "r2:<key>" when the bucket is configured, "/uploads/<fname>" when it
    is not. The caller does not branch on which.
    """
    if configured():
        try:
            if put(fname, data, content_type):
                return PREFIX + fname
            log.error("blob_store: PUT returned a non-2xx for %s; using disk", fname)
        except urllib.error.HTTPError as exc:
            # A 4xx is a permanent misconfiguration, not an outage: it
            # will fail identically on every upload until somebody fixes
            # a credential. Swallowing it silently is how a bucket stays
            # unused for weeks while every upload still reports success
            # and the disk this exists to protect fills up anyway.
            #
            # Safe to log: the secret never appears in an HTTPError, and
            # the S3 body is Cloudflare naming its own refusal.
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            log.error("blob_store: R2 refused PUT %s with %s %s. %s "
                      "Falling back to disk; check the R2 env vars.",
                      fname, exc.code, exc.reason, body)
        except Exception as exc:
            # Transient: a timeout or a network blip. Quiet fallback,
            # because the artist's upload must not be lost over it.
            log.warning("blob_store: PUT %s failed (%s); using disk",
                        fname, type(exc).__name__)

    if uploads_dir:
        # A key may be a path ("beats/<user>/<id>.wav") because that is
        # how it wants to live in a bucket. On disk those segments are
        # real directories, and open() will not make them: without this,
        # every nested key raised FileNotFoundError while the R2 path
        # accepted the same key happily.
        dest = os.path.join(uploads_dir, *fname.split("/"))
        parent = os.path.dirname(dest)
        if parent and parent != uploads_dir:
            os.makedirs(parent, exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(data)
        return "/uploads/" + fname

    # No object store and nowhere on disk to put it. Returning a path
    # here would record a database row pointing at a file that was never
    # written - a broken download later instead of an error now.
    raise RuntimeError(
        "blob_store.save: nothing to save into. The object store is "
        "unconfigured or refused the write, and no uploads_dir was given.")


def is_remote(path):
    return bool(path) and path.startswith(PREFIX)


def key_of(path):
    return path[len(PREFIX):] if is_remote(path) else None


def url_for(path, ttl=DEFAULT_TTL):
    """Resolve a stored path to something a browser can fetch."""
    if not is_remote(path):
        return path                      # legacy disk path, served locally
    key = key_of(path)
    base = _env("R2_PUBLIC_BASE_URL")
    if base:
        return "%s/%s" % (base.rstrip("/"), _quote(key))
    if not configured():
        # Credentials were removed after objects were written, or a
        # worker booted without them. Signing here would raise and take
        # the whole page with it; a dead link is the smaller failure.
        return path
    try:
        return presigned_get(key, ttl)
    except Exception:
        return path


def diagnose():
    """Why the bucket is unreachable, without printing any secret.

    A URLError out of put() means the request never got to Cloudflare, so
    the useful question is whether the endpoint host resolves - and the
    host is built entirely from R2_ACCOUNT_ID. A Cloudflare account id is
    32 hex characters; anything else is usually a pasted URL, a token id
    or a truncated copy.
    """
    import socket

    account = _env("R2_ACCOUNT_ID")
    bucket = _env("R2_BUCKET")
    access = _env("R2_ACCESS_KEY_ID")
    report = {
        # A Cloudflare access key id is also 32 hex characters, so it is
        # indistinguishable from an account id by shape. Comparing them
        # is the only way to catch the swap, and it prints neither.
        "account_id_equals_access_key_id": bool(account and account == access),
        # A 32-hex bucket is the shape of an access key id. If it IS the
        # access key, the paste was shifted across the four variables.
        "bucket_equals_access_key_id": bool(bucket and bucket == access),
        "bucket_equals_account_id": bool(bucket and bucket == account),
        "bucket_looks_like_an_id": bool(
            len(bucket) == 32 and all(c in "0123456789abcdefABCDEF" for c in bucket)),
        # R2's S3 pair has a fixed shape: the access key id is 32 hex
        # (it is the token's id) and the secret is 64 hex (it is the
        # SHA-256 of the token value). Anything else means the pair did
        # not come from R2 -> Manage R2 API Tokens. A raw "cfk_..." token
        # value in either slot is the classic case.
        "access_key_len": len(access),
        "access_key_is_32_hex": bool(
            len(access) == 32 and all(c in "0123456789abcdefABCDEF" for c in access)),
        "access_key_looks_like_a_cf_token": access.startswith("cfk_"),
        "secret_len": len(_env("R2_SECRET_ACCESS_KEY")),
        "secret_is_64_hex": bool(
            len(_env("R2_SECRET_ACCESS_KEY")) == 64
            and all(c in "0123456789abcdefABCDEF" for c in _env("R2_SECRET_ACCESS_KEY"))),
        "secret_looks_like_a_cf_token": _env("R2_SECRET_ACCESS_KEY").startswith("cfk_"),
        "account_id_len": len(account),
        "account_id_is_32_hex": bool(
            len(account) == 32 and all(c in "0123456789abcdefABCDEF" for c in account)),
        "account_id_has_scheme_or_slash": ("/" in account or ":" in account),
        "bucket_len": len(bucket),
        "bucket_has_slash": "/" in bucket,
        "host_suffix": ".r2.cloudflarestorage.com",
    }
    try:
        socket.getaddrinfo(_host(), 443)
        report["host_resolves"] = True
    except Exception as exc:
        report["host_resolves"] = False
        report["dns_error"] = str(exc)[:180]
        report["verdict"] = "DNS failed for the endpoint host"
        return report

    # DNS is not the discriminator: Cloudflare wildcards
    # *.r2.cloudflarestorage.com, so any account id resolves. What it does
    # NOT do is complete a TLS handshake for an account that does not
    # exist - it rejects the SNI. So the handshake is the real test, and
    # it needs no credentials to run.
    import ssl
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((_host(), 443), timeout=15) as raw:
            with ctx.wrap_socket(raw, server_hostname=_host()):
                report["tls_handshake"] = True
                report["verdict"] = ("endpoint is real; a failure past this "
                                     "point is credentials or bucket, not the "
                                     "account id")
    except ssl.SSLError as exc:
        report["tls_handshake"] = False
        report["tls_error"] = str(exc)[:180]
        report["verdict"] = ("Cloudflare refused the TLS handshake for this "
                             "account subdomain, which means R2_ACCOUNT_ID is "
                             "not an account Cloudflare recognises. It is the "
                             "32-hex id in the R2 S3 endpoint "
                             "https://<id>.r2.cloudflarestorage.com - not the "
                             "bucket name, token id or token value.")
        # If the value sitting in R2_BUCKET completes the handshake, the
        # two variables are simply the wrong way round. Worth one more
        # connection to be able to say so outright.
        if report.get("bucket_looks_like_an_id"):
            try:
                alt = "%s.r2.cloudflarestorage.com" % bucket
                with socket.create_connection((alt, 443), timeout=15) as raw2:
                    with ctx.wrap_socket(raw2, server_hostname=alt):
                        report["bucket_value_is_the_account"] = True
                        report["verdict"] = (
                            "R2_ACCOUNT_ID and R2_BUCKET are swapped: the "
                            "value in R2_BUCKET completes the handshake as an "
                            "account subdomain and the one in R2_ACCOUNT_ID "
                            "does not. Put the 32-hex account id in "
                            "R2_ACCOUNT_ID and the bucket's name in R2_BUCKET.")
            except Exception:
                report["bucket_value_is_the_account"] = False
    except Exception as exc:
        report["tls_handshake"] = False
        report["tls_error"] = "%s: %s" % (type(exc).__name__, str(exc)[:140])
        report["verdict"] = "could not reach the endpoint at all"
    return report


def fetch(path, timeout=30):
    """Read an object back as bytes, or None.

    Only the batch-download zip needs this: everything else hands the
    browser a presigned URL and lets it do the fetching. Returns None
    rather than raising, because one unreachable object should cost that
    file and not the whole archive.
    """
    if not is_remote(path) or not configured():
        return None
    try:
        url = presigned_get(key_of(path), ttl=120)
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except Exception:
        # Deliberately broad. Signing an unreachable or half-configured
        # endpoint raises things that are not URLError - an empty account
        # id produces a malformed host and a UnicodeError from idna - and
        # one bad object must not take the archive down with it.
        return None


def remove(path, uploads_dir=None):
    if is_remote(path):
        try:
            return delete(key_of(path))
        except Exception:
            return False
    if uploads_dir and path and path.startswith("/uploads/"):
        try:
            # basename() would miss a nested key entirely and delete
            # nothing while reporting success. relpath() also refuses to
            # escape the uploads directory.
            os.remove(safe_local_path(path, uploads_dir))
            return True
        except (OSError, ValueError):
            return False
    return False


def safe_local_path(path, uploads_dir):
    """The on-disk location for a "/uploads/..." path, or ValueError.

    The key may be nested, so this joins every segment — and then checks
    the result is still inside uploads_dir, so a stored path that somehow
    contains ".." cannot reach the rest of the filesystem.
    """
    rel = path[len("/uploads/"):]
    dest = os.path.abspath(os.path.join(uploads_dir, *rel.split("/")))
    root = os.path.abspath(uploads_dir)
    if not (dest == root or dest.startswith(root + os.sep)):
        raise ValueError("path escapes the uploads directory")
    return dest
