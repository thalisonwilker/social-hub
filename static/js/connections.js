/* Central de conexões (spec 0017): troca de rede e de conta sem recarregar; sem JS, os ícones são links ?rede=. */
(function () {
  "use strict";

  var hub = document.querySelector("[data-hub]");
  if (!hub) return;

  // Ativa uma aba de um tablist: aria-selected, tabindex itinerante e o painel ligado por aria-controls.
  function activate(tabs, tab) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.setAttribute("tabindex", on ? "0" : "-1");
      var panel = document.getElementById(t.getAttribute("aria-controls"));
      if (panel) panel.hidden = !on;
    });
  }

  // Setas/Home/End movem o foco; Enter/Espaço selecionam (AC-13).
  function keyboard(tabs, onSelect) {
    tabs.forEach(function (tab, i) {
      tab.addEventListener("keydown", function (event) {
        var next = null;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
        else if (event.key === "ArrowUp" || event.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
        else if (event.key === "Home") next = tabs[0];
        else if (event.key === "End") next = tabs[tabs.length - 1];
        else if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(tab);
          return;
        }
        if (next) {
          event.preventDefault();
          next.focus();
        }
      });
      tab.addEventListener("click", function (event) {
        event.preventDefault();
        onSelect(tab);
      });
    });
  }

  // Redes (AC-5)
  var netTabs = Array.prototype.slice.call(hub.querySelectorAll("[data-hub-tab]"));
  keyboard(netTabs, function (tab) {
    if (tab.getAttribute("aria-selected") === "true") return;
    activate(netTabs, tab);
    tab.focus();
    try {
      var url = new URL(window.location.href);
      url.searchParams.set("rede", tab.getAttribute("data-hub-tab"));
      window.history.replaceState(null, "", url);
    } catch (e) { /* URL/History indisponível: a troca já aconteceu */ }
  });

  // Contas da mesma rede (AC-7)
  hub.querySelectorAll("[data-hub-account-list]").forEach(function (list) {
    var tabs = Array.prototype.slice.call(list.querySelectorAll("[data-hub-account]"));
    keyboard(tabs, function (tab) {
      activate(tabs, tab);
      tab.focus();
    });
  });

  // Avatar que não carrega (URL expirada da Meta) → ícone da rede.
  hub.querySelectorAll("[data-hub-avatar]").forEach(function (img) {
    var box = img.parentNode;
    function fallback() {
      img.remove();
      var icon = box.querySelector("[data-hub-avatar-fallback]");
      if (icon) icon.hidden = false;
    }
    if (img.complete && img.naturalWidth === 0) fallback();
    else img.addEventListener("error", fallback);
  });
})();
