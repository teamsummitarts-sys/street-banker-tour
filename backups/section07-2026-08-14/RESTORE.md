# Section 7 — Creative Studio, as it stood before the portrait

Taken 2026-08-14, immediately before the generated merch-table mockup was
replaced with the owner's portrait. Tag: `pre-section7-photo-2026-08-14`.

## What is here

| Path | What it is |
| --- | --- |
| `img/` | The 12 pre-swap derivatives — `creative-wide-{520,830}` and `creative-close-{400,600}`, each in avif, webp and jpg |
| `creative_config.py` | The old `IMAGE` block, including the merch-table alt text |
| `creative_studio.html` | The section partial as it was |
| `creative-studio.css` | The stylesheet as it was — **the reason this folder exists in this shape** |

The stylesheet matters. The swap changed more than the pictures: the
crop point moved (`object-position` 62% 45% → 50% 6%) and all three veil
gradients were shortened for a high-key frame. Putting the old low-key
photograph back under the new CSS gives you neither look. Restore both or
neither.

## Restore

    git checkout pre-section7-photo-2026-08-14 -- \
        static/img/creative-wide-* static/img/creative-close-* \
        static/css/creative-studio.css creative_config.py \
        templates/partials/creative_studio.html

Then bump `VERSION` in `static/js/sw.js` — the worker serves `/static`
cache-first with no revalidation, and these image URLs carry no `?v=`, so
without a bump every returning visitor keeps whichever picture they
already cached.

Two tests will fail after a restore, and they are supposed to:
`test_the_alt_text_describes_the_picture_and_sells_nothing` pins the
portrait's alt text, and
`test_the_shipped_crops_are_reproducible_from_the_tracked_original`
rebuilds the crops from `incoming/artist-photos/creative-portrait.jpg`
and compares pixels. Restoring the old picture means restoring the old
expectations in `tests/test_creative_studio.py` too.
