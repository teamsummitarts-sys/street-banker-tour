/** Content sources and theme for the Street Banker stylesheet.
 *
 *  Templates alone are not enough. rackdsp.js and the other browser
 *  modules assemble class strings at runtime - "sw h-7 w-7 text-[11px]",
 *  "fader w-28", the lane and knob classes - so scanning only .html would
 *  drop every class the Rack generates and produce a stylesheet that looks
 *  correct right up until somebody opens the Rack.
 *
 *  The .py files are here because a few routes and config modules carry
 *  class strings for badges and status chips.
 *
 *  Paths are relative to the repo root, so this rebuilds anywhere:
 *
 *      npm install tailwindcss@3
 *      npx tailwindcss -c tools/tailwind.config.js -i tools/tailwind-input.css \
 *          -o static/css/tailwind.css --minify
 *
 *  Then bump the ?v= on the <link> in the templates and VERSION in
 *  static/js/sw.js, or browsers keep serving the old sheet.
 *
 *  ---------------------------------------------------------------------
 *  DESIGN SYSTEM v1 (22 Aug 2026)
 *
 *  The theme below is the Tailwind mirror of the tokens defined as CSS
 *  custom properties in tools/tailwind-input.css. Both exist because the
 *  platform styles itself two ways: utility classes in the templates, and
 *  hand-written CSS in static/css/*.css. One source of truth, two
 *  spellings.
 *
 *  The stock palette families are deliberately REDEFINED rather than
 *  extended. 396 templates say `text-amber-500` and 257 say `text-green-400`;
 *  pointing those names at the brand ramp converts every one of them in a
 *  single build instead of 650 hand edits, and it makes the wrong colour
 *  unreachable - there is no `amber-500` that is Tailwind's #F59E0B any
 *  more. Same reasoning for gray -> the warm ink ramp, and for the radius
 *  and font-size scales below.
 */

/* --- brand gold: one ramp. 400 is hover, 500 is brand, 700 is lines. --- */
const GOLD = {
  50: "#FBF3DF",
  100: "#F6E7BE",
  200: "#EFD696",
  300: "#E8C667",
  400: "#E8B950", // gold-bright  · hover
  500: "#C9A24A", // gold         · brand
  600: "#B08B3C",
  700: "#8A6E30", // gold-deep    · lines
  800: "#6B5526",
  900: "#4A3A1A",
  950: "#2A2110",
};

/* --- state: never decorative, never the accent --- */
const GOOD = {
  50: "#EEF6ED", 100: "#D8EAD6", 200: "#B7DAB3", 300: "#98C793",
  400: "#79B473", 500: "#79B473", 600: "#5F9A5A", 700: "#497845",
  800: "#365732", 900: "#253C23", 950: "#142213",
};
const WARN = {
  50: "#FDF1E8", 100: "#F9DDC7", 200: "#F4BE96", 300: "#EE9F65",
  400: "#E8843F", 500: "#E8843F", 600: "#C86A2C", 700: "#A15321",
  800: "#783E19", 900: "#4F2911", 950: "#2C1709",
};
const CRIT = {
  50: "#FCEEEC", 100: "#F8D6D1", 200: "#F1B0A7", 300: "#E8867A",
  400: "#E8776A", 500: "#E05C4A", 600: "#C44A3A", 700: "#9E3A2D",
  800: "#752B21", 900: "#4D1D16", 950: "#2A100C",
};
const INFO = {
  50: "#EFF4FD", 100: "#DAE6FA", 200: "#BACFF4", 300: "#9BBAEE",
  400: "#7FA8E8", 500: "#7FA8E8", 600: "#5A87CC", 700: "#446AA3",
  800: "#314D77", 900: "#20334E", 950: "#111B2B",
};

/* --- ink at the light end, surfaces at the dark end. One ramp, because
       on a dark UI "grey" is either type or ground and nothing between. --- */
const INK = {
  50: "#FAF7F0",
  100: "#F2ECE0", // ink
  200: "#DCD3C2",
  300: "#C4B8A2",
  400: "#A99B84", // ink-2
  500: "#8A7D68",
  600: "#91836A", // ink-3 - lifted from the spec's #6E6350 to clear AA
  700: "#3A3226", // line-strong
  800: "#2A241C", // line
  900: "#1A1714", // surface-2
  950: "#131110", // surface-1
};

