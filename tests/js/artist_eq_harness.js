/* Execute static/js/artist-eq.js against the config the server ships.
 *
 * Why this exists: the Python suite passes without executing a single
 * line of JavaScript. Renaming two keys in artist_eq_config.py fixed a
 * real Jinja hazard, kept 886 Python tests green, and shipped an Artist
 * EQ that threw a TypeError on every render — sliders dead, presets
 * dead — because the browser reads that same config as JSON and
 * `lane.keys` had become `undefined`.
 *
 * So this is not a unit test of a helper. It loads the real script with
 * the real config and drives the two interactions that matter: moving a
 * fader and clicking a preset. Anything the browser would throw, this
 * throws.
 *
 * Usage:  node artist_eq_harness.js <script.js> <config.json>
 * Prints one JSON object on stdout. Never throws itself — a crash in the
 * script under test is a result, not a harness failure.
 *
 * WHAT THIS IS NOT: a browser. There is no layout, no CSS, no painting,
 * no real event dispatch. It proves the script's logic runs and
 * recomputes; it says nothing about whether the result looks right.
 */
"use strict";

const fs = require("fs");

const [scriptPath, configPath] = process.argv.slice(2);
const src = fs.readFileSync(scriptPath, "utf8");
const configText = fs.readFileSync(configPath, "utf8");

/* --- a DOM, in the smallest form the script will accept ---------------- */

const handlers = new Map();          // id -> {event: fn}
const unknownIds = new Set();        // ids the script wanted that we did not plan for

function el(id, extra) {
  const node = {
    id: id,
    textContent: "",
    innerHTML: "",
    value: "5",
    hidden: false,
    dataset: (extra && extra.dataset) || {},
    style: {
      _v: {},
      setProperty(k, v) { this._v[k] = v; },
      removeProperty(k) { delete this._v[k]; },
      getPropertyValue(k) { return this._v[k] || ""; },
    },
    classList: {
      add() {}, remove() {}, toggle() {}, contains() { return false; },
    },
    setAttribute() {},
    removeAttribute() {},
    getAttribute() { return "/plan"; },
    appendChild() {},
    closest() { return null; },
    /* Return a stub rather than null: a missing stub would surface as
       "cannot set textContent of null" and read like a bug in the
       script, which is exactly the false alarm to avoid. */
    querySelector(sel) { return el("child:" + sel); },
    querySelectorAll() { return []; },
    getBoundingClientRect() {
      return { width: 800, height: 400, top: 0, left: 0, right: 800, bottom: 400 };
    },
    addEventListener(type, fn) {
      if (!handlers.has(this.id)) { handlers.set(this.id, {}); }
      handlers.get(this.id)[type] = fn;
    },
    removeEventListener() {},
  };
  if (extra) { Object.assign(node, extra); }
  return node;
}

const config = JSON.parse(configText);
const channelKeys = (config.channels || []).map(function (c) { return c.key; });

const faders = channelKeys.map(function (k) {
  return el("range:" + k, { dataset: { key: k }, value: "5" });
});
const presetButtons = (config.presets || []).map(function (p) {
  return el("preset:" + p.id, { dataset: { preset: p.id } });
});

const byId = {};
byId["sbeq-config"] = el("sbeq-config", { textContent: configText });

const root = el("artist-eq");
root.querySelectorAll = function (sel) {
  if (sel.indexOf("range") !== -1) { return faders; }
  if (sel.indexOf("preset") !== -1) { return presetButtons; }
  return [];
};
root.querySelector = function (sel) {
  const key = sel.replace(/^[#.]/, "");
  return byId[key] || el("root:" + sel);
};

global.document = {
  readyState: "complete",
  documentElement: el("html"),
  body: el("body"),
  getElementById: function (id) {
    if (id === "artist-eq") { return root; }
    if (!byId[id]) { unknownIds.add(id); byId[id] = el(id); }
    return byId[id];
  },
  querySelector: function () { return root; },
  querySelectorAll: function (sel) { return root.querySelectorAll(sel); },
  createElement: function (t) { return el("created:" + t); },
  createElementNS: function (ns, t) { return el("created:" + t); },
  addEventListener: function () {},
};

const storage = {
  _d: {},
  getItem(k) { return Object.prototype.hasOwnProperty.call(this._d, k) ? this._d[k] : null; },
  setItem(k, v) { this._d[k] = String(v); },
  removeItem(k) { delete this._d[k]; },
};

global.window = {
  localStorage: storage,
  matchMedia: function () {
    return { matches: false, addEventListener() {}, addListener() {} };
  },
  getComputedStyle: function () { return { getPropertyValue: function () { return ""; } }; },
  requestAnimationFrame: function (fn) { fn(0); return 1; },
  cancelAnimationFrame: function () {},
  IntersectionObserver: function () {
    return { observe() {}, unobserve() {}, disconnect() {} };
  },
  addEventListener: function () {},
  removeEventListener: function () {},
  location: { pathname: "/", search: "", href: "https://example.test/" },
  history: { replaceState() {}, pushState() {} },
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  fetch: function () { return Promise.resolve({ ok: true, json: () => Promise.resolve({}) }); },
  gtag: undefined,
  dataLayer: [],
};
global.localStorage = storage;
global.IntersectionObserver = global.window.IntersectionObserver;
global.requestAnimationFrame = global.window.requestAnimationFrame;
global.fetch = global.window.fetch;
/* Node 20+ defines `navigator` as a getter-only global, so assigning to it
   throws. Only fill it in when it is genuinely absent. */
if (typeof globalThis.navigator === "undefined") {
  global.navigator = { userAgent: "node", sendBeacon: function () { return true; } };
}

/* --- run it ------------------------------------------------------------ */

const result = {
  loaded: false, loadError: null,
  dragged: false, dragError: null,
  presetApplied: false, presetError: null,
  initial: null, afterDrag: null, afterPreset: null,
  unknownIds: [],
};

function snapshot() {
  const get = (id) => (byId[id] ? String(byId[id].textContent || "") : "");
  return {
    score: get("sbeq-score"),
    band: get("sbeq-band"),
    lane: get("sbeq-lane-name"),
    setup: get("sbeq-setup"),
  };
}

try {
  new Function(src)();
  result.loaded = true;
} catch (e) {
  result.loadError = e.message;
}

result.initial = snapshot();

/* Move the last fader to its maximum — the same event an <input type=range>
   fires while being dragged. */
if (result.loaded) {
  try {
    const target = faders[faders.length - 1];
    const bound = handlers.get(target.id);
    if (!bound || !bound.input) {
      result.dragError = "no input handler bound to the fader";
    } else {
      target.value = "10";
      bound.input({ target: target, currentTarget: target });
      result.dragged = true;
    }
  } catch (e) {
    result.dragError = e.message;
  }
}
result.afterDrag = snapshot();

/* Click a named preset that is not the default, so the plan must change. */
if (result.loaded) {
  try {
    const named = presetButtons.filter(function (b) {
      return b.dataset.preset !== config.default_preset && b.dataset.preset !== "custom";
    });
    const target = named[named.length - 1];
    const bound = target && handlers.get(target.id);
    if (!bound || !bound.click) {
      result.presetError = "no click handler bound to the preset";
    } else {
      bound.click({
        preventDefault() {}, target: target, currentTarget: target,
      });
      result.presetApplied = true;
      result.presetId = target.dataset.preset;
    }
  } catch (e) {
    result.presetError = e.message;
  }
}
result.afterPreset = snapshot();
result.unknownIds = Array.from(unknownIds);

process.stdout.write(JSON.stringify(result, null, 1));
