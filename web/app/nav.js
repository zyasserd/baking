/* Site navigation: stacked full-screen views (landing, app, about).
 *
 * The landing and the app are separate layers, not a scrolling page. Choosing
 * "app" animates the landing away and the app up over it; once you are in the
 * app there is no scroll back to the landing. About is its own layer and
 * scrolls internally. The hash keeps #app / #about linkable.
 */
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  const home = document.getElementById("view-home");
  const app = document.getElementById("app");
  const about = document.getElementById("view-about");
  if (!home || !app || !about) return;

  const reduce = window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const DUR = reduce ? 0 : 520;

  // start on the landing; the other layers are off
  about.hidden = true;
  app.hidden = true;
  home.hidden = false;
  let active = home;
  let zTop = 3;
  home.style.zIndex = "1";
  app.style.zIndex = "2";
  about.style.zIndex = "3";

  function setNav(which) {
    // The main link is a toggle: "app" on the landing, "home" in the app.
    const navMain = document.getElementById("nav-main");
    if (navMain) {
      const inApp = which !== "home";
      navMain.textContent = inApp ? "home" : "app";
      navMain.setAttribute("data-nav", inApp ? "home" : "app");
    }
    document.querySelectorAll("[data-nav]").forEach(a =>
      a.classList.toggle("active", a.getAttribute("data-nav") === which));
  }

  function viewFor(which) {
    return which === "about" ? about : (which === "home" ? home : app);
  }

  /* The view named by a hash, ignoring any app-state query (e.g. "#app?p=…"). */
  function viewToken(hash) {
    if (AID.hashView) return AID.hashView(hash);
    const t = String(hash || "").replace(/^#/, "").split(/[?&]/)[0].toLowerCase();
    return t === "app" ? "app" : (t === "about" ? "about" : "home");
  }

  function switchTo(next, which) {
    if (next === active) { setNav(which); return; }
    const prev = active;
    next.hidden = false;
    next.style.zIndex = String(++zTop); // the entering layer is always on top
    next.classList.remove("leave");
    next.classList.add("enter");
    void next.offsetWidth; // flush the start state so the transition runs
    next.classList.remove("enter");
    prev.classList.add("leave");
    active = next;
    setNav(which);
    if (next === about) next.scrollTop = 0;
    window.setTimeout(() => {
      if (prev === active) return; // switched again meanwhile
      prev.hidden = true;
      prev.classList.remove("leave");
    }, DUR);
  }

  document.querySelectorAll("[data-nav]").forEach(a => {
    a.addEventListener("click", e => {
      e.preventDefault();
      const which = a.getAttribute("data-nav");
      switchTo(viewFor(which), which);
      // A real hash assignment pushes history, so Back returns to the view you
      // came from. For "app" the current app state (partition, selection,
      // search…) is folded in, so leaving and returning does not lose it.
      try {
        location.hash = AID.hashFor
          ? AID.hashFor(which)
          : (which === "home" ? "#" : "#" + which);
      } catch (err) { /* file:// without history: views still switch */ }
    });
  });

  window.addEventListener("hashchange", () => {
    const which = viewToken(location.hash);
    switchTo(viewFor(which), which);
  });

  switchTo(viewFor(viewToken(location.hash)), viewToken(location.hash));
})();
