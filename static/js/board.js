/* Team-Up Board — enhancement only. Everything below works without this
   file: the region field is a <datalist>, genres are a <datalist> +
   comma-separated text, the post form is a <details>. Here we add: region
   typeahead that fills the hidden code, genre chips, and auto-open. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  // region typeahead -> hidden region_code
  document.querySelectorAll("[data-region-input]").forEach(function (input) {
    var hidden = document.getElementById(input.getAttribute("data-region-input"));
    var list = document.getElementById(input.getAttribute("list"));
    if (!hidden || !list) return;
    var options = Array.prototype.map.call(list.options, function (o) { return {label: o.value, code: o.getAttribute("data-code") || ""}; });
    function sync() {
      var v = (input.value || "").trim().toLowerCase();
      var hit = options.filter(function (o) { return o.label.toLowerCase() === v; })[0];
      hidden.value = hit ? hit.code : "";
      input.setAttribute("aria-invalid", (!hit && v) ? "true" : "false");
    }
    input.addEventListener("input", sync); input.addEventListener("change", sync); sync();
  });

  // genre chips over a text input + hidden multi-select of codes
  document.querySelectorAll("[data-genre-input]").forEach(function (input) {
    var box = document.getElementById(input.getAttribute("data-genre-input"));
    var list = document.getElementById(input.getAttribute("list"));
    if (!box || !list) return;
    var options = Array.prototype.map.call(list.options, function (o) { return {label: o.value, code: o.getAttribute("data-code")}; });
    var chips = document.createElement("div"); chips.className = "tb-chips"; chips.setAttribute("aria-live", "polite"); input.parentNode.appendChild(chips);
    function selected() { return Array.prototype.filter.call(box.options, function (o) { return o.selected; }).map(function (o) { return o.value; }); }
    function paint() {
      chips.innerHTML = "";
      selected().forEach(function (code) {
        var opt = options.filter(function (o) { return o.code === code; })[0]; if (!opt) return;
        var c = document.createElement("span"); c.className = "tb-chip"; c.textContent = opt.label + " ";
        var x = document.createElement("button"); x.type = "button"; x.textContent = "×"; x.setAttribute("aria-label", "Remove " + opt.label);
        x.addEventListener("click", function () { Array.prototype.forEach.call(box.options, function (o) { if (o.value === code) o.selected = false; }); paint(); });
        c.appendChild(x); chips.appendChild(c);
      });
    }
    function commit() {
      var v = (input.value || "").trim().toLowerCase().replace(/,$/, "");
      if (!v) return;
      var hit = options.filter(function (o) { return o.label.toLowerCase() === v; })[0];
      if (hit) { Array.prototype.forEach.call(box.options, function (o) { if (o.value === hit.code) o.selected = true; }); input.value = ""; paint(); }
    }
    input.addEventListener("change", commit);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); commit(); } });
    box.style.display = "none"; paint();
  });

  // auto-open the post fold when asked (?new=1 / prefill) or after a coaching note
  var fold = document.querySelector("details.tb-post");
  if (fold && (/[?&](new|title|kind)=/.test(location.search) || fold.getAttribute("data-open") === "1")) fold.open = true;
  // focus the reply box when landing on #reply
  if (location.hash === "#reply") { var ta = document.querySelector("#reply textarea"); if (ta) ta.focus(); }
})();
