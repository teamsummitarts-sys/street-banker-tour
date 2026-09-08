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
  replaceChildren() {} append() {} remove() {} focus() { this.focused = true; }
  scrollIntoView() { this.scrolled = true; }
  removeAttribute(key) { delete this[key]; }
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
  const ticks = Object.fromEntries(['texture','motion','space','mix','level'].map(key => [key,
    Array.from({length: 41}, (_, i) => { const e = new Element(); e.dataset.dialTick = String(i); return e; })]));
  const created = [];
  const resetButtons = ['texture','motion','space','mix','level'].map(key => {
    const element = new Element(); element.dataset.resetMacro = key; return element;
  });
  globalThis.document = {getElementById: get, querySelector: get,
    querySelectorAll: selector => {
      const key = selector.match(/data-macro="([a-z]+)"/);
      if (key) return ticks[key[1]];
      if (selector === '[data-reset-macro]') return resetButtons;
      return loops;
    }, addEventListener() {},
    createElement: () => { const e = new Element(); created.push(e); return e; },
    body: {append() {}, dataset: {csrf: 'test-csrf'}}};
  const requests = [];
  const availability = {ai_generation: true, generation: {configured: true, usage: {remaining: 20}}};
  let respond = async () => ({ok: true, json: async () => availability});
  globalThis.fetch = async (url, options) => { requests.push({url, options}); return respond(url, options); };
  const lifecycle = new Element();
  globalThis.window = lifecycle;
  Object.defineProperty(globalThis, 'navigator', {configurable: true, value: {}});
  globalThis.isSecureContext = true;
  globalThis.AudioContext = function() {};
  globalThis.AudioWorkletNode = function() {};
  globalThis.requestAnimationFrame = () => 1;
  globalThis.cancelAnimationFrame = () => {};
  const creation = deferred();
  const audio = {
    playing: false, playCalls: 0, stopCalls: 0, onstatechange: null,
    bypassCalls: [], setRecipe() {}, setBypass(value) { this.bypassCalls.push(value); }, getPosition() { return 0; },
    getLevels() { return {input: [0.5, 0.25], output: [0.125, 0.0625]}; },
    getInfo() { return {playing: this.playing, duration: 8, channels: 1, sampleRate: 8000, name: 'Test loop'}; },
    loadDemo() { return this.getInfo(); },
    async play() { this.playCalls++; this.playing = true; },
    stop() { this.stopCalls++; this.playing = false; },
    disposeCalls: 0, dispose() { this.disposeCalls++; },
    async exportWav() { return new Blob(['test PCM'], {type: 'audio/wav'}); },
    cancelExport() {},
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
  return {get, ticks, resetButtons, choose, startImport, creation, audio, lifecycle, created, requests,
    setResponse: fn => { respond = fn; }};
}

const generated = recipe => ({ok: true, redirected: false,
  json: async () => ({recipe, generationVersion: 'noise-lab-prompt-1.0.0',
    generation: {configured: true, usage: {remaining: 19}}})});

async function readyToGenerate() {
  const context = await setup();
  const playing = context.get('play').click();
  context.creation.resolve(context.audio); await playing;
  context.get('sound-prompt').value = 'Metallic growl, keep the pick attack';
  return context;
}

test('the source-required action enables effects without starting playback', async () => {
  const {get, creation, audio} = await setup();
  assert.equal(get('source-required').hidden, false);
  assert.equal(get('generate-sound').disabled, true);
  const loading = get('load-selected-source').click();
  creation.resolve(audio);
  await loading;
  assert.equal(get('source-required').hidden, true);
  assert.equal(get('generate-sound').disabled, false);
  assert.equal(get('sound-prompt').focused, true);
  assert.equal(audio.playCalls, 0);
  assert.match(get('export-format').textContent, /16-bit PCM WAV · 8 kHz/);
});

test('clean preview and previous settings are explicitly different listening states', async () => {
  const {get, choose} = await readyToGenerate();
  await choose('metal-bloom');
  await get('compare-a').click();
  assert.match(get('compare-state').textContent, /Previous settings/);
  assert.equal(get('macro-texture').disabled, true);
  await get('clean').click();
  assert.match(get('compare-state').textContent, /Clean preview · A settings retained/);
  await get('clean').click();
  await get('compare-b').click();
  assert.match(get('compare-state').textContent, /Current settings/);
  assert.equal(get('macro-texture').disabled, false);
});

