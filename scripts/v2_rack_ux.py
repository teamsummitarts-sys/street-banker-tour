from pathlib import Path

rack = Path("templates/rack.html")
s = rack.read_text()

css = r'''
/* ---- V2 session workflow: make the Rack feel like a task, not a manual ---- */
.rk-session {
  max-width: 980px; margin: 18px auto 6px; padding: 14px; border: 1px solid var(--sb-line);
  border-radius: 12px; background: linear-gradient(180deg, rgba(24,20,16,.96), rgba(10,8,6,.98));
  box-shadow: 0 18px 45px -28px rgba(0,0,0,.9); color: var(--sb-ink);
}
.rk-session-top { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:12px; }
.rk-session-kicker { margin:0 0 3px; font:600 10px/1.2 var(--sb-mono); letter-spacing:.16em; text-transform:uppercase; color:var(--sb-gold); }
.rk-session-title { margin:0; font:700 clamp(17px,2vw,22px)/1.15 var(--sb-display); color:var(--sb-ink); }
.rk-session-sub { margin:5px 0 0; max-width:68ch; font:400 12px/1.5 var(--sb-display); color:var(--sb-ink-2); }
.rk-session-file { flex:0 0 auto; max-width:260px; padding:7px 10px; border:1px solid var(--sb-line); border-radius:6px;
  font:500 11px/1.3 var(--sb-mono); color:var(--sb-ink-2); background:var(--rk-well); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.rk-journey { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:7px; }
.rk-journey-step { position:relative; min-width:0; padding:10px 10px 9px; border:1px solid var(--sb-line); border-radius:7px;
  background:var(--rk-well-2); color:var(--sb-ink-2); text-align:left; cursor:pointer; transition:border-color .15s ease, background .15s ease, transform .15s ease; }
.rk-journey-step:hover { border-color:var(--sb-line-strong); transform:translateY(-1px); }
.rk-journey-step:focus-visible { outline:2px solid var(--sb-gold); outline-offset:2px; }
.rk-journey-step[disabled] { cursor:not-allowed; opacity:.48; transform:none; }
.rk-journey-step.is-current { border-color:var(--sb-gold); background:linear-gradient(180deg, rgba(232,185,80,.13), var(--rk-well-2)); }
.rk-journey-step.is-done { border-color:rgba(116,180,103,.55); }
.rk-journey-num { display:block; margin-bottom:5px; font:700 10px/1 var(--sb-mono); letter-spacing:.12em; color:var(--sb-gold); }
.rk-journey-name { display:block; font:700 12px/1.15 var(--sb-display); color:var(--sb-ink); }
.rk-journey-note { display:block; margin-top:3px; font:400 10px/1.35 var(--sb-display); color:var(--sb-ink-3); }
.rk-session-next { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-top:10px; padding:9px 10px;
  border-top:1px solid var(--sb-line); font:500 11px/1.4 var(--sb-display); color:var(--sb-ink-2); }
.rk-session-next strong { color:var(--sb-ink); }
.rk-session-actions { display:flex; gap:6px; flex-wrap:wrap; }
.rk-session-actions .sw { min-height:30px; }
@media (max-width:760px) {
  .rk-session { margin:10px 8px 4px; padding:10px; }
  .rk-session-top { flex-direction:column; gap:8px; } .rk-session-file { max-width:100%; width:100%; }
  .rk-journey { grid-template-columns:1fr 1fr; } .rk-journey-step:last-child { grid-column:1/-1; }
  .rk-session-next { align-items:flex-start; flex-direction:column; }
}
'''

html = r'''
<section class="rk-session" id="rk-session" aria-labelledby="rk-session-title">
  <div class="rk-session-top">
    <div>
      <p class="rk-session-kicker">Session workflow</p>
      <h2 class="rk-session-title" id="rk-session-title">From raw track to deliverable</h2>
      <p class="rk-session-sub">The rack is the instrument. This strip is the workflow: load a track, measure it, shape it, compare it, then bounce or archive the result.</p>
    </div>
    <div class="rk-session-file" id="rk-guide-file" aria-live="polite">No track loaded</div>
  </div>
  <div class="rk-journey" role="list" aria-label="Rack session steps">
    <button class="rk-journey-step is-current" id="rk-guide-load" type="button" role="listitem"><span class="rk-journey-num">01</span><span class="rk-journey-name">Load</span><span class="rk-journey-note">Drop or choose audio</span></button>
    <button class="rk-journey-step" id="rk-guide-analyze" type="button" role="listitem" disabled><span class="rk-journey-num">02</span><span class="rk-journey-name">Analyze</span><span class="rk-journey-note">LUFS · peak · range</span></button>
    <button class="rk-journey-step" id="rk-guide-shape" type="button" role="listitem" disabled><span class="rk-journey-num">03</span><span class="rk-journey-name">Shape</span><span class="rk-journey-note">EQ · tube · dynamics</span></button>
    <button class="rk-journey-step" id="rk-guide-compare" type="button" role="listitem" disabled><span class="rk-journey-num">04</span><span class="rk-journey-name">Compare</span><span class="rk-journey-note">Bypass · reference · A/B</span></button>
    <button class="rk-journey-step" id="rk-guide-deliver" type="button" role="listitem" disabled><span class="rk-journey-num">05</span><span class="rk-journey-name">Deliver</span><span class="rk-journey-note">Bounce · Vault · Smart Link</span></button>
  </div>
  <div class="rk-session-next">
    <span id="rk-guide-next"><strong>Start here:</strong> load a WAV, MP3, FLAC or M4A. Audio processing stays in this browser.</span>
    <div class="rk-session-actions"><button class="sw" id="rk-guide-explain" type="button">Show explanations</button><button class="sw sw-gold" id="rk-guide-primary" type="button">Load track</button></div>
  </div>
</section>

'''

