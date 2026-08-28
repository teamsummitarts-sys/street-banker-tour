/* Parse the encoders' output back out of the bytes. Nothing is taken on
   trust: headers are read field by field and samples are decoded and
   compared against what went in. */
const AC = require("../../static/js/audioconv.js");

let fails = 0;
function ok(name, cond, detail) {
  console.log((cond ? "PASS  " : "FAIL  ") + name + (detail ? "   " + detail : ""));
  if (!cond) { fails++; }
}
function ascii(dv, o, n) {
  let s = ""; for (let i = 0; i < n; i++) { s += String.fromCharCode(dv.getUint8(o + i)); }
  return s;
}

// A short deterministic signal: a ramp on the left, its inverse on the right.
const N = 500;
const L = new Float32Array(N), R = new Float32Array(N);
for (let i = 0; i < N; i++) {
  L[i] = -1 + 2 * i / (N - 1);
  R[i] = 1 - 2 * i / (N - 1);
}

console.log("=== WAV headers ===");
[[16, 1], [24, 1], [32, 3]].forEach(function (pair) {
  const bits = pair[0], wantFmt = pair[1];
  const ab = AC.encodeWav([L, R], 48000, bits, {dither: false});
  const dv = new DataView(ab);
  const bytesPer = bits / 8;
  const expect = 44 + N * 2 * bytesPer;
  ok(bits + "-bit WAV is the right size", ab.byteLength === expect,
     ab.byteLength + " vs " + expect);
  ok(bits + "-bit WAV RIFF/WAVE/fmt/data tags",
     ascii(dv, 0, 4) === "RIFF" && ascii(dv, 8, 4) === "WAVE"
       && ascii(dv, 12, 4) === "fmt " && ascii(dv, 36, 4) === "data");
  ok(bits + "-bit WAV declares format tag " + wantFmt,
     dv.getUint16(20, true) === wantFmt, "got " + dv.getUint16(20, true));
  ok(bits + "-bit WAV channels/rate/depth",
     dv.getUint16(22, true) === 2 && dv.getUint32(24, true) === 48000
       && dv.getUint16(34, true) === bits);
  ok(bits + "-bit WAV byte rate and block align",
     dv.getUint32(28, true) === 48000 * 2 * bytesPer
       && dv.getUint16(32, true) === 2 * bytesPer);
  ok(bits + "-bit WAV RIFF size field agrees with the file",
     dv.getUint32(4, true) === ab.byteLength - 8);
  ok(bits + "-bit WAV data size field agrees",
     dv.getUint32(40, true) === N * 2 * bytesPer);
});

console.log("\n=== WAV samples survive the round trip ===");
function readWav(ab) {
  const dv = new DataView(ab);
  const bits = dv.getUint16(34, true), ch = dv.getUint16(22, true);
  const n = dv.getUint32(40, true) / (ch * bits / 8);
  const out = [];
  for (let c = 0; c < ch; c++) { out.push(new Float32Array(n)); }
  let o = 44;
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < ch; c++) {
      if (bits === 16) { out[c][i] = dv.getInt16(o, true) / 32768; o += 2; }
      else if (bits === 32) { out[c][i] = dv.getFloat32(o, true); o += 4; }
      else {
        let v = dv.getUint8(o) | (dv.getUint8(o + 1) << 8) | (dv.getUint8(o + 2) << 16);
        if (v & 0x800000) { v -= 0x1000000; }
        out[c][i] = v / 8388608; o += 3;
      }
    }
  }
  return out;
}
[[16, 1 / 32768 * 2], [24, 1 / 8388608 * 2], [32, 1e-7]].forEach(function (pair) {
  const bits = pair[0], tol = pair[1];
  const back = readWav(AC.encodeWav([L, R], 44100, bits, {dither: false}));
  let maxL = 0, maxR = 0;
  for (let i = 0; i < N; i++) {
    maxL = Math.max(maxL, Math.abs(back[0][i] - L[i]));
    maxR = Math.max(maxR, Math.abs(back[1][i] - R[i]));
  }
  ok(bits + "-bit WAV decodes back to the input", maxL < tol && maxR < tol,
     "max error L " + maxL.toExponential(2) + " R " + maxR.toExponential(2));
  ok(bits + "-bit WAV kept the channels un-swapped",
     back[0][0] < -0.9 && back[1][0] > 0.9,
     "first frame L " + back[0][0].toFixed(3) + " R " + back[1][0].toFixed(3));
});

