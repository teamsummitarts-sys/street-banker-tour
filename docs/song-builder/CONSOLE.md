# Song Builder console — implementation review

The owner approved the touring-console visual direction and asked to continue.
This implements a functional V2 pass using the supplied bracketed Street Banker
logo, graphite/brass surfaces, rotary rack controls, a selected-instrument mixer,
Sound/Trim/Takes tabs and persistent transport. Styling is CSS/native controls;
the generated design image is a visual reference, not a screenshot of this code.
Do not claim pixel-matched fidelity or physical iPhone verification yet.

## Behavior

- Selecting an instrument focuses its mixer. On phones the chosen track expands
  to a wider waveform; All instruments returns to the arrangement. Selecting a
  track never implicitly solos it. A Solo active notice names audible solo tracks;
  Clear solo is one undoable arrangement edit.
- The rack retains existing Body/Bite/Dirt/Space/Output processing and presets.
  Body/Bite are signed macro amounts, Dirt/Space display percentages, and only
  Output displays dB. Vertical pointer gestures preview live; release commits
  one edit. Cancellation restores the original. Double-tap resets; explicit
  Reset buttons and keyboard-adjustable native ranges are also available.
- Sound/Trim/Takes use tab semantics and arrow/Home/End keys. Existing clip,
  lyrics, section protection, generation and export controls are retained.
  Section settings and exports use disclosure menus. Original/Processed bypass,
  per-track pan Center, clip trimming/fades and the portable format remain.
- Play section now supplies an audio-engine range; it no longer waits for a
  requestAnimationFrame callback to stop at the section end. Loop section queues
  repeating sources ahead on the Web Audio clock, retaining the track processing
  graph and room response. Ended source nodes are released. Stop/dispose clears
  scheduling. Existing hidden-page handling stops playback; background looping
  is not promised. Very long main-thread stalls can still exhaust queued audio.
- Numeric left/right master sample peaks are measured after rack/fader/pan through
  two analysers. Meter motion follows audio, and clipping indication is latched
  until reset. The analog-style display is labeled dBFS, not calibrated VU.
  These are windowed sample peaks, not LUFS or inter-sample true-peak metering.
- A section ruler and moving playhead track the selected section. Ruler bars use
  the existing fixed 4/4 assumption. Target BPM remains metadata; existing audio
  is not time-stretched. Audio sources, project schema and account isolation are
  unchanged by the console. Rack schema work from the prior open PR is included.

## Fresh verification

```
node --test tests/song_builder/*.test.mjs
RACK_TEST_MODULES=/tmp/song-rack-verification/node_modules node --test tests/song_builder/rack.integration.mjs tests/song_builder/console.integration.mjs
python -m pytest -q tests/test_song_builder_backend.py tests/test_song_builder_host.py tests/test_song_builder_provider.py tests/test_song_builder_v2.py tests/test_song_builder_demo.py
```

Test dependencies remain test-only: jsdom 30.0.1 and node-web-audio-api 2.2.0.
36 JavaScript unit checks, 8 native-audio/DOM/controller integration checks and
26 Python checks pass (70 total). These exercise sample preservation and exports,
section boundaries, repeated audio cycles, stereo metering/pan, rack changes in a
loop, gesture cancellation/reset, tabs, clipping latch, mixer reparenting, solo
clear/Undo, and the existing project/auth/protection/persistence boundaries.
The Python suites are pytest tests; unittest is not their runner.

## Before release

The cloud browser previously blocked the isolated localhost preview. No rendered
screenshot, real iPhone touch result or listening verdict is claimed for this
implementation. Check desktop and 390px phone layout, text overflow, touch
capture, scrolling versus knob drags, tab visibility, and transport safe-area
clearance. Compare actual surfaces against the approved design image. Native
DOM checks cannot certify visual fidelity or accessibility on a device.

Base main inspected: 1b60692352aedcb0a2b03403ca6b7133982fb73b. The six existing
Song Builder source files affected by the preceding rack work match its original
base (ignoring terminal newlines); newer Noise Lab work is kept intact.
Only Song Builder code/assets/tests/docs are in this change. No V1, host config,
provider requests, disk operations or deployment are included.

The owner verified the host DB is active on /var/data/v2/streetbanker.db. Before
restarting V2, independently verify and preserve Song Builder's own project DB
and audio directory; its storage path is separate from the host DB.
