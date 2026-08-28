# Integration Map

Every external dependency, what gates it, and what happens when it is
absent. Nothing here fabricates a result when unconfigured — that rule is
load-bearing, and this document exists partly to keep it honest.

## Live integrations

### StemSplit — `stemsplit_provider.py`
**Gate:** `STEMSPLIT_API_KEY` · **Absent:** Studio Split hidden entirely

Demucs-class stem separation. Five modes, discovered by asking the API
rather than reading docs — an invalid `outputType` makes it name the
valid ones: `VOCALS`, `INSTRUMENTAL`, `BOTH`, `FOUR_STEMS`, `SIX_STEMS`.

Two behaviours worth knowing:

- **`outputFormat` does nothing.** The job body echoes `"MP3"` back and
  every output URL ends `.wav`. The stem container follows the *source*
  container. Measured both ways: WAV in → 5.05 MB WAV stems, MP3 in →
  1.15 MB MP3 stems.
- **A job can report `COMPLETED` before its URLs exist.** `job_status`
  holds it open for up to 90s rather than handing back a finished split
  with nothing to download.

Credits are deducted at submission. A rejected job costs nothing —
verified by balance before and after.

### Resend — `email_provider.py`
**Gate:** `RESEND_API_KEY` · **Absent:** no sends; reset and drop flows
still complete, they simply do not deliver

`EMAIL_FROM` still points at `onboarding@resend.dev`, the shared test
sender. A verified sending domain is outstanding — until then deliverability
is whatever a shared sandbox domain gets. `/mail/diag?domains=1` reports
the real state.

### Stripe — `stripe_provider.py`
**Gate:** `STRIPE_SECRET_KEY` · **Absent:** checkout disabled, plans read-only

Subscriptions and fan-club checkout. Webhook setup is available from
inside the app. Test keys behave identically; only the money differs.

### Spotify — `spotify_provider.py`
**Gate:** Spotify OAuth env vars · **Absent:** Artist Pulse empty, presave
falls back to notify-me

Feeds `pulse_snapshots` (popularity, followers) into the qualification
score's Streaming Momentum category.

### Bandsintown — `bandsintown_provider.py`
**Gate:** artist ID on the EPK · **Absent:** no tour dates on the press kit

Read-only, cached in `api_cache`.

### S3-compatible backup — `backup_store.py`
**Gate:** `BACKUP_S3_ENDPOINT/BUCKET/KEY/SECRET` · **Absent:** no off-box copy

SigV4 implemented in pure Python — no boto3. `/backup/run` is exempt from
the login wall via `BACKUP_TOKEN` so a cron job can reach it.

### ffmpeg — `convert_engine.py`
**Gate:** binary on `PATH` · **Absent:** WAV and AIFF only, in-browser

Present on the Render instance with `libmp3lame`, `flac`, `alac`, `aac`,
`libopus`, `libvorbis`. Nothing user-typed reaches the command line:
every codec, bitrate, rate and channel count is looked up in a table and
passed as its own argv entry.

Opus accepts only 8/12/16/24/48 kHz. Asking for 44.1 failed every
conversion until it resampled — and it now says so on a header rather
than silently returning something different.

## Not integrated

Distribution delivery, PRO/MRO/CMO registration, MLC, SoundExchange,
neighbouring-rights societies, YouTube Content ID, social publishing, ad
platforms, sync libraries.

The pages for several of these exist and are marked demo. **They must not
be described as connected.** The `insights_config` incident — a dead
module producing fabricated "uncollected royalties by territory" figures,
one import away from a live page — is what that rule is protecting
against.

## Adding a provider

1. One module, `*_provider.py`. No external calls anywhere else.
2. A `configured()` predicate, and the app hides or degrades on false.
3. A diagnostic route reporting shape, never a secret value.
4. Failures return `(None, error)`; they do not raise into a request.
5. Secrets come from the environment only. Never in the repo, never in
   chat, never echoed by a diagnostic.
