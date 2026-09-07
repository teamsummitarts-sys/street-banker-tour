"""Provider request-shape tests. No network or paid generation calls."""
from song_builder.provider import composition_payload


def test_music_v2_section_uses_prompt_contract_and_exact_duration():
    payload = composition_payload({
        'prompt': 'A wider, urgent chorus', 'tempo': 92, 'key': 'D minor',
        'section': {'name': 'Chorus', 'duration': 12.5,
                    'direction': 'Half-time drums', 'lyrics': 'Hold the line'},
    })
    assert payload['model_id'] == 'music_v2'
    assert payload['music_length_ms'] == 12500
    assert payload['store_for_inpainting'] is False
    assert 'composition_plan' not in payload
    assert 'A wider, urgent chorus' in payload['prompt']
    assert 'Target tempo: 92 BPM.' in payload['prompt']
    assert 'Target key: D minor.' in payload['prompt']
    assert 'Use these original lyrics:\nHold the line' in payload['prompt']
