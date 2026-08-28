# Implementation Log

Newest first. Each entry states what changed and what evidence drove it.

## Rack measurements reach the rest of the app

**Why:** an audit proved the Rack's loudness engine produced real,
standards-compliant measurements that no engine ever read, while Release
Readiness was scored entirely from campaign and artwork metadata. See
`PRODUCT_GAP_ANALYSIS.md`.

**Changed**

- `audio_readiness.py` *(new)* — rulings from stored measurements. True
  peak against the −1 dBTP ceiling, loudness against published platform
  targets, EBU 3342 range, tempo/key gated on detector confidence.
- `db.py` — `track_analysis` table; `save_track_analysis`,
  `get_track_analyses`, `latest_track_analysis`.
- `app.py` — `POST /rack/analysis`. Stores only; computes nothing.
  Rejects non-finite values and reports back the assessment.
- `static/js/rackdsp.js` — `reportAnalysis()` posts after each
  measurement, de-duplicated, and fails silently so a network error
  cannot break the meter.
- `qualification.py` — **Master Quality** category.
- `artist_twin.py` — `rack` added to `SOURCES`; `gather_context` reads
  the latest measurement under consent.
- `tests/test_audio_readiness.py` — 22 tests.

**A real bug the tests caught.** A master that is quiet *and* already
peaking fell through both branches to "sits in the normal band". That
combination is diagnostic, not neutral: the average is far below target
while the peaks are at the ceiling, so it cannot be raised without
clipping — usually one stray transient holding the record down. It is
now its own ruling.

**Verification:** 22 new tests; full suite green.

## Two more arrows: the Twin's master read, and money sorted by money

**Why:** a severed-signal audit traced every place the app computes real
data. Of 56 signals across the Rack, smart links and the money side, 42
came back severed. Two were worth closing immediately.

**The Twin was apologising for a capability it has.** `artist_os.py`
listed "Hook / structure notes — audio analysis, planned, not faked"
among the sections waiting on data that had not landed. It landed this
session. `twin_report` now takes the latest Rack measurement and reports
a **Master read**: what the loudness meter found, which rulings are
problems, and what to do. When nothing has been measured it says what
unlocks it rather than sitting empty.

**Recovery cases sorted by recency, not by value.** `list_recovery_cases`
ordered by status then `updated DESC`, so a $4 case sat above a $4,000
one purely because someone opened it more recently — in a list that is
worked from the top down. Now ordered by `estimated_amount` within
status, so open cases lead and the biggest money leads within them.

**A finding I refuted.** The audit claimed the Money Queue sorted a
$4,000 action identically to a $4 one. It does not: `action_queue` sorts
on `(not critical, -impact)`. Release-blocking items lead, then value.
Reported as a correction rather than "fixed".

**Verification:** 5 new tests, 489 in the suite, all green.

## The audit caught a bug I had just shipped

**The tempo and key pipe was dead on arrival.** `reportAnalysis` read
`tk.bpm.bpm` and `tk.key.key`, but `tkFound` stores `bpm` as a *number*
and `key` as a *string*. Both evaluated to `undefined`, `JSON.stringify`
drops undefined keys, and every tempo and key column landed NULL — while
`audio_readiness.tempo_key_ruling` and the Twin sat waiting for values
that could never arrive. The pipe was laid end to end and carried
nothing.

Two breaks, both fixed: detection was also discarding `bpm.confidence`
and `key.score` one line after computing them — the confidence being
exactly the number that decides whether a tempo is safe to quote.

**`sample_peak` was written on every pass and read by nothing.** It is
now evidence in the true-peak ruling, and it is the clearest statement of
the whole problem: *"A normal peak meter reads −0.31 dBFS on this file,
so 0.28 dB of it sits between the samples where that meter cannot see."*

**Two copies of the platform targets.** `loudness.js` has seven,
`audio_readiness.py` six. A test now refuses to let the overlapping six
disagree — the Rack must not tell an artist one figure while the score is
computed from another. They are deliberately not merged: the browser
needs its copy and the server needs its own.

