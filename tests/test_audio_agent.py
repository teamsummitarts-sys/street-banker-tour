"""The Operator Voice Agent: the three things it is never allowed to be.

Not a person. Not an artist. Not anybody with a name.

These tests exist because a rule written in a doc is followed by whoever read
the doc, and this product gets configured by an operator under time pressure
who did not. So the rules refuse, and these check that they refuse.
"""
import os
import uuid

import pytest

import audio_agent as agent

OWNER = "agent-owner-%s@example.net" % uuid.uuid4().hex[:8]
MEMBER = "agent-member-%s@example.net" % uuid.uuid4().hex[:8]

GOOD = {
    "name": "Front desk",
    "purpose": "Answer distribution questions and take details.",
    "greeting": "You are speaking with an AI assistant for the label. "
                "I can answer questions or put you through to a person.",
    "human_contact": "Operations team, ops@example.net",
    "persona_note": "A calm front-desk assistant.",
}


@pytest.fixture(scope="module")
def application():
    os.environ["OWNER_EMAILS"] = OWNER
    os.environ["AUDIO_INTELLIGENCE_ENABLED"] = "1"
    os.environ["AUDIO_OPERATOR_ENABLED"] = "1"
    import app as appmod
    return appmod.app


@pytest.fixture
def owner(application):
    client = application.test_client()
    client.post("/signup", data={"name": "Ag Owner", "email": OWNER,
                                 "password": "ag-pass-123"})
    client.post("/login", data={"email": OWNER, "password": "ag-pass-123"})
    return client


# --- disclosure ------------------------------------------------------------

@pytest.mark.parametrize("greeting", [
    "You are speaking with an AI assistant for Artis War Records.",
    "Hi, this is an automated assistant. I can take details.",
    "This call is handled by an AI. How can I help?",
    "You're talking to a virtual assistant, not a real person.",
])
def test_a_real_disclosure_is_recognised(greeting):
    assert agent.discloses_ai(greeting)


@pytest.mark.parametrize("greeting", [
    "Hi, thanks for calling Artis War Records. How can I help?",
    "Good afternoon, you've reached the front desk.",
    "Hello! I'm here to help with distribution questions.",
    "",
])
def test_a_friendly_greeting_is_not_a_disclosure(greeting):
    """The commonest failure is a warm greeting that never says what it is."""
    assert not agent.discloses_ai(greeting)


@pytest.mark.parametrize("greeting", [
    "I am a real person, not a bot.",
    "You're speaking with a real person today.",
    "I'm a human assistant here to help.",
])
def test_a_greeting_claiming_personhood_is_caught(greeting):
    assert agent.claims_personhood(greeting)


def test_offering_a_human_is_not_claiming_to_be_one():
    greeting = "You are speaking with an AI assistant. I can put you through to a person."
    assert agent.discloses_ai(greeting)
    assert not agent.claims_personhood(greeting)


# --- identity --------------------------------------------------------------

@pytest.mark.parametrize("persona", [
    "Speaks as Marla Quinn, our head of A&R.",
    "You are Jordan Vale and you handle sync requests.",
    "Sounds like Ben Ortiz from the label.",
    "Voice of Marla Quinn.",
    "Impersonates Dana Whitlock on calls.",
    "As if you were Alan Prieto.",
    "SPEAKS AS Marla Quinn.",
])
def test_a_persona_naming_a_person_is_refused(persona):
    """The whole failure mode of a voice product in music is a machine that
    sounds like a specific artist."""
    assert agent._names_a_real_person(persona, ["Nine Volt Heart", "Marla Quinn"])


def test_the_capitalised_form_is_caught_at_the_start_of_a_sentence():
    """A case-sensitive verb let 'You are Jordan Vale' through - the most
    natural way an operator would write the thing this refuses."""
    assert agent._names_a_real_person("You are Jordan Vale.", [])


@pytest.mark.parametrize("persona", [
    "A calm front-desk assistant for the label.",
    "Answers distribution questions in plain language.",
    "Speaks as the label's front desk.",
    "",
])
def test_a_role_description_is_allowed(persona):
    """A guardrail that blocks ordinary configuration gets switched off by
    whoever it blocks."""
    assert not agent._names_a_real_person(persona, ["Marla Quinn"])


def test_a_roster_name_is_caught_however_it_is_typed():
    """The layer that actually matters: people the system knows about."""
    for form in ("marla quinn", "MARLA QUINN", "Marla Quinn"):
        assert agent._names_a_real_person("Speaks as %s." % form, ["Marla Quinn"])


# --- the profile lifecycle -------------------------------------------------

def test_every_problem_is_reported_at_once(application):
    """So an operator fixes the configuration once instead of discovering the
    next problem after each save."""
    with application.app_context():
        with pytest.raises(agent.GuardrailRefusal) as caught:
            agent.create_profile({"greeting": "Hello there."})
    assert caught.value.reason.count(".") >= 3


def test_a_profile_is_created_as_a_draft(application):
    with application.app_context():
        profile = agent.create_profile(dict(GOOD))
    assert profile["status"] == "draft", \
        "a profile that could speak the moment it was saved is one nobody read back"


def test_a_missing_human_exit_is_refused(application):
    fields = dict(GOOD)
    fields["human_contact"] = ""
    with application.app_context():
        with pytest.raises(agent.GuardrailRefusal):
            agent.create_profile(fields)


