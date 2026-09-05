/** Frozen, explicitly authored settings. No generated DSP, URLs, or executable code. */
export const ENGINE_VERSION = 'noise-lab-1.0.0';
export const SCHEMA_VERSION = 1;
export const MACRO_KEYS = Object.freeze(['texture', 'motion', 'space', 'mix', 'level']);
export const PROFILES = Object.freeze({
  clean: Object.freeze({drive: 2, rate: 1.1, delay: 0.14, feedback: 0.22, tone: 6200}),
  'metal-bloom': Object.freeze({drive: 12, rate: 3.4, delay: 0.19, feedback: 0.38, tone: 3900}),
  'slow-orbit': Object.freeze({drive: 4, rate: 0.55, delay: 0.31, feedback: 0.48, tone: 5100}),
  'dark-room': Object.freeze({drive: 6, rate: 1.6, delay: 0.105, feedback: 0.42, tone: 1700}),
});

function exactKeys(value, keys, label) {
  if (value === null || typeof value !== 'object' || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new TypeError(`${label} must be a plain object.`);
  }
  const own = Reflect.ownKeys(value);
  if (own.length !== keys.length || !keys.every(key => own.includes(key))) {
    throw new TypeError(`${label} has missing or unrecognized fields.`);
  }
  for (const key of keys) {
    if (!Object.getOwnPropertyDescriptor(value, key)?.hasOwnProperty('value')) {
      throw new TypeError(`${label} must contain data fields only.`);
    }
  }
}

/** Reject rather than silently clamp. Old/unknown versions need an explicit migration. */
export function validateRecipe(value) {
  exactKeys(value, ['schemaVersion', 'engineVersion', 'profile', 'macros'], 'Recipe');
  if (value.schemaVersion !== SCHEMA_VERSION || value.engineVersion !== ENGINE_VERSION) {
    throw new RangeError('This recipe version is unsupported; the working sound has been retained.');
  }
  if (typeof value.profile !== 'string' || !Object.hasOwn(PROFILES, value.profile)) {
    throw new RangeError('Unknown effect profile.');
  }
  exactKeys(value.macros, MACRO_KEYS, 'Macros');
  const macros = {};
  for (const key of MACRO_KEYS) {
    const number = value.macros[key];
    const minimum = key === 'level' ? -60 : 0;
    const maximum = key === 'level' ? 0 : 100;
    if (typeof number !== 'number' || !Number.isFinite(number) || number < minimum || number > maximum) {
      throw new RangeError(`${key} must be a finite number between ${minimum} and ${maximum}.`);
    }
    macros[key] = number;
  }
  return {schemaVersion: SCHEMA_VERSION, engineVersion: ENGINE_VERSION, profile: value.profile, macros};
}

function preset(id, name, description, values) {
  return Object.freeze({id, name, description, recipe: Object.freeze({
    schemaVersion: SCHEMA_VERSION, engineVersion: ENGINE_VERSION, profile: id,
    macros: Object.freeze(Object.fromEntries(MACRO_KEYS.map((key, i) => [key, values[i]]))),
  })});
}

export const PRESETS = Object.freeze([
  preset('clean', 'Clean start', 'Gentle saturation; the starting point for comparison.', [10, 0, 0, 25, -12]),
  preset('metal-bloom', 'Metal Bloom', 'Dense saturation, controlled tremolo, and a short dark echo.', [76, 22, 30, 68, -12]),
  preset('slow-orbit', 'Slow Orbit', 'Slow amplitude movement with a longer repeating echo.', [26, 80, 70, 70, -12]),
  preset('dark-room', 'Dark Room', 'Warm saturation and filtered, close reflections.', [46, 18, 64, 62, -12]),
]);
export const DEFAULT_RECIPE = PRESETS[0].recipe;
