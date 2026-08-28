"""Street Banker Audio Intelligence - the provider seam.

WHY THIS FILE EXISTS
--------------------
Audio vendors supply transcription, speech, agents, dubbing and generative
audio. Street Banker supplies the music-industry judgement around them:
rights, consent, relationships, approval, billing, and the record of who
decided what. The vendor is infrastructure and must stay replaceable, so
nothing in the domain is named after one.

Every capability is an abstract base class here. Adapters live in
audio_mock.py (complete, credential-free) and audio_elevenlabs.py (real,
env-gated). The registry picks one per capability from configuration, so
swapping a vendor is a settings change, not a refactor.

WHAT A PROVIDER MAY NOT DECIDE
------------------------------
A provider never decides whether a job is allowed. Entitlement, consent,
rights, retention and budget are settled before an adapter is called, by
audio_policy.gate(). An adapter that is handed work can assume the work
was authorised; it may still refuse on its own terms (unsupported
feature, unverified retention, bad input) and that refusal is honest.

HEALTH IS A FACT, NOT A GUESS
-----------------------------
health() reports what the adapter can actually verify right now. A mock
says it is a mock. A real adapter with no credentials says unconfigured -
it never reports healthy on the strength of a key it has not used.
"""
import abc


# --- capability names --------------------------------------------------------
# The registry, the settings page and the usage ledger all use these strings.
TRANSCRIPTION = "transcription"
SPEECH = "speech"
AGENT = "agent"
DUBBING = "dubbing"
MUSIC = "music"
STEMS = "stems"
VOICE_ISOLATION = "voice_isolation"
SOUND_EFFECTS = "sound_effects"
VOICE_IDENTITY = "voice_identity"

CAPABILITIES = (TRANSCRIPTION, SPEECH, AGENT, DUBBING, MUSIC, STEMS,
                VOICE_ISOLATION, SOUND_EFFECTS, VOICE_IDENTITY)

CAPABILITY_LABELS = {
    TRANSCRIPTION: "Transcription",
    SPEECH: "Speech synthesis",
    AGENT: "Conversational agent",
    DUBBING: "Dubbing",
    MUSIC: "Music generation",
    STEMS: "Stem separation",
    VOICE_ISOLATION: "Voice isolation",
    SOUND_EFFECTS: "Sound effects",
    VOICE_IDENTITY: "Voice identity",
}


class ProviderHealth(object):
    """What an adapter can actually verify about itself right now."""

    def __init__(self, ok, state, detail="", verified_live=False):
        self.ok = bool(ok)
        # unconfigured | mock | ready | degraded | error
        self.state = state
        self.detail = detail
        # True only when a real call to the vendor has succeeded in this
        # process. A key in the environment is not evidence of anything.
        self.verified_live = bool(verified_live)

    def as_dict(self):
        return {"ok": self.ok, "state": self.state, "detail": self.detail,
                "verified_live": self.verified_live}


class ProviderRefusal(Exception):
    """The adapter will not do this, and says plainly why.

    Distinct from a transport failure: a refusal is a decision the caller
    should surface to a person, not retry.
    """

    def __init__(self, reason, code="refused"):
        Exception.__init__(self, reason)
        self.reason = reason
        self.code = code


class ProviderUnavailable(Exception):
    """The vendor could not be reached, or answered with a transport error.
    Retryable, unlike a refusal."""


class AudioProvider(object):
    """Common ground: a name, a capability, and an honest health report."""
    __metaclass__ = abc.ABCMeta

    key = "abstract"
    capability = None

    def health(self):
        raise NotImplementedError

    # Adapters that cannot do something say so rather than pretending. The
    # gate reads this before it promises anything to a person.
    def supports(self, feature):
        return False

    def supports_zero_retention(self):
        """Never True unless the adapter has verified it with the vendor for
        the account in use. Claiming zero retention that was not configured
        is the one failure in this module that cannot be walked back."""
        return False


class TranscriptionProvider(AudioProvider):
    capability = TRANSCRIPTION

    @abc.abstractmethod
    def transcribe(self, request):
        """request: TranscriptionRequest -> TranscriptionJobResult"""

    @abc.abstractmethod
    def status(self, provider_job_id):
        """-> TranscriptionJobStatus"""


class SpeechProvider(AudioProvider):
    capability = SPEECH

    @abc.abstractmethod
    def synthesize(self, request):
        """request: SpeechRequest -> SpeechResult"""


class AgentProvider(AudioProvider):
    capability = AGENT

    @abc.abstractmethod
    def create_agent(self, request):
        """-> AgentDefinition (provider side)"""

    @abc.abstractmethod
    def update_agent(self, request):
        """-> AgentDefinition"""

    @abc.abstractmethod
    def create_session(self, request):
        """-> ConversationSession"""

    @abc.abstractmethod
    def get_conversation(self, provider_conversation_id):
        """-> ProviderConversation"""

    def verify_webhook(self, raw_body, headers, secret):
        """Return True only when the signature checks out. Default is False:
        an adapter that has not implemented verification must not be able to
        wave events through."""
        return False


