# Noise Lab — Pretest Hardening Audit

Date: 2026-09-09

## Scope

Current V2 implementation only. Historical briefs do not override deployed/current code. Preserve approved Noise Lab visual system and product workflow. No feature expansion before musician testing.

## Verified current implementation

- Local Web Audio / AudioWorklet DSP engine.
- Current macros in code: Texture, Motion, Space, Mix, Level.
- AI/effect recipes are validated structured data, not blindly executed code.
- Noise Lab has dedicated engine, controller, mobile-console, and sound-effects Node test suites.
- Patch system uses server-side persistence with version/owner boundaries in the current V2 architecture.
- Export is client-side WAV rendering using the current DSP recipe.
- Current live/performance UI does not imply microphone or real-time instrument-input support.

## Release gates

### Must pass before LOCKED FOR USER TESTING

1. Noise Lab CI test suite passes from a pull request touching Noise Lab code.
2. Fresh deployed authenticated save -> reload -> reopen patch verification.
3. Fresh deployed export verification on desktop and iPhone Safari.
4. Fresh deployed source-generation request verification and provider/error fallback verification.
5. Account-isolation regression check on patch read/write routes.
6. Mobile workflow check at common iPhone widths, including discoverability of Export.

## Do not change before testing

- Approved visual design / tactile hardware styling.
- Current macro contract unless a confirmed product decision supersedes the deployed implementation.
- Core DSP mappings absent a verified audio defect.
- SQLite/persistent-disk pilot architecture solely for architectural purity.
- No MIDI, crowd control, live input, patch morphing, marketplace, or other roadmap features.

## Future architecture note

For wider multi-service scale, canonical relational data should move to a managed shared data service and large persistent audio to object/asset storage with asset IDs. Do not perform this migration as part of pretest hardening unless current persistence proves unreliable.
