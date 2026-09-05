# Phase 2: sound descriptions to validated settings

## Contract and compatibility

`POST /noise-lab/api/generate` accepts exactly `{"prompt":"…"}`: a nonblank
description of at most 500 characters in at most 4096 UTF-8 request bytes. It
requires the host's authenticated account and an account-bound session CSRF token
in `X-Noise-Lab-CSRF`. Cross-site requests are rejected. Client-supplied identity,
audio, model, endpoint, recipe, code and extra fields are rejected before spending.

The server uses the Responses API, pinned `gpt-4.1-mini-2025-04-14`, strict JSON
schema and generation contract `noise-lab-prompt-1.0.0`. The model chooses only
one of the four authored profiles and Texture/Motion/Space/Mix percentages. The
server enforces exact fields, finite numeric types, bounds and the profile enum.
Refusals, truncated responses, duplicate JSON keys, non-JSON, tool calls and extra
fields fail closed. No generated code or URL is executable anywhere in this path.

The server constructs schema 1 / engine `noise-lab-1.0.0` with Level at -12 dB.
The browser revalidates it through the existing reader and sets Level to the lower
of the candidate and the current value. Only the musician can raise the level.
No engine/profile mapping/schema changed; old recipe files remain readable with
no migration. Exported recipes remain the original settings-only envelope. Model
and generation contract versions are returned separately and recorded in source.

The UI commits a valid result as a single undo step in B. It never auto-plays.
Changes to macros, presets, imports, description, A/B, clean comparison, source,
Clear session or page exit prevent stale generation from replacing newer work.
Cancel invalidates the pending result; the already sent request may still finish
and be billed. No silent retry. Native sliders and the iPhone two-tap export flow
remain intact. The text area is labeled, uses a 16px font, and actions have 44px
minimum touch targets; focus and status/error messages are available to keyboard
and assistive technology users. Physical mobile/assistive-technology checks are
still required, rather than inferred from markup or fake-DOM tests.

## Activation and isolation

The user approved OpenAI, dedicated credential creation, local `.env.local`
storage, then direct configuration in Render after the provisioning connector
rejected twice. No credential was created through that connector. The user later
reported pasting a key into V2 Render. Its validity and balance remain unverified.

`NOISE_LAB_ENABLED=1` already enables the module in V2. Generation additionally
needs a nonempty server-side `OPENAI_API_KEY`. `NOISE_LAB_AI_ENABLED` defaults to
`1`; set it to `0` to disable only AI without removing local audio and exports.
No API key is shipped to the browser. No environment mutation, new integration
with ElevenLabs, new dependency, shared-template edit or application DB migration
is needed for this source change. Save-only Render env changes take effect at
the next approved deploy. Only the exact existing V2 service may be deployed.

`/capabilities` distinguishes configured from verified-live. Key presence is only
configuration. A successful real provider call with validated settings marks
verified-live for this process; injected synthetic responses never do. Host login
redirects are treated as expired sessions by the browser, preserving local work.

## Limits, failures and measurement

One process-local locked ledger reserves attempts before provider I/O: 20 per
account and 100 in total for that server-process lifetime, one in flight per
account and two globally, at least ten seconds between starts. Invalid client
requests and absent configuration do not consume attempts. Provider attempts,
including errors, timeouts and abandoned/cancelled UI requests, are never refunded.
Network timeout: 12 seconds; UI timeout: 20 seconds; response cap: 32768 bytes;
output cap: 256 tokens. Redirects are not followed. There are no automatic retries.

**These are not daily or persistent quotas.** They reset on restart and apply
to one worker/instance only. The existing Render start command uses `--workers 1
--threads 4` and one instance. Deployment/restart overlap can have independent
old/new ledgers. Do not scale or use this as a durable monetary cap. Shared
persistent quota/spend enforcement is a prerequisite for a broader pilot.

Authenticated capabilities expose only the calling account's attempts, completed
successes/failures, total elapsed milliseconds and input/output tokens where
actually reported. Unknown usage is counted explicitly, including transport
failures. Cost is an **estimate for reported tokens only**, using published
standard model rates checked 2026-09-05 ($0.40/M input and $1.60/M output), ignoring
cache discounts. It excludes unknown usage, taxes and billing adjustments. Reconcile
against the provider invoice; zero reported usage does not prove zero cost.
No sample figures are presented as actual usage. No prompts, audio or full
provider responses appear in this ledger, application logs, or error messages.

Time-to-first-private-save, preference, repeat use and willingness to pay are
still Phase 3/4 measures. Downloading a recipe is not an account patch save.

### Provider limit diagnostics — 2026-09-05

An iPhone report showed an upstream limit failure with 19 local attempts still
available. The preceding release mapped every upstream HTTP 429 to the same
message and discarded the body, so the cause of that request cannot be recovered
from the screenshot. It does not establish exhausted credits or a valid key.

The adapter now reads at most 4097 bytes of a 429 body, rejects bodies over 4096
bytes, and uses strict JSON parsing to select an allowlisted error code/type.
It distinguishes insufficient quota, exhausted credits, spending limits, assigned
usage limits and temporary rate limiting. Unknown, oversized or malformed bodies
keep an explicitly uncertain message. Raw provider messages never reach the UI,
logs or storage. Each request still makes one attempt; failures retain the working
patch and manual presets. This changes diagnostics, not the provider account's
quota or access. A fresh authenticated request is needed to identify its current
condition. Engine, recipe and generation contracts remain unchanged.

Error meanings checked against the official
[OpenAI error codes](https://developers.openai.com/api/docs/guides/error-codes).

## Retention, deletion, backups and removal

Audio and patch/undo/description state live only in browser page memory and in
user-directed downloads. Clear session releases page state and cancels pending
application; it does not delete downloaded files or reset generation allowance.
The app does not upload audio. Only the sound description leaves the device.

The server holds descriptions and provider JSON transiently while handling the
request, with no module persistence or body logging. `store:false` disables
Responses application-state storage; OpenAI abuse-monitoring logs can retain
content for up to 30 days by default, subject to legal exceptions. Zero retention
has not been verified for the account. Clear session is not a provider deletion
request. Infrastructure-level retention remains separate and is not certified.

Account-linked usage counters stay only in server memory until restart; no backup
or automatic recovery exists. They are retained for the lifetime of the allowance
to prevent client deletion from bypassing limits. No cloud patch records exist.
Remove the module's one `app.py` registration and its owned files to remove the
prototype; no schema rollback, scheduled job or dependency uninstall is needed.
Review/revoke the dedicated API key separately when retiring the prototype.

## Official references checked for this implementation

- [Responses structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Pinned model, capabilities and rates](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
- [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)
- [Render environment save/deploy behavior](https://render.com/docs/configure-environment-variables)
