/* About page: fill the headline numbers and the stage-1 row funnel from the
 * provenance that ships inside the data. Pure DOM; no geometry. */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.fillAbout = function (data) {
    const stats = (data.meta.provenance || {}).stats || {};

    const total = document.getElementById("about-total");
    if (total && stats.total) total.textContent = stats.total.toLocaleString();

    const funnel = document.getElementById("funnel");
    if (!funnel || !stats.total) return;

    const steps = [
      ["corpus recipes", stats.total],
      ["with a Food.com link", stats.food_rows],
      ["joined to Food.com", stats.joined],
      ["kept as baked goods", stats.kept],
    ];
    funnel.textContent = "";
    for (const [label, n] of steps) {
      if (n === undefined) continue;
      const row = document.createElement("div");
      row.className = "frow";

      const l = document.createElement("span");
      l.className = "flabel";
      l.textContent = label;

      const bar = document.createElement("span");
      bar.className = "fbar";
      const fill = document.createElement("i");
      fill.style.width = Math.max(1.5, (n / stats.total) * 100).toFixed(2) + "%";
      fill.title = n.toLocaleString() + " recipes";
      bar.appendChild(fill);

      const num = document.createElement("span");
      num.className = "fnum";
      num.textContent = n.toLocaleString();

      row.appendChild(l);
      row.appendChild(bar);
      row.appendChild(num);
      funnel.appendChild(row);
    }
  };
})();
