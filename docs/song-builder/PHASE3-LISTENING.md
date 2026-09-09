# The Room — Phase 3 hosted listening

## Workflow

1. Join the live session. Collaborators release instrument editing control using Listen only.
2. An owner or invited editor chooses Host listening. This releases their own editing control and holds the saved mix at its current revision.
3. Other participants choose Follow host. This explicit gesture enables their local audio device; merely opening a project never starts playback.
4. The host uses Play shared mix, Pause shared playback, and the Shared position slider. Each browser plays its own decoded copy of the same saved audio.
5. Add note at playhead records feedback with author, time, and saved revision. Authors and the owner can resolve or reopen notes. Listen here is available when a note matches the current revision and exits follow mode before auditioning.
6. End session releases the saved mix for further editing. Followers can stop following at any time. The ordinary Stop control exits follower playback or pauses the host's transport.

## Timing and recovery

Transport is polled once per second. Position uses the server timestamp with a bounded half-round-trip latency estimate. A drift greater than 0.5 seconds triggers repositioning. This is approximate coordinated listening, not sample-accurate synchronization, synchronized recording, streaming microphone audio, or an internet band rehearsal system.

The browser must already have the host's saved revision and no unsaved edits. A mismatched listener pauses and is asked to reload. Active hosted review rejects project edits and new editing claims on the server, including from older clients.

Requests time out after five seconds. A disconnected listener stops local playback and reports the interruption; following resumes on a successful reconnect unless the user stopped following. Hidden follower tabs exit follow mode. Host presence expires after 20 seconds without a live heartbeat, ending the shared session. Host commands use expected versions so stale or reordered commands cannot overwrite newer transport state. An uncertain host-start response can be recovered with Resume hosting.

## Feedback and access

Viewer invitations can leave feedback but cannot host. Every route remains project-scoped, authenticated and CSRF-protected. Live session IDs are not credentials. Host records bind both session ID and actor to avoid inheriting authority through a reused expired ID.

Feedback requests are idempotent by UUID. Notes have a 1,000-character limit, a 500-note project cap and a short submission rate limit. The UI displays the latest 100 notes. Old-revision notes stay labeled rather than being silently remapped to a changed arrangement. Display names remain self-reported.

The existing audio files, portable project schema, V2 storage path, Noise Lab, and V1 are unchanged. Two additive tables hold transport metadata and feedback. No generation credits or external audio services are used.
