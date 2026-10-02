/* Class legend: the families list, always in the side panel.
 *
 * One row per tag class (its palette color, name, recipe count). Click to
 * isolate that family; click several to combine (OR within the selected
 * families). The selection lives in store.classFilter and is ANDed with the
 * search query by searchbar.js, so points outside the selection fade like a
 * search.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.attachLegend = function (el, store, data) {
    // class counts, computed once
    const count = {};
    for (const c of data.recipes.cls) count[c] = (count[c] || 0) + 1;

    function toggle(cls) {
      const cur = (store.get().classFilter || []).slice();
      const at = cur.indexOf(cls);
      if (at >= 0) cur.splice(at, 1); else cur.push(cls);
      store.set({ classFilter: cur });
      if (AID.rerunSearch) AID.rerunSearch();
    }

    function clear() {
      store.set({ classFilter: [] });
      if (AID.rerunSearch) AID.rerunSearch();
    }

    function render() {
      el.textContent = "";
      const sel = store.get().classFilter || [];

      for (const cls of data.meta.classes) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "fam" + (sel.indexOf(cls) >= 0 ? " active" : "");
        const dot = document.createElement("i");
        dot.style.background = AID.colorOf(cls);
        const name = document.createElement("span");
        name.className = "famname";
        name.textContent = cls;
        const n = document.createElement("span");
        n.className = "famcount";
        n.textContent = (count[cls] || 0).toLocaleString();
        row.appendChild(dot);
        row.appendChild(name);
        row.appendChild(n);
        row.addEventListener("click", () => toggle(cls));
        el.appendChild(row);
      }

      // Always present (hidden when nothing is selected) so that appearing
      // here never changes the section's height and nudges the panel.
      const c = document.createElement("button");
      c.type = "button";
      c.className = "fam clear" + (sel.length ? "" : " hidden");
      c.textContent = "clear families";
      c.disabled = sel.length === 0;
      c.addEventListener("click", clear);
      el.appendChild(c);
    }

    store.subscribe(render);
    render();
    return { render };
  };
})();
