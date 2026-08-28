"""ElevenLabs adapters, written against the installed SDK.

WHAT CHANGED FROM THE FIRST DRAFT
---------------------------------
The first version of this file refused every call, because guessing
endpoint names would have been worse than admitting ignorance. The SDK is
now installed (elevenlabs 2.65.0) and every signature below was read from
it rather than remembered:

    speech_to_text.convert(file|cloud_storage_url, model_id, diarize,
                           timestamps_granularity, num_speakers,
                           tag_audio_events, language_code, enable_logging)
    text_to_speech.convert(voice_id, text, model_id, output_format,
                           language_code, seed, enable_logging)
    text_to_sound_effects.convert(text, duration_seconds, prompt_influence,
                                  loop, model_id, output_format)
    audio_isolation.convert(audio, file_format)
    music.compose(prompt, composition_plan, music_length_ms, model_id, seed,
                  force_instrumental, store_for_inpainting, output_format)
    music.upload(file, extract_composition_plan, with_timestamps)
    music.separate_stems(file, output_format, stem_variation_id)
    dubbing.create(file|source_url, source_lang, target_lang, num_speakers,
                   watermark, name)
    dubbing.get(dubbing_id)
    conversational_ai.agents / conversations / knowledge_base / tools
    models.list()

ZERO RETENTION IS ONE FLAG, AND IT IS GATED BY PLAN
---------------------------------------------------
The SDK documents `enable_logging` in its own words:

    "When enable_logging is set to false zero retention mode will be used
     for the request. This will mean log and transcript storage features
     are unavailable for this request. Zero retention mode may only be
     used by enterprise customers."

Two consequences the code honours. First, a key is not evidence of
entitlement - an ordinary account setting enable_logging=False gets an
error, not privacy - so supports_zero_retention() stays False until an
operator sets ELEVENLABS_ZERO_RETENTION_VERIFIED after confirming the
account in writing. Second, zero retention disables transcript STORAGE,
so the result must be taken from the response; there is nothing to fetch
later. The transcription adapter therefore returns the transcript inline
and status() reads a per-process cache rather than calling back.

HEALTH IS MEASURED, NOT DECLARED
--------------------------------
health() calls models.list() - cheap, read-only, and the only honest way
to know a key works. It caches the answer briefly so a page of adapters
does not make nine calls. Nothing here reports ready on the strength of
an environment variable.
"""
import os
import threading
import time

import audio_providers as ap

VENDOR = "elevenlabs"

# Defaults taken from the SDK's own docstring examples. Overridable, and
# verifiable at runtime with models.list() - which is authoritative, unlike
# any id written into source.
DEFAULT_STT_MODEL = os.environ.get("ELEVENLABS_STT_MODEL") or "scribe_v2"
DEFAULT_TTS_MODEL = os.environ.get("ELEVENLABS_TTS_MODEL") or "eleven_multilingual_v2"

_TRUE = ("1", "true", "yes", "on")
_lock = threading.Lock()
_health_cache = {"at": 0.0, "value": None}
_HEALTH_TTL = 60.0


def _on(name):
    return (os.environ.get(name) or "").strip().lower() in _TRUE


def _enabled():
    return _on("ELEVENLABS_ENABLED")


def _api_key():
    return (os.environ.get("ELEVENLABS_API_KEY") or "").strip()


def _client():
    """A configured SDK client, or None. Never a stand-in."""
    if not _enabled() or not _api_key():
        return None
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        return None
    try:
        return ElevenLabs(api_key=_api_key())
    except Exception:
        return None


def _zero_retention_ok():
    """Enterprise-gated at the vendor, and undetectable from here.

    There is no endpoint that answers "is this account allowed zero
    retention". Sending enable_logging=False on an account without it
    produces an error, not privacy - so this stays an operator assertion,
    made after confirming the account in writing.
    """
    return _on("ELEVENLABS_ZERO_RETENTION_VERIFIED")


