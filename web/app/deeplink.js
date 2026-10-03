/* Deep-linkable app state: encode/decode the Aid's view into a URL fragment.
 *
 * Pure and DOM-free (executed by tests/test_web.js): it turns a plain state
 * object into the query string after ``#app?`` and back, and classifies a hash
 * into a view name. url.js owns the history/DOM side.
 *
 * Format — only non-default fields are written, so the common link stays short:
 *   p=<groupsKey>   partition (omit for canonical 2-D)
 *   s=<n>           selected recipe index (omit when none)
 *   f=<kind>:<id>   focused marker, kind "a" (archetype) or "c" (class)
 *   k=<class>       class filter, repeated
 *   q=<json>        search tokens/connectors/ratio overlays, URI-encoded JSON
 *   nb=0 ar=0 ct=0  a display layer turned off
 * Values are encodeURIComponent'd; the groups key's "|" and "+" survive it.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.DEFAULT_PARTITION = "canon2";

  function defaultKey() {
    return AID.groupsKey(AID.PARTITIONS[AID.DEFAULT_PARTITION].groups);
  }

  /* The view a hash names: "app" (with or without params), "about" or "home". */
  AID.hashView = function (hash) {
    const t = String(hash || "").replace(/^#/, "").split(/[?&]/)[0].toLowerCase();
    return t === "app" ? "app" : (t === "about" ? "about" : "home");
  };

  /* State object -> the string after "#app?" ("" when everything is default). */
  AID.encodeAppState = function (st) {
    const parts = [];
    const groups = st.groups || AID.PARTITIONS[AID.DEFAULT_PARTITION].groups;
    const gk = AID.groupsKey(groups);
    if (gk !== defaultKey()) parts.push("p=" + encodeURIComponent(gk));
    if (st.selection != null && st.selection >= 0) parts.push("s=" + st.selection);
    if (st.focus) {
      const kind = st.focus.kind === "archetype" ? "a" : "c";
      parts.push("f=" + encodeURIComponent(kind + ":" + st.focus.id));
    }
    for (const c of st.classFilter || []) parts.push("k=" + encodeURIComponent(c));
    const s = st.search;
    if (s && ((s.t && s.t.length) || (s.e && s.e.length))) {
      parts.push("q=" + encodeURIComponent(JSON.stringify(s)));
    }
    if (st.showNeighbourhood === false) parts.push("nb=0");
    if (st.showArchetypes === false) parts.push("ar=0");
    if (st.showCentroids === false) parts.push("ct=0");
    return parts.join("&");
  };

  /* A hash (app view only) -> a fully-defaulted state object, or null when the
   * hash does not name the app. Tolerant: unknown keys and malformed values are
   * dropped, never thrown. */
  AID.parseAppHash = function (hash) {
    if (AID.hashView(hash) !== "app") return null;
    const rest = String(hash).replace(/^#/, "");
    const qi = rest.indexOf("?");
    const query = qi >= 0 ? rest.slice(qi + 1) : "";
    const out = {
      groups: AID.PARTITIONS[AID.DEFAULT_PARTITION].groups.map(g => g.slice()),
      selection: -1,
      focus: null,
      classFilter: [],
      search: null,
      showNeighbourhood: true,
      showArchetypes: true,
      showCentroids: true,
    };
    if (!query) return out;
    for (const kv of query.split("&")) {
      const eq = kv.indexOf("=");
      const key = eq < 0 ? kv : kv.slice(0, eq);
      let val = eq < 0 ? "" : kv.slice(eq + 1);
      try { val = decodeURIComponent(val); } catch (e) { continue; }
      if (key === "p") {
        const g = AID.parseGroupsKey(val);
        if (g) out.groups = g;
      } else if (key === "s") {
        const n = Number(val);
        if (Number.isInteger(n) && n >= 0) out.selection = n;
      } else if (key === "f") {
        const i = val.indexOf(":");
        if (i > 0) {
          const kind = val.slice(0, i) === "a" ? "archetype" : "class";
          out.focus = { kind, id: val.slice(i + 1) };
        }
      } else if (key === "k") {
        if (val) out.classFilter.push(val);
      } else if (key === "q") {
        try { out.search = JSON.parse(val); } catch (e) { /* ignore */ }
      } else if (key === "nb") {
        out.showNeighbourhood = val !== "0";
      } else if (key === "ar") {
        out.showArchetypes = val !== "0";
      } else if (key === "ct") {
        out.showCentroids = val !== "0";
      }
    }
    return out;
  };
})();
