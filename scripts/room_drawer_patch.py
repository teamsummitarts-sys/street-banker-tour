from pathlib import Path
import re

NAV = '''<details class="room-nav-drawer">
  <summary aria-label="Open The Room navigation"><span>Menu</span></summary>
  <nav aria-label="The Room navigation">
    <a href="{{ builder_base_url }}/">Studio</a>
    <a href="{{ builder_base_url }}/analyze#sound-dna">Sound DNA</a>
    <a href="{{ builder_base_url }}/analyze#improve-track">Improve My Track</a>
    <a href="{{ builder_base_url }}/analyze#reports-heading">Tempo &amp; Key Lab</a>
    <a href="{{ builder_base_url }}/workflow">Pro Workflow</a>
    <a href="{{ builder_base_url }}/#session-team">Collaborate + Listen</a>
    <div class="room-nav-divider"></div>
    <a href="/noise-lab/">Noise Lab</a>
    <a href="/reach/">Reach</a>
  </nav>
</details>'''

index = Path('song_builder/templates/song_builder/index.html')
analyze = Path('song_builder/templates/song_builder/analyze.html')
workflow = Path('song_builder/templates/song_builder/workflow.html')

text = index.read_text()
brand = '<a class="brand" href="{{ builder_base_url }}/" aria-label="The Room projects"><span class="room-brand-crop"><img src="{{ builder_assets_url }}ui/images/the-room-approved.png" alt="The Room by Street Banker"></span></a>'
new_header = f'  <header class="site-bar room-app-header">\n    {brand}\n    ' + NAV.replace('{{ builder_base_url }}/#session-team','') .replace('<a href="">Collaborate + Listen</a>','<a href="#session-team">Collaborate + Listen</a>').replace('\n','\n    ') + '\n  </header>'
text, n = re.subn(r'  <header class="site-bar">.*?  </header>', new_header, text, count=1, flags=re.S)
if n != 1: raise SystemExit('index header not replaced')
index.write_text(text)

text = analyze.read_text()
brand = '<a href="{{ builder_base_url }}/" class="wordmark"><span class="room-brand-crop"><img src="{{ builder_assets_url }}ui/images/the-room-approved.png" alt="The Room by Street Banker" width="1536" height="1024"></span></a>'
new_header = '<header class="site-bar room-app-header">\n  ' + brand + '\n  <span class="header-title">Analyze &amp; Improve</span>\n  ' + NAV.replace('\n','\n  ') + '\n</header>'
text, n = re.subn(r'<header class="site-bar">.*?</header>', new_header, text, count=1, flags=re.S)
if n != 1: raise SystemExit('analyze header not replaced')
analyze.write_text(text)

text = workflow.read_text()
left = '''<div>
      <a class="workflow-brand" href="{{ builder_base_url }}/"><img src="{{ builder_assets_url }}ui/images/the-room-approved.png" alt="The Room by Street Banker"></a>
      <h1>Pro Workflow</h1>
    </div>'''
new_header = '  <header class="topbar room-app-header">\n    ' + left.replace('\n','\n    ') + '\n    ' + NAV.replace('\n','\n    ') + '\n  </header>'
text, n = re.subn(r'  <header class="topbar">.*?  </header>', new_header, text, count=1, flags=re.S)
if n != 1: raise SystemExit('workflow header not replaced')
workflow.write_text(text)

css = Path('song_builder/static/ui/room-navigation.css')
css.write_text('''/* Navigation-only drawer shared by The Room surfaces. */
.room-app-header{position:relative!important;z-index:60;display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;}
.room-nav-drawer{position:relative;margin-left:auto;flex:0 0 auto;}
.room-nav-drawer>summary{list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;min-width:48px;min-height:44px;padding:8px 12px;border:1px solid #5d6260;border-radius:6px;background:linear-gradient(180deg,#3a4042,#1e2325);color:#eee9df;font:600 12px/1 sans-serif;box-shadow:inset 0 1px #ffffff24,0 2px 5px #0008;}
.room-nav-drawer>summary::-webkit-details-marker{display:none}.room-nav-drawer>summary::before{content:'☰';font-size:20px}.room-nav-drawer[open]>summary::before{content:'×';font-size:24px}
.room-nav-drawer nav{position:absolute;top:calc(100% + 10px);right:0;width:min(320px,calc(100vw - 24px));padding:10px;background:linear-gradient(150deg,#262c2e,#111617);border:1px solid #686d69;border-radius:9px;box-shadow:0 18px 34px #000d,inset 0 1px #ffffff1c;display:grid;gap:4px;z-index:100}
.room-nav-drawer nav a{display:flex;align-items:center;min-height:44px;padding:10px 12px;border-radius:6px;color:#eee9df;text-decoration:none;font:600 13px/1.25 sans-serif;border:1px solid transparent}.room-nav-drawer nav a:hover,.room-nav-drawer nav a:focus-visible{background:#ffffff0c;border-color:#8b7650;color:#f3d495;outline:none}.room-nav-divider{height:1px;margin:5px 4px;background:#7a7e7752}
@media(max-width:800px){.room-app-header{min-height:64px!important;height:64px!important;padding:7px 10px!important;margin-bottom:6px!important}.room-app-header .header-title{display:none!important}.room-app-header .brand{flex:0 0 116px!important}.room-app-header .brand .room-brand-crop{width:116px!important}.room-nav-drawer>summary span{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}.room-nav-drawer>summary{width:48px;min-width:48px;padding:7px}.room-nav-drawer nav{position:fixed;top:max(76px,calc(env(safe-area-inset-top) + 58px));right:10px;left:10px;width:auto;max-height:calc(100vh - 100px - env(safe-area-inset-bottom));overflow:auto}}
''')

link = '<link rel="stylesheet" href="{{ builder_assets_url }}ui/room-navigation.css?v=2">'
markers = {
    index: '<link rel="stylesheet" href="{{ builder_assets_url }}ui/collaboration.css">',
    analyze: '<link rel="stylesheet" href="{{ builder_assets_url }}ui/collaboration.css">',
    workflow: '<link rel="stylesheet" href="{{ builder_assets_url }}ui/workflow.css?v=1">',
}
for p, marker in markers.items():
    text=p.read_text()
    if link not in text:
        if marker not in text: raise SystemExit(f'marker missing {p}')
        p.write_text(text.replace(marker, marker+'\n  '+link, 1))

for p in (index, analyze, workflow):
    text=p.read_text()
    for token in ('Sound DNA','Improve My Track','Tempo &amp; Key Lab','Pro Workflow','Collaborate + Listen','/noise-lab/','/reach/','room-nav-drawer'):
        if token not in text: raise SystemExit(f'{p} missing {token}')