def _measure_health():
    """One real call. models.list() is read-only and costs nothing."""
    if not _enabled():
        return ap.ProviderHealth(False, "unconfigured",
                                 "ELEVENLABS_ENABLED is not set. The mock adapter is in use.")
    if not _api_key():
        return ap.ProviderHealth(False, "unconfigured",
                                 "ELEVENLABS_ENABLED is set but ELEVENLABS_API_KEY is empty.")
    try:
        import elevenlabs  # noqa: F401
    except ImportError:
        return ap.ProviderHealth(False, "unconfigured",
                                 "The elevenlabs SDK is not installed in this environment.")
    c = _client()
    if c is None:
        return ap.ProviderHealth(False, "error", "The SDK client could not be constructed.")
    try:
        models = c.models.list()
        n = len(list(models)) if models is not None else 0
        return ap.ProviderHealth(
            True, "ready",
            "Key accepted. %d models visible to this account." % n,
            verified_live=True)
    except Exception as e:
        # Deliberately not parsed into "probably auth" - the vendor's own
        # message is more use to whoever is reading the admin page.
        return ap.ProviderHealth(False, "error",
                                 "%s: %s" % (type(e).__name__, str(e)[:200]))


def _health():
    now = time.time()
    with _lock:
        if _health_cache["value"] is not None and now - _health_cache["at"] < _HEALTH_TTL:
            return _health_cache["value"]
    h = _measure_health()
    with _lock:
        _health_cache.update({"at": now, "value": h})
    return h


def reset_health_cache():
    with _lock:
        _health_cache.update({"at": 0.0, "value": None})


class _Base(ap.AudioProvider):
    key = VENDOR

    def health(self):
        return _health()

    def supports_zero_retention(self):
        return _zero_retention_ok()

    def _ready(self):
        h = _health()
        if not h.ok:
            raise ap.ProviderRefusal(
                "ElevenLabs is not available: %s" % h.detail, "provider_unavailable")
        c = _client()
        if c is None:
            raise ap.ProviderRefusal("The ElevenLabs client could not be built.",
                                     "provider_unavailable")
        return c

    def _logging_flag(self, zero_retention):
        """enable_logging=False IS zero-retention mode. Refuse rather than
        send it on an account that has not been confirmed for it: the
        request would fail anyway, and a caller that asked for zero
        retention must never get a stored one instead."""
        if not zero_retention:
            return True
        if not _zero_retention_ok():
            raise ap.ProviderRefusal(
                "Zero-retention processing was requested, but this ElevenLabs "
                "account has not been confirmed for it. Zero retention is an "
                "enterprise feature; nothing was sent.", "zero_retention_unavailable")
        return False


class ElevenLabsTranscription(_Base, ap.TranscriptionProvider):
    capability = ap.TRANSCRIPTION

    # Under zero retention the vendor stores nothing, so there is nothing to
    # poll for. The transcript comes back on the response and lives here
    # only until the caller reads it.
    _results = {}

    def supports(self, feature):
        return feature in ("diarization", "timestamps", "language_detect",
                           "keyterms", "entities", "audio_events")

    def transcribe(self, request):
        c = self._ready()
        logging_on = self._logging_flag(request.zero_retention)
        kw = {
            "model_id": DEFAULT_STT_MODEL,
            "diarize": bool(request.diarize),
            "tag_audio_events": True,
            "enable_logging": logging_on,
        }
        if request.timestamps:
            kw["timestamps_granularity"] = "word"
        if request.language:
            kw["language_code"] = request.language      # omitted = detect
        if request.audio_url:
            kw["cloud_storage_url"] = request.audio_url
            resp = c.speech_to_text.convert(**kw)
        else:
            with open(request.audio_path, "rb") as fh:
                kw["file"] = fh
                resp = c.speech_to_text.convert(**kw)

        norm = self._normalise(resp)
        jid = getattr(resp, "transcription_id", None) or ("inline_%d" % (time.time() * 1000))
        norm["provider_job_id"] = jid
        self._results[jid] = norm
        return {"provider_job_id": jid, "status": "completed", "is_mock": False,
                "inline": norm}

    def status(self, provider_job_id):
        cached = self._results.get(provider_job_id)
        if cached:
            return cached
        raise ap.ProviderRefusal(
            "That transcript is not held here. Under zero retention the "
            "provider stores nothing, so the result must be read from the "
            "response that produced it.", "no_stored_transcript")

    def _normalise(self, resp):
        """Vendor shape -> the shape audio_store.save_transcript expects.

        Written defensively: the SDK returns typed objects, and a field that
        moves should degrade to a transcript with no segments rather than
        raise inside a background job.
        """
        def g(o, *names, **kw):
            for n in names:
                if isinstance(o, dict) and n in o:
                    return o[n]
                if hasattr(o, n):
                    return getattr(o, n)
            return kw.get("default")

        words = g(resp, "words", default=None) or []
        segments, cur = [], None
        for w in words:
            wtype = g(w, "type", default="word")
            speaker = g(w, "speaker_id", "speaker", default="") or ""
            text = g(w, "text", default="") or ""
            start = g(w, "start", default=0) or 0
            end = g(w, "end", default=0) or 0
            if wtype not in ("word", "spacing", "audio_event"):
                continue
            if cur is None or (speaker and speaker != cur["speaker"]):
                if cur:
                    segments.append(cur)
                cur = {"speaker": speaker or "Speaker 1",
                       "start_ms": int(float(start) * 1000),
                       "end_ms": int(float(end) * 1000), "text": text}
            else:
                cur["text"] += text
                cur["end_ms"] = int(float(end) * 1000)
        if cur:
            segments.append(cur)
        for s in segments:
            s["text"] = " ".join(s["text"].split())
        return {
            "status": "completed",
            "is_mock": False,
            "language": g(resp, "language_code", "language", default="") or "",
            "confidence": g(resp, "language_probability", default=None),
            "full_text": g(resp, "text", default="") or "",
            "segments": segments,
            "speakers": sorted({s["speaker"] for s in segments}),
        }


