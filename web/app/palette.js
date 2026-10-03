/* Class palette — one shared color map for every view, chip and label. */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.palette = {
    cookie: "#e15759",
    cake: "#4e79a7",
    pie_pastry: "#f28e2b",
    bread: "#9c755f",
    quick_bread: "#59a14f",
    brownies: "#b07aa1",
    batter: "#76b7b2",
    dessert_other: "#bab0ac",
  };

  AID.colorOf = function (cls) {
    return AID.palette[cls] || "#777777";
  };

  /* De-emphasised dots (context when something else is highlighted). Drawn in
   * the class colour, a dense pile of translucent dots still stacks to a solid,
   * saturated blob that reads like a highlighted point — the cookie cluster is
   * the worst case. Fading the colour toward the page background gives the pile
   * a low ceiling: hundreds of overlaps top out at a pale tint, never at the
   * full class colour, so a dimmed cluster cannot masquerade as highlighted. */
  const DIM_MIX = 0.7;
  const dimCache = {};
  AID.dimColorOf = function (cls) {
    const base = AID.colorOf(cls);
    if (dimCache[base]) return dimCache[base];
    const r = parseInt(base.slice(1, 3), 16);
    const g = parseInt(base.slice(3, 5), 16);
    const b = parseInt(base.slice(5, 7), 16);
    const mix = v => Math.round(v + (255 - v) * DIM_MIX);
    const hex = v => v.toString(16).padStart(2, "0");
    const out = "#" + hex(mix(r)) + hex(mix(g)) + hex(mix(b));
    dimCache[base] = out;
    return out;
  };

  /* Per-vertex colours, indexed by compartment slot; shared by the divider bar
   * and the canvas badges. */
  AID.VERTEX_COLORS = ["#4e79a7", "#f28e2b", "#59a14f", "#b07aa1", "#e15757"];
  AID.vertexColor = function (i) {
    return AID.VERTEX_COLORS[i % AID.VERTEX_COLORS.length];
  };

  /* Vertex labels are letters (A, B, C, D), matching the plot corner badges and
   * the divider-bar compartments, so a compartment can be named in a ratio. */
  AID.VERTEX_LABELS = ["A", "B", "C", "D"];
  AID.vertexName = function (i) {
    return AID.VERTEX_LABELS[i] || String(i + 1);
  };
})();