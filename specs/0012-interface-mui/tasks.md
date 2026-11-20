---
name: tasks
description: Decomposição e gates da feature 0012 — interface MUI (toolchain, tema, elevador de componentes, shell, telas, build).
alwaysApply: false
---

# Tasks — Interface com MUI

| #  | Task | Cobre AC | Depende de | Gate (comando) | Status |
|----|------|----------|------------|----------------|--------|
| 1  | Toolchain: esbuild + React + MUI + Emotion, script `build:js`, tema | AC-1, AC-6, AC-8 | — | `npm run build` | done |
| 2  | Elevador genérico (botão, campo, caixa, selo, cartão, tabela, alerta, ícone) e diálogo de confirmação | AC-2, AC-3, AC-5 | 1 | `npm run build` + `… test apps.social.tests.test_mui` | done |
| 3  | Shell MUI (menu lateral e barra superior) | AC-4 | 2 | `… test apps.social.tests.test_mui` | done |
| 4  | Telas de perfil, wizard e login (Stepper, Avatar, tiles) | AC-7 | 2, 3 | `… test apps.social.tests.test_mui` | done |
| 5  | Docs (ADR-0015, README, STATE, glossário), Dockerfile e regressão total | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8 | 1–4 | `… test` + build Docker | done |
