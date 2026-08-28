# Public route map

Every GET route with no path parameter, and what a **signed-out**
visitor gets. Generated against the running application.

## Public — answer 200 anonymously (28)

| Route | Purpose |
| --- | --- |
| `/` | Homepage |
| `/about` | About |
| `/ai` | How the Twin uses AI |
| `/artist-control` | Artist control policy |
| `/artist-twin/start` | Artist Twin entry |
| `/catalog-sweep` | Free catalog sweep intake |
| `/contact` | Contact |
| `/creative-studio` | Creative Studio |
| `/distribution` | Distribution guide |
| `/forgot` | Reset password |
| `/lanes` | Three lanes |
| `/login` | Log in |
| `/metadata` | Metadata Passport |
| `/partners` | Partner network |
| `/plan` | Artist EQ plan, recomputed server-side |
| `/privacy` | Privacy |
| `/product-tour` | Public product tour |
| `/product-tour/smart-link` | Smart Links, Fan Intelligence, artwork proof |
| `/release-check` | Release-readiness check (DISTRIBUTE NOW) |
| `/release-signal` | Release Signal — what it reads, and its status |
| `/rollout` | Rollout Engine |
| `/royalty-sweep` | Royalty Sweep method |
| `/services` | Label services |
| `/signup` | Create account |
| `/start` | Guided starting plan (receives the Artist EQ mix) |
| `/submit` | Music submission |
| `/sw.js` | Service worker |
| `/terms` | Terms |

## Gated — redirect to /login (104)

These need an account by design: they act on the artist's own data.

```
/actions
/admin/review
/ai-rights
/apparel
/artist-profile
/artist-twin
/artwork
/audience
/backup
/beats
/benchmark
/billing
/capital
/capital-score
/catalog
/certified
/command-center
/conflicts
/connections
/dashboard
/deal-room
/deal-room/onesheet
/discover
/disputes
/documents
/epk
/fan-club
/fan-label
/fans
/fraud-sentinel
/funding
/hours
/identifiers
/inbox
/insights
/lights
/links
/links/autofill
/links/fans
/links/fans/export.csv
/links/new
/mail/diag
/marketplace
/mechanicals
/metadata-passport
/metadata-passport/export.csv
/money-queue
/neighboring-rights
/network
/notifications
/onboarding
/opportunities
/overview
/playlists
/portal
/publishing
/pulse
/pulse/search
/qualification
/rack
/rack/studio-split/diag
/recovery
/referrals
/registration
/releases
/releases/autopilot
/releases/autopilot/kit.txt
/releases/calendar.ics
/releases/clean-release
/reports
/reports/campaigns.csv
/reports/executive
/reports/recovery.csv
/reports/royalty-report/download.csv
/revenue-os
/rollout-studio
/rollout-studio/new
/roster
/roster/export.csv
/royalties
/royalty-lanes
/royalty-recovery/cases
/royalty-recovery/mlc
/search
/settings
/spend-optimizer
/stage-plot
/statements
/stats
/sync
/sync/clearance-packs
/sync/deal-simulator
/tax
/team
/territories
/tour
/tour-board
/tracks
/trust-score
/valuation
/vault
/voice-of-fan
/walkthrough
/walkthrough/sample-statement.csv
```

## The rule

A public product-information CTA never lands on a login wall. An account
is asked for at the point where there is something to save, upload,
deliver or claim — never in exchange for finding out what the product is.

`tests/test_closing.py::test_no_homepage_link_sends_a_visitor_into_the_login_wall`
walks the rendered homepage and fails the build if any destination stops
answering 200.

## Naming note

The public tour is at `/product-tour`, not `/tour`. `/tour` is the
signed-in touring pipeline (`/tour/add`, `/tour/<id>`,
`/tour/<id>/status`, `/tour-board`) and taking that path would have
broken five live routes.
