/* Beats — the producer's page.
 *
 * Three jobs, no framework:
 *
 *   upload    Drop N files. Each one is decoded HERE, measured for tempo
 *             and key with the same detector the Rack uses, drawn down to
 *             a peak array, and sent up with the bytes. The audio is
 *             never handed to a third party to be analysed, and the
 *             server never decodes it.
 *
 *   play      One player for the whole list. Clicking a second beat stops
 *             the first, because two beats at once is never what anyone
 *             meant. The waveform is the seek bar.
 *
 *   chrome    A register drawer and the tab strip. Both are plain DOM
 *             with real focus handling — a drawer you cannot escape from
 *             with a keyboard is a trap, not a drawer.
 */
(function () {
  "use strict";
  var TK = window.SBTempoKey;
  var audio = window.__btAudio || {};
  function $(id) { return document.getElementById(id); }
  function say(msg) {
    var live = $("bt-live");
    if (!live) return;
    live.textContent = "";
    setTimeout(function () { live.textContent = msg; }, 30);
  }

  // ---------- tabs ----------
  var TABS = [["bt-tab-catalog", "bt-panel-catalog"],
              ["bt-tab-licences", "bt-panel-licences"],
              ["bt-tab-api", "bt-panel-api"]];
  function showTab(which) {
    TABS.forEach(function (pair) {
      var on = pair[0] === which;
      var tab = $(pair[0]), panel = $(pair[1]);
      if (!tab || !panel) return;
      tab.setAttribute("aria-selected", on ? "true" : "false");
      panel.hidden = !on;
    });
  }
  TABS.forEach(function (pair, i) {
    var tab = $(pair[0]);
    if (!tab) return;
    tab.addEventListener("click", function () { showTab(pair[0]); });
    tab.addEventListener("keydown", function (e) {
      var step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      e.preventDefault();
      var next = $(TABS[(i + step + TABS.length) % TABS.length][0]);
      next.focus(); next.click();
    });
  });

  // ---------- register drawer ----------
  var drawer = $("bt-drawer"), scrim = $("bt-scrim"), lastFocus = null;
  function openDrawer() {
    lastFocus = document.activeElement;
    drawer.hidden = false; scrim.hidden = false;
    $("bt-title").focus();
    document.addEventListener("keydown", drawerKeys);
  }
  function closeDrawer() {
    drawer.hidden = true; scrim.hidden = true;
    document.removeEventListener("keydown", drawerKeys);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }
  function drawerKeys(e) {
    if (e.key === "Escape") { closeDrawer(); return; }
    if (e.key !== "Tab") return;
    // Keep Tab inside the drawer: it is modal, and tabbing out to a page
    // covered by a scrim leaves the focus ring somewhere nobody can see.
    // type=hidden is an input and is NOT focusable. This drawer has none
    // today, but the licence modal did, and the naive selector stranded
    // focus outside the dialog it had just opened.
    var focusable = Array.prototype.filter.call(
      drawer.querySelectorAll("input, textarea, select, button, a[href]"),
      function (el) { return el.type !== "hidden" && !el.disabled && el.offsetParent !== null; });
    if (!focusable.length) return;
    var first = focusable[0], last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
    else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
  }
  if ($("bt-open-drawer")) $("bt-open-drawer").addEventListener("click", openDrawer);
  if ($("bt-empty-cta")) $("bt-empty-cta").addEventListener("click", openDrawer);
  if ($("bt-drawer-close")) $("bt-drawer-close").addEventListener("click", closeDrawer);
  if (scrim) scrim.addEventListener("click", closeDrawer);

  // ---------- waveforms ----------
  function peaksOf(buf, buckets) {
    // Min/max per bucket off the first channel. Two passes would be more
    // faithful on a wide stereo image; one is enough for a 38px strip.
    var ch = buf.getChannelData(0), n = ch.length, out = [];
    var per = Math.max(1, Math.floor(n / buckets));
    for (var i = 0; i < buckets; i++) {
      var start = i * per, end = Math.min(n, start + per), peak = 0;
      for (var j = start; j < end; j += 3) {
        var v = ch[j] < 0 ? -ch[j] : ch[j];
        if (v > peak) peak = v;
      }
      out.push(Math.round(peak * 1000) / 1000);
    }
    return out;
  }

  function drawWave(canvas, peaks, progress) {
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth || 240, h = canvas.clientHeight || 38;
    if (canvas.width !== Math.round(w * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    }
    var g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    if (!peaks || !peaks.length) return;
    var mid = h / 2, step = w / peaks.length, played = w * (progress || 0);
    for (var i = 0; i < peaks.length; i++) {
      var x = i * step, amp = Math.max(1, peaks[i] * (h * 0.46));
      g.fillStyle = x <= played ? "#E8B950" : "rgba(238,232,220,0.34)";
      g.fillRect(x, mid - amp, Math.max(1, step - 0.6), amp * 2);
    }
  }

  function paintAll(activeId, progress) {
    Array.prototype.forEach.call(document.querySelectorAll("[data-wave]"), function (c) {
      var id = c.getAttribute("data-wave"), a = audio[id];
      drawWave(c, a && a.peaks, id === activeId ? progress : 0);
    });
  }

  // ---------- one player for the list ----------
  var el = new Audio(), playingId = null, raf = null;
  el.preload = "none";

  function stop() {
    el.pause();
    if (raf) cancelAnimationFrame(raf);
    raf = null;
    if (playingId) {
      var btn = document.querySelector('[data-play="' + playingId + '"]');
      if (btn) { btn.innerHTML = "&#9654;"; btn.setAttribute("aria-pressed", "false"); }
    }
    var was = playingId;
    playingId = null;
    paintAll(was, 0);
  }

  function tick() {
    if (!playingId) return;
    var a = audio[playingId];
    var dur = (a && a.duration) || el.duration || 0;
    paintAll(playingId, dur ? el.currentTime / dur : 0);
    raf = requestAnimationFrame(tick);
  }

  function play(id) {
    if (playingId === id) { stop(); return; }
    stop();
    playingId = id;
    el.src = "/beats/" + id + "/stream";
    el.play().then(function () {
      var btn = document.querySelector('[data-play="' + id + '"]');
      if (btn) { btn.innerHTML = "&#10073;&#10073;"; btn.setAttribute("aria-pressed", "true"); }
      tick();
    }).catch(function () {
      playingId = null;
      say("That beat would not play — the file may still be uploading.");
    });
  }
  el.addEventListener("ended", stop);

  document.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest("[data-play]") : null;
    if (btn && !btn.disabled) { play(btn.getAttribute("data-play")); return; }
    var wave = e.target.closest ? e.target.closest("[data-wave]") : null;
    if (wave) {
      var id = wave.getAttribute("data-wave"), a = audio[id];
      var dur = (a && a.duration) || 0;
      if (!dur) return;
      var r = wave.getBoundingClientRect();
      if (playingId !== id) play(id);
      el.currentTime = dur * Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
      paintAll(id, el.currentTime / dur);
    }
  });

  window.addEventListener("resize", function () { paintAll(playingId, 0); });
  paintAll(null, 0);

  // ---------- bulk upload ----------
  var drop = $("bt-drop"), queue = $("bt-queue");
  if (drop) {
    ["dragenter", "dragover"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("is-over"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("is-over"); });
    });
    drop.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files) take(e.dataTransfer.files);
    });
    $("bt-files").addEventListener("change", function () { take(this.files); });
  }

  function row(name) {
    var li = document.createElement("li");
    li.className = "bt-q";
    var b = document.createElement("b"); b.textContent = name;
    var s = document.createElement("span"); s.textContent = "waiting";
    var bar = document.createElement("div"); bar.className = "bt-bar";
    var fill = document.createElement("i"); bar.appendChild(fill);
    li.appendChild(b); li.appendChild(s); li.appendChild(bar);
    queue.appendChild(li);
    return {li: li, status: s, fill: fill};
  }

  function take(files) {
    var list = Array.prototype.slice.call(files).filter(function (f) {
      return /^audio\//.test(f.type) || /\.(mp3|wav|aiff?|flac|m4a|ogg)$/i.test(f.name);
    });
    if (!list.length) { say("None of those looked like audio files."); return; }
    say(list.length + " file" + (list.length === 1 ? "" : "s") + " queued.");
    // One at a time: decoding and measuring a track is not cheap, and
    // forty in parallel would freeze the tab it is running in.
    list.reduce(function (chain, f) {
      return chain.then(function () { return one(f); });
    }, Promise.resolve()).then(function () {
      say("Uploads finished. Reloading the list.");
      setTimeout(function () { location.reload(); }, 900);
    });
  }

  // Flask refuses an oversize request before routing, so without this a
  // producer dropping forty WAVs would upload every one of them in full
  // and get forty bare failures. Check the size we already know first.
  var MAX_BYTES = (window.__btMaxMb || 24) * 1024 * 1024;

  function one(file) {
    var r = row(file.name);
    if (file.size > MAX_BYTES) {
      r.li.classList.add("is-bad");
      r.status.textContent = Math.round(file.size / 1048576) + " MB — the ceiling is "
        + (window.__btMaxMb || 24) + " MB. Bounce it to MP3 or FLAC.";
      return Promise.resolve();
    }
    return readAndMeasure(file, r)
      .then(function (measured) { return send(file, measured, r); })
      .catch(function (err) {
        r.li.classList.add("is-bad");
        r.status.textContent = (err && err.message) || "failed";
      });
  }

  function readAndMeasure(file, r) {
    r.status.textContent = "reading";
    return file.arrayBuffer().then(function (raw) {
      r.status.textContent = "decoding";
      r.fill.style.width = "20%";
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return {peaks: [], skipped: "this browser cannot decode audio here"};
      var ctx = new AC();
      return ctx.decodeAudioData(raw.slice(0)).then(function (buf) {
        r.status.textContent = "measuring tempo and key";
        r.fill.style.width = "45%";
        var out = {duration: buf.duration, sample_rate: buf.sampleRate,
                   peaks: peaksOf(buf, 480)};
        try {
          var chans = [];
          for (var c = 0; c < Math.min(2, buf.numberOfChannels); c++) chans.push(buf.getChannelData(c));
          var bpm = TK && TK.detectBpm(chans, buf.sampleRate);
          var key = TK && TK.detectKey(chans, buf.sampleRate);
          if (bpm) {
            out.bpm = bpm.bpm;
            out.bpm_confidence = bpm.confidence;
            out.bpm_alternates = (bpm.alternates || []).join("/");
          }
          if (key) { out.song_key = key.key; out.key_fit = key.score; }
        } catch (e) {
          // A measurement that throws is a measurement we do not have.
          // The upload still carries the audio and the waveform.
        }
        try { ctx.close(); } catch (e) {}
        return out;
      }).catch(function () {
        try { ctx.close(); } catch (e) {}
        // Undecodable here does not mean unplayable in an <audio> tag, so
        // the file still goes up — it just arrives without measurements.
        return {peaks: [], skipped: "could not decode for analysis"};
      });
    });
  }

  function send(file, m, r) {
    r.status.textContent = "registering";
    r.fill.style.width = "60%";
    // The beat row has to exist before its audio can hang off it.
    return fetch("/beats/register", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({title: file.name.replace(/\.[^.]+$/, "").slice(0, 200)})
    }).then(function (res) { return res.json(); }).then(function (d) {
      if (!d.ok) throw new Error("could not register");
      return upload(d.id, file, m, r).catch(function (err) {
        // The row existed only to hang this file off. Leaving it behind
        // would litter the catalogue with empty beats after a bad drop,
        // and it has nothing else on it yet to lose.
        return fetch("/beats/" + d.id + "/delete", {method: "POST"})
          .catch(function () {})
          .then(function () { throw err; });
      });
    });
  }

  function upload(beatId, file, m, r) {
    return new Promise(function (resolve, reject) {
      var fd = new FormData();
      fd.append("file", file);
      fd.append("peaks", JSON.stringify(m.peaks || []));
      ["duration", "sample_rate", "bpm", "bpm_confidence", "bpm_alternates",
       "song_key", "key_fit"].forEach(function (k) {
        if (m[k] !== undefined && m[k] !== null) fd.append(k, String(m[k]));
      });
      var xhr = new XMLHttpRequest();
      xhr.open("POST", "/beats/" + beatId + "/audio");
      xhr.upload.addEventListener("progress", function (e) {
        if (!e.lengthComputable) return;
        r.fill.style.width = (60 + 40 * (e.loaded / e.total)).toFixed(0) + "%";
      });
      xhr.addEventListener("load", function () {
        var d = {};
        try { d = JSON.parse(xhr.responseText); } catch (e) {}
        if (xhr.status >= 400 || !d.ok) { reject(new Error(d.error || "upload refused")); return; }
        r.li.classList.add("is-done");
        r.fill.style.width = "100%";
        r.status.textContent = m.skipped
          ? "registered — " + m.skipped
          : "registered · " + (m.bpm ? Math.round(m.bpm) + " BPM" : "no tempo found")
            + (m.song_key ? " · " + m.song_key : "");
        resolve(d);
      });
      xhr.addEventListener("error", function () { reject(new Error("network error")); });
      xhr.send(fd);
    });
  }
})();
