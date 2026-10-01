/* Smoke tests for the Aid's DOM-free JS modules, run under qjs.
 *
 * Load order mirrors web/index.html. DOM-touching files (plot.js, views.js'
 * canvas code paths, main.js) get a syntax check only (new Function parses
 * without executing); pure modules (palette, state, geo) run for real.
 * Exit code 0 = all green; the pytest wrapper (tests/test_web.py) enforces it.
 */

import * as std from "std";

const AID = (globalThis.AID = globalThis.AID || {});

let failures = 0;
function ok(cond, msg) {
  if (!cond) { failures++; print("FAIL: " + msg); }
}
function close(a, b, eps, msg) {
  ok(Math.abs(a - b) <= eps, msg + " (" + a + " vs " + b + ")");
}

/* ── load pure modules ───────────────────────────────────────────────── */
std.loadScript("web/app/palette.js");
std.loadScript("web/app/state.js");
std.loadScript("web/app/geo.js");
std.loadScript("web/app/search.js");

/* ── palette ─────────────────────────────────────────────────────────── */
ok(AID.colorOf("cookie") === "#e15759", "palette cookie");
ok(AID.colorOf("unknown_class") === "#777777", "palette fallback");

/* ── store ───────────────────────────────────────────────────────────── */
{
  const st = AID.createStore({ a: 1 });
  let seen = null;
  st.subscribe(s => { seen = s; });
  st.set({ b: 2 });
  ok(seen.a === 1 && seen.b === 2, "store notify carries merged state");
  ok(st.get().b === 2, "store get after set");
}

/* ── geo: partitions and barycentric coordinates ─────────────────────── */
{
  const flourOnly = [[1, 0, 0, 0, 0]];
  const b = AID.bary(flourOnly, "canon2");
  close(b[0], 1, 1e-6, "canon2 flour slot 0");
  close(b[1], 0, 1e-6, "canon2 flour slot 1");
  close(b[2], 0, 1e-6, "canon2 flour slot 2");

  // canonical merge: wet = liquid+egg, rich = fat+sugar; rows sum to 1
  const pound = [[0.25, 0.25, 0.25, 0.125, 0.125]];
  const pb = AID.bary(pound, "canon2");
  close(pb[0], 0.25, 1e-6, "canon2 flour");
  close(pb[1], 0.5, 1e-6, "canon2 wet merged");
  close(pb[2], 0.25, 1e-6, "canon2 rich merged");
  close(pb[0] + pb[1] + pb[2], 1, 1e-6, "canon2 sums to 1");

  // subcomposition: hydration triangle renormalizes over flour+liquid+egg
  const uniform = [[0.2, 0.2, 0.2, 0.2, 0.2]];
  const hb = AID.bary(uniform, "hydration");
  close(hb[0], 1 / 3, 1e-6, "hydration renormalizes slot 0");
  close(hb[1], 1 / 3, 1e-6, "hydration renormalizes slot 1");
  close(hb[2], 1 / 3, 1e-6, "hydration renormalizes slot 2");

  // 1D partitions: group vs complement — the raw share of the whole
  const rb = AID.bary(uniform, "rich");
  close(rb[0], 0.4, 1e-6, "rich share of uniform");
  close(rb[1], 0.6, 1e-6, "rich complement");
  const fb = AID.bary(uniform, "flourAxis");
  close(fb[0], 0.2, 1e-6, "flour share of uniform");

  // 3D partitions
  const cb3 = AID.bary(pound, "canon3");
  close(cb3[0] + cb3[1] + cb3[2] + cb3[3], 1, 1e-6, "canon3 sums to 1");
  close(cb3[3], 0.125, 1e-6, "canon3 sugar slot");
}

/* ── geo: projections ────────────────────────────────────────────────── */
{
  const out = [0, 0];
  AID.project2([1, 0, 0], out);
  close(out[0], AID.TRI2[0][0], 1e-6, "project2 flour vertex x");
  close(out[1], AID.TRI2[0][1], 1e-6, "project2 flour vertex y");
  AID.project2([0, 0.5, 0.5], out);
  close(out[0], (AID.TRI2[1][0] + AID.TRI2[2][0]) / 2, 1e-6, "project2 edge midpoint x");
  close(out[1], (AID.TRI2[1][1] + AID.TRI2[2][1]) / 2, 1e-6, "project2 edge midpoint y");
  AID.project2([1 / 3, 1 / 3, 1 / 3], out);
  close(out[0], 0.5, 1e-6, "project2 centroid x");

  // 3D: vertices project to themselves at zero rotation, and stay in frame
  AID.project3([1, 0, 0, 0], 0, 0, out);
  close(out[0], AID.TET3[0][0], 1e-5, "project3 vertex 0 x (identity)");
  close(out[1], AID.TET3[0][1], 1e-5, "project3 vertex 0 y (identity)");
  AID.project3([0.25, 0.25, 0.25, 0.25], 0.6, 0.35, out);
  ok(out[0] > -1 && out[0] < 2 && out[1] > -1 && out[1] < 2, "project3 centroid bounded");
}