test('live controls provide momentary clean preview and a persistent effect bypass', async () => {
  const {get, audio} = await readyToGenerate();
  await get('clean').event('pointerdown', {pointerId: 1, currentTarget: get('clean'), preventDefault() {}});
  assert.equal(audio.bypassCalls.at(-1), true);
  assert.match(get('compare-state').textContent, /Clean preview/);
  await get('clean').event('pointerup');
  assert.equal(audio.bypassCalls.at(-1), false);
  await get('engage').click();
  assert.equal(audio.bypassCalls.at(-1), true);
  assert.equal(get('engage').querySelector('.switch-state').textContent, 'BYPASSED');
  await get('engage').click();
  assert.equal(audio.bypassCalls.at(-1), false);
});

test('each macro can reset independently to Clean start and Undo restores it', async () => {
  const {get, resetButtons} = await readyToGenerate();
  get('value-texture').value = '44'; await get('value-texture').event('change');
  await resetButtons.find(button => button.dataset.resetMacro === 'texture').click();
  assert.equal(get('value-texture').value, '10');
  assert.equal(get('value-motion').value, '0');
  await get('undo').click();
  assert.equal(get('value-texture').value, '44');
});

test('generation sends only description, applies a valid patch without raising level, and supports Undo', async () => {
  const {get, setResponse, requests} = await readyToGenerate();
  get('value-level').value = '-30'; await get('value-level').event('change');
  setResponse(async () => generated(recipe('metal-bloom')));
  await get('generate-sound').click();
  const posted = requests.filter(r => r.options?.method === 'POST');
  assert.equal(posted.length, 1);
  assert.deepEqual(JSON.parse(posted[0].options.body), {prompt: 'Metallic growl, keep the pick attack'});
  assert.equal(posted[0].options.headers['X-Noise-Lab-CSRF'], 'test-csrf');
  assert.equal(get('value-texture').value, '76');
  assert.equal(get('value-level').value, '-30');
  assert.equal(get('generated-recipe').hidden, false);
  assert.match(get('generated-recipe-summary').textContent, /Changed/);
  await get('undo').click();
  assert.equal(get('value-texture').value, '10');
  assert.equal(get('value-level').value, '-30');
});

test('late generation cannot overwrite newer edits or revive a cleared session', async () => {
  const {get, setResponse, choose} = await readyToGenerate();
  const pending = deferred(); setResponse(() => pending.promise);
  const task = get('generate-sound').click();
  await choose('dark-room');
  pending.resolve(generated(recipe('metal-bloom'))); await task;
  assert.equal(get('preset').value, 'dark-room');
  assert.match(get('generation-status').textContent, /discarded/i);
  const next = deferred(); setResponse(() => next.promise);
  const after = get('generate-sound').click();
  await get('clear-session').click();
  next.resolve(generated(recipe('metal-bloom'))); await after;
  assert.equal(get('preset').value, 'clean');
  assert.equal(get('sound-prompt').value, '');
});

test('generation cancellation, malformed settings and authentication failure retain patch and presets', async () => {
  const {get, setResponse, choose} = await readyToGenerate();
  await choose('dark-room');
  const pending = deferred(); setResponse(() => pending.promise);
  const task = get('generate-sound').click();
  await get('cancel-generation').click();
  pending.resolve(generated(recipe('metal-bloom'))); await task;
  assert.equal(get('preset').value, 'dark-room');
  assert.equal(get('preset').disabled, false);
  setResponse(async () => generated({...recipe('metal-bloom'), code: 'never execute'}));
  await get('generate-sound').click();
  assert.equal(get('preset').value, 'dark-room');
  assert.match(get('generation-status').textContent, /retained/);
  setResponse(async () => ({ok: true, redirected: true, json: () => { throw Error('must not parse login HTML'); }}));
  await get('generate-sound').click();
  assert.match(get('generation-status').textContent, /sign in/i);
  assert.equal(get('preset').value, 'dark-room');
});

