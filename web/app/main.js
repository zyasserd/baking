/* Baker's Aid — bootstrap: data contract check, view switching, wiring. */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  const status = document.getElementById("status");
  if (typeof AID_DATA === "undefined") {
    status.textContent = "no data — run scripts/analyze.py first";
    return;
  }
  const data = AID_DATA;
  status.style.display = "none";

  const store = AID.createStore({
    partition: "canon2",
    groups: AID.resolveGroups("canon2"),
    selection: -1,
    classFilter: [],
  });

  const plotCtl = AID.attachPlot(
    document.getElementById("canvas"),
    document.getElementById("tooltip"),
    store, data);

  const searchCtl = AID.attachSearch(
    document.getElementById("searchbar"),
    store, data, plotCtl);

  AID.attachLegend(document.getElementById("legend"), store, data);

  AID.attachDividerBar(document.getElementById("ratio"), store);

  AID.attachPanel(document.getElementById("panel"), store, data);

  document.getElementById("reset").addEventListener("click", () => {
    // clear the query and the family filter first, then reset the geometry
    store.set({ classFilter: [], selection: -1 });
    if (searchCtl) searchCtl.clear();
    store.set({
      partition: "canon2",
      groups: AID.resolveGroups("canon2"),
    });
  });
})();