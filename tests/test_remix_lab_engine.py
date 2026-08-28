"""Remix Lab, connected to the audio seam.

The page shipped saying generation was not connected, and it was right to: a
brief that opens "original sits around 92 BPM in A minor" needs somebody to
have listened to the record, and inventing that number is the most damaging
fake available here because a producer would act on it.

A MusicProvider now exposes composition_plan() — tempo, section boundaries,
an energy curve — which is a measurement. These tests are about the line
between what is measured, what is convention, and what is still nobody's to
claim.
"""
import io
import os
import re
import uuid

import pytest

import audio_mock
import remix_lab_config as rlc
import remix_lab_engine as rle

PLAN = audio_mock.MockMusic().composition_plan({"source_asset_id": "a1"})

CHOICES = {"lane": "Club / DJ Edit", "targetUse": "DJ pack", "energy": "High",
           "tempoDirection": "Same", "vocalTreatment": "Hook-first",
           "instrumentation": "Balanced", "riskLevel": "Exploratory"}


@pytest.fixture(scope="module")
def application():
    """Switches the engine on for this module and puts the environment back.

    Setting os.environ without restoring it leaks into every module that runs
    afterwards - test_remix_lab.py reads the page's note, which is now
    conditional on these flags, so a leak here makes that suite pass or fail
    depending on the order the files happened to run in.
    """
    before = {name: os.environ.get(name)
              for name in ("AUDIO_INTELLIGENCE_ENABLED",
                           "REMIX_LAB_AUDIO_ENGINE_ENABLED")}
    os.environ["AUDIO_INTELLIGENCE_ENABLED"] = "1"
    os.environ["REMIX_LAB_AUDIO_ENGINE_ENABLED"] = "1"

    import app as appmod
    yield appmod.app

    for name, value in before.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@pytest.fixture
def artist(application):
    email = "remix-%s@example.net" % uuid.uuid4().hex[:8]
    client = application.test_client()
    client.post("/signup", data={"name": "Artist", "email": email,
                                 "password": "rl-pass-123"})
    client.post("/login", data={"email": email, "password": "rl-pass-123"})
    return client


def _post(client, **extra):
    data = {"rights_own": "1", "rights_likeness": "1",
            "remixLane": "Club / DJ Edit", "targetUse": "DJ pack",
            "energy": "High", "tempoDirection": "Same",
            "vocalTreatment": "Hook-first", "instrumentation": "Balanced",
            "riskLevel": "Exploratory",
            "file": (io.BytesIO(b"RIFF" + b"\0" * 600), "master.wav")}
    data.update(extra)
    return client.post("/remix-lab/brief", data=data,
                       content_type="multipart/form-data")


# --- the flag that gated nothing -------------------------------------------

def test_the_engine_flag_now_gates_something():
    """REMIX_LAB_AUDIO_ENGINE_ENABLED sat in FLAGS checked by nothing. An
    operator could set it and watch nothing happen."""
    import audio_policy

    specs = [s for s in audio_policy.FEATURES.values()
             if s["flag"] == "REMIX_LAB_AUDIO_ENGINE_ENABLED"]
    assert specs, "the flag still gates nothing"


def test_the_engine_is_off_unless_both_flags_are_set(monkeypatch):
    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.delenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", raising=False)
    assert not rlc.engine_live()

    monkeypatch.setenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", "1")
    assert rlc.engine_live()


def test_the_page_says_which_state_it_is_in(monkeypatch):
    """It has always said generation was not connected. Now that can be
    false, and the note must stop saying it."""
    monkeypatch.delenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", raising=False)
    assert "not yet connected" in rlc.get_remix_lab_config()["preview_note"]

    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", "1")
    live = rlc.get_remix_lab_config()["preview_note"]
    assert "not yet connected" not in live
    assert "measurement" in live or "read for tempo" in live


# --- what the brief may and may not claim ----------------------------------

def test_a_measured_tempo_is_labelled_measured():
    brief = rle.compose_brief(PLAN, CHOICES)
    tempo = [(b, s) for h, b, s in brief if h == "Tempo"][0]
    assert "measured" in tempo[1]
    assert str(PLAN["tempo_bpm"]) in tempo[0]


def test_a_lane_convention_is_labelled_a_convention():
    """It is not a reading of this record and must not read as one."""
    brief = rle.compose_brief(PLAN, CHOICES)
    arrangement = [(b, s) for h, b, s in brief if h == "Arrangement"]
    assert arrangement and arrangement[0][1] == "convention"
    assert "usually" in arrangement[0][0]


