"""Remix Lab — one release into more moments, rights-safe.

A professional music-business tool, not a novelty AI toy: remix briefs,
social edit concepts, DJ edit directions and producer-ready concepts for
artists who own or control their audio.

Two rules govern everything here:

  1. Rights first. Uploads require an ownership confirmation and a
     no-likeness confirmation before the button so much as enables, and
     reference text is screened for imitation requests - no "sound
     like", no voice cloning, no protected-style copying. The screen
     runs in the browser AND must run again server-side when generation
     is wired up; the pattern list below is the single source for both.

  2. No faking. Whether generation is connected is now a FACT about the
     deployment, read from engine_live(), and every claim on the page is
     conditional on it: the hero chip, the note by the form, the note on
     the example panel, and capability_status. When it is off the page
     says so and the results panel is a worked example labelled EXAMPLE
     OUTPUT; when it is on the page says what is actually measured. The
     "worth making" read stays bands describing fit and effort in both
     states - it predicts no streams, no placement and no revenue.

No real artist, producer or celebrity is named anywhere in this file,
including in the examples of what not to do.
"""
import re

TITLE = "Remix Lab"
EYEBROW = "Remix Lab"
SUBHEAD = "More versions. More moments. More ways to move the record."
BODY = ("Remix Lab helps artists transform owned audio into remix briefs, "
        "social edits, DJ versions, and producer-ready concepts while "
        "keeping rights, likeness, and catalog protection at the center.")

HERO_HEADLINE = ["Turn One Release", "Into More Moments."]
HERO_SUBLINE = ("Upload a track you own or control. Remix Lab helps generate "
                "remix briefs, social edit concepts, DJ version ideas, and "
                "producer-ready directions without copying another artist's "
                "voice, likeness, or protected style.")
PRIMARY_CTA = {"label": "Start Remix Brief", "href": "#brief"}
SECONDARY_CTA = {"label": "How Rights Protection Works", "href": "#rights"}

# Preview truth, stated where the form is.
PREVIEW_NOTE = ("Preview build. Nothing you choose here is uploaded or "
                "stored, and generation is not yet connected — the output "
                "below is a worked example of what a Remix Lab brief looks "
                "like.")

# When the engine IS wired, the note has to stop saying it is not. It also has
# to be honest about what the engine actually does: it MEASURES the track -
# tempo, section boundaries, an energy curve - and composes a brief from those
# facts plus the choices made on this page. It does not listen to the record
# and form an opinion about it, and no wording here should suggest it does.
LIVE_NOTE = ("Your track is read for tempo, section boundaries and an energy "
             "curve, and the brief is built from those measurements plus the "
             "choices you make below. Every line says where it came from. "
             "The audio is stored privately and destroyed on your retention "
             "schedule.")

FEATURES = [
    ("Remix Briefs", "Turn a track into clear creative directions for "
                     "producers, DJs, editors, and rollout teams."),
    ("Social Edits", "Generate hook-first ideas for TikTok, Reels, Shorts, "
                     "fan drops, and creator campaigns."),
    ("DJ + Club Versions", "Create structured directions for intros, outros, "
                           "tempo shifts, and performance-ready edits."),
    ("Rights-Safe Workflow", "Built around owned audio, authorization "
                             "checks, and no voice/likeness imitation."),
    ("Producer Handoff", "Move the best idea from AI-assisted concept to "
                         "human review and release-ready execution."),
    ("Release Strategy", "Connect remix concepts to fan capture, creator "
                         "rollout, and revenue-layer planning."),
]

# --- the rights gate -------------------------------------------------------
RIGHTS_CHECKBOX = ("I confirm that I own or control the audio I am "
                   "uploading, or have authorization from the rights holder "
                   "to use it for remix concept generation.")
LIKENESS_CHECKBOX = ("I understand Remix Lab will not generate outputs using "
                     "another artist's name, voice, likeness, or protected "
                     "style.")

UPLOAD_FORMATS = [".wav", ".mp3", ".aiff", ".flac"]
UPLOAD_MAX_MB = 250

STEM_OPTIONS = ["Vocal", "Instrumental", "Drums", "Bass", "Other"]

REFERENCE_HELPER = ("Use references for broad creative direction only. Do "
                    "not request imitation of a real artist, voice, "
                    "likeness, or protected style.")
