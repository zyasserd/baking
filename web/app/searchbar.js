/* Search bar UI: chips, typeahead dropdown, keyboard, match count.
 *
 * Chips are typed and colored: ingredient green, class = palette color,
 * keyword amber, ratio blue. State flow: input -> tokens -> search.run ->
 * store.matches -> painters highlight; the painters never touch the DOM here.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.attachSearch = function (root, store, data, plotCtl) {
    const input = root.querySelector("#search");
    const chipsEl = root.querySelector("#chips");
    const dropdown = root.querySelector("#dropdown");
    const countEl = root.querySelector("#count");
    input.disabled = false;

    let tokens = [];
    let suggestions = [];
    let active = 0;

    function commit(token) {
      if (token.type === "ratio") {
        token.min = 0;
        token.max = 100;
      }
      tokens.push(token);
      input.value = "";
      suggestions = [];
      dropdown.style.display = "none";
      rerun();
    }

    function rerun() {
      const res = AID.runSearch(tokens, data);
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
      store.set({ tokens: tokens.slice(), matches: mask, matchCount: count });
      renderChips();
      countEl.textContent = (tokens.length || sel.length)
        ? count.toLocaleString() + " of " + data.meta.n.toLocaleString() + " recipes"
        : "";
      if (plotCtl) plotCtl.markDirty();
    }
    AID.rerunSearch = rerun;

    function renderChips() {
      chipsEl.textContent = "";
      tokens.forEach((t, i) => {
        const chip = document.createElement("span");
        chip.className = "chip " + t.type;
        if (t.type === "class") chip.style.borderColor = AID.colorOf(t.label);
        const label = document.createElement("span");
        label.textContent = t.type === "ratio" ? t.target.label : t.label;
        chip.appendChild(label);
        if (t.type === "ratio") {
          const min = document.createElement("input");
          min.type = "number"; min.value = t.min;
          const max = document.createElement("input");
          max.type = "number"; max.value = t.max;
          min.addEventListener("input", () => { t.min = Number(min.value); rerun(); });
          max.addEventListener("input", () => { t.max = Number(max.value); rerun(); });
          chip.appendChild(min);
          chip.appendChild(max);
        }
        const x = document.createElement("button");
        x.textContent = "×";
        x.addEventListener("click", () => { tokens.splice(i, 1); rerun(); });
        chip.appendChild(x);
        chipsEl.appendChild(chip);
      });
    }

    function renderDropdown() {
      dropdown.textContent = "";
      if (!suggestions.length) { dropdown.style.display = "none"; return; }
      suggestions.forEach((s, i) => {
        const item = document.createElement("div");
        item.className = "suggestion " + s.type + (i === active ? " active" : "");
        const name = document.createElement("span");
        name.textContent = s.label;
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
      suggestions = AID.suggest(input.value, data);
      active = 0;
      renderDropdown();
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
        tokens.pop();
        rerun();
      } else if (e.key === "Escape") {
        input.value = "";
        suggestions = [];
        dropdown.style.display = "none";
      }
    });

    input.addEventListener("blur", () => {
      setTimeout(() => { dropdown.style.display = "none"; }, 150);
    });
    input.addEventListener("focus", () => { if (suggestions.length) renderDropdown(); });

    renderChips();
    function clear() {
      tokens = [];
      input.value = "";
      suggestions = [];
      dropdown.style.display = "none";
      rerun();
    }
    return { rerun, clear };
  };
})();