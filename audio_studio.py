"""Audio Studio - the artist-facing surface for phases 4, 5 and 6.

WHAT IS HERE
------------
  Global Release Pack      dubbing a release into other languages
  Campaign Audio Toolkit   voiceover and sound effects for a campaign
  Remix Lab Audio Engine   stem separation and voice isolation
  Artist Voice Vault       registering a voice the OWNER verified

One page rather than four, because they are the same act with different
verbs - upload something you own, confirm you own it, run one operation -
and four pages would each grow their own half of the rights check.

EVERY LANE IS OFF UNTIL ITS OWN FLAG IS SET
-------------------------------------------
The page renders with nothing enabled and says so per lane. An artist should
be able to see what the product would do before an operator switches on
anything that costs money.

THE VOICE VAULT IS DIFFERENT AND SAYS SO
----------------------------------------
Every other lane processes a recording. The Vault registers a VOICE, which is
a person. Street Banker never holds the voice model - it records a reference
to one the owner verified through the vendor's own process, plus the
permission record around it. A manager cannot register an artist's voice from
this page, and the mock adapter refuses it too, so the calling code meets that
path in development rather than in production.
"""
import os
import time

from flask import (Blueprint, abort, redirect, render_template, request,
                   send_file, url_for)

import audio_policy
import audio_retention
import audio_store as astore
import audio_works as works
import blob_store

bp = Blueprint("audio_studio", __name__)

STUDIO_PREFIX = "studio:"

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".mp4", ".aac", ".ogg", ".oga",
              ".flac", ".webm"}

# lane key -> (work kind, flag, title, one-line description)
LANES = [
    ("release_pack", "dubbing", "GLOBAL_RELEASE_PACK_ENABLED",
     "Global Release Pack",
     "Dub a release into other languages, keeping the performance."),
    ("campaign_vo", "campaign_voiceover", "CAMPAIGN_AUDIO_TOOLKIT_ENABLED",
     "Campaign voiceover",
     "A read for an advert, a trailer or a social cut."),
    ("campaign_sfx", "sound_effects", "CAMPAIGN_AUDIO_TOOLKIT_ENABLED",
     "Sound effects",
     "Short effects for a campaign edit."),
    ("remix_stems", "stem_separation", "STEM_SEPARATION_ENABLED",
     "Stem separation",
     "Split a recording you own into vocals, drums, bass and instruments."),
    ("remix_isolate", "voice_isolation", "VOICE_ISOLATION_ENABLED",
     "Voice isolation",
     "Lift a vocal out of a recording you own."),
    ("voice_vault", "voice_vault", "ARTIST_VOICE_VAULT_ENABLED",
     "Artist Voice Vault",
     "Register a voice its owner has verified. Only they can."),
]

LANE_BY_KEY = {lane[0]: lane for lane in LANES}


# Lanes whose gate demands a consent record that NOTHING in this app can
# write yet. audio_policy.gate() requires a "voice_owner" consent row for the
# Vault, and astore.record_consent() has no caller anywhere - so the lane
# would advertise itself, take a submission, create a work row and then refuse
# every single time.
#
# A lane that can never complete must not read as available. This is the same
# rule the rest of the product follows: do not offer what cannot work. Remove
# a key from here the moment its consent flow exists.
_CONSENT_FLOW_MISSING = {"voice_vault"}


def _on(flag, kind=None):
    """Is this lane genuinely usable?

    The lane's own flag is not enough. audio_policy.gate() checks the flag
    named in FEATURES for the work kind, and the two are not always the same
    name - the campaign lanes advertise under CAMPAIGN_AUDIO_TOOLKIT_ENABLED
    while sound effects gate on SOUND_EFFECTS_ENABLED.

    Reading only the lane flag showed "available" on a lane that then refused
    every submission, which is a worse failure than showing it off: the artist
    fills in a brief, presses the button and is told no for a reason that has
    nothing to do with what they typed. So both are required, and the gate's
    flag is looked up rather than restated here.
    """
    if not audio_policy.flag("AUDIO_INTELLIGENCE_ENABLED"):
        return False
    if not audio_policy.flag(flag):
        return False
    if kind in _CONSENT_FLOW_MISSING:
        return False
    spec = audio_policy.FEATURES.get(kind) if kind else None
    if spec and not audio_policy.flag(spec["flag"]):
        return False
    return True


def _needed_flags(lane_flag, kind):
    """Every flag this lane actually needs, so the page can name all of them
    rather than the first one somebody thought of."""
    names = [lane_flag]
    spec = audio_policy.FEATURES.get(kind)
    if spec and spec["flag"] not in names:
        names.append(spec["flag"])
    return " and ".join(names)


def _studio_dir():
    import db as store
    path = os.path.join(os.path.dirname(store.db_path()), "audio_studio")
    os.makedirs(path, exist_ok=True)
    return path


def _save(fname, data, content_type):
    """Never the public uploads tree. A master an artist uploaded to be split
    into stems is the most valuable file they own."""
    if blob_store.configured():
        try:
            if blob_store.put("studio/" + fname, data, content_type):
                return blob_store.PREFIX + "studio/" + fname
        except Exception:
            pass
    with open(os.path.join(_studio_dir(), fname), "wb") as handle:
        handle.write(data)
    return STUDIO_PREFIX + fname


def _current_user():
    return _user_getter() if _user_getter else None


_user_getter = None


