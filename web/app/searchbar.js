/* Search bar UI: chips, inline AND/OR connectors, typeahead, keyboard, count.
 *
 * Chips are typed and colored: ingredient green, class = palette color,
 * keyword amber, ratio blue. Between two chips sits a small connector pill
 * showing how they combine (AND/OR); clicking it flips the operator, so the
 * user never has to type "and"/"or" (they still can, as a convenience).
 * State flow: input -> tokens -> search.run -> store.matches -> painters
 * highlight; the painters never touch the DOM here.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  // Two adjacent ingredients default to OR (find recipes with any of them);
  // every other pair defaults to AND.
  function defaultConn(a, b) {
    return a.type === "ingredient" && b.type === "ingredient" ? "or" : "and";
  }

  AID.attachSearch = function (root, store, data, plotCtl) {
    const input = root.querySelector("#search");
    const chipsEl = root.querySelector("#chips");
    const dropdown = root.querySelector("#dropdown");
    const countEl = root.querySelector("#count");
    const clearBtn = root.querySelector("#searchclear");
    input.disabled = false;

    let tokens = [];    // filter operands only (no op tokens)
    let conns = [];     // explicit connector before tokens[i+1]; null = default
    let eqs = [];       // ratio-equation overlays (drawn as loci, never filter)
    let pending = null; // connector typed before the next operand
    let suggestions = [];
    let active = 0;

    const connAt = i => conns[i] || defaultConn(tokens[i], tokens[i + 1]);
    const hideDropdown = () => { dropdown.style.display = "none"; };

    // Current partition, so single letters A-D and "+" combinations resolve
    // against the compartments shown on the plot.
    const groupsOf = () => {
      const st = store.get();
      return st.groups || AID.resolveGroups(st.partition);
    };

    function queryTokens() {
      const out = [];
      for (let i = 0; i < tokens.length; i++) {
        if (i > 0) out.push({ type: "op", op: connAt(i - 1) });
        out.push(tokens[i]);
      }
      return out;
    }

    function commit(token) {
      // A ratio equation is a geometric overlay, not a filter.
      if (token.type === "ratioeq") {
        eqs.push(token);
        input.value = "";
        suggestions = [];
        hideDropdown();
        renderChips();
        rerun();
        return;
      }
      // A family/class is a legend filter, not a search chip: choosing one
      // highlights its chip in the legend bar below (ANDed with any query),
      // rather than adding another token to the search row.
      if (token.type === "class") {
        const cur = (store.get().classFilter || []).slice();
        if (cur.indexOf(token.label) < 0) cur.push(token.label);
        input.value = "";
        suggestions = [];
        hideDropdown();
        store.set({ classFilter: cur });
        renderChips();
        rerun();
        return;
      }
      // "and"/"or" typed free-hand become the connector before the next chip.
      if (token.type === "keyword") {
        const w = token.label.trim().toLowerCase();
        if (w === "and" || w === "or") {
          pending = w;
          input.value = "";
          suggestions = [];
          hideDropdown();
          return;
        }
      }
      if (token.type === "ratio") {
        token.min = 0;
        token.max = 100;
      }
      if (tokens.length > 0) conns.push(pending);
      tokens.push(token);
      pending = null;
      input.value = "";
      suggestions = [];
      hideDropdown();
      renderChips();
      rerun();
    }

    function removeToken(i) {
      tokens.splice(i, 1);
      if (conns.length) conns.splice(i === 0 ? 0 : i - 1, 1);
      renderChips();
      rerun();
    }

    function removeEq(i) {
      eqs.splice(i, 1);
      renderChips();
      rerun();
    }

    function toggleConn(i) {
      conns[i] = connAt(i) === "and" ? "or" : "and";
      renderChips();
      rerun();
    }

    function rerun() {
      const res = AID.runSearch(queryTokens(), data);
      let mask = res.mask, count = res.count;
      // the class legend filters the search result (AND with the token query)
      const sel = store.get().classFilter || [];
      if (sel.length) {
        if (!mask) mask = new Uint8Array(data.meta.n).fill(1);
        let c = 0;
        for (let i = 0; i < data.meta.n; i++) {
          if (mask[i] && sel.indexOf(data.recipes.cls[i]) >= 0) c++;
          else mask[i] = 0;
        }
        count = c;
      }
      store.set({
        tokens: tokens.slice(),
        ratioEqs: eqs.slice(),
        matches: mask,
        matchCount: count,
        focus: null,
      });
      countEl.textContent = (tokens.length || sel.length)
        ? count.toLocaleString() + " of " + data.meta.n.toLocaleString() + " recipes"
        : (eqs.length ? "ratio overlay" : "");
      if (clearBtn) {
        clearBtn.style.display = (tokens.length || sel.length || eqs.length) ? "flex" : "none";
      }
      if (plotCtl) plotCtl.markDirty();
    }
    AID.rerunSearch = rerun;

    function chipEl(t, i) {
      if (t.type === "ratioeq") return eqChipEl(t, i);
      const chip = document.createElement("span");
      chip.className = "chip " + t.type;
      if (t.type === "class") chip.style.borderColor = AID.colorOf(t.label);
      const label = document.createElement("span");
      label.textContent = t.type === "ratio" ? t.target.label : t.label;
      chip.appendChild(label);
      if (t.type === "ratio") {
        const min = document.createElement("input");
        min.type = "number"; min.value = t.min; min.setAttribute("aria-label", "minimum percent");
        const max = document.createElement("input");
        max.type = "number"; max.value = t.max; max.setAttribute("aria-label", "maximum percent");
        // Editing a range only re-runs the query (chips are not rebuilt), so
        // focus is preserved while typing.
        min.addEventListener("input", () => { t.min = Number(min.value); rerun(); });
        max.addEventListener("input", () => { t.max = Number(max.value); rerun(); });
        chip.appendChild(min);
        chip.appendChild(max);
      }
      const x = document.createElement("button");
      x.textContent = "×";
      x.setAttribute("aria-label", "remove " + (t.type === "ratio" ? t.target.label : t.label));
      x.addEventListener("click", () => removeToken(i));
      chip.appendChild(x);
      return chip;
    }

    function eqChipEl(t, i) {
      const chip = document.createElement("span");
      chip.className = "chip eq";
      const label = document.createElement("span");
      label.textContent = t.label;
      chip.appendChild(label);
      const x = document.createElement("button");
      x.textContent = "×";
      x.setAttribute("aria-label", "remove ratio " + t.label);
      x.addEventListener("click", () => removeEq(i));
      chip.appendChild(x);
      return chip;
    }

    function connEl(i) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "conn " + connAt(i);
      b.textContent = connAt(i);
      b.title = "click to combine with " + (connAt(i) === "and" ? "OR" : "AND");
      b.addEventListener("click", () => toggleConn(i));
      return b;
    }

    function renderChips() {
      chipsEl.textContent = "";
      tokens.forEach((t, i) => {
        chipsEl.appendChild(chipEl(t, i));
        if (i < tokens.length - 1) chipsEl.appendChild(connEl(i));
      });
      eqs.forEach((t, i) => chipsEl.appendChild(eqChipEl(t, i)));
    }

    // Bold the typed substring inside a suggestion label.
    function highlight(label, q) {
      const frag = document.createDocumentFragment();
      const at = q ? label.toLowerCase().indexOf(q.toLowerCase()) : -1;
      if (at < 0) {
        frag.appendChild(document.createTextNode(label));
        return frag;
      }
      frag.appendChild(document.createTextNode(label.slice(0, at)));
      const b = document.createElement("b");
      b.textContent = label.slice(at, at + q.length);
      frag.appendChild(b);
      frag.appendChild(document.createTextNode(label.slice(at + q.length)));
      return frag;
    }

    function renderDropdown() {
      dropdown.textContent = "";
      if (!suggestions.length) { hideDropdown(); return; }
      const raw = input.value.trim();
      suggestions.forEach((s, i) => {
        const item = document.createElement("div");
        item.className = "suggestion " + s.type + (i === active ? " active" : "");
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", i === active ? "true" : "false");
        const name = document.createElement("span");
        if (s.type === "keyword" || s.type === "op") name.textContent = s.label;
        else name.appendChild(highlight(s.label, raw));
        item.appendChild(name);
        if (s.count !== undefined) {
          const c = document.createElement("span");
          c.className = "scount";
          c.textContent = s.count.toLocaleString();
          item.appendChild(c);
        }
        item.addEventListener("mousedown", e => { e.preventDefault(); commit(s); });
        dropdown.appendChild(item);
      });
      dropdown.style.display = "block";
    }

    input.addEventListener("input", () => {
      suggestions = AID.suggest(input.value, data, groupsOf());
      active = 0;
      renderDropdown();
      if (clearBtn) clearBtn.style.display = (tokens.length || input.value) ? "flex" : "none";
    });

    input.addEventListener("keydown", e => {
      if (e.key === "ArrowDown" && suggestions.length) {
        active = (active + 1) % suggestions.length;
        renderDropdown();
        e.preventDefault();
      } else if (e.key === "ArrowUp" && suggestions.length) {
        active = (active - 1 + suggestions.length) % suggestions.length;
        renderDropdown();
        e.preventDefault();
      } else if (e.key === "Enter") {
        if (suggestions.length) commit(suggestions[active]);
        else if (input.value.trim()) commit({ type: "keyword", label: input.value.trim() });
      } else if (e.key === "Backspace" && !input.value && tokens.length) {
        removeToken(tokens.length - 1);
      } else if (e.key === "Escape") {
        input.value = "";
        suggestions = [];
        hideDropdown();
        if (clearBtn) {
          clearBtn.style.display = (tokens.length || eqs.length) ? "flex" : "none";
        }
      }
    });

    input.addEventListener("blur", () => {
      setTimeout(hideDropdown, 150);
    });
    input.addEventListener("focus", () => { if (suggestions.length) renderDropdown(); });

    function clear() {
      tokens = [];
      conns = [];
      eqs = [];
      pending = null;
      input.value = "";
      suggestions = [];
      hideDropdown();
      renderChips();
      rerun();
    }
    if (clearBtn) {
      clearBtn.style.display = "none";
      clearBtn.addEventListener("click", () => {
        if ((store.get().classFilter || []).length) store.set({ classFilter: [] });
        clear();
      });
    }

    renderChips();
    return { rerun, clear };
  };
})();