for (const [code, expected] of [
  ['provider_quota', /insufficient API credits or quota/],
  ['provider_credit', /exhausted API credit balance/],
  ['provider_spend', /spending limit reached/],
  ['provider_usage', /assigned monthly usage limit reached/],
  ['provider_rate_limit', /Wait briefly before trying again/],
  ['provider_limit', /exact cause is unavailable/],
]) {
  test(`${code} gives a specific action, retains the patch, and does not retry`, async () => {
    const {get, setResponse, choose, requests} = await readyToGenerate();
    await choose('dark-room');
    setResponse(async () => ({ok: false, status: 503, json: async () => ({
      error: code, message: 'untrusted provider message',
      generation: {usage: {remaining: 19}},
    })}));
    await get('generate-sound').click();
    const message = get('generation-status').textContent;
    assert.match(message, expected);
    assert.match(message, /working patch is retained/);
    assert.doesNotMatch(message, /untrusted/);
    if (code === 'provider_rate_limit') assert.doesNotMatch(message, /billing|credits/i);
    assert.equal(get('preset').value, 'dark-room');
    assert.equal(get('preset').disabled, false);
    assert.equal(get('value-texture').value, String(recipe('dark-room').macros.texture));
    assert.equal(requests.filter(r => r.options?.method === 'POST').length, 1);
    await choose('clean');
    assert.equal(get('preset').value, 'clean');
  });
}

test('empty descriptions and unavailable generation never send a POST', async () => {
  const {get, setResponse, requests} = await readyToGenerate();
  get('sound-prompt').value = '   ';
  await get('generate-sound').click();
  assert.equal(requests.filter(r => r.options?.method === 'POST').length, 0);
  setResponse(async () => ({ok: true, json: async () => ({ai_generation: false,
    generation: {configured: false, usage: {remaining: 20}}})}));
  await get('refresh-generation').click();
  assert.equal(get('generate-sound').disabled, true);
  assert.equal(get('preset').disabled, false);
  assert.match(get('generation-status').textContent, /unavailable/i);
});

test('account save sends only a named settings snapshot and keeps the iPhone session open', async () => {
  const {get, setResponse, requests, created, audio} = await readyToGenerate();
  const id = '4bf647db-1234-4567-8901-234567890abc';
  const patch = {id, name: 'My growl', headVersion: 1, updated: '2026-09-05T00:00:00Z',
    versions: [{version: 1, name: 'My growl', created: '2026-09-05T00:00:00Z', recipe: recipe('clean')}]};
  setResponse(async (url, options) => ({ok: true, json: async () =>
    url.endsWith('/capabilities') ? {ai_generation: true, cloud_patch_storage: true,
      generation: {configured: true, usage: {remaining: 19}}}
      : options?.method === 'POST' ? {patch} : {patches: []}}));
  await get('refresh-generation').click();
  get('patch-name').value = 'My growl';
  await get('save-patch').click();
  const posted = requests.filter(r => r.options?.method === 'POST');
  assert.equal(posted.length, 1);
  assert.equal(posted[0].url, '/noise-lab/api/patches');
  const data = JSON.parse(posted[0].options.body);
  assert.deepEqual(Object.keys(data).sort(), ['name', 'recipe', 'requestId']);
  assert.equal(data.name, 'My growl');
  assert.deepEqual(data.recipe, recipe('clean'));
  assert.equal(posted[0].options.headers['X-Noise-Lab-CSRF'], 'test-csrf');
  assert.match(get('patch-status').textContent, /Saved.*version 1/i);
  assert.equal(get('working-save-state').textContent, 'B settings · Saved v1');
  await get('save-patch').click();
  assert.equal(requests.filter(r => r.options?.method === 'POST').length, 1, 'A repeated tap after acknowledgment does not create a duplicate.');
  assert.equal(audio.disposeCalls, 0);
  assert.equal(created.some(element => element.href), false);
  get('value-texture').value = '32';
  await get('value-texture').event('change');
  assert.equal(get('working-save-state').textContent, 'B settings · Changes not saved');
  await get('undo').click();
  assert.equal(get('working-save-state').textContent, 'B settings · Saved v1');
});

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

