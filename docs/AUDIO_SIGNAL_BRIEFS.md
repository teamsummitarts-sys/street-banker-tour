# Signal Audio Briefs (`/signal/briefs`)

The week's Signal alerts, read aloud.

> **Every sentence is assembled from alert rows by a template.** Nothing in a
> brief is generated, inferred or summarised. Each number and name is read
> straight out of the database.

## Why that rule is stricter here than anywhere else

A brief is listened to while driving. Nobody cross-checks a voice, and a spoken
number carries more authority than the same number on a screen — so a brief
that smoothed over a gap in the data would simply be believed.

## What it says when there is nothing to say

It says so:

> *Nothing crossed an alert threshold in that window. That is not the same as
> nothing happening, so the dashboard is still worth a look.*

Two deliberate choices there. Silence is a bug the listener cannot tell apart
from a broken player, so the brief is always produced. And "no alert" is not
"no activity" — claiming otherwise would be a conclusion the data does not
support.

## Composition rules

| Rule | Why |
| --- | --- |
| Grouped critical → warning → info | The order somebody needs them in |
| Artist name leads each sentence | That is what a listener is holding in their head |
| A body that restates its title is dropped | A voice repeating itself is how attention is lost |
| Above 8 items it counts instead of listing | A spoken list of forty artists is noise with a number in it |
| Always ends `End of brief.` | So the listener knows the file did not cut off |

`compose_script()` is deterministic and total: the same rows always produce the
same script, and a script is always produced.

## The script is kept beside the audio

Audio cannot be skimmed, searched or quoted, and cannot be checked against its
source without listening to all of it. Every brief stores its exact script, and
the page shows it.

## Mock briefs are silent on purpose

With no provider configured, the speech adapter returns a correctly-formed WAV
of **silence**, the length the script would take to read — not a tone, not a
stock voice. A demo that plays audible speech gets mistaken for a working one,
and somebody eventually plays it to a client.

The page says so **above the player**, because somebody who presses play and
hears nothing needs to already know why.

## Privacy

A brief names the artists an organisation is watching and says why. That is its
strategy, read aloud.

* Stored outside the public uploads tree — the bucket under `briefs/` when
  configured, a private directory otherwise.
* Served through `/signal/briefs/<id>/audio`, which re-checks the Signal seat
  on **every** request. It is deliberately not a URL that works for anyone
  holding it.
* A non-member gets 403; a signed-out visitor never reaches it.
* Audio past its retention date returns **410**, not a 500 — it was destroyed
  on purpose and the page should say so.

## Costs

Writing a brief is free — it only reads the database. Turning one into speech
is charged per character, so a brief renders **once**: the job carries
`idempotency_key="brief:<id>"`, and the script cannot change after it is
written.

## Files

| File | Role |
| --- | --- |
| `audio_briefs.py` | Schema and `compose_script()`. No I/O in the composer, so it is testable directly. |
| `audio_signal.py` | Routes, registered onto Signal's own blueprint. |
| `templates/signal/briefs.html`, `signal/brief.html` | The two pages. |
| `static/css/signal.css` | `.sg-script` — monospaced and pre-wrapped, because the line breaks are where the voice pauses. |
| `tests/test_audio_briefs.py` | 15 tests. |
