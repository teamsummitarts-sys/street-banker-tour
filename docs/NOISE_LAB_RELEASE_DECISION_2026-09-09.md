# Noise Lab — Current Release Decision

Date: 2026-09-09

## Decision

**NOT YET LOCKED FOR MUSICIAN TESTING.**

Current implementation is a real functioning audio product with local DSP, strict AI-recipe validation, private owner-scoped patch data, source generation integration, and real WAV export. Remaining blockers are verification/storage-contract issues rather than a need for redesign.

## Critical gates still open

1. Fresh deployed authenticated save -> reload -> reopen patch test.
2. Fresh deployed iPhone Safari export test.
3. Fresh deployed ElevenLabs source generation test and failure fallback test.
4. Cross-account patch ownership test against deployed service.
5. Confirm generated/imported source-audio persistence expectations for saved patches. Current server patch schema stores recipes/versions but no durable source asset.
6. Run Noise Lab CI gate on a Noise Lab-changing pull request.

## Product freeze

Until those gates are resolved:

- No visual redesign.
- No macro renaming.
- No MIDI/live-input/crowd-controller work.
- No marketplace or patch-sharing expansion.
- No forced Postgres/object-storage migration unless persistence testing proves the pilot architecture inadequate.

Once the critical gates pass, mark:

`NOISE LAB — LOCKED FOR USER TESTING`