REFERENCE_MIN, REFERENCE_MAX = 2, 5

REMIX_LANES = [
    "Club / DJ Edit", "Short-Form Social Edit", "Acoustic / Stripped Version",
    "Dance / House Direction", "Afro / Global Rhythm Direction",
    "Latin / Percussion Direction", "Cinematic / Sync Direction",
    "Radio / Clean Edit", "Fan Drop / Exclusive Version",
    "Producer Handoff Brief",
]

TARGET_USES = [
    "TikTok / Reels / Shorts", "DSP alternate version", "DJ pack",
    "Live show intro", "Sync pitch", "Fan community drop", "Brand campaign",
    "Internal creative exploration",
]

VIBE_CONTROLS = [
    ("energy", "Energy", ["Low", "Medium", "High"]),
    ("tempoDirection", "Tempo direction", ["Slower", "Same", "Faster"]),
    ("vocalTreatment", "Vocal treatment",
     ["Natural", "Chopped", "Sparse", "Hook-first"]),
    ("instrumentation", "Instrumentation", ["Minimal", "Balanced", "Full"]),
    ("riskLevel", "Risk level", ["Conservative", "Exploratory", "Aggressive"]),
]

# --- the likeness screen ---------------------------------------------------
# One list, used by the browser now and by the server when generation is
# wired. Regex rather than bare substrings so "sound like" also catches
# "sounds like" without a second entry.
BANNED_PATTERNS = [
    r"\bsounds?\s+like\b",
    r"\bin\s+the\s+style\s+of\b",
    r"\bmake\s+it\s+like\b",
    r"\buse\s+\S{1,40}(?:'s)?\s+voice\b",
    r"\bclone\s+(?:a\s+|the\s+)?voice\b",
    r"\bvoice\s+clon(?:e|ing)\b",
    r"\bdeep\s*fake\b",
    r"\bai\s+cover\b",
    r"\bimpersonat\w*\b",
    r"\bcopy\s+the\s+vocals?\b",
    r"\bsame\s+flow\s+as\b",
    r"\bsame\s+voice\s+as\b",
    # "<somebody> type beat" is the native idiom for this request in music,
    # and leaving it out screened the wording rather than the ask: naming an
    # artist after "in the style of" was refused, while the same artist
    # before "type beat" - the way somebody in this industry actually types
    # it - went straight through.
    #
    # It also catches genre uses like "trap type beat". That is deliberate and
    # consistent with the entry above it, which refuses "in the style of"
    # whatever follows. The warning says what to write instead, and
    # "trap-influenced, 140 bpm, sparse hi-hats" is a better brief anyway.
    r"\b[\w'-]+\s+type\s+beat\b",
]
_BANNED = [re.compile(p, re.IGNORECASE) for p in BANNED_PATTERNS]

SAFETY_WARNING = ("Remix Lab can't imitate a real person's voice, likeness, "
                  "or protected style. Try describing the musical direction "
                  "instead: tempo, energy, instrumentation, era, mood, or "
                  "use case.")

# Allowed replacements — musical descriptors, no real names.
ALLOWED_EXAMPLES = [
    "High-energy club version with faster drums and a hook-first intro.",
    "Warm acoustic version with sparse percussion and intimate vocals.",
    "Percussion-heavy global rhythm direction with clean DJ intro/outro.",
    "Cinematic version for trailer or sync pitch.",
]


def engine_live():
    """Is the Remix Lab engine actually available on this deployment?

    Both flags, because audio_policy.gate() checks both and a page that
    offered a real button the gate would refuse is worse than one that
    honestly says it is a preview.

    Imported lazily: this module is pure configuration and is read by tests
    that have no app around them.
    """
    try:
        import audio_policy
    except Exception:
        return False
    return (audio_policy.flag("AUDIO_INTELLIGENCE_ENABLED")
            and audio_policy.flag("REMIX_LAB_AUDIO_ENGINE_ENABLED"))


def check_reference_text(text):
    """The pattern that makes a reference an imitation request, or None.

    The browser runs the same list for the inline warning; this is the
    authoritative copy the server must call before any generation
    request leaves the building.
    """
    for pattern in _BANNED:
        match = pattern.search(text or "")
        if match:
            return match.group(0)
    return None


