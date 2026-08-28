/* Light Studio — the reader's view of a shared show (epic 5).
 *
 * Small on purpose. This page has no audio, no editing and no account:
 * it renders the cue list against a clock, runs the same lightingAt()
 * the studio uses, and takes notes anchored to a timecode.
 *
 * Notes anchor to TIME, not to a cue: lights.js strips cue ids on save,
 * so an id would not survive the round trip, while 1:14 is still 1:14
 * after the cue there is deleted.
 */
(function () {
  "use strict";
  var E = window.LightsEngine;
  var share = window.__lxShare || {}, token = window.__lxToken || "";
  var show = share.data || {cues: [], bars: 6};
  var comments = window.__lxComments || [];
  var canComment = share.permission === "comment";

  var cues = (show.cues || []).slice().sort(function (a, b) { return a.t - b.t; });
  var bars = Math.max(1, show.bars || 6);
  var dur = Math.max(30, cues.length ? cues[cues.length - 1].t + 10 : 60);

  var t = 0, running = false, raf = null, startedAt = 0, startedFrom = 0;
  function $(id) { return document.getElementById(id); }

  // ---------- stage ----------
  var barEls = [];
  (function buildStage() {
    var wrap = $("lxs-stage");
    for (var i = 0; i < bars; i++) {
      var b = document.createElement("i");
      b.className = "lxs-bar";
      wrap.appendChild(b);
      barEls.push(b);
    }
  })();

  function paintStage() {
    var looks = E.lightingAt(show, t);
    for (var i = 0; i < barEls.length; i++) {
      var l = looks[i] || {rgb: [0, 0, 0], inten: 0};
      barEls[i].style.background = "rgb(" + l.rgb.join(",") + ")";
      barEls[i].style.opacity = String(0.12 + 0.88 * Math.max(0, Math.min(1, l.inten)));
    }
  }

  // ---------- timeline ----------
  var line = $("lxs-timeline");
  function pct(x) { return (100 * Math.max(0, Math.min(1, x / dur))) + "%"; }

  function buildTimeline() {
    // Rebuilt whenever notes change, so a new note gets its marker without
    // a reload. The playhead is kept, not recreated.
    var old = line.querySelectorAll(".lxs-flag, .lxs-note-pin");
    for (var i = 0; i < old.length; i++) old[i].remove();
    cues.forEach(function (c, i) {
      var f = document.createElement("button");
      f.type = "button";
      f.className = "lxs-flag";
      f.style.left = pct(c.t);
      f.style.setProperty("--flag", c.color || "#E8B950");
      f.title = E.fmtClock(c.t) + " · " + (c.note || E.groupLabel(c.group, bars));
      f.setAttribute("aria-label", "Cue " + (i + 1) + " at " + E.fmtClock(c.t) + ". Jump here.");
      f.addEventListener("click", function (e) { e.stopPropagation(); seek(c.t); });
      line.appendChild(f);
    });
    comments.filter(function (c) { return !c.parent_id && c.t !== null && c.t !== undefined; })
      .forEach(function (c) {
        var p = document.createElement("button");
        p.type = "button";
        p.className = "lxs-note-pin" + (c.resolved ? " is-done" : "");
        p.style.left = pct(c.t);
        p.title = c.author + ": " + c.body.slice(0, 60);
        p.setAttribute("aria-label", "Note from " + c.author + " at " + E.fmtClock(c.t) + ". Jump here.");
        p.addEventListener("click", function (e) {
          e.stopPropagation();
          seek(c.t);
          var el = document.getElementById("thread-" + c.id);
          if (el) { el.scrollIntoView({block: "center"}); el.classList.add("is-lit"); setTimeout(function () { el.classList.remove("is-lit"); }, 1200); }
        });
        line.appendChild(p);
      });
  }

  line.addEventListener("click", function (e) {
    var r = line.getBoundingClientRect();
    seek(dur * (e.clientX - r.left) / r.width);
  });
  line.addEventListener("keydown", function (e) {
    var step = e.shiftKey ? 5 : 1;
    if (e.key === "ArrowRight") { seek(t + step); e.preventDefault(); }
    else if (e.key === "ArrowLeft") { seek(t - step); e.preventDefault(); }
    else if (e.key === "Home") { seek(0); e.preventDefault(); }
    else if (e.key === "End") { seek(dur); e.preventDefault(); }
  });

  function seek(next) {
    t = Math.max(0, Math.min(dur, next));
    if (running) { startedAt = Date.now(); startedFrom = t; }
    paint();
  }

  function paint() {
    $("lxs-playhead").style.left = pct(t);
    $("lxs-clock").textContent = E.fmtClock(t);
    line.setAttribute("aria-valuenow", String(Math.round(t)));
    line.setAttribute("aria-valuemax", String(Math.round(dur)));
    line.setAttribute("aria-valuetext", E.fmtClock(t) + " of " + E.fmtClock(dur));
    if (canComment) $("lxs-at-time").textContent = E.fmtClock(t);
    paintStage();
    paintCueList();
  }

  // ---------- cue list ----------
  var cueEls = [];
  (function buildCues() {
    var list = $("lxs-cue-list");
    if (!cues.length) {
      var empty = document.createElement("li");
      empty.className = "lx-hint";
      empty.textContent = "This show has no cues yet.";
      list.appendChild(empty);
      return;
    }
    cues.forEach(function (c, i) {
      var li = document.createElement("li");
      li.className = "lxs-cue";
      li.innerHTML =
        '<button type="button" class="lxs-cue-btn">' +
        '<i class="lxs-swatch"></i>' +
        '<span class="lxs-cue-t"></span>' +
        '<span class="lxs-cue-note"></span>' +
        '<span class="lxs-cue-meta"></span>' +
        "</button>";
      li.querySelector(".lxs-swatch").style.background = c.color || "#E8B950";
      li.querySelector(".lxs-cue-t").textContent = E.fmtClock(c.t);
      li.querySelector(".lxs-cue-note").textContent = c.note || E.groupLabel(c.group, bars);
      li.querySelector(".lxs-cue-meta").textContent =
        Math.round(c.intensity) + "% · " + (c.fade || 0) + "s fade";
      li.querySelector(".lxs-cue-btn").addEventListener("click", function () { seek(c.t); });
      list.appendChild(li);
      cueEls.push(li);
    });
  })();

  function paintCueList() {
    var active = -1;
    for (var i = 0; i < cues.length; i++) if (cues[i].t <= t + 0.001) active = i;
    for (var j = 0; j < cueEls.length; j++) cueEls[j].classList.toggle("is-live", j === active);
  }

  // ---------- run ----------
  function tick() {
    if (!running) return;
    t = startedFrom + (Date.now() - startedAt) / 1000;
    if (t >= dur) { t = dur; stop(); paint(); return; }
    paint();
    raf = requestAnimationFrame(tick);
  }
  function stop() {
    running = false;
    if (raf) cancelAnimationFrame(raf);
    raf = null;
    $("lxs-run").textContent = "Run";
    $("lxs-run").setAttribute("aria-pressed", "false");
  }
  $("lxs-run").addEventListener("click", function () {
    if (running) { stop(); return; }
    if (t >= dur - 0.05) t = 0;
    running = true; startedAt = Date.now(); startedFrom = t;
    this.textContent = "Stop";
    this.setAttribute("aria-pressed", "true");
    tick();
  });
  $("lxs-rewind").addEventListener("click", function () { seek(0); });

  // ---------- notes ----------
  function fmtWhen(iso) {
    var d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleDateString([], {month: "short", day: "numeric"}) +
      " " + d.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  }

  function renderThreads() {
    var box = $("lxs-threads");
    box.textContent = "";
    var tops = comments.filter(function (c) { return !c.parent_id; });
    var open = tops.filter(function (c) { return !c.resolved; }).length;
    $("lxs-note-count").textContent = tops.length
      ? "· " + open + " open of " + tops.length
      : "";
    if (!tops.length) {
      var p = document.createElement("p");
      p.className = "lx-hint";
      p.textContent = canComment
        ? "No notes yet. Yours would be the first."
        : "No notes on this show yet.";
      box.appendChild(p);
      return;
    }
    tops.forEach(function (c) {
      var wrap = document.createElement("article");
      wrap.className = "lxs-thread" + (c.resolved ? " is-done" : "");
      wrap.id = "thread-" + c.id;
      wrap.appendChild(noteEl(c));
      comments.filter(function (r) { return r.parent_id === c.id; })
        .forEach(function (r) {
          var re = noteEl(r);
          re.classList.add("is-reply");
          wrap.appendChild(re);
        });
      if (canComment) wrap.appendChild(replyBox(c.id));
      box.appendChild(wrap);
    });
  }

  function noteEl(c) {
    var el = document.createElement("div");
    el.className = "lxs-note";
    var head = document.createElement("p");
    head.className = "lxs-note-head";
    var who = document.createElement("b");
    who.textContent = c.author;
    head.appendChild(who);
    if (c.t !== null && c.t !== undefined) {
      var at = document.createElement("button");
      at.type = "button";
      at.className = "lxs-note-at";
      at.textContent = "@ " + E.fmtClock(c.t);
      at.setAttribute("aria-label", "Jump to " + E.fmtClock(c.t));
      at.addEventListener("click", function () { seek(c.t); });
      head.appendChild(at);
    }
    var when = document.createElement("span");
    when.className = "lxs-note-when";
    when.textContent = fmtWhen(c.created) + (c.resolved ? " · settled" : "");
    head.appendChild(when);
    var body = document.createElement("p");
    body.className = "lxs-note-body";
    body.textContent = c.body;                      // textContent, never innerHTML
    el.appendChild(head);
    el.appendChild(body);
    return el;
  }

  function replyBox(parentId) {
    var f = document.createElement("form");
    f.className = "lxs-reply";
    f.innerHTML = '<input class="lx-input lxs-reply-in" type="text" maxlength="1200" placeholder="Reply…" aria-label="Reply to this note">' +
                  '<button class="lx-btn lx-btn--ghost lx-btn--small" type="submit">Reply</button>';
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var input = f.querySelector(".lxs-reply-in");
      var name = ($("lxs-author").value || "").trim();
      if (!name) { $("lxs-form-hint").textContent = "Put your name at the top first, so the designer knows who is asking."; $("lxs-author").focus(); return; }
      if (!input.value.trim()) return;
      send({author: name, body: input.value, parent_id: parentId}, function () { input.value = ""; });
    });
    return f;
  }

  function send(body, done) {
    var hint = $("lxs-form-hint");
    hint.textContent = "Sending…";
    fetch("/lights/show/" + token + "/comment", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    }).then(function (r) { return r.json().then(function (d) { return {status: r.status, d: d}; }); })
      .then(function (res) {
        if (res.status === 403) { hint.textContent = "This link is read only now."; return; }
        if (!res.d.ok) { hint.textContent = "That did not send — try again."; return; }
        comments = res.d.comments || comments;
        hint.textContent = "Sent.";
        if (done) done();
        renderThreads();
        buildTimeline();
      })
      .catch(function () { hint.textContent = "Offline — the note was not sent."; });
  }

  if (canComment) {
    $("lxs-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var name = ($("lxs-author").value || "").trim();
      var text = ($("lxs-body").value || "").trim();
      if (!name || !text) return;
      send({author: name, body: text, t: $("lxs-at").checked ? t : null}, function () {
        $("lxs-body").value = "";
      });
    });
  }

  buildTimeline();
  renderThreads();
  paint();
})();
