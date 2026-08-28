"""StemSplit.io — the Stem Deck's studio-quality separation tier.

Env-gated on STEMSPLIT_API_KEY (pasted into Render Environment, never
through chat). Without the key the feature does not render and its
endpoints answer 503 - nothing pretends.

Flow, shaped around the Render Starter's limits:
  1. The Rack uploads the loaded track once; we park it on disk under an
     unguessable token and lend StemSplit a public URL to fetch it from
     (their documented source_url flow) - the dyno never re-streams the
     source to the API.
  2. We create a FOUR_STEMS job and the browser polls our status proxy;
     the key stays server-side.
  3. Finished stems stream back through us (their presigned URLs make no
     CORS promises), then the temp source is deleted. A sweeper also
     drops anything older than an hour so restarts cannot leak files.

Uses urllib - no new dependency.
"""

import json
import os
import tempfile
import time
import urllib.error
import urllib.request
import uuid

BASE = "https://stemsplit.io/api/v1"
# Who we are, said plainly, with somewhere to look us up. Follows
# PUBLIC_BASE_URL so it stays true when the domain changes.
UA = "StreetBanker/1.0 (+%s)" % (
    os.environ.get("PUBLIC_BASE_URL")
    or "https://street-banker.onrender.com").rstrip("/")
JOBS = os.environ.get("STEMSPLIT_JOBS_PATH", "/jobs")
SRC_DIR = os.path.join(tempfile.gettempdir(), "sb-stem-src")
MAX_UPLOAD = 60 * 1024 * 1024          # a full-length WAV, with headroom
SRC_TTL = 3600

# job id -> temp source path, so terminal statuses can clean up
_sources = {}

# A job can report COMPLETED before its output URLs exist. That is not a
# guess: a real split came back "COMPLETED, progress 100, stems []", and
# the four URLs were there when we asked again moments later. Clients stop
# polling on COMPLETED, so that one response would leave a finished split
# with nothing to download and no reason to look again.
#
# So completion is only believed once there is something to hand over.
# Until then the job is still settling: keep reporting progress, keep the
# parked source alive, and keep the client asking.
_settling = {}
SETTLE_GRACE = 90.0   # after this, report the truth instead of spinning


def configured():
    return bool(os.environ.get("STEMSPLIT_API_KEY"))


def _headers():
    """Identify the client properly.

    StemSplit sits behind Cloudflare, whose browser-integrity check rejects
    requests carrying urllib's default `Python-urllib/3.x` agent - it
    answered 403 with Cloudflare error 1010 on EVERY path, including
    /balance and a job id that does not exist. Identical answers everywhere
    is the signature of a WAF, not an API: a real API 404s an unknown path
    and 401s a bad key, and that pattern is what showed the key was never
    the problem.

    This is a plain, honest product agent with a contact URL - the client
    saying who it is, which is what an API expects. It is not pretending to
    be a browser.
    """
    return {
        "Authorization": "Bearer " + os.environ.get("STEMSPLIT_API_KEY", ""),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": UA,
    }


def _call(method, path, payload=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()), None
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
            msg = detail.get("message") or detail.get("error") or str(e)
        except Exception:
            msg = str(e)
        return None, "%s (HTTP %s)" % (msg, e.code)
    except Exception as e:
        return None, str(e)


def _scrub(text):
    """Never let the key appear in anything we hand back, even by accident."""
    key = os.environ.get("STEMSPLIT_API_KEY")
    if key and len(key) > 6:
        text = text.replace(key, "[redacted]")
    return text


def probe():
    """Which read-only endpoints does this key actually reach?

    Two published sources disagree about the path (/jobs in the REST docs,
    /separate in the n8n node), and a wrong path answers 403 rather than
    404, which is indistinguishable from a dead key. So ask the API. Every
    path here is GET and free - no job is created and no credit is spent.
    Returns status codes and a scrubbed body snippet, never the key.
    """
    out = []
    for path in ("/balance", "/jobs", "/separate",
                 "/jobs/probe-no-such-job", "/separate/probe-no-such-job"):
        req = urllib.request.Request(BASE + path, headers=_headers(),
                                     method="GET")
        entry = {"path": path}
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                entry["status"] = resp.status
                entry["body"] = _scrub(resp.read(400).decode("utf8", "replace"))
        except urllib.error.HTTPError as e:
            entry["status"] = e.code
            try:
                entry["body"] = _scrub(e.read(400).decode("utf8", "replace"))
            except Exception:
                entry["body"] = ""
        except Exception as e:
            entry["status"] = None
            entry["body"] = _scrub(str(e))
        out.append(entry)
    return out


def sweep():
    """Drop parked sources older than an hour - restart-safe cleanup."""
    try:
        now = time.time()
        for name in os.listdir(SRC_DIR):
            p = os.path.join(SRC_DIR, name)
            if os.path.isfile(p) and now - os.path.getmtime(p) > SRC_TTL:
                os.remove(p)
    except OSError:
        pass


