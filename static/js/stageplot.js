/* Stage plot rendering shared by the designer (/stage-plot) and the public
   show-day page (/showday/<token>). Pure functions of a plot state:
   {name, items: {key: count}, pos: {"key-n": [x, y]}}. */
window.StagePlot = (function () {
  "use strict";
  var CATALOG = [
    {key: "riser",    label: "Drum Riser 8×8", w: 210, h: 150, max: 1, glyph: "RISER",  inputs: []},
    {key: "drums",    label: "Drum Kit",          w: 170, h: 110, max: 1, glyph: "DRUMS",
     inputs: ["Kick — Beta 52", "Snare — SM57", "Hi-Hat — SM81", "Rack Tom — e604", "Floor Tom — e604", "OH L — SM81", "OH R — SM81"]},
    {key: "gtr",      label: "Guitar Amp",        w: 92,  h: 66,  max: 3, glyph: "GTR",    inputs: ["Guitar Amp {n} — SM57"]},
    {key: "bass",     label: "Bass Amp",          w: 92,  h: 76,  max: 1, glyph: "BASS",   inputs: ["Bass — DI"]},
    {key: "keys",     label: "Keys",              w: 130, h: 56,  max: 2, glyph: "KEYS",   inputs: ["Keys {n} L — DI", "Keys {n} R — DI"]},
    {key: "acoustic", label: "Acoustic Guitar",   w: 60,  h: 60,  max: 2, glyph: "AC",     inputs: ["Acoustic {n} — DI"]},
    {key: "vox",      label: "Vocal Mic",         w: 44,  h: 44,  max: 4, glyph: "VOX",    inputs: ["Vocal {n} — SM58"]},
    {key: "playback", label: "Playback / Tracks", w: 84,  h: 50,  max: 1, glyph: "TRKS",   inputs: ["Tracks L — DI", "Tracks R — DI"]},
    {key: "dj",       label: "DJ Table",          w: 150, h: 66,  max: 1, glyph: "DJ",     inputs: ["DJ L — DI", "DJ R — DI"]},
    {key: "wedge",    label: "Monitor Wedge",     w: 72,  h: 46,  max: 4, glyph: "MON",    inputs: []},
    {key: "power",    label: "Power Drop",        w: 46,  h: 32,  max: 4, glyph: "⚡", inputs: []}
  ];
  var BY_KEY = {};
  CATALOG.forEach(function (c) { BY_KEY[c.key] = c; });

  var ST = {x: 60, y: 120, w: 880, h: 500};
  var DEFAULTS = {
    riser: [500, 210], drums: [500, 220], gtr: [790, 300], bass: [210, 300],
    keys: [170, 440], acoustic: [800, 440], vox: [500, 500], playback: [90, 180],
    dj: [500, 340], wedge: [500, 570], power: [110, 560]
  };

  function instances(state) {
    var out = [];
    CATALOG.forEach(function (c) {
      var n = (state.items || {})[c.key] || 0;
      for (var i = 1; i <= n; i++) out.push({cat: c, n: i, id: c.key + "-" + i});
    });
    return out;
  }

  function posFor(state, inst) {
    if (state.pos && state.pos[inst.id]) return state.pos[inst.id];
    var d = DEFAULTS[inst.cat.key] || [500, 350];
    var count = (state.items || {})[inst.cat.key] || 1;
    var x = d[0] + (inst.n - 1) * (inst.cat.w + 18) - ((count - 1) * (inst.cat.w + 18)) / 2;
    return [Math.max(ST.x + inst.cat.w / 2, Math.min(ST.x + ST.w - inst.cat.w / 2, x)), d[1]];
  }

  function channelList(state) {
    var chans = [];
    CATALOG.forEach(function (c) {
      var n = (state.items || {})[c.key] || 0;
      for (var i = 1; i <= n; i++) {
        c.inputs.forEach(function (tpl) {
          chans.push(tpl.replace("{n}", n > 1 ? String(i) : "").replace(/\s+/g, " ").trim());
        });
      }
    });
    return chans;
  }

  function esc(t) {
    return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function itemSvg(state, inst) {
    var c = inst.cat, p = posFor(state, inst);
    var x = p[0] - c.w / 2, y = p[1] - c.h / 2;
    var label = c.label + (((state.items || {})[c.key] || 0) > 1 ? " " + inst.n : "");
    var shape;
    if (c.key === "riser") {
      shape = '<rect x="' + x + '" y="' + y + '" width="' + c.w + '" height="' + c.h + '" rx="6" fill="none" stroke="#8A6E30" stroke-width="2" stroke-dasharray="8 6"/>';
    } else if (c.key === "vox") {
      shape = '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="' + c.w / 2 + '" fill="#14100A" stroke="#C9A24A" stroke-width="2"/>';
    } else if (c.key === "wedge") {
      shape = '<path d="M' + x + ' ' + y + ' L' + (x + c.w) + ' ' + y + ' L' + (x + c.w - 14) + ' ' + (y + c.h) + ' L' + (x + 14) + ' ' + (y + c.h) + ' Z" fill="#1A1714" stroke="#C9A24A" stroke-width="2"/>';
    } else {
      shape = '<rect x="' + x + '" y="' + y + '" width="' + c.w + '" height="' + c.h + '" rx="6" fill="#1A1714" stroke="#C9A24A" stroke-width="2"/>';
    }
    return '<g class="sp-item" data-id="' + inst.id + '" style="cursor:move">' + shape +
      '<text x="' + p[0] + '" y="' + (p[1] + 4) + '" text-anchor="middle" font-family="Arial, sans-serif" font-size="15" font-weight="800" fill="#E8B950">' + esc(c.glyph) + '</text>' +
      '<text x="' + p[0] + '" y="' + (y + c.h + 16) + '" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#A99B84">' + esc(label) + '</text></g>';
  }

  function buildSvg(state) {
    var chans = channelList(state);
    var rows = Math.max(1, Math.ceil(chans.length / 2));
    var listH = 70 + rows * 24;
    var H = 700 + listH;
    var s = '<svg id="sp-svg" viewBox="0 0 1000 ' + H + '" xmlns="http://www.w3.org/2000/svg">';
    s += '<rect width="1000" height="' + H + '" fill="#0B0A08"/>';
    s += '<text x="60" y="60" font-family="Arial, sans-serif" font-size="30" font-weight="900" fill="#E8B950">' + esc(state.name || "STAGE PLOT") + '</text>';
    s += '<text x="60" y="86" font-family="Arial, sans-serif" font-size="13" letter-spacing="4" fill="#8A6E30">STAGE PLOT · ' + new Date().toISOString().slice(0, 10) + '</text>';
    s += '<text x="940" y="60" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#91836A">.street banker</text>';
    s += '<rect x="' + ST.x + '" y="' + ST.y + '" width="' + ST.w + '" height="' + ST.h + '" rx="10" fill="#14100A" stroke="#3A3226" stroke-width="2"/>';
    s += '<text x="500" y="' + (ST.y + 24) + '" text-anchor="middle" font-family="Arial, sans-serif" font-size="11" letter-spacing="5" fill="#91836A">UPSTAGE (BACK)</text>';
    s += '<text x="500" y="' + (ST.y + ST.h + 34) + '" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" letter-spacing="6" fill="#8A6E30">DOWNSTAGE · AUDIENCE</text>';
    instances(state).forEach(function (inst) { s += itemSvg(state, inst); });
    var ly = 700;
    s += '<line x1="60" y1="' + (ly - 6) + '" x2="940" y2="' + (ly - 6) + '" stroke="#221D18" stroke-width="1"/>';
    s += '<text x="60" y="' + (ly + 22) + '" font-family="Arial, sans-serif" font-size="15" font-weight="800" letter-spacing="3" fill="#E8B950">INPUT LIST · ' + chans.length + ' CHANNELS</text>';
    if (chans.length) {
      chans.forEach(function (ch, i) {
        var col = i < rows ? 0 : 1;
        var cy = ly + 50 + (i % rows) * 24;
        s += '<text x="' + (60 + col * 450) + '" y="' + cy + '" font-family="Arial, sans-serif" font-size="14" fill="#A99B84">' + (i + 1) + '. ' + esc(ch) + '</text>';
      });
    } else {
      s += '<text x="60" y="' + (ly + 50) + '" font-family="Arial, sans-serif" font-size="13" fill="#91836A">No inputs yet — tick items on the left.</text>';
    }
    return s + "</svg>";
  }

  return {CATALOG: CATALOG, BY_KEY: BY_KEY, ST: ST, instances: instances,
          posFor: posFor, channelList: channelList, buildSvg: buildSvg, esc: esc};
})();
