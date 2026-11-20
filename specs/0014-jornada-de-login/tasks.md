---
name: tasks
description: Decomposição e gates da feature 0014 (jornada de login). Puxe ao implementar.
alwaysApply: false
---

# Tasks — Jornada de login

> Cada task mapeia para `AC-N` da `spec.md` e tem um gate executável. Testes em
> `apps/accounts/tests/`, um `test_AC_N_*` por critério.
> Gate geral: `.venv/bin/python manage.py test apps` (ou a versão Docker em `docs/engineering/TESTING.md`).

## Plano
| # | Task | Cobre AC | Depende de | Gate (comando) | Status |
|---|------|----------|------------|----------------|--------|
| 1 | ADR-0016: limitação de tentativas e idempotência do login no banco (por que não cache; HMAC do e-mail; `REMOTE_ADDR`; retenção de 24 h) | AC-5, AC-6, AC-10 | — | revisão | done |
| 2 | Modelo `LoginAttempt` (chave UUID única, `email_hash`, `ip`, `succeeded`, `created_at` com índice) + migração; funções puras de hash do e-mail e de janela/limite | AC-5, AC-6, AC-10 | 1 | `manage.py test apps.accounts.tests.test_login_throttle` | done |
| 3 | Backend por e-mail: casa `username__iexact`, senão `email__iexact` de conta única; sem @ não autentica; hash roda também sem conta (tempo igual) | AC-2, AC-4 | — | `manage.py test apps.accounts.tests.test_login_email` | done |
| 4 | `LoginForm` novo: e-mail (normaliza, 254) e senha obrigatória, mensagens pt-BR, `chave_idempotencia` UUID | AC-3, AC-7 | — | `manage.py test apps.accounts.tests.test_login_journey` | done |
| 5 | `LoginView`: ordem da matriz (campos/chave → repetição → bloqueio → autenticar → gravar tentativa → `login()`), códigos 302/400/401/409/429 + `Retry-After`, `next` seguro, limpeza de 24 h, log sem dado sensível | AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-10 | 2, 3, 4 | `manage.py test apps.accounts.tests.test_login_journey` | done |
| 6 | Template `login.html`: alerta de erro, campos com erro por campo, UUID do servidor como reserva, botão Google e "Esqueci minha senha" sem ação | AC-7, AC-8, AC-9 | 5 | `manage.py test apps.accounts.tests.test_login_journey` | done |
| 7 | JS `static/js/login.js`: `crypto.randomUUID()` na renderização, validação antes do envio, carregamento ("Entrando…", desabilita, somente leitura), reset no `pageshow` | AC-3, AC-7, AC-8, AC-9 | 6 | UAT no navegador | done |
| 8 | Ajustar testes existentes que entram por username (`apps/core/tests.py` e outros `client.post(login, username=…)`) e a nota de supersessão no AC-8 da spec 0013 | AC-4 | 3, 5 | `manage.py test apps` | done |
| 9 | Docs vivas: glossário ("Tentativa de login", "Chave de idempotência do login", "Bloqueio por tentativas"), README, `docs/lessons.md` se surgir gotcha, `docs/STATE.md` | — | 1–8 | revisão | done |

## Riscos / gotchas conhecidos
- **Sem cache compartilhado:** 2 workers do gunicorn e LocMem por processo → contadores e chaves no banco (mesmo motivo da 0013).
- **SQLite e escrita por tentativa:** cada login grava uma linha; volume baixo neste app. A limpeza de 24 h roda a cada POST (consulta indexada por `created_at`).
- **IP atrás de proxy:** `REMOTE_ADDR` vira o IP do proxy e o limite por IP passa a valer para todos juntos; resolver ao publicar com proxy confiável (ADR-0016).
- **Botão MUI e `readonly`:** conferido no UAT (2026-11-19): `readOnly` no `<input>` do MUI funciona e o botão reflete `disabled`.
- **Testes que logam por username** (`tester`) quebram com o login só por e-mail — task 8.

## Plano de teste
- Unidade: hash do e-mail, janela de 15 min, cálculo do `Retry-After`, validação da chave.
- Integração: backend por e-mail (username × campo e-mail × duplicado), gravação única da tentativa.
- Aceite: `test_AC_1_*` … `test_AC_10_*` com o `Client` do Django (status, mensagem, sessão, contagem); corrida simulada com `mock`; `assertLogs` sem senha/e-mail/chave. AC-7/8/9 (JS) também no UAT.

## Divergências (SPEC_DEVIATION)
- [ ] —

## Checklist de Definition of Done
- [x] Todos os AC verdes **pelo gate executável** (AC-7/8/9 também no UAT do navegador)
- [x] Nenhum `SPEC_DEVIATION` pendente
- [x] ADR-0016 registrado
- [x] Glossário atualizado
- [x] Spec reflete o que foi construído
- [x] `docs/STATE.md` atualizado (próximo passo / decisões)
