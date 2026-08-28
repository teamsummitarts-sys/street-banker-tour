/* Section 9 — Royalty Sweep.
 *
 * The section reads with this file absent: the five stages are printed,
 * the example case is only hidden, and the CTA is a link. What is here
 * is the disclosure and measurement.
 *
 * Nothing an artist uploaded, entered or was shown goes into an event.
 * The events carry stage names from the config and nothing else.
 */
(function () {
  "use strict";

  var root = document.getElementById("royalty-sweep-section");
  if (!root) { return; }

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

  /* Which stage held someone's attention, once each. */
  var seen = {};
  [].slice.call(root.querySelectorAll(".sbsw-stage")).forEach(function (stage) {
    var id = stage.dataset.stage;
    stage.addEventListener("mouseenter", function () {
      if (seen[id]) { return; }
      seen[id] = true;
      track("sweep_stage_selected", {stage: id});
    });
  });

  var toggle = document.getElementById("sbsw-example-btn");
  var example = document.getElementById("sbsw-example");
  if (toggle && example) {
    toggle.addEventListener("click", function () {
      var opening = example.hasAttribute("hidden");
      if (opening) { example.removeAttribute("hidden"); }
      else { example.setAttribute("hidden", ""); }
      toggle.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) {
        example.scrollIntoView({block: "nearest",
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto" : "smooth"});
        track("sweep_example_case_opened", {});
      }
    });
  }

  var cta = root.querySelector(".sbsw-cta");
  if (cta) {
    cta.addEventListener("click", function () {
      track("sweep_run_clicked", {href: cta.getAttribute("href")});
    });
  }

  var method = root.querySelector(".sbsw-method");
  if (method) {
    method.addEventListener("click", function () {
      track("sweep_methodology_clicked", {});
    });
  }

  /* Section viewed, once. */
  if ("IntersectionObserver" in window) {
    var viewed = false;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && !viewed) {
          viewed = true;
          track("sweep_section_viewed", {});
          obs.disconnect();
        }
      });
    }, {threshold: 0.25});
    obs.observe(root);
  }
})();
