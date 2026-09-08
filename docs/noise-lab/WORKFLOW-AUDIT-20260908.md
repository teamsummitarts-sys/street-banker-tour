# Noise Lab workflow and implementation audit — 8 September 2026

## Scope and evidence

Reviewed the authenticated V2 Noise Lab page, current Noise Lab source at live commit `47d5be203195cd2b3e6c54d330f03fcee514daee`, and the supplied mobile screenshots and Manus review. The Manus presentation explicitly says its author did not inspect the authenticated workspace. Its proposed missing features must therefore be checked against implementation, not treated as backend findings.

This change is confined to Noise Lab's workflow, copy and presentation. The approved logo, tactile finish, engraved knobs, five macros, DSP, provider configuration, API contracts and account persistence remain intact. V1 and The Room are outside scope. Noise Lab's existing navigation label now calls the song builder The Room.

## Findings and response

| Finding | Evidence | Response |
| --- | --- | --- |
| Source generation and effect generation compete | Two closed, similarly styled disclosures precede the editor | Optional ElevenLabs generation is inside Source; the effect prompt is open by default, including on mobile |
| First action and next step are unclear | A demo appears selected before its audio is loaded; effect generation is disabled without explanation | Numbered Source / Shape / Listen & refine links; an explicit Load demo loop action beside the disabled effect prompt |
| Source and patch meanings overlap | Clean start appears as the heading and preset while source information lives elsewhere | Explicit Effect preset, source metadata, current B save state and concise control descriptions |
| A/B is easy to misinterpret | Existing code makes A the preceding history snapshot, B the current settings; clean bypass is independent | Preserve behavior and visibly label Previous / Current; describe clean preview separately |
| Save is ambiguous; export disappears on mobile | Mobile CSS hides Export and the word patch; desktop library exposes administrative controls up front | Save patch and Export WAV remain visible; saved patch browsing and settings-file tools are secondary disclosures |
| Saving state is hidden away from the controls | The library already tracks saved recipes and later edits | Mirror actual B saved/unsaved state beside the effect title, including restored saved settings after Undo |
| Prepared files can be hidden in a closed mobile drawer | Original MP3 can be prepared from the source card while file-ready is in the drawer | Reveal and focus the prepared file; retain the separate iPhone download/share tap |
| Mobile footer clearance is fixed | Dock height varies with labels, safe area and text settings | Reserve measured dock height and safe-area space; return focus to the action that opened the drawer |

## Backend and sound-quality findings

- **Already implemented:** account-gated module routes and assets, account-bound CSRF checks, strict recipe validation and bounds, limited provider requests, preservation of newer edits when a response arrives late, explicit generated-source acceptance, versioned account-owned patch settings, conflict/idempotency handling, local WAV/recipe export, per-gesture Undo, direct numeric entry and native keyboard ranges.
- **A/B is not clean versus processed.** A is the preceding settings history entry, not necessarily a saved version. B is current settings. Compare clean independently bypasses effects. Saving and exporting use B even when auditioning A or clean. Relabeling A as clean without an engine/state change would be incorrect.
- **Audio protection exists, with limits.** The engine ramps transitions and bounds output through soft clipping; AI settings cannot raise Level above the current value or −12 dB. These are not loudness matching, true-peak certification, a guarantee of inaudible switching, or a guarantee of safe acoustic volume.
- **Generation quality has a concrete format constraint.** The ElevenLabs request uses `mp3_44100_128`: a 44.1 kHz, 128 kbps MP3 source. Local export is 16-bit PCM WAV at the engine's current sample rate. WAV export cannot recover information removed by source compression. Provider/model/output-format changes require a separate quality-focused change, not a silent part of this UX patch.
- **Generation versus processing:** ElevenLabs creates a new audio source. OpenAI selects validated settings for the existing bounded effects; it neither listens to the audio nor synthesizes a new DSP algorithm. Clearer prompts do not remove those processing limits.
- **Persistence boundary:** patches store names and versioned recipes, not source audio or sound descriptions. Audio remains in page memory until downloaded. Reopening a patch requires its source separately. Automatic session recovery and a verified off-site recovery guarantee are not established.
- **Quota boundary:** effect-setting attempt counters are process-local and reset on restart. Source-generation attempt records are durable. The present UI explains these separately; this pass does not change quota behavior.

## Verification and release state

- Backend: 124 focused route, validation, generation, ownership, persistence and failure-path tests passed using isolated test accounts/databases and provider doubles.
- Frontend/engine: existing 54 checks passed; two new controller regressions verify source loading without autoplay and explicit clean/previous/current semantics. Updated coverage checks mobile prompt visibility, drawer focus and prepared-file discovery, plus saved-state changes and Undo.
- Public behavior is tested through controller events and isolated Flask routes. No paid provider calls, user recordings or production patch writes were made for this audit.
- **Visual verification remains blocked:** this Cloud browser rejected the local HTTP preview and its offline file preview. No screenshot of the revised build has been verified. Responsive CSS, real iPhone safe-area behavior, keyboard zoom and physical device audio must still be inspected before release.
- This is a review branch, not a deployed update or a completion claim for sound quality.

## Next quality gate

Use the same representative source material and effect requests for repeatable, level-matched listening: sparse transients, sustained notes, bass, textures and rhythmic loops. Judge prompt adherence, usable takes, attack preservation, low-end definition, unwanted noise and loop continuity separately. Compare original generated audio with the processed export so source artifacts are not mistaken for effect-engine artifacts. Select any higher-quality provider format only after verifying availability, account entitlement, decoding support and measured benefit. None of these listening outcomes has been established by this audit's automated tests.