def test_the_artists_own_choices_are_labelled_chosen():
    brief = rle.compose_brief(PLAN, CHOICES)
    assert any(s == "chosen" for _h, _b, s in brief)


def test_it_never_claims_a_key():
    """The plan carries no key, and guessing one sends a producer to the
    wrong pitch shift."""
    text = " ".join(b for _h, b, _s in rle.compose_brief(PLAN, CHOICES)).lower()
    assert "key of" not in text
    assert not re.search(r"\bin [a-g] (minor|major)\b", text)


def test_it_never_claims_musical_judgement():
    text = " ".join(b for _h, b, _s in rle.compose_brief(PLAN, CHOICES)).lower()
    for phrase in ("builds like", "lands on the one", "feels", "sounds like",
                   "the strongest section"):
        assert phrase not in text, phrase


def test_the_artists_tempo_direction_beats_the_lane_convention():
    """They chose it deliberately; the convention is only a default."""
    choices = dict(CHOICES, tempoDirection="Slower")
    tempo = [b for h, b, _s in rle.compose_brief(PLAN, choices) if h == "Tempo"][0]
    assert "slower" in tempo.lower()
    assert "as you asked" in tempo


def test_section_timings_come_from_the_plan():
    brief = rle.compose_brief(PLAN, CHOICES)
    structure = [b for h, b, _s in brief if h == "Structure"][0]
    assert str(len(PLAN["sections"])) in structure
    assert "0:00" in structure


# --- degrading honestly ----------------------------------------------------

def test_with_no_plan_nothing_is_marked_measured():
    brief = rle.compose_brief({}, CHOICES)
    assert not rle.brief_is_grounded(brief)
    assert all(not s.startswith("measured") for _h, _b, s in brief)


def test_with_no_plan_it_says_the_tempo_was_not_measured():
    brief = rle.compose_brief({}, CHOICES)
    tempo = [b for h, b, _s in brief if h == "Tempo"][0]
    assert "not measured" in tempo


def test_a_grounded_brief_is_recognised():
    assert rle.brief_is_grounded(rle.compose_brief(PLAN, CHOICES))


# --- the server-side screen the code asked for -----------------------------

def test_an_imitation_reference_is_refused_before_anything_is_spent(artist):
    """remix_lab_config called this 'the authoritative copy the server must
    call before any generation request leaves the building'."""
    resp = _post(artist, reference="Make it sound like a famous singer")
    assert resp.status_code == 400
    body = resp.get_data(as_text=True)
    assert "sound like" in body, "the refusal must quote what stopped it"


def test_the_refusal_offers_replacements(artist):
    body = _post(artist, reference="in the style of that artist").get_data(as_text=True)
    assert rlc.ALLOWED_EXAMPLES[0] in body


def test_a_clean_reference_runs(artist):
    resp = _post(artist, reference="High-energy club version with faster drums")
    assert resp.status_code == 200


# --- the rights gate -------------------------------------------------------

def test_both_confirmations_are_required(artist):
    assert _post(artist, rights_own="").status_code == 400
    assert _post(artist, rights_likeness="").status_code == 400


def test_a_non_audio_file_is_refused(artist):
    resp = _post(artist, file=(io.BytesIO(b"%PDF-"), "master.pdf"))
    assert resp.status_code == 400


def test_an_empty_file_is_refused(artist):
    resp = _post(artist, file=(io.BytesIO(b""), "master.wav"))
    assert resp.status_code == 400


# --- access ----------------------------------------------------------------

def test_a_signed_out_visitor_cannot_run_one(application):
    resp = application.test_client().post("/remix-lab/brief", data={"rights_own": "1"})
    assert resp.status_code in (301, 302)
    assert "/login" in (resp.headers.get("Location") or "")


def test_the_public_page_still_opens_for_a_visitor(application):
    """The brochure, the rights gate and the likeness screen are what a
    visitor needs to judge the tool. None of that required a login."""
    assert application.test_client().get("/remix-lab").status_code == 200


def test_the_form_only_posts_when_the_engine_is_live(application, monkeypatch):
    """A form that posted to a route the gate would refuse is worse than one
    that honestly stays a preview."""
    monkeypatch.delenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", raising=False)
    body = application.test_client().get("/remix-lab").get_data(as_text=True)
    assert 'action="/remix-lab/brief"' not in body

    monkeypatch.setenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", "1")
    body = application.test_client().get("/remix-lab").get_data(as_text=True)
    assert 'action="/remix-lab/brief"' in body


