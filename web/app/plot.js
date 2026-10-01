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
    let pinchDist = 0, lastTap = 0, lastTapX = 0, lastTapY = 0;

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
        caches[key] = {          key, groups,
          dim: AID.dimOf(groups),
          bary: AID.bary(data.recipes.P, groups),
          colors: data.recipes.cls.map(c => AID.colorOf(c)),
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
     *   3D -> 2D  reverse that rotation and settle face-on, then switch to the
     *             flat 2D painter.
     * other changes just tween point positions at the current camera. */
    let anim = null;
    const DUR = 550;
    const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

    function morphTo(groups) {
      if (anim) { cancelAnimationFrame(anim); anim = null; }
      const key = AID.groupsKey(groups);
      const old = cache;
      const nextDim = AID.dimOf(groups);
      const cam = AID.camera3 || (AID.camera3 = { yaw: 0, pitch: 0, zoom: 1 });

      // which corner a 2D↔3D split was born on (null = came from the rest box)
      let birthSlot = null;
      if (old && old.dim === 2 && nextDim === 3) {
        birthSlot = AID.birthParent(old.groups, groups);
        cam.yaw = 0; cam.pitch = 0; cam.zoom = 1; // face-on base === the 2D frame
      }
      const mergeSlot = old && old.dim === 3 && nextDim === 2
        ? AID.birthParent(groups, old.groups) : null;

      // build caches in the regular orientation; the birth branch rotates after
      AID.setBirthAt(null, 0);
      AID.birthE = 1;
      const next = buildCache(key, groups);
      const from = old && old.dim >= 2 && next.dim >= 2
        ? Float32Array.from(old.frame) : null;
      cache = next;
      cache.fade = 1; // fade branch below lowers it; others stay fully opaque
      painter = AID["view" + next.dim](cache, data, store);
      painter.hover = hover;
      painter.reset(W, H);

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

      // 3D -> 2D: rotate back about that edge (the split corner returns to the
      // equilateral position, the apex folds away) and settle the camera
      // face-on, so the final 3D frame equals the 2D frame. Works for merging
      // any two corners; when it was a born split, the rotation is reversed.
      if (from && old.dim === 3 && next.dim === 2) {
        const pcache = buildCache("nul|" + key, groups.concat([[]]));
        const p3 = AID.view3(pcache, data, store);
        p3.hover = hover;
        p3.reset(W, H);
        const y0 = cam.yaw, p0 = cam.pitch;
        const ob = old.bary, tgt = pcache.bary, n = data.meta.n, tmp = [0, 0, 0];
        if (mergeSlot !== null) { AID.setBirthAt(mergeSlot, 1); AID.birthE = 1; }
        else { AID.setBirthAt(null, 0); AID.birthE = 1; }
        p3.setCamera(y0, p0);
        painter = p3;
        pcache.frameLocked = true;
        pcache.frame.set(from); // first paint is exactly the old 3D frame
        const t0 = performance.now();
        const step = now => {
          const t = Math.min(1, (now - t0) / DUR), e = ease(t), keep = 1 - e;
          if (mergeSlot !== null) { AID.setBirthAt(mergeSlot, keep); AID.birthE = keep; }
          p3.setCamera(y0 * keep, p0 * keep);
          for (let i = 0; i < n; i++) {
            const b = [
              ob[i * 4] * keep + tgt[i * 4] * e,
              ob[i * 4 + 1] * keep + tgt[i * 4 + 1] * e,
              ob[i * 4 + 2] * keep + tgt[i * 4 + 2] * e,
              ob[i * 4 + 3] * keep + tgt[i * 4 + 3] * e,
            ];
            AID.project3(b, y0 * keep, p0 * keep, tmp);
            pcache.frame[i * 2] = tmp[0];
            pcache.frame[i * 2 + 1] = tmp[1];
          }
          if (t < 1) anim = requestAnimationFrame(step);
          else {
            cam.yaw = 0; cam.pitch = 0; cam.zoom = 1;
            AID.setBirthAt(null, 0);
            AID.birthE = 1;
            cache = next;
            painter = AID.view2(cache, data, store);
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
        dragging = false;
        return;
      }
      dragging = true; moved = false;
      last = pos(e);
    });

    canvas.addEventListener("pointermove", e => {
      if (pointers.has(e.pointerId)) pointers.set(e.pointerId, pos(e));

      // two-finger pinch zooms about the midpoint
      if (pointers.size === 2) {
        const pts = [...pointers.values()];
        const d = Math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]);
        if (pinchDist > 0 && painter && painter.zoom && Math.abs(d - pinchDist) > 1) {
          const mx = (pts[0][0] + pts[1][0]) / 2, my = (pts[0][1] + pts[1][1]) / 2;
          painter.zoom(mx, my, d / pinchDist);
          markDirty();
        }
        pinchDist = d;
        moved = true;
        hideTooltip();
        return;
      }

      const [mx, my] = pos(e);
      if (dragging && painter && painter.drag) {
        painter.drag(mx, my, mx - last[0], my - last[1]);
        last = [mx, my];
        moved = true;
        hideTooltip();
        markDirty();
        return;
      }
      if (e.pointerType === "mouse") {
        const idx = painter ? painter.hit(mx, my) : -1;
        if (idx !== hover) {
          hover = idx;
          painter.hover = idx;
          markDirty();
        }
        if (idx >= 0) showTooltip(idx, mx, my); else hideTooltip();
      }
    });

    function pointerUp(e) {
      if (!pointers.has(e.pointerId)) return;
      pointers.delete(e.pointerId);
      if (pointers.size > 0) { pinchDist = 0; return; }
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
          const idx = e.pointerType === "mouse" ? hover
            : (painter ? painter.hit(mx, my) : -1);
          store.set({ selection: idx >= 0 ? idx : -1 });
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