import {PROFILES, DEFAULT_RECIPE, validateRecipe} from './recipes.mjs';

export const TRANSITION_SECONDS = 0.04;
export const OUTPUT_CEILING = 10 ** (-1 / 20);
// The next lower Float32 value makes the bound survive output-buffer conversion.
export const SAFE_CEILING = 0.8912509083747864;
export const MAX_TAIL_SECONDS = 2;
const TAU = 2 * Math.PI;

function parameters(recipe, sampleRate) {
  const p = PROFILES[recipe.profile];
  const m = recipe.macros;
  return {
    texture: m.texture / 100, drive: 1 + p.drive * m.texture / 100,
    motion: 0.8 * m.motion / 100, rate: p.rate,
    space: m.space / 100, delay: p.delay * sampleRate,
    feedback: p.feedback * m.space / 100,
    tone: 1 - Math.exp(-TAU * Math.min(p.tone, sampleRate * 0.4) / sampleRate),
    mix: m.mix / 100, level: 10 ** (m.level / 20), bypass: 0,
  };
}

/**
 * One deterministic graph for both the worklet and local WAV rendering.
 * Fixed graph: DC removal -> saturation/tremolo -> filtered feedback echo ->
 * dry/wet -> output level -> bounded soft clipping. Space is an echo, not convolution.
 * This sample limiter does not certify true-peak/loudness or safe listening volume.
 */
export class NoiseDSP {
  constructor(sampleRate, recipe = DEFAULT_RECIPE, bypass = false) {
    if (!Number.isInteger(sampleRate) || sampleRate < 8000 || sampleRate > 192000) {
      throw new RangeError('Unsupported sample rate.');
    }
    this.sampleRate = sampleRate;
    this.recipe = validateRecipe(recipe);
    this.current = parameters(this.recipe, sampleRate);
    this.current.bypass = bypass ? 1 : 0;
    this.target = {...this.current};
    this.steps = Object.fromEntries(Object.keys(this.current).map(key => [key, 0]));
    this.rampRemaining = 0;
    this.rampFrames = Math.ceil(sampleRate * TRANSITION_SECONDS);
    this.length = Math.ceil(sampleRate * 0.5) + 2;
    this.buffers = [new Float32Array(this.length), new Float32Array(this.length)];
    this.low = [0, 0]; this.previousInput = [0, 0]; this.previousDC = [0, 0];
    this.dc = Math.exp(-TAU * 18 / sampleRate);
    this.cursor = 0; this.phase = 0; this.faulted = false;
  }

  #ramp(target) {
    this.target = target;
    for (const key of Object.keys(target)) {
      this.steps[key] = (target[key] - this.current[key]) / this.rampFrames;
    }
    this.rampRemaining = this.rampFrames;
  }

  setRecipe(value) {
    const recipe = validateRecipe(value); // Validate before touching the working patch.
    const next = parameters(recipe, this.sampleRate);
    next.bypass = this.target.bypass;
    this.recipe = recipe;
    this.#ramp(next);
  }

  setBypass(value) {
    if (typeof value !== 'boolean') throw new TypeError('Bypass must be boolean.');
    this.#ramp({...this.target, bypass: value ? 1 : 0});
  }

  /** A nonfinite sample latches silence until an explicit transport reset. */
  fault() { this.faulted = true; }

  processFrame(left, right = left, output = new Float32Array(2)) {
    if (this.faulted || !Number.isFinite(left) || !Number.isFinite(right)) {
      this.faulted = true; output[0] = 0; output[1] = 0; return output;
    }
    if (this.rampRemaining > 0) {
      for (const key of Object.keys(this.current)) this.current[key] += this.steps[key];
      if (--this.rampRemaining === 0) this.current = {...this.target};
    }
    const p = this.current;
    const modulation = 1 - p.motion * (0.5 + 0.5 * Math.sin(this.phase));
    this.phase = (this.phase + TAU * p.rate / this.sampleRate) % TAU;
    const position = (this.cursor - p.delay + this.length) % this.length;
    const i = Math.floor(position); const fraction = position - i;
    const wetRatio = p.mix * (1 - p.bypass);
    for (let channel = 0; channel < 2; channel++) {
      const incoming = channel === 0 ? left : right;
      const sample = Math.max(-1, Math.min(1, incoming));
      const dry = sample - this.previousInput[channel] + this.dc * this.previousDC[channel];
      this.previousInput[channel] = sample; this.previousDC[channel] = dry;
      const saturated = dry + p.texture * (Math.tanh(dry * p.drive) - dry);
      const direct = saturated * modulation;
      const ring = this.buffers[channel];
      const delayed = ring[i] * (1 - fraction) + ring[(i + 1) % this.length] * fraction;
      this.low[channel] += p.tone * (delayed - this.low[channel]);
      ring[this.cursor] = Math.max(-2, Math.min(2, direct + this.low[channel] * p.feedback));
      const wet = direct * (1 - 0.3 * p.space) + this.low[channel] * p.space * 0.65;
      let result = (dry * (1 - wetRatio) + wet * wetRatio) * p.level;
      if (!Number.isFinite(result)) {
        this.faulted = true; output[0] = 0; output[1] = 0; return output;
      }
      // Smooth limiting above 0.7; final clamp also covers floating point rounding.
      const magnitude = Math.abs(result);
      if (magnitude > 0.7) result = Math.sign(result) *
        (0.7 + (SAFE_CEILING - 0.7) * Math.tanh((magnitude - 0.7) / (SAFE_CEILING - 0.7)));
      output[channel] = Math.max(-SAFE_CEILING, Math.min(SAFE_CEILING, result));
    }
    this.cursor = (this.cursor + 1) % this.length;
    return output;
  }

  processBlock(inputs, outputs) {
    const left = inputs[0]; const right = inputs[1] || left;
    const frame = this.frame || (this.frame = new Float32Array(2));
    for (let i = 0; i < outputs[0].length; i++) {
      this.processFrame(left?.[i] ?? 0, right?.[i] ?? 0, frame);
      outputs[0][i] = frame[0];
      if (outputs[1]) outputs[1][i] = frame[1];
    }
  }
}

export function playbackEnvelope(index, totalFrames, sampleRate) {
  const ramp = Math.ceil(sampleRate * TRANSITION_SECONDS);
  return Math.min(1, index / ramp, Math.max(0, (totalFrames - 1 - index) / ramp));
}
