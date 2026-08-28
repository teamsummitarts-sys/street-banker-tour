/* Light Studio engine checks - known by construction.
   node check_lights.js  (exits non-zero on failure) */
const E = require("../../static/js/lights-engine.js");

let fails = 0;
function ok(name, cond, detail) {
  console.log((cond ? "PASS  " : "FAIL  ") + name + (detail ? "   " + detail : ""));
  if (!cond) fails++;
}

// groups
ok("all of 6", E.membersOf("all", 6).join() === "1,2,3,4,5,6");
ok("odd/even of 5", E.membersOf("odd", 5).join() === "1,3,5" && E.membersOf("even", 5).join() === "2,4");
ok("pair1 of 6 is outermost", E.membersOf("pair1", 6).join() === "1,6");
ok("pair3 of 5 is the centre bar alone", E.membersOf("pair3", 5).join() === "3");
ok("mirror of 2 in 6 is 5; centre has none", E.mirrorOf(2, 6) === 5 && E.mirrorOf(3, 5) === null);
ok("group options count", E.groupOptions(6).length === 3 + 3 + 6);

// lighting resolver: fade maths
const show = {bars: 2, chans: 4, cues: [
  {t: 0, group: "all", color: "#ff0000", intensity: 100, fade: 1},
  {t: 10, group: "b1", color: "#0000ff", intensity: 50, fade: 2}]};
let L = E.lightingAt(show, 0.5);
ok("half way through a 1s fade from black to red", L[0].rgb[0] === 128 && Math.abs(L[0].inten - 0.5) < 1e-9, JSON.stringify(L[0]));
L = E.lightingAt(show, 11);
ok("bar 1 half way red->blue at 50%", L[0].rgb[0] === 128 && L[0].rgb[2] === 128 && Math.abs(L[0].inten - 0.75) < 1e-9, JSON.stringify(L[0]));
ok("bar 2 untouched by a b1 cue", L[1].rgb[0] === 255 && L[1].inten === 1);
ok("before the first cue everything is dark", E.lightingAt({bars: 3, cues: [{t: 5, group: "all", color: "#ffffff", intensity: 100, fade: 0}]}, 1).every(x => x.inten === 0));

// ENTTEC framing
const pkt = E.dmxFrame({bars: 1, chans: 4}, [{rgb: [10, 20, 30], inten: 1}]);
ok("packet start/label/length/end", pkt[0] === 0x7E && pkt[1] === 6 && pkt[2] === (513 & 255) && pkt[3] === (513 >> 8) && pkt[pkt.length - 1] === 0xE7, Array.from(pkt.slice(0, 4)).join());
ok("start code 0 then dimmer+RGB", pkt[4] === 0 && pkt[5] === 255 && pkt[6] === 10 && pkt[7] === 20 && pkt[8] === 30);
const pkt3 = E.dmxFrame({bars: 1, chans: 3}, [{rgb: [200, 100, 0], inten: 0.5}]);
ok("3ch scales colour by intensity", pkt3[5] === 100 && pkt3[6] === 50 && pkt3[7] === 0);
ok("packet length is 5 + 513", pkt.length === 518);

// timecode
ok("fmtTimecode", E.fmtTimecode(65.257) === "1:05.25" && E.fmtTimecode(0) === "0:00.00", E.fmtTimecode(65.257));
ok("fmtClock", E.fmtClock(125.04) === "2:05.0");

// peaks on a known signal: 1 kHz tone at 0.5 amplitude, 1 s, 100 buckets
const RATE = 8000;
const tone = new Float32Array(RATE);
for (let i = 0; i < RATE; i++) tone[i] = 0.5 * Math.sin(2 * Math.PI * 1000 * i / RATE);
const pk = E.peaks(tone, RATE, 0, 1, 100);
ok("peaks max ~0.5 and min ~-0.5 in every bucket", Array.from(pk.max).every(v => v > 0.45 && v <= 0.5) && Array.from(pk.min).every(v => v < -0.45 && v >= -0.5));
const half = E.peaks(tone, RATE, 0.5, 1, 10);
ok("window peaks same amplitude", half.max[3] > 0.45);
const silent = E.peaks(new Float32Array(RATE), RATE, 0, 1, 10);
ok("silence is flat", silent.max.every(v => v === 0) && silent.min.every(v => v === 0));

