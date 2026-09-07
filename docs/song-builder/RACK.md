# Track sound rack

The first rack adds live Body, Bite, Dirt, Space, and Output controls to a
selected track, with Clean, Warm, Grit, and Space presets. The Original and
Processed buttons bypass/enable the entire rack, including its output gain.
The existing track level, pan, mute, and solo still apply in either mode.

Use the Rack button on a track, choose a preset or Assign rack, and press Play.
Slider input previews the sound immediately; change/release commits one Undo
step and autosaves. Reset restores a single control. Cancellation restores its
pre-gesture setting without saving. Assigning the first rack during playback
rebuilds playback at its current position; subsequent rack changes update audio
parameters without restarting playback. A short smoothing ramp reduces clicks.

The rack applies throughout the track, across all sections. If a protected
section contains a clip on that track, its rack cannot change until the affected
sections have been unlocked and saved. This is enforced in the editor and server.
Existing level/pan/mute/solo protection semantics are unchanged.

## Compatibility and processing

- `track.rack` is optional within project schema version 1. Older projects keep
  their exact shape until a rack is assigned. Rack data is strictly validated on
  both sides, deep-copied, and included in versions and portable backups.
- Settings: `enabled` (boolean), `body` and `bite` (-100 to 100), `dirt` and
  `space` (0 to 100), `outputDb` (-24 to 6). No presets or host URLs are required
  to interpret these settings. Older editor builds reject unknown rack fields;
  use the updated portable module on a future host.
- Signal: source clips and fades → tone shelves → parallel drive → dry/finite
  room response → rack output → track fader/pan → mix. Original bypasses the
  entire processing branch. Original audio files are never changed.
- Playback and export use the same graph. Eight-second export chunks include
  one second of preceding audio to restore filter/convolution history. Selected
  range exports include the preceding audio's rack tails where relevant. Tails
  stop at the chosen export/song boundary; no extra duration is appended.
- The room response is synthesized locally, deterministic, stereo, and finite
  (0.65 seconds). There are no network requests or music-generation charges.
- This first rack has fixed processing order. Arbitrary device chains, compressor,
  tempo delay, automation recording, custom user presets, and loudness matching
  are future work. Tone processing does not rewrite the underlying performance.

## Verification

Run the existing project tests and native audio integration check:

```sh
node --test tests/song_builder/*.test.mjs
python -m pytest -q tests/test_song_builder_backend.py tests/test_song_builder_host.py tests/test_song_builder_v2.py tests/test_song_builder_provider.py
node --check song_builder/static/ui/controller.mjs

# Test dependencies only; not part of the production runtime.
npm install --prefix /tmp/song-rack-verification jsdom@30.0.1 node-web-audio-api@2.2.0 --no-audit --no-fund
RACK_TEST_MODULES=/tmp/song-rack-verification/node_modules node --test tests/song_builder/rack.integration.mjs
```

Native audio checks compare samples, verify tone/drive and room response, compare
chunked and selected-range WAV output against a continuous render, and confirm
live updates retain the active playback graph. DOM checks cover preset selection
after server JSON ordering, slider changes, reset, and bypass. Backend checks
cover restart persistence and locked/invalid writes.

The cloud browser blocked the local preview URL. DOM simulation and native audio
checks do not verify visual rendering, physical iPhone gestures, or perceived
sound quality on a device. Those checks remain before calling the rack polished.

## Release boundary

V2 repository only. No V1 or host configuration changes. The owner subsequently
verified the host database at `/var/data/v2/streetbanker.db` with the disk mounted.
That supersedes the earlier host-database warning. The separate Song Builder
project database/audio directory still needs its own path and retention check
before a deployment. Do not infer its location from the host database path.
See CONSOLE.md for the new console UI and verification boundary.