/* ── geo: readout ────────────────────────────────────────────────────── */
{
  ok(AID.DISPLAY_ORDER.join(",") === "0,3,4,1,2", "display order is flour/fat/sugar/liquid/egg");
  ok(AID.readout([1, 0, 0, 0, 0]) === "100 : 0 : 0 : 0 : 0", "readout pure flour");
  const pound = [0.25, 0.25, 0.25, 0.125, 0.125];
  ok(AID.readout(pound) === "100 : 50 : 50 : 100 : 100", "readout pound cake (display order)");
}

/* ── search: normalization, suggestions, query execution ────────────── */
{
  ok(AID.normQuery("Chocolate Chips") === "chocolate chip", "normQuery plural");
  ok(AID.normQuery("berries") === "berry", "normQuery ies");
  ok(AID.normQuery("  Oats  ") === "oat", "normQuery whitespace");

  const data = {
    meta: { n: 5, classes: ["cake", "cookie"] },
    recipes: {
      name: ["Chocolate Cake", "Walnut Cookie", "Plain Cake", "Choc Chunk Cookie", "Bread"],
      cls: ["cake", "cookie", "cake", "cookie", "bread"],
      P: [
        [0.4, 0.2, 0.1, 0.1, 0.2],
        [0.4, 0.1, 0.1, 0.3, 0.1],
        [0.5, 0.2, 0.1, 0.05, 0.15],
        [0.4, 0.1, 0.1, 0.2, 0.2],
        [0.6, 0.3, 0.0, 0.02, 0.08],
      ],
    },
    heads: ["chocolate chips", "walnuts", "yeast"],
    index: { "chocolate chips": [0, 3], "walnuts": [1], "yeast": [4] },
  };

  // suggestions: plural query resolves to the head
  const sugg = AID.suggest("chocolate chips", data);
  ok(sugg.length > 0 && sugg[0].type === "ingredient"
     && sugg[0].head === "chocolate chips" && sugg[0].count === 2,
     "suggest ranks the exact head first");
  const csugg = AID.suggest("cook", data);
  ok(csugg.some(s => s.type === "class" && s.label === "cookie"), "suggest classes");
  const rsugg = AID.suggest("sug", data);
  ok(rsugg.some(s => s.type === "ratio" && s.target.key === undefined && s.target.idx[0] === 4),
     "suggest ratio targets");

  // ingredient OR within group
  let r = AID.runSearch([
    { type: "ingredient", label: "chocolate chips", head: "chocolate chips" },
    { type: "ingredient", label: "walnuts", head: "walnuts" },
  ], data);
  ok(r.count === 3 && r.mask[0] && r.mask[1] && r.mask[3], "ingredient OR group");

  // AND across types: class + ingredient
  r = AID.runSearch([
    { type: "ingredient", head: "chocolate chips", label: "chocolate chips" },
    { type: "class", label: "cookie" },
  ], data);
  ok(r.count === 1 && r.mask[3], "AND across types");

  // keyword
  r = AID.runSearch([{ type: "keyword", label: "cake" }], data);
  ok(r.count === 2 && r.mask[0] && r.mask[2], "keyword substring");

  // ratio range: sugar 16-20% hits recipes 0 and 3 (recipe 2 sits at 15)
  r = AID.runSearch([{ type: "ratio", label: "sugar", target: { idx: [4] }, min: 16, max: 20 }], data);
  ok(r.count === 2 && r.mask[0] && r.mask[3], "ratio range");
  // rich (fat+sugar) merge: recipes 1 and 3 sit at exactly 40%
  r = AID.runSearch([{ type: "ratio", label: "rich", target: { idx: [3, 4] }, min: 40, max: 45 }], data);
  ok(r.count === 2 && r.mask[1] && r.mask[3], "ratio merged target");

  // empty search = everything
  r = AID.runSearch([], data);
  ok(r.mask === null && r.count === 5, "empty search shows all");
}

