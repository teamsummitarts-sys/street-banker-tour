from pathlib import Path

FLOW_HEAD='''\n{% block head_scripts %}{{ super() }}<link rel="stylesheet" href="/static/css/studio-flow.css?v=1">{% endblock %}\n'''
FLOW='''\n<section class="sb-studio-flow" aria-label="Studio and assets workflow">\n  <div class="sb-studio-flow__head"><div><div class="sb-label sb-label-gold">Studio pipeline</div><div class="sb-studio-flow__title">Track → master → release asset</div><div class="sb-studio-flow__sub">One production path across the tools. Each stage hands its real output to the next.</div></div><div class="sb-studio-flow__state">{{ flow_state|default('production') }}</div></div>\n  <nav class="sb-studio-flow__rail" aria-label="Production stages">\n    {% for href,name,note,key in [('/tracks','Track','identity + rights','track'),('/rack','Rack','shape + measure','rack'),('/audio-studio','Stems','split + isolate','stems'),('/audio-studio','Versions','dub + campaign cuts','versions'),('/rack','Master','bounce + loudness','master'),('/vault','Vault','archive deliverables','vault'),('/tracks','Passport','release truth','passport')] %}\n    <a href="{{ href }}" class="sb-studio-flow__step {{ 'is-here' if flow_here|default('') == key else '' }}"><span class="sb-studio-flow__num">0{{ loop.index }}</span><span class="sb-studio-flow__name">{{ name }}</span><span class="sb-studio-flow__note">{{ note }}</span></a>\n    {% endfor %}\n  </nav>\n  <div class="sb-studio-flow__actions"><p><strong>{{ flow_next_title|default('Keep the asset moving.') }}</strong> {{ flow_next_copy|default('Do the work here, then send the result into the next stage instead of starting over on another page.') }}</p><a href="{{ flow_primary_href|default('/rack') }}" class="sb-btn sb-btn-primary sb-btn-sm">{{ flow_primary_label|default('Open Rack') }}</a><a href="/vault" class="sb-btn sb-btn-secondary sb-btn-sm">Open Vault</a></div>\n</section>\n'''

def inject(path, here, title, copy, href, label):
    p=Path(path); s=p.read_text()
    if 'studio-flow.css?v=1' not in s:
        marker='{% block content %}'
        s=s.replace(marker,FLOW_HEAD+'\n'+marker,1)
    if 'aria-label="Studio and assets workflow"' not in s:
        vars=("{% set flow_here = '"+here+"' %}{% set flow_next_title = '"+title.replace("'","&#39;")+"' %}{% set flow_next_copy = '"+copy.replace("'","&#39;")+"' %}{% set flow_primary_href = '"+href+"' %}{% set flow_primary_label = '"+label+"' %}\n")
        # put workflow inside the existing max-width page wrapper so it aligns with the product
        needle='<div class="mx-auto max-w-['
        pos=s.find(needle)
        if pos<0: raise SystemExit('wrapper missing '+path)
        end=s.find('>',pos)+1
        s=s[:end]+vars+FLOW+s[end:]
    p.write_text(s)

inject('templates/audio_studio.html','stems','Build the usable versions.','Split, isolate or create the campaign-ready audio, then move the approved result into the Rack or Vault.','/rack','Open Rack')
inject('templates/vault.html','vault','Archive the deliverable.','This is the handoff point for masters, stems, art and campaign files. The next move is attaching release truth in the Track Passport.','/tracks','Open Passports')
inject('templates/os_tracks.html','track','Start with the song record.','Create or choose the track first so rights, metadata and every downstream asset have a single identity.','/rack','Open Rack')
inject('templates/os_track_detail.html','passport','Finish the release truth.','This passport is the control record. Resolve red rights issues and incomplete metadata before the release leaves the building.','/vault','Open Vault')

# Give Audio Studio stronger production-room hierarchy without changing backend forms.
p=Path('templates/audio_studio.html'); s=p.read_text()
s=s.replace('<div class="grid gap-4 md:grid-cols-2">\n    {% for lane in lanes %}\n      <section class="sb-panel p-4">','<div class="sb-audio-lanes">\n    {% for lane in lanes %}\n      <section class="sb-audio-lane {{ \'is-live\' if lane.on else \'\' }}">\n        <div class="sb-audio-lane__top"><div class="sb-audio-lane__icon">{{ \'STEM\' if lane.kind == \'stem_separation\' else \'ISO\' if lane.kind == \'voice_isolation\' else \'DUB\' if lane.kind == \'dubbing\' else \'VO\' if lane.kind == \'campaign_voiceover\' else \'SFX\' if lane.kind == \'sound_effects\' else \'AUD\' }}</div><div class="sb-audio-lane__copy">',1)
s=s.replace('        <p class="mt-2 text-sm text-gray-300">{{ lane.note }}</p>','        <p class="sb-audio-lane__note">{{ lane.note }}</p></div></div><div class="sb-audio-lane__body">',1)
# This replacement must happen for every lane at runtime, not every template copy; close once around templated body.
s=s.replace('        {% endif %}\n      </section>\n    {% endfor %}','        {% endif %}\n        </div>\n      </section>\n    {% endfor %}',1)
p.write_text(s)

# Vault upload should read like a receiving dock, not a generic form.
p=Path('templates/vault.html'); s=p.read_text().replace('<section class="rounded-2xl border border-sb-gold/25 bg-sb-surface-2 p-4">\n    <form id="vault-upload-form"','<section class="sb-vault-drop">\n    <div class="sb-label sb-label-gold">Receiving dock</div><div class="mt-1 text-sm font-bold">File the finished asset</div><p class="mt-1 mb-3 text-xs text-gray-300">Masters, stems, art and campaign files land here with a useful label so the next person can actually find them.</p>\n    <form id="vault-upload-form"',1); p.write_text(s)

# Track detail gets direct production actions next to the passport, reducing backtracking.
p=Path('templates/os_track_detail.html'); s=p.read_text(); needle='  <div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">'
bar='''  <div class="sb-passport-actionbar"><span>Production shortcuts for this track — process the audio, archive the files, then come back here to certify the release record.</span><a href="/rack" class="sb-btn sb-btn-secondary sb-btn-sm">Process in Rack</a><a href="/audio-studio" class="sb-btn sb-btn-secondary sb-btn-sm">Create Stems / Versions</a><a href="/vault" class="sb-btn sb-btn-secondary sb-btn-sm">Open Vault</a></div>\n\n'''
if 'Production shortcuts for this track' not in s: s=s.replace(needle,bar+needle,1)
p.write_text(s)
