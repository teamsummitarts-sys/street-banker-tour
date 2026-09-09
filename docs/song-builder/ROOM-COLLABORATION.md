# The Room: shared projects and producer handoff

## Delivered

Owners create viewer or editor invitations from **Invite & collaborators**. Each link is single-use, expires after seven days, and is displayed for the owner to share manually. Redeeming a link creates a project-scoped guest session; it does not create a host account. Names are self-reported, not verified identities. Revoking an invitation revokes the corresponding session. Clearing browser session cookies requires a fresh invitation.

Viewers can listen and export. Editors can upload audio and save arrangement edits. Guest API requests cannot access other projects, analysis reports, generation credits, workflow metadata, invitations, Noise Lab, or the host's private routes. Section and clip protections remain enforced. The owner can revoke access at any time. Audio already downloaded cannot be recalled.

Every save checks its expected revision. An outdated save returns a conflict rather than overwriting newer work. Reload shared project pulls the latest saved version. This release does not provide simultaneous live editing or presence. Contributor history records guest display names and saved revisions, not ownership or royalties.

Analysis recommendations offer **Try this in a song** with explicit project, section, and within-section placement. Reference timestamps never silently become arrangement positions. The editor can audition that placement, reject the recommendation, or prepare a separate working version with section locks and workflow metadata retained. Preparing a version does not run generation or apply the suggested audio change automatically.

Analyze & Improve exposes missing provider configuration. Local measurements remain available; musical interpretation requires the configured Gemini key, model, and billing-enabled project confirmation. No new provider credentials, billing configuration, paid requests, or external messages were created for this release.

## Validation

The focused Python and JavaScript suites cover invitation scoping, the actual host gate, viewer/editor permissions, token reuse and expiry, revocation during save, CSRF, stale revisions, protected audio, portable backup, native rack playback/export, and producer-note placement and copying. Full-site import testing requires the complete host checkout. Physical iPhone use and configured musical interpretation need live validation.

## Rollout

Invitation tables are additive in the existing Room SQLite database; no audio is moved. Keep the configured persistent disk and Room data directory. The only host change delegates matching Room guest routes to the Room blueprint, which applies its own authorization. Existing host signup and all unrelated app routes retain their current policy.