// beats: click track at 120 BPM, 20 s, clicks 30 ms long with decay
const SR = 22050, DUR = 20, BPM = 120;
const clicks = new Float32Array(SR * DUR);
for (let b = 0.25; b < DUR; b += 60 / BPM) {
  const s0 = Math.floor(b * SR);
  for (let i = 0; i < SR * 0.03; i++) clicks[s0 + i] = Math.sin(i * 0.9) * Math.exp(-i / (SR * 0.01));
}
const det = E.detectBeats(clicks, SR);
ok("detects ~120 BPM", Math.abs(det.bpm - 120) < 1.5, "bpm=" + det.bpm);
ok("phase near the first click", det.offset < 0.3 || Math.abs(det.offset - 0.25) < 0.06 || Math.abs(det.offset - 0.75) < 0.06, "offset=" + det.offset);
ok("beat list spans the track", det.beats.length > 30 && det.beats[det.beats.length - 1] < DUR);
const det2 = E.detectBeats(new Float32Array(SR * 2), SR);
ok("too short / silent -> no tempo, no crash", det2.bpm === 0 && det2.beats.length === 0);

// snap & tap
ok("snapToBeat lands on the grid", E.snapToBeat(1.1, 120, 0.25) === 1.25 && E.snapToBeat(0.9, 120, 0.25) === 0.75);
ok("snap with no bpm is identity", E.snapToBeat(1.1, 0, 0) === 1.1);
ok("tap tempo from 8 taps at 0.5s = 120", E.tapTempo([0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5]) === 120);
ok("tap tempo ignores a long gap", E.tapTempo([0, 0.5, 10, 10.5, 11]) === 120);
ok("nearestCue within tolerance", E.nearestCue([{t: 1}, {t: 5}], 5.2, 0.5).t === 5 && E.nearestCue([{t: 1}], 5, 0.5) === null);
ok("isBlackout", E.isBlackout({color: "#000000", intensity: 80}) && E.isBlackout({color: "#ff0000", intensity: 0}) && !E.isBlackout({color: "#ff0000", intensity: 1}));
ok("six keyed looks, last is blackout", E.LOOKS.length === 6 && E.LOOKS[5].key === "blackout");
// the stock palette on top of the keyed six - the studio must not open as a
// six-colour tool
ok("the stock palette ships more than a handful", E.PALETTE.length >= 12, "palette=" + E.PALETTE.length);
ok("every stock look is a valid, distinct colour", (() => {
  const all = E.LOOKS.concat(E.PALETTE);
  const hex = /^#[0-9a-f]{6}$/i;
  const keys = new Set(), colours = new Set();
  for (const l of all) {
    if (!hex.test(l.color) || !l.name) return false;
    if (l.intensity < 0 || l.intensity > 100 || l.fade < 0) return false;
    if (keys.has(l.key)) return false;
    keys.add(l.key);
    colours.add(l.color.toLowerCase() + "/" + l.intensity + "/" + (l.move || ""));
  }
  return colours.size === all.length;
})());
ok("a look may carry movement, and it is a real move", E.PALETTE.filter(l => l.move).every(l => E.MOVES.some(m => m[0] === l.move)));

// a cue interrupting a fade starts from what is ON STAGE, not from the
// previous cue's target - otherwise the rig pops to full then fades down
const interrupt = {bars: 1, cues: [
  {t: 0, group: "all", color: "#ffb347", intensity: 100, fade: 4},
  {t: 1, group: "all", color: "#ffb347", intensity: 0, fade: 1}]};
const justBefore = E.lightingAt(interrupt, 0.99)[0].inten;
const atCut = E.lightingAt(interrupt, 1.0)[0].inten;
ok("an interrupted fade does not jump to the previous cue's target",
   Math.abs(atCut - justBefore) < 0.02, "before=" + justBefore.toFixed(3) + " at=" + atCut.toFixed(3));
ok("and it keeps fading down from there", E.lightingAt(interrupt, 1.5)[0].inten < atCut / 1.5);
ok("a fade that completed still starts from its full target",
   Math.abs(E.lightingAt({bars: 1, cues: [
     {t: 0, group: "all", color: "#ffffff", intensity: 100, fade: 0.5},
     {t: 5, group: "all", color: "#000000", intensity: 0, fade: 1}]}, 5)[0].inten - 1) < 1e-9);

