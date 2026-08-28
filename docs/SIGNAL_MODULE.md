# Street Banker Signal (`/signal`)

A&R, distribution, rights and contact intelligence. Signal finds movement,
weighs whether it is real, reads the infrastructure behind it, and hands a
sourced case to the **Operator Desk** — which already existed and was not
rebuilt.

> Signal ranks, flags, compares and explains. It does not sign artists, send
> offers, or contact anyone, and it does not replace A&R judgement, legal
> counsel or a royalty professional.

## Stack ruling

The originating brief specified React / Next.js / PostgreSQL / Prisma /
TypeScript. That stack **does not apply here**, on the brief's own instruction
to prefer the existing one. This app is Flask + Jinja2 + SQLite with
hand-written SQL, no ORM, no build step and no npm. TypeScript interfaces
became Python base classes; Prisma models became `CREATE TABLE IF NOT EXISTS`;
React pages became server-rendered Jinja templates. No dependency was added —
`requirements.txt` is unchanged.

## Files

| File | Role |
| --- | --- |
| `signal_hub.py` | Blueprint, routes, access guard, Operator Desk hand-off. |
| `signal_store.py` | Schema and accessors. Nothing else touches SQL. |
| `signal_scoring.py` | Pure scoring — no I/O, so it is testable headlessly. |
| `signal_providers.py` | Adapter interface, real adapter declarations, mock, registry. |
| `signal_ingest.py` | Pull, normalise, record evidence, score, evaluate alerts. |
| `templates/signal/*` | Standalone shell (`_shell.html`), one file per page. |
| `static/css/signal.css` | Hand-written `sg-*` (the Tailwind build is frozen). |
| `tests/test_signal.py` | Access, tenancy, providers, scoring, evidence, end-to-end. |

### Why `signal_hub.py` and not `signal.py`

The repo root is on `sys.path` under both gunicorn and pytest. A module named
`signal` there **shadows the standard library's `signal`**, which gunicorn's
arbiter and Werkzeug's reloader both import at startup — it would break the
production boot and the entire test session. The blueprint is still named
`signal` and still serves `/signal`.

## Access

Composes with what the app already has rather than replacing it:

* the global `before_request` login wall already covers `/signal/*`;
* `/signal` is in neither `plans._ARTIST_PATHS` nor `_PRO_PATHS`, so it is not
  plan-gated;
* a seat is a row in `signal_members`. It is seeded two ways — the app's
  existing `OWNER_EMAILS` predicate enrols an owner on first sight, and any
  active Operator Desk seat is mirrored in with a mapped role
  (`owner→owner, admin→admin, member→scout, viewer→viewer`).

**No person's name appears anywhere in the module**, and a test enforces it.
Roles: Owner, Admin, A&R Executive, Scout, Analyst, Deal Team, Viewer, with a
`PERMS` matrix the decorator and the templates both read. The decorator is the
boundary; a hidden button is only cosmetic.

## Tenancy boundary

Two layers, and the split is deliberate:

* **Shared intelligence** — `signal_artists`, `signal_releases`,
  `signal_metrics`, `signal_city_metrics`, `signal_evidence`, `signal_scores`.
  Derived from public/provider data, owned by no customer, so **no
  `organization_id`**. This is the layer Street Banker owns and improves.
* **Tenant-owned** — `signal_watchlists`, `signal_watch_items`,
  `signal_mandates`, `signal_alert_rules`, `signal_alerts`,
  `signal_desk_links`. Anything that reveals what a customer is *doing*.
  Every one carries `organization_id` and every query filters on it.

The rule: **if a row would tell you a competitor's strategy, it is
tenant-owned.** Cross-tenant ids are refused, not silently honoured — covered
by `test_one_organisation_never_sees_another_s_work`.

## Providers

`MusicIntelligenceProvider` is the only thing Signal talks to. Adapters
declare `capabilities`; the registry picks a preferred provider **per
capability**, so one vendor can serve city movement and another playlists.
Shipped: Soundcharts, Chartmetric, MusicBrainz, The MLC, SoundExchange,
Spotify metadata, public web research, internal Street Banker — each declared,
each inert until its env vars exist — plus a deterministic mock.

Rules that matter:

* An unimplemented capability **raises**; it never returns a plausible guess.
  A fabricated distributor or manager is worse than a blank one.
* A provider that fails is caught, recorded in `signal_provider_runs`, and
  skipped. A broken vendor degrades the product; it never takes a page down.
* With nothing configured the product runs in **demo mode** on a fictional
  universe and says so on every screen.

## Evidence before assertion

Signal never states a distributor, manager or rights status as bare fact.
Every claim lands in `signal_evidence` with source type, label, URL, excerpt,
confidence, first-seen, last-verified and a status drawn from
`EVIDENCE_STATUSES`. Absence of a public record is `potential_gap` — never
"unregistered". A human can overrule the machine
(`manually_confirmed` / `manually_rejected`), and a later automatic pass will
not silently undo that judgement.

## Scoring

`SCORE_VERSION` is stored with every value and history is never overwritten,
so "what did we know at the time" stays answerable. Every score returns its
feature contributions, weights, cohort and what data was missing — a number
with no explanation is not shippable, and every score in the UI links to its
own explanation page.

Cohorts are career stage × audience band × genre: a developing act is never
compared to a superstar. **Missing inputs are named and the remaining weights
renormalised** — they never become a zero that reads as a fact.

Scores: SB Momentum (with an anomaly penalty, capped at 25 and always
itemised), Momentum Quality, Playlist Dependency Risk, Distribution Gap,
Rights Health, Contact Confidence, Deal Readiness.

## No job system

There is no scheduler, worker or queue in this app. Phase 1 does what the
codebase already does for periodic work (`board.py::_sweep_renewals`): a
bounded sweep on a request. `ensure_universe()` fills an empty universe once;
`sweep()` refreshes at most `SWEEP_ARTIST_BUDGET` stale artists and evaluates
that org's alert rules. Opening a page never turns into a hundred provider
calls.

## Operator Desk hand-off

`POST /signal/artist/<id>/operator-desk` finds or creates the lead in the
**existing** `desk_*` tables, attaches the exact intelligence snapshot and
score version, writes a first note and a follow-up task, and starts watching.
`desk_store` takes an actor **dict**, so the real Desk seat is looked up by
email and the Desk's own activity log attributes the action correctly.
Pushing twice does not create a second lead.

The preserved snapshot is what makes "was Signal right?" answerable later.

## Not built yet (phase two and beyond)

Release Reaction, Business Change Signals, the relationship graph and warm-intro
finder, roster intelligence and Roster Fit, Investability, the Provider
Comparison Lab, the Signal Accuracy dashboard, private audio, and email/Slack
alert delivery. `Ask Signal` parses deterministically today and **names the
filters it cannot support** rather than dropping them quietly.

## Endpoints

`GET /signal` · `/signal/breaking` · `/signal/early` · `/signal/cities` ·
`/signal/undervalued` · `/signal/deal-ready` · `/signal/ask` ·
`/signal/watchlists` · `/signal/mandates` (+ `/<id>`, `/<id>/delete`) ·
`/signal/alerts` (+ `/rules`, `/rules/<id>/delete`) · `/signal/team` ·
`/signal/artist/<id>` (+ `/score/<key>`, `/watch`, `/operator-desk`) ·
`/signal/admin/data-sources` (+ `/refresh`) · `/signal/export/board.csv`.
