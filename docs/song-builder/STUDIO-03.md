# The Room — Studio 03

## Experience thesis
Choose a section, select an instrument, turn a control, hear the result, and keep or undo the change. The console should communicate this through the waveforms, signal meters and hardware controls.

## Audit and decisions
- Old design compressed essential labels to 8–11px and mixed three conflicting style layers. Retire console.css from the Room template; room.css now owns its responsive presentation over base editor styles.
- Old Song Map stretched a few sections into wide empty panels. Use consistent section keys with horizontal scrolling for longer arrangements.
- Old master display lacked a calibrated face and squeezed the selected mixer into horizontal sliders. Draw the actual −48…0 dBFS scale, retain the real peak needle/stereo signal, add a vertical native volume fader and a drag/keyboard pan knob.
- Use neutral graphite plates, silver hardware, cream labels, restrained amber engagement and per-track waveform colors. The approved TR artwork and silver knob asset remain unchanged.
- Move infrequent Rename/Remove/Open rack controls into Track options; keep Sound/Trim/Takes immediately available.
- Old unassigned tracks had disabled knobs despite instructions to drag them. Neutral processing now exists only in the runtime playback copy; the first committed change creates one undo edit. Selection and cancellation do not assign a saved rack.
- Desktop transport follows the rack without covering it. Mobile retains a fixed transport with explicit four-column placement and safe-area space.
- Mobile Song/Instrument/Rack navigation stays stable. Sound remains inside Instrument; Rack opens the dedicated rack view. The Projects menu is anchored to the full project bar to fit narrow screens.

## Operating states
- Empty: section creation, upload, recording and synth/AI entry remain reachable; no-track rack controls are disabled.
- Playing: real audio drives peak and stereo displays; first-use output previews alter signal without stopping transport.
- Protected/busy/recording: existing mutation guards remain in force.
- Original: bypass is explicit and disables processing adjustments until Processed is selected.
- Cancel: pending knob gestures restore their starting value; completed changes remain undoable.
- Errors, recovery, export and account storage stay on existing controller paths.

## Verification
36 existing JavaScript unit tests; 13 native audio/DOM/controller integration tests; 24 relevant Python backend/host/V2 tests passed before release. Focused regressions cover first-use real signal attenuation, cancel, one-step undo, bypass, blocked states, mobile view transitions and pan cancellation.

Visual verification is performed on the deployed desktop page. Physical iPhone touch testing remains a user acceptance check. No paid music generation calls are part of verification.

## Scope
Only song_builder, its tests and this document. No Noise Lab, V1, storage migration, provider contract or portable project schema changes.
