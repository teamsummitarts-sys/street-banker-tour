/* Loudness is specified, so it can be checked against published answers
   rather than eyeballed. This runs the EBU Tech 3341 compliance cases for
   integrated loudness, the Tech 3342 cases for loudness range, and checks
   the derived K-weighting coefficients against the table printed in
   ITU-R BS.1770-4 itself. A tolerance of 0.1 LU is the one the spec sets. */
const L = require("../../static/js/loudness.js");

let fails = 0;
function ok(name, cond, detail) {
  console.log((cond ? "PASS  " : "FAIL  ") + name + (detail ? "   " + detail : ""));
  if (!cond) { fails++; }
}
function near(a, b, tol) { return a !== null && Math.abs(a - b) <= tol; }

const RATE = 48000;

/* A 1 kHz sine whose PEAK amplitude is 10^(db/20). The compliance cases
   are specified this way, and the checks below confirm that reading is
   right by requiring the meter to return the same number back. */
function sine(db, secs, rate, hz) {
  const n = Math.floor((secs || 1) * (rate || RATE));
  const amp = Math.pow(10, db / 20);
  const d = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    d[i] = amp * Math.sin(2 * Math.PI * (hz || 1000) * i / (rate || RATE));
  }
  return d;
}
function concat(parts) {
  const n = parts.reduce((s, p) => s + p.length, 0);
  const out = new Float64Array(n);
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}
function stereo(mono) { return [mono, Float64Array.from(mono)]; }
function I(chans, rate) {
  return L.integrated(chans.map(c => L.kWeight(c, rate || RATE)), rate || RATE);
}

console.log("=== BS.1770-4: derived coefficients match the published table ===");
/* The standard prints these for 48 kHz only. Deriving them per rate is the
   whole point - using 48 kHz numbers on a 44.1 kHz file is a real and
   common error - so the derivation has to reproduce the table exactly. */
const c48 = L.kCoefficients(48000);
const wantShelf = {b0: 1.53512485958697, b1: -2.69169618940638,
                   b2: 1.19839281085285, a1: -1.69065929318241,
                   a2: 0.73248077421585};
const wantHp = {b0: 1.0, b1: -2.0, b2: 1.0,
                a1: -1.99004745483398, a2: 0.99007225036621};
for (const k of Object.keys(wantShelf)) {
  ok("shelf " + k + " matches the spec table",
     Math.abs(c48[0][k] - wantShelf[k]) < 1e-11,
     c48[0][k].toFixed(14) + " vs " + wantShelf[k]);
}
for (const k of Object.keys(wantHp)) {
  ok("high-pass " + k + " matches the spec table",
     Math.abs(c48[1][k] - wantHp[k]) < 1e-8,
     c48[1][k].toFixed(11) + " vs " + wantHp[k]);
}
// And the coefficients must genuinely change with rate, or the derivation
// is decorative.
const c441 = L.kCoefficients(44100);
ok("coefficients differ at 44.1 kHz (they are derived, not copied)",
   Math.abs(c441[0].b0 - c48[0].b0) > 1e-4,
   "44.1k b0 " + c441[0].b0.toFixed(6) + " vs 48k " + c48[0].b0.toFixed(6));

console.log("\n=== EBU Tech 3341 — integrated loudness compliance ===");
// Case 1 & 2: a steady sine must read back its own level.
ok("case 1: stereo 1 kHz sine at -23 dBFS reads -23.0 LUFS",
   near(I(stereo(sine(-23, 20))), -23.0, 0.1),
   fmt(I(stereo(sine(-23, 20)))));
ok("case 2: stereo 1 kHz sine at -33 dBFS reads -33.0 LUFS",
   near(I(stereo(sine(-33, 20))), -33.0, 0.1),
   fmt(I(stereo(sine(-33, 20)))));

// Case 3: quiet tails must not drag the average down - that is the
// relative gate doing its job.
const case3 = concat([sine(-36, 10), sine(-23, 60), sine(-36, 10)]);
ok("case 3: -36/-23/-36 reads -23.0 (relative gate excludes the quiet)",
   near(I(stereo(case3)), -23.0, 0.1), fmt(I(stereo(case3))));

