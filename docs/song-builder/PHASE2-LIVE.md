# The Room: Phase 2 shared editing

Choose **Join live session**, then select an instrument under **Editing control**. The selected instrument also becomes the active editor track. **Song arrangement** reserves structural edits; **Listen only** releases editing control. Viewers can join and listen but cannot claim a part.

Presence and saved revisions refresh every three seconds. Different-track changes merge against canonical server revision history. Same-track or structural conflicts are retained for review instead of overwriting newer work. All writes, including from older clients, respect active editing leases. Existing section and clip protections still apply inside the save transaction.

The server retains at most 40 revisions and approximately 2 MiB of merge history per project. Very old edits require manual conflict resolution. Client undo history resets when incorporating a live save or remote update so undo cannot restore stale versions of collaborators' work. Portable project export remains available for retaining an unsaved arrangement.

Editing leases expire after 20 seconds without a heartbeat. A revoked invitation immediately loses access and its presence/lease is removed on the next live request. Session identifiers do not authenticate a collaborator; every endpoint still checks the signed host or invited guest session and project permissions.

Remote revisions wait while audio plays, a pointer gesture is active, recording runs, or local edits are unsaved. Stop playback to load the updated mix. This release provides shared saved-state editing with presence, not synchronized playheads, internet audio streaming, or simultaneous live performance. Network failures preserve local edits and display a reconnect status. A reconnect cannot silently overwrite a changed part.

Validation covers real concurrent SQLite saves by owner and guest, same-track/arrangement exclusion, old-client writes, lease expiry, revoked and viewer access, session identifier scoping, protected clips, pending local edits during save, JSON key-order independence, and deferred UI updates during playback and pointer gestures.

No service, paid provider, schema change to the portable project, host access change, or storage-location migration is required. Live tables are additive in the existing Room database. Noise Lab and V1 are outside this release.
