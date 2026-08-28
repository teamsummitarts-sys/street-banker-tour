# Performance audit

Measured against the rendered homepage. **No Lighthouse run and no field
data**: nothing in this environment can render a page, so every figure
here is a static property of the document rather than an observed
metric. Treat it as an inventory, not a score.

## Document

| Measure | Value |
| --- | --- |
| Homepage HTML, uncompressed | 130 KB |
| Distinct static assets referenced | 163 |
| Total bytes of all srcset variants | 8821 KB |
| `<picture>` elements | 11 |
| `<img>` elements | 14 |
| Images with AVIF + WebP + JPEG | all |
| Images with intrinsic width/height | 13 of 14 |
| Lazy-loaded images | 10 of 14 |
| Blocking stylesheets | 15 |
| Deferred scripts | 11 |
| Third-party requests | 0 |
| Animation libraries | 0 |

The total-bytes figure is the sum of **every** variant. A browser picks
one per image, so a real page load is a fraction of it — but the number
is worth watching because it is what a cold service-worker precache
would cost if anyone added these to it. It is derived, not hand-kept:
sum the file behind every distinct `/static` image URL in the rendered
homepage's `src` and `srcset`. Recompute it whenever a photograph is
replaced. Last moved 2026-08-14, when the real hero and Section 7
photographs replaced generated frames and took 412 KB out with them.

## What is already right

- Only the hero is eager; it is the LCP element. Everything else is lazy.
- Every image declares intrinsic dimensions, so the box is reserved
  before bytes arrive and no photograph shifts the page.
- AVIF and WebP with JPEG fallback at every width.
- Separate mobile crops rather than a desktop asset scaled down, so a
  phone never downloads a 1672px frame.
- No framework, no animation library, no third-party script, no web font.
- Every section renders completely with JavaScript disabled; the scripts
  add measurement and interaction, and remove nothing when absent.
- Collapsed content is inert markup, not a deferred fetch — opening a
  disclosure costs nothing.

## The one real problem

**15 blocking stylesheets in the critical path.** Each section owns its
own sheet, which is good for authoring and bad for first paint. They are
individually small and HTTP/2 multiplexes them, so it is tolerable — but
concatenating them at build time is the single largest first-paint win
available on this page and it is a build-step change, not a rewrite.

## Not measured

- Largest Contentful Paint, Cumulative Layout Shift, Interaction to Next
  Paint — all need a browser.
- Real-world transfer sizes after compression.
- Service-worker cache hit rate.

Service worker is at `sb-v96`; asset query strings are bumped in step so
a cache-first worker cannot serve a stale stylesheet.
