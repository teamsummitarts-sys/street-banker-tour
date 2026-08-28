# Current Feature Inventory

Counted from the codebase on 2026-07-31, not from a roadmap.

| | |
|---|---|
| Routes in `app.py` | 280 |
| SQLite tables | 67 |
| Jinja templates | 131 |
| Python modules | 61 |
| Browser JS modules | 11 |
| Tests | 522 |

The five-year directive asks for twelve primary destinations. **All twelve
already exist as routes.** So does the admin review queue, the fan CRM,
the metadata passport, the qualification score and the catalog
opportunity engine. The gap was never the feature list.

## The distinction that actually matters

Every module in this repo falls into one of three groups, and confusing
them is the single biggest risk in the codebase.

### Engines — read the artist's own data

| Module | Reads |
|---|---|
| `statements_engine.py` | uploaded royalty CSVs; totals, coverage gaps, valuation band |
| `capital_engine.py` | statement income, periods, sources → advance band |
| `qualification.py` | links, fans, rollouts, EPK, tracks, **audio, income** |
| `trust_score.py` | splits, metadata, paperwork state |
| `audio_readiness.py` | Rack measurements → loudness, peak, hook rulings |
| `rollout_learning.py` | past rollout variants → per-platform conversion |
| `links_engine.py` | campaign scores, destinations |
| `rollout_engine.py` | campaign shape, assets, post statuses |
| `insights_engine.py` | statements, links, catalog |
| `command_center.py` | smart links, actions, alerts |
| `artist_twin.py` | consented sources only (EPK, catalog, campaigns, fans, lyrics, **rack**) |
| `artist_os.py` | tracks, passports, lockbox, money queue, **master read** |
| `royalty_types.py` | statement rows by type and territory |
| `hours_engine.py` | sessions, invoices, bookings |

**14 engines.** These are the product.

### Config modules — illustrative data, 28 of them

`artist_eq_config`, `artwork_config`, `audience_config`,
`benchmark_config`, `billing_config`, `capital_config`, `catalog_config`,
`community_config`, `connections_config`, `discover_config`,
`disputes_config`, `epk_config`, `funding_config`, `label_config`,
`landing_config`, `links_config`, `mechanicals_config`,
`neighboring_rights_config`, `network_config`, `notifications_config`,
`playlists_config`, `publishing_config`, `reports_config`,
`search_config`, `stats_config`, `sync_config`, `tax_config`,
`territories_config`.

Some are legitimately configuration (`landing_config` holds real
homepage copy). Some hold demo datasets that pages fall back to. **The
ratio of 28 config modules to 14 engines is the honest state of the
product**, and closing that gap is the work.

`territories_config` is the only one no longer imported by `app.py` — it
was feeding a dead module that generated fabricated "money you are not
collecting" figures. See `PRODUCT_GAP_ANALYSIS.md`.

### Providers — real external calls, all env-gated

| Module | Gated on | Degrades to |
|---|---|---|
| `stemsplit_provider.py` | `STEMSPLIT_API_KEY` | Studio Split hidden |
| `email_provider.py` | `RESEND_API_KEY` | no sends, flows still work |
| `stripe_provider.py` | `STRIPE_SECRET_KEY` | checkout disabled |
| `spotify_provider.py` | Spotify OAuth env | Pulse empty |
| `bandsintown_provider.py` | artist id on the EPK | no tour dates |
| `backup_store.py` | `BACKUP_S3_*` | no off-box backup |
| `convert_engine.py` | `ffmpeg` present | WAV/AIFF only, in-browser |

None fabricate a result when absent. Each reports its own state.

## Browser-side DSP

`static/js/` carries genuine signal processing, not UI decoration:

- `loudness.js` — ITU-R BS.1770-4, verified against EBU Tech 3341
  compliance cases
- `tempokey.js` — spectral-flux onsets, autocorrelation tempo,
  Krumhansl-Schmuckler key, WSOLA time-stretch
- `audioconv.js` — WAV/AIFF encoders including 80-bit IEEE extended
- `tubes.js` — six saturation stages, harmonic-measured
- `rackdsp.js` — the rack: 12-band EQ, compressor, cab sim, stem deck

These are the most technically substantial thing in the repo, and until
this session none of their output survived the browser tab.

## Verified real, end to end

- Statement CSV ingestion → recovery findings → recovery cases
- Smart links with click tracking, variants, fan capture
- Rollout Studio with per-post attribution
- The Rack (all DSP above), Studio Split against the live StemSplit API
- Hours desk: sessions, invoices, bookings, clash detection
- Auth, billing, team invites, notifications, vault, backups
