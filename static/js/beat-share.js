/* One beat, one player. The peaks were measured in the producer's
 * browser at upload time and travel with the page, so this draws a real
 * waveform without decoding anything here. */
(function () {
  "use strict";
  var share = window.__btShare || {}, token = window.__btToken || "";
  var canvas = document.getElementById("bts-wave");
  if (!canvas) return;                      // no audio on this beat

  var el = new Audio(), playing = false, raf = null;
  el.preload = "none";
  el.src = "/beat/" + token + "/stream";

  var peaks = share.peaks || [];
  var dur = share.duration || 0;

  function clock(t) {
    t = Math.max(0, t || 0);
    var m = Math.floor(t / 60), s = Math.floor(t % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function draw(progress) {
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.clientWidth || 320, h = canvas.clientHeight || 70;
    if (canvas.width !== Math.round(w * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    }
    var g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    if (!peaks.length) {
      g.fillStyle = "rgba(238,232,220,0.30)";
      g.fillRect(0, h / 2 - 1, w, 2);
      return;
    }
    var mid = h / 2, step = w / peaks.length, played = w * (progress || 0);
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
    document.getElementById("bts-clock").textContent = clock(el.currentTime);
    raf = requestAnimationFrame(tick);
  }

  var btn = document.getElementById("bts-play");
  btn.addEventListener("click", function () {
    if (playing) {
      el.pause(); playing = false;
      btn.innerHTML = "&#9654;"; btn.setAttribute("aria-pressed", "false");
      if (raf) cancelAnimationFrame(raf);
      return;
    }
    el.play().then(function () {
      playing = true;
      btn.innerHTML = "&#10073;&#10073;"; btn.setAttribute("aria-pressed", "true");
      document.getElementById("bts-note").textContent = "Playing.";
      tick();
    }).catch(function () {
      document.getElementById("bts-note").textContent =
        "That would not play here. The link may have been switched off.";
    });
  });

  el.addEventListener("ended", function () {
    playing = false;
    btn.innerHTML = "&#9654;"; btn.setAttribute("aria-pressed", "false");
    if (raf) cancelAnimationFrame(raf);
    draw(0);
    document.getElementById("bts-clock").textContent = clock(0);
  });

  el.addEventListener("loadedmetadata", function () {
    if (!dur && el.duration) {
      dur = el.duration;
      document.getElementById("bts-length").textContent = clock(dur);
    }
  });

  canvas.addEventListener("click", function (e) {
    var d = dur || el.duration || 0;
    if (!d) return;
    var r = canvas.getBoundingClientRect();
    el.currentTime = d * Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    draw(el.currentTime / d);
    document.getElementById("bts-clock").textContent = clock(el.currentTime);
  });

  window.addEventListener("resize", function () {
    var d = dur || el.duration || 0;
    draw(d ? el.currentTime / d : 0);
  });
  draw(0);
})();
