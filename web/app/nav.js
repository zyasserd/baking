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
      try {
        if (history.replaceState) {
          history.replaceState(null, "", which === "home" ? "#" : "#" + which);
        }
      } catch (err) { /* file:// without history: views still switch */ }
    });
  });

  window.addEventListener("hashchange", () => {
    if (location.hash === "#about") switchTo(about, "about");
    else if (location.hash === "#app") switchTo(app, "app");
    else if (location.hash === "#home") switchTo(home, "home");
  });

  if (location.hash === "#about") switchTo(about, "about");
  else if (location.hash === "#app") switchTo(app, "app");
  else switchTo(home, "home");
})();
