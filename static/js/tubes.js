/* Street Banker · SB-14 VLV-6 — six colouring stages, each a real process.
 *
 * The point of six tubes is six DIFFERENT things, not one algorithm wearing
 * six labels. Each stage below changes the signal in a way you can measure,
 * and the faceplate only claims what these functions actually do:
 *
 *   V1 TRIODE    A squaring term, which for a sine lands entirely on DC and
 *                the 2nd harmonic - the EVEN harmonics people mean by
 *                "warmth" - and makes no 3rd at all. The DC it creates is
 *                blocked at 15 Hz in the graph.
 *
 *   V2 PENTODE   Symmetric shaping. An odd-symmetric curve can only produce
 *                ODD harmonics (3rd, 5th) - edge and push rather than
 *                warmth. Deliberately the opposite symmetry to V1.
 *
 *   V3 TAPE      Soft-knee saturating exponential, plus the two filter
 *                moves that actually make tape sound like tape: high
 *                frequency loss and a low "head bump".
 *
 *   V4 FLUTTER   Wow and flutter: two LFOs (slow ~0.7 Hz, fast ~6.3 Hz)
 *                modulating a short delay line, which is genuine pitch
 *                movement, not a chorus pretending to be one.
 *
 *   V5 IRON      The gentlest of the four curves, applied ONLY to the low
 *                band, because that is where a transformer core saturates.
 *
 *   V6 VARI-MU   Slow, program-dependent gain reduction - the tube
 *                compressor behaviour, distinct from the rack's existing
 *                fast compressor.
 *
 * Two decisions do most of the work in making this read as warmth rather
 * than as damage:
 *
 *   Slope normalisation. Every curve is divided by its slope at zero, not
 *   by its peak. Peak normalisation turns a saturator into a large
 *   low-level BOOST - at one earlier setting, +12 dB - so the stage was
 *   mostly just louder, and louder wins a careless comparison for the
 *   wrong reason. Normalised by slope, a stage is unity where the music
 *   actually sits and compressive only as it approaches full scale.
 *
 *   Level matching. What compression the curve does apply is measured and
 *   handed back by compensation(), so switching a stage on changes the
 *   CHARACTER at the same loudness. That is the only way to hear whether
 *   you like it.
 *
 * The glow is a meter, not decoration: each tube's brightness comes from
 * how hard that stage is really being driven right now (and for V6, from
 * its actual gain reduction). A tube that is doing nothing stays dark.
 *
 * Curves are pure array maths - no DOM, no Web Audio - so every claim above
 * is checked in Node with an FFT rather than asserted.
 */
