# CTA route map

Every destination reachable from the Street Banker homepage, and what a
**signed-out** visitor gets. Generated against the running application.

## The rule

A public product-information CTA never lands on a login wall. An account
is asked for at the point where there is something to save, upload,
deliver or claim — never in exchange for finding out what the product is.

`tests/test_closing.py::test_no_homepage_link_sends_a_visitor_into_the_login_wall`
fails the build if any of these stops answering 200.

## Every homepage destination (55)

| Destination | Response | |
| --- | --- | --- |
| `#artist-twin-section` | anchor | ok |
| `#creative-studio` | anchor | ok |
| `#main` | anchor | ok |
| `#metadata-passport` | anchor | ok |
| `#rollout-engine` | anchor | ok |
| `#royalty-sweep-section` | anchor | ok |
| `/` | 200 | ok |
| `/#artist-twin-section` | 200 | ok |
| `/#creative-studio` | 200 | ok |
| `/#metadata-passport` | 200 | ok |
| `/#platform` | 200 | ok |
| `/#rollout-engine` | 200 | ok |
| `/#royalty-sweep` | 200 | ok |
| `/about` | 200 | ok |
| `/ai` | 200 | ok |
| `/artist-control` | 200 | ok |
| `/artist-control#data-ownership` | 200 | ok |
| `/artist-control#security` | 200 | ok |
| `/artist-twin/start` | 200 | ok |
| `/catalog-sweep` | 200 | ok |
| `/contact` | 200 | ok |
| `/creative-studio` | 200 | ok |
| `/distribution` | 200 | ok |
| `/distribution#guide` | 200 | ok |
| `/lanes` | 200 | ok |
| `/lanes#development` | 200 | ok |
| `/lanes#partnership` | 200 | ok |
| `/login` | 200 | ok |
| `/metadata` | 200 | ok |
| `/metadata#used` | 200 | ok |
| `/partners` | 200 | ok |
| `/plan?release=10&amp;creative=8&amp;audience=8&amp;rights=7&amp;revenue=5&amp;growth=6&amp;preset=releasing-soon` | 200 | ok |
| `/plan?release=10&amp;creative=8&amp;audience=8&amp;rights=7&amp;revenue=5&amp;growth=6&amp;preset=releasing-soon#artwork-generator` | 200 | ok |
| `/plan?release=10&amp;creative=8&amp;audience=8&amp;rights=7&amp;revenue=5&amp;growth=6&amp;preset=releasing-soon#creative-studio` | 200 | ok |
| `/plan?release=10&amp;creative=8&amp;audience=8&amp;rights=7&amp;revenue=5&amp;growth=6&amp;preset=releasing-soon#fan-intelligence` | 200 | ok |
| `/plan?release=10&amp;creative=8&amp;audience=8&amp;rights=7&amp;revenue=5&amp;growth=6&amp;preset=releasing-soon#metadata-passport` | 200 | ok |
| `/plan?release=10&amp;creative=8&amp;audience=8&amp;rights=7&amp;revenue=5&amp;growth=6&amp;preset=releasing-soon#rights-ownership` | 200 | ok |
| `/plan?release=10&amp;creative=8&amp;audience=8&amp;rights=7&amp;revenue=5&amp;growth=6&amp;preset=releasing-soon#rollout-studio` | 200 | ok |
| `/plan?release=10&amp;creative=8&amp;audience=8&amp;rights=7&amp;revenue=5&amp;growth=6&amp;preset=releasing-soon#smart-links` | 200 | ok |
| `/privacy` | 200 | ok |
| `/product-tour` | 200 | ok |
| `/product-tour/smart-link` | 200 | ok |
| `/product-tour/smart-link#fans` | 200 | ok |
| `/release-check` | 200 | ok |
| `/release-signal` | 200 | ok |
| `/rollout` | 200 | ok |
| `/royalty-sweep` | 200 | ok |
| `/royalty-sweep#how` | 200 | ok |
| `/services` | 200 | ok |
| `/services/distribution` | 200 | ok |
| `/signup` | 200 | ok |
| `/start` | 200 | ok |
| `/submit` | 200 | ok |
| `/terms` | 200 | ok |
| `https://instagram.com/summitartsgroup` | external | — |

**Problems: 0**

## Fixed in this pass

| Was | Problem | Now |
| --- | --- | --- |
| `DISTRIBUTE NOW` → `/distribution` | Same destination as the guide button, so the primary CTA did nothing | `/release-check` |
| `Start a release` → `/distribution` | Did not start a release | `/release-check` |
| Lane CTAs → `/lanes#<lane>` | Three anchors on one page; said "Explore" rather than what happens | `/release-check`, `/start`, `/lanes#partnership` |
| Hero `Explore Street Banker` → `#platform` | Scrolled down the same page | `/product-tour` |
| Header nav `#platform` etc. | Relative, so dead on the ten public pages that are not the homepage | `/#platform` |
| Footer About → `/services` | Label services, not About | `/about` |
| Footer Contact → `/submit` | The A&R form, not Contact | `/contact` |
| Footer Partner Network → `/network` | Login wall | `/partners` |
| Footer `/overview` `/recovery` `/roster` `/audience` `/capital` | Login walls | Public equivalents |
| Departments → `#artist-twin` `#creative-rollout` `#tools` | Anchors of a retired section | Real section ids |
