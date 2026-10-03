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
    /* Donut of the family composition of the neighbourhood. SVG so it scales
     * and needs no canvas context; a single-family neighbourhood degenerates
     * to a full ring (an SVG arc of 360° is empty). */
    function pie(counts) {
      const NS = "http://www.w3.org/2000/svg";
      const entries = Object.keys(counts).map(c => [c, counts[c]])
        .sort((a, b) => b[1] - a[1]);
      const total = entries.reduce((s, e) => s + e[1], 0);
      const size = 108, rr = 46, ri = 26, c = size / 2;
      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("viewBox", "0 0 " + size + " " + size);
      svg.setAttribute("width", size);
      svg.setAttribute("height", size);
      svg.setAttribute("class", "pie");

      if (entries.length === 1) {
        for (const [fill, r] of [[AID.colorOf(entries[0][0]), rr], ["#fff", ri]]) {
          const circ = document.createElementNS(NS, "circle");
          circ.setAttribute("cx", c); circ.setAttribute("cy", c);
          circ.setAttribute("r", r); circ.setAttribute("fill", fill);
          svg.appendChild(circ);
        }
      } else {
        let ang = -Math.PI / 2;
        for (const [cls, n] of entries) {
          const a2 = ang + (n / total) * Math.PI * 2, large = n / total > 0.5 ? 1 : 0;
          const x1 = c + rr * Math.cos(ang), y1 = c + rr * Math.sin(ang);
          const x2 = c + rr * Math.cos(a2), y2 = c + rr * Math.sin(a2);
          const x3 = c + ri * Math.cos(a2), y3 = c + ri * Math.sin(a2);
          const x4 = c + ri * Math.cos(ang), y4 = c + ri * Math.sin(ang);
          const path = document.createElementNS(NS, "path");
          path.setAttribute("fill", AID.colorOf(cls));
          path.setAttribute("d", "M" + x1 + " " + y1 +
            "A" + rr + " " + rr + " 0 " + large + " 1 " + x2 + " " + y2 +
            "L" + x3 + " " + y3 +
            "A" + ri + " " + ri + " 0 " + large + " 0 " + x4 + " " + y4 + "Z");
          svg.appendChild(path);
          ang = a2;
        }
      }

      const wrap = document.createElement("div");
      wrap.className = "pierow";
      wrap.appendChild(svg);
      const legend = document.createElement("div");
      legend.className = "pielegend";
      for (const [cls, n] of entries) {
        const item = document.createElement("span");
        const sw = document.createElement("i");
        sw.style.background = AID.colorOf(cls);
        item.appendChild(sw);
        item.appendChild(document.createTextNode(
          cls + " " + n.toLocaleString() + " (" +
          Math.round(n / total * 100) + "%)"));
        legend.appendChild(item);
      }
      wrap.appendChild(legend);
      return wrap;
    }

    function appendComposition(P) {
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
    }

    /* The closest simple ratio (small integers), above the per-100 readout. */
    function appendSimpleRatio(P, eps) {
      const sr = AID.simpleRatio(P, eps);
      const ro = document.createElement("div");
      ro.className = "readout";
      ro.textContent = sr ? AID.formatRatio(sr) : "\u2014";
      const lab = document.createElement("div");
      lab.className = "readoutlabel";
      lab.textContent = "closest simple ratio (flour:fat:sugar:liquid:egg)";
      panel.appendChild(ro);
      panel.appendChild(lab);
    }

    function appendPer100(P) {
      const ro = document.createElement("div");
      ro.className = "readout";
      ro.textContent = AID.readout(P);
      const roLabel = document.createElement("div");
      roLabel.className = "readoutlabel";
      roLabel.textContent = "parts per 100 flour (flour:fat:sugar:liquid:egg)";
      panel.appendChild(ro);
      panel.appendChild(roLabel);
    }

    /* A selected marker (archetype star or class-mean diamond) is a ratio, not
     * a recipe: show its composition and simple ratio. */
    function renderMarker(focus) {
      const P = AID.markerComposition(data, focus);
      const head = document.createElement("div");
      head.className = "cardhead";
      const b = document.createElement("b");
      b.textContent = (focus.kind === "archetype" ? "\u2605 " : "\u25c6 ") + focus.id;
      head.appendChild(b);
      const fam = focus.kind === "class"
        ? focus.id : (AID.ARCHETYPE_FAMILY[focus.id] || null);
      const tag = document.createElement("span");
      tag.className = "classchip";
      tag.style.background = AID.colorOf(fam);
      tag.textContent = focus.kind === "class" ? "class mean" : "archetype";
      head.appendChild(tag);
      panel.appendChild(head);
      if (P) {
        appendSimpleRatio(P, focus.kind === "archetype" ? 1e-5 : undefined);
        appendPer100(P);
        appendComposition(P);
      }
      const info = document.createElement("div");
      info.className = "arch";
      info.appendChild(document.createTextNode(
        focus.kind === "class" ? "class centre \u00b7 family: " : "family: "));
      const bb = document.createElement("b");
      bb.textContent = fam || "\u2014";
      info.appendChild(bb);
      panel.appendChild(info);
    }

    function render(sel, focus) {
      panel.textContent = "";
      nbEl = null;
      if (focus) { renderMarker(focus); return; }
      if (sel < 0 || sel >= data.meta.n) {
        const intro = document.createElement("div");
        intro.className = "intro";
        intro.innerHTML =
          "<p>Click a point for its ratios. While anything is highlighted — a " +
          "search, a selection with its family and neighbourhood, or a marker — " +
          "a click near a highlighted point snaps to it; click empty space to " +
          "clear. Click a \u2605 book archetype or a \u25c6 class centre to see " +
          "its ratio. Regroup the five parts in the " +
          "ratio bar above the plot (drag a pill, or click it then a " +
          "compartment; click a divider or <code>+|</code> to change the " +
          "dimension). A fixed-radius " +
          "neighbourhood (a band on the axis, a disc in the triangle, a ball " +
          "in the tetrahedron) marks nearby recipes, dotted lines point to the " +
          "nearest class and book ratio, and its family stays highlighted " +
          "(toggle it in <b>display</b> below). In the " +
          "tetrahedron, drag to orbit and Ctrl-drag to pan.</p>" +
          "<p>Search, or pick families in the list below, to highlight recipes.</p>" +
          "<p><b>" + data.meta.n.toLocaleString() + "</b> baking recipes, each " +
          "reduced to five structural parts: " +
          data.meta.partNames.join(", ") + ".</p>" +
          "<p>\u2605 = book archetypes (Ruhlman's <i>Ratio</i>).</p>";
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
      appendSimpleRatio(P);
      appendPer100(P);
      appendComposition(P);

      // nearest archetype and nearest class centroid
      const near = AID.aitchisonNearest(P, data.archetypes);
      const cent = AID.nearestCentroid(P, data.recipes.P, data.recipes.cls);
      const arch = document.createElement("div");
      arch.className = "arch";
      arch.innerHTML =
        "nearest archetype: <b>\u2605 " + near.name + "</b> " +
        '<span class="muted">(d=' + near.d.toFixed(3) + ")</span><br>" +
        "nearest centroid: <b>" + cent.name + "</b> " +
        '<span class="muted">(d=' + cent.d.toFixed(3) + ")</span>";
      panel.appendChild(arch);

      // neighbourhood donut. It is screen-space (the painter owns it) and
      // arrives via setNeighbourhood() after each draw; render leaves a slot.
      const nh = document.createElement("div");
      nh.className = "pchead";
      panel.appendChild(nh);
      const nbody = document.createElement("div");
      panel.appendChild(nbody);
      nbEl = { sel, head: nh, body: nbody };
      fillNeighbourhood(store.get().showNeighbourhood ? lastNb : null);
    }

    let nbEl = null, lastNb = null, lastNbSig = null, lastNbT = 0;

    function fillNeighbourhood(nb) {
      if (!nbEl) return;
      if (!nb || nb.sel !== nbEl.sel || nb.count === 0) {
        nbEl.head.textContent = "neighbourhood: \u2014";
        nbEl.body.textContent = "";
        return;
      }
      nbEl.head.textContent = "neighbourhood: " +
        nb.count.toLocaleString() + " recipes";
      nbEl.body.textContent = "";
      nbEl.body.appendChild(pie(nb.counts));
    }

    /* Latest neighbourhood from the painter. Selection changes render at once;
     * orbit/zoom churn is throttled (~8/s) so the donut does not rebuild every
     * frame. */
    function setNeighbourhood(nb) {
      const sig = nb ? nb.sel + ":" + nb.count : "null";
      if (sig === lastNbSig) return;
      const selChanged = !lastNb || !nb || lastNb.sel !== nb.sel;
      lastNb = nb;
      const now = Date.now();
      if (!selChanged && now - lastNbT < 120) return;
      lastNbT = now;
      lastNbSig = sig;
      fillNeighbourhood(nb);
    }

    store.subscribe(st => render(st.selection, st.focus));
    render(-1, null);
    return { render, setNeighbourhood };
  };
})();