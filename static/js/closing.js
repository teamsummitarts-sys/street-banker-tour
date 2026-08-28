/* 11.5 + Section 12 — the trust band and the closing frame.
 *
 * Both read with this file absent: everything is text and links. This is
 * measurement only, plus one thing worth doing — carrying the Artist EQ
 * mix the visitor set at the top of the page into the starting plan at
 * the bottom, so the last button knows what the first console was told.
 */
(function () {
  "use strict";

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

  var band = document.getElementById("artist-control");
  if (band) {
    var link = band.querySelector(".sbtb-link");
    if (link) {
      link.addEventListener("click", function () {
        track("trust_policy_opened", {});
      });
    }
    if ("IntersectionObserver" in window) {
      var bandSeen = false;
      var bandObs = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting && !bandSeen) {
            bandSeen = true;
            track("trust_band_viewed", {});
            bandObs.disconnect();
          }
        });
      }, {threshold: 0.4});
      bandObs.observe(band);
    }
  }

  var root = document.getElementById("closing");
  if (!root) { return; }

  /* The mix the visitor set in the Artist EQ, carried down to the last
     button so the starting plan opens on what they already chose rather
     than on a default. Values and a preset id - nothing about a person. */
  var primary = root.querySelector(".sbcl-cta");
  if (primary) {
    try {
      var raw = window.localStorage.getItem("streetBankerArtistEq");
      var saved = raw ? JSON.parse(raw) : null;
      if (saved && saved.values) {
        var parts = [];
        Object.keys(saved.values).forEach(function (key) {
          var n = Number(saved.values[key]);
          if (isFinite(n)) { parts.push(key + "=" + encodeURIComponent(n)); }
        });
        if (typeof saved.preset === "string") {
          parts.push("preset=" + encodeURIComponent(saved.preset));
        }
        if (parts.length) {
          primary.setAttribute("href",
            primary.getAttribute("href").split("?")[0] + "?" + parts.join("&"));
          primary.dataset.carried = "eq";
        }
      }
    } catch (e) { /* private mode: the plan just starts from the default */ }

    primary.addEventListener("click", function () {
      track("build_my_street_banker_clicked",
            {carried: primary.dataset.carried === "eq" ? "artist_eq" : "none"});
    });
  }

  var secondary = root.querySelector(".sbcl-cta-2");
  if (secondary) {
    secondary.addEventListener("click", function () {
      track("explore_the_platform_clicked", {href: secondary.getAttribute("href")});
    });
  }

  if ("IntersectionObserver" in window) {
    var seen = false;
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && !seen) {
          seen = true;
          track("closing_section_viewed", {});
          obs.disconnect();
        }
      });
    }, {threshold: 0.25});
    obs.observe(root);
  }
})();
