import { NoiseEngine, PRESETS, LOOPS, DEFAULT_RECIPE, validateRecipe, supportsAudio } from '../engine/index.mjs';

const $ = id => document.getElementById(id);
const clone = value => JSON.parse(JSON.stringify(value));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const keys = ['texture', 'motion', 'space', 'mix', 'level'];
const controls = Object.fromEntries(keys.map(key => [key, {
  range: $(`macro-${key}`), number: $(`value-${key}`),
  dial: document.querySelector(`[data-macro="${key}"] .dial-hand`)
}]));
let current = validateRecipe(DEFAULT_RECIPE);
let history = [clone(current)];
let cursor = 0;
let comparison = 'b';
let clean = false;
let engine = null;
let creating = null;
let sourceId = LOOPS[0]?.id || 'harmonic-pluck';
let loaded = false;
let loading = false;
let starting = false;
let exporting = false;
let faulted = false;
let gesture = null;
let animation = null;
let generation = 0;
let recipeRevision = 0;
let transportRevision = 0;
let downloadUrls = new Set();
let preparedFile = null;
let fileRevision = 0;

function message(text, error = false) {
  const target = $(error ? 'error' : 'notice');
  $(error ? 'notice' : 'error').hidden = true;
  target.textContent = text;
  target.hidden = !text;
}

function describeError(error, fallback) {
  return typeof error?.message === 'string' && error.message.length < 500 ? error.message : fallback;
}