def test_the_route_is_absent_when_the_engine_is_off(artist, monkeypatch):
    monkeypatch.delenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", raising=False)
    assert _post(artist, reference="A warm acoustic version").status_code == 404


# --- the page ---------------------------------------------------------------

def test_a_mock_plan_is_labelled_as_not_a_measurement(artist):
    """A fictional tempo that reads as a measurement is the one failure here
    a producer would act on."""
    body = _post(artist, reference="High-energy club version").get_data(as_text=True)
    text = re.sub(r"\s+", " ", body)
    assert "not measurements of your track" in text


def test_the_page_states_what_it_did_not_do(artist):
    body = _post(artist, reference="High-energy club version").get_data(as_text=True)
    text = re.sub(r"\s+", " ", body).lower()
    assert "no key detection" in text
    assert "did not listen to your record" in text


# --- the claims the page makes about itself --------------------------------
#
# Every one of these was a single unconditional string that became FALSE the
# moment the engine was switched on for a real deployment. They were found by
# probing the live site after the flags were set, not by any test.

def test_the_example_panel_note_stops_saying_generation_is_off(monkeypatch):
    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", "1")
    assert "not yet connected" not in rlc.get_remix_lab_config()["example_note"]

    monkeypatch.delenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", raising=False)
    assert "not yet connected" in rlc.get_remix_lab_config()["example_note"]


def test_the_capability_status_flips_with_the_flags(monkeypatch):
    import capability_status

    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", "1")
    assert capability_status.resolve("remix_lab")["status"] == capability_status.LIVE

    monkeypatch.delenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", raising=False)
    assert capability_status.resolve("remix_lab")["status"] == \
        capability_status.COMING_SOON


def test_the_hero_chip_stops_saying_coming_soon(application, monkeypatch):
    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", "1")
    body = application.test_client().get("/remix-lab").get_data(as_text=True)
    assert "generation coming soon" not in body

    monkeypatch.delenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", raising=False)
    body = application.test_client().get("/remix-lab").get_data(as_text=True)
    assert "generation coming soon" in body


# --- the bug the whole suite missed ----------------------------------------

def test_the_browser_is_told_whether_the_engine_is_live(application, monkeypatch):
    """Without this the script cannot know, and the form's action attribute
    is decoration."""
    import json

    monkeypatch.setenv("AUDIO_INTELLIGENCE_ENABLED", "1")
    monkeypatch.setenv("REMIX_LAB_AUDIO_ENGINE_ENABLED", "1")
    body = application.test_client().get("/remix-lab").get_data(as_text=True)
    blob = re.search(r'id="sbrl-config">(.*?)</script>', body, re.S).group(1)
    assert json.loads(blob)["engineLive"] is True


def test_the_submit_handler_does_not_cancel_unconditionally():
    """The bug this file exists to prevent a repeat of.

    preventDefault() sat at the TOP of the submit handler, which was correct
    while the page was a preview and became a real defect the moment the form
    got an action: with JavaScript on - every actual visitor - the submission
    never reached the server. Every test here uses the Flask test client,
    which runs no JavaScript, so the whole suite passed while the live page
    was broken.

    This reads the source because the suite has no browser. It is a weaker
    check than driving the page, and it is the one that would have caught it.
    """
    script = open("static/js/remix-lab.js", encoding="utf-8").read()
    handler = script[script.index('addEventListener("submit"'):]

    guard = handler.index("CFG.engineLive")
    cancels = [m.start() for m in re.finditer(r"event\.preventDefault\(\)", handler)]
    assert cancels, "the preview path must still cancel the submit"

    # Every cancel before the engine check has to be inside a validation
    # branch that also returns - never a bare cancel at the top.
    head = handler[:guard]
    assert "function stop(message)" in head, \
        "cancels before the engine check must go through the guarded helper"
    assert not re.search(r"submit\",\s*function \(event\) \{\s*event\.preventDefault\(\)",
                         handler), "preventDefault is unconditional again"


def test_the_preview_path_still_cancels():
    """With the engine off the form must NOT post - the route would 404 and
    the visitor would lose what they typed."""
    script = open("static/js/remix-lab.js", encoding="utf-8").read()
    handler = script[script.index('addEventListener("submit"'):]
    after_guard = handler[handler.index("CFG.engineLive"):]
    assert "event.preventDefault()" in after_guard
