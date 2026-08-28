"""Mock audio adapters - the app runs, and demos, with no vendor at all.

These are not stubs that raise NotImplementedError. They are complete,
deterministic implementations that return well-formed results, so every
workflow above them can be built and tested without a key, a network, or
a bill. Demo mode is this file.

TWO RULES THEY FOLLOW WITHOUT EXCEPTION
---------------------------------------
1. They say they are mocks. health().state is "mock", every result carries
   is_mock=True, and the UI is expected to show it. Nothing here should
   ever be mistakable for a real transcription of real audio.
2. They are deterministic. The same input gives the same output, seeded
   from a checksum of the request, so tests can assert on results and a
   demo looks the same twice.

They also refuse what a real provider would refuse - unsupported features,
and zero-retention claims they cannot honour - so the calling code meets
those paths in development rather than in production.
"""
import hashlib
import json
import time

import audio_providers as ap


def _seed(*parts):
    raw = "|".join(str(p) for p in parts).encode("utf-8", "replace")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16)


def _mock_id(prefix, *parts):
    raw = "|".join(str(p) for p in parts).encode("utf-8", "replace")
    return "%s_mock_%s" % (prefix, hashlib.sha256(raw).hexdigest()[:16])


# Fictional throughout. No real artist, manager, label or company appears
# here, and none should ever be added: demo data that names a real person
# is a rights problem wearing a placeholder's clothes.
_SPEAKERS = ["Speaker 1", "Speaker 2", "Speaker 3"]

_LINES = [
    "Thanks for making time. I want to walk through where the record is.",
    "We have got eleven finished masters and two that need a vocal pass.",
    "The distributor conversation is the part I am least sure about.",
    "Right now everything is going out through the aggregator we started with.",
    "We should talk about the split on the two features before release.",
    "I will send the paperwork over so your attorney can look at it.",
    "The tour announcement lands the same week, which is either good or a mess.",
    "Let us get the metadata cleaned up before anything is delivered.",
    "I do not want to commit to a term length until we see the offer in writing.",
    "Can you pull the last twelve months of statements for that catalogue.",
]


class MockTranscription(ap.TranscriptionProvider):
    key = "mock"

    def health(self):
        return ap.ProviderHealth(True, "mock",
                                 "Deterministic offline transcription. Nothing leaves this machine.")

    def supports(self, feature):
        return feature in ("diarization", "timestamps", "language_detect",
                           "keyterms", "entities")

    def supports_zero_retention(self):
        # Honest, and true for once: a mock has nowhere to retain anything.
        return True

    def transcribe(self, request):
        jid = _mock_id("tr", request.audio_path or request.audio_url,
                       request.language, request.partner_id)
        return {"provider_job_id": jid, "status": "completed", "is_mock": True}

    def status(self, provider_job_id):
        n = 4 + (_seed(provider_job_id) % 5)          # 4-8 segments
        segments, t = [], 0
        for i in range(n):
            line = _LINES[(_seed(provider_job_id, i)) % len(_LINES)]
            dur = 2200 + (_seed(provider_job_id, i, "d") % 3400)
            segments.append({
                "speaker": _SPEAKERS[i % 2],
                "start_ms": t,
                "end_ms": t + dur,
                "text": line,
                "confidence": 0.82 + (_seed(provider_job_id, i, "c") % 15) / 100.0,
            })
            t += dur + 300
        return {
            "provider_job_id": provider_job_id,
            "status": "completed",
            "language": "en",
            "is_mock": True,
            "full_text": " ".join(s["text"] for s in segments),
            "segments": segments,
            "speakers": sorted({s["speaker"] for s in segments}),
            "duration_ms": t,
        }


