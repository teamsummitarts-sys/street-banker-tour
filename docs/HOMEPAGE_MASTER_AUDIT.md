# Homepage master audit

State of the Street Banker public experience after the coordinated
implementation pass. Every number here was measured against the running
application, not estimated.

## What was found and fixed

### Public code leaks — 5 found, 5 fixed

| Where | Leak | Cause |
| --- | --- | --- |
| `/product-tour/smart-link` | `<built-in method copy of dict object at 0x…>` × 2 | `FAN_PANEL["copy"]` and `BRAND_MEMORY["copy"]` read as `fi.copy` / `brand.copy` |
| `clean_release.html` | built-in method rendered into a `data-cats` attribute | `cat_nodes["keys"]` read as `n.keys` |
| `artist_eq_config` | latent | `preset["values"]`, `lane["keys"]` |
| `rollout_config` | latent | `SAMPLE["items"]` |
| `search_config` | latent | `groups[]["items"]` |

Jinja resolves `thing.copy` to the dict's built-in method before it looks
for the key. The `clean_release` one was live and silently broke the
hover-highlight the attribute fed — nothing errored, the feature just
stopped working.

Guarded by `tests/test_no_object_leaks.py`: 25 public routes are walked
for rendered object strings, and a second test fails if any config
introduces a key named `copy`, `items`, `keys`, `values`, `get`, `pop`,
`update`, `clear`, `setdefault`, `fromkeys` or `popitem`.

### Routes — 4 classes of failure

1. **Footer pages that did not exist.** About → `/services` (label
   services), Contact → `/submit` (the A&R form), Partner Network →
   `/network` (login wall). Three real public pages now exist.
2. **Duplicate CTA destinations.** `DISTRIBUTE NOW` and `VIEW
   DISTRIBUTION GUIDE` both pointed at `/distribution`, making the
   primary CTA a no-op. The first now opens `/release-check`.
3. **Relative hash links in the shared header.** Every nav anchor was
   written `#platform` rather than `/#platform`, so on the ten public
   pages that are not the homepage the entire navigation scrolled
   nowhere.
4. **App chrome served to signed-out visitors.** `/services` rendered the
   signed-in sidebar — roughly seventy links, every one a login redirect.

### Unsupported claims — 6 removed

- "the single most common reason money sits uncollected" (4 files) →
  "Incomplete or unsigned splits are a common reason royalty income
  becomes delayed or difficult to reconcile."
- "free community image model" → "current image-generation provider"
- "Royalty lanes claimed on all sources" → "Royalty source coverage
  reviewed"
- "Statements read and reported back to you" → "Uploaded and
  partner-provided statements organized in one place"

Swept for: guaranteed, first ever, number one, most common, every
platform, all sources, 100%, instant, real time, always, complete
recovery, viral probability, 200+, no hidden fees, cancel anytime. Zero
remain on any public route.

### Naming and spelling

`Rollout Studio` → `Rollout Engine` across 17 modules, templates and
tests. 31 British spellings standardized to American English across
public copy (organize, color, judgment, catalog, analyze, license).
Zero remain on public routes.

### Capability status

Previously written out independently on the homepage, the product tour
and each product page, with nothing failing when they disagreed. Now one
module, `capability_status.py`, with six statuses and no others.

Three capabilities resolve **against the running deployment** rather than
being asserted:

| Capability | Probe | True | False |
| --- | --- | --- | --- |
| Spotify pre-save | `SPOTIFY_CLIENT_ID` + `SECRET` | Live | Integration ready |
| Release-day email | `RESEND_API_KEY` | Live | Integration ready |
| Billing | `STRIPE_SECRET_KEY` | Live | Coming soon |

**This resolved the Spotify ambiguity.** The OAuth flow, token storage
and release-day save are all implemented but every one is gated on
credentials. A hardcoded "Live" becomes false the moment a key is
missing. The privacy page's claim that pre-save tokens are encrypted at
rest is now conditional on those credentials actually being present —
with them unset it says instead that no Spotify token is requested,
stored or processed.

## Measurements

| Metric | Before | After |
| --- | --- | --- |
| Visible homepage words | 1691 | 1589 (−6.0%) |
| Public routes answering 200 anonymously | 24 | 31 |
| Object-string leaks on public pages | 2 live, 3 latent | 0 |
| Footer links into the login wall | 7 of 15 | 0 |
| Unsupported claims | 6 | 0 |
| Horizontal-overflow sources on mobile | 3 (lanes rack, departments strip, creative labels) | 0 |

Visible-word counting excludes closed `<details>`, `[hidden]` elements
and the eight visually-hidden classes discovered from the stylesheets —
see `tools/visible_words.py`. Counting the screen-reader fallbacks would
have inflated the figure by roughly 20%.

## Known gaps

See `HOMEPAGE_IMPLEMENTATION_LOG.md` for the phase-by-phase account of
what landed and what did not. The three that matter most:

1. **Nothing has been seen rendered.** Browser screenshots time out in
   this environment and have for the whole project.
2. **Visible-word reduction reached 6%, not 35–45%.** The deep blocks the
   brief lists were largely already collapsed before this pass, and the
   remaining visible text is the approved copy the same brief specifies.
   Hitting the number means deleting copy Phase 2 mandates.
3. **Static overflow analysis, not a rendered measurement.** The
   overflow tests check the causes in CSS, not `scrollWidth` in a
   browser.
