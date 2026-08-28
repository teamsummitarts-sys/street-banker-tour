# Light Studio

`/lights`. A browser light-show tool: load a song (Web Audio, never
uploaded), cue looks to it on a simulated stage, and drive real fixtures
over Web Serial (ENTTEC USB Pro framing, `0x7E … 0xE7`, 30 fps).

## Files

| File | Role |
| --- | --- |
| `static/js/lights-engine.js` | Pure maths, no DOM — groups, fade resolver, DMX framing, waveform peaks, onset/BPM detection, beat snap, tap tempo, looks. Loads in Node (`tests/js/check_lights.js`) and the browser (`window.LightsEngine`). |
| `static/js/lights.js` | The studio: transport, waveform lane, hi-DPI stage, cue list, group picker, looks, bar selection, keyboard, library/autosave, focus mode, phone dock. Test hooks on `window.__lightsTest`. |
| `static/css/light-studio.css` | Hand-written `lx-*` styles (the Tailwind build is frozen). |
| `templates/lights.html` | Page. Every `$("id")` in `lights.js` must exist here — `tests/test_light_studio.py` enforces it. |
| `lights_store.py` | Library: `light_show_library` (named shows, track + tour-date links) and `light_show_versions` (snapshot per explicit save, last 20). The one-per-user working copy stays in `light_shows`. |
| `tools/dev_preview.py` | Local preview on a throwaway DB for the in-app browser pane (`.claude/launch.json` → `sb-preview`). |

## What the overhaul added

- **Waveform timeline** under the transport: decoded peaks (max/min per
  pixel, hi-DPI), draggable cue flags (blackouts are dashed diamonds with
  a cross), click to seek, wheel to zoom / shift-wheel to pan / pinch on
  touch, playhead, beat grid when a tempo is known.
- **Focus mode**: `body.lx-focus` tightens the shell and folds the sidebar
  to its rail (`body.sb-rail`, desktop). Remembered in `localStorage`
  (`lxFocus`, `lxRail`); the header button and the rail toggle both undo
  it. Desktop: stage and cue list share the viewport; phones stack.
- **Transport**: sticky; big tabular-mono timecode; status text wraps and
  never collapses; DMX state chip (`Preview only` / `Connected · universe
  1 · N fps` measured from real writes / error). Phones get a fixed
  bottom dock (Play, + Cue, Blackout, clock) instead of the tall sticky
  bar.
- **Stage**: renders at `devicePixelRatio`, fills its container, redraws
  on resize; ≥44 px hit areas; hover / selected / mirror-partner /
  group-hover rings; arrow keys nudge the selected bar (`R` flips);
  Hung / Side-stick segmented control for the selected bar; a bars table
  as the screen-reader twin of the canvas.
- **Group picker**: mini stage diagram per group with the firing bars lit;
  hover previews on the stage; sets the selected cue's group or the
  default for new cues.
- **Cue rows**: mono timecode, colour swatch (blackout ✕), group glyph,
  fade, editable note, delete; click previews the stage at that time.
  “+ Cue” disabled with a hint until a song is loaded (or Run cues only).
- **Looks** chips (amber wash, cold blue, red alert, white full, violet
  haze, blackout) + keys 1–6.
- **Beats**: onset/BPM detection on load (parabolic-refined
  autocorrelation), snap-to-beat toggle, tap tempo, grid toggle.
- **Library**: named shows, autosave (1.5 s debounce) to the working
  copy + the active library entry, “Saved ✓ hh:mm”, version history with
  restore, link to a track and a tour date (validated server-side).
- **Keyboard**: Space play/pause, C cue, B blackout, 1–6 looks, 7–0 your
  looks, X all off, ←/→ seek, Esc closes the gel book / deselects;
  visible focus rings; helper text ≥12 px.

## Unsaved work, undo, accessibility (polish pass)

- **Draft vs library.** Every change autosaves the *draft* (the
  `light_shows` working copy) 1.5 s later with `draftDirty` /
  `draftSavedAt`. A library row changes **only** on "Save to library",
  which also takes a version. A dirty draft of a library show prompts on
  load: keep the draft, or open the last library save. `beforeunload`
  warns while there are unsaved changes relative to the last library
  save (or an autosave is pending). The indicator by the Save button
  reads *unsaved changes* / *saved to library* / *not in library yet*.
- **Undo/redo.** `LightsEngine.makeHistory(50, 800)` — snapshots of
  cues/pos/rot/bars/chans; gestures coalesce by key inside 800 ms;
  Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, Ctrl+Y (ignored while typing in a
  field); Undo/Redo buttons in the cue pane.
