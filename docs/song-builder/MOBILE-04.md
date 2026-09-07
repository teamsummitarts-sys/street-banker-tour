# Mobile workbench correction

Project administration is behind a keyboard-accessible Project disclosure on phones. Existing controls are moved, never duplicated; desktop retains the full project bar. Song Map is compact and belongs to Song view. Instrument and Rack views prioritize the selected layer; the large master meter follows editing controls. Navigation stays visible while scrolling and transport retains safe-area spacing. Approved branding and hardware materials remain.

Validation: console integration suite checks playback, knobs, cancel, undo, take acceptance, navigation and Project disclosure handlers. Physical iPhone rendering remains unverified; do not claim mobile acceptance from DOM tests.

## Collaboration access finding
No project memberships or invitations exist. Projects, audio assets and generation jobs currently authorize by owner ID. The host current_user resolver rejects non-owner identities in closed signup mode on every request; its global plan gate redirects unauthenticated requests before Room routes execute.

A real collaboration release needs a narrowly scoped Room identity/invitation flow, expiring and revocable invitations, owner/editor permissions, access checks for referenced audio, and revision-conflict handling. It must not loosen access to Noise Lab, V1 or unrelated host routes. An Invite button without this backend would misrepresent capability. Simultaneous editing requires a separate synchronization contract and multi-account verification.
