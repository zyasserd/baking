/* Views: one painter per partition dimension (1D violin, 2D triangle, 3D tetra).
 *
 * A painter owns its view transform and drawing; the plot engine (plot.js)
 * owns the canvas, pointer events and the tooltip, and delegates. Painters
 * share one protocol: reset(W,H), draw(ctx), hit(mx,my), wheel/drag/dblclick,
 * value(idx). All geometry comes from AID.geo; state (hover/selection) comes
 * from the plot engine.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  const PT_R = 2.2, HOVER_R = 6, SEL_R = 8;
  /* How far (screen px) a click may land from a highlighted point and still
   * snap onto it. Beyond this the click is treated as empty and deselects. */
  const SNAP_R = 16;

  /* Dot opacity. Points are always translucent so overlaps *blend* (same-class
   * overlaps deepen toward the class colour, different classes mix) instead of
   * one opaque dot hiding the ones beneath it. No dot is ever drawn opaque —
   * opacity carries state, size carries depth, and the selected dot is marked
   * by its ring, not by covering everything under it. */
  const A_IDLE = 0.30, A_ACTIVE = 0.62, A_DIM = 0.06, A_CHOSEN = 0.85;

  /* One dot style for both simplex views: identical radius and opacity in 2D
   * and 3D, so changing dimension never changes how the cloud looks. */
  function dotRadius(v) {
    return v.active ? PT_R + (v.context ? 0.4 : 0) : PT_R - 0.5;
  }

  /* deterministic per-point jitter in [-1, 1] (violin strips) */
  function jitter(i) {
    const s = Math.sin((i + 1) * 127.1) * 43758.5453;
    return (s - Math.floor(s)) * 2 - 1;
  }

  /* client-side KDE mode — where the class bulges (memoized per partition) */
  const modeCache = {};
  AID.kdeMode = function (values, key) {
    if (modeCache[key]) return modeCache[key];
    const n = values.length;
    let m = 0;
    for (let i = 0; i < n; i++) m += values[i];
    m /= n;
    let v = 0;
    for (let i = 0; i < n; i++) { const d = values[i] - m; v += d * d; }
    const sd = Math.sqrt(v / n);
    const h = sd > 0 ? 1.06 * sd * Math.pow(n, -0.2) : 1;
    const lo = Math.max(0, m - 3 * sd), hi = Math.min(100, m + 3 * sd);
    const G = 256;
    let best = lo, bestD = -1;
    for (let g = 0; g < G; g++) {
      const x = lo + (hi - lo) * g / (G - 1);
      let d = 0;
      for (let i = 0; i < n; i++) {
        const u = (x - values[i]) / h;
        d += Math.exp(-0.5 * u * u);
      }
      if (d > bestD) { bestD = d; best = x; }
    }
    modeCache[key] = best;
    return best;
  };

  /* ── shared painter scaffolding ─────────────────────────────────────── */

  function makeBase(cache, data, store) {
    return {
      cache, data, store,
      nb: null, // set by draw(): the current screen-space neighbourhood
      sel: () => store.get().selection,
      /* A point is pickable only when no search/filter is active or when it
       * survives that filter: you can never open a recipe the query excluded. */
      matchActive: i => { const m = store.get().matches; return !m || !!m[i]; },
      /* The selected marker (a book archetype star or a class-mean diamond),
       * or null. Markers are not recipes: selecting one clears the recipe
       * selection and highlights a family instead of drawing a neighbourhood. */
      focus: () => store.get().focus || null,
      /* The family a marker highlights: a class-mean marker is its own class,
       * an archetype star uses the hand-picked ARCHETYPE_FAMILY map. */
      focusClass: function () {
        const f = store.get().focus;
        if (!f) return null;
        return f.kind === "class" ? f.id : (AID.ARCHETYPE_FAMILY[f.id] || null);
      },
      /* "Selected mode": something is highlighted, so clicks may only land on
       * the highlighted points. That is a search/filter (matches), a marker
       * (its family), or a selection whose neighbourhood is drawn — the
       * clicked recipe's family and its disc/band/ball. */
      selectedMode: function () {
        const st = store.get();
        return !!st.matches || !!st.focus || (st.selection >= 0 && !!this.nb);
      },
      /* Whether point i is one of the highlighted points (mirrors vis()). */
      isHighlighted: function (i) {
        const st = store.get();
        const m = st.matches;
        if (m && !m[i]) return false;
        const fc = this.focusClass();
        if (fc) return data.recipes.cls[i] === fc;
        const nb = this.nb;
        if (!nb) return true;
        const sel = st.selection, cls = data.recipes.cls;
        return (sel >= 0 && cls[i] === cls[sel]) || !!nb.mask[i];
      },
      /* Markers drawn by the current view, in screen space (set by draw()).
       * Returns the nearest one within its hit radius, or null. A `tall`
       * marker (the 1-D archetype tick) ignores y except for a vertical band. */
      markerAt: function (mx, my) {
        let best = null, bd = Infinity;
        for (const mk of this._markers || []) {
          if (mk.tall) {
            if (my < mk.y0 || my > mk.y1) continue;
          }
          const dx = mx - mk.x, dy = mk.tall ? 0 : my - mk.y;
          const d = Math.hypot(dx, dy);
          if (d <= mk.r && d < bd) { bd = d; best = mk; }
        }
        return best;
      },
      /* Ring the selected marker so it reads as chosen over the dots. */
      drawFocusMarks: function (ctx) {
        const f = this.focus();
        if (!f) return;
        for (const mk of this._markers || []) {
          if (mk.kind !== f.kind || mk.id !== f.id) continue;
          const r = mk.kind === "archetype" ? 13 : 11;
          ctx.save();
          ctx.strokeStyle = "#262626";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(mk.x, mk.y, r, 0, 6.2832);
          ctx.stroke();
          ctx.strokeStyle = "#fff";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(mk.x, mk.y, r + 2, 0, 6.2832);
          ctx.stroke();
          ctx.restore();
        }
      },
      /* archetype frame coords for this partition */
      archBary: AID.bary(data.archetypes.map(a => a.P), cache.groups),
    };
  }

  function star(g, x, y, r) {
    g.beginPath();
    for (let i = 0; i < 10; i++) {
      const a = -Math.PI / 2 + i * Math.PI / 5;
      const rr = i % 2 === 0 ? r : r * 0.45;
      const px = x + rr * Math.cos(a), py = y + rr * Math.sin(a);
      if (i === 0) g.moveTo(px, py); else g.lineTo(px, py);
    }
    g.closePath();
    g.fill();
    // white casing + dark edge so the star reads over the point cloud
    g.lineWidth = 3; g.strokeStyle = "#fff"; g.stroke();
    g.lineWidth = 1.2; g.strokeStyle = "#262626"; g.stroke();
  }

  /* Vertex badge (A/B/C/D) — matches the divider-bar compartment colour. */
  function vertexBadge(ctx, x, y, i) {
    ctx.beginPath();
    ctx.arc(x, y, 11, 0, 6.2832);
    ctx.fillStyle = AID.vertexColor(i);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "700 12px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(AID.vertexName(i), x, y + 0.5);
  }

  /* Hit radius for the fused-vertex merge handle (the two overlapping badges). */
  const MERGE_R = 26;

  /* The compartment's parts, e.g. "fat + sugar". */
  function groupText(g) {
    return g.map(p => AID.PART_NAMES[p]).join(" + ");
  }

  function vertexLabel(ctx, x, y, text, align) {
    ctx.font = "600 11px system-ui, sans-serif";
    ctx.fillStyle = "#55554f";
    ctx.textAlign = align;
    ctx.textBaseline = "middle";
    ctx.fillText(text, x, y);
  }

  /* Visibility of point i. `sameFam` = the point shares the highlighted
   * family (the selected recipe's class, or a selected marker's family, both
   * of which are always highlighted). Under a selection, a point is active if
   * it is same-family or inside the disc; the rest of a search/filter context
   * is whispered. A marker highlights only its family (no disc). A search and
   * a selection both constrain, so they intersect. */
  function vis(m, nb, i, sameFam, focusOn) {
    if (!m && !nb && !focusOn) return { active: true, context: false };
    return {
      active: (!m || !!m[i]) && (focusOn ? sameFam : (!nb || sameFam || !!nb.mask[i])),
      context: true,
    };
  }

  /* The selection disc: a *fixed data-space* radius (see geo AID.NEIGHBOURHOOD_R)
   * drawn at the current view scale, so zooming never changes who is inside.
   * Everything the mask flags, plus the selected recipe's family, is
   * highlighted. The radius shrinks with the on-screen scale of the frame. */
  function drawDisc(ctx, x0, y0, rPx) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(x0, y0, rPx, 0, 6.2832);
    ctx.fillStyle = "rgba(78, 121, 167, 0.10)";
    ctx.fill();
    // white casing, then a dashed dark ring, so the edge reads over the dots
    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = 5;
    ctx.stroke();
    ctx.setLineDash([7, 5]);
    ctx.strokeStyle = "rgba(30, 30, 30, 0.9)";
    ctx.lineWidth = 2.2;
    ctx.stroke();
    ctx.restore();
  }

  /* The 1D analogue of the disc: an interval on the axis, drawn as a band that
   * spans every family row, so it covers all types at once. */
  function drawBand(ctx, x0, x1, yTop, yBot) {
    const left = Math.min(x0, x1), right = Math.max(x0, x1);
    ctx.save();
    ctx.fillStyle = "rgba(78, 121, 167, 0.10)";
    ctx.fillRect(left, yTop, right - left, yBot - yTop);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = 5;
    ctx.setLineDash([7, 5]);
    ctx.beginPath();
    ctx.moveTo(left, yTop); ctx.lineTo(left, yBot);
    ctx.moveTo(right, yTop); ctx.lineTo(right, yBot);
    ctx.stroke();
    ctx.strokeStyle = "rgba(30, 30, 30, 0.9)";
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.moveTo(left, yTop); ctx.lineTo(left, yBot);
    ctx.moveTo(right, yTop); ctx.lineTo(right, yBot);
    ctx.stroke();
    ctx.restore();
  }

  /* Data-space neighbourhood: every recipe within `r` of the selection in the
   * partition's regular-simplex frame. For a unit-edge regular simplex the
   * squared distance between two points is |Δb|²/2, independent of k — so one
   * formula serves the axis interval (k=2), the triangle (k=3) and the tetra
   * (k=4), and the result is invariant to zoom, rotation and panning. */
  function frameNeighbours(data, n, sel, r, bary, k) {
    if (sel < 0) return null;
    const off = sel * k, r2 = 2 * r * r, cls = data.recipes.cls;
    const mask = new Uint8Array(n), counts = {};
    let count = 0;
    for (let i = 0; i < n; i++) {
      const o = i * k;
      let d2 = 0;
      for (let j = 0; j < k; j++) { const e = bary[o + j] - bary[off + j]; d2 += e * e; }
      if (d2 <= r2) {
        mask[i] = 1;
        count++;
        counts[cls[i]] = (counts[cls[i]] || 0) + 1;
      }
    }
    return { mask, count, counts, r, sel, k };
  }

  /* ── ratio-equation locus ──────────────────────────────────────────────
   * A ratio equation ("flour : fat = 2 : 1") is a linear slice of the
   * simplex. geo.ratioLocusVertices gives its corner points; projecting them
   * and taking the convex hull draws the set as a translucent region — a
   * line, a plane or a point, depending on the view. It never filters. */
  const LOCUS_FILL = "rgba(176, 122, 161, 0.14)";
  const LOCUS_EDGE = "rgba(150, 92, 138, 0.95)";

  /* A ratio can pin a single point (more operands than the simplex has room
   * for, or a slice that meets it at one vertex). A degenerate hull would
   * draw nothing, so mark the point with a target ring that reads over dots. */
  function drawLocusPoint(ctx, x, y) {
    ctx.beginPath();
    ctx.arc(x, y, 8.5, 0, 6.2832);
    ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
    ctx.fill();
    ctx.lineWidth = 2.4;
    ctx.strokeStyle = LOCUS_EDGE;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, 6.2832);
    ctx.fillStyle = LOCUS_EDGE;
    ctx.fill();
  }

  /* Draw the non-degenerate loci (regions/lines) in the background; return the
   * screen positions of point-sized loci so the painter can mark them ON TOP of
   * the cloud (a single point under 28k translucent dots would be invisible). */
  function drawLocus(ctx, eqs, toScreen) {
    const points = [];
    if (!eqs || !eqs.length) return points;
    for (const eq of eqs) {
      const verts = AID.ratioLocusVertices(eq.ops);
      if (verts.length < 1) continue;
      const pts = verts.map(toScreen);
      // screen spread: a locus that collapses to roughly a pixel is a point
      let minx = Infinity, maxx = -Infinity, miny = Infinity, maxy = -Infinity;
      for (const [x, y] of pts) {
        if (x < minx) minx = x; if (x > maxx) maxx = x;
        if (y < miny) miny = y; if (y > maxy) maxy = y;
      }
      const hull = AID.hull2(pts);
      if (Math.max(maxx - minx, maxy - miny) < 8 || hull.length < 2) {
        points.push([(minx + maxx) / 2, (miny + maxy) / 2]);
        continue;
      }
      ctx.save();
      ctx.beginPath();
      if (hull.length === 2) {
        ctx.moveTo(hull[0][0], hull[0][1]);
        ctx.lineTo(hull[1][0], hull[1][1]);
      } else {
        hull.forEach((pt, i) => (i ? ctx.lineTo(pt[0], pt[1]) : ctx.moveTo(pt[0], pt[1])));
        ctx.closePath();
        ctx.fillStyle = LOCUS_FILL;
        ctx.fill();
      }
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = LOCUS_EDGE;
      ctx.lineWidth = 1.6;
      ctx.stroke();
      ctx.restore();
    }
    return points;
  }

  /* Point-sized loci, drawn last so they sit above the cloud. */
  function drawLocusMarks(ctx, points) {
    if (!points || !points.length) return;
    for (const [x, y] of points) drawLocusPoint(ctx, x, y);
  }

  /* 1D locus: the slice projects to an interval on the axis, drawn as a band
   * spanning every family row. A point-sized slice has no width, so it is
   * returned for the caller to mark on top (see drawEqMark). */
  function drawEqBand(ctx, x0, x1, yTop, yBot) {
    if (!isFinite(x0) || !isFinite(x1)) return null;
    const left = Math.min(x0, x1), right = Math.max(x0, x1);
    if (right - left < 6) return (left + right) / 2;
    ctx.save();
    ctx.fillStyle = LOCUS_FILL;
    ctx.fillRect(left, yTop, right - left, yBot - yTop);
    ctx.setLineDash([6, 4]);
    ctx.strokeStyle = LOCUS_EDGE;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(left, yTop); ctx.lineTo(left, yBot);
    ctx.moveTo(right, yTop); ctx.lineTo(right, yBot);
    ctx.stroke();
    ctx.restore();
    return null;
  }

  /* Marker for a point-sized 1D locus, drawn above the rows. */
  function drawEqMark(ctx, x, yTop, yBot) {
    ctx.save();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = 5;
    ctx.beginPath(); ctx.moveTo(x, yTop); ctx.lineTo(x, yBot); ctx.stroke();
    ctx.strokeStyle = LOCUS_EDGE;
    ctx.lineWidth = 2.6;
    ctx.beginPath(); ctx.moveTo(x, yTop); ctx.lineTo(x, yBot); ctx.stroke();
    ctx.restore();
  }

  /* Dotted link from the selection to a marker (nearest centroid / archetype). */
  function dottedLink(ctx, x1, y1, x2, y2) {
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    // white casing under the dashes so the line stays legible over the dots
    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = 4;
    ctx.stroke();
    ctx.setLineDash([6, 5]);
    ctx.strokeStyle = "rgba(30, 30, 30, 0.95)";
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.restore();
  }

  function diamond(ctx, x, y, r, fill) {
    ctx.beginPath();
    ctx.moveTo(x, y - r); ctx.lineTo(x + r, y);
    ctx.lineTo(x, y + r); ctx.lineTo(x - r, y);
    ctx.closePath();
    ctx.fillStyle = fill; ctx.fill();
    ctx.lineWidth = 3; ctx.strokeStyle = "#fff"; ctx.stroke();
    ctx.lineWidth = 1.4; ctx.strokeStyle = "#262626"; ctx.stroke();
  }

  /* Blend two #rrggbb colours (the fused compartments' colours). */
  function mixHex(a, b, t) {
    const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
    const ch = (v, s) => (v >> s) & 255;
    const m = s => Math.round(ch(pa, s) * (1 - t) + ch(pb, s) * t);
    return "rgb(" + m(16) + "," + m(8) + "," + m(0) + ")";
  }

  /* ── 2D: triangle ───────────────────────────────────────────────────── */

  AID.view2 = function (cache, data, store) {
    const base = makeBase(cache, data, store);
    const n = data.meta.n;
    const groups = cache.groups;
    const frame = cache.frame; // engine-owned (animates during morphs)

    // uniform grid over frame space for hit-testing
    const CELL = 0.02, grid = new Map();
    const key = (x, y) => (Math.floor(x / CELL) + 2000) * 4000 + Math.floor(y / CELL);
    for (let i = 0; i < n; i++) {
      const k = key(frame[i * 2], frame[i * 2 + 1]);
      const arr = grid.get(k);
      if (arr) arr.push(i); else grid.set(k, [i]);
    }

    const p = Object.assign(base, {
      s: 1, tx: 0, ty: 0,
      sx(x) { return x * this.s + this.tx; },
      sy(y) { return H_ - (y * this.s + this.ty); },
    });
    let W_ = 0, H_ = 0;

    p.reset = function (W, H) {
      W_ = W; H_ = H;
      // same framing as view3, so the 2D triangle is exactly the 3D base face
      this.s = Math.min(W - 112, H - 112) / (2 * AID.TET_RADIUS);
      this.tx = W / 2 - this.s * AID.TET_CENTROID[0];
      this.ty = H / 2 - this.s * AID.TET_CENTROID[1];
    };

    p.draw = function (ctx, W, H) {
      W_ = W; H_ = H;
      // frame
      ctx.strokeStyle = "#c9c9c0";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      for (let i = 0; i < 3; i++) {
        const a = AID.TRI2[i], b = AID.TRI2[(i + 1) % 3];
        ctx.moveTo(this.sx(a[0]), this.sy(a[1]));
        ctx.lineTo(this.sx(b[0]), this.sy(b[1]));
      }
      ctx.stroke();

      // ratio-equation locus (background guide), projected like the points
      const eqsV = this.store.get().ratioEqs;
      let locusPts = [];
      if (eqsV && eqsV.length) {
        const self = this;
        locusPts = drawLocus(ctx, eqsV, raw => {
          const bb = AID.bary([raw], groups);
          const o = [0, 0];
          AID.project2(bb, o);
          return [self.sx(o[0]), self.sy(o[1])];
        });
      }

      const sel = this.sel();
      const focusOn = !!this.focusClass();
      const sameBase = focusOn ? this.focusClass()
        : (sel >= 0 ? this.data.recipes.cls[sel] : null);
      const nb = (!focusOn && this.store.get().showNeighbourhood && sel >= 0)
        ? frameNeighbours(this.data, n, sel, AID.NEIGHBOURHOOD_R,
          cache.bary, groups.length)
        : null;
      this.nb = nb;

      // points: matches/neighbours pop, the rest whisper (uniform when idle)
      const m = this.store.get().matches;
      const fade = this.cache.fade == null ? 1 : this.cache.fade;
      const clsArr = this.data.recipes.cls;
      for (let i = 0; i < n; i++) {
        if (i === sel) continue; // the selected dot is drawn on top, last
        const sameFam = sameBase !== null && clsArr[i] === sameBase;
        const v = vis(m, nb, i, sameFam, focusOn);
        // a dimmed dot uses the pale colour so a dense pile stays subdued
        ctx.fillStyle = (v.context && !v.active)
          ? this.cache.dimColors[i] : this.cache.colors[i];
        ctx.globalAlpha = (v.context ? (v.active ? A_ACTIVE : A_DIM) : A_IDLE) * fade;
        ctx.beginPath();
        ctx.arc(this.sx(frame[i * 2]), this.sy(frame[i * 2 + 1]),
          dotRadius(v), 0, 6.2832);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      if (nb) drawDisc(ctx, this.sx(frame[sel * 2]), this.sy(frame[sel * 2 + 1]),
        AID.NEIGHBOURHOOD_R * this.s);

      // markers: class centres (geometric mean) and book archetypes. Positions
      // are kept in frame space and projected to screen for drawing/picking.
      const cmeans = AID.classMeanMap(this.data.recipes.P, clsArr);
      const cents = [], atmp = [0, 0], archPos = {};
      for (const c in cmeans) {
        AID.project2(AID.bary([cmeans[c]], groups), atmp);
        cents.push([c, atmp[0], atmp[1]]);
      }
      for (let a = 0; a < this.archBary.length / 3; a++) {
        AID.project2(this.archBary.subarray(a * 3, a * 3 + 3), atmp);
        archPos[this.data.archetypes[a].name] = [atmp[0], atmp[1]];
      }
      this._markers = [];
      for (const [c, x, y] of cents) {
        this._markers.push({ kind: "class", id: c, x: this.sx(x), y: this.sy(y), r: 12 });
      }
      for (const nm in archPos) {
        this._markers.push({ kind: "archetype", id: nm,
          x: this.sx(archPos[nm][0]), y: this.sy(archPos[nm][1]), r: 14 });
      }

      // dotted lines to the nearest centroid and nearest book archetype
      if (sel >= 0 && nb) {
        const rp = this.data.recipes.P[sel];
        const nc = AID.nearestCentroid(rp, this.data.recipes.P, clsArr);
        const na = AID.aitchisonNearest(rp, this.data.archetypes);
        const x1 = this.sx(frame[sel * 2]), y1 = this.sy(frame[sel * 2 + 1]);
        for (const [c, x, y] of cents) {
          if (c === nc.name) dottedLink(ctx, x1, y1, this.sx(x), this.sy(y));
        }
        if (archPos[na.name]) {
          dottedLink(ctx, x1, y1, this.sx(archPos[na.name][0]), this.sy(archPos[na.name][1]));
        }
      }

      // markers over everything: class centres, then book archetypes
      const focus = this.focus();
      for (const [c, x, y] of cents) diamond(ctx, this.sx(x), this.sy(y), 5.5, AID.colorOf(c));
      ctx.fillStyle = "#3a3a35";
      for (let a = 0; a < this.archBary.length / 3; a++) {
        const ap = archPos[this.data.archetypes[a].name];
        star(ctx, this.sx(ap[0]), this.sy(ap[1]), 8);
        ctx.font = "600 11px system-ui, sans-serif";
        ctx.fillText(this.data.archetypes[a].name,
          this.sx(ap[0]), this.sy(ap[1]) - 12);
      }
      this.drawFocusMarks(ctx);

      // the selected dot, always drawn last at near-full strength so it is
      // never hidden by the cloud it sits in
      if (sel >= 0) {
        ctx.fillStyle = this.cache.colors[sel];
        ctx.globalAlpha = A_CHOSEN * fade;
        ctx.beginPath();
        ctx.arc(this.sx(frame[sel * 2]), this.sy(frame[sel * 2 + 1]),
          PT_R + 1.6, 0, 6.2832);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
      if (sel >= 0) {
        ctx.strokeStyle = "#262626";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(this.sx(frame[sel * 2]), this.sy(frame[sel * 2 + 1]), SEL_R, 0, 6.2832);
        ctx.stroke();
      }
      if (this.hover >= 0 && this.hover !== sel) {
        ctx.strokeStyle = "#262626";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(this.sx(frame[this.hover * 2]), this.sy(frame[this.hover * 2 + 1]),
          HOVER_R, 0, 6.2832);
        ctx.stroke();
      }

      // point-sized ratio loci, above the cloud
      drawLocusMarks(ctx, locusPts);

      // corner badges + labels (match the divider-bar compartments)
      const cen = [this.sx(0.5), this.sy(0.8660254 / 3)];
      AID.TRI2.forEach((v, i) => {
        const vx = this.sx(v[0]), vy = this.sy(v[1]);
        vertexBadge(ctx, vx, vy, i);
        const dx = vx - cen[0], dy = vy - cen[1], l = Math.hypot(dx, dy) || 1;
        vertexLabel(ctx, vx + dx / l * 20, vy + dy / l * 20,
          groupText(groups[i]), dx > 8 ? "left" : dx < -8 ? "right" : "center");
      });
    };

    p.hit = function (mx, my) {
      const fx = (mx - this.tx) / this.s;
      const fy = (H_ - my - this.ty) / this.s;
      const r = HOVER_R / this.s;
      let best = -1, bd = r * r;
      const x0 = Math.floor((fx - r) / CELL), x1 = Math.floor((fx + r) / CELL);
      const y0 = Math.floor((fy - r) / CELL), y1 = Math.floor((fy + r) / CELL);
      for (let cx = x0; cx <= x1; cx++) for (let cy = y0; cy <= y1; cy++) {
        const arr = grid.get((cx + 2000) * 4000 + cy);
        if (!arr) continue;
        for (const i of arr) {
          if (!this.matchActive(i)) continue;
          const dx = frame[i * 2] - fx, dy = frame[i * 2 + 1] - fy;
          const d = dx * dx + dy * dy;
          if (d < bd) { bd = d; best = i; }
        }
      }
      return best;
    };

    /* Selection click. In selected mode only highlighted points are pickable:
     * a direct hit counts only if it is highlighted; otherwise a click within
     * SNAP_R snaps to the nearest highlighted point, and anything farther is
     * empty and deselects. With nothing highlighted this is exactly hit(). */
    p.pick = function (mx, my) {
      const idx = this.hit(mx, my);
      if (!this.selectedMode()) return idx;
      if (idx >= 0 && this.isHighlighted(idx)) return idx;
      const fx = (mx - this.tx) / this.s, fy = (H_ - my - this.ty) / this.s;
      const r = SNAP_R / this.s, r2 = r * r;
      let best = -1, bd = r2;
      for (let i = 0; i < n; i++) {
        if (!this.isHighlighted(i)) continue;
        const dx = frame[i * 2] - fx, dy = frame[i * 2 + 1] - fy;
        const d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = i; }
      }
      return best;
    };

    p.zoom = function (mx, my, f) {
      const fx = (mx - this.tx) / this.s, fy = (H_ - my - this.ty) / this.s;
      this.s *= f;
      this.tx = mx - fx * this.s;
      this.ty = (H_ - my) - fy * this.s;
    };
    p.wheel = function (mx, my, dy) { this.zoom(mx, my, dy < 0 ? 1.15 : 1 / 1.15); };

    p.drag = function (mx, my, dx, dy) {
      // frame y is up, screen y is down: negate dy so content follows the cursor
      this.tx += dx; this.ty -= dy;
    };
    /* Two-finger drag (touch): same pan as a one-finger drag, for consistency. */
    p.pan = function (dx, dy) { this.tx += dx; this.ty -= dy; };

    p.dblclick = function () { this.reset(W_, H_); };
    p.value = idx => AID.readout(data.recipes.P[idx]);
    return p;
  };

  /* ── 1D: violin rows ────────────────────────────────────────────────── */

  AID.view1 = function (cache, data, store) {
    const base = makeBase(cache, data, store);
    const groups = cache.groups;
    const k = groups.length;
    const n = cache.bary.length / k;
    const values = new Float32Array(n);
    for (let i = 0; i < n; i++) values[i] = cache.bary[i * k] * 100;

    // class rows sorted by KDE mode (where the class bulges)
    const classes = data.meta.classes.slice()
      .filter(c => data.recipes.cls.indexOf(c) >= 0);
    const rowsByClass = {};
    for (const c of classes) rowsByClass[c] = [];
    for (let i = 0; i < n; i++) rowsByClass[data.recipes.cls[i]].push(i);
    const order = classes.slice().sort((a, b) => {
      const av = AID.kdeMode(rowsByClass[a].map(i => values[i]), cache.key + a);
      const bv = AID.kdeMode(rowsByClass[b].map(i => values[i]), cache.key + b);
      return av - bv;
    });

    // per-row points sorted by value for hit-testing
    const rowPts = order.map(c =>
      rowsByClass[c].slice().sort((a, b) => values[a] - values[b]));

    let X0 = 0, X1 = 100; // zoomable value domain
    const TOP = 64;        // corner pills + rest row above the violin rows
    const p = Object.assign(base, {});
    let W_ = 0, H_ = 0, plotL = 0, plotR = 0;

    const sx = v => plotL + (v - X0) / (X1 - X0) * (plotR - plotL);

    p.reset = function (W, H) {
      W_ = W; H_ = H;
      // narrow screens give the family labels less room so the axis stays usable
      plotL = W < 520 ? 104 : 150; plotR = W - 24;
    };

    p.draw = function (ctx, W, H) {
      W_ = W; H_ = H;
      const nR = order.length;
      const rowH = (H - TOP - 44) / nR;

      // axis
      ctx.strokeStyle = "#c9c9c0";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(plotL, H - 30); ctx.lineTo(plotR, H - 30);
      ctx.stroke();
      ctx.fillStyle = "#8a8a84";
      ctx.font = "11px system-ui, sans-serif";
      ctx.textAlign = "center";
      for (let t = 0; t <= 100; t += 25) {
        if (t < X0 || t > X1) continue;
        const x = sx(t);
        ctx.beginPath(); ctx.moveTo(x, H - 30); ctx.lineTo(x, H - 25); ctx.stroke();
        ctx.fillText(t + "%", x, H - 12);
      }

      // ratio-equation locus (background band) spanning every family row
      const eqsV = this.store.get().ratioEqs;
      const eqMarks = [];
      if (eqsV && eqsV.length) {
        for (const eq of eqsV) {
          const verts = AID.ratioLocusVertices(eq.ops);
          if (verts.length < 1) continue;
          let lo = Infinity, hi = -Infinity;
          for (const raw of verts) {
            const v = AID.bary([raw], groups)[0] * 100;
            if (v < lo) lo = v;
            if (v > hi) hi = v;
          }
          if (hi < X0 || lo > X1) continue; // slice is off-screen
          const mark = drawEqBand(ctx, sx(Math.max(X0, lo)), sx(Math.min(X1, hi)), TOP, H - 30);
          if (mark != null) eqMarks.push(mark);
        }
      }

      if (this.pathKey !== X0 + "|" + X1) {
        this.pathKey = X0 + "|" + X1;
        this.paths = order.map((c, r) => {
          const pts = rowPts[r];
          const vv = pts.map(i => values[i]);
          let m = 0; for (const v of vv) m += v; m /= vv.length;
          let va = 0; for (const v of vv) { const d = v - m; va += d * d; }
          const sd = Math.sqrt(va / vv.length);
          const h = sd > 0 ? 1.06 * sd * Math.pow(vv.length, -0.2) : 1;
          const G = 128, lo = Math.max(X0, m - 3 * sd), hi = Math.min(X1, m + 3 * sd);
          const path = [];
          let maxD = 0;
          for (let g = 0; g < G; g++) {
            const x = lo + (hi - lo) * g / (G - 1);
            let d = 0;
            for (const v of vv) { const u = (x - v) / h; d += Math.exp(-0.5 * u * u); }
            path.push([x, d]);
            if (d > maxD) maxD = d;
          }
          // normalize each silhouette to its own peak: rows no longer overflow
          // their band and overlap the neighbours.
          const inv = maxD > 0 ? 1 / maxD : 0;
          for (const q of path) q[1] *= inv;
          return path;
        });
      }

      // screen position of every point, for the fixed-radius selection disc
      const xp = new Float32Array(n), yp = new Float32Array(n);
      order.forEach((c, r) => {
        const yMid = TOP + r * rowH + rowH / 2;
        const half = Math.min(rowH * 0.42, 26);
        for (const i of rowPts[r]) {
          xp[i] = sx(Math.max(X0, Math.min(X1, values[i])));
          yp[i] = yMid + jitter(i) * half * 0.5;
        }
      });
      this._xp = xp; this._yp = yp; // kept for pick() below
      const sel = this.sel();
      const focusOn = !!this.focusClass();
      const sameBase = focusOn ? this.focusClass()
        : (sel >= 0 ? this.data.recipes.cls[sel] : null);
      const nb = (!focusOn && this.store.get().showNeighbourhood && sel >= 0)
        ? frameNeighbours(this.data, n, sel, AID.NEIGHBOURHOOD_R, cache.bary, k)
        : null;
      this.nb = nb;

      // class centres (geometric mean) on this axis, and archetype ticks —
      // kept in screen space so they can be picked like the markers in 2D/3D
      const cmeans = AID.classMeanMap(this.data.recipes.P, this.data.recipes.cls);
      const meanVal = {};
      for (const c in cmeans) meanVal[c] = AID.bary([cmeans[c]], groups)[0] * 100;
      this._markers = [];
      for (const c in meanVal) {
        const r = order.indexOf(c);
        if (r < 0) continue;
        this._markers.push({ kind: "class", id: c,
          x: sx(meanVal[c]), y: TOP + r * rowH + rowH / 2, r: 12 });
      }
      for (let a = 0; a < this.archBary.length / k; a++) {
        const v = this.archBary[a * k] * 100;
        if (v < X0 || v > X1) continue;
        this._markers.push({ kind: "archetype", id: this.data.archetypes[a].name,
          x: sx(v), y: (TOP + H_ - 30) / 2, tall: true, y0: TOP, y1: H_ - 30, r: 10 });
      }

      order.forEach((c, r) => {
        const yTop = TOP + r * rowH, yMid = yTop + rowH / 2;
        const pts = rowPts[r];
        const half = Math.min(rowH * 0.42, 26);

        // KDE silhouette (path cached per zoom domain; [value, density] pairs)
        ctx.globalAlpha = 0.35;
        ctx.fillStyle = AID.colorOf(c);
        ctx.beginPath();
        const path = this.paths[r];
        let mode = path[0][0], modeD = path[0][1];
        for (const q of path) if (q[1] > modeD) { modeD = q[1]; mode = q[0]; }
        ctx.moveTo(sx(path[0][0]), yMid);
        for (const pt of path) ctx.lineTo(sx(pt[0]), yMid - pt[1] * half * 1.5);
        for (let g = path.length - 1; g >= 0; g--)
          ctx.lineTo(sx(path[g][0]), 2 * yMid - (yMid - path[g][1] * half * 1.5));
        ctx.closePath();
        ctx.fill();
        ctx.globalAlpha = 1;

        // mode marker
        ctx.strokeStyle = AID.colorOf(c);
        ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(sx(mode), yTop + 4); ctx.lineTo(sx(mode), yTop + rowH - 4); ctx.stroke();
        ctx.setLineDash([]);

        // points: matches/neighbours pop, the rest whisper
        const m = this.store.get().matches;
        const fade = this.cache.fade == null ? 1 : this.cache.fade;
        const clsArr = this.data.recipes.cls;
        for (const i of pts) {
          if (i === sel) continue; // drawn on top, after every row
          const sameFam = sameBase !== null && clsArr[i] === sameBase;
          const v = vis(m, nb, i, sameFam, focusOn);
          // a dimmed dot uses the pale colour so a dense pile stays subdued
          ctx.fillStyle = (v.context && !v.active)
            ? AID.dimColorOf(c) : AID.colorOf(c);
          ctx.globalAlpha = (v.context ? (v.active ? A_ACTIVE : A_DIM) : A_IDLE) * fade;
          ctx.beginPath();
          ctx.arc(xp[i], yp[i], v.active ? 1.8 : 1.3, 0, 6.2832);
          ctx.fill();
        }
        ctx.globalAlpha = 1;

        // class centre (geometric mean) on this row
        if (pts.length) diamond(ctx, sx(meanVal[c]), yMid, 5.5, AID.colorOf(c));

        // archetype ticks
        ctx.strokeStyle = "#3a3a35";
        for (let a = 0; a < this.archBary.length / k; a++) {
          const v = this.archBary[a * k] * 100;
          if (v < X0 || v > X1) continue;
          ctx.beginPath();
          ctx.moveTo(sx(v), yTop + rowH * 0.25);
          ctx.lineTo(sx(v), yTop + rowH * 0.75);
          ctx.stroke();
        }

        // row label
        ctx.fillStyle = AID.colorOf(c);
        ctx.textAlign = "right";
        ctx.font = "600 12px system-ui, sans-serif";
        ctx.fillText(c, plotL - 12, yMid + 4);
      });
      this.drawFocusMarks(ctx);

      if (nb) {
        const rv = AID.NEIGHBOURHOOD_R * 100; // share units -> percent
        drawBand(ctx, sx(values[sel] - rv), sx(values[sel] + rv), TOP - 6, H - 30);
      }

      // the selected dot, drawn last so it is never hidden by its row
      if (sel >= 0) {
        ctx.fillStyle = AID.colorOf(this.data.recipes.cls[sel]);
        ctx.globalAlpha = (this.cache.fade == null ? 1 : this.cache.fade) * A_CHOSEN;
        ctx.beginPath(); ctx.arc(xp[sel], yp[sel], 2.8, 0, 6.2832); ctx.fill();
        ctx.globalAlpha = 1;
      }

      const clampX = v => sx(Math.max(X0, Math.min(X1, v)));
      if (sel >= 0) {
        const r = order.indexOf(this.data.recipes.cls[sel]);
        if (r >= 0) {
          const yMid = TOP + r * rowH + rowH / 2;
          const half = Math.min(rowH * 0.42, 26);
          ctx.strokeStyle = "#262626"; ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(clampX(values[sel]), yMid + jitter(sel) * half * 0.5, SEL_R - 1, 0, 6.2832);
          ctx.stroke();
        }
      }
      if (this.hover >= 0 && this.hover !== sel) {
        const r = order.indexOf(this.data.recipes.cls[this.hover]);
        if (r >= 0) {
          const yMid = TOP + r * rowH + rowH / 2;
          const half = Math.min(rowH * 0.42, 26);
          ctx.strokeStyle = "#262626"; ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(clampX(values[this.hover]),
            yMid + jitter(this.hover) * half * 0.5, HOVER_R, 0, 6.2832);
          ctx.stroke();
        }
      }

      // point-sized ratio loci, above the rows
      for (const x of eqMarks) drawEqMark(ctx, x, TOP, H - 30);

      // corner badges: group 0 at the right (100%), its complement left
      const anchors = [[plotR - 6, 22]];
      if (groups.length > 1) anchors[1] = [plotL + 6, 22];
      anchors.forEach((a, i) => {
        vertexBadge(ctx, a[0], a[1], i);
        vertexLabel(ctx, a[0], a[1] + 20, groupText(groups[i]), "center");
      });
    };

    p.hit = function (mx, my) {
      const nR = order.length;
      const rowH = (H_ - TOP - 44) / nR;
      const r = Math.floor((my - TOP) / rowH);
      if (r < 0 || r >= nR) return -1;
      const pts = rowPts[r];
      const mxv = X0 + (mx - plotL) / (plotR - plotL) * (X1 - X0);
      // binary search nearest by value
      let lo = 0, hi = pts.length - 1;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (values[pts[mid]] < mxv) lo = mid + 1; else hi = mid;
      }
      let best = -1, bd = Infinity;
      for (const i of [lo, Math.max(0, lo - 1)]) {
        if (!this.matchActive(pts[i])) continue;
        const d = Math.abs(values[pts[i]] - mxv);
        if (d < bd) { bd = d; best = pts[i]; }
      }
      const tol = (X1 - X0) * HOVER_R / (plotR - plotL);
      return bd <= tol ? best : -1;
    };

    /* Selection click: in selected mode only highlighted points are pickable —
     * a direct hit counts only if highlighted, else a bounded snap (see
     * view2.pick). */
    p.pick = function (mx, my) {
      const idx = this.hit(mx, my);
      if (!this.selectedMode()) return idx;
      if (idx >= 0 && this.isHighlighted(idx)) return idx;
      if (!this._xp) return -1;
      let best = -1, bd = SNAP_R * SNAP_R;
      for (let i = 0; i < n; i++) {
        if (!this.isHighlighted(i)) continue;
        const dx = this._xp[i] - mx, dy = this._yp[i] - my;
        const d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = i; }
      }
      return best;
    };

    p.zoom = function (mx, my, f) {
      const v = X0 + (mx - plotL) / (plotR - plotL) * (X1 - X0);
      X0 = v - (v - X0) * f; X1 = v + (X1 - v) * f;
      X0 = Math.max(0, X0); X1 = Math.min(100, X1);
      if (X1 - X0 < 2) { X0 = Math.max(0, v - 1); X1 = Math.min(100, v + 1); }
    };
    p.wheel = function (mx, my, dy) { this.zoom(mx, my, dy < 0 ? 0.8 : 1.25); };

    p.drag = null;
    p.dblclick = function () { X0 = 0; X1 = 100; };
    p.value = idx =>
      AID.groupLabel(groups[0]) + " " + values[idx].toFixed(1) + "%";
    return p;
  };

  /* ── 3D: tetrahedron with orbit ─────────────────────────────────────── */

  AID.view3 = function (cache, data, store) {
    const base = makeBase(cache, data, store);
    const n = data.meta.n;
    const groups = cache.groups;
    const screen = cache.frame; // engine-owned; painter reprojects on rotate
    // The orbit camera lives outside the painter so editing the partition does
    // not reset the user's perspective. Default is face-on: the base face (the
    // 2D triangle) is seen straight on, the apex projects to its centroid.
    const cam = AID.camera3 || (AID.camera3 = { yaw: 0, pitch: 0, zoom: 1 });
    let yaw = cam.yaw, pitch = cam.pitch, zoom = cam.zoom;
    let W_ = 0, H_ = 0;

    const p = Object.assign(base, {});
    p.rot = { get yaw() { return yaw; }, get pitch() { return pitch; } };
    const tmp = [0, 0, 0];
    const UNIT = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]];

    const depth = new Float32Array(n);
    let order = null, lastYaw = NaN, lastPitch = NaN;

    function projectAll() {
      if (cache.frameLocked) return; // a morph owns the frame; don't clobber
      cache.updateFrame([yaw, pitch]);
      if (order && yaw === lastYaw && pitch === lastPitch) return;
      lastYaw = yaw; lastPitch = pitch;
      for (let i = 0; i < n; i++) {
        AID.project3(cache.bary.subarray(i * 4, i * 4 + 4), yaw, pitch, tmp);
        depth[i] = tmp[2];
      }
      // Sorting 29k points every orbit frame is wasteful; while the camera is
      // moving, re-sort at most ~8/s and always once movement settles.
      const now = performance.now();
      const settled = now - (p._lastMove || 0) > 200;
      if (!order) { order = new Array(n); for (let i = 0; i < n; i++) order[i] = i; }
      if (settled || now - (p._lastSort || 0) > 120) {
        order.sort((a, b) => depth[a] - depth[b]); // far -> near: near on top
        p._lastSort = now;
      }
    }

    function fit(W, H) {
      // fixed fit to the bounding sphere: stable under rotation (no pulsing)
      const m = 56;
      const s = Math.min((W - 2 * m), (H - 2 * m)) / (2 * AID.TET_RADIUS) * zoom;
      return {
        s,
        tx: W / 2 - s * AID.TET_CENTROID[0] + (cam.panx || 0),
        ty: H / 2 - s * AID.TET_CENTROID[1] - (cam.pany || 0),
      };
    }

    let T = { s: 1, tx: 0, ty: 0 };
    p.reset = function (W, H) { W_ = W; H_ = H; T = fit(W, H); };
    const sx = x => x * T.s + T.tx, sy = y => H_ - (y * T.s + T.ty);

    p.draw = function (ctx, W, H) {
      W_ = W; H_ = H;
      projectAll();
      T = fit(W, H);

      // During a 3D->2D morph the wireframe is driven frame-by-frame: this.wire
      // holds four frame-space corners (the two merging ones converge). It is a
      // pure frame-space move, so the transition needs no camera rotation.
      const proj = this.wire
        ? this.wire.map(p => [sx(p[0]), sy(p[1])])
        : UNIT.map(u => {
            AID.project3(u, yaw, pitch, tmp);
            return [sx(tmp[0]), sy(tmp[1])];
          });

      // base triangle (front face) — always present, so 2D -> 3D morphs feel
      // like the rich vertex tearing open rather than a scene swap
      ctx.strokeStyle = "#c9c9c0"; ctx.lineWidth = 1.5;
      ctx.beginPath();
      for (let i = 0; i < 3; i++) {
        const a = proj[i], b = proj[(i + 1) % 3];
        ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
      }
      ctx.stroke();

      // apex edges (fade with the birth phase so the flat 2D view carries over)
      const apexAlpha = AID.birthE == null ? 1 : AID.birthE;
      ctx.strokeStyle = "#c9c9c0";
      ctx.globalAlpha = apexAlpha;
      ctx.beginPath();
      for (let j = 0; j < 3; j++) {
        ctx.moveTo(proj[3][0], proj[3][1]);
        ctx.lineTo(proj[j][0], proj[j][1]);
      }
      ctx.stroke();
      ctx.globalAlpha = 1;

      // ratio-equation locus (background guide), reprojected with the camera
      const eqsV = this.store.get().ratioEqs;
      let locusPts = [];
      if (eqsV && eqsV.length) {
        locusPts = drawLocus(ctx, eqsV, raw => {
          const bb = AID.bary([raw], groups);
          AID.project3(bb, yaw, pitch, tmp);
          return [sx(tmp[0]), sy(tmp[1])];
        });
      }

      const sel = this.sel();
      const clsArr = this.data.recipes.cls;
      const focusOn = !!this.focusClass();
      const sameBase = focusOn ? this.focusClass()
        : (sel >= 0 ? clsArr[sel] : null);
      const nb = (!focusOn && this.store.get().showNeighbourhood && sel >= 0)
        ? frameNeighbours(this.data, n, sel, AID.NEIGHBOURHOOD_R,
          cache.bary, groups.length)
        : null;
      this.nb = nb;

      // points in painter's order (far first, near on top)
      const m = this.store.get().matches;
      const fade = this.cache.fade == null ? 1 : this.cache.fade;
      for (let k = 0; k < n; k++) {
        const i = order ? order[k] : k;
        if (i === sel) continue; // the selected dot is drawn on top, last
        const sameFam = sameBase !== null && clsArr[i] === sameBase;
        const v = vis(m, nb, i, sameFam, focusOn);
        // a dimmed dot uses the pale colour so a dense pile stays subdued
        ctx.fillStyle = (v.context && !v.active)
          ? this.cache.dimColors[i] : this.cache.colors[i];
        // same opacity and size as the 2D view: overlaps blend, depth is not
        // encoded in the dot (only the draw order and the camera give depth)
        ctx.globalAlpha = (v.context ? (v.active ? A_ACTIVE : A_DIM) : A_IDLE) * fade;
        ctx.beginPath();
        ctx.arc(sx(screen[i * 2]), sy(screen[i * 2 + 1]),
          dotRadius(v), 0, 6.2832);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      if (nb) drawDisc(ctx, sx(screen[sel * 2]), sy(screen[sel * 2 + 1]),
        AID.NEIGHBOURHOOD_R * T.s);

      // markers: class centres (geometric mean) and book archetypes. Positions
      // are kept in projected space and mapped to screen for drawing/picking.
      const cmeans = AID.classMeanMap(this.data.recipes.P, clsArr);
      const cents = [], archPos = {};
      for (const c in cmeans) {
        AID.project3(AID.bary([cmeans[c]], groups), yaw, pitch, tmp);
        cents.push([c, tmp[0], tmp[1]]);
      }
      for (let a = 0; a < this.archBary.length / 4; a++) {
        if (this.arch) {
          archPos[this.data.archetypes[a].name] =
            [this.arch[a][0], this.arch[a][1]];
        } else {
          AID.project3(this.archBary.subarray(a * 4, a * 4 + 4), yaw, pitch, tmp);
          archPos[this.data.archetypes[a].name] = [tmp[0], tmp[1]];
        }
      }
      this._markers = [];
      for (const [c, x, y] of cents) {
        this._markers.push({ kind: "class", id: c, x: sx(x), y: sy(y), r: 12 });
      }
      for (const nm in archPos) {
        this._markers.push({ kind: "archetype", id: nm,
          x: sx(archPos[nm][0]), y: sy(archPos[nm][1]), r: 14 });
      }

      // dotted lines to the nearest centroid and nearest book archetype
      if (sel >= 0 && nb) {
        const rp = this.data.recipes.P[sel];
        const nc = AID.nearestCentroid(rp, this.data.recipes.P, clsArr);
        const na = AID.aitchisonNearest(rp, this.data.archetypes);
        const x1 = sx(screen[sel * 2]), y1 = sy(screen[sel * 2 + 1]);
        for (const [c, x, y] of cents) {
          if (c === nc.name) dottedLink(ctx, x1, y1, sx(x), sy(y));
        }
        if (archPos[na.name]) {
          dottedLink(ctx, x1, y1, sx(archPos[na.name][0]), sy(archPos[na.name][1]));
        }
      }

      // markers over everything: class centres, then book archetypes
      for (const [c, x, y] of cents) diamond(ctx, sx(x), sy(y), 5.5, AID.colorOf(c));
      ctx.fillStyle = "#3a3a35";
      for (let a = 0; a < this.archBary.length / 4; a++) {
        const ap = archPos[this.data.archetypes[a].name];
        star(ctx, sx(ap[0]), sy(ap[1]), 8);
        ctx.font = "600 11px system-ui, sans-serif";
        ctx.fillText(this.data.archetypes[a].name, sx(ap[0]), sy(ap[1]) - 12);
      }
      this.drawFocusMarks(ctx);

      // the selected dot, drawn last so it is never hidden by the cloud
      if (sel >= 0) {
        ctx.fillStyle = this.cache.colors[sel];
        ctx.globalAlpha = A_CHOSEN * fade;
        ctx.beginPath();
        ctx.arc(sx(screen[sel * 2]), sy(screen[sel * 2 + 1]),
          PT_R + 1.6, 0, 6.2832);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
      if (sel >= 0) {
        ctx.strokeStyle = "#262626"; ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(sx(screen[sel * 2]), sy(screen[sel * 2 + 1]), SEL_R, 0, 6.2832);
        ctx.stroke();
      }
      if (this.hover >= 0 && this.hover !== sel) {
        ctx.strokeStyle = "#262626"; ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(sx(screen[this.hover * 2]), sy(screen[this.hover * 2 + 1]), HOVER_R, 0, 6.2832);
        ctx.stroke();
      }

      // two corners that line up on screen can be merged. As they come
      // together they visibly fuse — two lobes pulled toward their midpoint,
      // swelling, then a single lozenge with an ∞ — and once fused the glyph is
      // the click target that collapses the pair into one 2D vertex.
      this.mergePair = null;
      if (!cache.frameLocked) {
        let best = 1e9, bi = 0, bj = 1;
        for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) {
          const dx = proj[i][0] - proj[j][0], dy = proj[i][1] - proj[j][1];
          const d = Math.hypot(dx, dy);
          if (d < best) { best = d; bi = i; bj = j; }
        }
        const FUSE = 40;
        if (best <= FUSE) {
          this.mergePair = {
            i: bi, j: bj,
            x: (proj[bi][0] + proj[bj][0]) / 2,
            y: (proj[bi][1] + proj[bj][1]) / 2,
            t: Math.max(0, 1 - best / FUSE),
          };
        }
        const mp = this.mergePair;
        if (mp) {
          const t = mp.t;
          const pulse = (1 + 0.04 * Math.sin(performance.now() / 220)) * (1 + 0.12 * t);
          const pull = 0.45 * t;
          const ax = proj[mp.i][0] + (mp.x - proj[mp.i][0]) * pull;
          const ay = proj[mp.i][1] + (mp.y - proj[mp.i][1]) * pull;
          const bx = proj[mp.j][0] + (mp.x - proj[mp.j][0]) * pull;
          const by = proj[mp.j][1] + (mp.y - proj[mp.j][1]) * pull;
          const r = (11 + 4 * t) * pulse;
          const d = Math.hypot(bx - ax, by - ay);
          const colI = AID.vertexColor(mp.i), colJ = AID.vertexColor(mp.j);
          const th = Math.atan2(by - ay, bx - ax);

          if (d >= 2 * r) {
            // still two distinct blobs, each in its own colour
            for (const [x, y, col] of [[ax, ay, colI], [bx, by, colJ]]) {
              ctx.beginPath(); ctx.arc(x, y, r, 0, 6.2832);
              ctx.fillStyle = col; ctx.fill();
              ctx.lineWidth = 2.5; ctx.strokeStyle = "#262626"; ctx.stroke();
            }
          } else {
            // union of the two discs: a single outline with no seam, so they
            // read as one fused object (the colour blends as they merge)
            const al = Math.acos(Math.min(1, d / (2 * r)));
            ctx.beginPath();
            ctx.arc(ax, ay, r, th - al, th + al, true);
            ctx.arc(bx, by, r, Math.PI - al + th, Math.PI + al + th, true);
            ctx.closePath();
            ctx.fillStyle = mixHex(colI, colJ, 0.5);
            ctx.fill();
            ctx.lineWidth = 2.5; ctx.strokeStyle = "#262626"; ctx.stroke();
          }

          // compartment letters, pinned to the outer ends of the fused shape
          ctx.fillStyle = "#fff";
          ctx.font = "700 12px system-ui, sans-serif";
          ctx.textAlign = "center"; ctx.textBaseline = "middle";
          const ex = ax - Math.cos(th) * r * 0.5, ey = ay - Math.sin(th) * r * 0.5;
          const fx = bx + Math.cos(th) * r * 0.5, fy = by + Math.sin(th) * r * 0.5;
          ctx.fillText(AID.vertexName(mp.i), ex, ey + 0.5);
          ctx.fillText(AID.vertexName(mp.j), fx, fy + 0.5);
        }
      }

      // point-sized ratio loci, above the cloud
      drawLocusMarks(ctx, locusPts);

      // corner badges + labels (the fused pair is drawn above)
      AID.project3([0.25, 0.25, 0.25, 0.25], yaw, pitch, tmp);
      const cen = [sx(tmp[0]), sy(tmp[1])];
      const pair = this.mergePair;
      proj.forEach((v, i) => {
        if (pair && (i === pair.i || i === pair.j)) return;
        // The newborn 4th corner fades with the birth phase: at phase 0 the
        // regular tetra's apex projects to the base centroid (the middle of
        // the flat 2D triangle), so an opaque badge would pop in at the
        // center instead of growing out of the corner it was split from.
        const alpha = i === 3 ? (AID.birthE == null ? 1 : AID.birthE) : 1;
        if (alpha <= 0.02) return;
        ctx.globalAlpha = alpha;
        vertexBadge(ctx, v[0], v[1], i);
        const dx = v[0] - cen[0], dy = v[1] - cen[1], l = Math.hypot(dx, dy) || 1;
        vertexLabel(ctx, v[0] + dx / l * 20, v[1] + dy / l * 20,
          groupText(groups[i]), dx > 8 ? "left" : dx < -8 ? "right" : "center");
        ctx.globalAlpha = 1;
      });
    };

    p.hit = function (mx, my) {
      const r = HOVER_R, r2 = r * r;
      let best = -1, bd = r2;
      for (let i = 0; i < n; i++) {
        if (!this.matchActive(i)) continue;
        const dx = sx(screen[i * 2]) - mx, dy = sy(screen[i * 2 + 1]) - my;
        const d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = i; }
      }
      return best;
    };

    /* Selection click: in selected mode only highlighted points are pickable —
     * a direct hit counts only if highlighted, else a bounded snap (see
     * view2.pick). */
    p.pick = function (mx, my) {
      const idx = this.hit(mx, my);
      if (!this.selectedMode()) return idx;
      if (idx >= 0 && this.isHighlighted(idx)) return idx;
      let best = -1, bd = SNAP_R * SNAP_R;
      for (let i = 0; i < n; i++) {
        if (!this.isHighlighted(i)) continue;
        const dx = sx(screen[i * 2]) - mx, dy = sy(screen[i * 2 + 1]) - my;
        const d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = i; }
      }
      return best;
    };

    /* Click target for the fused-corner merge glyph, if one is showing. */
    p.mergeHit = function (mx, my) {
      const pair = this.mergePair;
      if (!pair) return null;
      return Math.hypot(mx - pair.x, my - pair.y) <= MERGE_R ? pair : null;
    };

    p.zoom = function (mx, my, f) { zoom *= f; cam.zoom = zoom; };
    p.wheel = function (mx, my, dy) { this.zoom(mx, my, dy < 0 ? 1.15 : 1 / 1.15); };
    /* Used by the 2D->3D morph to rotate the frame while the points blend. */
    p.setCamera = function (y, pi) { yaw = y; pitch = pi; };
    p.setZoom = function (z) { zoom = z; cam.zoom = z; };
    /* Frame-space corners / archetype points the 3D->2D morph interpolates. */
    p.wireCorners = function () {
      return UNIT.map(u => {
        AID.project3(u, yaw, pitch, tmp);
        return [tmp[0], tmp[1]];
      });
    };
    p.archPoints = function () {
      const out = [];
      for (let a = 0; a < this.archBary.length / 4; a++) {
        AID.project3(this.archBary.subarray(a * 4, a * 4 + 4), yaw, pitch, tmp);
        out.push([tmp[0], tmp[1]]);
      }
      return out;
    };
    p.drag = function (mx, my, dx, dy, ctrl) {
      if (ctrl) {
        // ctrl+drag pans the scene (screen pixels); plain drag orbits
        cam.panx = (cam.panx || 0) + dx;
        cam.pany = (cam.pany || 0) + dy;
        return;
      }      yaw += dx * 0.01;
      pitch = Math.max(-1.3, Math.min(1.3, pitch + dy * 0.01));
      cam.yaw = yaw; cam.pitch = pitch;
      p._lastMove = performance.now();
    };
    /* Two-finger drag (touch): pan without the ctrl modifier a keyboard offers. */
    p.pan = function (dx, dy) {
      cam.panx = (cam.panx || 0) + dx;
      cam.pany = (cam.pany || 0) + dy;
    };
    p.dblclick = function () {
      yaw = 0; pitch = 0; zoom = 1;
      cam.yaw = yaw; cam.pitch = pitch; cam.zoom = zoom;
      cam.panx = 0; cam.pany = 0;
    };
    p.value = idx => AID.readout(p.data.recipes.P[idx]);
    return p;
  };
})();