import test from 'node:test';
import assert from 'node:assert/strict';
import {createConsoleUI} from '../../noise_lab/static/ui/console.mjs';

test('mobile library opens modally, closes with focus return, and survives desktop resize', () => {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, {
      open: ['library-drawer', 'prompt-details'].includes(id), listeners: {},
      addEventListener(name, fn) { this.listeners[name] = fn; },
      setAttribute() {}, focus() { this.focused = true; },
      scrollIntoView() { this.scrolled = true; },
      show() { this.open = true; this.modal = false; },
      showModal() { assert.equal(this.open, false); this.open = true; this.modal = true; },
      close() { this.open = false; this.modal = false; this.listeners.close?.(); },
    });
    return elements.get(id);
  };
  const phone = {matches: true, addEventListener(name, fn) { this.changed = fn; }};
  globalThis.window = {matchMedia: () => phone};
  globalThis.document = {getElementById: get, body: {dataset: {}}};
  const ui = createConsoleUI();
  const drawer = get('library-drawer');
  assert.equal(drawer.open, false);
  assert.equal(get('prompt-details').open, true, 'The effect prompt remains discoverable on mobile');
  get('open-library').listeners.click();
  assert.equal(drawer.modal, true);
  assert.equal(get('patch-library').focused, true);
  get('close-library').listeners.click();
  assert.equal(drawer.open, false);
  assert.equal(get('open-library').focused, true);
  get('open-export').listeners.click();
  assert.equal(drawer.open, true);
  assert.equal(get('output').focused, true);
  get('close-library').listeners.click();
  assert.equal(get('open-export').focused, true, 'Closing export returns to the export action');
  ui.revealFile();
  assert.equal(drawer.modal, true, 'Prepared files are shown even if the drawer was closed');
  assert.equal(get('file-ready').focused, true);
  phone.matches = false;
  phone.changed();
  assert.equal(drawer.open, true);
  assert.equal(drawer.modal, false);
  phone.matches = true;
  phone.changed();
  assert.equal(drawer.open, false);
});
