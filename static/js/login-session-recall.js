/* /login — Session Recall behaviours.

   Everything here decorates a page that already works without it: the
   login form posts on its own, the request-access form posts on its own,
   and the mix rack simply stays hidden if this script never runs. */
(function () {
  "use strict";

  var STORAGE_KEY = "streetBankerArtistSignalProfile";
  var LEGACY_STORAGE_KEY = "streetBankerArtistEq";

  function track(name, detail) {
    try {
      if (typeof window.gtag === "function") {
        window.gtag("event", name, detail || {});
      } else if (window.dataLayer && typeof window.dataLayer.push === "function") {
        window.dataLayer.push(Object.assign({ event: name }, detail || {}));
      } else if (typeof window.sbTrack === "function") {
        window.sbTrack(name, detail || {});
      }
    } catch (e) { /* never break the page for analytics */ }
  }
  track("login_page_viewed", {});

  /* --- show/hide password ---------------------------------------------- */
  var pw = document.getElementById("lsr-password");
  var pwToggle = document.getElementById("lsr-pw-toggle");
  if (pw && pwToggle) {
    pwToggle.addEventListener("click", function () {
      var showing = pw.type === "text";
      pw.type = showing ? "password" : "text";
      pwToggle.setAttribute("aria-pressed", showing ? "false" : "true");
      pwToggle.setAttribute("aria-label",
        showing ? "Show password" : "Hide password");
      pw.focus();
    });
  }

  /* --- submit-once loading state --------------------------------------- */
  var loginForm = document.getElementById("lsr-login-form");
  var submitBtn = document.getElementById("lsr-submit");
  if (loginForm && submitBtn) {
    loginForm.addEventListener("submit", function () {
      if (submitBtn.disabled) { return; }
      track("login_submitted", {});
      /* Disable after this tick so the value still posts. */
      setTimeout(function () {
        submitBtn.disabled = true;
        submitBtn.textContent = "RECALLING…";
      }, 0);
    });
  }

  /* --- workspace selector ---------------------------------------------- */
  var DEMO_EMAILS = {
    artist: "demo-artist@streetbanker.io",
    pro: "demo-pro@streetbanker.io",
    label: "demo@streetbanker.io",
    fan: "demo-fan@streetbanker.io"
  };
  var radios = Array.prototype.slice.call(
    document.querySelectorAll('input[name="lsr-workspace"]'));
  var demoEmail = document.getElementById("lsr-demo-email");
  var requestWorkspace = document.getElementById("lsr-request-workspace");

  function applyWorkspace() {
    var picked = "artist";
    radios.forEach(function (r) { if (r.checked) { picked = r.value; } });
    if (demoEmail) { demoEmail.value = DEMO_EMAILS[picked] || DEMO_EMAILS.artist; }
    if (requestWorkspace) { requestWorkspace.value = picked; }
    try { sessionStorage.setItem("sbLoginWorkspace", picked); } catch (e) {}
  }
  radios.forEach(function (r) {
    r.addEventListener("change", function () {
      applyWorkspace();
      track("login_demo_workspace_selected", { workspace: r.value });
    });
  });
  /* restore the selection for this browsing session */
  try {
    var savedWs = sessionStorage.getItem("sbLoginWorkspace");
    if (savedWs) {
      radios.forEach(function (r) { r.checked = (r.value === savedWs); });
    }
  } catch (e) {}
  applyWorkspace();

  /* "Remember this device" remembers the choice too. The box ships
     ticked — it controls a 31-day session, and a sign-in without it
     lasts only until the browser closes — so the only thing worth
     restoring here is an explicit opt-OUT. Reading "1" and ticking would
     be redundant now, and would also re-tick the box for somebody who
     had deliberately turned it off. Stored in this browser, nowhere
     else. */
  var remember = document.getElementById("lsr-remember");
  if (remember) {
    try {
      if (localStorage.getItem("sbRemember") === "0") { remember.checked = false; }
    } catch (e) {}
    remember.addEventListener("change", function () {
      try {
        localStorage.setItem("sbRemember", remember.checked ? "1" : "0");
      } catch (e) {}
    });
  }

  var openForm = document.getElementById("lsr-open-form");
  if (openForm) {
    openForm.addEventListener("submit", function () {
      track("login_demo_opened", {});
    });
  }

  /* flip between request-access and have-password states */
  var requestForm = document.getElementById("lsr-request-form");
  var havePw = document.getElementById("lsr-have-pw");
  var needPw = document.getElementById("lsr-need-pw");
  if (havePw && requestForm && openForm) {
    havePw.addEventListener("click", function () {
      requestForm.hidden = true;
      openForm.hidden = false;
      var f = document.getElementById("lsr-demo-pw");
      if (f) { f.focus(); }
    });
  }
  if (needPw && requestForm && openForm) {
    needPw.addEventListener("click", function () {
      openForm.hidden = true;
      requestForm.hidden = false;
      var f = document.getElementById("lsr-lead-email");
      if (f) { f.focus(); }
    });
  }

  /* --- YOUR MIX IS READY ------------------------------------------------ */
  function readMix() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY) ||
                window.localStorage.getItem(LEGACY_STORAGE_KEY);
      if (!raw) { return null; }
      var mix = JSON.parse(raw);
      if (!mix || typeof mix !== "object") { return null; }
      if (!mix.recommendedLane || !mix.priorities) { return null; }
      if (!Array.isArray(mix.recommendedModules)) { return null; }
      return mix;
    } catch (e) { return null; }
  }

  var LABELS = {
    rightsSplits: "Rights & Splits", royaltyRecovery: "Royalty Recovery",
    distribution: "Distribution", metadata: "Metadata",
    releaseStrategy: "Release Strategy", content: "Content",
    audienceGrowth: "Audience Growth", fanOwnership: "Fan Ownership",
    touringLive: "Touring & Live", syncLicensing: "Sync & Licensing",
    funding: "Funding", brand: "Brand", partnerships: "Partnerships",
    catalogValue: "Catalog Value", longTermVision: "Long-Term Vision"
  };

  var mixRack = document.getElementById("lsr-mix");
  var mix = readMix();
  if (mixRack && mix) {
    var laneEl = document.getElementById("lsr-mix-lane");
    if (laneEl) { laneEl.textContent = mix.recommendedLane; }

    var priEl = document.getElementById("lsr-mix-priorities");
    if (priEl) {
      Object.keys(mix.priorities)
        .filter(function (k) { return typeof mix.priorities[k] === "number"; })
        .sort(function (a, b) { return mix.priorities[b] - mix.priorities[a]; })
        .slice(0, 3)
        .forEach(function (k) {
          var li = document.createElement("li");
          li.textContent = LABELS[k] || k;
          priEl.appendChild(li);
        });
    }

    var toolsEl = document.getElementById("lsr-mix-tools");
    if (toolsEl) {
      mix.recommendedModules.slice(0, 4).forEach(function (name) {
        var li = document.createElement("li");
        li.textContent = String(name);
        toolsEl.appendChild(li);
      });
    }

    mixRack.hidden = false;
    track("login_artist_eq_recall_viewed", { lane: mix.recommendedLane });

    var live = document.getElementById("lsr-live");
    if (live) {
      live.textContent = "Your saved Artist EQ mix is ready: " +
        mix.recommendedLane + ".";
    }

    var buildBtn = document.getElementById("lsr-mix-build");
    if (buildBtn) {
      buildBtn.addEventListener("click", function () {
        track("login_artist_eq_program_loaded", { lane: mix.recommendedLane });
        /* localStorage rides along to signup on the same origin - no
           copying needed; the link just navigates. */
      });
    }
  }
})();
