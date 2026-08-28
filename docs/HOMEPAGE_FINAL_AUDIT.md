# Homepage final audit

The state of the Street Banker homepage after Section 12 and the
consolidation pass.

## The page

| # | Section | Owns | Anchor |
| --- | --- | --- | --- |
| 1 | Header | `landing_config.nav` | — |
| 2 | Hero | `landing_config.hero` | `sbhero` |
| 3 | Artist EQ | `artist_eq_config.py` | `artist-eq` |
| 4 | One System, Six Departments | `departments_config.py` | `departments` |
| 5 | AI Artist Twin | `artist_twin_config.py` | `artist-twin-section` |
| 6 | Three Street Banker Lanes | `lanes_config.py` | `lanes` |
| 7 | Creative Studio | `creative_config.py` | `creative-studio` |
| 8 | Rollout Engine | `rollout_config.py` | `rollout-engine` |
| 9 | Royalty Sweep | `sweep_config.py` | `royalty-sweep-section` |
| 10 | Global Distribution | `distro_config.py` | `global-distribution` |
| 11 | Metadata Passport + Rights | `passport_config.py` | `metadata-passport` |
| 11.5 | Trust band | `closing_config.BAND` | `artist-control` |
| 12 | Closing statement | `closing_config.py` | `closing` |
| — | Footer | `landing_config.footer` | — |

Order is asserted by position in
`tests/test_app.py::test_landing_is_the_twelve_approved_sections_in_order`,
so a future section cannot be inserted in the wrong place silently.

## What this pass changed

### Removed
- **Signature Tools strip.** Five module cards whose five links all went
  into the login wall. The footer's Platform column names the modules
  instead, publicly.
- **Archive-shelf band and the old final CTA** ("YOUR MUSIC IS THE
  PRODUCT." / "START FREE"). Section 12 says the same thing better, over
  a photograph, with a CTA that goes somewhere a stranger can use.
- **Dead config.** `landing_config` no longer carries `tools`,
  `final_cta`, `band_image`, `lanes` or `sweep` — all five had been
  superseded by their own section modules and were still being maintained
  as though rendered. That file now holds only the header, hero and
  footer.

### Added
- **11.5 trust band** — four columns gathering the promises the page
  makes elsewhere, linking to a public policy page.
- **Section 12** — the closing frame, two sentences, two CTAs, one
  photograph used unaltered.
- **`/start`** — the guided starting plan, public, which receives the
  Artist EQ mix carried down from the top of the page.
- **`/artist-control`** — the ten-point policy, public.
- **`/product-tour`** and **`/product-tour/smart-link`** — the twelve-step
  tour and the Smart Links / Fan Intelligence / artwork-generator proof.

### Repaired
- Every footer link (seven were login walls).
- Every header hash link (all were relative and dead on the ten public
  pages that are not the homepage).
- Three department destinations pointing at retired anchors.
- The app rail rendering to signed-out visitors on `/services`, where
  roughly seventy sidebar links each answered with a login redirect.
- Generic social URLs (`x.com`, `youtube.com`, `linkedin.com`) removed.
- `Rollout Studio` renamed to `Rollout Engine` across 14 modules,
  templates and tests.
- Analytics event `artist_twin_see_how_it_thinks` renamed
  `artist_twin_reasoning_opened` to match the `<subject>_<verb>` pattern
  every other event follows.
- Footer logo given intrinsic dimensions (it was the one image on the
  page that could shift layout).

## Honesty position

No testimonials, client names, partner logos, artist counts, stream
counts, recovery totals, country counts, earnings, accuracy percentages
or "trusted by" claims appear anywhere on the homepage or the new public
pages. None of those exist to report.

Every figure on the page is either computed from a real input or labelled
an example. Every example is labelled in words, not only by colour. The
metadata completeness score is named for completion, not prediction. The
distribution claims were audited against `label_config.py` in the Section
10 pass and eight unsupported statements were removed then; nothing in
this pass reintroduced any of them.

`tests/test_closing.py::test_closing_carries_no_numbers_or_claims` fails
the build if a figure or a guarantee appears in the closing frame.

## Verification status

- **Automated:** full suite green (see IMPLEMENTATION_LOG.md), plus new
  route-map, anchor, naming and status-vocabulary tests.
- **Visual:** none. Every browser screenshot attempt in this environment
  timed out, across the whole project. Layout was reasoned from CSS and
  verified structurally; nobody has looked at the rendered page. That is
  the single biggest open risk and a human should walk the six test
  widths before this is called finished.