// colour maths behind the RGB/HSV mixer
ok("rgbHex round trips and pads", E.rgbHex([255, 122, 0]) === "#ff7a00" && E.rgbHex([0, 0, 0]) === "#000000" && E.rgbHex([5, 5, 5]) === "#050505");
ok("rgbHex clamps out-of-range input", E.rgbHex([300, -20, 12.6]) === "#ff000d");
ok("rgb -> hsv on the primaries", E.rgbToHsv([255, 0, 0]).join() === "0,100,100" && E.rgbToHsv([0, 255, 0]).join() === "120,100,100" && E.rgbToHsv([0, 0, 255]).join() === "240,100,100");
ok("rgb -> hsv on grey and black", E.rgbToHsv([128, 128, 128]).join() === "0,0,50" && E.rgbToHsv([0, 0, 0]).join() === "0,0,0");
ok("hsv -> rgb on the primaries", E.hsvToRgb([0, 100, 100]).join() === "255,0,0" && E.hsvToRgb([120, 100, 100]).join() === "0,255,0" && E.hsvToRgb([240, 100, 100]).join() === "0,0,255");
ok("hsv wraps and clamps", E.hsvToRgb([360, 100, 100]).join() === "255,0,0" && E.hsvToRgb([-120, 100, 100]).join() === "0,0,255" && E.hsvToRgb([0, 500, 500]).join() === "255,0,0");
let rtFails = 0;
for (const hex of ["#ff7a00", "#3b82f6", "#8b5cf6", "#ffffff", "#000000", "#123456", "#0a0b0c", "#e3001b"]) {
  const back = E.rgbHex(E.hsvToRgb(E.rgbToHsv(E.hexRgb(hex))));
  // rounding through integer HSV can move a channel by 1; anything more is a bug
  if (E.hexRgb(back).some((v, i) => Math.abs(v - E.hexRgb(hex)[i]) > 2)) { rtFails++; console.log("   drift", hex, "->", back); }
}
ok("rgb -> hsv -> rgb round trips within rounding", rtFails === 0);

// custom (hand-picked) groups
ok("custom group members, sorted and deduped", E.membersOf("b3+b1+b3", 6).join() === "1,3");
ok("custom group ignores bars beyond the rig", E.membersOf("b1+b9", 6).join() === "1");
ok("customGroup canonical keys", E.customGroup([3, 1]) === "b1+b3" && E.customGroup([2]) === "b2" && E.customGroup([]) === "all");
ok("toggleInGroup adds and removes", E.toggleInGroup("b1", 3, 6) === "b1+b3" && E.toggleInGroup("b1+b3", 1, 6) === "b3" && E.toggleInGroup("all", 2, 3) === "b1+b3");
ok("custom group label", E.groupLabel("b2+b5", 6) === "Bars 2 + 5");
// two cues at the same timecode on different groups both land (per-fixture merge)
const merge = {bars: 4, chans: 4, cues: [
  {t: 2, group: "odd", color: "#ff0000", intensity: 100, fade: 0},
  {t: 2, group: "even", color: "#0000ff", intensity: 50, fade: 0},
  {t: 2, group: "b4", color: "#00ff00", intensity: 100, fade: 0}]};
const M = E.lightingAt(merge, 3);
ok("same-timecode cues merge per bar (odd red, even blue, b4 overrides)",
   M[0].rgb.join() === "255,0,0" && M[1].rgb.join() === "0,0,255" && M[1].inten === 0.5 && M[3].rgb.join() === "0,255,0" && M[3].inten === 1, JSON.stringify(M));

// grand master / panic
const SL = E.scaleLooks([{rgb: [255, 0, 0], inten: 1}, {rgb: [0, 0, 255], inten: 0.5}], 0.5, false);
ok("master halves every intensity, keeps colour", SL[0].inten === 0.5 && SL[1].inten === 0.25 && SL[0].rgb.join() === "255,0,0");
ok("panic forces everything off", E.scaleLooks([{rgb: [255, 0, 0], inten: 1}], 1, true)[0].inten === 0);
ok("master defaults to 1 and clamps", E.scaleLooks([{rgb: [1, 2, 3], inten: 1}])[0].inten === 1 && E.scaleLooks([{rgb: [1, 2, 3], inten: 1}], 7)[0].inten === 1);

