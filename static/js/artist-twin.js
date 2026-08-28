/* Section 5 — the AI Artist Twin.
 *
 * The rows are native <details>: they open, close and take the keyboard
 * with this file absent. Everything here is the part the platform does
 * not do - keeping one row open at a time, wiring "See how it thinks",
 * keeping aria-expanded honest - plus measurement.
 *
 * Nothing an artist typed, uploaded or was told goes into an event. The
 * events carry row ids from the config and nothing else.
 */
(function () {
  "use strict";

  var root = document.getElementById("artist-twin-section");
  if (!root) { return; }

  var rows = [].slice.call(root.querySelectorAll(".sbtw-row"));
  if (!rows.length) { return; }

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

  function sync(row) {
    var summary = row.querySelector(".sbtw-summary");
    if (summary) { summary.setAttribute("aria-expanded", row.open ? "true" : "false"); }
  }

  rows.forEach(function (row) {
    sync(row);
    row.addEventListener("toggle", function () {
      sync(row);
      if (!row.open) { return; }
      rows.forEach(function (other) {
        if (other !== row && other.open) { other.open = false; sync(other); }
      });
      track("artist_twin_row_expanded", {row: row.dataset.row});
    });
  });

  /* "See how it thinks" opens the row whose reasoning is the clearest
     worked example, rather than saying anything new. */
  var explain = document.getElementById("sbtw-explain");
  if (explain) {
    explain.addEventListener("click", function () {
      var target = document.getElementById(explain.getAttribute("aria-controls"));
      if (!target) { return; }
      target.open = true;
      var summary = target.querySelector(".sbtw-summary");
      if (summary) { summary.focus({preventScroll: true}); }
      target.scrollIntoView({block: "nearest",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto" : "smooth"});
      track("artist_twin_reasoning_opened", {});
    });
  }

  var build = root.querySelector(".sbtw-cta");
  if (build) {
    build.addEventListener("click", function () {
      track("artist_twin_build_clicked", {href: build.getAttribute("href")});
    });
  }

  var trust = root.querySelector(".sbtw-trust");
  if (trust) {
    trust.addEventListener("click", function () {
      track("artist_twin_ai_trust_clicked", {});
    });
  }

  /* Section viewed, once. */
  if ("IntersectionObserver" in window) {
    var seen = false;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && !seen) {
          seen = true;
          track("artist_twin_section_viewed", {});
          obs.disconnect();
        }
      });
    }, {threshold: 0.25});
    obs.observe(root);
  }
})();
