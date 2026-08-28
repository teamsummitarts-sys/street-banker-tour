# Meeting Intelligence (`/operator-desk/meetings`)

A recording becomes a transcript with speakers and timestamps. The transcript
is then read for phrases that usually mean somebody committed to something,
and those become suggestions a person approves.

> **It does not understand the meeting.** The audio seam supplies audio
> capabilities — transcription, speech, agents. There is no language-reasoning
> provider behind it, and an extractor that claimed to know what was *decided*
> would be inventing the most consequential part of the record.

## What is real and what is a guess

| Step | How it works |
| --- | --- |
| Transcript, speakers, timestamps | Real, from the transcription provider |
| Candidate extraction | **Deterministic regex over phrasing** |
| Task or note on a lead | Only when a person approves it, under their name |

Every candidate carries the exact sentence it came from, the speaker, and the
millisecond it was said, because a suggestion you cannot check against the
recording is one you have to take on faith.

The reason shown is written to be readable — *"somebody said they would"*,
*"a next step was named"*. Not a confidence score: `0.82` is not checkable by
the person being asked to trust it.

## The rules

Each rule is `(kind, human-readable reason, pattern)` in `audio_meetings._RULES`.
Four kinds: `action`, `decision`, `risk`, `date`.

**Order is load-bearing.** First match wins, and action rules come first
deliberately. *"We agreed that I will send the contract by Friday"* is both a
decision and an action; classifying it as an action is what puts a task in
front of somebody. Reordering the list changes what a meeting produces.

Measured against the ten mock transcript lines: **7 matched, 3 skipped** — and
all three skips are correct (a pleasantry and two statements of fact). It stays
silent on small talk, dedupes a repeated sentence, and yields at most one
candidate per sentence.

It **will** miss commitments phrased unusually and **will** pick up sentences
that are not commitments. That is why nothing reaches a lead without approval.

### One gap worth knowing about

Transcription engines expand contractions inconsistently. The rules match both
`let's` and `let us` for this reason — the unexpanded form is the one a
hand-written regex forgets, and a missed next step is a task nobody was offered.

## Consent

Recording a meeting is the only audio operation in this product that involves
people who are not the user.

* `meeting_recording` carries a consent requirement through
  `audio_policy.gate()`, and `DEFAULT_POLICY` has it **off**.
* `meeting_intelligence` (a file the operator already holds) is a separate
  feature, because uploading a recording you have is a different act from
  recording a live conversation.

The upload form's checkbox says what it means — *"everyone recorded knew they
were being recorded, and that it may be transcribed by a third-party
provider"* — rather than hiding behind "I agree to the terms". A meeting
without it recorded shows **no recording consent was recorded** on its page.

## Storage and retention

Audio goes through the Desk's own `_save_desk_file`: the bucket when
configured, a private directory otherwise, **never the public uploads tree**.
The retention clock starts at upload, not at transcription — the bytes exist
from then.

Deleting a meeting destroys its audio. Approved tasks and notes stay where
they are; they are the operator's record now, not the meeting's.

## Costs

Transcription is charged per minute. Pressing *Transcribe* twice does not
transcribe twice — the job carries `idempotency_key="meeting:<id>"` — and
re-running the harvest does not double the review queue.

## Files

| File | Role |
| --- | --- |
| `audio_meetings.py` | Schema, the rules, the extractor, approval records. |
| `audio_desk.py` | Routes, registered onto the Desk's own blueprint. |
| `templates/desk/meetings.html`, `desk/meeting.html` | The two pages. |
| `tests/test_audio_meetings.py` | 18 tests. |

`audio_desk.register()` runs **at most once per process**. The Desk blueprint
is a module-level singleton and `app.py` builds an app at import, so a second
`create_app()` — which every test wanting a clean app does — would otherwise
try to add routes to a blueprint Flask has already registered, and Flask
refuses. The Desk's own routes sidestep this by being declared at import time;
these cannot be, because they need the guard passed in.
