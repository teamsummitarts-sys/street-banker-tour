import test from 'node:test';
import assert from 'node:assert/strict';
import {PRESETS, DEFAULT_RECIPE, validateRecipe} from '../../noise_lab/static/engine/recipes.mjs';
import {NoiseDSP, OUTPUT_CEILING, TRANSITION_SECONDS} from '../../noise_lab/static/engine/dsp.mjs';
import {createDemo, decodeWav, inspectWav, encodeWav, MAX_FILE_BYTES} from '../../noise_lab/static/engine/audio.mjs';
import {samplePeak, decibels} from '../../noise_lab/static/engine/meter.mjs';
import {meterPercent, PeakHold} from '../../noise_lab/static/ui/console.mjs';
import {NoiseEngine, supportsAudio} from '../../noise_lab/static/engine/index.mjs';

const clone = value => JSON.parse(JSON.stringify(value));
function recipe(profile = 'metal-bloom', changes = {}) {
  const value = clone(PRESETS.find(preset => preset.id === profile).recipe);
  Object.assign(value.macros, changes); return value;
}
function fixture({channels = 1, frames = 800, sampleRate = 8000, encoding = 1, bits = 16} = {}) {
  const bytes = bits / 8; const buffer = new ArrayBuffer(44 + frames * channels * bytes);
  const view = new DataView(buffer);
  const text = (offset, value) => [...value].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
  text(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); text(8, 'WAVE'); text(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, encoding, true); view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * channels * bytes, true);
  view.setUint16(32, channels * bytes, true); view.setUint16(34, bits, true);
  text(36, 'data'); view.setUint32(40, frames * channels * bytes, true);
  for (let frame = 0; frame < frames; frame++) for (let ch = 0; ch < channels; ch++) {
    const offset = 44 + (frame * channels + ch) * bytes;
    const sample = Math.sin(frame / 15) * 0.45 * (ch === 0 ? 1 : -1);
    if (encoding === 3) view.setFloat32(offset, sample, true);
    else if (bits === 16) view.setInt16(offset, sample * 32767, true);
    else if (bits === 32) view.setInt32(offset, sample * 2147483647, true);
    else { const value = Math.round(sample * 8388607); for (let byte = 0; byte < 3; byte++) view.setUint8(offset + byte, (value >> (8 * byte)) & 255); }
  }
  return buffer;
}

test('recipes reject malformed, nonfinite, executable, and incompatible data before replacing a valid sound', () => {
  const valid = validateRecipe(DEFAULT_RECIPE);
  valid.macros.level = -60;
  assert.equal(DEFAULT_RECIPE.macros.level, -12);
  const malformed = [null, [], 'code', {}, {...clone(DEFAULT_RECIPE), engineVersion: 'future'},
    {...clone(DEFAULT_RECIPE), schemaVersion: 2}, {...clone(DEFAULT_RECIPE), profile: '__proto__'},
    {...clone(DEFAULT_RECIPE), workletURL: 'https://example.invalid/evil.js'},
    recipe('clean', {texture: '50'}), recipe('clean', {space: NaN}), recipe('clean', {motion: Infinity}),
    recipe('clean', {level: 1}), recipe('clean', {level: -61}), recipe('clean', {mix: 101}),
    recipe('clean', {texture: -1}), Object.create(DEFAULT_RECIPE),
    {...clone(DEFAULT_RECIPE), macros: {...DEFAULT_RECIPE.macros, code: 'eval(1)'}},
  ];
  const getter = clone(DEFAULT_RECIPE);
  Object.defineProperty(getter, 'profile', {get() { throw new Error('Getter must never execute'); }, enumerable: true});
  malformed.push(getter);
  const dsp = new NoiseDSP(48000, DEFAULT_RECIPE);
  for (const value of malformed) {
    assert.throws(() => validateRecipe(value));
    assert.throws(() => dsp.setRecipe(value));
    assert.deepEqual(dsp.recipe, DEFAULT_RECIPE);
  }
});

