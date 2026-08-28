/* Section 8 — Rollout Engine.
 *
 * The section reads with this file absent: the four capability lines are
 * printed, every workflow detail is in the document, and the example
 * campaign is only hidden. What is here is the workflow line's reveal,
 * the sample disclosure, and measurement.
 *
 * Events carry ids from the config. No campaign of anybody's goes into
 * one, and the example is the only campaign this section knows about.
 */
(function () {
  "use strict";

  var root = document.getElementById("rollout-engine");
  if (!root) { return; }

  var caps = [].slice.call(root.querySelectorAll(".sbro-cap"));
  var stages = [].slice.call(root.querySelectorAll(".sbro-stage-btn"));
  var detail = root.querySelector(".sbro-flow-text");
  var details = {};
  var terms = root.querySelectorAll(".sbro-flow-fallback dt");
  var defs = root.querySelectorAll(".sbro-flow-fallback dd");
  for (var i = 0; i < terms.length; i++) {
    if (defs[i]) { details[terms[i].textContent.toLowerCase()] = defs[i].textContent; }
  }

  function track(name, payload) {
    try {
      if (typeof window.gtag === "function") {
        window.gtag("event", name, payload || {});
      } else if (window.dataLayer && typeof window.dataLayer.push === "function") {
        window.dataLayer.push(Object.assign({event: name}, payload || {}));
      } else if (typeof window.sbTrack === "function") {
        window.sbTrack(name, payload || {});
      }
    } catch (e) { /* analytics must never break the page */ }
  }

  /* --- the four capabilities ------------------------------------------- */
  var seenCap = {};
  caps.forEach(function (button) {
    var id = button.dataset.cap;
    function pick() {
      caps.forEach(function (b) { b.classList.toggle("is-active", b === button); });
      if (seenCap[id]) { return; }
      seenCap[id] = true;
      track("rollout_capability_selected", {capability: id});
    }
    button.addEventListener("mouseenter", pick);
    button.addEventListener("focus", pick);
    button.addEventListener("click", pick);
    button.addEventListener("mouseleave", releaseCaps);
    button.addEventListener("blur", function () { window.setTimeout(releaseCaps, 0); });
  });

  function releaseCaps() {
    var held = null;
    caps.forEach(function (b) { if (b === document.activeElement) { held = b; } });
    caps.forEach(function (b) { b.classList.toggle("is-active", b === held); });
  }

  /* --- the workflow line ------------------------------------------------ */
  var seenStage = {};
  stages.forEach(function (button, index) {
    var id = button.dataset.stage;
    function show() {
      stages.forEach(function (b) { b.classList.toggle("is-active", b === button); });
      if (detail && details[id]) { detail.textContent = details[id]; }
      if (seenStage[id]) { return; }
      seenStage[id] = true;
      track("rollout_stage_selected", {stage: id});
    }
    button.addEventListener("mouseenter", show);
    button.addEventListener("focus", show);
    button.addEventListener("click", show);
    if (index === 0) { button.classList.add("is-active"); }
  });

  /* --- the example campaign --------------------------------------------- */
  var toggle = document.getElementById("sbro-sample-btn");
  var sample = document.getElementById("sbro-sample");
  if (toggle && sample) {
    toggle.addEventListener("click", function () {
      var opening = sample.hasAttribute("hidden");
      if (opening) { sample.removeAttribute("hidden"); }
      else { sample.setAttribute("hidden", ""); }
      toggle.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) {
        sample.scrollIntoView({block: "nearest",
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto" : "smooth"});
        track("rollout_sample_opened", {});
      }
    });
    /* Which row of the example somebody looked at, by its day offset -
       the example is the same for everybody, so this says nothing about
       the reader beyond which part of it held them. */
    sample.querySelectorAll(".sbro-sample-list li").forEach(function (row) {
      row.addEventListener("click", function () {
        var day = row.querySelector(".sbro-day");
        track("rollout_sample_item_opened", {day: day ? day.textContent : ""});
      });
    });
  }

  var cta = root.querySelector(".sbro-cta");
  if (cta) {
    cta.addEventListener("click", function () {
      track("rollout_engine_opened", {href: cta.getAttribute("href")});
    });
  }

  /* Section viewed, once. */
  if ("IntersectionObserver" in window) {
    var seen = false;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && !seen) {
          seen = true;
          track("rollout_section_viewed", {});
          obs.disconnect();
        }
      });
    }, {threshold: 0.25});
    obs.observe(root);
  }
})();