// Case 4: segments below -70 LUFS must be dropped by the absolute gate.
const case4 = concat([sine(-72, 10), sine(-23, 60), sine(-72, 10)]);
ok("case 4: -72/-23/-72 reads -23.0 (absolute gate drops the silence)",
   near(I(stereo(case4)), -23.0, 0.1), fmt(I(stereo(case4))));

// Case 5: the published mixed-level case.
const case5 = concat([sine(-26, 20), sine(-20, 20.1), sine(-26, 20)]);
ok("case 5: -26/-20/-26 reads -23.0",
   near(I(stereo(case5)), -23.0, 0.1), fmt(I(stereo(case5))));

console.log("\n=== The gates are actually load-bearing ===");
/* If the gating were skipped, case 3 would come out far lower. Proving the
   ungated answer is different is what shows the gate is doing work. */
const weighted3 = stereo(case3).map(c => L.kWeight(c, RATE));
const blocks = L._blockPowers(weighted3, RATE, 400, 100);
const w = L.channelWeights(2);
let sum = 0;
for (const b of blocks) { sum += w[0] * b[0] + w[1] * b[1]; }
const ungated = -0.691 + 10 * Math.log10(sum / blocks.length);
ok("ungated mean would read lower than the gated answer",
   ungated < -23.5, "ungated " + ungated.toFixed(2) + " vs gated -23.0");

console.log("\n=== Silence and degenerate input ===");
ok("digital silence has no integrated loudness (null, not a number)",
   I(stereo(new Float64Array(RATE * 2))) === null);
ok("a clip shorter than one 400 ms block returns null",
   I(stereo(sine(-23, 0.2))) === null);
ok("mono works and is not silently treated as stereo",
   near(I([sine(-23, 20)]), -26.0, 0.15),
   fmt(I([sine(-23, 20)])) + " (one channel is 3 dB below the stereo pair)");

console.log("\n=== EBU Tech 3342 — loudness range ===");
function LRA(chans) {
  return L.loudnessRange(chans.map(c => L.kWeight(c, RATE)), RATE);
}
const lra1 = LRA(stereo(concat([sine(-20, 20), sine(-30, 20)])));
ok("case 1: -20 and -30 segments give LRA 10 LU", near(lra1, 10, 1),
   fmt(lra1) + " LU");
const lra2 = LRA(stereo(concat([sine(-20, 20), sine(-15, 20)])));
ok("case 2: -20 and -15 segments give LRA 5 LU", near(lra2, 5, 1),
   fmt(lra2) + " LU");
const lraFlat = LRA(stereo(sine(-23, 40)));
ok("a dead-flat signal has essentially no range", lraFlat !== null && lraFlat < 1,
   fmt(lraFlat) + " LU");

console.log("\n=== True peak: the peak BETWEEN samples ===");
/* A sine at a quarter of the sample rate, phase-shifted so no sample ever
   lands on the crest. Sample peak reads about -3 dB; the real signal hits
   full scale, and that is what a converter and every lossy encoder see. */
const n = 4096, tricky = new Float64Array(n);
for (let i = 0; i < n; i++) {
  tricky[i] = Math.sin(2 * Math.PI * (RATE / 4) * i / RATE + Math.PI / 4);
}
const sp = L.toDb(L.samplePeak([tricky]));
const tp = L.toDb(L.truePeak([tricky]));
ok("sample peak under-reads this signal by about 3 dB", near(sp, -3.01, 0.1),
   fmt(sp) + " dBFS");
ok("true peak finds the real 0 dB crest", near(tp, 0, 0.3), fmt(tp) + " dBTP");
ok("true peak is higher than sample peak here", tp > sp + 2,
   (tp - sp).toFixed(2) + " dB of inter-sample peak");
/* A signal whose peaks land on samples must not be inflated. 4800 samples
   of 1 kHz at 48 kHz is exactly 100 cycles, so it begins and ends on a
   zero crossing and has no edge discontinuity to overshoot. */
