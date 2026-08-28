# Data Model

67 SQLite tables. `db.py` is the only module that touches the database;
everything else goes through its accessors.

## Conventions

- **IDs** are `uuid4().hex` strings, not integers.
- **Timestamps** are ISO-8601 strings via `_now()`.
- **Ownership** is a `user_id` column on nearly every table. There is no
  organisation layer yet — the roster/label features hang off
  `roster_members` rather than a separate tenant table.
- **JSON blobs** carry the shapes that change often: `passport`,
  `lockbox`, `data`, `settings`. Anything queried or aggregated is a real
  column.
- **Migrations** are `ALTER TABLE ... ADD COLUMN` in `init_db()`, each
  wrapped in `try/except sqlite3.OperationalError`. `CREATE TABLE IF NOT
  EXISTS` does **not** add columns to an existing table — a lesson learned
  the hard way when `track_analysis` gained hook columns and would have
  raised "no such column" on every existing install.

## Groups

### Identity and access
`users`, `team_members`, `sign_tokens`, `ingest_tokens`, `api_cache`,
`app_kv`

### Money — the spine
`statements`, `statement_rows`, `recovery_cases`, `revenue_expenses`,
`disputes`, `deals`

`statement_rows` is the trunk everything financial hangs off: title,
source, amount, period, territory. It is read by `capital_engine`,
`insights_engine`, `royalty_types`, `qualification`, the tax centre, the
roster, the portal, the CSV export **and now the public press kit and the
funding page.** More consumers than any other table, and correctly so.

### Catalog and rights
`catalog_tracks`, `os_tracks` (passport + lockbox JSON), `documents`,
`vault_files`, `sync_packs`

### Audio measurement
`track_analysis` — one row per measured file. Loudness (`integrated`,
`lra`, `true_peak`, `sample_peak`, `short_term_max`, `momentary_max`),
tempo and key with confidence, hook windows (`hook_15s`, `hook_30s`),
beat grid (`first_beat`, `bar_seconds`, `grid_confidence`), plus format
facts and the engine string.

Added this session. Before it, every one of these numbers was computed to
a published standard and then discarded when the tab closed.

### Links, campaigns, fans
`ml_campaigns`, `ml_destinations`, `ml_variants`, `ml_events`, `ml_fans`,
`ml_consents`, `smart_links`, `link_clicks`

`ml_variants` deserves a note. Rollout posts create one variant each,
named `rollout_{platform}_{phase}_{date}` with `utm_source={platform}`.
`ro_posts` is cleared on every regenerate — **`ml_variants` is not.** That
accident of design is why per-platform conversion history survives back
to an account's first rollout, and why `rollout_learning` needed no
migration.

### Rollout
`ro_campaigns`, `ro_assets`, `ro_posts`

### Audience-facing
`epk_profiles`, `epk_assets`, `epk_shares`, `epk_share_events`,
`onesheet_shares`, `onesheet_views`, `fan_clubs`, `club_members`,
`club_drops`

### Touring
`tour_shows`, `stage_plots`, `tour_board`, `tour_board_replies`

TOUR (tour_store.py) groups shows into tours and adds what a tour runs
on. `tour_shows` stays the Show entity and gains `tour_id` + `tz`;
everything else TOUR knows about a show lives in `tour_show_ext`
(promoter, capacity, tickets, guest allocation/cutoff, deal and money
fields, marketing JSON). Then: `tours`, `tour_members` (invite lifecycle
+ scopes JSON), `tour_days`, `tour_schedule`, `tour_venues` (per
account, reused across tours), `tour_advance` (one row per checklist
item per show), `tour_travel`, `tour_lodging`, `tour_rooms`,
`tour_people`, `tour_guests`, `tour_vip`, `tour_files` (private
`tour:` paths or R2 `tour/`, never `/uploads/`), `tour_expenses`,
`tour_merch_products`, `tour_merch_counts`, `tour_content`,
`tour_setlists` + `tour_setlist_items` (`os_track_id` links the
catalog), `tour_changes` + `tour_acks` (before/after, severity, who
acknowledged), `tour_share_links` (token, scope, show, password hash,
expiry, revoked, access count), `tour_imports`, `tour_fan_captures`.
Every row carries the tour OWNER's `user_id`; membership and scopes are
enforced in tour_os.py, never in the store.

### Studio
`rack_presets`, `light_shows`

### Hours desk
`hours_rates`, `hours_entries`, `hours_invoices`, `hours_bookings`,
`hours_submissions`, `hours_blocks`

### Network
`collab_requests`, `collab_replies`, `collab_saves`, `outreach_items`,
`roster_members`

### Platform
`notifications`, `street_actions`, `twin_settings`, `twin_generations`,
`pulse_profiles`, `pulse_snapshots`, `pulse_peers`,
`pulse_peer_snapshots`, `spotify_presaves`, `artist_signal_profiles`,
`inbox`

## Against the directive's entity list

Most of its ~40 entities map onto existing tables. The genuine absences:

| Missing | Consequence |
|---|---|
| `Organization` / tenant | roster works, but there is no true multi-tenant boundary |
| `ProvenanceRecord` | no creation/edit history for generated assets |
| `ConsentRecord` for AI | `ml_consents` covers fans, not likeness or voice |
| `AuditLog` | no general action log; `street_actions` is closest |
| `Experiment` | variants exist; formal A/B records do not |
| `ArtistScore` history | scores recompute per request and are never stored, so no trend |

That last one recurs. `qualification`, `trust_score`, `capital_engine`
and the catalog valuation all compute per request and persist nothing —
so the app can tell an artist where they stand today and never whether
they are improving.