test('preparing an export does not navigate; saving targets a separate context', async () => {
  const {get, created} = await setup();
  await get('export-recipe').click();
  assert.equal(get('file-ready').hidden, false);
  assert.match(get('save-download').href, /^blob:/);
  assert.equal(get('save-download').target, '_blank');
  assert.equal(get('save-download').rel, 'noopener');
  assert.ok(!created.some(e => e.href), 'No synthetic download navigation.');
  await get('clear-session').click();
  assert.equal(get('file-ready').hidden, true);
  assert.equal(get('save-download').href, undefined);
});

test('iPhone share is invoked only by the save gesture; cancel retains edits and prepared file', async () => {
  const {get, choose} = await setup();
  let shared = 0;
  navigator.canShare = ({files}) => files[0] instanceof File;
  navigator.share = async () => { shared++; throw new DOMException('Cancelled', 'AbortError'); };
  await choose('metal-bloom');
  await get('export-recipe').click();
  assert.equal(shared, 0);
  assert.equal(get('share-download').hidden, false);
  await get('share-download').click();
  assert.equal(shared, 1);
  assert.equal(get('preset').value, 'metal-bloom');
  assert.equal(get('file-ready').hidden, false);
  assert.match(get('notice').textContent, /cancelled/i);
  await get('undo').click();
  assert.equal(get('preset').value, 'clean');
  await get('clear-session').click();
});

test('returning from a cached file preview preserves source and undo; full unload disposes audio', async () => {
  const {get, choose, creation, audio, lifecycle} = await setup();
  const start = get('play').click(); creation.resolve(audio); await start;
  await choose('metal-bloom');
  await lifecycle.event('pagehide', {persisted: true});
  assert.equal(audio.playing, false);
  assert.equal(audio.disposeCalls, 0);
  await lifecycle.event('pageshow', {persisted: true});
  assert.equal(get('preset').value, 'metal-bloom');
  assert.equal(get('export-audio').disabled, false);
  await get('undo').click();
  assert.equal(get('preset').value, 'clean');
  await lifecycle.event('pagehide', {persisted: false});
  assert.equal(audio.disposeCalls, 1);
});

test('WAV rendering prepares a file without invoking the OS; a later save tap shares it', async () => {
  const {get, creation, audio} = await setup();
  let sharedFile;
  navigator.canShare = () => true;
  navigator.share = async ({files}) => { sharedFile = files[0]; };
  const start = get('play').click(); creation.resolve(audio); await start;
  const render = deferred(); audio.exportWav = () => render.promise;
  const pending = get('export-audio').click();
  assert.equal(sharedFile, undefined);
  render.resolve(new Blob(['PCM fixture'], {type: 'audio/wav'})); await pending;
  assert.equal(sharedFile, undefined);
  assert.match(get('save-download').download, /\.wav$/);
  const saving = get('share-download').click();
  assert.ok(sharedFile instanceof File, 'Sharing starts synchronously from the new tap.');
  assert.equal(sharedFile.type, 'audio/wav');
  assert.equal(await sharedFile.text(), 'PCM fixture');
  await saving;
  assert.equal(audio.disposeCalls, 0);
  assert.equal(get('file-ready').hidden, false);
  await get('clear-session').click();
});

test('unsupported or failed native sharing keeps a working manual download', async () => {
  const {get} = await setup();
  navigator.canShare = () => false;
  navigator.share = async () => { throw new Error('Sharing unavailable'); };
  await get('export-recipe').click();
  assert.equal(get('share-download').hidden, true);
  assert.match(get('save-download').href, /^blob:/);
  navigator.canShare = () => true;
  await get('export-recipe').click();
  await get('share-download').click();
  assert.equal(get('file-ready').hidden, false);
  assert.match(get('save-download').href, /^blob:/);
  assert.match(get('error').textContent, /Download file/);
  await get('clear-session').click();
});

