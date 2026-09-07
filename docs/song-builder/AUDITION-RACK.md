# The Room: take audition rack

Generated candidates now use the arrangement AudioEngine, decoded source buffers, track rack DSP and stereo meters. “Audition with rack” opens a temporary one-track project, limited to the destination section. It does not write the arrangement or call the music provider.

Body, Bite, Dirt, Space, Output and Original/Processed affect this preview. Settings are retained per project/take for the current browser session. Accept into new version copies them onto a new generated-take track, preserving other tracks and the original version. Unaccepted audition settings are not persisted across page reloads.

Stop invalidates pending decoding; changing sections or selecting an arrangement instrument exits audition. The transport identifies TAKE playback. Rack actions include replay, accept and return to takes.

Visual pass: layered metal faceplates, inset glass, beveled illuminated buttons, dimensional silver knob faces and segmented stereo level columns driven by the actual master signal. Phone rules preserve 44px control targets and a two-column knob bank.

Verification: 36 unit tests, 10 native-audio/DOM integration tests and 30 backend/storage tests pass. The new controller integration measures actual candidate output attenuation, bypass restoration, replay retention, accepted rack settings, unchanged source project and cancellation during decoding. Physical iPhone listening remains a device check.

Scope: The Room only. Noise Lab and V1 excluded.