# --- the worked example ----------------------------------------------------
# Everything below renders inside a panel labelled EXAMPLE OUTPUT. It is
# nobody's track and no figure in it is a measurement.
EXAMPLE_TAG = "Example output"
EXAMPLE_NOTE = ("A worked example of what a Remix Lab brief looks like — "
                "not generated from your track. Generation is not yet "
                "connected on this deployment.")

# The same sentence, for a deployment where generation IS connected. The panel
# is still a worked example and still says so - what changes is the reason it
# is an example. Left as one unconditional string, this claimed "generation is
# not yet connected" on a deployment where it was, which is the exact class of
# stale claim the rest of this file exists to avoid.
EXAMPLE_NOTE_LIVE = ("A worked example of what a Remix Lab brief looks like — "
                     "not generated from your track. Run one above and your "
                     "own brief comes back with every line marked as measured, "
                     "convention, or your own choice.")

EXAMPLE_BRIEF = [
    ("BPM / key notes", "Original sits around 92 BPM in A minor. The club "
                        "lane reads best lifted to 122–126; keep the hook "
                        "melody inside one octave so the pitch shift stays "
                        "clean."),
    ("Strongest direction", "Club / DJ edit. The pre-chorus already builds "
                            "like a riser and the hook lands on the one — "
                            "the record wants a four-on-the-floor read."),
    ("Arrangement suggestion", "16-bar DJ intro on drums and bass, first "
                               "hook at 0:45, strip verse two to half "
                               "instrumentation, double the final hook with "
                               "the full kit back in."),
    ("Audience / use case", "Club sets and a DJ pack first; the same edit "
                            "trims to a 30-second hook-first cut for "
                            "short-form."),
    ("What to avoid", "Do not bury the lead vocal under a new topline, and "
                      "keep the bridge — it is the most distinctive section "
                      "and the cheapest moment of contrast you have."),
]

EXAMPLE_SOCIAL = [
    {"name": "Hook First",
     "hook": "Open on the hook at 0:45 — the strongest eight bars.",
     "opening": "First 3 seconds: cold vocal, no drums, one line of text on "
                "screen.",
     "caption": "Ask a question the hook answers; keep it under ten words.",
     "cta": "Point to the pre-save or fan-capture link, not just the "
            "profile."},
    {"name": "Build & Drop",
     "hook": "Use the pre-chorus rise into the first hook, 0:36–0:52.",
     "opening": "First 3 seconds: the riser already in motion — never from "
                "silence.",
     "caption": "Caption names the moment: what drops when the beat does.",
     "cta": "Invite duets/stitches on the drop moment."},
    {"name": "Stripped Verse",
     "hook": "Verse two over the acoustic pass — contrast is the hook.",
     "opening": "First 3 seconds: a lyric on screen before any audio "
                "resolves.",
     "caption": "Lead with the lyric, credit the writers.",
     "cta": "Route to the alternate-version pre-save."},
]

EXAMPLE_PRODUCER = [
    {"lane": "Club / DJ Edit",
     "drums": "Four-on-the-floor at 124, claps layered on 2 and 4, 16-bar "
              "mixable intro and outro.",
     "instrumentation": "Keep the original bass line as the anchor; replace "
                        "pads with a tighter stab pattern.",
     "vocal": "Full lead through the hooks, chopped fills through the "
              "verses.",
     "release": "DJ pack plus a DSP alternate version."},
    {"lane": "Acoustic / Stripped",
     "drums": "Brushes or light percussion only; let the room breathe.",
     "instrumentation": "One guitar or keys carrying the harmony, bass in "
                        "only for the final hook.",
     "vocal": "Natural, dry, up-front — intimacy is the point.",
     "release": "Fan drop or exclusive version; strong sync candidate."},
    {"lane": "Cinematic / Sync",
     "drums": "Sparse hits, big space; no loops.",
     "instrumentation": "Strings or sustained keys under the existing "
                        "chords, build to one clear peak.",
     "vocal": "Sparse — hook only, entering late.",
     "release": "Sync pitch first; internal exploration for a trailer "
                "cut."},
]

EXAMPLE_READINESS = [
    "Splits confirmed", "Stems available", "Clean artwork ready",
    "Rights risk reviewed", "Creator plan attached",
    "DJ intro/outro needed", "Fan capture destination ready",
]