function storedPatch(versions = ['clean']) {
  return {id: '4bf647db-1234-4567-8901-234567890abc', name: 'Private growl', headVersion: versions.length,
    updated: '2026-09-05T00:00:00Z', versions: versions.map((id, i) => ({version: i+1,
      name: 'Private growl', created: '2026-09-05T00:00:00Z', recipe: recipe(id)}))};
}
async function enableLibrary(context, respond) {
  context.setResponse(async (url, options) => url.endsWith('/capabilities')
    ? {ok: true, json: async () => ({ai_generation: true, cloud_patch_storage: true, account_scope: 'test-csrf', generation: {configured: true, usage: {remaining: 19}}})}
    : respond(url, options));
  await context.get('refresh-generation').click();
}
const ok = data => ({ok: true, json: async () => data});

test('restoring an old saved version supports Undo and subsequent saving appends at the latest head', async () => {
  const ctx = await readyToGenerate(), {get, choose, requests} = ctx;
  const patch = storedPatch(['clean', 'dark-room']);
  await enableLibrary(ctx, async (_url, options) => ok(options?.method === 'POST' ? {patch: storedPatch(['clean','dark-room','clean'])} : {patches: [patch], patch}));
  await choose('metal-bloom');
  get('patch-list').value = patch.id; await get('patch-list').event('change');
  assert.equal(get('preset').value, 'metal-bloom', 'Browsing never replaces unsaved settings.');
  get('patch-version').value = '1'; await get('load-patch-version').click();
  assert.equal(get('preset').value, 'clean');
  await get('undo').click(); assert.equal(get('preset').value, 'metal-bloom');
  await get('redo').click(); assert.equal(get('preset').value, 'clean');
  await get('save-version').click();
  const posted = requests.filter(r => r.options?.method === 'POST');
  assert.equal(posted.length, 1);
  assert.equal(JSON.parse(posted[0].options.body).baseVersion, 2);
  assert.match(get('patch-status').textContent, /version 3/);
});

test('a save acknowledges its snapshot without overwriting edits made while waiting', async () => {
  const ctx = await readyToGenerate(), {get, choose} = ctx;
  const wait = deferred();
  await enableLibrary(ctx, async (_url, options) => options?.method === 'POST' ? wait.promise : ok({patches: []}));
  get('patch-name').value = 'Private growl';
  const saving = get('save-patch').click();
  await choose('metal-bloom');
  wait.resolve(ok({patch: storedPatch()})); await saving;
  assert.equal(get('preset').value, 'metal-bloom');
  assert.match(get('patch-status').textContent, /newer edits are not saved/);
  assert.match(get('patch-save-state').textContent, /not saved/);
});

test('uncertain saves reuse the request ID; conflicts and expired sessions preserve working audio', async () => {
  const ctx = await readyToGenerate(), {get, choose, requests, audio} = ctx;
  let attempt = 0;
  await enableLibrary(ctx, async (_url, options) => {
    if (options?.method !== 'POST') return ok({patches: []});
    if (++attempt === 1) throw Error('Offline');
    if (attempt === 2) return {ok: false, status: 409, json: async () => ({error: 'version_conflict'})};
    return {ok: false, status: 401, json: async () => ({})};
  });
  await choose('dark-room'); get('patch-name').value = 'Private growl';
  await get('save-patch').click(); await get('save-patch').click();
  const posts = requests.filter(r => r.options?.method === 'POST');
  assert.equal(JSON.parse(posts[0].options.body).requestId, JSON.parse(posts[1].options.body).requestId);
  assert.match(get('patch-status').textContent, /Another save/);
  await get('save-patch').click();
  assert.match(get('patch-status').textContent, /sign-in/);
  assert.equal(get('save-version').disabled, true);
  assert.equal(get('preset').value, 'dark-room'); assert.equal(audio.disposeCalls, 0);
});

