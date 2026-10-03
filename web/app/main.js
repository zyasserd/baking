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
    focus: null,
    classFilter: [],
    showNeighbourhood: true,
    showArchetypes: true,
    showCentroids: true,
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

  // Display toggles. Turning a marker layer off also clears a focus on it, so
  // the plot never keeps "highlighting" something it no longer draws.
  [
    ["nbtoggle", "showNeighbourhood", null],
    ["atoggle", "showArchetypes", "archetype"],
    ["ctoggle", "showCentroids", "class"],
  ].forEach(([id, key, kind]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.setAttribute("aria-pressed", String(store.get()[key]));
    btn.addEventListener("click", () => {
      const on = !store.get()[key];
      const patch = { [key]: on };
      const f = store.get().focus;
      if (!on && kind && f && f.kind === kind) patch.focus = null;
      store.set(patch);
      btn.setAttribute("aria-pressed", String(on));
    });
  });

  // The painter owns the screen-space neighbourhood (it depends on the current
  // projection); the plot forwards it here to feed the ratio card's donut.
  AID.onNeighbourhood = nb => panelCtl.setNeighbourhood(nb);
})();