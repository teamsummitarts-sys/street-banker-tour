"""Street Banker Audio Intelligence - the gate.

Nothing reaches a provider without passing through gate(). It is one
function on purpose: ten separate checks scattered across ten call sites is
how a repo ends up with nine of them applied.

THE TEN CHECKS, IN THIS ORDER
-----------------------------
 1. global feature flag        - is this capability on at all
 2. tenant entitlement         - does this partner's plan include it
 3. tenant toggle              - has this partner switched it off
 4. provider entitlement       - is an adapter registered and healthy
 5. user permission            - does this seat hold the capability
 6. usage limit                - is there budget left
 7. consent                    - recording/disclosure consent on file
 8. rights confirmation        - ownership asserted where audio is processed
 9. retention configuration    - can the policy actually be honoured
10. provider health            - is the adapter able to work right now

Order matters. The cheap, certain refusals come first so an unentitled
request never costs a database round trip to the usage ledger, and the
provider is asked last because it is the only check that can be slow.

WHY IT RETURNS A DECISION RATHER THAN RAISING
---------------------------------------------
A refusal is something a person reads. Each one carries a code the UI can
branch on and a sentence that says what would make it pass, because "403"
tells an artist nothing about the consent box they did not tick.

THE ZERO-RETENTION RULE
-----------------------
If a partner requires zero retention and the adapter cannot prove it
supports it for this account, the answer is no. Not a downgrade, not a
warning, not a job that runs anyway with a flag set. Telling somebody
their audio was never stored when it was is the one mistake here with no
remedy.
"""
import os

import audio_providers as ap
import audio_store as astore
import partner_store as pstore


# --- feature flags -----------------------------------------------------------
# Server-side only. A flag that is not set is OFF, so a deployment gets the
# new surface deliberately rather than by upgrading.
FLAGS = (
    "AUDIO_INTELLIGENCE_ENABLED", "ELEVENLABS_ENABLED",
    "MEETING_INTELLIGENCE_ENABLED", "SIGNAL_AUDIO_BRIEFS_ENABLED",
    "AUDIO_OPERATOR_ENABLED", "GLOBAL_RELEASE_PACK_ENABLED",
    "CAMPAIGN_AUDIO_TOOLKIT_ENABLED", "REMIX_LAB_AUDIO_ENGINE_ENABLED",
    "ARTIST_VOICE_VAULT_ENABLED", "WHITE_LABEL_AUDIO_OPERATOR_ENABLED",
    "DUBBING_ENABLED", "MUSIC_GENERATION_ENABLED", "MUSIC_INPAINTING_ENABLED",
    "STEM_SEPARATION_ENABLED", "VOICE_ISOLATION_ENABLED", "SOUND_EFFECTS_ENABLED",
    "VOICE_CLONING_ENABLED", "ZERO_RETENTION_REQUIRED",
)

_TRUE = ("1", "true", "yes", "on")


def flag(name):
    return (os.environ.get(name) or "").strip().lower() in _TRUE


