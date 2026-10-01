/* The ratio card: what the Aid knows that the recipe page does not.
 *
 * Selected recipe -> the five structural ratios per 100 flour, the part
 * composition bar, the nearest book archetype with Aitchison distance, and
 * per-part percentile placement within the recipe's class. Pure helpers live
 * in geo.js; this file only renders state to the DOM.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  // hues in DISPLAY_ORDER (flour, fat, sugar, liquid, egg)
  const PART_HUES = ["#b39168", "#c44e52", "#8172b2", "#5b9bd5", "#edc948"];

  AID.attachPanel = function (panel, store, data) {
    function classRows(cls) {
      const rows = [];
      const P = data.recipes.P, clsArr = data.recipes.cls;
      for (let i = 0; i < P.length; i++) if (clsArr[i] === cls) rows.push(P[i]);
      return rows;
    }

    function mergedQuantiles(cls, idx) {
      const vals = classRows(cls)
        .map(r => idx.reduce((s, j) => s + r[j], 0) * 100)
        .sort((a, b) => a - b);
      const q = p => vals[Math.floor(p / 100 * (vals.length - 1))];
      return [q(5), q(25), q(50), q(75), q(95)];
    }

    function render(sel) {
      panel.textContent = "";
      if (sel < 0 || sel >= data.meta.n) {
        const intro = document.createElement("div");
        intro.className = "intro";
        intro.innerHTML =
          "<h2>Baker's Aid</h2>" +
          "<p>Regroup the parts in the bar above (drag a pill, or click it " +
          "then a compartment; click a divider or <code>+|</code> to change " +
          "the dimension). Click a point for its ratios.</p>" +
          "<p>Search or use the family chips to highlight recipes.</p>" +
          "<p><b>" + data.meta.n.toLocaleString() + "</b> baking recipes, each " +
          "reduced to five structural parts: " +
          data.meta.partNames.join(", ") + ".</p>" +
          "<p>★ = book archetypes (Ruhlman's <i>Ratio</i>).</p>";
        panel.appendChild(intro);
        return;
      }

      const r = data.recipes;
      const head = document.createElement("div");
      head.className = "cardhead";
      const a = document.createElement("a");
      a.href = r.url[sel];
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = r.name[sel];
      head.appendChild(a);
      const cls = document.createElement("span");
      cls.className = "classchip";
      cls.style.background = AID.colorOf(r.cls[sel]);
      cls.textContent = r.cls[sel];
      head.appendChild(cls);
      panel.appendChild(head);

      const P = r.P[sel];

      const ro = document.createElement("div");
      ro.className = "readout";
      ro.textContent = AID.readout(P);
      const roLabel = document.createElement("div");
      roLabel.className = "readoutlabel";
      roLabel.textContent = "parts per 100 flour (flour:fat:sugar:liquid:egg)";
      panel.appendChild(ro);
      panel.appendChild(roLabel);

      // composition bar
      const bar = document.createElement("div");
      bar.className = "compbar";
      AID.DISPLAY_ORDER.forEach((di, pos) => {
        const v = P[di];
        const seg = document.createElement("span");
        seg.style.width = (v * 100).toFixed(1) + "%";
        seg.style.background = PART_HUES[pos];
        seg.title = AID.PART_NAMES[di] + " " + (v * 100).toFixed(1) + "%";
        bar.appendChild(seg);
      });
      panel.appendChild(bar);

      const legend = document.createElement("div");
      legend.className = "legend";
      AID.DISPLAY_ORDER.forEach((di, pos) => {
        const item = document.createElement("span");
        const sw = document.createElement("i");
        sw.style.background = PART_HUES[pos];
        item.appendChild(sw);
        item.appendChild(document.createTextNode(
          AID.PART_NAMES[di] + " " + (P[di] * 100).toFixed(1) + "%"));
        legend.appendChild(item);
      });
      panel.appendChild(legend);

      // nearest archetype
      const near = AID.aitchisonNearest(P, data.archetypes);
      const arch = document.createElement("div");
      arch.className = "arch";
      arch.innerHTML = "nearest archetype: <b>★ " + near.name + "</b> " +
        '<span class="muted">(d=' + near.d.toFixed(3) + ")</span>";
      panel.appendChild(arch);

      // per-part percentile within the class
      const qs = data.percentiles[r.cls[sel]];
      const rich = mergedQuantiles(r.cls[sel], [3, 4]);
      const wet = mergedQuantiles(r.cls[sel], [1, 2]);
      const targets = AID.DISPLAY_ORDER.map(i => ({
        name: AID.PART_NAMES[i], v: P[i] * 100, q: qs[AID.PART_NAMES[i]],
      })).concat([
        { name: "rich (fat+sugar)", v: (P[3] + P[4]) * 100, q: rich },
        { name: "wet (liquid+egg)", v: (P[1] + P[2]) * 100, q: wet },
      ]);

      const h = document.createElement("div");
      h.className = "pchead";
      h.textContent = "where this sits in " + r.cls[sel];
      panel.appendChild(h);

      targets.forEach(t => {
        const row = document.createElement("div");
        row.className = "pcrow";
        const lab = document.createElement("span");
        lab.className = "pclabel";
        lab.textContent = t.name;
        const track = document.createElement("div");
        track.className = "track";
        const marker = document.createElement("i");
        marker.style.left = Math.max(0, Math.min(100, AID.percentileOf(t.v, t.q))).toFixed(1) + "%";
        track.appendChild(marker);
        const val = document.createElement("span");
        val.className = "pcval";
        val.textContent = "p" + Math.round(AID.percentileOf(t.v, t.q));
        row.appendChild(lab);
        row.appendChild(track);
        row.appendChild(val);
        panel.appendChild(row);
      });
    }

    store.subscribe(st => render(st.selection));
    render(-1);
    return { render };
  };
})();