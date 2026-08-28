# Accessibility audit

Scope: the homepage and the four public pages added in this pass
(`/product-tour`, `/product-tour/smart-link`, `/start`,
`/artist-control`).

## Method and its limits

Structural checks were run against the rendered markup of all five pages:
heading order, single `h1`, `alt` on every `<img>`, `lang`, landmark
regions, form labels, table headers and scope. Contrast ratios were
computed from the declared token values. Keyboard order was reasoned from
DOM order, which on these pages is the reading order everywhere except
the closing section, where the picture follows the copy in the DOM and
CSS `order` puts it below on narrow screens — so the tab order and the
visual order agree.

**Not done:** no screen-reader pass with NVDA, JAWS or VoiceOver, and no
axe-core run in a real browser. The browser tooling available in this
environment could not screenshot or drive any page — every attempt timed
out — so nothing here rests on an observed render. Treat the contrast
figures as computed, not measured.

## Results

| Check | Result |
| --- | --- |
| One `h1` per page | Pass, all five |
| Heading levels never skip | Pass, all five |
| `alt` on every image | Pass |
| `lang="en"` | Pass |
| `<main>` landmark | Pass |
| Skip link to `#main` | Pass |
| Decorative overlays hidden | Pass — the closing veil is `aria-hidden="true"` |
| Tables have `<th scope>` and a caption | Pass — the fan-intelligence table |
| Status conveyed by colour alone | None. Every chip carries its word. |
| Visible focus ring | `:focus-visible` with 2px brass and 3px offset on every CTA, tour link and trust link |
| Touch target ≥ 44px | Pass — CTAs are 50–54px; footer links carry `-my-2 py-3.5` on phones |
| `prefers-reduced-motion` | Honoured; all transitions in `closing.css` and `product-tour.css` are disabled |

## Contrast (computed against `#080807`)

| Token | Use | Ratio |
| --- | --- | --- |
| `#EEE8DC` ivory | body copy, headings | 15.6:1 |
| `#C9A86A` brass | eyebrows, links, chips | 7.6:1 |
| `#A7A198` muted | supporting copy | 7.3:1 |
| `#7E786F` | footer meta only | 4.6:1 |
| `#14120E` on `#C9A86A` | primary CTA label | 6.9:1 |

All pass AA for their size. `#7E786F` is used only for the copyright line
and back-links; it clears AA for normal text but is the weakest value on
the page and should not be reused for anything a visitor has to read.

## Known gaps

1. No screen-reader verification (above).
2. The homepage is long — twelve sections. There is a skip link to
   `#main` but no section-level skip navigation. A keyboard user who
   wants the footer traverses everything.
3. The Artist EQ sliders were built earlier in this project; their
   keyboard behaviour is not re-verified here.