test('silence remains exactly silent under every profile and maximum effects', () => {
  for (const preset of PRESETS) {
    const dsp = new NoiseDSP(8000, recipe(preset.id, {texture: 100, motion: 100, space: 100, mix: 100, level: 0}));
    const out = new Float32Array(2);
    for (let i = 0; i < 16000; i++) assert.deepEqual([...dsp.processFrame(0, 0, out)], [0, 0]);
  }
});

test('all macro extrema stay finite and below -1 dBFS with adversarial tone, impulse, noise, and oversized input', () => {
  let seed = 901;
  const random = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 2147483648 - 1; };
  let largest = 0;
  for (const rate of [8000, 44100, 48000]) for (const preset of PRESETS) for (let mask = 0; mask < 32; mask++) {
    const changes = {};
    ['texture', 'motion', 'space', 'mix', 'level'].forEach((key, index) => {
      changes[key] = key === 'level' ? ((mask >> index) & 1 ? 0 : -60) : ((mask >> index) & 1 ? 100 : 0);
    });
    const dsp = new NoiseDSP(rate, recipe(preset.id, changes)); const out = new Float32Array(2);
    const segment = Math.ceil(rate / 4);
    // One full second reaches the longest echo at each declared test rate.
    for (let i = 0; i < segment * 4; i++) {
      const signal = i < segment ? Math.sin(i * 0.9) : i < segment * 2 ? (i === segment ? 1e300 : 0) : i < segment * 3 ? random() : (i % 2 ? -1e300 : 1e300);
      dsp.processFrame(signal, -signal, out);
      for (const sample of out) { assert.ok(Number.isFinite(sample)); assert.ok(Math.abs(sample) <= OUTPUT_CEILING); largest = Math.max(largest, Math.abs(sample)); }
    }
    assert.equal(dsp.faulted, false);
  }
  assert.ok(largest > 0.75, 'The stress test actually exercised the limiter.');
});

test('invalid audio latches silence rather than forwarding NaN/Infinity or resuming unpredictably', () => {
  for (const value of [NaN, Infinity, -Infinity]) {
    const dsp = new NoiseDSP(48000); const frame = new Float32Array(2);
    assert.deepEqual([...dsp.processFrame(value, 1, frame)], [0, 0]);
    assert.equal(dsp.faulted, true);
    assert.deepEqual([...dsp.processFrame(1, 1, frame)], [0, 0]);
  }
});

test('bypass crossfade begins continuously and reaches the matching dry path in exactly 40 ms', () => {
  const rate = 48000; const settings = recipe();
  const changing = new NoiseDSP(rate, settings); const unchanged = new NoiseDSP(rate, settings);
  const dry = new NoiseDSP(rate, settings, true);
  const a = new Float32Array(2); const b = new Float32Array(2); const c = new Float32Array(2);
  const signal = i => 0.12 * Math.sin(2 * Math.PI * 220 * i / rate);
  for (let i = 0; i < 20000; i++) { const x = signal(i); changing.processFrame(x, x, a); unchanged.processFrame(x, x, b); dry.processFrame(x, x, c); }
  changing.setBypass(true);
  const ramp = Math.ceil(TRANSITION_SECONDS * rate);
  for (let i = 0; i < ramp; i++) {
    const x = signal(i + 20000); changing.processFrame(x, x, a); unchanged.processFrame(x, x, b); dry.processFrame(x, x, c);
    if (i === 0) assert.ok(Math.abs(a[0] - b[0]) < 0.001, 'No instantaneous wet/dry jump.');
  }
  assert.equal(a[0], c[0]); assert.equal(a[1], c[1]);
});

