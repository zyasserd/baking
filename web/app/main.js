/* Baker's Aid — bootstrap: data contract check, view switching, wiring. */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  const status = document.getElementById("status");
  if (typeof AID_DATA === "undefined") {
    status.textContent = "no data: run scripts/analyze.py first";
    return;
  }
  const data = AID_DATA;
  status.style.display = "none";

  if (AID.fillAbout) AID.fillAbout(data);

  const store = AID.createStore({
    partition: "canon2",
    groups: AID.resolveGroups("canon2"),
    selection: -1,
    classFilter: [],
    showNeighbourhood: true,
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

  const panelCtl = AID.attachPanel(document.getElementById("recipe"), store, data);

  const nbBtn = document.getElementById("nbtoggle");
  nbBtn.setAttribute("aria-pressed", String(store.get().showNeighbourhood));
  nbBtn.addEventListener("click", () => {
    const on = !store.get().showNeighbourhood;
    store.set({ showNeighbourhood: on });
    nbBtn.setAttribute("aria-pressed", String(on));
  });

  // The painter owns the screen-space neighbourhood (it depends on the current
  // projection); the plot forwards it here to feed the ratio card's donut.
  AID.onNeighbourhood = nb => panelCtl.setNeighbourhood(nb);

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