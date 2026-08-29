/* Street Banker V2 — Rack session guide. */
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
