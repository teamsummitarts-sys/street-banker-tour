/* Light Studio engine — the parts with no DOM, no Web Audio and no serial
   port, so they can be proved in Node (tests/js/check_lights.js) the same
   way the rack's DSP is: groups, the fade/lighting resolver, the ENTTEC
   DMX framing, waveform peaks, onset/BPM detection, beat snapping and
   the timecode formatter. lights.js is the browser around this. */
(function (root, factory) {
  if (typeof module === "object" && module.exports) { module.exports = factory(); }
  else { root.LightsEngine = factory(); }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // ---------- groups ----------
  function membersOf(group, bars) {
    var out = [], i;
    group = group || "all";
    if (group === "all") { for (i = 1; i <= bars; i++) out.push(i); }
    else if (group === "odd") { for (i = 1; i <= bars; i += 2) out.push(i); }
    else if (group === "even") { for (i = 2; i <= bars; i += 2) out.push(i); }
    else if (group.indexOf("pair") === 0) {
      var k = parseInt(group.slice(4), 10);
      if (k >= 1 && k <= Math.floor(bars / 2)) out.push(k, bars + 1 - k);
      if (bars % 2 && k === Math.ceil(bars / 2)) out.push(k);
    } else if (group.indexOf("+") > 0) {
      // custom pick: "b1+b3+b6" — built by shift-clicking bars on the stage
      group.split("+").forEach(function (part) {
        var m = parseInt(part.replace(/^b/, ""), 10);
        if (m >= 1 && m <= bars && out.indexOf(m) < 0) out.push(m);
      });
      out.sort(function (a, b) { return a - b; });
    } else if (group.indexOf("b") === 0) {
      var n = parseInt(group.slice(1), 10);
      if (n >= 1 && n <= bars) out.push(n);
    }
    return out;
  }
  function customGroup(members) {
    // Canonical key for a hand-picked set of bars; one bar collapses to
    // its plain "bN" group, an empty pick to "all".
    var m = (members || []).filter(function (n, i, a) { return n >= 1 && a.indexOf(n) === i; }).sort(function (a, b) { return a - b; });
    if (!m.length) return "all";
    if (m.length === 1) return "b" + m[0];
    return m.map(function (n) { return "b" + n; }).join("+");
  }
  function toggleInGroup(group, bar, bars) {
    var mem = membersOf(group, bars), i = mem.indexOf(bar);
    if (i >= 0) mem.splice(i, 1); else mem.push(bar);
    return customGroup(mem);
  }
  function groupOptions(bars) {
    var opts = [["all", "All bars", "Every bar together"],
                ["odd", "Odd side", "Bars 1, 3, 5… — one side of a split look"],
                ["even", "Even side", "Bars 2, 4, 6… — the other side"]];
    for (var k = 1; k <= Math.ceil(bars / 2); k++) {
      var partner = bars + 1 - k;
      opts.push(["pair" + k, "Pair " + k,
                 partner === k ? "The centre bar on its own" : "Bars " + k + " & " + partner + ", outermost in"]);
    }
    for (var n = 1; n <= bars; n++) opts.push(["b" + n, "Bar " + n, "Just this one"]);
    return opts;
  }
  function groupLabel(group, bars) {
    var opts = groupOptions(bars);
    for (var i = 0; i < opts.length; i++) if (opts[i][0] === group) return opts[i][1];
    if ((group || "").indexOf("+") > 0) return "Bars " + membersOf(group, bars).join(" + ");
    return group;
  }
  function mirrorOf(bar, bars) {
    var m = bars + 1 - bar;
    return m === bar ? null : m;
  }

  function hexRgb(hex) {
    var m = /^#?([0-9a-f]{6})$/i.exec(hex || "#000000");
    var v = parseInt(m ? m[1] : "000000", 16);
    return [v >> 16 & 255, v >> 8 & 255, v & 255];
  }
  function isBlackout(cue) {
    return !cue.intensity || hexRgb(cue.color).join(",") === "0,0,0";
  }
  function rgbHex(rgb) {
    return "#" + rgb.map(function (v) {
      var n = Math.max(0, Math.min(255, Math.round(v || 0))).toString(16);
      return n.length < 2 ? "0" + n : n;
    }).join("");
  }
  // RGB <-> HSV. The picker keeps both in step, so a designer can reach for
  // whichever they think in. V is the colour's own brightness - never the
  // fixture's output, which stays the cue's intensity.
  function rgbToHsv(rgb) {
    var r = (rgb[0] || 0) / 255, g = (rgb[1] || 0) / 255, b = (rgb[2] || 0) / 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
    var h = 0;
    if (d) {
      if (max === r) h = ((g - b) / d + (g < b ? 6 : 0));
      else if (max === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h *= 60;
    }
    return [Math.round(h), Math.round(max ? (d / max) * 100 : 0), Math.round(max * 100)];
  }
  function hsvToRgb(hsv) {
    var h = ((hsv[0] % 360) + 360) % 360, s = Math.max(0, Math.min(100, hsv[1])) / 100,
        v = Math.max(0, Math.min(100, hsv[2])) / 100;
    var c = v * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c;
    var p = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
          : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
    return p.map(function (n) { return Math.round((n + m) * 255); });
  }

  // ---------- lighting resolver ----------
  function lightingAt(show, t) {
    // Per fixture: latest cue at or before t, faded in from the look before it.
    var bars = show.bars, out = [];
    var sorted = (show.cues || []).slice().sort(function (a, b) { return a.t - b.t; });
    for (var f = 1; f <= bars; f++) {
      var seq = sorted.filter(function (c) {
        return membersOf(c.group, bars).indexOf(f) >= 0;
      });
      // A cue fades from WHAT IS ON STAGE, not from the previous cue's
      // declared target. Those differ whenever a cue lands before the fade
      // under it has finished - which the shipped looks and auto-cue do
      // routinely (a 2 s intro fade with a hard stop inside it). Reading the
      // target instead made the rig jump to full brightness at the instant
      // the new cue fired, then fade from there. So walk the sequence and
      // carry the rendered state forward.
      var cur = null, from = {rgb: [0, 0, 0], inten: 0};
      for (var i = 0; i < seq.length; i++) {
        if (seq[i].t > t) break;
        if (cur) {
          // render the cue we are leaving, at the moment the next one fires
          var kp = Math.min(1, (seq[i].t - cur.t) / Math.max(0.01, cur.fade || 0.01));
          var tp = {rgb: hexRgb(cur.color), inten: (cur.intensity || 0) / 100};
          from = {
            rgb: [0, 1, 2].map(function (ci) {
              return from.rgb[ci] + (tp.rgb[ci] - from.rgb[ci]) * kp;
            }),
            inten: from.inten + (tp.inten - from.inten) * kp
          };
        }
        cur = seq[i];
      }
      if (!cur) { out.push({rgb: [0, 0, 0], inten: 0}); continue; }
      var target = {rgb: hexRgb(cur.color), inten: (cur.intensity || 0) / 100};
      var k = Math.min(1, (t - cur.t) / Math.max(0.01, cur.fade || 0.01));
      var inten = from.inten + (target.inten - from.inten) * k;
      if (cur.move) inten *= movementGain(cur, f, t, show, bars);
      out.push({
        rgb: [0, 1, 2].map(function (ci) {
          return Math.round(from.rgb[ci] + (target.rgb[ci] - from.rgb[ci]) * k);
        }),
        inten: inten
      });
    }
    return out;
  }
  // Movement hints are part of a cue's INTENT and are compiled per rig at
  // runtime: the same "chase" runs across 4 bars or 8. Beat-locked when
  // the show has a tempo, 120 BPM otherwise. rate = cycles per beat.
  var MOVES = [["", "Still"], ["pulse", "Pulse"], ["strobe", "Strobe"], ["chase", "Chase"]];
  function movementGain(cue, fixture, t, show, bars) {
    var bpm = show.bpm || 120, period = 60 / bpm, rate = cue.rate > 0 ? cue.rate : 1;
    var phase = Math.max(0, t - cue.t) / period * rate, frac = phase - Math.floor(phase);
    if (cue.move === "strobe") return frac < 0.35 ? 1 : 0;
    if (cue.move === "pulse") return 0.3 + 0.7 * (0.5 + 0.5 * Math.cos(2 * Math.PI * frac));
    if (cue.move === "chase") {
      var mem = membersOf(cue.group, bars), n = mem.length, idx = mem.indexOf(fixture);
      if (n < 2 || idx < 0) return 1;
      return (Math.floor(phase) % n) === idx ? 1 : 0.12;
    }
    return 1;
  }

  // ---------- rig profiles ----------
  // A rig is bar count + fixture type + layout + patch. Shows store
  // intents (looks, group roles, movement), so the same show compiles onto
  // any rig — swap the profile and the cues re-render.
  var RIG_PRESETS = [
    {key: "dive4", name: "Dive bar 4-bar", bars: 4, chans: 3, dmxStart: 1, rot: {},
     pos: {"1": [0.2, 0.14], "2": [0.8, 0.14], "3": [0.32, 0.8], "4": [0.68, 0.8]}},
    {key: "club8", name: "Club 8-bar", bars: 8, chans: 4, dmxStart: 1, rot: {}, pos: null},
    {key: "fest6", name: "Festival side-stick", bars: 6, chans: 4, dmxStart: 1, rot: {"1": 90, "6": 90},
     pos: {"1": [0.06, 0.5], "2": [0.3, 0.12], "3": [0.5, 0.12], "4": [0.7, 0.12], "5": [0.5, 0.8], "6": [0.94, 0.5]}}
  ];
  function copyMap(m) { var o = {}; Object.keys(m || {}).forEach(function (k) { o[k] = Array.isArray(m[k]) ? m[k].slice() : m[k]; }); return o; }

  // Same look, different rig. "all"/"odd"/"even" are roles and need no
  // translation; anything that names a bar is a POSITION on the stage, so
  // it is remapped proportionally instead of firing nothing. Bar N of F
  // sits at (N-0.5)/F across; the bar covering that spot on the new rig
  // is ceil(pos * T).
  function remapGroup(group, fromBars, toBars) {
    group = group || "all";
    if (fromBars === toBars || group === "all" || group === "odd" || group === "even") return group;
    function scale(n, fromN, toN) { return Math.max(1, Math.min(toN, Math.ceil((n - 0.5) / fromN * toN))); }
    if (group.indexOf("+") > 0) return customGroup(membersOf(group, fromBars).map(function (n) { return scale(n, fromBars, toBars); }));
    if (group.indexOf("pair") === 0) {
      var k = parseInt(group.slice(4), 10);
      if (!(k >= 1)) return "all";
      return "pair" + scale(k, Math.ceil(fromBars / 2), Math.ceil(toBars / 2));
    }
    if (group.charAt(0) === "b") {
      var n = parseInt(group.slice(1), 10);
      if (!(n >= 1)) return "all";
      return "b" + scale(n, fromBars, toBars);
    }
    return group;
  }
  function remapCues(cues, fromBars, toBars) {
    return (cues || []).map(function (c) {
      var d = {}; Object.keys(c).forEach(function (k) { d[k] = c[k]; });
      d.group = remapGroup(c.group, fromBars, toBars);
      return d;
    });
  }

  function applyRig(show, rig) {
    var fromBars = show.bars || 6;
    show.bars = Math.max(2, Math.min(10, parseInt(rig.bars, 10) || 6));
    show.chans = rig.chans === 3 ? 3 : 4;
    show.pos = copyMap(rig.pos); show.rot = copyMap(rig.rot);
    show.dmxStart = Math.max(1, Math.min(512, parseInt(rig.dmxStart, 10) || 1));
    show.dmxAddr = copyMap(rig.dmxAddr);
    show.rigKey = rig.key || rig.id || null; show.rigName = rig.name || "";
    if (show.bars !== fromBars) show.cues = remapCues(show.cues, fromBars, show.bars);
    return show;
  }
  function rigFromShow(show, name) {
    return {name: name || show.rigName || "Custom rig", bars: show.bars, chans: show.chans, pos: copyMap(show.pos), rot: copyMap(show.rot),
            dmxStart: show.dmxStart || 1, dmxAddr: copyMap(show.dmxAddr)};
  }
  function venueKey(name) { return String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); }

  // ---------- output scaling: grand master + panic ----------
  function scaleLooks(looks, master, panic) {
    // master 0..1 multiplies every intensity; panic forces everything off.
    // Pure: returns new look objects, never touches the resolver output.
    var m = panic ? 0 : Math.max(0, Math.min(1, master == null ? 1 : master));
    return looks.map(function (l) { return {rgb: l.rgb.slice(), inten: l.inten * m}; });
  }

  // ---------- DMX patch ----------
  function fixtureAddress(show, bar) {
    // Start address of a bar: an explicit per-bar patch wins, otherwise
    // fixtures run from the first address one after another.
    var chans = show.chans === 3 ? 3 : 4, first = parseInt(show.dmxStart, 10) || 1;
    var own = show.dmxAddr && show.dmxAddr[String(bar)];
    var a = parseInt(own, 10);
    if (!(a >= 1)) a = first + (bar - 1) * chans;
    return Math.max(1, Math.min(512, a));
  }
  function patchOverlaps(show) {
    // Pairs of bars whose channel ranges collide — worth a warning, not a block.
    var chans = show.chans === 3 ? 3 : 4, ranges = [], hits = [];
    for (var i = 1; i <= show.bars; i++) { var a = fixtureAddress(show, i); ranges.push([i, a, a + chans - 1]); }
    for (var x = 0; x < ranges.length; x++) for (var y = x + 1; y < ranges.length; y++) {
      if (ranges[x][1] <= ranges[y][2] && ranges[y][1] <= ranges[x][2]) hits.push([ranges[x][0], ranges[y][0]]);
    }
    return hits;
  }

  // ---------- ENTTEC USB Pro framing ----------
  function dmxFrame(show, looks) {
    var data = new Uint8Array(513);        // start code + 512 channels
    var chans = show.chans === 3 ? 3 : 4;
    looks.forEach(function (look, idx) {
      var ch = fixtureAddress(show, idx + 1);
      if (ch + chans - 1 > 512) return;     // patched off the end of the universe: skip, never wrap
      if (chans === 4) {
        data[ch++] = Math.round(look.inten * 255);
        data[ch++] = look.rgb[0]; data[ch++] = look.rgb[1]; data[ch++] = look.rgb[2];
      } else {
        data[ch++] = Math.round(look.rgb[0] * look.inten);
        data[ch++] = Math.round(look.rgb[1] * look.inten);
        data[ch++] = Math.round(look.rgb[2] * look.inten);
      }
    });
    var len = data.length;
    var pkt = new Uint8Array(5 + len);
    pkt[0] = 0x7E; pkt[1] = 6; pkt[2] = len & 255; pkt[3] = len >> 8;
    pkt.set(data, 4); pkt[4 + len] = 0xE7;
    return pkt;
  }

  // ---------- network DMX: Art-Net and sACN (E1.31) ----------
  // A browser cannot open a UDP socket, so these build the exact datagram a
  // local bridge forwards verbatim. Keeping the packet building here means
  // it is pure, unit-tested against the published packet layouts, and the
  // bridge stays a dumb pipe with no protocol knowledge of its own.

  function dmxData(show, looks) {
    /* The 512-slot universe (no start code) that both protocols carry. */
    var data = new Uint8Array(512);
    var chans = show.chans === 3 ? 3 : 4;
    looks.forEach(function (look, idx) {
      var ch = fixtureAddress(show, idx + 1);       // 1-based DMX address
      if (ch + chans - 1 > 512) return;             // off the end: skip, never wrap
      var i = ch - 1;
      if (chans === 4) {
        data[i] = Math.round(look.inten * 255);
        data[i + 1] = look.rgb[0]; data[i + 2] = look.rgb[1]; data[i + 3] = look.rgb[2];
      } else {
        data[i] = Math.round(look.rgb[0] * look.inten);
        data[i + 1] = Math.round(look.rgb[1] * look.inten);
        data[i + 2] = Math.round(look.rgb[2] * look.inten);
      }
    });
    return data;
  }

  // Art-Net 4, ArtDmx (OpOutput 0x5000). Opcode and ProtVer are the two
  // fields people get backwards: opcode is LITTLE endian, everything else
  // that is 16-bit here is big endian.
  var ARTNET_ID = [0x41, 0x72, 0x74, 0x2D, 0x4E, 0x65, 0x74, 0x00];   // "Art-Net\0"

  function artnetPacket(show, looks, opts) {
    opts = opts || {};
    var data = dmxData(show, looks);
    var universe = Math.max(0, Math.min(32767, parseInt(opts.universe, 10) || 0));
    var pkt = new Uint8Array(18 + data.length);
    pkt.set(ARTNET_ID, 0);
    pkt[8] = 0x00; pkt[9] = 0x50;                  // OpDmx, little endian
    pkt[10] = 0; pkt[11] = 14;                     // ProtVer 14, big endian
    pkt[12] = (opts.sequence || 0) & 0xFF;         // 0 = sequencing disabled
    pkt[13] = 0;                                   // Physical
    pkt[14] = universe & 0xFF;                     // SubUni
    pkt[15] = (universe >> 8) & 0xFF;              // Net
    pkt[16] = (data.length >> 8) & 0xFF;           // LengthHi
    pkt[17] = data.length & 0xFF;                  // LengthLo
    pkt.set(data, 18);
    return pkt;
  }

  var ACN_PID = [0x41, 0x53, 0x43, 0x2D, 0x45, 0x31, 0x2E, 0x31, 0x37, 0x00, 0x00, 0x00];

  function sacnPacket(show, looks, opts) {
    /* E1.31 data packet: root layer + framing layer + DMP layer. */
    opts = opts || {};
    var data = dmxData(show, looks);
    var universe = Math.max(1, Math.min(63999, parseInt(opts.universe, 10) || 1));
    var priority = Math.max(0, Math.min(200, opts.priority == null ? 100 : opts.priority));
    var cid = opts.cid && opts.cid.length === 16 ? opts.cid : defaultCid();
    var propCount = data.length + 1;               // start code + slots
    var pkt = new Uint8Array(126 + data.length);
    var v = new DataView(pkt.buffer);

    // --- root layer
    v.setUint16(0, 0x0010);                        // preamble size
    v.setUint16(2, 0x0000);                        // postamble size
    pkt.set(ACN_PID, 4);
    v.setUint16(16, 0x7000 | (pkt.length - 16));   // flags 0x7 + length
    v.setUint32(18, 0x00000004);                   // VECTOR_ROOT_E131_DATA
    pkt.set(cid, 22);

    // --- framing layer
    v.setUint16(38, 0x7000 | (pkt.length - 38));
    v.setUint32(40, 0x00000002);                   // VECTOR_E131_DATA_PACKET
    var name = String(opts.sourceName || "Street Banker Light Studio");
    for (var i = 0; i < 63 && i < name.length; i++) pkt[44 + i] = name.charCodeAt(i) & 0x7F;
    v.setUint8(108, priority);
    v.setUint16(109, 0);                           // synchronization address
    v.setUint8(111, (opts.sequence || 0) & 0xFF);
    v.setUint8(112, 0);                            // options
    v.setUint16(113, universe);

    // --- DMP layer
    v.setUint16(115, 0x7000 | (pkt.length - 115));
    v.setUint8(117, 0x02);                         // VECTOR_DMP_SET_PROPERTY
    v.setUint8(118, 0xA1);                         // address type & data type
    v.setUint16(119, 0x0000);                      // first property address
    v.setUint16(121, 0x0001);                      // address increment
    v.setUint16(123, propCount);
    v.setUint8(125, 0x00);                         // DMX start code
    pkt.set(data, 126);
    return pkt;
  }

  var _cid = null;
  function defaultCid() {
    /* A stable per-session component id. Receivers use it to tell sources
       apart; it only has to be unique, not meaningful. */
    if (_cid) return _cid;
    _cid = new Uint8Array(16);
    if (typeof crypto !== "undefined" && crypto.getRandomValues) crypto.getRandomValues(_cid);
    else for (var i = 0; i < 16; i++) _cid[i] = Math.floor(Math.random() * 256);
    _cid[6] = (_cid[6] & 0x0F) | 0x40;             // UUID v4 shape
    _cid[8] = (_cid[8] & 0x3F) | 0x80;
    return _cid;
  }

  var OUTPUTS = [
    ["preview", "Preview only", "Nothing leaves this machine."],
    ["enttec", "ENTTEC USB", "Direct over Web Serial (Chrome/Edge, desktop)."],
    ["artnet", "Art-Net node", "Via the local bridge, UDP 6454."],
    ["sacn", "sACN / E1.31", "Via the local bridge, UDP 5568."]
  ];

  // ---------- timecode ----------
  function fmtClock(t) {
    var m = Math.floor(t / 60), s = (t - m * 60);
    return m + ":" + (s < 10 ? "0" : "") + s.toFixed(1);
  }
  function fmtTimecode(t) {
    // M:SS.hh — what the big transport digits show.
    t = Math.max(0, t || 0);
    var m = Math.floor(t / 60), s = Math.floor(t - m * 60), h = Math.floor((t - m * 60 - s) * 100);
    return m + ":" + (s < 10 ? "0" : "") + s + "." + (h < 10 ? "0" : "") + h;
  }

  // ---------- waveform peaks ----------
  function peaks(channel, sampleRate, startSec, endSec, buckets) {
    // Max and min sample per horizontal bucket of the visible window.
    var n = channel.length;
    var s0 = Math.max(0, Math.floor(startSec * sampleRate));
    var s1 = Math.min(n, Math.ceil(endSec * sampleRate));
    var max = new Float32Array(buckets), min = new Float32Array(buckets);
    if (s1 <= s0 || buckets <= 0) return {max: max, min: min};
    var per = (s1 - s0) / buckets;
    var step = Math.max(1, Math.floor(per / 400));   // sample at most ~400 points per bucket
    for (var b = 0; b < buckets; b++) {
      var a = s0 + Math.floor(b * per), z = Math.min(s1, s0 + Math.floor((b + 1) * per));
      var hi = -1, lo = 1;
      if (z <= a) z = a + 1;
      for (var i = a; i < z && i < n; i += step) {
        var v = channel[i];
        if (v > hi) hi = v;
        if (v < lo) lo = v;
      }
      max[b] = hi === -1 ? 0 : hi; min[b] = lo === 1 ? 0 : lo;
    }
    return {max: max, min: min};
  }

  // ---------- onsets & tempo ----------
  function onsetEnvelope(mono, sampleRate, hop) {
    // Half-wave-rectified energy flux on short frames: a cheap onset
    // strength curve that is good enough to find a pulse.
    hop = hop || 512;
    var frames = Math.floor(mono.length / hop);
    var env = new Float32Array(frames);
    var prev = 0;
    for (var f = 0; f < frames; f++) {
      var e = 0, base = f * hop;
      for (var i = 0; i < hop; i++) { var v = mono[base + i]; e += v * v; }
      e = Math.sqrt(e / hop);
      env[f] = Math.max(0, e - prev);
      prev = e;
    }
    // normalise
    var mx = 0;
    for (var j = 0; j < frames; j++) if (env[j] > mx) mx = env[j];
    if (mx > 0) for (var k = 0; k < frames; k++) env[k] /= mx;
    return {env: env, hop: hop, rate: sampleRate / hop};
  }

  function detectBeats(mono, sampleRate, opts) {
    opts = opts || {};
    var minBpm = opts.minBpm || 60, maxBpm = opts.maxBpm || 200;
    var oe = onsetEnvelope(mono, sampleRate, opts.hop || 512);
    var env = oe.env, rate = oe.rate, n = env.length;
    if (n < rate * 4) return {bpm: 0, offset: 0, beats: [], confidence: 0};
    // autocorrelation over the lag range
    var minLag = Math.max(2, Math.floor(rate * 60 / maxBpm)), maxLag = Math.ceil(rate * 60 / minBpm);
    var best = 0, bestLag = 0, second = 0, ac = {};
    for (var lag = minLag - 1; lag <= maxLag + 1; lag++) {
      var s = 0;
      for (var i = lag; i < n; i++) s += env[i] * env[i - lag];
      // mild preference for lags near 120 BPM, like a listener's prior
      var bpmHere = 60 * rate / lag;
      var prior = Math.exp(-Math.pow(Math.log(bpmHere / 120), 2) / 0.8);
      s *= prior;
      ac[lag] = s;
      if (lag < minLag || lag > maxLag) continue;
      if (s > best) { second = best; best = s; bestLag = lag; }
      else if (s > second) second = s;
    }
    if (!bestLag) return {bpm: 0, offset: 0, beats: [], confidence: 0};
    // The true period is rarely a whole number of frames (120 BPM at 43 fps
    // is 21.5): refine the peak to a fraction of a lag by fitting a parabola
    // through its neighbours, else the tempo is off by a couple of percent.
    var l0 = ac[bestLag - 1] || 0, l1 = ac[bestLag], l2 = ac[bestLag + 1] || 0;
    var denom = l0 - 2 * l1 + l2;
    var frac = denom !== 0 ? 0.5 * (l0 - l2) / denom : 0;
    if (!(frac > -1 && frac < 1)) frac = 0;
    var lagF0 = bestLag + frac;
    var bpm = 60 * rate / lagF0;
    bpm = Math.round(bpm * 10) / 10;
    var period = 60 / bpm;                 // seconds
    // phase: which offset within one period lines up with the most onset energy
    var lagF = period * rate, bestOff = 0, bestSum = -1;
    var steps = Math.max(8, Math.round(lagF));
    for (var st = 0; st < steps; st++) {
      var off = st / steps * lagF, sum = 0;
      for (var p = off; p < n; p += lagF) sum += env[Math.floor(p)] || 0;
      if (sum > bestSum) { bestSum = sum; bestOff = off; }
    }
    var offset = bestOff / rate;
    var duration = mono.length / sampleRate;
    var beats = [];
    for (var b = offset; b < duration; b += period) beats.push(Math.round(b * 1000) / 1000);
    return {bpm: bpm, offset: Math.round(offset * 1000) / 1000, beats: beats,
            confidence: second > 0 ? Math.min(1, (best - second) / best + 0.2) : 1};
  }

  function snapToBeat(t, bpm, offset) {
    if (!bpm) return t;
    var period = 60 / bpm;
    var k = Math.round((t - (offset || 0)) / period);
    return Math.max(0, Math.round(((offset || 0) + k * period) * 1000) / 1000);
  }

  function tapTempo(taps) {
    // taps: ascending timestamps in seconds; BPM from the mean interval of
    // the last eight, ignoring gaps over two seconds (a new phrase).
    if (!taps || taps.length < 2) return 0;
    var recent = taps.slice(-8), ivs = [];
    for (var i = 1; i < recent.length; i++) {
      var d = recent[i] - recent[i - 1];
      if (d > 0.2 && d < 2) ivs.push(d);
    }
    if (!ivs.length) return 0;
    var mean = ivs.reduce(function (a, b) { return a + b; }, 0) / ivs.length;
    return Math.round(600 / mean) / 10;
  }

  function nearestCue(cues, t, tol) {
    var best = null, bd = tol;
    (cues || []).forEach(function (c) {
      var d = Math.abs(c.t - t);
      if (d <= bd) { bd = d; best = c; }
    });
    return best;
  }

  // ---------- track analysis: energy, bands, sections ----------
  function frameFeatures(mono, sampleRate, hop) {
    // Per frame: RMS energy plus low / mid / high band energies from two
    // one-pole filters run over the whole signal (cheap, no FFT, and
    // plenty to tell a verse from a chorus). Everything normalised to the
    // loudest frame.
    hop = hop || Math.round(sampleRate * 0.046);
    var n = mono.length, frames = Math.floor(n / hop);
    var energy = new Float32Array(frames), low = new Float32Array(frames), mid = new Float32Array(frames), high = new Float32Array(frames);
    var aL = Math.exp(-2 * Math.PI * 150 / sampleRate), aH = Math.exp(-2 * Math.PI * 3000 / sampleRate);
    var yL = 0, yH = 0, i, f;
    for (f = 0; f < frames; f++) {
      var base = f * hop, e = 0, el = 0, em = 0, eh = 0;
      for (i = 0; i < hop; i++) {
        var x = mono[base + i];
        yL = aL * yL + (1 - aL) * x;          // < ~150 Hz
        yH = aH * yH + (1 - aH) * x;          // < ~3 kHz
        var hi = x - yH, md = yH - yL;
        e += x * x; el += yL * yL; em += md * md; eh += hi * hi;
      }
      energy[f] = Math.sqrt(e / hop); low[f] = Math.sqrt(el / hop); mid[f] = Math.sqrt(em / hop); high[f] = Math.sqrt(eh / hop);
    }
    var mx = 0;
    for (f = 0; f < frames; f++) if (energy[f] > mx) mx = energy[f];
    if (mx > 0) for (f = 0; f < frames; f++) { energy[f] /= mx; low[f] /= mx; mid[f] /= mx; high[f] /= mx; }
    return {energy: energy, low: low, mid: mid, high: high, hop: hop, rate: sampleRate / hop, frames: frames};
  }

  function _meanVec(F, a, b) {
    var n = Math.max(1, b - a), v = [0, 0, 0, 0];
    for (var i = a; i < b; i++) { v[0] += F.energy[i]; v[1] += F.low[i]; v[2] += F.mid[i]; v[3] += F.high[i]; }
    return v.map(function (x) { return x / n; });
  }
  function _cosDist(a, b) {
    var d = 0, na = 0, nb = 0;
    for (var i = 1; i < a.length; i++) { d += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
    if (!na || !nb) return (na || nb) ? 1 : 0;
    return 1 - d / Math.sqrt(na * nb);
  }

  function detectSections(F, opts) {
    // Novelty = how different the next ~1.5 s sounds from the last ~1.5 s
    // (band balance + loudness). Peaks above mean + 1 sd, at least 6 s
    // apart, are boundaries. Sections are then labelled by relative
    // loudness and position: intro / verse / chorus / drop / breakdown /
    // bridge / outro, plus hard stops (near-silence inside the song).
    opts = opts || {};
    var W = Math.max(4, Math.round(F.rate * (opts.window || 1.5)));
    var minGap = Math.max(W, Math.round(F.rate * (opts.minGap || 6)));
    var n = F.frames, nov = new Float32Array(n), i;
    for (i = W; i < n - W; i++) {
      var A = _meanVec(F, i - W, i), B = _meanVec(F, i, i + W);
      nov[i] = _cosDist(A, B) + Math.abs(B[0] - A[0]);
    }
    var mean = 0, cnt = 0;
    for (i = W; i < n - W; i++) { mean += nov[i]; cnt++; }
    mean = cnt ? mean / cnt : 0;
    var sd = 0;
    for (i = W; i < n - W; i++) sd += (nov[i] - mean) * (nov[i] - mean);
    sd = cnt ? Math.sqrt(sd / cnt) : 0;
    var thr = mean + (opts.sigma || 1.0) * sd;
    var peaks = [];
    for (i = W + 1; i < n - W - 1; i++) {
      if (nov[i] >= thr && nov[i] >= nov[i - 1] && nov[i] >= nov[i + 1]) {
        if (peaks.length && i - peaks[peaks.length - 1] < minGap) {
          if (nov[i] > nov[peaks[peaks.length - 1]]) peaks[peaks.length - 1] = i;
        } else peaks.push(i);
      }
    }
    var bounds = [0].concat(peaks, [n]);
    // energy per section
    var secs = [];
    for (i = 0; i < bounds.length - 1; i++) {
      var a = bounds[i], b = bounds[i + 1];
      if (b - a < 1) continue;
      var v = _meanVec(F, a, b);
      secs.push({start: a / F.rate, end: b / F.rate, energy: v[0], low: v[1], high: v[3], f0: a, f1: b});
    }
    var emax = 0;
    secs.forEach(function (s) { if (s.energy > emax) emax = s.energy; });
    var duration = n / F.rate, chorusSeen = 0;
    secs.forEach(function (s, k) {
      var rel = emax ? s.energy / emax : 0;
      var prev = secs[k - 1];
      var label;
      if (rel >= 0.7) label = "chorus";
      else if (rel >= 0.38) label = "verse";
      else label = (k === 0) ? "intro" : (k === secs.length - 1 ? "outro" : "breakdown");
      if (k === 0 && label !== "intro" && s.end - s.start < 12 && rel < 0.9) label = "intro";
      if (k === secs.length - 1 && label === "breakdown") label = "outro";
      if (label === "chorus") {
        // a drop: arrives from something much quieter and hits within a second
        var jumpIn = prev && prev.energy < 0.6 * s.energy;
        var early = 0, cntE = 0;
        for (i = s.f0; i < Math.min(s.f1, s.f0 + Math.round(F.rate)); i++) { early += F.energy[i]; cntE++; }
        early = cntE ? early / cntE : 0;
        if (jumpIn && early >= 0.8 * s.energy && s.low > 0.2 * emax) label = "drop";
        chorusSeen++;
      } else if (label === "verse" && chorusSeen >= 2 && s.start / duration > 0.5 && s.start / duration < 0.88) {
        label = "bridge";
      }
      s.label = label; s.rel = rel;
    });
    // hard stops: near-silence for >= 0.6 s, not in the first or last 1.5 s
    var stops = [], quiet = Math.round(F.rate * 0.6), run = 0;
    for (i = 0; i < n; i++) {
      if (F.energy[i] < 0.03) { run++; if (run === quiet) { var st = (i - quiet + 1) / F.rate; if (st > 1.5 && st < duration - 1.5) stops.push({start: st}); } }
      else { if (run >= quiet && stops.length) stops[stops.length - 1].end = i / F.rate; run = 0; }
    }
    stops.forEach(function (s) { if (!s.end) s.end = duration; });
    return {sections: secs.map(function (s) { return {start: Math.round(s.start * 100) / 100, end: Math.round(s.end * 100) / 100, label: s.label, energy: Math.round(s.rel * 100) / 100}; }),
            stops: stops.map(function (s) { return {start: Math.round(s.start * 100) / 100, end: Math.round(s.end * 100) / 100}; }),
            novelty: nov, threshold: thr};
  }

  function analyzeTrack(mono, sampleRate, opts) {
    var F = frameFeatures(mono, sampleRate);
    var beats = detectBeats(mono, sampleRate, opts);
    var sec = detectSections(F, opts);
    return {bpm: beats.bpm, offset: beats.offset, beats: beats.beats, sections: sec.sections, stops: sec.stops,
            duration: mono.length / sampleRate, energy: F.energy, rate: F.rate};
  }

  // Section label -> look. Warm and dim going in, cold mids, full-stage
  // lifts, accents on drops, blackout on hard stops.
  var SECTION_LOOKS = {
    intro: {color: "#ffb347", intensity: 35, fade: 2.0, group: "all"},
    verse: {color: "#3b82f6", intensity: 55, fade: 1.0, group: "all"},
    chorus: {color: "#fff4d0", intensity: 100, fade: 0.4, group: "all"},
    drop: {color: "#ff2d2d", intensity: 100, fade: 0.0, group: "all"},
    breakdown: {color: "#8b5cf6", intensity: 40, fade: 1.5, group: "all"},
    bridge: {color: "#8b5cf6", intensity: 65, fade: 1.0, group: "all"},
    outro: {color: "#ffb347", intensity: 30, fade: 2.5, group: "all"}
  };

  function generateCues(analysis, opts) {
    // An editable first pass: one cue per section (snapped to the beat
    // grid when there is one), a three-beat odd/even/all accent burst on
    // a drop, and blackout + restore around every hard stop. Every cue
    // carries auto:true so the UI can badge it and clear the set.
    opts = opts || {};
    var bpm = analysis.bpm, off = analysis.offset || 0, out = [];
    function snap(t) { return bpm ? snapToBeat(t, bpm, off) : Math.round(t * 100) / 100; }
    analysis.sections.forEach(function (s, k) {
      var look = SECTION_LOOKS[s.label] || SECTION_LOOKS.verse;
      var t = k === 0 ? 0 : snap(s.start);
      out.push({t: t, group: look.group, color: look.color, intensity: look.intensity, fade: look.fade, note: s.label, auto: true});
      if (s.label === "drop") {
        var beat = bpm ? 60 / bpm : 0.5;
        var burst = [["odd", "#ffffff"], ["even", "#ffffff"], ["all", "#ff2d2d"]];
        burst.forEach(function (bst, j) {
          out.push({t: Math.round((t + beat * (j + 1)) * 100) / 100, group: bst[0], color: bst[1], intensity: 100, fade: 0.05, note: "drop accent", auto: true});
        });
        out.push({t: Math.round((t + beat * 4) * 100) / 100, group: "all", color: SECTION_LOOKS.chorus.color, intensity: 100, fade: 0.3, note: "drop settle", auto: true});
      }
    });
    (analysis.stops || []).forEach(function (st) {
      out.push({t: Math.round(st.start * 100) / 100, group: "all", color: "#000000", intensity: 0, fade: 0.1, note: "hard stop", auto: true});
      if (st.end && st.end < analysis.duration - 0.5) {
        // restore the look of the section the stop ends in
        var sec = null;
        analysis.sections.forEach(function (s) { if (s.start <= st.end && st.end < s.end) sec = s; });
        var look = SECTION_LOOKS[(sec && sec.label) || "verse"];
        out.push({t: Math.round(st.end * 100) / 100, group: "all", color: look.color, intensity: look.intensity, fade: 0.2, note: "back in", auto: true});
      }
    });
    out.sort(function (a, b) { return a.t - b.t; });
    // no two cues on the same group at the same instant
    var seen = {};
    return out.filter(function (c) { var k = c.group + "@" + c.t.toFixed(2); if (seen[k]) return false; seen[k] = 1; return true; });
  }

  // ---------- undo history ----------
  function makeHistory(cap, window_) {
    // Snapshot stack. push() takes the state BEFORE a change plus a
    // coalescing key: repeated pushes with the same key inside the window
    // (a slider being dragged, a note being typed) keep the first
    // snapshot and drop the rest, so one undo steps back over the whole
    // gesture. Redo is cleared by any new push.
    cap = cap || 50; window_ = window_ || 800;
    var undo = [], redo = [], lastKey = null, lastAt = -1e9;
    return {
      push: function (snapshot, key, now) {
        now = now || 0;
        if (key && key === lastKey && (now - lastAt) < window_) { lastAt = now; return false; }
        undo.push(snapshot); if (undo.length > cap) undo.shift();
        redo.length = 0; lastKey = key || null; lastAt = now; return true;
      },
      undo: function (current) { if (!undo.length) return null; redo.push(current); lastKey = null; return undo.pop(); },
      redo: function (current) { if (!redo.length) return null; undo.push(current); lastKey = null; return redo.pop(); },
      canUndo: function () { return undo.length > 0; },
      canRedo: function () { return redo.length > 0; },
      size: function () { return undo.length; },
      reset: function () { undo = []; redo = []; lastKey = null; lastAt = -1e9; }
    };
  }

  // The six that hold keys 1-6. Blackout stays distinct on 6.
  var LOOKS = [
    {key: "amber", name: "Amber wash", color: "#ffb347", intensity: 85, fade: 1.0},
    {key: "blue", name: "Cold blue", color: "#3b82f6", intensity: 80, fade: 1.0},
    {key: "red", name: "Red alert", color: "#ff2d2d", intensity: 90, fade: 0.3},
    {key: "white", name: "White full", color: "#ffffff", intensity: 100, fade: 0.2},
    {key: "violet", name: "Violet haze", color: "#8b5cf6", intensity: 70, fade: 1.5},
    {key: "blackout", name: "Blackout", color: "#000000", intensity: 0, fade: 0.1}
  ];

  // The rest of the stock palette. These have no keyboard shortcut - there
  // are only ten number keys - but they are on the page from the first load,
  // so the studio opens with a palette rather than six swatches and a
  // "make your own" button. Named and dialled like real gels: intensity and
  // fade are part of a look, not just a colour.
  var PALETTE = [
    {key: "deepblue", name: "Deep blue", color: "#1d4ed8", intensity: 75, fade: 1.4},
    {key: "congo", name: "Congo night", color: "#2b0e8a", intensity: 65, fade: 2.0},
    {key: "teal", name: "Teal wash", color: "#00b3a4", intensity: 78, fade: 1.2},
    {key: "cyan", name: "Ice cyan", color: "#57b8ff", intensity: 82, fade: 0.8},
    {key: "seagreen", name: "Sea green", color: "#00a651", intensity: 75, fade: 1.2},
    {key: "lime", name: "Lime punch", color: "#b9f3b0", intensity: 85, fade: 0.5},
    {key: "gold", name: "Pale gold", color: "#fff1c9", intensity: 80, fade: 1.6},
    {key: "sunrise", name: "Sunrise", color: "#ff7a00", intensity: 88, fade: 1.0},
    {key: "flame", name: "Flame", color: "#ff4a1c", intensity: 92, fade: 0.4},
    {key: "magenta", name: "Magenta", color: "#ff3fa4", intensity: 85, fade: 0.6},
    {key: "rose", name: "Rose", color: "#ff6fb5", intensity: 78, fade: 1.1},
    {key: "mauve", name: "Mauve", color: "#b63fa0", intensity: 72, fade: 1.3},
    {key: "lavender", name: "Lavender", color: "#b9a7ff", intensity: 70, fade: 1.5},
    {key: "ctb", name: "Cold white", color: "#cfe6ff", intensity: 95, fade: 0.5},
    {key: "bastard", name: "Bastard amber", color: "#ffd7a8", intensity: 70, fade: 1.8},
    {key: "chocolate", name: "Chocolate", color: "#8a5a2b", intensity: 55, fade: 2.2},
    {key: "strobe", name: "White strobe", color: "#ffffff", intensity: 100, fade: 0.0, move: "strobe"},
    {key: "chase", name: "Amber chase", color: "#ffb347", intensity: 95, fade: 0.0, move: "chase"}
  ];

  return {
    membersOf: membersOf, groupOptions: groupOptions, groupLabel: groupLabel, mirrorOf: mirrorOf,
    customGroup: customGroup, toggleInGroup: toggleInGroup,
    hexRgb: hexRgb, rgbHex: rgbHex, rgbToHsv: rgbToHsv, hsvToRgb: hsvToRgb,
    isBlackout: isBlackout, lightingAt: lightingAt, dmxFrame: dmxFrame,
    scaleLooks: scaleLooks, fixtureAddress: fixtureAddress, patchOverlaps: patchOverlaps,
    dmxData: dmxData, artnetPacket: artnetPacket, sacnPacket: sacnPacket, OUTPUTS: OUTPUTS,
    MOVES: MOVES, movementGain: movementGain, RIG_PRESETS: RIG_PRESETS, applyRig: applyRig, rigFromShow: rigFromShow, venueKey: venueKey,
    remapGroup: remapGroup, remapCues: remapCues,
    fmtClock: fmtClock, fmtTimecode: fmtTimecode, peaks: peaks,
    onsetEnvelope: onsetEnvelope, detectBeats: detectBeats, snapToBeat: snapToBeat,
    tapTempo: tapTempo, nearestCue: nearestCue, LOOKS: LOOKS, PALETTE: PALETTE,
    frameFeatures: frameFeatures, detectSections: detectSections, analyzeTrack: analyzeTrack,
    generateCues: generateCues, SECTION_LOOKS: SECTION_LOOKS, makeHistory: makeHistory
  };
});
