/* Street Banker · SB-13 TMP-1 — tempo and key, measured and changed.
 *
 * Four jobs, all classical DSP, all in this tab:
 *
 *   detectBpm   Onset-energy envelope -> autocorrelation. This is the
 *               standard beat-tracking approach (Scheirer 1998, Ellis
 *               2007): band-limited energy flux gives one impulse per
 *               transient, and the lag that best correlates with itself
 *               is the beat period. It reports the half- and double-tempo
 *               readings too, because autocorrelation genuinely cannot
 *               tell 85 from 170 - that is a musical judgement, not a
 *               measurement, so we hand the user all three.
 *
 *   detectKey   Chroma (12 pitch classes, energy folded across octaves)
 *               correlated against the Krumhansl-Schmuckler major and
 *               minor profiles. Returns the best fit plus the runner-up,
 *               with a correlation score, because a key estimate on a
 *               finished mix is a guess with a number attached.
 *
 *   timeStretch WSOLA - waveform-similarity overlap-add. Slides each
 *               output frame within a small search window to the offset
 *               that best matches what has already been written, so the
 *               splices land on matching phase instead of clicking.
 *               Time-domain, so transients survive better than a naive
 *               phase vocoder at the moderate ratios people actually use.
 *
 *   pitchShift  Resample by the pitch ratio (which moves tempo too), then
 *               time-stretch by the inverse to put the tempo back. The
 *               classic composition; no pitch tracking involved.
 *
 * No DOM, no network, no Web Audio - plain arrays in, plain arrays out,
 * so every claim above can be checked in Node against a signal whose
 * tempo and key are known by construction. Long jobs yield through the
 * same ladder Rough Split uses, because setTimeout is throttled to ~1s
 * per tick in a background tab and would stall the progress bar.
 */
