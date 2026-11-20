---
name: tasks
description: Decomposição e gates da feature 0015 (revisão do cadastro). Puxe ao implementar.
alwaysApply: false
---

# Tasks — Revisão do cadastro

> Correções pontuais sobre a 0013; testes novos em `apps/accounts/tests/test_signup_review.py`.
> Gate geral: `.venv/bin/python manage.py test apps`.

## Plano
| # | Task | Cobre AC | Depende de | Gate (comando) | Status |
|---|------|----------|------------|----------------|--------|
| 1 | Migração `accounts`: índice único em `lower(email)` (parcial, e-mail não vazio) na tabela de usuários, com checagem prévia de repetidos | AC-4 | — | `manage.py test apps.accounts.tests.test_signup_review` | done |
| 2 | `validate_person_name`: normalizar NFC antes de validar e devolver o nome em NFC | AC-3 | — | idem | done |
| 3 | Mensagem de sucesso nova na view + `aria-invalid` no servidor para campos com erro | AC-2, AC-6 | — | idem | done |
| 4 | Template: botão "Registrar" com indicador; erros com `aria-live` | AC-1, AC-2 | — | idem | done |
| 5 | `signup.js`: envio único + carregamento + `pageshow`; NFC no nome; regex de e-mail alinhada | AC-1, AC-3, AC-5 | 4 | UAT no navegador | done |
| 6 | Ajustar testes da 0013 que conferem o texto antigo; nota na spec 0013; STATE | AC-6 | 1–5 | `manage.py test apps` | done |

## Plano de teste
- Aceite: um `test_AC_N_*` por AC (AC-1 e AC-5 por marcação + UAT, já que são comportamento do navegador).
- Integração: `IntegrityError` ao criar usuário com e-mail repetido (direto no ORM) e cadastro com e-mail repetido por corrida → mensagem amigável.

## Checklist de Definition of Done
- [x] AC verdes pelo gate (AC-1/AC-5 também no UAT)
- [x] Spec 0013 anotada onde mudou
- [x] `docs/STATE.md` atualizado
