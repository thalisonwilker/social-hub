---
name: tasks
description: Decomposição e gates da feature 0011 — perfis, seleção, wizard e login.
alwaysApply: false
---

# Tasks — Perfis, seleção de perfil e wizard

> Comando-base: `.venv/bin/python manage.py test <módulo>`. Testes em `apps/social/tests/test_profiles.py`, `test_AC_N_*`.

## Plano
| #  | Task | Cobre AC | Depende de | Gate (comando) | Status |
|----|------|----------|------------|----------------|--------|
| 1  | Modelo `Profile`, `SocialAccount.profile`, migration com backfill "Principal", serviço de perfil ativo | AC-10, AC-11 | — | `… test apps.social.tests.test_profiles` | done |
| 2  | Views/rotas: seleção, entrar, wizard (nome, conectar), vínculo das contas e retorno ao dashboard | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-11 | 1 | `… test apps.social.tests.test_profiles` | done |
| 3  | Escopo por perfil (contas, dashboard, destinos) e exigência de perfil ativo | AC-8, AC-9 | 1, 2 | `… test apps.social.tests.test_profiles` | done |
| 4  | Telas: seleção, wizard, novo login, chip do perfil no header; build do CSS | AC-2, AC-5, AC-12 | 2 | `… test apps.social.tests.test_profiles` | done |
| 5  | Docs (glossário, STATE) e regressão total | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12 | 1–4 | `… test` + `makemigrations --check` | done |
