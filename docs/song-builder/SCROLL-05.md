# Studio 05: continuous console

## Audit and change contract
The previous UI repeated the same texture and border treatment across nearly every surface, while mobile view tabs hid the arrangement and controls. The approved revision is one scrolling page, keeping the TR logo and silver hardware identity.

All editing panels now stay visible. Instrument selection updates in place without automatic scrolling. Open controls, AI creation, audition and Back to takes use explicit scroll destinations. Project administration remains a disclosure. Playback remains fixed on phones with safe-area padding. Desktop uses a full-width arrangement and a three-column editing module that stacks on phones.

Material hierarchy: smooth graphite chassis, recessed blue-black waveform and editing surfaces, brushed rack plate, deeper machined knob shadows, larger labels and more separation between modules. No new generated assets or API calls.

## Verification
Ten focused native audio/controller/DOM checks passed. The checks cover audio boundaries, live rack output, cancellation, undo, take acceptance, continuous panel visibility, stable track selection, scroll shortcut targeting and Project keyboard access. One obsolete audition tab-click dependency failed and was corrected before rerunning.

Live visual inspection follows deployment. Physical iPhone rendering remains unverified. Noise Lab, V1, backend access, storage and project schema are excluded. Collaboration is still not implemented.
