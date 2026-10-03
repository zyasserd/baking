/* Plot engine: canvas sizing, pointer events, tooltip, dirty-loop rendering.
 *
 * Owns hover/selection state; delegates all drawing and hit-testing to the
 * active painter (views.js). Events flow user -> store -> redraw, one way.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.attachPlot = function (canvas, tooltip, store, data) {
    const ctx = canvas.getContext("2d");
    let dpr = 1, W = 0, H = 0;
    let painter = null;
    let hover = -1, dirty = true, raf = 0;
    let dragging = false, moved = false, last = null;
    let cache = null;
    const pointers = new Map(); // active pointers (pinch support)
    let pinchDist = 0, pinchMid = null, lastTap = 0, lastTapX = 0, lastTapY = 0;

    function markDirty() {
      dirty = true;
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (dirty) { dirty = false; draw(); } });
    }

    function resize() {
      const r = canvas.parentElement.getBoundingClientRect();
      dpr = window.devicePixelRatio || 1;
      const w = Math.max(1, r.width), h = Math.max(1, r.height);
      const px = Math.round(w * dpr), py = Math.round(h * dpr);
      // only touch the backing store when it actually changes: assigning
      // canvas.width clears the canvas, which would flash blank mid-morph
      if (canvas.width !== px || canvas.height !== py) {
        W = w; H = h;
        canvas.width = px;
        canvas.height = py;
        if (painter) painter.reset(W, H);
        draw(); // repaint in the same tick, no blank frame
      } else {
        W = w; H = h;
        if (painter) painter.reset(W, H);
      }
      markDirty();
    }

    function draw() {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      if (painter) painter.draw(ctx, W, H);
      notifyNeighbours();
    }

    /* The painter computes the (screen-space) neighbourhood while drawing;
     * forward it to the ratio card. Keyed so it only fires when the selection
     * or the count changes (the card throttles the orbit churn). */
    let lastNbKey = null;
    function notifyNeighbours() {
      const nb = painter && painter.nb;
      const key = nb ? nb.sel + ":" + nb.count : "null";
      if (key === lastNbKey) return;
      lastNbKey = key;
      if (AID.onNeighbourhood) AID.onNeighbourhood(nb);
    }

    function rebuild() {
      const st = store.get();
      morphTo(st.groups || AID.resolveGroups(st.partition));
    }

    /* geometry cache per partition: bary coords, frame coords, colors.
     * The engine owns frame projection so a partition change can animate
     * points from their old positions to the new geometry (the morph). */
    const caches = {};
    function buildCache(key, groups) {
      if (!caches[key]) {
        // displace() folds overlap separation into the bary coords, so every
        // downstream step (projection, morph, hit grid) is consistent.
        const bary = AID.displace(
          AID.bary(data.recipes.P, groups), data.meta.n, groups.length);
        caches[key] = {          key, groups,
          dim: AID.dimOf(groups),
          bary,
          colors: data.recipes.cls.map(c => AID.colorOf(c)),
          // pale ceiling colour for de-emphasised dots (see AID.dimColorOf)
          dimColors: data.recipes.cls.map(c => AID.dimColorOf(c)),
          frame: new Float32Array(data.meta.n * 2),
          frameLocked: false,
          fade: 1, // painters scale point alpha by this (1D <-> 2D crossfade)
          updateFrame: function (rot) {
            const n = data.meta.n, tmp = [0, 0];
            if (this.dim === 2) {
              for (let i = 0; i < n; i++) {
                AID.project2(this.bary.subarray(i * 3, i * 3 + 3), tmp);
                this.frame[i * 2] = tmp[0]; this.frame[i * 2 + 1] = tmp[1];
              }
            } else if (this.dim === 3) {
              if (this.frameLocked) return;
              // project at the *current* orbit camera, not a hard-coded default,
              // so a partition change tweens from the view you are looking at
              const c = AID.camera3 || { yaw: 0, pitch: 0 };
              const yaw = rot ? rot[0] : c.yaw, pitch = rot ? rot[1] : c.pitch;
              for (let i = 0; i < n; i++) {
                AID.project3(this.bary.subarray(i * 4, i * 4 + 4), yaw, pitch, tmp);
                this.frame[i * 2] = tmp[0]; this.frame[i * 2 + 1] = tmp[1];
              }
            } else {
              // 1D: frame x = share of group 0 (violin reads bary directly)
              const k = groups.length;
              for (let i = 0; i < n; i++) {
                this.frame[i * 2] = this.bary[i * k];
                this.frame[i * 2 + 1] = 0;
              }
            }
          },
        };
        caches[key].updateFrame(null);
      } else {
        // reused cache: never leave it locked by an abandoned morph
        caches[key].frameLocked = false;
        caches[key].fade = 1;
        caches[key].updateFrame(null);
      }
      return caches[key];
    }

    /* ── the morph ────────────────────────────────────────────────────────
     * 2D is the tetrahedron seen face-on. So:
     *   2D -> 3D  rotate the regular tetra about the edge of the two untouched
     *             corners (geo.setBirthAt) so they stay put, the split corner
     *             extends and the apex hides behind it; points reproject live.
     *   3D -> 2D  fold flat where it stands: the merged corners converge and
     *             every point moves straight to the canonical 2D frame — no
     *             camera rotation, only an in-plane/scale adjustment.
     * other changes just tween point positions at the current camera. */
    let anim = null;
    const DUR = 550;
    const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

    function morphTo(groups) {
      if (anim) { cancelAnimationFrame(anim); anim = null; }
      const key = AID.groupsKey(groups);
      const old = cache;
      const oldPainter = painter;
      const nextDim = AID.dimOf(groups);
      const cam = AID.camera3 || (AID.camera3 = { yaw: 0, pitch: 0, zoom: 1 });

      // which corner a 2D↔3D split was born on (null = came from the rest box)
      let birthSlot = null;
      if (old && old.dim === 2 && nextDim === 3) {
        birthSlot = AID.birthParent(old.groups, groups);
        cam.yaw = 0; cam.pitch = 0; cam.zoom = 1; // face-on base === the 2D frame
        cam.panx = 0; cam.pany = 0;
      }
      // build caches in the regular orientation; the birth branch rotates after
      AID.setBirthAt(null, 0);
      AID.birthE = 1;
      const next = buildCache(key, groups);
      const from = old && old.dim >= 2 && next.dim >= 2
        ? Float32Array.from(old.frame) : null;
      cache = next;
      cache.fade = 1; // fade branch below lowers it; others stay fully opaque
      const nextPainter = AID["view" + next.dim](cache, data, store);
      nextPainter.hover = hover;
      nextPainter.reset(W, H);
      painter = nextPainter;

      // 2D -> 3D by splitting: rotate the regular tetra about the edge joining
      // the two untouched corners while reprojecting every frame. Those corners
      // never move; the split corner extends out and the apex ends up hidden
      // behind it. The apex fades in from nothing so the 2D frame carries over
      // seamlessly (no jitter).
      if (from && old.dim === 2 && next.dim === 3 && birthSlot !== null) {
        const ob = old.bary, nb = cache.bary, n = data.meta.n, tmp = [0, 0, 0];
        AID.setBirthAt(birthSlot, 0);
        AID.birthE = 0;
        cache.frameLocked = true; // the frame is driven here, not by projectAll
        cache.frame.set(from);    // first paint is exactly the old 2D frame
        const t0 = performance.now();
        const step = now => {
          const t = Math.min(1, (now - t0) / DUR), e = ease(t);
          AID.setBirthAt(birthSlot, e);
          AID.birthE = e;
          // weights move from the flat 4-group embedding (child weight 0) to the
          // real split, projected at the turning tetra: the new vertex grows out
          // of its parent corner and every point follows the frame exactly.
          for (let i = 0; i < n; i++) {
            const b = [
              ob[i * 3] * (1 - e) + nb[i * 4] * e,
              ob[i * 3 + 1] * (1 - e) + nb[i * 4 + 1] * e,
              ob[i * 3 + 2] * (1 - e) + nb[i * 4 + 2] * e,
              nb[i * 4 + 3] * e,
            ];
            AID.project3(b, 0, 0, tmp);
            cache.frame[i * 2] = tmp[0];
            cache.frame[i * 2 + 1] = tmp[1];
          }
          if (t < 1) anim = requestAnimationFrame(step);
          else {
            AID.setBirthAt(birthSlot, 1);
            AID.birthE = 1;
            cache.frameLocked = false;
            cache.updateFrame([0, 0]);
            anim = null;
          }
          markDirty();
        };
        anim = requestAnimationFrame(step);
        markDirty();
        return;
      }

      // 3D -> 2D: fold the tetra flat right where it stands — no camera
      // rotation. Merging two groups means two tetra corners become one, so the
      // scene is already an (in-plane-rotated) triangle; every point just moves
      // straight to its place in the canonical 2D triangle, the merged pair of
      // corners converge, and zoom/pan ease back to the default fit. All motion
      // is in frame space, so this is the shortest possible transition.
      const pair = old && old.dim === 3 && next.dim === 2
        ? AID.mergedPair(old.groups, groups) : null;
      if (from && pair && oldPainter && oldPainter.wireCorners) {
        AID.setBirthAt(null, 0); AID.birthE = 1;
        old.frameLocked = true;                 // the morph drives old.frame
        const oldFrame = Float32Array.from(old.frame);
        const toFrame = next.frame;             // the new 2D frame
        const a = pair[0], b = pair[1];         // kept corner, collapsed corner
        const slotOf = k => (k === b ? a : (k > b ? k - 1 : k));
        const wire0 = oldPainter.wireCorners();
        const wire1 = [0, 1, 2, 3].map(k => AID.TRI2[slotOf(k)]);
        const arch0 = oldPainter.archPoints();
        const archB = AID.bary(data.archetypes.map(x => x.P), groups);
        const arch1 = arch0.map((_, idx) => {
          const q = [0, 0];
          AID.project2(archB.subarray(idx * 3, idx * 3 + 3), q);
          return [q[0], q[1]];
        });
        const wire = wire0.map(p => p.slice());
        const arch = arch0.map(p => p.slice());
        const z0 = cam.zoom, px0 = cam.panx || 0, py0 = cam.pany || 0;
        painter = oldPainter;                   // keep drawing the 3D painter
        oldPainter.wire = wire;
        oldPainter.arch = arch;
        const t0 = performance.now();
        const step = now => {
          const t = Math.min(1, (now - t0) / DUR), e = ease(t);
          for (let i = 0; i < oldFrame.length; i++)
            old.frame[i] = oldFrame[i] + (toFrame[i] - oldFrame[i]) * e;
          for (let k = 0; k < 4; k++) {
            wire[k][0] = wire0[k][0] + (wire1[k][0] - wire0[k][0]) * e;
            wire[k][1] = wire0[k][1] + (wire1[k][1] - wire0[k][1]) * e;
          }
          for (let k = 0; k < arch.length; k++) {
            arch[k][0] = arch0[k][0] + (arch1[k][0] - arch0[k][0]) * e;
            arch[k][1] = arch0[k][1] + (arch1[k][1] - arch0[k][1]) * e;
          }
          oldPainter.setZoom(z0 + (1 - z0) * e);
          cam.panx = px0 * (1 - e); cam.pany = py0 * (1 - e);
          if (t < 1) anim = requestAnimationFrame(step);
          else {
            oldPainter.wire = null; oldPainter.arch = null;
            old.frameLocked = false;
            painter = nextPainter;
            painter.hover = hover;
            painter.reset(W, H);
            anim = null;
          }
          markDirty();
        };
        anim = requestAnimationFrame(step);
        markDirty();
        return;
      }

      // remaining changes: tween point positions at the current camera
      if (from && next.dim >= 2) {
        AID.setBirthAt(null, 0); AID.birthE = 1;
        // a 2D->3D that has no parent corner (a part pulled out of the rest
        // box) still should not pop its new apex into the middle: fade it in.
        const birthing = old.dim === 2 && next.dim === 3;
        if (birthing) AID.birthE = 0;
        const to = Float32Array.from(cache.frame);
        cache.frameLocked = true;
        const t0 = performance.now();
        const step = now => {
          const t = Math.min(1, (now - t0) / DUR), e = ease(t);
          if (birthing) AID.birthE = e;
          for (let i = 0; i < to.length; i++) {
            cache.frame[i] = from[i] + (to[i] - from[i]) * e;
          }
          if (t < 1) anim = requestAnimationFrame(step);
          else {
            cache.frameLocked = false;
            if (birthing) AID.birthE = 1;
            if (painter.rot) cache.updateFrame([painter.rot.yaw, painter.rot.pitch]);
            anim = null;
          }
          markDirty();
        };
        anim = requestAnimationFrame(step);
        markDirty();
        return;
      }

      // 1D <-> higher dims (and the very first paint): the violin and the
      // simplexes live in different coordinate spaces, so instead of tweening
      // positions crossfade the new view in.
      {
        AID.setBirthAt(null, 0);
        AID.birthE = 1;
        const t0 = performance.now();
        cache.fade = 0;
        const step = now => {
          const t = Math.min(1, (now - t0) / DUR);
          cache.fade = ease(t);
          if (t < 1) anim = requestAnimationFrame(step);
          else { cache.fade = 1; anim = null; }
          markDirty();
        };
        anim = requestAnimationFrame(step);
      }
      markDirty();
    }

    /* ── tooltip ──────────────────────────────────────────────────────── */
    function showTooltip(idx, mx, my) {
      const r = data.recipes;
      tooltip.innerHTML =
        "<b>" + escapeHtml(r.name[idx]) + "</b><br>" +
        '<span style="display:inline-block;width:8px;height:8px;border-radius:4px;' +
        "background:" + AID.colorOf(r.cls[idx]) + '"></span> ' +
        escapeHtml(r.cls[idx]) +
        "<br><code>" + painter.value(idx) + "</code>";
      tooltip.style.display = "block";
      const tw = tooltip.offsetWidth;
      tooltip.style.left = Math.min(W - tw - 8, mx + 14) + "px";
      tooltip.style.top = Math.max(8, my - 10) + "px";
    }
    function hideTooltip() { tooltip.style.display = "none"; }
    function showMarkerTooltip(mk, mx, my) {
      const r = AID.markerRatio(data, mk);
      const label = (mk.kind === "archetype" ? "\u2605 " : "\u25c6 ") +
        escapeHtml(mk.id);
      tooltip.innerHTML = "<b>" + label + "</b><br><code>" +
        (r ? AID.formatRatio(r) : "\u2014") + "</code>";
      tooltip.style.display = "block";
      const tw = tooltip.offsetWidth;
      tooltip.style.left = Math.min(W - tw - 8, mx + 14) + "px";
      tooltip.style.top = Math.max(8, my - 10) + "px";
    }
    function escapeHtml(s) {
      return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    /* ── pointer events: one code path for mouse and touch ────────────── */
    function pos(e) {
      const rect = canvas.getBoundingClientRect();
      return [e.clientX - rect.left, e.clientY - rect.top];
    }

    canvas.addEventListener("pointerdown", e => {
      canvas.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, pos(e));
      if (pointers.size === 2) {
        const pts = [...pointers.values()];
        pinchDist = Math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]);
        pinchMid = [(pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2];
        dragging = false;
        return;
      }
      dragging = true; moved = false;
      last = pos(e);
    });

    canvas.addEventListener("pointermove", e => {
      if (pointers.has(e.pointerId)) pointers.set(e.pointerId, pos(e));

      // two-finger gesture: pinch zooms about the midpoint, and the moving
      // midpoint pans (the touch equivalent of ctrl+drag)
      if (pointers.size === 2) {
        const pts = [...pointers.values()];
        const d = Math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]);
        const mx = (pts[0][0] + pts[1][0]) / 2, my = (pts[0][1] + pts[1][1]) / 2;
        if (pinchDist > 0) {
          if (painter && painter.zoom && Math.abs(d - pinchDist) > 1) {
            painter.zoom(mx, my, d / pinchDist);
          }
          if (pinchMid && painter && painter.pan) {
            painter.pan(mx - pinchMid[0], my - pinchMid[1]);
          }
        }
        pinchDist = d;
        pinchMid = [mx, my];
        moved = true;
        hideTooltip();
        markDirty();
        return;
      }

      const [mx, my] = pos(e);
      if (dragging && painter && painter.drag) {
        painter.drag(mx, my, mx - last[0], my - last[1], e.ctrlKey);
        last = [mx, my];
        moved = true;
        hideTooltip();
        markDirty();
        return;
      }
      if (e.pointerType === "mouse") {
        const mk = painter && painter.markerAt ? painter.markerAt(mx, my) : null;
        let idx = painter ? painter.hit(mx, my) : -1;
        // In selected mode only highlighted points are interactive: a dim point
        // gets no hover ring and no tooltip either.
        if (idx >= 0 && painter.selectedMode && painter.selectedMode()
            && !painter.isHighlighted(idx)) idx = -1;
        const overMerge = painter && painter.mergeHit && painter.mergeHit(mx, my);
        if (mk) idx = -1; // markers win over the dots underneath
        canvas.style.cursor = (overMerge || mk) ? "pointer" : "";
        if (idx !== hover) {
          hover = idx;
          painter.hover = idx;
          markDirty();
        }
        if (mk) showMarkerTooltip(mk, mx, my);
        else if (idx >= 0) showTooltip(idx, mx, my);
        else hideTooltip();
      }
    });

    function pointerUp(e) {
      if (!pointers.has(e.pointerId)) return;
      pointers.delete(e.pointerId);
      if (pointers.size > 0) { pinchDist = 0; pinchMid = null; return; }
      if (!dragging) return;
      dragging = false;
      const [mx, my] = pos(e);
      // double-tap resets the view (mobile equivalent of dblclick)
      const now = performance.now();
      if (!moved) {
        if (now - lastTap < 300 && Math.abs(mx - lastTapX) < 24
            && Math.abs(my - lastTapY) < 24) {
          if (painter && painter.dblclick) painter.dblclick();
          lastTap = 0;
        } else {
          lastTap = now; lastTapX = mx; lastTapY = my;
          if (tryMerge(mx, my)) {
            if (painter) painter.hover = -1;
            hideTooltip();
            markDirty();
            return;
          }
          // pick(), not hit(): in selected mode a click near a highlighted
          // point snaps to it; a click on empty space clears the selection.
          // A marker (star/diamond) wins over the dots under it.
          const mk = painter && painter.markerAt ? painter.markerAt(mx, my) : null;
          if (mk) {
            store.set({ focus: { kind: mk.kind, id: mk.id }, selection: -1 });
          } else {
            const idx = painter ? painter.pick(mx, my) : -1;
            store.set({ selection: idx >= 0 ? idx : -1, focus: null });
          }
        }
        if (painter) painter.hover = -1;
        hideTooltip();
        markDirty();
      }
    }
    window.addEventListener("pointerup", pointerUp);
    window.addEventListener("pointercancel", pointerUp);

    canvas.addEventListener("pointerleave", () => {
      if (pointers.size) return;
      hover = -1;
      if (painter) painter.hover = -1;
      hideTooltip();
      markDirty();
    });

    canvas.addEventListener("wheel", e => {
      if (!painter || !painter.wheel) return;
      e.preventDefault();
      const [mx, my] = pos(e);
      painter.wheel(mx, my, e.deltaY);
      markDirty();
    }, { passive: false });
    canvas.addEventListener("dblclick", () => {
      if (painter && painter.dblclick) painter.dblclick();
      markDirty();
    });

    let prevPart = null;
    store.subscribe(st => {
      if (st.partition !== prevPart) {
        prevPart = st.partition;
        hover = -1; hideTooltip(); rebuild();
      } else {
        markDirty();
      }
    });

    /* Fused-corner merge: clicking the ∞ glyph combines its two compartments. */
    function tryMerge(mx, my) {
      if (!painter || !painter.mergeHit) return false;
      const pair = painter.mergeHit(mx, my);
      if (!pair) return false;
      const g = store.get().groups || AID.resolveGroups(store.get().partition);
      const ng = AID.mergeGroups(g, pair.i, pair.j);
      store.set({ groups: ng, partition: AID.groupsKey(ng) });
      return true;
    }

    new ResizeObserver(resize).observe(canvas.parentElement);
    resize();
    // paint immediately: nothing changes the store on load
    prevPart = store.get().partition;
    rebuild();
    return { markDirty };
  };
})();