# Bands, not scores. Fit and effort on THIS example - never a prediction
# of streams, placement or revenue, and the page says so beside it.
EXAMPLE_WORTH = [
    ("Commercial potential", "Promising"),
    ("Social potential", "Strong"),
    ("DJ utility", "Strong"),
    ("Sync potential", "Moderate"),
    ("Rights risk", "Low — owned master assumed"),
    ("Production lift", "Medium"),
]
WORTH_NOTE = ("Bands describe fit and effort on this worked example. They "
              "predict no streams, no placement, and no revenue.")

# --- producer handoff ------------------------------------------------------
PRODUCER_CARD = {
    "title": "Producer Review Available",
    "body": ("Send the strongest concept to a Street Banker "
             "producer/operator for human review, refinement, and "
             "release-readiness feedback."),
    "cta": {"label": "Request Producer Review", "href": "/contact"},
}

# --- the rights section ----------------------------------------------------
RIGHTS_POINTS = [
    ("Owned audio only", "Upload only audio you own, control, or are "
                         "authorized by the rights holder to use. Both "
                         "confirmations above the upload are required, and "
                         "the button stays off until they are made."),
    ("No likeness imitation", "No name, image, likeness, voice, or style "
                              "imitation of real artists, producers, or "
                              "public figures. No voice cloning. No "
                              "unauthorized interpolation, covers, or "
                              "derivative use."),
    ("References are directional", "Reference tracks and descriptions steer "
                                   "tempo range, energy, instrumentation, "
                                   "structure, audience, or use case — "
                                   "never imitation of a person."),
    ("Screened both ways", "Imitation requests are caught as you type and "
                           "will be screened again server-side before any "
                           "generation runs."),
]


def get_remix_lab_config():
    return {
        "title": TITLE,
        "eyebrow": EYEBROW,
        "subhead": SUBHEAD,
        "body": BODY,
        "hero_headline": HERO_HEADLINE,
        "hero_subline": HERO_SUBLINE,
        "primary_cta": PRIMARY_CTA,
        "secondary_cta": SECONDARY_CTA,
        "preview_note": LIVE_NOTE if engine_live() else PREVIEW_NOTE,
        "features": FEATURES,
        "rights_checkbox": RIGHTS_CHECKBOX,
        "likeness_checkbox": LIKENESS_CHECKBOX,
        "upload_formats": UPLOAD_FORMATS,
        "upload_max_mb": UPLOAD_MAX_MB,
        "stem_options": STEM_OPTIONS,
        "reference_helper": REFERENCE_HELPER,
        "reference_min": REFERENCE_MIN,
        "reference_max": REFERENCE_MAX,
        "remix_lanes": REMIX_LANES,
        "target_uses": TARGET_USES,
        "vibe_controls": VIBE_CONTROLS,
        "safety_warning": SAFETY_WARNING,
        "allowed_examples": ALLOWED_EXAMPLES,
        "example_tag": EXAMPLE_TAG,
        "example_note": EXAMPLE_NOTE_LIVE if engine_live() else EXAMPLE_NOTE,
        # Whether generation is actually wired on THIS deployment. The
        # page has always said it was not; now that can be true or false,
        # and it must be read from the gate rather than assumed either way.
        "engine_live": engine_live(),
        "example_brief": EXAMPLE_BRIEF,
        "example_social": EXAMPLE_SOCIAL,
        "example_producer": EXAMPLE_PRODUCER,
        "example_readiness": EXAMPLE_READINESS,
        "example_worth": EXAMPLE_WORTH,
        "worth_note": WORTH_NOTE,
        "producer_card": PRODUCER_CARD,
        "rights_points": RIGHTS_POINTS,
    }


def get_remix_lab_client_config():
    """What the browser needs, and nothing else."""
    return {
        "patterns": BANNED_PATTERNS,
        "warning": SAFETY_WARNING,
        "max_mb": UPLOAD_MAX_MB,
        "formats": UPLOAD_FORMATS,
        "reference_max": REFERENCE_MAX,
        # The script must know this. With the engine live the form posts to
        # the server, and the submit handler has to STOP calling
        # preventDefault - otherwise the action attribute is decoration and
        # the form never reaches the route.
        "engineLive": engine_live(),
    }