test('rapid preset/bypass changes and sixty seconds of continuous DSP remain bounded', () => {
  const rate = 8000; const dsp = new NoiseDSP(rate, recipe()); const output = new Float32Array(2);
  let previous = 0; let delta = 0;
  for (let i = 0; i < 60 * rate; i++) {
    if (i % 173 === 0) dsp.setRecipe(recipe(PRESETS[Math.floor(i / 173) % PRESETS.length].id));
    if (i % 239 === 0) dsp.setBypass(Boolean(Math.floor(i / 239) % 2));
    dsp.processFrame(Math.sin(2 * Math.PI * 110 * i / rate) * 0.08, 0, output);
    assert.ok(Number.isFinite(output[0]) && Math.abs(output[0]) <= OUTPUT_CEILING);
    delta = Math.max(delta, Math.abs(output[0] - previous)); previous = output[0];
  }
  assert.ok(delta < 0.025, `Unexpected sample discontinuity: ${delta}`);
  assert.equal(dsp.faulted, false);
});

test('the actual worklet and the local DSP produce identical samples for identical input/settings', async () => {
  let Processor;
  globalThis.sampleRate = 48000;
  globalThis.AudioWorkletProcessor = class { constructor() { this.port = {postMessage() {}, onmessage: null}; } };
  globalThis.registerProcessor = (name, value) => { assert.equal(name, 'street-banker-noise-lab-v1'); Processor = value; };
  await import('../../noise_lab/static/engine/processor.mjs');
  const settings = recipe('slow-orbit');
  const worklet = new Processor({processorOptions: {recipe: settings, bypass: false}});
  const local = new NoiseDSP(48000, settings);
  for (let block = 0; block < 100; block++) {
    const left = Float32Array.from({length: 128}, (_, i) => Math.sin((block * 128 + i) / 20) * 0.7);
    const right = Float32Array.from(left, value => -value);
    const rendered = [new Float32Array(128), new Float32Array(128)];
    const expected = [new Float32Array(128), new Float32Array(128)];
    if (block === 20) { const next = recipe('dark-room'); worklet.port.onmessage({data: {type: 'recipe', recipe: next}}); local.setRecipe(next); }
    if (block === 30) { worklet.port.onmessage({data: {type: 'bypass', value: true}}); local.setBypass(true); }
    worklet.process([[left, right]], [rendered]); local.processBlock([left, right], expected);
    assert.deepEqual(rendered, expected);
  }
  delete globalThis.AudioWorkletProcessor; delete globalThis.registerProcessor; delete globalThis.sampleRate;
});

test('original procedural loops are deterministic, eight seconds, finite, and fade to zero at the seam', () => {
  for (const id of ['harmonic-pluck', 'pulse-bass']) {
    const a = createDemo(id, 8000); const b = createDemo(id, 8000);
    assert.deepEqual(a, b); assert.equal(a.duration, 8); assert.match(a.name, /synthetic/);
    assert.equal(a.channels[0][0], 0); assert.equal(a.channels[0].at(-1), 0);
    assert.ok(a.channels[0].every(value => Number.isFinite(value) && Math.abs(value) < 0.75));
    assert.ok(a.channels[0].some(value => Math.abs(value) > 0.1));
  }
});

test('WAV preflight accepts declared PCM/float mono/stereo forms and preserves stereo polarity', () => {
  for (const bits of [16, 24, 32]) for (const channels of [1, 2]) {
    const source = fixture({bits, channels}); const info = inspectWav(source);
    assert.equal(info.bits, bits); assert.equal(info.channels, channels);
    const decoded = decodeWav(source, 16000);
    assert.equal(decoded.channels[0].length, 1600);
    if (channels === 2) for (let i = 0; i < 1600; i++) assert.ok(Math.abs(decoded.channels[0][i] + decoded.channels[1][i]) < 0.0001);
  }
  const decoded = decodeWav(fixture({encoding: 3, bits: 32}), 8000);
  assert.equal(decoded.channels[0].length, 800);
});

