/* The store — one source of truth, one-way flow: events -> state -> redraw.
 *
 * State: { view, partition, selection, hover } with view in {1, 2, 3} and
 * partition a geo.PARTITIONS key. Subscribers are called on every set().
 */
(function () {
  "use strict";
  const AID = (globalThis.AID = globalThis.AID || {});

  AID.createStore = function (initial) {
    let state = initial;
    const subs = [];
    return {
      get: () => state,
      set(patch) {
        state = Object.assign({}, state, patch);
        for (const f of subs) f(state);
      },
      subscribe(f) { subs.push(f); },
    };
  };
})();