def test_editing_a_live_agent_cannot_remove_the_disclosure(application):
    """Otherwise the check is a one-time gate somebody walks through and then
    edits the greeting behind."""
    with application.app_context():
        profile = agent.create_profile(dict(GOOD))
        agent.activate(profile["id"])

        with pytest.raises(agent.GuardrailRefusal):
            agent.update_profile(profile["id"],
                                 {"greeting": "Hi, thanks for calling!"})

        assert agent.get_profile(profile["id"])["status"] == "active", \
            "the refused edit should not have changed anything"


def test_a_legitimate_edit_drops_a_live_agent_back_to_draft(application):
    with application.app_context():
        profile = agent.create_profile(dict(GOOD))
        agent.activate(profile["id"])
        edited = agent.update_profile(profile["id"],
                                      {"purpose": "Also answer sync questions."})
    assert edited["status"] == "draft"


def test_suspending_is_one_write(application):
    """Any guardrail that cannot be applied instantly is not a guardrail."""
    with application.app_context():
        profile = agent.create_profile(dict(GOOD))
        agent.activate(profile["id"])
        assert agent.suspend(profile["id"])["status"] == "suspended"


# --- sessions --------------------------------------------------------------

def test_disclosure_is_read_from_what_the_agent_said(application):
    with application.app_context():
        profile = agent.create_profile(dict(GOOD))
        session = agent.create_session(profile["id"])
        agent.record_outcome(session["id"], transcript=[
            {"role": "agent", "text": "You are speaking with an AI assistant."},
            {"role": "caller", "text": "Fine."}], status="completed")
        assert agent.get_session(session["id"])["disclosed"]


def test_a_caller_asking_if_it_is_an_ai_is_not_a_disclosure(application):
    """Reading the whole transcript instead of the agent's own turns would
    score the caller's question as the agent disclosing."""
    with application.app_context():
        profile = agent.create_profile(dict(GOOD))
        session = agent.create_session(profile["id"])
        agent.record_outcome(session["id"], transcript=[
            {"role": "caller", "text": "Am I speaking to an AI?"},
            {"role": "agent", "text": "How can I help you today?"}],
            status="completed")
        assert not agent.get_session(session["id"])["disclosed"]


def test_a_request_for_a_person_is_detected(application):
    with application.app_context():
        profile = agent.create_profile(dict(GOOD))
        session = agent.create_session(profile["id"])
        agent.record_outcome(session["id"], transcript=[
            {"role": "agent", "text": "You are speaking with an AI assistant."},
            {"role": "caller", "text": "Can I speak to a real person please?"}],
            status="completed")
        assert agent.get_session(session["id"])["human_requested"]


def test_unmet_requests_are_findable(application):
    """The single most important report here. An agent that quietly refuses
    to escalate is worse than no agent, and nobody would spot it in a list."""
    with application.app_context():
        profile = agent.create_profile(dict(GOOD))
        session = agent.create_session(profile["id"])
        agent.record_outcome(session["id"], transcript=[
            {"role": "caller", "text": "Put me through to a person."}],
            status="completed")

        unmet = agent.unmet_human_requests()
        assert any(s["id"] == session["id"] for s in unmet)

        agent.record_outcome(session["id"], status="escalated", escalated_to="Someone")
        unmet_after = agent.unmet_human_requests()
        assert not any(s["id"] == session["id"] for s in unmet_after)


# --- over HTTP -------------------------------------------------------------

def test_the_guardrails_hold_over_http(owner):
    no_disclosure = dict(GOOD)
    no_disclosure["greeting"] = "Hi, thanks for calling the label!"
    assert owner.post("/operator-desk/agents/new", data=no_disclosure).status_code == 400

    named = dict(GOOD)
    named["persona_note"] = "You are Jordan Vale, head of A&R."
    assert owner.post("/operator-desk/agents/new", data=named).status_code == 400


def test_a_refusal_says_what_would_fix_it(owner):
    no_disclosure = dict(GOOD)
    no_disclosure["greeting"] = "Hi, thanks for calling the label!"
    body = owner.post("/operator-desk/agents/new", data=no_disclosure).get_data(as_text=True)
    assert "speaking to an AI" in body
    assert "for example" in body.lower(), "a refusal should show the operator a fix"


def test_creating_an_agent_is_an_owner_action(application, owner):
    """It is the one thing in the Desk that speaks to the public in the
    company's name."""
    client = application.test_client()
    client.post("/signup", data={"name": "Member", "email": MEMBER,
                                 "password": "mb-pass-123"})
    client.post("/login", data={"email": MEMBER, "password": "mb-pass-123"})
    assert client.post("/operator-desk/agents/new", data=dict(GOOD)).status_code == 403


def test_escalating_creates_a_task_and_clears_the_report(application, owner):
    import desk_store

    with application.app_context():
        profile = agent.create_profile(dict(GOOD))
        agent.activate(profile["id"])
        session = agent.create_session(profile["id"], caller_ref="+15550100")
        agent.record_outcome(session["id"], transcript=[
            {"role": "caller", "text": "Can I speak to a person?"}],
            status="completed")
        before = len(desk_store.list_tasks())

    owner.post("/operator-desk/agents/sessions/%s/escalate" % session["id"])

    with application.app_context():
        assert len(desk_store.list_tasks()) == before + 1
        row = agent.get_session(session["id"])
        assert row["status"] == "escalated"
        assert row["escalated_to"]


def test_the_feature_is_absent_when_switched_off(application, owner, monkeypatch):
    monkeypatch.delenv("AUDIO_OPERATOR_ENABLED", raising=False)
    assert owner.post("/operator-desk/agents/new", data=dict(GOOD)).status_code == 404