// DMX patch: first address, per-bar overrides, overlaps, off-the-end
ok("default patch runs from 1 in fixture-sized steps", E.fixtureAddress({bars: 3, chans: 4}, 1) === 1 && E.fixtureAddress({bars: 3, chans: 4}, 3) === 9 && E.fixtureAddress({bars: 3, chans: 3}, 3) === 7);
ok("first address shifts the run", E.fixtureAddress({bars: 3, chans: 4, dmxStart: 101}, 2) === 105);
ok("per-bar address wins", E.fixtureAddress({bars: 3, chans: 4, dmxStart: 1, dmxAddr: {"2": 200}}, 2) === 200 && E.fixtureAddress({bars: 3, chans: 4, dmxAddr: {"2": "x"}}, 2) === 5);
ok("overlaps are reported as bar pairs", JSON.stringify(E.patchOverlaps({bars: 3, chans: 4, dmxAddr: {"2": 3}})) === "[[1,2]]" && E.patchOverlaps({bars: 3, chans: 4}).length === 0);
const patched = E.dmxFrame({bars: 2, chans: 4, dmxStart: 10, dmxAddr: {"2": 100}}, [{rgb: [1, 2, 3], inten: 1}, {rgb: [4, 5, 6], inten: 1}]);
ok("frame writes each bar at its own address", patched[4 + 10] === 255 && patched[4 + 11] === 1 && patched[4 + 100] === 255 && patched[4 + 103] === 6 && patched[4 + 5] === 0);
const offEnd = E.dmxFrame({bars: 1, chans: 4, dmxAddr: {"1": 511}}, [{rgb: [9, 9, 9], inten: 1}]);
ok("a fixture patched off the end of the universe is skipped, never wrapped", offEnd.length === 518 && offEnd[4 + 511] === 0 && offEnd[4 + 1] === 0);

// movement hints compile per rig: strobe / pulse / chase ride on the faded intent
const mv = {bars: 4, chans: 4, bpm: 120, cues: [{t: 0, group: "all", color: "#ffffff", intensity: 100, fade: 0, move: "chase"}]};
const c0 = E.lightingAt(mv, 0.01).map(l => l.inten), c1 = E.lightingAt(mv, 0.51).map(l => l.inten), c3 = E.lightingAt(mv, 1.51).map(l => l.inten);
ok("chase lights one bar per beat and walks", c0[0] === 1 && c0[1] < 0.2 && c1[1] === 1 && c1[0] < 0.2 && c3[3] === 1, JSON.stringify([c0, c1, c3]));
const st = {bars: 2, chans: 4, bpm: 120, cues: [{t: 0, group: "all", color: "#ffffff", intensity: 100, fade: 0, move: "strobe"}]};
ok("strobe is on early in the beat and off later", E.lightingAt(st, 0.05)[0].inten === 1 && E.lightingAt(st, 0.3)[0].inten === 0);
// pulse: peak on the beat, floor at the half-beat (120 BPM default -> 0.5 s period)
const pu = {bars: 1, chans: 4, cues: [{t: 0, group: "all", color: "#ffffff", intensity: 100, fade: 0, move: "pulse"}]};
ok("pulse floors at the half-beat and peaks on the beat",
   Math.abs(E.lightingAt(pu, 0.25)[0].inten - 0.3) < 1e-9 && Math.abs(E.lightingAt(pu, 0.5)[0].inten - 1) < 1e-9,
   JSON.stringify([E.lightingAt(pu, 0.25)[0].inten, E.lightingAt(pu, 0.5)[0].inten]));
