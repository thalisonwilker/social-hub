// Infraestrutura comum: provedores (tema + Emotion), montagem no lugar do elemento original e utilitários de DOM.
import React, { useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { StyledEngineProvider, ThemeProvider } from "@mui/material/styles";
import { getTheme } from "./theme.js";

const subscribe = (cb) => {
  const observer = new MutationObserver(cb);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
};
const currentMode = () => (document.documentElement.classList.contains("dark") ? "dark" : "light");

export function useMode(forceDark = false) {
  const mode = useSyncExternalStore(subscribe, currentMode, () => "light");
  return forceDark ? "dark" : mode;
}

export function Providers({ forceDark, children }) {
  const mode = useMode(forceDark);
  return (
    <StyledEngineProvider injectFirst>
      <ThemeProvider theme={getTheme(mode)}>{children}</ThemeProvider>
    </StyledEngineProvider>
  );
}

// Classes que o Tailwind usava para o visual dos controles: saem (o MUI cuida); o resto (layout) é mantido.
const COMPONENT_CLASS = /^(card|card-title|btn|btn-primary|btn-ghost|input|label|badge|badge-ok|badge-warn|badge-danger|shadow(-.*)?|rounded(-.*)?|border(-.*)?|bg-.*|px-.*|py-.*|text-(xs|sm|base|lg|xl|\dxl|muted|fg|accent|ok|warn|danger|accent-fg|white|zinc-.*)|font-.*|hover:.*|accent-accent|cursor-.*|transition.*)$/;

export function layoutClass(el, extraDrop) {
  return [...el.classList]
    .filter((c) => !COMPONENT_CLASS.test(c))
    .filter((c) => !(extraDrop && extraDrop.test(c)))
    .join(" ");
}

export function copyAttrs(from, to, skip = []) {
  for (const attr of Array.from(from.attributes)) {
    if (attr.name === "class" || attr.name === "style" || skip.includes(attr.name)) continue;
    try { to.setAttribute(attr.name, attr.value); } catch (e) { /* atributo inválido: ignora */ }
  }
}

export function moveChildren(from, to, filter) {
  Array.from(from.childNodes).forEach((node) => {
    if (filter && !filter(node)) { node.remove(); return; }
    to.appendChild(node);
  });
}

/** Callback de ref que move os filhos do elemento original para o nó React (uma única vez). */
export const mover = (el, filter) => (node) => {
  if (node && !node.__moved) { node.__moved = true; moveChildren(el, node, filter); }
};

/** Substitui `el` por um contêiner e renderiza `node` (componente MUI) nele, de forma síncrona. */
export function mount(el, node) {
  const forceDark = !!el.closest('[data-mui-theme="dark"]');
  const parent = el.parentElement;
  el.__parent = parent; // o original sai do DOM: os componentes consultam o pai por aqui
  const host = document.createElement("div");
  host.setAttribute("data-mui-host", "");
  // Pais com `space-*`/`divide-*` aplicam margem/borda ao filho direto: o contêiner precisa ter caixa.
  host.style.display = parent && /\b(space-|divide-)/.test(parent.className) ? "flex" : "contents";
  if (host.style.display === "flex") host.style.flexDirection = "column";
  el.replaceWith(host);
  const root = createRoot(host);
  flushSync(() => root.render(<Providers forceDark={forceDark}>{node}</Providers>));
  return host;
}

export function mountFixed(node, forceDark = false) {
  const host = document.createElement("div");
  host.setAttribute("data-mui-host", "");
  host.style.display = "contents";
  document.body.appendChild(host);
  flushSync(() => createRoot(host).render(<Providers forceDark={forceDark}>{node}</Providers>));
}

export function iconSize(el) {
  const match = /\b(?:h|w)-\[?([\d.]+)(px)?\]?/.exec(el.className);
  return match ? (match[2] ? Number(match[1]) : Number(match[1]) * 4) : 20;
}
