---
name: spec
description: Contrato da feature 0012 — interface em MUI (Material UI) em todas as telas e elementos, por ilhas React que "elevam" o HTML do servidor. Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Interface com MUI em todas as telas

> **Fonte da verdade.** Status: aprovado · implementado (aguardando UAT visual)
> Os `AC-N` desta spec são numerados a partir de 1. Decisão e alternativas em `design.md` e **ADR-0015**.

## Resumo
O servidor continua renderizando HTML (Django) com os mesmos formulários, rotas, CSRF e textos. Um bundle JS (`static/dist/js/mui.js`) **eleva** esse HTML para componentes MUI: botões, campos, caixas de seleção, cartões, chips, alertas, tabelas, ícones, avatares, barras de progresso, passos (Stepper), diálogo de confirmação, e o shell (menu lateral e barra superior). O tema é escuro/claro (alternável) com o laranja atual.

## Critérios de aceite

### AC-1: Bundle carregado em todas as telas
- **Dado** qualquer página do sistema (login, seleção de perfil, wizard e telas internas)
- **Quando** o HTML é servido
- **Então** carrega `dist/js/mui.js` antes de `app.js` e `ai-image.js`

### AC-2: HTML do servidor continua sendo a fonte
- **Dado** uma tela com formulário
- **Quando** o JavaScript está indisponível
- **Então** a página continua funcional (mesmos formulários, nomes de campos, CSRF e rotas), apenas sem o visual MUI

### AC-3: Controles viram componentes MUI
- **Dado** botões (`.btn`), campos (`input/textarea/select.input`), caixas (`checkbox`), selos (`.badge`), cartões (`.card`), tabelas, alertas e ícones
- **Quando** a página carrega
- **Então** cada um é renderizado por um componente MUI, preservando `id`, `name`, valor, `disabled`, `hidden`, `data-*` e o envio nativo do formulário

### AC-4: Shell em MUI
- **Dado** uma tela interna
- **Quando** abre
- **Então** o menu lateral (mini no desktop, gaveta no celular) e a barra superior (perfil ativo, tema, usuário, sair) são MUI e mantêm as mesmas rotas e o POST de logout com CSRF

### AC-5: Confirmação em diálogo
- **Dado** um formulário com `data-confirm`
- **Quando** o usuário envia
- **Então** abre um Dialog MUI com a mensagem; confirmar envia, cancelar não envia

### AC-6: Tema escuro/claro
- **Dado** o botão de tema
- **Quando** alternado
- **Então** todos os componentes MUI trocam junto com o restante da página; as telas de perfil e o painel de marca do login ficam sempre escuros

### AC-7: Telas de perfil e wizard
- **Dado** a seleção de perfil e o wizard (spec 0011)
- **Quando** abrem
- **Então** usam Avatar/Card/Stepper MUI, com os mesmos formulários e rotas

### AC-8: Imagem de produção contém o bundle
- **Dado** o build Docker
- **Quando** a imagem é construída
- **Então** `npm run build` gera o CSS, os vendors e o `mui.js`, e o `collectstatic` o publica

## Fora de escopo (vinculante)
- SPA/React Router; reescrever views em API JSON.
- Substituir `<input type="file">` e `<details>` (permanecem nativos, estilizados pelo tema).
- Testes de interface em navegador automatizado na CI (verificação visual manual no UAT).