/* ── grouping edits (divider bar) ────────────────────────────────────── */
{
  const key = g => AID.groupsKey(g);
  const canon2 = [[0], [1, 2], [3, 4]];

  // move fat (3) out of fat+sugar into the flour compartment
  let g = AID.movePart(canon2, 3, 0);
  ok(key(g) === "0+3|1+2|4", "movePart moves a part; siblings stay behind");

  // move the last part out of a compartment -> that compartment disappears
  g = AID.movePart([[3], [4]], 3, -1);
  ok(key(g) === "4", "movePart to rest drops an emptied compartment");

  // move a hidden part back in
  g = AID.movePart([[0], [3, 4]], 1, 0);
  ok(key(g) === "0+1|3+4", "movePart pulls a hidden part into a compartment");

  // merge two arbitrary compartments (one fewer vertex)
  g = AID.mergeGroups(canon2, 1, 2);
  ok(key(g) === "0|1+2+3+4", "mergeGroups combines compartments");

  // merge adjacent by default
  g = AID.mergeGroups([[0], [1], [2], [3]], 2);
  ok(key(g) === "0|1|2+3", "mergeGroups defaults to the next compartment");

  // split: last part of a compartment becomes its own (appended) corner
  g = AID.splitGroup(canon2, 1);
  ok(key(g) === "0|1|3+4|2", "splitGroup adds a divider (one more vertex)");

  // guards
  ok(key(AID.splitGroup([[0], [1]], 1)) === "0|1", "cannot split a lone part");
  ok(key(AID.splitGroup([[0], [1], [2], [3]], 2)) === "0|1|2|3",
     "cannot exceed four compartments");
  ok(key(AID.movePart([[0]], 0, -1)) === "0", "at least one compartment remains");

  // pullOut: any part gets its own new compartment (add divider)
  ok(key(AID.pullOut(canon2, 1)) === "0|2|3+4|1",
     "pullOut gives any part its own compartment");
  ok(key(AID.pullOut([[0], [3, 4]], 1)) === "0|3+4|1",
     "pullOut activates a hidden part");
  ok(key(AID.pullOut([[0], [1], [2], [3]], 4)) === "0|1|2|3",
     "pullOut respects the four-compartment cap");

  // birth parent: the corner a 2D->3D split's apex hides behind
  ok(AID.birthParent(canon2, AID.splitGroup(canon2, 1)) === 1,
     "birthParent finds the split-from corner");
  ok(AID.birthParent(canon2, AID.pullOut(canon2, 4)) === 2,
     "birthParent finds the corner a dragged part left");
  ok(AID.birthParent([[0], [1, 2], [3]], AID.pullOut([[0], [1, 2], [3]], 4)) === null,
     "birthParent is null for a resurrected (rest) part");

  // setBirthAt: a split pins the two untouched corners and hides the apex
  const _tv = [0, 0, 0];
  const _proj = b => { AID.project3(b, 0, 0, _tv); return _tv.slice(); };
  const _uv = s => [0, 1, 2, 3].map(i => (i === s ? 1 : 0));
  for (const _s of [0, 1, 2]) {
    AID.setBirthAt(_s, 1);
    const a = _proj(_uv(3)), x = _proj(_uv(_s));
    ok(Math.hypot(a[0] - x[0], a[1] - x[1]) < 1e-6,
       "setBirthAt hides the apex behind split corner " + _s);
    for (const _k of [0, 1, 2]) {
      if (_k === _s) continue;
      const v = _proj(_uv(_k));
      ok(Math.hypot(v[0] - AID.TRI2[_k][0], v[1] - AID.TRI2[_k][1]) < 1e-6,
         "setBirthAt pins untouched corner " + _k + " (split " + _s + ")");
    }
    AID.setBirthAt(_s, 0);
    ok(AID.TET3.every((v, i) => v.every((c, d) => c === AID.TET3_REGULAR[i][d])),
       "setBirthAt(slot,0) restores the regular tetrahedron");
  }
  AID.setBirthAt(null, 0);
  ok(AID.TET3[3][2] === AID.TET3_REGULAR[3][2] && AID.birthE === 1,
     "setBirthAt(null,0) leaves the regular orientation");
}