- **A11y.** Labelled transport; `role=list` cue rows with timecode+look
  labels; waveform as a keyboard slider; bars table with Select buttons
  (updated in place); `#lx-live` polite announcements; focus rings.
- **Focus rail.** `body.lx-focus` at ≥1024 px hides `#sb-aside` and
  shows `#lx-rail` (56 px, icon links + expand control).
- **Known-good interactions (self-tested with a real WAV through the
  file input):** click-seek, flag drag at any zoom, zoom anchoring, pan,
  pinch, Fit song, Detect beats, Snap to beat.

## Colour, looks, output, patch (audit pass)

- **Stage art.** Background is `static/img/stage-bg-2.jpg` (the supplied
  stage photo); fixtures are `static/img/light-bar.png`, an 8-lens LED bar
  sprite drawn to scale (rotated for a side stick) with its lenses lit in
  the look's colour. Lens geometry lives in `LENS_X` / `LENS_CY` /
  `LENS_R` in `lights.js` (measured from the sprite once). A drawn housing
  is the fallback until the sprite loads.
- **Gel book + mixer.** Every cue swatch is a button that opens `#lx-gel`,
  one shared popover: 30 named gels (Lee numbers people actually carry),
  recent colours (`localStorage` `lxRecentGels`), **your palette**
  (`lxPalette` — colours you mixed and named; right-click a chip to remove
  it), a hex field, and a **"Mix a colour" RGB + HSV picker**. The two
  spaces stay in step through `LightsEngine.rgbToHsv` / `hsvToRgb`
  (pure, unit-tested, round-trip verified). HSV's **V is the colour's own
  brightness, never the fixture's output** — intensity stays the slider on
  the cue. "System picker…" still reaches the OS dialog for anyone who
  wants it. Esc closes and returns focus to the swatch.
- **Fade indicators.** Each cue draws a wedge on the waveform running back
  over its fade time, tinted with the cue's own colour (warm for a look,
  red for a blackout), so how long a look takes to arrive is visible on the
  timeline. The selected cue's wedge is outlined and labelled with its
  duration.
- **Group picker.** Role chips only — All / Odd / Even / Pairs, each with a
  mini stage diagram. A button per bar was a wall of chips that grew with
  the rig, so a single bar is now a compact dropdown and **any** combination
  is shift-click on the stage (`b1+b3+b6`), with a plain-language summary of
  what is picked and a Clear control.
- **Your looks.** "Save selected cue as look" stores up to four
  `{name,color,intensity,fade}` in `show.looks`, so they travel with the
  working copy and every library save/version. Keys `7 8 9 0` apply them;
  `1–6` stay the house looks, `B` blackout. Removable with ×. Covered by
  undo.
- **Per-group colour at one timecode.** Not a per-cue field — instead two
  cues at the same time on different groups resolve per fixture
  (`lightingAt` is per bar; later cue wins for a bar in both). Proved in
  `check_lights.js` ("same-timecode cues merge per bar").
- **Hand-picked groups.** `shift-click` bars on the stage toggles them in
  a custom group key `b1+b3+b6` (`LightsEngine.customGroup` /
  `toggleInGroup`); the cue row's dropdown shows it as "Bars 1 + 3 + 6
  (picked)". The visual group picker is folded by default.
- **Grand master + All off.** Live state, not part of the show:
  `LightsEngine.scaleLooks(looks, master, panic)` feeds the stage, the
  bar list and the DMX frame (`outLooks(t)`). `X` toggles All off; the
  button goes red and `body.lx-panic` outlines the stage. When a DMX
  interface is connected the rig is also fed a slow heartbeat while idle
  so it holds what the stage shows.
- **DMX patch.** `show.dmxStart` (first address), `show.dmxAddr[bar]`
  (per-bar override, from the bar drawer), `show.dmxUniverse` (label on
  the chip; the USB Pro drives one universe).
  `LightsEngine.fixtureAddress(show, bar)` resolves; `patchOverlaps` warns
  in the drawer; a fixture patched past 512 is skipped, never wrapped.
- **Bar drawer.** Clicking a bar (canvas or the All-bars list) opens
  `#lx-barctl`: orientation, across/down %, DMX start, look now, mirror
  partner, prev/next. The All-bars list (`#lx-bars-list`) replaced the
  table as the screen-reader twin.
- **Audio controls.** Volume (gain node), rate (½× … 1½× —
  `now()` scales elapsed context time by the rate so the clock and cues
  stay in song time), and a scrub slider mirroring the playhead.
