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