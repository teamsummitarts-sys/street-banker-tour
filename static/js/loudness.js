/* Street Banker · SB-15 LDN-1 — loudness, to the standard.
 *
 * Peak metering tells you about clipping and nothing about how loud you
 * will actually sound. Every streaming platform normalises by LOUDNESS, so
 * this is the number that decides whether your record arrives at the same
 * level as the one before it. That measurement is specified, not a matter
 * of taste, so this implements the specification rather than an
 * approximation of it: ITU-R BS.1770-4, with loudness range from EBU Tech
 * 3342.
 *
 *   K-weighting   Two biquads: a high shelf standing in for the acoustic
 *                 effect of a head, then a high-pass (RLB) that discounts
 *                 the very low end the ear barely weights. The published
 *                 coefficients are given for 48 kHz only, so they are
 *                 DERIVED here for whatever rate the file actually is -
 *                 using 48 kHz numbers on a 44.1 kHz file is a real and
 *                 common error, and it skews the answer.
 *
 *   Integrated    Mean square per 400 ms block, 75% overlap, then the two
 *                 gates the standard requires: an absolute one at -70 LUFS
 *                 so silence cannot drag the average down, and a relative
 *                 one 10 LU below the ungated mean so quiet passages do
 *                 not either. Ungated averaging is the single most common
 *                 way to get this wrong.
 *
 *   LRA           EBU 3342: 3-second blocks, gated 20 LU relative, then
 *                 the spread from the 10th to the 95th percentile.
 *
 *   True peak     The peak BETWEEN samples, which is what a converter and
 *                 every lossy encoder actually see. Sample peak can read
 *                 -3 dB on a signal that genuinely hits 0. Measured by
 *                 4x polyphase oversampling, the minimum the standard
 *                 allows; that method is known to under-read by up to
 *                 about 0.7 dB in the worst case, which is why mastering
 *                 ceilings sit at -1 dBTP rather than 0.
 *
 * Pure array maths - no DOM, no Web Audio - so the whole thing is checked
 * in Node against the EBU Tech 3341 compliance cases, where the right
 * answer is published and not a matter of opinion.
 */