def park_source(data, ext):
    """Store the uploaded track under a token; returns (token, path)."""
    os.makedirs(SRC_DIR, exist_ok=True)
    sweep()
    token = uuid.uuid4().hex + (ext or "")
    path = os.path.join(SRC_DIR, token)
    with open(path, "wb") as f:
        f.write(data)
    return token, path


def source_path(token):
    """Resolve a token back to its file - tokens only, no path tricks."""
    if not token or "/" in token or "\\" in token or ".." in token:
        return None
    path = os.path.join(SRC_DIR, token)
    return path if os.path.isfile(path) else None


# Values worth asking the API about. FOUR_STEMS is the only one we have
# seen work; everything else here is a candidate to be tested, never
# something to ship on faith. The nonsense entry is the control: a
# rejection message for a value that certainly does not exist often names
# the ones that do.
PROBE_TYPES = ("FOUR_STEMS", "SIX_STEMS", "FIVE_STEMS", "TWO_STEMS",
               "SEVEN_STEMS", "VOCALS_INSTRUMENTAL", "VOCAL_REMOVER",
               "STEMS_6", "SIX", "6", "NOT_A_REAL_OUTPUT_TYPE")

# A source that can never be fetched. Reserved TLD, so no DNS, no request
# leaves for anyone's server, and nothing of the user's is exposed.
PROBE_SOURCE = "https://probe.invalid/nonexistent.wav"


def probe_output_types(candidates=None):
    """Which outputType values does this account's API actually accept?

    Asked rather than assumed, and asked for free. We know first-hand that
    a job whose source cannot be downloaded is refused before any work
    happens - one of ours came back DOWNLOAD_TIMEOUT with no job created
    and no credits moved. So an unfetchable source is a safe canary:

      invalid outputType -> the request fails validation, and the error
                            talks about the field
      valid   outputType -> validation passes and it fails later, at the
                            download, which is a different error entirely

    The shape of the failure is the answer. Nothing is separated, so
    nothing is billed.
    """
    results = []
    for value in (candidates or PROBE_TYPES):
        body, err = _call("POST", JOBS, {
            "sourceUrl": PROBE_SOURCE,
            "outputType": value,
            "quality": "BEST",
            "outputFormat": "MP3",
        })
        text = ("" if err is None else str(err))
        low = text.lower()
        # Getting as far as the download means the enum was fine.
        reached_download = any(k in low for k in (
            "download", "fetch", "source", "url", "timed out", "timeout"))
        names_the_field = any(k in low for k in (
            "outputtype", "output_type", "invalid", "enum", "must be",
            "one of", "allowed", "unsupported"))
        if err is None:
            verdict = "accepted"          # a job was created - see below
        elif reached_download and not names_the_field:
            verdict = "accepted"
        elif names_the_field:
            verdict = "rejected"
        else:
            verdict = "unclear"
        results.append({
            "value": value,
            "verdict": verdict,
            "error": text[:400],
            # If one ever does create a job, say so loudly: that would
            # mean the canary fetched, and a real job may be running.
            "job_created": None if err else (body.get("id")
                                             or body.get("jobId")),
        })
    return results


def create_job(source_url, output_type=None):
    """One separation job at best quality. Keys are camelCase per the
    published REST contract - snake_case is silently rejected.

    outputFormat does nothing. We send MP3 and the job body comes back
    saying options.outputFormat is "MP3", and then every output URL ends
    in .wav. It is not being honoured; the container of the stems follows
    the container of the SOURCE.

    Verified rather than assumed: the same 30-second cut sent as WAV came
    back as seven .wav files at 5.05 MB each, and sent as MP3 came back
    as .mp3 at 1.15 MB. So the lever for stem size is the format the
    source is uploaded in, not this field.

    We keep sending MP3 anyway - it costs nothing, it is what we would
    want if they ever start honouring it, and it documents the intent.
    """
    if output_type not in MODES:
        output_type = DEFAULT_MODE      # never post an unknown enum
    body, err = _call("POST", JOBS, {
        "sourceUrl": source_url,
        "outputType": output_type,
        "quality": "BEST",
        "outputFormat": "MP3",
    })
    if err:
        return None, err
    job_id = body.get("id") or body.get("jobId")
    if not job_id:
        return None, "StemSplit accepted the job but returned no id"
    return job_id, None


def remember_source(job_id, path):
    _sources[job_id] = path


"""Every stem name the API can hand back, across all modes."""
STEMS = ("vocals", "drums", "bass", "other", "instrumental",
         "guitar", "piano")