- **Auto-cue (epic 1).** `Auto-cue` in the wave bar runs
  `LightsEngine.analyzeTrack` (sections, drops, hard stops, tempo) and
  `generateCues` on the loaded song: one editable cue per section, a
  three-beat accent burst on a drop, blackout + restore around hard
  stops. Auto cues carry `auto:true`, wear an "auto" badge and become
  yours the moment you edit any field (`own()`); "Clear N auto cues"
  removes only the untouched ones. Sections/stops are kept in
  `show.sections` / `show.stops` and drawn as tinted, labelled bands on
  the waveform; re-running replaces the auto set, never your cues.
- **Looks abstraction + rig profiles (epic 2).** A cue stores *intent*, not
  channel values: colour, intensity, fade, a **group role** (`all` / `odd` /
  `even` / `pairN` / `bN` / a hand-picked `b1+b3`), an optional `move`
  (still / pulse / strobe / chase, beat-locked to the show tempo, 120 BPM
  until one is detected) and the `look` key it came from. `lightingAt` +
  `movementGain` + `dmxFrame` are the compiler that renders that onto the
  current rig, so a chase written for 8 bars runs across 4.
  A **rig** is bar count, fixture type, layout and patch —
  `LightsEngine.RIG_PRESETS` ships *Dive bar 4-bar*, *Club 8-bar* and
  *Festival side-stick*; `applyRig` swaps one in. Because a bar-naming
  group is a *position*, `remapGroup` moves it proportionally
  (bar 7 of 8 → bar 4 of 4, `pair4` → `pair2`) instead of leaving the cue
  dark; roles like All/Odd/Even are rig-independent and never rewritten.
  Changing the Bars dropdown remaps too, and the whole swap is one undo step.
  Saved rigs live in `light_rigs` (per account, capped at
  `lights_store.MAX_RIGS`, sanitised server-side) and can be bound to a
  **venue** by name (`venue_key` normalises case/punctuation, newest binding
  wins). Linking a show to a tour date at that venue *offers* the rig — it
  never swaps the rig under the user.
- **Import / export.** `Export JSON` downloads
  `{format:"street-banker-lights", version:1, show}`; `Import JSON`
  sanitises every field (`importShow`) and replaces the working copy only
  (confirm first when cues exist) — library saves are untouched.

## The phone remote (epic 3)

A second operator's hands. The laptop stays the source of truth; the
phone can only enqueue a button press, and `applyRemoteCommand` in
`lights.js` decides what to do with each one. Anything it does not
recognise is ignored rather than guessed at.

There is no WebSocket in this stack and no job runner, so the transport
is polling: the phone POSTs a press, the laptop drains its own queue
every 400ms. That is fast enough that a blackout from the phone lands
about as quickly as pressing X on the keyboard.

**Pairing.** `POST /lights/remote/start` mints a 32-hex code and retires
any previous one — a rig has one remote at a time. The studio shows a QR
(rendered by `segno`, already a dependency) plus the plain URL. The
pairing URL is built from the request host, not `PUBLIC_BASE_URL`, so a
local or self-hosted run hands out a code the phone can actually reach;
`X-Forwarded-Proto` is honoured for TLS-terminating proxies.

**Authorisation.** `/lights/remote/<code>` is public — the unguessable
code is the whole authorisation, exactly like a share link, so a
bandmate picks it up without an account. `_PUBLIC_PREFIXES` carries
`"/lights/remote/"` with the trailing slash so it cannot swallow
`/lights` or `/lights/library`; `start`, `end`, `poll` and `qr.svg` each
call `current_user()` themselves. Codes expire after
`REMOTE_TTL_HOURS = 12`.

**What the phone carries.** Buttons only — no cue list, no show data, no
audio, no studio script. `templates/lights_remote.html` is standalone
and a test asserts the page contains none of it.

**Commands.** `blackout` · `restore` · `play` · `stop` · `tap` · `look`
(value 1–6) · `next` · `prev` · `ping`. Anything else is refused with a
404 rather than stored — the remote is not a general channel. `ping` is
a keep-alive so the phone's status line is honest before the first real
press; the laptop treats it as a no-op, because sending `tap` as a
heartbeat would drag the tempo.

**Holding a look.** A phone look press does *not* edit the cue list —
the operator cannot see that happening from across a dark room and
would find the show changed after the gig with no undo. It sets `bump`,
a rig-wide override read at the top of `outLooks()`, which outranks both
the cue list and the between-songs gap look. Pressing the same look
again releases it. The studio shows a loud `#lx-bump` chip in the
transport row while a look is held, and that chip is also the release
control.

