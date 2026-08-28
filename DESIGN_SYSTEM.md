# Design System

**v1 — 22 Aug 2026.** A fixed set of values, small enough to hold in your
head and enforce in review. Defined once, in two spellings:

- `tools/tailwind-input.css` — CSS custom properties (`--sb-*`). This is
  what the hand-written stylesheets in `static/css/*.css` read.
- `tools/tailwind.config.js` — the same values as Tailwind theme keys.

Rebuild after touching either:

```
npx tailwindcss -c tools/tailwind.config.js -i tools/tailwind-input.css \
    -o static/css/tailwind.css --minify
```

**No network needed** — tailwindcss 3.4.19 already sits two levels up, so
this runs offline and skips `npx`'s install prompt entirely:

```
node ../../node_modules/tailwindcss/lib/cli.js \
    -c tools/tailwind.config.js -i tools/tailwind-input.css \
    -o static/css/tailwind.css --minify
```

Then bump the `?v=` on the stylesheet link and `VERSION` in
`static/js/sw.js`, or browsers keep serving the old sheet.

**A rebuild is not expected to be byte-identical to the committed sheet.**
The committed one can lag the templates, so a diff is not automatically a
regression — compare the *class sets*, not the file sizes, and confirm
that anything the rebuild drops is genuinely unused. The last rebuild
dropped eleven classes (all dead) and added three that templates were
already using and the stale sheet did not carry, including the
`border-sb-line` that Partner OS phase 1 shipped its panels with.

`tests/test_design_system.py` fails the build on raw hex outside the
token set, type below 12px, a radius that is not one of the three, an ink
that misses WCAG AA, or a page that reads a token without loading the file
that defines it.

Five re-runnable scripts do the mechanical work. All take `--dry-run`:

| Script | What it moves |
|---|---|
| `tools/sweep_colours.py` | colour literals → tokens |
| `tools/normalise_type.py` | font sizes → the 8-step scale; radii → the three |
| `tools/adopt_components.py` | page titles → `sb-h1`, labels → `sb-label`, machine values → `sb-num` |
| `tools/adopt_controls.py` | buttons → `sb-btn` variants |
| `tools/gold_discipline.py` | gold off metrics and status, onto ink and the state palette |
| `tools/adopt_module_headings.py` | the module CSS systems' h1/h2 → the display and label steps |

## What v1 replaced

Measured from the live pages, not eyeballed:

| Before | After |
|---|---|
| `ui-sans-serif` — the browser default | Archivo variable + IBM Plex Mono |
| 8 sizes between 8px and 24px | 8 steps, 12px floor, 40px display |
| two golds (`#C9A24A` and Tailwind's `#F59E0B`) | one gold ramp |
| stock `#22C55E` green, stock `#EF4444` red | one state family |
| four blacks, some cool, some warm | one warm elevation ladder |
| six corner radii | 6px control · 10px panel · 999px pill |
| no focus ring anywhere | a gold ring on every focusable element |

## Colour

Warm-biased neutrals, so the ground and the gold belong to the same
world.

### Ground and surfaces — the elevation ladder
| Token | Value | Use |
|---|---|---|
| `--sb-ground` | `#0B0A08` | the page |
| `--sb-surface-1` | `#131110` | cards, the sidebar |
| `--sb-surface-2` | `#1A1714` | raised panels, the warm money surface |
| `--sb-surface-3` | `#221D18` | hover ground, chips, wells |
| `--sb-line` | `#2A241C` | hairlines |
| `--sb-line-strong` | `#3A3226` | control borders |

### Ink
| Token | Value | Use |
|---|---|---|
| `--sb-ink` | `#F2ECE0` | body copy, values |
| `--sb-ink-2` | `#A99B84` | secondary copy |
| `--sb-ink-3` | `#91836A` | labels, hints |

`--sb-ink-3` is `#91836A`, not the `#6E6350` the spec drew. Measured,
`#6E6350` is 2.84:1 on surface-3 — it fails AA at the 12px label size it
is actually used for. `#91836A` is the smallest hue-preserving lift that
clears 4.5:1 on all four surfaces. The test measures this rather than
trusting it.

### Brand gold — one ramp, three roles
| Token | Value | Role |
|---|---|---|
| `--sb-gold-bright` | `#E8B950` | hover, lit values |
| `--sb-gold` | `#C9A24A` | brand, primary action |
| `--sb-gold-deep` | `#8A6E30` | lines |
| `--sb-gold-wash` | 12% | fills |
| `--sb-on-gold` | `#14100A` | text on brass |

### Paper — the platform's one light surface
Signal and the Operator Desk are internal desks meant to read as paper,
not as console. That is a real surface, so it has real tokens rather than
borrowing `--sb-ink` for a background:

| Token | Value | Use |
|---|---|---|
| `--sb-paper` | `#F4F1EA` | the sheet |
| `--sb-paper-panel` | `#FBF9F4` | a card on the sheet |
| `--sb-paper-ink` | `#141210` | body copy |
| `--sb-paper-ink-2` | `#5A544A` | secondary |
| `--sb-paper-ink-3` | `#6E6656` | labels |
| `--sb-paper-gold` | `#856A2E` | brand on paper |

`--sb-paper-gold` is darker than the brand gold because gold on paper is
the one place the accent has to be adjusted to stay readable. The desks
shipped `#8A6D1F`, which measures 4.34:1 — under AA, and under AA before
this migration too.

### State — never decorative, never the accent
`--sb-good` `#79B473` · `--sb-warn` `#E8843F` · `--sb-crit` `#E05C4A` ·
`--sb-info` `#7FA8E8`, each with a 13% wash and a 40% line.

### Two rules that do most of the work

**1. Gold is never a status.** A gold pill cannot mean "warning" if gold
is also the Save button. Warnings are orange, failures red, healthy
green.

**2. One gold-filled element per view.** If two things are gold, neither
is primary — demote one to outlined or ghost.

### The stock Tailwind families are repointed

The templates say `text-amber-500` in hundreds of places. Rather than
edit 650 of them, `tailwind.config.js` redefines the families —
`amber`/`yellow` → the gold ramp, `green`/`emerald` → good, `red`/`rose`
→ crit, `blue`/`sky` → info, `gray`/`slate`/`zinc`/`neutral`/`stone` →
the ink ramp. There is no `amber-500` that is Tailwind's `#F59E0B` any
more, so the wrong colour is unreachable rather than merely discouraged.

### What the sweep broke, and the two tests that now stand where it broke

The sweep that removed raw hex from the markup (`90754c4`) did its stated
job — no hex survived — and quietly destroyed 29 elements on the way.
Where it could not map a hex to a token it wrote a class that does not
exist (`bg-transparent-bright`, `border-sb-line-strong-bright`,
`text-sb-ink-deep`), appended a stray `border`, and in nineteen places ate
the `>` off the opening tag: `<div class="…" style="width: 40%;"</div>`.

Every proportion bar in the royalty, capital, tax, territory and analytics
pages rendered as an empty outline, and because an unclosed element
swallows its following siblings, whole stacks of rows collapsed onto one
line. It shipped and sat there, because each lock covered its own concern
and nothing covered the gap between them: the raw-hex lock passed (the hex
really was gone), the staleness check passed (it only reads
arbitrary-value classes, and none of the broken names had brackets), and
HTML has no way to be invalid, so the parser never complained.

Two checks now cover that gap, and the lesson generalises past this
sweep: **a lock that proves the old thing is gone proves nothing about
what replaced it.**

- `test_no_utility_class_in_the_markup_resolves_to_nothing` — every
  utility-shaped class in a template must carry a rule in some stylesheet.
  It reads conditional attributes too, since two dead meters hid inside
  `{{ 'a' if x else 'b' }}` where the first pass could not see them.
- `test_no_opening_tag_is_missing_its_closing_bracket` — walks each tag,
  stepping over quoted values, and fails if a `<` arrives before a `>`.

Both are cheap. Run them before trusting any future sweep, and prefer a
sweep that fails loudly on a hex it cannot map over one that guesses.

## Type

Archivo carries display and text from one variable file; its width axis
gives headings an expanded, institutional stance while the normal width
stays tight in dense tables. IBM Plex Mono owns every machine value:
timecode, DMX address, ISRC, money, deltas, IDs, table numerics — always
with `tabular-nums`.

| Step | Size | Tailwind | Use |
|---|---|---|---|
| label | 12px mono, .13em, caps | `text-xs` / `.sb-label` | labels |
| small | 13.5px | `text-sm` | secondary copy |
| body | 15px | `text-base` | prose |
| h3 | 17px | `text-lg` | card titles |
| card title | 19px | `text-xl` | priority cards |
| h2 | 22px | `text-2xl` / `.sb-h2` | section heads |
| h1 | 28px | `text-3xl` / `.sb-h1` | page titles |
| numeric | 32px | `text-4xl` | metrics |
| display | 40px | `text-5xl` / `.sb-display` | hero |

**12px is the floor.** 9–11px text is unreadable on a laptop in a green
room. Letterspaced 12px mono reads smaller than it measures, which is how
the old 9px labels retire without the page getting louder.

**Uppercase belongs to structure** — page titles, section heads, labels.
Never body copy, never card titles; those stay sentence case so they can
be read rather than scanned.

## Space, shape, depth, motion

- **Spacing** `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64`, nothing between.
- **Radius** `6px` controls · `10px` panels · `999px` pills. `50%` is a
  circle, which is a shape rather than a radius, and is allowed.
- **Elevation** a lighter surface and a 1px top highlight, not drop
  shadows: `--sb-e1` flat card, `--sb-e2` raised panel, `--sb-e3`
  floating overlay.
- **Motion** 120ms controls, 220ms panels, both
  `cubic-bezier(.2,.6,.35,1)`. The landing sections keep their own
  150–250ms band, which their own tests pin.
- **Focus** every interactive element gets a 2px gold ring offset by 2px
  of ground, from the base layer, platform-wide.

## The component library

`templates/_sb.html` (markup) plus `@layer components` in
`tools/tailwind-input.css` (styling). **If a page needs a pattern the
library does not cover, add it to the library rather than styling it
one-off** — that is the whole mechanism by which this stops drifting.

```jinja
{% import "_sb.html" as sb %}
{{ sb.btn("Send request", variant="primary", size="sm") }}
```

| Macro | Notes |
|---|---|
| `btn` | primary / secondary / ghost / danger, two sizes. `disabled_reason` is the only way to disable one, so a dead button always says why |
| `badge` | dot **and** colour, so state survives greyscale and colour-blindness |
| `kpi` | value, scale, delta, target, sparkline — plus a "not started" variant that shows the first step instead of a 0 |
| `priority` | severity stripe, quantified impact, one real primary action |
| `module_card` | icon, no LIVE badge |
| `table` | mono right-aligned numerics, badge status column |
| `field` | real `<label>` above; the placeholder is an example, never the label |
| `transport` / `timecode` / `cue` | the console pages |
| `rail` | icon nav |
| `icons` | the shared 24-box stroked set |

Two modules keep their own class vocabulary because their JavaScript
binds to it: Light Studio (`lx-*`) and the Team-Up Board (`tb-*`). Both
now read their values from the tokens rather than from private hexes, so
they move with the system without their scripts being touched.

## Exemptions, and why they exist

Three kinds of colour in this repo are **not** interface chrome, and
tokenising them would be a bug. All three are allowlisted in the sweep
and in the test:

- **Stage colours** (`static/js/lights*.js`, `lights_store.py`, and the
  hue slider in `light-studio.css`). `#FF0000` there means the bar goes
  red, not "critical" — and a hue slider made of tokens cannot pick a
  hue.
- **Artwork and cover palettes** (`artwork_config.py`,
  `discover_config.py`, `network_config.py`, `artwork.html`). Output, not
  interface.
- **The Rack and EQ instrument faces** (`rack.html`, `_gear.html`,
  `rackdsp.js`, `artist-eq.css`) — see the standing rule below.

Third-party brand marks (Spotify, Apple Music, YouTube, Deezer, Stripe,
SoundCloud) are never swept: a brand colour is a fact about someone
else's brand.

### The Rack — instrument surfaces
| Token | Use |
|---|---|
| `#e8c667` | lit value, arc, pointer |
| `#c9bd9c` | engraved legend on dark |
| `#8a7c5d` | secondary legend |
| `#4c4536` / `#2e2920` | chassis dark / silver-unit text |
| `#e07a3c` | cut — negative EQ gain, and the bass instrument band |

## Rules that came from being wrong

**No black boxes on black with dim grey text.** A standing correction.
Use ivory bands, gold accents, amber borders and near-white copy.

**Small type is engraving, not body copy.** The 8–10px sizes on the Rack
and the EQ are scale markings on an instrument — frequency labels, dB
ticks. They are correct at that size. A blanket "raise all small text"
sweep would cost the hardware look and fix nothing. Body copy, labels and
anything a decision depends on must not be that small.

*Reconciled with v1's 12px floor:* the floor applies to the interface,
and the sweep raised 397 instances of 8–11px type across the app. The
Rack and EQ keep their engraving, and the test allowlists exactly those
four files. The component library also runs three mono micro-labels below
the floor, as the spec draws them — badge 11px, table header 11.5px,
transport caption 10.5px — and those are reviewed, in one file, rather
than ad hoc across 163 templates.

**Disclosure travels with the number it describes.** The public press kit
carried a "Sample metrics" line in a section the artist could switch off
independently of the figures. A disclosure that can be hidden separately
from the thing it discloses is not a disclosure. Sample warnings now
render against the numbers themselves.

**Never two badges that contradict.** A green "Catalog verified" sat
directly above "Sample metrics shown". The verified badge now only
appears when the figures are genuinely from uploaded statements.

**A dead control must say why it is dead.** The `btn` macro takes
`disabled_reason` and nothing else can disable a button, so "Add cue"
greyed out always carries "Load a song first" on hover.

**A component that can be a link must never contain a link.** The KPI tile's empty variant carried its own first-step link, and the macro also wrapped the tile in an `<a>` when given an href. Nested anchors are not HTML: the parser closes the outer one at the inner one's open tag and the inner link falls out of the component into the page. Counting the elements never catches it — only containment does — so `test_the_component_macros_never_nest_an_anchor_in_an_anchor` walks the rendered macros with a real parser. An empty tile is always a `<div>`.

**An empty metric is not a failing metric.** `0%` with no tracks behind
it reads as failure when it means "not started". The `kpi` macro's empty
variant shows the first step instead.

## Touch

Keyed on `(pointer: coarse)` where the control is physical, and on width
where the layout is. A touch laptop at 1400px needs the same targets a
phone does; a narrow desktop window does not.

- **44px minimum** on anything tappable. Enforced on rack module
  switches, format pickers, Hours decision buttons, EPK controls and the
  two header buttons.
- **Hover-only is missing on touch.** Anything revealed by
  `group-hover:` needs an `@media (hover: none)` fallback. Removing a
  catalog track was impossible on a phone because of this.
- **Keyboard focus must be visible**, and shaped like its control — the
  rack knobs carry a round ring, because a square outline on a round knob
  reads as a rendering fault.

## Motion

For loading, completion, progression, validation and status changes.
Not for decoration. `prefers-reduced-motion` is honoured globally by a
`*` guard in the base layer, not per component.

## Components worth reusing

Design system: see the table above. The Rack keeps its own instrument
vocabulary: `.u` / `.u-dark` / `.u-silver` (rack units), `.plate`,
`.pick` + `.cap` (segmented pickers), `.sw` (switch/button), `.fader`,
`.lamp`, `.lane`, `.note`, `.sk` (engraved label), `.chip`, `.rk-knob`.

## Known debt

- ~~Tailwind arbitrary values are duplicated rather than tokenised.~~
  Closed by v1: the build step exists, the tokens are in the theme, and
  3,923 colour literals plus 2,466 sizes and radii were swept onto them.
- `loudness.js` and `audio_readiness.py` each keep their own copy of the
  platform loudness targets. A test forbids them disagreeing, but they
  are still two copies.
- ~10 painful and ~12 cosmetic mobile findings remain, plus 48 rack
  `title=` tooltips carrying the only explanation of what a control does
  — invisible on touch, and a content decision rather than a layout one.
- 151 of 299 templates now compose from the library. The remainder are
  mostly partials and fragments with no chrome of their own; what the
  rest still build by hand are stat cards and tables, which are per-page
  shapes rather than repeated ones. Five pages use the Jinja macros
  directly (Command Center, Tour Hub, Stage Plot, plus the two console
  modules through their own CSS).
- Some views still carry more than one gold-filled element. Status pills
  and gold-tinted buttons are demoted, which fixed most of it, but which
  of two remaining *actions* is primary is a judgement about the page.
  `tools/gold_discipline.py` reports the offenders per page.
- Three responsive `clamp()` heroes (`submit`, `release_signal`) stay off
  the fixed title step deliberately — they are art direction, and pinning
  them to 28px would be worse rather than more consistent.