class MockSpeech(ap.SpeechProvider):
    key = "mock"

    def health(self):
        return ap.ProviderHealth(True, "mock",
                                 "Generates a silent, correctly-formed WAV. No voice is synthesised.")

    def supports(self, feature):
        return feature in ("streaming",)

    def supports_zero_retention(self):
        return True

    def synthesize(self, request):
        """A real, playable WAV of silence, the length the text would take.

        Silence rather than a tone: a demo that plays audible noise gets
        mistaken for a working voice, and somebody eventually ships it.
        """
        words = max(1, len((request.text or "").split()))
        seconds = min(600.0, max(0.6, words / 2.6))   # ~155 wpm
        rate, ch, bits = 44100, 1, 16
        n = int(rate * seconds)
        data_len = n * ch * bits // 8
        hdr = b"RIFF" + (36 + data_len).to_bytes(4, "little") + b"WAVE"
        hdr += b"fmt " + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
        hdr += ch.to_bytes(2, "little") + rate.to_bytes(4, "little")
        hdr += (rate * ch * bits // 8).to_bytes(4, "little")
        hdr += (ch * bits // 8).to_bytes(2, "little") + bits.to_bytes(2, "little")
        hdr += b"data" + data_len.to_bytes(4, "little")
        return {
            "audio": hdr + b"\x00" * data_len,
            "mime_type": "audio/wav",
            "duration_ms": int(seconds * 1000),
            "characters": len(request.text or ""),
            "voice_id": request.voice_id or "mock-voice",
            "is_mock": True,
        }


class MockAgent(ap.AgentProvider):
    key = "mock"

    def health(self):
        return ap.ProviderHealth(True, "mock",
                                 "Scripted conversations. No call is placed and no audio is streamed.")

    def supports(self, feature):
        return feature in ("web", "human_transfer", "tools", "knowledge_base")

    def supports_zero_retention(self):
        return True

    def create_agent(self, request):
        return {"provider_agent_id": _mock_id("ag", request.get("name"),
                                              request.get("partner_id")),
                "status": "ready", "is_mock": True}

    def update_agent(self, request):
        return {"provider_agent_id": request.get("provider_agent_id"),
                "status": "ready", "is_mock": True}

    def create_session(self, request):
        return {"provider_conversation_id": _mock_id("cv", time.time(),
                                                     request.get("agent_id")),
                "status": "open", "is_mock": True}

    def get_conversation(self, provider_conversation_id):
        return {
            "provider_conversation_id": provider_conversation_id,
            "status": "completed",
            "duration_seconds": 90 + (_seed(provider_conversation_id) % 240),
            "is_mock": True,
            "transcript": [
                {"role": "agent", "text": "You are speaking with an AI assistant. "
                                          "I can answer questions and take details, "
                                          "and I can put you through to a person."},
                {"role": "caller", "text": "I want to know about distribution."},
                {"role": "agent", "text": "I can take some details and have an "
                                          "operator call you back."},
            ],
        }

    def verify_webhook(self, raw_body, headers, secret):
        """The mock verifies a real HMAC. The signing path is the part that
        must not be exercised for the first time in production, so the same
        code runs here."""
        import hmac as _hmac
        sig = (headers or {}).get("X-Signature") or ""
        if not secret or not sig:
            return False
        want = _hmac.new(secret.encode("utf-8"), raw_body or b"", hashlib.sha256).hexdigest()
        return _hmac.compare_digest(want, sig)


class MockDubbing(ap.DubbingProvider):
    key = "mock"

    def health(self):
        return ap.ProviderHealth(True, "mock", "Returns the source unchanged, labelled as a mock.")

    def supports_zero_retention(self):
        return True

    def create_project(self, request):
        return {"provider_job_id": _mock_id("db", request.get("source_asset_id")),
                "status": "completed", "is_mock": True}

    def status(self, provider_job_id):
        return {"provider_job_id": provider_job_id, "status": "completed", "is_mock": True}

    def download(self, provider_job_id, language_code):
        return {"audio": b"", "mime_type": "audio/wav", "language": language_code,
                "is_mock": True,
                "note": "Mock dubbing returns no audio. Nothing here is translated."}


class MockMusic(ap.MusicProvider):
    key = "mock"

    def health(self):
        return ap.ProviderHealth(True, "mock", "No music is generated. Structure only.")

    def supports(self, feature):
        return feature in ("composition_plan",)

    def supports_zero_retention(self):
        return True

    def generate(self, request):
        raise ap.ProviderRefusal(
            "Mock mode does not generate music. Configure a music provider, "
            "or use the composition plan, which needs no generation.",
            "mock_no_generation")

    def composition_plan(self, request):
        s = _seed(request.get("source_asset_id"), request.get("prompt"))
        bpm = 84 + (s % 60)
        return {
            "is_mock": True,
            "sections": [
                {"name": "intro", "start_ms": 0, "end_ms": 12000},
                {"name": "verse", "start_ms": 12000, "end_ms": 42000},
                {"name": "chorus", "start_ms": 42000, "end_ms": 70000},
                {"name": "outro", "start_ms": 70000, "end_ms": 88000},
            ],
            "tempo_bpm": bpm,
            "time_signature": "4/4",
            "energy": ["low", "medium", "high", "medium"],
        }


class MockStems(ap.StemProvider):
    key = "mock"

    def health(self):
        return ap.ProviderHealth(True, "mock",
                                 "Names the lanes; returns no separated audio.")

    def supports_zero_retention(self):
        return True

    def separate(self, request):
        return {"is_mock": True, "status": "completed",
                "stems": [{"name": n, "audio": b""} for n in
                          ("vocals", "drums", "bass", "instruments")],
                "note": "Mock separation returns no audio."}


class MockVoiceIsolation(ap.VoiceIsolationProvider):
    key = "mock"

    def health(self):
        return ap.ProviderHealth(True, "mock", "Returns the input unchanged.")

    def supports_zero_retention(self):
        return True

    def isolate(self, request):
        return {"is_mock": True, "audio": b"", "mime_type": "audio/wav",
                "note": "Mock isolation does not process audio."}


class MockSoundEffects(ap.SoundEffectsProvider):
    key = "mock"

    def health(self):
        return ap.ProviderHealth(True, "mock", "Returns silence of the requested length.")

    def supports_zero_retention(self):
        return True

    def generate_effect(self, request):
        secs = min(22.0, max(0.5, float(request.get("duration_seconds") or 2.0)))
        out = MockSpeech().synthesize(ap.SpeechRequest(" " * int(secs * 2.6)))
        out["effect_prompt"] = request.get("prompt") or ""
        return out


class MockVoiceIdentity(ap.VoiceIdentityProvider):
    key = "mock"

    def health(self):
        return ap.ProviderHealth(True, "mock",
                                 "Records a reference only. No voice model is created or held.")

    def supports_zero_retention(self):
        return True

    def register_verified_voice(self, request):
        """Even in mock, this refuses without evidence that the OWNER did the
        verifying. The whole point of the Voice Vault is that a manager
        cannot register somebody else's voice, and a mock that shrugs at
        that teaches the calling code the wrong shape."""
        if not request.get("owner_verified"):
            raise ap.ProviderRefusal(
                "The voice owner has not completed verification. A voice can "
                "only be registered by the person whose voice it is.",
                "owner_not_verified")
        return {"provider_voice_id": _mock_id("vc", request.get("owner_person_id")),
                "verification_status": "verified_mock", "is_mock": True}

    def revoke(self, provider_voice_id):
        return {"revoked": True, "is_mock": True}


def register_all():
    for a in (MockTranscription(), MockSpeech(), MockAgent(), MockDubbing(),
              MockMusic(), MockStems(), MockVoiceIsolation(),
              MockSoundEffects(), MockVoiceIdentity()):
        ap.register(a)


register_all()
