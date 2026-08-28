/* Verify tempokey.js against signals whose answers are known by
   construction. Nothing here trusts the module's own report. */
const TK = require("../../static/js/tempokey.js");

const RATE = 22050;
let fails = 0;
function ok(name, cond, detail) {
  console.log((cond ? "PASS  " : "FAIL  ") + name + (detail ? "   " + detail : ""));
  if (!cond) { fails++; }
}

/* A click track: sharp broadband transients at an exact BPM, plus a quiet
   sine bed so the envelope has something to sit on. */
function clickTrack(bpm, seconds, rate) {
  const n = Math.floor(seconds * rate);
  const d = new Float32Array(n);
  const period = rate * 60 / bpm;
  for (let i = 0; i < n; i++) {
    d[i] = 0.02 * Math.sin(2 * Math.PI * 110 * i / rate);
  }
  for (let b = 0; b * period < n; b++) {
    const at = Math.round(b * period);
    // 6 ms decaying noise burst = one drum hit.
    for (let k = 0; k < rate * 0.006 && at + k < n; k++) {
      const env = Math.exp(-k / (rate * 0.0015));
      d[at + k] += 0.9 * env * (Math.random() * 2 - 1);
    }
  }
  return d;
}

/* A triad held for the whole clip, with a few harmonics, so the chroma
   has exactly the pitch classes of one known chord. */
function chordTone(midiNotes, seconds, rate) {
  const n = Math.floor(seconds * rate);
  const d = new Float32Array(n);
  midiNotes.forEach(function (m, idx) {
    const hz = 440 * Math.pow(2, (m - 69) / 12);
    const amp = 0.3 / (idx + 1);
    for (let h = 1; h <= 4; h++) {
      if (hz * h > rate / 2 - 100) { break; }
      for (let i = 0; i < n; i++) {
        d[i] += (amp / h) * Math.sin(2 * Math.PI * hz * h * i / rate);
      }
    }
  });
  return d;
}

console.log("=== BPM detection ===");
[90, 120, 140].forEach(function (bpm) {
  const sig = clickTrack(bpm, 20, RATE);
  const got = TK.detectBpm([sig], RATE);
  const err = got ? Math.abs(got.bpm - bpm) : Infinity;
  ok("click track at " + bpm + " BPM", err <= 1.5,
     "got " + (got ? got.bpm + " (conf " + got.confidence + ", alts "
                     + got.alternates.join("/") + ")" : "null"));
});

console.log("\n=== Beat grid: where the beats actually fall ===");
/* A tempo without a phase is useless for cutting - you know the spacing
   but not where to start. These click tracks put the first hit at a known
   offset, so the detected phase can be checked against it. */
function clickAt(bpm, offsetSec, secs) {
  const n = Math.floor(secs * RATE), d = new Float32Array(n);
  const period = RATE * 60 / bpm, start = Math.round(offsetSec * RATE);
  for (let i = 0; i < n; i++) { d[i] = 0.02 * Math.sin(2*Math.PI*110*i/RATE); }
  for (let b = 0; start + b * period < n; b++) {
    const at = Math.round(start + b * period);
    for (let k = 0; k < RATE * 0.006 && at + k < n; k++) {
      d[at + k] += 0.9 * Math.exp(-k / (RATE * 0.0015)) * (Math.random() * 2 - 1);
    }
  }
  return d;
}
[[120, 0.35], [90, 0.0], [140, 1.21]].forEach(function (pair) {
  const bpm = pair[0], off = pair[1];
  const g = TK.beatGrid([clickAt(bpm, off, 25)], RATE);
  ok("grid found at " + bpm + " BPM", g !== null);
  if (!g) { return; }
  ok("  tempo within 1.5 BPM", Math.abs(g.bpm - bpm) <= 1.5, g.bpm + "");
  // Phase repeats every beat, so compare modulo the period.
  const per = 60 / bpm;
  let err = Math.abs(((g.firstBeat - off) % per + per) % per);
  if (err > per / 2) { err = per - err; }
  /* The onset envelope hops every 256 samples - about 12 ms of resolution -
     so anything inside 50 ms is at the limit of what it can resolve. */
  ok("  phase within 50 ms of the real downbeat", err < 0.05,
     (err * 1000).toFixed(0) + " ms");
  ok("  confident on a clean click track", g.confidence > 0.5,
     g.confidence.toFixed(2));
});

const grid = TK.beatGrid([clickAt(120, 0.35, 25)], RATE);
ok("snapping lands exactly on a beat",
   Math.abs(((TK.snapToBeat(3.10, grid) - grid.firstBeat) / grid.period) % 1)
     < 1e-9);
ok("snapping to bars lands on every 4th beat",
   Math.abs(((TK.snapToBeat(3.10, grid, 4) - grid.firstBeat)
             / (grid.period * 4)) % 1) < 1e-9);
ok("snapping never moves further than half a beat",
   Math.abs(TK.snapToBeat(3.10, grid) - 3.10) <= grid.period / 2 + 1e-9,
   (Math.abs(TK.snapToBeat(3.10, grid) - 3.10) * 1000).toFixed(0) + " ms");
ok("snapping never returns a negative time", TK.snapToBeat(0.01, grid) >= 0);
ok("beats between 3s and 5s are evenly spaced",
   (function () {
     const b = TK.beatsBetween(grid, 3, 5);
     if (b.length < 3) { return false; }
     for (let i = 1; i < b.length; i++) {
       if (Math.abs((b[i] - b[i - 1]) - grid.period) > 1e-6) { return false; }
     }
     return true;
   })(), TK.beatsBetween(grid, 3, 5).length + " beats");
