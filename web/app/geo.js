/* Geometry: partitions of the five parts, barycentric coordinates, projections.
 *
 * A view is a PARTITION of {flour, liquid, egg, fat, sugar} into k displayed
 * groups — k=1 an axis, k=2 a triangle, k=3 a tetrahedron. Parts left out of
 * the groups are a hidden "rest"; displayed coordinates renormalize over the
 * shown total, so e.g. the hydration triangle (flour:liquid:egg) is a true
 * subcomposition. The same operator merges recipes and archetypes alike.
 *
 * Pure math, no DOM — executed by tests/test_web.js under qjs.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.PART_NAMES = ["flour", "liquid", "egg", "fat", "sugar"];

  /* Display order: the parts as shown in the readout, card and legend.
   * Indices into PART_NAMES / the data columns — flour, fat, sugar, liquid, egg. */
  AID.DISPLAY_ORDER = [0, 3, 4, 1, 2];

  // Named partitions. groups = part indices displayed, in slot order.
  // 1D partitions are two-group (the axis group vs its complement), so the
  // value is the group's share of the WHOLE composition, not a renormalized
  // subcomposition.
  AID.PARTITIONS = {
    rich:       { dim: 1, groups: [[3, 4], [0, 1, 2]] },
    wet:        { dim: 1, groups: [[1, 2], [0, 3, 4]] },
    flourAxis:  { dim: 1, groups: [[0], [1, 2, 3, 4]] },
    canon2:     { dim: 2, groups: [[0], [1, 2], [3, 4]] },   // flour : wet : rich
    hydration:  { dim: 2, groups: [[0], [1], [2]] },          // rest: fat+sugar
    shortbread: { dim: 2, groups: [[0], [3], [4]] },          // rest: liquid+egg
    canon3:     { dim: 3, groups: [[0], [1, 2], [3], [4]] },  // flour : wet : fat : sugar
    egg3:       { dim: 3, groups: [[0], [1], [2], [3, 4]] },
  };

  AID.groupLabel = g => g.map(i => AID.PART_NAMES[i]).join("+");

  /* Resolve a partition spec to groups: a preset name or literal groups. */
  AID.resolveGroups = function (part) {
    if (typeof part === "string") {
      const p = AID.PARTITIONS[part];
      if (!p) throw new Error("unknown partition: " + part);
      return p.groups;
    }
    return part;
  };

  /* Displayed-group count -> view dimension. One displayed group = the axis
   * (raw share of the whole); two groups still a 1D axis (group vs its
   * complement); three a triangle; four a tetrahedron. */
  AID.dimOf = function (groups) {
    return groups.length <= 2 ? 1 : groups.length - 1;
  };

  AID.groupsKey = groups => groups.map(g => g.join("+")).join("|");

  /* Parts not currently shown in any group. */
  AID.hiddenParts = function (groups) {
    const shown = new Set(groups.flat());
    return [0, 1, 2, 3, 4].filter(i => !shown.has(i));
  };

  /* Grouping edits behind the divider bar — all pure, all return a fresh
   * groups array. A "group" is one compartment / plot vertex. */

  /* Move `part` into compartment `target` (or, target < 0, to the rest). An
   * emptied source compartment disappears; at least one compartment remains. */
  AID.movePart = function (groups, part, target) {
    let g = groups.map(a => a.slice());
    const src = g.findIndex(a => a.indexOf(part) >= 0);
    if (src >= 0) g[src] = g[src].filter(p => p !== part);
    if (target >= 0 && target < g.length) {
      g[target] = g[target].concat([part]).sort((a, b) => a - b);
    }
    g = g.filter(a => a.length > 0);
    return g.length ? g : [[part]];
  };

  /* Merge compartment j into i (default j = i + 1) — one fewer vertex. */
  AID.mergeGroups = function (groups, i, j) {
    const g = groups.map(a => a.slice());
    if (j === undefined) j = i + 1;
    if (i < 0 || j < 0 || i >= g.length || j >= g.length || i === j) return g;
    const [a, b] = i < j ? [i, j] : [j, i];
    g[a] = g[a].concat(g[b]).sort((x, y) => x - y);
    g.splice(b, 1);
    return g;
  };

  /* Split one part off compartment i into a new compartment at the end — the
   * new geometric vertex (up to four). No-op for a lone part or a full
   * simplex. Appending keeps the new corner the "extra" vertex, so its birth
   * animation can start it on the compartment it was split from. */
  AID.splitGroup = function (groups, i) {
    const g = groups.map(a => a.slice());
    if (i < 0 || i >= g.length || g[i].length < 2 || g.length >= 4) return g;
    const part = g[i].pop();
    g.push([part]);
    return g;
  };

  /* Pull `part` (from any compartment, or from the rest) into its own brand
   * new compartment at the end — the drag target for "add a divider". */
  AID.pullOut = function (groups, part) {
    const g = groups.map(a => a.slice());
    if (g.length >= 4) return g;
    const src = g.findIndex(a => a.indexOf(part) >= 0);
    if (src < 0) return g.concat([[part]]); // was hidden
    g[src] = g[src].filter(p => p !== part);
    const out = g.filter(a => a.length > 0);
    out.push([part]);
    return out;
  };

  /* Per-recipe barycentric coordinates: Float32Array(n*k), group sums
   * renormalized over the displayed parts (k=1: the raw share of the whole).
   * P is an array of 5-share rows; spec is a preset name or groups array. */
  AID.bary = function (P, spec) {
    const groups = AID.resolveGroups(spec);
    const k = groups.length, n = P.length;
    const out = new Float32Array(n * k);
    for (let r = 0; r < n; r++) {
      const row = P[r];
      let tot = 0;
      for (let g = 0; g < k; g++) {
        let s = 0;
        const idx = groups[g];
        for (let j = 0; j < idx.length; j++) s += row[idx[j]];
        out[r * k + g] = s;
        tot += s;
      }
      const inv = tot > 0 ? 1 / tot : 0;
      for (let g = 0; g < k; g++) out[r * k + g] *= k === 1 ? 1 : inv;
    }
    return out;
  };

  /* ── overlap separation ────────────────────────────────────────────────
   * Recipes that share the displayed position render as dots on top of each
   * other: their translucency stacks and zoom cannot tell them apart.
   * displace() returns a copy of the barycentric coordinates in which such
   * points are nudged onto a small deterministic golden-angle spiral around the
   * true spot, so they can be told apart once zoomed in. The nudge is tiny and
   * of fixed size (it never grows with the pile), lives in barycentric space so
   * it can never leave the simplex (the step is scaled back until every
   * coordinate is >= 0, and the deltas sum to zero), and is fully deterministic
   * — the angle is the point's position in its collision group, never a random
   * source. Points with no collision are returned exactly where the data puts
   * them. */
  AID.DISPLACE_QUANTUM = 1e-4; // displayed positions closer than this collide
  AID.DISPLACE_SPREAD = 0.0015; // fixed spiral radius, frame units
  const GOLDEN_ANGLE = 2.399963229728653;

  AID.displace = function (bary, n, k) {
    const out = Float32Array.from(bary);
    if (k < 3) return out; // the axis view already strips points vertically
    const groups = new Map();
    for (let i = 0; i < n; i++) {
      let key = "";
      for (let g = 0; g < k; g++) {
        key += Math.round(bary[i * k + g] / AID.DISPLACE_QUANTUM) + ",";
      }
      const a = groups.get(key);
      if (a) a.push(i); else groups.set(key, [i]);
    }
    // Map a desired frame-space offset to a sum-zero bary delta through slots
    // 0,1,2 (the base triangle, shared by the 2D and 3D frames), so the spiral
    // stays circular instead of shearing with the triangle's 120° corners.
    const v0x = AID.TRI2[0][0] - AID.TRI2[2][0];
    const v0y = AID.TRI2[0][1] - AID.TRI2[2][1];
    const v1x = AID.TRI2[1][0] - AID.TRI2[2][0];
    const v1y = AID.TRI2[1][1] - AID.TRI2[2][1];
    const det = v0x * v1y - v1x * v0y;
    const d = new Float32Array(k); // one reusable sum-zero displacement
    for (const a of groups.values()) {
      const m = a.length;
      if (m < 2) continue;
      for (let j = 0; j < m; j++) {
        const ang = j * GOLDEN_ANGLE;
        const rr = AID.DISPLACE_SPREAD * Math.sqrt((j + 0.5) / m);
        const dx = Math.cos(ang) * rr, dy = Math.sin(ang) * rr;
        d.fill(0);
        d[0] = (v1y * dx - v1x * dy) / det;
        d[1] = (-v0y * dx + v0x * dy) / det;
        d[2] = -(d[0] + d[1]);
        const o = a[j] * k;
        // largest safe step toward the offset before hitting a simplex face
        let t = 1;
        for (let g = 0; g < k; g++) if (d[g] < 0) t = Math.min(t, bary[o + g] / -d[g]);
        for (let g = 0; g < k; g++) out[o + g] = bary[o + g] + t * d[g];
      }
    }
    return out;
  };

  /* 2D frame space: equilateral triangle, y up, flour at the top.
   * Vertex slots match group slots; slot 0 (flour) is the apex. */
  AID.TRI2 = [[0.5, 0.8660254], [0, 0], [1, 0]];

  AID.project2 = function (b, out) {
    // b: 3 barycentric coords -> [x, y]
    const x = b[0] * AID.TRI2[0][0] + b[1] * AID.TRI2[1][0] + b[2] * AID.TRI2[2][0];
    const y = b[0] * AID.TRI2[0][1] + b[1] * AID.TRI2[1][1] + b[2] * AID.TRI2[2][1];
    out[0] = x; out[1] = y;
  };

  /* 3D frame space: regular tetrahedron. The base face of slots 0,1,2 is
   * exactly TRI2 (same orientation, flour at the top), and slot 3 is the apex
   * above its centroid — so the 2D triangle is a face of the 3D tetrahedron and
   * the two views share an orientation. */
  AID.TET3 = [
    [0.5, 0.8660254, 0],             // slot 0: top of the base face
    [0, 0, 0],                       // slot 1: bottom-left
    [1, 0, 0],                       // slot 2: bottom-right
    [0.5, 0.2886751, 0.8164966],     // slot 3: apex over the centroid
  ];

  /* The untouched regular orientation. Every birth/merge is a rigid rotation of
   * THIS, so the tetrahedron is never deformed — only turned. */
  AID.TET3_REGULAR = AID.TET3.map(v => v.slice());

  /* Birth phase 0..1 while a 2D↔3D split animates: the apex (and its edges) is
   * faded by this so the flat 2D view carries over without a pop. */
  AID.birthE = 1;

  /* True centroid of the tetrahedron — the orbit pivot. Rotating about it
   * keeps the shape centred instead of drifting as yaw/pitch change. */
  const TET_CENTROID = AID.TET3.reduce(
    (a, v) => [a[0] + v[0] / 4, a[1] + v[1] / 4, a[2] + v[2] / 4], [0, 0, 0]);
  AID.TET_CENTROID = TET_CENTROID;

  /* Rotation-independent bounding-sphere radius: the frame is fitted once to
   * this, so the scene never pulses as the bounding box changes with yaw. */
  AID.TET_RADIUS = Math.max(...AID.TET3.map(v => Math.hypot(
    v[0] - TET_CENTROID[0], v[1] - TET_CENTROID[1], v[2] - TET_CENTROID[2])));

  /* Orthographic 3D projection with yaw (around the vertical axis) and pitch.
   * Returns [x, y] in frame space; out[2] (if present) receives the rotated
   * depth for painter's-order drawing. */
  AID.project3 = function (b, yaw, pitch, out) {
    let x = 0, y = 0, depth = 0;
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    for (let i = 0; i < 4; i++) {
      const v = AID.TET3[i], w = b[i];
      // translate to centroid, yaw around the vertical axis, then pitch.
      const vx = v[0] - TET_CENTROID[0];
      const vy = v[1] - TET_CENTROID[1];
      const vz = v[2] - TET_CENTROID[2];
      const x1 = vx * cy + vz * sy;
      const z1 = -vx * sy + vz * cy;
      const y1 = vy * cp - z1 * sp;
      x += w * (x1 + TET_CENTROID[0]);
      y += w * (y1 + TET_CENTROID[1]);
      depth += w * z1;
    }
    out[0] = x; out[1] = y;
    if (out.length > 2) out[2] = depth;
  };

  /* ── "Birth": turn the tetrahedron so the 4th vertex hides behind the corner
   * it was split from, keeping the other two base corners pinned ──
   *
   * A split takes a part out of corner X; the other two base corners Y,Z are
   * untouched. Rotating rigidly about the edge Y–Z leaves Y,Z exactly where they
   * are on screen, swings X out, and carries the apex around the (opposite) edge
   * X–apex until that edge points at the viewer — so the apex lands on the same
   * pixel as X, hidden behind it. `e` is the animation phase (0 = the plain
   * regular face-on tetra, 1 = fully born); other splits/merges reverse it.
   * A part pulled out of the `rest` box has no parent, so nothing rotates. */

  const _sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const _dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const _cross = (a, b) => [
    a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const _unit = a => {
    const l = Math.hypot(a[0], a[1], a[2]) || 1;
    return [a[0] / l, a[1] / l, a[2] / l];
  };
  /* Rodrigues: rotate point p about the axis (through q, direction a) by th. */
  function _rot(p, q, a, th) {
    const x = p[0] - q[0], y = p[1] - q[1], z = p[2] - q[2];
    const c = Math.cos(th), s = Math.sin(th), d = _dot(a, [x, y, z]);
    const cr = _cross(a, [x, y, z]);
    return [
      q[0] + x * c + cr[0] * s + a[0] * d * (1 - c),
      q[1] + y * c + cr[1] * s + a[1] * d * (1 - c),
      q[2] + z * c + cr[2] * s + a[2] * d * (1 - c),
    ];
  }

  AID.setBirthAt = function (slot, e) {
    const reg = AID.TET3_REGULAR;
    for (let i = 0; i < 4; i++) AID.TET3[i] = reg[i].slice();
    if (slot == null || !e) return;
    const y = (slot + 1) % 3, z = (slot + 2) % 3;
    const axis = _unit(_sub(AID.TET3[z], AID.TET3[y]));
    const w = _sub(AID.TET3[3], AID.TET3[slot]);       // the opposite edge X–apex
    const up = [0, 0, 1];
    const th = Math.atan2(_dot(_cross(w, up), axis), _dot(w, up)) * e;
    const q = AID.TET3[y];
    for (let i = 0; i < 4; i++) AID.TET3[i] = _rot(AID.TET3[i], q, axis, th);
  };

  /* The corner a 2D→3D split's new vertex was born on: old groups (3) lost a
   * part into the appended compartment (groups[3]); the parent is the
   * compartment that part came from, null if it was a hidden "rest" part. */
  AID.birthParent = function (oldGroups, groups) {
    if (!oldGroups || oldGroups.length !== 3 || groups.length !== 4) return null;
    const baby = groups[groups.length - 1];
    if (!baby || baby.length !== 1) return null;
    const oi = oldGroups.findIndex(g => g.indexOf(baby[0]) >= 0);
    return oi >= 0 ? oi : null;
  };

  /* When a partition drops from four groups to three, which two of the old
   * groups were combined? Every part of one new group comes from exactly two
   * old groups; returns [mergedParent, absorbed] (parent first, so slot i is
   * the kept corner) or null if the change was not a merge. */
  AID.mergedPair = function (oldGroups, newGroups) {
    if (oldGroups.length !== 4 || newGroups.length !== 3) return null;
    for (const ng of newGroups) {
      const parts = new Set(ng), src = [];
      for (let k = 0; k < oldGroups.length; k++) {
        if (oldGroups[k].every(p => parts.has(p))) src.push(k);
      }
      if (src.length === 2) {
        const covered = new Set();
        for (const k of src) for (const p of oldGroups[k]) covered.add(p);
        if (covered.size === parts.size) return [src[0], src[1]];
      }
    }
    return null;
  };

  /* Simple-ratio readout: parts per 100 flour, "100 : 50 : 50 : 100 : 100"
   * in display order (flour : fat : sugar : liquid : egg). */
  AID.readout = function (row) {
    const f = row[0] > 0 ? row[0] : 1;
    const s = AID.DISPLAY_ORDER.map(i => Math.round((row[i] / f) * 100));
    return s.join(" : ");
  };

  /* ── closest simple integer ratio ────────────────────────────────────────
   *
   * A recipe is a point on the 5-part simplex; "3 : 2 : 1" is the primitive
   * integer point nearest it. We want the *simplest* ratio still close enough:
   * among all primitive integer vectors whose normalized position is within
   * RATIO_EPS (max absolute component error) of the recipe, the one with the
   * smallest largest term. Searching N = 1, 2, 3 … and returning the first N
   * that has any candidate inside the ball gives exactly that min-max ratio.
   *
   * The simplex is 4-D, so ~N⁴ primitive ratios have max term ≤ N and their
   * typical spacing is ~1/N: small integers and a tight epsilon trade off
   * directly. On this dataset eps=0.05 resolves every recipe within max 10. */
  AID.RATIO_EPS = 0.04;
  AID.RATIO_MAX_TERM = 12;

  function ratioGcd(a) {
    let g = 0;
    for (let i = 0; i < 5; i++) {
      let v = a[i];
      while (v) { const t = g % v; g = v; v = t; }
    }
    return g;
  }

  function ratioResult(terms, err, max, eps) {
    return {
      terms: AID.DISPLAY_ORDER.map(i => terms[i]), // display order, like readout
      raw: terms,                                  // PART_NAMES order
      err, max, ok: err <= eps,
    };
  }

  /* `eps` is the max component error tolerated (default RATIO_EPS). Passing a
   * near-zero eps recovers the exact primitive ratio of an already-simple
   * composition, e.g. a book archetype — handy because 5:3 has a smaller
   * 3:2 approximation that the default epsilon would otherwise prefer.
   *
   * The primitive integer ratios are the same for every query, so they are
   * built once (lazily) into per-max-term groups and reused: a query only
   * scans the groups in order and returns the first with a candidate inside
   * the ball (min max term), or the closest if none is. */
  let _lattice = null;
  function buildLattice() {
    const cap = AID.RATIO_MAX_TERM;
    const gp = [], gt = [];
    for (let i = 0; i <= cap; i++) { gp.push([]); gt.push([]); }
    const a = [0, 0, 0, 0, 0];
    for (a[0] = 0; a[0] <= cap; a[0]++)
    for (a[1] = 0; a[1] <= cap; a[1]++)
    for (a[2] = 0; a[2] <= cap; a[2]++)
    for (a[3] = 0; a[3] <= cap; a[3]++)
    for (a[4] = 0; a[4] <= cap; a[4]++) {
      let m = a[0];
      for (let i = 1; i < 5; i++) if (a[i] > m) m = a[i];
      if (m === 0 || ratioGcd(a) !== 1) continue;
      const s = a[0] + a[1] + a[2] + a[3] + a[4];
      for (let i = 0; i < 5; i++) { gp[m].push(a[i] / s); gt[m].push(a[i]); }
    }
    const groups = [];
    for (let N = 0; N <= cap; N++) {
      groups.push({
        pos: Float32Array.from(gp[N]),
        terms: Int8Array.from(gt[N]),
        count: gp[N].length / 5,
      });
    }
    _lattice = { cap, groups };
  }

  AID.simpleRatio = function (row, eps) {
    const tol = eps == null ? AID.RATIO_EPS : eps;
    let sum = 0;
    for (let i = 0; i < 5; i++) sum += row[i];
    if (!(sum > 0)) return null;
    const x = [0, 0, 0, 0, 0];
    for (let i = 0; i < 5; i++) x[i] = row[i] / sum;
    if (!_lattice) buildLattice();
    const L = _lattice;
    let best = null, bestErr = Infinity, bestMax = 0;
    for (let N = 1; N <= L.cap; N++) {
      const g = L.groups[N];
      if (!g.count) continue;
      const pos = g.pos, terms = g.terms;
      let hit = null, hitErr = Infinity;
      for (let c = 0; c < g.count; c++) {
        const o = c * 5;
        let e = 0;
        for (let i = 0; i < 5; i++) {
          let d = x[i] - pos[o + i];
          if (d < 0) d = -d;
          if (d > e) e = d;
        }
        if (e <= tol && e < hitErr) {
          hit = [terms[o], terms[o + 1], terms[o + 2], terms[o + 3], terms[o + 4]];
          hitErr = e;
        }
        if (e < bestErr) {
          best = [terms[o], terms[o + 1], terms[o + 2], terms[o + 3], terms[o + 4]];
          bestErr = e; bestMax = N;
        }
      }
      if (hit) return ratioResult(hit, hitErr, N, tol);
    }
    return best ? ratioResult(best, bestErr, bestMax, tol) : null;
  };

  AID.formatRatio = function (r) {
    return r ? r.terms.join(" : ") : "";
  };

  /* Exact small-integer ratio of an archetype composition (no approximation). */
  AID.archetypeRatio = function (P) {
    return AID.simpleRatio(P, 1e-5);
  };

  /* Display ratio for a marker: exact for a book archetype, approximate for a
   * class mean. Memoized — the hover tooltip asks on every pointer move. */
  let _markerRatio = null;
  AID.markerRatio = function (data, mk) {
    if (!_markerRatio || _markerRatio.data !== data) _markerRatio = { data, map: {} };
    const key = mk.kind + ":" + mk.id;
    if (key in _markerRatio.map) return _markerRatio.map[key];
    const comp = AID.markerComposition(data, mk);
    const r = comp
      ? (mk.kind === "archetype" ? AID.archetypeRatio(comp) : AID.simpleRatio(comp))
      : null;
    _markerRatio.map[key] = r;
    return r;
  };

  /* ── Aitchison geometry: ILR (pivot balances) and nearest archetype ──
   *
   * Mirrors src/method/coda.py so distances agree with the method's numbers.
   * Zero replacement follows config.ZERO_REPLACEMENT_DELTA (delta = factor *
   * min positive share in the row). */

  AID.ZERO_REPLACEMENT_DELTA = 0.5;

  function pivotPsi(D) {
    const psi = [];
    for (let k = 0; k < D - 1; k++) {
      const coef = Math.sqrt((D - k - 1) / (D - k));
      const row = new Array(D).fill(0);
      row[k] = coef;
      for (let j = k + 1; j < D; j++) row[j] = -coef / (D - k - 1);
      psi.push(row);
    }
    return psi;
  }
  const PSI5 = pivotPsi(5);

  function ilrRow(P, psi) {
    const z = [];
    for (const row of psi) {
      const pos = [], neg = [];
      for (let j = 0; j < P.length; j++) (row[j] > 0 ? pos : neg).push(Math.log(P[j]));
      const mean = a => a.reduce((s, v) => s + v, 0) / a.length;
      const r = pos.length, sN = neg.length;
      z.push(Math.sqrt(r * sN / (r + sN)) * (mean(pos) - mean(neg)));
    }
    return z;
  }

  function replaceZeros(row) {
    const minPos = Math.min(...row.filter(v => v > 0));
    const delta = AID.ZERO_REPLACEMENT_DELTA * minPos;
    const out = row.map(v => (v > 0 ? v : delta));
    const tot = out.reduce((s, v) => s + v, 0);
    return out.map(v => v / tot);
  }

  /* Nearest archetype by Aitchison distance (Euclidean in ILR). */
  AID.aitchisonNearest = function (Prow, archs) {
    const P = replaceZeros(Prow);
    const z = ilrRow(P, PSI5);
    let best = null, bd = Infinity;
    for (const a of archs) {
      const za = ilrRow(replaceZeros(a.P), PSI5);
      let d = 0;
      for (let i = 0; i < z.length; i++) { const e = z[i] - za[i]; d += e * e; }
      d = Math.sqrt(d);
      if (d < bd) { bd = d; best = a; }
    }
    return { name: best.name, d: bd };
  };

  /* Per-class centroid = arithmetic mean of the class's share rows. Kept for
   * comparison; the compositional centre is the geometric mean below. */
  let _centroids = null;
  function classCentroidMap(P, cls) {
    if (_centroids && _centroids.P === P) return _centroids.map;
    const sums = {}, cnt = {}, map = {};
    for (let i = 0; i < P.length; i++) {
      const c = cls[i];
      let s = sums[c];
      if (!s) { s = sums[c] = [0, 0, 0, 0, 0]; cnt[c] = 0; }
      for (let j = 0; j < 5; j++) s[j] += P[i][j];
      cnt[c]++;
    }
    for (const c in sums) map[c] = sums[c].map(v => v / cnt[c]);
    _centroids = { P, map };
    return map;
  }

  /* Per-class centre in Aitchison geometry: the CLR mean,
   * close(exp(mean(log(share)))), with the usual zero replacement. This is the
   * composition the class is centred on — the arithmetic mean of raw shares is
   * pulled toward whatever the class's spread is and is not the centre the
   * Aitchison distances measure to. Memoized: the panel and every draw ask. */
  let _cmeans = null;
  AID.classMeanMap = function (P, cls) {
    if (_cmeans && _cmeans.P === P) return _cmeans.map;
    const acc = {}, cnt = {}, map = {};
    for (let i = 0; i < P.length; i++) {
      const c = cls[i];
      let s = acc[c];
      if (!s) { s = acc[c] = [0, 0, 0, 0, 0]; cnt[c] = 0; }
      const z = replaceZeros(P[i]);
      for (let j = 0; j < 5; j++) s[j] += Math.log(z[j]);
      cnt[c]++;
    }
    for (const c in acc) {
      const m = acc[c].map(v => Math.exp(v / cnt[c]));
      const t = m[0] + m[1] + m[2] + m[3] + m[4];
      map[c] = m.map(v => v / t);
    }
    _cmeans = { P, map };
    return map;
  };
  AID.classMean = function (data, clsName) {
    return AID.classMeanMap(data.recipes.P, data.recipes.cls)[clsName] || null;
  };

  /* Composition behind a marker: a class-mean diamond or an archetype star. */
  AID.markerComposition = function (data, mk) {
    if (!mk) return null;
    if (mk.kind === "class") return AID.classMean(data, mk.id);
    const a = data.archetypes.find(x => x.name === mk.id);
    return a ? a.P : null;
  };

  /* Book archetype -> the tag family it stands for. Hand-picked, not derived:
   * an archetype is a composition, not a class, so which family it "belongs"
   * to is a judgement call (e.g. an American biscuit reads as a quick bread,
   * shortbread as a cookie). Selecting a star highlights this family. */
  AID.ARCHETYPE_FAMILY = {
    bread: "bread",
    quick_bread: "quick_bread",
    pie_dough: "pie_pastry",
    biscuit: "quick_bread",
    cookie: "cookie",
    shortbread: "cookie",
    choux: "batter",
    pancake: "batter",
    crepe: "batter",
    pound_cake: "cake",
    angel_food: "cake",
  };

  /* Nearest class centroid by Aitchison distance (Euclidean in ILR). Uses the
   * geometric (CLR) mean — the class's compositional centre. */
  AID.nearestCentroid = function (Prow, P, cls) {
    const map = AID.classMeanMap(P, cls);
    const z = ilrRow(replaceZeros(Prow), PSI5);
    let best = null, bd = Infinity;
    for (const c in map) {
      const zc = ilrRow(replaceZeros(map[c]), PSI5);
      let d = 0;
      for (let i = 0; i < z.length; i++) { const e = z[i] - zc[i]; d += e * e; }
      d = Math.sqrt(d);
      if (d < bd) { bd = d; best = c; }
    }
    return { name: best, d: bd };
  };

  /* ── Neighbourhood radius ──────────────────────────────────────────────
   *
   * A fixed radius in the partition's own frame — a unit-edge regular simplex —
   * so the neighbourhood is the same set of recipes however far you zoom or
   * rotate. It is a composition distance, not a screen size. One group gives an
   * interval on the axis, three a disc in the triangle, four a sphere in the
   * tetrahedron. Measured as Euclidean distance in the simplex: |Δb|²/2, where
   * b are the group barycentric coordinates (see frameNeighbours in views.js). */

  AID.NEIGHBOURHOOD_R = 0.05;

  /* Percentile of v within a class distribution given [p05,p25,p50,p75,p95],
   * piecewise-linear in between (below p05 -> 0-5, above p95 -> 95-100). */
  AID.percentileOf = function (v, qs) {
    const cuts = [0, 5, 25, 50, 75, 95, 100];
    const edges = [-Infinity].concat(qs, [Infinity]);
    for (let i = 0; i < 5; i++) {
      if (v >= edges[i] && v <= edges[i + 1]) {
        const lo = edges[i], hi = edges[i + 1];
        if (hi === lo) return (cuts[i] + cuts[i + 1]) / 2;
        const t = (v - lo) / (hi - lo);
        return cuts[i] + t * (cuts[i + 1] - cuts[i]);
      }
    }
    return 50;
  };

  /* ── Ratio equation locus ────────────────────────────────────────────────
   *
   * A ratio equation ("flour : fat = 2 : 1", or more terms) pins a linear
   * relation among raw part shares: k_j * G_i - k_i * G_j = 0 for every pair,
   * where G_i is the share summed over operand i's parts. Intersected with the
   * simplex (sum = 1, p >= 0) this is a convex polytope. Its vertices are the
   * basic feasible solutions: pick `r` parts to be nonzero (r = #equations),
   * solve the square system, and keep the solutions with p >= 0. The painters
   * project these and take their convex hull — a line, a plane or a point,
   * depending on the view. Pure and DOM-free, so it is unit tested. */

  /* Ops: [{ idx: [partIndex...], k: number }, ...], at least two. Returns an
   * array of raw 5-share rows. */
  AID.ratioLocusVertices = function (ops) {
    const r = ops ? ops.length : 0;
    if (r < 2 || r > 5) return [];

    // r equations over the five parts: the simplex sum plus (r-1) ratios.
    const rows = [[1, 1, 1, 1, 1]];
    const rhs = [1];
    const k0 = ops[0].k;
    for (let j = 1; j < r; j++) {
      const row = [0, 0, 0, 0, 0];
      for (const t of ops[0].idx) row[t] += ops[j].k;
      for (const t of ops[j].idx) row[t] -= k0;
      rows.push(row);
      rhs.push(0);
    }

    const verts = [];
    const seen = new Set();
    for (const comb of combinations(5, r)) {
      const A = rows.map(row => comb.map(c => row[c]));
      const x = solveSquare(A, rhs.slice());
      if (!x || x.some(v => v < -1e-9)) continue;
      const p = [0, 0, 0, 0, 0];
      comb.forEach((c, i) => { p[c] = x[i] < 0 ? 0 : x[i]; });
      const key = p.map(v => v.toFixed(6)).join(",");
      if (seen.has(key)) continue;
      seen.add(key);
      verts.push(p);
    }
    return verts;
  };

  /* All combinations of `k` indices from 0..n-1. */
  function combinations(n, k) {
    const out = [];
    const rec = (start, acc) => {
      if (acc.length === k) { out.push(acc.slice()); return; }
      for (let i = start; i < n; i++) { acc.push(i); rec(i + 1, acc); acc.pop(); }
    };
    rec(0, []);
    return out;
  }

  /* Solve A x = b for square A (Gauss-Jordan); null when singular. */
  function solveSquare(A, b) {
    const m = b.length;
    for (let c = 0; c < m; c++) {
      let piv = c;
      for (let r = c + 1; r < m; r++) if (Math.abs(A[r][c]) > Math.abs(A[piv][c])) piv = r;
      if (Math.abs(A[piv][c]) < 1e-12) return null;
      const tA = A[c]; A[c] = A[piv]; A[piv] = tA;
      const tb = b[c]; b[c] = b[piv]; b[piv] = tb;
      for (let r = 0; r < m; r++) {
        if (r === c) continue;
        const f = A[r][c] / A[c][c];
        if (!f) continue;
        for (let cc = c; cc < m; cc++) A[r][cc] -= f * A[c][cc];
        b[r] -= f * b[c];
      }
    }
    const x = new Array(m);
    for (let i = 0; i < m; i++) x[i] = b[i] / A[i][i];
    return x;
  }

  /* 2D convex hull (monotone chain), counter-clockwise. */
  AID.hull2 = function (points) {
    const pts = points.slice().sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]));
    if (pts.length < 3) return pts;
    const cross = (o, a, b) =>
      (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lower = [];
    for (const p of pts) {
      while (lower.length >= 2 &&
        cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
      lower.push(p);
    }
    const upper = [];
    for (let i = pts.length - 1; i >= 0; i--) {
      const p = pts[i];
      while (upper.length >= 2 &&
        cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
      upper.push(p);
    }
    lower.pop(); upper.pop();
    return lower.concat(upper);
  };

})();