**Verification:** 30 tests in this module, 492 in the suite, all green.

## Still severed (from the completed audit, unverified)

- Per-post click heat — the thesis in miniature: rollout posts carry real
  attribution, derived per request, never persisted, never informing the
  next rollout's platform choice.
- Catalog valuation from real statements — computed, discarded, so no
  trend exists.
- Territory splits — flagged as possibly *wrong*, not merely unused.
  Check before building on it.
- Hook windows — the Rack finds them, snapped to the downbeat; Rollout
  Studio generates clip ideas without them.
- `short_term_max` / `momentary_max` — stored on every pass, read by no
  ruling. These are the numbers broadcast delivery specs are written in.

## Territories: the claim was wrong, the danger was real

The audit flagged this as *"worse than unused — the Territories insight
the app actually surfaces is built from invented data."* Checked, and
that is **not true**:

- `/territories` renders `royalty_types.territory_report(user_id)`, which
  reads the real `statement_rows.territory` column.
- `/insights` renders `insights_engine.build_insights(user_id)`, which is
  real-data driven.
- The fabricated path, `insights_config.get_insights_data`, was **never
  called** — imported at `app.py:63` and invoked nowhere.

A second claim, that ingestion is "territory-blind by construction"
because `app.py:818` rebuilds rows as a 4-key dict, is technically true
and harmless: `statements_engine.analyze` consumes exactly `title`,
`source`, `amount`, `period`. Dropping territory matches the contract.

**But the investigation found something worth acting on.**
`insights_config.py` built a ranked list of *money the artist is not
collecting* — `"Close collection gaps in N territories"` with an `impact`
figure and a CTA — entirely from `_TERRITORY_SHARES`, hardcoded
percentages. It was dead, but it was imported into `app.py`, so wiring it
into the insights template was one line, and that line would have looked
completely reasonable to anyone.

Fabricated audio measurements would be embarrassing. Fabricated *money
owed* is the one number this product cannot get wrong.

Deleted `insights_config.py` and both dead imports. `territories_config`
survives — a test asserts real invariants on it — but now carries a
header saying it is wired to nothing, must stay that way, and where the
real per-country money actually lives.

**Verification:** 492 tests green.

## Rollout learns from its own rollouts

The audit called this *"the product thesis in miniature and it is
severed."* Two of its three claims held; the third — and the most
alarming — did not.

**Held.** `rollout_engine.generate_rollout(campaign, lyrics,
video_asset_id, image_asset_id)` takes no performance argument.
`next_action` reads only post statuses and asset types, and its final
line is *"Rollout is live — watch the performance page for what
converts."* The app told the artist to watch what converts and did not
watch it itself.

**Did not hold.** The claim that `clear_posts()` destroys the evidence
"at the exact moment the next decision is made" is wrong.
`variant_name()` encodes `rollout_{platform}_{phase}_{date}`,
`create_variant` stores `utm_source={platform}`, and `clear_posts` only
touches `ro_posts` — `ml_variants` and their events are never deleted.
The attribution survives every regenerate.

That correction is what made this cheap: **no schema change, no
migration, and the history already reaches back to the first rollout the
account ever ran.**

`rollout_learning.py` rolls those variants up by platform and by phase
and reports conversion *rates*. Two disciplines:

1. **It refuses to speak on thin evidence.** Under 25 visits on a
   platform, or 60 across everything, it says so and stops. A 75% click
   rate on 8 visits is noise, and an artist who reweights a campaign on
   it is worse off than one told nothing.
2. **Rates, not totals.** The platform with the most clicks is usually
   just the one with the most posts.

Wired in two places: an empty platform selection now defaults to what
converted rather than a fixed list (falling back to the fixed list when
evidence is thin, so new accounts behave exactly as before), and
`next_action` says something true when there is something true to say.

**Verification:** 14 new tests, 506 in the suite, all green.

## The press kit was quoting a catalogue that belonged to nobody

The audit called this "the sharpest break on the money side". It
understated it.

