"""Street Banker Release Signal — a quick read on a record.

**Status on this deployment: no analysis provider is connected.** The
public entry point says so, in those words, and does not accept an
upload. The brief for this feature is explicit that a scan must never be
faked when nothing is behind it, and a form that takes a file and returns
invented genres would be exactly that.

What is built here is the part that survives whichever provider is
eventually chosen: a neutral analysis interface, the shape of a result,
the artist-correction model that lets a human overrule it, and the
disabled state. Connecting a provider means writing one adapter class and
setting its credentials. Nothing above this layer knows which provider
answered, which is the point — the application must not grow a hundred
references to one vendor's field names.

Why no provider is connected yet: an audio-analysis or market-data
service is a commercial decision with terms attached. Before one goes
live we need confirmed rights to display its data commercially, to cache
it, and to derive recommendations from it, plus its retention terms. None
of that is settled, so the honest state is off.

The output vocabulary is deliberately constrained. There is no hit score,
no viral probability, no industry approval and no algorithm score,
because none of those can be honestly produced. What a provider can
support is a description of the record and where it sits, with a
confidence band and a statement of what it could not tell.
"""
import os

# --- what a read is allowed to say ----------------------------------------
# Six outputs, in the order the public quick scan shows them.
OUTPUTS = [
    ("genre_direction", "Genre direction",
     "Where the record sits stylistically, in the words an editor would use."),
    ("mood_energy", "Mood and energy",
     "Tempo feel, intensity and register — how the record carries."),
    ("sonic_references", "Sonic references",
     "Records this one shares production language with."),
    ("audience_adjacency", "Audience adjacency",
     "Listeners who already listen to something structurally near this."),
    ("creative_direction", "Creative direction",
     "What the sound suggests for artwork, campaign and positioning."),
    ("next_moves", "Recommended next moves",
     "The two or three things worth doing with this record first."),
]

# Three comparison axes, kept apart on purpose. Collapsing them into one
# "similar artists" list is how an artist ends up positioned against
# someone they sound nothing like, because a shared audience and a shared
# production style are different claims.
COMPARISON_AXES = [
    ("sounds_like", "Sounds like",
     "Shares production language, arrangement or vocal placement."),
    ("shares_audience", "Shares an audience with",
     "Different sound, overlapping listeners."),
    ("market_near", "Sits in the market near",
     "Released into a comparable commercial position."),
]

# What the artist can say back. A read the artist cannot correct is a
# verdict, and the corrections are what make the result worth feeding
# into anything else.
CORRECTIONS = [
    ("accurate", "Accurate"),
    ("inaccurate", "Inaccurate"),
    ("do_not_use", "Do not use this comparison"),
    ("preferred_market", "Preferred market direction"),
    ("approved_signal", "Approved creative signal"),
]

# Confidence is a band with a reason, never a percentage. "97.8% accurate"
# is a number nobody can defend.
CONFIDENCE_BANDS = [
    ("clear", "Clear read", "Consistent signals across the whole track."),
    ("mixed", "Mixed read", "The track changes character; treat as two reads."),
    ("thin", "Thin read", "Short, sparse or heavily processed — less to go on."),
]

LIMITS = [
    "A read of the recording, not of the song's potential.",
    "It cannot hear a lyric's meaning, a scene, or a moment.",
    "It does not know your history, your audience or your plans.",
    "Comparisons are structural. They are not endorsements and they are "
    "not predictions.",
]


class AnalysisProvider(object):
    """The interface every provider adapter implements.

    Deliberately small. Anything a specific vendor does beyond this stays
    inside its own adapter, so swapping vendors is one file.
    """

    name = "unnamed"

    def configured(self):
        """True only when this provider can actually answer."""
        raise NotImplementedError

    def analyze(self, audio_ref):
        """Return a result dict, or raise. Never called when not configured."""
        raise NotImplementedError


class NullProvider(AnalysisProvider):
    """The provider in use when none is connected.

    It refuses rather than inventing. Every caller has to handle this,
    which is what stops a fabricated read reaching a page.
    """

    name = "none"

    def configured(self):
        return False

    def analyze(self, audio_ref):
        raise RuntimeError(
            "No analysis provider is connected. Release Signal must not "
            "produce a result without one.")


class ChartmetricAdapter(AnalysisProvider):
    """Market-data adapter. Not enabled.

    Written as an adapter rather than as calls scattered through the
    application so that choosing a different data partner later does not
    mean touching the homepage, the Artist Twin and the tour.

    Before this may be switched on, four things need confirming and none
    of them is a code change: credentials, the right to display the data
    commercially, the right to cache it and to derive recommendations
    from it, and the retention terms.
    """

    name = "chartmetric"

    def configured(self):
        return bool(os.environ.get("CHARTMETRIC_TOKEN")
                    and os.environ.get("CHARTMETRIC_RIGHTS_CONFIRMED"))

    def analyze(self, audio_ref):
        raise NotImplementedError(
            "Chartmetric adapter is a stub. Commercial display, caching and "
            "derived-recommendation rights are unconfirmed.")


_PROVIDERS = [ChartmetricAdapter(), NullProvider()]


def active_provider():
    """The first provider that can actually answer. NullProvider always can't."""
    for provider in _PROVIDERS:
        if provider.configured():
            return provider
    return _PROVIDERS[-1]


def enabled():
    return active_provider().configured()


def status_key():
    """Which capability status the public surfaces should show."""
    return "release_signal"


def get_release_signal_config():
    return {
        "name": "Street Banker Release Signal",
        "headline": "Let Street Banker hear the record.",
        "support": ("Upload a track or paste a private link for a quick read "
                    "on its sound, positioning, creative direction, and "
                    "strongest next moves."),
        "outputs": OUTPUTS,
        "axes": COMPARISON_AXES,
        "corrections": CORRECTIONS,
        "confidence_bands": CONFIDENCE_BANDS,
        "limits": LIMITS,
        "enabled": enabled(),
        "provider": active_provider().name,
        "disabled_reason": (
            "No analysis provider is connected yet, so Release Signal cannot "
            "read a track on this deployment. The interface below is what it "
            "will do — we would rather show you that than take an upload and "
            "invent an answer."),
    }
