/* Public header behaviour: scrolled surface, active section, mobile drawer.
 *
 * No dependency added for any of it. Three small pieces, each of which
 * degrades to something usable if scripting fails: without JS the bar is
 * still sticky and readable, the links still navigate, and the drawer's
 * contents are still in the DOM behind a button that simply does nothing
 * rather than a menu that traps you.
 */
(function () {
  "use strict";

  var header = document.getElementById("sb-header");
  if (!header) { return; }

  var reduced = window.matchMedia
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* --- 1. denser surface after a little scrolling ----------------------- */
  var SCROLL_AT = 24;
  var lastState = null;
  function paintScroll() {
    // Written straight from the scroll handler rather than inside
    // requestAnimationFrame: rAF does not run in a hidden or background
    // tab, so the frame-scheduled version left the header in its
    // top-of-page state until the tab was looked at. This reads one
    // number and writes one attribute - there is no layout to batch.
    var state = window.scrollY > SCROLL_AT ? "true" : "false";
    if (state !== lastState) {
      header.dataset.scrolled = state;
      lastState = state;
    }
  }
  window.addEventListener("scroll", paintScroll, {passive: true});
  paintScroll();

  /* --- 2. active section ------------------------------------------------ */
  var sectionLinks = [].slice.call(header.querySelectorAll(".sbh-link[data-section]"));
  var byId = {};
  var targets = [];
  sectionLinks.forEach(function (link) {
    var el = document.getElementById(link.dataset.section);
    if (el) { byId[link.dataset.section] = link; targets.push(el); }
  });

  function markActive(id) {
    sectionLinks.forEach(function (link) {
      link.setAttribute("aria-current", link.dataset.section === id ? "true" : "false");
    });
  }

  /* Of the markers inside the band, the lowest one is the section the
     reader has most recently entered. Split out and exposed as a test
     seam: IntersectionObserver does not deliver callbacks in a hidden
     tab, so the choice itself has to be checkable without one. */
  function pickActive(list, inBand, rectOf) {
    rectOf = rectOf || function (el) { return el.getBoundingClientRect(); };
    var best = null, bestTop = -Infinity;
    list.forEach(function (el) {
      if (!inBand[el.id]) { return; }
      var top = rectOf(el).top;
      if (top > bestTop) { bestTop = top; best = el.id; }
    });
    return best;
  }
  window.SBHeader = {pickActive: pickActive};

  if (targets.length && "IntersectionObserver" in window) {
    // isIntersecting, not intersectionRatio: the anchors are zero-height
    // markers placed above each section so nothing below the header had to
    // be restyled, and a zero-area box always reports a ratio of 0 - which
    // silently meant "no section is ever current".
    var inBand = {};
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        inBand[entry.target.id] = entry.isIntersecting;
      });
      markActive(pickActive(targets, inBand));
    }, {
      // The bar covers the top of the viewport, so a section counts as
      // current once its marker has passed under the bar and before it
      // leaves through the top.
      rootMargin: "-90px 0px -45% 0px",
      threshold: 0,
    });
    targets.forEach(function (el) { observer.observe(el); });
  }

  /* --- 3. mobile drawer ------------------------------------------------- */
  var drawer = document.getElementById("sb-header-drawer");
  var burger = document.getElementById("sb-header-burger");
  var closeBtn = document.getElementById("sb-header-close");
  if (!drawer || !burger) { return; }

  var lastFocus = null;
  var FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea';

  function focusables() {
    return [].slice.call(drawer.querySelectorAll(FOCUSABLE))
      .filter(function (el) { return el.offsetParent !== null; });
  }

  function openDrawer() {
    lastFocus = document.activeElement;
    drawer.hidden = false;
    document.body.classList.add("sbh-locked");
    burger.setAttribute("aria-expanded", "true");
    var first = focusables()[0];
    if (first) { first.focus(); }
    document.addEventListener("keydown", onKeydown, true);
  }

  function closeDrawer() {
    drawer.hidden = true;
    document.body.classList.remove("sbh-locked");
    burger.setAttribute("aria-expanded", "false");
    document.removeEventListener("keydown", onKeydown, true);
    // Back where it came from, and the burger as the floor: closing with
    // focus on <body> would drop a keyboard user at the top of the
    // document with no idea where the menu went.
    var back = (lastFocus && lastFocus.focus && lastFocus !== document.body)
      ? lastFocus : burger;
    if (back && back.focus) { back.focus(); }
  }

  function onKeydown(e) {
    var key = e.key || "";
    if (key === "Escape") { e.preventDefault(); closeDrawer(); return; }
    if (key !== "Tab") { return; }
    // Trap: wrap at both ends so focus cannot leave an open drawer.
    var items = focusables();
    if (!items.length) { return; }
    var first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault(); first.focus();
    }
  }

  burger.addEventListener("click", function () {
    if (drawer.hidden) { openDrawer(); } else { closeDrawer(); }
  });
  if (closeBtn) { closeBtn.addEventListener("click", closeDrawer); }
  drawer.addEventListener("click", function (e) {
    if (e.target === drawer) { closeDrawer(); }   // tap the backdrop
  });
  // Choosing a destination closes it, including a same-page anchor, which
  // navigates nothing and would otherwise leave the panel over the section
  // it just scrolled to.
  drawer.addEventListener("click", function (e) {
    var link = e.target.closest && e.target.closest("a[href]");
    if (link) { closeDrawer(); }
  });
  // Growing past the breakpoint with the drawer open would leave the page
  // scroll-locked behind a panel nobody can see.
  window.addEventListener("resize", function () {
    if (!drawer.hidden && window.innerWidth >= 1024) { closeDrawer(); }
  });

  if (reduced) { header.style.transition = "none"; }
})();
