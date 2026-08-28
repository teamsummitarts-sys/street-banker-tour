# Operator Voice Agent (`/operator-desk/agents`)

An agent that can answer a line for a music company: take details, answer
questions it has been given answers to, and put a caller through to a person.

## The three things it is never allowed to be

**Not a person. Not an artist. Not anybody with a name.**

These are functions that refuse, not documentation. A rule written in a doc is
followed by whoever read the doc, and this product gets configured by an
operator under time pressure who did not.

| Rule | Enforced by |
| --- | --- |
| The greeting must disclose it is an AI | `discloses_ai()` — checked against the words that will actually be spoken |
| The greeting must not claim to be a person | `claims_personhood()` |
| It must name a way to reach a human | `check_profile()` — an agent with no exit is a hold queue that never ends |
| The persona must not name a real person | `_names_a_real_person()` |

A refusal returns **every** problem at once, each with a sentence saying what
would fix it, so an operator corrects the configuration once instead of
discovering the next failure after each save.

## Why disclosure is checked on the text, not a checkbox

A caller who does not know they are talking to a machine cannot consent to it.
A checkbox beside the greeting records that somebody *clicked*; only the
greeting itself records what the caller will *hear*.

The same reasoning applies after the call: `session.disclosed` is **derived
from the agent's own turns in the transcript**, not from the configuration. An
agent configured correctly that then failed to say it is what this must be able
to find. A caller asking *"am I speaking to an AI?"* is explicitly not counted —
reading the whole transcript instead of the agent's turns would score the
caller's question as the agent disclosing.

## The identity guardrail, and its known hole

Two layers:

1. **Roster check** — exact, case-insensitive, against every name the instance
   knows (leads, contacts, managers, team). This is the layer that matters,
   because the people this product could plausibly imitate are on it.
2. **Shape check** — a heuristic for names the system has never heard of.
   Requires Capitalised Words after an identity verb (`speaks as`, `you are`,
   `voice of`, `sounds like`, `impersonates`, `as if you were`).

> **The hole:** `"you are jordan vale"` in all lower case is not caught by
> layer 2. Making the name part case-insensitive would refuse `"you are the
> front desk"` — a legitimate role description — and a guardrail that blocks
> ordinary configuration gets switched off by whoever it blocks.

This is defence in depth, not a proof. The form tells the operator the rule;
the roster check enforces it for real people.

**A bug worth remembering:** the verb was originally case-sensitive, so
`"You are Jordan Vale"` — a capital Y, the most natural way anyone would type
it — walked straight through. The flag is now scoped with `(?i:...)` so the
verb is case-insensitive while the name still requires capitals.

## Lifecycle

```
create ──► draft ──activate──► active ──suspend──► suspended
             ▲                    │
             └──── any edit ──────┘
```

* Always created as a **draft**. A profile that could speak the moment it was
  saved is one nobody read back.
* `activate()` **re-runs every check** rather than trusting that creation ran
  them — the row may have been edited by another path, and this is the only
  moment that matters.
* Any edit drops a live agent back to draft. Otherwise the disclosure check is
  a one-time gate somebody walks through and then edits the greeting behind.
* `suspend()` is one column write. Any guardrail that cannot be applied
  instantly is not a guardrail.

Creating an agent requires `manage_users` — owner only. It is the one thing in
the Desk that speaks to the public in the company's name.

## The report that matters most

`unmet_human_requests()` — sessions where the caller asked for a person and the
session did not end escalated. It is rendered **above everything else** on the
agent page.

An agent that quietly refuses to escalate is worse than no agent, and nobody
would spot it in a session list. Picking one up creates a high-priority
call-back task under the operator's name, so it cannot be forgotten.

Detection reads the **caller's** turns only, matching phrasings like *"speak to
a person"*, *"put me through"*, *"real person"*, *"operator"*.

## Recording

Call recording carries a consent requirement through `audio_policy.gate()` like
any other recording, and `DEFAULT_POLICY` has `allow_call_recording` **off**.

## Files

| File | Role |
| --- | --- |
| `audio_agent.py` | Schema, guardrails, profile lifecycle, session derivation. |
| `audio_desk.py` | Routes, on the Desk's blueprint. |
| `templates/desk/agents.html`, `desk/agent_session.html` | The two pages. |
| `tests/test_audio_agent.py` | 40 tests. |

## What is not built

The live call itself. Profiles, guardrails, sessions, transcripts, disclosure
derivation and escalation are real and tested; placing or receiving an actual
call needs the vendor's agent platform and a key, and none of that has been
exercised against a live account. The mock adapter returns a scripted
conversation, and every session it produces is labelled *scripted demo, no call
was placed*.