(function (root) {
  "use strict";

  var N = 2048;   // waveshaper table size; plenty for audio-rate shaping

  function table(fn) {
    var c = new Float32Array(N);
    for (var i = 0; i < N; i++) {
      var x = (i / (N - 1)) * 2 - 1;
      var y = fn(x);
      c[i] = y > 1 ? 1 : (y < -1 ? -1 : y);
    }
    return c;
  }

  /* V1. A squaring term is what actually generates even harmonics: for a
     sine input, x^2 lands entirely on DC and the 2nd harmonic and produces
     no 3rd at all.

     There is deliberately no tanh here. The first version softened the peak
     with one, and that tanh generated more 3rd harmonic than the squaring
     term generated 2nd - so the stage labelled "warmth" was actually making
     edge. A bare quadratic is already bounded on [-1, 1], so nothing needs
     clipping, and the 3rd harmonic is exactly zero.

     a is capped well under 0.5, where the slope 1 + 2*a*x would reach zero
     and the curve could fold back on itself. */
  function triodeCurve(amount) {
    if (amount <= 0) { return table(function (x) { return x; }); }
    var a = amount * 0.16;
    return table(function (x) { return (x + a * x * x) / (1 + a); });
  }

  /* V2. Odd-symmetric by construction: f(-x) === -f(x), which is exactly
     the condition for producing only odd harmonics. Note /k rather than
     /tanh(k) - see the slope-normalisation note in the file header. k rides
     amount with no floor under it, so the curve slides continuously out of
     the identity instead of jumping to a fixed drive when switched on. */
  function pentodeCurve(amount) {
    if (amount <= 0) { return table(function (x) { return x; }); }
    var k = amount * 1.6;
    return table(function (x) { return Math.tanh(k * x) / k; });
  }

  /* V3. Gentle in the middle, firmly compressed approaching full scale.
     Odd-symmetric, so it colours without the even-harmonic warmth V1 adds -
     the tape character comes as much from the filters around it. */
  function tapeCurve(amount) {
    if (amount <= 0) { return table(function (x) { return x; }); }
    var k = amount * 0.8;
    return table(function (x) {
      var s = x < 0 ? -1 : 1;
      return s * (1 - Math.exp(-k * Math.abs(x))) / k;
    });
  }

  /* V5. The gentlest of the four, and applied to the low band only, because
     a transformer rounds the bottom rather than squashing it. */
  function ironCurve(amount) {
    if (amount <= 0) { return table(function (x) { return x; }); }
    var k = amount * 1.0;
    return table(function (x) { return Math.tanh(k * x) / k; });
  }

  /* Read a curve the way Web Audio does, so a gain measured here is the
     gain the audio graph will really apply. */
  function sampleCurve(curve, x) {
    var n = curve.length;
    var t = ((x < -1 ? -1 : (x > 1 ? 1 : x)) + 1) / 2 * (n - 1);
    var i = Math.floor(t), f = t - i;
    var a = curve[i], b = i + 1 < n ? curve[i + 1] : a;
    return a + (b - a) * f;
  }

  /* How much level a curve loses, measured rather than guessed, on a
     deterministic Gaussian signal at a realistic mix level. A sine would
     overstate it: a sine spends most of its time near its peaks, which is
     exactly where these curves compress hardest. */
  function curveGain(curve, rms) {
    var n = 8192, seed = 22461, inSum = 0, outSum = 0, i;
    for (i = 0; i < n; i++) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      var u1 = ((seed >>> 8) % 100000) / 100000 + 1e-7;
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      var u2 = ((seed >>> 8) % 100000) / 100000;
      var x = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2) * rms;
      if (x > 1) { x = 1; } else if (x < -1) { x = -1; }
      var y = sampleCurve(curve, x);
      inSum += x * x;
      outSum += y * y;
    }
    return outSum > 1e-12 ? Math.sqrt(inSum / outSum) : 1;
  }

  // -16 dBFS: about where a mastered record actually sits.
  var REF_RMS = 0.158;

  var CURVES = {triode: triodeCurve, pentode: pentodeCurve,
                tape: tapeCurve, iron: ironCurve};

  function compensation(key, amount) {
    var fn = CURVES[key];
    if (!fn || amount <= 0) { return 1; }
    return curveGain(fn(amount), REF_RMS);
  }

  /* A little top-end softening is the other half of warmth - harmonics on
     their own read as grit. Kept small enough to feel rather than hear. */
  function tiltDb(key, amount) {
    if (amount <= 0) { return 0; }
    if (key === "triode") { return -1.4 * amount; }
    if (key === "tape") { return -4 * amount; }
    return 0;
  }

  /* V4's two LFOs. Wow is the slow drift, flutter the fast wobble; real
     machines have both, at very different rates and depths.

     The depths are deliberately tiny. A professional machine wanders about
     0.1% and a consumer cassette about 0.4%, which is roughly 2 to 7 cents.
     The first version swung 52 cents - nearly a quarter-tone - and that is
     seasickness rather than tape. */
  function flutterParams(amount) {
    return {
      base: 0.004,                         // 4 ms nominal delay
      wowHz: 0.7,
      wowDepth: 0.00021 * amount,          // seconds of swing
      flutterHz: 6.3,
      flutterDepth: 0.000045 * amount,
    };
  }

  /* V6's envelope. Slow attack and long release is what makes a vari-mu
     grab the shape of a phrase instead of individual transients.

     No makeup figure here on purpose. A compressor's output level is
     program-dependent, and on top of that Chrome's DynamicsCompressorNode
     applies an INTERNAL makeup gain derived from threshold, knee and ratio
     which is not specified anywhere that can be relied on - measured, it
     handed back about 2 dB MORE than it took away, which is exactly the
     "it just got louder" problem this panel exists to avoid. So the trim is
     measured at runtime against the browser actually running, over in
     rackdsp.js, rather than derived from a formula here. What this module
     owes is the envelope, not the gain. */
  function variMuParams(amount) {
    return {
      threshold: -8 - amount * 16,
      ratio: 1.5 + amount * 2.5,
      attack: 0.045,
      release: 0.55,
      knee: 12,
    };
  }

  /* Glow: how hard this stage is being driven, right now. RMS is mapped
     through a curve so quiet-but-present reads as a warm filament rather
     than off, and the amount knob scales it because a stage turned down is
     not working hard however loud the input. */
  function glow(rms, amount) {
    if (!(rms > 0) || amount <= 0) { return 0; }
    var db = 20 * Math.log(rms) / Math.LN10;      // -inf .. 0
    var lit = (db + 42) / 42;                     // -42 dBFS -> 0, 0 dBFS -> 1
    lit = lit < 0 ? 0 : (lit > 1 ? 1 : lit);
    return Math.pow(lit, 0.7) * (0.35 + 0.65 * amount);
  }

  /* Gain reduction reads as glow directly: 12 dB of squeeze is a fully lit
     tube. Kept separate from the level mapping so neither has to pretend to
     be the other. */
  function glowFromReduction(reductionDb, amount) {
    if (amount <= 0) { return 0; }
    var g = Math.min(1, Math.abs(reductionDb || 0) / 12);
    return Math.pow(g, 0.7) * (0.4 + 0.6 * amount);
  }

  var STAGES = [
    {key: "triode", tube: "V1", name: "Triode",
     blurb: "Even harmonics · warmth", curve: triodeCurve, dc: true},
    {key: "pentode", tube: "V2", name: "Pentode",
     blurb: "Odd harmonics · push", curve: pentodeCurve},
    {key: "tape", tube: "V3", name: "Tape",
     blurb: "Soft knee · HF loss · head bump", curve: tapeCurve},
    {key: "flutter", tube: "V4", name: "Flutter",
     blurb: "Wow &amp; flutter · real pitch drift", mod: true},
    {key: "iron", tube: "V5", name: "Iron",
     blurb: "Transformer · lows only", curve: ironCurve, lowOnly: true},
    {key: "varimu", tube: "V6", name: "Vari-Mu",
     blurb: "Slow tube compression", comp: true},
  ];

  var api = {
    STAGES: STAGES,
    triodeCurve: triodeCurve,
    pentodeCurve: pentodeCurve,
    tapeCurve: tapeCurve,
    ironCurve: ironCurve,
    flutterParams: flutterParams,
    variMuParams: variMuParams,
    compensation: compensation,
    tiltDb: tiltDb,
    REF_RMS: REF_RMS,
    glow: glow,
    glowFromReduction: glowFromReduction,
    _N: N,
    _curveGain: curveGain,
    _sampleCurve: sampleCurve,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.SBTubes = api;
})(typeof self !== "undefined" ? self : this);