class ElevenLabsSpeech(_Base, ap.SpeechProvider):
    capability = ap.SPEECH

    def supports(self, feature):
        return feature in ("streaming", "timestamps", "seed")

    def synthesize(self, request):
        c = self._ready()
        if not request.voice_id:
            raise ap.ProviderRefusal(
                "A voice must be chosen before speech can be generated.",
                "no_voice")
        kw = {
            "voice_id": request.voice_id,
            "text": request.text or "",
            "model_id": request.model or DEFAULT_TTS_MODEL,
            "enable_logging": self._logging_flag(request.zero_retention),
        }
        if request.language:
            kw["language_code"] = request.language
        stream = c.text_to_speech.convert(**kw)
        audio = b"".join(stream) if hasattr(stream, "__iter__") and not isinstance(
            stream, (bytes, bytearray)) else bytes(stream or b"")
        return {"audio": audio, "mime_type": "audio/mpeg",
                "characters": len(request.text or ""),
                "voice_id": request.voice_id, "is_mock": False}


class ElevenLabsSoundEffects(_Base, ap.SoundEffectsProvider):
    capability = ap.SOUND_EFFECTS

    def generate_effect(self, request):
        c = self._ready()
        kw = {"text": request.get("prompt") or ""}
        if request.get("duration_seconds"):
            kw["duration_seconds"] = float(request["duration_seconds"])
        if request.get("loop") is not None:
            kw["loop"] = bool(request["loop"])
        stream = c.text_to_sound_effects.convert(**kw)
        audio = b"".join(stream) if hasattr(stream, "__iter__") and not isinstance(
            stream, (bytes, bytearray)) else bytes(stream or b"")
        return {"audio": audio, "mime_type": "audio/mpeg", "is_mock": False,
                "effect_prompt": kw["text"]}


class ElevenLabsVoiceIsolation(_Base, ap.VoiceIsolationProvider):
    capability = ap.VOICE_ISOLATION

    def isolate(self, request):
        c = self._ready()
        with open(request["audio_path"], "rb") as fh:
            stream = c.audio_isolation.convert(audio=fh)
        audio = b"".join(stream) if hasattr(stream, "__iter__") and not isinstance(
            stream, (bytes, bytearray)) else bytes(stream or b"")
        return {"audio": audio, "mime_type": "audio/mpeg", "is_mock": False}