ok("movement never exceeds the cue's own intensity", E.lightingAt({bars: 1, bpm: 120, cues: [{t: 0, group: "all", color: "#ffffff", intensity: 40, fade: 0, move: "pulse"}]}, 0.5)[0].inten <= 0.4 + 1e-9);
ok("a still cue is untouched by movement", E.lightingAt({bars: 1, cues: [{t: 0, group: "all", color: "#ffffff", intensity: 50, fade: 0, move: ""}]}, 0.3)[0].inten === 0.5);
ok("chase on an 8-bar rig walks all 8 (same intent, bigger rig)", E.lightingAt({bars: 8, bpm: 120, cues: mv.cues}, 3.51).map(l => l.inten)[7] === 1);

// rig profiles: presets apply, shows carry intents so they re-render on any rig
ok("three presets ship", E.RIG_PRESETS.length === 3 && E.RIG_PRESETS.map(r => r.key).join() === "dive4,club8,fest6");
const sh = {bars: 6, chans: 4, pos: {"1": [0.5, 0.5]}, rot: {"2": 90}, dmxStart: 7, dmxAddr: {"3": 99}, cues: [{t: 0, group: "odd", color: "#ff0000", intensity: 100, fade: 0}]};
E.applyRig(sh, E.RIG_PRESETS[0]);
ok("applyRig sets bars/chans/layout/patch and tags the rig", sh.bars === 4 && sh.chans === 3 && sh.pos["1"][0] === 0.2 && sh.rot["2"] === undefined && sh.dmxStart === 1 && Object.keys(sh.dmxAddr).length === 0 && sh.rigKey === "dive4");
ok("cues survive a rig swap and re-resolve (odd of 4)", E.lightingAt(sh, 1).map(l => l.inten).join() === "1,0,1,0");
E.applyRig(sh, E.RIG_PRESETS[2]);
ok("festival preset stands the outer bars up", sh.bars === 6 && sh.rot["1"] === 90 && sh.rot["6"] === 90 && sh.pos["1"][0] === 0.06);
// same look, different bar count: bar-naming groups remap by position, roles do not
ok("roles are rig-independent", ["all", "odd", "even"].every(g => E.remapGroup(g, 8, 4) === g));
ok("bar groups remap by position, never to nothing", E.remapGroup("b7", 8, 4) === "b4" && E.remapGroup("b1", 8, 4) === "b1" && E.remapGroup("b1", 4, 8) === "b1" && E.remapGroup("b4", 4, 8) === "b7");
ok("bar groups clamp inside the new rig", E.membersOf(E.remapGroup("b10", 10, 2), 2).length === 1 && E.remapGroup("b10", 10, 2) === "b2");
ok("pairs remap outermost-in", E.remapGroup("pair4", 8, 4) === "pair2" && E.remapGroup("pair1", 8, 4) === "pair1");
ok("custom picks remap and dedupe", E.remapGroup("b1+b2+b7+b8", 8, 4) === "b1+b4", E.remapGroup("b1+b2+b7+b8", 8, 4));
ok("remap is identity at the same size", E.remapGroup("b3+b5", 6, 6) === "b3+b5" && E.remapGroup("pair2", 6, 6) === "pair2");
ok("malformed groups fall back to all, never crash", E.remapGroup("bXX", 8, 4) === "all" && E.remapGroup("pair", 8, 4) === "all" && E.remapGroup("", 8, 4) === "all");
// an 8-bar show played on a 4-bar rig still lights something for every cue
const big = {bars: 8, chans: 4, cues: [{t: 0, group: "b7", color: "#ff0000", intensity: 100, fade: 0}, {t: 0, group: "pair4", color: "#00ff00", intensity: 100, fade: 0}]};
ok("before remap, an 8-bar cue is dark on a 4-bar rig", E.lightingAt({bars: 4, cues: big.cues}, 1).every(l => l.inten === 0));
E.applyRig(big, E.RIG_PRESETS[0]);
ok("after a rig swap every cue still lights a bar", big.bars === 4 && E.lightingAt(big, 1).some(l => l.inten > 0) && big.cues.every(c => E.membersOf(c.group, 4).length > 0), JSON.stringify(big.cues.map(c => c.group)));
ok("remapCues does not mutate the originals", (() => { const src = [{t: 0, group: "b8", color: "#fff", intensity: 50, fade: 0, note: "keep"}]; const out = E.remapCues(src, 8, 4); return src[0].group === "b8" && out[0].group === "b4" && out[0].note === "keep"; })());

