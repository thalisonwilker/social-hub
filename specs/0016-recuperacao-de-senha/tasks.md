---
name: tasks
description: Decomposição e gates da feature 0016 (recuperação de senha). Puxe ao implementar.
alwaysApply: false
---

# Tasks — Recuperação de senha

> Testes em `apps/accounts/tests/test_password_reset.py` (um `test_AC_N_*` por critério), e-mail `locmem`
> e envio síncrono nos testes. Gate geral: `.venv/bin/python manage.py test apps`.

## Plano
| # | Task | Cobre AC | Depende de | Gate (comando) | Status |
|---|------|----------|------------|----------------|--------|
| 1 | Config de e-mail: `EMAIL_*`/`DEFAULT_FROM_EMAIL` do `.env`, backend de arquivo em `var/emails/` sem SMTP, `ACCOUNTS_EMAIL_ASYNC`, system check em produção, `.env.example`, `.gitignore` | AC-4, AC-12 | — | `manage.py check` + testes | done |
| 2 | Modelos `PasswordResetRequest` e `PasswordResetToken` + migração | AC-4, AC-5, AC-6, AC-10 | — | `manage.py makemigrations --check` | done |
| 3 | `password_reset.py`: emitir token (hash, invalidar antigos), validar, consumir (UPDATE condicional), limites IP/conta, retenção; localizador de conta reaproveitado do `EmailBackend` | AC-4, AC-5, AC-6, AC-8, AC-10, AC-14 | 2 | `manage.py test apps.accounts.tests.test_password_reset` | done |
| 4 | `emails.py`: e-mail do link e aviso de senha alterada (texto pt-BR), envio após commit em thread, falha logada sem conteúdo | AC-3, AC-4, AC-12, AC-14 | 1 | idem | done |
| 5 | Views/rotas: pedido (matriz), abrir link (sessão + redirect + no-referrer), redefinir (política do cadastro, consumo, sessões apagadas, aviso, redirect ao login); `sensitive_post_parameters` | AC-2, AC-3, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11 | 3, 4 | idem | done |
| 6 | Templates `password_reset_request.html`, `password_reset_confirm.html`, `password_reset_invalid.html`; link "Esqueci minha senha" no login | AC-1, AC-7, AC-8, AC-13 | 5 | idem | done |
| 7 | JS `password_reset.js`: UUID, validação de e-mail e senha (regras do cadastro), botão desabilitado, carregamento e envio único | AC-1, AC-2, AC-9, AC-13 | 6 | UAT no navegador | done |
| 8 | Filtro de log do `runserver` sem query string; teste de logs | AC-14 | 5 | idem | done |
| 9 | Docs vivas: glossário, README (SMTP), nota na spec 0014, ADR-0017 aceito, STATE | — | 1–8 | revisão | done |

## Plano de teste
- Unidade: hash do token, expiração (relógio controlado), consumo condicional, limites.
- Integração: e-mails no `mail.outbox` (destinatário, link, texto), sessões apagadas, corrida no consumo (mock).
- Aceite: `test_AC_1_*` … `test_AC_14_*`; AC-1/7/9/13 também no UAT (JS).

## Divergências (SPEC_DEVIATION)
- [ ] —

## Checklist de Definition of Done
- [x] Todos os AC verdes pelo gate (UAT para o JS)
- [x] ADR-0017 aceito
- [x] Glossário atualizado
- [x] Spec fiel ao construído
- [x] `docs/STATE.md` atualizado
