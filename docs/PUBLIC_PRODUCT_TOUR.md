# Public product tour

**Route:** `/product-tour` — not `/tour`. `/tour` is the signed-in
touring pipeline (`/tour/add`, `/tour/<id>`, `/tour/<id>/status`,
`/tour-board`) and taking that path would have broken it.

**Content:** `tour_config.py` · **Templates:**
`templates/product_tour.html`, `templates/product_tour_smart_link.html` ·
**Styles:** `static/css/product-tour.css`

## What it is

Twelve steps through one example artist's release, in the order the work
actually happens. Every step names its module, carries a capability
status chip, says in one sentence what the module does *and* what it does
not do, and links to the public page for that module. Nothing on the tour
asks for an account — a visitor is meant to be able to decide against
Street Banker from here without ever signing in.

| # | Module | Step | Status | Links to |
| --- | --- | --- | --- | --- |
| 01 | Artist EQ | The artist sets their priorities | Live | `/plan` |
| 02 | AI Artist Twin | The Twin reads the release | Example | `/artist-twin/start` |
| 03 | Metadata Passport | The release gets organised | Live | `/metadata` |
| 04 | Creative Studio | The artwork and the campaign assets | Live | `/creative-studio` |
| 05 | Rollout Engine | The campaign gets built | Integration ready | `/rollout` |
| 06 | Smart Links | The release gets one door | Live | `/product-tour/smart-link` |
| 07 | Fan Intelligence | The response gets attributed | Example | `…/smart-link#fans` |
| 08 | Global Distribution | The package gets prepared | Partner delivered | `/distribution` |
| 09 | Rights & Ownership | The splits get confirmed | Live | `/metadata#used` |
| 10 | Royalty Sweep | A gap gets found | Example | `/royalty-sweep` |
| 11 | Street Banker | The next move gets recommended | Live | `/start` |
| 12 | Three Lanes | The artist picks a lane | Live | `/lanes` |

The tour opens with a key explaining all six status labels, so a visitor
knows what the chips mean before reading a single one.

## The smart-link page

`/product-tour/smart-link` carries three proofs the homepage claims but
had no public evidence for:

**Smart Links.** An example release page shaped like the real thing —
artwork panel, artist, title, pre-save state, and a stack of streaming
destinations. The destinations are chipped *Integration ready*: the
interface exists, and on this example page they are not wired to a
platform. Email capture and consent recording are *Live*; SMS capture and
QR codes are *Coming soon*.

**Fan Intelligence.** Six signals with an example reading each, under the
positioning line "Own the relationship, not just the stream." Every
reading begins with the word "Example" — enforced by a test — and the
trust statement is stated plainly: *fan information is collected only
with consent and remains controlled by the artist*.

**Creative Studio artwork generator.** The five-step workflow (brief →
directions → revision → approval → adaptation), the eleven output types
with a status each, and the brand-memory panel with its five states. Two
outputs are honestly marked *Coming soon*: motion/video assets and
print-ready separations.

## Where it is linked from

Header nav (all public pages) · Section 12 "Explore the platform" ·
footer, Platform column · `/start` · the Fan Intelligence department card
in Section 4, which points at the fan workspace because there is no Fan
Intelligence section on the homepage.

## What is deliberately absent

No testimonials, no client names, no logos, no artist counts, no recovery
totals, no country counts, no accuracy percentages, no "trusted by". None
of that exists to report, so none of it appears.
