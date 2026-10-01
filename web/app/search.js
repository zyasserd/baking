/* Search: token suggestions and query execution. Pure, no DOM.
 *
 * Token types: ingredient (resolved USDA head, colored green), class (the
 * tag-class palette color), keyword (name substring, amber), ratio (part or
 * merged group with a min/max % range, blue).
 *
 * Semantics: OR within the ingredient group (find recipes with any of the
 * listed ingredients), AND across everything else. Executed as byte masks —
 * the painters read state.matches to highlight matches vs context.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  /* plural-insensitive normalization — mirrors src/preprocess/reference.py */
  function canonical(word) {
    let w = word.toLowerCase();
    if (w.length > 4 && w.endsWith("ies")) return w.slice(0, -3) + "y";
    if (w.length > 4 && w.endsWith("oes")) return w.slice(0, -2);
    if (w.length > 3 && w.endsWith("s") && !w.endsWith("ss")) return w.slice(0, -1);
    return w;
  }
  AID.normQuery = function (text) {
    return text.toLowerCase().split(/\s+/).filter(Boolean).map(canonical).join(" ");
  };

  /* ratio targets: the five parts (display order) plus the two canonical merges */
  const RATIO_TARGETS = [
    { label: "flour", idx: [0] },
    { label: "fat", idx: [3] },
    { label: "sugar", idx: [4] },
    { label: "liquid", idx: [1] },
    { label: "egg", idx: [2] },
    { label: "rich (fat+sugar)", idx: [3, 4], key: "rich" },
    { label: "wet (liquid+egg)", idx: [1, 2], key: "wet" },
  ];

  /* Suggestions for the typed text: ingredients (ranked by match + count),
   * classes, ratio targets, and a keyword fallback. */
  AID.suggest = function (text, data) {
    const q = AID.normQuery(text);
    if (!q) return [];
    const out = [];

    const scored = [];
    for (let h = 0; h < data.heads.length; h++) {
      const head = AID.normQuery(data.heads[h]);
      let score = 0;
      if (head === q) score = 4;
      else if (head.startsWith(q)) score = 3;
      else if (head.includes(" " + q)) score = 2;
      else if (head.includes(q)) score = 1;
      if (score) scored.push([score, data.index[data.heads[h]].length, data.heads[h]]);
    }
    scored.sort((a, b) => (b[0] - a[0]) || (b[1] - a[1]));
    for (const [score, count, head] of scored.slice(0, 8)) {
      out.push({ type: "ingredient", label: head, head, count });
    }

    for (const c of data.meta.classes) {
      if (AID.normQuery(c).startsWith(q)) {
        out.push({ type: "class", label: c, count: classCount(c, data) });
      }
    }

    for (const t of RATIO_TARGETS) {
      if (AID.normQuery(t.label).startsWith(q)) {
        out.push({ type: "ratio", label: t.label, target: t });
      }
    }

    if (out.length === 0) {
      out.push({ type: "keyword", label: text.trim() });
    }
    return out;
  };

  function classCount(cls, data) {
    let n = 0;
    for (const c of data.recipes.cls) if (c === cls) n++;
    return n;
  }

  /* Execute tokens -> { mask: Uint8Array|null, ids: Int32Array, count }. */
  AID.runSearch = function (tokens, data) {
    const n = data.meta.n;
    if (tokens.length === 0) return { mask: null, ids: null, count: n };

    let mask = null;
    const and = m2 => {
      if (!mask) { mask = m2; return; }
      for (let i = 0; i < n; i++) mask[i] = mask[i] && m2[i] ? 1 : 0;
    };

    const ings = tokens.filter(t => t.type === "ingredient");
    if (ings.length) { // OR within the ingredient group
      const m = new Uint8Array(n);
      for (const t of ings) for (const i of data.index[t.head]) m[i] = 1;
      and(m);
    }

    for (const t of tokens.filter(t => t.type === "class")) {
      const m = new Uint8Array(n);
      const cls = data.recipes.cls;
      for (let i = 0; i < n; i++) if (cls[i] === t.label) m[i] = 1;
      and(m);
    }

    for (const t of tokens.filter(t => t.type === "keyword")) {
      const m = new Uint8Array(n);
      const q = t.label.toLowerCase();
      const names = data.recipes.name;
      for (let i = 0; i < n; i++) if (names[i].toLowerCase().includes(q)) m[i] = 1;
      and(m);
    }

    for (const t of tokens.filter(t => t.type === "ratio")) {
      const m = new Uint8Array(n);
      const P = data.recipes.P;
      const idx = t.target.idx;
      for (let i = 0; i < n; i++) {
        let v = 0;
        for (const j of idx) v += P[i][j];
        const pct = v * 100;
        if (pct >= t.min && pct <= t.max) m[i] = 1;
      }
      and(m);
    }

    const ids = [];
    for (let i = 0; i < n; i++) if (mask[i]) ids.push(i);
    return { mask, ids: Int32Array.from(ids), count: ids.length };
  };

  AID.RATIO_TARGETS = RATIO_TARGETS;
})();