test('WAV preflight rejects decode bombs, truncated layout, excessive duration, unsupported codecs and invalid floats', () => {
  const oversized = new ArrayBuffer(MAX_FILE_BYTES + 1); assert.throws(() => inspectWav(oversized));
  const long = fixture({frames: 31 * 8000}); assert.throws(() => inspectWav(long), /30 seconds/);
  assert.throws(() => inspectWav(fixture({channels: 3})), /mono\/stereo/);
  assert.throws(() => inspectWav(fixture({encoding: 65534})), /mono\/stereo/);
  const badLength = fixture(); new DataView(badLength).setUint32(40, 0xffffffff, true); assert.throws(() => inspectWav(badLength), /truncated/);
  const badRate = fixture(); new DataView(badRate).setUint32(24, 4000000000, true); assert.throws(() => inspectWav(badRate));
  const badAlign = fixture(); new DataView(badAlign).setUint16(32, 60000, true); assert.throws(() => inspectWav(badAlign), /inconsistent/);
  const badFloat = fixture({bits: 32, encoding: 3}); new DataView(badFloat).setFloat32(48, NaN, true); assert.throws(() => decodeWav(badFloat, 8000), /nonfinite/);
  const unknown = new ArrayBuffer(44); assert.throws(() => inspectWav(unknown), /RIFF WAV/);
});

test('export encoding preserves channel layout and cannot round peaks beyond the DSP ceiling', () => {
  const dsp = new NoiseDSP(8000, recipe('metal-bloom', {level: 0, texture: 100, mix: 100}));
  const channels = [new Float32Array(8000), new Float32Array(8000)]; const output = new Float32Array(2);
  for (let i = 0; i < 8000; i++) { dsp.processFrame(i % 2 ? 1 : -1, 0, output); channels[0][i] = output[0]; channels[1][i] = output[1]; }
  const wav = encodeWav(channels, 8000); const info = inspectWav(wav); assert.equal(info.channels, 2);
  const view = new DataView(wav);
  for (let offset = 44; offset < wav.byteLength; offset += 2) assert.ok(Math.abs(view.getInt16(offset, true) / 32768) <= OUTPUT_CEILING);
});

function fakeContext() {
  const gain = () => ({value: 0, cancelScheduledValues() {}, setValueAtTime(value) { this.value = value; }, linearRampToValueAtTime(value) { this.value = value; }});
  return {analysers: [], connections: [], audioWorklet: {}, sampleRate: 8000, currentTime: 0, state: 'running', destination: {},
    createGain() { const context = this; return {gain: gain(), connect(node) { context.connections.push({from: this, to: node}); return node; }, disconnect() {}}; },
    createChannelSplitter() { return {connect(node) { return node; }, disconnect() {}}; },
    createAnalyser() { const node = {sample: 0, reads: 0, getFloatTimeDomainData(samples) { this.reads++; samples.fill(this.sample); }, disconnect() { this.disconnected = true; }}; this.analysers.push(node); return node; },
    createBuffer(channels, length) { return {copyToChannel() {}, numberOfChannels: channels, length}; },
    createBufferSource() { return {connect(node) { return node; }, disconnect() {}, start() {}, stop() { this.onended?.(); }}; },
    async resume() { this.state = 'running'; }, async close() { this.state = 'closed'; },
  };
}
function installFakeWorklet() {
  const previous = globalThis.AudioWorkletNode;
  globalThis.AudioWorkletNode = class { constructor() { this.port = {postMessage() {}, close() {}}; } connect(node) { return node; } disconnect() {} };
  return () => { globalThis.AudioWorkletNode = previous; };
}

test('source load failures retain working audio; asynchronous stale imports cannot replace a newer source', async () => {
  const restore = installFakeWorklet(); const engine = new NoiseEngine(fakeContext());
  try {
    engine.loadDemo('harmonic-pluck'); const before = engine.getInfo();
    await assert.rejects(() => engine.loadFile({size: 44, arrayBuffer: async () => new ArrayBuffer(44)}));
    assert.deepEqual(engine.getInfo(), before);
    let finish; const pending = engine.loadFile({size: 1644, name: 'old.wav', arrayBuffer: () => new Promise(resolve => { finish = resolve; })});
    engine.loadDemo('pulse-bass'); finish(fixture());
    await assert.rejects(pending, error => error.name === 'AbortError');
    assert.match(engine.getInfo().name, /Pulse bass/);
  } finally { await engine.dispose(); restore(); }
});

