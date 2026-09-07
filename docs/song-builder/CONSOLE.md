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

### Follow-up release check

Empty track lanes now retain a real text message alongside the playhead; repeated
console synchronization does not duplicate either. The five console integration
checks passed again, with a separate DOM check covering empty and populated lanes.

Render confirms that V2 has a disk mounted at `/var/data`, but its connector does
not expose environment reads or a shell. Run this read-only check from the V2
service's project root in Render Shell before deploying. It does not import the
host app, initialize a database, change configuration, or move files. The default
below matches the current host's standard Flask instance directory; if the host
later overrides that directory or passes a data_dir argument, inspect that first.

```sh
python - <<'PY'
import os
from pathlib import Path
directory = Path(os.environ.get('SONG_BUILDER_DATA_DIR') or 'instance/song_builder').resolve()
print('Song Builder directory:', directory)
print('Explicit directory configured:', bool(os.environ.get('SONG_BUILDER_DATA_DIR')))
print('Persistent disk mounted:', os.path.ismount('/var/data'))
for label, path in [('Database', directory / 'songs.sqlite3'), ('Audio', directory / 'audio')]:
    print(label, 'exists:', path.exists(), 'resolved:', path.resolve(),
          'under persistent disk:', path.resolve().is_relative_to(Path('/var/data')))
PY
```

Do not change the directory setting or redeploy merely because a path is outside
the disk: preserve existing projects and audio together before a storage move.
This check identifies location only; it does not certify a backup or DB integrity.

### Integration with the live Noise Lab console

The V2 deployment at 63f5a50e02ebd439eb948f71af8332c3287cc2a5 includes the
separate Noise Lab metallic console and Club view. Its nine changed files are
carried into this branch unchanged, with that commit retained as a merge parent.
The Song Builder diff against that main remains scoped to Song Builder.

The intermediate-width transport rule now retains bottom safe-area padding,
including iPhone landscape widths. Narrow phones already had transport padding;
page-bottom clearance now also includes the safe-area inset at both breakpoints.
This is a CSS review correction, not evidence of a physical iPhone test.

The Render deployment history confirms the newer V2 host is live. It does not
establish where Song Builder's separate audio files reside. A targeted log search
returned no Song Builder storage-path evidence. The read-only shell check above
remains the missing storage evidence; the host disk verification is accepted.
