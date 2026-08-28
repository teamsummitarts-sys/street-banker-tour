/* Rough Split — classical DSP stem approximation for the Stem Deck.

   NOT machine learning and never sold as such: this is harmonic/percussive
   separation (Fitzgerald 2010 median-filter HPSS) plus centre extraction
   and band splitting, computed right here in the tab. Nothing uploads.

   The four lanes PARTITION the record: every time-frequency bin of the
   original is assigned across the four masks, which sum to exactly 1, so
   Vocals + Drums + Bass + Instruments reconstructs the input sample for
   sample (within float rounding and the analysis window's edges). Solo a
   lane and you hear a rough isolation; play all four and you hear your
   record.

   Pure array math, no DOM, no WebAudio: testable in Node, called from
   rackdsp.js with channel Float32Arrays.

   Pipeline (2048-point Hann frames, 512 hop — COLA-safe):
     pass 1: mixture magnitude spectrogram
             -> median filter along time  = harmonic-enhanced
             -> median filter along freq  = percussive-enhanced
             -> soft masks (p = 2)
     pass 2: re-FFT each frame, apply the four partition masks per bin,
             overlap-add eight inverse FFTs (4 stems x 2 channels)

   Masks per bin (always summing to 1):
     drums  = P                          (percussive)
     bass   = (1-P) x B                  (harmonic, below the bass split)
     vocals = (1-P) x (1-B) x W          (harmonic, centred, vocal band)
     other  = (1-P) x (1-B) x (1-W)      (everything else)
   where B is a soft low-frequency edge and W = centredness x vocal-band
   weight. Centredness uses channel balance and phase coherence, so on
   mono sources W falls back to the band weight alone - rougher, still
   honest. */
