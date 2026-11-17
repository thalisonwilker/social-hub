/* Social Hub — comportamento da interface (JavaScript puro, sem dependências além do Lucide). */
(function () {
  "use strict";

  var root = document.documentElement;

  // Tema: o estado inicial é aplicado por um script inline no <head> (evita "flash").
  function setTheme(theme) {
    root.classList.toggle("dark", theme === "dark");
    try { localStorage.setItem("theme", theme); } catch (e) { /* armazenamento indisponível */ }
  }

  document.addEventListener("click", function (event) {
    var themeBtn = event.target.closest("[data-theme-toggle]");
    if (themeBtn) {
      setTheme(root.classList.contains("dark") ? "light" : "dark");
      return;
    }

    var openBtn = event.target.closest("[data-sidebar-open]");
    if (openBtn) { toggleSidebar(true); return; }
    if (event.target.closest("[data-sidebar-close]")) { toggleSidebar(false); return; }

    var dismiss = event.target.closest("[data-dismiss]");
    if (dismiss && dismiss.parentElement) { dismiss.parentElement.remove(); }
  });

  // Sidebar em modo "gaveta" no mobile.
  function toggleSidebar(open) {
    var sidebar = document.getElementById("sidebar");
    var backdrop = document.getElementById("sidebar-backdrop");
    if (!sidebar || !backdrop) return;
    sidebar.classList.toggle("-translate-x-full", !open);
    backdrop.classList.toggle("hidden", !open);
    document.body.classList.toggle("overflow-hidden", open);
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") toggleSidebar(false);
  });

  // Ícones Lucide: converte <i data-lucide="..."> em SVG.
  if (window.lucide) window.lucide.createIcons();
})();