(function (root) {
  "use strict";

  var yieldNow = (function () {
    /* Node first: its MessageChannel ports would hold the process open. */
    if (typeof setImmediate !== "undefined") { return setImmediate; }
    if (typeof MessageChannel !== "undefined") {
      var mc = new MessageChannel();
      var pending = null;
      mc.port1.onmessage = function () {
        var fn = pending; pending = null;
        if (fn) { fn(); }
      };
      return function (fn) { pending = fn; mc.port2.postMessage(0); };
    }
    return function (fn) { setTimeout(fn, 0); };
  })();

  var NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G",
               "G#", "A", "A#", "B"];

  /* Krumhansl-Schmuckler probe-tone profiles: how strongly each of the 12
     pitch classes belongs to a major and a minor key, from the listening
     experiments. Rotating these round the circle and correlating is the
     textbook key-finding method. */
  var MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                       2.52, 5.19, 2.39, 3.66, 2.29, 2.88];
  var MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                       2.54, 4.75, 3.98, 2.69, 3.34, 3.17];

  // ---------------------------------------------------------------- FFT
  function fft(re, im) {
    var n = re.length, i, j = 0, k, m, t;
    for (i = 1; i < n; i++) {
      var bit = n >> 1;
      for (; j & bit; bit >>= 1) { j ^= bit; }
      j ^= bit;
      if (i < j) {
        t = re[i]; re[i] = re[j]; re[j] = t;
        t = im[i]; im[i] = im[j]; im[j] = t;
      }
    }
    for (m = 2; m <= n; m <<= 1) {
      var ang = -2 * Math.PI / m;
      var wr = Math.cos(ang), wi = Math.sin(ang);
      for (i = 0; i < n; i += m) {
        var cr = 1, ci = 0;
        for (k = 0; k < m / 2; k++) {
          var ar = re[i + k], ai = im[i + k];
          var br = re[i + k + m / 2], bi = im[i + k + m / 2];
          var tr = br * cr - bi * ci, ti = br * ci + bi * cr;
          re[i + k] = ar + tr; im[i + k] = ai + ti;
          re[i + k + m / 2] = ar - tr; im[i + k + m / 2] = ai - ti;
          var ncr = cr * wr - ci * wi;
          ci = cr * wi + ci * wr; cr = ncr;
        }
      }
    }
  }

  function mono(channels) {
    var n = channels[0].length;
    var out = new Float32Array(n);
    var c, i, ch = channels.length;
    for (c = 0; c < ch; c++) {
      var d = channels[c];
      for (i = 0; i < n; i++) { out[i] += d[i] / ch; }
    }
    return out;
  }

  // ------------------------------------------------------------ onsets
  /* Spectral-flux envelope: how much MORE energy each frame holds than
     the last, summed over the low and mid bands where beats live. Rising
     energy only - a decay is not an onset. */
  function onsetEnvelope(sig, rate) {
    var N = 1024, hop = 256;
    var win = new Float32Array(N), i;
    for (i = 0; i < N; i++) {
      win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / N);
    }
    var frames = Math.max(1, Math.floor((sig.length - N) / hop));
    var env = new Float32Array(frames);
    var prev = new Float32Array(N / 2);
    var re = new Float32Array(N), im = new Float32Array(N);
    // Beats live below ~5 kHz; above that is mostly cymbal wash and noise.
    var top = Math.min(N / 2, Math.floor(5000 / (rate / N)));
    for (var f = 0; f < frames; f++) {
      var base = f * hop;
      for (i = 0; i < N; i++) { re[i] = sig[base + i] * win[i]; im[i] = 0; }
      fft(re, im);
      var flux = 0;
      for (i = 1; i < top; i++) {
        var mag = Math.sqrt(re[i] * re[i] + im[i] * im[i]);
        var d = mag - prev[i];
        if (d > 0) { flux += d; }
        prev[i] = mag;
      }
      env[f] = flux;
    }
    // Subtract a local mean so a loud chorus does not outvote a quiet verse.
    var smoothed = new Float32Array(frames);
    var W = 12;
    for (f = 0; f < frames; f++) {
      var lo = Math.max(0, f - W), hi = Math.min(frames, f + W + 1), s = 0;
      for (i = lo; i < hi; i++) { s += env[i]; }
      smoothed[f] = Math.max(0, env[f] - s / (hi - lo));
    }
    return {env: smoothed, rate: rate / hop};
  }

  /* Autocorrelation of the onset envelope over musically plausible lags,
     then the strongest peak. Multiplying each candidate by its own
     harmonic support (2x and 4x the lag) is what keeps a straight
     four-on-the-floor from reporting the eighth-note pulse. */
  function bpmFromEnvelope(env, envRate, minBpm, maxBpm) {
    var minLag = Math.max(2, Math.floor(envRate * 60 / maxBpm));
    var maxLag = Math.min(env.length - 1, Math.ceil(envRate * 60 / minBpm));
    if (maxLag <= minLag) { return null; }
    var best = null, scores = [];
    for (var lag = minLag; lag <= maxLag; lag++) {
      var s = 0, n = env.length - lag;
      for (var i = 0; i < n; i++) { s += env[i] * env[i + lag]; }
      s /= n;
      scores.push(s);
    }
    // Harmonic reinforcement: a real beat period also correlates at 2x/4x.
    for (var k = 0; k < scores.length; k++) {
      var lag2 = (minLag + k) * 2 - minLag;
      var lag4 = (minLag + k) * 4 - minLag;
      var boost = scores[k];
      if (lag2 < scores.length) { boost += 0.5 * scores[lag2]; }
      if (lag4 < scores.length) { boost += 0.25 * scores[lag4]; }
      if (best === null || boost > best.score) {
        best = {score: boost, lag: minLag + k, raw: scores[k]};
      }
    }
    if (!best) { return null; }
    // Parabolic interpolation around the peak: sub-sample lag precision,
    // which at these hop sizes is the difference between 120 and 119.4.
    var bi = best.lag - minLag;
    var lagF = best.lag;
    if (bi > 0 && bi < scores.length - 1) {
      var y0 = scores[bi - 1], y1 = scores[bi], y2 = scores[bi + 1];
      var denom = y0 - 2 * y1 + y2;
      if (denom !== 0) {
        lagF = best.lag + 0.5 * (y0 - y2) / denom;
      }
    }
    var mean = 0;
    for (k = 0; k < scores.length; k++) { mean += scores[k]; }
    mean /= scores.length;
    return {
      bpm: envRate * 60 / lagF,
      // How far the winning peak stands above the average lag. Clamped to
      // 0..1 and reported as-is; it is a sharpness measure, not a promise.
      confidence: mean > 0
        ? Math.max(0, Math.min(1, (best.raw / mean - 1) / 4))
        : 0,
    };
  }

  function detectBpm(channels, rate, opts) {
    opts = opts || {};
    var sig = mono(channels);
    var oe = onsetEnvelope(sig, rate);
    var got = bpmFromEnvelope(oe.env, oe.rate,
                              opts.minBpm || 60, opts.maxBpm || 190);
    if (!got) { return null; }
    var bpm = Math.round(got.bpm * 10) / 10;
    return {
      bpm: bpm,
      confidence: Math.round(got.confidence * 100) / 100,
      // Autocorrelation cannot separate a tempo from its half or double.
      alternates: [Math.round(bpm / 2 * 10) / 10,
                   Math.round(bpm * 2 * 10) / 10]
                  .filter(function (b) { return b >= 40 && b <= 260; }),
    };
  }

  /* Where the beats actually FALL, not just how fast they are.
   *
   * detectBpm gives the spacing; this adds the phase - which is the half
   * that matters for cutting. Knowing a track is 128 BPM tells you nothing
   * about where to start a clip; knowing the first beat lands at 0.34 s
   * tells you everything. Phase is found by testing every offset within
   * one beat period against the onset envelope and keeping the one the
   * transients agree with.
   *
   * Returns null rather than a guess when there is not enough to measure.
   */
  function beatGrid(channels, rate, opts) {
    opts = opts || {};
    var oe = onsetEnvelope(mono(channels), rate);
    var bpm = opts.bpm;
    if (!bpm) {
      var got = bpmFromEnvelope(oe.env, oe.rate,
                                opts.minBpm || 60, opts.maxBpm || 190);
      if (!got) { return null; }
      bpm = got.bpm;
    }
    var period = oe.rate * 60 / bpm;          // envelope frames per beat
    if (!(period > 1) || oe.env.length < period * 2) { return null; }

    var steps = Math.max(1, Math.round(period));
    var scores = [], best = null;
    for (var off = 0; off < steps; off++) {
      var sum = 0, n = 0;
      for (var t = off; t < oe.env.length; t += period) {
        sum += oe.env[Math.round(t)] || 0;
        n++;
      }
      var score = n ? sum / n : 0;
      scores.push(score);
      if (!best || score > best.score) { best = {score: score, off: off}; }
    }
    var mean = 0;
    for (var i = 0; i < scores.length; i++) { mean += scores[i]; }
    mean /= scores.length || 1;

    /* Silence has no beats. Without this the autocorrelation still returns
       its best lag over a flat envelope and the grid comes back looking
       authoritative - 191 BPM on a track with nothing in it - which is
       worse than admitting there is nothing to measure. */
    if (!(mean > 0) || !(best.score > 0)) { return null; }

    return {
      bpm: Math.round(bpm * 10) / 10,
      period: 60 / bpm,                       // seconds per beat
      firstBeat: best.off / oe.rate,          // seconds
      /* How much the winning phase stands above the average one. A loop
         with no transients scores flat everywhere and lands near 0. */
      confidence: mean > 0
        ? Math.max(0, Math.min(1, (best.score / mean - 1))) : 0,
    };
  }

  /* Nearest beat to a time. `bars` snaps to every Nth beat instead - use 4
     for downbeats, which is usually where a clip wants to start. */
  function snapToBeat(seconds, grid, bars) {
    if (!grid || !(grid.period > 0)) { return seconds; }
    var step = grid.period * (bars && bars > 1 ? bars : 1);
    var n = Math.round((seconds - grid.firstBeat) / step);
    var at = grid.firstBeat + n * step;
    return at < 0 ? grid.firstBeat : at;      // never snap before the track
  }

  /* Beat times inside a window, for drawing a grid. */
  function beatsBetween(grid, from, to, bars) {
    if (!grid || !(grid.period > 0)) { return []; }
    var step = grid.period * (bars && bars > 1 ? bars : 1);
    var out = [];
    var n = Math.ceil((from - grid.firstBeat) / step);
    for (var t = grid.firstBeat + n * step; t <= to; t += step) {
      if (t >= from) { out.push(t); }
      if (out.length > 4096) { break; }       // a guard, not a limit anyone hits
    }
    return out;
  }

  // --------------------------------------------------------------- key
  /* Chroma: fold spectral energy onto the 12 pitch classes. Weighted by
     magnitude, restricted to the range where pitch is unambiguous. */
  function chroma(sig, rate) {
    var N = 4096, hop = 2048;
    var win = new Float32Array(N), i;
    for (i = 0; i < N; i++) {
      win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / N);
    }
    var out = new Float64Array(12);
    var re = new Float32Array(N), im = new Float32Array(N);
    var frames = Math.max(1, Math.floor((sig.length - N) / hop));
    var binHz = rate / N;
    var lo = Math.max(1, Math.floor(55 / binHz));    // A1
    var hi = Math.min(N / 2, Math.floor(2100 / binHz)); // ~C7
    for (var f = 0; f < frames; f++) {
      var base = f * hop;
      for (i = 0; i < N; i++) { re[i] = sig[base + i] * win[i]; im[i] = 0; }
      fft(re, im);
      for (i = lo; i < hi; i++) {
        var mag = Math.sqrt(re[i] * re[i] + im[i] * im[i]);
        if (mag <= 0) { continue; }
        var hz = i * binHz;
        // MIDI note number, then pitch class. 69 = A4 = 440 Hz.
        var midi = 69 + 12 * Math.log(hz / 440) / Math.LN2;
        var pc = ((Math.round(midi) % 12) + 12) % 12;
        out[pc] += mag;
      }
    }
    return out;
  }

  function correlate(a, b) {
    var n = a.length, i, ma = 0, mb = 0;
    for (i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
    ma /= n; mb /= n;
    var num = 0, da = 0, db = 0;
    for (i = 0; i < n; i++) {
      var x = a[i] - ma, y = b[i] - mb;
      num += x * y; da += x * x; db += y * y;
    }
    return (da > 0 && db > 0) ? num / Math.sqrt(da * db) : 0;
  }

  function detectKey(channels, rate) {
    var c = chroma(mono(channels), rate);
    var total = 0, i;
    for (i = 0; i < 12; i++) { total += c[i]; }
    if (total <= 0) { return null; }
    var ranked = [];
    for (var root = 0; root < 12; root++) {
      var rotated = new Float64Array(12);
      for (i = 0; i < 12; i++) { rotated[i] = c[(root + i) % 12]; }
      ranked.push({key: NOTES[root] + " major", root: root, mode: "major",
                   score: correlate(rotated, MAJOR_PROFILE)});
      ranked.push({key: NOTES[root] + " minor", root: root, mode: "minor",
                   score: correlate(rotated, MINOR_PROFILE)});
    }
    ranked.sort(function (a, b) { return b.score - a.score; });
    var chromaOut = [];
    for (i = 0; i < 12; i++) {
      chromaOut.push(Math.round(c[i] / total * 1000) / 1000);
    }
    return {
      key: ranked[0].key,
      root: ranked[0].root,
      mode: ranked[0].mode,
      score: Math.round(ranked[0].score * 100) / 100,
      runnerUp: ranked[1].key,
      runnerUpScore: Math.round(ranked[1].score * 100) / 100,
      chroma: chromaOut,
      notes: NOTES.slice(),
    };
  }

  // ------------------------------------------------------- time stretch
  /* WSOLA. Output frames are written at a fixed hop; each input frame is
     allowed to slide within +/- SEEK samples to the position whose
     leading edge best matches the tail already written, so consecutive
     frames splice at matching phase. */
  function stretchChannel(input, ratio, frameLen, seek) {
    var hopOut = Math.floor(frameLen / 2);
    var hopIn = hopOut / ratio;
    var outLen = Math.max(1, Math.ceil(input.length * ratio) + frameLen);
    var out = new Float32Array(outLen);
    var norm = new Float32Array(outLen);
    var win = new Float32Array(frameLen), i;
    for (i = 0; i < frameLen; i++) {
      win[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / frameLen);
    }
    /* The search window has to span at least one period of the lowest
       frequency that matters, or bass can never be spliced at matching
       phase and the low end goes hollow and phasey. 44.1 kHz / 512 is
       86 Hz; the old +/-128 could only align down to about 345 Hz, which
       is why a 110 Hz tone came out 20 dB dirtier than a 440 Hz one. */
    var cmp = Math.min(hopOut, 600);
    var outPos = 0, inPos = 0;

    /* Normalised against the CANDIDATE's own energy. Plain cross-
       correlation just picks whichever offset is loudest, which is not the
       same as the offset that lines up - and on real music it is the
       reason splices audibly thump. The reference energy is constant
       across candidates, so it can be left out. */
    function score(cand, step) {
      var num = 0, den = 0;
      for (var k = 0; k < cmp; k += step) {
        var a = input[cand + k];
        num += a * out[outPos + k];
        den += a * a;
      }
      return den > 1e-9 ? num / Math.sqrt(den) : -Infinity;
    }

    while (outPos + frameLen < outLen && inPos + frameLen < input.length) {
      var pick = Math.round(inPos);
      if (outPos > 0 && seek > 0) {
        var lo = Math.max(0, pick - seek);
        var hi = Math.min(input.length - frameLen - 1, pick + seek);
        // Coarse pass, then refine: full resolution alignment for a
        // fraction of the work an exhaustive search would cost.
        var bestScore = -Infinity, bestAt = pick, cand;
        for (cand = lo; cand <= hi; cand += 8) {
          var sc = score(cand, 2);
          if (sc > bestScore) { bestScore = sc; bestAt = cand; }
        }
        var flo = Math.max(lo, bestAt - 8), fhi = Math.min(hi, bestAt + 8);
        bestScore = -Infinity;
        for (cand = flo; cand <= fhi; cand++) {
          var sf = score(cand, 1);
          if (sf > bestScore) { bestScore = sf; bestAt = cand; }
        }
        pick = bestAt;
      }
      for (i = 0; i < frameLen; i++) {
        out[outPos + i] += input[pick + i] * win[i];
        norm[outPos + i] += win[i];
      }
      outPos += hopOut;
      inPos += hopIn;
    }
    var used = Math.min(outLen, outPos + frameLen);
    var res = new Float32Array(used);
    for (i = 0; i < used; i++) {
      res[i] = norm[i] > 1e-6 ? out[i] / norm[i] : out[i];
    }
    return res;
  }

  /* Second-order lowpass, coefficients in normalised frequency so the
     caller does not need the sample rate. Used to keep a pitch-up
     resample from folding everything above the new Nyquist back down as
     aliasing, which is the harshness people hear on a cheap shifter. */
  function lowpass(data, cutoffFrac) {
    if (!(cutoffFrac > 0) || cutoffFrac >= 0.5) { return data; }
    var w0 = 2 * Math.PI * cutoffFrac;
    var cs = Math.cos(w0), alpha = Math.sin(w0) / (2 * 0.7071);
    var a0 = 1 + alpha;
    var b0 = (1 - cs) / 2 / a0, b1 = (1 - cs) / a0, b2 = b0;
    var a1 = -2 * cs / a0, a2 = (1 - alpha) / a0;
    var out = data;
    // Two passes for a steeper skirt; the shifter needs the stopband.
    for (var pass = 0; pass < 2; pass++) {
      var x1 = 0, x2 = 0, y1 = 0, y2 = 0;
      var src = out;
      out = new Float32Array(src.length);
      for (var i = 0; i < src.length; i++) {
        var x0 = src[i];
        var y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
        x2 = x1; x1 = x0; y2 = y1; y1 = y0;
        out[i] = y0;
      }
    }
    return out;
  }

  /* Catmull-Rom interpolated resample. Linear interpolation is a crude
     lowpass whose error rises with frequency, so it dulls and roughens
     every shift; a cubic fit through four points costs a handful of
     multiplies and is far closer to the real waveform between samples.
     Reading faster than 1:1 also needs the band limited first, or
     everything above the new Nyquist folds back as aliasing. */
  function resample(input, ratio) {
    var src = ratio > 1 ? lowpass(input, 0.45 / ratio) : input;
    var outLen = Math.max(1, Math.floor(src.length / ratio));
    var out = new Float32Array(outLen);
    var last = src.length - 1;
    for (var i = 0; i < outLen; i++) {
      var pos = i * ratio;
      var i1 = Math.floor(pos);
      var t = pos - i1;
      var i0 = i1 > 0 ? i1 - 1 : 0;
      var i2 = i1 + 1 <= last ? i1 + 1 : last;
      var i3 = i1 + 2 <= last ? i1 + 2 : i2;
      var p0 = src[i0], p1 = src[i1], p2 = src[i2], p3 = src[i3];
      var a = -0.5 * p0 + 1.5 * p1 - 1.5 * p2 + 0.5 * p3;
      var b = p0 - 2.5 * p1 + 2 * p2 - 0.5 * p3;
      var c = -0.5 * p0 + 0.5 * p2;
      out[i] = ((a * t + b) * t + c) * t + p1;
    }
    return out;
  }

  /* Both transforms in one pass so the UI only has one thing to drive.
     tempo: output length multiplier (0.5 = half speed, 2 = double).
     semitones: pitch offset, tempo untouched. cents: fine trim. */
  function transform(channels, opts, onProgress, done) {
    opts = opts || {};
    var tempo = opts.tempo || 1;
    var semis = (opts.semitones || 0) + (opts.cents || 0) / 100;
    var frameLen = opts.frameLen || 2048;
    // Wide enough to align one period of the deepest bass; see the
    // note in stretchChannel for why 128 was not.
    var seek = opts.seek === undefined ? 512 : opts.seek;
    var pitchRatio = Math.pow(2, semis / 12);
    /* Pitch comes from resampling: reading the input pitchRatio times
       faster raises it by that ratio and shortens it to 1/pitchRatio, so
       the stretch has to undo that as well as apply the tempo. */
    var stretch = tempo * pitchRatio;
    var out = [];
    var idx = 0;

    function step() {
      if (idx >= channels.length) {
        if (onProgress) { onProgress(1); }
        done(out);
        return;
      }
      var ch = channels[idx];
      var work = ch;
      if (pitchRatio !== 1) { work = resample(work, pitchRatio); }
      if (Math.abs(stretch - 1) > 1e-6) {
        work = stretchChannel(work, stretch, frameLen, seek);
      } else if (work === ch) {
        work = ch.slice();
      }
      out.push(work);
      idx++;
      if (onProgress) { onProgress(idx / channels.length); }
      yieldNow(step);
    }
    yieldNow(step);
  }

  /* What a given tempo/pitch pair does to a known BPM and key, so the
     panel can state the result instead of leaving the user to do it. */
  function project(bpm, keyRoot, keyMode, tempo, semitones) {
    var out = {};
    if (typeof bpm === "number" && bpm > 0) {
      out.bpm = Math.round(bpm / tempo * 10) / 10;
    }
    if (typeof keyRoot === "number") {
      var shifted = ((keyRoot + Math.round(semitones)) % 12 + 12) % 12;
      out.key = NOTES[shifted] + " " + keyMode;
    }
    return out;
  }

  var api = {
    detectBpm: detectBpm,
    detectKey: detectKey,
    beatGrid: beatGrid,
    snapToBeat: snapToBeat,
    beatsBetween: beatsBetween,
    transform: transform,
    project: project,
    NOTES: NOTES,
    // Exposed for the Node checks: each piece verified on its own.
    _fft: fft, _onsetEnvelope: onsetEnvelope, _chroma: chroma,
    _stretchChannel: stretchChannel, _resample: resample,
    _lowpass: lowpass,
    _correlate: correlate,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.SBTempoKey = api;
})(typeof self !== "undefined" ? self : this);
