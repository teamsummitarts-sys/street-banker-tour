/* The Rack — SB-1200. All DSP runs here in the browser via Web Audio;
   nothing is uploaded. Knobs, meters, and curves read/write one state
   object; buildChain() is shared by live playback and offline export. */
(function () {
  "use strict";
  var EQ_BANDS = [
    {f: 40, type: "lowshelf", label: "40"},
    {f: 80, type: "peaking", label: "80"},
    {f: 120, type: "peaking", label: "120"},
    {f: 250, type: "peaking", label: "250"},
    {f: 400, type: "peaking", label: "400"},
    {f: 630, type: "peaking", label: "630"},
    {f: 1000, type: "peaking", label: "1k"},
    {f: 1600, type: "peaking", label: "1.6k"},
    {f: 2500, type: "peaking", label: "2.5k"},
    {f: 4000, type: "peaking", label: "4k"},
    {f: 8000, type: "peaking", label: "8k"},
    {f: 14000, type: "highshelf", label: "14k"}
  ];
  var LANES = [
    {label: "Sub / 808",       lo: 30,   hi: 70,    color: "#c94f4f"},
    {label: "Kick",            lo: 40,   hi: 100,   color: "#e05252"},
    {label: "Bass",            lo: 50,   hi: 250,   color: "#e07a3c"},
    {label: "Synths",          lo: 60,   hi: 2500,  color: "#4fc9b0"},
    {label: "Toms",            lo: 80,   hi: 300,   color: "#e0a03c"},
    {label: "Piano / Keys",    lo: 90,   hi: 1800,  color: "#3cc96a"},
    {label: "Guitars",         lo: 100,  hi: 1200,  color: "#8fbf5f"},
    {label: "Vocals",          lo: 110,  hi: 1300,  color: "#5f9fd6"},
    {label: "Snare",           lo: 150,  hi: 400,   color: "#e0c452"},
    {label: "Strings / Horns", lo: 150,  hi: 2000,  color: "#5fb8d6"},
    {label: "Presence",        lo: 2000, hi: 5000,  color: "#9d7fd6"},
    {label: "Hi-Hats",         lo: 3000, hi: 10000, color: "#c97fd6"},
    {label: "Air / Cymbals",   lo: 6000, hi: 16000, color: "#d67fb8"}
  ];
  var CABS = {
    direct:    null,
    combo112:  {hp: 90, ls: [120, 0],  p1: [800, 2],    p2: [2200, 1.5], lp1: 5000, lp2: 5200, lp3: 5600},
    open212:   {hp: 75, ls: [120, 0],  p1: [450, -1.5], p2: [2800, 2],   lp1: 5500, lp2: 6000, lp3: 6400},
    closed412: {hp: 70, ls: [120, 2],  p1: [700, -2],   p2: [2500, 2.5], lp1: 3900, lp2: 4050, lp3: 4200},
    bass810:   {hp: 40, ls: [100, 3],  p1: [800, -1],   p2: [1600, 1],   lp1: 3400, lp2: 3600, lp3: 3900}
  };
  var MICS = {
    dynamic:   {presence: [4500, 3],  top: [10000, -1], body: [150, 0]},
    ribbon:    {presence: [3000, -1], top: [5000, -4],  body: [150, 1.5]},
    condenser: {presence: [3000, 0],  top: [10000, 1],  body: [150, 0]}
  };
  var DEF_CAB = {cab: "direct", mic: "dynamic", axis: "on", dist: 0, on: true};
  var PRESETS = {
    flat:   {eq: [0,0,0,0,0,0,0,0,0,0,0,0], q: 1, tube: {drive: 1, bias: 0, mix: 0}, comp: {thr: 0, ratio: 1, att: 0.01, rel: 0.25, makeup: 0}, out: 0, cab: {cab: "direct", mic: "dynamic", axis: "on", dist: 0, on: true}},
    warm:   {eq: [2,1,0,-1.5,0,0,0,0,0,0.5,1,0.5], q: 1, tube: {drive: 3, bias: 0.25, mix: 0.35}, comp: {thr: -18, ratio: 2, att: 0.03, rel: 0.3, makeup: 1}, out: 0, cab: {cab: "direct", mic: "dynamic", axis: "on", dist: 0, on: true}},
    vocal:  {eq: [0,0,0,-2,-1,-0.5,0,1,2.5,2,1.5,1], q: 1.2, tube: {drive: 2, bias: 0.15, mix: 0.2}, comp: {thr: -22, ratio: 3, att: 0.01, rel: 0.2, makeup: 2}, out: 0, cab: {cab: "direct", mic: "dynamic", axis: "on", dist: 0, on: true}},
    bass:   {eq: [2,2,-1,-2,-1,0,0,0,0,0,0,0], q: 1.4, tube: {drive: 2.5, bias: 0.2, mix: 0.25}, comp: {thr: -26, ratio: 4, att: 0.005, rel: 0.15, makeup: 2}, out: 0, cab: {cab: "direct", mic: "dynamic", axis: "on", dist: 0, on: true}},
    guitar: {eq: [0,0,0,0,0,0,0,0,0,0,0,0], q: 1, tube: {drive: 4.5, bias: 0.3, mix: 0.6}, comp: {thr: -20, ratio: 2.5, att: 0.02, rel: 0.2, makeup: 2}, out: 0, cab: {cab: "closed412", mic: "dynamic", axis: "on", dist: 0.15, on: true}}
  };
  /* SB-14 defaults: every valve off. A colour section that arrives already
     colouring your audio would be lying about what you are hearing.
     Declared up here because ensureFx() reads it while building state - a
     var further down hoists as undefined, not as this array. */
  var VALVE_KEYS = ["triode", "pentode", "tape", "flutter", "iron", "varimu"];

  function defaultValves() {
    var v = {};
    VALVE_KEYS.forEach(function (k) { v[k] = {on: false, amt: 0.45}; });
    return v;
  }

  /* ---------- the patch bay ----------
     The rack's units are bolted in place; the CABLES move. state.patch is
     the signal order of the seven patchable blocks between the master-bus
     matrix and the output trim. Anything invalid — an old save, a hand
     edit, a missing key — falls back to the factory order, silently and
     completely: half a patch would be a guess. */
  var PATCH_KEYS = ["eq", "sub", "tube", "vlv", "cab", "comp", "fx"];
  var PATCH_LABELS = {eq: "EQ-12", sub: "SUB-1", tube: "TS-1", vlv: "VLV-6",
                      cab: "CAB-3", comp: "DYN-1", fx: "FX"};
  function patchOrder() {
    var p = state.patch;
    if (!p || p.length !== PATCH_KEYS.length) return PATCH_KEYS.slice();
    var seen = {};
    for (var i = 0; i < p.length; i++) {
      if (PATCH_KEYS.indexOf(p[i]) < 0 || seen[p[i]]) return PATCH_KEYS.slice();
      seen[p[i]] = true;
    }
    return p;
  }

  var saved = window.__savedRack || null;
  var state = (saved && saved.eq && saved.eq.length === EQ_BANDS.length)
    ? saved : JSON.parse(JSON.stringify(PRESETS.flat));
  if (!state.cab) state.cab = JSON.parse(JSON.stringify(DEF_CAB));
  function ensureFx(s) {
    if (!s.dly) s.dly = {time: 0.3, fb: 0.3, tone: 5000, mix: 0};
    if (!s.rev) s.rev = {size: 1.6, damp: 5000, pre: 0.02, mix: 0};
    if (!s.sub) s.sub = {depth: 0, growl: 0, shake: 0};
    // EQ-12 mid/side and per-band bypass arrived after every preset and
    // most saved racks: default to the behaviour they were saved with.
    if (s.eqMode !== "mid" && s.eqMode !== "side") s.eqMode = "stereo";
    if (s.comp && typeof s.comp.key !== "string") s.comp.key = "";   // "" = the internal detector
    if (!s.eqOff || s.eqOff.length !== EQ_BANDS.length) s.eqOff = EQ_BANDS.map(function () { return false; });
    if (!s.patch) s.patch = PATCH_KEYS.slice();   // patchOrder() validates the rest
    // Racks saved before SB-14 existed have no valves; give them silent
    // ones rather than colouring a mix the artist already signed off.
    if (!s.valves) { s.valves = defaultValves(); }
    VALVE_KEYS.forEach(function (k) {
      if (!s.valves[k]) { s.valves[k] = {on: false, amt: 0.45}; }
    });
  }
  ensureFx(state);
  state.bypass = false;
  // Per-module power. Off neutralizes that module's processing in BOTH the
  // live chain and the offline export while the knobs keep their positions.
  if (!state.mods) state.mods = {};
  function modOn(m) {
    if (m === "cab") return !!state.cab.on;
    return state.mods[m] !== false;
  }


  var ctx = null, buffer = null, playing = null;
  var live = null;
  var loadedName = "";
  var loadedFile = null;   // the original bytes, for Studio Split uploads
  var refBuffer = null, refMode = false, refSpec = null;

  // ---------- chain ----------
  function tubeCurve(drive, bias) {
    var n = 2048, c = new Float32Array(n);
    var norm = Math.tanh(drive);
    for (var i = 0; i < n; i++) {
      var x = (i / (n - 1)) * 2 - 1;
      var d = x >= 0 ? drive * (1 + bias) : drive * (1 - bias * 0.6);
      c[i] = Math.tanh(d * x) / norm;
    }
    return c;
  }

  function mulberry32(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  function roomIR(ac) {
    var rate = ac.sampleRate, len = Math.floor(rate * 0.18);
    var buf = ac.createBuffer(2, len, rate);
    for (var ch = 0; ch < 2; ch++) {
      var d = buf.getChannelData(ch), rnd = mulberry32(1337 + ch);
      d[0] = 1;
      for (var r = 0; r < 14; r++) {
        var at = Math.floor((0.008 + rnd() * 0.05) * rate);
        if (at < len) d[at] += (rnd() * 2 - 1) * 0.4 * Math.pow(0.75, r);
      }
      var lp = 0;
      for (var i = 1; i < len; i++) {
        var decay = Math.pow(1 - i / len, 2.2);
        lp = lp * 0.82 + (rnd() * 2 - 1) * 0.18;
        d[i] += lp * 0.25 * decay;
      }
    }
    return buf;
  }

  function bq(ac, type, f, gain, q) {
    var n = ac.createBiquadFilter();
    n.type = type; n.frequency.value = f;
    if (gain !== undefined) n.gain.value = gain;
    if (q !== undefined) n.Q.value = q;
    return n;
  }

  function buildCabMic(ac) {
    var m = {
      moduleIn: ac.createGain(), moduleOut: ac.createGain(),
      thru: ac.createGain(), procIn: ac.createGain(),
      hp: bq(ac, "highpass", 10, undefined, 0.7),
      ls: bq(ac, "lowshelf", 120, 0),
      p1: bq(ac, "peaking", 800, 0, 1),
      p2: bq(ac, "peaking", 2500, 0, 1),
      lp1: bq(ac, "lowpass", 20000, undefined, 0.7),
      lp2: bq(ac, "lowpass", 20000, undefined, 0.7),
      lp3: bq(ac, "lowpass", 20000, undefined, 0.7),
      micPresence: bq(ac, "peaking", 4500, 0, 1.2),
      micTop: bq(ac, "highshelf", 10000, 0),
      micBody: bq(ac, "lowshelf", 150, 0),
      axisCut: bq(ac, "highshelf", 4000, 0),
      proxLS: bq(ac, "lowshelf", 120, 0),
      distHS: bq(ac, "highshelf", 8000, 0),
      conv: ac.createConvolver(),
      convWet: ac.createGain(), convDry: ac.createGain()
    };
    m.conv.buffer = roomIR(ac);
    m.convWet.gain.value = 0;
    var chain = [m.hp, m.ls, m.p1, m.p2, m.lp1, m.lp2, m.lp3, m.micPresence,
                 m.micTop, m.micBody, m.axisCut, m.proxLS, m.distHS];
    var node = m.procIn;
    chain.forEach(function (f) { node.connect(f); node = f; });
    node.connect(m.convDry); m.convDry.connect(m.moduleOut);
    node.connect(m.conv); m.conv.connect(m.convWet); m.convWet.connect(m.moduleOut);
    m.moduleIn.connect(m.thru); m.thru.connect(m.moduleOut);
    m.moduleIn.connect(m.procIn);
    m.cabFilters = chain;
    return m;
  }

  function voiceCabMic(m) {
    var c = state.cab;
    var active = c.on && c.cab !== "direct" && CABS[c.cab];
    m.thru.gain.value = active ? 0 : 1;
    m.procIn.gain.value = active ? 1 : 0;
    if (!active) { m.convWet.gain.value = 0; m.convDry.gain.value = 1; return; }
    var cab = CABS[c.cab], mic = MICS[c.mic] || MICS.dynamic;
    m.hp.frequency.value = cab.hp;
    m.ls.frequency.value = cab.ls[0]; m.ls.gain.value = cab.ls[1];
    m.p1.frequency.value = cab.p1[0]; m.p1.gain.value = cab.p1[1];
    m.p2.frequency.value = cab.p2[0]; m.p2.gain.value = cab.p2[1];
    m.lp1.frequency.value = cab.lp1; m.lp2.frequency.value = cab.lp2;
    m.lp3.frequency.value = cab.lp3;
    m.micPresence.frequency.value = mic.presence[0]; m.micPresence.gain.value = mic.presence[1];
    m.micTop.frequency.value = mic.top[0]; m.micTop.gain.value = mic.top[1];
    m.micBody.frequency.value = mic.body[0]; m.micBody.gain.value = mic.body[1];
    m.axisCut.gain.value = c.axis === "off" ? -3.5 : 0;
    m.proxLS.gain.value = (1 - c.dist) * 3;
    m.distHS.gain.value = -1.5 * c.dist;
    m.convWet.gain.value = 0.35 * c.dist;
    m.convDry.gain.value = 1 - 0.2 * c.dist;
  }

  function reverbIR(ac, size) {
    // Seeded decaying noise: the same space every render, live or offline.
    var rate = ac.sampleRate, len = Math.max(1, Math.floor(rate * size));
    var buf = ac.createBuffer(2, len, rate);
    for (var ch = 0; ch < 2; ch++) {
      var d = buf.getChannelData(ch), rnd = mulberry32(4242 + ch);
      for (var i = 0; i < len; i++) {
        d[i] = (rnd() * 2 - 1) * Math.pow(1 - i / len, 2.6);
      }
    }
    return buf;
  }

  function buildSub(ac) {
    // Foundation: protective HP + deep shelf + 42Hz room resonance in the
    // main path; a parallel band generates harmonics OF the sub region so
    // small speakers perceive lows they can't reproduce (psychoacoustics).
    var m = {inNode: ac.createGain(), outNode: ac.createGain(),
             protect: bq(ac, "highpass", 24, undefined, 0.7),
             depth: bq(ac, "lowshelf", 45, 0),
             shake: bq(ac, "peaking", 42, 0, 2.2),
             band: bq(ac, "lowpass", 120, undefined, 0.7),
             drive: ac.createWaveShaper(),
             growlHP: bq(ac, "highpass", 90, undefined, 0.7),
             growl: ac.createGain()};
    var n = 1024, c = new Float32Array(n);
    for (var i = 0; i < n; i++) {
      var x = (i / (n - 1)) * 2 - 1;
      // Asymmetric: odd AND even harmonics of the sub band, tube-style.
      c[i] = Math.tanh(3 * x + 1.1 * x * x) - Math.tanh(1.1 * (i === 0 ? 1 : 1)) * 0;
    }
    m.drive.curve = c; m.drive.oversample = "2x";
    m.growl.gain.value = 0;
    m.inNode.connect(m.protect); m.protect.connect(m.depth);
    m.depth.connect(m.shake); m.shake.connect(m.outNode);
    m.inNode.connect(m.band); m.band.connect(m.drive);
    m.drive.connect(m.growlHP); m.growlHP.connect(m.growl);
    m.growl.connect(m.outNode);
    return m;
  }

  function voiceSub(m) {
    var on = modOn("sub") ? 1 : 0;
    m.depth.gain.value = state.sub.depth * on;
    m.shake.gain.value = state.sub.shake * 8 * on;
    m.growl.gain.value = state.sub.growl * 0.7 * on;
  }

  /* SB-14 Valve Bank. Six stages in series, each individually neutral when
     off: the shapers fall back to the identity curve, the filters to 0 dB,
     the modulator to zero depth and the compressor to 1:1. Nothing is
     rewired on a toggle, so a switch can never click the audio - and
     because tubes.js proves amount 0 is exactly the identity, neutral
     really is transparent rather than nearly so.

     An AnalyserNode sits after each stage purely so the glow can report
     what that stage is actually doing. */
  function buildValves(ac) {
    var T = window.SBTubes;
    var m = {inNode: ac.createGain(), outNode: ac.createGain(), taps: {}};
    if (!T) {                       // module missing: pass audio through
      m.inNode.connect(m.outNode);
      return m;
    }

    function tap(key, from) {
      var an = ac.createAnalyser();
      an.fftSize = 256;
      an.smoothingTimeConstant = 0.5;
      from.connect(an);
      m.taps[key] = {node: an, buf: new Uint8Array(an.fftSize)};
      return from;
    }

    /* Every shaping stage gets a trim after it. The curves are normalised
       by their slope at zero, so they only lose level as the peaks
       compress - the trim puts that back, which is what lets you A/B a
       stage on character instead of loudness. */
    // V1 triode: DC blocker (its asymmetry makes DC), gentle top-end
    // softening, then the level match.
    m.triode = ac.createWaveShaper();
    m.triode.oversample = "4x";
    m.triodeDC = bq(ac, "highpass", 15, undefined, 0.7);
    m.triodeTilt = bq(ac, "highshelf", 9000, 0);
    m.triodeGain = ac.createGain();
    // V2 pentode.
    m.pentode = ac.createWaveShaper();
    m.pentode.oversample = "4x";
    m.pentodeGain = ac.createGain();
    // V3 tape: curve, HF loss, head bump.
    m.tape = ac.createWaveShaper();
    m.tape.oversample = "4x";
    m.tapeHF = bq(ac, "highshelf", 8000, 0);
    m.tapeBump = bq(ac, "lowshelf", 60, 0);
    m.tapeGain = ac.createGain();
    // V4 flutter: a short delay with two LFOs on its delayTime.
    m.flutterIn = ac.createGain();
    m.flutter = ac.createDelay(0.05);
    m.wow = ac.createOscillator();
    m.wowGain = ac.createGain();
    m.flut = ac.createOscillator();
    m.flutGain = ac.createGain();
    m.wow.type = "sine"; m.flut.type = "triangle";
    m.wowGain.gain.value = 0; m.flutGain.gain.value = 0;
    m.wow.connect(m.wowGain); m.wowGain.connect(m.flutter.delayTime);
    m.flut.connect(m.flutGain); m.flutGain.connect(m.flutter.delayTime);
    try { m.wow.start(); m.flut.start(); } catch (e) { /* already running */ }
    // V5 iron: saturate the low band only, then recombine.
    m.ironIn = ac.createGain();
    m.ironLow = bq(ac, "lowpass", 200, undefined, 0.7);
    m.ironHigh = bq(ac, "highpass", 200, undefined, 0.7);
    m.ironShape = ac.createWaveShaper();
    m.ironShape.oversample = "2x";
    // Trim sits on the low band only: that is the only part being shaped,
    // so compensating the summed signal would lift the untouched highs too.
    m.ironGain = ac.createGain();
    m.ironSum = ac.createGain();
    // V6 vari-mu, with the makeup that stops it just turning things down.
    m.varimu = ac.createDynamicsCompressor();
    m.varimuMakeup = ac.createGain();

    var n = m.inNode;
    n.connect(m.triode); m.triode.connect(m.triodeDC);
    m.triodeDC.connect(m.triodeTilt); m.triodeTilt.connect(m.triodeGain);
    n = tap("triode", m.triodeGain);
    n.connect(m.pentode); m.pentode.connect(m.pentodeGain);
    n = tap("pentode", m.pentodeGain);
    n.connect(m.tape); m.tape.connect(m.tapeHF); m.tapeHF.connect(m.tapeBump);
    m.tapeBump.connect(m.tapeGain);
    n = tap("tape", m.tapeGain);
    n.connect(m.flutterIn);
    m.flutterIn.connect(m.flutter);
    n = tap("flutter", m.flutter);
    n.connect(m.ironIn);
    m.ironIn.connect(m.ironLow); m.ironLow.connect(m.ironShape);
    m.ironShape.connect(m.ironGain); m.ironGain.connect(m.ironSum);
    m.ironIn.connect(m.ironHigh); m.ironHigh.connect(m.ironSum);
    n = tap("iron", m.ironSum);
    n.connect(m.varimu); m.varimu.connect(m.varimuMakeup);
    tap("varimu", m.varimuMakeup);
    m.varimuMakeup.connect(m.outNode);
    return m;
  }

  /* Chrome's DynamicsCompressorNode applies its own internal makeup gain,
     derived from threshold/knee/ratio, whose size is not specified in any
     way worth depending on - at the default setting it handed back about
     2 dB MORE than it took away, so switching V6 on made the mix louder
     rather than steadier. Rather than hard-code a magic number measured on
     one machine, render a reference tone through a bare compressor with
     the same settings and keep the reciprocal. Cached per setting, and the
     first pass runs with a trim of 1 so nothing ever waits on it. */
  var variMuTrim = {};

  function variMuKey(amount) { return amount.toFixed(2); }

  function measureVariMu(amount, onReady) {
    var T = window.SBTubes;
    var key = variMuKey(amount);
    if (variMuTrim[key] !== undefined || !T
        || typeof OfflineAudioContext === "undefined") { return; }
    variMuTrim[key] = 1;                  // provisional
    /* Long enough for the envelope to settle before it is measured. The
       release is 550 ms, so a 0.4 s render caught the compressor still
       letting go - the trim came out 3 dB too aggressive and overshot the
       other way. */
    var rate = 44100, len = Math.floor(rate * 1.6);
    var oc, vp = T.variMuParams(amount);
    try { oc = new OfflineAudioContext(1, len, rate); } catch (e) { return; }
    var comp = oc.createDynamicsCompressor();
    comp.threshold.value = vp.threshold;
    comp.ratio.value = vp.ratio;
    comp.attack.value = vp.attack;
    comp.release.value = vp.release;
    comp.knee.value = vp.knee;
    var osc = oc.createOscillator();
    osc.frequency.value = 220;
    var g = oc.createGain();
    g.gain.value = T.REF_RMS * Math.SQRT2;
    osc.connect(g); g.connect(comp); comp.connect(oc.destination);
    osc.start();
    oc.startRendering().then(function (buf) {
      var d = buf.getChannelData(0);
      // Measure only the last third, which is fully settled.
      var from = Math.floor(len * 0.7), sum = 0, n = 0;
      for (var i = from; i < len; i++) { sum += d[i] * d[i]; n++; }
      var outRms = Math.sqrt(sum / (n || 1));
      var trim = outRms > 1e-6 ? T.REF_RMS / outRms : 1;
      variMuTrim[key] = Math.max(0.25, Math.min(4, trim));
      if (onReady) { onReady(); }
    }).catch(function () { /* keep the provisional 1 */ });
  }

  function voiceValves(m) {
    var T = window.SBTubes;
    if (!T || !m.triode) { return; }
    var bankOn = modOn("vlv");
    function amt(key) {
      var v = state.valves[key];
      return (bankOn && v && v.on) ? v.amt : 0;
    }
    var tra = amt("triode");
    m.triode.curve = T.triodeCurve(tra);
    m.triodeTilt.gain.value = T.tiltDb("triode", tra);
    m.triodeGain.gain.value = T.compensation("triode", tra);
    var pa = amt("pentode");
    m.pentode.curve = T.pentodeCurve(pa);
    m.pentodeGain.gain.value = T.compensation("pentode", pa);
    var ta = amt("tape");
    m.tape.curve = T.tapeCurve(ta);
    m.tapeHF.gain.value = T.tiltDb("tape", ta);   // tape loses top
    m.tapeBump.gain.value = 2.5 * ta;             // and lifts the head bump
    m.tapeGain.gain.value = T.compensation("tape", ta);
    var fp = T.flutterParams(amt("flutter"));
    m.flutter.delayTime.value = fp.base;
    m.wow.frequency.value = fp.wowHz;
    m.flut.frequency.value = fp.flutterHz;
    m.wowGain.gain.value = fp.wowDepth;
    m.flutGain.gain.value = fp.flutterDepth;
    var ia = amt("iron");
    m.ironShape.curve = T.ironCurve(ia);
    m.ironGain.gain.value = T.compensation("iron", ia);
    var va = amt("varimu");
    var vp = T.variMuParams(va);
    if (va > 0) {
      // Kick off a measurement if this setting has not been seen; re-voice
      // once it lands so the trim applies without blocking anything.
      /* Re-voice whichever chain asked, not just the live one: an offline
         render builds its own chain and would otherwise keep the
         provisional trim of 1. measureVariMu only fires the callback on
         the first measurement, so this cannot recurse. */
      measureVariMu(va, function () { voiceValves(m); });
    }
    m.varimuMakeup.gain.value = va > 0
      ? (variMuTrim[variMuKey(va)] || 1) : 1;
    if (va <= 0) {
      m.varimu.threshold.value = 0;
      m.varimu.ratio.value = 1;
    } else {
      m.varimu.threshold.value = vp.threshold;
      m.varimu.ratio.value = vp.ratio;
      m.varimu.attack.value = vp.attack;
      m.varimu.release.value = vp.release;
      m.varimu.knee.value = vp.knee;
    }
  }

  function buildFx(ac) {
    var fx = {inNode: ac.createGain(), outNode: ac.createGain(),
              dDry: ac.createGain(), dWet: ac.createGain(),
              delay: ac.createDelay(2), fb: ac.createGain(),
              tone: bq(ac, "lowpass", 5000, undefined, 0.7),
              rDry: ac.createGain(), rWet: ac.createGain(),
              pre: ac.createDelay(0.2), conv: ac.createConvolver(),
              damp: bq(ac, "lowpass", 5000, undefined, 0.7), irSize: 0};
    var mid = ac.createGain();
    fx.inNode.connect(fx.dDry); fx.dDry.connect(mid);
    fx.inNode.connect(fx.delay);
    fx.delay.connect(fx.tone); fx.tone.connect(fx.fb); fx.fb.connect(fx.delay);
    fx.tone.connect(fx.dWet); fx.dWet.connect(mid);
    mid.connect(fx.rDry); fx.rDry.connect(fx.outNode);
    mid.connect(fx.pre); fx.pre.connect(fx.conv); fx.conv.connect(fx.damp);
    fx.damp.connect(fx.rWet); fx.rWet.connect(fx.outNode);
    return fx;
  }

  function voiceFx(fx, ac) {
    fx.delay.delayTime.value = state.dly.time;
    fx.fb.gain.value = state.dly.fb;
    fx.tone.frequency.value = state.dly.tone;
    fx.dWet.gain.value = modOn("dly") ? state.dly.mix : 0; fx.dDry.gain.value = 1;
    var sz = Math.round(state.rev.size * 10) / 10;
    if (fx.irSize !== sz) { fx.conv.buffer = reverbIR(ac, sz); fx.irSize = sz; }
    fx.pre.delayTime.value = state.rev.pre;
    fx.damp.frequency.value = state.rev.damp;
    fx.rWet.gain.value = modOn("rev") ? state.rev.mix : 0; fx.rDry.gain.value = 1;
  }

  function buildCenterMatrix(ac) {
    var split = ac.createChannelSplitter(2), merge = ac.createChannelMerger(2);
    var m = {input: split, output: merge,
             ll: ac.createGain(), rl: ac.createGain(),
             lr: ac.createGain(), rr: ac.createGain()};
    split.connect(m.ll, 0); split.connect(m.lr, 0);
    split.connect(m.rl, 1); split.connect(m.rr, 1);
    m.ll.connect(merge, 0, 0); m.rl.connect(merge, 0, 0);
    m.lr.connect(merge, 0, 1); m.rr.connect(merge, 0, 1);
    return m;
  }

  function voiceCenter(cm) {
    var mode = state.center || "normal";
    var v = mode === "solo"   ? [0.5, 0.5, 0.5, 0.5]
          : mode === "remove" ? [0.5, -0.5, -0.5, 0.5]
          : [1, 0, 0, 1];
    cm.ll.gain.value = v[0]; cm.rl.gain.value = v[1];
    cm.lr.gain.value = v[2]; cm.rr.gain.value = v[3];
  }

  /* EQ-12 as a mid/side block. L/R are encoded to M = (L+R)/2 and
     S = (L-R)/2, each runs through its own twelve biquads, and the pair
     is decoded back to L = M+S, R = M-S. In STEREO both chains carry the
     same gains, which is exactly the same as EQing L and R (the matrix
     and the filters are all linear). In MID only the mid chain is voiced
     and the side chain sits flat; in SIDE the reverse. A mono source has
     no side at all, so SIDE does nothing to it - that is the truth of the
     signal, not a bug.
     LISTEN rides on the decoded output: while a band switch is held, a
     band-pass at that band's centre (a low-pass for the low shelf, a
     high-pass for the high shelf) replaces the through path, so you hear
     the region the band is touching, already EQ'd. */
  function buildEq(ac) {
    var split = ac.createChannelSplitter(2), merge = ac.createChannelMerger(2);
    var e = {inNode: ac.createGain(), outNode: ac.createGain(),
             mL: ac.createGain(), mR: ac.createGain(), sL: ac.createGain(), sR: ac.createGain(),
             dML: ac.createGain(), dSL: ac.createGain(), dMR: ac.createGain(), dSR: ac.createGain(),
             thru: ac.createGain(), listen: ac.createBiquadFilter(), listenGain: ac.createGain()};
    e.inNode.channelCount = 2; e.inNode.channelCountMode = "explicit";   // mono arrives as L = R
    e.inNode.connect(split);
    var mid = ac.createGain(), side = ac.createGain();
    e.mL.gain.value = 0.5; e.mR.gain.value = 0.5; e.sL.gain.value = 0.5; e.sR.gain.value = -0.5;
    split.connect(e.mL, 0); split.connect(e.mR, 1); e.mL.connect(mid); e.mR.connect(mid);
    split.connect(e.sL, 0); split.connect(e.sR, 1); e.sL.connect(side); e.sR.connect(side);
    function chain(from) {
      var fs = EQ_BANDS.map(function (b) {
        var f = ac.createBiquadFilter();
        f.type = b.type; f.frequency.value = b.f; f.Q.value = state.q; f.gain.value = 0;
        return f;
      });
      var n = from;
      fs.forEach(function (f) { n.connect(f); n = f; });
      return {filters: fs, out: n};
    }
    var cm = chain(mid), cs = chain(side);
    e.filtersM = cm.filters; e.filtersS = cs.filters;
    e.dML.gain.value = 1; e.dSL.gain.value = 1; e.dMR.gain.value = 1; e.dSR.gain.value = -1;
    cm.out.connect(e.dML); cs.out.connect(e.dSL); cm.out.connect(e.dMR); cs.out.connect(e.dSR);
    e.dML.connect(merge, 0, 0); e.dSL.connect(merge, 0, 0);
    e.dMR.connect(merge, 0, 1); e.dSR.connect(merge, 0, 1);
    merge.connect(e.thru); e.thru.connect(e.outNode);
    merge.connect(e.listen); e.listen.connect(e.listenGain); e.listenGain.connect(e.outNode);
    e.listen.type = "bandpass"; e.thru.gain.value = 1; e.listenGain.gain.value = 0;
    return e;
  }

  var eqSolo = -1;   // the band held for LISTEN; transient, never saved, never in history
  function voiceEq(e, eqOn) {
    var mode = state.eqMode || "stereo";
    var onM = eqOn && mode !== "side", onS = eqOn && mode !== "mid";
    EQ_BANDS.forEach(function (b, i) {
      var g = state.eqOff[i] ? 0 : state.eq[i];
      e.filtersM[i].gain.value = onM ? g : 0; e.filtersM[i].Q.value = state.q;
      e.filtersS[i].gain.value = onS ? g : 0; e.filtersS[i].Q.value = state.q;
    });
    var solo = eqSolo >= 0 ? EQ_BANDS[eqSolo] : null;
    if (solo) {
      e.listen.type = solo.type === "lowshelf" ? "lowpass" : solo.type === "highshelf" ? "highpass" : "bandpass";
      e.listen.frequency.value = solo.type === "lowshelf" ? solo.f * 1.6
                                : solo.type === "highshelf" ? solo.f / 1.6 : solo.f;
      e.listen.Q.value = solo.type === "peaking" ? Math.max(1.2, state.q * 1.5) : 0.7;
    }
    e.thru.gain.value = solo ? 0 : 1;
    e.listenGain.gain.value = solo ? 1 : 0;
  }

  /* ---------- DYN-1 sidechain: the ducker worklet ----------
     The compressor node has no key input, so keying DYN-1 from a stem runs
     through static/js/rack-ducker.js, an AudioWorklet spliced between the
     compressor and its makeup gain. Every context loads the module once;
     until it has — or where worklets do not exist at all — the splice is a
     plain wire and DYN-1 uses its own detector exactly as before. A keyed
     chain neutralises the internal detector so nothing is compressed twice.
     The key is the stem's RAW signal, before its lane fader, mute or solo:
     that is how a sidechain input behaves on hardware, and it means the
     kick can drive the duck while being muted from the mix. */
  var DUCKER_URL = "/static/js/rack-ducker.js?v=1";
  var duckReady = (typeof WeakMap !== "undefined") ? new WeakMap() : null;   // context -> Promise<bool>
  var keyGR = 0;                                                              // live ducker reduction, dB (<= 0)
  function loadDucker(ac) {
    if (!ac || !ac.audioWorklet || !duckReady) return Promise.resolve(false);
    var p = duckReady.get(ac);
    if (!p) {
      p = ac.audioWorklet.addModule(DUCKER_URL).then(function () { return true; }, function () { return false; });
      duckReady.set(ac, p);
    }
    return p;
  }
  function armDucker(c, ac) {
    if (c.duck || !ac.audioWorklet) return;
    var d;
    try {
      d = new AudioWorkletNode(ac, "sb-ducker", {numberOfInputs: 2, numberOfOutputs: 1, outputChannelCount: [2]});
    } catch (e) { return; }
    // comp -> duckIn -> makeup becomes comp -> duck -> duckIn -> makeup, key -> duck
    c.comp.disconnect(c.duckIn);
    c.comp.connect(d, 0, 0);
    d.connect(c.duckIn);
    c.keyIn.connect(d, 0, 1);
    c.duck = d;
    d.port.onmessage = function (e) { if (c === live) keyGR = +e.data || 0; };
  }
  function keyStem() {
    var k = state.comp && state.comp.key;
    if (!k) return null;
    for (var i = 0; i < stems.length; i++) if (stems[i].name === k) return stems[i];
    return null;
  }
  function voiceDuck(c, compOn) {
    if (!c.duck) return false;
    var keyed = compOn && !!keyStem();
    var P = c.duck.parameters;
    P.get("threshold").value = state.comp.thr; P.get("ratio").value = state.comp.ratio;
    P.get("attack").value = state.comp.att;    P.get("release").value = state.comp.rel;
    P.get("knee").value = 6;
    P.get("active").value = keyed ? 1 : 0;
    c.duckKeyed = keyed;
    return keyed;
  }

  function buildChain(ac, dest) {
    var input = ac.createGain();
    // Mono sources must duplicate to both channels before the mid/side split.
    input.channelCount = 2;
    input.channelCountMode = "explicit";
    var eq = buildEq(ac);
    var filters = eq.filtersM;            // the chain the scope draws; voiceChain re-points it per mode
    var tube = ac.createWaveShaper();
    tube.curve = tubeCurve(state.tube.drive, state.tube.bias);
    tube.oversample = "4x";
    var wetTube = ac.createGain(); wetTube.gain.value = state.tube.mix;
    var dryTube = ac.createGain(); dryTube.gain.value = 1 - state.tube.mix;
    var cabMic = buildCabMic(ac);
    var comp = ac.createDynamicsCompressor();
    comp.threshold.value = state.comp.thr; comp.ratio.value = state.comp.ratio;
    comp.attack.value = state.comp.att; comp.release.value = state.comp.rel;
    comp.knee.value = 6;
    var makeup = ac.createGain();
    makeup.gain.value = Math.pow(10, state.comp.makeup / 20);
    var outGain = ac.createGain();
    outGain.gain.value = Math.pow(10, state.out / 20);

    var centerM = buildCenterMatrix(ac);
    voiceCenter(centerM);
    input.connect(centerM.input);
    var sub = buildSub(ac);
    voiceSub(sub);
    var tubeIn = ac.createGain();               // an explicit door, so the tube block is patchable
    tubeIn.connect(tube); tube.connect(wetTube);
    tubeIn.connect(dryTube);
    var sum = ac.createGain();
    wetTube.connect(sum); dryTube.connect(sum);
    var valves = buildValves(ac);
    voiceValves(valves);
    voiceCabMic(cabMic);
    var duckIn = ac.createGain(), keyIn = ac.createGain();   // the sidechain splice; see armDucker
    comp.connect(duckIn); duckIn.connect(makeup);
    var fx = buildFx(ac);
    voiceFx(fx, ac);
    // The bay: seven blocks, each a door in and a door out, cabled in
    // whatever order the artist patched. The matrix is always first and
    // the output trim always last - those are the bay's end plates.
    var blocks = {eq:   {i: eq.inNode,       o: eq.outNode},
                  sub:  {i: sub.inNode,      o: sub.outNode},
                  tube: {i: tubeIn,          o: sum},
                  vlv:  {i: valves.inNode,   o: valves.outNode},
                  cab:  {i: cabMic.moduleIn, o: cabMic.moduleOut},
                  comp: {i: comp,            o: makeup},
                  fx:   {i: fx.inNode,       o: fx.outNode}};
    var order = patchOrder(), node = centerM.output;
    order.forEach(function (k) { node.connect(blocks[k].i); node = blocks[k].o; });
    node.connect(outGain);
    outGain.connect(dest);
    return {input: input, filters: filters, eq: eq, tube: tube, wetTube: wetTube,
            patchOrder: order.join(","), tubeIn: tubeIn,
            duckIn: duckIn, keyIn: keyIn, duck: null, duckKeyed: false,
            dryTube: dryTube, sum: sum, cabMic: cabMic, comp: comp,
            makeup: makeup, outGain: outGain, out: outGain, centerM: centerM,
            fx: fx, sub: sub, valves: valves};
  }

  /* Per-module level meters.
   *
   * Each analyser taps that module's OWN output, so you can watch the
   * level change down the chain and see where it dies.
   *
   * Switching a module OFF does not zero its meter, and should not: an
   * off module passes through neutrally by design (EQ gains 0, tube fully
   * dry, comp 1:1), so signal still leaves it. Measured: valves off holds
   * at the same reading as valves on.
   *
   * dly and rev are the exception, and the reason they tap their wet
   * sends rather than the fx bus. The bus carries the dry signal too, so
   * it reads hot with both effects at zero and tells you nothing. The wet
   * send reads exactly 0 with the effect off and rises as you bring it
   * in, which is what you actually want to see.
   */
  function meterTaps(ch) {
    return {sub: ch.sub.outNode,
            eq: ch.eq.outNode,
            tube: ch.sum,
            vlv: ch.valves.outNode,
            cab: ch.cabMic.moduleOut,
            comp: ch.makeup,
            dly: ch.fx.dWet,
            rev: ch.fx.rWet,
            out: ch.outGain};
  }

  function buildMeters(ac, ch) {
    var taps = meterTaps(ch), out = {};
    Object.keys(taps).forEach(function (k) {
      if (!taps[k]) return;
      var a = ac.createAnalyser();
      a.fftSize = 256;
      a.smoothingTimeConstant = 0;   // we want peak; the fall is smoothed below
      taps[k].connect(a);            // a tap, not a link in the chain
      out[k] = {node: a, buf: new Uint8Array(a.fftSize), peak: 0};
    });
    return out;
  }

  var lvlEls = null;

  function paintMeters() {
    if (!live || !live.meters) return;
    if (!lvlEls) {
      lvlEls = {};
      document.querySelectorAll(".rk-lvl").forEach(function (el) {
        lvlEls[el.dataset.mod] = {wrap: el, fill: el.firstElementChild};
      });
    }
    Object.keys(live.meters).forEach(function (k) {
      var m = live.meters[k], el = lvlEls[k];
      if (!el) return;
      m.node.getByteTimeDomainData(m.buf);
      var peak = 0;
      for (var i = 0; i < m.buf.length; i++) {
        var v = Math.abs(m.buf[i] - 128) / 128;
        if (v > peak) peak = v;
      }
      // Rise instantly, fall slowly. A meter that falls as fast as it rises
      // is a flicker at any tempo with transients in it.
      m.peak = peak > m.peak ? peak : m.peak * 0.86 + peak * 0.14;
      el.fill.style.right = ((1 - Math.min(1, m.peak)) * 100).toFixed(1) + "%";
      el.wrap.classList.toggle("is-hot", m.peak > 0.98);
    });
  }

  function buildLive() {
    live = buildChain(ctx, ctx.destination);
    live.analyser = ctx.createAnalyser();
    live.analyser.fftSize = 4096;
    live.analyser.smoothingTimeConstant = 0.8;
    live.meters = buildMeters(ctx, live);
    var mine = live;
    loadDucker(ctx).then(function (ok) { if (ok && live === mine) { armDucker(live, ctx); voiceLive(); } });
    live.outGain.connect(live.analyser);
    live.wet = ctx.createGain(); live.dry = ctx.createGain();
    live.dry.gain.value = 0;
    live.wet.connect(live.input);
    live.dry.connect(ctx.destination);
    live.dry.connect(live.analyser);
  }
  /* Re-cable the live rack to the current patch order. Web Audio cannot
     reorder a graph in place, so the chain is rebuilt; the old one is
     fully disconnected first or it would keep playing into the output.
     Playback is the caller's problem (applyState resumes it). */
  function rebuildLive() {
    if (!ctx || !live) return;
    if (playing) stop();
    try { live.outGain.disconnect(); } catch (e) {}
    try { live.wet.disconnect(); } catch (e) {}
    try { live.dry.disconnect(); } catch (e) {}
    keyGR = 0;
    buildLive();
  }
  function ensureCtx() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      buildLive();
    }
    return ctx;
  }

  function updateGlow() {
    var el = document.getElementById("tube-glow");
    if (!el) return;
    var heat = modOn("tube")
      ? Math.min(1, ((state.tube.drive - 1) / 9) * (0.25 + 0.75 * state.tube.mix))
      : 0;
    el.style.opacity = (0.12 + 0.88 * heat).toFixed(2);
    el.style.boxShadow = "0 0 " + Math.round(3 + heat * 14) + "px rgba(255,156,63," + (heat * 0.7).toFixed(2) + ")";
  }

  /* Voice one chain (live or offline) from state, honoring module power.
     Off modules read as neutral: EQ gains 0, tube fully dry, comp 1:1 at
     0dB, sends muted, trim 0dB — knob positions stay untouched. */
  function voiceChain(c, ac) {
    if (c.valves) { voiceValves(c.valves); }
    var eqOn = modOn("eq"), tubeOn = modOn("tube"), compOn = modOn("comp");
    voiceEq(c.eq, eqOn);
    c.filters = (state.eqMode === "side") ? c.eq.filtersS : c.eq.filtersM;   // what the scope draws
    c.tube.curve = tubeCurve(state.tube.drive, state.tube.bias);
    c.wetTube.gain.value = tubeOn ? state.tube.mix : 0;
    c.dryTube.gain.value = tubeOn ? 1 - state.tube.mix : 1;
    voiceCabMic(c.cabMic);
    voiceCenter(c.centerM);
    voiceFx(c.fx, ac);
    voiceSub(c.sub);
    var keyed = voiceDuck(c, compOn);
    c.comp.threshold.value = (compOn && !keyed) ? state.comp.thr : 0;
    c.comp.ratio.value = (compOn && !keyed) ? state.comp.ratio : 1;
    c.comp.attack.value = state.comp.att;
    c.comp.release.value = state.comp.rel;
    c.makeup.gain.value = Math.pow(10, (compOn ? state.comp.makeup : 0) / 20);
    c.outGain.gain.value = Math.pow(10, (modOn("out") ? state.out : 0) / 20);
  }

  // ---------- undo / redo ----------
  // The rack had A/B per module and no way back at all. This snapshots the
  // state BEFORE each change, which is what an undo actually needs, and
  // coalesces a drag so turning one knob is one step rather than sixty.
  //
  // It hangs off applyState() — the single call every mutation already
  // makes — so a change from anywhere is captured without each caller
  // having to remember to record it.
  var HIST_MAX = 60, HIST_COALESCE_MS = 700;
  var hist = {past: [], future: [], prev: null, label: "", at: 0, quiet: false};

  function snap() { return JSON.parse(JSON.stringify(state)); }

  function histMark(label) {
    // Called from applyState AFTER the mutation. An entry means "this is
    // what things looked like BEFORE `label` happened", so it pairs the
    // PREVIOUS state with the NEW label — pairing it with the previous
    // label named every step after the one before it.
    var now = Date.now();
    if (hist.prev === null) { hist.prev = snap(); hist.at = now; return; }
    var top = hist.past[hist.past.length - 1];
    // Coalesce against the entry actually on the stack, not against a
    // field this function overwrites on every call. Sixty pointermove
    // events on one knob are one thing the user did, and a history that
    // lists them sixty times is unusable.
    var sameGesture = top && top.label === label && (now - hist.at) < HIST_COALESCE_MS;
    if (!sameGesture) {
      hist.past.push({s: hist.prev, label: label || "change"});
      if (hist.past.length > HIST_MAX) hist.past.shift();
      hist.future.length = 0;
    }
    hist.prev = snap();
    hist.label = label;
    hist.at = now;
    paintHistory();
  }

  function histRestore(snapshot, label) {
    hist.quiet = true;
    state = JSON.parse(JSON.stringify(snapshot));
    ensureFx(state);
    hist.prev = snap();
    hist.label = label || "";
    syncAll(); applyState();
    hist.quiet = false;
    paintHistory();
  }

  function histUndo() {
    if (!hist.past.length) return;
    var step = hist.past.pop();
    hist.future.push({s: hist.prev, label: hist.label || "change"});
    histRestore(step.s, step.label);
    setStatus("Undone: " + step.label);
  }

  function histRedo() {
    if (!hist.future.length) return;
    var step = hist.future.pop();
    hist.past.push({s: hist.prev, label: hist.label || "change"});
    histRestore(step.s, step.label);
    setStatus("Redone: " + step.label);
  }

  function histJump(index) {
    // index counts back from the most recent step: 0 is the newest.
    if (index < 0 || index >= hist.past.length) return;
    var keep = hist.past.slice(0, hist.past.length - index);
    var target = keep[keep.length - 1];
    // Everything newer than the target becomes redoable, newest last.
    var undone = hist.past.slice(hist.past.length - index);
    hist.future = hist.future.concat([{s: hist.prev, label: hist.label || "change"}])
                             .concat(undone.slice(1).map(function (x) { return x; }));
    hist.past = keep.slice(0, keep.length - 1);
    histRestore(target.s, target.label);
    setStatus("Back to: " + target.label);
  }

  function setStatus(msg) {
    var el = document.getElementById("rk-status");
    if (el) el.textContent = msg;
    var live = document.getElementById("rk-live");
    if (live) { live.textContent = ""; setTimeout(function () { live.textContent = msg; }, 30); }
  }

  function paintHistory() {
    var u = document.getElementById("rk-undo"), r = document.getElementById("rk-redo");
    if (u) { u.disabled = !hist.past.length; u.title = hist.past.length
      ? "Undo " + hist.past[hist.past.length - 1].label + " (Ctrl+Z)" : "Nothing to undo"; }
    if (r) { r.disabled = !hist.future.length; r.title = hist.future.length
      ? "Redo " + hist.future[hist.future.length - 1].label + " (Ctrl+Shift+Z)" : "Nothing to redo"; }
    var btn = document.getElementById("rk-hist-btn");
    if (btn) btn.disabled = !hist.past.length;
    var list = document.getElementById("rk-hist-list");
    if (!list) return;
    list.textContent = "";
    if (!hist.past.length) {
      var none = document.createElement("li");
      none.className = "rk-hist-none";
      none.textContent = "Nothing yet — every change you make lands here.";
      list.appendChild(none);
      return;
    }
    // Newest first: that is the order somebody looking for "what did I just
    // do" reads in.
    for (var i = hist.past.length - 1, n = 0; i >= 0 && n < 20; i--, n++) {
      (function (idx, step) {
        var li = document.createElement("li");
        var b = document.createElement("button");
        b.type = "button";
        b.className = "rk-hist-item";
        b.textContent = step.label;
        b.setAttribute("aria-label", "Go back to before " + step.label);
        b.addEventListener("click", function () { histJump(idx); closeHistory(); });
        li.appendChild(b);
        list.appendChild(li);
      })(n, hist.past[i]);
    }
  }

  function closeHistory() {
    var pop = document.getElementById("rk-hist-pop");
    var btn = document.getElementById("rk-hist-btn");
    if (pop) pop.hidden = true;
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  // What a change is CALLED matters more than that it happened: "EQ 250 Hz"
  // is a step somebody recognises, "change" is not. Set by the mutation
  // sites that know; anything else falls back to the module name.
  var histLabel = "change";
  function labelled(name, fn) {
    return function () { histLabel = name; return fn.apply(this, arguments); };
  }

  function applyState() {
    var resumeAt = -1;
    if (live && live.patchOrder !== patchOrder().join(",")) {
      resumeAt = playing ? playPos() : -1;
      rebuildLive();
    }
    if (live) {
      voiceChain(live, ctx);
      live.wet.gain.value = state.bypass ? 0 : 1;
      live.dry.gain.value = state.bypass ? 1 : 0;
    }
    updateGlow();
    syncModButtons();
    paintCabView();
    eqCurveDirty = true;
    if (resumeAt >= 0) startPlayback(resumeAt);
    if (!hist.quiet) histMark(histLabel);
  }

  // ---------- SB-08 placement diagram ----------
  // A schematic of the chosen cab, mic, angle and gap. Every number here
  // is read straight off state.cab, so it can only ever show the setup
  // that is actually in the audio chain - it is not an illustration.
  /* Each cab gets the proportions of the real thing - a combo is wide and
     low, a 4×12 close to square, an 8×10 the tall two-by-four fridge - so
     the silhouette alone tells you which one is in the chain. Cone offsets
     are measured from the centre of the box; the box stands on the floor. */
  var FLOOR = 103, CAB_X = 12;
  // Named apart from the DSP tables at the top of this file on purpose:
  // they live in the same function scope, so sharing a name meant sharing
  // a binding, and whichever ran last won. These are the picture; CABS and
  // MICS up there are the filters.
  var CAB_ART = {
    direct:    {cap: "Direct / DI", w: 0, h: 0, cones: []},
    combo112:  {cap: "1×12 combo", w: 78, h: 56, cones: [[0, 0, 17]]},
    open212:   {cap: "2×12 open-back", w: 82, h: 50,
                cones: [[-19, 0, 15], [19, 0, 15]]},
    closed412: {cap: "4×12 closed-back", w: 68, h: 78,
                cones: [[-16, -17, 14], [16, -17, 14],
                        [-16, 17, 14], [16, 17, 14]]},
    bass810:   {cap: "8×10 bass", w: 48, h: 92,
                cones: [[-10.5, -31.5, 8.5], [10.5, -31.5, 8.5],
                        [-10.5, -10.5, 8.5], [10.5, -10.5, 8.5],
                        [-10.5, 10.5, 8.5], [10.5, 10.5, 8.5],
                        [-10.5, 31.5, 8.5], [10.5, 31.5, 8.5]]},
  };
  var MIC_LABELS = {dynamic: "Dynamic", ribbon: "Ribbon", condenser: "Condenser"};

  function svgEl(name, attrs) {
    var el = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.keys(attrs).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    return el;
  }

  function micShape(kind) {
    /* Drawn lying on its side, capsule to the left, so the group can be
       rotated about the capsule to show the off-axis angle. */
    var g = svgEl("g", {});
    if (kind === "ribbon") {
      g.appendChild(svgEl("rect", {x: -9, y: -6, width: 20, height: 12, rx: 6,
                                   fill: "#1b1813", stroke: "#c9bd9c"}));
      g.appendChild(svgEl("path", {d: "M-1 -6V6", stroke: "#c9bd9c"}));
      g.appendChild(svgEl("rect", {x: 11, y: -1.2, width: 9, height: 2.4,
                                   fill: "#8a7c5d"}));
    } else if (kind === "condenser") {
      g.appendChild(svgEl("rect", {x: -8, y: -8, width: 16, height: 16, rx: 2,
                                   fill: "#1b1813", stroke: "#c9bd9c"}));
      g.appendChild(svgEl("circle", {cx: -1, cy: 0, r: 5.2,
                                     fill: "none", stroke: "#c9bd9c"}));
      g.appendChild(svgEl("rect", {x: 8, y: -1.2, width: 12, height: 2.4,
                                   fill: "#8a7c5d"}));
    } else {
      g.appendChild(svgEl("circle", {cx: -4, cy: 0, r: 5.8,
                                     fill: "#1b1813", stroke: "#c9bd9c"}));
      g.appendChild(svgEl("path", {d: "M-6.4 -4.2V4.2M-1.6 -4.2V4.2",
                                   stroke: "#8a7c5d"}));
      g.appendChild(svgEl("rect", {x: 1.4, y: -3.4, width: 16, height: 6.8, rx: 1.6,
                                   fill: "#1b1813", stroke: "#c9bd9c"}));
    }
    return g;
  }

  function paintCabView() {
    var svg = document.getElementById("rk-cabview");
    if (!svg) { return; }
    var cap = document.getElementById("rk-cabview-cap");
    var c = state.cab;
    var spec = CAB_ART[c.cab] || CAB_ART.direct;
    var room = Math.round(35 * c.dist);
    svg.innerHTML = "";
    svg.setAttribute("opacity", c.on ? "1" : "0.32");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke-width", "1.3");

    if (c.cab === "direct") {
      // No cab, no mic: a DI plate patched straight to the output.
      svg.appendChild(svgEl("rect", {x: 40, y: 40, width: 62, height: 36, rx: 3,
                                     fill: "#100e0a", stroke: "#c9bd9c"}));
      svg.appendChild(svgEl("circle", {cx: 58, cy: 58, r: 6,
                                       fill: "none", stroke: "#c9bd9c"}));
      svg.appendChild(svgEl("circle", {cx: 58, cy: 58, r: 2.1,
                                       fill: "#e8c667", stroke: "none"}));
      svg.appendChild(svgEl("path", {d: "M64 58h14c8 0 8 -14 16 -14h62",
                                     stroke: "#8a7c5d",
                                     "stroke-dasharray": "none"}));
      svg.appendChild(svgEl("path", {d: "M168 40l8 4-8 4", stroke: "#8a7c5d"}));
      if (cap) {
        cap.textContent = c.on
          ? "DIRECT · NO CAB OR MIC IN CIRCUIT"
          : "BYPASSED · DIRECT";
      }
      return;
    }

    // The floor everything stands on, drawn first so it sits behind.
    svg.appendChild(svgEl("path", {d: "M4 " + FLOOR + "h188", stroke: "#3a3424"}));

    // Cabinet: box, baffle, then this model's real cone layout.
    var cx0 = CAB_X + spec.w / 2, cy0 = FLOOR - spec.h / 2;
    svg.appendChild(svgEl("rect", {x: CAB_X, y: FLOOR - spec.h,
                                   width: spec.w, height: spec.h, rx: 4,
                                   fill: "#151210", stroke: "#c9bd9c"}));
    svg.appendChild(svgEl("rect", {x: CAB_X + 5, y: FLOOR - spec.h + 5,
                                   width: spec.w - 10, height: spec.h - 10, rx: 2,
                                   fill: "#0c0a08", stroke: "#3a3424"}));
    spec.cones.forEach(function (cone) {
      var cx = cx0 + cone[0], cy = cy0 + cone[1], r = cone[2];
      svg.appendChild(svgEl("circle", {cx: cx, cy: cy, r: r,
                                       fill: "none", stroke: "#8a7c5d"}));
      svg.appendChild(svgEl("circle", {cx: cx, cy: cy, r: (r * 0.34).toFixed(1),
                                       fill: "#c9a24a", stroke: "none"}));
    });

    // Mic: the gap is the Distance knob, the angle is the axis switch, and
    // it lines up with one driver - the way anyone actually mics a cab -
    // rather than hovering at the geometric middle of the box.
    var SCALE = 1.35;
    var right = CAB_X + spec.w;
    var mx = right + 16 + c.dist * 52;
    var my = cy0 + spec.cones.reduce(function (best, cone) {
      return Math.abs(cone[1]) < Math.abs(best) ? cone[1] : best;
    }, spec.cones[0][1]);
    var angle = c.axis === "off" ? 32 : 0;
    var g = micShape(c.mic);
    g.setAttribute("transform", "translate(" + mx.toFixed(1) + ","
                   + my.toFixed(1) + ") rotate(" + angle + ") scale("
                   + SCALE + ")");
    svg.appendChild(svgEl("path", {d: "M" + right + " " + my.toFixed(1)
                                      + "H" + (mx - 13).toFixed(1),
                                   stroke: "#c9a24a",
                                   "stroke-dasharray": "3 3"}));
    svg.appendChild(g);
    // Stand: the mic has to be held up by something.
    var sx = mx + 19 * SCALE;
    svg.appendChild(svgEl("path", {
      d: "M" + sx.toFixed(1) + " " + my.toFixed(1) + "V" + FLOOR + "m-9 0h18",
      stroke: "#3a3424"}));

    if (cap) {
      cap.textContent = (c.on ? "" : "BYPASSED · ")
        + spec.cap.toUpperCase() + " · " + (MIC_LABELS[c.mic] || "").toUpperCase()
        + " · " + (c.axis === "off" ? "OFF-AXIS" : "ON-AXIS")
        + " · ROOM " + room + "%";
    }
  }

  // ---------- knob factory ----------
  function knobPt(r, aDeg) {
    var a = (aDeg - 90) * Math.PI / 180;
    return [40 + r * Math.cos(a), 40 + r * Math.sin(a)];
  }
  function knobArc(r, a0, a1) {
    var p0 = knobPt(r, a0), p1 = knobPt(r, a1);
    var large = Math.abs(a1 - a0) > 180 ? 1 : 0;
    var sweep = a1 > a0 ? 1 : 0;
    return "M" + p0[0].toFixed(2) + " " + p0[1].toFixed(2) +
           " A" + r + " " + r + " 0 " + large + " " + sweep + " " +
           p1[0].toFixed(2) + " " + p1[1].toFixed(2);
  }
  var knobUid = 0;

  // One floating readout shared by every knob: shows the exact value while
  // dragging or wheeling, fades when released.
  var knobTip = null, knobTipT = null;
  function showTip(x, y, text) {
    if (!knobTip) {
      knobTip = document.createElement("div");
      knobTip.style.cssText =
        "position:fixed;z-index:60;pointer-events:none;padding:3px 9px;" +
        "border:1px solid #8a6d1f;border-radius:4px;background:#141209;" +
        "color:#e8c667;font:700 12px/1.4 ui-monospace,monospace;" +
        "transform:translate(-50%,-135%);box-shadow:0 2px 8px rgba(0,0,0,.6);display:none;";
      document.body.appendChild(knobTip);
    }
    knobTip.textContent = text;
    knobTip.style.left = x + "px";
    knobTip.style.top = y + "px";
    knobTip.style.display = "block";
  }
  function hideTip() { if (knobTip) knobTip.style.display = "none"; }

  /* makeKnob: one rotary control. opts:
     min/max/def, bipolar (arc from 12 o'clock), size px, label, fmt(v),
     wheelStep, decimals, get(), set(v) -> writes state. Returns {el, sync}. */
  function makeKnob(opts) {
    var id = "kb" + (knobUid++);
    var col = document.createElement("div");
    col.className = "flex flex-col items-center";
    var val = document.createElement("div");
    val.className = "k-value font-mono text-[10px] font-bold tabular-nums";
    var wrap = document.createElement("div");
    wrap.style.touchAction = "none";
    wrap.style.cursor = "ns-resize";
    /* Click it, then drive it from the keyboard. A rotary control that
       can only be dragged is unreachable without a mouse and invisible to
       a screen reader, so it announces itself as what it actually is - a
       slider with a range and a current value. */
    wrap.className = "rk-knob";
    wrap.tabIndex = 0;
    wrap.setAttribute("role", "slider");
    wrap.setAttribute("aria-label", opts.label);
    wrap.setAttribute("aria-valuemin", String(opts.min));
    wrap.setAttribute("aria-valuemax", String(opts.max));
    wrap.innerHTML =
      '<svg viewBox="0 0 80 80" width="' + opts.size + '" height="' + opts.size + '">' +
      '<defs><radialGradient id="' + id + '" cx="0.35" cy="0.3" r="0.9">' +
      '<stop offset="0" stop-color="#f0dfa8"/><stop offset="0.45" stop-color="#d8b25a"/>' +
      '<stop offset="0.8" stop-color="#8a6d1f"/><stop offset="1" stop-color="#5c4715"/>' +
      '</radialGradient></defs>' +
      '<circle cx="40" cy="40" r="33" fill="none" stroke="#332e22" stroke-width="3" stroke-dasharray="1.8 3.95"/>' +
      '<path d="' + knobArc(29, -135, 135) + '" fill="none" stroke="#221e16" stroke-width="5" stroke-linecap="round"/>' +
      '<path class="k-glow" fill="none" stroke-width="9" stroke-linecap="round" opacity="0.22"/>' +
      '<path class="k-arc" fill="none" stroke-width="4.5" stroke-linecap="round"/>' +
      '<circle cx="40" cy="40" r="22" fill="url(#' + id + ')"/>' +
      '<circle cx="40" cy="40" r="22" fill="none" stroke="#1c1302" stroke-width="2"/>' +
      '<circle cx="40" cy="40" r="22" fill="none" stroke="rgba(255,255,255,0.14)" stroke-width="0.8"/>' +
      '<line class="k-ptr" x1="40" y1="40" x2="40" y2="21.5" stroke="#f7efd8" stroke-width="3" stroke-linecap="round"/>' +
      '<circle cx="40" cy="40" r="2.4" fill="#1c1302"/>' +
      '</svg>';
    var svg = wrap.firstChild;
    var ptr = svg.querySelector(".k-ptr");
    var arc = svg.querySelector(".k-arc");
    var glow = svg.querySelector(".k-glow");
    var lab = document.createElement("div");
    lab.className = "k-label text-[9px] font-bold uppercase tracking-wide";
    lab.textContent = opts.label;

    function angleOf(v) {
      return -135 + (v - opts.min) / (opts.max - opts.min) * 270;
    }
    function paint() {
      var v = opts.get();
      var ang = angleOf(v);
      ptr.setAttribute("transform", "rotate(" + ang + " 40 40)");
      var from = opts.bipolar ? 0 : -135;
      var isCut = opts.bipolar && v < 0;
      var color = isCut ? "#e07a3c" : "#e8c667";
      var near = Math.abs(ang - from) < 1.5;
      if (near) {
        arc.setAttribute("d", ""); glow.setAttribute("d", "");
      } else {
        var d = ang > from ? knobArc(29, from, ang) : knobArc(29, ang, from);
        arc.setAttribute("d", d); arc.setAttribute("stroke", color);
        glow.setAttribute("d", d); glow.setAttribute("stroke", color);
      }
      val.textContent = opts.fmt(v);
      val.style.color = opts.bipolar
        ? (Math.abs(v) < 1e-6 ? "#9a8f78" : color) : "#e8c667";
      // Screen readers read valuetext when it exists, so they hear
      // "Drive 2.4" rather than a bare number with no unit.
      wrap.setAttribute("aria-valuenow", String(v));
      wrap.setAttribute("aria-valuetext", opts.label + " " + opts.fmt(v));
    }
    function setVal(v) {
      v = Math.max(opts.min, Math.min(opts.max, v));
      v = Math.round(v / opts.wheelStep * 5) * opts.wheelStep / 5;   // fine grid
      v = Math.round(v * 1000) / 1000;
      if (v === opts.get()) return;
      // The knob's own caption is what the user just grabbed, so it is
      // also what the history entry should be called. Coalescing in
      // histMark turns one drag into one step rather than sixty.
      histLabel = opts.label;
      opts.set(v);
      paint(); applyState();
    }
    var drag = null;
    function tipText() { return opts.label + "  " + opts.fmt(opts.get()); }
    wrap.addEventListener("pointerdown", function (e) {
      var r = wrap.getBoundingClientRect();
      drag = {y: e.clientY, v: opts.get(), tx: r.left + r.width / 2, ty: r.top};
      wrap.setPointerCapture(e.pointerId);
      showTip(drag.tx, drag.ty, tipText());
      e.preventDefault();
    });
    wrap.addEventListener("pointermove", function (e) {
      if (drag) {
        setVal(drag.v + (drag.y - e.clientY) * (opts.max - opts.min) / 200);
        showTip(drag.tx, drag.ty, tipText());
      }
    });
    wrap.addEventListener("pointerup", function () { drag = null; hideTip(); });
    wrap.addEventListener("pointercancel", function () { drag = null; hideTip(); });
    wrap.addEventListener("dblclick", function () { setVal(opts.def); });
    wrap.addEventListener("wheel", function (e) {
      e.preventDefault();
      setVal(opts.get() + (e.deltaY < 0 ? opts.wheelStep : -opts.wheelStep));
      var r = wrap.getBoundingClientRect();
      showTip(r.left + r.width / 2, r.top, tipText());
      clearTimeout(knobTipT);
      knobTipT = setTimeout(hideTip, 700);
    }, {passive: false});

    /* Keyboard. The steps follow the same grid the wheel and the drag
       already snap to, so a knob turned by arrow keys lands on exactly
       the values a mouse can reach - no third set of numbers. */
    function nudge(mult) {
      setVal(opts.get() + opts.wheelStep * mult);
      var r = wrap.getBoundingClientRect();
      showTip(r.left + r.width / 2, r.top, tipText());
      clearTimeout(knobTipT);
      knobTipT = setTimeout(hideTip, 1200);
    }
    wrap.addEventListener("keydown", function (e) {
      if (e.altKey || e.ctrlKey || e.metaKey) { return; }   // leave shortcuts alone
      // Shift is the fine grid - a fifth of a step, which is the finest
      // value setVal will actually keep.
      var step = e.shiftKey ? 0.2 : 1;
      var handled = true;
      switch (e.key) {
        case "ArrowUp": case "ArrowRight": nudge(step); break;
        case "ArrowDown": case "ArrowLeft": nudge(-step); break;
        case "PageUp": nudge(10); break;
        case "PageDown": nudge(-10); break;
        case "Home": setVal(opts.min); break;
        case "End": setVal(opts.max); break;
        // Same as double-click: put it back where it started.
        case "Backspace": case "Delete": case "0":
          setVal(opts.def);
          break;
        default: handled = false;
      }
      if (handled) {
        e.preventDefault();       // stop the page scrolling under the rack
        e.stopPropagation();
      }
    });
    // Show the read-out while it has focus, so a keyboard user sees the
    // value they are changing without hunting for it.
    wrap.addEventListener("focus", function () {
      var r = wrap.getBoundingClientRect();
      showTip(r.left + r.width / 2, r.top, tipText());
      clearTimeout(knobTipT);
    });
    wrap.addEventListener("blur", hideTip);
    paint();
    col.appendChild(val); col.appendChild(wrap); col.appendChild(lab);
    return {el: col, sync: paint};
  }

  // ---------- EQ + module knobs ----------
  var eqWrap = document.getElementById("rk-eq");
  function renderEq() {
    eqWrap.innerHTML = "";
    EQ_BANDS.forEach(function (b, i) {
      var k = makeKnob({
        min: -12, max: 12, def: 0, bipolar: true,
        size: eqWrap.dataset.ksize ? +eqWrap.dataset.ksize : 58,
        label: b.label, wheelStep: 0.5,
        fmt: function (v) { return (v > 0 ? "+" : "") + (v === 0 ? "0.0" : v.toFixed(1)); },
        get: function () { return state.eq[i]; },
        set: function (v) { state.eq[i] = v; }
      });
      var sw = bandSwitch(i, b);
      k.el.appendChild(sw);
      k.el.classList.toggle("is-bypassed", !!state.eqOff[i]);
      k.el.addEventListener("keydown", function (e) {
        if (e.target !== k.el.querySelector(".rk-knob")) return;
        if (e.key === "b" || e.key === "B") { e.preventDefault(); sw.click(); }
        else if ((e.key === "s" || e.key === "S") && !e.repeat) { e.preventDefault(); sw.listen(); }
      });
      k.el.addEventListener("keyup", function (e) {
        if (e.key === "s" || e.key === "S") sw.release();
      });
      eqWrap.appendChild(k.el);
    });
  }

  /* Under each band: one small latching switch. TAP bypasses the band -
     the knob keeps its value, the band just stops acting, and the column
     dims. HOLD is LISTEN: while the switch is down the EQ output is
     replaced by that band's region, which is how you find what a band is
     actually touching. Keyboard, with the knob focused: B toggles bypass,
     S held is listen. Listen is transient and leaves no history. */
  var HOLD_MS = 260;
  function voiceLive() { if (live) voiceChain(live, ctx); }
  function bandSwitch(i, b) {
    var sw = document.createElement("button");
    sw.type = "button"; sw.className = "eq-band-sw";
    sw.setAttribute("aria-pressed", state.eqOff[i] ? "true" : "false");
    sw.setAttribute("aria-label", "Bypass the " + b.label + " band; hold to listen to it");
    var timer = null, held = false;
    sw.listen = function () { held = true; eqSolo = i; voiceLive(); sw.classList.add("is-listen"); };
    sw.release = function () { if (eqSolo === i) { eqSolo = -1; voiceLive(); } sw.classList.remove("is-listen"); };
    sw.addEventListener("pointerdown", function (e) {
      held = false; timer = setTimeout(sw.listen, HOLD_MS);
      if (sw.setPointerCapture) { try { sw.setPointerCapture(e.pointerId); } catch (err) {} }
    });
    function up() {
      if (timer) { clearTimeout(timer); timer = null; }
      if (held) { sw.release(); held = false; sw.dataset.skipClick = "1"; }
    }
    sw.addEventListener("pointerup", up); sw.addEventListener("pointercancel", up);
    sw.addEventListener("click", function () {
      if (sw.dataset.skipClick) { delete sw.dataset.skipClick; return; }   // a hold is not a tap
      histLabel = (state.eqOff[i] ? "band on: " : "band off: ") + b.label;
      state.eqOff[i] = !state.eqOff[i];
      sw.setAttribute("aria-pressed", state.eqOff[i] ? "true" : "false");
      sw.parentElement.classList.toggle("is-bypassed", state.eqOff[i]);
      applyState();
    });
    return sw;
  }

  function setEqModeButtons() {
    document.querySelectorAll(".rk-eqmode").forEach(function (x) {
      x.classList.toggle("sw-lit", x.dataset.eqmode === (state.eqMode || "stereo"));
    });
  }
  document.querySelectorAll(".rk-eqmode").forEach(function (b) {
    b.addEventListener("click", function () {
      histLabel = "EQ " + b.dataset.eqmode;
      state.eqMode = b.dataset.eqmode;
      setEqModeButtons(); applyState();
    });
  });

  /* The bay row: seven jacks between IN and OUT. Drag one onto another
     to take its place; with the keyboard, arrows move the focused jack;
     on touch (or without dragging), tap a jack to pick it up and tap
     where it should go. Every move is one undoable step. */
  var patchArmed = null;
  function movePatch(from, to) {
    if (from === to || from < 0 || to < 0) return;
    var p = patchOrder().slice();
    var k = p.splice(from, 1)[0];
    p.splice(to, 0, k);
    histLabel = "patch: " + PATCH_LABELS[k] + " to slot " + (to + 1);
    state.patch = p;
    patchArmed = null;
    renderPatch(); applyState();
  }
  function renderPatch() {
    var row = document.getElementById("rk-patch-row");
    if (!row) return;
    row.innerHTML = "";
    var order = patchOrder();
    order.forEach(function (k, i) {
      var li = document.createElement("li");
      var b = document.createElement("button");
      b.type = "button";
      b.className = "rk-jack sw" + (patchArmed === i ? " is-armed" : "");
      b.draggable = true;
      b.dataset.slot = i;
      b.textContent = PATCH_LABELS[k];
      b.setAttribute("aria-label", PATCH_LABELS[k] + ", slot " + (i + 1) + " of " + order.length +
                     ". Arrow keys move it; or press it, then press its new place.");
      b.addEventListener("dragstart", function (e) {
        e.dataTransfer.setData("text/plain", String(i));
        e.dataTransfer.effectAllowed = "move";
        b.classList.add("is-dragging");
      });
      b.addEventListener("dragend", function () { b.classList.remove("is-dragging"); });
      b.addEventListener("dragover", function (e) { e.preventDefault(); b.classList.add("is-over"); });
      b.addEventListener("dragleave", function () { b.classList.remove("is-over"); });
      b.addEventListener("drop", function (e) {
        e.preventDefault();
        b.classList.remove("is-over");
        movePatch(parseInt(e.dataTransfer.getData("text/plain"), 10), i);
      });
      b.addEventListener("keydown", function (e) {
        if (e.key === "ArrowLeft" && i > 0) { e.preventDefault(); movePatch(i, i - 1); focusPatch(i - 1); }
        else if (e.key === "ArrowRight" && i < order.length - 1) { e.preventDefault(); movePatch(i, i + 1); focusPatch(i + 1); }
      });
      b.addEventListener("click", function () {
        if (patchArmed === null) { patchArmed = i; b.classList.add("is-armed"); return; }
        if (patchArmed === i) { patchArmed = null; b.classList.remove("is-armed"); return; }
        movePatch(patchArmed, i);
      });
      li.appendChild(b);
      row.appendChild(li);
    });
    var note = document.getElementById("rk-patch-note");
    if (note) {
      var dflt = order.join(",") === PATCH_KEYS.join(",");
      note.textContent = dflt ? "" : "custom order \u2014 " + order.map(function (k) { return PATCH_LABELS[k]; }).join(" \u203a ");
    }
  }
  function focusPatch(i) {
    var b = document.querySelector('#rk-patch-row [data-slot="' + i + '"]');
    if (b) b.focus();
  }
  var patchReset = document.getElementById("rk-patch-reset");
  if (patchReset) {
    patchReset.addEventListener("click", function () {
      histLabel = "patch: default order";
      state.patch = PATCH_KEYS.slice();
      patchArmed = null;
      renderPatch(); applyState();
    });
  }
  document.getElementById("rk-eq-flat").addEventListener("click", function () {
    histLabel = "EQ flat";
    state.eq = state.eq.map(function () { return 0; });
    renderEq(); applyState();
  });

  var MOD_KNOBS = [
    {kn: "drive",  min: 1, max: 10, def: 2, size: 64, label: "Drive", wheelStep: 0.1,
     fmt: function (v) { return v.toFixed(1); },
     get: function () { return state.tube.drive; }, set: function (v) { state.tube.drive = v; }},
    {kn: "bias",   min: 0, max: 0.6, def: 0.2, size: 64, label: "Bias", wheelStep: 0.02,
     fmt: function (v) { return v.toFixed(2); },
     get: function () { return state.tube.bias; }, set: function (v) { state.tube.bias = v; }},
    {kn: "mix",    min: 0, max: 1, def: 0.3, size: 64, label: "Mix", wheelStep: 0.05,
     fmt: function (v) { return Math.round(v * 100) + "%"; },
     get: function () { return state.tube.mix; }, set: function (v) { state.tube.mix = v; }},
    {kn: "dist",   min: 0, max: 1, def: 0, size: 60, label: "Distance", wheelStep: 0.05,
     fmt: function (v) { return Math.round(v * 100) + "%"; },
     get: function () { return state.cab.dist; }, set: function (v) { state.cab.dist = v; }},
    {kn: "thr",    min: -60, max: 0, def: -24, size: 62, label: "Threshold", wheelStep: 1,
     fmt: function (v) { return Math.round(v) + " dB"; },
     get: function () { return state.comp.thr; }, set: function (v) { state.comp.thr = v; }},
    {kn: "ratio",  min: 1, max: 20, def: 3, size: 62, label: "Ratio", wheelStep: 0.5,
     fmt: function (v) { return v + ":1"; },
     get: function () { return state.comp.ratio; }, set: function (v) { state.comp.ratio = v; }},
    {kn: "att",    min: 0.001, max: 0.3, def: 0.01, size: 62, label: "Attack", wheelStep: 0.005,
     fmt: function (v) { return Math.round(v * 1000) + " ms"; },
     get: function () { return state.comp.att; }, set: function (v) { state.comp.att = v; }},
    {kn: "rel",    min: 0.05, max: 1, def: 0.25, size: 62, label: "Release", wheelStep: 0.05,
     fmt: function (v) { return Math.round(v * 1000) + " ms"; },
     get: function () { return state.comp.rel; }, set: function (v) { state.comp.rel = v; }},
    {kn: "makeup", min: 0, max: 12, def: 0, size: 62, label: "Makeup", wheelStep: 0.5,
     fmt: function (v) { return "+" + v + " dB"; },
     get: function () { return state.comp.makeup; }, set: function (v) { state.comp.makeup = v; }},
    {kn: "sdepth", min: 0, max: 9, def: 0, size: 62, label: "Depth", wheelStep: 0.5,
     fmt: function (v) { return "+" + v.toFixed(1) + " dB"; },
     get: function () { return state.sub.depth; }, set: function (v) { state.sub.depth = v; }},
    {kn: "sgrowl", min: 0, max: 1, def: 0, size: 62, label: "Growl", wheelStep: 0.05,
     fmt: function (v) { return Math.round(v * 100) + "%"; },
     get: function () { return state.sub.growl; }, set: function (v) { state.sub.growl = v; }},
    {kn: "sshake", min: 0, max: 1, def: 0, size: 62, label: "Shake", wheelStep: 0.05,
     fmt: function (v) { return Math.round(v * 100) + "%"; },
     get: function () { return state.sub.shake; }, set: function (v) { state.sub.shake = v; }},
    {kn: "dtime",  min: 0.02, max: 1.2, def: 0.3, size: 60, label: "Time", wheelStep: 0.01,
     fmt: function (v) { return Math.round(v * 1000) + " ms"; },
     get: function () { return state.dly.time; }, set: function (v) { state.dly.time = v; }},
    {kn: "dfb",    min: 0, max: 0.85, def: 0.3, size: 60, label: "Feedback", wheelStep: 0.05,
     fmt: function (v) { return Math.round(v * 100) + "%"; },
     get: function () { return state.dly.fb; }, set: function (v) { state.dly.fb = v; }},
    {kn: "dtone",  min: 500, max: 12000, def: 5000, size: 60, label: "Tone", wheelStep: 250,
     fmt: function (v) { return v >= 1000 ? (v / 1000).toFixed(1) + "k" : Math.round(v); },
     get: function () { return state.dly.tone; }, set: function (v) { state.dly.tone = v; }},
    {kn: "dmix",   min: 0, max: 1, def: 0, size: 60, label: "Mix", wheelStep: 0.05,
     fmt: function (v) { return Math.round(v * 100) + "%"; },
     get: function () { return state.dly.mix; }, set: function (v) { state.dly.mix = v; }},
    {kn: "rsize",  min: 0.3, max: 5, def: 1.6, size: 60, label: "Size", wheelStep: 0.1,
     fmt: function (v) { return v.toFixed(1) + " s"; },
     get: function () { return state.rev.size; }, set: function (v) { state.rev.size = v; }},
    {kn: "rdamp",  min: 1000, max: 12000, def: 5000, size: 60, label: "Damping", wheelStep: 250,
     fmt: function (v) { return (v / 1000).toFixed(1) + "k"; },
     get: function () { return state.rev.damp; }, set: function (v) { state.rev.damp = v; }},
    {kn: "rpre",   min: 0, max: 0.08, def: 0.02, size: 60, label: "Pre-delay", wheelStep: 0.005,
     fmt: function (v) { return Math.round(v * 1000) + " ms"; },
     get: function () { return state.rev.pre; }, set: function (v) { state.rev.pre = v; }},
    {kn: "rmix",   min: 0, max: 1, def: 0, size: 60, label: "Mix", wheelStep: 0.05,
     fmt: function (v) { return Math.round(v * 100) + "%"; },
     get: function () { return state.rev.mix; }, set: function (v) { state.rev.mix = v; }},
    {kn: "out",    min: -24, max: 12, def: 0, size: 68, label: "Gain", bipolar: true, wheelStep: 0.5,
     fmt: function (v) { return (v > 0 ? "+" : "") + v + " dB"; },
     get: function () { return state.out; }, set: function (v) { state.out = v; }}
  ];
  var modKnobRefs = [];
  MOD_KNOBS.forEach(function (spec) {
    var mount = document.querySelector('[data-kn="' + spec.kn + '"]');
    if (!mount) return;
    if (mount.dataset.ksize) spec = Object.assign({}, spec, {size: +mount.dataset.ksize});
    var k = makeKnob(spec);
    mount.appendChild(k.el);
    modKnobRefs.push(k);
  });
  var qMount = document.getElementById("kn-q");
  var qKnob = makeKnob({
    min: 0.4, max: 3, def: 1, label: "Q", wheelStep: 0.1,
    size: qMount.dataset.ksize ? +qMount.dataset.ksize : 44,
    fmt: function (v) { return v.toFixed(1); },
    get: function () { return state.q; }, set: function (v) { state.q = v; }
  });
  qMount.appendChild(qKnob.el);
  modKnobRefs.push(qKnob);

  function syncAll() {
    renderEq();
    modKnobRefs.forEach(function (k) { k.sync(); });
    document.getElementById("rk-cab-on").checked = !!state.cab.on;
    document.getElementById("rk-cab-cab").value = state.cab.cab;
    document.getElementById("rk-cab-mic").value = state.cab.mic;
    document.querySelectorAll("input[name=rk-axis]").forEach(function (el) {
      el.checked = el.value === state.cab.axis;
    });
    syncCabPicks();
    setCenterButtons();
    setEqModeButtons();
    renderKeyButtons();
    renderPatch();
    syncValveUI();
  }

  /* The visible caps follow state, so a preset or an imported rig lights
     the right ones instead of leaving the panel lying about itself. */
  function syncCabPicks() {
    var want = {"rk-cabpick": state.cab.cab, "rk-micpick": state.cab.mic,
                "rk-axispick": state.cab.axis};
    Object.keys(want).forEach(function (name) {
      document.querySelectorAll("input[name=" + name + "]")
        .forEach(function (el) { el.checked = el.value === want[name]; });
    });
  }

  // ---------- transport ----------
  var fileInput = document.getElementById("rk-file");
  var playBtn = document.getElementById("rk-play");
  var abBtn = document.getElementById("rk-ab");
  var exportBtn = document.getElementById("rk-export");
  var statusEl = document.getElementById("rk-status");
  var scopeLamp = document.getElementById("scope-lamp");

  /* The "drop audio" scrim. Guidance, not a gate: it ignores the mouse so
     the knobs underneath stay usable, and it goes away for good once
     something decodes. dragDepth counts enter/leave because they fire for
     every child element the pointer crosses, so a bare boolean flickers. */
  var emptyEl = document.getElementById("rk-empty");
  var dragDepth = 0;

  function hideEmpty() {
    if (emptyEl) { emptyEl.hidden = true; emptyEl.classList.remove("is-over"); }
  }

  function markDrag(on) {
    if (emptyEl && !emptyEl.hidden) emptyEl.classList.toggle("is-over", on);
  }

  function loadFile(file) {
    ensureCtx().resume();
    file.arrayBuffer().then(function (ab) { return ctx.decodeAudioData(ab); })
      .then(function (buf) {
        buffer = buf;
        loadedFile = file;
        loadedName = file.name.replace(/\.[^.]+$/, "");
        hideEmpty();
        showCost();      // now there is a length to estimate for
        document.getElementById("rk-fileinfo").textContent =
          file.name + " — " + buf.duration.toFixed(1) + "s · " +
          buf.numberOfChannels + "ch · " + buf.sampleRate + "Hz";
        playBtn.disabled = abBtn.disabled = exportBtn.disabled = false;
        var rsBtn = document.getElementById("rk-roughsplit");
        if (rsBtn && window.SBRoughSplit) { rsBtn.disabled = false; }
        cnvPlanText(); cnvShowPeak(); tkEnable(); ldnEnable();
        var ssBtn = document.getElementById("rk-studiosplit");
        if (ssBtn) { ssBtn.disabled = false; }
        renderWave();
      })
      .catch(function () { statusEl.textContent = "Couldn't decode that file."; });
  }
  fileInput.addEventListener("change", function () {
    if (fileInput.files[0]) loadFile(fileInput.files[0]);
  });
  document.addEventListener("dragover", function (e) { e.preventDefault(); });
  document.addEventListener("dragenter", function () { dragDepth++; markDrag(true); });
  document.addEventListener("dragleave", function () {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) markDrag(false);
  });
  document.addEventListener("drop", function (e) {
    e.preventDefault();
    dragDepth = 0;
    markDrag(false);
    if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]);
  });

  var stems = [];

  function stemGainValue(st) {
    var anySolo = stems.some(function (s) { return s.solo; });
    if (anySolo) return st.solo ? st.gain : 0;
    return st.mute ? 0 : st.gain;
  }
  function refreshStemGains() {
    stems.forEach(function (st) {
      if (st.playGain) st.playGain.gain.value = stemGainValue(st);
    });
  }

  function stop() {
    if (playing) {
      (Array.isArray(playing) ? playing : [playing]).forEach(function (s) {
        try { s.stop(); } catch (e) {}
      });
      playing = null;
    }
    stems.forEach(function (st) { st.playGain = null; });
    playBtn.textContent = "Play";
    scopeLamp.classList.remove("grn");
  }
  // Playback tracks its position so the waveform scrubber can seek.
  var playT0 = 0, playOffset = 0;

  function duration() {
    if (refMode && refBuffer) return refBuffer.duration;
    if (stems.length) {
      return Math.max.apply(null, stems.map(function (s) { return s.buffer.duration; }));
    }
    return buffer ? buffer.duration : 0;
  }

  function startPlayback(offset) {
    ensureCtx().resume();
    var loop = document.getElementById("rk-loop").checked;
    offset = Math.max(0, Math.min(offset || 0, Math.max(0, duration() - 0.05)));
    if (refMode && refBuffer) {
      // Reference plays completely untouched — straight to the speakers.
      var rsrc = ctx.createBufferSource();
      rsrc.buffer = refBuffer;
      rsrc.loop = loop;
      rsrc.connect(live.dry);
      rsrc.onended = function () { if (playing === rsrc) stop(); };
      live.dry.gain.value = 1; live.wet.gain.value = 0;
      rsrc.start(0, offset);
      playing = rsrc;
      playT0 = ctx.currentTime;
      playOffset = offset;
      playBtn.textContent = "Stop";
      scopeLamp.classList.add("grn");
      return;
    }
    // Leaving ref mode: restore the wet/dry split to the bypass setting.
    if (live) {
      live.wet.gain.value = state.bypass ? 0 : 1;
      live.dry.gain.value = state.bypass ? 1 : 0;
    }
    if (stems.length) {
      var t0 = ctx.currentTime + 0.06;
      var sources = [];
      stems.forEach(function (st) {
        var src = ctx.createBufferSource();
        src.buffer = st.buffer; src.loop = loop;
        var gn = ctx.createGain();
        gn.gain.value = stemGainValue(st);
        st.playGain = gn;
        src.connect(gn); gn.connect(live.wet); gn.connect(live.dry);
        if (state.comp.key && state.comp.key === st.name && live.keyIn) src.connect(live.keyIn);
        src.start(t0, Math.min(offset, Math.max(0, st.buffer.duration - 0.01)));
        sources.push(src);
      });
      sources[0].onended = function () { if (playing === sources) stop(); };
      playing = sources;
      playT0 = t0;
    } else {
      var src = ctx.createBufferSource();
      src.buffer = buffer;
      src.loop = loop;
      src.connect(live.wet); src.connect(live.dry);
      src.onended = function () { if (playing === src) stop(); };
      src.start(0, offset);
      playing = src;
      playT0 = ctx.currentTime;
    }
    playOffset = offset;
    playBtn.textContent = "Stop";
    scopeLamp.classList.add("grn");
  }

  function playPos() {
    if (!playing || !ctx) return 0;
    var d = duration();
    if (!d) return 0;
    var p = playOffset + (ctx.currentTime - playT0);
    return document.getElementById("rk-loop").checked ? p % d : Math.min(p, d);
  }

  function seek(t) {
    if (!buffer && !stems.length) return;
    if (playing) stop();
    startPlayback(t);
  }

  playBtn.addEventListener("click", function () {
    if (playing) { stop(); return; }
    startPlayback(0);
  });
  // Hold either bypass button to hear the raw file for as long as you hold;
  // release snaps back to your processed chain. A quick click still toggles.
  function attachHoldCompare(btn) {
    var holdT = null, held = false, prev = false;
    btn.addEventListener("pointerdown", function () {
      if (btn.disabled) return;
      holdT = setTimeout(function () {
        held = true;
        prev = state.bypass;
        state.bypass = true;
        applyState();
        btn.classList.add("sw-lit");
        abBtn.textContent = "Bypass: HOLDING (raw)";
      }, 300);
    });
    function release() {
      clearTimeout(holdT);
      if (held) {
        state.bypass = prev;
        applyState();
        btn.classList.toggle("sw-lit", state.bypass);
        abBtn.textContent = "Bypass: " + (state.bypass ? "ON (raw)" : "OFF");
      }
    }
    btn.addEventListener("pointerup", release);
    btn.addEventListener("pointercancel", release);
    btn.addEventListener("click", function (e) {
      if (held) { e.stopImmediatePropagation(); e.preventDefault(); held = false; }
    }, true);
  }
  attachHoldCompare(abBtn);

  abBtn.addEventListener("click", function () {
    state.bypass = !state.bypass;
    abBtn.textContent = "Bypass: " + (state.bypass ? "ON (raw)" : "OFF");
    abBtn.classList.toggle("sw-lit", state.bypass);
    applyState();
  });

  // ---------- stem deck UI ----------
  var stemsWrap = document.getElementById("rk-stems");

  function dormantLane(label, hint) {
    var row = document.createElement("div");
    row.className = "lane dim";
    var lamp = document.createElement("span");
    lamp.className = "lamp";
    var name = document.createElement("span");
    name.className = "ln";
    name.textContent = label;
    var rail = document.createElement("span");
    rail.className = "rail";
    var state = document.createElement("span");
    state.className = "ld";
    state.textContent = hint;
    row.appendChild(lamp); row.appendChild(name);
    row.appendChild(rail); row.appendChild(state);
    return row;
  }

  function renderStems() {
    stemsWrap.innerHTML = "";
    if (!stems.length) {
      /* An unloaded deck still shows its four channels - dark lamps,
         empty rails. Real hardware does not hide its lanes. */
      ["VOCALS", "DRUMS", "BASS", "INSTRUMENTS"].forEach(function (nm) {
        stemsWrap.appendChild(dormantLane(nm, "empty"));
      });
      renderKeyButtons();
      return;
    }
    stems.forEach(function (st, i) {
      var row = document.createElement("div");
      row.className = "lane" + (st.mute && !st.solo ? " dim" : "");
      // Jewel lamp: gold = in the mix, green = soloed, dark = muted.
      var lamp = document.createElement("span");
      lamp.className = "lamp" + (st.solo ? " grn" : st.mute ? "" : " on");
      row.appendChild(lamp);
      var name = document.createElement("span");
      name.className = "ln min-w-0 truncate";
      name.textContent = st.name;
      var wave = document.createElement("canvas");
      wave.className = "lane-wave";
      wave.setAttribute("aria-hidden", "true");
      var dur = document.createElement("span");
      dur.className = "ld";
      dur.textContent = st.buffer.duration.toFixed(1) + "s";
      var gain = document.createElement("input");
      gain.type = "range"; gain.min = 0; gain.max = 1.2; gain.step = 0.02;
      gain.value = st.gain;
      gain.className = "fader w-28";
      gain.addEventListener("input", function () {
        st.gain = parseFloat(gain.value); refreshStemGains();
      });
      var mute = document.createElement("button");
      mute.textContent = "M"; mute.title = "Mute";
      mute.className = "sw h-7 w-7 text-[11px] " + (st.mute ? "sw-lit" : "");
      mute.addEventListener("click", function () {
        st.mute = !st.mute; if (st.mute) st.solo = false;
        renderStems(); refreshStemGains();
      });
      var solo = document.createElement("button");
      solo.textContent = "S"; solo.title = "Solo";
      solo.className = "sw h-7 w-7 text-[11px] " + (st.solo ? "sw-lit" : "");
      solo.addEventListener("click", function () {
        st.solo = !st.solo; if (st.solo) st.mute = false;
        renderStems(); refreshStemGains();
      });
      var dl = document.createElement("button");
      dl.textContent = "WAV"; dl.title = "Download this stem as a WAV";
      dl.className = "sw h-7 px-2 text-[10px] text-[#e8c667]";
      dl.addEventListener("click", function () {
        var blob = encodeWav(st.buffer);
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = (loadedName || "stem") + " - " + st.name + ".wav";
        a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
      });
      var rm = document.createElement("button");
      rm.textContent = "×"; rm.title = "Remove stem";
      rm.className = "sw h-7 w-7 text-sm text-gray-300";
      rm.addEventListener("click", function () {
        stop(); stems.splice(i, 1); renderStems(); syncDeckInfo(); renderWave();
      });
      row.appendChild(name); row.appendChild(wave); row.appendChild(dur); row.appendChild(gain);
      row.appendChild(mute); row.appendChild(solo); row.appendChild(dl);
      row.appendChild(rm);
      stemsWrap.appendChild(row);
      paintLaneWave(wave, st);          // after append: the lane has a width now
    });
    renderKeyButtons();
  }

  /* One static picture per lane: the stem's OWN peaks, so a bay of four
     reads as four different instruments rather than four identical bars.
     Peaks are measured once per stem and cached on it; the canvas just
     draws them at whatever width the lane gives it. No playhead here -
     the dock carries the one playhead for the whole mix, and four more
     would mean four more repaints a frame for nothing new. */
  var LANE_COLS = 240;
  function stemPeaks(st) {
    if (st.peaks) return st.peaks;
    var d = st.buffer.getChannelData(0), n = d.length;
    var step = Math.max(1, Math.floor(n / LANE_COLS)), hop = Math.max(1, Math.floor(step / 32));
    var out = new Float32Array(LANE_COLS);
    for (var c = 0; c < LANE_COLS; c++) {
      var pk = 0;
      for (var j = c * step, e = Math.min(n, (c + 1) * step); j < e; j += hop) {
        var v = d[j] < 0 ? -d[j] : d[j];
        if (v > pk) pk = v;
      }
      out[c] = pk;
    }
    st.peaks = out;
    return out;
  }
  function paintLaneWave(cv, st) {
    var dpr = window.devicePixelRatio || 1;
    var w = cv.clientWidth || 140, h = cv.clientHeight || 22;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    var g = cv.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    var pk = stemPeaks(st), mid = h / 2, colW = w / pk.length;
    g.fillStyle = "rgba(201,162,74,0.78)";
    for (var i = 0; i < pk.length; i++) {
      var a = Math.max(0.6, pk[i] * (h * 0.46));
      g.fillRect(i * colW, mid - a, Math.max(0.8, colW - 0.4), a * 2);
    }
  }

  /* KEY: Internal, or any loaded stem by name. The choice is saved with
     the rack; a key that names a stem which is not loaded right now falls
     back to the internal detector and says so. */
  function renderKeyButtons() {
    var wrap = document.getElementById("rk-comp-key");
    if (!wrap) return;
    wrap.innerHTML = "";
    var key = (state.comp && state.comp.key) || "";
    var names = [""].concat(stems.map(function (s) { return s.name; }));
    names.forEach(function (nm) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "rk-key sw" + (nm === key ? " sw-lit" : "");
      b.dataset.key = nm; b.textContent = nm || "Internal";
      b.setAttribute("aria-pressed", nm === key ? "true" : "false");
      b.addEventListener("click", function () {
        histLabel = "key: " + (nm || "internal");
        state.comp.key = nm;
        renderKeyButtons(); applyState();
        if (playing) seek(playPos());                            // re-route the key
      });
      wrap.appendChild(b);
    });
    var note = document.getElementById("rk-comp-key-note");
    if (note) {
      note.textContent = (key && !keyStem()) ? "keyed to " + key + " \u2014 not loaded, using the internal detector" : "";
    }
  }

  function syncDeckInfo() {
    if (stems.length) {
      document.getElementById("rk-fileinfo").textContent =
        stems.length + " stem" + (stems.length > 1 ? "s" : "") +
        " loaded — deck mode: Play mixes them through the rack.";
      playBtn.disabled = abBtn.disabled = exportBtn.disabled = false;
    } else if (buffer) {
      playBtn.disabled = abBtn.disabled = exportBtn.disabled = false;
    } else {
      document.getElementById("rk-fileinfo").textContent =
        "No file loaded — drop a WAV/MP3 anywhere on this page.";
      playBtn.disabled = abBtn.disabled = exportBtn.disabled = true;
    }
  }

  // ---------- Rough Split: classical DSP lanes from the loaded track ----
  // The math lives in roughsplit.js (pure, Node-tested). This handler only
  // moves audio in and out: channel data in, four AudioBuffers into the
  // same stems array the deck already plays. Rough lanes replace previous
  // rough lanes; user-loaded stems are never touched.
  var roughBtn = document.getElementById("rk-roughsplit");
  var roughStatus = document.getElementById("rk-roughsplit-status");
  var roughWrap = document.getElementById("rk-roughsplit-wrap");
  var roughFill = document.getElementById("rk-roughsplit-fill");
  var roughLamp = document.getElementById("rk-roughsplit-lamp");
  var roughRunning = false;

  function roughNote(msg, pct) {
    if (roughWrap) roughWrap.classList.remove("hidden");
    if (roughStatus) roughStatus.textContent = msg;
    if (roughFill && typeof pct === "number") {
      roughFill.style.width = Math.round(pct * 100) + "%";
    }
  }

  if (roughBtn) {
    roughBtn.addEventListener("click", function () {
      if (roughRunning || !buffer || !window.SBRoughSplit) return;
      roughRunning = true;
      roughBtn.disabled = true;
      if (roughLamp) roughLamp.classList.add("on");
      stop();
      ensureCtx();
      var channels = [buffer.getChannelData(0)];
      if (buffer.numberOfChannels > 1) channels.push(buffer.getChannelData(1));
      var mins = buffer.duration / 60;
      roughNote("Splitting… a " + mins.toFixed(1) +
        "-minute track takes about " + Math.max(1, Math.round(mins * 0.6)) +
        " minute" + (mins * 0.6 > 1.5 ? "s" : "") + ".", 0);
      var lastPct = -1;
      window.SBRoughSplit.split(channels, buffer.sampleRate, function (p) {
        var pct = Math.round(p * 100);
        if (pct !== lastPct) {
          lastPct = pct;
          roughNote("Splitting… " + pct + "% — all in this tab, nothing uploads.", p);
        }
      }).then(function (lanes) {
        var order = [["Vocals (rough)", "vocals"], ["Drums (rough)", "drums"],
                     ["Bass (rough)", "bass"], ["Instruments (rough)", "other"]];
        stems = stems.filter(function (st) { return !st.rough; });
        order.forEach(function (pair) {
          var chans = lanes[pair[1]];
          var buf = ctx.createBuffer(chans.length, buffer.length, buffer.sampleRate);
          for (var c = 0; c < chans.length; c++) {
            buf.getChannelData(c).set(chans[c]);
          }
          stems.push({ name: pair[0], buffer: buf, gain: 1,
                       mute: false, solo: false, rough: true });
        });
        roughNote("Done — four rough lanes below. Solo one to audition; " +
          "played together they are your record. Session-prep quality, " +
          "expect bleed.", 1);
        roughRunning = false;
        roughBtn.disabled = false;
        if (roughLamp) roughLamp.classList.remove("on");
        renderStems(); syncDeckInfo(); renderWave();
      }).catch(function () {
        roughNote("Split failed on this file — try a WAV or a shorter bounce.", 0);
        roughRunning = false;
        roughBtn.disabled = false;
        if (roughLamp) roughLamp.classList.remove("on");
      });
    });
  }

  document.getElementById("rk-stems-file").addEventListener("change", function (e) {
    var files = Array.prototype.slice.call(e.target.files || []);
    if (!files.length) return;
    ensureCtx().resume();
    Promise.all(files.map(function (f) {
      return f.arrayBuffer()
        .then(function (ab) { return ctx.decodeAudioData(ab); })
        .then(function (buf) { return {name: f.name, buffer: buf, gain: 1, mute: false, solo: false, playGain: null}; })
        .catch(function () { return null; });
    })).then(function (loaded) {
      var ok = loaded.filter(Boolean);
      stems = stems.concat(ok).slice(0, 8);
      if (loaded.length !== ok.length) statusEl.textContent = "Some files couldn't be decoded.";
      stop(); renderStems(); syncDeckInfo(); renderWave();
    });
    e.target.value = "";
  });

  function setCenterButtons() {
    document.querySelectorAll(".rk-center").forEach(function (x) {
      x.classList.toggle("sw-lit", x.dataset.center === (state.center || "normal"));
    });
  }
  document.querySelectorAll(".rk-center").forEach(function (b) {
    b.addEventListener("click", function () {
      state.center = b.dataset.center;
      setCenterButtons();
      applyState();
    });
  });

  // ---------- per-module power + A/B compare ----------
  // Every data-mod in rack.html needs an entry here: the A/B button reads
  // MOD_KEYS[mod] directly. "vlv" is the valve bank, whose state lives
  // under `valves`.
  var MOD_KEYS = {tube: ["tube"], eq: ["eq", "q", "eqMode", "eqOff"], sub: ["sub"], comp: ["comp"],
                  cab: ["cab"], dly: ["dly"], rev: ["rev"], out: ["out"],
                  vlv: ["valves"]};

  function modSlice(m) {
    var o = {};
    MOD_KEYS[m].forEach(function (k) { o[k] = JSON.parse(JSON.stringify(state[k])); });
    return o;
  }
  var cmpA = {};  // per-module snapshot: the "other side" of A/B
  var cmpSide = {};  // which side each module is showing: "A" (yours) or "B" (stored)
  function syncAbLeds() {
    document.querySelectorAll(".rk-ledwrap").forEach(function (wsp) {
      var side = cmpSide[wsp.dataset.mod] || "A";
      wsp.querySelector(".rk-la").classList.toggle("on", side === "A");
      wsp.querySelector(".rk-lb").classList.toggle("on", side === "B");
    });
  }
  function resetCompare() {
    Object.keys(MOD_KEYS).forEach(function (m) { cmpA[m] = modSlice(m); });
    cmpSide = {};
    document.querySelectorAll(".rk-cmp").forEach(function (b) {
      b.classList.remove("sw-lit");
    });
    syncAbLeds();
  }
  function syncModButtons() {
    document.querySelectorAll(".rk-pwr").forEach(function (b) {
      var on = modOn(b.dataset.mod);
      b.classList.toggle("sw-lit", on);
      b.textContent = on ? "ON" : "OFF";
    });
  }
  document.querySelectorAll(".rk-pwr").forEach(function (b) {
    b.addEventListener("click", function () {
      var m = b.dataset.mod;
      histLabel = m.toUpperCase() + " power";
      if (m === "cab") state.cab.on = !state.cab.on;
      else state.mods[m] = state.mods[m] === false;
      syncAll(); applyState();
    });
  });
  document.querySelectorAll(".rk-cmp").forEach(function (b) {
    b.addEventListener("click", function () {
      var m = b.dataset.mod;
      histLabel = m.toUpperCase() + " A/B";
      var cur = modSlice(m);
      MOD_KEYS[m].forEach(function (k) { state[k] = cmpA[m][k]; });
      cmpA[m] = cur;
      cmpSide[m] = cmpSide[m] === "B" ? "A" : "B";
      b.classList.toggle("sw-lit");
      syncAbLeds();
      syncAll(); applyState();
    });
  });

  document.querySelectorAll(".rk-preset").forEach(function (b) {
    b.addEventListener("click", function () {
      var p = JSON.parse(JSON.stringify(PRESETS[b.dataset.preset]));
      p.bypass = state.bypass;
      p.center = state.center || "normal";
      p.mods = state.mods;
      histLabel = "preset"; state = p; ensureFx(state); syncAll(); applyState();
      resetCompare();
      statusEl.textContent = "Preset loaded.";
    });
  });
  document.getElementById("rk-save").addEventListener("click", function () {
    fetch("/rack/save", {method: "POST", headers: {"Content-Type": "application/json"},
                         body: JSON.stringify(state)})
      .then(function (r) { return r.json(); })
      .then(function (d) { statusEl.textContent = d.ok ? "Rack saved — loads with the page." : "Save failed."; })
      .catch(function () { statusEl.textContent = "Save failed."; });
  });

  /* ---------- the preset library ----------
   * "Save my rack" keeps ONE rack: the one that loads with the page. This
   * keeps many, named, so a vocal chain and a drum bus can both exist.
   *
   * Loading a preset carries over bypass, center and mods from the rack you
   * are sitting in, exactly as the built-in presets do — those describe how
   * you are LISTENING, not what the rack is, and resetting them mid-audition
   * is disorienting.
   */
  (function rackLibrary() {
    var back = document.getElementById("rk-lib-back");
    var openBtn = document.getElementById("rk-lib-btn");
    if (!back || !openBtn) return;

    var listEl = document.getElementById("rk-lib-list");
    var msgEl = document.getElementById("rk-lib-msg");
    var countEl = document.getElementById("rk-lib-count");
    var nameEl = document.getElementById("rk-lib-name");
    var noteEl = document.getElementById("rk-lib-note");
    var presets = [], max = 40, loaded = false, lastFocus = null;

    function say(t) { msgEl.textContent = t || ""; }

    function fmtWhen(iso) {
      var d = new Date(iso);
      return isNaN(d) ? "" : d.toLocaleDateString([], {month: "short", day: "numeric"});
    }

    function render() {
      countEl.textContent = presets.length + " of " + max;
      listEl.textContent = "";
      if (!presets.length) {
        var none = document.createElement("li");
        none.className = "rk-lib-none";
        none.textContent = "Nothing saved yet. Name the rack you have now and it lands here.";
        listEl.appendChild(none);
        return;
      }
      presets.forEach(function (pr) {
        var li = document.createElement("li");
        li.className = "rk-lib-row";

        var box = document.createElement("span");
        box.className = "rk-lib-name";
        var nm = document.createElement("b");
        nm.className = "rk-lib-nm";
        nm.textContent = pr.name;                 // textContent, never innerHTML
        var meta = document.createElement("span");
        meta.className = "rk-lib-meta";
        meta.textContent = (pr.note ? pr.note + " · " : "") + fmtWhen(pr.updated);
        box.appendChild(nm);
        box.appendChild(meta);

        var load = document.createElement("button");
        load.type = "button";
        load.className = "sw px-2.5 py-1 text-[10px] font-medium";
        load.textContent = "Load";
        load.setAttribute("aria-label", "Load " + pr.name);
        load.addEventListener("click", function () { loadPreset(pr); });

        var del = document.createElement("button");
        del.type = "button";
        del.className = "sw px-2 py-1 text-[10px] font-medium";
        del.textContent = "Delete";
        del.setAttribute("aria-label", "Delete " + pr.name);
        del.addEventListener("click", function () { removePreset(pr, del); });

        li.appendChild(box);
        li.appendChild(load);
        li.appendChild(del);
        listEl.appendChild(li);
      });
    }

    function refresh() {
      fetch("/rack/library")
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) { say("Sign in to keep a library of racks."); return; }
          presets = d.presets || [];
          max = d.max || max;
          loaded = true;
          render();
        })
        .catch(function () { say("Offline — the library did not load."); });
    }

    function loadPreset(pr) {
      say("Loading…");
      fetch("/rack/library/" + encodeURIComponent(pr.id))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          var p = d.ok && d.preset ? d.preset.data : null;
          if (!p) { say("That preset would not load."); return; }
          // A rack saved before a band count changed no longer fits the EQ.
          if (!p.eq || p.eq.length !== EQ_BANDS.length) {
            say("That one was saved by an older rack and no longer fits.");
            return;
          }
          p.bypass = state.bypass;
          p.center = state.center || "normal";
          p.mods = state.mods;
          histLabel = "load: " + pr.name;
          state = p;
          ensureFx(state);
          syncAll();
          applyState();
          resetCompare();
          closeLib();
          statusEl.textContent = "Loaded “" + pr.name + "”.";
        })
        .catch(function () { say("Offline — that preset did not load."); });
    }

    function removePreset(pr, btn) {
      // Two-step rather than a confirm(): a modal inside a modal is worse,
      // and this reverts itself if you walk away from it.
      if (btn.dataset.sure !== "1") {
        btn.dataset.sure = "1";
        btn.textContent = "Sure?";
        setTimeout(function () {
          if (btn.dataset.sure === "1") { btn.dataset.sure = ""; btn.textContent = "Delete"; }
        }, 4000);
        return;
      }
      say("Deleting…");
      fetch("/rack/library/" + encodeURIComponent(pr.id) + "/delete", {method: "POST"})
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) { say("That did not delete."); return; }
          presets = d.presets || [];
          render();
          say("Deleted.");
        })
        .catch(function () { say("Offline — nothing was deleted."); });
    }

    document.getElementById("rk-lib-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var nm = (nameEl.value || "").trim();
      if (!nm) return;
      say("Saving…");
      fetch("/rack/library/save", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({name: nm, note: (noteEl.value || "").trim(), data: state})
      })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) { say(d.error || "That did not save."); return; }
          presets = d.presets || presets;
          nameEl.value = ""; noteEl.value = "";
          render();
          say("Saved.");
        })
        .catch(function () { say("Offline — nothing was saved."); });
    });

    function openLib() {
      lastFocus = document.activeElement;
      back.hidden = false;
      openBtn.setAttribute("aria-expanded", "true");
      say("");
      if (!loaded) refresh();
      nameEl.focus();
    }

    function closeLib() {
      back.hidden = true;
      openBtn.setAttribute("aria-expanded", "false");
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    openBtn.addEventListener("click", openLib);
    document.getElementById("rk-lib-x").addEventListener("click", closeLib);
    back.addEventListener("click", function (e) { if (e.target === back) closeLib(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !back.hidden) closeLib();
    });

    render();
  })();

  // ---------- cab & mic selectors ----------
  document.getElementById("rk-cab-on").addEventListener("change", function (e) {
    histLabel = "cab " + (e.target.checked ? "on" : "off"); state.cab.on = e.target.checked; applyState();
  });
  document.getElementById("rk-cab-cab").addEventListener("change", function (e) {
    histLabel = "cab: " + e.target.value; state.cab.cab = e.target.value; applyState();
  });
  document.getElementById("rk-cab-mic").addEventListener("change", function (e) {
    histLabel = "mic: " + e.target.value; state.cab.mic = e.target.value; applyState();
  });
  document.querySelectorAll("input[name=rk-axis]").forEach(function (el) {
    el.addEventListener("change", function () {
      histLabel = "mic axis: " + el.value; state.cab.axis = el.value; applyState();
    });
  });
  /* The selector caps are the control surface; the hidden select stays the
     one canonical value, so presets and rig files have a single place to
     read and write and none of this has to know about the other. */
  [["rk-cabpick", "cab", "rk-cab-cab"],
   ["rk-micpick", "mic", "rk-cab-mic"],
   ["rk-axispick", "axis", null]].forEach(function (spec) {
    document.querySelectorAll("input[name=" + spec[0] + "]")
      .forEach(function (el) {
        el.addEventListener("change", function () {
          if (!el.checked) { return; }
          state.cab[spec[1]] = el.value;
          if (spec[2]) { document.getElementById(spec[2]).value = el.value; }
          document.querySelectorAll("input[name=rk-axis]")
            .forEach(function (a) { a.checked = a.value === state.cab.axis; });
          applyState();
        });
      });
  });

  // ---------- transport dock: waveform scrubber + proxies ----------
  var waveCache = null;

  function renderWave() {
    var wc = document.getElementById("rk-wave");
    if (!wc) return;
    var buf = stems.length
      ? stems.reduce(function (a, s) {
          return s.buffer.duration > a.buffer.duration ? s : a;
        }, stems[0]).buffer
      : buffer;
    var wg = wc.getContext("2d");
    var W = wc.width = wc.clientWidth || 300, H = wc.height = wc.clientHeight || 40;
    wg.clearRect(0, 0, W, H);
    if (!buf) { waveCache = null; return; }
    var d = buf.getChannelData(0), step = Math.max(1, Math.floor(d.length / W));
    var hop = Math.max(1, Math.floor(step / 24));
    wg.strokeStyle = "rgba(216,178,90,0.8)"; wg.lineWidth = 1;
    wg.beginPath();
    for (var x = 0; x < W; x++) {
      var mn = 0, mx = 0;
      for (var j = x * step; j < (x + 1) * step && j < d.length; j += hop) {
        var v = d[j];
        if (v < mn) mn = v; if (v > mx) mx = v;
      }
      wg.moveTo(x + 0.5, H / 2 - mx * H * 0.48);
      wg.lineTo(x + 0.5, H / 2 - mn * H * 0.48 + 0.5);
    }
    wg.stroke();
    waveCache = wg.getImageData(0, 0, W, H);
  }
  var waveEl = document.getElementById("rk-wave");
  if (waveEl) {
    waveEl.addEventListener("click", function (e) {
      var d = duration();
      if (!d) return;
      var r = waveEl.getBoundingClientRect();
      seek((e.clientX - r.left) / r.width * d);
    });
  }
  function mmss(s) {
    s = Math.max(0, Math.floor(s));
    return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2);
  }
  var dockPlay = document.getElementById("rk-play2"),
      dockAb = document.getElementById("rk-ab2"),
      dockExp = document.getElementById("rk-export2");
  if (dockPlay) dockPlay.addEventListener("click", function () { playBtn.click(); });
  if (dockAb) dockAb.addEventListener("click", function () { abBtn.click(); });
  if (dockAb) attachHoldCompare(dockAb);
  if (dockExp) dockExp.addEventListener("click", function () { exportBtn.click(); });

  // ---------- SB-11 snippet finder: real energy scan, honest hooks ----------
  /* Whatever the scan runs on: the loaded track, or failing that the
     longest stem in the deck. The map has to measure the same thing. */
  function hookBuffer() {
    return buffer || (stems.length
      ? stems.reduce(function (a, s) {
          return s.buffer.duration > a.buffer.duration ? s : a;
        }, stems[0]).buffer
      : null);
  }

  function hookDuration() {
    var buf = hookBuffer();
    return buf ? buf.duration : 0;
  }

  function scanHooks(len) {
    var buf = hookBuffer();
    if (!buf || buf.duration <= len + 1) return null;
    var d = buf.getChannelData(0), rate = buf.sampleRate;
    var hop = Math.floor(rate / 4);  // 0.25s frames
    var frames = Math.floor(d.length / hop);
    var rms = new Float32Array(frames);
    for (var f = 0; f < frames; f++) {
      var s = 0, base = f * hop;
      for (var j = 0; j < hop; j += 16) {
        var v = d[base + j];
        s += v * v;
      }
      rms[f] = s;
    }
    var win = Math.round(len * 4), best = 0, run = 0;
    for (f = 0; f < win && f < frames; f++) run += rms[f];
    var bestSum = run;
    for (f = win; f < frames; f++) {
      run += rms[f] - rms[f - win];
      if (run > bestSum) { bestSum = run; best = f - win + 1; }
    }
    return {start: best / 4, len: len};
  }
  /* SB-13's tempo, finally doing something. A hook that starts mid-beat
     reads as a mistake in a Reel no matter how good the audio is, so the
     window is snapped to the nearest downbeat before it is offered.
     Cached because the grid costs an onset-envelope pass and the source
     rarely changes between scans. */
  var hookGrid = null, hookGridFor = null;

  function ensureHookGrid() {
    var buf = hookBuffer();
    if (!buf) { hookGrid = null; hookGridFor = null; return null; }
    if (hookGridFor === buf) { return hookGrid; }
    hookGridFor = buf;
    hookGrid = null;
    if (!window.SBTempoKey) { return null; }
    var chans = [];
    for (var c = 0; c < buf.numberOfChannels; c++) {
      chans.push(buf.getChannelData(c));
    }
    try {
      // Reuse SB-13's reading when the artist has already adopted one -
      // they may have chosen half or double time, and that choice stands.
      var opts = (tkFound && tkFound.bpm) ? {bpm: tkFound.bpm} : {};
      hookGrid = window.SBTempoKey.beatGrid(chans, buf.sampleRate, opts);
    } catch (e) {
      hookGrid = null;
    }
    return hookGrid;
  }

  /* Snap a hook to the grid, but only when doing so is a small move and
     the grid is worth believing. Dragging a window most of a bar to reach
     a downbeat would lose the hook it found. */
  function snapHook(h) {
    var grid = ensureHookGrid();
    if (!grid || grid.confidence < 0.25) {
      return {start: h.start, len: h.len, snapped: false, grid: grid};
    }
    var bar = grid.period * 4;
    var at = window.SBTempoKey.snapToBeat(h.start, grid, 4);
    var moved = at - h.start;
    if (Math.abs(moved) > bar / 2 + 1e-6 || at < 0) {
      return {start: h.start, len: h.len, snapped: false, grid: grid};
    }
    // Never snap past the end of the track.
    var buf = hookBuffer();
    if (buf && at + h.len > buf.duration) {
      at = window.SBTempoKey.snapToBeat(h.start, grid, 4) - bar;
      if (at < 0 || at + h.len > buf.duration) {
        return {start: h.start, len: h.len, snapped: false, grid: grid};
      }
      moved = at - h.start;
    }
    return {start: at, len: h.len, snapped: Math.abs(moved) > 0.001,
            moved: moved, grid: grid};
  }

  var hookPreviewT = null;
  function previewHook(h) {
    seek(h.start);
    clearTimeout(hookPreviewT);
    hookPreviewT = setTimeout(function () { if (playing) stop(); }, h.len * 1000 + 100);
  }
  function exportHookWav(h) {
    if (!buffer && !stems.length) return;
    statusEl.textContent = "Rendering snippet…";
    var rate = stems.length ? stems[0].buffer.sampleRate : buffer.sampleRate;
    var oc = new OfflineAudioContext(2, Math.floor(h.len * rate), rate);
    var chain = buildChain(oc, oc.destination);
    voiceChain(chain, oc);
    if (stems.length) {
      stems.forEach(function (st) {
        var src = oc.createBufferSource();
        src.buffer = st.buffer;
        var gn = oc.createGain();
        gn.gain.value = stemGainValue(st);
        src.connect(gn); gn.connect(chain.input);
        src.start(0, Math.min(h.start, Math.max(0, st.buffer.duration - 0.01)), h.len);
      });
    } else {
      var src = oc.createBufferSource();
      src.buffer = buffer;
      src.connect(chain.input);
      src.start(0, h.start, h.len);
    }
    oc.startRendering().then(function (rendered) {
      var a = document.createElement("a");
      a.download = (loadedName || "hook") + "-" + h.len + "s.wav";
      a.href = URL.createObjectURL(encodeWav(rendered));
      a.click();
      statusEl.textContent = "Snippet WAV downloaded — processed through the rack.";
    }).catch(function () { statusEl.textContent = "Snippet render failed."; });
  }
  function renderHookVideo(h) {
    if (!window.MediaRecorder) {
      statusEl.textContent = "This browser can't record video — use the WAV export.";
      return;
    }
    ensureCtx().resume();
    var vc = document.createElement("canvas");
    vc.width = 720; vc.height = 1280;
    var vg = vc.getContext("2d");
    var dest = ctx.createMediaStreamDestination();
    live.outGain.connect(dest);
    var tracks = vc.captureStream(30).getVideoTracks()
      .concat(dest.stream.getAudioTracks());
    var rec;
    try { rec = new MediaRecorder(new MediaStream(tracks), {mimeType: "video/webm"}); }
    catch (e) { rec = new MediaRecorder(new MediaStream(tracks)); }
    var chunks = [];
    rec.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
    rec.onstop = function () {
      try { live.outGain.disconnect(dest); } catch (e) {}
      var a = document.createElement("a");
      a.download = (loadedName || "hook") + "-" + h.len + "s-vertical.webm";
      a.href = URL.createObjectURL(new Blob(chunks, {type: "video/webm"}));
      a.click();
      statusEl.textContent = "Vertical video downloaded (WebM — phone editors convert to MP4).";
      if (playing) stop();
    };
    var vFreq = new Uint8Array(live.analyser.frequencyBinCount);
    var t0 = performance.now();
    function frame() {
      if (rec.state !== "recording") return;
      vg.fillStyle = "#0a0908"; vg.fillRect(0, 0, 720, 1280);
      live.analyser.getByteFrequencyData(vFreq);
      var bars = 48, cx = 360, cy = 560, R = 200;
      for (var b = 0; b < bars; b++) {
        var bin = Math.floor(Math.pow(b / bars, 1.6) * (vFreq.length * 0.6));
        var e2 = vFreq[bin] / 255;
        var a2 = (b / bars) * Math.PI * 2 - Math.PI / 2;
        vg.strokeStyle = "rgba(216,178,90," + (0.3 + e2 * 0.7).toFixed(2) + ")";
        vg.lineWidth = 7;
        vg.beginPath();
        vg.moveTo(cx + Math.cos(a2) * R, cy + Math.sin(a2) * R);
        vg.lineTo(cx + Math.cos(a2) * (R + 14 + e2 * 130),
                  cy + Math.sin(a2) * (R + 14 + e2 * 130));
        vg.stroke();
      }
      vg.textAlign = "center";
      vg.fillStyle = "#e8c667";
      vg.font = "900 44px Arial";
      vg.fillText((loadedName || "Untitled").slice(0, 24).toUpperCase(), 360, 1080);
      vg.fillStyle = "#8a7c5d";
      vg.font = "700 18px Arial";
      vg.fillText("STREET BANKER · ROYALTY SWEEP", 360, 1118);
      var prog = Math.min(1, (performance.now() - t0) / (h.len * 1000));
      vg.fillStyle = "rgba(255,255,255,0.12)"; vg.fillRect(60, 1180, 600, 6);
      vg.fillStyle = "#e8c667"; vg.fillRect(60, 1180, 600 * prog, 6);
      requestAnimationFrame(frame);
    }
    seek(h.start);
    rec.start();
    statusEl.textContent = "Recording " + h.len + "s vertical video — keep this tab visible…";
    frame();
    setTimeout(function () { if (rec.state === "recording") rec.stop(); }, h.len * 1000 + 200);
  }
  function renderHooksIdle() {
    var wrap0 = document.getElementById("rk-hooks");
    if (!wrap0 || wrap0.children.length) { return; }
    ["BEST 15S HOOK", "BEST 30S HOOK"].forEach(function (nm) {
      wrap0.appendChild(dormantLane(nm, "awaiting scan"));
    });
    paintHookMap([], 0);
  }

  /* SB-11's hook map: the strip is the whole track and each mark sits at
     the window the scan actually chose, so the picture and the buttons
     below it can never disagree. Empty strip until a scan has run. */
  function paintHookMap(hooks, dur) {
    var svg = document.getElementById("rk-hookmap");
    if (!svg) { return; }
    var cap = document.getElementById("rk-hookmap-cap");
    var W = 600;
    svg.innerHTML = "";
    // Film body and the sprocket rows that make it read as a strip.
    svg.appendChild(svgEl("rect", {x: 0, y: 0, width: W, height: 40, rx: 2,
                                   fill: "#0b0a08"}));
    for (var x = 5; x < W - 6; x += 24) {
      [1.5, 33.5].forEach(function (y) {
        svg.appendChild(svgEl("rect", {x: x, y: y, width: 12, height: 5, rx: 1.2,
                                       fill: "#1d1a15"}));
      });
    }
    svg.appendChild(svgEl("rect", {x: 0, y: 9, width: W, height: 22,
                                   fill: "#131110"}));

    if (!dur || !hooks.length) {
      svg.appendChild(svgEl("path", {d: "M0 20h" + W, stroke: "#221f19",
                                     "stroke-width": 1}));
      if (cap) { cap.textContent = "No scan yet"; }
      return;
    }

    /* Bar lines, when there is a grid worth drawing: the marks then sit
       visibly on the music rather than floating over it. Drawn under the
       minute ticks and faint, because they are reference, not data. */
    var grid = hookGrid;
    if (grid && grid.confidence >= 0.25 && grid.period > 0) {
      var bar = grid.period * 4;
      // Thin them out on long tracks so the strip does not turn solid.
      var every = Math.max(1, Math.ceil(dur / bar / 90));
      var bars = window.SBTempoKey.beatsBetween(grid, 0, dur, 4);
      for (var bi = 0; bi < bars.length; bi += every) {
        var bx = (bars[bi] / dur) * W;
        svg.appendChild(svgEl("path", {d: "M" + bx.toFixed(1) + " 9v22",
                                       stroke: "#231f18", "stroke-width": 1}));
      }
    }

    // Minute ticks give the strip a scale to read the marks against.
    for (var t = 60; t < dur; t += 60) {
      var tx = (t / dur) * W;
      svg.appendChild(svgEl("path", {d: "M" + tx.toFixed(1) + " 9v22",
                                     stroke: "#3a3424", "stroke-width": 1}));
    }
    hooks.forEach(function (h, i) {
      var x0 = (h.start / dur) * W;
      var w = Math.max(3, (h.len / dur) * W);
      var y = i === 0 ? 11 : 21;
      svg.appendChild(svgEl("rect", {x: x0.toFixed(1), y: y, width: w.toFixed(1),
                                     height: 8, rx: 1.5, fill: "#c9a24a"}));
      // The label sits after the mark, or before it when a hook lands late
      // enough that there is no room left on the right.
      var text = h.len + "S · " + mmss(h.start);
      var room = W - (x0 + w) > 58;
      var lab = svgEl("text", {
        x: (room ? x0 + w + 5 : x0 - 5).toFixed(1), y: y + 7,
        "text-anchor": room ? "start" : "end",
        fill: "#8a7c5d", "font-size": "9",
        "font-family": "Arial Narrow, Arial, sans-serif",
        "font-weight": "800"});
      lab.textContent = text;
      svg.appendChild(lab);
    });
    if (cap) {
      cap.textContent = hooks.length + " window"
        + (hooks.length === 1 ? "" : "s") + " over " + mmss(dur);
    }
  }

  var hookBtn = document.getElementById("rk-hook-scan");
  var lastHooks = {};
  var lastGrid = null;
  if (hookBtn) hookBtn.addEventListener("click", function () {
    var wrap2 = document.getElementById("rk-hooks");
    wrap2.innerHTML = "";
    var found = [];
    var snapNote = "";
    [15, 30].forEach(function (L) {
      var h = scanHooks(L);
      if (!h) return;
      var snap = snapHook(h);
      if (snap.snapped) {
        h = {start: snap.start, len: h.len};
        snapNote = "Snapped to the beat grid at "
          + snap.grid.bpm.toFixed(1) + " BPM.";
      } else if (snap.grid && snap.grid.confidence >= 0.25) {
        snapNote = "Already on the grid at "
          + snap.grid.bpm.toFixed(1) + " BPM.";
      } else {
        snapNote = "No clear beat to snap to — windows left where the "
          + "energy peaked.";
      }
      found.push(h);
      // Remember where the strongest window starts. Until now this became
      // a DOM row and a download, so nothing outside this tab could ever
      // say where an artist's hook actually is.
      lastHooks[L] = h.start;
      if (snap.grid) {
        lastGrid = {first: snap.grid.firstBeat,
                    bar: snap.grid.period * 4,
                    confidence: snap.grid.confidence};
      }
      var row = document.createElement("div");
      row.className = "lane";
      var lamp2 = document.createElement("span");
      lamp2.className = "lamp on";
      row.appendChild(lamp2);
      var lab2 = document.createElement("span");
      lab2.className = "ln min-w-0 flex-1 truncate";
      lab2.textContent = "Best " + L + "s hook · " + mmss(h.start);
      row.appendChild(lab2);
      [["Preview", function () { previewHook(h); }],
       ["Snippet WAV", function () { exportHookWav(h); }],
       ["Vertical video", function () { renderHookVideo(h); }]].forEach(function (bd) {
        var btn = document.createElement("button");
        btn.className = "sw px-2.5 py-1 text-[10px]";
        btn.textContent = bd[0];
        btn.addEventListener("click", bd[1]);
        row.appendChild(btn);
      });
      wrap2.appendChild(row);
    });
    if (!wrap2.children.length) {
      wrap2.innerHTML = '<p class="note">Load a track longer than ~16 seconds first.</p>';
    }
    paintHookMap(found, hookDuration());
    var note = document.getElementById("rk-hook-note");
    if (note) { note.textContent = snapNote; }
  });

  // ---------- Studio Split: StemSplit quality tier ----------------------
  // Renders only when the server says the key is configured. Uploads the
  // ORIGINAL file (no re-encode), then polls the server proxy; finished
  // stems stream back through the server and drop into the same lanes.
  // The status line says plainly that this one leaves the tab.
  var studioBtn = document.getElementById("rk-studiosplit");
  var studioRunning = false;

  /* How far to split. The modes come from the server, which got them
     from the API itself, so the menu can never offer one the API would
     reject. */
  var studioMode = document.getElementById("rk-studiomode");
  var studioModeNote = document.getElementById("rk-studiomode-note");
  var studioModes = (function () {
    var el = document.getElementById("rk-studiomodes");
    try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; }
  })();

  function showModeNote() {
    if (!studioMode || !studioModeNote) return;
    var m = studioModes.filter(function (x) {
      return x.value === studioMode.value;
    })[0];
    studioModeNote.textContent = m ? m.note : "";
  }
  if (studioMode) {
    studioMode.addEventListener("change", showModeNote);
    showModeNote();
  }

  function studioDone(err) {
    studioRunning = false;
    if (studioBtn) studioBtn.disabled = !loadedFile;
    if (roughLamp) roughLamp.classList.remove("on");
    if (err) roughNote("Studio Split failed: " + err, 0);
  }

  /* What each stem is called on a lane strip. */
  var STEM_LABEL = {
    vocals: "Vocals", drums: "Drums", bass: "Bass", other: "Instruments",
    guitar: "Guitar", piano: "Piano", instrumental: "Instrumental"
  };

  function studioLanes(jobId, wanted) {
    /* `wanted` is the partition the server said this mode produces - the
       set that sums back to the record. It matters that we use it rather
       than everything the API returns: a four-stem job also hands back an
       "instrumental" mix, which is drums+bass+other over again, and
       laying that alongside them would play the record twice. */
    var order = (wanted && wanted.length ? wanted : ["vocals", "drums", "bass", "other"])
      .map(function (name) {
        return [(STEM_LABEL[name] || name) + " (studio)", name];
      });
    if (!order.length) { studioDone("no stems came back"); return; }
    roughNote("Studio Split done — downloading " + order.length + " stem" +
      (order.length > 1 ? "s" : "") + "…", 0.9);
    Promise.all(order.map(function (pair) {
      return fetch("/rack/studio-split/" + jobId + "/stem/" + pair[1])
        .then(function (r) {
          if (!r.ok) { throw new Error(pair[1] + " download failed"); }
          return r.arrayBuffer();
        })
        .then(function (ab) { return ctx.decodeAudioData(ab); })
        .then(function (buf) {
          return { name: pair[0], buffer: buf, gain: 1,
                   mute: false, solo: false, studio: true };
        });
    })).then(function (lanes) {
      stems = stems.filter(function (st) { return !st.studio; });
      lanes.forEach(function (st) { stems.push(st); });
      roughNote("Studio stems on the deck — processed by StemSplit.", 1);
      studioDone();
      renderStems(); syncDeckInfo(); renderWave();
    }).catch(function (e) { studioDone(e.message); });
  }

  function studioPoll(jobId, tries, wanted) {
    if (tries > 200) { studioDone("timed out — retry in a minute"); return; }
    fetch("/rack/studio-split/" + jobId)
      .then(function (r) { return r.json(); })
      .then(function (st) {
        if (st.error) { throw new Error(st.error); }
        if (st.status === "COMPLETED") {
          /* Take the mode's lanes, but only the ones that actually
             arrived - asking for a stem the job never produced would
             fail the whole set. */
          var have = st.stems || [];
          var use = (wanted || []).filter(function (n) {
            return !have.length || have.indexOf(n) !== -1;
          });
          studioLanes(jobId, use.length ? use : wanted);
          return;
        }
        if (st.status === "FAILED" || st.status === "EXPIRED") {
          throw new Error("StemSplit reported " + st.status);
        }
        var p = Math.max(0.05, Math.min(0.85, (st.progress || 0) / 100));
        roughNote("Studio Split running at StemSplit… " +
          Math.round(p * 100) + "%", p);
        setTimeout(function () { studioPoll(jobId, tries + 1); }, 4000);
      })
      .catch(function (e) { studioDone(e.message); });
  }

  if (studioBtn) {
    studioBtn.addEventListener("click", function () {
      if (studioRunning || roughRunning || !loadedFile) return;
      studioRunning = true;
      studioBtn.disabled = true;
      if (roughLamp) roughLamp.classList.add("on");
      ensureCtx();
      roughNote("Uploading to StemSplit for separation — this track " +
        "leaves this tab for processing.", 0.02);
      var fd = new FormData();
      fd.append("audio", loadedFile, loadedFile.name);
      if (studioMode) { fd.append("mode", studioMode.value); }
      fetch("/rack/studio-split", { method: "POST", body: fd })
        .then(function (r) {
          return r.json().then(function (j) {
            if (!r.ok) { throw new Error(j.error || ("HTTP " + r.status)); }
            return j;
          });
        })
        // The server answers with the lanes this mode yields, so the deck
        // never keeps its own idea of which stems belong together.
        .then(function (j) { studioPoll(j.job, 0, j.stems); })
        .catch(function (e) { studioDone(e.message); });
    });
  }


  /* ---------- Explain mode -------------------------------------------
     Forty-eight controls on this page carry a title attribute holding
     the only description of what they do. Hover does not exist on a
     touch screen, so on a phone that text was unreachable - and it is
     not decoration, it is sentences like "this one uploads the track for
     processing".

     One switch prints them on the panel. The captions are built from the
     title attributes themselves rather than a hand-written list, so a
     control added tomorrow is covered without anyone remembering this
     exists. The titles stay in place, so a mouse still gets its tooltip.
  */
  var explainBtn = document.getElementById("rk-explain");
  var explainOn = false;

  function explainTargets() {
    var root = document.querySelector("main") || document.body;
    return Array.prototype.filter.call(
      root.querySelectorAll("[title]"),
      function (el) {
        // Skip anything already carrying its own visible caption, and
        // the toggle itself.
        return el.id !== "rk-explain"
          && (el.getAttribute("title") || "").trim().length > 12
          && !el.querySelector(".rk-explain-note");
      });
  }

  function setExplain(on) {
    explainOn = on;
    if (explainBtn) {
      explainBtn.classList.toggle("sw-lit", on);
      explainBtn.setAttribute("aria-pressed", on ? "true" : "false");
    }
    document.querySelectorAll(".ru-explain").forEach(function (c) { c.hidden = !on; });
    Array.prototype.forEach.call(
      document.querySelectorAll(".rk-explain-note"),
      function (n) { n.remove(); });
    if (!on) { return; }
    explainTargets().forEach(function (el) {
      var note = document.createElement("span");
      note.className = "rk-explain-note";
      // textContent, never innerHTML - these strings come from the
      // template but the habit is what keeps it safe when one day they
      // do not.
      note.textContent = el.getAttribute("title");
      // Sit the caption after the control rather than inside it, so a
      // button's own layout and hit area are untouched.
      var host = el.parentNode;
      if (host) { host.insertBefore(note, el.nextSibling); }
    });
  }

  if (explainBtn) {
    explainBtn.addEventListener("click", function () { setExplain(!explainOn); });
  }

  /* Boot: the deck and the scanner show their hardware before any file
     arrives - dormant lanes, not blank wells. */
  renderStems();
  renderHooksIdle();

  // ---------- Rack -> Smart Link handoff ----------
  var rolloutBtn = document.getElementById("rk-rollout");
  if (rolloutBtn) rolloutBtn.addEventListener("click", function () {
    var facts = [];
    var d = duration();
    if (d) facts.push(mmss(d));
    var pk = document.getElementById("rk-peakdb").textContent;
    if (pk && pk !== "−∞") facts.push("peak " + pk);
    if (stems.length) facts.push(stems.length + " stems");
    window.location = "/links/new?title=" + encodeURIComponent(loadedName || "") +
      "&rack=" + encodeURIComponent("bounced through The Rack" +
        (facts.length ? " — " + facts.join(" · ") : ""));
  });

  // ---------- reference track: A/B against a commercial mix ----------
  var refFileInput = document.getElementById("rk-ref-file");
  var refBtn = document.getElementById("rk-ref");
  if (refFileInput) refFileInput.addEventListener("change", function () {
    var f = refFileInput.files[0];
    if (!f) return;
    ensureCtx().resume();
    f.arrayBuffer().then(function (ab) { return ctx.decodeAudioData(ab); })
      .then(function (buf) {
        refBuffer = buf;
        refSpec = null;
        refBtn.disabled = false;
        refBtn.textContent = "REF: " + f.name.replace(/\.[^.]+$/, "").slice(0, 14);
        statusEl.textContent = "Reference loaded — toggle REF to A/B against it.";
      })
      .catch(function () { statusEl.textContent = "Couldn't decode the reference."; });
  });
  if (refBtn) refBtn.addEventListener("click", function () {
    if (!refBuffer) return;
    var wasPlaying = !!playing;
    var pos = playPos();
    if (playing) stop();
    refMode = !refMode;
    refBtn.classList.toggle("sw-lit", refMode);
    if (wasPlaying) startPlayback(Math.min(pos, Math.max(0, duration() - 0.1)));
  });

  // ---------- rig export / import (shareable JSON) ----------
  var rigExp = document.getElementById("rk-rig-export");
  var rigImp = document.getElementById("rk-rig-import");
  if (rigExp) rigExp.addEventListener("click", function () {
    var rig = JSON.parse(JSON.stringify(state));
    delete rig.bypass;
    var a = document.createElement("a");
    a.download = "streetbanker-rig.json";
    a.href = URL.createObjectURL(new Blob([JSON.stringify(rig, null, 2)],
                                          {type: "application/json"}));
    a.click();
    statusEl.textContent = "Rig exported — send the file to a collaborator.";
  });
  if (rigImp) rigImp.addEventListener("change", function () {
    var f = rigImp.files[0];
    if (!f) return;
    f.text().then(function (txt) {
      var rig = JSON.parse(txt);
      if (!rig || !Array.isArray(rig.eq) || rig.eq.length !== EQ_BANDS.length) {
        statusEl.textContent = "That file isn't a Street Banker rig.";
        return;
      }
      rig.bypass = state.bypass;
      state = rig;
      ensureFx(state);
      if (!state.mods) state.mods = {};
      syncAll(); applyState(); resetCompare();
      statusEl.textContent = "Rig loaded.";
    }).catch(function () { statusEl.textContent = "Couldn't read that rig file."; });
    rigImp.value = "";
  });

  // ---------- signal-flow strip: click a node, jump to the module ----------
  document.querySelectorAll(".flow-node").forEach(function (node) {
    node.addEventListener("click", function () {
      var target = document.querySelector(node.dataset.target);
      if (!target) return;
      target.scrollIntoView({behavior: "smooth", block: "center"});
      target.classList.add("flow-flash");
      setTimeout(function () { target.classList.remove("flow-flash"); }, 1600);
    });
  });

  // ---------- focus mode: hide the app sidebar while dialing in ----------
  var focusBtn = document.getElementById("rk-focus");
  var sideEl = document.querySelector("aside");
  function setFocus(onF) {
    if (sideEl) sideEl.style.display = onF ? "none" : "";
    if (focusBtn) {
      focusBtn.classList.toggle("sw-lit", onF);
      focusBtn.textContent = onF ? "Exit focus" : "Focus mode";
    }
    try { localStorage.setItem("rkFocus", onF ? "1" : ""); } catch (e) {}
  }
  if (focusBtn) {
    focusBtn.addEventListener("click", function () {
      setFocus(!(sideEl && sideEl.style.display === "none"));
    });
    try { if (localStorage.getItem("rkFocus")) setFocus(true); } catch (e) {}
  }

  // ---------- scope ----------
  var canvas = document.getElementById("rk-scope");
  var g = canvas.getContext("2d");
  var eqCurveDirty = true, eqCurve = null, cabCurve = null;
  var FMIN = 20, FMAX = 20000;
  // Screen mode: the canvas lives inside the photo chassis window — it tracks
  // its slot height, drops the label gutter, and draws slim unlabeled lanes
  // (the lane legend renders in HTML under the chassis instead).
  var SCREEN = canvas.hasAttribute("data-screen");
  var GUT = SCREEN ? 14 : 108;
  var selLane = -1, laneHitRects = [];
  var zeroCache = 0, spanCache = 1, nodeDrag = -1, nodeMoved = false;
  canvas.style.touchAction = "none";
  var vuPos = 0;
  function fx(f, w) {
    return GUT + Math.log(f / FMIN) / Math.log(FMAX / FMIN) * (w - GUT - 10);
  }

  function responseOf(filters) {
    var n = 200, freqs = new Float32Array(n),
        mag = new Float32Array(n), ph = new Float32Array(n),
        total = new Float32Array(n).fill(0);
    for (var i = 0; i < n; i++) freqs[i] = FMIN * Math.pow(FMAX / FMIN, i / (n - 1));
    filters.forEach(function (f) {
      f.getFrequencyResponse(freqs, mag, ph);
      for (var i = 0; i < n; i++) total[i] += 20 * Math.log10(mag[i] || 1e-6);
    });
    return {freqs: freqs, db: total};
  }

  function laneBar(x1, y, x2, h, style) {
    g.fillStyle = style;
    if (g.roundRect) {
      g.beginPath(); g.roundRect(x1, y, Math.max(2, x2 - x1), h, 4); g.fill();
    } else {
      g.fillRect(x1, y, Math.max(2, x2 - x1), h);
    }
  }

  var freqData = null, timeData = null;
  /* The faceplate prints 0, 3, 6, 10 and 20 at roughly even spacings, so
     the scale is compressed at the top like a real GR meter. Sweeping the
     needle linearly across it makes it point at the wrong number - 3 dB of
     reduction would sit where the scale says about 1.5 - so interpolate
     through the same anchors the labels are drawn at. Angles measured from
     vertical about the pivot at (100, 100). */
  var VU_SCALE = [[0, -52], [3, -28.5], [6, 0], [10, 28.5], [20, 53]];

  function vuAngle(db) {
    if (!(db > 0)) { return VU_SCALE[0][1]; }
    for (var i = 1; i < VU_SCALE.length; i++) {
      if (db <= VU_SCALE[i][0]) {
        var a = VU_SCALE[i - 1], b = VU_SCALE[i];
        return a[1] + (b[1] - a[1]) * (db - a[0]) / (b[0] - a[0]);
      }
    }
    return VU_SCALE[VU_SCALE.length - 1][1];
  }

  function draw() {
    requestAnimationFrame(draw);
    paintValves();
    paintMeters();
    var w = canvas.clientWidth;
    if (canvas.width !== w) canvas.width = w;
    if (SCREEN) {
      var chh = canvas.clientHeight;
      if (chh && canvas.height !== chh) canvas.height = chh;
    }
    var h = canvas.height;
    // In screen mode the lane block adapts to the window height; labels
    // draw in-canvas whenever the lanes are tall enough to carry them.
    var laneH = SCREEN
      ? Math.max(7, Math.min(15, Math.floor(h * 0.52 / LANES.length)))
      : 15;
    var laneLabels = !SCREEN || laneH >= 10;
    GUT = SCREEN ? (laneLabels ? 84 : 14) : 108;
    var lanesTop = h - LANES.length * laneH - (SCREEN ? 6 : 10);
    g.clearRect(0, 0, w, h);

    var binHz = ctx ? ctx.sampleRate / (live.analyser.fftSize) : 0;
    if (live && playing) {
      if (!freqData) { freqData = new Uint8Array(live.analyser.frequencyBinCount);
                       timeData = new Uint8Array(live.analyser.fftSize); }
      live.analyser.getByteFrequencyData(freqData);
      live.analyser.getByteTimeDomainData(timeData);
    }

    g.font = "9px Arial";
    [50, 100, 250, 500, 1000, 2500, 6000, 12000].forEach(function (f) {
      var x = fx(f, w);
      g.fillStyle = "rgba(150,140,120,0.14)";
      g.fillRect(x, 22, 1, h - 30);
      g.fillStyle = "rgba(150,140,120,0.6)";
      g.fillText(f >= 1000 ? (f / 1000) + "k" : f, x + 3, 16);
    });

    if (freqData && playing && refMode) {
      // Accumulate the reference's spectral ceiling while it plays.
      if (!refSpec) refSpec = new Float32Array(freqData.length);
      for (var rb = 0; rb < freqData.length; rb++) {
        if (freqData[rb] > refSpec[rb]) refSpec[rb] = freqData[rb];
      }
    }
    if (refSpec && binHz) {
      // Reference trace: dashed cyan ceiling accumulated from the ref track.
      g.beginPath();
      for (var rpx = GUT; rpx <= w - 10; rpx += 3) {
        var rf = FMIN * Math.pow(FMAX / FMIN, (rpx - GUT) / (w - GUT - 10));
        var rbin = Math.min(refSpec.length - 1, Math.round(rf / binHz));
        var rv = refSpec[rbin] / 255;
        var ry = lanesTop - 8 - rv * (lanesTop - 34);
        rpx === GUT ? g.moveTo(rpx, ry) : g.lineTo(rpx, ry);
      }
      g.setLineDash([3, 3]);
      g.strokeStyle = "rgba(103,232,249,0.55)"; g.lineWidth = 1; g.stroke();
      g.setLineDash([]);
    }
    if (freqData && playing) {
      g.beginPath();
      for (var px = GUT; px <= w - 10; px += 2) {
        var f = FMIN * Math.pow(FMAX / FMIN, (px - GUT) / (w - GUT - 10));
        var bin = Math.min(freqData.length - 1, Math.round(f / binHz));
        var v = freqData[bin] / 255;
        var y = lanesTop - 8 - v * (lanesTop - 34);
        px === GUT ? g.moveTo(px, y) : g.lineTo(px, y);
      }
      g.strokeStyle = "rgba(232,198,103,0.85)"; g.lineWidth = 1.4; g.stroke();
      g.lineTo(w - 10, lanesTop - 8); g.lineTo(GUT, lanesTop - 8); g.closePath();
      var grad = g.createLinearGradient(0, 22, 0, lanesTop - 8);
      grad.addColorStop(0, "rgba(232,198,103,0.42)");
      grad.addColorStop(1, "rgba(232,198,103,0.04)");
      g.fillStyle = grad; g.fill();
    }

    if (eqCurveDirty && live) {
      eqCurve = responseOf(live.filters);
      var cc = state.cab;
      cabCurve = (cc.on && cc.cab !== "direct")
        ? responseOf(live.cabMic.cabFilters) : null;
      eqCurveDirty = false;
    }
    var zero = (lanesTop - 8) * 0.55, span = (lanesTop - 8) * 0.35 / 12;
    if (cabCurve) {
      g.beginPath();
      for (var ci = 0; ci < cabCurve.freqs.length; ci++) {
        var cxp = fx(cabCurve.freqs[ci], w);
        var cyp = zero - Math.max(-14, Math.min(14, cabCurve.db[ci])) * span;
        ci === 0 ? g.moveTo(cxp, cyp) : g.lineTo(cxp, cyp);
      }
      g.setLineDash([5, 4]);
      g.strokeStyle = "rgba(216,178,90,0.8)"; g.lineWidth = 1.2; g.stroke();
      g.setLineDash([]);
    }
    if (eqCurve) {
      g.beginPath();
      for (var i = 0; i < eqCurve.freqs.length; i++) {
        var x = fx(eqCurve.freqs[i], w);
        var y = zero - eqCurve.db[i] * span;
        i === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
      }
      g.strokeStyle = "#f3ead2"; g.lineWidth = 1.5; g.stroke();
      g.strokeStyle = "rgba(255,255,255,0.1)"; g.lineWidth = 1;
      g.beginPath(); g.moveTo(GUT, zero); g.lineTo(w - 10, zero); g.stroke();
      // Draggable band nodes riding the curve: grab one and pull.
      zeroCache = zero; spanCache = span;
      EQ_BANDS.forEach(function (b, ni) {
        var nx = fx(b.f, w), ny = zero - state.eq[ni] * span;
        g.beginPath();
        g.arc(nx, ny, ni === nodeDrag ? 6 : 4.5, 0, 6.2832);
        g.fillStyle = ni === nodeDrag ? "#f3ead2" : "rgba(232,198,103,0.92)";
        g.fill();
        g.strokeStyle = "#1c1302"; g.lineWidth = 1.2; g.stroke();
      });
    }

    g.strokeStyle = "rgba(201,162,74,0.25)";
    g.beginPath(); g.moveTo(0, lanesTop - 2); g.lineTo(w, lanesTop - 2); g.stroke();

    LANES.forEach(function (lane, li) {
      var y = lanesTop + 4 + li * laneH;
      var x1 = fx(lane.lo, w), x2 = fx(lane.hi, w);
      var energy = 0;
      if (freqData && playing && binHz) {
        var b1 = Math.max(0, Math.floor(lane.lo / binHz));
        var b2 = Math.min(freqData.length - 1, Math.ceil(lane.hi / binHz));
        var sum = 0;
        for (var b = b1; b <= b2; b++) sum += freqData[b];
        energy = (sum / (b2 - b1 + 1)) / 255;
      }
      laneHitRects[li] = [y, laneH];
      if (laneLabels) {
        g.fillStyle = li === selLane ? "#e8c667"
          : energy > 0.04 ? lane.color : "rgba(160,150,130,0.55)";
        g.font = (SCREEN ? "bold 8px" : "bold 9px") + " Arial";
        g.textAlign = "right";
        g.fillText(lane.label.toUpperCase(), GUT - 10, y + laneH - (SCREEN ? 3 : 6));
        g.textAlign = "left";
      }
      var bo = SCREEN ? 1 : 2, bh = laneH - (SCREEN ? 3 : 6);
      laneBar(x1, y + bo, x2, bh, lane.color + "26");
      if (energy > 0.04) {
        var alpha = Math.round(Math.min(1, energy * 1.6) * 200 + 55)
          .toString(16).padStart(2, "0");
        laneBar(x1, y + bo, x1 + (x2 - x1) * Math.min(1, energy * 1.3), bh,
                lane.color + alpha);
      }
      if (li === selLane) {
        g.fillStyle = "rgba(232,198,103,0.09)";
        g.fillRect(2, y - 1, w - 4, laneH + 2);
        g.strokeStyle = "#e8c667"; g.lineWidth = 1.4;
        g.strokeRect(x1 - 2, y + bo - 2, (x2 - x1) + 4, bh + 4);
      }
    });

    // VU needle: fast attack, slow release, like the real thing.
    var gr = live ? (live.duckKeyed ? keyGR : (live.comp.reduction || 0)) : 0;
    var target = (live && playing) ? Math.min(20, -gr) : 0;
    vuPos += (target - vuPos) * (target > vuPos ? 0.45 : 0.07);
    var needle = document.getElementById("rk-vu-needle");
    if (needle) {
      needle.setAttribute("transform",
        "rotate(" + vuAngle(vuPos).toFixed(1) + " 100 100)");
      var grEl = document.getElementById("rk-grdb");
      /* A needle parked at zero because the compressor is set to 1:1 looks
         exactly like a broken meter, so say which it is. The scale only
         means anything when something is actually being reduced. */
      if (!modOn("comp")) {
        grEl.textContent = "COMP OFF";
      } else if (state.comp.ratio <= 1.02) {
        grEl.textContent = "COMP AT 1:1";
      } else {
        grEl.textContent = vuPos.toFixed(1) + " dB";
      }
    }
    // Compressor-side gain reduction bar (same real reduction value)
    var grBar = document.getElementById("rk-gr");
    if (grBar) {
      grBar.style.width = Math.min(100, vuPos / 20 * 100) + "%";
      document.getElementById("rk-grdb2").textContent =
        vuPos > 0.05 ? "−" + vuPos.toFixed(1) + " dB" : "0.0 dB";
    }
    // Transport dock: mirror state, playhead, clock
    if (dockPlay) {
      dockPlay.textContent = playing ? "Stop" : "Play";
      dockPlay.disabled = playBtn.disabled;
      dockAb.textContent = abBtn.textContent;
      dockAb.disabled = abBtn.disabled;
      dockAb.classList.toggle("sw-lit", state.bypass);
      dockExp.disabled = exportBtn.disabled;
      if (rolloutBtn) rolloutBtn.disabled = playBtn.disabled;
      var vb = document.getElementById("rk-vault");
      if (vb && !vb.dataset.busy) vb.disabled = playBtn.disabled;
      var wc2 = document.getElementById("rk-wave");
      if (wc2 && waveCache) {
        var wg2 = wc2.getContext("2d");
        wg2.putImageData(waveCache, 0, 0);
        var dtot = duration();
        if (dtot) {
          var phx = playPos() / dtot * wc2.width;
          wg2.fillStyle = "#e8c667";
          wg2.fillRect(phx - 1, 0, 2, wc2.height);
        }
      }
      var timeEl = document.getElementById("rk-time");
      if (timeEl) {
        var dtt = duration();
        timeEl.textContent = mmss(playPos()) + " / " + mmss(dtt);
      }
      var pk2 = document.getElementById("rk-peak2");
      if (pk2) pk2.style.width = document.getElementById("rk-peak").style.width;
    }
    if (live && playing && timeData) {
      var peak = 0;
      for (var t = 0; t < timeData.length; t += 4) {
        peak = Math.max(peak, Math.abs(timeData[t] - 128) / 128);
      }
      document.getElementById("rk-peak").style.width = Math.min(100, peak * 100) + "%";
      document.getElementById("rk-peakdb").textContent =
        peak > 0.001 ? (20 * Math.log10(peak)).toFixed(1) + " dB" : "−∞";
    }
  }

  // ---------- WAV export ----------
  function encodeWav(rendered) {
    var ch = rendered.numberOfChannels, len = rendered.length, rate = rendered.sampleRate;
    var bytes = 44 + len * ch * 2;
    var ab = new ArrayBuffer(bytes), dv = new DataView(ab);
    function str(o, s) { for (var i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); }
    str(0, "RIFF"); dv.setUint32(4, bytes - 8, true); str(8, "WAVE");
    str(12, "fmt "); dv.setUint32(16, 16, true); dv.setUint16(20, 1, true);
    dv.setUint16(22, ch, true); dv.setUint32(24, rate, true);
    dv.setUint32(28, rate * ch * 2, true); dv.setUint16(32, ch * 2, true);
    dv.setUint16(34, 16, true); str(36, "data"); dv.setUint32(40, len * ch * 2, true);
    var offset = 44;
    var chans = [];
    for (var c = 0; c < ch; c++) chans.push(rendered.getChannelData(c));
    for (var i = 0; i < len; i++) {
      for (var c2 = 0; c2 < ch; c2++) {
        var v = Math.max(-1, Math.min(1, chans[c2][i]));
        dv.setInt16(offset, v < 0 ? v * 32768 : v * 32767, true);
        offset += 2;
      }
    }
    return new Blob([ab], {type: "audio/wav"});
  }

  /* One offline render path shared by the WAV export, the Vault archive
     and the Format Bench. Split in two so the Bench can reach the raw
     AudioBuffer instead of a WAV blob it would have to decode again. */
  /* How long a bounce will take.
   *
   * This began as a DSP load meter and the measurements killed that idea.
   * Web Audio exposes no CPU reading, so the only honest number is a timed
   * render — and a timed render of THIS rack turns out not to vary with
   * how the rack is set. Measured, idle, six alternating samples at a
   * three-second render: a 0.3s reverb tail cost 205 ms per second of
   * audio and a 3.0s tail cost 180 ms. The larger one was faster. The
   * spread within each setting was bigger than the gap between them.
   *
   * So the graph's cost is essentially fixed, and what is really being
   * measured is how quickly this machine renders it. That is worth
   * exactly one thing, and it is a thing people actually ask: how long
   * will exporting take. So that is what it says.
   *
   * Measured once, at load. There is nothing to re-measure on a knob
   * turn, and re-rendering on every change was burning real CPU to
   * report a number that never moved.
   */
  var COST_SECONDS = 1.0, COST_RATE = 44100;
  var costBusy = false, costNoiseBuf = null, costFactor = 0;

  function costSource(oc, len) {
    // Noise, not silence. A chain fed zeros does not exercise the
    // waveshaper curve or make the compressor work, so silence would
    // time a rack that is not the one being listened to.
    if (!costNoiseBuf || costNoiseBuf.length !== len) {
      costNoiseBuf = oc.createBuffer(1, len, COST_RATE);
      var d = costNoiseBuf.getChannelData(0), seed = 12345;
      for (var i = 0; i < len; i++) {
        seed = (seed * 1103515245 + 12345) & 0x7fffffff;   // deterministic
        d[i] = ((seed / 0x7fffffff) * 2 - 1) * 0.5;
      }
    }
    var src = oc.createBufferSource();
    src.buffer = costNoiseBuf;
    return src;
  }

  function measureCost() {
    var el = document.getElementById("rk-cost");
    if (!el || costBusy || typeof OfflineAudioContext === "undefined") return;
    costBusy = true;
    var len = Math.floor(COST_RATE * COST_SECONDS), oc;
    try { oc = new OfflineAudioContext(2, len, COST_RATE); }
    catch (e) { costBusy = false; return; }
    var chain = buildChain(oc, oc.destination);
    voiceChain(chain, oc);          // the same voicing the export uses
    var src = costSource(oc, len);
    src.connect(chain.input);
    src.start();
    var t0 = performance.now();
    oc.startRendering().then(function () {
      var ms = performance.now() - t0;
      costFactor = (COST_SECONDS * 1000) / Math.max(0.01, ms);
      showCost();
      costBusy = false;
    }).catch(function () { costBusy = false; });
  }

  function fmtDur(sec) {
    if (sec < 90) return Math.max(1, Math.round(sec)) + "s";
    return Math.round(sec / 60) + " min";
  }

  /* With a track loaded this answers for THAT track. Without one there is
     no length to answer for, so it falls back to the rate it measured. */
  function showCost() {
    var el = document.getElementById("rk-cost");
    if (!el || !costFactor) return;
    var dur = buffer ? buffer.duration : 0;
    if (stems.length) {
      dur = Math.max.apply(null, stems.map(function (s) { return s.buffer.duration; }));
    }
    if (dur) {
      el.textContent = "export ~" + fmtDur(dur / costFactor);
      el.title = "Rendering this rack measured " + costFactor.toFixed(1) +
                 "x realtime when the page loaded, so " + fmtDur(dur) +
                 " of audio should bounce in about " + fmtDur(dur / costFactor) + ".\n" +
                 "A timed render, not a CPU reading — the browser does not report one.";
    } else {
      el.textContent = "x" + (costFactor >= 10 ? Math.round(costFactor) : costFactor.toFixed(1)) +
                       " realtime";
      el.title = "This rack renders " + costFactor.toFixed(1) + "x faster than realtime on " +
                 "this machine, so a three-minute track would export in about " +
                 fmtDur(180 / costFactor) + ".\n" +
                 "Load a track and this becomes an estimate for that track.\n" +
                 "A timed render, not a CPU reading — the browser does not report one.";
    }
    // Below realtime the export takes longer than the song, and live
    // playback is at risk of falling behind on this machine.
    el.classList.toggle("is-heavy", costFactor < 1);
  }

  function renderMaster() {
    return renderMasterBuffer().then(encodeWav);
  }

  function renderMasterBuffer() {
    var rate = stems.length ? stems[0].buffer.sampleRate : buffer.sampleRate;
    var len = stems.length
      ? Math.max.apply(null, stems.map(function (s) { return s.buffer.length; }))
      : buffer.length;
    var oc = new OfflineAudioContext(2, len, rate);
    return loadDucker(oc).then(function (ok) {
      var chain = buildChain(oc, oc.destination);
      if (ok) armDucker(chain, oc);
      voiceChain(chain, oc);  // renders honor module power exactly like live
      if (stems.length) {
        stems.forEach(function (st) {
          var src = oc.createBufferSource();
          src.buffer = st.buffer;
          var gn = oc.createGain();
          gn.gain.value = stemGainValue(st);
          src.connect(gn); gn.connect(chain.input);
          if (state.comp.key && state.comp.key === st.name) src.connect(chain.keyIn);
          src.start();
        });
      } else {
        var src = oc.createBufferSource();
        src.buffer = buffer;
        src.connect(chain.input);
        src.start();
      }
      return oc.startRendering();
    });
  }

  exportBtn.addEventListener("click", function () {
    if (!buffer && !stems.length) return;
    statusEl.textContent = "Rendering…";
    renderMaster().then(function (blob) {
      var a = document.createElement("a");
      a.download = stems.length ? "rack-stem-bounce.wav" : "rack-processed.wav";
      a.href = URL.createObjectURL(blob);
      a.click();
      statusEl.textContent = "WAV exported — processed copy downloaded.";
    }).catch(function () { statusEl.textContent = "Render failed — try again."; });
  });

  // Archive the processed master straight into the Asset Vault.
  var vaultBtn = document.getElementById("rk-vault");
  if (vaultBtn) vaultBtn.addEventListener("click", function () {
    if (!buffer && !stems.length) return;
    statusEl.textContent = "Rendering master for the Vault…";
    vaultBtn.disabled = true;
    vaultBtn.dataset.busy = "1";
    renderMaster().then(function (blob) {
      var fd = new FormData();
      var name = (loadedName || "rack-master") + "-master.wav";
      fd.append("file", blob, name);
      fd.append("kind", "master");
      fd.append("label", (loadedName || "Rack master") + " — rack master");
      return fetch("/vault/upload", {method: "POST", body: fd})
        .then(function (r) { return r.json(); });
    }).then(function (d) {
      statusEl.textContent = d.ok
        ? "Master archived in the Vault ✓" : (d.error || "Vault save failed.");
      delete vaultBtn.dataset.busy;
      vaultBtn.disabled = false;
    }).catch(function () {
      statusEl.textContent = "Vault save failed.";
      delete vaultBtn.dataset.busy;
      vaultBtn.disabled = false;
    });
  });

  // ---------- zone select: click an instrument lane, trim just its range ----------
  function zoneBands(lane) {
    // The EQ bands whose centers sit inside the lane's frequency range;
    // if none do, the single nearest band takes the trim.
    var idx = [];
    EQ_BANDS.forEach(function (b, i) {
      if (b.f >= lane.lo && b.f <= lane.hi) idx.push(i);
    });
    if (!idx.length) {
      var c = Math.sqrt(lane.lo * lane.hi), best = 0, bd = Infinity;
      EQ_BANDS.forEach(function (b, i) {
        var d = Math.abs(Math.log(b.f / c));
        if (d < bd) { bd = d; best = i; }
      });
      idx.push(best);
    }
    return idx;
  }
  function zoneTrim(delta) {
    if (selLane < 0) return;
    zoneBands(LANES[selLane]).forEach(function (i) {
      state.eq[i] = Math.max(-12, Math.min(12, +(state.eq[i] + delta).toFixed(1)));
    });
    renderEq(); applyState(); syncZoneUI();
  }
  function syncZoneUI() {
    var strip = document.getElementById("rk-zone");
    if (!strip) return;
    if (selLane < 0) { strip.style.display = "none"; return; }
    strip.style.display = "flex";
    var lane = LANES[selLane];
    var idx = zoneBands(lane);
    document.getElementById("rk-zone-name").textContent = lane.label;
    document.getElementById("rk-zone-name").style.color = lane.color;
    document.getElementById("rk-zone-bands").textContent =
      idx.map(function (i) {
        var v = state.eq[i];
        return EQ_BANDS[i].label + "Hz " + (v > 0 ? "+" : "") + v.toFixed(1);
      }).join(" · ");
  }
  function nodeAt(x, y) {
    var w = canvas.width, best = -1, bd = 144; // 12px grab radius
    EQ_BANDS.forEach(function (b, i) {
      var dx = x - fx(b.f, w), dy = y - (zeroCache - state.eq[i] * spanCache);
      var dd = dx * dx + dy * dy;
      if (dd < bd) { bd = dd; best = i; }
    });
    return best;
  }
  canvas.addEventListener("pointerdown", function (e) {
    var r = canvas.getBoundingClientRect();
    if (!r.width) return;
    var x = (e.clientX - r.left) * (canvas.width / r.width);
    var y = (e.clientY - r.top) * (canvas.height / r.height);
    var n = nodeAt(x, y);
    if (n >= 0) {
      nodeDrag = n; nodeMoved = false;
      canvas.setPointerCapture(e.pointerId);
      e.preventDefault();
    }
  });
  canvas.addEventListener("pointermove", function (e) {
    if (nodeDrag < 0) return;
    var r = canvas.getBoundingClientRect();
    var y = (e.clientY - r.top) * (canvas.height / r.height);
    var v = Math.max(-12, Math.min(12, (zeroCache - y) / spanCache));
    state.eq[nodeDrag] = Math.round(v * 10) / 10;
    nodeMoved = true;
    showTip(e.clientX, e.clientY - 16,
            EQ_BANDS[nodeDrag].label + "Hz  " +
            (state.eq[nodeDrag] > 0 ? "+" : "") + state.eq[nodeDrag].toFixed(1) + " dB");
    applyState();
  });
  canvas.addEventListener("pointerup", function () {
    if (nodeDrag >= 0 && nodeMoved) { renderEq(); syncZoneUI(); }
    nodeDrag = -1;
    hideTip();
  });
  canvas.addEventListener("click", function (e) {
    if (nodeMoved) { nodeMoved = false; return; }  // a node drag, not a lane pick
    var r = canvas.getBoundingClientRect();
    if (!r.width) return;
    var y = (e.clientY - r.top) * (canvas.height / r.height);
    var hit = -1;
    laneHitRects.forEach(function (lr, i) {
      if (lr && y >= lr[0] && y <= lr[0] + lr[1]) hit = i;
    });
    selLane = hit === selLane ? -1 : hit;
    syncZoneUI();
  });
  var zm = document.getElementById("rk-zone-minus"),
      zp = document.getElementById("rk-zone-plus"),
      zz = document.getElementById("rk-zone-zero"),
      zc = document.getElementById("rk-zone-clear");
  if (zm) zm.addEventListener("click", function () { zoneTrim(-1); });
  if (zp) zp.addEventListener("click", function () { zoneTrim(1); });
  if (zz) zz.addEventListener("click", function () {
    if (selLane < 0) return;
    zoneBands(LANES[selLane]).forEach(function (i) { state.eq[i] = 0; });
    renderEq(); applyState(); syncZoneUI();
  });
  if (zc) zc.addEventListener("click", function () { selLane = -1; syncZoneUI(); });

  // ---------- SB-12 Format Bench: decode anything, write exact PCM ------
  // The browser decodes and resamples; audioconv.js writes the container.
  // Every number the panel shows is computed from the real buffer.
  var cnvGo = document.getElementById("rk-cnv-go");
  var cnvPlan = document.getElementById("rk-cnv-plan");
  var cnvPeak = document.getElementById("rk-cnv-peak");
  var cnvStatus = document.getElementById("rk-cnv-status");
  var cnvRunning = false;

  function pickedValue(name, fallback) {
    var el = document.querySelector("input[name=" + name + "]:checked");
    return el ? el.value : fallback;
  }

  function cnvSourceBuffer() {
    if (pickedValue("rk-cnvsrc", "raw") === "master") {
      return renderMasterBuffer();
    }
    return buffer
      ? Promise.resolve(buffer)
      : Promise.reject(new Error("no decoded file — load a track, or convert "
                                + "the rack master instead"));
  }

  /* Resample and re-channel through an OfflineAudioContext, which is the
     browser's own resampler - better than anything worth hand-rolling
     here, and it is the same path the export already trusts. */
  function cnvResample(buf, rate, channels) {
    var len = Math.max(1, Math.round(buf.duration * rate));
    var oc = new OfflineAudioContext(channels, len, rate);
    var src = oc.createBufferSource();
    src.buffer = buf;
    src.connect(oc.destination);
    src.start();
    return oc.startRendering();
  }

  function fmtBytes(n) {
    if (n >= 1048576) { return (n / 1048576).toFixed(1) + " MB"; }
    if (n >= 1024) { return Math.round(n / 1024) + " KB"; }
    return n + " B";
  }

  /* The plan line: what the current settings will actually produce. Size
     is exact for PCM, so it is stated rather than estimated. */
  function cnvPlanText() {
    if (!cnvPlan) { return; }
    var haveSource = !!buffer || stems.length > 0;
    if (cnvGo) { cnvGo.disabled = cnvRunning || !haveSource; }
    if (!haveSource) {
      cnvPlan.textContent = "Load a track to convert.";
      if (cnvPeak) { cnvPeak.textContent = "No source"; }
      return;
    }
    /* Raw means the decoded file. With only stems in the deck there is no
       single decoded file to convert, so that option goes away rather than
       failing at the click. */
    var rawEl = document.getElementById("cs-raw");
    var masterEl = document.getElementById("cs-master");
    if (rawEl && masterEl) {
      rawEl.disabled = !buffer;
      rawEl.nextElementSibling.style.opacity = buffer ? "1" : "0.45";
      rawEl.nextElementSibling.title = buffer
        ? "The file exactly as decoded — no rack processing at all"
        : "No decoded file loaded — only the deck's stems are here";
      if (!buffer) { masterEl.checked = true; }
    }
    var fmt = pickedValue("rk-cnvfmt", "wav");
    var bits = parseInt(pickedValue("rk-cnvbits", "16"), 10);
    var rate = parseInt(pickedValue("rk-cnvrate", "44100"), 10);
    var ch = parseInt(pickedValue("rk-cnvch", "2"), 10);
    var spec = window.SBAudioConv.FORMATS[fmt];
    var effBits = bits;
    if (fmt === "aiff" && bits === 32) { effBits = 24; }
    var dur = (buffer || stems[0].buffer).duration;
    var frames = Math.round(dur * rate);
    var header = fmt === "wav" ? 44 : 54;
    var bytes = header + frames * ch * (effBits / 8);
    var note = spec.label + " · " + effBits + (effBits === 32 ? "-bit float" : "-bit")
      + " · " + (rate / 1000) + " kHz · "
      + (ch === 1 ? "mono" : "stereo") + " · " + fmtBytes(bytes);
    if (fmt === "aiff" && bits === 32) {
      note += "  (AIFF has no float form — writing 24-bit)";
    }
    cnvPlan.textContent = note;
    // Dither only means anything when resolution is actually being lost.
    var dth = document.getElementById("rk-cnv-dither");
    if (dth) {
      var useful = effBits < 32;
      dth.disabled = !useful;
      dth.parentElement.style.opacity = useful ? "1" : "0.45";
      dth.parentElement.title = useful
        ? "Decorrelates the quantisation error when reducing bit depth"
        : "Nothing to dither: 32-bit float keeps full resolution";
    }
  }

  /* True peak of whatever is actually loaded, named so the number is never
     ambiguous about what it measured. */
  function cnvShowPeak() {
    if (!cnvPeak) { return; }
    var src = buffer || (stems.length ? stems[0].buffer : null);
    if (!src) { cnvPeak.textContent = "No source"; return; }
    var chans = [];
    for (var c = 0; c < src.numberOfChannels; c++) {
      chans.push(src.getChannelData(c));
    }
    var db = window.SBAudioConv.peakDbfs(chans);
    cnvPeak.textContent = (buffer ? "File peak " : "Stem 1 peak ")
      + (db === -Infinity ? "silent" : db.toFixed(1) + " dBFS");
  }

  // Rate caps are built from the module's own list, so the two cannot drift.
  (function buildRateCaps() {
    var wrap = document.getElementById("rk-cnv-rate");
    if (!wrap || !window.SBAudioConv) { return; }
    window.SBAudioConv.RATES.forEach(function (r) {
      var id = "cr-" + r;
      var input = document.createElement("input");
      input.type = "radio"; input.name = "rk-cnvrate"; input.id = id;
      input.value = String(r);
      if (r === 44100) { input.checked = true; }
      var label = document.createElement("label");
      label.setAttribute("for", id);
      label.title = r === 44100 ? "CD and streaming standard"
        : (r === 48000 ? "Video and broadcast standard" : "");
      var cap = document.createElement("span");
      cap.className = "cap";
      cap.textContent = String(r / 1000);
      label.appendChild(cap);
      wrap.appendChild(input);
      wrap.appendChild(label);
    });
  })();

  (function buildLufsTargets() {
    var sel = document.getElementById("rk-cnv-lufs");
    if (!sel || !window.SBLoudness) { return; }
    window.SBLoudness.TARGETS.forEach(function (t) {
      var o = document.createElement("option");
      o.value = t.key;
      o.textContent = "Normalise to " + t.name + " (" + t.lufs + " LUFS)";
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () {
      var note = document.getElementById("rk-cnv-lufsnote");
      if (!note) { return; }
      var t = window.SBLoudness.TARGETS.filter(function (x) {
        return x.key === sel.value;
      })[0];
      note.textContent = t
        ? "Ceiling " + t.ceiling + " dBTP — measured after resampling."
        : "";
    });
  })();

  /* Apply a single clean gain so the output lands on a target. Measured on
     the ACTUAL output - after resampling and channel mapping - because
     that is the file being delivered, and its loudness is not necessarily
     the source's. If the gain would push the true peak past the ceiling it
     is capped so the peak lands exactly on it, and the caller is told how
     far short that left the loudness. No limiting: quietly squashing
     someone's master to hit a number is not normalisation. */
  function cnvNormalise(chans, rate, key) {
    var LD = window.SBLoudness;
    var target = LD.TARGETS.filter(function (t) { return t.key === key; })[0];
    if (!target) { return null; }
    var res = LD.analyse(chans, rate);
    if (res.integrated === null) {
      return {applied: 0, note: "too short to measure — level left alone"};
    }
    var wanted = target.lufs - res.integrated;
    var applied = wanted;
    var capped = false;
    if (res.truePeak !== null && res.truePeak + wanted > target.ceiling) {
      applied = target.ceiling - res.truePeak;
      capped = true;
    }
    var gain = Math.pow(10, applied / 20);
    if (gain !== 1) {
      for (var c = 0; c < chans.length; c++) {
        var d = chans[c];
        for (var i = 0; i < d.length; i++) { d[i] *= gain; }
      }
    }
    var note = (applied >= 0 ? "+" : "") + applied.toFixed(1) + " dB to reach "
      + target.name + " (" + res.integrated.toFixed(1) + " LUFS in";
    if (capped) {
      note += ", stopped " + Math.abs(wanted - applied).toFixed(1)
        + " dB short at the " + target.ceiling + " dBTP ceiling)";
    } else {
      note += ", " + (res.integrated + applied).toFixed(1) + " LUFS out)";
    }
    return {applied: applied, capped: capped, note: note,
            before: res.integrated, truePeak: res.truePeak};
  }

  ["rk-cnvsrc", "rk-cnvfmt", "rk-cnvbits", "rk-cnvrate", "rk-cnvch"]
    .forEach(function (name) {
      document.querySelectorAll("input[name=" + name + "]")
        .forEach(function (el) {
          el.addEventListener("change", cnvPlanText);
        });
    });

  /* Formats the browser cannot write. WAV and AIFF are encoded in this
     tab and never leave it; everything below needs an encoder no browser
     exposes to a page, so the audio goes to the server. The rate,
     channel, depth and loudness work still happens here - the server only
     changes the container. */
  var cnvServerFormats = (function () {
    var el = document.getElementById("rk-cnv-formats");
    var map = {};
    try {
      (el ? JSON.parse(el.textContent) : []).forEach(function (f) {
        if (f.value !== "wav" && f.value !== "aiff") { map[f.value] = f; }
      });
    } catch (e) { /* no server encoder: local formats only */ }
    return map;
  })();

  var cnvBrWrap = document.getElementById("rk-cnv-brwrap");
  var cnvBr = document.getElementById("rk-cnv-br");
  var cnvWhere = document.getElementById("rk-cnv-where");

  function cnvSyncFormat() {
    var fmt = pickedValue("rk-cnvfmt", "wav");
    var spec = cnvServerFormats[fmt];
    if (cnvBrWrap) {
      var lossy = !!(spec && spec.lossy);
      cnvBrWrap.classList.toggle("hidden", !lossy);
      if (lossy && cnvBr && cnvBr.getAttribute("data-for") !== fmt) {
        cnvBr.setAttribute("data-for", fmt);
        cnvBr.innerHTML = "";
        spec.bitrates.forEach(function (b) {
          var id = "cbr-" + b;
          var input = document.createElement("input");
          input.type = "radio"; input.name = "rk-cnvbr";
          input.id = id; input.value = b;
          if (b === spec.default_bitrate) { input.checked = true; }
          var label = document.createElement("label");
          label.setAttribute("for", id);
          label.innerHTML = '<span class="cap">' + b + '</span>';
          cnvBr.appendChild(input); cnvBr.appendChild(label);
        });
      }
    }
    if (cnvWhere) {
      cnvWhere.textContent = spec
        ? "Encoded on the server — this uploads your audio. " + spec.note
        : "Written in this tab. Nothing uploads.";
      cnvWhere.className = "note mt-1.5 text-[9px] leading-snug "
        + (spec ? "text-[#e8c667]" : "text-[#8a8069]");
    }
  }
  Array.prototype.slice.call(
    document.querySelectorAll('input[name="rk-cnvfmt"]'))
    .forEach(function (el) { el.addEventListener("change", cnvSyncFormat); });
  cnvSyncFormat();

  /* Hand the finished audio to the server to be re-containered. */
  function cnvServerEncode(chans, rate, fmt, spec, bits, dither, norm, lufsKey) {
    // Carry it over as PCM WAV. Never dither ahead of a lossy encoder -
    // the noise it adds is exactly what the codec then spends bits on.
    var serverNote = "";
    var carrierBits = spec.lossy ? 24 : (bits === 16 ? 16 : 24);
    var carrier = window.SBAudioConv.encode(
      "wav", chans, rate, carrierBits,
      {dither: !spec.lossy && carrierBits === 16 && dither});
    var fd = new FormData();
    fd.append("audio", new Blob([carrier], {type: "audio/wav"}),
              (loadedName || "audio") + ".wav");
    fd.append("format", fmt);
    fd.append("rate", String(rate));
    fd.append("channels", String(chans.length));
    if (spec.lossy) { fd.append("bitrate", pickedValue("rk-cnvbr", "")); }
    cnvStatus.textContent = "Uploading " + fmtBytes(carrier.byteLength)
      + " to be encoded as " + spec.label + "…";
    return fetch("/rack/convert", {method: "POST", body: fd})
      .then(function (r) {
        if (!r.ok) {
          return r.json().then(function (j) {
            throw new Error(j.error || ("HTTP " + r.status));
          });
        }
        serverNote = r.headers.get("X-Convert-Note") || "";
        return r.blob();
      })
      .then(function (blob) {
        var a = document.createElement("a");
        a.download = (loadedName || "converted") + "-" + (rate / 1000) + "k"
          + (spec.lossy ? "-" + pickedValue("rk-cnvbr", "") + "kbps" : "")
          + (norm && norm.applied ? "-" + lufsKey : "") + "." + spec.ext;
        a.href = URL.createObjectURL(blob);
        a.click();
        cnvStatus.textContent = "Converted — " + a.download + " ("
          + fmtBytes(blob.size) + ") downloaded."
          + (norm ? "  Loudness: " + norm.note + "." : "")
          + (serverNote ? "  " + serverNote : "");
      });
  }

  if (cnvGo) cnvGo.addEventListener("click", function () {
    if (cnvRunning) { return; }
    cnvRunning = true;
    cnvGo.disabled = true;
    cnvStatus.textContent = "Converting…";
    var fmt = pickedValue("rk-cnvfmt", "wav");
    var bits = parseInt(pickedValue("rk-cnvbits", "16"), 10);
    var rate = parseInt(pickedValue("rk-cnvrate", "44100"), 10);
    var ch = parseInt(pickedValue("rk-cnvch", "2"), 10);
    var dither = document.getElementById("rk-cnv-dither");
    cnvSourceBuffer()
      .then(function (buf) { return cnvResample(buf, rate, ch); })
      .then(function (out) {
        var chans = [];
        for (var c = 0; c < out.numberOfChannels; c++) {
          // Copy: normalising writes in place, and the rendered buffer is
          // not ours to modify.
          chans.push(Float32Array.from(out.getChannelData(c)));
        }
        var lufsKey = (document.getElementById("rk-cnv-lufs") || {}).value;
        var norm = lufsKey && window.SBLoudness
          ? cnvNormalise(chans, rate, lufsKey) : null;

        // Compressed formats finish on the server; the work above has
        // already happened either way.
        var server = cnvServerFormats[fmt];
        if (server) {
          return cnvServerEncode(chans, rate, fmt, server, bits,
                                 !!(dither && dither.checked), norm, lufsKey)
            .then(function () { cnvRunning = false; cnvPlanText(); });
        }

        var spec = window.SBAudioConv.FORMATS[fmt];
        var ab = window.SBAudioConv.encode(fmt, chans, rate, bits,
                                           {dither: !!(dither && dither.checked)});
        var a = document.createElement("a");
        a.download = (loadedName || "converted") + "-" + (rate / 1000)
          + "k-" + bits + "bit"
          + (norm && norm.applied ? "-" + lufsKey : "") + "." + spec.ext;
        a.href = URL.createObjectURL(new Blob([ab], {type: spec.mime}));
        a.click();
        cnvStatus.textContent = "Converted — " + a.download + " ("
          + fmtBytes(ab.byteLength) + ") downloaded."
          + (norm ? "  Loudness: " + norm.note + "." : "");
        cnvRunning = false;
        cnvPlanText();
      })
      .catch(function (e) {
        cnvRunning = false;
        cnvPlanText();
        cnvStatus.textContent = "Convert failed: " + (e.message || e);
      });
  });

  // ---------- SB-13 Tempo & Key --------------------------------------
  // Detection is measurement with a score; the transform is WSOLA. The
  // panel only ever states what tempokey.js actually returned.
  var tkDetect = document.getElementById("rk-tk-detect");
  var tkLamp = document.getElementById("rk-tk-lamp");
  var tkStatus = document.getElementById("rk-tk-status");
  var tkPlan = document.getElementById("rk-tk-plan");
  var tkPreview = document.getElementById("rk-tk-preview");
  var tkRender = document.getElementById("rk-tk-render");
  var tkWrap = document.getElementById("rk-tk-wrap");
  var tkFill = document.getElementById("rk-tk-fill");
  var tkSemis = 0, tkCents = 0, tkTempo = 1;
  var tkFound = null;            // last detection result, or null
  var tkBusy = false;
  var tkPreviewSrc = null;

  function tkChannels(buf) {
    var out = [];
    for (var c = 0; c < buf.numberOfChannels; c++) {
      out.push(buf.getChannelData(c));
    }
    return out;
  }

  function tkSource() {
    return buffer || (stems.length ? stems[0].buffer : null);
  }

  function tkEnable() {
    var have = !!tkSource();
    if (tkDetect) { tkDetect.disabled = tkBusy || !have; }
    if (tkPreview) { tkPreview.disabled = tkBusy || !have; }
    if (tkRender) { tkRender.disabled = tkBusy || !have; }
  }

  /* The 12 measured pitch classes, with the detected root lit. Nothing is
     drawn until a real chroma exists. */
  function tkPaintChroma(res) {
    var svg = document.getElementById("rk-tk-chroma");
    if (!svg) { return; }
    var W = 480, H = 76, base = 62;
    svg.innerHTML = "";
    svg.appendChild(svgEl("path", {d: "M0 " + base + "h" + W,
                                   stroke: "#6b665b", "stroke-width": 1}));
    var names = (res && res.notes) || window.SBTempoKey.NOTES;
    var vals = res && res.chroma;
    var max = 0, i;
    if (vals) {
      for (i = 0; i < 12; i++) { if (vals[i] > max) { max = vals[i]; } }
    }
    for (i = 0; i < 12; i++) {
      var x = 6 + i * 39.5;
      var lit = res && i === res.root;
      var h = vals && max > 0 ? Math.max(1, (vals[i] / max) * 52) : 1;
      svg.appendChild(svgEl("rect", {
        x: x, y: base - h, width: 27, height: h, rx: 1.5,
        fill: lit ? "#a37c2a" : (vals ? "#7b7669" : "#8f8a7e"),
        opacity: vals ? 1 : 0.4}));
      var lab = svgEl("text", {x: x + 13.5, y: H - 2, "text-anchor": "middle",
                               fill: lit ? "#2e2920" : "#4c4536",
                               "font-size": "10", "font-weight": "800",
                               "font-family": "Arial Narrow, Arial, sans-serif"});
      lab.textContent = names[i];
      svg.appendChild(lab);
    }
    if (!vals) {
      var hint = svgEl("text", {x: W / 2, y: 22, "text-anchor": "middle",
                                fill: "#4c4536", "font-size": "10",
                                "font-weight": "800", "letter-spacing": "2",
                                "font-family": "Arial Narrow, Arial, sans-serif"});
      hint.textContent = "NO ANALYSIS YET";
      svg.appendChild(hint);
    }
  }

  /* One line stating source and result. Only the parts that were actually
     measured appear - an unmeasured key never becomes a claim. */
  function tkPlanText() {
    if (!tkPlan) { return; }
    var pct = Math.round(tkTempo * 100);
    var parts = ["Tempo " + pct + "%"];
    var semiTotal = tkSemis + tkCents / 100;
    parts.push("pitch " + (semiTotal >= 0 ? "+" : "") + semiTotal.toFixed(2) + " st");
    if (tkFound) {
      var proj = window.SBTempoKey.project(
        tkFound.bpm, tkFound.root, tkFound.mode, tkTempo, tkSemis);
      parts.push(tkFound.bpm.toFixed(1) + " → " + proj.bpm.toFixed(1) + " BPM");
      parts.push(tkFound.key + " → " + proj.key);
    }
    var src = tkSource();
    if (src) {
      parts.push("length " + mmss(src.duration) + " → "
                 + mmss(src.duration * tkTempo));
    }
    tkPlan.textContent = parts.join("  ·  ");
  }

  function tkSetSemis(v) {
    tkSemis = Math.max(-12, Math.min(12, v));
    var el = document.getElementById("rk-tk-semis");
    if (el) {
      el.textContent = (tkSemis > 0 ? "+" : "") + tkSemis + " st";
    }
    tkPlanText();
  }

  function tkSetTempo(pct) {
    tkTempo = Math.max(0.5, Math.min(2, pct / 100));
    var el = document.getElementById("rk-tk-tempoval");
    if (el) { el.textContent = Math.round(tkTempo * 100) + "%"; }
    tkPlanText();
  }

  var tkTempoEl = document.getElementById("rk-tk-tempo");
  if (tkTempoEl) tkTempoEl.addEventListener("input", function () {
    tkSetTempo(parseFloat(tkTempoEl.value));
    var t = document.getElementById("rk-tk-target");
    // The slider is now the authority; clear a stale target reading.
    if (t && tkFound) { t.value = (tkFound.bpm / tkTempo).toFixed(1); }
  });

  var tkTargetEl = document.getElementById("rk-tk-target");
  if (tkTargetEl) tkTargetEl.addEventListener("input", function () {
    var want = parseFloat(tkTargetEl.value);
    if (!tkFound) {
      tkStatus.textContent = "Detect the tempo first — a target BPM needs "
        + "something to measure from.";
      return;
    }
    if (!want || want <= 0) { return; }
    // Output BPM = source / tempo, so tempo = source / target.
    var ratio = tkFound.bpm / want;
    if (ratio < 0.5 || ratio > 2) {
      tkStatus.textContent = "That target needs a " + ratio.toFixed(2)
        + "x stretch — outside the 0.5x–2x the stretcher holds up over.";
      return;
    }
    tkStatus.textContent = "";
    tkSetTempo(ratio * 100);
    if (tkTempoEl) { tkTempoEl.value = String(Math.round(ratio * 100)); }
  });

  var tkCentsEl = document.getElementById("rk-tk-cents");
  if (tkCentsEl) tkCentsEl.addEventListener("input", function () {
    tkCents = parseFloat(tkCentsEl.value) || 0;
    var el = document.getElementById("rk-tk-centsval");
    if (el) { el.textContent = (tkCents > 0 ? "+" : "") + tkCents; }
    tkPlanText();
  });

  var tkUpEl = document.getElementById("rk-tk-up");
  if (tkUpEl) tkUpEl.addEventListener("click", function () { tkSetSemis(tkSemis + 1); });
  var tkDownEl = document.getElementById("rk-tk-down");
  if (tkDownEl) tkDownEl.addEventListener("click", function () { tkSetSemis(tkSemis - 1); });
  var tkZeroEl = document.getElementById("rk-tk-zero");
  if (tkZeroEl) tkZeroEl.addEventListener("click", function () {
    tkSetSemis(0);
    tkCents = 0;
    if (tkCentsEl) { tkCentsEl.value = "0"; }
    var cv = document.getElementById("rk-tk-centsval");
    if (cv) { cv.textContent = "0"; }
    tkSetTempo(100);
    if (tkTempoEl) { tkTempoEl.value = "100"; }
  });

  if (tkDetect) tkDetect.addEventListener("click", function () {
    var src = tkSource();
    if (!src || tkBusy) { return; }
    tkBusy = true;
    tkEnable();
    if (tkLamp) { tkLamp.classList.add("on"); }
    tkStatus.textContent = "Analysing…";
    // Yield first so the lamp and status actually paint before the work.
    setTimeout(function () {
      try {
        var chans = tkChannels(src);
        var bpm = window.SBTempoKey.detectBpm(chans, src.sampleRate);
        var key = window.SBTempoKey.detectKey(chans, src.sampleRate);
        tkFound = null;
        if (bpm && key) {
          tkFound = {bpm: bpm.bpm, confidence: bpm.confidence,
                     root: key.root, mode: key.mode, key: key.key,
                     keyFit: key.score};
        }
        var bpmEl = document.getElementById("rk-tk-bpm");
        var bpmSub = document.getElementById("rk-tk-bpmsub");
        if (bpm) {
          bpmEl.textContent = bpm.bpm.toFixed(1);
          bpmSub.textContent = "confidence " + bpm.confidence.toFixed(2)
            + " · could also be " + bpm.alternates.join(" or ");
        } else {
          bpmEl.textContent = "—";
          bpmSub.textContent = "too short to measure a tempo";
        }
        var keyEl = document.getElementById("rk-tk-key");
        var keySub = document.getElementById("rk-tk-keysub");
        if (key) {
          keyEl.textContent = key.key;
          keySub.textContent = "fit " + key.score.toFixed(2)
            + " · next best " + key.runnerUp + " (" + key.runnerUpScore.toFixed(2) + ")";
        } else {
          keyEl.textContent = "—";
          keySub.textContent = "no pitched content found";
        }
        tkPaintChroma(key);
        // Half/double tempo are one click away, because the maths cannot
        // choose between them and the artist can.
        var alts = document.getElementById("rk-tk-alts");
        if (alts) {
          alts.innerHTML = "";
          if (bpm) {
            bpm.alternates.forEach(function (alt) {
              var b = document.createElement("button");
              b.className = "sw px-2 py-1 text-[9px]";
              b.textContent = "Treat as " + alt;
              b.title = "Adopt " + alt + " BPM as the source reading";
              b.addEventListener("click", function () {
                tkFound = tkFound || {};
                tkFound.bpm = alt;
                document.getElementById("rk-tk-bpm").textContent = alt.toFixed(1);
                bpmSub.textContent = "adopted " + alt + " BPM (you chose this "
                  + "over the measured " + bpm.bpm.toFixed(1) + ")";
                tkPlanText();
              });
              alts.appendChild(b);
            });
          }
        }
        tkStatus.textContent = "";
        tkPlanText();
      } catch (e) {
        tkStatus.textContent = "Analysis failed: " + (e.message || e);
      }
      tkBusy = false;
      if (tkLamp) { tkLamp.classList.remove("on"); }
      tkEnable();
    }, 30);
  });

  /* Run the transform over a slice or the whole track. onDone gets a real
     AudioBuffer built from the stretched channels. */
  function tkTransform(seconds, onDone) {
    var src = tkSource();
    if (!src || tkBusy) { return; }
    var semiTotal = tkSemis + tkCents / 100;
    if (Math.abs(tkTempo - 1) < 1e-6 && Math.abs(semiTotal) < 1e-6) {
      tkStatus.textContent = "Nothing to change — tempo is 100% and pitch is 0.";
      return;
    }
    tkBusy = true;
    tkEnable();
    ensureCtx();
    if (tkLamp) { tkLamp.classList.add("on"); }
    if (tkWrap) { tkWrap.classList.remove("hidden"); }
    tkStatus.textContent = "Processing…";
    var chans = [];
    var take = seconds
      ? Math.min(src.length, Math.round(seconds * src.sampleRate))
      : src.length;
    for (var c = 0; c < src.numberOfChannels; c++) {
      chans.push(src.getChannelData(c).subarray(0, take));
    }
    window.SBTempoKey.transform(
      chans, {tempo: tkTempo, semitones: tkSemis, cents: tkCents},
      function (p) {
        if (tkFill) { tkFill.style.width = Math.round(p * 100) + "%"; }
      },
      function (out) {
        try {
          var buf = ctx.createBuffer(out.length, out[0].length, src.sampleRate);
          for (var i = 0; i < out.length; i++) {
            buf.copyToChannel(out[i], i);
          }
          onDone(buf);
        } catch (e) {
          tkStatus.textContent = "Processing failed: " + (e.message || e);
        }
        tkBusy = false;
        if (tkLamp) { tkLamp.classList.remove("on"); }
        if (tkWrap) { tkWrap.classList.add("hidden"); }
        if (tkFill) { tkFill.style.width = "0%"; }
        tkEnable();
      });
  }

  if (tkPreview) tkPreview.addEventListener("click", function () {
    tkTransform(12, function (buf) {
      if (playing) { stop(); }
      if (tkPreviewSrc) {
        try { tkPreviewSrc.stop(); } catch (e) { /* already finished */ }
      }
      ensureCtx();
      ctx.resume();
      tkPreviewSrc = ctx.createBufferSource();
      tkPreviewSrc.buffer = buf;
      tkPreviewSrc.connect(ctx.destination);
      tkPreviewSrc.start();
      tkStatus.textContent = "Playing " + mmss(buf.duration)
        + " preview — dry, straight out, not through the rack.";
    });
  });

  if (tkRender) tkRender.addEventListener("click", function () {
    tkTransform(0, function (buf) {
      var chans = tkChannels(buf);
      var ab = window.SBAudioConv.encodeWav(chans, buf.sampleRate, 24,
                                            {dither: false});
      var bits = [];
      if (Math.abs(tkTempo - 1) > 1e-6) {
        bits.push(Math.round(tkTempo * 100) + "pct");
      }
      if (tkSemis || tkCents) {
        bits.push((tkSemis >= 0 ? "up" : "dn") + Math.abs(tkSemis) + "st");
      }
      var a = document.createElement("a");
      a.download = (loadedName || "track") + "-" + bits.join("-") + ".wav";
      a.href = URL.createObjectURL(new Blob([ab], {type: "audio/wav"}));
      a.click();
      tkStatus.textContent = "Bounced " + a.download + " — 24-bit WAV, "
        + mmss(buf.duration) + ".";
    });
  });

  tkPaintChroma(null);
  tkPlanText();
  tkEnable();
  cnvPlanText();

  // ---------- SB-14 Valve Bank: controls and the glow loop -------------
  var valveEls = {};

  function syncValveUI() {
    VALVE_KEYS.forEach(function (key) {
      var el = valveEls[key];
      if (!el) { return; }
      var v = state.valves[key];
      var on = !!v.on && modOn("vlv");
      el.pwr.setAttribute("aria-pressed", on ? "true" : "false");
      el.box.classList.toggle("off", !on);
      if (document.activeElement !== el.amt) {
        el.amt.value = String(Math.round(v.amt * 100));
      }
      el.amt.disabled = !on;
    });
    var all = document.getElementById("rk-vlv-all");
    if (all) {
      var anyOn = VALVE_KEYS.some(function (k) { return state.valves[k].on; });
      all.textContent = anyOn ? "All off" : "Warm up";
      all.title = anyOn
        ? "Switch every valve off — back to a clean signal"
        : "Switch on the two most useful stages: triode warmth and tape";
    }
  }

  VALVE_KEYS.forEach(function (key) {
    var box = document.getElementById("rk-vlv-" + key);
    if (!box) { return; }
    valveEls[key] = {
      box: box,
      pwr: box.querySelector(".vlv-pwr"),
      amt: box.querySelector(".fader"),
      fil: box.querySelector(".vlv-fil"),
      halo: box.querySelector(".vlv-halo"),
      plate: box.querySelector(".vlv-plate"),
      glow: 0,
    };
    valveEls[key].pwr.addEventListener("click", function () {
      state.valves[key].on = !state.valves[key].on;
      ensureCtx();
      if (live) { voiceValves(live.valves); }
      syncValveUI();
    });
    valveEls[key].amt.addEventListener("input", function (e) {
      state.valves[key].amt = (parseFloat(e.target.value) || 0) / 100;
      if (live) { voiceValves(live.valves); }
    });
  });

  var valveAll = document.getElementById("rk-vlv-all");
  if (valveAll) valveAll.addEventListener("click", function () {
    var anyOn = VALVE_KEYS.some(function (k) { return state.valves[k].on; });
    if (anyOn) {
      VALVE_KEYS.forEach(function (k) { state.valves[k].on = false; });
    } else {
      /* "Warm up" is a starting point, not a preset with opinions: the two
         stages that flatter almost anything, at modest settings. */
      state.valves.triode.on = true; state.valves.triode.amt = 0.4;
      state.valves.tape.on = true; state.valves.tape.amt = 0.3;
    }
    ensureCtx();
    if (live) { voiceValves(live.valves); }
    syncValveUI();
  });

  /* Read what each stage is really doing and light it accordingly. Called
     from the existing draw loop, so it stops when the tab is hidden - and
     because it only ever paints, a missed frame costs nothing. */
  function paintValves() {
    var T = window.SBTubes;
    if (!T || !live || !live.valves || !live.valves.taps) { return; }
    var taps = live.valves.taps;
    VALVE_KEYS.forEach(function (key) {
      var el = valveEls[key];
      if (!el) { return; }
      var v = state.valves[key];
      var amt = (v.on && modOn("vlv")) ? v.amt : 0;
      var target = 0;
      if (amt > 0 && playing) {
        if (key === "varimu") {
          target = T.glowFromReduction(live.valves.varimu.reduction, amt);
        } else {
          var tap = taps[key];
          if (tap) {
            tap.node.getByteTimeDomainData(tap.buf);
            var sum = 0;
            for (var i = 0; i < tap.buf.length; i++) {
              var d = (tap.buf[i] - 128) / 128;
              sum += d * d;
            }
            target = T.glow(Math.sqrt(sum / tap.buf.length), amt);
          }
        }
      }
      // Ease so a filament warms and cools instead of strobing.
      el.glow += (target - el.glow) * (target > el.glow ? 0.28 : 0.09);
      if (el.glow < 0.004) { el.glow = 0; }
      var g = el.glow;
      el.box.style.setProperty("--heat", g.toFixed(3));   // the deck glass lights from this
      if (el.halo) { el.halo.setAttribute("opacity", (g * 0.9).toFixed(3)); }
      if (el.fil) {
        if (g <= 0) {
          el.fil.setAttribute("stroke", "#3a3424");
          el.fil.setAttribute("stroke-width", "1.5");
        } else {
          var r = Math.round(122 + 133 * g);
          var gr = Math.round(62 + 173 * g);
          var b = Math.round(14 + 156 * g);
          el.fil.setAttribute("stroke", "rgb(" + r + "," + gr + "," + b + ")");
          el.fil.setAttribute("stroke-width", (1.5 + g * 0.9).toFixed(2));
        }
      }
      if (el.plate) {
        el.plate.setAttribute("stroke", g > 0.25 ? "#8a6d1f" : "#4a4438");
      }
    });
  }

  // ---------- SB-15 Loudness: the number platforms normalise by ---------
  var ldnGo = document.getElementById("rk-ldn-go");
  var ldnLamp = document.getElementById("rk-ldn-lamp");
  var ldnStatus = document.getElementById("rk-ldn-status");
  var ldnWrap = document.getElementById("rk-ldn-wrap");
  var ldnFill = document.getElementById("rk-ldn-fill");
  var ldnBusy = false;
  var ldnLast = null;

  function ldnSource() {
    return buffer || (stems.length ? stems[0].buffer : null);
  }

  function ldnEnable() {
    if (!ldnGo) { return; }
    var have = !!ldnSource() || stems.length > 0;
    ldnGo.disabled = ldnBusy || !have;
    var raw = document.getElementById("ld-raw");
    var master = document.getElementById("ld-master");
    if (raw && master) {
      // "File" means a decoded file. With only stems in the deck there is
      // none, so that option goes away rather than failing at the click.
      raw.disabled = !buffer;
      raw.nextElementSibling.style.opacity = buffer ? "1" : "0.45";
      if (!buffer) { master.checked = true; }
    }
    var src = document.getElementById("rk-ldn-src");
    if (src) {
      var b = ldnSource();
      src.textContent = b
        ? (buffer ? "File" : "Stem 1") + " · " + mmss(b.duration)
          + " · " + (b.sampleRate / 1000) + " kHz"
        : "No source";
    }
  }

  /* The short-term curve, drawn from the real 3-second blocks. The scale
     is pinned to the range the reading actually occupies, so a flat master
     does not get stretched into looking dynamic. */
  function ldnPaintGraph(res) {
    var svg = document.getElementById("rk-ldn-graph");
    if (!svg) { return; }
    var W = 600, H = 90;
    svg.innerHTML = "";
    svg.appendChild(svgEl("rect", {x: 0, y: 0, width: W, height: H, rx: 2,
                                   fill: "#0b0a08"}));
    var vals = (res && res.shortTerm || []).filter(function (v) {
      return isFinite(v);
    });
    if (vals.length < 2) {
      var hint = svgEl("text", {x: W / 2, y: H / 2 + 3, "text-anchor": "middle",
                                fill: "#4c4536", "font-size": "10",
                                "font-weight": "800", "letter-spacing": "2",
                                "font-family": "Arial Narrow, Arial, sans-serif"});
      hint.textContent = res ? "TOO SHORT FOR A SHORT-TERM CURVE"
                             : "NOT MEASURED YET";
      svg.appendChild(hint);
      return;
    }
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    // Always show at least 6 LU so a steady master is not magnified.
    if (hi - lo < 6) { var mid = (hi + lo) / 2; lo = mid - 3; hi = mid + 3; }
    lo -= 1; hi += 1;
    function y(v) { return H - 6 - (v - lo) / (hi - lo) * (H - 14); }

    // The integrated value as a reference line, labelled.
    if (res.integrated !== null && res.integrated > lo && res.integrated < hi) {
      var iy = y(res.integrated);
      svg.appendChild(svgEl("path", {d: "M0 " + iy.toFixed(1) + "H" + W,
                                     stroke: "#8a6d1f", "stroke-width": 1,
                                     "stroke-dasharray": "4 4"}));
      var lab = svgEl("text", {x: 4, y: iy - 3, fill: "#8a6d1f",
                               "font-size": "9", "font-weight": "800",
                               "font-family": "Arial Narrow, Arial, sans-serif"});
      lab.textContent = "I " + res.integrated.toFixed(1);
      svg.appendChild(lab);
    }
    var d = "";
    vals.forEach(function (v, i) {
      var x = (i / (vals.length - 1)) * W;
      d += (i ? "L" : "M") + x.toFixed(1) + " " + y(v).toFixed(1);
    });
    svg.appendChild(svgEl("path", {d: d, fill: "none", stroke: "#c9a24a",
                                   "stroke-width": 1.6}));
    [lo + 1, hi - 1].forEach(function (v) {
      var t = svgEl("text", {x: W - 3, y: y(v) + (v === lo + 1 ? -3 : 8),
                             "text-anchor": "end", fill: "#4c4536",
                             "font-size": "8", "font-weight": "800",
                             "font-family": "Arial Narrow, Arial, sans-serif"});
      t.textContent = v.toFixed(0);
      svg.appendChild(t);
    });
  }

  /* One row per published target: how far off, which way the platform will
     move it, and whether raising it would clip. */
  function ldnPaintTargets(res) {
    var wrap = document.getElementById("rk-ldn-targets");
    if (!wrap) { return; }
    wrap.innerHTML = "";
    if (!res || res.integrated === null) {
      var p = document.createElement("p");
      p.className = "note";
      p.textContent = "Measure a track and every target fills in with the "
        + "exact gain it would take to hit it.";
      wrap.appendChild(p);
      return;
    }
    res.targets.forEach(function (t) {
      var row = document.createElement("div");
      row.className = "ldn-row";
      var name = document.createElement("span");
      name.className = "ldn-name";
      name.textContent = t.name;
      var tgt = document.createElement("span");
      tgt.className = "val ldn-t";
      tgt.textContent = t.lufs + " LUFS";
      var delta = document.createElement("span");
      delta.className = "val ldn-d " + (Math.abs(t.delta) <= 0.5 ? "ok"
        : (t.over ? "over" : "under"));
      delta.textContent = (t.delta > 0 ? "+" : "") + t.delta.toFixed(1) + " LU";
      var verdict = document.createElement("span");
      verdict.className = "ldn-v";
      if (Math.abs(t.delta) <= 0.5) {
        verdict.textContent = "on target";
      } else if (t.over) {
        verdict.textContent = "turned down " + Math.abs(t.gain).toFixed(1)
          + " dB — costs nothing";
      } else if (t.clipsIfRaised) {
        verdict.textContent = "+" + t.gain.toFixed(1) + " dB would hit "
          + (res.truePeak + t.gain).toFixed(1) + " dBTP — clips";
        verdict.className += " warn";
      } else {
        verdict.textContent = "room for +" + t.gain.toFixed(1) + " dB";
      }
      row.appendChild(name); row.appendChild(tgt);
      row.appendChild(delta); row.appendChild(verdict);
      wrap.appendChild(row);
    });
  }

  function ldnShow(res) {
    ldnLast = res;
    var set = function (id, txt) {
      var el = document.getElementById(id);
      if (el) { el.textContent = txt; }
    };
    set("rk-ldn-i", res && res.integrated !== null
        ? res.integrated.toFixed(1) : "—");
    set("rk-ldn-tp", res && res.truePeak !== null
        ? res.truePeak.toFixed(1) : "—");
    set("rk-ldn-lra", res && res.range !== null ? res.range.toFixed(1) : "—");
    if (res && res.truePeak !== null) {
      // Say how much of the peak a sample meter would have missed.
      set("rk-ldn-tpsub", "dBTP · " + (res.intersample > 0.05
        ? "+" + res.intersample.toFixed(2) + " dB above sample peak"
        : "sample peak " + res.samplePeak.toFixed(1)));
    }
    if (res && res.range === null) {
      set("rk-ldn-lrasub", "LU · needs about 10s to measure");
    }
    ldnPaintGraph(res);
    ldnPaintTargets(res);
    reportAnalysis(res);
  }

  /* Send the measurement up so it outlives the tab.

     Everything this meter computes used to vanish when the page closed,
     which meant Release Readiness could call a record ready while its
     master clipped on every platform - the score was built from campaign
     setup and artwork counts, and never once looked at the audio.

     Nothing is computed here that is not already on screen. If the post
     fails the Rack carries on; a meter that stops working because a
     network call failed would be a worse trade than losing the history. */
  var lastReported = null;
  function reportAnalysis(res) {
    if (!res || res.integrated === null || res.integrated === undefined) { return; }
    var tk = tkFound || {};
    var payload = {
      filename: loadedName || "",
      integrated: res.integrated, lra: res.range,
      true_peak: res.truePeak, sample_peak: res.samplePeak,
      short_term_max: res.shortTermMax, momentary_max: res.momentaryMax,
      bpm: typeof tk.bpm === "number" ? tk.bpm : null,
      bpm_confidence: typeof tk.confidence === "number" ? tk.confidence : null,
      key: typeof tk.key === "string" ? tk.key : "",
      key_fit: typeof tk.keyFit === "number" ? tk.keyFit : null,
      duration: buffer ? buffer.duration : null,
      sample_rate: buffer ? buffer.sampleRate : null,
      channels: buffer ? buffer.numberOfChannels : null,
      hook_15s: typeof lastHooks[15] === "number" ? lastHooks[15] : null,
      hook_30s: typeof lastHooks[30] === "number" ? lastHooks[30] : null,
      first_beat: lastGrid ? lastGrid.first : null,
      bar_seconds: lastGrid ? lastGrid.bar : null,
      grid_confidence: lastGrid ? lastGrid.confidence : null,
      engine: "rack/loudness.js BS.1770-4"
    };
    // Same file, same numbers - no need to say it twice.
    var sig = JSON.stringify(payload);
    if (sig === lastReported) { return; }
    lastReported = sig;
    fetch("/rack/analysis", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: sig
    }).catch(function () { lastReported = null; });
  }

  function ldnBuffer() {
    if (pickedValue("rk-ldnsrc", "raw") === "master") {
      return renderMasterBuffer();
    }
    return buffer
      ? Promise.resolve(buffer)
      : Promise.reject(new Error("no decoded file — measure the master instead"));
  }

  if (ldnGo) ldnGo.addEventListener("click", function () {
    if (ldnBusy || !window.SBLoudness) { return; }
    ldnBusy = true;
    ldnEnable();
    if (ldnLamp) { ldnLamp.classList.add("on"); }
    if (ldnWrap) { ldnWrap.classList.remove("hidden"); }
    if (ldnFill) { ldnFill.style.width = "15%"; }
    ldnStatus.textContent = "Measuring…";
    ldnBuffer().then(function (buf) {
      if (ldnFill) { ldnFill.style.width = "55%"; }
      // Yield once so the lamp and bar paint before the analysis blocks.
      return new Promise(function (resolve) {
        setTimeout(function () {
          var chans = [];
          for (var c = 0; c < buf.numberOfChannels; c++) {
            chans.push(buf.getChannelData(c));
          }
          resolve(window.SBLoudness.analyse(chans, buf.sampleRate));
        }, 30);
      });
    }).then(function (res) {
      ldnShow(res);
      ldnStatus.textContent = res.integrated === null
        ? "Too short to measure — loudness needs at least 400 ms."
        : "";
      ldnBusy = false;
      if (ldnLamp) { ldnLamp.classList.remove("on"); }
      if (ldnWrap) { ldnWrap.classList.add("hidden"); }
      if (ldnFill) { ldnFill.style.width = "0%"; }
      ldnEnable();
      cnvPlanText();
    }).catch(function (e) {
      ldnBusy = false;
      if (ldnLamp) { ldnLamp.classList.remove("on"); }
      if (ldnWrap) { ldnWrap.classList.add("hidden"); }
      ldnEnable();
      ldnStatus.textContent = "Measurement failed: " + (e.message || e);
    });
  });

  document.querySelectorAll("input[name=rk-ldnsrc]").forEach(function (el) {
    el.addEventListener("change", function () {
      // A reading belongs to what it measured; changing the source retires
      // it rather than leaving a number attached to the wrong signal.
      ldnShow(null);
      ldnStatus.textContent = "";
    });
  });

  ldnShow(null);
  ldnEnable();

  window.__rackTest = {buildChain: buildChain, encodeWav: encodeWav,
                       tubeCurve: tubeCurve, roomIR: roomIR,
                       // The meters are painted from the rAF loop, which a
                       // headless or backgrounded page never runs. Exposing
                       // the painter lets the level path be driven and read
                       // without a compositor.
                       paintMeters: function () { paintMeters(); },
                       renderMasterBuffer: function () { return renderMasterBuffer(); },
                       meters: function () { return live && live.meters; },
                       state: function () { return state; },
                       stems: function () { return stems; },
                       addStem: function (s) {
                         stems.push(s); renderStems(); syncDeckInfo();
                         cnvPlanText(); cnvShowPeak(); tkEnable();
                         tkPlanText(); ldnEnable();
                       },
                       stemGainValue: stemGainValue,
                       modOn: modOn, voiceChain: voiceChain,
                       zoneBands: zoneBands, zoneTrim: zoneTrim,
                       setLane: function (i) { selLane = i; syncZoneUI(); },
                       lanes: LANES, applyState: applyState,
                       seek: seek, playPos: playPos, duration: duration,
                       renderWave: renderWave, bands: EQ_BANDS,
                       refState: function () {
                         return {loaded: !!refBuffer, mode: refMode,
                                 spec: !!refSpec};
                       },
                       cnvPlanText: cnvPlanText,
                       loudness: function () { return ldnLast; },
                       ldnEnable: ldnEnable,
                       valves: function () { return state.valves; },
                       valveGlow: function () {
                         var out = {};
                         VALVE_KEYS.forEach(function (k) {
                           out[k] = valveEls[k] ? valveEls[k].glow : null;
                         });
                         return out;
                       },
                       paintValves: paintValves,
                       variMuTrim: function () { return variMuTrim; },
                       measureVariMu: measureVariMu,
                       syncValveUI: syncValveUI,
                       tkState: function () {
                         return {tempo: tkTempo, semis: tkSemis,
                                 cents: tkCents, found: tkFound};
                       },
                       setRef: function (buf) {
                         refBuffer = buf; refSpec = null;
                         if (refBtn) refBtn.disabled = false;
                       }};
  syncAll();
  renderStems();
  paintCabView();
  syncValveUI();
  // Warm the vari-mu trim for the default setting, so the first time V6 is
  // switched on it is already level-matched rather than a frame late.
  measureVariMu(0.45, function () { if (live) { voiceValves(live.valves); } });
  updateGlow();
  resetCompare();
  syncModButtons();
  draw();
  measureCost();   // once; see the note above measureCost

  // Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z, but never while somebody is typing in
  // a field — the browser's own undo belongs to the text box.
  document.addEventListener("keydown", function (e) {
    var t = e.target || {};
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || "") || t.isContentEditable;
    if (typing || !(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
    e.preventDefault();
    if (e.shiftKey) histRedo(); else histUndo();
  });


  /* ---------- the manual drawer ----------
     The printed manual, in the drawer under the amp. Nothing in it is a
     second copy that can drift: the signal path is read from the patch the
     moment the drawer opens, and the unit pages are CLONES of the explain
     cards on the units themselves - one source of truth, two places to
     read it. */
  (function manualDrawer() {
    var toggle = document.getElementById("rk-man-toggle");
    var body = document.getElementById("rk-man-body");
    if (!toggle || !body) return;
    function renderManual() {
      var path = document.getElementById("rk-man-path");
      if (path) {
        path.textContent = "In \u203a " + patchOrder().map(function (k) { return PATCH_LABELS[k]; }).join(" \u203a ") + " \u203a Out";
      }
      var units = document.getElementById("rk-man-units");
      if (!units) return;
      units.innerHTML = "";
      document.querySelectorAll("#sb14, .chassis .ru").forEach(function (sec) {
        var tag = sec.querySelector(".ru-tag"), title = sec.querySelector(".ru-title");
        var prose = sec.querySelector(".ru-explain .ru-ex-prose");
        if (!tag || !title || !prose) return;
        var page = document.createElement("div");
        page.className = "rk-man-page";
        var head = document.createElement("div");
        head.className = "rk-man-head";
        head.setAttribute("role", "heading"); head.setAttribute("aria-level", "4");
        head.textContent = tag.textContent.trim() + " \u00b7 " + title.textContent.trim();
        page.appendChild(head);
        page.appendChild(prose.cloneNode(true));
        units.appendChild(page);
      });
    }
    toggle.addEventListener("click", function () {
      var open = body.hidden;
      if (open) renderManual();
      body.hidden = !open;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !body.hidden) {
        body.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  })();


  /* ---------- BOUNCE: render once, measure THAT render, hand over the file ----------
     The page could already export a WAV, measure loudness, and convert
     formats - but each of those rendered the rack again, so the numbers on
     screen described a different pass than the file you kept. This renders
     once and everything downstream reads that one buffer: the LUFS, the
     true peak, the target table and the bytes you download are all the
     same audio. It honours the patch order and the sidechain because it
     goes through renderMasterBuffer, the same path the old export used.

     Rate changes and the lossy formats stay in SB-12, which is built for
     them; this bounces what the rack is playing, at its own rate. */
  (function bounceModal() {
    var back = document.getElementById("rk-bnc-back");
    if (!back || !document.getElementById("rk-export")) return;
    var bodyEl = document.getElementById("rk-bnc-body");
    var statusEl2 = document.getElementById("rk-bnc-status");
    var srcEl = document.getElementById("rk-bnc-src");
    var planEl = document.getElementById("rk-bnc-plan");
    var doneEl = document.getElementById("rk-bnc-done");
    var rendered = null, measured = null, lastFocus = null, busy = false;
    var fmt = "wav", depth = 24;

    function say(t) { statusEl2.textContent = t || ""; }
    function n1(v, suffix) { return v === null || v === undefined ? "\u2014" : v.toFixed(1) + (suffix || ""); }

    function segs(wrap, items, current, pick) {
      wrap.innerHTML = "";
      items.forEach(function (it) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "sw" + (it.value === current ? " sw-lit" : "");
        b.textContent = it.label;
        b.setAttribute("aria-pressed", it.value === current ? "true" : "false");
        b.addEventListener("click", function () { pick(it.value); });
        wrap.appendChild(b);
      });
    }

    function renderChoices() {
      var specs = window.SBAudioConv ? window.SBAudioConv.FORMATS : null;
      var containers = [{value: "wav", label: "WAV"}, {value: "aiff", label: "AIFF"}];
      segs(document.getElementById("rk-bnc-fmt"), containers, fmt, function (v) {
        fmt = v;
        // AIFF here is 16 or 24; a 32-bit float AIFF is not what this writes.
        if (fmt === "aiff" && depth === 32) depth = 24;
        renderChoices(); planText();
      });
      var depths = (specs && specs[fmt] ? specs[fmt].depths : [16, 24]).map(function (d) {
        return {value: d, label: d === 32 ? "32f" : String(d)};
      });
      segs(document.getElementById("rk-bnc-depth"), depths, depth, function (v) {
        depth = v; renderChoices(); planText();
      });
      var dw = document.getElementById("rk-bnc-dither-wrap");
      if (dw) { dw.hidden = depth !== 16; }
    }

    function planText() {
      if (!rendered) { planEl.textContent = ""; return; }
      var dither = depth === 16 && document.getElementById("rk-bnc-dither").checked;
      var bytes = rendered.length * rendered.numberOfChannels * (depth === 32 ? 4 : depth / 8);
      planEl.textContent = fmt.toUpperCase() + " \u00b7 " + depth + (depth === 32 ? "-bit float" : "-bit") +
        " \u00b7 " + rendered.sampleRate + " Hz \u00b7 " +
        (rendered.numberOfChannels === 1 ? "mono" : "stereo") + " \u00b7 " +
        (bytes / 1048576).toFixed(1) + " MB" + (dither ? " \u00b7 TPDF dither" : "");
    }

    function paintTargets() {
      var wrap = document.getElementById("rk-bnc-targets");
      wrap.innerHTML = "";
      if (!measured || measured.integrated === null || !window.SBLoudness) return;
      window.SBLoudness.TARGETS.forEach(function (t) {
        var a = window.SBLoudness.againstTarget(measured.integrated, measured.truePeak, t);
        var row = document.createElement("div");
        row.className = "rk-bnc-row" + (a.clipsIfRaised ? " is-clip" : a.over ? " is-over" : a.under ? " is-under" : " is-ok");
        var name = document.createElement("span");
        name.className = "bn-name"; name.textContent = a.name;
        var tgt = document.createElement("span");
        tgt.className = "bn-t"; tgt.textContent = a.lufs + " LUFS \u00b7 ceiling " + a.ceiling;
        var d = document.createElement("span");
        d.className = "bn-d";
        d.textContent = a.delta === null ? "\u2014"
          : a.clipsIfRaised ? "would clip if raised " + n1(a.gain, " dB")
          : a.over ? "they turn it down " + n1(-a.gain, " dB")
          : a.under ? "they leave it \u2014 " + n1(Math.abs(a.delta), " LU under")
          : "on target";
        row.appendChild(name); row.appendChild(tgt); row.appendChild(d);
        wrap.appendChild(row);
      });
    }

    function measure(buf) {
      var chans = [];
      for (var c = 0; c < buf.numberOfChannels; c++) chans.push(buf.getChannelData(c));
      return window.SBLoudness.analyse(chans, buf.sampleRate);
    }

    function start() {
      busy = true; rendered = null; measured = null;
      bodyEl.hidden = true; doneEl.textContent = "";
      say("Rendering the rack\u2026");
      srcEl.textContent = stems.length ? stems.length + " stems \u00b7 " + patchOrder().length + " units"
                                       : (loadedName || "loaded track") + " \u00b7 " + patchOrder().length + " units";
      renderMasterBuffer().then(function (buf) {
        rendered = buf;
        say("Measuring that render\u2026");
        return new Promise(function (r) { setTimeout(function () { r(measure(buf)); }, 30); });
      }).then(function (res) {
        measured = res;
        document.getElementById("rk-bnc-i").textContent = n1(res.integrated);
        document.getElementById("rk-bnc-tp").textContent = res.truePeak === null ? "\u2014" : res.truePeak.toFixed(2);
        document.getElementById("rk-bnc-lra").textContent = n1(res.range);
        paintTargets(); renderChoices(); planText();
        bodyEl.hidden = false;
        say(res.integrated === null ? "Too short to measure \u2014 loudness needs at least 400 ms. The file is still yours to take." : "");
        busy = false;
      }).catch(function (e) {
        busy = false;
        say("That render failed: " + (e && e.message ? e.message : e));
      });
    }

    function openBnc() {
      if (!buffer && !stems.length) return;
      lastFocus = document.activeElement;
      back.hidden = false;
      document.getElementById("rk-bnc-x").focus();
      start();
    }
    function closeBnc() {
      back.hidden = true;
      rendered = null; measured = null;      // never hand back a stale render
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    document.getElementById("rk-bnc-x").addEventListener("click", closeBnc);
    back.addEventListener("click", function (e) { if (e.target === back) closeBnc(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !back.hidden) closeBnc();
    });
    document.getElementById("rk-bnc-dither").addEventListener("change", planText);

    document.getElementById("rk-bnc-go").addEventListener("click", function () {
      if (!rendered || busy) return;
      var chans = [];
      for (var c = 0; c < rendered.numberOfChannels; c++) chans.push(rendered.getChannelData(c));
      var dither = depth === 16 && document.getElementById("rk-bnc-dither").checked;
      var bytes = window.SBAudioConv.encode(fmt, chans, rendered.sampleRate, depth, {dither: dither});
      var a = document.createElement("a");
      a.download = (loadedName || (stems.length ? "rack-stem-bounce" : "rack-processed")) + "." + fmt;
      a.href = URL.createObjectURL(new Blob([bytes], {type: fmt === "wav" ? "audio/wav" : "audio/aiff"}));
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
      doneEl.textContent = "Bounced \u2014 the file matches the numbers above.";
    });

    var vault = document.getElementById("rk-bnc-vault");
    if (vault) vault.addEventListener("click", function () {
      var v = document.getElementById("rk-vault");
      if (v) { closeBnc(); v.click(); }
    });

    /* BOTH export buttons open this - the one on SB-07 and its twin in the
       power strip. Two buttons with the same word on them must do the same
       thing, and the straight-to-WAV download they used to do is now the
       Bounce button inside, one render later and with the numbers to go
       with it. Capture phase, so the old handlers never fire. */
    var intercepting = true;
    ["rk-export", "rk-export2"].forEach(function (id) {
      var b = document.getElementById(id);
      if (!b) return;
      b.addEventListener("click", function (e) {
        if (b.disabled || !intercepting) return;
        /* Fail safe: Export worked before this modal existed and must keep
           working if the modal ever throws. Only swallow the old handler
           once this one has actually opened; if anything goes wrong, stop
           intercepting for the rest of the session and let the original
           straight-to-WAV export run. */
        try {
          openBnc();
        } catch (err) {
          intercepting = false;
          try { back.hidden = true; } catch (e2) {}
          return;                       // the old export handler runs next
        }
        e.stopImmediatePropagation();
        e.preventDefault();
      }, true);
    });
  })();

  (function wireHistoryUi() {
    // Seed the baseline HERE rather than lazily on the first applyState.
    // applyState is not called during boot, so the lazy version consumed
    // the user's first real change as the starting point and that change
    // could never be undone.
    if (hist.prev === null) { hist.prev = snap(); hist.label = ""; }
    var u = document.getElementById("rk-undo"), r = document.getElementById("rk-redo");
    var btn = document.getElementById("rk-hist-btn"), pop = document.getElementById("rk-hist-pop");
    if (u) u.addEventListener("click", histUndo);
    if (r) r.addEventListener("click", histRedo);
    if (btn && pop) {
      btn.addEventListener("click", function () {
        var open = pop.hidden;
        pop.hidden = !open;
        btn.setAttribute("aria-expanded", open ? "true" : "false");
      });
      document.addEventListener("click", function (e) {
        if (!pop.hidden && !pop.contains(e.target) && e.target !== btn) closeHistory();
      });
      document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeHistory(); });
    }
    paintHistory();
  })();
})();