# Which flag, capability, entitlement and policy key each feature needs.
# One table so a new feature cannot be added without saying what governs it.
FEATURES = {
    "meeting_intelligence": {
        "flag": "MEETING_INTELLIGENCE_ENABLED", "capability": ap.TRANSCRIPTION,
        "cap": "audio.meeting_intelligence", "policy": "allow_transcription",
        "consent": None, "rights": False,
    },
    "meeting_recording": {
        "flag": "MEETING_INTELLIGENCE_ENABLED", "capability": ap.TRANSCRIPTION,
        "cap": "audio.meeting_recording", "policy": "allow_meeting_recording",
        "consent": "recording", "rights": False,
    },
    "transcription": {
        "flag": "AUDIO_INTELLIGENCE_ENABLED", "capability": ap.TRANSCRIPTION,
        "cap": "audio.transcription", "policy": "allow_transcription",
        "consent": None, "rights": False,
    },
    "signal_briefs": {
        "flag": "SIGNAL_AUDIO_BRIEFS_ENABLED", "capability": ap.SPEECH,
        "cap": "audio.signal_briefs", "policy": "allow_voice_generation",
        "consent": None, "rights": False,
    },
    "operator_agent": {
        "flag": "AUDIO_OPERATOR_ENABLED", "capability": ap.AGENT,
        "cap": "audio.operator_agent", "policy": None,
        "consent": "agent_disclosure", "rights": False,
    },
    "dubbing": {
        "flag": "DUBBING_ENABLED", "capability": ap.DUBBING,
        "cap": "audio.dubbing", "policy": "allow_dubbing",
        "consent": None, "rights": True,
    },
    "campaign_voiceover": {
        "flag": "CAMPAIGN_AUDIO_TOOLKIT_ENABLED", "capability": ap.SPEECH,
        "cap": "audio.campaign_voiceover", "policy": "allow_voice_generation",
        "consent": None, "rights": False,
    },
    "sound_effects": {
        "flag": "SOUND_EFFECTS_ENABLED", "capability": ap.SOUND_EFFECTS,
        "cap": "audio.sound_effects", "policy": None,
        "consent": None, "rights": False,
    },
    "voice_isolation": {
        "flag": "VOICE_ISOLATION_ENABLED", "capability": ap.VOICE_ISOLATION,
        "cap": "audio.voice_isolation", "policy": None,
        "consent": None, "rights": True,
    },
    "stem_separation": {
        "flag": "STEM_SEPARATION_ENABLED", "capability": ap.STEMS,
        "cap": "audio.stem_separation", "policy": None,
        "consent": None, "rights": True,
    },
    "music_generation": {
        "flag": "MUSIC_GENERATION_ENABLED", "capability": ap.MUSIC,
        "cap": "audio.music_generation", "policy": "allow_music_generation",
        "consent": None, "rights": True,
    },
    # The Remix Lab engine. This is what REMIX_LAB_AUDIO_ENGINE_ENABLED was
    # declared for and never wired to - it sat in FLAGS gating nothing, so an
    # operator could set it and watch nothing happen.
    #
    # It reads a track and reports what is measurable in it: tempo, section
    # boundaries, an energy curve. It generates NOTHING, which is why it is
    # separate from music_generation and why an artist can run it without
    # switching generation on.
    "remix_plan": {
        "flag": "REMIX_LAB_AUDIO_ENGINE_ENABLED", "capability": ap.MUSIC,
        "cap": "audio.remix_lab", "policy": None,
        "consent": None, "rights": True,
    },
    "music_inpainting": {
        "flag": "MUSIC_INPAINTING_ENABLED", "capability": ap.MUSIC,
        "cap": "audio.music_inpainting", "policy": "allow_music_generation",
        "consent": None, "rights": True,
    },
    "voice_vault": {
        "flag": "ARTIST_VOICE_VAULT_ENABLED", "capability": ap.VOICE_IDENTITY,
        "cap": "audio.voice_vault", "policy": "allow_voice_cloning",
        "consent": "voice_owner", "rights": False,
    },
}


class Decision(object):
    """Allowed, or refused with a reason a person can act on."""

    def __init__(self, allowed, code="ok", reason="", adapter=None, feature=None):
        self.allowed = bool(allowed)
        self.code = code
        self.reason = reason
        self.adapter = adapter
        self.feature = feature

    def __bool__(self):
        return self.allowed

    __nonzero__ = __bool__

    def as_dict(self):
        return {"allowed": self.allowed, "code": self.code, "reason": self.reason,
                "feature": self.feature,
                "adapter": getattr(self.adapter, "key", None)}


def _no(code, reason, feature):
    return Decision(False, code, reason, None, feature)