# The separation modes this account actually has. Not a guess: the API
# names them itself when it rejects an unknown one -
#   "Must be one of: VOCALS, INSTRUMENTAL, BOTH, FOUR_STEMS, SIX_STEMS"
# - which is what probe_output_types() above goes and asks for.
#
# "stems" is the PARTITION: the set that adds back up to the record, and
# so the set that can sit on the deck together. The API often returns
# extras beyond it - a FOUR_STEMS job also came back with an instrumental
# mix - and those are fine to download but must not become lanes, because
# instrumental is drums+bass+other over again and would play the record
# twice.
MODES = {
    "VOCALS": {
        "label": "Vocal only",
        "stems": ("vocals",),
        "note": "Just the voice, pulled out on its own.",
    },
    "INSTRUMENTAL": {
        "label": "Instrumental only",
        "stems": ("instrumental",),
        "note": "The record with the voice taken out.",
    },
    "BOTH": {
        "label": "Vocal + instrumental",
        "stems": ("vocals", "instrumental"),
        "note": "Two lanes. The classic acapella-and-beat pair.",
    },
    "FOUR_STEMS": {
        "label": "Four stems",
        "stems": ("vocals", "drums", "bass", "other"),
        "note": "Vocals, drums, bass, and everything else in one lane.",
    },
    "SIX_STEMS": {
        "label": "Six stems",
        "stems": ("vocals", "drums", "bass", "guitar", "piano", "other"),
        "note": "The four, with guitar and piano lifted out of "
                "“everything else”. Asking for more separation costs some "
                "precision — the lanes add back up slightly less exactly "
                "than four do.",
    },
}
DEFAULT_MODE = "FOUR_STEMS"


def mode_stems(output_type):
    """The lanes a mode produces - the ones that sum back to the record."""
    return list(MODES.get(output_type, MODES[DEFAULT_MODE])["stems"])


def mode_list():
    """Modes for the UI, in the order they get more detailed."""
    order = ("VOCALS", "INSTRUMENTAL", "BOTH", "FOUR_STEMS", "SIX_STEMS")
    return [dict(value=k, count=len(MODES[k]["stems"]), **MODES[k])
            for k in order]


def _outputs(body):
    """Stem name -> url, from either published response shape: the docs'
    nested {"outputs": {"vocals": {"url": ...}}} or the n8n node's flat
    {"vocalsUrl": ...}. Whichever this account's API returns, we read it."""
    found = {}
    nested = body.get("outputs") or {}
    if isinstance(nested, dict):
        for name, entry in nested.items():
            url = entry.get("url") if isinstance(entry, dict) else entry
            if isinstance(url, str):
                found[name.lower()] = url
    for name in STEMS:
        url = body.get(name + "Url")
        if isinstance(url, str) and name not in found:
            found[name] = url
    return found


def job_status(job_id):
    """Normalized status: {status, progress, stems:[name]}. Terminal
    statuses delete the parked source."""
    body, err = _call("GET", JOBS + "/" + job_id)
    if err:
        return None, err
    status = str(body.get("status") or "PENDING").upper()
    stems = sorted(_outputs(body).keys())

    if status == "COMPLETED" and not stems:
        first = _settling.setdefault(job_id, time.monotonic())
        if time.monotonic() - first < SETTLE_GRACE:
            # Hold the job open rather than hand back a completed split
            # with no stems in it. The source stays parked too, because
            # the cleanup below would delete the one thing a retry needs.
            return {"status": "PROCESSING",
                    "progress": min(99, int(body.get("progress") or 99)),
                    "stems": [], "settling": True}, None
        # Waited long enough. Report what the API actually says - a job
        # that never produces outputs is a failure worth showing, not one
        # to keep spinning on.
    else:
        _settling.pop(job_id, None)

    out = {"status": status,
           "progress": body.get("progress") or 0,
           "stems": stems}
    if status in ("COMPLETED", "FAILED", "EXPIRED"):
        _settling.pop(job_id, None)
        path = _sources.pop(job_id, None)
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
    return out, None


def stem_url(job_id, stem):
    """Fresh presigned URL for one stem, straight from the API - they
    expire in an hour, so we never cache them."""
    body, err = _call("GET", JOBS + "/" + job_id)
    if err:
        return None, err
    url = _outputs(body).get(stem)
    if not url or not url.startswith("https://"):
        return None, "stem not available"
    return url, None


# Content-Type -> file extension. The API returns WAV for these jobs, but
# the format is the account's to choose, so the name follows what actually
# arrived rather than what we assumed.
_EXT = {"audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
        "audio/vnd.wave": "wav", "audio/mpeg": "mp3", "audio/mp3": "mp3",
        "audio/flac": "flac", "audio/x-flac": "flac", "audio/aiff": "aiff",
        "audio/x-aiff": "aiff", "audio/mp4": "m4a", "audio/aac": "m4a"}


def stem_filename(stem, url, content_type):
    """What the browser should call this file.

    Without a filename the browser names the download after the last path
    segment, so five stems arrive as "vocals", "drums", "bass" - no
    extension, and nothing on the machine knows how to open them.
    """
    ext = _EXT.get((content_type or "").split(";")[0].strip().lower())
    if not ext:
        # Fall back to the presigned URL's own extension before guessing.
        tail = (url or "").split("?")[0].rsplit("/", 1)[-1]
        if "." in tail:
            cand = tail.rsplit(".", 1)[-1].lower()
            if cand.isalnum() and 2 <= len(cand) <= 4:
                ext = cand
    return "studio-split-%s.%s" % (stem, ext or "wav")


def open_stream(url):
    """Open the presigned URL for streaming to the browser."""
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}),
        timeout=60)