(function (root) {
  "use strict";

  var ABS_GATE = -70.0;          // LUFS, absolute
  var REL_GATE = -10.0;          // LU below the ungated mean
  var LRA_GATE = -20.0;          // LU, for loudness range
  var OFFSET = -0.691;           // the BS.1770 calibration constant

  /* Derive the K-weighting biquads for this sample rate. These constants
     are the ones that reproduce the published 48 kHz coefficient table
     exactly, which the checks verify rather than assume. */
  function kCoefficients(rate) {
    // Stage 1: high shelf, ~+4 dB above about 1.7 kHz.
    var f0 = 1681.974450955533;
    var G = 3.999843853973347;
    var Q = 0.7071752369554196;
    var K = Math.tan(Math.PI * f0 / rate);
    var Vh = Math.pow(10, G / 20);
    var Vb = Math.pow(Vh, 0.4996667741545416);
    var den = 1 + K / Q + K * K;
    var s1 = {
      b0: (Vh + Vb * K / Q + K * K) / den,
      b1: 2 * (K * K - Vh) / den,
      b2: (Vh - Vb * K / Q + K * K) / den,
      a1: 2 * (K * K - 1) / den,
      a2: (1 - K / Q + K * K) / den,
    };
    // Stage 2: RLB high pass at about 38 Hz.
    f0 = 38.13547087602444;
    Q = 0.5003270373238773;
    K = Math.tan(Math.PI * f0 / rate);
    var den2 = 1 + K / Q + K * K;
    var s2 = {
      b0: 1, b1: -2, b2: 1,
      a1: 2 * (K * K - 1) / den2,
      a2: (1 - K / Q + K * K) / den2,
    };
    return [s1, s2];
  }

  function biquad(data, c) {
    var out = new Float64Array(data.length);
    var x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (var i = 0; i < data.length; i++) {
      var x0 = data[i];
      var y0 = c.b0 * x0 + c.b1 * x1 + c.b2 * x2 - c.a1 * y1 - c.a2 * y2;
      x2 = x1; x1 = x0; y2 = y1; y1 = y0;
      out[i] = y0;
    }
    return out;
  }

  function kWeight(channel, rate) {
    var c = kCoefficients(rate);
    return biquad(biquad(channel, c[0]), c[1]);
  }

  /* BS.1770 channel weights. Left, right and centre count fully; the
     surrounds are weighted up because they contribute more loudness than
     their level suggests. Anything beyond five channels is weighted 1. */
  function channelWeights(count) {
    var full = [1.0, 1.0, 1.0, 1.41, 1.41];
    var out = [];
    for (var i = 0; i < count; i++) { out.push(i < 5 ? full[i] : 1.0); }
    return out;
  }

  /* Mean square of each K-weighted channel over overlapping blocks.
     Returns one entry per block: the per-channel mean squares, which the
     gates then work over. */
  function blockPowers(weighted, rate, blockMs, hopMs) {
    var block = Math.round(rate * blockMs / 1000);
    var hop = Math.round(rate * hopMs / 1000);
    var n = weighted[0].length;
    var out = [];
    if (n < block) { return out; }
    for (var start = 0; start + block <= n; start += hop) {
      var per = [];
      for (var c = 0; c < weighted.length; c++) {
        var d = weighted[c], sum = 0;
        for (var i = start; i < start + block; i++) { sum += d[i] * d[i]; }
        per.push(sum / block);
      }
      out.push(per);
    }
    return out;
  }

  function loudnessOf(powers, weights) {
    var sum = 0;
    for (var c = 0; c < powers.length; c++) { sum += weights[c] * powers[c]; }
    return sum > 0 ? OFFSET + 10 * Math.log(sum) / Math.LN10 : -Infinity;
  }

  function meanPowers(blocks, weights) {
    if (!blocks.length) { return -Infinity; }
    var chans = blocks[0].length;
    var acc = new Float64Array(chans);
    for (var b = 0; b < blocks.length; b++) {
      for (var c = 0; c < chans; c++) { acc[c] += blocks[b][c]; }
    }
    for (var c2 = 0; c2 < chans; c2++) { acc[c2] /= blocks.length; }
    return loudnessOf(acc, weights);
  }

  /* Integrated loudness, both gates applied in the order the standard
     sets out. Returns null when there is not even one full block, rather
     than a number that would be meaningless. */
  function integrated(weighted, rate) {
    var weights = channelWeights(weighted.length);
    var blocks = blockPowers(weighted, rate, 400, 100);
    if (!blocks.length) { return null; }
    // Absolute gate first: digital silence must not pull the mean down.
    var absKept = blocks.filter(function (p) {
      return loudnessOf(p, weights) > ABS_GATE;
    });
    if (!absKept.length) { return null; }
    // Relative gate is measured against the absolute-gated mean, not the
    // raw one - getting that order wrong shifts quiet records.
    var relThreshold = meanPowers(absKept, weights) + REL_GATE;
    var kept = absKept.filter(function (p) {
      return loudnessOf(p, weights) > relThreshold;
    });
    if (!kept.length) { return null; }
    return meanPowers(kept, weights);
  }

  function blockLoudness(weighted, rate, blockMs, hopMs) {
    var weights = channelWeights(weighted.length);
    return blockPowers(weighted, rate, blockMs, hopMs).map(function (p) {
      return loudnessOf(p, weights);
    });
  }

  function percentile(sorted, p) {
    if (!sorted.length) { return null; }
    var idx = (sorted.length - 1) * p;
    var lo = Math.floor(idx), hi = Math.ceil(idx);
    if (lo === hi) { return sorted[lo]; }
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  }

  /* Loudness range: how much the level actually moves across the record.
     A number near zero means it is squashed flat; a large one means it
     breathes (or that the quiet intro is dragging it). */
  function loudnessRange(weighted, rate) {
    var weights = channelWeights(weighted.length);
    var blocks = blockPowers(weighted, rate, 3000, 1000);
    if (blocks.length < 2) { return null; }
    var absKept = blocks.filter(function (p) {
      return loudnessOf(p, weights) > ABS_GATE;
    });
    if (absKept.length < 2) { return null; }
    var threshold = meanPowers(absKept, weights) + LRA_GATE;
    var vals = absKept.map(function (p) { return loudnessOf(p, weights); })
                      .filter(function (l) { return l > threshold; })
                      .sort(function (a, b) { return a - b; });
    if (vals.length < 2) { return null; }
    var lo = percentile(vals, 0.10), hi = percentile(vals, 0.95);
    return Math.max(0, hi - lo);
  }

  /* 4x polyphase interpolation FIR: a windowed sinc, decomposed so each
     output phase is a short dot product rather than a full upsample. */
  function interpolatorPhases(factor, tapsPerPhase) {
    var N = factor * tapsPerPhase;
    var centre = (N - 1) / 2;
    var h = new Float64Array(N);
    for (var i = 0; i < N; i++) {
      var t = (i - centre) / factor;
      var sinc = Math.abs(t) < 1e-9
        ? 1 : Math.sin(Math.PI * t) / (Math.PI * t);
      // Blackman window: enough stopband to keep images out of the peak.
      var w = 0.42 - 0.5 * Math.cos(2 * Math.PI * i / (N - 1))
              + 0.08 * Math.cos(4 * Math.PI * i / (N - 1));
      h[i] = sinc * w;
    }
    var phases = [];
    for (var p = 0; p < factor; p++) {
      var ph = [];
      for (var j = p; j < N; j += factor) { ph.push(h[j]); }
      /* Normalise each phase to unity DC gain. Without this the phases
         have slightly different gains, which both modulates the output
         and overshoots - it read a plain 1 kHz sine 0.44 dB hotter than
         its own sample peak, inventing headroom that is not there. A true
         peak meter that over-reads is worse than useless: it makes people
         turn masters down for no reason. */
      var sum = 0;
      for (var k = 0; k < ph.length; k++) { sum += ph[k]; }
      if (Math.abs(sum) > 1e-12) {
        for (var m = 0; m < ph.length; m++) { ph[m] /= sum; }
      }
      phases.push(ph);
    }
    return phases;
  }

  var _phaseCache = {};

  function truePeak(channels, factor, tapsPerPhase) {
    factor = factor || 4;
    tapsPerPhase = tapsPerPhase || 12;
    var key = factor + ":" + tapsPerPhase;
    var phases = _phaseCache[key]
      || (_phaseCache[key] = interpolatorPhases(factor, tapsPerPhase));
    var peak = 0;
    for (var c = 0; c < channels.length; c++) {
      var d = channels[c], n = d.length;
      for (var i = 0; i < n; i++) {
        // The sample itself is one of the interpolated points.
        var a = d[i] < 0 ? -d[i] : d[i];
        if (a > peak) { peak = a; }
        for (var p = 0; p < phases.length; p++) {
          var ph = phases[p], acc = 0;
          for (var j = 0; j < ph.length; j++) {
            var idx = i - j + (tapsPerPhase >> 1);
            if (idx >= 0 && idx < n) { acc += ph[j] * d[idx]; }
          }
          var m = acc < 0 ? -acc : acc;
          if (m > peak) { peak = m; }
        }
      }
    }
    return peak;
  }

  function toDb(linear) {
    return linear > 0 ? 20 * Math.log(linear) / Math.LN10 : -Infinity;
  }

  function samplePeak(channels) {
    var peak = 0;
    for (var c = 0; c < channels.length; c++) {
      var d = channels[c];
      for (var i = 0; i < d.length; i++) {
        var a = d[i] < 0 ? -d[i] : d[i];
        if (a > peak) { peak = a; }
      }
    }
    return peak;
  }

  /* Published normalisation targets. These are the figures the platforms
     state; they are references for planning a master, not something this
     app verifies against the services, and they do move. Ceilings are the
     true-peak maximum each recommends. */
  var TARGETS = [
    {key: "spotify", name: "Spotify", lufs: -14, ceiling: -1},
    {key: "apple", name: "Apple Music", lufs: -16, ceiling: -1},
    {key: "youtube", name: "YouTube", lufs: -14, ceiling: -1},
    {key: "amazon", name: "Amazon Music", lufs: -14, ceiling: -2},
    {key: "tidal", name: "Tidal", lufs: -14, ceiling: -1},
    {key: "deezer", name: "Deezer", lufs: -15, ceiling: -1},
    {key: "broadcast", name: "Broadcast (EBU R128)", lufs: -23, ceiling: -1},
  ];

  /* What a target actually means for this master: how far off it is, which
     way the platform will move it, and what a clean bounce would need. */
  function againstTarget(lufs, truePeakDb, target) {
    var delta = lufs === null ? null : Math.round((lufs - target.lufs) * 10) / 10;
    var headroom = truePeakDb === -Infinity
      ? null : Math.round((target.ceiling - truePeakDb) * 10) / 10;
    var out = {
      key: target.key, name: target.name,
      lufs: target.lufs, ceiling: target.ceiling,
      delta: delta, gain: delta === null ? null : -delta,
      peakHeadroom: headroom,
      over: delta !== null && delta > 0.5,
      under: delta !== null && delta < -0.5,
    };
    if (delta !== null) {
      /* Turning a master down is lossless; turning it up is not, because
         the true peak comes up with it. Only the second case can clip. */
      out.clipsIfRaised = truePeakDb !== -Infinity
        && (truePeakDb + out.gain) > target.ceiling;
    }
    return out;
  }

  function analyse(channels, rate, opts) {
    opts = opts || {};
    var weighted = channels.map(function (ch) { return kWeight(ch, rate); });
    var lufs = integrated(weighted, rate);
    var tp = truePeak(channels, opts.oversample || 4);
    var tpDb = toDb(tp);
    var spDb = toDb(samplePeak(channels));
    var short = blockLoudness(weighted, rate, 3000, 1000);
    var momentary = blockLoudness(weighted, rate, 400, 100);
    var finite = short.filter(function (v) { return isFinite(v); });
    return {
      integrated: lufs === null ? null : Math.round(lufs * 10) / 10,
      range: (function () {
        var r = loudnessRange(weighted, rate);
        return r === null ? null : Math.round(r * 10) / 10;
      })(),
      truePeak: tpDb === -Infinity ? null : Math.round(tpDb * 100) / 100,
      samplePeak: spDb === -Infinity ? null : Math.round(spDb * 100) / 100,
      // How much the inter-sample peaks exceed what a sample meter shows.
      intersample: (tpDb === -Infinity || spDb === -Infinity)
        ? null : Math.round((tpDb - spDb) * 100) / 100,
      shortTermMax: finite.length ? Math.round(Math.max.apply(null, finite) * 10) / 10 : null,
      momentaryMax: (function () {
        var f = momentary.filter(function (v) { return isFinite(v); });
        return f.length ? Math.round(Math.max.apply(null, f) * 10) / 10 : null;
      })(),
      shortTerm: short,
      momentary: momentary,
      seconds: channels[0].length / rate,
      channels: channels.length,
      rate: rate,
      targets: TARGETS.map(function (t) {
        return againstTarget(lufs === null ? null : Math.round(lufs * 10) / 10,
                             tpDb, t);
      }),
    };
  }

  var api = {
    analyse: analyse,
    integrated: integrated,
    loudnessRange: loudnessRange,
    truePeak: truePeak,
    samplePeak: samplePeak,
    kWeight: kWeight,
    kCoefficients: kCoefficients,
    blockLoudness: blockLoudness,
    channelWeights: channelWeights,
    againstTarget: againstTarget,
    toDb: toDb,
    TARGETS: TARGETS,
    ABS_GATE: ABS_GATE,
    REL_GATE: REL_GATE,
    _interpolatorPhases: interpolatorPhases,
    _blockPowers: blockPowers,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.SBLoudness = api;
})(typeof self !== "undefined" ? self : this);
