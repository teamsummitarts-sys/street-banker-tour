/* One beat's page: its audio, its private links, and the licence
 * generator.
 *
 * The presets below are starting points a producer edits, not contracts
 * this app is standing behind. They say plainly what each shape gives
 * away, because the difference between a lease and an exclusive is the
 * thing producers most often get wrong on a handshake.
 */
(function () {
  "use strict";
  var D = window.__btDetail || {};
  var shares = D.shares || [], audio = D.audio || null;
  function $(id) { return document.getElementById(id); }
  function say(msg) {
    var live = $("bt-live");
    if (!live) return;
    live.textContent = "";
    setTimeout(function () { live.textContent = msg; }, 30);
  }

  // ---------- player ----------
  (function player() {
    var canvas = $("bt-d-wave");
    if (!canvas || !audio) return;
    var el = new Audio(), playing = false, raf = null;
    el.preload = "none";
    el.src = "/beats/" + D.beatId + "/stream";
    var peaks = audio.peaks || [], dur = audio.duration || 0;

    function clock(t) {
      t = Math.max(0, t || 0);
      var m = Math.floor(t / 60), s = Math.floor(t % 60);
      return m + ":" + (s < 10 ? "0" : "") + s;
    }
    function draw(p) {
      var dpr = window.devicePixelRatio || 1;
      var w = canvas.clientWidth || 300, h = canvas.clientHeight || 52;
      if (canvas.width !== Math.round(w * dpr)) {
        canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      }
      var g = canvas.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      if (!peaks.length) { g.fillStyle = "rgba(238,232,220,0.3)"; g.fillRect(0, h / 2 - 1, w, 2); return; }
      var mid = h / 2, step = w / peaks.length, played = w * (p || 0);
      for (var i = 0; i < peaks.length; i++) {
        var x = i * step, amp = Math.max(1, peaks[i] * (h * 0.45));
        g.fillStyle = x <= played ? "#E8B950" : "rgba(238,232,220,0.32)";
        g.fillRect(x, mid - amp, Math.max(1, step - 0.6), amp * 2);
      }
    }
    function tick() {
      if (!playing) return;
      var d = dur || el.duration || 0;
      draw(d ? el.currentTime / d : 0);
      $("bt-d-clock").textContent = clock(el.currentTime);
      raf = requestAnimationFrame(tick);
    }
    $("bt-d-play").addEventListener("click", function () {
      if (playing) {
        el.pause(); playing = false;
        this.innerHTML = "&#9654;"; this.setAttribute("aria-pressed", "false");
        if (raf) cancelAnimationFrame(raf);
        return;
      }
      var btn = this;
      el.play().then(function () {
        playing = true;
        btn.innerHTML = "&#10073;&#10073;"; btn.setAttribute("aria-pressed", "true");
        tick();
      }).catch(function () { say("That would not play."); });
    });
    el.addEventListener("ended", function () {
      playing = false;
      $("bt-d-play").innerHTML = "&#9654;";
      $("bt-d-play").setAttribute("aria-pressed", "false");
      if (raf) cancelAnimationFrame(raf);
      draw(0); $("bt-d-clock").textContent = clock(0);
    });
    canvas.addEventListener("click", function (e) {
      var d = dur || el.duration || 0;
      if (!d) return;
      var r = canvas.getBoundingClientRect();
      el.currentTime = d * Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
      draw(el.currentTime / d);
      $("bt-d-clock").textContent = clock(el.currentTime);
    });
    window.addEventListener("resize", function () {
      var d = dur || el.duration || 0;
      draw(d ? el.currentTime / d : 0);
    });
    draw(0);

    // Removing audio also kills every link that was playing it, so say so
    // before doing it rather than after.
    $("bt-d-remove").addEventListener("click", function () {
      var live = shares.length;
      var warn = live
        ? "Remove this audio? " + live + " live link" + (live === 1 ? "" : "s")
          + " will have nothing to play."
        : "Remove this audio from the beat?";
      if (!window.confirm(warn)) return;
      fetch("/beats/" + D.beatId + "/audio/delete", {method: "POST"})
        .then(function (r) { return r.json(); })
        .then(function (d) { if (d.ok) location.reload(); });
    });
  })();

  // ---------- private links ----------
  function renderShares() {
    var ul = $("bt-share-list");
    if (!ul) return;
    ul.textContent = "";
    if (!shares.length) {
      var p = document.createElement("li");
      p.className = "bt-hint";
      p.textContent = "No links yet.";
      ul.appendChild(p);
      return;
    }
    shares.forEach(function (s) {
      var li = document.createElement("li");
      li.className = "bt-link";
      var input = document.createElement("input");
      input.className = "bt-input"; input.type = "text"; input.readOnly = true;
      input.value = (D.origin || location.origin) + "/beat/" + s.token;
      input.setAttribute("aria-label", "Private link" + (s.label ? " for " + s.label : ""));
      input.addEventListener("focus", function () { this.select(); });
      var who = document.createElement("span");
      who.className = "bt-hint";
      who.textContent = (s.label || "no label")
        + (s.expires ? " · lapses " + s.expires.slice(0, 10) : " · no expiry")
        + " · " + s.plays + " play" + (s.plays === 1 ? "" : "s");
      var kill = document.createElement("button");
      kill.type = "button"; kill.className = "bt-btn bt-btn--ghost bt-btn--small";
      kill.textContent = "Revoke";
      kill.setAttribute("aria-label", "Revoke the link" + (s.label ? " for " + s.label : ""));
      kill.addEventListener("click", function () {
        fetch("/beat-link/" + s.token + "/revoke", {method: "POST"})
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (!d.ok) return;
            shares = shares.filter(function (x) { return x.token !== s.token; });
            renderShares();
            say("Link revoked — it opens to a dead page now.");
          });
      });
      li.appendChild(input); li.appendChild(who); li.appendChild(kill);
      ul.appendChild(li);
    });
  }
  if ($("bt-share-new")) {
    $("bt-share-new").addEventListener("click", function () {
      if (!audio) {
        $("bt-share-status").textContent = "There is no audio on this beat yet, so a link would have nothing to play.";
        say($("bt-share-status").textContent);
        return;
      }
      fetch("/beats/" + D.beatId + "/share", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({label: $("bt-share-label").value,
                              days: parseInt($("bt-share-days").value, 10) || 0})
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (!d.ok) { $("bt-share-status").textContent = "Could not make a link."; return; }
        shares = d.shares || shares;
        $("bt-share-label").value = "";
        $("bt-share-status").textContent = "Link ready — copy it from the list.";
        renderShares();
        say("Private link created");
      });
    });
  }
  renderShares();

  // ---------- licence generator ----------
  var PRESETS = {
    lease: {
      type: "lease", territory: "Worldwide", term: "2 years", fee: "49.99", split: 50,
      terms: "NON-EXCLUSIVE LEASE\n\n" +
        "The producer keeps ownership of the beat and may licence it to other artists.\n\n" +
        "You may: record and release one (1) song using this beat; distribute it on streaming and download platforms; perform it live; make one music video.\n\n" +
        "You may not: register the beat with a content-identification system; claim ownership of the underlying composition beyond your own contribution; resell or sub-licence the beat itself.\n\n" +
        "Credit: the producer must be credited as producer on every release, in the form they specify.\n\n" +
        "Term: this licence runs for the term above from the date of signature. It ends if the fee is not paid."
    },
    premium: {
      type: "lease", territory: "Worldwide", term: "5 years", fee: "149.99", split: 50,
      terms: "PREMIUM NON-EXCLUSIVE LEASE\n\n" +
        "The producer keeps ownership of the beat and may licence it to other artists.\n\n" +
        "You may: record and release up to three (3) songs using this beat; distribute them on streaming and download platforms; perform them live; make music videos; use the recordings in paid promotion.\n\n" +
        "You may not: register the beat with a content-identification system; claim ownership of the underlying composition beyond your own contribution; resell or sub-licence the beat itself.\n\n" +
        "Stems: the producer supplies track stems on request.\n\n" +
        "Credit: the producer must be credited as producer on every release, in the form they specify.\n\n" +
        "Term: this licence runs for the term above from the date of signature. It ends if the fee is not paid."
    },
    exclusive: {
      type: "exclusive", territory: "Worldwide", term: "In perpetuity", fee: "1000.00", split: 50,
      terms: "EXCLUSIVE LICENCE\n\n" +
        "On signature and payment, the producer stops licensing this beat to anybody else and removes it from sale. Licences already granted before this date stay in force — ask the producer which exist before you sign.\n\n" +
        "You may: record and release recordings using this beat without a song limit; distribute, perform, synchronise to visual media, and use in paid promotion.\n\n" +
        "The producer keeps: authorship of the underlying composition and the producer share above, collected through their publisher or PRO.\n\n" +
        "You may not: resell or sub-licence the beat itself as a beat.\n\n" +
        "Credit: the producer must be credited as producer on every release, in the form they specify.\n\n" +
        "Term: as stated above, worldwide unless a territory is named."
    },
    work_for_hire: {
      type: "work_for_hire", territory: "Worldwide", term: "In perpetuity", fee: "2500.00", split: 0,
      terms: "WORK FOR HIRE\n\n" +
        "The producer assigns their rights in this beat to the client for the fee above. The client owns the master and the producer's share of the composition.\n\n" +
        "Read this before signing it as a producer: a work for hire gives up the back end. If the record earns, the fee above is all of it. Take it when the number is worth more to you than the possibility.\n\n" +
        "Credit: the producer is credited as producer on every release, in the form they specify. Credit is not the same as ownership and survives this assignment.\n\n" +
        "The producer warrants the beat is their original work and contains no uncleared samples."
    },
    free: {
      type: "free", territory: "Worldwide", term: "1 year", fee: "0.00", split: 50,
      terms: "FREE / PROMOTIONAL USE\n\n" +
        "No fee. The producer keeps ownership and may licence this beat to anybody else at any time.\n\n" +
        "You may: release one (1) non-commercial song using this beat — a loosie, a mixtape cut, a demo — and perform it live.\n\n" +
        "You may not: monetise the recording, distribute it to paid streaming platforms, or register it with a content-identification system, without first agreeing a paid licence.\n\n" +
        "Credit: the producer must be credited as producer wherever it appears, in the form they specify.\n\n" +
        "Term: one year from signature, after which a paid licence is needed to keep it up."
    }
  };

  var modal = $("bt-lic"), scrim = $("bt-scrim"), lastFocus = null;
  function focusables(root) {
    // type=hidden is an input and is NOT focusable — the form's action
    // field is the first one in this dialog, so a naive querySelector
    // left focus stranded outside the modal it had just opened.
    return Array.prototype.filter.call(
      root.querySelectorAll("input, textarea, select, button, a[href]"),
      function (el) { return el.type !== "hidden" && !el.disabled && el.offsetParent !== null; });
  }
  function openLic() {
    lastFocus = document.activeElement;
    modal.hidden = false; scrim.hidden = false;
    var f = focusables(modal);
    if (f.length) f[0].focus();
    document.addEventListener("keydown", licKeys);
  }
  function closeLic() {
    modal.hidden = true; scrim.hidden = true;
    document.removeEventListener("keydown", licKeys);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function licKeys(e) {
    if (e.key === "Escape") { closeLic(); return; }
    if (e.key !== "Tab") return;
    var f = focusables(modal);
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
    else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
  }
  if ($("bt-lic-open")) $("bt-lic-open").addEventListener("click", openLic);
  if ($("bt-lic-close")) $("bt-lic-close").addEventListener("click", closeLic);
  if ($("bt-lic-cancel")) $("bt-lic-cancel").addEventListener("click", closeLic);
  if (scrim) scrim.addEventListener("click", closeLic);

  Array.prototype.forEach.call(document.querySelectorAll("[data-preset]"), function (b) {
    b.addEventListener("click", function () {
      var p = PRESETS[b.getAttribute("data-preset")];
      if (!p) return;
      // Never silently discard wording somebody has been editing.
      var written = ($("bt-lic-terms").value || "").trim();
      var fromPreset = Object.keys(PRESETS).some(function (k) {
        return PRESETS[k].terms.trim() === written;
      });
      if (written && !fromPreset &&
          !window.confirm("Replace the terms you have written with this preset?")) return;
      $("bt-lic-type").value = p.type;
      $("bt-lic-territory").value = p.territory;
      $("bt-lic-term").value = p.term;
      $("bt-lic-fee").value = p.fee;
      $("bt-lic-split").value = String(p.split);
      $("bt-lic-terms").value = p.terms;
      Array.prototype.forEach.call(document.querySelectorAll("[data-preset]"), function (o) {
        o.setAttribute("aria-pressed", o === b ? "true" : "false");
      });
      say(b.textContent.trim() + " loaded — edit anything before you issue it.");
    });
  });
})();