module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/js/**/*.js",
    "./*.py",
  ],
  darkMode: "class",
  /* The component classes below are assembled from Jinja variables in
     places ("sb-badge-" ~ tone), so the content scanner cannot see every
     one of them. Keep the whole sb- namespace. */
  safelist: [{ pattern: /^sb-/ }],
  theme: {
    extend: {
      colors: {
        /* The named token set - what new work should reach for. */
        sb: {
          ground: "#0B0A08",
          "surface-1": "#131110",
          "surface-2": "#1A1714",
          "surface-3": "#221D18",
          line: "#2A241C",
          "line-strong": "#3A3226",
          ink: "#F2ECE0",
          "ink-2": "#A99B84",
          "ink-3": "#91836A",
          gold: "#C9A24A",
          "gold-bright": "#E8B950",
          "gold-deep": "#8A6E30",
          "gold-wash": "rgba(201,162,74,.12)",
          "gold-line": "rgba(201,162,74,.34)",
          good: "#79B473",
          "good-wash": "rgba(121,180,115,.13)",
          warn: "#E8843F",
          "warn-wash": "rgba(232,132,63,.13)",
          crit: "#E05C4A",
          "crit-wash": "rgba(224,92,74,.13)",
          info: "#7FA8E8",
          "info-wash": "rgba(127,168,232,.13)",
          "on-gold": "#14100A",
        },

        /* Stock families, repointed. Everything already written keeps
           working and lands on the ramp. */
        black: "#0B0A08",
        amber: GOLD,
        yellow: GOLD,
        gold: GOLD,
        green: GOOD,
        emerald: GOOD,
        lime: GOOD,
        teal: GOOD,
        orange: WARN,
        red: CRIT,
        rose: CRIT,
        pink: CRIT,
        blue: INFO,
        sky: INFO,
        indigo: INFO,
        cyan: INFO,
        violet: INFO,
        purple: INFO,
        gray: INK,
        slate: INK,
        zinc: INK,
        neutral: INK,
        stone: INK,
      },

      fontFamily: {
        /* Archivo carries display and text from one variable file; its
           width axis gives headings an expanded, institutional stance. */
        sans: ["Archivo", "Helvetica Neue", "Arial", "system-ui", "sans-serif"],
        display: ["Archivo", "Helvetica Neue", "Arial", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "SFMono-Regular", "Consolas", "Liberation Mono", "monospace"],
      },

      /* Eight steps, 12px floor. The old scale ran 9px to 24px; this one
         starts where that one ended. Stock names are remapped onto the
         steps so existing markup lands on the scale automatically. */
      fontSize: {
        xs: ["12px", { lineHeight: "1.4" }],       // label   (mono, .13em, caps)
        sm: ["13.5px", { lineHeight: "1.5" }],     // small
        base: ["15px", { lineHeight: "1.6" }],     // body
        lg: ["17px", { lineHeight: "1.45" }],      // h3
        xl: ["19px", { lineHeight: "1.35" }],      // card title
        "2xl": ["22px", { lineHeight: "1.15" }],   // h2
        "3xl": ["28px", { lineHeight: "1.1" }],    // h1
        "4xl": ["32px", { lineHeight: "1" }],      // numeric
        "5xl": ["40px", { lineHeight: "1" }],      // display
        "6xl": ["52px", { lineHeight: ".98" }],
        "7xl": ["64px", { lineHeight: ".95" }],
        "8xl": ["74px", { lineHeight: ".94" }],
        "9xl": ["88px", { lineHeight: ".92" }],
        /* Named steps, for markup that would rather say what it means. */
        label: ["12px", { lineHeight: "1.4", letterSpacing: ".13em" }],
        small: ["13.5px", { lineHeight: "1.5" }],
        body: ["15px", { lineHeight: "1.6" }],
        h3: ["17px", { lineHeight: "1.45" }],
        h2: ["22px", { lineHeight: "1.15" }],
        h1: ["28px", { lineHeight: "1.1" }],
        numeric: ["32px", { lineHeight: "1" }],
        display: ["40px", { lineHeight: "1" }],
      },

      /* Two values plus a pill. The 4/8/12/16/24 mixture goes away. */
      borderRadius: {
        none: "0px",
        sm: "6px",
        DEFAULT: "6px",
        md: "6px",
        control: "6px",
        lg: "10px",
        xl: "10px",
        "2xl": "10px",
        "3xl": "10px",
        panel: "10px",
        full: "999px",
        pill: "999px",
      },

      /* Tailwind's 4px base already matches the scale; these are the
         named aliases so CSS and utilities can say the same thing. */
      spacing: {
        s1: "4px", s2: "8px", s3: "12px", s4: "16px",
        s5: "24px", s6: "32px", s7: "48px", s8: "64px",
      },

      /* Dark UIs elevate with a lighter surface and a 1px top highlight,
         not drop shadows. */
      boxShadow: {
        "sb-1": "inset 0 1px 0 rgba(255,255,255,.03)",
        "sb-2": "inset 0 1px 0 rgba(255,255,255,.045), 0 1px 2px rgba(0,0,0,.4)",
        "sb-3": "inset 0 1px 0 rgba(255,255,255,.06), 0 8px 24px -8px rgba(0,0,0,.65)",
        "sb-focus": "0 0 0 2px #0B0A08, 0 0 0 4px #C9A24A",
      },

      transitionTimingFunction: {
        sb: "cubic-bezier(.2,.6,.35,1)",
      },
      transitionDuration: {
        fast: "120ms",
        slow: "220ms",
      },
    },
  },
  plugins: [],
};