test('history export prepares a separate iPhone download and deletion requires a second explicit action', async () => {
  const ctx = await readyToGenerate(), {get, requests, choose, audio} = ctx;
  const patch = storedPatch(['clean','dark-room']);
  await enableLibrary(ctx, async (url, options) => ok(options?.method === 'DELETE' ? {deleted: true}
    : url.endsWith('/export') ? {archiveVersion: 1, patch} : {patches: [patch], patch}));
  await choose('metal-bloom');
  get('patch-list').value = patch.id; await get('patch-list').event('change');
  await get('export-patch-history').click();
  assert.equal(get('file-ready').hidden, false);
  assert.equal(get('save-download').target, '_blank');
  assert.match(get('prepared-name').textContent, /noise-lab-patch/);
  await get('delete-patch').click();
  assert.equal(requests.some(r => r.options?.method === 'DELETE'), false);
  await get('cancel-delete-patch').click();
  await get('confirm-delete-patch').click();
  assert.equal(requests.some(r => r.options?.method === 'DELETE'), false);
  await get('delete-patch').click(); await get('confirm-delete-patch').click();
  const deletions = requests.filter(r => r.options?.method === 'DELETE');
  assert.equal(deletions.length, 1);
  assert.deepEqual(JSON.parse(deletions[0].options.body), {baseVersion: 2});
  assert.equal(get('preset').value, 'metal-bloom'); assert.equal(audio.disposeCalls, 0);
  assert.match(get('patch-status').textContent, /deleted from the active library/);
  await get('clear-session').click();
});

test('a cleared session ignores late library responses and a switched account cannot reuse its library', async () => {
  const ctx = await readyToGenerate(), {get, choose} = ctx;
  const wait = deferred();
  await enableLibrary(ctx, async (_url, options) => options?.method === 'POST' ? wait.promise : ok({patches: []}));
  get('patch-name').value = 'Private growl';
  const saving = get('save-patch').click();
  await get('clear-session').click();
  wait.resolve(ok({patch: storedPatch()})); await saving;
  assert.equal(get('patch-name').value, '');
  assert.equal(get('save-version').disabled, true);
  await choose('dark-room');
  ctx.setResponse(async () => ok({ai_generation: true, cloud_patch_storage: true, account_scope: 'another-account-csrf'}));
  await get('refresh-generation').click();
  assert.equal(get('save-patch').disabled, true);
  assert.equal(get('generate-sound').disabled, true);
  assert.equal(get('preset').value, 'dark-room');
});


test('Display settings keep the recipe, source and private save flow intact', async () => {
  const {get, audio, requests} = await readyToGenerate();
  get('display-brightness').value = 'bright';
  await get('display-brightness').event('change');
  assert.equal(document.body.dataset.display, 'bright');
  assert.equal(get('value-level').value, '-12');
  assert.equal(audio.playing, true);
  await get('open-library').click();
  assert.equal(get('patch-library').focused, true);
  assert.equal(get('patch-library').scrolled, true);
  assert.equal(requests.filter(r => r.options?.method === 'POST').length, 0);
  await get('stop').click();
  assert.equal(get('input-reading').textContent, '—');
  assert.equal(get('output-reading').textContent, '—');
});

test('signal desk displays measured levels and clears held markers after Stop', async () => {
  const {get} = await readyToGenerate();
  assert.equal(get('input-reading').textContent, '-6.0');
  assert.equal(get('output-reading').textContent, '-18.1');
  assert.equal(get('input-l-hold').hidden, false);
  assert.match(get('output-r-meter')['aria-valuetext'], /-24.1 dBFS/);
  await get('stop').click();
  assert.equal(get('input-l-hold').hidden, true);
  assert.equal(get('output-r-hold').hidden, true);
  assert.equal(get('input-l-meter')['aria-valuetext'], 'Stopped');
  assert.equal(get('input-l-fill').style.clipPath, 'inset(0 100% 0 0)');
});


test('engraved scale follows the heard settings through exact entry, A/B and Undo', async () => {
  const {get, ticks} = await setup();
  const lastLit = key => ticks[key].findLastIndex(tick => tick['data-active'] === 'true');
  get('value-texture').value = '50'; await get('value-texture').event('change');
  assert.equal(lastLit('texture'), 20, '50% points to the middle hashmark');
  await get('compare-a').click();
  assert.equal(get('value-texture').value, '10');
  assert.equal(lastLit('texture'), 4, 'A shows the previous sound on the scale');
  await get('compare-b').click();
  assert.equal(lastLit('texture'), 20);
  await get('undo').click();
  assert.equal(lastLit('texture'), 4);
  get('value-level').value = '-60'; await get('value-level').event('change');
  assert.equal(lastLit('level'), 0);
  get('value-level').value = '0'; await get('value-level').event('change');
  assert.equal(lastLit('level'), 40, '0 dB reaches the final mark without changing the allowed gain range');
});
