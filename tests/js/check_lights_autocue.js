/* Epic 1 - auto-cue. A synthetic song with known structure: 6 s quiet
   warm intro (220 Hz tone, soft), 8 s loud bright chorus (noise + tone,
   hard hit at the boundary), a 1 s hard stop, then 6 s of quieter verse.
   The analysis must find the boundaries and label them sensibly, and the
   generated cues must follow the defaults and all be auto. */
const E = require("../../static/js/lights-engine.js");
let fails = 0;
function ok(name, cond, detail) { console.log((cond ? "PASS  " : "FAIL  ") + name + (detail ? "   " + detail : "")); if (!cond) fails++; }

const SR = 22050, DUR = 21;
const x = new Float32Array(SR * DUR);
let seed = 7; const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296 - 0.5; };
for (let i = 0; i < x.length; i++) {
  const t = i / SR;
  if (t < 6) x[i] = 0.08 * Math.sin(2 * Math.PI * 220 * t);                                          // intro: quiet, low
  else if (t < 14) x[i] = 0.55 * rnd() + 0.3 * Math.sin(2 * Math.PI * 2200 * t) + 0.2 * Math.sin(2 * Math.PI * 110 * t); // chorus/drop: loud, bright, bass
  else if (t < 15) x[i] = 0;                                                                           // hard stop
  else x[i] = 0.22 * Math.sin(2 * Math.PI * 440 * t) + 0.1 * rnd();                                    // verse: mid
}
// beats: clicks every 0.5 s on top - except inside the hard stop, which is silent
for (let b = 0.25; b < DUR; b += 0.5) { if (b >= 14 && b < 15) continue; const s0 = Math.floor(b * SR); for (let i = 0; i < SR * 0.02; i++) x[s0 + i] += 0.5 * Math.sin(i * 0.9) * Math.exp(-i / (SR * 0.008)); }

const A = E.analyzeTrack(x, SR);
console.log("sections:", JSON.stringify(A.sections), "stops:", JSON.stringify(A.stops), "bpm", A.bpm);
ok("finds at least three sections", A.sections.length >= 3, "n=" + A.sections.length);
const near = (t, target, tol) => Math.abs(t - target) <= tol;
ok("a boundary near 6 s", A.sections.some(s => near(s.start, 6, 1.2)), A.sections.map(s => s.start).join());
ok("a boundary near 14-15 s", A.sections.some(s => near(s.start, 14.5, 1.5)), A.sections.map(s => s.start).join());
ok("first section is the intro", A.sections[0].label === "intro", A.sections[0].label);
const loud = A.sections.find(s => s.start >= 5 && s.start <= 7.5);
ok("the loud section is a chorus or drop", loud && (loud.label === "chorus" || loud.label === "drop"), loud && loud.label);
ok("hard stop detected near 14 s", A.stops.some(s => near(s.start, 14, 0.6)), JSON.stringify(A.stops));
ok("tempo found", Math.abs(A.bpm - 120) < 3, "bpm=" + A.bpm);

const cues = E.generateCues(A);
ok("cues generated and sorted", cues.length >= 4 && cues.every((c, i) => i === 0 || c.t >= cues[i - 1].t), "n=" + cues.length);
ok("every generated cue is auto", cues.every(c => c.auto === true));
ok("first cue is a dim warm intro at 0", cues[0].t === 0 && cues[0].intensity <= 40 && cues[0].color === "#ffb347", JSON.stringify(cues[0]));
const lift = cues.find(c => c.t >= 5 && c.t <= 7.5 && c.intensity === 100);
ok("full-stage lift at the chorus/drop boundary", !!lift, JSON.stringify(cues.filter(c => c.t >= 5 && c.t <= 9)));
ok("blackout on the hard stop", cues.some(c => c.color === "#000000" && c.intensity === 0 && near(c.t, 14, 0.6)));
ok("a look comes back after the stop", cues.some(c => c.note === "back in" && near(c.t, 15, 0.8)));
ok("cues are plain editable objects (t, group, color, intensity, fade, note)", cues.every(c => typeof c.t === "number" && typeof c.group === "string" && /^#/.test(c.color) && typeof c.intensity === "number" && typeof c.fade === "number" && typeof c.note === "string"));
ok("no duplicate group@time", new Set(cues.map(c => c.group + "@" + c.t.toFixed(2))).size === cues.length);
// the resolver accepts them straight away
const looks = E.lightingAt({bars: 4, cues: cues}, 7.0);
ok("resolver renders generated cues", looks.length === 4 && looks[0].inten > 0.5, JSON.stringify(looks[0]));
// silence: nothing to generate, nothing crashes
const S = E.analyzeTrack(new Float32Array(SR * 3), SR);
ok("silent track -> no crash, one or zero sections", S.sections.length <= 1 && E.generateCues(S).length <= 1);

console.log(fails ? ("\n" + fails + " FAILED") : "\nall passed");
process.exit(fails ? 1 : 0);
