# The Room — approved TR console

Owner approved the uploaded 02 identity on 2026-09-07: rounded TR monogram, amber square, wide stacked THE ROOM, original Street Banker endorsement. The uploaded PNG is retained byte-for-byte as `the-room-approved.png`; CSS crops only the presentation margins. Do not substitute the rejected doorway or couch identities.

The reference remains the silver flight-case console with waveforms, adjacent master/channel strip, a full-width sound rack and transport. This implementation moves project controls into the header, promotes the Song Map across the entire console, integrates the rack into the workspace and gives mobile three navigation views (Song, Instrument, Rack). Existing tools are moved, never duplicated. Takes and section settings remain reachable. Playback and project schemas are unchanged.

`room.css` scopes the new layout to `.room-console`. It includes the metal rails, physical panels, compact desktop measurements and mobile navigation visibility. The knob face uses a generated unmarked metal asset; its light stays fixed while the real interactive indicator rotates separately. Each instrument waveform uses a distinct muted ink color and a higher-resolution canvas.

Asset provenance:
- `the-room-approved.png`: exact owner-uploaded ChatGPT Image Sep 7, 2026, 04_37_06 AM.png, explicitly approved in this conversation.
- `room-knob.png`: generated original recording-hardware material asset, unmarked machined silver top view; created for this implementation. No third-party product photography.

Fresh validation before release: 36 core unit tests, 11 native-audio/DOM integration tests and 30 backend/storage tests pass. New navigation test covers all three views, Takes access, section settings and uniqueness of moved control IDs. Desktop visual inspection occurs after deployment; no physical iPhone claim is implied by DOM checks.

Scope is The Room only. This release is based on main after Noise Lab PR60 and carries no changes to Noise Lab or V1. The persistent audio directory remains /var/data/v2/the_room.
