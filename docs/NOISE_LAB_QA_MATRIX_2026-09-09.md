# Noise Lab QA Matrix — Pre-Musician Test

Date: 2026-09-09

Use current implementation as source of truth. Do not change approved visual design during this matrix.

## Automated gates

- Engine recipe validation and DSP safety
- Silence / clipping / output ceiling tests
- Audio encode/decode and file-size limits
- Controller state preservation
- A/B and undo state behavior
- Save idempotency/session preservation
- Mobile console behavior
- Source-generation request behavior
- Module syntax checks

## Required deployed manual verification

| Scenario | Desktop | iPhone Safari | Required result |
| --- | --- | --- | --- |
| New authenticated user | Yes | Yes | Opens without stale state |
| Upload/local source | Yes | Yes | Decodes and plays or gives non-destructive error |
| Generate source | Yes | Yes | One provider request per action; returned audio plays |
| Good effect prompt | Yes | Yes | Valid recipe applied without replacing source |
| Empty/bad prompt | Yes | Yes | Clear error; current sound retained |
| AI timeout/provider failure | Yes | Yes | Manual controls remain usable; current sound retained |
| Texture | Yes | Yes | Audible, bounded, smooth |
| Motion | Yes | Yes | Audible, bounded, smooth |
| Space | Yes | Yes | Audible, bounded, smooth |
| Mix | Yes | Yes | Audible dry/wet behavior |
| Level | Yes | Yes | Bounded output level; no clipping |
| A/B | Yes | Yes | Immediate understandable compare; state preserved |
| Undo | Yes | Yes | Non-destructive expected state restoration |
| Save patch | Yes | Yes | No logout/audio reset |
| Save after long session | Yes | Yes | No logout/audio reset |
| Reload/reopen patch | Yes | Yes | Recipe/version restores correctly |
| Patch ownership | Yes | Yes | Cross-account ID access returns not found/denied |
| Export | Yes | Yes | WAV matches current processed recipe and duration |
| Export after reload | Yes | Yes | Works for restorable state |
| Rapid Generate taps | Yes | Yes | Duplicate/busy protections prevent duplicate charge |
| Session expiration | Yes | Yes | Clear session error; local working sound retained |
| Render redeploy | Yes | Yes | Durable patch data survives |
| Unsupported audio | Yes | Yes | Non-destructive decode error |
| Network loss | Yes | Yes | Local manual sound remains available |

## Release decision

Do not mark `NOISE LAB — LOCKED FOR USER TESTING` until all critical deployed checks above pass. Any failure that loses audio, loses a saved patch, breaks ownership isolation, applies malformed AI settings, or produces incorrect/clipped export is a blocker.
