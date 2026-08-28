/* DYN-1 sidechain: a keyed compressor for the Rack.
 *
 * The browser's DynamicsCompressorNode has no key input, so a stem cannot
 * drive it. This processor is the missing piece: input 0 is the programme,
 * input 1 is the KEY. A peak follower rides the key, a soft-knee gain
 * computer turns that level into a reduction, and the reduction is applied
 * to the programme. The knobs are the same five DYN-1 already has —
 * threshold, ratio, attack, release, and the knee the rack uses (6 dB).
 *
 * It reports its reduction (dB, negative) over the port about thirty times
 * a second so the GR ladder can show it. When `active` is 0 it is a wire.
 *
 * Runs in both the live AudioContext and the offline bounce: the same
 * module is added to each, so an export ducks exactly as playback did.
 */
class SBDucker extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [
      {name: "threshold", defaultValue: -24, minValue: -60, maxValue: 0,   automationRate: "k-rate"},
      {name: "ratio",     defaultValue: 4,   minValue: 1,   maxValue: 20,  automationRate: "k-rate"},
      {name: "attack",    defaultValue: 0.01, minValue: 0.0005, maxValue: 1, automationRate: "k-rate"},
      {name: "release",   defaultValue: 0.25, minValue: 0.01, maxValue: 3,  automationRate: "k-rate"},
      {name: "knee",      defaultValue: 6,   minValue: 0,   maxValue: 30,  automationRate: "k-rate"},
      {name: "active",    defaultValue: 0,   minValue: 0,   maxValue: 1,   automationRate: "k-rate"}
    ];
  }

  constructor() {
    super();
    this.env = 0;      // key envelope, linear
    this.gr = 0;       // last block's mean reduction, dB
    this.n = 0;
  }

  process(inputs, outputs, p) {
    var main = inputs[0], key = inputs[1], out = outputs[0];
    var ch = out.length, frames = out[0].length, c, i;
    var active = p.active[0] > 0.5 && key.length > 0 && key[0] && key[0].length > 0;
    if (!main.length || !main[0]) {                 // nothing arriving: silence out
      for (c = 0; c < ch; c++) out[c].fill(0);
      return true;
    }
    if (!active) {                                  // a wire
      for (c = 0; c < ch; c++) out[c].set(main[Math.min(c, main.length - 1)]);
      this.gr = 0;
      if ((this.n++ & 7) === 0) this.port.postMessage(0);
      return true;
    }
    var thr = p.threshold[0], ratio = p.ratio[0], knee = p.knee[0];
    var aA = Math.exp(-1 / (sampleRate * Math.max(0.0005, p.attack[0])));
    var aR = Math.exp(-1 / (sampleRate * Math.max(0.01, p.release[0])));
    var kch = key.length, sum = 0, slope = 1 - 1 / ratio;
    for (i = 0; i < frames; i++) {
      var k = 0;
      for (c = 0; c < kch; c++) { var v = key[c][i]; k += v * v; }
      k = Math.sqrt(k / kch);
      var coef = k > this.env ? aA : aR;
      this.env = coef * this.env + (1 - coef) * k;
      var lvl = 20 * Math.log10(this.env + 1e-9), over = lvl - thr, g;
      if (over <= -knee / 2)      g = 0;
      else if (over >= knee / 2)  g = -slope * over;
      else { var x = over + knee / 2; g = -slope * x * x / (2 * knee); }
      sum += g;
      var lin = Math.pow(10, g / 20);
      for (c = 0; c < ch; c++) out[c][i] = main[Math.min(c, main.length - 1)][i] * lin;
    }
    this.gr = sum / frames;
    if ((this.n++ & 7) === 0) this.port.postMessage(this.gr);
    return true;
  }
}
registerProcessor("sb-ducker", SBDucker);
