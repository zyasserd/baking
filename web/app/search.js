/* Search: token suggestions and query execution. Pure, no DOM.
 *
 * Token types: ingredient (resolved USDA head, colored green), class (the
 * tag-class palette color), keyword (name substring, amber), ratio (a part,
 * a "+" combination, or a vertex letter A-D with a min/max % range, blue).
 *
 * Semantics: OR within the ingredient group (find recipes with any of the
 * listed ingredients), AND across everything else. The user may also type
 * explicit "and"/"or" connectors, which are evaluated left-to-right and
 * override the defaults for the pair they sit between. Executed as byte
 * masks — the painters read state.matches to highlight matches vs context.
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
   * classes, ratio targets, and a keyword fallback. `groups` is the current
   * partition (optional) so single letters A-D and "+" combinations resolve. */
  AID.suggest = function (text, data, groups) {
    const q = AID.normQuery(text);
    if (!q) return [];
    const out = [];

    // a complete ratio equation ("flour : fat = 2 : 1") is its own token
    if (text.indexOf(":") >= 0 && text.indexOf("=") >= 0) {
      const eq = AID.parseRatioEq(text, groups);
      if (eq) return [eq];
    }

    // a bare "+" combination of parts ("fat+sugar") is a ratio target
    if (text.indexOf("+") >= 0) {
      const combo = AID.resolveOperand(text, groups);
      if (combo && combo.label) {
        out.push({ type: "ratio", label: combo.label, target: combo });
      }
    }

    // explicit boolean connectors
    if (q === "and" || q === "or") {
      return [{ type: "op", label: q.toUpperCase(), op: q }];
    }

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

    // A family/class typed exactly (or as a prefix) resolves to a legend
    // filter, so surface it ahead of ingredient matches for Enter to hit.
    const clsMatches = [];
    for (const c of data.meta.classes) {
      const nc = AID.normQuery(c);
      if (nc.startsWith(q)) clsMatches.push({ type: "class", label: c, count: classCount(c, data), exact: nc === q });
    }
    const exactClass = clsMatches.filter(s => s.exact);
    if (exactClass.length) out.unshift(...exactClass);
    else out.push(...clsMatches);

    for (const t of RATIO_TARGETS) {
      if (AID.normQuery(t.label).startsWith(q)) {
        out.push({ type: "ratio", label: t.label, target: t });
      }
    }

    // a single letter A-D names the current partition's compartment
    if (groups) {
      for (let i = 0; i < groups.length; i++) {
        if (AID.vertexName(i).toLowerCase() !== q) continue;
        const label = AID.vertexName(i) + " (" + groupText(groups[i]) + ")";
        out.push({
          type: "ratio", label,
          target: { label, idx: groups[i].slice(), key: "vertex", vertex: i },
        });
      }
    }

    // Substring search over recipe names. Always offered (not just as a
    // fallback) so a recipe name is searchable even when an ingredient or class
    // also matches; the "name" tag and count make it clear what it does.
    const kw = text.trim();
    if (kw) out.push({ type: "keyword", label: kw, count: nameCount(kw, data) });
    return out;
  };

  function nameCount(text, data) {
    const needle = text.toLowerCase();
    const names = data.recipes && data.recipes.name ? data.recipes.name : [];
    let n = 0;
    for (let i = 0; i < names.length; i++) {
      if (names[i].toLowerCase().includes(needle)) n++;
    }
    return n;
  }

  function groupText(idx) {
    return idx.map(p => AID.PART_NAMES[p]).join("+");
  }

  function classCount(cls, data) {
    let n = 0;
    for (const c of data.recipes.cls) if (c === cls) n++;
    return n;
  }

  /* Execute tokens -> { mask: Uint8Array|null, ids: Int32Array, count }.
   *
   * Tokens may include explicit "and"/"or" connectors ({ type: "op" }).
   * Evaluation is strictly left-to-right; an "op" token overrides the
   * default connector for the pair it sits between. Without an explicit
   * connector, two adjacent ingredients default to OR and everything else
   * defaults to AND. */
  function operandMask(t, data, n) {
    const m = new Uint8Array(n);
    if (t.type === "ingredient") {
      for (const i of data.index[t.head]) m[i] = 1;
    } else if (t.type === "class") {
      const cls = data.recipes.cls;
      for (let i = 0; i < n; i++) if (cls[i] === t.label) m[i] = 1;
    } else if (t.type === "keyword") {
      const q = t.label.toLowerCase();
      const names = data.recipes.name;
      for (let i = 0; i < n; i++) if (names[i].toLowerCase().includes(q)) m[i] = 1;
    } else if (t.type === "ratio") {
      const P = data.recipes.P;
      const idx = t.target.idx;
      for (let i = 0; i < n; i++) {
        let v = 0;
        for (const j of idx) v += P[i][j];
        const pct = v * 100;
        if (pct >= t.min && pct <= t.max) m[i] = 1;
      }
    }
    return m;
  }

  AID.runSearch = function (tokens, data) {
    const n = data.meta.n;
    const operands = tokens.filter(t => t.type !== "op" && t.type !== "ratioeq");
    if (operands.length === 0) return { mask: null, ids: null, count: n };

    let mask = null;
    let prev = null;
    let pending = null;
    for (const t of tokens) {
      if (t.type === "op") { if (mask) pending = t.op; continue; }
      if (t.type === "ratioeq") continue; // overlay only: never filters
      const m = operandMask(t, data, n);
      if (!mask) { mask = m; prev = t; pending = null; continue; }
      const conn = pending || (prev.type === "ingredient" && t.type === "ingredient" ? "or" : "and");
      if (conn === "and") {
        for (let i = 0; i < n; i++) mask[i] = mask[i] && m[i] ? 1 : 0;
      } else {
        for (let i = 0; i < n; i++) if (m[i]) mask[i] = 1;
      }
      prev = t;
      pending = null;
    }

    const ids = [];
    for (let i = 0; i < n; i++) if (mask[i]) ids.push(i);
    return { mask, ids: Int32Array.from(ids), count: ids.length };
  };

  AID.RATIO_TARGETS = RATIO_TARGETS;

  /* Operands accepted by a ratio equation: the five parts plus the two
   * canonical merges, looked up by normalized name. A "+"-joined sum of these
   * is also an operand (e.g. "fat+sugar"), and a single letter A-D names the
   * current partition's compartment. */
  const EQ_OPERANDS = [
    { label: "flour", idx: [0] },
    { label: "fat", idx: [3] },
    { label: "sugar", idx: [4] },
    { label: "liquid", idx: [1] },
    { label: "egg", idx: [2] },
    { label: "rich", idx: [3, 4] },
    { label: "wet", idx: [1, 2] },
  ];
  const EQ_BY_NAME = {};
  for (const o of EQ_OPERANDS) EQ_BY_NAME[AID.normQuery(o.label)] = o;

  /* Resolve one term to { idx, label } (or null): a vertex letter (A-D) via
   * the current groups, otherwise a "+"-joined sum of known operands. */
  AID.resolveOperand = function (term, groups) {
    const t = String(term).trim();
    if (!t) return null;
    const letter = /^([a-dA-D])$/.exec(t);
    if (letter) {
      const i = letter[1].toUpperCase().charCodeAt(0) - 65;
      if (groups && groups[i]) {
        return { idx: groups[i].slice(), label: letter[1].toUpperCase(), vertex: i };
      }
      return null;
    }
    const words = t.split("+").map(s => s.trim()).filter(Boolean);
    if (!words.length) return null;
    const idx = [], labels = [];
    for (const w of words) {
      const op = EQ_BY_NAME[AID.normQuery(w)];
      if (!op) return null;
      for (const j of op.idx) if (idx.indexOf(j) < 0) idx.push(j);
      labels.push(op.label);
    }
    return idx.length ? { idx, label: labels.join("+") } : null;
  };

  /* Parse "flour : fat = 2 : 1", "fat+sugar : flour = 2 : 1" or "A : B = 2 : 1"
   * (two or more terms each side) into a ratioeq token, or null when the text
   * is not a complete, valid equation. */
  AID.parseRatioEq = function (text, groups) {
    if (text.indexOf(":") < 0 || text.indexOf("=") < 0) return null;
    const sides = text.split("=");
    if (sides.length !== 2) return null;
    const left = sides[0].split(":").map(s => s.trim()).filter(Boolean);
    const right = sides[1].split(":").map(s => s.trim()).filter(Boolean);
    if (left.length < 2 || left.length !== right.length) return null;
    const ops = [];
    for (let i = 0; i < left.length; i++) {
      const op = AID.resolveOperand(left[i], groups);
      const k = Number(right[i]);
      if (!op || !isFinite(k) || k <= 0) return null;
      ops.push({ idx: op.idx.slice(), label: op.label, k });
    }
    return {
      type: "ratioeq",
      label: ops.map(o => o.label).join(" : ") + " = " + ops.map(o => o.k).join(" : "),
      ops,
    };
  };
})();