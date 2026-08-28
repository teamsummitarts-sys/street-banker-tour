# Browser-DSP checks

The rack's signal maths lives in plain-array modules with no DOM, no
network and no Web Audio, so it can be verified against signals whose
answers are known by construction rather than eyeballed in a browser.

Run them with Node from this directory:

    node check_tempokey.js     # BPM, key, time-stretch, pitch-shift
    node check_audioconv.js    # WAV and AIFF headers, dither, clipping

Both exit non-zero on failure, so they can be wired into CI.

What "known by construction" means here:

- `check_tempokey.js` builds click tracks at exact BPMs and triads of
  exact pitch classes, then asserts the detector lands within 1.5 BPM and
  names the right key. The stretch checks measure the dominant frequency
  of the output with an FFT — a pitch shift that also changed length, or a
  tempo change that moved the pitch, fails.
- `check_audioconv.js` parses the encoders' own bytes back out field by
  field: chunk tags, sizes, format tag, the 80-bit extended sample rate
  AIFF requires, then decodes the samples and compares them with what
  went in. It also proves dither perturbs a 16-bit DC level, never
  touches 32-bit float, and that over-range input clamps instead of
  wrapping.
