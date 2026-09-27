// Side menu: collapsible to icons, resizable by dragging its edge, a drawer on phones.
// Loaded in <head> (the CSP allows no inline script), so the saved mode applies before first paint.
(function () {
  var root = document.documentElement;
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };
  if (store.get("vinot.side") === "mini") root.classList.add("side-mini");
  var w = parseInt(store.get("vinot.sideW"), 10);
  if (w >= 200 && w <= 360) root.style.setProperty("--side-w", w + "px");

  function phone() { return window.matchMedia("(max-width: 900px)").matches; }
  function setMini(on) {
    root.classList.toggle("side-mini", on);
    store.set("vinot.side", on ? "mini" : "full");
  }
  function saveSections() {
    var closed = [].slice.call(document.querySelectorAll(".side-sec:not([open])")).map(function (d) { return d.dataset.sec; });
    store.set("vinot.sections", closed.join(","));
  }

  document.addEventListener("DOMContentLoaded", function () {
    var closed = (store.get("vinot.sections") || "").split(",");
    document.querySelectorAll(".side-sec").forEach(function (d) {
      // the section holding the current page always starts open
      if (closed.indexOf(d.dataset.sec) >= 0 && !d.querySelector("a.active")) d.open = false;
      d.addEventListener("toggle", saveSections);
    });

    var handle = document.getElementById("side-resize");
    if (handle) {
      handle.addEventListener("pointerdown", function (e) {
        if (phone() || root.classList.contains("side-mini")) return;
        e.preventDefault();
        handle.setPointerCapture(e.pointerId);
        root.classList.add("side-resizing");
        function move(ev) {
          var nw = Math.max(200, Math.min(360, ev.clientX));
          root.style.setProperty("--side-w", nw + "px");
        }
        function up() {
          root.classList.remove("side-resizing");
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", up);
          store.set("vinot.sideW", parseInt(getComputedStyle(root).getPropertyValue("--side-w"), 10));
        }
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", up);
      });
      handle.addEventListener("dblclick", function () {
        root.style.removeProperty("--side-w");
        store.set("vinot.sideW", "");
      });
    }
  });

  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t.closest("#side-toggle")) {
      if (phone()) document.body.classList.toggle("side-open");
      else setMini(!root.classList.contains("side-mini"));
    } else if (t.closest("#side-collapse")) {
      setMini(!root.classList.contains("side-mini"));
    } else if (t.closest("#side-shade") || (phone() && t.closest(".side a"))) {
      document.body.classList.remove("side-open");
    } else if (t.closest("[data-sections]")) {
      var open = t.closest("[data-sections]").dataset.sections === "open";
      document.querySelectorAll(".side-sec").forEach(function (d) { d.open = open; });
      saveSections();
    } else if (t.closest(".side-mini .side-sec > summary")) {
      e.preventDefault();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") document.body.classList.remove("side-open");
  });
})();
document.addEventListener("click", function (e) {
  var b = e.target.closest("[data-copy]");
  if (!b) return;
  var input = document.getElementById(b.dataset.copy);
  input.select();
  var done = function () { var t = b.textContent; b.textContent = "Copiado!"; setTimeout(function () { b.textContent = t; }, 1500); };
  if (navigator.clipboard) navigator.clipboard.writeText(input.value).then(done, function () { document.execCommand("copy"); done(); });
  else { document.execCommand("copy"); done(); }
});
