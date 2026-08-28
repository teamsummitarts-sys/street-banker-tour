/* Light Studio — cue timeline locked to the song, waveform lane with
   draggable cue flags, hi-DPI canvas stage preview (simulation), and real
   DMX output to an ENTTEC USB Pro over Web Serial. Audio stays in the
   browser; saving stores the cue list, rig layout and timing only.
   The maths lives in lights-engine.js so it can be tested without a DOM. */
(function () {
  "use strict";
  var E = window.LightsEngine;
  var $ = function (id) { return document.getElementById(id); };
  // Your own looks. The first four get keyboard shortcuts (7 8 9 0); the
  // rest are click-only. The old cap of four made the Looks row look like a
  // fixed palette of six house colours, which is not what it is.
  var MAX_USER_LOOKS = 16;
  var saved = window.__savedShow || null;
  var lib = window.__lightsLibrary || {shows: [], tracks: [], tour_shows: []};
  var show = (saved && saved.cues) ? saved : {name: "", bars: 6, chans: 4, cues: []};
  show.bars = Math.max(2, Math.min(10, show.bars || 6));
  show.chans = show.chans === 3 ? 3 : 4;
  show.cues.forEach(function (c) { if (typeof c.note !== "string") c.note = ""; });
  show.looks = Array.isArray(show.looks) ? show.looks.slice(0, MAX_USER_LOOKS) : [];   // user looks (keys 7 8 9 0), saved with the show

  // ---------- state ----------
  var ctx = null, buffer = null, playing = false, startAt = 0, playOffset = 0, runStart = null, scrubT = 0, src = null;
  // Output scaling is live state, not part of the show: the grand master
  // multiplies every intensity, panic forces everything off. Volume and
  // rate only touch the preview audio; the clock always reads song time.
  var master = 1, panic = false, volume = 1, rate = 1, gainNode = null;
  var port = null, writer = null, lastDmx = 0, dmxWrites = 0, dmxFps = 0, dmxSec = 0;
  var selectedCue = null, selectedBar = null, hoverBar = null, hoverGroup = null, defaultGroup = "all";
  var dirty = false, saveTimer = null, beatGrid = true, taps = [];
  // libraryDirty: edits since the last explicit "Save to library" (or load).
  // The draft autosave keeps them safe; it never writes a library version.
  var libraryDirty = false;
  var H = E.makeHistory(50, 800);
  var DPR = function () { return Math.max(1, Math.min(3, window.devicePixelRatio || 1)); };
  function announce(msg) { var el = $("lx-live"); if (!el) return; el.textContent = ""; setTimeout(function () { el.textContent = msg; }, 30); }

  function ensureCtx() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      gainNode = ctx.createGain(); gainNode.gain.value = volume; gainNode.connect(ctx.destination);
    }
    return ctx;
  }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function isTyping(t) {
    var tag = ((t && t.tagName) || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || (t && t.isContentEditable);
  }
  function duration() { return buffer ? buffer.duration : 0; }

  // ---------- transport ----------
  var playBtn = $("lx-play"), clockEl = $("lx-clock"), totalEl = $("lx-clock-total"), infoEl = $("lx-fileinfo");
  function now() {
    if (buffer && playing) return Math.min(buffer.duration, (ctx.currentTime - startAt) * rate + playOffset);
    if (runStart !== null) return (performance.now() - runStart) / 1000;
    return scrubT;
  }
  function stopSource() {
    if (src) { try { src.onended = null; src.stop(); } catch (e) {} src = null; }
  }
  function startPlayback(offset) {
    ensureCtx().resume();
    stopSource();
    var s = ctx.createBufferSource();
    s.buffer = buffer; s.playbackRate.value = rate; s.connect(gainNode || ctx.destination);
    s.onended = function () {
      if (src !== s) return;
      playing = false; src = null; scrubT = buffer.duration; paintTransport();
      songEnded();
    };
    src = s;
    s.start(0, clamp(offset, 0, Math.max(0, buffer.duration - 0.01)));
    startAt = ctx.currentTime; playOffset = offset; playing = true; runStart = null;
    paintTransport();
  }
  function stopAll() {
    if (playing) scrubT = now();
    stopSource();
    playing = false; runStart = null;
    paintTransport();
  }
  function seek(t) {
    t = clamp(t, 0, duration() || 1e9);
    if (playing) startPlayback(t);
    else { scrubT = t; if (runStart !== null) runStart = performance.now() - t * 1000; }
  }
  function togglePlay() {
    if (playing || runStart !== null) { stopAll(); return; }
    if (!buffer) return;
    startPlayback(scrubT >= buffer.duration - 0.05 ? 0 : scrubT);
  }
  function paintTransport() {
    var live = playing || runStart !== null;
    playBtn.textContent = live ? "Stop" : "Play";
    playBtn.setAttribute("aria-pressed", live ? "true" : "false");
    var canCue = !!buffer || runStart !== null;
    $("lx-run").setAttribute("aria-pressed", runStart !== null ? "true" : "false");
    $("lx-add").disabled = !canCue; $("lx-blackout").disabled = !canCue;
    $("lx-add").setAttribute("aria-disabled", canCue ? "false" : "true"); $("lx-blackout").setAttribute("aria-disabled", canCue ? "false" : "true");
    $("lx-add").title = canCue ? "Add a cue at the playhead (C)" : "Load a song first — then cues land at the playhead";
    $("lx-blackout").title = canCue ? "Add a blackout at the playhead (B)" : "Load a song first — then a blackout lands at the playhead";
    playBtn.title = buffer ? "Play or stop (Space)" : "Load a song to play it";
    playBtn.setAttribute("aria-disabled", buffer ? "false" : "true");
    $("lx-cue-hint").hidden = canCue;
    // phone dock mirrors the transport
    $("lx-dock-play").textContent = live ? "Stop" : "Play"; $("lx-dock-play").disabled = !buffer;
    $("lx-dock-add").disabled = !canCue; $("lx-dock-black").disabled = !canCue;
  }
  playBtn.addEventListener("click", togglePlay);
  $("lx-dock-play").addEventListener("click", togglePlay);
  $("lx-dock-add").addEventListener("click", function () { $("lx-add").click(); });
  $("lx-dock-black").addEventListener("click", function () { $("lx-blackout").click(); });
  $("lx-run").addEventListener("click", function () {
    if (runStart !== null || playing) { stopAll(); return; }
    runStart = performance.now() - scrubT * 1000;
    paintTransport();
  });

  // ---------- audio controls: volume, rate, scrub ----------
  var volEl = $("lx-vol"), rateEl = $("lx-rate"), scrubEl = $("lx-scrub");
  volEl.addEventListener("input", function () {
    volume = clamp(parseInt(volEl.value, 10) / 100, 0, 1);
    if (gainNode) gainNode.gain.value = volume;
    $("lx-vol-val").textContent = Math.round(volume * 100) + "%";
  });
  rateEl.addEventListener("change", function () {
    var t = now();
    rate = parseFloat(rateEl.value) || 1;
    if (playing) startPlayback(t);
    announce("Playback " + rateEl.options[rateEl.selectedIndex].textContent + (rate !== 1 ? " — the clock still reads song time" : ""));
  });
  scrubEl.addEventListener("input", function () { if (buffer) seek(parseInt(scrubEl.value, 10) / 1000 * buffer.duration); });
  function paintScrub(t) {
    if (!buffer || document.activeElement === scrubEl) return;
    var v = String(Math.round(t / buffer.duration * 1000));
    if (scrubEl.value !== v) { scrubEl.value = v; scrubEl.setAttribute("aria-valuetext", E.fmtTimecode(t)); }
  }
  function loadBuffer(buf, name) {
    buffer = buf; scrubT = 0; stopSource(); playing = false; runStart = null;
    show.name = show.name || String(name || "").replace(/\.[^.]+$/, "");
    $("lx-show-name").value = show.name;
    infoEl.innerHTML = "<b>" + esc(name || "song") + "</b> — " + E.fmtClock(buf.duration) + ", " +
      buf.numberOfChannels + " ch · stays on this machine";
    totalEl.textContent = "of " + E.fmtTimecode(buf.duration);
    playBtn.disabled = false; scrubEl.disabled = false; scrubEl.value = "0";
    view.start = 0; view.end = buf.duration; invalidatePeaks();
    paintTransport(); paintWaveAria(); paintAutoCue();
    announce("Song loaded: " + E.fmtClock(buf.duration));
    setTimeout(detectBeats, 50);
  }
  $("lx-file").addEventListener("change", function (e) {
    var f = e.target.files[0];
    if (!f) return;
    ensureCtx().resume();
    infoEl.innerHTML = "<b>Decoding " + esc(f.name) + "…</b>";
    f.arrayBuffer().then(function (ab) { return ctx.decodeAudioData(ab); })
      .then(function (buf) { loadBuffer(buf, f.name); })
      .catch(function () {
        infoEl.innerHTML = "<b>Could not decode that file.</b> Try an MP3, WAV, M4A or OGG.";
      });
  });
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"); }

  // ---------- undo / redo ----------
  // Snapshots cover what the user edits on the page: cues, bar layout,
  // orientation, bar count and fixture type. Library metadata (name,
  // track, tour date) is not part of the stack.
  function snapshot() {
    return JSON.stringify({cues: show.cues, pos: show.pos || {}, rot: show.rot || {}, bars: show.bars, chans: show.chans,
                           looks: show.looks || [], dmxStart: show.dmxStart || 1, dmxAddr: show.dmxAddr || {},
                           sections: show.sections || [], stops: show.stops || [],
                           rigKey: show.rigKey || null, rigName: show.rigName || "",
                           // Auto-cue adopts the tempo it detected, so the
                           // grid has to be part of the snapshot too - or
                           // undoing it silently keeps a tempo that
                           // overwrote a hand-tapped one.
                           bpm: show.bpm || 0, beatOffset: show.beatOffset || 0, snap: !!show.snap});
  }
  function record(key) { var pushed = H.push(snapshot(), key, performance.now()); paintHistory(); return pushed; }
  function applySnapshot(json) {
    var s = JSON.parse(json), selId = selectedCue ? selectedCue._id : null, selBar = selectedBar;
    show.cues = s.cues || []; show.pos = s.pos || {}; show.rot = s.rot || {};
    show.bars = Math.max(2, Math.min(10, s.bars || 6)); show.chans = s.chans === 3 ? 3 : 4;
    show.looks = Array.isArray(s.looks) ? s.looks : []; show.dmxStart = s.dmxStart || 1; show.dmxAddr = s.dmxAddr || {};
    show.sections = s.sections || []; show.stops = s.stops || [];
    show.rigKey = s.rigKey || null; show.rigName = s.rigName || "";
    show.bpm = s.bpm || 0; show.beatOffset = s.beatOffset || 0; show.snap = !!s.snap;
    // Point the wheel back at nothing: the cue it was editing is about to
    // be thrown away by this restore.
    ensureIds();
    selectedCue = null;
    show.cues.forEach(function (c) { if (selId && c._id === selId) selectedCue = c; });
    if (selBar > show.bars) selectedBar = null;
    barsSel.value = String(show.bars); chansSel.value = String(show.chans);
    renderCues(); paintGroups(); paintLooks(); paintRig(); paintBarCtl(); paintAutoCue(); paintBeats(); markDirty();
  }
  function undo() { var s = H.undo(snapshot()); if (s) { applySnapshot(s); announce("Undone"); } paintHistory(); }
  function redo() { var s = H.redo(snapshot()); if (s) { applySnapshot(s); announce("Redone"); } paintHistory(); }
  function paintHistory() {
    var u = $("lx-undo"), r = $("lx-redo");
    if (!u || !r) return;
    u.disabled = !H.canUndo(); r.disabled = !H.canRedo();
    u.setAttribute("aria-disabled", u.disabled ? "true" : "false"); r.setAttribute("aria-disabled", r.disabled ? "true" : "false");
  }

  // ---------- waveform lane ----------
  var wave = $("lx-wave"), wg = wave.getContext("2d");
  var view = {start: 0, end: 0};
  var peakCanvas = null, peakKey = "";
  var waveCss = {w: 0, h: 112};
  function waveSize() {
    var w = wave.clientWidth, d = DPR();
    if (w && (waveCss.w !== w || wave.width !== Math.round(w * d))) {
      waveCss.w = w;
      wave.width = Math.round(w * d); wave.height = Math.round(waveCss.h * d);
      invalidatePeaks();
    }
    wg.setTransform(d, 0, 0, d, 0, 0);
  }
  function invalidatePeaks() { peakKey = ""; }
  function tToX(t) { return (t - view.start) / Math.max(0.001, view.end - view.start) * waveCss.w; }
  function xToT(x) { return view.start + x / Math.max(1, waveCss.w) * (view.end - view.start); }
  function ensurePeaks() {
    var key = [view.start.toFixed(4), view.end.toFixed(4), waveCss.w].join("|");
    if (key === peakKey && peakCanvas) return;
    peakKey = key;
    var d = DPR(), w = waveCss.w, h = waveCss.h;
    peakCanvas = document.createElement("canvas");
    peakCanvas.width = Math.round(w * d); peakCanvas.height = Math.round(h * d);
    var pg = peakCanvas.getContext("2d");
    pg.setTransform(d, 0, 0, d, 0, 0);
    pg.fillStyle = "#070708"; pg.fillRect(0, 0, w, h);
    var ch0 = buffer.getChannelData(0);
    var pk = E.peaks(ch0, buffer.sampleRate, view.start, view.end, w);
    if (buffer.numberOfChannels > 1) {
      var pk2 = E.peaks(buffer.getChannelData(1), buffer.sampleRate, view.start, view.end, w);
      for (var i = 0; i < w; i++) { pk.max[i] = Math.max(pk.max[i], pk2.max[i]); pk.min[i] = Math.min(pk.min[i], pk2.min[i]); }
    }
    var mid = h / 2, amp = (h / 2) - 6;
    var grad = pg.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, "rgba(232,198,103,0.95)"); grad.addColorStop(0.5, "rgba(201,162,74,0.75)"); grad.addColorStop(1, "rgba(232,198,103,0.95)");
    pg.fillStyle = grad;
    for (var x = 0; x < w; x++) {
      var top = mid - pk.max[x] * amp, bot = mid - pk.min[x] * amp;
      if (bot - top < 1) { top = mid - 0.5; bot = mid + 0.5; }
      pg.fillRect(x, top, 1, bot - top);
    }
    pg.fillStyle = "rgba(255,255,255,0.08)"; pg.fillRect(0, mid, w, 1);
  }
  function drawWave(t) {
    waveSize();
    var w = waveCss.w, h = waveCss.h;
    if (!w) return;
    if (!buffer) {
      wg.fillStyle = "#070708"; wg.fillRect(0, 0, w, h);
      wg.fillStyle = "#8b857b"; wg.font = "600 12px -apple-system, Segoe UI, Roboto, sans-serif"; wg.textAlign = "center";
      wg.fillText("Load a song — its waveform lands here; click to seek, wheel to zoom, drag a cue flag to retime it.", w / 2, h / 2 + 4);
      wg.textAlign = "left";
      return;
    }
    ensurePeaks();
    wg.drawImage(peakCanvas, 0, 0, w, h);
    // song sections and hard stops (from Auto-cue): tinted bands + labels
    (show.sections || []).forEach(function (s) {
      var x0 = tToX(s.start), x1 = tToX(s.end);
      if (x1 < 0 || x0 > w) return;
      var a = Math.max(0, x0), b = Math.min(w, x1);
      wg.fillStyle = SECTION_TINT[s.label] || "rgba(255,255,255,0.04)"; wg.fillRect(a, 0, b - a, h);
      wg.strokeStyle = "rgba(255,255,255,0.18)"; wg.lineWidth = 1; wg.beginPath(); wg.moveTo(Math.round(x0) + 0.5, 0); wg.lineTo(Math.round(x0) + 0.5, h); wg.stroke();
      if (b - a > 44) { wg.fillStyle = "rgba(238,232,220,0.72)"; wg.font = "700 9.5px -apple-system, Segoe UI, Roboto, sans-serif"; wg.fillText(String(s.label).toUpperCase(), a + 4, h - 17); }
    });
    (show.stops || []).forEach(function (st) {
      var x0 = tToX(st.start), x1 = tToX(st.end || st.start + 0.5);
      if (x1 < 0 || x0 > w) return;
      wg.fillStyle = "rgba(240,165,142,0.14)"; wg.fillRect(x0, 0, Math.max(2, x1 - x0), h);
    });
    // beat grid
    if (show.bpm && beatGrid) {
      var period = 60 / show.bpm, off = show.beatOffset || 0;
      var first = off + Math.ceil((view.start - off) / period) * period;
      var span = view.end - view.start;
      var every = span > 90 ? 4 : 1;
      wg.strokeStyle = "rgba(255,255,255,0.10)"; wg.lineWidth = 1;
      for (var b = first, n = Math.round((first - off) / period); b <= view.end; b += period, n++) {
        if (n % every) continue;
        var bx = Math.round(tToX(b)) + 0.5;
        wg.beginPath(); wg.moveTo(bx, n % 4 === 0 ? 2 : h * 0.35); wg.lineTo(bx, h - 2); wg.stroke();
      }
    }
    // cue flags
    var sorted = show.cues.slice().sort(function (a, b) { return a.t - b.t; });
    // Fade indicators, drawn under the flags: a wedge running back from the
    // cue over its fade time, so how long a look takes to arrive is visible
    // on the timeline instead of only being a number in the row.
    sorted.forEach(function (c) {
      var fade = Math.max(0, c.fade || 0);
      if (!fade || c.t < view.start - fade - 1 || c.t > view.end + 1) return;
      var xEnd = tToX(c.t), xStart = tToX(c.t - fade);
      if (xEnd - xStart < 1.5) return;
      var col = E.isBlackout(c) ? [240, 165, 142] : E.hexRgb(c.color || "#d8b25a");
      var g2 = wg.createLinearGradient(xStart, 0, xEnd, 0);
      g2.addColorStop(0, "rgba(" + col.join(",") + ",0)");
      g2.addColorStop(1, "rgba(" + col.join(",") + "," + (c === selectedCue ? 0.42 : 0.24) + ")");
      wg.fillStyle = g2;
      // a wedge: narrow where the fade starts, full height where it lands
      wg.beginPath();
      wg.moveTo(xStart, h - 3);
      wg.lineTo(xEnd, 18);
      wg.lineTo(xEnd, h - 3);
      wg.closePath();
      wg.fill();
      if (c === selectedCue) {
        wg.strokeStyle = "rgba(255,255,255,0.5)"; wg.lineWidth = 1;
        wg.beginPath(); wg.moveTo(xStart, h - 3); wg.lineTo(xEnd, 18); wg.stroke();
        if (xEnd - xStart > 34) {
          wg.fillStyle = "rgba(238,232,220,0.85)";
          wg.font = "600 9.5px -apple-system, Segoe UI, Roboto, sans-serif";
          wg.fillText(fade.toFixed(1) + "s", xStart + 3, h - 6);
        }
      }
    });
    sorted.forEach(function (c) {
      if (c.t < view.start - 1 || c.t > view.end + 1) return;
      var x = Math.round(tToX(c.t)) + 0.5, black = E.isBlackout(c), sel = c === selectedCue;
      wg.lineWidth = sel ? 2.5 : 1.5;
      wg.strokeStyle = black ? "rgba(240,165,142,0.95)" : (sel ? "#ffffff" : "rgba(232,198,103,0.95)");
      wg.beginPath(); wg.moveTo(x, 12); wg.lineTo(x, h - 2); wg.stroke();
      if (black) {
        // blackout: dark diamond, warm outline, a cross through it
        wg.fillStyle = "#111"; wg.beginPath(); wg.moveTo(x, 2); wg.lineTo(x + 8, 10); wg.lineTo(x, 18); wg.lineTo(x - 8, 10); wg.closePath(); wg.fill(); wg.stroke();
        wg.beginPath(); wg.moveTo(x - 3, 7); wg.lineTo(x + 3, 13); wg.moveTo(x + 3, 7); wg.lineTo(x - 3, 13); wg.stroke();
      } else {
        wg.fillStyle = c.color || "#d8b25a";
        wg.beginPath(); wg.moveTo(x, 2); wg.lineTo(x + 12, 2); wg.lineTo(x + 12, 11); wg.lineTo(x, 16); wg.closePath(); wg.fill();
        wg.strokeStyle = sel ? "#ffffff" : "rgba(0,0,0,0.7)"; wg.lineWidth = sel ? 2 : 1; wg.stroke();
      }
      if (sel && c.note) {
        wg.fillStyle = "rgba(0,0,0,0.75)"; wg.font = "600 11px -apple-system, Segoe UI, Roboto, sans-serif";
        var tw = wg.measureText(c.note).width + 10;
        wg.fillRect(x + 14, 4, tw, 16); wg.fillStyle = "#EEE8DC"; wg.fillText(c.note, x + 19, 16);
      }
    });
    // Notes left on this show (epic 5). Pinned under the wave so they sit
    // clear of the cue flags: a note is about a moment, not a cue, and
    // may well be pointing at a moment where there is no cue yet.
    notes.forEach(function (n) {
      if (n.parent_id || n.t === null || n.t === undefined) return;
      if (n.t < view.start - 1 || n.t > view.end + 1) return;
      var nx = Math.round(tToX(n.t)) + 0.5;
      wg.fillStyle = n.resolved ? "rgba(194,187,174,0.5)" : "#e8c667";
      wg.strokeStyle = "rgba(0,0,0,0.7)"; wg.lineWidth = 1;
      wg.beginPath(); wg.arc(nx, h - 9, 5, 0, Math.PI * 2); wg.fill(); wg.stroke();
      wg.fillStyle = "rgba(0,0,0,0.8)";
      wg.font = "800 8px -apple-system, Segoe UI, Roboto, sans-serif";
      wg.textAlign = "center"; wg.fillText("!", nx, h - 6); wg.textAlign = "left";
    });
    // playhead
    var px = tToX(t);
    if (px >= -1 && px <= w + 1) {
      wg.strokeStyle = "#fff4d0"; wg.lineWidth = 2;
      wg.beginPath(); wg.moveTo(px, 0); wg.lineTo(px, h); wg.stroke();
      wg.fillStyle = "#fff4d0"; wg.beginPath(); wg.moveTo(px - 6, h); wg.lineTo(px + 6, h); wg.lineTo(px, h - 8); wg.closePath(); wg.fill();
    }
    // scale
    wg.fillStyle = "rgba(238,232,220,0.6)"; wg.font = "600 10px ui-monospace, Menlo, Consolas, monospace";
    wg.fillText(E.fmtClock(view.start), 4, h - 4);
    wg.textAlign = "right"; wg.fillText(E.fmtClock(view.end), w - 4, h - 4); wg.textAlign = "left";
  }
  function cueAtX(x) {
    var best = null, bd = 9;
    show.cues.forEach(function (c) { var d = Math.abs(tToX(c.t) - x); if (d < bd) { bd = d; best = c; } });
    return best;
  }
  // Active pointers by id (for pinch) kept apart from the pinch baseline:
  // storing the baseline as a key on the same object once made every
  // click after the first count as a second finger.
  var wDrag = null, wSeeking = false, pointers = {}, pinchBase = null;
  function pointerIds() { return Object.keys(pointers); }
  wave.addEventListener("pointerdown", function (e) {
    if (!buffer) return;
    var r = wave.getBoundingClientRect(), x = e.clientX - r.left;
    pointers[e.pointerId] = {x: e.clientX};
    if (pointerIds().length >= 2) { wDrag = null; wSeeking = false; pinchBase = null; return; }
    var c = cueAtX(x);
    wave.setPointerCapture(e.pointerId);
    if (c) { record("drag:" + c._id); wDrag = c; selectCue(c); wave.style.cursor = "grabbing"; }
    else { wSeeking = true; seek(xToT(x)); }
    e.preventDefault();
  });
  // Keyboard alternative for the timeline: the lane is a slider over the
  // song. Arrows nudge the playhead, Home/End jump, and the live value is
  // announced through aria-valuetext.
  wave.addEventListener("keydown", function (e) {
    if (!buffer) return;
    var step = e.shiftKey ? 5 : 1;
    if (e.key === "ArrowLeft") { seek(now() - step); e.preventDefault(); e.stopPropagation(); }
    else if (e.key === "ArrowRight") { seek(now() + step); e.preventDefault(); e.stopPropagation(); }
    else if (e.key === "Home") { seek(0); e.preventDefault(); }
    else if (e.key === "End") { seek(duration()); e.preventDefault(); }
    paintWaveAria();
  });
  var lastAria = 0;
  function paintWaveAria() {
    var t = now();
    wave.setAttribute("aria-valuenow", t.toFixed(2));
    wave.setAttribute("aria-valuemax", duration().toFixed(2));
    wave.setAttribute("aria-valuetext", buffer ? "Playhead at " + E.fmtTimecode(t) + " of " + E.fmtTimecode(duration()) : "No song loaded");
  }
  wave.addEventListener("pointermove", function (e) {
    var r = wave.getBoundingClientRect(), x = e.clientX - r.left;
    if (pointers[e.pointerId]) pointers[e.pointerId].x = e.clientX;
    var ids = pointerIds();
    if (ids.length === 2) {
      var dist = Math.abs(pointers[ids[0]].x - pointers[ids[1]].x);
      if (!pinchBase) pinchBase = {dist: dist, start: view.start, end: view.end};
      else if (pinchBase.dist > 10) {
        var mid = xToT((pointers[ids[0]].x + pointers[ids[1]].x) / 2 - r.left);
        zoomTo((pinchBase.end - pinchBase.start) * pinchBase.dist / Math.max(10, dist), mid);
      }
      return;
    }
    if (wDrag) {
      var t = clamp(xToT(x), 0, duration());
      if (show.snap && show.bpm) t = E.snapToBeat(t, show.bpm, show.beatOffset);
      wDrag.t = Math.round(t * 100) / 100; own(wDrag); markDirty(); renderCues(false);
    } else if (wSeeking) { seek(xToT(x)); }
    else { wave.style.cursor = cueAtX(x) ? "grab" : "crosshair"; }
  });
  function wUp(e) { delete pointers[e.pointerId]; if (pointerIds().length < 2) pinchBase = null; if (wDrag) { wDrag = null; renderCues(); } wSeeking = false; wave.style.cursor = "crosshair"; paintWaveAria(); }
  wave.addEventListener("pointerup", wUp); wave.addEventListener("pointercancel", wUp);
  wave.addEventListener("wheel", function (e) {
    if (!buffer) return;
    e.preventDefault();
    var r = wave.getBoundingClientRect(), x = e.clientX - r.left;
    if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      var span0 = view.end - view.start, shift = (e.deltaX || e.deltaY) / waveCss.w * span0;
      panTo(view.start + shift);
    } else {
      zoomTo((view.end - view.start) * Math.exp(e.deltaY * 0.0018), xToT(x));
    }
  }, {passive: false});
  function zoomTo(span, anchorT) {
    var dur = duration(); span = clamp(span, Math.min(2, dur), dur);
    var frac = (anchorT - view.start) / Math.max(0.001, view.end - view.start);
    var start = clamp(anchorT - frac * span, 0, dur - span);
    view.start = start; view.end = start + span; invalidatePeaks();
  }
  function panTo(start) {
    var span = view.end - view.start, dur = duration();
    view.start = clamp(start, 0, Math.max(0, dur - span)); view.end = view.start + span; invalidatePeaks();
  }
  $("lx-zoom-fit").addEventListener("click", function () { if (buffer) { view.start = 0; view.end = buffer.duration; invalidatePeaks(); } });

  // ---------- beats ----------
  function detectBeats() {
    if (!buffer) return;
    var n = buffer.length, mono = new Float32Array(n), chs = buffer.numberOfChannels;
    for (var c = 0; c < chs; c++) { var d = buffer.getChannelData(c); for (var i = 0; i < n; i++) mono[i] += d[i] / chs; }
    var res = E.detectBeats(mono, buffer.sampleRate);
    if (res.bpm) { show.bpm = res.bpm; show.beatOffset = res.offset; markDirty(); }
    paintBeats(res.bpm ? "detected" : "not found");
  }
  // ---------- auto-cue: a first pass from the song's own structure ----------
  // analyzeTrack (sections, drops, hard stops, tempo) + generateCues in the
  // engine; here we only wire it up. Auto cues carry auto:true, wear a
  // badge, and become yours the moment you edit one (own()).
  var SECTION_TINT = {intro: "rgba(255,179,71,0.07)", verse: "rgba(59,130,246,0.07)", chorus: "rgba(255,244,208,0.09)", drop: "rgba(255,45,45,0.10)",
                      breakdown: "rgba(139,92,246,0.08)", bridge: "rgba(139,92,246,0.08)", outro: "rgba(255,179,71,0.06)"};
  function monoMix() {
    var n = buffer.length, mono = new Float32Array(n), chs = buffer.numberOfChannels;
    for (var c = 0; c < chs; c++) { var d = buffer.getChannelData(c); for (var i = 0; i < n; i++) mono[i] += d[i] / chs; }
    return mono;
  }
  function own(c) {
    if (!c || !c.auto) return;
    c.auto = false;
    var badge = cuesWrap.querySelector('[data-id="' + c._id + '"] .lx-auto'); if (badge) badge.remove();
    paintAutoCue();
  }
  function autoCue() {
    if (!buffer) return;
    var btn = $("lx-autocue"); btn.disabled = true; btn.textContent = "Listening…";
    setTimeout(function () {
      var an = E.analyzeTrack(monoMix(), buffer.sampleRate), gen = E.generateCues(an);
      record("autocue");
      if (an.bpm) { show.bpm = an.bpm; show.beatOffset = an.offset; }
      show.sections = an.sections.map(function (s) { return {start: s.start, end: s.end, label: s.label}; });
      show.stops = an.stops.map(function (s) { return {start: s.start, end: s.end}; });
      show.cues = show.cues.filter(function (c) { return !c.auto; }).concat(gen);
      if (selectedCue && selectedCue.auto) selectedCue = null;
      ensureIds(); markDirty(); renderCues(); paintGroups(); paintBeats(an.bpm ? "detected" : "not found"); paintAutoCue();
      var msg = "Auto-cue: " + an.sections.length + " sections, " + an.stops.length + (an.stops.length === 1 ? " hard stop, " : " hard stops, ") + gen.length + " cues" +
        (an.bpm ? " at " + an.bpm.toFixed(1) + " BPM" : "") + " — every one is editable; drag a flag to retime it, change anything and it becomes yours.";
      $("lx-autocue-note").textContent = msg; announce(msg);
      btn.disabled = false; btn.textContent = "Auto-cue again";
    }, 30);
  }
  function clearAutoCues() {
    var n = show.cues.filter(function (c) { return c.auto; }).length;
    if (!n) return;
    record("autocue-clear");
    show.cues = show.cues.filter(function (c) { return !c.auto; });
    if (selectedCue && selectedCue.auto) selectedCue = null;
    markDirty(); renderCues(); paintGroups(); paintAutoCue();
    $("lx-autocue-note").textContent = n + " auto cue" + (n === 1 ? "" : "s") + " cleared — the section bands stay on the timeline; your own cues were kept.";
    announce($("lx-autocue-note").textContent);
  }
  function paintAutoCue() {
    var n = show.cues.filter(function (c) { return c.auto; }).length, btn = $("lx-autocue");
    btn.disabled = !buffer; btn.setAttribute("aria-disabled", buffer ? "false" : "true");
    btn.title = buffer ? "Listen to the song and lay down a first pass of cues" : "Load a song first";
    $("lx-autocue-clear").hidden = !n; $("lx-autocue-clear").textContent = "Clear " + n + " auto cue" + (n === 1 ? "" : "s");
  }
  $("lx-autocue").addEventListener("click", autoCue);
  $("lx-autocue-clear").addEventListener("click", clearAutoCues);

  function paintBeats(how) {
    $("lx-bpm").textContent = show.bpm ? show.bpm.toFixed(1) : "—";
    $("lx-bpm-how").textContent = show.bpm ? (how || "") : (how || "");
    $("lx-snap").setAttribute("aria-pressed", show.snap ? "true" : "false");
    $("lx-snap").disabled = !show.bpm;
  }
  $("lx-detect").addEventListener("click", detectBeats);
  $("lx-snap").addEventListener("click", function () { show.snap = !show.snap; markDirty(); paintBeats(); });
  $("lx-grid").addEventListener("click", function () { beatGrid = !beatGrid; $("lx-grid").setAttribute("aria-pressed", beatGrid ? "true" : "false"); });
  $("lx-tap").addEventListener("click", function () {
    var t = performance.now() / 1000;
    if (taps.length && t - taps[taps.length - 1] > 2) taps = [];
    taps.push(t);
    var bpm = E.tapTempo(taps);
    if (bpm) {
      show.bpm = bpm;
      var period = 60 / bpm, ph = now();
      show.beatOffset = Math.round((ph - Math.floor(ph / period) * period) * 1000) / 1000;
      markDirty(); paintBeats("tapped");
    } else { $("lx-bpm-how").textContent = "tap again…"; }
  });

  // ---------- stage preview (hi-DPI, responsive, audience view) ----------
  var stage = $("lx-stage"), g = stage.getContext("2d"), stageWrap = $("lx-stage-wrap");
  var barRects = [], stageCss = {w: 0, h: 0};
  var bgImg = new Image();
  bgImg.src = "/static/img/stage-bg-2.jpg";
  // The fixture sprite: an 8-lens LED bar photographed head-on. Lens
  // centres as fractions of the sprite width, the lens row as a fraction
  // of its height, lens radius as a fraction of width (measured once).
  var barImg = new Image();
  barImg.src = "/static/img/light-bar.png";
  var LENS_X = [0.127, 0.233, 0.339, 0.446, 0.553, 0.66, 0.766, 0.874], LENS_CY = 0.399, LENS_R = 0.019, SPRITE_RATIO = 372 / 1200;
  function hz(n) { var x = Math.sin(n * 12.9898) * 43758.5453; return x - Math.floor(x); }
  function stageSize() {
    var w = stageWrap.clientWidth, d = DPR();
    if (!w) return false;
    var h = Math.max(200, Math.round(w * 400 / 798));
    if (stageCss.w !== w || stageCss.h !== h || stage.width !== Math.round(w * d)) {
      stageCss = {w: w, h: h};
      stage.width = Math.round(w * d); stage.height = Math.round(h * d);
      stage.style.height = h + "px";
    }
    g.setTransform(d, 0, 0, d, 0, 0);
    return true;
  }
  function barPos(i, bars) {
    var key = String(i);
    if (show.pos && show.pos[key]) return show.pos[key];
    var top = Math.ceil(bars / 2);
    if (i <= top) return [0.15 + 0.7 * ((i - 0.5) / top), 0.12];
    var n = i - top, count = bars - top;
    return [0.17 + 0.66 * ((n - 0.5) / count), 0.78];
  }
  function drawStage(t) {
    if (!stageSize()) return;
    var w = stageCss.w, h = stageCss.h;
    var bgReady = bgImg.complete && bgImg.naturalWidth > 0;
    if (bgReady) {
      var scale = Math.max(w / bgImg.naturalWidth, h / bgImg.naturalHeight);
      var iw = bgImg.naturalWidth * scale, ih = bgImg.naturalHeight * scale;
      g.drawImage(bgImg, (w - iw) / 2, (h - ih) / 2, iw, ih);
      var vg = g.createLinearGradient(0, 0, 0, h);
      vg.addColorStop(0, "rgba(5,5,6,0.35)"); vg.addColorStop(0.4, "rgba(5,5,6,0)"); vg.addColorStop(1, "rgba(5,5,6,0.25)");
      g.fillStyle = vg; g.fillRect(0, 0, w, h);
    } else {
      var bgg = g.createLinearGradient(0, 0, 0, h);
      bgg.addColorStop(0, "#08080a"); bgg.addColorStop(1, "#111014");
      g.fillStyle = bgg; g.fillRect(0, 0, w, h);
      g.fillStyle = "#0d0c10"; g.fillRect(w * 0.1, h * 0.08, w * 0.8, h * 0.5);
      g.strokeStyle = "#1d1a22";
      for (var cx = w * 0.12; cx < w * 0.88; cx += 26) { g.beginPath(); g.moveTo(cx, h * 0.08); g.lineTo(cx, h * 0.58); g.stroke(); }
      g.fillStyle = "#17150f"; g.beginPath();
      g.moveTo(w * 0.13, h * 0.58); g.lineTo(w * 0.87, h * 0.58); g.lineTo(w * 0.97, h * 0.9); g.lineTo(w * 0.03, h * 0.9);
      g.closePath(); g.fill(); g.strokeStyle = "#2c2820"; g.stroke();
    }
    // show name: bottom-left, clear of the truss row of bars
    g.fillStyle = "rgba(239,230,205,0.5)";
    g.font = "bold " + Math.max(10, Math.round(h * 0.04)) + "px 'Arial Narrow', Arial";
    g.textAlign = "left"; g.fillText((show.name || "YOUR SET").toUpperCase().slice(0, 48), 12, h - 10);

    var looks = outLooks(t), bars = show.bars, sc = w / 798;
    barRects = [];
    g.save(); g.globalCompositeOperation = "lighter";
    var WIDTHS = [1, 0.62, 0.3], ALPHAS = [0.16, 0.24, 0.4];
    for (var i = 1; i <= bars; i++) {
      var p = barPos(i, bars), bx = p[0] * w, by = p[1] * h, look = looks[i - 1], col = look.rgb, a = look.inten;
      if (a <= 0.02) continue;
      var vert = (show.rot || {})[String(i)] === 90, c3;
      if (vert) {
        var ex = bx < w / 2 ? bx + w * 0.42 : bx - w * 0.42;
        for (c3 = 0; c3 < 3; c3++) {
          var hw = 60 * sc * WIDTHS[c3], hgrad = g.createLinearGradient(bx, by, ex, by);
          hgrad.addColorStop(0, "rgba(" + col.join(",") + "," + (ALPHAS[c3] * a).toFixed(3) + ")"); hgrad.addColorStop(1, "rgba(" + col.join(",") + ",0)");
          g.fillStyle = hgrad; g.beginPath();
          g.moveTo(bx, by - 16 * sc * WIDTHS[c3]); g.lineTo(bx, by + 16 * sc * WIDTHS[c3]); g.lineTo(ex, by + hw); g.lineTo(ex, by - hw); g.closePath(); g.fill();
        }
        for (var k = 0; k < 7; k++) {
          var pr = (hz(i * 97 + k) + t * 0.02 * (0.5 + hz(i + k))) % 1, px = bx + (ex - bx) * pr, py = by + (hz(i * 31 + k) - 0.5) * 2 * (16 + 44 * pr) * sc;
          g.fillStyle = "rgba(" + col.join(",") + "," + (0.35 * a * (1 - pr)).toFixed(3) + ")"; g.beginPath(); g.arc(px, py, 1.6, 0, 7); g.fill();
        }
      } else {
        var down = p[1] < 0.5, ly = down ? h * 0.86 : h * 0.1;
        for (c3 = 0; c3 < 3; c3++) {
          var lw = 70 * sc * WIDTHS[c3], grad = g.createLinearGradient(bx, by, bx, ly);
          grad.addColorStop(0, "rgba(" + col.join(",") + "," + (ALPHAS[c3] * a).toFixed(3) + ")"); grad.addColorStop(1, "rgba(" + col.join(",") + ",0)");
          g.fillStyle = grad; g.beginPath();
          g.moveTo(bx - 16 * sc * WIDTHS[c3], by); g.lineTo(bx + 16 * sc * WIDTHS[c3], by); g.lineTo(bx + lw, ly); g.lineTo(bx - lw, ly); g.closePath(); g.fill();
        }
        for (var k2 = 0; k2 < 7; k2++) {
          var pr2 = (hz(i * 53 + k2) + t * 0.02 * (0.5 + hz(i * 7 + k2))) % 1, py2 = by + (ly - by) * pr2, px2 = bx + (hz(i * 17 + k2) - 0.5) * 2 * (16 + 54 * pr2) * sc;
          g.fillStyle = "rgba(" + col.join(",") + "," + (0.35 * a * (1 - pr2)).toFixed(3) + ")"; g.beginPath(); g.arc(px2, py2, 1.6, 0, 7); g.fill();
        }
        if (down) {
          var pool = g.createRadialGradient(bx, h * 0.8, 4, bx, h * 0.8, 90 * sc);
          pool.addColorStop(0, "rgba(" + col.join(",") + "," + (0.4 * a).toFixed(3) + ")"); pool.addColorStop(1, "rgba(" + col.join(",") + ",0)");
          g.fillStyle = pool; g.beginPath(); g.ellipse(bx, h * 0.8, 95 * sc, 28 * sc, 0, 0, 7); g.fill();
          var refl = g.createLinearGradient(bx, h * 0.8, bx, h * 0.98);
          refl.addColorStop(0, "rgba(" + col.join(",") + "," + (0.12 * a).toFixed(3) + ")"); refl.addColorStop(1, "rgba(" + col.join(",") + ",0)");
          g.fillStyle = refl; g.fillRect(bx - 24 * sc, h * 0.8, 48 * sc, h * 0.18);
        }
      }
    }
    g.restore();

    if (!bgReady) {
      g.fillStyle = "#0b0a08"; g.strokeStyle = "#332d20";
      g.fillRect(w * 0.42, h * 0.5, w * 0.16, h * 0.09); g.strokeRect(w * 0.42, h * 0.5, w * 0.16, h * 0.09);
      g.beginPath(); g.arc(w * 0.5, h * 0.51, h * 0.045, 0, 7); g.fill(); g.stroke();
      g.fillRect(w * 0.2, h * 0.52, w * 0.07, h * 0.11); g.fillRect(w * 0.73, h * 0.52, w * 0.07, h * 0.11);
    }

    // Fixtures on top, with hover / selected / mirror / group states
    var hoverMembers = hoverGroup ? E.membersOf(hoverGroup, bars) : [];
    var mirror = hoverBar ? E.mirrorOf(hoverBar, bars) : null;
    var spriteReady = barImg.complete && barImg.naturalWidth > 0;
    for (var j = 1; j <= bars; j++) {
      var p2 = barPos(j, bars), x2 = p2[0] * w, y2 = p2[1] * h, lk = looks[j - 1];
      var vert2 = (show.rot || {})[String(j)] === 90;
      var barLen = Math.max(44, 66 * sc), barThick = barLen * SPRITE_RATIO;
      var bw = vert2 ? barThick : barLen, bh = vert2 ? barLen : barThick;
      var isSel = selectedBar === j, isHov = hoverBar === j, isMir = mirror === j, inGroup = hoverMembers.indexOf(j) >= 0;
      if (isSel || isHov || isMir || inGroup) {
        g.save();
        g.strokeStyle = isSel ? "#ffffff" : (isMir ? "rgba(232,198,103,0.9)" : (inGroup ? "rgba(232,198,103,0.95)" : "rgba(255,255,255,0.7)"));
        g.lineWidth = isSel ? 2.5 : 1.5;
        if (isMir) g.setLineDash([4, 3]);
        g.shadowColor = isSel || inGroup ? "#e8c667" : "#ffffff"; g.shadowBlur = isSel ? 18 : 10;
        g.strokeRect(x2 - bw / 2 - 7, y2 - bh / 2 - 7, bw + 14, bh + 14);
        g.restore();
      }
      // The bar itself: the product sprite (rotated for a side stick), its
      // eight lenses lit in the look's colour. Falls back to a drawn
      // housing until the sprite has loaded.
      g.save();
      g.translate(x2, y2);
      if (vert2) g.rotate(-Math.PI / 2);
      var L = barLen, T = barThick, lensY = -T / 2 + T * LENS_CY;
      if (spriteReady) {
        g.shadowColor = "rgba(0,0,0,0.75)"; g.shadowBlur = 8;
        g.drawImage(barImg, -L / 2, -T / 2, L, T);
        g.shadowBlur = 0;
      } else {
        g.fillStyle = "#1a1712"; g.fillRect(-L / 2, -T / 2, L, T);
        g.lineWidth = 1.5; g.strokeStyle = isSel ? "#ffffff" : "#d8b25a"; g.strokeRect(-L / 2, -T / 2, L, T);
        lensY = 0;
      }
      var rr = Math.max(1.8, L * LENS_R);
      for (var s2 = 0; s2 < LENS_X.length; s2++) {
        var lensX = -L / 2 + L * LENS_X[s2];
        if (lk.inten > 0.02) {
          g.save(); g.globalCompositeOperation = "lighter";
          var lg = g.createRadialGradient(lensX, lensY, 0, lensX, lensY, rr * 2.4);
          lg.addColorStop(0, "rgba(" + lk.rgb.join(",") + "," + (0.9 * lk.inten).toFixed(3) + ")");
          lg.addColorStop(0.45, "rgba(" + lk.rgb.join(",") + "," + (0.5 * lk.inten).toFixed(3) + ")");
          lg.addColorStop(1, "rgba(" + lk.rgb.join(",") + ",0)");
          g.fillStyle = lg; g.beginPath(); g.arc(lensX, lensY, rr * 2.4, 0, 7); g.fill();
          g.restore();
          g.fillStyle = "rgba(" + lk.rgb.join(",") + "," + (0.45 + 0.55 * lk.inten).toFixed(2) + ")";
        } else g.fillStyle = spriteReady ? "rgba(26,24,20,0.55)" : "#26221a";
        g.beginPath(); g.arc(lensX, lensY, rr, 0, 7); g.fill();
        if (lk.inten > 0.3) { g.fillStyle = "rgba(255,255,255," + (0.35 * lk.inten).toFixed(2) + ")"; g.beginPath(); g.arc(lensX, lensY, rr * 0.35, 0, 7); g.fill(); }
      }
      g.restore();
      if (lk.inten > 0.02) {
        g.save(); g.globalCompositeOperation = "lighter";
        var bloom = g.createRadialGradient(x2, y2, 1, x2, y2, (30 + 26 * lk.inten) * sc);
        bloom.addColorStop(0, "rgba(" + lk.rgb.join(",") + "," + (0.4 * lk.inten).toFixed(3) + ")"); bloom.addColorStop(1, "rgba(" + lk.rgb.join(",") + ",0)");
        g.fillStyle = bloom; g.beginPath(); g.ellipse(x2, y2, (vert2 ? 18 : 40) * sc + 20 * lk.inten, (vert2 ? 40 : 18) * sc + 20 * lk.inten, 0, 0, 7); g.fill(); g.restore();
      }
      g.fillStyle = isSel ? "#e8c667" : "rgba(0,0,0,0.75)";
      g.fillRect(x2 - bw / 2 - 4, y2 - bh / 2 - 17, 15, 13);
      g.fillStyle = isSel ? "#1c1302" : "#e8c667"; g.font = "bold 10px Arial";
      g.fillText(String(j), x2 - bw / 2 - 1, y2 - bh / 2 - 7);
      // hit box: at least 44px square around the fixture
      var hx = Math.max(44, bw + 20), hy = Math.max(44, bh + 20);
      barRects.push({i: j, x: x2 - hx / 2, y: y2 - hy / 2, w: hx, h: hy});
    }
  }
  function barAt(mx, my) {
    for (var k = barRects.length - 1; k >= 0; k--) {
      var b = barRects[k];
      if (mx >= b.x && mx <= b.x + b.w && my >= b.y && my <= b.y + b.h) return b.i;
    }
    return null;
  }
  var dragBar = null, dragMoved = false;
  stage.addEventListener("pointerdown", function (e) {
    var r = stage.getBoundingClientRect(), b = barAt(e.clientX - r.left, e.clientY - r.top);
    if (b && e.shiftKey) { pickBar(b); e.preventDefault(); return; }
    if (b) { record("pos:" + b); dragBar = b; dragMoved = false; stage.setPointerCapture(e.pointerId); e.preventDefault(); }
    else { selectBar(null); }
  });
  // Shift-click on the stage hand-picks bars into a custom group ("b1+b3")
  // for the selected cue, or for the group new cues start with.
  function pickBar(b) {
    var cur = selectedCue ? selectedCue.group : defaultGroup, next = E.toggleInGroup(cur, b, show.bars);
    if (selectedCue) { record("group:" + selectedCue._id); selectedCue.group = next; own(selectedCue); markDirty(); renderCues(); }
    else defaultGroup = next;
    paintGroups();
    announce(E.groupLabel(next, show.bars) + (selectedCue ? " set on the selected cue" : " set for new cues"));
  }
  stage.addEventListener("pointermove", function (e) {
    var r = stage.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    if (dragBar === null) {
      var hb = barAt(mx, my);
      if (hb !== hoverBar) { hoverBar = hb; stage.style.cursor = hb ? "grab" : "default"; }
      return;
    }
    dragMoved = true; stage.style.cursor = "grabbing";
    show.pos = show.pos || {};
    show.pos[String(dragBar)] = [clamp(mx / r.width, 0.03, 0.97), clamp(my / stageCss.h, 0.04, 0.92)];
    markDirty();
  });
  function stageUp() { if (dragBar !== null) { selectBar(dragBar); dragBar = null; stage.style.cursor = "grab"; } }
  stage.addEventListener("pointerup", stageUp); stage.addEventListener("pointercancel", stageUp);
  stage.addEventListener("pointerleave", function () { hoverBar = null; });
  stage.addEventListener("dblclick", function (e) {
    var r = stage.getBoundingClientRect(), b = barAt(e.clientX - r.left, e.clientY - r.top);
    if (b) { setRot(b, (show.rot || {})[String(b)] === 90 ? 0 : 90); selectBar(b); }
  });
  function setRot(bar, deg) { record("rot:" + bar); show.rot = show.rot || {}; show.rot[String(bar)] = deg; markDirty(); paintBarCtl(); announce("Bar " + bar + (deg === 90 ? " stood up as a side stick" : " hung")); }
  function selectBar(b) {
    var changed = b !== selectedBar;
    selectedBar = b; paintBarCtl(); paintBarsList(now());
    // Selection is otherwise conveyed only by a ring on the canvas, which a
    // screen reader cannot see.
    if (changed && b) announce("Bar " + b + " selected, DMX " + E.fixtureAddress(show, b) +
                               ((show.rot || {})[String(b)] === 90 ? ", side stick" : ", hung"));
  }
  // The bar drawer: orientation, position, DMX start address, look now,
  // mirror partner, prev/next. Opens on click (canvas or list row).
  function paintBarCtl() {
    var box = $("lx-barctl");
    if (!selectedBar) { box.hidden = true; return; }
    box.hidden = false;
    var rot = (show.rot || {})[String(selectedBar)] === 90, mir = E.mirrorOf(selectedBar, show.bars);
    $("lx-barctl-name").textContent = "Bar " + selectedBar + " of " + show.bars;
    $("lx-or-hung").setAttribute("aria-pressed", rot ? "false" : "true");
    $("lx-or-side").setAttribute("aria-pressed", rot ? "true" : "false");
    var p = barPos(selectedBar, show.bars), ax = $("lx-bar-x"), ay = $("lx-bar-y"), ad = $("lx-bar-addr");
    if (document.activeElement !== ax) ax.value = Math.round(p[0] * 100);
    if (document.activeElement !== ay) ay.value = Math.round(p[1] * 100);
    var own = (show.dmxAddr || {})[String(selectedBar)];
    if (document.activeElement !== ad) ad.value = own ? own : "";
    ad.placeholder = "auto · " + E.fixtureAddress(show, selectedBar);
    $("lx-bar-mirror").textContent = mir ? "Mirror partner: bar " + mir + " (pairs move as a look)." : "Centre bar — no mirror partner.";
    // A control that disables itself while it holds focus drops the keyboard
    // to <body> mid-task. Hand focus to the sibling that is still live first.
    var prevBtn = $("lx-bar-prev"), nextBtn = $("lx-bar-next");
    var wantPrevOff = selectedBar <= 1, wantNextOff = selectedBar >= show.bars;
    if (wantPrevOff && document.activeElement === prevBtn && !wantNextOff) nextBtn.focus();
    if (wantNextOff && document.activeElement === nextBtn && !wantPrevOff) prevBtn.focus();
    prevBtn.disabled = wantPrevOff; nextBtn.disabled = wantNextOff;
    paintPatchWarn();
  }
  function paintPatchWarn() {
    var el = $("lx-patch-warn"), hits = E.patchOverlaps(show);
    el.hidden = !hits.length;
    el.textContent = hits.length ? "Patch overlap: bars " + hits.map(function (h) { return h[0] + " & " + h[1]; }).join(", ") + " share DMX channels — give one its own start address." : "";
  }
  $("lx-or-hung").addEventListener("click", function () { if (selectedBar) setRot(selectedBar, 0); });
  $("lx-or-side").addEventListener("click", function () { if (selectedBar) setRot(selectedBar, 90); });
  $("lx-bar-deselect").addEventListener("click", function () { selectBar(null); stage.focus(); });
  $("lx-bar-prev").addEventListener("click", function () { if (selectedBar > 1) selectBar(selectedBar - 1); });
  $("lx-bar-next").addEventListener("click", function () { if (selectedBar < show.bars) selectBar(selectedBar + 1); });
  function placeFromFields() {
    if (!selectedBar) return;
    var x = clamp((parseFloat($("lx-bar-x").value) || 0) / 100, 0.03, 0.97), y = clamp((parseFloat($("lx-bar-y").value) || 0) / 100, 0.04, 0.92);
    record("pos:" + selectedBar); show.pos = show.pos || {}; show.pos[String(selectedBar)] = [x, y]; markDirty();
  }
  $("lx-bar-x").addEventListener("change", placeFromFields);
  $("lx-bar-y").addEventListener("change", placeFromFields);
  $("lx-bar-addr").addEventListener("change", function () {
    if (!selectedBar) return;
    var v = parseInt($("lx-bar-addr").value, 10);
    record("addr:" + selectedBar); show.dmxAddr = show.dmxAddr || {};
    if (v >= 1 && v <= 512) show.dmxAddr[String(selectedBar)] = v; else { delete show.dmxAddr[String(selectedBar)]; $("lx-bar-addr").value = ""; }
    markDirty(); paintBarCtl(); paintBarsList(now());
    announce("Bar " + selectedBar + " starts at DMX " + E.fixtureAddress(show, selectedBar));
  });
  function nudge(dx, dy) {
    if (!selectedBar) return;
    record("nudge:" + selectedBar);
    var p = barPos(selectedBar, show.bars).slice();
    show.pos = show.pos || {};
    show.pos[String(selectedBar)] = [clamp(p[0] + dx, 0.03, 0.97), clamp(p[1] + dy, 0.04, 0.92)];
    markDirty();
  }
  stage.addEventListener("keydown", function (e) {
    var st = e.shiftKey ? 0.05 : 0.01;
    if (e.key === "ArrowLeft") { nudge(-st, 0); e.preventDefault(); }
    else if (e.key === "ArrowRight") { nudge(st, 0); e.preventDefault(); }
    else if (e.key === "ArrowUp") { nudge(0, -st); e.preventDefault(); }
    else if (e.key === "ArrowDown") { nudge(0, st); e.preventDefault(); }
    else if (e.key === "Tab" && !e.shiftKey && selectedBar === null) { /* fall through */ }
    else if (e.key === "Enter" && selectedBar === null) { selectBar(1); }
    else if (e.key === "r" || e.key === "R") { if (selectedBar) setRot(selectedBar, (show.rot || {})[String(selectedBar)] === 90 ? 0 : 90); }
    else if (/^[0-9]$/.test(e.key) && e.key !== "0") { var n = parseInt(e.key, 10); if (n <= show.bars) selectBar(n); }
  });

  // All-bars list: the screen-reader-accessible twin of the canvas. Rows
  // are built once per bar count and updated in place, so a focused row
  // is never torn out from under the keyboard. Activating a row opens
  // the drawer for that bar.
  function paintBarsList(t) {
    var ul = $("lx-bars-list"); if (!ul) return;
    var looks = outLooks(t);
    if (ul.children.length !== show.bars) {
      ul.innerHTML = "";
      for (var n = 1; n <= show.bars; n++) {
        var li = document.createElement("li");
        li.innerHTML = '<button type="button" class="lx-barrow" data-bar="' + n + '" aria-pressed="false"><b>Bar ' + n + '</b><span class="lx-sw" aria-hidden="true"></span><span class="c-pct"></span><span class="c-pos"></span><span class="c-addr"></span><span class="c-mir"></span></button>';
        li.querySelector("button").addEventListener("click", function (e) {
          var b = parseInt(e.currentTarget.getAttribute("data-bar"), 10);
          selectBar(selectedBar === b ? null : b);
        });
        ul.appendChild(li);
      }
    }
    for (var i = 1; i <= show.bars; i++) {
      var row = ul.children[i - 1].firstChild, p = barPos(i, show.bars), lk = looks[i - 1], rot = (show.rot || {})[String(i)] === 90, mir = E.mirrorOf(i, show.bars);
      row.setAttribute("aria-pressed", selectedBar === i ? "true" : "false");
      row.querySelector(".lx-sw").style.background = "rgb(" + lk.rgb.join(",") + ")";
      row.querySelector(".c-pct").textContent = "look " + Math.round(lk.inten * 100) + "%";
      row.querySelector(".c-pos").textContent = Math.round(p[0] * 100) + "% across · " + (p[1] < 0.5 ? "truss" : "floor") + " · " + (rot ? "side stick" : "hung");
      row.querySelector(".c-addr").textContent = "DMX " + E.fixtureAddress(show, i);
      row.querySelector(".c-mir").textContent = mir ? "mirror " + mir : "centre";
    }
    if (selectedBar && looks[selectedBar - 1]) {
      var sl = looks[selectedBar - 1];
      $("lx-bar-look").style.background = "rgb(" + sl.rgb.join(",") + ")"; $("lx-bar-pct").textContent = Math.round(sl.inten * 100) + "%";
    }
  }

  // ---------- grand master / panic ----------
  // outLooks() is what the stage, the list and the DMX frame all read:
  // the resolved cues scaled by the master, or nothing at all on panic.
  function outLooks(t) {
    // A bump is a hand on the desk: someone pressed a look and the rig
    // holds it until they release it. It outranks the cue list and the
    // gap look, because it is the most recent human decision.
    if (bump) return E.scaleLooks(bumpLooks(), master, panic);
    // Between songs the rig holds the gap look. A black stage between
    // songs reads as a fault rather than a choice.
    if (inGap) return E.scaleLooks(gapLooks(), master, panic);
    return E.scaleLooks(E.lightingAt(show, t), master, panic);
  }
  // A held look. Set from the phone remote (or the release button here);
  // it never touches show.cues, so releasing it hands the song straight
  // back to the cue list with nothing to undo.
  var bump = null;
  function bumpLooks() {
    var col = E.hexRgb(bump.color), inten = (bump.intensity || 0) / 100, out = [];
    for (var i = 0; i < show.bars; i++) out.push({rgb: col.slice(), inten: inten});
    return out;
  }
  function setBump(l) {
    bump = (l && bump && bump.key === l.key) ? null : (l || null);   // same look again = release
    $("lx-bump").hidden = !bump;
    if (bump) $("lx-bump-name").textContent = bump.name;
    if (writer) sendDmx(now());
    announce(bump ? bump.name + " held over the whole rig" : "Look released — back to the cue list");
  }
  $("lx-bump").addEventListener("click", function () { setBump(null); });

  var masterEl = $("lx-master"), panicEl = $("lx-panic");
  function paintMaster() {
    $("lx-master-val").textContent = Math.round(master * 100) + "%";
    panicEl.setAttribute("aria-pressed", panic ? "true" : "false");
    panicEl.textContent = panic ? "ALL OFF — restore" : "All off";
    document.body.classList.toggle("lx-panic", panic);
    if (writer) paintDmxLive();
  }
  masterEl.addEventListener("input", function () { master = clamp(parseInt(masterEl.value, 10) / 100, 0, 1); paintMaster(); });
  function togglePanic() {
    panic = !panic; paintMaster();
    if (writer) sendDmx(now());
    announce(panic ? "All lights off — preview and DMX. Press All off again to restore." : "Restored — master " + Math.round(master * 100) + "%");
  }
  panicEl.addEventListener("click", togglePanic);

  // ---------- DMX (ENTTEC USB Pro over Web Serial) ----------
  function paintDmx(state, text) {
    var chip = $("lx-dmx-chip");
    chip.className = "lx-chip" + (state === "on" ? " is-on" : (state === "err" ? " is-err" : ""));
    $("lx-dmx-text").textContent = text;
  }
  function paintDmxLive() {
    var live = playing || runStart !== null;
    var where = output === "enttec" ? "Connected" : (output === "artnet" ? "Art-Net" : "sACN");
    paintDmx("on", where + " · universe " + (show.dmxUniverse || 1) + " · " +
             (panic ? "ALL OFF" : (live ? dmxFps + " fps" : "idle · holding")));
  }

  // ---------- outputs ----------
  // One frame loop, several sinks. ENTTEC goes out over Web Serial; Art-Net
  // and sACN are UDP, which a browser cannot speak, so they are POSTed to a
  // bridge script running on this machine that forwards them verbatim.
  var output = "preview", bridgeOk = false, bridgeInFlight = false;
  function bridgeUrl(path) { return "http://127.0.0.1:" + (parseInt($("lx-bridge-port").value, 10) || 7070) + path; }

  function paintOutputs() {
    var sel = $("lx-output");
    if (!sel.options.length) {
      E.OUTPUTS.forEach(function (o) {
        var op = document.createElement("option"); op.value = o[0]; op.textContent = o[1]; op.title = o[2];
        sel.appendChild(op);
      });
    }
    sel.value = output;
    var net = $("lx-net-now");
    if (net) net.textContent = (output === "artnet" || output === "sacn")
      ? "· " + (bridgeOk ? "bridge connected" : "bridge not found") : "";
    $("lx-dmx").hidden = output !== "enttec";
    if (output === "preview") paintDmx("", "Preview only · no hardware");
    else if (output === "enttec") { if (!writer) paintDmx("", "Preview only · no hardware"); else paintDmxLive(); }
    else paintDmx(bridgeOk ? "on" : "err", bridgeOk
      ? (output === "artnet" ? "Art-Net" : "sACN") + " · via the local bridge"
      : "Bridge not running — start lx-bridge.py on this computer");
  }

  $("lx-output").addEventListener("change", function () {
    output = $("lx-output").value;
    show.output = output; markDirty();
    if (output === "artnet" || output === "sacn") { $("lx-net-fold").open = true; checkBridge(); }
    paintOutputs();
    announce("Output set to " + $("lx-output").options[$("lx-output").selectedIndex].textContent);
  });

  function checkBridge() {
    var status = $("lx-bridge-status");
    status.textContent = "checking…";
    return fetch(bridgeUrl("/"), {cache: "no-store"})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        bridgeOk = !!(d && d.ok);
        status.textContent = bridgeOk
          ? "Bridge is running — Art-Net to " + (d.artnet_host || "?") + ", sACN to " + (d.sacn_host || "?") + "."
          : "Something answered on that port, but it is not the bridge.";
        paintOutputs();
        return bridgeOk;
      })
      .catch(function () {
        bridgeOk = false;
        status.textContent = "No bridge on that port. Download it, then run: python lx-bridge.py";
        paintOutputs();
        return false;
      });
  }
  $("lx-bridge-test").addEventListener("click", checkBridge);
  $("lx-bridge-port").addEventListener("change", function () { bridgeOk = false; paintOutputs(); });

  function sendDmx(t) {
    var looks = outLooks(t);
    if (output === "enttec") {
      if (!writer) return;
      writer.write(E.dmxFrame(show, looks)).catch(function () {});
      dmxWrites++;
      return;
    }
    if (output !== "artnet" && output !== "sacn") return;
    // Never queue: if the previous frame is still in flight, skip this one.
    // A backlog of stale frames is worse than a dropped one.
    if (bridgeInFlight) return;
    var seq = (dmxSeq = (dmxSeq + 1) & 0xFF);
    var pkt = output === "artnet"
      ? E.artnetPacket(show, looks, {universe: (show.dmxUniverse || 1) - 1, sequence: seq})
      : E.sacnPacket(show, looks, {universe: show.dmxUniverse || 1, sequence: seq});
    bridgeInFlight = true;
    fetch(bridgeUrl(output === "artnet" ? "/artnet" : "/sacn"),
          {method: "POST", body: pkt, headers: {"Content-Type": "application/octet-stream"}})
      .then(function () { dmxWrites++; if (!bridgeOk) { bridgeOk = true; paintOutputs(); } })
      .catch(function () { if (bridgeOk) { bridgeOk = false; paintOutputs(); } })
      .then(function () { bridgeInFlight = false; });
  }
  var dmxSeq = 0;
  $("lx-dmx").addEventListener("click", function () {
    if (!("serial" in navigator)) { paintDmx("err", "No Web Serial in this browser — use Chrome or Edge on desktop"); return; }
    if (port) {
      try { writer && writer.releaseLock(); } catch (e) {}
      writer = null; port.close().catch(function () {}); port = null;
      paintDmx("", "Preview only · no hardware"); $("lx-dmx").textContent = "Connect DMX (ENTTEC)";
      return;
    }
    navigator.serial.requestPort().then(function (p) { port = p; return port.open({baudRate: 57600}); })
      .then(function () {
        writer = port.writable.getWriter(); dmxWrites = 0; dmxFps = 0;
        paintDmxLive(); $("lx-dmx").textContent = "Disconnect DMX";
      }).catch(function () { port = null; paintDmx("", "Preview only · no hardware"); });
  });

  // ---------- cue list ----------
  var cuesWrap = $("lx-cues");
  function sortedCues() { return show.cues.slice().sort(function (a, b) { return a.t - b.t; }); }
  function selectCue(c, scroll) {
    selectedCue = c;
    aimWheelAt(c);
    if (c && !playing) scrubT = c.t;
    renderCues(false);
    paintGroups();
    if (c && scroll) { var el = cuesWrap.querySelector('[data-id="' + c._id + '"]'); if (el && el.scrollIntoView) el.scrollIntoView({block: "nearest"}); }
  }
  var cueSeq = 0;
  function ensureIds() { show.cues.forEach(function (c) { if (!c._id) c._id = "c" + (++cueSeq); }); }
  function glyphHtml(group) {
    var mem = E.membersOf(group, show.bars), h = '<span class="lx-glyph" aria-hidden="true">';
    for (var i = 1; i <= show.bars; i++) h += '<i class="' + (mem.indexOf(i) >= 0 ? "on" : "") + '"></i>';
    return h + "</span>";
  }
  function renderCues(full) {
    ensureIds();
    if (typeof paintTrackShip === "function") paintTrackShip();
    $("lx-cues-count").textContent = show.cues.length ? show.cues.length + (show.cues.length === 1 ? " cue" : " cues") : "";
    var sorted = sortedCues();
    if (!sorted.length) {
      cuesWrap.innerHTML = '<div class="lx-empty">No cues yet. Play the song and press <span class="lx-kbd">C</span> — or “+ Cue at playhead” — where the music turns: intro dim, chorus full, drop blackout. ' +
        'Pick a look chip to land a ready-made colour, then drag its flag on the waveform to retime it.</div>';
      return;
    }
    if (full === false && cuesWrap.children.length === sorted.length) {
      // light repaint: order, selection, timecodes, swatches
      sorted.forEach(function (c, idx) {
        var row = cuesWrap.querySelector('[data-id="' + c._id + '"]');
        if (!row) return;
        if (cuesWrap.children[idx] !== row) cuesWrap.insertBefore(row, cuesWrap.children[idx]);
        row.classList.toggle("is-sel", c === selectedCue); row.classList.toggle("is-black", E.isBlackout(c));
        var tc = row.querySelector(".lx-cue-tc input"); if (tc && document.activeElement !== tc) tc.value = c.t.toFixed(2);
        var sw = row.querySelector(".lx-swatch"); if (sw) { sw.style.background = c.color; sw.classList.toggle("is-black", E.isBlackout(c)); }
      });
      return;
    }
    cuesWrap.innerHTML = "";
    sorted.forEach(function (c, idx) {
      var row = document.createElement("div");
      var lookName = c.note || (E.isBlackout(c) ? "blackout" : "look " + c.color);
      row.className = "lx-cue" + (c === selectedCue ? " is-sel" : "") + (E.isBlackout(c) ? " is-black" : "");
      row.setAttribute("data-id", c._id); row.setAttribute("role", "listitem"); row.tabIndex = 0;
      row.setAttribute("aria-label", "Cue " + (idx + 1) + " at " + E.fmtTimecode(c.t) + ", " + lookName + ", " + E.groupLabel(c.group, show.bars) + (c.auto ? ", placed by Auto-cue" : "") + ". Enter previews the stage here.");
      // timecode
      var tc = document.createElement("div"); tc.className = "lx-cue-tc";
      var tin = document.createElement("input"); tin.type = "number"; tin.step = "0.01"; tin.min = "0"; tin.value = c.t.toFixed(2); tin.setAttribute("aria-label", "Cue time in seconds");
      tin.addEventListener("input", function () { record("time:" + c._id); c.t = Math.max(0, parseFloat(tin.value) || 0); own(c); markDirty(); });
      tin.addEventListener("change", function () { renderCues(false); });
      tc.appendChild(tin); row.appendChild(tc);
      // swatch: shows the cue's colour and aims the wheel at it
      var sw = document.createElement("button"); sw.type = "button"; sw.className = "lx-swatch" + (E.isBlackout(c) ? " is-black" : ""); sw.style.background = c.color;
      sw.title = "Colour — gel book, recent, or custom"; sw.setAttribute("aria-label", "Cue colour " + (gelName(c.color) || c.color) + " — open the gel book"); sw.setAttribute("aria-haspopup", "dialog");
      var cin = document.createElement("input"); cin.type = "color"; cin.className = "sr-only"; cin.tabIndex = -1; cin.value = /^#[0-9a-f]{6}$/i.test(c.color) ? c.color : "#000000"; cin.setAttribute("aria-label", "Custom cue colour");
      cin.addEventListener("input", function () { setCueColor(c, cin.value, sw); });
      // Clicking a swatch points the always-visible wheel at that cue.
      sw.addEventListener("click", function (e) { e.stopPropagation(); selectCue(c); aimWheelAt(c); $("lx-wheel").focus(); });
      row.appendChild(sw); row.appendChild(cin);
      // glyph
      var gl = document.createElement("span"); gl.innerHTML = glyphHtml(c.group); gl.title = E.groupLabel(c.group, show.bars); row.appendChild(gl.firstChild);
      // middle controls
      var mid = document.createElement("div"); mid.className = "lx-cue-mid";
      if (c.auto) { var ab = document.createElement("span"); ab.className = "lx-auto"; ab.textContent = "auto"; ab.title = "Placed by Auto-cue — change anything and it becomes yours"; mid.appendChild(ab); }
      var sel = document.createElement("select"); sel.className = "lx-select"; sel.setAttribute("aria-label", "Group");
      var gopts = E.groupOptions(show.bars), known = false;
      gopts.forEach(function (o) { var op = document.createElement("option"); op.value = o[0]; op.textContent = o[1]; op.selected = c.group === o[0]; if (op.selected) known = true; sel.appendChild(op); });
      if (!known && c.group) { var cop = document.createElement("option"); cop.value = c.group; cop.textContent = E.groupLabel(c.group, show.bars) + " (picked)"; cop.selected = true; sel.appendChild(cop); }
      sel.addEventListener("change", function () { record("group:" + c._id); c.group = sel.value; own(c); markDirty(); renderCues(); paintGroups(); });
      mid.appendChild(sel);
      var inten = document.createElement("input"); inten.type = "range"; inten.min = 0; inten.max = 100; inten.value = c.intensity; inten.setAttribute("aria-label", "Intensity");
      inten.title = "Intensity";
      inten.addEventListener("input", function () { record("inten:" + c._id); c.intensity = parseInt(inten.value, 10); own(c); sw.classList.toggle("is-black", E.isBlackout(c)); markDirty(); });
      mid.appendChild(inten);
      // movement is part of the cue's intent: it compiles per rig, so a
      // chase runs across whatever bars the group has on the night.
      var mv = document.createElement("select"); mv.className = "lx-select"; mv.setAttribute("aria-label", "Movement");
      mv.title = "Movement — beat-locked to the show tempo (120 BPM until one is detected)";
      E.MOVES.forEach(function (m) { var op = document.createElement("option"); op.value = m[0]; op.textContent = m[1]; op.selected = (c.move || "") === m[0]; mv.appendChild(op); });
      mv.addEventListener("change", function () { record("move:" + c._id); c.move = mv.value; own(c); markDirty(); });
      mid.appendChild(mv);
      var fw = document.createElement("label"); fw.textContent = "fade "; fw.title = "Seconds from the previous look into this one";
      var fin = document.createElement("input"); fin.type = "number"; fin.step = "0.1"; fin.min = "0"; fin.value = c.fade; fin.className = "lx-input"; fin.style.width = "64px"; fin.setAttribute("aria-label", "Fade seconds");
      fin.addEventListener("input", function () { record("fade:" + c._id); c.fade = Math.max(0, parseFloat(fin.value) || 0); own(c); markDirty(); });
      fw.appendChild(fin); fw.appendChild(document.createTextNode(" s")); mid.appendChild(fw);
      var note = document.createElement("input"); note.type = "text"; note.className = "lx-input lx-cue-note"; note.placeholder = "note — chorus, drop, verse 2…"; note.value = c.note || ""; note.maxLength = 80; note.setAttribute("aria-label", "Cue note");
      note.addEventListener("input", function () { record("note:" + c._id); c.note = note.value; own(c); markDirty(); });
      mid.appendChild(note);
      row.appendChild(mid);
      // delete
      var del = document.createElement("button"); del.type = "button"; del.className = "lx-cue-x"; del.textContent = "×"; del.setAttribute("aria-label", "Delete cue at " + E.fmtTimecode(c.t));
      del.addEventListener("click", function (e) {
        e.stopPropagation(); record("delete");
        show.cues.splice(show.cues.indexOf(c), 1); if (selectedCue === c) selectedCue = null;
        markDirty(); renderCues(); announce("Cue at " + E.fmtTimecode(c.t) + " deleted");
      });
      row.appendChild(del);
      // row click = preview at that time + select
      row.addEventListener("click", function (e) { if (isTyping(e.target) || e.target === del) return; selectCue(c); });
      row.addEventListener("keydown", function (e) { if ((e.key === "Enter" || e.key === " ") && e.target === row) { e.preventDefault(); selectCue(c); } });
      cuesWrap.appendChild(row);
    });
  }
  function addCue(look) {
    var t = Math.round(now() * 100) / 100;
    if (show.snap && show.bpm) t = E.snapToBeat(t, show.bpm, show.beatOffset);
    var c = {t: t, group: defaultGroup, color: "#d8b25a", intensity: 80, fade: 0.5, note: "", move: ""};
    if (look) { c.color = look.color; c.intensity = look.intensity; c.fade = look.fade; c.note = look.name; c.look = look.key || ""; c.move = look.move || ""; }
    record("add");
    show.cues.push(c); markDirty(); ensureIds(); renderCues(); selectCue(c, true);
    announce((look ? look.name : "Cue") + " added at " + E.fmtTimecode(t));
  }
  $("lx-add").addEventListener("click", function () { addCue(); });
  $("lx-blackout").addEventListener("click", function () { addCue(E.LOOKS[5]); });

  // ---------- group picker ----------
  function miniStage(group) {
    var bars = show.bars, mem = E.membersOf(group, bars), s = '<svg viewBox="0 0 100 34" aria-hidden="true">';
    s += '<rect x="4" y="26" width="92" height="6" rx="1.5" fill="#1a1712" stroke="#3a3224"/>';
    for (var i = 1; i <= bars; i++) {
      var p = barPos(i, bars), x = 6 + p[0] * 88, y = 4 + p[1] * 22, on = mem.indexOf(i) >= 0;
      var rot = (show.rot || {})[String(i)] === 90;
      s += '<rect x="' + (x - (rot ? 1.5 : 5)) + '" y="' + (y - (rot ? 5 : 1.5)) + '" width="' + (rot ? 3 : 10) + '" height="' + (rot ? 10 : 3) + '" rx="0.8" fill="' + (on ? "#e8c667" : "#2b271f") + '"' + (on ? ' style="filter:drop-shadow(0 0 2px #e8c667)"' : "") + '/>';
    }
    return s + "</svg>";
  }
  function paintGroups() {
    var box = $("lx-groups"), cur = selectedCue ? selectedCue.group : defaultGroup;
    box.innerHTML = "";
    // Roles and pairs only. One button per bar was a wall of chips that grew
    // with the rig; a single bar is now the compact dropdown below, and any
    // combination is shift-click on the stage.
    E.groupOptions(show.bars).filter(function (o) {
      return !/^b\d+$/.test(o[0]);
    }).forEach(function (o) {
      var b = document.createElement("button"); b.type = "button"; b.className = "lx-group";
      b.setAttribute("aria-pressed", cur === o[0] ? "true" : "false"); b.setAttribute("data-group", o[0]);
      b.setAttribute("aria-label", o[1] + " — " + o[2] + " (bars " + (E.membersOf(o[0], show.bars).join(", ") || "none") + ")");
      b.innerHTML = miniStage(o[0]) + "<b>" + o[1] + "</b><small>" + o[2] + "</small>";
      b.addEventListener("mouseenter", function () { hoverGroup = o[0]; });
      b.addEventListener("mouseleave", function () { hoverGroup = null; });
      b.addEventListener("focus", function () { hoverGroup = o[0]; });
      b.addEventListener("blur", function () { hoverGroup = null; });
      b.addEventListener("click", function () {
        // own() matters: without it an auto cue the user just re-grouped
        // still counts as auto, and "Clear auto cues" would delete the
        // edit they just made.
        if (selectedCue) { record("group:" + selectedCue._id); selectedCue.group = o[0]; own(selectedCue); markDirty(); renderCues(); }
        else defaultGroup = o[0];
        paintGroups();
      });
      box.appendChild(b);
    });
    $("lx-groups-for").textContent = selectedCue ? "Sets the group of the selected cue (" + E.fmtTimecode(selectedCue.t) + ")." : "No cue selected — sets the group new cues start with.";
    paintSingleBar(cur);
  }
  // The compact replacement for a button per bar.
  function paintSingleBar(cur) {
    var sel = $("lx-group-one");
    if (!sel) return;
    var want = /^b\d+$/.test(cur) ? cur : "";
    if (sel.options.length !== show.bars + 1) {
      sel.innerHTML = '<option value="">— pick a bar —</option>';
      for (var i = 1; i <= show.bars; i++) {
        var op = document.createElement("option");
        op.value = "b" + i; op.textContent = "Bar " + i;
        sel.appendChild(op);
      }
    }
    sel.value = want;
    var picked = /\+/.test(cur) ? E.membersOf(cur, show.bars) : [];
    $("lx-group-picked").textContent = picked.length
      ? "Hand-picked: bars " + picked.join(", ") + "."
      : "";
    $("lx-group-clear").hidden = !picked.length;
  }
  function setGroup(next) {
    if (selectedCue) { record("group:" + selectedCue._id); selectedCue.group = next; own(selectedCue); markDirty(); renderCues(); }
    else defaultGroup = next;
    paintGroups();
  }
  $("lx-group-one").addEventListener("change", function () {
    var v = $("lx-group-one").value;
    if (!v) return;
    setGroup(v);
    announce(E.groupLabel(v, show.bars) + (selectedCue ? " set on the selected cue" : " set for new cues"));
  });
  $("lx-group-clear").addEventListener("click", function () {
    setGroup("all");
    announce("Back to all bars");
  });

  // ---------- looks: six house looks (keys 1-6) + up to four of yours (7 8 9 0) ----------
  var USER_KEYS = ["7", "8", "9", "0"];
  function paintLooks() {
    var box = $("lx-looks"); box.innerHTML = "";
    E.LOOKS.forEach(function (l, i) {
      var b = document.createElement("button"); b.type = "button"; b.className = "lx-look";
      b.innerHTML = '<i style="background:' + l.color + '" aria-hidden="true"></i>' + esc(l.name) + ' <span class="lx-kbd" aria-hidden="true">' + (i + 1) + '</span>';
      b.setAttribute("aria-label", l.name + " — apply this look to the selected cue or add a cue at the playhead (key " + (i + 1) + ")");
      b.title = (selectedCue ? "Apply to the selected cue" : "Add a cue at the playhead with this look") + " — key " + (i + 1);
      b.addEventListener("click", function () { applyLook(l); });
      box.appendChild(b);
    });
    // the rest of the stock palette - no shortcut, but on the page from the
    // first load so the studio never looks like a six-colour tool
    (E.PALETTE || []).forEach(function (l) {
      var b = document.createElement("button"); b.type = "button"; b.className = "lx-look";
      b.innerHTML = '<i style="background:' + l.color + '" aria-hidden="true"></i>' + esc(l.name) +
        (l.move ? ' <span class="lx-kbd" aria-hidden="true">' + l.move.charAt(0).toUpperCase() + '</span>' : "");
      b.setAttribute("aria-label", l.name + " — " + l.intensity + "%, fade " + l.fade + " s" +
        (l.move ? ", " + l.move : "") + ". Apply to the selected cue or add a cue at the playhead.");
      b.title = selectedCue ? "Apply to the selected cue" : "Add a cue at the playhead with this look";
      b.addEventListener("click", function () { applyLook(l); });
      box.appendChild(b);
    });
    (show.looks || []).forEach(function (l, i) {
      var wrap = document.createElement("span"); wrap.className = "lx-look is-user";
      var b = document.createElement("button"); b.type = "button"; b.className = "lx-look-apply";
      var key = USER_KEYS[i];
      b.innerHTML = '<i style="background:' + l.color + '" aria-hidden="true"></i>' + esc(l.name) +
        (key ? ' <span class="lx-kbd" aria-hidden="true">' + key + '</span>' : "");
      b.setAttribute("aria-label", l.name + " (your look, " + l.intensity + "%, fade " + l.fade + " s) — apply to the selected cue or add a cue at the playhead" + (key ? " (key " + key + ")" : ""));
      b.addEventListener("click", function () { applyLook(l); });
      var x = document.createElement("button"); x.type = "button"; x.className = "lx-look-x"; x.textContent = "×"; x.setAttribute("aria-label", "Remove the look " + l.name);
      x.addEventListener("click", function () { record("look-remove"); show.looks.splice(i, 1); markDirty(); paintLooks(); announce("Look " + l.name + " removed"); });
      wrap.appendChild(b); wrap.appendChild(x); box.appendChild(wrap);
    });
  }
  function applyLook(l) {
    if (selectedCue) {
      record("look:" + selectedCue._id);
      selectedCue.color = l.color; selectedCue.intensity = l.intensity; selectedCue.fade = l.fade;
      selectedCue.look = l.key || "";
      selectedCue.move = l.move || "";        // a look may carry movement (strobe, chase)
      if (!selectedCue.note) selectedCue.note = l.name;
      own(selectedCue); markDirty(); renderCues(); announce(l.name + " applied");
    }
    else if (buffer || runStart !== null) addCue(l);
  }
  $("lx-look-save").addEventListener("click", function () {
    var hint = $("lx-look-form-hint");
    if (!selectedCue) { hint.textContent = "Select a cue first — its colour, intensity and fade become the look."; announce(hint.textContent); return; }
    show.looks = show.looks || [];
    if (show.looks.length >= MAX_USER_LOOKS) { hint.textContent = "That is " + MAX_USER_LOOKS + " of your own looks — remove one first."; announce(hint.textContent); return; }
    var name = ($("lx-look-name").value || "").trim() || selectedCue.note || ("Look " + (show.looks.length + 1));
    addUserLook(name, selectedCue.color, selectedCue.intensity, selectedCue.fade, hint);
  });

  function addUserLook(name, color, intensity, fade, hint) {
    show.looks = show.looks || [];
    record("look-save");
    show.looks.push({key: "user-" + Date.now().toString(36) + show.looks.length,
                     name: (name || "Look").slice(0, 24), color: color,
                     intensity: intensity, fade: fade, user: true});
    $("lx-look-name").value = "";
    var key = USER_KEYS[show.looks.length - 1];
    var msg = "“" + name + "” added to Looks" + (key ? " — key " + key : " (no shortcut left, click it)") +
      ". It travels with the show.";
    if (hint) hint.textContent = msg;
    markDirty(); paintLooks(); announce(msg);
  }

  // Mix a look with no cue selected. Before this, the colour mixer could
  // only be reached through a cue's swatch - so with no song loaded there
  // were no cues, and no way to reach it at all.
  $("lx-look-new").addEventListener("click", function () {
  });

  // ---------- colour: one wheel, always on the page ----------
  // Named after the gels people actually carry; the native picker is one
  // tap away for anything else. Intensity never lives here.
  var GELS = [
    ["L106 Primary Red", "#e3001b"], ["L026 Bright Red", "#ff2d2d"], ["L164 Flame Red", "#ff4a1c"], ["L158 Deep Orange", "#ff7a00"], ["L204 Full CTO", "#ffb347"], ["L147 Apricot", "#ffc27a"],
    ["L010 Medium Yellow", "#ffd400"], ["L101 Yellow", "#fff200"], ["L139 Primary Green", "#00a651"], ["L124 Dark Green", "#0c7a3e"], ["L116 Medium Blue-Green", "#00b3a4"], ["L115 Peacock Blue", "#00aeef"],
    ["L118 Light Blue", "#3b82f6"], ["L132 Medium Blue", "#1d4ed8"], ["L119 Dark Blue", "#1a33c9"], ["L181 Congo Blue", "#2b0e8a"], ["L058 Lavender", "#b9a7ff"], ["L180 Dark Lavender", "#8b5cf6"],
    ["L126 Mauve", "#b63fa0"], ["L128 Bright Pink", "#ff3fa4"], ["L111 Dark Pink", "#ff6fb5"], ["L201 Full CTB", "#cfe6ff"], ["L202 Half CTB", "#e8f1ff"], ["Open white", "#ffffff"],
    ["L003 Lavender Tint", "#f3e9ff"], ["L004 Medium Bastard Amber", "#ffd7a8"], ["L152 Pale Gold", "#fff1c9"], ["L156 Chocolate", "#8a5a2b"], ["L322 Soft Green", "#b9f3b0"], ["L068 Sky Blue", "#57b8ff"]
  ];
  // Gel names are kept only to LABEL a colour ("Flame red" reads better
  // than "#ff4a1c"). They are no longer a browsable list - one wheel and
  // one row of looks replaced five overlapping colour lists.
  function gelName(hex) { for (var i = 0; i < GELS.length; i++) if (GELS[i][1].toLowerCase() === String(hex || "").toLowerCase()) return GELS[i][0]; return null; }
  function setCueColor(c, hex, sw) {
    if (!/^#[0-9a-f]{6}$/i.test(hex)) return;
    record("color:" + c._id); c.color = hex; own(c);
    if (sw) { sw.style.background = hex; sw.classList.toggle("is-black", E.isBlackout(c)); sw.setAttribute("aria-label", "Cue colour " + (gelName(hex) || hex) + " — edit it on the colour wheel"); }
    markDirty();
  }

  // The wheel edits whatever is selected. gelFor is the cue it is pointed
  // at, or a scratch colour when nothing is selected.
  var gelFor = {color: "#ffb347", intensity: 85, fade: 1.0, t: 0, _id: "__scratch__"};
  var gelMode = "look";
  function gelSummary() {
    var what = gelName(gelFor.color) || gelFor.color;
    if (gelMode === "look") return what + " — no cue selected, so this is just a mixer.";
    return "Recolouring the cue at " + E.fmtTimecode(gelFor.t) + " · intensity stays " + gelFor.intensity + "%";
  }
  function aimWheelAt(cue) {
    // Point the wheel at the selected cue, or back at the scratch colour.
    if (cue) { gelMode = "cue"; gelFor = cue; }
    else { gelMode = "look"; gelFor = {color: gelFor.color, intensity: 85, fade: 1.0, t: 0, _id: "__scratch__"}; }
    paintMix(/^#[0-9a-f]{6}$/i.test(gelFor.color) ? gelFor.color : "#ffb347");
    // the label has to follow the target, not wait for the next colour change
    $("lx-gel-for").textContent = gelSummary();
  }

  // ---------- the mixer: RGB and HSV, kept in step ----------
  var mixIds = {r: "lx-mix-r", g: "lx-mix-g", b: "lx-mix-b", h: "lx-mix-h", s: "lx-mix-s", v: "lx-mix-v"};
  var mixing = false;                 // guards the two-way sync from looping
  function paintMix(hex) {
    var rgb = E.hexRgb(hex), hsv = E.rgbToHsv(rgb);
    mixing = true;
    $(mixIds.r).value = rgb[0]; $(mixIds.g).value = rgb[1]; $(mixIds.b).value = rgb[2];
    $(mixIds.h).value = hsv[0]; $(mixIds.s).value = hsv[1]; $(mixIds.v).value = hsv[2];
    ["r", "g", "b", "h", "s", "v"].forEach(function (k) { $(mixIds[k] + "-v").textContent = $(mixIds[k]).value; });
    mixing = false;
    var sw = $("lx-gel-swatch"); if (sw) sw.style.background = hex;
    var nm = $("lx-gel-name"); if (nm) nm.textContent = gelName(hex) || hex;
    $("lx-gel-hex").value = hex;
    paintWheel(hsv);
  }
  function mixFrom(space) {
    if (mixing) return;
    var hex;
    if (space === "rgb") {
      hex = E.rgbHex([+$(mixIds.r).value, +$(mixIds.g).value, +$(mixIds.b).value]);
    } else {
      hex = E.rgbHex(E.hsvToRgb([+$(mixIds.h).value, +$(mixIds.s).value, +$(mixIds.v).value]));
    }
    paintMix(hex);
    if (gelFor) applyGelColor(hex, null, false);
  }
  ["r", "g", "b"].forEach(function (k) { $(mixIds[k]).addEventListener("input", function () { mixFrom("rgb"); }); });
  ["h", "s", "v"].forEach(function (k) { $(mixIds[k]).addEventListener("input", function () { mixFrom("hsv"); }); });

  // ---------- the colour wheel ----------
  // Hue around the circumference, saturation from the centre out, V on its
  // own slider. One gesture instead of three, which is how every lighting
  // desk does it. The face is drawn once at full brightness; V is a black
  // scrim over it, which is exactly what scaling V does to the colour.
  var wheel = $("lx-wheel"), wg2 = wheel.getContext("2d"), wheelFace = null;
  var WHEEL_R = 100;                       // the canvas is 200x200 backing pixels

  function buildWheelFace() {
    if (wheelFace) return wheelFace;
    wheelFace = document.createElement("canvas");
    wheelFace.width = wheelFace.height = WHEEL_R * 2;
    var g = wheelFace.getContext("2d");
    var img = g.createImageData(WHEEL_R * 2, WHEEL_R * 2), d = img.data;
    for (var y = 0; y < WHEEL_R * 2; y++) {
      for (var x = 0; x < WHEEL_R * 2; x++) {
        var dx = x - WHEEL_R + 0.5, dy = y - WHEEL_R + 0.5;
        var dist = Math.sqrt(dx * dx + dy * dy), i = (y * WHEEL_R * 2 + x) * 4;
        if (dist > WHEEL_R) { d[i + 3] = 0; continue; }
        // 0deg at the top, clockwise - reads like a colour wheel, not maths
        var hue = (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
        var rgb = E.hsvToRgb([hue, Math.min(100, dist / WHEEL_R * 100), 100]);
        d[i] = rgb[0]; d[i + 1] = rgb[1]; d[i + 2] = rgb[2];
        // feather the last pixel so the rim is not stair-stepped
        d[i + 3] = dist > WHEEL_R - 1 ? Math.round(255 * (WHEEL_R - dist)) : 255;
      }
    }
    g.putImageData(img, 0, 0);
    return wheelFace;
  }

  function paintWheel(hsv) {
    var face = buildWheelFace();
    wg2.clearRect(0, 0, WHEEL_R * 2, WHEEL_R * 2);
    wg2.drawImage(face, 0, 0);
    // V as a black scrim: multiplying the face by V is what V means
    var v = Math.max(0, Math.min(100, hsv[2])) / 100;
    if (v < 1) {
      wg2.save();
      wg2.globalCompositeOperation = "source-atop";
      wg2.fillStyle = "rgba(0,0,0," + (1 - v).toFixed(3) + ")";
      wg2.fillRect(0, 0, WHEEL_R * 2, WHEEL_R * 2);
      wg2.restore();
    }
    // handle
    var ang = (hsv[0] - 90) * Math.PI / 180, rad = hsv[1] / 100 * WHEEL_R;
    var hx = WHEEL_R + Math.cos(ang) * rad, hy = WHEEL_R + Math.sin(ang) * rad;
    wg2.beginPath(); wg2.arc(hx, hy, 9, 0, 7);
    wg2.strokeStyle = "rgba(0,0,0,0.8)"; wg2.lineWidth = 4; wg2.stroke();
    wg2.strokeStyle = "#ffffff"; wg2.lineWidth = 2; wg2.stroke();
  }

  function wheelPick(clientX, clientY) {
    var r = wheel.getBoundingClientRect();
    // the canvas is 200 backing px shown at whatever CSS size, so scale
    var x = (clientX - r.left) / r.width * WHEEL_R * 2 - WHEEL_R;
    var y = (clientY - r.top) / r.height * WHEEL_R * 2 - WHEEL_R;
    var dist = Math.sqrt(x * x + y * y);
    var hue = (Math.atan2(x, -y) * 180 / Math.PI + 360) % 360;
    var sat = Math.min(100, dist / WHEEL_R * 100);
    setMixHsv([Math.round(hue), Math.round(sat), +$(mixIds.v).value]);
  }
  function setMixHsv(hsv) {
    var hex = E.rgbHex(E.hsvToRgb(hsv));
    paintMix(hex);
    if (gelFor) applyGelColor(hex, null, false);
  }

  var wheelDrag = false;
  wheel.addEventListener("pointerdown", function (e) {
    wheelDrag = true; wheel.setPointerCapture(e.pointerId); wheelPick(e.clientX, e.clientY); e.preventDefault();
  });
  wheel.addEventListener("pointermove", function (e) { if (wheelDrag) wheelPick(e.clientX, e.clientY); });
  function wheelUp(e) { wheelDrag = false; try { wheel.releasePointerCapture(e.pointerId); } catch (err) {} }
  wheel.addEventListener("pointerup", wheelUp);
  wheel.addEventListener("pointercancel", wheelUp);
  wheel.addEventListener("keydown", function (e) {
    var h = +$(mixIds.h).value, s = +$(mixIds.s).value, step = e.shiftKey ? 10 : 2;
    if (e.key === "ArrowLeft") h -= step * 3;
    else if (e.key === "ArrowRight") h += step * 3;
    else if (e.key === "ArrowUp") s += step;
    else if (e.key === "ArrowDown") s -= step;
    else return;
    e.preventDefault();
    setMixHsv([(Math.round(h) + 360) % 360, Math.max(0, Math.min(100, Math.round(s))), +$(mixIds.v).value]);
  });
  // "Save as look" keeps the wheel's colour as a chip you can click again.
  $("lx-look-new").addEventListener("click", function () {
    var hint = $("lx-look-form-hint");
    var hex = $("lx-gel-hex").value.trim();
    if (!/^#[0-9a-f]{6}$/i.test(hex)) return;
    if ((show.looks || []).length >= MAX_USER_LOOKS) {
      hint.textContent = "That is " + MAX_USER_LOOKS + " of your own looks — remove one first.";
      announce(hint.textContent);
      return;
    }
    var name = ($("lx-look-name").value || "").trim() || gelName(hex) || hex;
    addUserLook(name, hex, gelFor.intensity || 85, gelFor.fade == null ? 1.0 : gelFor.fade, hint);
  });

  function applyGelColor(hex, name, syncMix) {
    if (!gelFor) return;
    if (gelMode === "look") {
      // a scratch colour, not a cue - nothing is recorded or marked dirty
      gelFor.color = hex;
    } else {
      var row = cuesWrap.querySelector('[data-id="' + gelFor._id + '"]'), sw = row ? row.querySelector(".lx-swatch") : null;
      setCueColor(gelFor, hex, sw);
    }
    $("lx-gel-for").textContent = gelSummary();
    if (syncMix !== false) paintMix(hex);
    else { $("lx-gel-hex").value = hex; var s = $("lx-gel-swatch"); if (s) s.style.background = hex; }
    if (name) announce(name + " set");
  }
  function pickGel(hex, name) { applyGelColor(hex, name || hex, true); }
  $("lx-gel-hex").addEventListener("change", function () { var v = $("lx-gel-hex").value.trim(); if (/^#?[0-9a-f]{6}$/i.test(v)) pickGel(v[0] === "#" ? v : "#" + v, null); });

  // ---------- rig ----------
  var barsSel = $("lx-bars");
  for (var b = 2; b <= 10; b++) { var o = document.createElement("option"); o.value = b; o.textContent = b + " bars"; o.selected = b === show.bars; barsSel.appendChild(o); }
  barsSel.addEventListener("change", function () {
    // Changing the bar count is a rig change: bar-specific cues follow the
    // position they were written for rather than going dark.
    record("bars");
    var was = show.bars, next = parseInt(barsSel.value, 10);
    var moved = show.cues.filter(function (c) { return E.remapGroup(c.group, was, next) !== c.group; }).length;
    show.cues = E.remapCues(show.cues, was, next);
    show.bars = next;
    if (selectedBar > show.bars) selectBar(null);
    selectedCue = null; ensureIds();
    markDirty(); renderCues(); paintGroups(); paintBarCtl(); paintRigList();
    if (moved) announce(moved + " cue" + (moved === 1 ? "" : "s") + " moved to the matching bar on a " + next + "-bar rig");
  });
  var chansSel = $("lx-chans"); chansSel.value = String(show.chans || 4);
  chansSel.addEventListener("change", function () { record("chans"); show.chans = parseInt(chansSel.value, 10); markDirty(); paintBarCtl(); paintBarsList(now()); });
  // DMX patch: first address (the run) and the universe label
  var dmxStartEl = $("lx-dmx-start"), dmxUniEl = $("lx-dmx-universe");
  function paintRig() {
    barsSel.value = String(show.bars); chansSel.value = String(show.chans);
    dmxStartEl.value = String(show.dmxStart || 1); dmxUniEl.value = String(show.dmxUniverse || 1);
    paintRigList();
  }

  // ---------- rig profiles (epic 2) ----------
  // The show stores looks and group ROLES, so it compiles onto any rig.
  // Applying a rig with a different bar count remaps bar-specific cues to
  // the matching position (engine: remapCues) instead of leaving them dark.
  var rigs = Array.isArray(lib.rigs) ? lib.rigs : [];
  var rigSel = $("lx-rig-select"), rigStatus = $("lx-rig-status");
  function rigStatusText(msg) { rigStatus.textContent = msg || ""; }
  function paintRigList() {
    if (!rigSel) return;
    var cur = rigSel.value;
    rigSel.innerHTML = '<option value="">— this show\'s own rig —</option>';
    var mine = document.createElement("optgroup"); mine.label = "Your rigs";
    rigs.forEach(function (r) {
      var o = document.createElement("option"); o.value = "saved:" + r.id;
      o.textContent = r.name + " · " + ((r.data && r.data.bars) || "?") + " bars" + (r.venue_key ? " · venue" : "");
      mine.appendChild(o);
    });
    if (rigs.length) rigSel.appendChild(mine);
    var pre = document.createElement("optgroup"); pre.label = "Presets";
    E.RIG_PRESETS.forEach(function (p) {
      var o = document.createElement("option"); o.value = "preset:" + p.key;
      o.textContent = p.name + " · " + p.bars + " bars";
      pre.appendChild(o);
    });
    rigSel.appendChild(pre);
    rigSel.value = cur && rigSel.querySelector('[value="' + cur.replace(/"/g, "") + '"]') ? cur : "";
    $("lx-rig-delete").disabled = rigSel.value.indexOf("saved:") !== 0;
    var now = $("lx-rig-now");
    if (now) now.textContent = "· " + (show.rigName ? show.rigName + " — " : "") + show.bars + " bars, " + (show.chans === 3 ? "RGB" : "dimmer + RGB");
  }
  function selectedRig() {
    var v = rigSel.value;
    if (v.indexOf("preset:") === 0) {
      var k = v.slice(7), hit = null;
      E.RIG_PRESETS.forEach(function (p) { if (p.key === k) hit = p; });
      return hit;
    }
    if (v.indexOf("saved:") === 0) {
      var id = v.slice(6), r = null;
      rigs.forEach(function (x) { if (x.id === id) r = x; });
      if (!r) return null;
      var d = r.data || {};
      return {key: r.id, name: r.name, bars: d.bars, chans: d.chans, pos: d.pos, rot: d.rot, dmxStart: d.dmxStart, dmxAddr: d.dmxAddr};
    }
    return null;
  }
  rigSel.addEventListener("change", function () {
    $("lx-rig-delete").disabled = rigSel.value.indexOf("saved:") !== 0;
    var r = selectedRig();
    if (!r) { rigStatusText(""); return; }
    rigStatusText(r.bars === show.bars
      ? "“" + r.name + "” is " + r.bars + " bars, same as now — layout and patch would change, cues stay put."
      : "“" + r.name + "” is " + r.bars + " bars (you have " + show.bars + "). Applying moves bar-specific cues to the matching position; roles like All / Odd / Pairs are unchanged.");
  });
  $("lx-rig-apply").addEventListener("click", function () {
    var r = selectedRig();
    if (!r) { rigStatusText("Pick a rig to apply first."); return; }
    var was = show.bars, moved = show.cues.filter(function (c) { return E.remapGroup(c.group, was, r.bars) !== c.group; }).length;
    record("rig");
    E.applyRig(show, r);
    selectedBar = null; selectedCue = null;
    ensureIds(); markDirty(); paintRig(); renderCues(); paintGroups(); paintBarCtl(); paintBarsList(now());
    var msg = "Applied “" + r.name + "” — " + show.bars + " bars" + (moved ? ", " + moved + " cue" + (moved === 1 ? "" : "s") + " remapped to the matching position" : ", every cue kept its group") + ". Undo puts it back.";
    rigStatusText(msg); announce(msg);
  });
  $("lx-rig-save").addEventListener("click", function () {
    var name = ($("lx-rig-name").value || "").trim() || show.rigName || "Rig " + show.bars + " bars";
    var body = {id: "", name: name, venue: ($("lx-rig-venue").value || "").trim(), data: E.rigFromShow(show, name)};
    var sel = rigSel.value;
    if (sel.indexOf("saved:") === 0) body.id = sel.slice(6);      // update the loaded rig in place
    rigStatusText("Saving rig…");
    post("/lights/rigs/save", body).then(function (d) {
      if (!d || !d.ok) { rigStatusText((d && d.error) || "Rig not saved."); return; }
      rigs = d.rigs || rigs;
      show.rigKey = d.id; show.rigName = name; markDirty();
      $("lx-rig-name").value = "";
      paintRigList(); rigSel.value = "saved:" + d.id; $("lx-rig-delete").disabled = false;
      var v = ($("lx-rig-venue").value || "").trim();
      rigStatusText("Saved “" + name + "”" + (v ? " and bound it to " + v + " — linking a show to a tour date there will offer it." : "."));
      announce("Rig saved");
    });
  });
  $("lx-rig-delete").addEventListener("click", function () {
    var sel = rigSel.value;
    if (sel.indexOf("saved:") !== 0) return;
    var id = sel.slice(6), name = "";
    rigs.forEach(function (r) { if (r.id === id) name = r.name; });
    if (!window.confirm("Delete the rig “" + name + "”? Shows that used it keep their current layout.")) return;
    post("/lights/rigs/" + id + "/delete", {}).then(function (d) {
      if (!d || !d.ok) return;
      rigs = d.rigs || [];
      rigSel.value = ""; paintRigList();
      rigStatusText("Deleted “" + name + "”."); announce("Rig deleted");
    });
  });
  // Venue pack: linking a show to a tour date offers the rig bound to that
  // room. Offers — never swaps the rig under you.
  function offerVenueRig() {
    var opt = $("lx-tourshow").selectedOptions && $("lx-tourshow").selectedOptions[0];
    var key = opt ? opt.getAttribute("data-venue-key") : "";
    if (!key) return;
    var hit = null;
    rigs.forEach(function (r) { if (r.venue_key && r.venue_key === key) hit = r; });
    if (!hit || hit.id === show.rigKey) return;
    $("lx-rig-fold").open = true;
    rigSel.value = "saved:" + hit.id; $("lx-rig-delete").disabled = false;
    var msg = "You have a rig saved for " + (opt.getAttribute("data-venue") || "this venue") + ": “" + hit.name + "” (" + ((hit.data && hit.data.bars) || "?") + " bars). Apply it to this show?";
    rigStatusText(msg); announce(msg);
  }
  dmxStartEl.addEventListener("change", function () {
    var v = parseInt(dmxStartEl.value, 10); if (!(v >= 1 && v <= 512)) v = 1;
    record("dmx"); show.dmxStart = v; dmxStartEl.value = String(v); markDirty(); paintBarCtl(); paintBarsList(now());
    announce("Bar 1 starts at DMX " + v + "; the rest follow");
  });
  dmxUniEl.addEventListener("change", function () {
    var v = parseInt(dmxUniEl.value, 10); if (!(v >= 1 && v <= 64)) v = 1;
    show.dmxUniverse = v; dmxUniEl.value = String(v); markDirty(); if (writer) paintDmxLive();
  });

  // ---------- draft autosave, library, unsaved-work protection ----------
  // Two layers. The DRAFT is the working copy (POST /lights/save): every
  // change lands there 1.5 s later, so a crash loses nothing. The LIBRARY
  // is only written by "Save to library", which also takes a version.
  // Autosave never touches a library row.
  var savedEl = $("lx-saved");
  function paintSaved(state, text) { savedEl.className = "lx-saved" + (state ? " is-" + state : ""); savedEl.textContent = text; }
  function paintLibDirty() {
    var el = $("lx-libdirty"); if (!el) return;
    if (show.libraryId) { el.textContent = libraryDirty ? "unsaved changes" : "saved to library"; el.className = "lx-libdirty" + (libraryDirty ? " is-dirty" : " is-ok"); }
    else { el.textContent = show.cues.length ? "not in library yet" : ""; el.className = "lx-libdirty"; }
  }
  function payload() {
    var out = {}; Object.keys(show).forEach(function (k) { out[k] = show[k]; });
    out.cues = show.cues.map(function (c) { var d = {}; Object.keys(c).forEach(function (k) { if (k !== "_id") d[k] = c[k]; }); return d; });
    return out;
  }
  function markDirty(touchLibrary) {
    dirty = true;
    if (touchLibrary !== false && show.libraryId) libraryDirty = true;
    paintSaved("dirty", "Saving draft…"); paintLibDirty();
    clearTimeout(saveTimer); saveTimer = setTimeout(autosave, 1500);
  }
  function post(url, body) {
    return fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)}).then(function (r) { return r.json(); });
  }
  function draftPayload() {
    var data = payload();
    data.draftDirty = !!(show.libraryId && libraryDirty);
    data.draftSavedAt = new Date().toISOString();
    return data;
  }
  function autosave() {
    if (!dirty) return;
    paintSaved("", "Saving draft…");
    post("/lights/save", draftPayload()).then(function (d) {
      if (d && d.ok) { dirty = false; paintSaved("ok", "Draft saved ✓ " + new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})); }
      else paintSaved("dirty", "Draft not saved — will retry");
    }).catch(function () { paintSaved("dirty", "Offline — draft will retry"); });
  }
  window.addEventListener("beforeunload", function (e) {
    if (dirty || libraryDirty) { e.preventDefault(); e.returnValue = ""; return ""; }
  });
  // Unsaved draft on load: the working copy carries edits a library show
  // never received. Ask, don't guess.
  function maybeOfferDraft() {
    var bar = $("lx-draft-prompt");
    if (!bar || !saved || !saved.libraryId || !saved.draftDirty) return;
    libraryDirty = true; paintLibDirty();
    var when = saved.draftSavedAt ? new Date(saved.draftSavedAt).toLocaleString([], {hour: "2-digit", minute: "2-digit", month: "short", day: "numeric"}) : "earlier";
    $("lx-draft-text").textContent = "You have an unsaved draft of “" + (saved.name || "this show") + "” from " + when + ". Keep working on it, or open the last library save?";
    bar.hidden = false;
    $("lx-draft-keep").onclick = function () { bar.hidden = true; announce("Draft kept"); };
    $("lx-draft-discard").onclick = function () {
      fetch("/lights/library/" + saved.libraryId).then(function (r) { return r.json(); }).then(function (d) {
        bar.hidden = true;
        if (!d.ok) { announce("The library copy could not be loaded; draft kept"); return; }
        loadShowData(d.show.data, d.show); libraryDirty = false; paintLibDirty(); markDirty(false);
        announce("Opened the last library save");
      });
    };
  }
  function paintLibrary() {
    var sel = $("lx-lib-select"); sel.innerHTML = '<option value="">— working copy —</option>';
    lib.shows.forEach(function (s) { var op = document.createElement("option"); op.value = s.id; op.textContent = s.name + " · " + s.cue_count + " cues"; op.selected = s.id === show.libraryId; sel.appendChild(op); });
    $("lx-show-name").value = show.name || "";
    $("lx-track").value = show.trackId || ""; $("lx-tourshow").value = show.tourShowId || "";
    paintTrackShip();
    $("lx-lib-delete").disabled = !show.libraryId;
    paintLibDirty();
    loadVersions();
  }
  $("lx-show-name").addEventListener("input", function () { show.name = $("lx-show-name").value.slice(0, 120); markDirty(); });
  $("lx-track").addEventListener("change", function () { show.trackId = $("lx-track").value; markDirty(); paintTrackShip(); });
  $("lx-tourshow").addEventListener("change", function () { show.tourShowId = $("lx-tourshow").value; markDirty(); offerVenueRig(); });
  $("lx-lib-save").addEventListener("click", function () {
    paintSaved("", "Saving…");
    var data = payload();
    post("/lights/library/save", {id: show.libraryId || "", name: show.name || "Untitled show", data: data, track_id: show.trackId || "", tour_show_id: show.tourShowId || "", note: $("lx-version-note").value || ""})
      .then(function (d) {
        if (!d.ok) { paintSaved("dirty", "Save failed"); return; }
        show.libraryId = d.id; dirty = false; libraryDirty = false;
        lib.shows = d.shows || lib.shows; $("lx-version-note").value = "";
        paintSaved("ok", "Saved to library ✓ v" + d.versions);
        paintLibrary(); loadNotes(); announce("Saved to library, version " + d.versions);
        return post("/lights/save", draftPayload());
      });
  });
  $("lx-lib-select").addEventListener("change", function () {
    var id = $("lx-lib-select").value;
    if (!id) { show.libraryId = null; libraryDirty = false; paintLibrary(); loadNotes(); markDirty(false); return; }
    fetch("/lights/library/" + id).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) return;
      loadShowData(d.show.data, d.show); libraryDirty = false; paintLibDirty(); markDirty(false);
    });
  });
  function loadShowData(data, meta) {
    var keep = {bars: data.bars, chans: data.chans};
    show = data && data.cues ? data : {name: meta ? meta.name : "", bars: 6, chans: 4, cues: []};
    show.bars = Math.max(2, Math.min(10, show.bars || keep.bars || 6)); show.chans = show.chans === 3 ? 3 : 4;
    show.cues.forEach(function (c) { if (typeof c.note !== "string") c.note = ""; });
    show.looks = Array.isArray(show.looks) ? show.looks.slice(0, MAX_USER_LOOKS) : [];
    show.dmxStart = parseInt(show.dmxStart, 10) || 1; show.dmxUniverse = parseInt(show.dmxUniverse, 10) || 1; show.dmxAddr = show.dmxAddr || {};
    show.rigName = show.rigName || ""; show.rigKey = show.rigKey || null;
    output = show.output || "preview";
    delete show.draftDirty; delete show.draftSavedAt;
    if (meta) { show.libraryId = meta.id; show.name = meta.name; show.trackId = meta.track_id || ""; show.tourShowId = meta.tour_show_id || ""; }
    selectedCue = null; selectedBar = null; aimWheelAt(null);
    H.reset(); paintHistory();
    paintRig();
    renderCues(); paintGroups(); paintLooks(); paintLibrary(); paintBeats(); paintBarCtl(); paintAutoCue();
    loadNotes();                              // notes belong to the show, not the page
  }

  // ---------- import / export (JSON) ----------
  // A portable copy of the working copy: cues, rig, looks, patch, tempo.
  // Import replaces the working copy only — library saves stay put.
  function exportJson() {
    var data = payload(); delete data.libraryId;
    return {format: "street-banker-lights", version: 1, exported: new Date().toISOString(), show: data};
  }
  $("lx-export").addEventListener("click", function () {
    var blob = new Blob([JSON.stringify(exportJson(), null, 2)], {type: "application/json"});
    var a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = ((show.name || "light-show").replace(/[^\w\- ]+/g, "").trim() || "light-show") + ".lights.json";
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    $("lx-io-status").textContent = "Exported " + a.download; announce("Show exported as JSON");
  });
  function importShow(obj) {
    var s = obj && obj.show && Array.isArray(obj.show.cues) ? obj.show : (obj && Array.isArray(obj.cues) ? obj : null);
    if (!s) return "Not a Light Studio show file (no cues array).";
    var hex = /^#[0-9a-f]{6}$/i;
    var moves = E.MOVES.map(function (m) { return m[0]; });
    var clean = {name: String(s.name || "").slice(0, 120), bars: Math.max(2, Math.min(10, parseInt(s.bars, 10) || 6)), chans: s.chans === 3 ? 3 : 4,
                 bpm: +s.bpm || 0, beatOffset: +s.beatOffset || 0, snap: !!s.snap, pos: {}, rot: {}, dmxAddr: {}, looks: [], cues: [],
                 rigName: String(s.rigName || "").slice(0, 80), rigKey: null,
                 output: ["preview", "enttec", "artnet", "sacn"].indexOf(s.output) >= 0 ? s.output : "preview",
                 dmxStart: Math.max(1, Math.min(512, parseInt(s.dmxStart, 10) || 1)), dmxUniverse: Math.max(1, Math.min(64, parseInt(s.dmxUniverse, 10) || 1))};
    Object.keys(s.pos || {}).forEach(function (k) { var p = s.pos[k]; if (Array.isArray(p) && p.length === 2) clean.pos[k] = [clamp(+p[0] || 0, 0.03, 0.97), clamp(+p[1] || 0, 0.04, 0.92)]; });
    Object.keys(s.rot || {}).forEach(function (k) { clean.rot[k] = s.rot[k] === 90 ? 90 : 0; });
    Object.keys(s.dmxAddr || {}).forEach(function (k) { var a = parseInt(s.dmxAddr[k], 10); if (a >= 1 && a <= 512) clean.dmxAddr[k] = a; });
    (Array.isArray(s.looks) ? s.looks : []).slice(0, 4).forEach(function (l) {
      if (l && hex.test(l.color || "")) clean.looks.push({key: String(l.key || "user"), name: String(l.name || "Look").slice(0, 24), color: l.color, intensity: clamp(parseInt(l.intensity, 10) || 0, 0, 100), fade: Math.max(0, +l.fade || 0), user: true});
    });
    s.cues.forEach(function (c) {
      if (!c || typeof c !== "object") return;
      clean.cues.push({t: Math.max(0, +c.t || 0), group: typeof c.group === "string" ? c.group.slice(0, 40) : "all", color: hex.test(c.color || "") ? c.color : "#d8b25a",
                       intensity: clamp(parseInt(c.intensity, 10) || 0, 0, 100), fade: Math.max(0, +c.fade || 0), note: String(c.note || "").slice(0, 80), auto: !!c.auto,
                       move: moves.indexOf(c.move) > 0 ? c.move : "", rate: Math.max(0, Math.min(8, +c.rate || 0)) || undefined,
                       look: String(c.look || "").slice(0, 40)});
    });
    loadShowData(clean, null); show.libraryId = null; libraryDirty = false; paintLibrary(); markDirty(false);
    return null;
  }
  $("lx-import").addEventListener("change", function (e) {
    var f = e.target.files[0]; if (!f) return;
    if (show.cues.length && !window.confirm("Replace the current working copy with the imported show? Your library saves are untouched.")) { e.target.value = ""; return; }
    f.text().then(function (txt) {
      var err; try { err = importShow(JSON.parse(txt)); } catch (ex) { err = "That file is not valid JSON."; }
      $("lx-io-status").textContent = err || ("Imported " + f.name + " — " + show.cues.length + " cues. It's a new working copy, not in the library yet.");
      announce(err || "Show imported — " + show.cues.length + " cues"); e.target.value = "";
    });
  });
  $("lx-lib-new").addEventListener("click", function () {
    loadShowData({name: "", bars: show.bars, chans: show.chans, cues: []}, null);
    show.libraryId = null; show.name = ""; libraryDirty = false; paintLibrary(); markDirty(false);
  });
  $("lx-lib-delete").addEventListener("click", function () {
    if (!show.libraryId || !window.confirm("Delete this show from the library? Versions go with it.")) return;
    post("/lights/library/" + show.libraryId + "/delete", {}).then(function (d) {
      if (d.ok) { lib.shows = d.shows || []; show.libraryId = null; paintLibrary(); paintSaved("", "Deleted from library"); }
    });
  });
  function loadVersions() {
    var box = $("lx-versions");
    if (!box) return;
    if (!show.libraryId) { box.innerHTML = '<span class="lx-hint">Save to the library to start a version history.</span>'; return; }
    fetch("/lights/library/" + show.libraryId + "/versions").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) return;
      if (!d.versions.length) { box.innerHTML = '<span class="lx-hint">No versions yet.</span>'; return; }
      box.innerHTML = "";
      d.versions.forEach(function (v) {
        var line = document.createElement("div");
        line.textContent = v.saved_at.slice(0, 16).replace("T", " ") + " UTC · " + v.cue_count + " cues" + (v.note ? " · " + v.note : "");
        var btn = document.createElement("button"); btn.type = "button"; btn.className = "lx-btn lx-btn--ghost lx-btn--small"; btn.textContent = "Restore";
        btn.addEventListener("click", function () {
          post("/lights/library/" + show.libraryId + "/restore", {version_id: v.id}).then(function (r) {
            if (r.ok) { loadShowData(r.data, {id: show.libraryId, name: show.name, track_id: show.trackId, tour_show_id: show.tourShowId}); markDirty(); announce("Version restored into the draft — save to library to keep it"); }
          });
        });
        line.appendChild(btn); box.appendChild(line);
      });
    });
  }

  // ---------- share the show for notes (epic 5) ----------
  // The designer sends one show out and gets notes back on the timeline.
  // Notes anchor to a TIMECODE: payload() strips cue ids on save, so an
  // id would not survive the round trip, but 1:14 is still 1:14 after the
  // cue there is deleted.
  var notes = [], shares = [];

  function paintNoteSummary() {
    var open = notes.filter(function (n) { return !n.parent_id && !n.resolved; }).length;
    $("lx-note-now").textContent = open
      ? "· " + open + " open note" + (open === 1 ? "" : "s")
      : (shares.length ? "· " + shares.length + " live link" + (shares.length === 1 ? "" : "s") : "");
  }

  function loadNotes() {
    // Only a saved show can carry notes - they are filed against a
    // library row, and a working copy has not got one yet.
    if (!show.libraryId) { notes = []; shares = []; renderShares(); renderNotes(); return; }
    var id = show.libraryId;
    fetch("/lights/library/" + id + "/comments", {cache: "no-store"})
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok && show.libraryId === id) { notes = d.comments || []; renderNotes(); drawWave(now()); } })
      .catch(function () { /* offline: the studio still works without notes */ });
    fetch("/lights/library/" + id + "/shares", {cache: "no-store"})
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d.ok && show.libraryId === id) { shares = d.shares || []; renderShares(); } })
      .catch(function () {});
  }

  function renderShares() {
    var ul = $("lx-share-list");
    ul.textContent = "";
    shares.forEach(function (s) {
      var li = document.createElement("li");
      li.className = "lx-share-row";
      var url = location.origin + "/lights/show/" + s.token;
      var input = document.createElement("input");
      input.className = "lx-input"; input.type = "text"; input.readOnly = true; input.value = url;
      input.setAttribute("aria-label", "Share link" + (s.label ? " for " + s.label : ""));
      input.addEventListener("focus", function () { this.select(); });
      var who = document.createElement("span");
      who.className = "lx-hint";
      who.textContent = (s.label || "no label") + " · " + (s.permission === "comment" ? "can leave notes" : "watch only");
      var kill = document.createElement("button");
      kill.type = "button"; kill.className = "lx-btn lx-btn--ghost lx-btn--small";
      kill.textContent = "Revoke";
      kill.setAttribute("aria-label", "Revoke this link" + (s.label ? " for " + s.label : ""));
      kill.addEventListener("click", function () {
        post("/lights/share/" + s.token + "/revoke", {}).then(function () {
          shares = shares.filter(function (x) { return x.token !== s.token; });
          renderShares(); paintNoteSummary();
          announce("Link revoked — it opens to a dead page now.");
        });
      });
      li.appendChild(input); li.appendChild(who); li.appendChild(kill);
      ul.appendChild(li);
    });
    paintNoteSummary();
  }

  $("lx-share-new").addEventListener("click", function () {
    if (!show.libraryId) {
      $("lx-share-status").textContent = "Save this show to the library first — a link points at a saved show.";
      announce($("lx-share-status").textContent);
      return;
    }
    post("/lights/library/" + show.libraryId + "/share",
         {permission: $("lx-share-perm").value, label: $("lx-share-label").value})
      .then(function (d) {
        if (!d || !d.ok) { $("lx-share-status").textContent = "Could not make a link."; return; }
        shares = d.shares || shares;
        $("lx-share-label").value = "";
        $("lx-share-status").textContent = "Link ready — copy it from the list.";
        renderShares();
        announce("Share link created");
      });
  });

  function renderNotes() {
    var box = $("lx-note-threads");
    box.textContent = "";
    var tops = notes.filter(function (n) { return !n.parent_id; });
    if (!tops.length) {
      var p = document.createElement("p");
      p.className = "lx-hint";
      p.textContent = show.libraryId
        ? "No notes on this show yet. Anyone holding a link that allows notes can leave one."
        : "Save this show to the library to share it and collect notes.";
      box.appendChild(p);
      paintNoteSummary();
      return;
    }
    tops.forEach(function (n) {
      var wrap = document.createElement("article");
      wrap.className = "lx-note" + (n.resolved ? " is-done" : "");
      wrap.appendChild(noteHead(n));
      notes.filter(function (r) { return r.parent_id === n.id; }).forEach(function (r) {
        var re = noteHead(r); re.classList.add("is-reply"); wrap.appendChild(re);
      });
      wrap.appendChild(noteActions(n));
      box.appendChild(wrap);
    });
    paintNoteSummary();
  }

  function noteHead(n) {
    var el = document.createElement("div");
    el.className = "lx-note-item";
    var head = document.createElement("p");
    head.className = "lx-note-meta";
    var who = document.createElement("b"); who.textContent = n.author; head.appendChild(who);
    if (n.t !== null && n.t !== undefined) {
      var at = document.createElement("button");
      at.type = "button"; at.className = "lx-note-at"; at.textContent = "@ " + E.fmtClock(n.t);
      at.setAttribute("aria-label", "Move the playhead to " + E.fmtClock(n.t));
      at.addEventListener("click", function () {
        seek(n.t);
        // Bring the note into view if it is off-screen at this zoom;
        // jumping the playhead somewhere you cannot see is not a jump.
        if (n.t < view.start || n.t > view.end) panTo(n.t - (view.end - view.start) / 2);
      });
      head.appendChild(at);
    }
    var body = document.createElement("p");
    body.className = "lx-note-body";
    body.textContent = n.body;                     // textContent, never innerHTML
    el.appendChild(head); el.appendChild(body);
    return el;
  }

  function noteActions(n) {
    var row = document.createElement("div");
    row.className = "lx-note-actions";
    var reply = document.createElement("form");
    reply.className = "lx-note-reply";
    var input = document.createElement("input");
    input.className = "lx-input"; input.type = "text"; input.maxLength = 1200;
    input.placeholder = "Reply…"; input.setAttribute("aria-label", "Reply to " + n.author);
    var send = document.createElement("button");
    send.className = "lx-btn lx-btn--ghost lx-btn--small"; send.type = "submit"; send.textContent = "Reply";
    reply.appendChild(input); reply.appendChild(send);
    reply.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!input.value.trim()) return;
      post("/lights/library/" + show.libraryId + "/comment", {body: input.value, parent_id: n.id})
        .then(function (d) { if (d.ok) { notes = d.comments || notes; input.value = ""; renderNotes(); } });
    });
    var settle = document.createElement("button");
    settle.type = "button"; settle.className = "lx-btn lx-btn--ghost lx-btn--small";
    settle.textContent = n.resolved ? "Reopen" : "Settled";
    settle.setAttribute("aria-label", (n.resolved ? "Reopen" : "Mark settled") + " — the note from " + n.author);
    settle.addEventListener("click", function () {
      post("/lights/comments/" + n.id + "/resolve", {resolved: !n.resolved}).then(function (d) {
        if (!d.ok) return;
        n.resolved = !n.resolved; renderNotes(); drawWave(now());
        announce(n.resolved ? "Note settled" : "Note reopened");
      });
    });
    var drop = document.createElement("button");
    drop.type = "button"; drop.className = "lx-btn lx-btn--ghost lx-btn--small";
    drop.textContent = "Delete";
    drop.setAttribute("aria-label", "Delete the note from " + n.author + " and its replies");
    drop.addEventListener("click", function () {
      post("/lights/comments/" + n.id + "/delete", {}).then(function (d) {
        if (!d.ok) return;
        notes = notes.filter(function (x) { return x.id !== n.id && x.parent_id !== n.id; });
        renderNotes(); drawWave(now());
        announce("Note deleted");
      });
    });
    row.appendChild(reply); row.appendChild(settle); row.appendChild(drop);
    return row;
  }

  // ---------- phone remote (epic 3) ----------
  // The laptop stays the source of truth. The phone can only enqueue a
  // press; this end decides what to do with it, and ignores anything it
  // does not recognise. There is no WebSocket in this stack, so the laptop
  // polls - fast enough that a blackout lands about as quickly as a key.
  var remoteCode = "", remoteTimer = null, remoteLastSeen = "", remoteQuietSince = 0;
  // Fast while the show is live, because a blackout from the phone has to
  // land like a key press. Slower once the rig has been sitting quiet, so
  // a remote left paired overnight is not 2.5 requests a second for
  // twelve hours. Any press, or hitting play, snaps it back to fast.
  var REMOTE_POLL_MS = 400, REMOTE_IDLE_MS = 1500, REMOTE_QUIET_AFTER = 90000;

  function remoteInterval() {
    if (playing || runStart !== null) return REMOTE_POLL_MS;
    if (!remoteQuietSince || Date.now() - remoteQuietSince < REMOTE_QUIET_AFTER) return REMOTE_POLL_MS;
    return REMOTE_IDLE_MS;
  }
  function armRemotePoll() {
    if (remoteTimer) clearInterval(remoteTimer);
    var ms = remoteInterval();
    remoteTimer = setInterval(function () {
      pollRemote();
      if (remoteInterval() !== ms) armRemotePoll();      // re-arm when the pace should change
    }, ms);
  }

  function paintRemote() {
    var on = !!remoteCode;
    $("lx-rem-start").hidden = on;
    $("lx-rem-end").hidden = !on;
    $("lx-rem-pair").hidden = !on;
    $("lx-rem-now").textContent = on
      ? "· " + (remoteLastSeen ? "phone connected" : "waiting for the phone")
      : "";
  }

  $("lx-rem-start").addEventListener("click", function () {
    post("/lights/remote/start", {}).then(function (d) {
      if (!d || !d.ok) { $("lx-rem-status").textContent = "Could not start a remote."; return; }
      remoteCode = d.code; remoteLastSeen = "";
      $("lx-rem-qr").src = "/lights/remote/" + d.code + "/qr.svg";
      $("lx-rem-url").value = d.url;
      $("lx-rem-status").textContent = "Scan the code. The remote ends when you press End, or after 12 hours.";
      $("lx-rem-fold").open = true;
      remoteQuietSince = Date.now();
      paintRemote(); armRemotePoll();
      announce("Phone remote started");
    });
  });
  $("lx-rem-end").addEventListener("click", function () {
    post("/lights/remote/end", {}).then(function () {
      remoteCode = ""; remoteLastSeen = "";
      if (remoteTimer) { clearInterval(remoteTimer); remoteTimer = null; }
      $("lx-rem-status").textContent = "Remote ended.";
      $("lx-rem-seen").textContent = "";
      paintRemote();
      announce("Phone remote ended");
    });
  });
  $("lx-rem-url").addEventListener("focus", function () { this.select(); });

  // A reload mid-set must not silently orphan the phone. The server still
  // holds the pairing, so pick it back up rather than making the operator
  // walk over and re-scan.
  function resumeRemote() {
    fetch("/lights/remote/poll", {cache: "no-store"})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok || !d.code) return;
        remoteCode = d.code;
        $("lx-rem-qr").src = "/lights/remote/" + d.code + "/qr.svg";
        $("lx-rem-url").value = location.origin + "/lights/remote/" + d.code;
        $("lx-rem-status").textContent = "A phone remote is still paired from before this page reloaded.";
        remoteQuietSince = Date.now();
        paintRemote(); armRemotePoll();
      })
      .catch(function () { /* offline: no remote to resume */ });
  }

  function pollRemote() {
    if (!remoteCode) return;
    fetch("/lights/remote/poll", {cache: "no-store"})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) return;
        if (d.phone_seen && d.phone_seen !== remoteLastSeen) {
          remoteLastSeen = d.phone_seen;
          $("lx-rem-seen").textContent = "Phone last heard from " + String(d.phone_seen).slice(11, 16) + " UTC.";
          paintRemote();
        }
        if (d.commands && d.commands.length) { remoteQuietSince = Date.now(); armRemotePoll(); }
        (d.commands || []).forEach(applyRemoteCommand);
      })
      .catch(function () { /* a dropped poll is not worth surfacing; the next one retries */ });
  }

  function applyRemoteCommand(c) {
    switch (c.kind) {
      case "ping": return;                       // keep-alive only
      case "blackout": if (!panic) togglePanic(); return;
      case "restore": if (panic) togglePanic(); return;
      case "play": togglePlay(); return;
      case "stop": stopAll(); return;
      case "tap": $("lx-tap").click(); return;
      case "next": if (setlist && setIndex < setlist.items.length - 1) loadSetlistItem(setIndex + 1); return;
      case "prev": if (setlist && setIndex > 0) loadSetlistItem(setIndex - 1); return;
      case "look": {
        // A phone press busks the stage; it must never edit the cue list,
        // which the operator cannot see happening from across the room.
        var n = parseInt(c.value, 10);
        if (n >= 1 && n <= E.LOOKS.length) setBump(E.LOOKS[n - 1]);
        return;
      }
      default: return;                           // unknown: ignore, never guess
    }
  }

  // ---------- the show ships with the song (epic 6) ----------
  // Cues store looks and group ROLES, not channel numbers, so a show
  // attached to a track renders on whatever rig the puller has.
  var trackShows = (lib.track_shows && typeof lib.track_shows === "object") ? lib.track_shows : {};

  function paintTrackShip() {
    var tid = $("lx-track").value;
    var attach = $("lx-attach"), pull = $("lx-pull");
    attach.disabled = !tid || !show.cues.length;
    attach.title = !tid ? "Pick the track this show belongs to first"
      : (!show.cues.length ? "Nothing to ship yet — add some cues" : "Attach this show to the track");
    var has = tid && trackShows[tid];
    pull.hidden = !has;
    if (has) pull.title = "“" + has.name + "” — " + has.cue_count + " cues, attached " + String(has.saved_at).slice(0, 10);
  }
  $("lx-attach").addEventListener("click", function () {
    var tid = $("lx-track").value;
    if (!tid) return;
    post("/lights/track/" + tid + "/attach",
         {name: show.name || "Untitled show", data: payload(), show_id: show.libraryId || ""})
      .then(function (d) {
        if (!d.ok) { $("lx-io-status").textContent = "Could not attach to that track."; return; }
        trackShows = d.tracks || trackShows;
        paintTrackShip();
        $("lx-io-status").textContent = "Attached to the track.";
        announce("This show now travels with the track — " + d.attached.cue_count + " cues.");
      });
  });
  $("lx-pull").addEventListener("click", function () {
    var tid = $("lx-track").value;
    if (!tid) return;
    if (show.cues.length && !window.confirm("Replace the working copy with the show attached to this track? Your library saves are untouched.")) return;
    fetch("/lights/track/" + tid + "/show").then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) { $("lx-io-status").textContent = "That track has no show attached."; return; }
      // Keep THIS rig: the point is the same looks on different fixtures.
      var mine = {bars: show.bars, chans: show.chans, pos: show.pos, rot: show.rot,
                  dmxStart: show.dmxStart, dmxAddr: show.dmxAddr, dmxUniverse: show.dmxUniverse,
                  rigKey: show.rigKey, rigName: show.rigName};
      var incoming = JSON.parse(JSON.stringify(d.show.data || {}));
      var fromBars = incoming.bars || mine.bars;
      incoming.cues = E.remapCues(incoming.cues || [], fromBars, mine.bars);
      Object.keys(mine).forEach(function (k) { incoming[k] = mine[k]; });
      incoming.name = d.show.name || incoming.name || "";
      loadShowData(incoming, null);
      show.libraryId = null; libraryDirty = false; paintLibrary(); markDirty(false);
      $("lx-track").value = tid; show.trackId = tid; markDirty();
      $("lx-io-status").textContent = "Pulled onto your rig.";
      announce("Pulled “" + (d.show.name || "the track's show") + "” onto your own rig — " +
               show.cues.length + " cues on " + show.bars + " bars.");
    });
  });

  // ---------- setlists (epic 7) ----------
  // Chain saved shows in order. Between songs the rig holds a gap look
  // rather than going black, because a black stage between songs reads as
  // a fault rather than a choice.
  var setlists = Array.isArray(lib.setlists) ? lib.setlists : [];
  var setlist = null, setIndex = -1;

  function paintSetlists() {
    var sel = $("lx-set-select"), cur = setlist ? setlist.id : "";
    sel.innerHTML = '<option value="">— none —</option>';
    setlists.forEach(function (s) {
      var o = document.createElement("option"); o.value = s.id;
      o.textContent = s.name + " · " + s.item_count + (s.item_count === 1 ? " song" : " songs");
      sel.appendChild(o);
    });
    sel.value = cur;
    $("lx-set-delete").disabled = !setlist;
    $("lx-set-name").value = setlist ? setlist.name : "";
    if (setlist) {
      $("lx-set-gap-color").value = setlist.gap_color || "#1a1712";
      $("lx-set-gap-int").value = setlist.gap_intensity == null ? 12 : setlist.gap_intensity;
    }
    $("lx-set-now").textContent = setlist
      ? "· " + setlist.name + (setIndex >= 0 ? " — song " + (setIndex + 1) + " of " + setlist.items.length : "")
      : "";
    paintSetItems();
    $("lx-set-prev").disabled = !setlist || setIndex <= 0;
    $("lx-set-next").disabled = !setlist || setIndex >= (setlist ? setlist.items.length - 1 : 0);
  }

  function paintSetItems() {
    var box = $("lx-set-items");
    box.innerHTML = "";
    if (!setlist) return;
    setlist.items.forEach(function (it, i) {
      var li = document.createElement("li");
      li.className = "lx-set-item" + (i === setIndex ? " is-current" : "");
      var name = document.createElement("b"); name.textContent = it.show_name || "(deleted show)";
      li.appendChild(name);

      var adv = document.createElement("select"); adv.className = "lx-select";
      adv.setAttribute("aria-label", "What happens when this song ends");
      [["manual", "wait for me"], ["auto", "auto-advance"]].forEach(function (o) {
        var op = document.createElement("option"); op.value = o[0]; op.textContent = o[1];
        op.selected = it.advance === o[0]; adv.appendChild(op);
      });
      adv.addEventListener("change", function () { it.advance = adv.value; });
      li.appendChild(adv);

      var gapWrap = document.createElement("label"); gapWrap.className = "lx-field";
      var gapLabel = document.createElement("span"); gapLabel.textContent = "gap";
      var gap = document.createElement("input"); gap.type = "number"; gap.min = "0"; gap.step = "1";
      gap.className = "lx-input"; gap.value = it.gap_seconds || 0;
      gap.setAttribute("aria-label", "Seconds of gap look after this song");
      gap.addEventListener("change", function () { it.gap_seconds = Math.max(0, parseFloat(gap.value) || 0); });
      gapWrap.appendChild(gapLabel); gapWrap.appendChild(gap); li.appendChild(gapWrap);

      var open = document.createElement("button"); open.type = "button";
      open.className = "lx-btn lx-btn--ghost lx-btn--small"; open.textContent = "Open";
      open.setAttribute("aria-label", "Load " + (it.show_name || "this song"));
      open.addEventListener("click", function () { loadSetlistItem(i); });
      li.appendChild(open);

      var up = document.createElement("button"); up.type = "button";
      up.className = "lx-btn lx-btn--ghost lx-btn--small"; up.textContent = "↑";
      up.disabled = i === 0; up.setAttribute("aria-label", "Move earlier");
      up.addEventListener("click", function () { moveSetItem(i, -1); });
      var down = document.createElement("button"); down.type = "button";
      down.className = "lx-btn lx-btn--ghost lx-btn--small"; down.textContent = "↓";
      down.disabled = i === setlist.items.length - 1; down.setAttribute("aria-label", "Move later");
      down.addEventListener("click", function () { moveSetItem(i, 1); });
      var rm = document.createElement("button"); rm.type = "button";
      rm.className = "lx-cue-x"; rm.textContent = "×";
      rm.setAttribute("aria-label", "Remove " + (it.show_name || "this song") + " from the setlist");
      rm.addEventListener("click", function () {
        setlist.items.splice(i, 1);
        if (setIndex >= setlist.items.length) setIndex = setlist.items.length - 1;
        paintSetlists();
      });
      li.appendChild(up); li.appendChild(down); li.appendChild(rm);
      box.appendChild(li);
    });
  }

  function moveSetItem(i, d) {
    var j = i + d;
    if (!setlist || j < 0 || j >= setlist.items.length) return;
    var tmp = setlist.items[i]; setlist.items[i] = setlist.items[j]; setlist.items[j] = tmp;
    if (setIndex === i) setIndex = j; else if (setIndex === j) setIndex = i;
    paintSetlists();
  }

  function loadSetlistItem(i) {
    if (!setlist || i < 0 || i >= setlist.items.length) return;
    var it = setlist.items[i];
    // Never lose the song you were on: flush the working copy first.
    if (dirty) autosave();
    fetch("/lights/library/" + it.show_id).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) { $("lx-set-status").textContent = "That show is no longer in the library."; return; }
      loadShowData(d.show.data, d.show);
      libraryDirty = false; paintLibDirty(); markDirty(false);
      setIndex = i; paintSetlists();
      $("lx-set-status").textContent = "Song " + (i + 1) + " of " + setlist.items.length + ": " + (it.show_name || "");
      announce("Loaded " + (it.show_name || "song " + (i + 1)));
      saveLive();
    });
  }

  $("lx-set-select").addEventListener("change", function () {
    var id = $("lx-set-select").value;
    if (!id) { setlist = null; setIndex = -1; paintSetlists(); return; }
    fetch("/lights/setlists/" + id).then(function (r) { return r.json(); }).then(function (d) {
      if (!d.ok) return;
      setlist = d.setlist; setIndex = -1; paintSetlists();
    });
  });
  $("lx-set-add").addEventListener("click", function () {
    if (!show.libraryId) {
      $("lx-set-status").textContent = "Save this show to the library first — a setlist chains saved shows.";
      announce($("lx-set-status").textContent);
      return;
    }
    if (!setlist) setlist = {id: "", name: $("lx-set-name").value || "Setlist", items: [],
                             gap_color: $("lx-set-gap-color").value, gap_intensity: +$("lx-set-gap-int").value};
    setlist.items.push({show_id: show.libraryId, show_name: show.name || "Untitled show",
                        advance: "manual", gap_seconds: 0});
    paintSetlists();
    $("lx-set-status").textContent = "Added. Save the setlist to keep it.";
  });
  $("lx-set-save").addEventListener("click", function () {
    var body = {
      id: setlist && setlist.id ? setlist.id : "",
      name: $("lx-set-name").value || (setlist && setlist.name) || "Setlist",
      gap_color: $("lx-set-gap-color").value || "#1a1712",
      gap_intensity: +$("lx-set-gap-int").value || 0,
      items: (setlist ? setlist.items : []).map(function (it) {
        return {show_id: it.show_id, advance: it.advance, gap_seconds: it.gap_seconds};
      })
    };
    post("/lights/setlists/save", body).then(function (d) {
      if (!d.ok) return;
      setlists = d.setlists || setlists; setlist = d.setlist;
      paintSetlists();
      $("lx-set-status").textContent = "Setlist saved.";
      announce("Setlist saved");
    });
  });
  $("lx-set-delete").addEventListener("click", function () {
    if (!setlist || !setlist.id || !window.confirm("Delete the setlist “" + setlist.name + "”? The shows themselves are untouched.")) return;
    post("/lights/setlists/" + setlist.id + "/delete", {}).then(function (d) {
      if (!d.ok) return;
      setlists = d.setlists || []; setlist = null; setIndex = -1; paintSetlists();
      $("lx-set-status").textContent = "Setlist deleted.";
    });
  });
  $("lx-set-next").addEventListener("click", function () { loadSetlistItem(setIndex + 1); });
  $("lx-set-prev").addEventListener("click", function () { loadSetlistItem(setIndex - 1); });

  // The gap look: what the rig holds between songs.
  function gapLooks() {
    var col = E.hexRgb((setlist && setlist.gap_color) || "#1a1712");
    var inten = ((setlist && setlist.gap_intensity) || 0) / 100;
    var out = [];
    for (var i = 0; i < show.bars; i++) out.push({rgb: col.slice(), inten: inten});
    return out;
  }
  var inGap = false;

  function songEnded() {
    /* Called when playback runs off the end of a song. */
    if (!setlist || setIndex < 0) return;
    var it = setlist.items[setIndex];
    if (!it || it.advance !== "auto") return;
    var wait = Math.max(0, it.gap_seconds || 0);
    inGap = true;
    $("lx-set-status").textContent = wait
      ? "Holding the gap look for " + wait + "s, then the next song."
      : "Advancing to the next song.";
    setTimeout(function () { inGap = false; loadSetlistItem(setIndex + 1); }, wait * 1000);
  }

  // ---------- crash safety (epic 7) ----------
  // A page reload mid-gig must not cost the show. The live position is
  // written to this browser roughly once a second; on load, a recent one
  // offers to pick up where it stopped. Cue edits already autosave.
  var LIVE_KEY = "lxLive", lastLiveSave = 0;
  function saveLive() {
    try {
      safeSet(LIVE_KEY, JSON.stringify({
        at: Date.now(), t: now(), running: playing || runStart !== null,
        libraryId: show.libraryId || "", name: show.name || "",
        setlistId: setlist ? setlist.id : "", setIndex: setIndex, output: output
      }));
    } catch (e) {}
  }
  function readLive() {
    try {
      var d = JSON.parse(safeGet(LIVE_KEY) || "null");
      if (!d || !d.at || Date.now() - d.at > 2 * 60 * 60 * 1000) return null;   // stale after 2h
      return d;
    } catch (e) { return null; }
  }
  function maybeOfferResume() {
    var d = readLive(), bar = $("lx-resume");
    if (!d || (!d.libraryId && !d.setlistId) || !(d.t > 1)) return;
    var mins = Math.round((Date.now() - d.at) / 60000);
    $("lx-resume-text").textContent = "The show was at " + E.fmtTimecode(d.t) +
      (d.name ? " in “" + d.name + "”" : "") + " " + (mins < 1 ? "less than a minute" : mins + " min") + " ago.";
    bar.hidden = false;
    $("lx-resume-no").onclick = function () { bar.hidden = true; try { safeSet(LIVE_KEY, ""); } catch (e) {} };
    $("lx-resume-go").onclick = function () {
      bar.hidden = true;
      var go = function () { seek(d.t); announce("Picked up at " + E.fmtTimecode(d.t)); };
      if (d.setlistId) {
        fetch("/lights/setlists/" + d.setlistId).then(function (r) { return r.json(); }).then(function (s) {
          if (s.ok) {
            setlist = s.setlist; setIndex = d.setIndex; paintSetlists();
            if (d.setIndex >= 0) { loadSetlistItem(d.setIndex); setTimeout(go, 400); return; }
          }
          go();
        });
      } else if (d.libraryId) {
        fetch("/lights/library/" + d.libraryId).then(function (r) { return r.json(); }).then(function (l) {
          if (l.ok) { loadShowData(l.show.data, l.show); libraryDirty = false; paintLibDirty(); markDirty(false); }
          setTimeout(go, 200);
        });
      } else go();
    };
  }

  // ---------- focus mode ----------
  // Focus mode hides the app sidebar entirely on desktop and shows the
  // slim studio rail (#lx-rail: four icon links + an expand control) in
  // its place, so the workspace gets the width. Leaving focus restores
  // the sidebar in whatever rail/full state the rest of the app uses.
  var FOCUS = "lxFocus";
  function setFocus(on, persist) {
    document.body.classList.toggle("lx-focus", on);
    if (!on && window.innerWidth >= 1024) document.body.classList.toggle("sb-rail", safeGet("sbRail") === "1");
    if (persist) safeSet(FOCUS, on ? "1" : "0");
    var btn = $("lx-focus"); btn.setAttribute("aria-pressed", on ? "true" : "false"); btn.textContent = on ? "Exit focus" : "Focus mode";
    var rt = $("sb-rail-tgl"); if (rt) rt.setAttribute("aria-pressed", document.body.classList.contains("sb-rail") ? "true" : "false");
  }
  function safeGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function safeSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  $("lx-focus").addEventListener("click", function () { setFocus(!document.body.classList.contains("lx-focus"), true); });
  $("lx-rail-expand").addEventListener("click", function () { setFocus(false, true); var rt = $("sb-rail-tgl"); if (rt) rt.focus(); });
  setFocus(safeGet(FOCUS) !== "0", false);
  $("lx-undo").addEventListener("click", undo);
  $("lx-redo").addEventListener("click", redo);

  // ---------- keyboard ----------
  document.addEventListener("keydown", function (e) {
    // Undo / redo: Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, Ctrl+Y. Inside a text
    // field the browser's own undo wins - never hijack typing.
    if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === "z" || e.key === "Z" || e.key === "y" || e.key === "Y")) {
      if (isTyping(e.target)) return;
      e.preventDefault();
      if (e.key === "y" || e.key === "Y" || e.shiftKey) redo(); else undo();
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (isTyping(e.target)) return;
    if (e.key === " " || e.code === "Space") { e.preventDefault(); togglePlay(); }
    else if (e.key === "c" || e.key === "C") { if (!$("lx-add").disabled) addCue(); }
    else if (e.key === "b" || e.key === "B") { if (!$("lx-blackout").disabled) addCue(E.LOOKS[5]); }
    else if (e.key === "x" || e.key === "X") { togglePanic(); }
    else if (/^[1-6]$/.test(e.key) && e.target !== stage) { applyLook(E.LOOKS[parseInt(e.key, 10) - 1]); }
    else if (USER_KEYS.indexOf(e.key) >= 0 && e.target !== stage) { var ul = (show.looks || [])[USER_KEYS.indexOf(e.key)]; if (ul) applyLook(ul); }
    else if (e.key === "Escape") { selectCue(null); selectBar(null); }
    else if (e.key === "ArrowLeft" && e.target !== stage && e.target !== wave && buffer) { seek(now() - (e.shiftKey ? 5 : 1)); }
    else if (e.key === "ArrowRight" && e.target !== stage && e.target !== wave && buffer) { seek(now() + (e.shiftKey ? 5 : 1)); }
  });

  // ---------- resize ----------
  if (window.ResizeObserver) {
    new ResizeObserver(function () { invalidatePeaks(); stageSize(); }).observe(stageWrap);
  } else window.addEventListener("resize", function () { invalidatePeaks(); });

  // ---------- main loop ----------
  var lastTable = 0, dockClock = $("lx-dock-clock");
  function loop() {
    requestAnimationFrame(loop);
    var t = now();
    clockEl.textContent = E.fmtTimecode(t);
    if (dockClock) dockClock.textContent = clockEl.textContent;
    drawStage(t);
    drawWave(t);
    paintScrub(t);
    var ts = performance.now();
    if (ts - lastTable > 500) { lastTable = ts; paintBarsList(t); }
    if (ts - lastAria > 400) { lastAria = ts; paintWaveAria(); }
    if (ts - lastLiveSave > 1000) { lastLiveSave = ts; saveLive(); }
    // DMX: 30 fps while the show runs; a slow heartbeat when idle so the
    // rig holds whatever the stage shows (master, panic, a selected cue).
    // Whichever sink is active gets the same 30 fps loop, and the same slow
    // heartbeat when idle so the rig holds what the stage shows.
    var sinkLive = (output === "enttec" && writer) || output === "artnet" || output === "sacn";
    if (sinkLive) {
      var live = playing || runStart !== null;
      if (ts - lastDmx > (live ? 33 : 500)) { lastDmx = ts; sendDmx(t); }
      if (ts - dmxSec > 1000) { dmxSec = ts; dmxFps = dmxWrites; dmxWrites = 0; paintDmxLive(); }
    }
  }

  window.__lightsTest = {
    show: function () { return show; }, lightingAt: function (t) { return E.lightingAt(show, t); },
    membersOf: E.membersOf, dmxFrame: function (looks) { return E.dmxFrame(show, looks); }, drawStage: drawStage,
    seek: seek, now: now, addCue: addCue, selectCue: selectCue, selectBar: selectBar, view: function () { return view; },
    zoomTo: zoomTo, setFocus: setFocus, stageSize: function () { return stageCss; }, barRects: function () { return barRects; },
    loadShowData: loadShowData, loadBuffer: loadBuffer, ensureCtx: ensureCtx, detectBeats: detectBeats,
    drawWave: drawWave, tick: function () { var t = now(); clockEl.textContent = E.fmtTimecode(t); if (dockClock) dockClock.textContent = clockEl.textContent; drawStage(t); drawWave(t); paintBarsList(t); paintScrub(t); paintWaveAria(); return t; },
    setHover: function (b, grp) { hoverBar = b; hoverGroup = grp; }, state: function () { return {playing: playing, buffer: !!buffer, selectedBar: selectedBar, selectedCue: selectedCue, dirty: dirty, libraryDirty: libraryDirty, master: master, panic: panic, rate: rate, volume: volume}; },
    undo: undo, redo: redo, historySize: function () { return H.size(); }, canRedo: function () { return H.canRedo(); },
    waveMetrics: function () { return {view: {start: view.start, end: view.end}, w: waveCss.w, tToX: tToX, xToT: xToT}; },
    draftPayload: draftPayload, maybeOfferDraft: maybeOfferDraft, announce: announce,
    outLooks: outLooks, setMaster: function (v) { masterEl.value = String(Math.round(v * 100)); master = clamp(v, 0, 1); paintMaster(); }, togglePanic: togglePanic,
    pickGel: pickGel, aimWheelAt: aimWheelAt, gels: function () { return GELS.slice(); },
    wheelHex: function () { return $("lx-gel-hex").value; },
    pickBar: pickBar, paintBarsList: paintBarsList, exportJson: exportJson, importShow: importShow, fixtureAddress: function (b) { return E.fixtureAddress(show, b); },
    autoCue: autoCue, clearAutoCues: clearAutoCues, own: own,
    applyRemoteCommand: applyRemoteCommand, pollRemote: pollRemote,
    remoteCode: function () { return remoteCode; },
    bump: function () { return bump; },
    trackShows: function () { return trackShows; }, paintTrackShip: paintTrackShip,
    setlist: function () { return setlist; }, setIndex: function () { return setIndex; },
    loadSetlistItem: loadSetlistItem, songEnded: songEnded, gapLooks: gapLooks,
    inGap: function (v) { if (v !== undefined) inGap = v; return inGap; },
    saveLive: saveLive, readLive: readLive, maybeOfferResume: maybeOfferResume,
    setOutput: function (o) { $("lx-output").value = o; $("lx-output").dispatchEvent(new Event("change")); },
    output: function () { return output; }, checkBridge: checkBridge, sendDmx: sendDmx,
    rigs: function () { return rigs; }, applyRigNow: function (r) { record("rig"); E.applyRig(show, r); selectedCue = null; selectedBar = null; ensureIds(); markDirty(); paintRig(); renderCues(); paintGroups(); paintBarCtl(); },
    offerVenueRig: offerVenueRig, setBars: function (n) { barsSel.value = String(n); barsSel.dispatchEvent(new Event("change")); },
    spriteReady: function () { return barImg.complete && barImg.naturalWidth > 0; }, bgReady: function () { return bgImg.complete && bgImg.naturalWidth > 0; }
  };
  ensureIds(); paintRig(); renderCues(); paintGroups(); paintLooks(); paintLibrary(); paintBeats(); paintTransport(); paintBarCtl(); paintMaster(); paintAutoCue(); paintOutputs(); paintRemote(); resumeRemote(); loadNotes();
  paintHistory(); paintWaveAria(); paintSetlists(); maybeOfferDraft(); maybeOfferResume();
  loop();
})();