class ElevenLabsMusic(_Base, ap.MusicProvider):
    capability = ap.MUSIC

    def supports(self, feature):
        return feature in ("composition_plan", "inpainting", "uploaded_audio",
                           "video_to_music")

    def generate(self, request):
        c = self._ready()
        kw = {"prompt": request.get("prompt") or ""}
        if request.get("composition_plan"):
            kw["composition_plan"] = request["composition_plan"]
        if request.get("length_ms"):
            kw["music_length_ms"] = int(request["length_ms"])
        if request.get("seed") is not None:
            kw["seed"] = int(request["seed"])
        if request.get("force_instrumental") is not None:
            kw["force_instrumental"] = bool(request["force_instrumental"])
        # Only ask the vendor to keep the piece when the caller intends to
        # inpaint it later; otherwise storage is somebody's data, retained.
        kw["store_for_inpainting"] = bool(request.get("store_for_inpainting"))
        stream = c.music.compose(**kw)
        audio = b"".join(stream) if hasattr(stream, "__iter__") and not isinstance(
            stream, (bytes, bytearray)) else bytes(stream or b"")
        return {"audio": audio, "mime_type": "audio/mpeg", "is_mock": False,
                "seed": request.get("seed")}

    def upload_owned(self, request):
        c = self._ready()
        with open(request["audio_path"], "rb") as fh:
            resp = c.music.upload(file=fh,
                                  extract_composition_plan=bool(
                                      request.get("extract_composition_plan", True)))
        return {"provider_song_id": getattr(resp, "song_id", None)
                or getattr(resp, "id", None),
                "composition_plan": getattr(resp, "composition_plan", None),
                "is_mock": False, "raw": resp}

    def composition_plan(self, request):
        out = self.upload_owned(dict(request, extract_composition_plan=True))
        plan = out.get("composition_plan")
        if plan is None:
            raise ap.ProviderRefusal(
                "The provider returned no composition plan for that audio.",
                "no_plan")
        return {"plan": plan, "provider_song_id": out.get("provider_song_id"),
                "is_mock": False}

    def inpaint(self, request):
        """Inpainting needs the source held by the vendor, which only happens
        when it was composed or uploaded with store_for_inpainting set. Say
        so plainly rather than failing at the API."""
        if not request.get("provider_song_id"):
            raise ap.ProviderRefusal(
                "Inpainting needs a piece the provider is holding. Compose or "
                "upload it with inpainting enabled first.", "no_stored_source")
        c = self._ready()
        kw = {"prompt": request.get("prompt") or "",
              "composition_plan": request.get("composition_plan"),
              "store_for_inpainting": True}
        kw = {k: v for k, v in kw.items() if v is not None}
        stream = c.music.compose(**kw)
        audio = b"".join(stream) if hasattr(stream, "__iter__") and not isinstance(
            stream, (bytes, bytearray)) else bytes(stream or b"")
        return {"audio": audio, "mime_type": "audio/mpeg", "is_mock": False}


class ElevenLabsStems(_Base, ap.StemProvider):
    capability = ap.STEMS

    def separate(self, request):
        c = self._ready()
        with open(request["audio_path"], "rb") as fh:
            resp = c.music.separate_stems(file=fh)
        return {"status": "completed", "is_mock": False, "raw": resp}


class ElevenLabsDubbing(_Base, ap.DubbingProvider):
    capability = ap.DUBBING

    def create_project(self, request):
        c = self._ready()
        kw = {"target_lang": request.get("target_lang"),
              "name": (request.get("name") or "")[:120]}
        if request.get("source_lang"):
            kw["source_lang"] = request["source_lang"]
        if request.get("num_speakers"):
            kw["num_speakers"] = int(request["num_speakers"])
        if request.get("source_url"):
            kw["source_url"] = request["source_url"]
            resp = c.dubbing.create(**kw)
        else:
            with open(request["source_path"], "rb") as fh:
                kw["file"] = fh
                resp = c.dubbing.create(**kw)
        return {"provider_job_id": getattr(resp, "dubbing_id", None),
                "status": "processing", "is_mock": False}

    def status(self, provider_job_id):
        c = self._ready()
        resp = c.dubbing.get(dubbing_id=provider_job_id)
        return {"provider_job_id": provider_job_id,
                "status": getattr(resp, "status", "unknown"),
                "is_mock": False, "raw": resp}

    def download(self, provider_job_id, language_code):
        c = self._ready()
        get = getattr(getattr(c.dubbing, "audio", None), "get", None)
        if get is None:
            raise ap.ProviderRefusal(
                "This SDK build exposes no dubbing audio download.", "unsupported")
        stream = get(dubbing_id=provider_job_id, language_code=language_code)
        audio = b"".join(stream) if hasattr(stream, "__iter__") and not isinstance(
            stream, (bytes, bytearray)) else bytes(stream or b"")
        return {"audio": audio, "mime_type": "audio/mpeg",
                "language": language_code, "is_mock": False}


