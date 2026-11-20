---
name: design
description: Technical Design Doc da feature 0012 — como o MUI (React) entra num front Django com templates: bundle esbuild, "elevador" de elementos HTML para componentes MUI, shell, tema e riscos.
alwaysApply: false
---

# Technical Design Doc — Interface com MUI

> **Tier:** arquitetural · **Status:** aprovado · **Data:** 2026-11-18 · Decisão: **ADR-0015**.

## Problema
O MUI é React; o Hub é Django + templates + Tailwind, com ~840 testes que validam o HTML do servidor, formulários nativos com CSRF e scripts que ligam eventos por `id`.

## Abordagem: ilhas que elevam o HTML do servidor
1. **Bundle único** (`frontend/mui/index.jsx` → esbuild → `static/dist/js/mui.js`), carregado antes de `app.js`.
2. **Elevador**: ao carregar, varre o DOM e, para cada elemento-alvo, monta um componente MUI num contêiner (`display: contents`, ou `block` se o pai usa `space-*`/`divide-*`) que substitui o original. O componente recebe o elemento original, **copia seus atributos** (`id`, `name`, `data-*`, `aria-*`, `hidden`…) para o nó MUI equivalente e **move os filhos** originais para dentro. O formulário continua nativo (o botão MUI é um `<button type=submit>`).
3. **Shell** (`#sidebar`, `header`) lê o próprio HTML de fallback (links, ícones, título, perfil, CSRF do logout) e renderiza `Drawer`/`AppBar`.
4. **Tema** MUI (claro/escuro) sincronizado com a classe `dark` do `<html>`; regiões `data-mui-theme="dark"` ficam sempre escuras.
5. **Ícones**: `<i data-lucide>` → `@mui/icons-material` por mapa; ícones sem mapa ficam com Lucide.
6. **Tailwind permanece só para layout** (grid, flex, espaçamento); o visual dos controles é do MUI.

## Mapeamento
| HTML | MUI |
|---|---|
| `.btn`, `.btn-primary`, `.btn-ghost` | `Button` (outlined/contained/text) |
| `input/textarea/select.input` | `TextField` (select nativo) |
| `input[type=checkbox]` | `Checkbox` |
| `.badge` | `Chip` |
| `.card`, tabelas | `Paper`, `Table` |
| `[role=status|alert]` com `border-l-*` | `Alert` |
| `[data-mui=stepper|tile|avatar|progress]` | `Stepper`, `Card`/`CardActionArea`, `Avatar`, `LinearProgress` |
| `data-confirm` | `Dialog` |

## Riscos e mitigação
- **Listeners por elemento perdidos:** o bundle roda antes dos demais scripts e preserva `id`/`data-*`; os scripts existentes usam `id` ou delegação.
- **Estilo Tailwind × MUI:** Emotion com `injectFirst`; sem `CssBaseline` (o preflight do Tailwind já normaliza).
- **JS desligado:** o HTML do servidor segue funcional (AC-2).
- **Peso:** ícones importados individualmente; bundle minificado.