`get_earnings_trend()` is a literal Jan–Jun list in `royalty_data.py`,
identical for every account. It feeds `estimate_catalog_value`, which
feeds the public EPK's **Est. Catalog Value** — rendered in gold,
captioned "Mid valuation", on the page an artist sends to a label. And
the `overrides` merge covers only `tagline, bio, location, genres,
socials, press, contact`: **`stats` was never overridable**, so
`Total Streams`, `Catalog Earnings`, `Est. Catalog Value` and the release
count were all demo figures for every artist on the platform.

**Not undisclosed** — a line at the foot of the sweep section did say
"Sample metrics shown". But it sat in 9px at `white/35`, directly beneath
a green **"Catalog verified"** badge that contradicted it, and inside a
section the artist can switch off independently of the numbers.

Now: `epk_config.real_stats()` builds the headline figures from the
artist's own statement rows and track count — Catalog Earnings from the
real total, Est. Catalog Value from `build_royalty_summary`'s annualised
3–5× band, Releases from the real catalogue. **Anything that cannot be
computed is left out rather than filled in**, so an empty press kit looks
empty instead of looking successful.

The disclosure now travels with the numbers: the sample warning renders
against the cover strip itself, and the "Catalog verified" badge only
appears when the figures really are from uploaded statements.

**Three bugs found while doing it, two of them mine:**

1. `analyze()` does not return `valuation`/`annualized` — those live in
   `build_royalty_summary`. The audit cited the right lines and the wrong
   function.
2. The template indexed `e.stats[0..3]` directly, so any account with
   fewer than four real stats crashed the public page.
3. Passing `stats_override=[]` on an account with no real data overrode
   the demo stats with nothing and deleted the section. `None` is the
   fallback signal, not `[]`.

Also fixed: turning the stats section off left stats visible in the sweep
panel. "Hide stats" now means hidden everywhere.

**Verification:** 506 tests green.

## The hook now outlives the tab that found it

The audit called this "the largest product-level break in the area", and
both its claims held. `scanHooks` finds the highest-energy 15 and 30
second windows and `snapHook` aligns them to the measured downbeat — then
the results became DOM rows terminating in a browser download. The
`/rack/analysis` payload I wrote earlier today had no field for any of
it, so nothing in the app could say where an artist's hook was outside
the one tab that measured it.

Persisted now: `hook_15s`, `hook_30s`, `first_beat`, `bar_seconds`,
`grid_confidence`. The Master read reports it as a timestamp — *"Strongest
section: 30 seconds from 1:04, 15 from 0:34"* — and says whether it was
snapped to the beat or is energy-only, because a clip that starts
mid-beat reads as a mistake however good the audio is.

The hook is deliberately **not** a quality gate. An unscanned hook leaves
a clean master reading "ok"; it is information for cutting a clip, not a
judgement on the record.

**A deployment bug caught before shipping.** `track_analysis` was created
earlier today, so any database from between then and now already has the
table — and `CREATE TABLE IF NOT EXISTS` does not add columns. Saving a
measurement would have raised "no such column: hook_15s" on every
existing install, including production. An `ALTER TABLE` migration now
runs alongside the others, and it is proved against a database built with
the old schema.

**Verification:** 6 new tests, 512 in the suite, all green.

## The score that gates money decisions now looks at money

The audit noted this as an inversion rather than a severance, and it was
right on both counts. `qualification.py` contained **zero** references to
statements, income, royalties, revenue or earnings — while gating:

| Unlock | Threshold |
|---|---|
| Catalog valuation review | 65 |
| Distribution rate improvement | 80 |
| Upstream review | 85 |

Three money decisions, scored entirely from marketing setup: link scores,
capture flags, fan counts, rollout posts, EPK assets, ISRC presence,
social handles, bio and press. An artist with real royalty income and no
smart links scored low. One with no income and a tidy press kit scored
high. `capital_engine` had the right three facts — income total, distinct
periods, distinct sources — and fed one page.

