/* Divider bar: the ratio's compartments, one per plot vertex.
 *
 * Reading left to right: a dashed `rest` box (inactive parts), then the active
 * compartments separated by dividers `|`, parts inside a compartment joined by
 * `+`. Each compartment carries a numbered badge coloured to match its plot
 * vertex.
 *
 * Editing:
 *   - drag a pill onto a compartment (or the rest box) to regroup it;
 *   - click a pill, then click a compartment (touch-friendly fallback);
 *   - click a divider `|` to remove it (merge the two compartments);
 *   - click a compartment's `+|` to add a divider (split off its last part).
 *
 * All edits only change the grouping — the plot camera/zoom is untouched.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.attachDividerBar = function (el, store) {
    let picked = -1;      // part selected for the click-to-move fallback
    let dragPart = null;  // part being dragged (Safari dataTransfer fallback)
    let lastKey = null;

    function groupsOf() {
      const st = store.get();
      return st.groups || AID.resolveGroups(st.partition);
    }

    function applyGroups(g) {
      if (!g || !g.length) return;
      picked = -1;
      store.set({ groups: g, partition: AID.groupsKey(g) });
    }

    function move(part, target) {
      applyGroups(AID.movePart(groupsOf(), part, target));
    }

    function pill(part) {
      const node = document.createElement("span");
      node.className = "rpill" + (picked === part ? " picked" : "");
      node.textContent = AID.PART_NAMES[part];
      node.draggable = true;
      node.addEventListener("dragstart", e => {
        dragPart = part;
        e.dataTransfer.setData("text/plain", String(part));
        e.dataTransfer.effectAllowed = "move";
        node.classList.add("dragging");
      });
      node.addEventListener("dragend", () => {
        dragPart = null;
        node.classList.remove("dragging");
      });
      node.addEventListener("click", e => {
        e.stopPropagation();
        picked = picked === part ? -1 : part;
        render();
      });
      return node;
    }

    function dropZone(node, onDrop) {
      node.addEventListener("dragover", e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        node.classList.add("over");
      });
      node.addEventListener("dragleave", () => node.classList.remove("over"));
      node.addEventListener("drop", e => {
        e.preventDefault();
        node.classList.remove("over");
        const raw = e.dataTransfer.getData("text/plain");
        const part = raw !== "" ? Number(raw) : dragPart;
        dragPart = null;
        if (part !== null && part !== undefined && !Number.isNaN(part)) onDrop(part);
      });
      // click-to-move fallback (also the only path on touch devices)
      node.addEventListener("click", () => { if (picked >= 0) onDrop(picked); });
    }

    function render() {
      const groups = groupsOf();
      const key = AID.groupsKey(groups) + "|" + picked;
      if (key === lastKey) return;
      lastKey = key;
      el.textContent = "";

      // rest compartment (inactive parts)
      const hidden = AID.hiddenParts(groups);
      const rest = document.createElement("div");
      rest.className = "rcomp rest";
      const rlabel = document.createElement("span");
      rlabel.className = "rclabel";
      rlabel.textContent = "rest";
      rest.appendChild(rlabel);
      if (hidden.length) {
        hidden.forEach(p => rest.appendChild(pill(p)));
      } else {
        const e = document.createElement("span");
        e.className = "rempty";
        e.textContent = "\u2014";
        rest.appendChild(e);
      }
      dropZone(rest, part => move(part, -1));
      el.appendChild(rest);

      groups.forEach((g, i) => {
        if (i > 0) {
          const div = document.createElement("button");
          div.type = "button";
          div.className = "rdivider";
          div.textContent = "|";
          div.title = "remove this divider (merge the two compartments)";
          div.addEventListener("click", e => {
            e.stopPropagation();
            applyGroups(AID.mergeGroups(groups, i - 1, i));
          });
          el.appendChild(div);
        }

        const comp = document.createElement("div");
        comp.className = "rcomp";
        const badge = document.createElement("em");
        badge.className = "rbadge";
        badge.style.background = AID.vertexColor(i);
        badge.textContent = String(i + 1);
        comp.appendChild(badge);
        g.forEach((p, k) => {
          if (k) {
            const plus = document.createElement("span");
            plus.className = "rplus";
            plus.textContent = "+";
            comp.appendChild(plus);
          }
          comp.appendChild(pill(p));
        });
        if (g.length > 1 && groups.length < 4) {
          const split = document.createElement("button");
          split.type = "button";
          split.className = "rsplit";
          split.textContent = "+|";
          split.title = "add a divider (split off this compartment's last part)";
          split.addEventListener("click", e => {
            e.stopPropagation();
            applyGroups(AID.splitGroup(groups, i));
          });
          comp.appendChild(split);
        }
        dropZone(comp, part => move(part, i));
        el.appendChild(comp);
      });

      // drop a pill here to pull it into its own new compartment (add divider)
      if (groups.length < 4) {
        const add = document.createElement("div");
        add.className = "rcomp add";
        add.title = "drop a part here to give it its own compartment";
        add.textContent = "+";
        dropZone(add, part => {
          applyGroups(AID.pullOut(groups, part));
        });
        el.appendChild(add);
      }
    }

    store.subscribe(render);
    render();
    return { render };
  };
})();
