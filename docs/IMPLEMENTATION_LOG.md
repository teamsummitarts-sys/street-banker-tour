# Implementation log — Section 12 and the consolidation pass

## Files created

| File | Purpose |
| --- | --- |
| `closing_config.py` | Section 12 copy, the 11.5 trust band, the ten-point policy |
| `tour_config.py` | The twelve tour steps, status vocabulary, smart-link / fan / creative example data |
| `templates/partials/trust_band.html` | 11.5 |
| `templates/partials/closing.html` | Section 12 |
| `templates/product_tour.html` | `/product-tour` |
| `templates/product_tour_smart_link.html` | `/product-tour/smart-link` |
| `templates/start_public.html` | `/start` |
| `templates/artist_control.html` | `/artist-control` |
| `static/css/closing.css` | Trust band + closing frame |
| `static/css/product-tour.css` | Tour, status chips, smart-link card, fan table |
| `static/js/closing.js` | Analytics + carrying the EQ mix into the final CTA |
| `static/img/closing-wide-{960,1440,1672}.{avif,webp,jpg}` | Section 12 desktop |
| `static/img/closing-close-{520,1070}.{avif,webp,jpg}` | Section 12 phone |
| `tests/test_closing.py` | 15 tests |
| `docs/*.md` | These seven documents |

## Files changed

`app.py` — four new public routes, four additions to `_PUBLIC_EXACT`, the
closing config passed to the homepage, and the dead `config["sweep"]`
image guard removed.
`templates/landing.html` — Signature Tools, archive band and old final CTA
removed; trust band and Section 12 included; footer rebuilt dark with five
columns; asset versions bumped.
`templates/base.html` — the app rail is now gated on `user_plan`, with the
public header shown to signed-out visitors.
`templates/services.html` — the store link goes to the store, not to a
login wall, when signed out.
`landing_config.py` — footer rebuilt; header hash links made absolute;
five retired blocks deleted.
`departments_config.py` — six destinations retargeted.
`artist_eq_config.py`, `hubs.py`, `plans.py`, `command_center.py`,
`creative_config.py`, `capital_engine.py`, `rollout_engine.py`,
`rollout_learning.py`, `rollout_store.py`, `social_providers.py`, eight
`templates/rollout_*.html` — `Rollout Studio` → `Rollout Engine`.
`static/js/artist-twin.js` — one event renamed.
`static/js/sw.js` — `sb-v94` → `sb-v95`.
Tailwind rebuilt; `tailwind.css?v=21` → `v=22` across 40 templates.

## Tests

Nine test files carried assertions about the retired sections. All were
repaired to assert the current page rather than deleted:

- `test_app.py` — three tests rewritten (`test_the_footer_carries_the_modules_and_every_link_is_public`,
  `test_the_retired_homepage_blocks_are_gone_from_config_and_page`,
  `test_landing_is_the_twelve_approved_sections_in_order`), two updated,
  one retargeted from "the footer may link into the app" to "nothing may".
- `test_artist_twin.py`, `test_creative_studio.py`, `test_departments.py`,
  `test_distribution.py`, `test_lanes.py`, `test_passport.py`,
  `test_rollout.py`, `test_sweep.py` — the "displaces nothing" tail
  markers updated from the retired closing block to the trust band and
  Section 12.
- `test_public_header.py` — now also asserts every header hash link is
  written `/#name`, which is the bug this pass fixed.
- `test_departments.py` — the "one route that leaves the page" test now
  describes Fan Intelligence, which is the department that does.

Suite before this pass: 792 tests, all green.
Suite after the section landed, before test repair: 18 failures, every one
a stale assertion about markup this pass deliberately removed.
Suite after repair: green — see the final run in the session output.

## What did not get done

1. **No visual verification.** Screenshots time out in this environment
   on every page and have done for the whole project. Nothing in this
   pass has been seen rendered. The six brief widths (375, 430, 768,
   1024, 1280, 1440, 1920) were reasoned from the CSS, not observed.
2. **No screen-reader pass.** Structure was checked; assistive-technology
   behaviour was not.
3. **`/tour` is `/product-tour`.** The brief asked for `/tour`; that path
   is the signed-in touring pipeline and taking it would have broken
   five routes.
4. **`/services` still renders app chrome.** The sidebar is now hidden
   from signed-out visitors, but the page itself is an internal-shaped
   page being used as the public "For Labels" destination. It works and
   nothing on it is a login wall any more, but it was not redesigned.
5. **No lint step exists in this repo** — there is no configured linter
   (no ruff, flake8 or eslint config). Nothing was skipped; there was
   nothing to run. Tests and the production Tailwind build were run.