Added **Income on Record**, read straight from statement rows. Directly
rather than by importing `capital_engine`, which would drag the
trust-score dependency chain into this module. With no statements it
scores zero and says why, same rule the master read follows: absent
evidence is not a pass.

**And a bug of mine, found while doing it.** Every category is worth ten
points and the total was a bare sum. Adding "Master Quality" earlier
today took the maximum from 100 to 110 — silently making every unlock
threshold about nine percent easier to reach, without anyone changing a
threshold. The total is now normalised to 0–100, so category count and
threshold meaning are independent. Adding "Income on Record" would have
compounded it to 120.

**Verification:** 3 new tests, 515 in the suite, all green.

## The last two dead columns

`short_term_max` and `momentary_max` were written on every measurement
and read by nothing. Both were mine — added when the measurement pipe
went in, then never consumed.

The honest question was what they say that loudness range does not, and
there is a real answer: **LRA is the 10th–95th percentile spread and
discards the extremes by design. Short-term max *is* the extreme.** A
record can be perfectly consistent by LRA and still have one section
towering over the body of it, and only one of those two numbers can tell
you so. A test pins exactly that case — `range` reads "ok" while
`peak_section` reads "watch" on the same track.

Short-term loudness is measured over 3-second blocks, which is the window
broadcast and sync delivery specifications are written in, so this is
also the figure a sync submission gets judged on.

Reported as the gap above the integrated average: under 2 LU nothing
rises above the rest, over 8 LU one passage dominates, between them a
normal lift. No invented ceiling — the rulings describe what was measured
and name what it bears on.

**Verification:** 6 new tests, 521 in the suite, all green.

---

## Audit closed

Every finding from the severed-signal audit has now been checked
individually rather than taken on trust. Final tally:

| | |
|---|---|
| Severances and inversions closed | 9 |
| Bugs found and fixed | 7 (five of them mine) |
| Findings refuted or materially corrected | 4 |

The refutation rate held near a third throughout, and twice the
correction was worth more than the original finding: the territories
check found a fabricated-money generator one line from going live rather
than the reported bug, and the click-heat correction turned a claimed
migration into a zero-schema change.

## Funding quotes the artist's own money now

`/funding` showed a **Suggested Advance in gold, with a Request button
under it**, and three offers with dollar amounts scaled off the same
figure. Every input traced back to `get_earnings_trend()` — the hardcoded
Jan–Jun list. Every artist on the platform was shown the same advance
regardless of what they earn.

This is the same fabrication as the press kit, one step worse: a press
kit misrepresents, an offer invites someone to act.

`capital_engine.advance_eligibility()` computes it from uploaded
statements — the annualised 0.8–1.5× band that `capital_score` already
produced for a page nobody reaches from the funding flow.

Three decisions worth naming:

1. **A range, not a number.** `$7,328–$13,740` rather than a single
   figure, because the underlying calculation is a band.
2. **The conservative end under the button.** The number a Request acts
   on is the one most likely to survive someone checking the statements.
3. **No income, no offer.** `get_funding_data` returns zero offers and
   the reason, rather than three offers scaled off zero. An amount nobody
   can stand behind must not be requestable — the route refuses it.

**A bug found by the test, not by reading.** The normal return path
rebuilt `eligibility` as a three-key subset, silently dropping `real`,
`band` and `note`. The engine was correct and the page still showed
nothing, because the dict was reassembled in between.

**Verification:** the funding test now covers both halves — nothing
quoted without income, a range and a working request with it. 522 tests
green.

## Scores have a history now

Qualification, Trust, Capital Readiness and the catalog valuation all
recomputed on every request and stored nothing. That answers "where do I
stand" and cannot answer "am I getting anywhere", which is the question
an artist actually has. A score without history is a number; with history
it is feedback.

`score_history` holds **one row per score per day**. These recalculate on
every page load, so appending on each call would write hundreds of
identical rows a day and turn a trend into noise — the day's reading is
updated in place instead.

The engines record themselves, one guarded line each, so any page showing
a score builds its history without the route having to remember.

