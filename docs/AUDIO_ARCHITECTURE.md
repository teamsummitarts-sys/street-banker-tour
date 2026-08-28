# Street Banker Audio Intelligence — architecture

Transcription, speech, conversational agents, dubbing and generative audio,
behind one seam. The vendor supplies the audio capability; Street Banker
supplies the music-industry judgement around it — rights, consent,
relationships, approval, billing, and the record of who decided what.

> The vendor is infrastructure and must stay replaceable. Nothing in the
> domain is named after one, and the app runs, demos and passes its whole
> test suite with no vendor, no key and no network.

## Stack ruling

The originating brief specified provider-agnostic TypeScript interfaces. The
same ruling as Signal applies: this app is Flask + Jinja2 + SQLite with
hand-written SQL. Interfaces became `abc` base classes; the job queue became
a table plus a poller; webhooks became one signed Flask route.

**One dependency was added** — `elevenlabs==2.65.0` — the first heavy one in
this repo. See [Why the SDK](#why-the-sdk-and-not-urllib).

## Files

| File | Role |
| --- | --- |
| `audio_providers.py` | Nine capability base classes, the registry, request shapes. |
| `audio_mock.py` | Nine complete offline adapters. Demo mode is this file. |
| `audio_elevenlabs.py` | The real adapter, env-gated, written against SDK 2.65.0. |
| `audio_policy.py` | `gate()` — the ten checks, in a fixed order. |
| `audio_store.py` | Schema, migrations, policy, consent, jobs, usage, transcripts. |
| `audio_jobs.py` | `submit()` / `poll()` — the only way work reaches an adapter. |
| `audio_webhooks.py` | The signed inbound edge for work that finishes late. |
| `audio_retention.py` | The sweep that makes the retention numbers true. |
| `audio_admin.py` | `/admin/audio` — the operator's window. Owner-gated. |
| `templates/audio_admin.html` | That page. Component library only, no bespoke CSS. |
| `tests/test_audio_jobs.py` | Gate, runner and schema, against real databases. |
| `tests/test_audio_webhooks.py` | Signature, dedup, tenancy, over real HTTP. |
| `tests/test_audio_retention.py` | Destruction, and never lying about it. |
| `tests/test_audio_admin.py` | Access, credential non-leakage, safe defaults. |

**Phase 2 — the first two products above the seam:**

| File | Role |
| --- | --- |
| `audio_meetings.py` | Meeting schema, the extraction rules, approval records. |
| `audio_desk.py` | Meeting routes, on the Operator Desk's own blueprint. |
| `audio_briefs.py` | Brief schema and `compose_script()` — no I/O, testable directly. |
| `audio_signal.py` | Brief routes, on Signal's own blueprint. |
| `tests/test_audio_meetings.py` | 18 tests. See `AUDIO_MEETING_INTELLIGENCE.md`. |
| `tests/test_audio_briefs.py` | 15 tests. See `AUDIO_SIGNAL_BRIEFS.md`. |

## The shape

```
caller  ->  audio_jobs.submit()
                |
                +-- audio_policy.gate()      ten checks, cheapest first
                |        refused -> Decision with a reason, NO job row
                |
                +-- audio_store.create_job() idempotent per (tenant, key)
                |
                +-- adapter.<verb>()         the only place this is called
                |
                +-- audio_store.record_usage()   always, mocks included
                |
                v
        fast work  -> completed here
        slow work  -> stays running; audio_jobs.poll() or a webhook settles it
```

### The gate is one function on purpose

Ten separate checks spread across ten call sites is how a repo ends up with
nine of them applied. `gate()` runs: feature flag, tenant entitlement, tenant
toggle, provider entitlement, seat permission, budget, consent, rights,
retention, provider health — in that order, so an unentitled request never
costs a database round trip, and the provider is asked last because it is the
only check that can be slow.

It returns a `Decision` rather than raising. A refusal is something a person
reads: each carries a code the UI can branch on and a sentence saying what
would make it pass, because `403` tells an artist nothing about the consent
box they did not tick.

### A refused request creates no job row

It cost nothing and sent nothing, so it is not in the ledger.

### Refusal is not failure

| Adapter raises | Job status | Retried? | Why |
| --- | --- | --- | --- |
| `ProviderRefusal` | `rejected` | Never | The provider decided. Retrying spends money to hear the same answer. |
| `ProviderUnavailable` | `queued` | Up to 3 | The vendor was unreachable, which is a condition that passes. |
| anything else | `failed` | Never | An adapter bug must not masquerade as a vendor outage. |

### The zero-retention rule

If a tenant requires zero retention and the adapter cannot prove it supports
it *for this account*, the answer is no. Not a downgrade, not a warning, not a
job that runs anyway with a flag set. Telling somebody their audio was never
stored when it was is the one mistake here with no remedy.

`supports_zero_retention()` returns `False` by default and the ElevenLabs
adapter refuses unless `ELEVENLABS_ZERO_RETENTION_VERIFIED` is set — the SDK's
own documentation restricts the mode to enterprise accounts, so it cannot be
inferred from a key alone.

## The inbound edge

`/webhooks/audio/<provider>` is under `/webhooks/`, an existing **public**
prefix — the login wall does not stand in front of it, because the vendor
calling it has no session. Everything protecting it is in the route:

1. **404** unless the feature is on *and* a signing secret is configured. An
   endpoint that answers differently when a feature is off tells a stranger
   what is deployed here.
2. **Signature over the raw body**, before anything is parsed. A payload that
   has been JSON-decoded and re-encoded is no longer the bytes that were
   signed.
3. Only then is the event recorded, and only then acted on.

The body never says which tenant it belongs to. The job is looked up by
`(provider, provider_job_id)` — both values we issued or recorded — and the
tenant comes from our own row. A webhook that could nominate its own
`partner_id` could write into any tenant on the instance.

Once a signature is good the route returns **200 even on a processing
failure**. A signed event we could not handle is our problem; a 500 makes the
vendor retry forever on a schedule we do not control. The failure is stored
with its reason and surfaces in admin instead.

## Schema notes worth knowing before you add a table

### `_pk()` — SQLite NULLs defeat key constraints

SQLite treats NULLs as *distinct* in `PRIMARY KEY` and `UNIQUE`. A NULL tenant
key silently defeats both. This module found that the hard way: every policy
write for the default tenant inserted a fresh row, `ON CONFLICT` never fired,
and the read picked the oldest — **a policy change that appeared to save and
did nothing**.

Anything used as a *key* passes through `_pk()`, which writes `''` for Street
Banker itself. Scoping *predicates* still use `partner_id IS ?`, which handles
NULL correctly.

### Partial unique indexes, not whole-column `UNIQUE`

Two tables have a key column with `DEFAULT ''`: `audio_jobs.idempotency_key`
and `audio_webhook_events.external_event_id`. Neither is always supplied.
Under a whole-column `UNIQUE`, every row that omits the key collides with the
first one that did:

* **jobs** — the second brief a tenant submitted raised `IntegrityError`.
* **webhooks** — genuinely different events from a vendor that sends no
  delivery id were reported as duplicates and **silently never processed**.

Both are now `CREATE UNIQUE INDEX ... WHERE <col> != ''`, which keeps the real
guard and drops the false collision.

### `CREATE TABLE IF NOT EXISTS` is not a migration

It does nothing at all to a table that already exists, so a column added to
the statement never reaches a database initialised before it. Structural
changes go in `_migrate()`, which **returns the list of steps it applied**.

That return value is not a convenience — it is the only honest way to test
whether a migration ran. SQLite reuses freed page numbers after a drop and
rename, so a table's `rootpage` can be identical either side of a full
rebuild. The first version of that test watched `rootpage` and passed against
code that rebuilt the table **on every single boot**.

For the same reason, the rebuild trigger matches on the *columns* an
auto-index covers, never on its name looking auto-generated: `id TEXT PRIMARY
KEY` produces one of those on every table.

## Why the SDK and not `urllib`

`stemsplit_provider.py` hand-rolls `urllib` and says so — it needed three
stateless REST calls, and that was the right call for that job. Audio
Intelligence needs `conversational_ai.agents/conversations/knowledge_base/
tools` and `music.compose/upload/separate_stems/inpaint`: stateful,
deeply-typed, multi-step, actively changing. Hand-rolling that means
re-deriving a vendor's schema every time they ship.

Measured before deciding:

| | |
| --- | --- |
| Added to the image | **33.5 MB** across 15 packages |
| Native compilation | **None** — `pydantic-core` ships manylinux wheels |
| `pyaudio` | Behind an `extra`; a plain install never fetches it, so no PortAudio headers are needed on Render |

It is **pinned**, unlike the other six dependencies, because the adapter is
written against 2.65.0's real method signatures and an unpinned major would
land on the next deploy with no commit of ours to blame.

It is **optional at runtime**: `bootstrap()` catches the import error and
leaves the mocks registered. An install without it boots, demos, and reports
`unconfigured` — verified by blocking the import at the meta-path level and
confirming every capability still resolves.

## What is real, and what is not

| Surface | State |
| --- | --- |
| Provider seam, registry, health | Real |
| Nine mock adapters | Real, deterministic, offline |
| Gate — flags, entitlement, consent, rights, retention, budget | Real |
| Job runner, idempotency, usage ledger | Real |
| Signed webhook edge, dedup, tenancy | Real |
| Retention sweep | Real |
| Operator admin page | Real |
| ElevenLabs adapter | Written against the real SDK; **not yet exercised against a live key** |
| Meeting Intelligence (phase 2) | Real — extraction is rule-based, not understood |
| Signal Audio Briefs (phase 2) | Real — script composed from rows, never generated |
| Operator Voice Agent (phase 3) | Profiles, guardrails, sessions and escalation real. **The live call is not built.** |
| Global Release Pack, Campaign Toolkit, stems/isolation (phases 4–5) | Real, at `/audio-studio` |
| Remix Lab engine | Real — measures tempo, sections, energy. See `REMIX_LAB_ENGINE.md` |
| Artist Voice Vault (phase 6) | **Cannot complete.** See below |
| White-Label Audio Operator | **Not built.** A flag and nothing else |

The mock adapters return well-formed results so the products can be built and
tested without a key, a network or a bill, and every result carries
`is_mock=True` so nothing here can be mistaken for a real transcription of real
audio.

### The Voice Vault cannot complete, and the lane is switched off

`gate()` requires a recorded `voice_owner` consent before a voice may be
registered. **`audio_store.record_consent()` has no caller anywhere in the
app** — so the Vault would advertise itself, accept a submission, create a work
row, and refuse every single time.

A lane that can never complete must not read as available, so
`audio_studio._CONSENT_FLOW_MISSING` holds it off and the page says the real
reason rather than naming a flag that would change nothing. Remove the key from
that set the moment an owner-verification route exists that calls
`record_consent`.

The same gap applies in principle to `recording` and `agent_disclosure`
consent, neither of which any route records either. Those are not currently
reachable — meeting uploads gate on `meeting_intelligence`, not
`meeting_recording` — but a route that starts using either feature key will hit
the same wall.

### Three flags gate nothing

`WHITE_LABEL_AUDIO_OPERATOR_ENABLED`, `VOICE_CLONING_ENABLED` and
`ZERO_RETENTION_REQUIRED` appear in `FLAGS` and are checked by no code. An
operator could set one, see `/admin/audio` report it **on**, and nothing would
change — which is worse than an absent switch. That page now lists them under
*"declared but wired to nothing"* rather than beside the real ones.

## The operator's window

`/admin/audio`, owner-gated on the same hashed-email predicate as every other
internal surface, and offered in the sidebar only to accounts that can open it
— a link that answers 404 is worse than no link.

It shows the serving adapter per capability (not per *adapter*: the raw health
report renders as nineteen rows carrying the same sentence nine times, which
buries the only question an operator has), every feature flag, which
credentials are **set** — never their values — recent jobs with the reason a
rejected one was refused, webhook deliveries including the rejected ones, the
usage ledger in units, and what is past its retention date.

Two buttons touch real state. `Advance waiting jobs` polls anything still
running. `Preview a sweep` never passes `confirm`, so pressing the wrong
button cannot destroy anything; only `Destroy expired audio` asks, and only
after saying how many assets it is about to remove.

## Products register onto the host's blueprint, never their own

Meeting Intelligence lives on the Operator Desk's blueprint; Audio Briefs live
on Signal's. Each inherits the host's guard, roster check and denied page.

A second permission system beside the first is how two of them end up
disagreeing — and the one that disagrees quietly is the one that leaks.

Both `register()` functions run **at most once per process**, because these
blueprints are module-level singletons and `app.py` builds an app at import.
A second `create_app()` would otherwise try to add routes to an
already-registered blueprint, which Flask refuses.

## Where the honesty line falls

Two products, two different answers to "can we claim this":

* **Meetings** — the transcript is real; the extraction is regex over phrasing
  and says so, with the source sentence attached and a human approving before
  anything is written.
* **Briefs** — the script is assembled from rows by a template, so every
  sentence traces to data. Nothing is summarised, because a summary is a claim.

Neither product has a language model behind it, and neither pretends to.