console.log("\n=== AIFF headers (big-endian) ===");
[16, 24].forEach(function (bits) {
  const ab = AC.encodeAiff([L, R], 44100, bits, {dither: false});
  const dv = new DataView(ab);
  const bytesPer = bits / 8;
  ok(bits + "-bit AIFF FORM/AIFF/COMM/SSND tags",
     ascii(dv, 0, 4) === "FORM" && ascii(dv, 8, 4) === "AIFF"
       && ascii(dv, 12, 4) === "COMM" && ascii(dv, 38, 4) === "SSND");
  ok(bits + "-bit AIFF FORM size agrees with the file",
     dv.getUint32(4, false) === ab.byteLength - 8);
  ok(bits + "-bit AIFF channels/frames/depth",
     dv.getUint16(20, false) === 2 && dv.getUint32(22, false) === N
       && dv.getUint16(26, false) === bits);
  ok(bits + "-bit AIFF SSND size covers offset+blockSize+samples",
     dv.getUint32(42, false) === 8 + N * 2 * bytesPer,
     "got " + dv.getUint32(42, false));
  // The 80-bit extended sample rate has to read back as exactly 44100.
  const exp = dv.getUint16(28, false) - 16383;
  const hi = dv.getUint32(30, false), lo = dv.getUint32(34, false);
  const mant = (hi + lo / Math.pow(2, 32)) / Math.pow(2, 31);
  const rate = mant * Math.pow(2, exp);
  ok(bits + "-bit AIFF sample rate decodes to 44100",
     Math.abs(rate - 44100) < 0.001, "got " + rate);
});
// 32-bit float has no plain-AIFF form; it must fall back to 24, not lie.
const a32 = new DataView(AC.encodeAiff([L, R], 44100, 32, {dither: false}));
ok("AIFF at 32 bits falls back to 24 rather than mislabel",
   a32.getUint16(26, false) === 24, "declares " + a32.getUint16(26, false));

console.log("\n=== extended-float writer on other rates ===");
[22050, 32000, 48000, 88200, 96000, 192000].forEach(function (r) {
  const ab = new ArrayBuffer(10);
  const dv = new DataView(ab);
  AC._writeExtended(dv, 0, r);
  const exp = dv.getUint16(0, false) - 16383;
  const mant = (dv.getUint32(2, false) + dv.getUint32(6, false) / Math.pow(2, 32))
               / Math.pow(2, 31);
  const back = mant * Math.pow(2, exp);
  ok("rate " + r + " round-trips through 80-bit extended",
     Math.abs(back - r) < 0.001, "got " + back);
});

console.log("\n=== peak measurement and dither ===");
const quiet = [new Float32Array([0.5, -0.25, 0.1])];
ok("peak finds the largest magnitude", AC.peak(quiet) === 0.5);
ok("peak in dBFS is about -6.02", Math.abs(AC.peakDbfs(quiet) + 6.0206) < 0.01,
   AC.peakDbfs(quiet).toFixed(4));
ok("digital silence reports -Infinity, not 0 dB",
   AC.peakDbfs([new Float32Array(8)]) === -Infinity);
// Dither must perturb 16-bit output but never 32-bit float.
const dc = [new Float32Array(400).fill(0.25)];
const d1 = readWav(AC.encodeWav(dc, 44100, 16, {dither: true}));
const d0 = readWav(AC.encodeWav(dc, 44100, 16, {dither: false}));
let varies = 0;
for (let i = 1; i < 400; i++) { if (d1[0][i] !== d1[0][0]) { varies++; } }
ok("dither varies the 16-bit quantisation of a DC level", varies > 100,
   varies + "/399 samples differ from the first");
let flat = true;
for (let i = 1; i < 400; i++) { if (d0[0][i] !== d0[0][0]) { flat = false; } }
ok("dither off leaves 16-bit truncation identical every sample", flat);
const f32 = readWav(AC.encodeWav(dc, 44100, 32, {dither: true}));
ok("32-bit float is never dithered", f32[0][0] === 0.25 && f32[0][399] === 0.25,
   "first " + f32[0][0] + " last " + f32[0][399]);

console.log("\n=== clipping is clamped, not wrapped ===");
const hot = [new Float32Array([1.8, -1.8, 0])];
const hb = readWav(AC.encodeWav(hot, 44100, 16, {dither: false}));
ok("over-range positive clamps near +1, no wrap to negative",
   hb[0][0] > 0.99, "got " + hb[0][0].toFixed(4));
ok("over-range negative clamps near -1, no wrap to positive",
   hb[0][1] < -0.99, "got " + hb[0][1].toFixed(4));
const hb24 = readWav(AC.encodeWav(hot, 44100, 24, {dither: false}));
ok("24-bit over-range clamps too",
   hb24[0][0] > 0.99 && hb24[0][1] < -0.99,
   hb24[0][0].toFixed(5) + " / " + hb24[0][1].toFixed(5));

console.log("\n=== mono ===");
const m = new DataView(AC.encodeWav([L], 44100, 16, {dither: false}));
ok("mono WAV declares one channel and half the block align",
   m.getUint16(22, true) === 1 && m.getUint16(32, true) === 2);

console.log("\n" + (fails ? fails + " FAILED" : "all checks passed"));
process.exit(fails ? 1 : 0);
