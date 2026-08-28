/* Section 10 — Global Distribution.
 *
 * The section reads with this file absent: the heading, the partner line
 * and the five capabilities are all printed, and both CTAs are plain
 * links. What is left here is measurement.
 *
 * The five-stage workflow reveal used to live here. The workflow moved
 * off the homepage to /distribution, so the stage handling went with it,
 * along with the example-checklist observer.
 *
 * No release metadata, contributor name, audio detail or ownership
 * information exists in this section to send anywhere.
 */
(function () {
  "use strict";

  var root = document.getElementById("global-distribution");
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

  /* The two CTAs, which now go to two different places: the release
     readiness check and the informational guide. */
  var primary = root.querySelector(".sbds-cta");
  if (primary) {
    primary.addEventListener("click", function () {
      track("distribute_now_clicked", {href: primary.getAttribute("href")});
    });
  }

  var guide = root.querySelector(".sbds-guide");
  if (guide) {
    guide.addEventListener("click", function () {
      track("distribution_guide_clicked", {href: guide.getAttribute("href")});
    });
  }

  /* Section viewed, once. */
  if ("IntersectionObserver" in window) {
    var seen = false;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && !seen) {
          seen = true;
          track("distribution_section_viewed", {});
          obs.disconnect();
        }
      });
    }, {threshold: 0.2});
    obs.observe(root);
  }
})();
