// Same-origin, account-scoped temporary audio copies. No network requests here.
export const HANDOFF_TTL_MS = 30 * 60 * 1000;
const MAX_BYTES = 64 * 1024 * 1024;
const TOKEN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
function key(scope, token) {
  if (typeof scope !== 'string' || !scope || scope.length > 256 || !TOKEN.test(token)) throw Error('This editor handoff is unavailable. Return to your song and create a fresh copy.');
  return scope + ':' + token;
}
export function validateHandoffMetadata(value) {
  if (!value || !['section', 'mix'].includes(value.kind) || !Number.isFinite(value.sourceStart) || !Number.isFinite(value.sourceEnd) || value.sourceStart < 0 || value.sourceEnd <= value.sourceStart || !Array.isArray(value.sections) || value.sections.length > 80) throw Error('The editor copy has invalid source information. Render a fresh copy.');
  const result = {kind:value.kind, sourceStart:value.sourceStart, sourceEnd:value.sourceEnd, revision:String(value.revision ?? '').slice(0, 80)};
  for (const field of ['projectId','projectName','sectionId','sectionName']) result[field] = String(value[field] ?? '').slice(0, 200);
  result.sections = value.sections.map(section => {
    if (!section || typeof section.name !== 'string' || !section.name.trim() || !Number.isFinite(section.start) || !Number.isFinite(section.end) || section.start < 0 || section.end <= section.start || section.end > value.sourceEnd - value.sourceStart + .01) throw Error('The editor section map does not match this audio copy.');
    return {name:section.name.replace(/[|\r\n]/g, ' ').slice(0, 100), start:section.start, end:section.end};
  });
  return result;
}
function database(indexedDB = globalThis.indexedDB) {
  if (!indexedDB) return Promise.reject(Error('Temporary editor copies are unavailable in this browser. Export a WAV and choose it in the audio desk.'));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('room-analysis-handoffs', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('copies', {keyPath:'key'});
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(Error('The browser could not open temporary editor copies. Export a WAV and choose it in the audio desk.'));
    request.onblocked = () => reject(Error('Close other Room tabs and try the editor handoff again.'));
  });
}
async function transact(mode, run, indexedDB) {
  const db = await database(indexedDB);
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction('copies', mode), store = tx.objectStore('copies'); let result, failure;
      tx.oncomplete = () => resolve(result);
      tx.onerror = tx.onabort = () => reject(failure || Error('The browser could not save this temporary copy. Free browser storage or export a WAV.'));
      try {run(store, value => {result = value;}, error => {failure = error; tx.abort();});} catch(error) {failure = error; tx.abort();}
    });
  } finally {db.close();}
}
export async function storeAnalysisHandoff({scope, file, metadata, indexedDB, now = Date.now()}) {
  const token = crypto.randomUUID(), id = key(scope, token), clean = validateHandoffMetadata(metadata);
  if (!file || typeof file.arrayBuffer !== 'function' || !file.size || file.size > MAX_BYTES) throw Error('The editor copy must be 64 MiB or smaller. Analyze a shorter section.');
  await transact('readwrite', (store, done, fail) => {
    const request = store.getAll();
    request.onsuccess = () => {
      const own = request.result.filter(row => row.scope === scope);
      for (const row of own.filter(row => row.expires <= now)) store.delete(row.key);
      if (own.filter(row => row.expires > now).length >= 3) {fail(Error('Three editor copies are waiting. Import or discard one in Analyze & Improve, or wait 30 minutes.')); return;}
      store.put({key:id, scope, token, file, name:String(file.name || 'Editor analysis copy.wav').slice(0, 220), metadata:clean, expires:now + HANDOFF_TTL_MS});
      done(token);
    };
  }, indexedDB);
  return token;
}
export async function loadAnalysisHandoff({scope, token, indexedDB, now = Date.now()}) {
  const id = key(scope, token);
  return transact('readwrite', (store, done) => {
    const request = store.get(id);
    request.onsuccess = () => {
      const row = request.result;
      if (!row || row.scope !== scope || row.expires <= now) {if (row) store.delete(id); done(null); return;}
      done({...row, metadata:validateHandoffMetadata(row.metadata)});
    };
  }, indexedDB);
}
export async function removeAnalysisHandoff({scope, token, indexedDB}) {
  const id = key(scope, token);
  return transact('readwrite', (store, done) => {store.delete(id); done();}, indexedDB);
}
