"""Remix Lab - turning a measured track plus the artist's choices into a brief.

WHAT CHANGED, AND WHY THIS FILE EXISTS NOW
------------------------------------------
The page shipped saying generation was not connected, and it was right to.
A remix brief that opens "original sits around 92 BPM in A minor" needs
somebody to have actually listened to the record, and inventing that number
would be the most damaging kind of fake here: a producer would act on it.

The audio seam can now measure part of it. A MusicProvider exposes
composition_plan(), which reports tempo, section boundaries and an energy
curve for a track the artist owns. That is a measurement, not an opinion.

So a brief is composed from exactly two honest sources:

  MEASURED   tempo, section boundaries, energy - from the provider's plan
  CHOSEN     lane, target use, energy, tempo direction, vocal treatment,
             instrumentation, risk - from the artist's own selections

and a third that is labelled every time it is used:

  CONVENTION what a club edit or a sync cut usually sits at. Stated as a
             convention out loud, because it is one - it is not a reading
             of this record.

WHAT IT STILL WILL NOT SAY
--------------------------
"The pre-chorus already builds like a riser and the hook lands on the one."
That is musical judgement about a specific record and nothing here can make
it. No key detection either: the plan does not carry a key, and guessing one
would send a producer to the wrong pitch shift.

The brief says what it knows, says where each part came from, and stops.
"""

# Lane -> what that kind of edit conventionally sits at, and how it is
# usually arranged. Conventions, and the composed brief says so.
LANE_CONVENTIONS = {
    "Club / DJ Edit": {
        "bpm": (122, 126),
        "arrangement": "a 16-bar mixable intro on drums and bass, the first "
                       "hook early, and a 16-bar outro that a DJ can ride out",
        "avoid": "burying the lead vocal under a new topline",
    },
    "Short-Form Social Edit": {
        "bpm": None,
        "arrangement": "the strongest hook inside the first three seconds, "
                       "and a cut that stands alone without the verse before it",
        "avoid": "opening from silence - short-form starts already moving",
    },
    "Acoustic / Stripped Version": {
        "bpm": None,
        "arrangement": "one instrument carrying the harmony, percussion light "
                       "or absent, and the vocal dry and forward",
        "avoid": "adding production back in for the final hook out of habit",
    },
    "Dance / House Direction": {
        "bpm": (120, 128),
        "arrangement": "a four-on-the-floor bed, a long build, and one clear peak",
        "avoid": "a drop that arrives before the listener has been made to wait",
    },
    "Afro / Global Rhythm Direction": {
        "bpm": (98, 112),
        "arrangement": "percussion carrying the groove rather than the kit, "
                       "with space left between parts",
        "avoid": "flattening the polyrhythm onto a straight grid",
    },
    "Latin / Percussion Direction": {
        "bpm": (95, 110),
        "arrangement": "percussion-led with the original bass kept as the anchor",
        "avoid": "treating the percussion as decoration over the old arrangement",
    },
    "Cinematic / Sync Direction": {
        "bpm": None,
        "arrangement": "sparse hits, wide space, no loops, building to a single peak",
        "avoid": "a busy mix - sync editors need room to place dialogue",
    },
    "Radio / Clean Edit": {
        "bpm": None,
        "arrangement": "the structure kept intact, trimmed toward a shorter runtime",
        "avoid": "cutting a section that the hook depends on for contrast",
    },
    "Fan Drop / Exclusive Version": {
        "bpm": None,
        "arrangement": "something the record does not already do - a different "
                       "read rather than a louder one",
        "avoid": "shipping an alternate mix and calling it a version",
    },
    "Producer Handoff Brief": {
        "bpm": None,
        "arrangement": "the sections named with timings, so somebody else can "
                       "work from it without the original session",
        "avoid": "describing a feeling where a timing would do",
    },
}

TEMPO_STEP = {"Slower": -0.12, "Same": 0.0, "Faster": 0.12}


