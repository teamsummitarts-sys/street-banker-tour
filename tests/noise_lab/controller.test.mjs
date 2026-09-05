// Controller event regressions, not a browser/layout or audio-device test.
import test from 'node:test';
import assert from 'node:assert/strict';
import {NoiseEngine, PRESETS} from '../../noise_lab/static/engine/index.mjs';

class Element {
  constructor(id = '') {
    Object.assign(this, {id, value: '', hidden: false, disabled: false, style: {},
      dataset: {}, listeners: {}, lastChild: {textContent: ''},
      min: id.includes('level') ? '-60' : '0', max: id.includes('level') ? '0' : '100',
      validity: {valid: true}});
  }
  addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); }
  setAttribute(key, value) { this[key] = value; }
  querySelector() { return this.span ??= new Element(); }
  replaceChildren() {} append() {} remove() {} focus() {}
  async event(type, event = {}) {
    return Promise.all((this.listeners[type] || []).map(fn => fn({target: this, ...event})));
  }
  click() { return this.disabled ? Promise.resolve() : this.event('click'); }
}

let session = 0;
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return {promise, resolve};
}
const recipe = id => PRESETS.find(preset => preset.id === id).recipe;

async function setup() {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  };
  const loops = ['harmonic-pluck', 'pulse-bass'].map(id => {
    const element = new Element(); element.dataset.loop = id; return element;
  });
  globalThis.document = {getElementById: get, querySelector: get,
    querySelectorAll: () => loops, addEventListener() {},
    createElement: () => new Element(), body: {append() {}}};
  globalThis.window = {addEventListener() {}};
  globalThis.isSecureContext = true;
  globalThis.AudioContext = function() {};
  globalThis.AudioWorkletNode = function() {};
  globalThis.requestAnimationFrame = () => 1;
  globalThis.cancelAnimationFrame = () => {};
  const creation = deferred();
  const audio = {
    playing: false, playCalls: 0, stopCalls: 0, onstatechange: null,
    setRecipe() {}, setBypass() {}, getPosition() { return 0; },
    getInfo() { return {playing: this.playing, duration: 8, channels: 1, sampleRate: 8000, name: 'Test loop'}; },
    loadDemo() { return this.getInfo(); },
    async play() { this.playCalls++; this.playing = true; },
    stop() { this.stopCalls++; this.playing = false; }, dispose() {},
  };
  NoiseEngine.create = () => creation.promise;
  await import(`../../noise_lab/static/ui/controller.mjs?test=${++session}`);
  const choose = async id => { get('preset').value = id; await get('preset').event('change'); };
  const startImport = () => {
    const read = deferred();
    get('recipe-file').files = [{size: 100, text: () => read.promise}];
    const done = get('recipe-file').event('change');
    return {resolve: read.resolve, done};
  };
  return {get, choose, startImport, creation, audio};
}

test('A identifies the preset being auditioned and B retains its own selection', async () => {
  const {get, choose} = await setup();
  await choose('metal-bloom');
  await get('compare-a').click();
  assert.equal(get('value-texture').value, '10');
  assert.equal(get('preset').value, 'clean');
  assert.equal(get('preset-description').textContent, PRESETS[0].description);
  assert.equal(get('macro-texture').disabled, true);
  await get('compare-b').click();
  assert.equal(get('preset').value, 'metal-bloom');
  assert.equal(get('value-texture').value, '76');
});

test('an older recipe read cannot overwrite a newer completed import', async () => {
  const {get, startImport} = await setup();
  const old = startImport();
  const newer = startImport();
  newer.resolve(JSON.stringify(recipe('dark-room'))); await newer.done;
  old.resolve(JSON.stringify(recipe('slow-orbit'))); await old.done;
  assert.equal(get('preset').value, 'dark-room');
  await get('undo').click();
  assert.equal(get('preset').value, 'clean');
});

test('edits and Undo invalidate pending recipe imports', async () => {
  const {get, choose, startImport} = await setup();
  const pending = startImport();
  get('value-texture').value = '99';
  await get('value-texture').event('change');
  pending.resolve(JSON.stringify(recipe('slow-orbit'))); await pending.done;
  assert.equal(get('value-texture').value, '99');
  await choose('metal-bloom');
  const afterEdit = startImport();
  await get('undo').click();
  afterEdit.resolve(JSON.stringify(recipe('dark-room'))); await afterEdit.done;
  assert.equal(get('value-texture').value, '99');
});

test('invalid recipe reports an error and clear-session rejects a pending import', async () => {
  const {get, choose, startImport} = await setup();
  await choose('metal-bloom');
  const invalid = startImport();
  invalid.resolve(JSON.stringify({...recipe('dark-room'), code: 'do not execute'}));
  await invalid.done;
  assert.equal(get('preset').value, 'metal-bloom');
  assert.equal(get('error').hidden, false);
  assert.match(get('error').textContent, /working patch is retained/);
  const pending = startImport();
  await get('clear-session').click();
  pending.resolve(JSON.stringify(recipe('dark-room'))); await pending.done;
  assert.equal(get('preset').value, 'clean');
});

test('Stop cancels a pending Play before an engine exists; a later Play works', async () => {
  const {get, creation, audio} = await setup();
  const pending = get('play').click();
  assert.equal(get('stop').disabled, false);
  await get('stop').click();
  creation.resolve(audio); await pending;
  assert.equal(audio.playCalls, 0);
  assert.equal(audio.playing, false);
  assert.equal(get('play').disabled, false);
  await get('play').click();
  assert.equal(audio.playCalls, 1);
  assert.equal(audio.playing, true);
  await get('stop').click();
  assert.equal(audio.stopCalls, 1);
  assert.equal(audio.playing, false);
});