/* ── views: painters execute without throwing (stub canvas) ──────────── */
std.loadScript("web/app/views.js");
{
  const vn = 6;
  const vP = [];
  for (let i = 0; i < vn; i++) vP.push([0.4, 0.1 + 0.02 * i, 0.1, 0.2, 0.2 - 0.02 * i]);
  const vcls = ["cake", "cookie", "cake", "cookie", "bread", "pie_pastry"];
  const vdata = {
    meta: { n: vn, classes: ["bread", "cake", "cookie", "pie_pastry"] },
    recipes: { P: vP, cls: vcls, name: vP.map((_, i) => "r" + i) },
    archetypes: [{ name: "pound_cake", P: [0.25, 0, 0.25, 0.25, 0.25] },
                 { name: "bread", P: [0.6, 0.4, 0, 0, 0] }],
  };
  const vstore = AID.createStore({ selection: 2, matches: null });
  const noop = () => {};
  const stubCtx = {};
  for (const m of ["beginPath", "moveTo", "lineTo", "stroke", "fill", "arc", "closePath",
    "fillText", "setLineDash", "clearRect", "setTransform", "fillRect", "save", "restore"]) stubCtx[m] = noop;
  stubCtx.measureText = t => ({ width: String(t).length * 6 });

  function cacheFor(groups) {
    const dim = AID.dimOf(groups);
    const bary = AID.bary(vP, groups);
    const c = {
      key: AID.groupsKey(groups), groups, dim, bary,
      colors: vcls.map(x => AID.colorOf(x)),
      frame: new Float32Array(vn * 2), frameLocked: false,
      updateFrame(rot) {
        const tmp = [0, 0, 0];
        if (this.dim === 2) {
          for (let i = 0; i < vn; i++) {
            AID.project2(this.bary.subarray(i * 3, i * 3 + 3), tmp);
            this.frame[i * 2] = tmp[0]; this.frame[i * 2 + 1] = tmp[1];
          }
        } else if (this.dim === 3) {
          const yaw = rot ? rot[0] : 0.6, pitch = rot ? rot[1] : 0.35;
          for (let i = 0; i < vn; i++) {
            AID.project3(this.bary.subarray(i * 4, i * 4 + 4), yaw, pitch, tmp);
            this.frame[i * 2] = tmp[0]; this.frame[i * 2 + 1] = tmp[1];
          }
        } else {
          for (let i = 0; i < vn; i++) { this.frame[i * 2] = this.bary[i * groups.length]; this.frame[i * 2 + 1] = 0; }
        }
      },
    };
    c.updateFrame(null);
    return c;
  }

  for (const [label, dim, name] of [["1D", 1, "rich"], ["2D", 2, "canon2"], ["3D", 3, "canon3"]]) {
    let err = null;
    try {
      const p = AID["view" + dim](cacheFor(AID.resolveGroups(name)), vdata, vstore);
      p.reset(800, 600);
      p.hover = 1;
      p.draw(stubCtx, 800, 600);
      p.hit(200, 200);
      p.value(0);
    } catch (e) { err = e; }
    ok(!err, label + " painter executes" + (err ? ": " + err : ""));
  }

  // the 2D <-> 3D birth phase must draw without error (the engine owns the
  // frame and only the newborn corner is faded)
  let berr = null;
  try {
    const c = cacheFor(AID.resolveGroups("canon3"));
    c.frameLocked = true;
    c.fade = 0.4;
    const p = AID.view3(c, vdata, vstore);
    p.reset(800, 600);
    AID.setBirthAt(2, 0.4); AID.birthE = 0.4;
    p.draw(stubCtx, 800, 600);
    p.hover = 1;
    p.draw(stubCtx, 800, 600);
  } catch (e) { berr = e; }
  ok(!berr, "3D birth phase draws" + (berr ? ": " + berr : ""));
  AID.setBirthAt(null, 0); AID.birthE = 1;
}

/* ── syntax-parse the DOM modules (no execution under qjs) ───────────── */
for (const f of ["web/app/views.js", "web/app/plot.js", "web/app/searchbar.js", "web/app/legend.js", "web/app/dividerbar.js", "web/app/panel.js", "web/app/main.js"]) {
  let src;
  try {
    src = std.read_file(f);
  } catch (e) {
    // qjs std has no read_file in some builds; fall back to std.loadScript-less read
    src = null;
  }
  if (src === null) {
    const fh = std.popen("cat " + f, "r");
    src = fh.readAsString();
    fh.close();
  }
  let parsed = true;
  try {
    new Function(src);
  } catch (e) {
    parsed = false;
    print("FAIL: syntax error in " + f + ": " + e);
    failures++;
  }
  ok(parsed, "syntax " + f);
}

print(failures === 0 ? "web tests: all green" : "web tests: " + failures + " failures");
if (failures > 0) throw new Error(failures + " web test failures");