def _mmss(ms):
    total = int((ms or 0) // 1000)
    return "%d:%02d" % (total // 60, total % 60)


def _plan_tempo(plan):
    try:
        value = int(round(float(plan.get("tempo_bpm"))))
        return value if 20 <= value <= 300 else None
    except (TypeError, ValueError):
        return None


def target_tempo(plan, lane, tempo_direction):
    """What to aim for, and why - as (text, source).

    The artist's own tempo direction wins over the lane convention, because
    they chose it deliberately and the convention is only a default.
    """
    measured = _plan_tempo(plan)
    convention = (LANE_CONVENTIONS.get(lane) or {}).get("bpm")

    if tempo_direction in ("Slower", "Faster") and measured:
        shifted = int(round(measured * (1 + TEMPO_STEP[tempo_direction])))
        return ("%d BPM measured, %s to about %d as you asked."
                % (measured, tempo_direction.lower(), shifted), "measured")

    if measured and convention:
        low, high = convention
        if low <= measured <= high:
            return ("%d BPM measured, already inside the %d-%d that this kind "
                    "of edit usually sits at." % (measured, low, high), "measured")
        return ("%d BPM measured. Edits of this kind conventionally sit at "
                "%d-%d, so this would need moving - check the hook survives "
                "the shift before committing."
                % (measured, low, high), "measured + convention")

    if measured:
        return ("%d BPM measured." % measured, "measured")
    if convention:
        return ("Tempo was not measured for this track. Edits of this kind "
                "conventionally sit at %d-%d." % convention, "convention")
    return ("Tempo was not measured for this track.", "unknown")


def structure_lines(plan):
    """The sections the provider actually found, with their timings."""
    sections = plan.get("sections") or []
    out = []
    for section in sections:
        name = (section.get("name") or "section").replace("_", " ")
        out.append("%s at %s" % (name, _mmss(section.get("start_ms"))))
    return out


def _energy_note(plan):
    energy = [e for e in (plan.get("energy") or []) if e]
    if not energy:
        return None
    if len(set(energy)) == 1:
        return ("The energy reading is flat across the whole track (%s "
                "throughout). Whatever contrast this version needs will have "
                "to be built, not found." % energy[0])
    peak = max(range(len(energy)), key=lambda i: ["low", "medium", "high"].index(energy[i])
               if energy[i] in ("low", "medium", "high") else 0)
    sections = plan.get("sections") or []
    where = ""
    if peak < len(sections):
        where = " around %s" % _mmss(sections[peak].get("start_ms"))
    return ("The energy reading peaks%s. That is the moment a short-form cut "
            "or a club drop has to be built around." % where)


def compose_brief(plan, choices, track_name=""):
    """A remix brief from measured facts and the artist's own choices.

    Returns a list of (heading, body, source) where source is one of
    "measured", "chosen", "convention" or a combination - so the page can
    show where every line came from rather than presenting all of it with
    the same authority.
    """
    plan = plan or {}
    choices = choices or {}
    lane = choices.get("lane") or "Producer Handoff Brief"
    convention = LANE_CONVENTIONS.get(lane) or {}
    out = []

    tempo_text, tempo_source = target_tempo(plan, lane, choices.get("tempoDirection"))
    out.append(("Tempo", tempo_text, tempo_source))

    sections = structure_lines(plan)
    if sections:
        signature = plan.get("time_signature")
        body = "The plan found %d section%s: %s." % (
            len(sections), "" if len(sections) == 1 else "s", ", ".join(sections))
        if signature:
            body += " Time signature reads %s." % signature
        out.append(("Structure", body, "measured"))
    else:
        out.append(("Structure",
                    "No section breakdown came back for this track, so the "
                    "arrangement below is the lane's usual shape rather than "
                    "a reading of this record.", "unknown"))

    energy = _energy_note(plan)
    if energy:
        out.append(("Where the energy is", energy, "measured"))

    if convention.get("arrangement"):
        out.append(("Arrangement",
                    "For a %s, that usually means %s."
                    % (lane.lower(), convention["arrangement"]), "convention"))

    chosen = []
    for key, label in (("energy", "energy"), ("vocalTreatment", "vocal treatment"),
                       ("instrumentation", "instrumentation"),
                       ("riskLevel", "risk")):
        value = (choices.get(key) or "").strip()
        if value:
            chosen.append("%s %s" % (value.lower(), label))
    if chosen:
        out.append(("What you asked for",
                    "You chose " + ", ".join(chosen) + ". Everything above is "
                    "read against that.", "chosen"))

    use = (choices.get("targetUse") or "").strip()
    if use:
        out.append(("Where it goes", "Aimed at %s." % use, "chosen"))

    if convention.get("avoid"):
        out.append(("What to avoid",
                    "The usual failure in this lane is %s."
                    % convention["avoid"], "convention"))

    risk = (choices.get("riskLevel") or "").strip()
    if risk == "Aggressive":
        out.append(("A note on the risk level",
                    "Aggressive was chosen. Keep the original stems - the "
                    "version most likely to be thrown away is the one nobody "
                    "can walk back.", "chosen"))

    return out


def brief_is_grounded(brief):
    """Does this brief rest on anything measured?

    A brief made entirely of conventions and the artist's own selections is
    still useful, but it is not a reading of their record and must not be
    presented as one. The page asks this before it decides what to say.
    """
    return any(source.startswith("measured") for _h, _b, source in brief or [])
