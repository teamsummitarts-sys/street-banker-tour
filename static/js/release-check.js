/* Live counting for the release-readiness check.
 *
 * The page is correct with this file absent: the form posts, the server
 * counts, and the readout comes back rendered. This only saves the round
 * trip and keeps the URL shareable.
 */
(function () {
  "use strict";

  var form = document.getElementById("sbrc-form");
  if (!form) { return; }

  var boxes = Array.prototype.slice.call(form.querySelectorAll(".sbrc-box"));
  var stateEl = document.getElementById("sbrc-state");
  var doneEl = document.getElementById("sbrc-done");
  var fillEl = document.getElementById("sbrc-fill");
  if (!boxes.length || !stateEl || !doneEl || !fillEl) { return; }

  var total = boxes.length;

  /* Same four bands the server uses. Completion only - none of these
     says anything about the record, only about the paperwork. */
  function stateFor(done) {
    if (done === total) { return "Delivery ready"; }
    if (done >= Math.ceil(total * 0.75)) { return "Ready for review"; }
    if (done >= Math.ceil(total * 0.35)) { return "Needs information"; }
    return "Setup incomplete";
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

  var started = false;

  function update() {
    var done = boxes.filter(function (b) { return b.checked; }).length;
    doneEl.textContent = String(done);
    stateEl.textContent = stateFor(done);
    fillEl.style.width = (total ? (done / total) * 100 : 0) + "%";

    /* The URL carries the answer so the page can be shared or reloaded
       without losing it. Replace rather than push: forty checkboxes
       should not become forty history entries. */
    var picked = boxes.filter(function (b) { return b.checked; })
                      .map(function (b) { return encodeURIComponent(b.value); });
    var url = window.location.pathname + (picked.length ? "?have=" + picked.join("&have=") : "");
    try { window.history.replaceState(null, "", url); } catch (e) {}

    if (!started) {
      started = true;
      track("release_check_started", {});
    }
  }

  boxes.forEach(function (b) { b.addEventListener("change", update); });

  var submit = form.querySelector("button[type=submit]");
  if (submit) { submit.style.display = "none"; }

  update();
})();
