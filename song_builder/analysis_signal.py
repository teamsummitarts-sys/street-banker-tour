"""Bounded PCM measurements. Musical labels are deliberately not measurements."""
from array import array
import io
import math
import sys
import wave
from . import validation as v


def db(value):
    return round(20 * math.log10(value), 2) if value > 0 else None


def measure(data):
    duration = v.wav_info(data)
    with wave.open(io.BytesIO(data), 'rb') as f:
        if f.getsampwidth() != 2:
            v.invalid('Analysis currently accepts 16-bit PCM WAV. Export a 16-bit WAV copy first.')
        channels, rate = f.getnchannels(), f.getframerate()
        samples = array('h', f.readframes(f.getnframes()))
    if sys.byteorder != 'little':
        samples.byteswap()
    peak, energy, clipped = 0, 0, 0
    envelopes, windows = [], []
    step = max(channels, round(rate / 50) * channels)
    frame_seconds = step / (rate * channels)
    for start in range(0, len(samples), step):
        part = samples[start:start + step]
        square = sum(x * x for x in part)
        energy += square
        local_peak = max((abs(x) for x in part), default=0)
        peak = max(peak, local_peak)
        clipped += sum(abs(x) >= 32760 for x in part)
        envelopes.append(math.sqrt(square / len(part)) / 32768)
    for start in range(0, len(envelopes), 50):
        values = envelopes[start:start + 50]
        windows.append({'start': round(start * frame_seconds, 3), 'end': round(min(duration, (start + len(values)) * frame_seconds), 3),
                        'rmsDbfs': db(math.sqrt(sum(x*x for x in values) / len(values)))})
    rms = math.sqrt(energy / len(samples)) / 32768
    active = sorted(w['rmsDbfs'] for w in windows if w['rmsDbfs'] is not None and w['rmsDbfs'] > -60)
    spread = round(active[int(.9 * (len(active)-1))] - active[int(.1 * (len(active)-1))], 2) if active else None
    onset = [max(0, b-a) for a, b in zip(envelopes, envelopes[1:])]
    tempo = {'bpm': None, 'confidence': 'unavailable', 'alternatives': [],
             'method': 'RMS-onset periodicity; heuristic, not a calibrated probability',
             'reason': 'No reliable periodic onset pattern detected.'}
    # Up to 90 seconds keeps computation bounded on a web worker. Full-song levels above.
    onset = onset[:round(90 / frame_seconds)]
    power = sum(x*x for x in onset)
    if duration >= 8 and power > 1e-7:
        scores = [(sum(onset[i]*onset[i-lag] for i in range(lag,len(onset))) / power, lag)
                  for lag in range(round(.3 / frame_seconds), round(1.5 / frame_seconds) + 1)]
        score, lag = max(scores)
        if score > .35:
            bpm = round(60 / (lag * frame_seconds), 1)
            tempo.update(bpm=bpm, confidence='medium' if score > .65 else 'low',
                         alternatives=[round(bpm/2, 1), round(bpm*2, 1)],
                         reason='Tap along to confirm; half/double time and changing tempos can mislead this estimate.')
    return {'durationSeconds': duration, 'sampleRate': rate, 'channels': channels,
            'peakDbfs': db(peak / 32768), 'rmsDbfs': db(rms),
            'crestDb': round(db(peak/32768)-db(rms), 2) if rms else None,
            'nearFullScaleSamples': clipped, 'nearFullScaleFraction': clipped / len(samples),
            'activeRmsSpreadDb': spread, 'windows': windows,
            'tempoEstimate': tempo, 'keyEstimate': {'value': None, 'confidence': 'unavailable',
                'reason': 'Key/mode requires a musical interpretation destination; it is not inferred from file metadata.'},
            'method': 'PCM16 sample peak and RMS, one-second windows. Not LUFS, true peak, or an EBU loudness range.'}


def conservative_notes(measured):
    works, notes = [], []
    if measured['nearFullScaleSamples'] == 0:
        works.append('No samples reached the near-full-scale threshold in this analysis copy. Preserve intentional dynamics.')
    if measured['rmsDbfs'] is None:
        return ['This file is silent; musical judgments are unavailable.'], []
    if measured['nearFullScaleSamples']:
        notes.append(dict(start=0, end=measured['durationSeconds'], section='Whole track',
            change='Inspect the loudest peaks in the original session; audition 1 dB less level into the final limiter.',
            benefit='Test whether transient clarity improves.', tradeoff='The result may be quieter; reducing this rendered file cannot undo earlier clipping.',
            confidence='medium', identityRisk='low', requires='stems'))
    quiet = [w for w in measured['windows'] if w['rmsDbfs'] is None or w['rmsDbfs'] < -60]
    leading = 0
    for w in quiet:
        if abs(w['start']-leading) > .01: break
        leading = w['end']
    if leading >= 2:
        notes.append(dict(start=0, end=leading, section='Opening (not a detected verse)',
            change='Audition shortening the leading near-silence by 0.5 seconds.',
            benefit='Test a quicker start.', tradeoff='Keep the original if the pause is intentional.',
            confidence='medium', identityRisk='low', requires='master'))
    return works, notes[:5]
