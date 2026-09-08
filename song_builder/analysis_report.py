"""Portable report v1, weighted trait synthesis and approval-only producer exports."""
import json
from .analysis_signal import conservative_notes


def build_report(tracks, payload):
    votes, appearances = {}, {}
    active = [t for t in payload['tracks'] if not t['muted'] and t['weight'] > 0]
    total = sum(t['weight'] for t in active)
    avoid = {s.casefold() for t in active for s in t['avoid']}
    works, recommendations = [], []
    for result, source in zip(tracks, active):
        interpretation = result['interpretation']
        labels = {s for values in (interpretation or {}).get('traits',{}).values() for s in values}
        labels |= set(source['keep'])
        for label in labels:
            key = label.casefold()
            if key in avoid: continue
            votes[key] = votes.get(key,0) + source['weight'] / total
            appearances.setdefault(key,[]).append(result['id'])
        existing, suggestions = conservative_notes(result['measured'])
        if interpretation:
            existing = interpretation['works']
            suggestions = interpretation['recommendations']
        works.extend({'trackId':result['id'], 'text':s} for s in existing)
        if payload['mode'] == 'improve':
            recommendations.extend(dict(s, id='change-'+str(i+1), decision='pending', source='model inference' if interpretation else 'signal-based test', trackId=result['id']) for i,s in enumerate(suggestions[:5]))
    ranked = sorted(votes, key=lambda key:(-votes[key],key))
    shared = [dict(trait=key, weight=round(votes[key],3), trackIds=appearances[key]) for key in ranked if len(appearances[key])>1]
    outliers = [dict(trait=key, trackIds=appearances[key]) for key in ranked if len(appearances[key])==1] if len(active)>1 else []
    tempos = [(t['measured']['tempoEstimate']['bpm'], a['weight']) for t,a in zip(tracks,active) if t['measured']['tempoEstimate']['bpm']]
    bpm = round(sum(b*w for b,w in tempos)/sum(w for _,w in tempos),1) if tempos else None
    length = round(sum(t['measured']['durationSeconds']*a['weight'] for t,a in zip(tracks,active))/total)
    center = ', '.join(ranked[:8]) or 'No supported musical traits yet. Add Keep traits or choose musical interpretation.'
    structure = ' → '.join(s['name'] for s in payload['sections']) or 'intro, verse, chorus, verse, chorus, bridge, final chorus, outro (proposed)'
    # Reserve exclusions first; never cut a trait or silently lose a constraint.
    pieces, omitted = [], []
    exclusions = []
    for trait in sorted(avoid):
        candidate = 'Avoid: '+', '.join(exclusions+[trait])
        if len(candidate) <= 999:
            exclusions.append(trait)
        else:
            omitted.append('Avoid: '+trait)
    suffix = 'Avoid: '+', '.join(exclusions) if exclusions else ''
    candidates = []
    if payload.get('goal'): candidates.append('Goal: '+payload['goal'])
    if bpm: candidates.append('Target tempo: '+str(bpm)+' BPM (verify by ear)')
    candidates += ['Target length: '+str(length)+' seconds', 'Structure: '+structure]
    candidates += ['Trait: '+trait for trait in ranked[:12]]
    for item in candidates:
        candidate = '. '.join(pieces+[item]+([suffix] if suffix else []))
        if len(candidate) <= 999:
            pieces.append(item)
        else:
            omitted.append(item)
    prompt = '. '.join(pieces+([suffix] if suffix else []))
    return {'schemaVersion':1, 'mode':payload['mode'], 'tracks':tracks, 'works':works,
        'blend':{'center':center, 'shared':shared, 'outliers':outliers, 'excluded':sorted(avoid),
            'method':'Normalized user weights over active references; shared/outlier tags are exact label matches, not a similarity model.',
            'tempoCaution':'Weighted BPM is only a creative target. Half/double-time estimates can make averaging misleading.'},
        'blueprint':{'prompt':prompt, 'omitted':omitted, 'alternates':[
            'Sparse: reduce layers and leave more space around the central motif.',
            'Driving: test a denser rhythmic pulse while retaining the core mood.',
            'Intimate: test a closer, drier presentation and restrained dynamics.'],
            'note':'Editable creative directions, not analysis facts. Instrument/vocal traits require interpretation or your Keep labels.' + (' Character limit: review omitted details before using this prompt: '+ '; '.join(omitted) if omitted else '')},
        'recommendations':recommendations[:5], 'sections':payload['sections'],
        'tempoKeyLab':{'tests':['Optional tempo test: audition ±2 BPM in a separate version.',
                              'Optional key test: audition ±1 semitone only if the performer benefits.'],
            'risks':'No automatic audio change. Time stretching may smear transients; pitch shifts may alter timbre and vocal formants. Re-recording may be preferable. Confirm tempo and key by ear.'},
        'limitations':['Signal measurements describe the uploaded analysis copy.',
            'Model confidence is self-reported, not a calibrated probability.',
            'Recommendations do not modify or rewrite your project.',
            'No artist identity or melody is required for this blueprint.']}


def export_report(run, kind):
    report = run['report']
    if kind == 'json': return json.dumps(report, ensure_ascii=False, indent=2), 'application/json', 'json'
    if kind == 'prompt': return report['blueprint']['prompt'], 'text/plain', 'txt'
    full = kind in ('full','markdown','text')
    lines = ['THE ROOM — ANALYZE & IMPROVE', 'Destination: '+run['destination'],
             'Recommendations are auditions to consider; no audio was changed.', '']
    if full:
        lines += ['ANALYSIS', json.dumps(report['tracks'], ensure_ascii=False, indent=2),
                  'CREATIVE CENTER', report['blend']['center'], 'SUNO BLUEPRINT', report['blueprint']['prompt'], '']
    lines += ['PRESERVE'] + [w['text'] for w in report['works']] + ['', 'EDIT LIST']
    notes = report['recommendations'] if full else [x for x in report['recommendations'] if x['decision']=='accepted']
    if not notes: lines.append('No accepted changes.' if not full else 'No supported changes proposed.')
    for n in notes:
        lines += [f"{n['start']:.2f}–{n['end']:.2f}s · {n['section']} · {n['decision']}", n['change'],
                  'Benefit: '+n['benefit'], 'Tradeoff: '+n['tradeoff'],
                  f"Confidence: {n['confidence']} · Identity risk: {n['identityRisk']} · Requires: {n['requires']}", '']
    lines += ['LIMITS'] + report['limitations'] + [report['tempoKeyLab']['risks']]
    return '\n'.join(lines), 'text/markdown' if kind=='markdown' else 'text/plain', 'md' if kind=='markdown' else 'txt'
