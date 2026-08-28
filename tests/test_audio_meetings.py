"""Meeting Intelligence: the extractor's honesty, and the approval boundary.

The thing under test that matters most is not "does it find action items".
It is that the tool never claims to have understood the meeting, and never
writes anything onto a lead without a person deciding. A record of a meeting
is what a deal argument later turns on, and an invented one is worse than
none.
"""
import io
import os
import uuid

import pytest

import audio_meetings as meetings

OWNER = "meet-owner-%s@example.net" % uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def application():
    os.environ["OWNER_EMAILS"] = OWNER
    os.environ["AUDIO_INTELLIGENCE_ENABLED"] = "1"
    os.environ["MEETING_INTELLIGENCE_ENABLED"] = "1"
    import app as appmod
    # The module-level app owns the Desk blueprint; a second create_app()
    # cannot add routes to an already-registered blueprint.
    return appmod.app


@pytest.fixture
def desk(application):
    client = application.test_client()
    client.post("/signup", data={"name": "Meet Owner", "email": OWNER,
                                 "password": "meet-pass-123"})
    client.post("/login", data={"email": OWNER, "password": "meet-pass-123"})
    return client


def _upload(client, name="call.wav", title="A meeting", consent="1"):
    data = {"file": (io.BytesIO(b"RIFF" + b"\0" * 400), name), "title": title}
    if consent:
        data["consent"] = consent
    resp = client.post("/operator-desk/meetings/upload", data=data,
                       content_type="multipart/form-data")
    assert resp.status_code in (301, 302), resp.get_data(as_text=True)[:400]
    return resp.headers["Location"].rstrip("/").split("/")[-1]


# --- the extractor ---------------------------------------------------------

def test_it_says_nothing_about_a_conversation_with_no_commitments():
    """A tool that always finds something will be trusted when it should not
    be. Small talk must produce an empty queue."""
    segments = [{"speaker": "S1", "start_ms": 0, "text":
                 "The weather was good. The room was on the third floor. "
                 "There were four people there. The coffee was cold."}]
    assert meetings.extract_candidates(segments) == []


def test_it_finds_a_plain_commitment():
    segments = [{"speaker": "S1", "start_ms": 0,
                 "text": "I will send the paperwork over so your attorney can look at it."}]
    found = meetings.extract_candidates(segments)
    assert len(found) == 1
    assert found[0]["kind"] == "action"


def test_every_candidate_carries_the_sentence_it_came_from():
    """A suggestion a person cannot check against the recording is one they
    have to take on faith, which is exactly what this must not ask."""
    segments = [{"speaker": "Speaker 2", "start_ms": 4200,
                 "text": "Can you pull the last twelve months of statements."}]
    candidate = meetings.extract_candidates(segments)[0]
    assert candidate["quote"]
    assert candidate["speaker"] == "Speaker 2"
    assert candidate["start_ms"] == 4200
    assert candidate["matched_on"], "a candidate must say why it was picked"


def test_the_reason_is_readable_by_a_person():
    """'somebody said they would' is checkable. 'confidence 0.82' is not."""
    segments = [{"speaker": "S1", "start_ms": 0,
                 "text": "I will send the contract across tomorrow morning."}]
    reason = meetings.extract_candidates(segments)[0]["matched_on"]
    assert " " in reason, "the reason should read as English, not a code"
    assert not any(ch.isdigit() for ch in reason)


def test_one_sentence_produces_at_most_one_candidate():
    segments = [{"speaker": "S1", "start_ms": 0, "text":
                 "We agreed that I will send the contract by Friday and we should review it."}]
    assert len(meetings.extract_candidates(segments)) == 1


def test_a_repeated_sentence_is_not_offered_twice():
    line = "I will send the paperwork over today."
    segments = [{"speaker": "S1", "start_ms": 0, "text": line},
                {"speaker": "S2", "start_ms": 9000, "text": line}]
    assert len(meetings.extract_candidates(segments)) == 1


def test_unexpanded_contractions_are_matched():
    """Transcription engines expand contractions inconsistently. 'Let us' is
    the form a hand-written regex forgets, and a missed next step is a task
    nobody was offered."""
    for phrasing in ("Let us get the metadata cleaned up before delivery.",
                     "Let's get the metadata cleaned up before delivery."):
        segments = [{"speaker": "S1", "start_ms": 0, "text": phrasing}]
        assert meetings.extract_candidates(segments), phrasing


def test_fragments_are_not_offered_as_candidates():
    segments = [{"speaker": "S1", "start_ms": 0, "text": "I will. We can. Yes."}]
    assert meetings.extract_candidates(segments) == []


# --- the workflow ----------------------------------------------------------

def test_a_non_audio_file_is_refused(desk):
    resp = desk.post("/operator-desk/meetings/upload",
                     data={"file": (io.BytesIO(b"%PDF-"), "contract.pdf")},
                     content_type="multipart/form-data")
    assert resp.status_code == 400


