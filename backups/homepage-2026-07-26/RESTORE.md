# Homepage backup — approved 2026-07-26

This folder is a complete, self-contained snapshot of the Street Banker
homepage as approved. If the homepage is ever changed and you want this
version back, everything you need is here.

## What's in this folder

| File | What it is |
|---|---|
| `COPY.md` | Every word on the page, in order, with links — including which words live inside the artwork vs. in the HTML |
| `landing_config.py` | All homepage content: headlines, buttons, links, image wiring |
| `templates/landing.html` | Page structure and section order |
| `templates/landing/_home.html` | The image/button/card macros |
| `templates/landing/_cards.html`, `hero_recovery.html` | Supporting macros |
| `static/img/sb-*.jpg` | The five artworks, recut to uniform margins |
| `static/img/streetbanker-logo-dark.svg` | Header + footer logo |
| `rendered-homepage.html` | The live page's HTML exactly as served on this date |

## Restore — pick either method

**Method 1 — git tag (cleanest).** The exact state is tagged in the repo:

```bash
git checkout homepage-approved-2026-07-26 -- landing_config.py templates/landing.html templates/landing static/img/sb-hero.jpg static/img/sb-engines.jpg static/img/sb-distro-lanes.jpg static/img/sb-ownership.jpg static/img/sb-patchbay.jpg
```

**Method 2 — copy from this folder.** From the repo root:

```bash
cp backups/homepage-2026-07-26/landing_config.py . && cp -r backups/homepage-2026-07-26/templates/. templates/ && cp backups/homepage-2026-07-26/static/img/*.jpg static/img/
```

After either method: bump `VERSION` in `static/js/sw.js` (it's at `sb-v16`
— go to `sb-v17`) and bump the `?v=3` cache-busters in `landing_config.py`
to `?v=4`. Without this, phones keep showing the cached old version.

## The page, top to bottom

1. **Header** — logo + ARTIST INFRASTRUCTURE tagline, Login only
   (centered as a column on phones, logo-left/actions-right on desktop)
2. **Hero** — RELEASE MUSIC. BUILD EQUITY. + three buttons
3. **Engines** — ONE PLATFORM. MULTIPLE ENGINES., six clickable panels
4. **Three Distro Lanes** — three clickable rack units + Explore button
5. **Ownership** — FROM RELEASE TO OWNERSHIP. + two buttons
6. **Royalty Sweep** — THE RECOVERY ENGINE text over the patchbay artwork
7. **Services strip** — five deep links
8. **Footer**

## Design rules this version follows

- **Nothing is said twice.** Every benefit appears exactly once. Where
  artwork carries a headline or label, the HTML does not repeat it.
- **No placeholder content.** No invented client names, no sample
  avatars, no AI-generated images. All five artworks are the owner's.
- **Artwork is navigation.** Panels and rack units are invisible
  clickable regions; mobile adds text buttons only below `sm` where the
  painted labels are too small to read.
- **Consistent spacing.** All image sections use `py-10`; every artwork
  has ~2.2% internal margin so gaps read evenly.
- **Cream ground** `#f6f3f0` matches the artworks' paper tone, with a
  26px mask fade on each image so edges dissolve into the page.
