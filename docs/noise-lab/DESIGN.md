# Noise Lab console / 2026-09-07

Approved direction: the owner's editorial + metallic rack mockups, combined into the existing V2 Flask/Jinja/native-module page. This is not hardware and does not introduce a new frontend stack.

## Behavior

- The existing Street Banker SVG brand asset is reused from V2. Module CSS is scoped to `.noise-lab`.
- Five satin silver dials have gold indices. Each dial overlays an actual native range, with its original label, bounds, keyboard semantics and undo gesture behavior. An adjacent numeric input accepts exact values. Horizontal drag maps to the existing range. Level remains **-60 to 0 dB**; the generated mockup's +12 endpoint was not adopted.
- Studio exposes sound description; Club view collapses it using native details and removes secondary explanatory lines. Prompt, source, preset, private library, exports and help remain reachable. Display settings change interface metal/mark contrast, never audio gain or device brightness. They persist only while this page remains in memory.
- At mobile widths, Play, Stop, A/B and Save stay in a bottom bar with safe-area padding. Save opens the private library form and focuses its heading; the existing explicit Save new patch/Save new version actions perform the save. These navigation buttons never claim a successful save.
- Clean bypass remains independent of A/B. The working heading identifies the heard preset or custom settings; A locks editing as before.
- Empty, pending, error, account-expiry, duplicate-save, deletion confirmation and two-step iPhone export flows remain in the existing controller/library modules. No fake patches or generation results are inserted.

## Meters and limits

`engine/meter.mjs` creates passive stereo analyser branches from the summed source and from the master output after its transport fade. Meter outputs never feed the audible destination. Explicit stereo speaker upmix on the input branch mirrors the mono-to-stereo worklet input. Real PCM data is sampled at most 30 times per second while the page is visible and playing. Each analyser retains at least 50 ms of recent samples; polling/foreground scheduling can miss peaks. The visual markers hold sampled peaks for 1.2 seconds. Stop, suspension, disposal and hidden-page handling clear the display.

The displays are **sampled sample-peak dBFS**, not calibrated loudness, continuous capture, true peak, a microphone input, or an output-safety certification. Nonfinite samples show unavailable and never become UI coordinates. Numeric readouts may show peaks outside the graphical -60..0 range; bars clamp to that range. HIGH appears at -1 dBFS or higher. Existing DSP ceiling and export encoding are unchanged.

The analyser implementation follows the [Web Audio AnalyserNode specification](https://www.w3.org/TR/webaudio/#AnalyserNode), including its unconnected output. No third-party library or remote meter transport is introduced.

## Compatibility and rollback

Recipe schema **1**, engine **noise-lab-1.0.0**, profiles, parameter mappings, fades, DSP source and WAV behavior remain unchanged. Metering is observation, not a change to recipes or engine behavior. Existing patch files and saved versions need no migration. No server endpoints, database schema, account ownership, retention, backup, generation limit, provider or environment variable is changed.

Removing the UI changes or disabling Noise Lab uses the existing module flag. Reverting this design commit does not require restoring a database. Keep all later V2 changes when reverting. V1 and Song Builder files are outside this change.

## Verification

Automated before publication: 133 Python tests and 46 JavaScript tests passed. Coverage includes private ownership/CSRF/storage, malformed AI and recipes, stale operations, save acknowledgement, iPhone export event ordering, output bounds, switching ramps, meter math, passive routing, stereo values, peak-hold expiry, Stop/suspend/dispose, and view changes without changing recipes. These tests do not certify physical iPhone touch/audio, dark-club readability, continuous device playback, or browser layout. Browser observations and remaining limits are recorded with the deployment result.
