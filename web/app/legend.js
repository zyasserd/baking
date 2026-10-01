/* Class legend: clickable family filter chips.
 *
 * One chip per tag class (its palette color). Click to isolate that family;
 * click several to combine (OR within the selected families). The selection
 * lives in store.classFilter and is ANDed with the search query by
 * searchbar.js, so points outside the selection fade like a search.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.attachLegend = function (el, store, data) {
    function toggle(cls) {
      const cur = (store.get().classFilter || []).slice();
      const at = cur.indexOf(cls);
      if (at >= 0) cur.splice(at, 1); else cur.push(cls);
      store.set({ classFilter: cur });
      if (AID.rerunSearch) AID.rerunSearch();
    }

    function render() {
      el.textContent = "";
      const sel = store.get().classFilter || [];

      const label = document.createElement("span");
      label.className = "legendlabel";
      label.textContent = "families:";
      el.appendChild(label);

      for (const cls of data.meta.classes) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "cchip" + (sel.indexOf(cls) >= 0 ? " active" : "");
        chip.style.borderColor = AID.colorOf(cls);
        const dot = document.createElement("i");
        dot.style.background = AID.colorOf(cls);
        chip.appendChild(dot);
        chip.appendChild(document.createTextNode(cls));
        chip.addEventListener("click", () => toggle(cls));
        el.appendChild(chip);
      }

      if (sel.length) {
        const clear = document.createElement("button");
        clear.type = "button";
        clear.className = "cchip clear";
        clear.textContent = "clear";
        clear.addEventListener("click", () => {
          store.set({ classFilter: [] });
          if (AID.rerunSearch) AID.rerunSearch();
        });
        el.appendChild(clear);
      }
    }

    store.subscribe(render);
    render();
    return { render };
  };
})();
