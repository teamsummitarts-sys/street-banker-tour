from pathlib import Path


def test_room_phase1_hardware_layer_is_active_and_scoped():
    root = Path(__file__).resolve().parents[1]
    shared = (root / 'song_builder/static/ui/unified-console.css').read_text()
    legacy = (root / 'song_builder/static/ui/unified-console-legacy.css').read_text()
    phase = (root / 'song_builder/static/ui/phase1-hardware.css').read_text()

    assert "unified-console-legacy.css" in shared
    assert "phase1-hardware.css" in shared
    assert shared.index('unified-console-legacy.css') < shared.index('phase1-hardware.css')

    # Analyze & Improve retains the approved shared styling.
    assert '.room-analysis' in legacy
    # Phase 1 is deliberately scoped to the main Room editor only.
    assert '.room-analysis' not in phase
    assert '.room-console.room-scroll .channel-strip' in phase
    assert '.room-console.room-scroll .sound-rack' in phase
    assert '.room-console.room-scroll .transport' in phase
    assert '@media(max-width:800px)' in phase
