---
name: ADR-0015
description: Interface em MUI (React) sobre templates Django — bundle esbuild que eleva o HTML do servidor a componentes MUI, em vez de SPA.
alwaysApply: false
---

# ADR-0015: Interface MUI por ilhas que elevam o HTML do servidor

- **Status:** aceito
- **Data:** 2026-11-18
- **Decisores:** Thalyson

## Contexto
Pedido: usar o MUI em todas as telas e elementos. O MUI exige React; o Hub é Django com templates, formulários nativos com CSRF, OAuth por redirecionamento e ~840 testes que validam o HTML do servidor.

## Decisão
- Adicionar um **bundle React + MUI** (esbuild) que, no carregamento, **eleva** elementos do HTML do servidor a componentes MUI, preservando atributos, filhos e envio nativo dos formulários. Shell (menu e barra) e telas de perfil usam componentes dedicados.
- **Tema** MUI claro/escuro com o laranja atual, sincronizado com a classe `dark`.
- Tailwind fica só como utilitário de layout.
- **Descartado:** SPA completa (reescreve views, OAuth e a maior parte dos testes; sem ganho de funcionalidade) e "só visual Material sem React" (não é o MUI).

## Consequências
- Visual 100% MUI sem mexer em rotas, views nem testes; o HTML do servidor é o fallback sem JS.
- Novo estágio de build (npm: react, react-dom, @mui/material, @mui/icons-material, @emotion/*, esbuild) e ~+400 KB de JS (minificado).
- Há uma camada de "elevação" a manter: novos elementos precisam das classes/atributos que o elevador reconhece (ver `design.md`).
- `<input type=file>` e `<details>` ficam nativos.
