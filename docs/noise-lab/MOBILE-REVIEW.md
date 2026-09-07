# Noise Lab iPhone correction — review build

Target: approved metallic rack mockup and the four owner iPhone screenshots.

Changes are confined to Noise Lab's template, console presentation controller,
and scoped CSS. Phone setup starts with a collapsed prompt, compact source row,
smaller header and a tighter three-plus-two dial bank. The existing silver dial
faces, actual audio meters and fixed transport remain. Private patches and
exports share a native dialog on phones and stay inline on desktop. Closing the
sheet returns focus to Save; resizing closes modal state before restoring the
desktop library. No audio engine, provider, database or deployment changes.

Fresh verification: 47 Node audio/controller/mobile-console tests and 71 Flask
route/private-patch tests passed. git diff --check passed. The design detector was degraded because
its HTML/CSS parser dependencies were unavailable; its empty findings are not
visual clearance. The controlled browser rejected the isolated local preview
with ERR_BLOCKED_BY_CLIENT. No new rendered mobile/desktop screenshots were
captured, and native Safari dialog/keyboard behavior remains unverified.

The browser also denied shared-file previews under its URL security policy.
No browser workaround was attempted after that denial. Visual verification
remains pending on the owner's iPhone after this authorized V2 release.

Release is based on V2 main 97222a837149484adfab32c92482f0913cd61450.
All 26 existing Noise Lab module/test files and db.py were compared with the
remote tree; only the three intended presentation files differed. Release uses
that remote base tree and only the explicit three files, regression test and
this review note, preserving the newer Song Builder work.