(function (global) {
  "use strict";

  /* Yield between work slabs WITHOUT setTimeout: background tabs clamp
     timers to a full second per tick, which would stretch a one-minute
     split into an hour the moment the user switches tabs. MessageChannel
     posts are not throttled that way. Node has no MessageChannel in old
     versions - setImmediate covers it there. */
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

  var N = 2048;            // frame size
  var HOP = 512;           // 75% overlap
  var MED_T = 13;          // median kernel along time (harmonic)
  var MED_F = 13;          // median kernel along freq (percussive)
  var BINS = N / 2 + 1;

  /* ---- FFT: iterative radix-2, complex, in-place ----------------------- */
  var revTable = null, twRe = null, twIm = null;
  function fftInit() {
    if (revTable) { return; }
    revTable = new Uint32Array(N);
    var bits = Math.log2(N);
    for (var i = 0; i < N; i++) {
      var r = 0;
      for (var b = 0; b < bits; b++) { r = (r << 1) | ((i >> b) & 1); }
      revTable[i] = r;
    }
    twRe = new Float64Array(N / 2);
    twIm = new Float64Array(N / 2);
    for (var k = 0; k < N / 2; k++) {
      twRe[k] = Math.cos(-2 * Math.PI * k / N);
      twIm[k] = Math.sin(-2 * Math.PI * k / N);
    }
  }

  function fft(re, im, inverse) {
    fftInit();
    var i, j, k;
    for (i = 0; i < N; i++) {
      j = revTable[i];
      if (j > i) {
        var tr = re[i]; re[i] = re[j]; re[j] = tr;
        var ti = im[i]; im[i] = im[j]; im[j] = ti;
      }
    }
    for (var size = 2; size <= N; size <<= 1) {
      var half = size >> 1;
      var step = N / size;
      for (i = 0; i < N; i += size) {
        for (j = i, k = 0; j < i + half; j++, k += step) {
          var wr = twRe[k];
          var wi = inverse ? -twIm[k] : twIm[k];
          var xr = re[j + half] * wr - im[j + half] * wi;
          var xi = re[j + half] * wi + im[j + half] * wr;
          re[j + half] = re[j] - xr;
          im[j + half] = im[j] - xi;
          re[j] += xr;
          im[j] += xi;
        }
      }
    }
    if (inverse) {
      for (i = 0; i < N; i++) { re[i] /= N; im[i] /= N; }
    }
  }

  /* ---- small-window median (insertion sort into scratch) --------------- */
  function median(arr, scratch, from, to) {
    var n = 0;
    for (var i = from; i < to; i++) {
      var v = arr[i];
      var j = n - 1;
      while (j >= 0 && scratch[j] > v) { scratch[j + 1] = scratch[j]; j--; }
      scratch[j + 1] = v;
      n++;
    }
    return scratch[(n - 1) >> 1];
  }

  function hann() {
    var w = new Float64Array(N);
    for (var i = 0; i < N; i++) {
      w[i] = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / N);
    }
    return w;
  }

  /* Vocal-band weight per bin: quiet under 110 Hz, full 200 Hz - 8 kHz,
     easing off above so cymbal air stays with the instruments lane. */
  function vocalBand(sampleRate) {
    var w = new Float64Array(BINS);
    for (var b = 0; b < BINS; b++) {
      var hz = b * sampleRate / N;
      var lo = hz <= 110 ? 0 : hz >= 200 ? 1 : (hz - 110) / 90;
      var hi = hz <= 8000 ? 1 : hz >= 13000 ? 0.25 : 1 - 0.75 * (hz - 8000) / 5000;
      w[b] = lo * hi;
    }
    return w;
  }

  /* Bass split: full below 100 Hz, gone above 220 Hz. */
  function bassBand(sampleRate) {
    var w = new Float64Array(BINS);
    for (var b = 0; b < BINS; b++) {
      var hz = b * sampleRate / N;
      w[b] = hz <= 100 ? 1 : hz >= 220 ? 0 : 1 - (hz - 100) / 120;
    }
    return w;
  }

  /* ---- the split -------------------------------------------------------
     channels: [Float32Array] length 1 or 2. onProgress(0..1) optional.
     Returns {vocals, drums, bass, other}: same channel count/length.
     Async: yields to the event loop between work slabs so the tab
     stays responsive; call from a click handler with a progress note. */
  function split(channels, sampleRate, onProgress) {
    var stereo = channels.length > 1;
    var L = channels[0];
    var R = stereo ? channels[1] : channels[0];
    var len = L.length;
    var nFrames = Math.max(1, Math.ceil((len + N) / HOP));
    var win = hann();
    var vb = vocalBand(sampleRate);
    var bb = bassBand(sampleRate);

    /* pass 1 storage: mixture magnitude, one row per frame */
    var mag = new Float32Array(nFrames * BINS);
    var re = new Float64Array(N), im = new Float64Array(N);
    var re2 = new Float64Array(N), im2 = new Float64Array(N);

    var names = ["vocals", "drums", "bass", "other"];
    var out = {};
    names.forEach(function (nm) {
      out[nm] = [new Float32Array(len)];
      if (stereo) { out[nm].push(new Float32Array(len)); }
    });
    /* COLA normaliser: sum of squared hann at 75% overlap = 1.5 */
    var cola = 1.5;

    function readFrame(src, offset) {
      for (var i = 0; i < N; i++) {
        var idx = offset + i;
        re[i] = (idx >= 0 && idx < len ? src[idx] : 0) * win[i];
        im[i] = 0;
      }
    }

    var progress = onProgress || function () {};
    var frame = 0;

    return new Promise(function (resolve) {
      /* ---- pass 1: magnitudes ---- */
      function pass1() {
        var until = Math.min(nFrames, frame + 64);
        for (; frame < until; frame++) {
          var off = frame * HOP - N + HOP;
          readFrame(L, off);
          fft(re, im, false);
          var row = frame * BINS;
          for (var b = 0; b < BINS; b++) {
            mag[row + b] = Math.hypot(re[b], im[b]);
          }
          if (stereo) {
            readFrame(R, off);
            fft(re, im, false);
            for (b = 0; b < BINS; b++) {
              mag[row + b] += Math.hypot(re[b], im[b]);
            }
          }
        }
        progress(0.25 * frame / nFrames);
        if (frame < nFrames) { yieldNow(pass1); }
        else { frame = 0; yieldNow(masks); }
      }

      /* ---- masks: median-filtered harmonic/percussive ---- */
      var pMask = new Float32Array(nFrames * BINS);
      var scratch = new Float64Array(Math.max(MED_T, MED_F) + 2);
      var col = new Float64Array(nFrames + MED_T);
      var bin = 0;

      function masks() {
        /* harmonic: median along TIME for each bin; percussive: median
           along FREQ for each frame. Do harmonic per-bin first into
           pMask as temp, then finish per-frame. */
        var untilBin = Math.min(BINS, bin + 96);
        var htime = MED_T >> 1;
        for (; bin < untilBin; bin++) {
          for (var f = 0; f < nFrames; f++) { col[f] = mag[f * BINS + bin]; }
          for (f = 0; f < nFrames; f++) {
            var a = Math.max(0, f - htime);
            var z = Math.min(nFrames, f + htime + 1);
            pMask[f * BINS + bin] = median(col, scratch, a, z); // harmonic-enhanced
          }
        }
        progress(0.25 + 0.25 * bin / BINS);
        if (bin < BINS) { yieldNow(masks); return; }
        frame = 0;
        yieldNow(masks2);
      }

      function masks2() {
        var until = Math.min(nFrames, frame + 48);
        var hfreq = MED_F >> 1;
        for (; frame < until; frame++) {
          var row = frame * BINS;
          for (var b = 0; b < BINS; b++) {
            var a = Math.max(0, b - hfreq);
            var z = Math.min(BINS, b + hfreq + 1);
            var perc = median(mag, scratch, row + a, row + z); // percussive-enhanced
            var harm = pMask[row + b];
            var p2 = perc * perc;
            var h2 = harm * harm;
            pMask[row + b] = p2 / (p2 + h2 + 1e-12);           // final P mask
          }
        }
        progress(0.5 + 0.2 * frame / nFrames);
        if (frame < nFrames) { yieldNow(masks2); }
        else { frame = 0; yieldNow(pass2); }
      }

      /* ---- pass 2: apply the partition, overlap-add ---- */
      var chL = { re: re, im: im };
      var chR = { re: re2, im: im2 };

      function synthFrame(specRe, specIm, dest, off) {
        fft(specRe, specIm, true);
        var a = Math.max(0, -off);
        var z = Math.min(N, len - off);
        for (var i = a; i < z; i++) {
          dest[off + i] += specRe[i] * win[i] / cola;
        }
      }

      var sRe = new Float64Array(N), sIm = new Float64Array(N);

      function pass2() {
        var until = Math.min(nFrames, frame + 24);
        for (; frame < until; frame++) {
          var off = frame * HOP - N + HOP;
          var row = frame * BINS;
          readFrame(L, off); var lRe = re.slice(), lIm = im.slice();
          fft(lRe, lIm, false);
          var rRe = lRe, rIm = lIm;
          if (stereo) {
            readFrame(R, off);
            rRe = re.slice(); rIm = im.slice();
            fft(rRe, rIm, false);
          }
          for (var s = 0; s < 4; s++) {
            var nm = names[s];
            for (var ch = 0; ch < (stereo ? 2 : 1); ch++) {
              var srcRe = ch ? rRe : lRe;
              var srcIm = ch ? rIm : lIm;
              for (var b = 0; b < BINS; b++) {
                var P = pMask[row + b];
                var m;
                if (s === 1) { m = P; }
                else {
                  var H = 1 - P;
                  if (s === 2) { m = H * bb[b]; }
                  else {
                    /* centredness x vocal band */
                    var la = Math.hypot(lRe[b], lIm[b]);
                    var ra = Math.hypot(rRe[b], rIm[b]);
                    var bal = 1 - Math.abs(la - ra) / (la + ra + 1e-12);
                    var coh = (lRe[b] * rRe[b] + lIm[b] * rIm[b]) /
                              (la * ra + 1e-12);
                    var W = bal * Math.max(0, Math.min(1, coh)) * vb[b];
                    var base = H * (1 - bb[b]);
                    m = s === 0 ? base * W : base * (1 - W);
                  }
                }
                /* mirror bin for the conjugate half */
                var mb = b === 0 || b === BINS - 1 ? [b] : [b, N - b];
                for (var q = 0; q < mb.length; q++) {
                  sRe[mb[q]] = srcRe[mb[q]] * m;
                  sIm[mb[q]] = srcIm[mb[q]] * m;
                }
              }
              synthFrame(sRe, sIm, out[nm][ch], off);
            }
          }
        }
        progress(0.7 + 0.3 * frame / nFrames);
        if (frame < nFrames) { yieldNow(pass2); }
        else { progress(1); resolve(out); }
      }

      pass1();
    });
  }

  var api = { split: split, _fft: fft, _N: N };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
  global.SBRoughSplit = api;
})(typeof window !== "undefined" ? window : globalThis);
