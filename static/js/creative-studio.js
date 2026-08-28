/* Section 7 — Creative Studio.
 *
 * The section reads with this file absent: the picture, the copy, the
 * CTA and every feature line are in the document, and the workflow list
 * is only hidden. What is here is the label row's one-line reveal, the
 * workflow disclosure, and measurement.
 *
 * Events carry feature ids from the config. Nothing an artist wrote,
 * uploaded or was shown goes into one.
 */
(function () {
  "use strict";

  var root = document.getElementById("creative-studio");
  if (!root) { return; }

  var features = [].slice.call(root.querySelectorAll(".sbcs-feature"));
  var wrap = root.querySelector(".sbcs-features");
  var line = root.querySelector(".sbcs-feature-text");
  var lines = {};
  root.querySelectorAll(".sbcs-feature-fallback dt").forEach(function (dt, i) {
    var dd = root.querySelectorAll(".sbcs-feature-fallback dd")[i];
    if (features[i] && dd) { lines[features[i].dataset.feature] = dd.textContent; }
  });

  function track(name, detail) {
    try {
      if (typeof window.gtag === "function") {
        window.gtag("event", name, detail || {});
      } else if (window.dataLayer && typeof window.dataLayer.push === "function") {
        window.dataLayer.push(Object.assign({event: name}, detail || {}));
      } else if (typeof window.sbTrack === "function") {
        window.sbTrack(name, detail || {});
      }
    } catch (e) { /* analytics must never break the page */ }
  }

  function show(feature) {
    features.forEach(function (b) {
      b.classList.toggle("is-active", b === feature);
    });
    if (!wrap || !line) { return; }
    if (feature) {
      line.textContent = lines[feature.dataset.feature] || line.textContent;
      wrap.classList.add("is-showing");
    } else {
      wrap.classList.remove("is-showing");
    }
  }

  /* Whatever still holds focus keeps its line up. */
  function release() {
    var held = null;
    features.forEach(function (b) { if (b === document.activeElement) { held = b; } });
    show(held);
  }

  var seenFeature = {};
  features.forEach(function (button) {
    var id = button.dataset.feature;
    function pick(source) {
      show(button);
      if (seenFeature[id + source]) { return; }
      seenFeature[id + source] = true;
      track("creative_feature_selected", {feature: id, via: source});
    }
    button.addEventListener("mouseenter", function () { pick("hover"); });
    button.addEventListener("focus", function () { pick("focus"); });
    button.addEventListener("click", function () { pick("click"); });
    button.addEventListener("mouseleave", release);
    button.addEventListener("blur", function () { window.setTimeout(release, 0); });
  });

  var toggle = document.getElementById("sbcs-workflow-btn");
  var workflow = document.getElementById("sbcs-workflow");
  if (toggle && workflow) {
    toggle.addEventListener("click", function () {
      var opening = workflow.hasAttribute("hidden");
      if (opening) { workflow.removeAttribute("hidden"); }
      else { workflow.setAttribute("hidden", ""); }
      toggle.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) { track("creative_workflow_opened", {}); }
    });
  }

  var cta = root.querySelector(".sbcs-cta");
  if (cta) {
    cta.addEventListener("click", function () {
      track("creative_studio_opened", {href: cta.getAttribute("href")});
    });
  }

  /* How far the label row was swiped on a phone, once it stops. */
  var row = root.querySelector(".sbcs-feature-row");
  if (row) {
    var timer = null, furthest = 0, reported = -1;
    row.addEventListener("scroll", function () {
      var width = (features[0] && features[0].getBoundingClientRect().width) || 1;
      var index = Math.round(row.scrollLeft / width);
      if (index > furthest) { furthest = index; }
      if (timer) { window.clearTimeout(timer); }
      timer = window.setTimeout(function () {
        if (furthest > 0 && furthest !== reported) {
          reported = furthest;
          track("creative_features_swiped", {furthest: furthest});
        }
      }, 400);
    }, {passive: true});
  }

  /* Section viewed, once. */
  if ("IntersectionObserver" in window) {
    var seen = false;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && !seen) {
          seen = true;
          track("creative_studio_section_viewed", {});
          obs.disconnect();
        }
      });
    }, {threshold: 0.25});
    obs.observe(root);
  }
})();
