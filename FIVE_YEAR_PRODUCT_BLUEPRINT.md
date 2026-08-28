# Five-Year Product Blueprint

## The premise this corrects

The obvious reading of Street Banker's position is that it needs more
features. That reading is wrong, and the code says so: all twelve primary
destinations the five-year directive asks for **already exist as routes**,
along with the admin review queue, the fan CRM, the metadata passport,
the qualification score and the catalog opportunity engine. 280 routes,
67 tables, 131 templates.

What did not exist was the loop.

An audit traced every place the app computes something real. It found 56
signals and **42 of them severed** — measured properly, then read by
nothing. The Rack implemented ITU-R BS.1770-4 to compliance-case
accuracy and threw the numbers away when the tab closed. Release
Readiness scored campaign setup and artwork counts, so an artist could be
told they were ready to release a master that clips on every platform.
Rollout Studio measured which platform converted and regenerated from
static templates. The press kit an artist sends a label quoted a catalog
value derived from a hardcoded Jan–Jun earnings list identical for every
account.

Adding features to that would have made it worse.

## The moat, stated honestly

**Every competitor can copy a feature. None of them can copy an artist's
accumulated measured history.**

A distributor knows what an artist released. A smart-link company knows
what got clicked. A royalty administrator knows what got paid. Street
Banker is the only place where the master's true peak, the hook
timestamp, the per-platform conversion of the last four rollouts, the
statement income by source and the metadata completeness sit in one
database against one artist.

That is only a moat if the pieces feed each other. Nine severed
connections are now closed:

| Signal | Now reaches |
|---|---|
| Loudness, true peak, dynamic range | Release Readiness, the Twin |
| Tempo, key, confidence | the Twin, pitch documents |
| Hook windows, beat grid | the Twin's master read |
| Short-term / momentary max | delivery-spec ruling |
| Past rollout conversion | next rollout's platform default |
| Statement income | qualification, funding, press kit |
| Statement-derived valuation | the public press kit |
| Recovery case value | queue ordering |
| Advance band | `/funding` |

## Principles the code now enforces

These came out of being wrong, and each has a test behind it.

1. **Absent evidence is not a pass.** An unmeasured master scores zero,
   not a default. A score that quietly assumes the best is not a score.
2. **Only quote what was measured confidently.** A 0.3-confidence tempo
   is hedged, never stated. The confidence figure is retained precisely
   so it can gate the claim.
3. **Every ruling carries its evidence and its threshold**, so a
   disagreeing artist can see exactly what was compared.
4. **Rates, not totals.** The platform with the most clicks is usually
   the one with the most posts.
5. **Refuse to speak on thin evidence.** Under 25 visits, say so and
   stop.
6. **Fewer true numbers beat more invented ones.** An empty press kit
   should look empty, not successful.
7. **Never quote money that is not real.** Fabricated audio measurements
   would embarrass. Fabricated money owed is the one number this product
   cannot get wrong.

## Now

- Persist the scores. `qualification`, `trust_score`, `capital_engine`
  and the valuation all recompute per request and store nothing, so the
  app can say where an artist stands and never whether they are
  improving. A history table turns every score into a trend.
- The remaining mobile findings, including the 48 rack tooltips.
- Verified Resend sending domain.

## Next

- **Rights Graph.** The entities exist across `os_tracks`,
  `catalog_tracks` and `statement_rows` but not as a graph. Contributor →
  work → recording → release → territory → share → claim is what makes
  registration gaps detectable rather than guessable.
- **Royalty Sweep detection depth.** Ingestion and case workflow are
  real; the detection rules are thin. Territory data is captured and
  barely used — income from a country with no local society registration
  is a finding the data already supports.
- **Provenance.** No creation or edit history for generated assets. The
  architecture should exist before generation volume makes it
  impossible to add.

## Later

- Organisation/tenant boundary. Roster works; a real multi-tenant edge
  does not exist.
- Distribution delivery and registration APIs — the largest single
  unlock, and the one most gated on partnerships rather than code.
- Campaign agents that act. The measurement loop has to be trusted before
  anything is allowed to spend money on its own.

## Five-year moat

The compounding asset is **an artist's measured history**, and its value
is a function of how long it has been accumulating and how many decisions
have been fed by it.

That is why the discipline matters more than the feature count. A single
fabricated number poisons the well — an artist who catches one invented
figure is right to distrust every other number on the page, including all
the ones that were carefully measured. The rules above are not
scrupulosity. They are what makes the accumulated history worth
anything.
