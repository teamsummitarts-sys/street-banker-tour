# Noise Lab original hardware reference

The owner's original phone and desktop mockups are the visual authority. Their
material and control detail must survive implementation; simpler bright circles
and sparse tick rings are not acceptable substitutes.

Restored in this change:
- Forty-one positions over the existing 270-degree sweep, including nine longer
  major marks per dial. Gold marks reflect the heard setting, including A/B and
  Undo. Numeric values remain the exact control; scale spacing is visual.
- Darker brushed-metal faces with fine concentric machining, a narrow bevel,
  a fine ridged outer rim, and an inset gold pointer.
- Twelve recessed cross-slot fasteners across the meter, instrument and library
  panels, fine vertical control separators and tighter black readout frames.
- One rack masthead for the exact existing Street Banker logo, Noise Lab title
  and Studio/Club controls. Navigation and display settings remain reachable in
  a native disclosure menu. Phone shows the action for switching views.

Protected behavior: existing audio processing, source loaders, range bounds,
exact-value entry, saved patches, provider settings and metering are unchanged.
Level remains -60 through 0 dB. No illustrative meter levels or patch names from
the mockups are inserted into the product.

Fresh checks: 48 Node audio/interface tests and 71 Flask route/private-save tests
passed. The rendered Jinja template has five complete scales, 205 tick paths
(including 45 major marks), twelve fasteners and no duplicate IDs. The new scale
regression verifies middle/end positions, A/B and Undo against numeric controls.

Visual limits: the controlled browser previously denied local and shared-file
previews under its security policy, so no new browser screenshot is claimed.
The CSS detector ran in degraded regex mode without its parser dependencies;
its empty findings do not verify visual contrast or rendered layout. The owner
must review the actual updated screen on iPhone. This file records the visual
contract; automated checks do not certify photographic fidelity.
