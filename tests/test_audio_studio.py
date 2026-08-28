"""Audio Studio: rights, the likeness screen, and who may register a voice.

Phases 4, 5 and 6 share one engine because they are the same act with
different verbs. These tests are about the three things that engine must never
get wrong:

  * a request to imitate a specific person is refused, server-side, before
    anything costs money
  * rights are confirmed for THIS piece of work, by a named person
  * a voice can only be registered by the person whose voice it is
"""
import io
import os
import uuid

import pytest

import audio_works as works

ARTIST = "studio-%s@example.net" % uuid.uuid4().hex[:8]
OTHER = "studio-other-%s@example.net" % uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def application():
    for flag in ("AUDIO_INTELLIGENCE_ENABLED", "CAMPAIGN_AUDIO_TOOLKIT_ENABLED",
                 "SOUND_EFFECTS_ENABLED", "STEM_SEPARATION_ENABLED"):
        os.environ[flag] = "1"
    import app as appmod
    return appmod.app


def _account(application, email):
    client = application.test_client()
    client.post("/signup", data={"name": "Studio Artist", "email": email,
                                 "password": "st-pass-123"})
    client.post("/login", data={"email": email, "password": "st-pass-123"})
    return client


@pytest.fixture
def artist(application):
    return _account(application, ARTIST)


def _start(client, **fields):
    data = {"lane": "campaign_sfx", "rights": "1"}
    data.update(fields)
    resp = client.post("/audio-studio/new", data=data)
    assert resp.status_code in (301, 302), resp.get_data(as_text=True)[:300]
    return resp.headers["Location"].rstrip("/").split("/")[-1]


# --- the likeness screen ---------------------------------------------------

@pytest.mark.parametrize("brief", [
    "Make it sound like a famous singer",
    "In the style of that artist",
    "Give it the same voice as the demo",
    "Copy the vocals from the reference",
    "Clone the voice on this track",
    "a reference artist type beat",
])
def test_an_imitation_brief_is_refused(brief):
    """remix_lab_config asked the server to make this check before any
    generation request leaves the building. This is where that happens."""
    assert works.screen_reference(brief), brief


@pytest.mark.parametrize("brief", [
    "High-energy club version with faster drums.",
    "Warm acoustic version, sparse percussion, intimate vocals.",
    "A vinyl crackle under soft room tone.",
    "",
])
def test_a_musical_brief_passes(brief):
    assert works.screen_reference(brief) is None, brief


def test_the_screen_runs_before_rights(application):
    """Both refuse, but the imitation check costs nothing and must be the one
    that answers. Otherwise somebody fixes the rights box and then discovers
    the real problem."""
    with application.app_context():
        item = works.create_work("u1", "sound_effects",
                                 brief="Make it sound like a famous singer")
        # rights deliberately NOT confirmed
        with pytest.raises(works.WorkRefusal) as caught:
            works.submit_work(item["id"])
    assert caught.value.code == "imitation"


def test_a_refusal_is_recorded_on_the_item(application):
    with application.app_context():
        item = works.create_work("u1", "sound_effects",
                                 brief="In the style of that artist")
        with pytest.raises(works.WorkRefusal):
            works.submit_work(item["id"])
        row = works.get_work(item["id"])
    assert row["status"] == "refused"
    assert row["refusal_code"] == "imitation"
    assert row["refusal_reason"], "the artist needs to read why"


def test_the_refusal_reaches_the_page_with_a_fix(artist):
    work_id = _start(artist, brief="Make it sound like a famous singer")
    body = artist.get("/audio-studio/%s" % work_id).get_data(as_text=True)
    assert "This was not run" in body
    assert "musical direction" in body, "a refusal should say what to write instead"


# --- rights ----------------------------------------------------------------

def test_nothing_runs_without_a_rights_confirmation(application, artist):
    work_id = artist.post("/audio-studio/new",
                          data={"lane": "campaign_sfx", "brief": "A door slam"}
                          ).headers["Location"].rstrip("/").split("/")[-1]
    with application.app_context():
        row = works.get_work(work_id)
    assert row["status"] == "refused"
    assert row["refusal_code"] == "rights_required"


def test_the_confirmation_records_who_and_when(application, artist):
    """'I own my catalogue' ticked once at signup is not a claim about the
    file somebody uploaded this afternoon."""
    work_id = _start(artist, brief="A vinyl crackle under soft room tone")
    with application.app_context():
        row = works.get_work(work_id)
    assert row["rights_confirmed"]
    assert row["rights_confirmed_by"], "who confirmed it was not recorded"
    assert row["rights_confirmed_at"]


