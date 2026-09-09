# The Room — workflow and recovery release

## Changes

- A compact production toolbar keeps Song Map and instrument waveforms ahead of collaboration controls. Session team opens the existing live, listening and invitation tools on demand. Mobile remains one continuous scroll; transport has visible Undo and Redo, with 44px track switches.
- The editor links to saved takes, section scenes, track groups and clip protections, carrying project/section/instrument selection. Pro Workflow returns to the same context. Track Groups is the accurate label: these controls edit member-track values and are not summed DSP buses. Copy to editing lane is manual phrase editing, not automatic comping.
- Named checkpoints capture saved arrangement, workflow and feedback. Restore and Save as new version create a separate project; saved takes/scenes/protections follow the copy. AI acceptance also uses a protected server-side fork instead of dropping workflow metadata.
- Owner arrangement drafts are journaled locally under an opaque account-specific scope before autosave. A reopening offers recovery into a new project. Successful server saves acknowledge only the matching draft from that tab. Audio must have uploaded before a clip enters the journal. Unsaved microphone capture, account deletion and browser-storage clearing are not recoverable. Guest edits retain the existing server revision/conflict recovery; the local journal is owner-only.
- `.room.zip` archives include current arrangement and rack settings, referenced audio, saved alternate takes/scenes, clip protections, listening notes and named checkpoints. Audio used only by saved alternatives/checkpoints is included. Import validates paths, duplicate entries, hashes, formats, quotas and source bounds before committing a new project. Disk failures remove newly written files and roll back metadata. Legacy `.sbsong` remains available for the active arrangement.
- Archives exclude live identities/invites/leases, provider candidates/decisions, pending collaborator submissions, temporary analysis uploads and standalone analysis reports. Export reports separately from Analyze & Improve. Limits: 512 MiB referenced audio, 32 MiB manifest, 256 sources, 50 checkpoints. Binary archive bodies spool to temporary storage instead of accumulating all audio in memory. The larger request ceiling applies only to archive import.
- Invited editors can upload a WAV performance and assign section, instrument and offset for owner review. Immutable submissions are scoped to their source project/revision/workflow. Contributors see their own submissions; owners see all. Preview mixes only the proposed lane range over the saved backing. Accept is idempotent and creates a separate version; stale backing/protections block approval. Request changes records feedback in the app. No email is sent.
- Pro Workflow compares a saved take with the current instrument in its section, over the same backing, with separate waveforms and an explicit scrubber. It uses the existing audio engine and leaves arrangement data unchanged.
- Provider take shortlist/reject decisions persist with the project across browsers. Rejected candidates can be returned to pending review.
- Analyze this section / Analyze full mix renders current rack processing into a local WAV copy and passes the section map through account-scoped IndexedDB. Copies expire after 30 minutes, max three/64 MiB each. User explicitly imports the copy into the local queue, uploads it and chooses a processing destination. Handoff does not invoke a provider.
- WAV/MP3 sources can be prepared as a separate PCM16 analysis excerpt. Source files remain unchanged. Sample rate/downmix choices and timestamp offsets are disclosed. Browser preparation accepts sources up to 32 MiB and six minutes; resulting server uploads remain at most 14 MiB and ten minutes. Excerpt timestamps begin at zero; the editor section map is clipped/offset accordingly.

## Remaining configuration / limits

Gemini interpretation still requires `ROOM_ANALYSIS_GEMINI_KEY`, `ROOM_ANALYSIS_GEMINI_MODEL` and `ROOM_ANALYSIS_GEMINI_PAID_CONFIRMED=true`. This release does not configure billing or credentials, make paid calls, or add contextual Music v2 inpainting. Local analysis reports measured signal values and a cautious BPM estimate; musical key, vocals, genre and production suggestions need a configured interpretation destination. No false LUFS, true-peak or key measurements are shown.

Guest sharing remains project-scoped. Accepted versions do not automatically invite existing collaborators. Hosted listening is approximate coordinated playback, not synchronized internet performance.

## Verification

Backend tests cover permission/CSRF boundaries, stale revisions, idempotent submission approval, interval preservation, protected fork edits, archive restoration of alternate audio and feedback, hash/path failures, quota scoping and disk-write rollback. Browser/module checks cover the actual rack graph, playback, first-use controls, clipboard-free section handoffs, local WAV signal conversion, comparison project isolation and account/tab recovery isolation. Physical iPhone rendering and touch use still need device validation.

Scope: Room files, Room tests and Room CI only. Noise Lab and V1 code/configuration remain locked. No storage path migration or credentials change.