def test_an_empty_file_is_refused(desk):
    resp = desk.post("/operator-desk/meetings/upload",
                     data={"file": (io.BytesIO(b""), "empty.wav")},
                     content_type="multipart/form-data")
    assert resp.status_code == 400


def test_transcribing_twice_does_not_double_the_review_queue(desk, application):
    """Transcription is charged per minute, and a doubled queue is a person
    reviewing the same sentence twice."""
    meeting_id = _upload(desk)
    desk.post("/operator-desk/meetings/%s/transcribe" % meeting_id)
    with application.app_context():
        first = len(meetings.list_candidates(meeting_id))
    desk.post("/operator-desk/meetings/%s/transcribe" % meeting_id)
    with application.app_context():
        second = len(meetings.list_candidates(meeting_id))
    assert first == second


def test_a_demo_transcript_says_so_on_the_page(desk):
    """A fictional transcript that reads as a real one is the most dangerous
    thing this page could show."""
    meeting_id = _upload(desk)
    desk.post("/operator-desk/meetings/%s/transcribe" % meeting_id)
    body = desk.get("/operator-desk/meetings/%s" % meeting_id).get_data(as_text=True)
    assert "demo transcript" in body.lower() or "fictional" in body.lower()


# --- the approval boundary -------------------------------------------------

def test_nothing_reaches_a_lead_until_a_person_approves(desk, application):
    import desk_store

    meeting_id = _upload(desk)
    desk.post("/operator-desk/meetings/%s/transcribe" % meeting_id)

    with application.app_context():
        candidates = meetings.list_candidates(meeting_id)
        assert candidates, "nothing was extracted, so this proves nothing"
        assert all(c["status"] == "pending" for c in candidates)
        before = len(desk_store.list_tasks())

    # Merely transcribing must not have written a task.
    with application.app_context():
        assert len(desk_store.list_tasks()) == before


def test_approving_writes_a_task_under_the_approver_s_name(desk, application):
    import desk_store

    meeting_id = _upload(desk, title="Distribution call")
    desk.post("/operator-desk/meetings/%s/transcribe" % meeting_id)

    with application.app_context():
        candidate = meetings.list_candidates(meeting_id)[0]
        before = len(desk_store.list_tasks())

    desk.post("/operator-desk/meetings/candidates/%s/decide" % candidate["id"],
              data={"action": "task"})

    with application.app_context():
        assert len(desk_store.list_tasks()) == before + 1
        row = meetings.get_candidate(candidate["id"])
        assert row["status"] == "approved"
        assert row["promoted_kind"] == "task"
        assert row["decided_by"], "who approved it must be recorded"


def test_an_approved_task_carries_where_it_came_from(desk, application):
    """Somebody reading this in six months needs to know it came from a
    meeting and which sentence produced it."""
    import desk_store

    meeting_id = _upload(desk, title="Distribution call")
    desk.post("/operator-desk/meetings/%s/transcribe" % meeting_id)
    with application.app_context():
        candidate = meetings.list_candidates(meeting_id)[0]
    desk.post("/operator-desk/meetings/candidates/%s/decide" % candidate["id"],
              data={"action": "task"})

    with application.app_context():
        row = meetings.get_candidate(candidate["id"])
        task = [t for t in desk_store.list_tasks() if t["id"] == row["promoted_id"]][0]

    description = (task["description"] or "").lower()
    assert "meeting" in description
    assert "matched on" in description, "the task must not imply it was understood"
    assert candidate["quote"][:30].lower() in description


def test_dismissing_writes_nothing(desk, application):
    import desk_store

    meeting_id = _upload(desk)
    desk.post("/operator-desk/meetings/%s/transcribe" % meeting_id)
    with application.app_context():
        candidate = meetings.list_candidates(meeting_id)[-1]
        before = len(desk_store.list_tasks())

    desk.post("/operator-desk/meetings/candidates/%s/decide" % candidate["id"],
              data={"action": "dismiss"})

    with application.app_context():
        assert len(desk_store.list_tasks()) == before
        assert meetings.get_candidate(candidate["id"])["status"] == "dismissed"


def test_the_feature_is_absent_when_switched_off(application, monkeypatch):
    monkeypatch.delenv("MEETING_INTELLIGENCE_ENABLED", raising=False)
    client = application.test_client()
    client.post("/login", data={"email": OWNER, "password": "meet-pass-123"})
    resp = client.post("/operator-desk/meetings/upload",
                       data={"file": (io.BytesIO(b"RIFF"), "x.wav")},
                       content_type="multipart/form-data")
    assert resp.status_code == 404


def test_a_signed_out_visitor_cannot_reach_meetings(application):
    resp = application.test_client().get("/operator-desk/meetings")
    assert resp.status_code in (301, 302, 403)