**The distinction the module exists to protect:** *no comparison yet* and
*no movement* are different answers. A first-day artist shown "+0"
concludes nothing is working; the truth is nothing has been compared. One
reading returns `None` and the page says "Tracking from today". Genuinely
unchanged returns `flat`.

Also: percent is omitted when the baseline is zero, because a 4-point
move from nothing is not an infinite improvement.

The qualification page now carries the movement above its score ring,
coloured by direction. A stored score nobody sees would be the same
failure in a new costume.

**Two test-isolation bugs of mine, both from shared database state:**

1. The EPK fixture checked for a *row* — but `save_epk_photo` inserts one
   with no slug, so `/epk/{None}` raised a `TypeError`. It now checks for
   the slug and mints one via `/epk/share`.
2. My funding test uploaded statements to the shared demo account, and
   the tax test asserts `$750.25` exactly. It has its own account now,
   promoted to `pro` because statements and funding both sit above the
   entry tier.

**Verification:** 21 new tests, 545 in the suite, green at `-n 8` and
`-n 4`.

## All four score pages show their movement

Trust, Capital Readiness and Catalog Valuation now carry their trend the
way Qualification already did — through `partials/score_trend.html`, one
include rather than four copies of the same markup, and Qualification was
refactored onto it too. Four copies drift; one does not.

Two behaviours the partial is built around:

- **Nothing renders without history.** A brand-new account sees no badge
  rather than a zero that reads as failure.
- **A falling score is not an error.** Down gets `text-red-300`, not the
  error red — it is information about a real thing, not a broken one.

Valuation is deliberately different from the other three: it exists only
where statements do, so with none the page says nothing rather than
inventing a number. Its test uploads a statement first, which is the
honest way to prove the behaviour.

**And a bug of mine, from the previous commit.** I had the EPK fixture
call `/epk/share` to mint a public slug. `/epk/share` is the *private
pitch-link token* — a different thing entirely — so the slug stayed
`None`, `/club/None` 404'd, and I had shipped it. The fixture now sets
the slug through the db layer, because which route happens to mint a
public slug is not something a fixture should depend on.

**Verification:** 550 tests, green at `-n 8` and `-n 4`.

## Mobile backlog closed

Every finding from the mobile audit was re-checked against the code as it
stands rather than fixed again from the original report. Of 38 confirmed
findings: **12 already handled** by earlier passes, **1 not a real
problem**, **11 still open and now fixed**.

Two of the eleven were more interesting than their descriptions.

**The fader fix I already made was being overridden.** `.vlv-amt .fader
{ height: 16px }` outranks the bare `.fader` rule in my coarse-pointer
block, both by specificity and by order — so the six tube-bank drive
sliders kept a 16px hit strip *while their thumb grew to 28px and hung
outside its own track.* My earlier change made those six visually worse,
not better.

**Login inputs at 14px.** Under 16px, iOS Safari zooms the viewport when
a field takes focus and does not zoom back, so a phone user is left
panning around a login form. Raised to 16px on coarse pointers only; the
desktop console face is unchanged.

### The rack's 48 tooltips

These carry the only description of what each control does — real
sentences, 60 to 130 characters — and hover does not exist on touch.
Printing all of them permanently would bury the instrument, so **Explain
mode** prints them on demand and turns them off again.

The captions are generated from the `title` attributes themselves rather
than a written list, so a control added later is covered without anyone
remembering the feature exists. Titles stay in place, so a pointer user
keeps the tooltip they had. `textContent`, never `innerHTML`.

### Final tally

38 confirmed findings: **12 already handled** by earlier passes, **2 not
real problems**, **18 still open and now fixed** across eleven files.

The last seven were the data pages — a goal-ring label that was the only
thing tying a percentage to a dollar figure, Action Center descriptions
truncated to one line (which is the to-do list, cutting exactly the part
that says what to do), a royalties column forcing horizontal scroll while
rendering zero-width, and the valuation multiple selector at 34x23px,
where a mis-tap silently reprices the catalogue.

**Verification:** Jinja if/for and div balance checked on every one of
the eleven files touched; 553 tests green.