/* Silence has no beats. Without the guard the autocorrelation still
   returns its best lag over a flat envelope and the grid comes back
   looking authoritative - 191 BPM on a track with nothing in it. */
ok("no grid without a signal is null, not a confident 191 BPM",
   TK.beatGrid([new Float32Array(RATE * 3)], RATE) === null);
ok("snapping with no grid leaves the time alone",
   TK.snapToBeat(4.2, null) === 4.2);

console.log("\n=== Key detection ===");
// C major triad: C4 E4 G4 -> pitch classes C, E, G.
const cmaj = chordTone([60, 64, 67], 8, RATE);
const k1 = TK.detectKey([cmaj], RATE);
ok("C-E-G reads as a C-rooted major key",
   k1 && k1.key === "C major", k1 ? k1.key + " score " + k1.score
     + " (runner-up " + k1.runnerUp + " " + k1.runnerUpScore + ")" : "null");
// A minor triad: A3 C4 E4 -> A, C, E.
const amin = chordTone([57, 60, 64], 8, RATE);
const k2 = TK.detectKey([amin], RATE);
ok("A-C-E reads as an A-rooted minor key",
   k2 && k2.key === "A minor", k2 ? k2.key + " score " + k2.score
     + " (runner-up " + k2.runnerUp + " " + k2.runnerUpScore + ")" : "null");
// F# major triad: F#4 A#4 C#5.
const fsmaj = chordTone([66, 70, 73], 8, RATE);
const k3 = TK.detectKey([fsmaj], RATE);
ok("F#-A#-C# reads as an F#-rooted major key",
   k3 && k3.root === 6 && k3.mode === "major", k3 ? k3.key : "null");
ok("chroma sums to 1 and lists 12 classes",
   k1 && k1.chroma.length === 12
     && Math.abs(k1.chroma.reduce((a, b) => a + b, 0) - 1) < 0.02,
   k1 ? "sum " + k1.chroma.reduce((a, b) => a + b, 0).toFixed(3) : "");

console.log("\n=== Time stretch: length and pitch ===");
function dominantHz(sig, rate) {
  const N = 8192;
  const re = new Float32Array(N), im = new Float32Array(N);
  const off = Math.floor((sig.length - N) / 2);
  for (let i = 0; i < N; i++) {
    const w = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / N);
    re[i] = sig[off + i] * w;
  }
  TK._fft(re, im);
  let best = 0, bestI = 1;
  for (let i = 1; i < N / 2; i++) {
    const m = re[i] * re[i] + im[i] * im[i];
    if (m > best) { best = m; bestI = i; }
  }
  return bestI * rate / N;
}

const tone = chordTone([69], 6, RATE);   // A4 = 440 Hz
ok("source tone really is 440 Hz", Math.abs(dominantHz(tone, RATE) - 440) < 6,
   dominantHz(tone, RATE).toFixed(1) + " Hz");

let pending = 3;
function maybeDone() {
  if (--pending > 0) { return; }
  console.log("\n=== project() arithmetic ===");
  const p = TK.project(120, 0, "major", 0.5, 2);   // half speed, up 2 semis
  ok("half-speed doubles the reported BPM", p.bpm === 240, "got " + p.bpm);
  ok("up two semitones from C major is D major", p.key === "D major",
     "got " + p.key);
  const p2 = TK.project(174, 9, "minor", 1.25, -3);
  ok("1.25x tempo on 174 BPM reads 139.2", p2.bpm === 139.2, "got " + p2.bpm);
  ok("down three semitones from A minor is F# minor", p2.key === "F# minor",
     "got " + p2.key);
  console.log("\n" + (fails ? fails + " FAILED" : "all checks passed"));
  process.exit(fails ? 1 : 0);
}

// Tempo only: twice as long, same pitch.
TK.transform([tone], {tempo: 2}, null, function (out) {
  const got = out[0];
  const ratio = got.length / tone.length;
  ok("tempo 2.0 doubles the length", Math.abs(ratio - 2) < 0.05,
     "ratio " + ratio.toFixed(3));
  ok("tempo 2.0 leaves pitch at 440 Hz",
     Math.abs(dominantHz(got, RATE) - 440) < 8,
     dominantHz(got, RATE).toFixed(1) + " Hz");
  maybeDone();
});

// Pitch only: same length, up an octave.
TK.transform([tone], {semitones: 12}, null, function (out) {
  const got = out[0];
  const ratio = got.length / tone.length;
  ok("+12 semitones keeps the length", Math.abs(ratio - 1) < 0.06,
     "ratio " + ratio.toFixed(3));
  ok("+12 semitones lands on 880 Hz",
     Math.abs(dominantHz(got, RATE) - 880) < 14,
     dominantHz(got, RATE).toFixed(1) + " Hz");
  maybeDone();
});

// Down a fifth, and slower at the same time.
TK.transform([tone], {semitones: -7, tempo: 1.5}, null, function (out) {
  const got = out[0];
  const want = 440 * Math.pow(2, -7 / 12);
  ok("-7 semitones at 1.5x tempo hits " + want.toFixed(1) + " Hz",
     Math.abs(dominantHz(got, RATE) - want) < 10,
     dominantHz(got, RATE).toFixed(1) + " Hz");
  ok("-7 semitones at 1.5x tempo is 1.5x long",
     Math.abs(got.length / tone.length - 1.5) < 0.06,
     "ratio " + (got.length / tone.length).toFixed(3));
  maybeDone();
});
