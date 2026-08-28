/* Section 6 — three lanes, one system.
 *
 * The section reads and links with this file absent: the summaries are
 * anchors, the comparison is in the document, and hover on a summary is
 * CSS. What is here is the part that crosses between the two - pointing
 * at a summary lights its channel on the unit - plus the comparison
 * toggle and measurement.
 */
(function () {
  "use strict";

  var root = document.getElementById("lanes");
  if (!root) { return; }

  var unit = root.querySelector(".sblane-unit");
  var summaries = [].slice.call(root.querySelectorAll(".sblane-summary"));
  if (!summaries.length) { return; }

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

  function select(lane) {
    summaries.forEach(function (s) {
      s.classList.toggle("is-active", !!lane && s.dataset.lane === lane);
    });
    if (!unit) { return; }
    if (lane) { unit.dataset.active = lane; } else { delete unit.dataset.active; }
  }

  /* Whatever still holds focus keeps the channel lit, so moving the
     mouse away does not darken the lane a keyboard reader is on. */
  function release() {
    var held = null;
    summaries.forEach(function (s) {
      if (s.contains(document.activeElement)) { held = s.dataset.lane; }
    });
    select(held);
  }

  var hovered = {};
  summaries.forEach(function (summary) {
    var lane = summary.dataset.lane;
    var link = summary.querySelector(".sblane-link");

    summary.addEventListener("mouseenter", function () {
      select(lane);
      if (hovered[lane]) { return; }
      hovered[lane] = true;
      track("lane_hovered", {lane: lane});
    });
    summary.addEventListener("mouseleave", release);

    if (link) {
      link.addEventListener("focus", function () {
        select(lane);
        track("lane_focused", {lane: lane});
      });
      link.addEventListener("blur", function () { window.setTimeout(release, 0); });
      link.addEventListener("click", function () {
        track("lane_clicked", {lane: lane, href: link.getAttribute("href")});
      });
    }
  });

  var compare = document.getElementById("sblane-compare");
  var comparison = document.getElementById("sblane-comparison");
  if (compare && comparison) {
    compare.addEventListener("click", function () {
      var open = comparison.hasAttribute("hidden");
      if (open) { comparison.removeAttribute("hidden"); }
      else { comparison.setAttribute("hidden", ""); }
      compare.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        comparison.scrollIntoView({block: "nearest",
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto" : "smooth"});
        track("lane_comparison_opened", {});
      }
    });
  }

  var primary = root.querySelector(".sblane-primary");
  if (primary) {
    primary.addEventListener("click", function () {
      track("find_my_lane_clicked", {href: primary.getAttribute("href")});
    });
  }

  /* Section viewed, once. */
  if ("IntersectionObserver" in window) {
    var seen = false;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && !seen) {
          seen = true;
          track("lanes_section_viewed", {});
          obs.disconnect();
        }
      });
    }, {threshold: 0.25});
    obs.observe(root);
  }
})();