class DubbingProvider(AudioProvider):
    capability = DUBBING

    @abc.abstractmethod
    def create_project(self, request):
        pass

    @abc.abstractmethod
    def status(self, provider_job_id):
        pass

    @abc.abstractmethod
    def download(self, provider_job_id, language_code):
        pass


class MusicProvider(AudioProvider):
    capability = MUSIC

    @abc.abstractmethod
    def generate(self, request):
        pass

    def upload_owned(self, request):
        raise ProviderRefusal("This provider cannot take uploaded audio.",
                              "unsupported")

    def inpaint(self, request):
        raise ProviderRefusal("This provider cannot inpaint.", "unsupported")

    def composition_plan(self, request):
        raise ProviderRefusal("This provider cannot extract a composition plan.",
                              "unsupported")


class StemProvider(AudioProvider):
    capability = STEMS

    @abc.abstractmethod
    def separate(self, request):
        pass


class VoiceIsolationProvider(AudioProvider):
    capability = VOICE_ISOLATION

    @abc.abstractmethod
    def isolate(self, request):
        pass


class SoundEffectsProvider(AudioProvider):
    capability = SOUND_EFFECTS

    @abc.abstractmethod
    def generate_effect(self, request):
        pass


class VoiceIdentityProvider(AudioProvider):
    capability = VOICE_IDENTITY

    @abc.abstractmethod
    def register_verified_voice(self, request):
        """Street Banker never holds the voice model. This records a
        reference to a voice the OWNER verified through the vendor's own
        process, plus the permission record around it."""

    @abc.abstractmethod
    def revoke(self, provider_voice_id):
        pass


# --- the registry ------------------------------------------------------------

_registry = {}
_default = {}


def register(adapter):
    """Adapters register themselves at import."""
    _registry.setdefault(adapter.capability, {})[adapter.key] = adapter
    return adapter


def adapters_for(capability):
    return dict(_registry.get(capability, {}))


def set_default(capability, adapter_key):
    if capability not in CAPABILITIES:
        raise ValueError("unknown capability: %s" % capability)
    _default[capability] = adapter_key


def get(capability, adapter_key=None):
    """The adapter to use, or None when nothing is registered.

    Resolution: the explicit argument, then the configured default, then
    the mock. Falling back to the mock is deliberate — a missing vendor
    must degrade to something honest and offline, never to a half-real
    call. The caller can always tell which it got from health().state.
    """
    pool = _registry.get(capability) or {}
    if not pool:
        return None
    for key in (adapter_key, _default.get(capability), "mock"):
        if key and key in pool:
            return pool[key]
    return None


def health_report():
    """Every registered adapter, for the admin page."""
    out = []
    for cap in CAPABILITIES:
        for key, adapter in sorted((_registry.get(cap) or {}).items()):
            h = adapter.health()
            row = h.as_dict()
            row.update({"capability": cap, "adapter": key,
                        "label": CAPABILITY_LABELS.get(cap, cap),
                        "is_default": _default.get(cap, "mock") == key})
            out.append(row)
    return out


# --- request/result shapes ---------------------------------------------------
# Plain dicts would work, but named fields keep the adapters honest about
# what they are given and stop a caller quietly dropping consent context.

class TranscriptionRequest(object):
    def __init__(self, audio_path=None, audio_url=None, language=None,
                 diarize=True, timestamps=True, keyterms=None,
                 detect_entities=False, zero_retention=False, partner_id=None):
        self.audio_path = audio_path
        self.audio_url = audio_url
        self.language = language          # None = ask the provider to detect
        self.diarize = diarize
        self.timestamps = timestamps
        self.keyterms = list(keyterms or [])
        self.detect_entities = detect_entities
        self.zero_retention = zero_retention
        self.partner_id = partner_id


class SpeechRequest(object):
    def __init__(self, text, voice_id=None, model=None, language=None,
                 zero_retention=False, partner_id=None):
        self.text = text
        self.voice_id = voice_id
        self.model = model
        self.language = language
        self.zero_retention = zero_retention
        self.partner_id = partner_id


def bootstrap():
    """Import the adapter modules so they register themselves.

    Explicit, and called once from create_app. Adapters cannot be imported
    at the top of this file - they import it - and an import buried in a
    function elsewhere is how a registry ends up empty in one process and
    full in another. Mock first, so it is the fallback even if a vendor
    module raises on import.
    """
    import audio_mock            # noqa: F401  registers the offline adapters
    try:
        import audio_elevenlabs  # noqa: F401  registers the vendor adapters
    except Exception:
        # A broken vendor module must not take the app down. The mock is
        # already registered, so audio degrades to offline rather than 500.
        pass
    return health_report()
