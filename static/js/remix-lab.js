/* Remix Lab — the brief builder, preview build.
 *
 * What this file does: gates the upload behind the two rights
 * confirmations, screens reference text for imitation requests, builds
 * the remixLabSubmission object the backend will eventually receive,
 * and reveals the worked example.
 *
 * What it deliberately does not do: transmit anything. No fetch, no
 * beacon with content, no storage of the file. The chosen audio never
 * leaves the browser in this preview, and the page says so. When
 * generation is wired, the submission object below is the contract —
 * and the banned-pattern screen MUST run again server-side
 * (remix_lab_config.check_reference_text); this copy is convenience,
 * not enforcement.
 */
(function () {
  "use strict";

  var root = document.getElementById("sbrl-form");
  var cfgEl = document.getElementById("sbrl-config");
  if (!root || !cfgEl) { return; }

  var CFG;
  try { CFG = JSON.parse(cfgEl.textContent); } catch (e) { return; }

  var PATTERNS = (CFG.patterns || []).map(function (p) {
    try { return new RegExp(p, "i"); } catch (e) { return null; }
  }).filter(Boolean);

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

  /* --- the rights gate --------------------------------------------------- */
  var ownBox = document.getElementById("sbrl-rights-own");
  var likenessBox = document.getElementById("sbrl-rights-likeness");
  var drop = document.getElementById("sbrl-drop");
  var fileInput = document.getElementById("sbrl-file");
  var uploadBtn = document.getElementById("sbrl-upload-btn");
  var fileName = document.getElementById("sbrl-file-name");

  function gateOpen() {
    return !!(ownBox && ownBox.checked && likenessBox && likenessBox.checked);
  }

  var gateNoted = false;
  function applyGate() {
    var open = gateOpen();
    if (fileInput) { fileInput.disabled = !open; }
    if (drop) { drop.classList.toggle("is-locked", !open); }
    if (uploadBtn) { uploadBtn.setAttribute("aria-disabled", open ? "false" : "true"); }
    if (open && !gateNoted) {
      gateNoted = true;
      track("remix_lab_rights_confirmed", {});
    }
    /* Unchecking after choosing a file revokes the choice: the file was
       only acceptable while the confirmations stood. */
    if (!open && fileInput && fileInput.value) {
      fileInput.value = "";
      chosenFile = null;
      if (fileName) { fileName.textContent = ""; }
    }
  }
  if (ownBox) { ownBox.addEventListener("change", applyGate); }
  if (likenessBox) { likenessBox.addEventListener("change", applyGate); }
  applyGate();

  /* --- the file ---------------------------------------------------------- */
  var chosenFile = null;

  function extOf(name) {
    var i = (name || "").lastIndexOf(".");
    return i < 0 ? "" : name.slice(i).toLowerCase();
  }

  function acceptFile(file) {
    if (!file) { return; }
    var formats = CFG.formats || [];
    if (formats.indexOf(extOf(file.name)) === -1) {
      if (fileName) {
        fileName.textContent = "That file type is not supported — use " +
          formats.join(", ") + ".";
      }
      chosenFile = null;
      return;
    }
    if (file.size > (CFG.max_mb || 250) * 1024 * 1024) {
      if (fileName) {
        fileName.textContent = "That file is over " + (CFG.max_mb || 250) +
          " MB — export a smaller master for the brief.";
      }
      chosenFile = null;
      return;
    }
    chosenFile = file;
    if (fileName) {
      fileName.textContent = file.name + (CFG.engineLive
        ? " — ready."
        : " — ready. Nothing is uploaded in this preview.");
    }
    track("remix_lab_track_selected", {ext: extOf(file.name)});
  }

  if (fileInput) {
    fileInput.addEventListener("change", function () {
      acceptFile(fileInput.files && fileInput.files[0]);
    });
  }

  if (drop) {
    ["dragenter", "dragover"].forEach(function (type) {
      drop.addEventListener(type, function (event) {
        event.preventDefault();
        if (gateOpen()) { drop.classList.add("is-drag"); }
      });
    });
    ["dragleave", "drop"].forEach(function (type) {
      drop.addEventListener(type, function (event) {
        event.preventDefault();
        drop.classList.remove("is-drag");
      });
    });
    drop.addEventListener("drop", function (event) {
      if (!gateOpen()) { return; }
      var file = event.dataTransfer && event.dataTransfer.files &&
                 event.dataTransfer.files[0];
      acceptFile(file);
    });
  }

  /* --- references, screened as you type ----------------------------------- */
  var refsWrap = document.getElementById("sbrl-refs");
  var addRef = document.getElementById("sbrl-add-ref");
  var warning = document.getElementById("sbrl-warning");

  function refInputs() {
    return [].slice.call(root.querySelectorAll(".sbrl-ref"));
  }

  function violation(text) {
    for (var i = 0; i < PATTERNS.length; i++) {
      var match = PATTERNS[i].exec(text || "");
      if (match) { return match[0]; }
    }
    return null;
  }

  var warned = false;
  function screenRefs() {
    var flagged = false;
    refInputs().forEach(function (input) {
      var hit = violation(input.value);
      input.classList.toggle("is-flagged", !!hit);
      if (hit) { flagged = true; }
    });
    if (warning) { warning.hidden = !flagged; }
    if (flagged && !warned) {
      warned = true;
      /* The event carries no text - only that the screen fired. */
      track("remix_lab_blocked_prompt", {});
    }
    return flagged;
  }

  root.addEventListener("input", function (event) {
    if (event.target && event.target.classList &&
        event.target.classList.contains("sbrl-ref")) {
      screenRefs();
    }
  });

  if (addRef && refsWrap) {
    addRef.addEventListener("click", function () {
      var count = refInputs().length;
      if (count >= (CFG.reference_max || 5)) { return; }
      var input = document.createElement("input");
      input.type = "text";
      input.maxLength = 300;
      input.className = "sbrl-input sbrl-ref";
      input.placeholder = "Another direction (optional)";
      refsWrap.appendChild(input);
      if (refInputs().length >= (CFG.reference_max || 5)) {
        addRef.hidden = true;
      }
      input.focus();
    });
  }

  /* --- submit ------------------------------------------------------------- */
  var results = document.getElementById("sbrl-results");
  var note = document.getElementById("sbrl-submit-note");

  function checkedValue(name) {
    var el = root.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : "";
  }

  function say(message) {
    if (note) { note.textContent = message; }
  }

  root.addEventListener("submit", function (event) {
    /* Every check below blocks the submit either way, so each one cancels
       the event itself. preventDefault() used to sit at the top and cancel
       it unconditionally - which was fine while this page was a preview and
       became a real bug the moment the form got an action: the server never
       saw a submission from any browser with JavaScript on. */
    function stop(message) { event.preventDefault(); say(message); }

    if (!gateOpen()) {
      stop("Confirm both rights statements first — the upload stays off until you do.");
      return;
    }
    if (screenRefs()) {
      stop("Rewrite the flagged reference using musical descriptors, then try again.");
      return;
    }
    if (!chosenFile) {
      stop("Choose an audio file — WAV, MP3, AIFF or FLAC.");
      return;
    }
    var lane = checkedValue("remixLane");
    if (!lane) { stop("Pick a remix lane."); return; }
    var use = checkedValue("targetUse");
    if (!use) { stop("Pick a target use."); return; }

    /* Engine live: hand the form to the browser. The server screens every
       reference again and re-checks both rights confirmations - this screen
       is convenience, that one is enforcement. */
    if (CFG.engineLive) {
      say("Reading your track — this takes a moment.");
      track("remix_lab_brief_submitted", {lane: lane, use: use});
      return;
    }
    event.preventDefault();

    /* The contract the backend will receive when generation is wired.
       Built and held in memory; nothing here transmits it. */
    var submission = {
      audioFile: {name: chosenFile.name, size: chosenFile.size,
                  type: chosenFile.type},
      optionalStems: [].slice.call(
        root.querySelectorAll('input[name="stems"]:checked')
      ).map(function (el) { return el.value; }),
      rightsConfirmed: true,
      noLikenessConfirmed: true,
      referenceDirections: refInputs().map(function (el) {
        return el.value.trim();
      }).filter(Boolean),
      remixLane: lane,
      targetUse: use,
      vibeControls: {
        energy: (root.querySelector('select[name="energy"]') || {}).value,
        tempoDirection: (root.querySelector('select[name="tempoDirection"]') || {}).value,
        vocalTreatment: (root.querySelector('select[name="vocalTreatment"]') || {}).value,
        instrumentation: (root.querySelector('select[name="instrumentation"]') || {}).value,
        riskLevel: (root.querySelector('select[name="riskLevel"]') || {}).value
      }
    };
    window.sbrlSubmission = submission;   /* inspectable, not transmitted */

    /* Preview path only - the live path returned above. */
    say("Example brief shown below — generation is not connected yet.");
    track("remix_lab_brief_started", {lane: lane, use: use});

    if (results) {
      results.hidden = false;
      results.scrollIntoView({
        block: "start",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto" : "smooth"
      });
    }
  });

  /* --- the producer handoff ----------------------------------------------- */
  var producer = document.querySelector(".sbrl-producer a");
  if (producer) {
    producer.addEventListener("click", function () {
      track("remix_lab_producer_review_clicked", {});
    });
  }

  /* --- section viewed, once ------------------------------------------------ */
  if ("IntersectionObserver" in window) {
    var seen = false;
    var target = document.querySelector(".sbrl-hero");
    if (target) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting && !seen) {
            seen = true;
            track("remix_lab_viewed", {});
            observer.disconnect();
          }
        });
      }, {threshold: 0.3});
      observer.observe(target);
    }
  }
})();
