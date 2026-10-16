/* MarketPulse theme switch (light / dark).
 *
 * The whole palette lives in CSS custom properties keyed off a `data-theme` attribute on <html>,
 * so a themed page needs no JavaScript to paint. This file is loaded in <head> — blocking, but
 * about 1 KB — so the attribute is set before the first paint and the page never flashes the
 * wrong theme. The retailer's choice is remembered; until they make one, we follow the OS.
 */
(function () {
  "use strict";

  var KEY = "mp_theme";
  var root = document.documentElement;

  function systemTheme() {
    try { return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
    catch (_) { return "light"; }
  }
  function stored() {
    try { return localStorage.getItem(KEY); } catch (_) { return null; }  // private mode
  }
  function save(v) { try { localStorage.setItem(KEY, v); } catch (_) { /* private mode */ } }

  function apply(theme) { root.setAttribute("data-theme", theme); }

  /* The button is icon-only, so its accessible name comes from the string table. */
  function syncLabel() {
    var btn = document.getElementById("btn-theme");
    if (!btn) return;
    var sel = document.getElementById("lang");
    var table = (window.I18N && window.I18N[(sel && sel.value) || root.lang || "en"]) || {};
    var label = table.theme_toggle || "Switch theme";
    btn.setAttribute("aria-label", label);
    btn.setAttribute("title", label);
  }

  apply(stored() || systemTheme());

  document.addEventListener("DOMContentLoaded", function () {
    syncLabel();
    var btn = document.getElementById("btn-theme");
    if (btn) {
      btn.addEventListener("click", function () {
        var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
        save(next);
        apply(next);
      });
    }
    var sel = document.getElementById("lang");
    if (sel) sel.addEventListener("change", syncLabel);

    // Follow the OS while the retailer has not picked a theme themselves.
    try {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
        if (!stored()) apply(systemTheme());
      });
    } catch (_) { /* older engines */ }
  });
})();