test('WAV export supports a recipe snapshot, cancellation, edit invalidation and an explicit tail', async () => {
  const restore = installFakeWorklet(); const engine = new NoiseEngine(fakeContext());
  try {
    const bytes = fixture(); await engine.loadFile({size: bytes.byteLength, name: 'test.wav', arrayBuffer: async () => bytes});
    const withoutTail = await engine.exportWav({includeTail: false, recipe: recipe(), bypass: false});
    const info = inspectWav(await withoutTail.arrayBuffer()); assert.equal(info.frames, 800);
    const withTail = await engine.exportWav({includeTail: true}); assert.equal(inspectWav(await withTail.arrayBuffer()).frames, 16800);
    const cancelled = engine.exportWav(); engine.cancelExport(); await assert.rejects(cancelled, error => error.name === 'AbortError');
    const stale = engine.exportWav(); engine.setRecipe(recipe('slow-orbit')); await assert.rejects(stale, error => error.name === 'AbortError');
    const replaced = engine.exportWav(); engine.loadDemo('pulse-bass'); await assert.rejects(replaced, error => error.name === 'AbortError');
    await assert.rejects(() => engine.exportWav({recipe: {schemaVersion: 9}}));
  } finally { await engine.dispose(); restore(); }
});

test('transport Stop cancels an in-flight Play; disposal is idempotent and releases source state', async () => {
  const restore = installFakeWorklet(); const context = fakeContext(); const engine = new NoiseEngine(context);
  try {
    engine.loadDemo('harmonic-pluck');
    const pending = engine.play(); engine.stop(); await pending;
    assert.equal(engine.getInfo().playing, false);
    await engine.play(); assert.equal(engine.getInfo().playing, true);
    engine.stop(); engine.stop(); assert.equal(engine.getInfo().playing, false);
    await engine.dispose(); await engine.dispose(); assert.equal(context.state, 'closed');
    assert.equal(engine.getInfo().duration, 0); assert.throws(() => engine.loadDemo('pulse-bass'), /closed/);
  } finally { restore(); }
});

test('browser support reporting is capability-based and rejects insecure/missing APIs', () => {
  const secure = globalThis.isSecureContext; globalThis.isSecureContext = false;
  assert.equal(supportsAudio().supported, false); assert.match(supportsAudio().reason, /HTTPS/);
  globalThis.isSecureContext = true; assert.equal(supportsAudio().supported, false);
  globalThis.isSecureContext = secure;
});


test('meter math measures absolute PCM peaks, preserves stereo differences, and rejects invalid samples', () => {
  assert.equal(samplePeak(new Float32Array([0, -.5, .25])), .5);
  assert.equal(samplePeak(new Float32Array([0, 0])), 0);
  assert.equal(samplePeak(new Float32Array([1, NaN])), null);
  assert.equal(samplePeak(new Float32Array([Infinity])), null);
  assert.ok(Math.abs(decibels(.5) + 6.020599913) < .000001);
  assert.equal(meterPercent(0), 0);
  assert.equal(meterPercent(null), 0);
  assert.equal(meterPercent(NaN), 0);
  assert.equal(meterPercent(100), 100);
  assert.equal(meterPercent(.0000001), 0);
});

test('peak markers hold 1.2 seconds, release, and immediately clear on Stop or invalid data', () => {
  const hold = new PeakHold();
  assert.equal(hold.update(.5, 0, true), .5);
  assert.equal(hold.update(.1, 1199, true), .5);
  assert.equal(hold.update(.1, 1200, true), .1);
  assert.equal(hold.update(.8, 1300, true), .8);
  assert.equal(hold.update(.8, 1301, false), 0);
  assert.equal(hold.update(.2, 1400, true), .2);
  assert.equal(hold.update(null, 1401, true), 0);
});