def test_a_clean_confirmed_brief_runs(application, artist):
    work_id = _start(artist, brief="A vinyl crackle under soft room tone")
    with application.app_context():
        assert works.get_work(work_id)["status"] == "ready"


# --- the voice vault -------------------------------------------------------

def test_the_vault_is_off_before_anything_else(application):
    """The outermost layer. With the flag unset the gate refuses first, and
    the consent question is never reached - which is why the test below has
    to switch it on to test the layer it is actually about."""
    with application.app_context():
        item = works.create_work("manager-1", "voice_vault",
                                 options={"owner_person_id": "An Artist"})
        works.confirm_rights(item["id"], "A Manager")
        with pytest.raises(works.WorkRefusal) as caught:
            works.submit_work(item["id"])
    assert caught.value.code == "disabled"


def test_a_manager_cannot_register_somebody_elses_voice(application, monkeypatch):
    """Three layers refuse this. With the flag AND the policy both switched
    on, the only thing left standing between a manager and somebody else's
    voice is the owner's own verification - and that is what this checks."""
    import audio_store as astore

    monkeypatch.setenv("ARTIST_VOICE_VAULT_ENABLED", "1")
    with application.app_context():
        astore.set_policy(None, {"allow_voice_cloning": True})
        try:
            item = works.create_work(
                "manager-1", "voice_vault",
                options={"owner_person_id": "An Artist", "owner_verified": False})
            works.confirm_rights(item["id"], "A Manager")
            with pytest.raises(works.WorkRefusal) as caught:
                works.submit_work(item["id"])
            assert caught.value.code == "owner_consent_required"
        finally:
            astore.set_policy(None, {"allow_voice_cloning": False})


def test_even_the_mock_refuses_an_unverified_registration(application):
    """So the calling code meets that path in development, not production."""
    import audio_providers as ap

    adapter = ap.get(ap.VOICE_IDENTITY)
    with pytest.raises(ap.ProviderRefusal):
        adapter.register_verified_voice({"owner_person_id": "An Artist",
                                         "owner_verified": False})


# --- lanes and gating ------------------------------------------------------

def test_a_lane_is_only_available_when_the_gate_would_allow_it(application, monkeypatch):
    """A lane that advertises itself and then refuses every submission is a
    worse failure than one shown as off: the artist writes a brief, presses
    the button and is told no for a reason unrelated to what they typed."""
    import audio_studio as studio

    monkeypatch.setenv("CAMPAIGN_AUDIO_TOOLKIT_ENABLED", "1")
    monkeypatch.delenv("SOUND_EFFECTS_ENABLED", raising=False)

    lanes = {lane["title"]: lane for lane in studio._lanes_for_render()}
    assert not lanes["Sound effects"]["on"]
    assert "SOUND_EFFECTS_ENABLED" in lanes["Sound effects"]["flag"], \
        "the page must name every flag the lane actually needs"


def test_an_off_lane_cannot_be_posted_to(artist):
    assert artist.post("/audio-studio/new",
                       data={"lane": "release_pack", "rights": "1"}).status_code == 404


def test_an_unknown_lane_is_a_404(artist):
    assert artist.post("/audio-studio/new",
                       data={"lane": "nonsense", "rights": "1"}).status_code == 404


def test_every_lane_is_listed_even_when_off(artist):
    """An artist should see what the product does before an operator switches
    on anything that costs money."""
    import audio_studio as studio

    body = artist.get("/audio-studio").get_data(as_text=True)
    for _key, _kind, _flag, title, _note in studio.LANES:
        assert title in body, title


# --- uploads and privacy ---------------------------------------------------

def test_a_non_audio_upload_is_refused(artist):
    resp = artist.post("/audio-studio/new",
                       data={"lane": "remix_stems", "rights": "1",
                             "file": (io.BytesIO(b"%PDF-"), "master.pdf")},
                       content_type="multipart/form-data")
    assert resp.status_code == 400


def test_an_empty_upload_is_refused(artist):
    resp = artist.post("/audio-studio/new",
                       data={"lane": "remix_stems", "rights": "1",
                             "file": (io.BytesIO(b""), "master.wav")},
                       content_type="multipart/form-data")
    assert resp.status_code == 400


def test_another_account_gets_a_404_not_a_403(application, artist):
    """They should not learn it exists."""
    work_id = _start(artist, brief="A vinyl crackle under soft room tone")
    other = _account(application, OTHER)
    assert other.get("/audio-studio/%s" % work_id).status_code == 404


def test_a_signed_out_visitor_is_sent_to_login(application):
    resp = application.test_client().get("/audio-studio")
    assert resp.status_code in (301, 302)
    assert "/login" in (resp.headers.get("Location") or "")
