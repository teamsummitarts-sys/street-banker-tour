import {validateRecipe} from '../engine/index.mjs';

// Account data is transient in this page. Audio and prompts never enter this API.
export function createPatchLibrary({getRecipe, getRevision, applyRecipe, prepareDownload}) {
  const $ = id => document.getElementById(id);
  const copy = value => JSON.parse(JSON.stringify(value));
  const uuid = value => typeof value === 'string' && /^[0-9a-f-]{36}$/i.test(value);
  let available = false, busy = false, sequence = 0, edit = 0, controller = null;
  let selected = null, entries = [], saved = null;
  const pending = new Map();
  const reasons = {
    version_conflict: 'Another save changed this patch. Refresh the library before saving a new version. Your working settings are retained.',
    request_conflict: 'This save conflicts with an earlier request. Refresh the library and check its versions.',
    request_retired: 'This earlier save belongs to a deleted patch and cannot be repeated. Save as a new patch if needed.',
    patch_limit: 'The limit of 50 patches is reached. Export and delete a patch before creating another.',
    version_limit: 'This patch has 100 versions. Save your settings as a new patch.',
    request_limit: 'The account save-request limit is reached. Export your settings and contact the V2 owner.',
    invalid_patch: 'The name or settings were rejected. Use a name up to 80 characters and a supported recipe.',
    incompatible_recipe: 'This recipe version is unsupported. Your working settings are retained.',
    storage_unavailable: 'Private saving is unavailable. Export your working recipe to keep it.',
    not_found: 'This patch is unavailable to your account. Your working settings are retained.',
  };
  function status(text, error = false) {
    $('patch-status').textContent = text;
    $('patch-status').setAttribute('role', error ? 'alert' : 'status');
  }
  function changed() {
    const dirty = !saved || saved.name !== $('patch-name').value.trim()
      || JSON.stringify(saved.recipe) !== JSON.stringify(getRecipe());
    $('patch-save-state').textContent = saved && !dirty ? `Saved snapshot · version ${saved.version}`
      : saved ? 'New edits are not saved' : 'Working settings are not linked to a saved version';
    const saveState = busy ? 'B settings · Saving or loading…' : saved && !dirty ? `B settings · Saved v${saved.version}` : saved ? 'B settings · Changes not saved' : 'B settings · Not saved';
    if ($('working-save-state').textContent !== saveState) $('working-save-state').textContent = saveState;
    const alreadySaved = !dirty && saved?.version === selected?.headVersion;
    $('save-patch').disabled = !available || busy || alreadySaved;
    $('save-version').disabled = !available || busy || !selected || alreadySaved;
    $('save-version').hidden = !selected;
  }
  function controls() {
    for (const id of ['save-patch', 'refresh-patches', 'patch-list']) $(id).disabled = !available || busy;
    for (const id of ['save-version', 'load-patch-version', 'patch-version', 'export-patch-history', 'delete-patch']) $(id).disabled = !available || busy || !selected;
    $('confirm-delete-patch').disabled = !available || busy || !selected;
    $('patch-library').setAttribute('aria-busy', String(busy));
    $('save-patch').textContent = busy ? 'Working…' : 'Save new patch';
    changed();
  }
  function options(target, values, blank) {
    const nodes = [];
    if (blank) { const o = document.createElement('option'); o.value = ''; o.textContent = blank; nodes.push(o); }
    for (const [value, label] of values) {
      const o = document.createElement('option'); o.value = String(value); o.textContent = label; nodes.push(o);
    }
    target.replaceChildren(...nodes);
  }
  function renderList() {
    options($('patch-list'), entries.map(p => [p.id, `${p.name} · v${p.headVersion}`]), entries.length ? 'Choose a saved patch' : 'No saved patches yet');
    $('patch-list').value = selected?.id || '';
  }
  function clearSelection() {
    selected = null; saved = null;
    $('delete-patch-confirmation').hidden = true;
    options($('patch-version'), [], 'Choose a patch first');
    $('patch-version').value = '';
    $('patch-selected').textContent = 'Choose a saved patch to browse its versions.';
  }
  function checkedPatch(patch) {
    if (!patch || !uuid(patch.id) || typeof patch.name !== 'string' || patch.name.length > 80
      || !Number.isInteger(patch.headVersion) || patch.headVersion < 1 || !Array.isArray(patch.versions)
      || !patch.versions.length || patch.versions.length > 100
      || patch.versions.some(v => !Number.isInteger(v.version) || v.version < 1 || typeof v.name !== 'string')) {
      throw Error('The saved patch response was invalid. Your working settings are retained.');
    }
    return patch;
  }
  function select(patch, version = patch.headVersion) {
    selected = checkedPatch(patch);
    options($('patch-version'), [...patch.versions].sort((a,b) => b.version-a.version)
      .map(v => [v.version, `Version ${v.version} · ${v.name}`]));
    $('patch-version').value = String(version);
    $('patch-selected').textContent = `${patch.name} · latest version ${patch.headVersion}. Loading changes B and supports Undo.`;
    const row = {id: patch.id, name: patch.name, headVersion: patch.headVersion, updated: patch.updated};
    entries = [row, ...entries.filter(p => p.id !== patch.id)];
    renderList();
    $('delete-patch-confirmation').hidden = true;
  }
  async function request(path, method, body, signal) {
    let response;
    try { response = await fetch(`/noise-lab/api/patches${path}`, {
      method, credentials: 'same-origin', cache: 'no-store', signal,
      headers: {'Content-Type': 'application/json', 'X-Noise-Lab-CSRF': document.body.dataset.csrf},
      ...(body ? {body: JSON.stringify(body)} : {}),
    }); } catch (error) {
      if (error?.name === 'AbortError') throw error;
      throw Error('Connection lost. A save may have completed. Refresh the library or retry the same save; your working settings are retained.');
    }
    if (response.redirected || response.status === 401 || response.status === 403) {
      available = false; entries = []; clearSelection(); renderList();
      throw Error('Your sign-in needs refreshing. Export your working recipe, then sign in and reload Noise Lab.');
    }
    let data;
    try { data = await response.json(); }
    catch { throw Error('The server response could not be read. Check the library before retrying; your working settings are retained.'); }
    if (!response.ok) throw Error(Object.hasOwn(reasons, data?.error) ? reasons[data.error] : 'The request could not finish. Check the library before retrying; your working settings are retained.');
    return data;
  }
  async function run(action) {
    if (!available || busy) return;
    const token = ++sequence;
    controller = new AbortController();
    const activeController = controller, signal = activeController.signal;
    const timer = setTimeout(() => activeController.abort(), 15000);
    busy = true; controls();
    try { await action(signal, () => token === sequence); }
    catch (error) {
      if (token === sequence) status(error?.name === 'AbortError'
        ? 'The request timed out. It may have saved. Check the library or retry the same save; your working settings are retained.'
        : error.message || 'Private saving failed. Your working settings are retained.', true);
    } finally {
      clearTimeout(timer);
      if (token === sequence) { busy = false; controller = null; controls(); }
    }
  }
  async function refresh() {
    return run(async (signal, active) => {
      status('Loading your private patches…');
      const data = await request('', 'GET', null, signal);
      if (!active()) return;
      if (!Array.isArray(data.patches) || data.patches.length > 50 || data.patches.some(p => !uuid(p.id) || typeof p.name !== 'string')) throw Error('The patch list was invalid. Try refreshing it.');
      entries = data.patches;
      // Refresh releases stale head versions; explicit selection fetches current data.
      clearSelection(); renderList();
      status(entries.length ? 'Choose a patch and version to load. Your working settings are unchanged.' : 'No saved patches yet. Name your sound and save your first patch.');
    });
  }
  async function save(asVersion) {
    if (asVersion && !selected) return;
    const name = $('patch-name').value.trim();
    if (!name || name.length > 80) { status('Enter a patch name from 1 to 80 characters.', true); $('patch-name').focus(); return; }
    let recipe;
    try { recipe = validateRecipe(getRecipe()); } catch { status('These settings cannot be saved. Your working patch is retained.', true); return; }
    const revision = getRevision(), nameRevision = edit;
    const path = asVersion ? `/${selected.id}/versions` : '';
    const value = {name, recipe, ...(asVersion ? {baseVersion: selected.headVersion} : {})};
    const key = path + JSON.stringify(value);
    if (!pending.has(key)) {
      // Bound retry bookkeeping to the current page, without persisting content.
      if (pending.size >= 100) pending.delete(pending.keys().next().value);
      pending.set(key, crypto.randomUUID());
    }
    const body = {...value, requestId: pending.get(key)};
    return run(async (signal, active) => {
      status('Saving a private settings snapshot…');
      const data = await request(path, 'POST', body, signal);
      if (!active()) return;
      const patch = checkedPatch(data.patch);
      const accepted = patch.versions.find(v => v.version === patch.headVersion);
      if (!accepted || accepted.name !== name || JSON.stringify(validateRecipe(accepted.recipe)) !== JSON.stringify(recipe)) {
        throw Error('The save acknowledgment did not match your settings. Refresh the library to check it; your working settings are retained.');
      }
      // Mark the submitted snapshot, never newer edits made during the request.
      select(patch);
      saved = {name, recipe: copy(recipe), version: patch.headVersion};
      status(`Saved “${name}” as version ${patch.headVersion}. ${revision !== getRevision() || nameRevision !== edit ? 'Your newer edits are not saved yet.' : 'Audio stays on this device; keep your source separately.'}`);
    });
  }
  $('save-patch').addEventListener('click', () => save(false));
  $('save-version').addEventListener('click', () => save(true));
  $('patch-name').addEventListener('input', () => { edit++; changed(); });
  $('refresh-patches').addEventListener('click', refresh);
  $('patch-list').addEventListener('change', () => {
    const id = $('patch-list').value;
    clearSelection(); controls();
    if (!uuid(id)) return;
    return run(async (signal, active) => {
      status('Loading version history…');
      const data = await request(`/${id}`, 'GET', null, signal);
      if (!active()) return;
      select(checkedPatch(data.patch));
      status('Choose a version, then Load version. Your current sound has not changed.');
    });
  });
  $('load-patch-version').addEventListener('click', () => {
    const version = selected?.versions.find(v => v.version === Number($('patch-version').value));
    if (!version) return;
    try {
      const recipe = validateRecipe(version.recipe);
      applyRecipe(recipe);
      $('patch-name').value = version.name;
      edit++; saved = {name: version.name, recipe: copy(recipe), version: version.version};
      status(`Loaded version ${version.version} into B. Undo keeps your previous settings. Load the matching source audio separately. Saving a version will append to the latest history.`);
      controls();
    } catch { status('This saved recipe is unsupported or invalid. Export its history to preserve it. Your working settings are retained.', true); }
  });
  $('export-patch-history').addEventListener('click', () => {
    if (!selected) return;
    const id = selected.id;
    return run(async (signal, active) => {
      const data = await request(`/${id}/export`, 'GET', null, signal);
      if (!active()) return;
      if (data.archiveVersion !== 1) throw Error('Unsupported archive response. No file was prepared.');
      checkedPatch(data.patch);
      prepareDownload(new Blob([JSON.stringify(data, null, 2) + '\n'], {type: 'application/json'}), `noise-lab-patch-${id}.json`);
      status('All saved versions are ready in the file panel below. Choose Save / share file or Download file. No audio is included.');
    });
  });
  $('delete-patch').addEventListener('click', () => {
    if (!selected) return;
    $('delete-patch-description').textContent = `Delete “${selected.name}” and all ${selected.versions.length} saved versions? Your working sound and downloaded files remain. Backups may retain earlier copies.`;
    $('delete-patch-confirmation').hidden = false;
    $('cancel-delete-patch').focus();
  });
  $('cancel-delete-patch').addEventListener('click', () => { $('delete-patch-confirmation').hidden = true; $('delete-patch').focus(); });
  $('confirm-delete-patch').addEventListener('click', () => {
    if (!selected || $('delete-patch-confirmation').hidden) return;
    const {id, headVersion} = selected;
    return run(async (signal, active) => {
      await request(`/${id}`, 'DELETE', {baseVersion: headVersion}, signal);
      if (!active()) return;
      entries = entries.filter(p => p.id !== id); clearSelection(); renderList();
      status('Patch and all its versions deleted from the active library. Your working settings remain. Downloaded files and backups are separate.');
      $('patch-list').focus();
    });
  });
  function suspend() {
    sequence++; controller?.abort(); controller = null; busy = false;
    entries = []; clearSelection(); renderList(); controls();
  }
  function reset() { suspend(); pending.clear(); edit++; $('patch-name').value = ''; status('Local session cleared. Saved account patches remain; use Refresh library to reopen them.'); }
  options($('patch-list'), [], 'Checking private storage…');
  clearSelection(); controls();
  return {
    changed, refresh, reset, suspend,
    async setAvailability(enabled) {
      const first = !available;
      available = enabled === true;
      if (!available) { suspend(); pending.clear(); status('Private saving is not enabled. Prepare a recipe download to keep your settings.'); }
      else if (first || !entries.length) await refresh();
      controls();
    },
  };
}