const rf = E.rigFromShow({bars: 5, chans: 3, pos: {"2": [0.1, 0.2]}, rot: {}, dmxStart: 33, dmxAddr: {}}, "My rig");
ok("rigFromShow captures the current rig", rf.name === "My rig" && rf.bars === 5 && rf.chans === 3 && rf.pos["2"][1] === 0.2 && rf.dmxStart === 33);
ok("venueKey normalises", E.venueKey("The Vault, Charlotte!") === "the vault charlotte" && E.venueKey("") === "");

// --- network DMX: checked against the published packet layouts -------------
const netShow = {bars: 2, chans: 4, dmxStart: 1};
const netLooks = [{rgb: [10, 20, 30], inten: 1}, {rgb: [40, 50, 60], inten: 0.5}];

const universe = E.dmxData(netShow, netLooks);
ok("universe is 512 slots with NO start code", universe.length === 512);
ok("first fixture lands at slot 1 (index 0)", universe[0] === 255 && universe[1] === 10 && universe[2] === 20 && universe[3] === 30);
ok("second fixture follows it", universe[4] === 128 && universe[5] === 40);
ok("a fixture patched past 512 is skipped, not wrapped",
   E.dmxData({bars: 1, chans: 4, dmxAddr: {"1": 511}}, [{rgb: [9, 9, 9], inten: 1}]).slice(0, 8).every(v => v === 0));

const art = E.artnetPacket(netShow, netLooks, {universe: 0});
ok("Art-Net header is 'Art-Net\\0'", Buffer.from(art.slice(0, 8)).toString("latin1") === "Art-Net\0");
ok("Art-Net opcode 0x5000 is little endian", art[8] === 0x00 && art[9] === 0x50);
ok("Art-Net protocol version 14 is big endian", art[10] === 0 && art[11] === 14);
ok("Art-Net length is big endian 512", art[16] === 0x02 && art[17] === 0x00);
ok("Art-Net packet is 18 + 512", art.length === 530);
ok("Art-Net carries the universe with no start code", art[18] === 255 && art[19] === 10);
const art15 = E.artnetPacket(netShow, netLooks, {universe: 0x0102});
ok("Art-Net splits universe into SubUni and Net", art15[14] === 0x02 && art15[15] === 0x01);

const sacn = E.sacnPacket(netShow, netLooks, {universe: 1, cid: new Uint8Array(16).fill(7)});
ok("sACN preamble and postamble", (sacn[0] << 8 | sacn[1]) === 0x0010 && (sacn[2] << 8 | sacn[3]) === 0x0000);
ok("sACN ACN packet identifier", Buffer.from(sacn.slice(4, 16)).toString("latin1") === "ASC-E1.17\0\0\0");
ok("sACN packet length is 126 + 512", sacn.length === 638);
const dv = new DataView(sacn.buffer, sacn.byteOffset, sacn.byteLength);
ok("sACN root vector is 0x04", dv.getUint32(18) === 4);
ok("sACN root flags+length", dv.getUint16(16) === (0x7000 | (638 - 16)));
ok("sACN framing vector is 0x02", dv.getUint32(40) === 2);
ok("sACN framing flags+length", dv.getUint16(38) === (0x7000 | (638 - 38)));
ok("sACN default priority is 100", sacn[108] === 100);
ok("sACN universe is big endian", dv.getUint16(113) === 1);
ok("sACN DMP vector and address type", sacn[117] === 0x02 && sacn[118] === 0xA1);
ok("sACN property count is 513 (start code + 512)", dv.getUint16(123) === 513);
ok("sACN start code is 0 and slots follow", sacn[125] === 0x00 && sacn[126] === 255 && sacn[127] === 10);
ok("sACN CID is carried verbatim", Array.from(sacn.slice(22, 38)).every(v => v === 7));
ok("sACN priority clamps", E.sacnPacket(netShow, netLooks, {priority: 9999})[108] === 200);
ok("sACN source name is ASCII and null padded", sacn[44] === "S".charCodeAt(0) && sacn[107] === 0);
ok("four output sinks are declared", E.OUTPUTS.length === 4 && E.OUTPUTS[0][0] === "preview");

console.log(fails ? ("\n" + fails + " FAILED") : "\nall passed");
process.exit(fails ? 1 : 0);
