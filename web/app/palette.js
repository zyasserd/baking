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

  /* Per-vertex colours, indexed by compartment slot (1-based labels on the
   * plot); shared by the divider bar and the canvas badges. */
  AID.VERTEX_COLORS = ["#4e79a7", "#f28e2b", "#59a14f", "#b07aa1", "#e15757"];
  AID.vertexColor = function (i) {
    return AID.VERTEX_COLORS[i % AID.VERTEX_COLORS.length];
  };
})();