# Homepage backup — 2026-07-29

Self-contained snapshot of the Street Banker homepage after the archive
band, the full-width lanes, the Sweep padding cut, and the rack-panel icon
set. Everything needed to bring this exact version back is in this folder.

Tag: `homepage-rack-icons-2026-07-29`

> This folder previously held the pre-archive-band state (commit
> `41f9777`). That state is not lost — it is preserved under the tag
> `homepage-sweep-photo-2026-07-29`.

## What's here

| File | What it is |
|---|---|
| `COPY.md` | Every word on the page, in order, with links |
| `landing_config.py` | All homepage content and image wiring |
| `templates/landing.html` | The full page — self-contained, no macros |
| `static/img/sb-hero-photo.jpg` | Hero: performer + crowd |
| `static/img/sb-lane-01..03.jpg` | The three rack-unit lane cards |
| `static/img/sb-band-sweep.jpg` | Royalty Sweep background: backstage corridor |
| `static/img/sb-band-catalog.jpg` | Full-bleed band: the archive shelf wall |
| `static/img/streetbanker-logo-dark.svg` | Header + footer logo |
| `rendered-homepage.html` | The page's HTML exactly as served on this date |

Only the artwork this version actually renders is kept. The retired arena
band (`sb-band.jpg`) and the older artwork-led set live in
`backups/homepage-2026-07-26/` and in the git history.

## Restore — either method

**Method 1 — git tag:**

```bash
git checkout homepage-rack-icons-2026-07-29 -- landing_config.py templates/landing.html static/img/sb-hero-photo.jpg static/img/sb-lane-01.jpg static/img/sb-lane-02.jpg static/img/sb-lane-03.jpg static/img/sb-band-sweep.jpg static/img/sb-band-catalog.jpg
```

**Method 2 — copy from this folder.** From the repo root:

```bash
cp backups/homepage-2026-07-29/landing_config.py . && cp backups/homepage-2026-07-29/templates/landing.html templates/ && cp backups/homepage-2026-07-29/static/img/* static/img/
```

After either: bump `VERSION` in `static/js/sw.js` (currently `sb-v18`) and
the `?v=` numbers in `landing_config.py`, or phones keep serving the cached
previous version. This has caused a "the change didn't deploy" false alarm
twice.

## The page

1. **Nav** — logo + tagline, four links, Login + Start Free Scan
2. **Hero** — THE ARTIST BACK OFFICE. beside the performer photograph
3. **Three Lanes** — full-bleed to 1800px so the rack units read at size
4. **Royalty Sweep** — the one dark section; the corridor photograph *is*
   the section, copy over a 75% scrim, padding kept tight to the words
5. **Signature Tools** — five black rack panels, ivory hardware glyphs
6. **Band** — full-bleed archive shelf wall, anchored top-left
7. **Final CTA** — your music is the product, your catalog is the asset
8. **Minimal footer** — four columns, socials, copyright

## Rules this version follows

- Homepage explains the promise; interior pages carry the detail
- No section makes more than one point; paragraphs are two lines max
- Every link resolves to a real route
- No invented client names, partner logos, or statistics
- Gold is an accent only — labels, active states, the Sweep CTA
- One dark section; the rest stays white/ivory editorial
- Icons are studio hardware drawn in the artwork's own vocabulary — knob,
  faders, label plate + barcode, VU meter, road case — on black rack
  faces. Outlines on pale chips read as weak beside the photography.
- Mobile: copy stacks before imagery, buttons full-width and tappable,
  every tool label stays on one line at 375px

## Earlier versions

| Tag | Folder | What it was |
|---|---|---|
| `homepage-sweep-photo-2026-07-29` | — | Arena band, before the icon work |
| `homepage-editorial-2026-07-26` | `backups/homepage-editorial-2026-07-26/` | First editorial rewrite; patchbay Sweep |
| `homepage-approved-2026-07-26` | `backups/homepage-2026-07-26/` | Artwork-led homepage |
