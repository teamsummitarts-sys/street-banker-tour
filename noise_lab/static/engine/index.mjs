import {StereoMeter} from './meter.mjs';
import {PRESETS, DEFAULT_RECIPE, validateRecipe} from './recipes.mjs';
import {LOOPS, createDemo, decodeWav, encodeWav, applyLoopEdges, MAX_FILE_BYTES} from './audio.mjs';
import {NoiseDSP, TRANSITION_SECONDS, MAX_TAIL_SECONDS, playbackEnvelope} from './dsp.mjs';
export {PRESETS, DEFAULT_RECIPE, validateRecipe, LOOPS};

export function supportsAudio() {
  if (!globalThis.isSecureContext) return {supported: false, reason: 'AudioWorklet requires HTTPS or localhost. This preview is not a secure audio context.'};
  if (typeof globalThis.AudioContext !== 'function' || typeof globalThis.AudioWorkletNode !== 'function') {
    return {supported: false, reason: 'This browser is missing AudioContext or AudioWorklet. Try an up-to-date Safari or Chromium browser. Device playback still needs pilot verification.'};
  }
  return {supported: true, reason: 'Required browser APIs are present. Start audio with a tap or keyboard action. Background playback and locked-screen playback are not guaranteed; physical-device validation is pending.'};
}

const abortError = () => new DOMException('Audio export cancelled because the source, patch, or playback settings changed.', 'AbortError');

/**
 * All source PCM remains in this page's memory. This module has no network transport,
 * microphone access, persistent storage, AI client, or account system.
 * create/play must be invoked from a user gesture. The app owns any patch persistence.
 */
export class NoiseEngine {
  #context; #worklet; #master; #inputMeter; #outputMeter; #source = null; #active = new Set();
  #recipe = validateRecipe(DEFAULT_RECIPE); #bypass = false; #playing = false;
  #disposed = false; #faulted = false; #revision = 0; #loadRevision = 0; #exportRevision = 0; #transportRevision = 0;
  #startedAt = 0; #masterStart = 0; #masterTarget = 0; #masterAt = 0;
  onstatechange = null;

  static async create() {
    const support = supportsAudio();
    if (!support.supported) throw new Error(support.reason);
    const context = new AudioContext({latencyHint: 'interactive'});
    try {
      // Initiate resume synchronously while the caller's activation is available.
      const resume = context.resume();
      await context.audioWorklet.addModule(new URL('./processor.mjs', import.meta.url));
      await resume;
      const engine = new NoiseEngine(context);
      return engine;
    } catch (error) {
      await context.close().catch(() => {});
      throw new Error(`Local audio could not start: ${error.message}`);
    }
  }

