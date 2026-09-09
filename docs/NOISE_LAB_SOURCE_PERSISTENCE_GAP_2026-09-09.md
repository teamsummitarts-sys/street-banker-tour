# Noise Lab — Source Persistence Gap

Date: 2026-09-09

## Verified behavior

The current private patch schema persists patch identity, owner, name, immutable recipe versions, timestamps, and idempotency request records. It does not persist a source-audio asset identifier, source prompt, generated-audio object, or original uploaded file.

The ElevenLabs source-generation route returns generated MP3 audio directly to the browser and explicitly does not store the audio or prompt.

## Consequence

A saved patch can restore its validated DSP recipe/version history, but the server cannot independently restore the exact source audio from that patch in a later session. A browser-local source can therefore be lost after reload/device change unless another current host mechanism retains it outside the Noise Lab patch system.

## Pretest classification

**HIGH PRIORITY PRODUCT-CONTRACT GAP.**

Do not solve this by copying arbitrary filesystem paths into patch rows. Before broader musician testing, decide whether a “private patch” is intentionally settings-only or must reopen with its source. The intended product journey specifies source-associated patches, so the preferred long-term fix is an owner-scoped asset ID backed by durable asset/object storage.

## Safe implementation boundary

Any source-persistence implementation must preserve:

- owner isolation
- private-by-default access
- non-predictable/signed retrieval as appropriate
- durable original source when explicitly saved
- cleanup of unsaved temporary previews
- no permanent storage of every intermediate render
- patch rows referencing an asset ID rather than arbitrary local paths
