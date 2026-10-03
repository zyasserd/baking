/* Deep-link wiring: keep ``location.hash`` and the store in step.
 *
 * The hash is a shareable/citable snapshot of the app view: partition,
 * selected recipe, focused marker, class filter, search query and the display
 * toggles (see deeplink.js for the format). State changes write a new history
 * entry (debounced) so Back/Forward walk the view; the browser's Back/Forward
 * re-applies the hash to the store.
 *
 * Programmatic writes use history.pushState (not location.hash =) on purpose:
 * that does not fire hashchange, so restoring never re-enters here mid-typing
 * and never steals focus from the search field.
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.attachUrl = function (store, data, ctx) {
    const search = ctx.search;
    let applying = false;
    let timer = 0;

    function snapshot() {
      const st = store.get();
      return {
        groups: st.groups,
        selection: st.selection,
        focus: st.focus,
        classFilter: st.classFilter || [],
        search: search ? search.getState() : null,
        showNeighbourhood: st.showNeighbourhood,
        showArchetypes: st.showArchetypes,
        showCentroids: st.showCentroids,
      };
    }

    /* The hash naming a view, with the current app state for "app". nav.js
     * calls this so switching back to the app restores what was there. */
    AID.hashFor = function (view) {
      if (view === "about") return "#about";
      if (view !== "app") return "#";
      const params = AID.encodeAppState(snapshot());
      return params ? "#app?" + params : "#app";
    };

    function apply(state) {
      applying = true;
      try {
        store.set({
          partition: AID.groupsKey(state.groups),
          groups: state.groups,
          classFilter: state.classFilter || [],
          showNeighbourhood: state.showNeighbourhood,
          showArchetypes: state.showArchetypes,
          showCentroids: state.showCentroids,
        });
        if (search) search.setState(state.search || { t: [], c: [], e: [] });
        store.set({ selection: state.selection, focus: state.focus });
        if (ctx.syncToggles) ctx.syncToggles();
      } finally {
        applying = false;
      }
    }

    function applyFromHash() {
      if (AID.hashView(location.hash) !== "app") return;
      const state = AID.parseAppHash(location.hash);
      if (state) apply(state);
    }

    /* Push the current state into history, unless we are already restoring one
     * (apply) or the app is not the visible view. Coalesces quick edits. */
    function schedule() {
      if (applying) return;
      if (AID.hashView(location.hash) !== "app") return;
      const h = AID.hashFor("app");
      if (h === location.hash) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        try {
          history.pushState(null, "", h);
        } catch (e) {
          try { history.replaceState(null, "", h); } catch (e2) { /* file:// */ }
        }
      }, 250);
    }

    store.subscribe(schedule);
    window.addEventListener("popstate", applyFromHash);
    window.addEventListener("hashchange", applyFromHash);
    applyFromHash();
    return { applyFromHash };
  };
})();