class ElevenLabsAgent(_Base, ap.AgentProvider):
    capability = ap.AGENT

    def supports(self, feature):
        return feature in ("web", "phone", "tools", "knowledge_base",
                           "human_transfer", "post_call_webhook")

    def create_agent(self, request):
        c = self._ready()
        resp = c.conversational_ai.agents.create(
            name=request.get("name") or "Street Banker Operator",
            conversation_config=request.get("conversation_config") or {})
        return {"provider_agent_id": getattr(resp, "agent_id", None),
                "status": "ready", "is_mock": False}

    def update_agent(self, request):
        c = self._ready()
        resp = c.conversational_ai.agents.update(
            agent_id=request["provider_agent_id"],
            conversation_config=request.get("conversation_config") or {})
        return {"provider_agent_id": getattr(resp, "agent_id",
                                             request["provider_agent_id"]),
                "status": "ready", "is_mock": False}

    def create_session(self, request):
        """A browser session needs a short-lived signed URL, never the key."""
        c = self._ready()
        link = getattr(c.conversational_ai.conversations, "get_signed_url", None)
        if link is None:
            raise ap.ProviderRefusal(
                "This SDK build exposes no signed conversation URL.", "unsupported")
        resp = link(agent_id=request["agent_id"])
        return {"signed_url": getattr(resp, "signed_url", None),
                "status": "open", "is_mock": False}

    def get_conversation(self, provider_conversation_id):
        c = self._ready()
        resp = c.conversational_ai.conversations.get(
            conversation_id=provider_conversation_id)
        return {"provider_conversation_id": provider_conversation_id,
                "status": getattr(resp, "status", "unknown"),
                "is_mock": False, "raw": resp}

    def verify_webhook(self, raw_body, headers, secret):
        """HMAC over "timestamp.body", the scheme the vendor documents for
        post-call webhooks. Written out rather than delegated: the failure
        mode of a missing verifier is accepting forged events, so it must
        exist even before the rest of the agent work does. Unknown header
        shape rejects - the safe direction."""
        import hashlib
        import hmac

        if not secret or not raw_body:
            return False
        sig = ((headers or {}).get("ElevenLabs-Signature")
               or (headers or {}).get("elevenlabs-signature") or "")
        if not sig:
            return False
        parts = dict(p.split("=", 1) for p in sig.split(",") if "=" in p)
        ts, provided = parts.get("t"), parts.get("v0")
        if not ts or not provided:
            return False
        try:
            if abs(time.time() - int(ts)) > 1800:      # thirty minutes
                return False
        except (TypeError, ValueError):
            return False
        signed = ("%s." % ts).encode("utf-8") + raw_body
        want = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, provided.lower())


class ElevenLabsVoiceIdentity(_Base, ap.VoiceIdentityProvider):
    capability = ap.VOICE_IDENTITY

    def register_verified_voice(self, request):
        """Street Banker records a REFERENCE to a voice its owner verified
        through the vendor's own process. It does not upload somebody's
        samples on their behalf, and it never holds the model."""
        if not request.get("owner_verified"):
            raise ap.ProviderRefusal(
                "The voice owner has not completed verification with the "
                "provider. Street Banker does not register a voice on somebody "
                "else's behalf.", "owner_not_verified")
        vid = request.get("provider_voice_id")
        if not vid:
            raise ap.ProviderRefusal(
                "A verified voice id from the owner's own account is required.",
                "no_voice_reference")
        c = self._ready()
        try:
            voice = c.voices.get(voice_id=vid)
        except Exception as e:
            raise ap.ProviderRefusal(
                "That voice could not be read from the provider: %s" % str(e)[:160],
                "voice_unreadable")
        return {"provider_voice_id": vid,
                "name": getattr(voice, "name", "") or "",
                "verification_status": "reference_confirmed", "is_mock": False}

    def revoke(self, provider_voice_id):
        """Street Banker revokes its own permission record. Deleting a voice
        that lives in the owner's account is the owner's to do, and doing it
        for them would be destroying somebody else's property."""
        return {"revoked_locally": True, "provider_voice_id": provider_voice_id,
                "note": "Street Banker's permission record is revoked. The voice "
                        "itself belongs to its owner's provider account.",
                "is_mock": False}


def register_all():
    for a in (ElevenLabsTranscription(), ElevenLabsSpeech(), ElevenLabsAgent(),
              ElevenLabsDubbing(), ElevenLabsMusic(), ElevenLabsStems(),
              ElevenLabsVoiceIsolation(), ElevenLabsSoundEffects(),
              ElevenLabsVoiceIdentity()):
        ap.register(a)
    # Default to the vendor only when it is switched on AND a key is present.
    # health() still decides per request whether it actually works, and the
    # gate falls back to nothing rather than to a half-configured vendor.
    if _enabled() and _api_key():
        for cap in ap.CAPABILITIES:
            ap.set_default(cap, VENDOR)


register_all()