**Reload safety.** The studio calls `resumeRemote()` at boot: if the
server still holds a live pairing for this account it picks it back up,
so a mid-set refresh does not leave the phone pressing buttons into a
queue nobody drains. `drain_remote_commands` applies the same expiry
rule the phone sees, so an expired pairing is never resumed.


## Sending a show out for notes (epic 5)

A designer sends the show to a manager, an MD or the artist and asks
"what do you think of the second chorus". `POST
/lights/library/<id>/share` mints a 32-hex token with a permission of
`read` or `comment`; the reader opens `/lights/show/<token>` with no
account, exactly like every other share link on the platform. The owner
can revoke a link at any time, and a revoked or deleted show renders a
plain "this link is no longer live" page rather than a 500.

**What travels.** `_share_payload()` in app.py assembles the response
field by field — name, cue data, updated, cue count, permission —
rather than handing over the library row, so a column added later
cannot quietly start travelling. A test asserts the page contains none
of the designer's other shows, their email, or the studio script.

**No audio, ever.** The song never left the designer's machine, so the
reader gets the cue list against a timeline plus a stage that runs the
cues — the same thing "Run cues only" does in the studio.
`lights-share.js` reuses `lights-engine.js` (`lightingAt`, `fmtClock`,
`groupLabel`) so the reader sees the real show, not a mock-up.

**Notes anchor to a TIMECODE, never a cue id.** `payload()` in lights.js
strips `_id` from every cue on save, so cue ids are regenerated on each
load and an id anchor would break on the next save. A second at 1:14 is
still 1:14 after the cue there is deleted. `tests/test_light_studio.py`
pins this, because it is the kind of thing a later refactor would
"improve" back.

**Threads stay shallow** — one level of reply. A note on a cue is not a
forum. A reply whose `parent_id` belongs to a different show is filed as
a new top-level note rather than accepted, so a reply cannot be used to
reach a thread on someone else's show. Only the owner settles or deletes
a note; a reader can raise one but cannot decide it is dealt with.
Deleting a show takes its links and its notes with it.

**Studio side.** The "Share & notes" fold lists live links with a revoke
button and the note threads with reply / settled / delete. Unresolved
notes draw as gold pins under the waveform — clear of the cue flags,
because a note is about a moment and may point at a moment with no cue
yet. Clicking `@ 1:13.8` moves the playhead and pans the view if that
moment is off-screen at the current zoom.

**A trap worth knowing.** The `js_json` Jinja filter accepts an object
*or an already-serialised JSON string*, and used to pass any `str`
through untouched. Handing it a bare token emitted
`window.__lxToken = 691ae30b…;` — a malformed numeric literal that took
the whole inline script down. It now serialises any string that is not
valid JSON, because the same path with a user-supplied name would have
been stored XSS rather than a syntax error.


## Endpoints

`GET /lights/rigs` · `POST /lights/rigs/save` (`id?`, `name`, `venue`,
`data`) · `POST /lights/rigs/<id>/delete`.

`POST /lights/library/<id>/share` (`permission`, `label` → `token`, `url`) ·
`GET /lights/library/<id>/shares` · `POST /lights/share/<token>/revoke` ·
`GET /lights/show/<token>` (public reader page) ·
`GET /lights/show/<token>/comments` · `POST /lights/show/<token>/comment`
(`author`, `body`, `t?`, `parent_id?`) · `GET /lights/library/<id>/comments` ·
`POST /lights/library/<id>/comment` · `POST /lights/comments/<id>/resolve` ·
`POST /lights/comments/<id>/delete`.

`POST /lights/remote/start` (→ `code`, `url`) · `POST /lights/remote/end`
· `GET /lights/remote/poll` (→ `code`, `commands[]`, `phone_seen`) ·
`GET /lights/remote/<code>` (public phone page) ·
`POST /lights/remote/<code>/cmd` (`kind`, `value`) ·
`GET /lights/remote/<code>/qr.svg`.

`GET /lights` · `POST /lights/save` (working copy) · `GET /lights/library`
· `POST /lights/library/save` (`id?`, `name`, `data`, `track_id`,
`tour_show_id`, `autosave`, `note`) · `GET /lights/library/<id>` ·
`GET /lights/library/<id>/versions` · `POST /lights/library/<id>/restore`
(`version_id` → `data`) · `POST /lights/library/<id>/delete`.

## Testing in the browser pane

The service worker caches static assets cache-first, so after editing
`lights.js`/`light-studio.css` unregister it and clear caches before
reloading (or bump `?v=`). `requestAnimationFrame` is frozen while the
pane is hidden — use `__lightsTest.tick()` to force a repaint and
`__lightsTest.loadBuffer(audioBuffer, name)` to load a synthesized song
without a file dialog.