def gate(feature, partner_id=None, member=None, subject_id="",
         rights_confirmed=False, budget_check=None, adapter_key=None):
    """The single door. Returns a Decision; never raises for a refusal.

    member is a Partner OS member row, or None for a direct Street Banker
    account, which is treated as holding every capability of its own tenant
    (there is no partner above it to grant them).
    """
    spec = FEATURES.get(feature)
    if spec is None:
        return _no("unknown_feature", "That feature does not exist.", feature)

    # 1. global flag - the umbrella first, then the feature's own
    if not flag("AUDIO_INTELLIGENCE_ENABLED"):
        return _no("disabled", "Audio Intelligence is switched off on this deployment.", feature)
    if not flag(spec["flag"]):
        return _no("disabled", "This audio feature is switched off on this deployment.", feature)

    policy = astore.get_policy(partner_id)

    # 2 & 5. entitlement and seat permission. A direct account answers to
    # itself; a partner seat answers to the role it was given.
    if member is not None:
        if not pstore.can(member, "view"):
            return _no("no_seat", "This account does not hold a seat here.", feature)
        # Audio capabilities ride the partner's plan. Until plans carry them
        # explicitly, owner and admin hold them and other roles do not - a
        # conservative default that cannot leak a capability nobody bought.
        if member.get("role") not in ("owner", "admin", "manager"):
            return _no("not_entitled",
                       "Your role does not include audio features. An owner or "
                       "admin at this organisation can grant them.", feature)

    # 3. tenant toggle
    pkey = spec.get("policy")
    if pkey and not policy.get(pkey, False):
        return _no("policy_off",
                   "Your organisation's audio policy does not allow this. An "
                   "owner can change it in Settings, Audio.", feature)

    # 4. provider entitlement
    adapter = ap.get(spec["capability"], adapter_key)
    if adapter is None:
        return _no("no_provider",
                   "No provider is configured for %s."
                   % ap.CAPABILITY_LABELS.get(spec["capability"], spec["capability"]),
                   feature)

    # 6. usage limit - supplied by the caller, because budget lives with
    #    billing, not here. None means "not checked", not "unlimited".
    if budget_check is not None and not budget_check:
        return _no("over_budget",
                   "This would exceed the audio budget for the period.", feature)

    # 7. consent
    ctype = spec.get("consent")
    if ctype == "recording" and policy.get("require_recording_consent", True):
        if not astore.has_consent(partner_id, "recording", subject_id):
            return _no("consent_required",
                       "Recording consent has not been recorded for this session.",
                       feature)
    if ctype == "agent_disclosure" and policy.get("require_agent_disclosure", True):
        if not astore.has_consent(partner_id, "agent_disclosure", subject_id):
            return _no("disclosure_required",
                       "The AI disclosure has not been acknowledged.", feature)
    if ctype == "voice_owner":
        if not astore.has_consent(partner_id, "voice_owner", subject_id):
            return _no("owner_consent_required",
                       "The voice owner has not completed verification and consent. "
                       "A voice can only be registered by the person whose voice it is.",
                       feature)

    # 8. rights
    if spec.get("rights") and policy.get("require_rights_confirmation", True):
        if not rights_confirmed:
            return _no("rights_required",
                       "Confirm you own or control this audio, or have the rights "
                       "holder's authorisation, before it is processed.", feature)

    # 9. retention - the rule with no remedy if it is got wrong
    if policy.get("require_zero_retention"):
        if not adapter.supports_zero_retention():
            return _no("zero_retention_unavailable",
                       "Your organisation requires zero-retention processing and "
                       "the configured provider has not verified support for it on "
                       "this account. The job was not sent and no audio left "
                       "Street Banker.", feature)

    # 10. provider health, last because it is the only slow one
    h = adapter.health()
    if not h.ok:
        return _no("provider_unavailable",
                   "The audio provider is not available right now (%s)." % h.state,
                   feature)

    return Decision(True, "ok", "", adapter, feature)


def zero_retention_claimable(partner_id, capability, adapter_key=None):
    """Whether a job may be LABELLED zero retention. Never infer this from
    the policy asking for it - only the adapter can answer."""
    a = ap.get(capability, adapter_key)
    return bool(a and a.supports_zero_retention())
