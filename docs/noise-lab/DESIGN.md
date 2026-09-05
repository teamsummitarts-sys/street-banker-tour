# Noise Lab interface — Phase 1

This standalone surface inherits the approved Street Banker V2 near-black,
warm-brass console language. The owner's black Noise Lab pedal establishes the
five macro labels: Texture, Motion, Space, Mix, and Level. It does not establish
hardware support; no hardware interface is implemented. The root PRODUCT.md and
DESIGN.md remain the parent authority; the opening template comment records the
inherited direction contract for this extension.

The page is scoped to `.noise-lab`, uses its own template and module-relative
assets, and returns to the supplied V2 team route. The supplied Archivo font is
self-hosted with its license in `static/ui/fonts`. No reference photography,
external font service, V1 asset, or shared layout is required.

The source and transport come first. The playback strip displays actual source
position; there is no invented waveform, spectrum, loudness meter, or metric.
The five SVG dial indicators reflect settings and accompany real labeled range
inputs plus direct numeric inputs. They are not substitutes for accessible
controls. Native keyboard range behavior, visible focus, explicit pressed
states, errors, and reduced-motion support are implemented. Buttons, the select,
ranges, and numeric inputs have 44px control heights or minimum heights; the tail
checkbox label is 36px high on desktop and 44px on mobile. This does not certify
all targets as 44 by 44px. Mobile CSS retains source controls and preview in
document order; rendered mobile behavior remains unverified.

Manual presets and local source processing are the operative Phase 1 journey.
The example sound description is static copy, clearly marked as next phase.
There is no editable prompt, AI request, generation charge, or simulated result.
No cloud Save action is present. Private recipe JSON download/import and a WAV
download are labeled by their actual behavior. Preparation reveals an explicit save/share button when supported and a download
link. No file opens automatically after rendering. The app does not claim a
verified save to the user's file system.

Each continuous slider gesture is one undo step. A auditions the preceding
committed patch while retaining current B edits; editing is locked while A is
selected, and preset metadata reflects the patch being auditioned. Clean
comparison is independent. WAV and JSON downloads use current B. An optional
two-second effect tail is explicit. File and recipe failures retain the previous
working source/settings. Recipe version validation belongs to the engine.
Later imports, edits, Undo, comparison changes, or session clearing invalidate
older pending recipe reads. Stop remains available during a pending Play and
cancels that start.

Audio and undo history live in page memory. This module does not use
localStorage or IndexedDB, upload source audio or send prompts, or provide
backups. Clear session disposes the local engine and drops references.
User-downloaded files remain under the user's control. Host-backed account
gating is implemented: the blueprint requires the feature to be enabled and the
injected V2 user resolver to return an account ID. Cloud patch ownership,
durable private patch storage, retention, generation limits, and AI validation
remain outside this Phase 1 implementation.

The independent finish review reported five controller tests passing and the
three fixes resolved at source-review scope: stale recipe imports versus later
edits, A preset metadata, and Stop during pending Play. No valid browser
screenshot or real audio/device run was obtained; the cloud browser blocked the
local preview with ERR_BLOCKED_BY_CLIENT. Visual appearance, keyboard/touch
operation, actual audio and failure recovery, mobile layouts, sustained and
declared-device playback, and musician evaluation remain unverified. Capability
detection does not certify device support. This document records implemented
design and behavior, not a claim that those validation gates have passed.

The iPhone export correction adds a compact file-ready region beneath the output
controls. It identifies the prepared filename and snapshot behavior, offers a
native Save / share file button when file sharing is supported, and retains a
separate-target Download file link. Cancelling does not clear the patch. Cached
history returns retain edits and undo; ordinary reload/eviction still loses
unsaved session data. Device verification remains pending.