def _lanes_for_render():
    return [{"key": key, "kind": kind, "title": title, "note": note,
             "on": _on(flag, kind), "flag": _needed_flags(flag, kind)}
            for key, kind, flag, title, note in LANES]


@bp.route("/audio-studio")
def studio():
    user = _current_user()
    if user is None:
        return redirect(url_for("login", next=request.path))
    return render_template(
        "audio_studio.html",
        lanes=_lanes_for_render(),
        works=works.list_works(user_id=user["id"], limit=40),
        safety_warning=works.safety_warning(),
        any_on=any(lane["on"] for lane in _lanes_for_render()))


@bp.route("/audio-studio/new", methods=["POST"])
def studio_new():
    user = _current_user()
    if user is None:
        return redirect(url_for("login", next=request.path))

    lane_key = (request.form.get("lane") or "").strip()
    lane = LANE_BY_KEY.get(lane_key)
    if lane is None:
        abort(404)
    _key, kind, flag, title, _note = lane
    if not _on(flag, kind):
        abort(404)

    source_asset_id = None
    upload = request.files.get("file")
    if upload is not None and upload.filename:
        ext = os.path.splitext(upload.filename)[1].lower()
        if ext not in AUDIO_EXTS:
            return _refuse("That is not an audio file this can work with.")
        data = upload.read()
        if not data:
            return _refuse("That file is empty.")
        if len(data) > MAX_UPLOAD_BYTES:
            return _refuse("That file is larger than the 200 MB limit.")
        path = _save("studio_%d%s" % (int(time.time() * 1000), ext), data,
                     upload.mimetype or "audio/mpeg")
        source_asset_id = astore.create_asset(
            None, user["id"], path, file_name=upload.filename[:200],
            mime_type=upload.mimetype or "audio/mpeg", file_size=len(data),
            rights_status="confirmed" if request.form.get("rights") == "1"
            else "unconfirmed",
            retention_days=audio_retention.retention_days(None, "source"))

    item = works.create_work(
        user["id"], kind, title=request.form.get("title") or title,
        brief=request.form.get("brief") or "",
        options=_options(kind), source_asset_id=source_asset_id)

    # The rights confirmation is an act, recorded against THIS item with who
    # performed it - never inherited from the account.
    if request.form.get("rights") == "1":
        works.confirm_rights(item["id"], user.get("name") or user.get("email") or "")

    try:
        works.submit_work(item["id"])
    except works.WorkRefusal:
        # The refusal is already recorded on the item and is rendered there.
        # Not raised into the artist's face as an error page: they are going
        # to want to read it and fix the brief.
        pass
    return redirect(url_for("audio_studio.studio_item", work_id=item["id"]))


@bp.route("/audio-studio/<work_id>")
def studio_item(work_id):
    user = _current_user()
    if user is None:
        return redirect(url_for("login", next=request.path))
    item = works.get_work(work_id)
    if item is None or item["user_id"] != user["id"]:
        # Somebody else's work is a 404, not a 403: they should not learn it
        # exists.
        abort(404)
    outputs = [astore.get_asset(None, aid) for aid in item["output_asset_ids"]]
    return render_template("audio_studio_item.html", item=item,
                           outputs=[o for o in outputs if o],
                           lane=_lane_for_kind(item["kind"]),
                           safety_warning=works.safety_warning())


@bp.route("/audio-studio/<work_id>/delete", methods=["POST"])
def studio_delete(work_id):
    user = _current_user()
    if user is None:
        return redirect(url_for("login", next=request.path))
    item = works.get_work(work_id)
    if item is None or item["user_id"] != user["id"]:
        abort(404)
    if item.get("source_asset_id"):
        asset = astore.get_asset(None, item["source_asset_id"])
        if asset and asset.get("storage_key"):
            _destroy(asset["storage_key"])
            astore.mark_asset_deleted(item["source_asset_id"])
    works.delete_work(work_id)
    return redirect(url_for("audio_studio.studio"))


def _destroy(storage_key):
    try:
        if storage_key.startswith(STUDIO_PREFIX):
            os.remove(os.path.join(_studio_dir(), storage_key[len(STUDIO_PREFIX):]))
        else:
            blob_store.remove(storage_key, uploads_dir=audio_retention.uploads_dir())
    except OSError:
        pass


def _lane_for_kind(kind):
    for key, lane_kind, flag, title, note in LANES:
        if lane_kind == kind:
            return {"key": key, "title": title, "note": note,
                    "on": _on(flag, kind)}
    return {"key": "", "title": kind, "note": "", "on": False}


def _options(kind):
    if kind == "sound_effects":
        try:
            seconds = float(request.form.get("duration_seconds") or 3)
        except (TypeError, ValueError):
            seconds = 3.0
        return {"duration_seconds": max(0.5, min(22.0, seconds))}
    if kind == "dubbing":
        langs = [x.strip() for x in (request.form.get("languages") or "").split(",")
                 if x.strip()]
        return {"languages": langs[:8] or ["es"]}
    if kind == "voice_vault":
        # owner_verified is never taken from this form. The vendor's own
        # verification is the only thing that can set it, and the adapter
        # refuses without it - including the mock, so this path is exercised
        # in development.
        return {"owner_person_id": request.form.get("owner_person_id") or "",
                "owner_verified": False}
    return {}


def _refuse(message):
    return render_template("audio_studio_refused.html", message=message), 400


def init(app, current_user):
    global _user_getter
    _user_getter = current_user
    works.init_works()
    app.register_blueprint(bp)
