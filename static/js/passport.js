/* Section 11 — Metadata Passport + Rights.
 *
 * The section reads with this file absent: all seven records are printed
 * with their descriptions and the CTA is a link. What is left here is the
 * connected-data disclosure and measurement.
 *
 * The category selection went with the example passport detail it drove.
 * The seven are a list now, not seven controls that change a panel.
 *
 * No credit, share, identifier, agreement or file name exists in this
 * section to send anywhere. The events carry category slugs only.
 */
(function () {
  "use strict";

  var root = document.getElementById("metadata-passport");
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

  var connectBtn = document.getElementById("sbmp-connect-btn");
  var connect = document.getElementById("sbmp-connect");
  if (connectBtn && connect) {
    connectBtn.addEventListener("click", function () {
      var opening = connect.hasAttribute("hidden");
      if (opening) { connect.removeAttribute("hidden"); }
      else { connect.setAttribute("hidden", ""); }
      connectBtn.setAttribute("aria-expanded", opening ? "true" : "false");
      if (opening) {
        connect.scrollIntoView({block: "nearest",
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
            ? "auto" : "smooth"});
        track("passport_connected_example_viewed", {});
      }
    });
  }

  var cta = root.querySelector(".sbmp-cta");
  if (cta) {
    cta.addEventListener("click", function () {
      track("passport_open_clicked", {href: cta.getAttribute("href")});
    });
  }

  var trust = root.querySelector(".sbmp-trust-link");
  if (trust) {
    trust.addEventListener("click", function () {
      track("passport_trust_link_clicked", {});
    });
  }

  /* Section viewed, once. */
  if ("IntersectionObserver" in window) {
    var viewed = false;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && !viewed) {
          viewed = true;
          track("passport_section_viewed", {});
          obs.disconnect();
        }
      });
    }, {threshold: 0.2});
    obs.observe(root);
  }
})();