  constructor(context) {
    if (!context?.audioWorklet) throw new TypeError('Use NoiseEngine.create() to start audio.');
    this.#context = context;
    this.#worklet = new AudioWorkletNode(context, 'street-banker-noise-lab-v1', {
      numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [2], channelCount: 2,
      channelCountMode: 'explicit', processorOptions: {recipe: this.#recipe, bypass: false},
    });
    this.#master = context.createGain(); this.#master.gain.value = 0;
    this.#worklet.connect(this.#master).connect(context.destination);
    this.#inputMeter = new StereoMeter(context);
    this.#outputMeter = new StereoMeter(context);
    this.#master.connect(this.#outputMeter.input);
    this.#worklet.port.onmessage = ({data}) => {
      if (data.type === 'fault') this.#fault(data.message);
      if (data.type === 'rejected') this.#emit('fault', data.message);
    };
    this.#worklet.onprocessorerror = () => this.#fault('The browser audio processor failed. Reload the lab to recover.');
    context.onstatechange = () => {
      if (context.state !== 'running' && this.#playing) this.stop();
      this.#emit(context.state === 'interrupted' ? 'suspended' : context.state,
        context.state !== 'running' ? 'Audio paused by the browser. Tap Play to resume.' : undefined);
    };
  }

  #assert() { if (this.#disposed) throw new Error('The audio session has been closed.'); }
  #emit(state, message) { if (typeof this.onstatechange === 'function') this.onstatechange({state, message}); }
  #fault(message) { this.#faulted = true; this.stop(); this.#emit('fault', message); }
  #rampMaster(target) {
    const now = this.#context.currentTime;
    const progress = Math.min(1, Math.max(0, (now - this.#masterAt) / TRANSITION_SECONDS));
    const current = this.#masterStart + (this.#masterTarget - this.#masterStart) * progress;
    this.#master.gain.cancelScheduledValues(now);
    this.#master.gain.setValueAtTime(current, now);
    this.#master.gain.linearRampToValueAtTime(target, now + TRANSITION_SECONDS);
    this.#masterStart = current; this.#masterTarget = target; this.#masterAt = now;
  }

  #retire(node, gain) {
    const now = this.#context.currentTime;
    gain.gain.cancelScheduledValues(now);
    // Retirement is scheduled only once per source; gain is born at one.
    gain.gain.setValueAtTime(gain.gain.value, now);
    gain.gain.linearRampToValueAtTime(0, now + TRANSITION_SECONDS);
    try { node.stop(now + TRANSITION_SECONDS + 0.01); } catch {}
  }

  #startSource() {
    const buffer = this.#context.createBuffer(this.#source.channels.length, this.#source.channels[0].length, this.#source.sampleRate);
    this.#source.channels.forEach((channel, index) => buffer.copyToChannel(channel, index));
    const node = this.#context.createBufferSource(); const gain = this.#context.createGain();
    node.buffer = buffer; node.loop = true; gain.gain.value = 1;
    node.connect(gain).connect(this.#worklet);
    gain.connect(this.#inputMeter.input);
    const entry = {node, gain}; this.#active.add(entry);
    node.onended = () => { node.disconnect(); gain.disconnect(); this.#active.delete(entry); };
    node.start(); this.#startedAt = this.#context.currentTime;
  }

  #install(source) {
    this.#assert();
    this.#revision++; this.#source = source;
    this.stop();
    // Source changes stop transport. Explicit Play avoids races with later Stop/imports.
    return this.getInfo();
  }

  loadDemo(loopId) {
    this.#assert();
    const candidate = createDemo(loopId, this.#context.sampleRate);
    this.#loadRevision++;
    return this.#install(candidate);
  }

  async loadFile(file) {
    this.#assert();
    if (!file || !Number.isFinite(file.size) || file.size < 44 || file.size > MAX_FILE_BYTES || typeof file.arrayBuffer !== 'function') {
      throw new RangeError('Choose an uncompressed WAV file no larger than 20 MiB.');
    }
    const load = ++this.#loadRevision;
    const bytes = await file.arrayBuffer();
    this.#assert();
    if (load !== this.#loadRevision) throw new DOMException('A newer source selection replaced this import.', 'AbortError');
    const candidate = decodeWav(bytes, this.#context.sampleRate);
    candidate.name = typeof file.name === 'string' ? file.name : 'Local WAV';
    return this.#install(candidate);
  }

  async loadGenerated(bytes, accept = () => true) {
    this.#assert();
    if (!(bytes instanceof ArrayBuffer) || bytes.byteLength < 128 || bytes.byteLength > 2 * 1024 * 1024) throw new RangeError('Unsupported generated audio size.');
    const load = ++this.#loadRevision;
    const decoded = await this.#context.decodeAudioData(bytes);
    this.#assert();
    if (load !== this.#loadRevision || !accept()) throw new DOMException('Newer work retained.', 'AbortError');
    if (![1,2].includes(decoded.numberOfChannels) || !Number.isFinite(decoded.duration) || decoded.duration <= 0 || decoded.duration > 11 || decoded.sampleRate !== this.#context.sampleRate) throw new RangeError('Unsupported generated audio.');
    const channels = Array.from({length:decoded.numberOfChannels}, (_, ch) => new Float32Array(decoded.getChannelData(ch)));
    for (const channel of channels) for (const value of channel) if (!Number.isFinite(value)) throw new RangeError('Invalid audio samples.');
    applyLoopEdges(channels, decoded.sampleRate);
    return this.#install({channels, sampleRate:decoded.sampleRate, duration:decoded.duration, name:'ElevenLabs generated sound'});
  }

  setRecipe(value) {
    this.#assert();
    const candidate = validateRecipe(value);
    this.#worklet.port.postMessage({type: 'recipe', recipe: candidate});
    this.#recipe = candidate; this.#revision++;
  }

  setBypass(value) {
    this.#assert();
    if (typeof value !== 'boolean') throw new TypeError('Bypass must be boolean.');
    this.#worklet.port.postMessage({type: 'bypass', value});
    this.#bypass = value; this.#revision++;
  }

  async play() {
    this.#assert();
    if (!this.#source) throw new Error('Choose a demonstration loop or import a WAV first.');
    if (this.#playing && this.#context.state === 'running') return;
    if (this.#faulted) throw new Error('Audio stopped after a processor fault. Reload the lab to reset safely.');
    const transport = ++this.#transportRevision;
    await this.#context.resume(); this.#assert();
    if (transport !== this.#transportRevision) return;
    if (this.#context.state !== 'running') throw new Error('Audio is paused by the browser. Tap Play again to enable sound.');
    // A rapid Stop/Play cannot reset DSP while the previous source is still audible.
    if (this.#active.size) await new Promise(resolve => setTimeout(resolve, 65));
    this.#assert();
    if (transport !== this.#transportRevision || this.#context.state !== 'running') return;
    if (this.#playing) return;
    this.#worklet.port.postMessage({type: 'reset'});
    this.#startSource(); this.#playing = true; this.#rampMaster(1);
    this.#emit('running');
  }

  stop() {
    if (this.#disposed) return;
    this.#transportRevision++;
    this.#playing = false;
    if (this.#masterTarget !== 0) this.#rampMaster(0);
    for (const entry of this.#active) if (!entry.retired) {
      entry.retired = true; this.#retire(entry.node, entry.gain);
    }
  }

  getInfo() {
    return {duration: this.#source?.duration || 0, channels: this.#source?.channels.length || 0,
      sampleRate: this.#source?.sampleRate || this.#context.sampleRate,
      name: this.#source?.name || '', playing: this.#playing && this.#context.state === 'running'};
  }

  getLevels() {
    if (this.#disposed || !this.#playing || this.#context.state !== 'running') return {input: [0, 0], output: [0, 0]};
    return {input: this.#inputMeter.read(), output: this.#outputMeter.read()};
  }

  getPosition() { return this.#playing && this.#source ? Math.max(0, this.#context.currentTime - this.#startedAt) % this.#source.duration : 0; }

  async exportWav({includeTail = true, recipe, bypass} = {}) {
    this.#assert();
    if (!this.#source) throw new Error('Choose a source before exporting.');
    if (typeof includeTail !== 'boolean') throw new TypeError('Tail selection must be boolean.');
    const renderRecipe = validateRecipe(recipe === undefined ? this.#recipe : recipe);
    const renderBypass = bypass === undefined ? this.#bypass : bypass;
    if (typeof renderBypass !== 'boolean') throw new TypeError('Bypass must be boolean.');
    const revision = this.#revision; const task = ++this.#exportRevision;
    const source = this.#source; const sampleRate = source.sampleRate;
    const sourceFrames = source.channels[0].length;
    const frames = sourceFrames + (includeTail ? Math.ceil(sampleRate * MAX_TAIL_SECONDS) : 0);
    const channels = source.channels.map(() => new Float32Array(frames));
    const dsp = new NoiseDSP(sampleRate, renderRecipe, renderBypass); const output = new Float32Array(2);
    const unchanged = () => { if (this.#disposed || revision !== this.#revision || task !== this.#exportRevision) throw abortError(); };
    for (let start = 0; start < frames; start += 8192) {
      unchanged();
      for (let i = start; i < Math.min(frames, start + 8192); i++) {
        const left = i < sourceFrames ? source.channels[0][i] : 0;
        const right = i < sourceFrames ? (source.channels[1] || source.channels[0])[i] : 0;
        dsp.processFrame(left, right, output);
        if (dsp.faulted) throw new Error('Export stopped because the processor encountered an invalid signal.');
        const envelope = playbackEnvelope(i, frames, sampleRate);
        channels[0][i] = output[0] * envelope;
        if (channels[1]) channels[1][i] = output[1] * envelope;
      }
      // Yield so edits, source replacement, close, and cancellation can invalidate the render.
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    unchanged();
    const wav = encodeWav(channels, sampleRate);
    unchanged();
    return new Blob([wav], {type: 'audio/wav'});
  }

  cancelExport() { this.#exportRevision++; }

  async dispose() {
    if (this.#disposed) return;
    this.stop(); this.#disposed = true; this.#revision++; this.#loadRevision++; this.#exportRevision++;
    if (this.#context.state === 'running') await new Promise(resolve => setTimeout(resolve, 65));
    for (const {node, gain} of this.#active) { try { node.stop(); } catch {} node.disconnect(); gain.disconnect(); }
    this.#active.clear(); this.#worklet.port.postMessage({type: 'dispose'}); this.#worklet.port.close();
    this.#worklet.disconnect(); this.#master.disconnect();
    this.#inputMeter.dispose(); this.#outputMeter.dispose();
    this.#source = null; this.#context.onstatechange = null;
    await this.#context.close(); this.#emit('closed');
  }
}
