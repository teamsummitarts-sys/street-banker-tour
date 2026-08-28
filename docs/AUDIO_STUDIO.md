# Audio Studio (`/audio-studio`) — phases 4, 5 and 6

Four products, one engine:

| Lane | Phase | What it does |
| --- | --- | --- |
| Global Release Pack | 4 | Dub a release into other languages |
| Campaign Audio Toolkit | 4 | Voiceover and sound effects for a campaign |
| Remix Lab Audio Engine | 5 | Stem separation and voice isolation |
| Artist Voice Vault | 6 | Register a voice its **owner** verified |

## Why one engine and not four modules

They are the same act with different verbs — take audio somebody owns, confirm
they own it, run one gated operation, keep what came back. Four near-identical
modules would drift, and the one that drifts is the one that forgets the rights
check.

`audio_works.submit_work()` is the only path to a provider, and it runs four
things in a fixed order:

1. does the item exist
2. **the likeness screen**, on the brief the person typed
3. **rights**, recorded against this item
4. `audio_policy.gate()`, which does the other ten

The cheap refusals come first. Screening before rights matters: both refuse,
but if rights answered first, somebody would fix the rights box and only then
discover the real problem.

## The likeness screen

`remix_lab_config.check_reference_text()` shipped with a note saying the server
must call it before any generation request leaves the building, and that the
browser copy is convenience rather than enforcement. **This is where that gets
honoured** — and for every lane, not only Remix Lab.

Refusing an imitation request is not squeamishness. A brief saying *"same voice
as \<a real singer\>"* is a request to imitate a specific person, and that
person has no say in it at the moment it is typed. So the answer is no, and the
item shows the phrase that stopped it plus what to write instead.

### A gap that was closed

The list banned *"in the style of \<name\>"* but not *"\<name\> type beat"* —
the same request, phrased the way somebody in this industry actually types it.
Screening one and not the other screens the wording, not the ask. The pattern
is now in the shared list, which reaches the browser unchanged (a test asserts
the two copies cannot drift).

It also catches genre uses like *"trap type beat"*. That is deliberate and
consistent with the entry above it, which refuses *"in the style of"* whatever
follows. The warning says what to write instead, and *"trap-influenced, 140 bpm,
sparse hi-hats"* is a better brief anyway.

> The repo rule that **no real artist is named anywhere** — "not in the copy,
> not in the examples, not even as what to avoid" — applies to comments and
> test cases too. A test caught a real name in an explanatory comment while
> this was being written.

## Rights are per work item

`rights_confirmed`, `rights_confirmed_by`, `rights_confirmed_at` live on the
work item. *"I own my catalogue"* ticked once at signup is not a claim about
the file somebody uploaded this afternoon.

`confirm_rights()` is deliberately a separate call from `create_work()` — the
confirmation is an act a person performs, and a default argument on a
constructor is not one.

## The Voice Vault is different

Every other lane processes a recording. The Vault registers a **voice**, which
is a person.

Street Banker never holds the voice model. It records a reference to one the
owner verified through the vendor's own process, plus the permission record
around it. **A manager cannot register an artist's voice**, and three
independent layers enforce that:

1. `ARTIST_VOICE_VAULT_ENABLED` is unset by default → `disabled`
2. `allow_voice_cloning` is **off** in `DEFAULT_POLICY` → `policy_off`
3. the consent gate wants the owner's verification → `owner_consent_required`

The **mock adapter refuses too**, so the calling code meets that path in
development rather than in production.

## A lane is only "available" if the gate would allow it

The lane flag alone is not enough. `CAMPAIGN_AUDIO_TOOLKIT_ENABLED` advertises
the campaign lanes, but sound effects gate on `SOUND_EFFECTS_ENABLED`, and
reading only the lane flag showed **available** on a lane that then refused
every submission.

That is a worse failure than showing it off: the artist writes a brief, presses
the button, and is told no for a reason that has nothing to do with what they
typed. `_on()` now consults the flag `audio_policy.FEATURES` will actually
check, and the page names **every** flag a lane needs.

Every lane is listed even when off, so an artist can see what the product does
before an operator switches on anything that costs money.

## Storage and privacy

Uploads go to the bucket under `studio/` when configured, a private directory
otherwise — **never the public uploads tree**. A master uploaded to be split
into stems is the most valuable file an artist owns.

Another account asking for a work item gets **404, not 403**: they should not
learn it exists. Deleting an item destroys the audio uploaded for it.

## Files

| File | Role |
| --- | --- |
| `audio_works.py` | The work item, the screen, and the one submit path. |
| `audio_studio.py` | Routes and lane definitions. |
| `templates/audio_studio*.html` | Three pages, component library only. |
| `tests/test_audio_studio.py` | 27 tests. |

## What is not built

Real output files. The mock adapters return correct shapes and **no audio** for
stems, dubbing and isolation — deliberately, since a demo that produced
something audible would be mistaken for the real thing, and the item page says
so. Wiring real outputs needs a provider key that has never been exercised.
