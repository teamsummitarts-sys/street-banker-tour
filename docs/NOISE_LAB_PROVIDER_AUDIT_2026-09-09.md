# Noise Lab — Provider Audit

Date: 2026-09-09

## OpenAI effect-settings generation

- Purpose: translate text descriptions into validated local DSP recipe settings.
- Model in current code: `gpt-4.1-mini-2025-04-14`.
- Endpoint: OpenAI Responses API, server-side.
- Secret: `OPENAI_API_KEY` read server-side from application configuration.
- Provider response is treated as untrusted data and must pass strict JSON shape/type/range validation.
- No redirects; 12-second timeout; one bounded attempt; no automatic retry.
- Provider prompts/responses are not logged by Noise Lab error handling.
- Per-process pilot allowance exists and resets on restart; it is not suitable as a durable subscription/usage system.
- Token usage and an estimated token cost are tracked in process memory when provider usage metadata is available.

## ElevenLabs source-audio generation

- Purpose: create source sound/loop audio; separate from effect-settings generation.
- Model in current code: `eleven_text_to_sound_v2`.
- Endpoint: ElevenLabs sound-generation endpoint, server-side.
- Secret: `ELEVENLABS_API_KEY` read server-side from application configuration.
- Output: MP3 44.1 kHz / 128 kbps response, max 2 MiB.
- Request duration: 5, 8, or 10 seconds.
- UUID request IDs plus durable reservations prevent automatic duplicate provider submission.
- 60-second bounded provider request; no redirect; no automatic retry.
- Provider output is minimally validated as MP3 framing before returning to browser.
- Durable request reservations/allowance metadata are stored, but generated audio and prompt are not stored by this module.

## Release concerns

1. Generated source audio is currently browser-session data, not a durable patch-linked asset.
2. OpenAI pilot usage allowance is process-local and resets on restart.
3. ElevenLabs usage tracks request counts/durations but does not currently persist provider cost/credit consumption.
4. Provider model availability and pricing are external dependencies and must be rechecked before subscription pricing is finalized.
5. Neither provider is required for manual DSP operation: local presets/macros must remain usable when providers fail.
