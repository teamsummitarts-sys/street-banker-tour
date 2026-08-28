# Audio Intelligence — operations

Everything here is **off by default**. A deployment gets the audio surface
deliberately, never by upgrading. With nothing set, the app boots, the mock
adapters serve every capability, and no audio leaves the machine.

## What you need before switching anything on

| # | Item | Where it comes from | Blocking? |
| --- | --- | --- | --- |
| 1 | `ELEVENLABS_API_KEY` | elevenlabs.io → profile → API keys | Yes, for anything real |
| 2 | Webhook signing secret | elevenlabs.io → webhooks, when a webhook is created | Only for slow work (dubbing, agents) |
| 3 | Public HTTPS URL for the webhook | `https://street-banker.onrender.com/webhooks/audio/elevenlabs` | Only for slow work |
| 4 | Written zero-retention confirmation | ElevenLabs sales — it is an **enterprise-only** mode | Only if a tenant requires it |
| 5 | A spend cap on the vendor account | elevenlabs.io billing | Strongly recommended |

> **Do not paste the key into this repo, a template, or a client-side file.**
> Set it in Render → Environment. The adapter reads it server-side only, and
> nothing serialises it to a page.

### On item 4

`enable_logging=False` is how zero retention is requested, and the SDK's own
documentation says the mode "may only be used by enterprise customers". The
adapter therefore refuses to *claim* zero retention on the strength of a key
alone: `ELEVENLABS_ZERO_RETENTION_VERIFIED` must be set by an operator who has
confirmed it for that account. If a tenant's policy requires zero retention
and that flag is unset, jobs are **refused, not downgraded**.

## Environment variables

### Credentials — never client-side

| Variable | Effect |
| --- | --- |
| `ELEVENLABS_API_KEY` | The key. Empty ⇒ the adapter reports `unconfigured` and the mock is used. |
| `ELEVENLABS_WEBHOOK_SECRET` | Signing secret for `/webhooks/audio/elevenlabs`. Absent ⇒ the endpoint is **404**. |
| `ELEVENLABS_ZERO_RETENTION_VERIFIED` | Operator's assertion that the account has the enterprise mode. |

### Master switches

| Variable | Effect |
| --- | --- |
| `AUDIO_INTELLIGENCE_ENABLED` | The umbrella. Unset ⇒ every audio feature refuses and the webhook 404s. |
| `ELEVENLABS_ENABLED` | Register the real adapter. Unset ⇒ mock only. |

### Per-feature flags

Each is checked *after* the umbrella, so both must be on.

`MEETING_INTELLIGENCE_ENABLED`, `SIGNAL_AUDIO_BRIEFS_ENABLED`,
`AUDIO_OPERATOR_ENABLED`, `GLOBAL_RELEASE_PACK_ENABLED`,
`CAMPAIGN_AUDIO_TOOLKIT_ENABLED`, `REMIX_LAB_AUDIO_ENGINE_ENABLED`,
`ARTIST_VOICE_VAULT_ENABLED`, `WHITE_LABEL_AUDIO_OPERATOR_ENABLED`,
`DUBBING_ENABLED`, `MUSIC_GENERATION_ENABLED`, `MUSIC_INPAINTING_ENABLED`,
`STEM_SEPARATION_ENABLED`, `VOICE_ISOLATION_ENABLED`,
`SOUND_EFFECTS_ENABLED`, `VOICE_CLONING_ENABLED`, `ZERO_RETENTION_REQUIRED`

### Model pinning

| Variable | Default |
| --- | --- |
| `ELEVENLABS_STT_MODEL` | `scribe_v2` |
| `ELEVENLABS_TTS_MODEL` | `eleven_multilingual_v2` |

Pinned in the environment rather than the code so a model deprecation is a
settings change, not a deploy. Model ids move; do not hardcode new ones
without checking the vendor's current list.

## Turning it on, in order

1. **Nothing set** — confirm the app boots and `/admin` shows every capability
   as `mock`. This is the state the whole test suite runs in.
2. **`AUDIO_INTELLIGENCE_ENABLED=1`** and one feature flag. Still mock: you are
   testing the gate, not the vendor.
3. **`ELEVENLABS_API_KEY`** — health should flip from `unconfigured` to `ready`
   only after a real call succeeds. A key alone never reports healthy.
4. **`ELEVENLABS_ENABLED=1`** — the real adapter is now selectable.
5. **Webhook** — create it at the vendor, set `ELEVENLABS_WEBHOOK_SECRET`, then
   confirm a delivery reaches `processed` (see below).

Roll back by unsetting `ELEVENLABS_ENABLED`. Work falls back to the mocks;
nothing in the schema changes.

## Where to look

`/admin/audio` — owner only, linked from the sidebar for accounts that can
open it. Every state below is shown there, alongside jobs, webhook
deliveries, usage and anything past its retention date. Start there before
reading logs.

## Health states

| State | Meaning |
| --- | --- |
| `mock` | Offline adapter. Nothing leaves the machine. |
| `unconfigured` | No key, flag off, or the SDK is not installed. The detail line says which. |
| `ready` | A real call to the vendor succeeded **in this process**. |
| `degraded` / `error` | Reachable but unhappy, or a transport failure. |

`verified_live` is set only by a call that actually succeeded. A key in the
environment is not evidence of anything.

## Checking a webhook is wired

```bash
curl -i -X POST https://street-banker.onrender.com/webhooks/audio/elevenlabs -d '{}'
```

| You get | It means |
| --- | --- |
| `404` | The feature is off, or no signing secret is set. Both are indistinguishable on purpose. |
| `401` | Reachable and verifying. This is the healthy answer to an unsigned probe. |
| `200` | Something signed it. If you did not, investigate. |

Deliveries — including rejected ones — are recorded in `audio_webhook_events`,
so a run of bad signatures is visible to a person rather than only in a log.

## Costs

Nothing here hardcodes vendor pricing; the usage ledger records **units**
(characters, milliseconds), not money, and `final_cost` stays NULL unless the
vendor reports one. Set a spend cap at the vendor — the app's budget check is
supplied by the caller and is not a substitute for one.

Usage is recorded for mock jobs too, with a null cost. A ledger with rows only
when a vendor was involved cannot answer "what did this artist actually use".

## Retention and deletion

`audio_assets.retention_expires_at` drives cleanup; `expired_assets()` lists
what is due and `mark_asset_deleted()` records the removal. Recording and
cloning are **off** in `DEFAULT_POLICY` and must be switched on per tenant.

Consent is a row, not a boolean — who, when, against which policy version, and
the exact text they were shown — because the question asked later is "what
exactly did they agree to", and a boolean cannot answer it.

## Things that will bite

* **A key is not health.** Do not gate UI on the key being present; ask the
  adapter.
* **Zero retention is refused, never downgraded.** If a tenant requires it and
  the flag is unset, the job does not run. That is the intended behaviour.
* **The webhook is on a public prefix.** `/webhooks/` skips the login wall by
  design. Do not add an audio route under it that assumes a session.
* **A refusal is terminal.** `rejected` jobs are never retried. If you see
  them piling up, the provider is saying no for a reason worth reading.
* **Model ids move.** Pin them in the environment and check the vendor's
  current list before changing one.