function sourceDefinition(id) { return LOOPS.find(loop => loop.id === id); }
function selectedPreset(recipe) { return PRESETS.find(preset => same(preset.recipe, recipe)); }
function previousRecipe() { return history[Math.max(0, cursor - 1)]; }
function heardRecipe() { return comparison === 'a' ? previousRecipe() : current; }
function time(seconds) {
  const safe = Math.max(0, Math.floor(Number(seconds) || 0));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`;
}

function applyAudio() {
  if (!engine || faulted) return;
  engine.setRecipe(heardRecipe());
  engine.setBypass(clean);
}

function renderControls() {
  const shown = heardRecipe();
  for (const key of keys) {
    const { range, number, dial } = controls[key];
    const value = shown.macros[key];
    range.value = String(value);
    number.value = String(value);
    range.setAttribute('aria-valuetext', `${value} ${key === 'level' ? 'decibels' : 'percent'}`);
    const min = Number(range.min), max = Number(range.max);
    dial.style.transform = `rotate(${-135 + ((value - min) / (max - min)) * 270}deg)`;
    // Presentation follows the actual recipe, never a simulated signal meter.
    range.disabled = comparison === 'a';
    number.disabled = comparison === 'a';
  }
  const preset = selectedPreset(shown);
  $('preset').value = preset?.id || 'custom';
  $('preset').disabled = comparison === 'a';
  $('preset-description').textContent = preset?.description || 'Custom settings · adjust, compare, and keep what works.';
  $('engine-version').textContent = current.engineVersion;
  $('compare-a').disabled = cursor === 0;
  $('compare-a').setAttribute('aria-pressed', String(comparison === 'a'));
  $('compare-b').setAttribute('aria-pressed', String(comparison === 'b'));
  $('clean').setAttribute('aria-pressed', String(clean));
  $('clean').textContent = clean ? 'Clean comparison on' : 'Compare clean';
  $('undo').disabled = cursor === 0 || comparison === 'a';
  $('redo').disabled = cursor >= history.length - 1 || comparison === 'a';
  $('compare-state').textContent = clean ? `Clean selected · ${comparison.toUpperCase()} patch retained` : `${comparison.toUpperCase()} selected · ${comparison === 'a' ? 'Previous patch · editing locked' : 'Current patch'}`;
}

function renderTransport() {
  const info = engine?.getInfo();
  const playing = Boolean(info?.playing);
  $('play').disabled = loading || !support.supported || faulted;
  $('play').setAttribute('aria-busy', String(loading));
  $('play').querySelector('span').textContent = loading ? 'Loading…' : playing ? 'Playing loop' : 'Play loop';
  $('play').setAttribute('aria-pressed', String(playing));
  $('stop').disabled = !playing && !starting;
  $('import-audio').disabled = loading || !support.supported || faulted;
  $('export-audio').disabled = !loaded || loading || exporting || faulted;
  $('export-audio').setAttribute('aria-busy', String(exporting));
  $('cancel-export').hidden = !exporting;
  $('export-audio').lastChild.textContent = exporting ? ' Rendering…' : 'Prepare WAV';
  document.querySelectorAll('[data-loop]').forEach(button => {
    button.disabled = loading || !support.supported || faulted;
    button.setAttribute('aria-pressed', String(button.dataset.loop === sourceId));
  });
  $('source').setAttribute('aria-busy', String(loading));
  if (loading) $('monitor-state').textContent = 'Loading source…';
  else if (faulted) $('monitor-state').textContent = 'Audio stopped · clear session to retry';
  else $('monitor-state').textContent = playing ? 'Playing locally' : loaded ? 'Stopped · source ready' : 'Ready for a loop';
  updatePosition();
}

function updatePosition() {
  const info = engine?.getInfo();
  const duration = info?.duration || 0;
  const position = duration ? Math.min(duration, Math.max(0, engine.getPosition() || 0)) : 0;
  $('source-time').textContent = `${time(position)} / ${duration ? time(duration) : '—'}`;
  $('playback-position').style.width = `${duration ? (position / duration) * 100 : 0}%`;
  if (info?.playing && animation === null) animation = requestAnimationFrame(tick);
}

function tick() {
  animation = null;
  updatePosition();
}

function updateSource(info, demo = false) {
  loaded = true;
  $('source-name').textContent = info.name || (demo ? sourceDefinition(sourceId)?.name : 'Your audio') || 'Clean source';
  $('source-description').textContent = demo ? sourceDefinition(sourceId)?.description || 'An original synthesized clean loop.' : 'Your local audio. It has not been uploaded.';
  $('source-badge').textContent = demo ? 'Original synthesis' : 'Local file';
  $('source-info').textContent = `${Number(info.duration || 0).toFixed(1)} seconds · ${info.channels === 1 ? 'Mono' : `${info.channels} channels`} · ${Math.round(info.sampleRate / 1000 * 10) / 10} kHz`;
}

async function ensureEngine() {
  if (engine) return engine;
  if (creating) return creating;
  const token = generation;
  // Creation starts inside the user's click, before any network or file awaits.
  const pending = NoiseEngine.create().then(created => {
    if (token !== generation) { created.dispose(); throw new Error('The previous session was cleared. Press Play to start again.'); }
    engine = created;
    created.onstatechange = event => {
      if (engine !== created) return;
      if (event.state === 'fault') {
        faulted = true;
        message(event.message || 'Audio processing stopped safely. Clear this session and try again.', true);
      } else if (event.state === 'suspended') {
        message('Your browser paused audio. Return to this page and press Play to resume.');
      }
      renderTransport();
    };
    applyAudio();
    return created;
  }).finally(() => { if (creating === pending) creating = null; });
  creating = pending;
  return creating;
}

async function loadSource({ loopId, file } = {}) {
  if (loading) return;
  const token = generation;
  loading = true;
  message('');
  renderTransport();
  try {
    const audio = await ensureEngine();
    const info = file ? await audio.loadFile(file) : await audio.loadDemo(loopId || sourceId);
    if (token !== generation) return;
    sourceId = file ? null : loopId || sourceId;
    updateSource(info || audio.getInfo(), !file);
    applyAudio();
    message(file ? 'Local source loaded. Press Play to audition it.' : 'Original loop loaded. Press Play to audition it.');
  } catch (error) {
    if (token !== generation) return;
    message(`${describeError(error, 'This source could not be loaded. Try a short PCM WAV.')} ${loaded ? 'Your previous source is still available.' : 'Choose another source and try again.'}`, true);
  } finally {
    if (token === generation) { loading = false; renderTransport(); }
  }
}

function commit(before) {
  if (same(before, current)) return;
  history = history.slice(0, cursor + 1);
  history.push(clone(current));
  if (history.length > 51) history.shift();
  cursor = history.length - 1;
  renderControls();
}

function finishGesture() {
  if (!gesture) return;
  const before = gesture.before;
  gesture = null;
  commit(before);
}

function replaceRecipe(recipe, { announce = '', fromImport = false } = {}) {
  if (!fromImport) recipeRevision++;
  finishGesture();
  const validated = validateRecipe(recipe);
  const before = clone(current);
  const beforeCompare = comparison;
  current = validated;
  comparison = 'b';
  try { applyAudio(); }
  catch (error) { current = before; comparison = beforeCompare; renderControls(); throw error; }
  commit(before);
  renderControls();
  if (announce) message(announce);
}

for (const key of keys) {
  const { range, number } = controls[key];
  const begin = (kind = null) => {
    if (comparison === 'a') return;
    recipeRevision++;
    if (gesture?.key !== key) finishGesture();
    if (!gesture) gesture = { key, kind, before: clone(current) };
    else if (kind) gesture.kind = kind;
  };
  range.addEventListener('pointerdown', () => begin('pointer'));
  range.addEventListener('keydown', event => {
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) begin('keyboard');
  });
  range.addEventListener('input', () => {
    begin();
    const before = clone(current);
    try {
      const next = clone(current);
      next.macros[key] = Number(range.value);
      current = validateRecipe(next);
      applyAudio();
      renderControls();
    } catch (error) {
      current = before;
      renderControls();
      message(describeError(error, 'That setting could not be applied. The working patch is retained.'), true);
    }
  });
  range.addEventListener('change', () => { if (gesture?.kind !== 'keyboard') finishGesture(); });
  range.addEventListener('pointerup', finishGesture);
  range.addEventListener('pointercancel', finishGesture);
  range.addEventListener('keyup', finishGesture);
  range.addEventListener('blur', finishGesture);
  number.addEventListener('change', () => {
    recipeRevision++;
    const value = Number(number.value);
    if (!number.value.trim() || !Number.isFinite(value) || !number.validity.valid) {
      number.value = String(current.macros[key]);
      message(`Enter a numeric ${key} value between ${number.min} and ${number.max}.`, true);
      number.focus();
      return;
    }
    try {
      const next = clone(current);
      next.macros[key] = value;
      replaceRecipe(next);
    } catch (error) { renderControls(); message(describeError(error, 'This setting was rejected. Your working patch is retained.'), true); }
  });
}

document.addEventListener('pointerup', finishGesture);
window.addEventListener('blur', finishGesture);

$('preset').replaceChildren(...PRESETS.map(preset => {
  const option = document.createElement('option');
  option.value = preset.id;
  option.textContent = preset.name;
  return option;
}));
const customOption = document.createElement('option');
customOption.value = 'custom';
customOption.textContent = 'Custom patch';
customOption.disabled = true;
$('preset').append(customOption);
$('preset').addEventListener('change', () => {
  const preset = PRESETS.find(item => item.id === $('preset').value);
  if (!preset) return;
  try { replaceRecipe(preset.recipe, { announce: `${preset.name} applied. Your previous patch is available on A or Undo.` }); }
  catch (error) { message(describeError(error, 'Preset could not be applied. Your working patch is retained.'), true); }
});

function changeComparison(next) {
  recipeRevision++;
  finishGesture();
  if (next === 'a' && cursor === 0) return;
  const before = comparison;
  comparison = next;
  try { applyAudio(); }
  catch (error) { comparison = before; message(describeError(error, 'Comparison could not switch. Your patch is retained.'), true); }
  renderControls();
}
$('compare-a').addEventListener('click', () => changeComparison('a'));
$('compare-b').addEventListener('click', () => changeComparison('b'));
$('clean').addEventListener('click', () => {
  recipeRevision++;
  clean = !clean;
  try { applyAudio(); }
  catch (error) { clean = !clean; message(describeError(error, 'Clean comparison could not switch.'), true); }
  renderControls();
});

function stepHistory(delta) {
  recipeRevision++;
  finishGesture();
  const next = cursor + delta;
  if (comparison === 'a' || next < 0 || next >= history.length) return;
  const before = current;
  current = clone(history[next]);
  try { applyAudio(); cursor = next; message(delta < 0 ? 'Previous settings restored.' : 'Next settings restored.'); }
  catch (error) { current = before; message(describeError(error, 'The change could not be restored.'), true); }
  renderControls();
}
$('undo').addEventListener('click', () => stepHistory(-1));
$('redo').addEventListener('click', () => stepHistory(1));

$('play').addEventListener('click', async () => {
  if (loading || faulted) return;
  const token = generation;
  const transport = ++transportRevision;
  starting = true;
  loading = true;
  message('');
  renderTransport();
  try {
    const audio = await ensureEngine();
    if (token !== generation || transport !== transportRevision) return;
    if (!loaded) {
      const info = await audio.loadDemo(sourceId || LOOPS[0].id);
      if (token !== generation || transport !== transportRevision) return;
      updateSource(info || audio.getInfo(), true);
    }
    applyAudio();
    await audio.play();
  } catch (error) {
    if (token === generation && transport === transportRevision) message(describeError(error, 'Playback could not start. Press Play again, or try another source.'), true);
  } finally {
    if (token === generation) { starting = loading = false; renderTransport(); }
  }
});
$('stop').addEventListener('click', () => {
  transportRevision++;
  const wasStarting = starting;
  starting = false;
  engine?.stop();
  if (wasStarting) message('Playback start cancelled.');
  renderTransport();
});
document.querySelectorAll('[data-loop]').forEach(button => button.addEventListener('click', () => loadSource({ loopId: button.dataset.loop })));
$('import-audio').addEventListener('click', () => $('audio-file').click());
$('audio-file').addEventListener('change', event => {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (file) loadSource({ file });
});

function prepareDownload(blob, name) {
  // Rendering can outlast a mobile browser's user activation. Prepare first;
  // a separate real tap opens the OS save sheet or the fallback download.
  const file = new File([blob], name, {type: blob.type});
  const url = URL.createObjectURL(blob);
  for (const previous of downloadUrls) URL.revokeObjectURL(previous);
  downloadUrls.clear();
  downloadUrls.add(url);
  preparedFile = file;
  fileRevision++;
  const link = $('save-download');
  link.href = url;
  link.download = name;
  link.target = '_blank';
  link.rel = 'noopener';
  $('prepared-name').textContent = name;
  let shareable = false;
  try { shareable = typeof navigator.share === 'function' && navigator.canShare?.({files: [file]}) === true; } catch {}
  $('share-download').hidden = !shareable;
  $('share-download').disabled = false;
  $('file-ready').hidden = false;
}

$('share-download').addEventListener('click', async () => {
  if (!preparedFile) return;
  const revision = fileRevision;
  $('share-download').disabled = true;
  try {
    // Called before any await, directly from this explicit save gesture.
    await navigator.share({files: [preparedFile]});
    if (revision === fileRevision) message('File handed to your device. Your patch is still here.');
  } catch (error) {
    if (revision === fileRevision) message(error?.name === 'AbortError'
      ? 'Save cancelled. Your file and patch are still here.'
      : 'The save sheet could not open. Use Download file instead; your patch is still here.', error?.name !== 'AbortError');
  } finally {
    if (revision === fileRevision) $('share-download').disabled = false;
  }
});

function fileStamp() { return new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-'); }
$('export-recipe').addEventListener('click', () => {
  finishGesture();
  try {
    const safeRecipe = validateRecipe(current);
    prepareDownload(new Blob([`${JSON.stringify(safeRecipe, null, 2)}\n`], { type: 'application/json' }), `noise-lab-recipe-${fileStamp()}.json`);
    message('Recipe ready below. Choose Save / share file or Download file. Keep source audio separately.');
  } catch (error) { message(describeError(error, 'The recipe could not be downloaded.'), true); }
});
$('import-recipe').addEventListener('click', () => $('recipe-file').click());
$('recipe-file').addEventListener('change', async event => {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  const token = generation;
  const request = ++recipeRevision;
  try {
    if (file.size > 64 * 1024) throw new Error('Recipe files must be under 64 KB. Choose a Noise Lab recipe JSON.');
    const parsed = JSON.parse(await file.text());
    if (token !== generation || request !== recipeRevision) return;
    replaceRecipe(parsed, { fromImport: true, announce: 'Recipe imported into B. Your previous settings are available through Undo.' });
  } catch (error) {
    if (token === generation && request === recipeRevision) message(`${describeError(error, 'This is not a valid Noise Lab recipe.')} Your working patch is retained.`, true);
  }
});
$('export-audio').addEventListener('click', async () => {
  if (!engine || !loaded || exporting) return;
  finishGesture();
  const token = generation;
  exporting = true;
  renderTransport();
  message('Rendering your current B patch locally…');
  try {
    const blob = await engine.exportWav({ includeTail: $('include-tail').checked, recipe: clone(current), bypass: false });
    if (token !== generation) return;
    prepareDownload(blob, `noise-lab-${current.profile}-${fileStamp()}.wav`);
    message('WAV ready below. Choose Save / share file or Download file. Your patch stays in the lab.');
  } catch (error) {
    if (token === generation) message(`${describeError(error, 'The WAV could not be rendered. Try a shorter source.')} Your source and working patch are retained.`, true);
  } finally {
    if (token === generation) { exporting = false; renderTransport(); }
  }
});
$('cancel-export').addEventListener('click', () => { engine?.cancelExport(); });

function clearSession({ announce = true } = {}) {
  generation++;
  if (animation !== null) cancelAnimationFrame(animation);
  animation = null;
  if (engine) { engine.onstatechange = null; engine.dispose(); }
  engine = null;
  creating = null;
  starting = loading = exporting = loaded = faulted = false;
  gesture = null;
  clean = false;
  comparison = 'b';
  current = validateRecipe(DEFAULT_RECIPE);
  history = [clone(current)];
  cursor = 0;
  sourceId = LOOPS[0]?.id || 'harmonic-pluck';
  for (const url of downloadUrls) URL.revokeObjectURL(url);
  downloadUrls.clear();
  preparedFile = null;
  fileRevision++;
  $('file-ready').hidden = true;
  $('save-download').removeAttribute('href');
  $('save-download').removeAttribute('download');
  $('prepared-name').textContent = '';
  $('audio-file').value = $('recipe-file').value = '';
  $('source-name').textContent = sourceDefinition(sourceId)?.name || 'Harmonic pluck';
  $('source-description').textContent = 'An original synthesized clean loop. Press Play to load and audition it.';
  $('source-badge').textContent = 'Original synthesis';
  $('source-info').textContent = 'Audio stays on this device.';
  renderControls();
  renderTransport();
  if (announce) message('Session cleared: loaded audio, patch edits, and undo history were released. Downloaded files are unchanged.');
}
$('clear-session').addEventListener('click', () => clearSession());
window.addEventListener('pagehide', event => {
  transportRevision++;
  if (event.persisted) {
    engine?.stop();
    engine?.cancelExport();
  } else if (engine) engine.dispose();
});
window.addEventListener('pageshow', event => {
  if (event.persisted) {
    renderControls();
    renderTransport();
    message('Your session is still here. Press Play to resume.');
  }
});
document.addEventListener('visibilitychange', () => { if (!document.hidden) renderTransport(); });

const support = supportsAudio();
$('browser-support').textContent = support.supported ? 'This browser exposes the audio APIs needed to attempt local playback and WAV rendering. This does not certify glitch-free operation.' : support.reason || 'This browser is missing a required audio capability. Try another browser; recipe controls and JSON downloads remain available.';
if (!support.supported) {
  $('support-message').hidden = false;
  $('support-message').textContent = support.reason || 'Audio processing is unavailable in this browser. You can still explore controls and download recipes.';
}
const initialSource = sourceDefinition(sourceId);
if (initialSource) {
  $('source-name').textContent = initialSource.name;
  $('source-description').textContent = `${initialSource.description} Press Play to audition.`;
}
renderControls();
renderTransport();