const plain = new Float64Array(4800);
for (let i = 0; i < 4800; i++) {
  plain[i] = 0.5 * Math.sin(2 * Math.PI * 1000 * i / RATE);
}
ok("true peak does not invent headroom on an ordinary signal",
   near(L.toDb(L.truePeak([plain])), -6.02, 0.05),
   fmt(L.toDb(L.truePeak([plain]))) + " dBTP vs sample peak "
     + fmt(L.toDb(L.samplePeak([plain]))));

/* A file that stops mid-waveform is a step down to silence, and a step has
   inter-sample overshoot whether or not anyone wants it. Reporting it is
   correct - that edit really will overshoot on playback - so this records
   the behaviour deliberately rather than leaving it to be rediscovered as
   a bug. The same tone cut mid-cycle reads about 0.4 dB hotter. */
const ragged = new Float64Array(4096);
for (let i = 0; i < 4096; i++) {
  ragged[i] = 0.5 * Math.sin(2 * Math.PI * 1000 * i / RATE);
}
const raggedTp = L.toDb(L.truePeak([ragged]));
ok("a hard cut mid-waveform genuinely overshoots, and is reported",
   raggedTp > -6.0 && raggedTp < -5.0,
   fmt(raggedTp) + " dBTP — the file ends at "
     + ragged[4095].toFixed(3) + ", a step to silence");
ok("silence has no peak", L.truePeak([new Float64Array(512)]) === 0);

console.log("\n=== Target arithmetic ===");
const t = L.TARGETS.find(x => x.key === "spotify");
// A master 4 LU too loud: the platform turns it down, which is lossless.
let a = L.againstTarget(-10, -0.5, t);
ok("4 LU too loud reports +4.0 over and -4.0 of gain", a.delta === 4 && a.gain === -4);
ok("too loud is flagged over, not under", a.over === true && a.under === false);
ok("turning down cannot clip", a.clipsIfRaised === false);
// A master 6 LU too quiet with almost no headroom: raising it WILL clip.
a = L.againstTarget(-20, -0.5, t);
ok("6 LU too quiet reports +6.0 of gain", a.gain === 6);
ok("raising a hot-peaked quiet master is flagged as clipping",
   a.clipsIfRaised === true, "peak would land at +5.5 dBTP");
// Quiet with real headroom: raising it is safe.
a = L.againstTarget(-20, -12, t);
ok("raising a master with headroom does not clip", a.clipsIfRaised === false);
ok("peak headroom against the ceiling is reported", a.peakHeadroom === 11,
   a.peakHeadroom + " dB below -1 dBTP");
ok("an unmeasurable master yields nulls, not zeros",
   L.againstTarget(null, -Infinity, t).delta === null);

console.log("\n=== analyse() ties it together ===");
const res = L.analyse(stereo(case5), RATE);
ok("integrated is reported", near(res.integrated, -23.0, 0.1), fmt(res.integrated));
ok("range is reported", res.range !== null, fmt(res.range) + " LU");
ok("true peak is reported", res.truePeak !== null, fmt(res.truePeak) + " dBTP");
ok("duration and channel count are honest",
   Math.abs(res.seconds - 60.1) < 0.2 && res.channels === 2,
   res.seconds.toFixed(1) + "s, " + res.channels + "ch");
ok("every published target is evaluated", res.targets.length === L.TARGETS.length);
ok("short-term maximum is at or above the integrated value",
   res.shortTermMax >= res.integrated - 0.1,
   res.shortTermMax + " vs " + res.integrated);
const silent = L.analyse(stereo(new Float64Array(RATE)), RATE);
ok("a silent file reports null loudness rather than a made-up number",
   silent.integrated === null && silent.truePeak === null);

function fmt(v) {
  return v === null || v === undefined ? "null"
    : (typeof v === "number" ? v.toFixed(2) : String(v));
}

console.log("\n" + (fails ? fails + " FAILED" : "all checks passed"));
process.exit(fails ? 1 : 0);
