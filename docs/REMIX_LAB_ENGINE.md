# Remix Lab, connected (`/remix-lab`)

The page shipped saying *"generation is not yet connected"*, and it was right
to. A remix brief that opens **"original sits around 92 BPM in A minor"** needs
somebody to have listened to the record, and inventing that number is the most
damaging fake available here — a producer would act on it.

The audio seam can now measure part of it. `MusicProvider.composition_plan()`
reports **tempo, section boundaries and an energy curve** for a track the artist
owns. That is a measurement, not an opinion.

## Three sources, and every line says which it is

| Source | What it means | Example |
| --- | --- | --- |
| `measured` | From the provider's plan | *"128 BPM measured."* |
| `convention` | What this kind of edit usually does — **not** a reading of this record | *"For a club edit that usually means a 16-bar mixable intro…"* |
| `chosen` | The artist's own selections on the page | *"You chose high energy, hook-first vocal treatment…"* |
| `unknown` | Nothing came back | *"Tempo was not measured for this track."* |

The brief page renders the source as a badge beside every heading, because a
producer needs to know which lines are about *their* record.

`brief_is_grounded()` answers whether a brief rests on anything measured at all.
A brief made only of conventions and selections is still useful — but it is not
a reading of their record, and the page says so instead of implying otherwise.

## What it still will not say

* **No key.** The plan does not carry one, and guessing would send a producer
  to the wrong pitch shift.
* **No musical judgement.** *"The pre-chorus already builds like a riser and the
  hook lands on the one"* is a call about a specific record, and nothing here
  can make it.
* **No claim that it listened.** It read a plan. The page states this outright.

Tests assert the absence of both the key pattern and the judgement phrasings.

## The server-side screen, finally honoured

`remix_lab_config.check_reference_text()` shipped with a note calling itself
*"the authoritative copy the server must call before any generation request
leaves the building"*, with the browser copy as convenience only.

`/remix-lab/brief` runs it on **every reference line first** — before the upload
is read, before an asset exists, before anything is spent. A refusal quotes the
exact phrase that stopped it and offers the allowed shapes, because a refusal
that will not say which words tripped it leaves somebody editing at random.

## The flag that gated nothing

`REMIX_LAB_AUDIO_ENGINE_ENABLED` was declared in `audio_policy.FLAGS` and
**checked by nothing**. An operator could set it and watch nothing happen —
the same dead-switch class as the `ELEVENLABS_VERIFIED` variable removed
earlier.

It now gates the `remix_plan` feature. That feature *analyses* and generates
nothing, which is deliberate: Remix Lab runs without music generation switched
on, and costs a plan rather than a generation.

> Three flags still gate nothing: `VOICE_CLONING_ENABLED`,
> `ZERO_RETENTION_REQUIRED` and `WHITE_LABEL_AUDIO_OPERATOR_ENABLED`. The last
> is a placeholder for an unbuilt product; the first two look redundant against
> `ARTIST_VOICE_VAULT_ENABLED` and the policy's `require_zero_retention`. Not
> touched here — flagged rather than silently removed.

## The page tells the truth in both states

`engine_live()` checks **both** flags, because `audio_policy.gate()` does. A
page offering a real button the gate would refuse is worse than one honestly
saying it is a preview.

* **Engine off** — the form has no `action` and stays exactly the preview it
  always was; the note still says generation is not connected.
* **Engine on** — the form posts, and the note describes what is actually
  measured.

The `/remix-lab` page itself stays **public**. The brochure, the rights gate and
the likeness screen are what a visitor needs to judge the tool, and none of that
needs a login. Running a brief does.

## Storage

Uploads go to the bucket under `studio/` when configured, a private directory
otherwise — never the public uploads tree. Retention comes from the tenant's
own policy. Both rights confirmations are required server-side, not only in the
browser.

## Files

| File | Role |
| --- | --- |
| `remix_lab_engine.py` | `compose_brief()` — no I/O, testable directly. |
| `remix_lab_config.py` | `engine_live()`, the pattern list, the two notes. |
| `app.py` | `/remix-lab/brief` — the screen, the gate, the upload, the compose. |
| `templates/remix_lab_brief.html` | The brief, with a source badge per line. |
| `templates/remix_lab_refused.html` | The refusal, quoting what stopped it. |
| `tests/test_remix_lab_engine.py` | 24 tests. |

## A test-isolation note worth keeping

The module fixture switches the engine on by writing `os.environ` and **puts it
back afterwards**. Without the restore it leaked into `test_remix_lab.py`, whose
page-note assertion is now conditional on those flags — so the suite passed or
failed depending on the order the files happened to run in. Both orders are now
verified.