if "id=\"rk-session\"" not in s:
    marker = "</style>\n\n<header class=\"rk-page-head\">"
    if marker not in s:
        raise SystemExit("style marker missing")
    s = s.replace(marker, css + "\n</style>\n\n<header class=\"rk-page-head\">", 1)
    marker = "<!-- THE AMP. One chassis: rails full height, nameplate, tube deck, then every unit flush. -->"
    if marker not in s:
        raise SystemExit("amp marker missing")
    s = s.replace(marker, html + marker, 1)
    marker = '<script src="/static/js/rackdsp.js?v=56"></script>'
    if marker not in s:
        raise SystemExit("rackdsp marker missing")
    s = s.replace(marker, marker + '\n<script src="/static/js/rack-guide.js?v=1"></script>', 1)
    rack.write_text(s)

Path("static/js/rack-guide.js").write_text(r'''/* Street Banker V2 — Rack session guide. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var steps = [$("rk-guide-load"), $("rk-guide-analyze"), $("rk-guide-shape"), $("rk-guide-compare"), $("rk-guide-deliver")];
  if (!steps[0]) return;
  var file = $("rk-file"), fileInfo = $("rk-fileinfo"), next = $("rk-guide-next"), primary = $("rk-guide-primary"), guideFile = $("rk-guide-file");
  var loaded = false, analyzed = false, shaped = false, compared = false;
  function setStep(index) { steps.forEach(function (el, i) { if (!el) return; el.classList.toggle("is-current", i === index); el.classList.toggle("is-done", i < index); }); }
  function loadedState(name) {
    loaded = true; steps.slice(1).forEach(function (el) { if (el) el.disabled = false; });
    if (guideFile) guideFile.textContent = name || "Track loaded"; setStep(1);
    if (next) next.innerHTML = "<strong>Next:</strong> measure the track before changing it. You need a baseline to know whether the rack improved anything.";
    if (primary) primary.textContent = "Analyze track";
  }
  function click(id) { var el = $(id); if (el && !el.disabled) el.click(); }
  function jump(id) { var el = $(id); if (el) el.scrollIntoView({behavior:"smooth", block:"center"}); }
  steps[0].addEventListener("click", function () { if (file) file.click(); });
  steps[1].addEventListener("click", function () { analyzed = true; click("rk-ldn-go"); setStep(2); jump("sb03"); if (next) next.innerHTML = "<strong>Shape:</strong> start with EQ, then tube and dynamics. Use each unit’s A/B instead of guessing."; if (primary) primary.textContent = "Go to EQ"; });
  steps[2].addEventListener("click", function () { shaped = true; setStep(3); jump("sb03"); if (next) next.innerHTML = "<strong>Compare:</strong> use global Bypass and load a commercial reference. Keep only changes that win the comparison."; if (primary) primary.textContent = "Compare A/B"; });
  steps[3].addEventListener("click", function () { compared = true; setStep(4); jump("rk-dock"); if (next) next.innerHTML = "<strong>Deliver:</strong> bounce the exact rack you are hearing, then archive it in Vault or start the Smart Link."; if (primary) primary.textContent = "Open bounce"; });
  steps[4].addEventListener("click", function () { click("rk-export2"); });
  primary.addEventListener("click", function () { if (!loaded) return steps[0].click(); if (!analyzed) return steps[1].click(); if (!shaped) return steps[2].click(); if (!compared) return steps[3].click(); return steps[4].click(); });
  var explain = $("rk-guide-explain"); if (explain) explain.addEventListener("click", function () { click("rk-explain"); });
  if (file) file.addEventListener("change", function () { if (file.files && file.files.length) loadedState(file.files[0].name); });
  if (fileInfo && window.MutationObserver) new MutationObserver(function () { var text = (fileInfo.textContent || "").trim(); if (!loaded && text && text.indexOf("No file loaded") !== 0) loadedState(text.split(" · ")[0]); }).observe(fileInfo, {childList:true, characterData:true, subtree:true});
})();
''')
