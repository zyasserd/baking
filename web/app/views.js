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
      sel: () => store.get().selection,
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
  }

  /* Numbered vertex badge — matches the divider-bar compartment colour. */
  function vertexBadge(ctx, x, y, i) {
    ctx.beginPath();
    ctx.arc(x, y, 11, 0, 6.2832);
    ctx.fillStyle = AID.vertexColor(i);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.font = "700 12px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(i + 1), x, y + 0.5);
  }

  /* Hit radius for the fused-vertex merge handle (the two overlapping badges). */
  const MERGE_R = 22;

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

      // archetype stars
      ctx.fillStyle = "#3a3a35";
      const atmp = [0, 0];
      for (let a = 0; a < this.archBary.length / 3; a++) {
        AID.project2(this.archBary.subarray(a * 3, a * 3 + 3), atmp);
        star(ctx, this.sx(atmp[0]), this.sy(atmp[1]), 7);
        ctx.font = "600 11px system-ui, sans-serif";
        ctx.fillText(this.data.archetypes[a].name, this.sx(atmp[0]),
          this.sy(atmp[1]) - 11);
      }

      // points: matches pop, the rest whisper (uniform when no search)
      const m = this.store.get().matches;
      const fade = this.cache.fade == null ? 1 : this.cache.fade;
      for (let i = 0; i < n; i++) {
        const on = !m || m[i];
        ctx.fillStyle = this.cache.colors[i];
        ctx.globalAlpha = (m ? (on ? 0.9 : 0.045) : 0.25) * fade;
        ctx.beginPath();
        ctx.arc(this.sx(frame[i * 2]), this.sy(frame[i * 2 + 1]),
          on ? PT_R + (m ? 0.4 : 0) : PT_R - 0.5, 0, 6.2832);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      const sel = this.sel();
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

      // numbered corner badges + labels (match the divider-bar compartments)
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
          const dx = frame[i * 2] - fx, dy = frame[i * 2 + 1] - fy;
          const d = dx * dx + dy * dy;
          if (d < bd) { bd = d; best = i; }
        }
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
      plotL = 150; plotR = W - 24;
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
          for (let g = 0; g < G; g++) {
            const x = lo + (hi - lo) * g / (G - 1);
            let d = 0;
            for (const v of vv) { const u = (x - v) / h; d += Math.exp(-0.5 * u * u); }
            path.push([lo + (hi - lo) * g / (G - 1), d / vv.length]);
          }
          return path;
        });
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
        for (const pt of path) ctx.lineTo(sx(pt[0]), yMid - pt[1] * half * 40);
        for (let g = path.length - 1; g >= 0; g--)
          ctx.lineTo(sx(path[g][0]), 2 * yMid - (yMid - path[g][1] * half * 40));
        ctx.closePath();
        ctx.fill();
        ctx.globalAlpha = 1;

        // mode marker
        ctx.strokeStyle = AID.colorOf(c);
        ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(sx(mode), yTop + 4); ctx.lineTo(sx(mode), yTop + rowH - 4); ctx.stroke();
        ctx.setLineDash([]);

        // points: matches pop, the rest whisper
        const m = this.store.get().matches;
        const fade = this.cache.fade == null ? 1 : this.cache.fade;
        for (const i of pts) {
          const on = !m || m[i];
          ctx.fillStyle = AID.colorOf(c);
          ctx.globalAlpha = (m ? (on ? 0.85 : 0.05) : 0.3) * fade;
          ctx.beginPath();
          ctx.arc(sx(Math.max(X0, Math.min(X1, values[i]))),
            yMid + jitter(i) * half * 0.5, on ? 1.8 : 1.3, 0, 6.2832);
          ctx.fill();
        }
        ctx.globalAlpha = 1;

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

      const sel = this.sel();
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

      // numbered corner badges: group 0 at the right (100%), its complement left
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
        const d = Math.abs(values[pts[i]] - mxv);
        if (d < bd) { bd = d; best = pts[i]; }
      }
      const tol = (X1 - X0) * HOVER_R / (plotR - plotL);
      return bd <= tol ? best : -1;
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
    let order = null, dmin = 0, dmax = 1, lastYaw = NaN, lastPitch = NaN;

    function projectAll() {
      if (cache.frameLocked) return; // a morph owns the frame; don't clobber
      cache.updateFrame([yaw, pitch]);
      if (order && yaw === lastYaw && pitch === lastPitch) return;
      lastYaw = yaw; lastPitch = pitch;
      dmin = Infinity; dmax = -Infinity;
      for (let i = 0; i < n; i++) {
        AID.project3(cache.bary.subarray(i * 4, i * 4 + 4), yaw, pitch, tmp);
        depth[i] = tmp[2];
        if (tmp[2] < dmin) dmin = tmp[2];
        if (tmp[2] > dmax) dmax = tmp[2];
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
        tx: W / 2 - s * AID.TET_CENTROID[0],
        ty: H / 2 - s * AID.TET_CENTROID[1],
      };
    }

    let T = { s: 1, tx: 0, ty: 0 };
    p.reset = function (W, H) { W_ = W; H_ = H; T = fit(W, H); };
    const sx = x => x * T.s + T.tx, sy = y => H_ - (y * T.s + T.ty);

    p.draw = function (ctx, W, H) {
      W_ = W; H_ = H;
      projectAll();
      T = fit(W, H);

      const proj = UNIT.map(u => {
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

      // archetype stars
      ctx.fillStyle = "#3a3a35";
      for (let a = 0; a < this.archBary.length / 4; a++) {
        AID.project3(this.archBary.subarray(a * 4, a * 4 + 4), yaw, pitch, tmp);
        star(ctx, sx(tmp[0]), sy(tmp[1]), 7);
        ctx.font = "600 11px system-ui, sans-serif";
        ctx.fillText(this.data.archetypes[a].name, sx(tmp[0]), sy(tmp[1]) - 11);
      }

      // points in painter's order: far first, near on top and a touch larger
      const m = this.store.get().matches;
      const span = dmax > dmin ? dmax - dmin : 1;
      const fade = this.cache.fade == null ? 1 : this.cache.fade;
      for (let k = 0; k < n; k++) {
        const i = order ? order[k] : k;
        const on = !m || m[i];
        const t = (depth[i] - dmin) / span;
        ctx.fillStyle = this.cache.colors[i];
        ctx.globalAlpha = (m ? (on ? 0.9 : 0.045) : (0.16 + 0.22 * t)) * fade;
        ctx.beginPath();
        ctx.arc(sx(screen[i * 2]), sy(screen[i * 2 + 1]),
          (on ? PT_R + 0.4 : PT_R - 0.5) * (0.8 + 0.6 * t), 0, 6.2832);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      const sel = this.sel();
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

      // two corners that line up on screen can be merged: draw their badges
      // fused — the born 4th vertex hidden behind its parent — and make the
      // overlapping pair the clickable merge handle.
      this.mergePair = null;
      if (!cache.frameLocked) {
        let best = 1e9;
        for (let i = 0; i < 4; i++) for (let j = i + 1; j < 4; j++) {
          const dx = proj[i][0] - proj[j][0], dy = proj[i][1] - proj[j][1];
          const d = Math.hypot(dx, dy);
          if (d < best) {
            best = d;
            this.mergePair = {
              i, j, x: (proj[i][0] + proj[j][0]) / 2, y: (proj[i][1] + proj[j][1]) / 2,
            };
          }
        }
        if (best > 26) this.mergePair = null;
        const mp = this.mergePair;
        if (mp) {
          let ux = proj[mp.i][0] - proj[mp.j][0], uy = proj[mp.i][1] - proj[mp.j][1];
          const L = Math.hypot(ux, uy);
          if (L > 1) { ux /= L; uy /= L; } else { ux = 1; uy = 0; }
          const o = 5;
          vertexBadge(ctx, proj[mp.j][0] - ux * o, proj[mp.j][1] - uy * o, mp.j);
          vertexBadge(ctx, proj[mp.i][0] + ux * o, proj[mp.i][1] + uy * o, mp.i);
        }
      }

      // numbered corner badges + labels (the fused pair is drawn above)
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
    p.drag = function (mx, my, dx, dy) {
      yaw += dx * 0.01;
      pitch = Math.max(-1.3, Math.min(1.3, pitch + dy * 0.01));
      cam.yaw = yaw; cam.pitch = pitch;
      p._lastMove = performance.now();
    };
    p.dblclick = function () {
      yaw = 0; pitch = 0; zoom = 1;
      cam.yaw = yaw; cam.pitch = pitch; cam.zoom = zoom;
    };
    p.value = idx => AID.readout(p.data.recipes.P[idx]);
    return p;
  };
})();