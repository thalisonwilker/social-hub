---
name: tasks
description: Decomposição e gates da feature 0013 (cadastro de novos usuários). Puxe ao implementar.
alwaysApply: false
---

# Tasks — Cadastro de novos usuários

> Cada task mapeia para `AC-N` da `spec.md` e tem um gate executável. Testes em
> `apps/accounts/tests/` (pacote novo), um `test_AC_N_*` por critério.
> Gate geral: `.venv/bin/python manage.py test apps` (ou a versão Docker em `docs/engineering/TESTING.md`).

## Plano
| # | Task | Cobre AC | Depende de | Gate (comando) | Status |
|---|------|----------|------------|----------------|--------|
| 1 | Validadores puros: nome/sobrenome, composição da senha (mensagens pt-BR) e `normalize_email` (aparar + minúsculas) em `apps/accounts/validators.py` | AC-5, AC-7 | — | `manage.py test apps.accounts.tests.test_validators` | done |
| 2 | `SignupForm` (nome, sobrenome, e-mail, senha, confirmação, aceite): revalida tudo, unicidade `email__iexact` OU `username__iexact`, validadores do Django + composição; `save()` grava `username=email` normalizado e trata `IntegrityError` como "já cadastrado" (o teste deste formulário fica em `test_signup_form`) | AC-5, AC-6, AC-7 | 1 | `manage.py test apps.accounts.tests.test_signup_form` | done |
| 3 | Views/rotas: `SignupView` (`login_not_required`, redireciona autenticado, mensagem de sucesso → login), páginas `/termos/` e `/privacidade/` | AC-1, AC-2, AC-7, AC-10 | 2 | `manage.py test apps.accounts.tests.test_signup_views` | done |
| 4 | Login por e-mail: backend de autenticação que casa `username__iexact` quando há `@` (mantém o `ModelBackend` para usernames antigos), rótulo "E-mail", mensagens do Django exibidas no login, link "Criar conta" | AC-1, AC-8 | 3 | `manage.py test apps.accounts.tests.test_login_email` | done |
| 5 | Template `accounts/signup.html` no layout de dois painéis do login: campos, lista de requisitos da senha, checkbox com links, botão Google (SVG inline, `type="button"`, "Em breve"), link "Já tem conta? Entrar" | AC-1, AC-9 | 3 | `manage.py test apps.accounts.tests.test_signup_views` | done |
| 6 | JS `static/js/signup.js`: validação campo a campo (mesmas regras), checklist da senha, matriz de habilitação do botão (sem consulta ao servidor); garantir que o botão MUI reflita `disabled` alterado após o carregamento (ver Riscos) | AC-3, AC-4, AC-9 | 5 | teste manual guiado (UAT) + `npm run build` sem erro | done |
| 7 | Testes de segurança/aceite: XSS/SQLi no nome e e-mail, CSRF, corrida de e-mail duplicado, sem JS o POST funciona | AC-5, AC-6 | 3,4 | `manage.py test apps.accounts` | done |
| 8 | Trava de idempotência: modelo `SignupIdempotencyKey` (chave única, `user` FK, `created_at`) + migração; chave assinada com `django.core.signing` (TTL 2 h) no formulário; na `SignupView`, conferir a chave **antes** da validação do e-mail e registrar chave + usuário em `transaction.atomic()`, tratando `IntegrityError` da chave como repetição | AC-11, AC-12 | 3 | `manage.py test apps.accounts.tests.test_signup_idempotency` | done |
| 9 | Docs vivas: glossário ("Cadastro", "Chave de idempotência do cadastro", "Usuário do Social Hub" entra por e-mail), README, `docs/STATE.md` | — | 1–8 | revisão | done |

## Riscos / gotchas conhecidos
- **MUI lê `disabled` só na montagem** (`frontend/mui/lift.jsx` copia `el.disabled` ao renderizar). Alternar `disabled` depois não reflete no botão MUI. Resolver na task 6 (ex.: observar o atributo no lift ou deixar o botão de cadastro fora do lift) — registrar a escolha em `docs/lessons.md`.
- A mensagem "Este e-mail já está cadastrado." no envio ainda permite descobrir e-mails cadastrados (sem limite de tentativas no `POST /cadastro/`, fora de escopo). Aceito conscientemente nesta feature.
- **Idempotência no banco, não em cache:** são 2 workers do gunicorn e não há cache compartilhado (só o LocMem padrão, um por processo). No SQLite com `transaction_mode=IMMEDIATE` a segunda requisição espera a primeira gravar e então esbarra na chave única. Teste de corrida: duas threads com a mesma chave → 1 usuário.
- `User.email` não é único no banco; a unicidade real vem do `username` (= e-mail). Usuários antigos podem ter `email` repetido — a checagem `iexact` cobre os dois campos.

## Plano de teste
- Unidade: validadores (tabela de regras da spec, um caso por mensagem), `normalize_email`.
- Integração: `SignupForm.save()`, backend de login por e-mail, trava de idempotência (repetição sequencial, concorrente e chave expirada).
- Aceite: `test_AC_1_*` … `test_AC_12_*` com o `Client` do Django; AC-3/4 (JS) verificados no UAT no navegador.

## Divergências (SPEC_DEVIATION)
- [ ] —

## Checklist de Definition of Done
- [x] Todos os AC verdes **pelo gate executável** (AC-3/4 também no UAT do navegador — conferidos em 2026-11-19)
- [x] Nenhum `SPEC_DEVIATION` pendente
- [ ] ADRs de decisões difíceis de reverter registrados (username = e-mail, se o time considerar irreversível)
- [x] Glossário / context-map atualizados se mudaram
- [x] Spec reflete o que foi construído
- [x] `docs/STATE.md` atualizado (próximo passo / decisões)