test('meter taps are passive, output follows master, reads stop when transport suspends or disposes', async () => {
  const restore = installFakeWorklet(); const context = fakeContext(); const engine = new NoiseEngine(context);
  try {
    engine.loadDemo('harmonic-pluck');
    context.analysers.forEach((node, index) => { node.sample = [0.5, 0.25, 0.125, 0.0625][index]; });
    assert.deepEqual(engine.getLevels(), {input: [0, 0], output: [0, 0]});
    assert.ok(context.analysers.every(node => node.reads === 0));
    const toSpeakers = context.connections.filter(c => c.to === context.destination);
    assert.equal(toSpeakers.length, 1, 'No metering branch is routed back into the audible mix.');
    const master = toSpeakers[0].from;
    assert.equal(context.connections.filter(c => c.from === master).length, 2, 'Master feeds speakers and the output-only metering tap.');
    await engine.play();
    assert.deepEqual(engine.getLevels(), {input: [.5, .25], output: [.125, .0625]});
    context.state = 'suspended';
    assert.deepEqual(engine.getLevels(), {input: [0, 0], output: [0, 0]});
    assert.ok(context.analysers.every(node => node.reads === 1));
    context.state = 'running'; engine.stop();
    assert.deepEqual(engine.getLevels(), {input: [0, 0], output: [0, 0]});
    await engine.dispose();
    assert.ok(context.analysers.every(node => node.disconnected));
    assert.deepEqual(engine.getLevels(), {input: [0, 0], output: [0, 0]});
  } finally { await engine.dispose(); restore(); }
});

test('generated audio uses protected processing and WAV export without changing recipe', async () => {
  const restore = installFakeWorklet(), context = fakeContext();
  context.decodeAudioData = async () => ({numberOfChannels:1,duration:1,sampleRate:8000,getChannelData:()=>new Float32Array(8000).fill(.2)});
  const engine = new NoiseEngine(context);
  try {
    engine.loadDemo('harmonic-pluck'); engine.setRecipe(recipe());
    const info = await engine.loadGenerated(new ArrayBuffer(256));
    assert.equal(info.name,'ElevenLabs generated sound'); assert.equal(info.playing,false);
    const output = await engine.exportWav({includeTail:false});
    assert.equal(inspectWav(await output.arrayBuffer()).frames,8000);
  } finally {await engine.dispose();restore();}
});
test('invalid and late generated decodes retain the previously loaded source', async () => {
  const restore = installFakeWorklet(), context = fakeContext(), engine = new NoiseEngine(context);
  try {
    engine.loadDemo('harmonic-pluck'); const original=engine.getInfo().name;
    context.decodeAudioData=async()=>({numberOfChannels:1,duration:31,sampleRate:8000});
    await assert.rejects(engine.loadGenerated(new ArrayBuffer(256)));assert.equal(engine.getInfo().name,original);
    let finish;context.decodeAudioData=()=>new Promise(resolve=>finish=resolve);
    const pending=engine.loadGenerated(new ArrayBuffer(256));engine.loadDemo('pulse-bass');
    finish({numberOfChannels:1,duration:1,sampleRate:8000,getChannelData:()=>new Float32Array(8000)});
    await assert.rejects(pending,error=>error.name==='AbortError');assert.match(engine.getInfo().name,/Pulse bass/);
    context.decodeAudioData=async()=>({numberOfChannels:1,duration:1,sampleRate:8000,getChannelData:()=>new Float32Array(8000)});
    await assert.rejects(engine.loadGenerated(new ArrayBuffer(256),()=>false));assert.match(engine.getInfo().name,/Pulse bass/);
  } finally {await engine.dispose();restore();}
});
