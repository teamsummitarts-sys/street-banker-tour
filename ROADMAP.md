# Roadmap notes

## Shopify = the commerce engine (decided)
The existing Shopify store (artiswarrecords.com) stays live and handles all real
commerce — merch, checkout, payments, PCI compliance. The app gets hosted at a
subdomain (target: **app.artiswarrecords.com**) and the two are stitched:

- App -> store links: done (services hub "Shop Apparel & Merch", homepage footer).
- User steps at go-live: DNS CNAME `app.artiswarrecords.com` -> host; add an
  "Artist Portal" link to the Shopify store nav.
- Next integrations: **Shopify Buy Button** embeds inside the app (Apparel page,
  Discover, Network artist profiles) — embed code generated from the Shopify
  admin; later the Storefront API can feed a live in-app Merch tab.
- Result: no custom payment code needed; the store the user already built is
  the ecosystem's real checkout.

## Native mobile app (planned)
Street Banker / Royalty Sweep is currently a Flask web app (demo + marketing
surface). The goal is to **also ship a native mobile app (iOS/Android)** and/or
push select features natively.

### Features earmarked for native (web can't fully deliver these)
- **Mintable Moments — real screen protection.** The web version only *deters*
  capture (privacy shield on focus-loss + tiled watermark + serial number). True
  screenshot blocking requires native:
  - **Android:** `WindowManager.LayoutParams.FLAG_SECURE` blocks screenshots &
    screen recording for the view.
  - **iOS:** cannot block, but can **detect** screenshots
    (`UIApplication.userDidTakeScreenshotNotification`) and react (e.g. void the
    moment / notify the creator). Screen-recording detection via
    `UIScreen.isCaptured`.
  - Real protection either way stays: **watermark + serial + provenance** so any
    capture is a traceable, defaced copy.
- **Push notifications** (the in-app Notifications inbox → real device pushes).
- **Camera / media upload** UX for Moments, EPK, cover art.
- **In-app purchases** (Moments claim, plans) via App Store / Play billing.

### What stays web
- Marketing homepage, label services, dashboards, reports — all fine on web and
  serve as the demo/investor surface.

## Path to "real" (see also, in-app)
- Foundation first: real accounts + database (persistence) + always-on hosting.
- Highest-value real wedge: **royalty recovery via distributor data**
  (CSV/statement ingestion, or a Symphonic/distributor API) → real missing-money
  detection. Everything else can stay demo until funded.
- Money features (advances, futures, staking, fan passes, Roll the Dice, Moments
  purchase) require legal/compliance + a payment/funding partner — kept as
  clearly-labeled simulated demos for now.
