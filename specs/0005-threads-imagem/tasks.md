---
name: tasks
description: Decomposição e gates da feature 0005 — imagem + texto no Threads via URL pública assinada e orçamento de tempo.
alwaysApply: false
---

# Tasks — Threads: publicar imagem junto com o texto

> Cada task mapeia para `AC-N` da [`spec.md`](./spec.md) e tem um **gate executável**. `[P]` = pode rodar em paralelo.
> Um commit por task, citando os ACs. **Liste os ACs explicitamente** (sem intervalos): o eval só reconhece `AC-N`.
> **Comando-base dos gates:** `docker compose run --rm --build web python manage.py test <módulo>`
> (iteração rápida local: `.venv/bin/python manage.py test <módulo>`).
> Testes em `apps/social/tests/`, nomeados `test_AC_N_*`; **inclua o token literal `AC-N` num docstring/comentário** de cada teste.
> A Threads API é **sempre mockada** no transporte; testes não gravam no `MEDIA_ROOT` real; relógio e `sleep` injetados nos testes de espera/orçamento.

## Plano
| #  | Task                                                                                                                                                       | Cobre AC                                              | Depende de | Gate (comando)                                                                  | Status |
|----|------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------|------------|---------------------------------------------------------------------------------|--------|
| 1  | Config e URL pública: settings (`PUBLIC_BASE_URL`, `THREADS_IMAGE_URL_TTL_SECONDS`, `THREADS_IMAGE_WAIT_SECONDS`, `PUBLISH_REQUEST_BUDGET_SECONDS`), `.env.example`, `conf.public_base_url()`/`public_url_configured()`, `public.py` (token assinado, validação, `build_public_image_url`) | AC-4, AC-5, AC-20 | — | `… test apps.social.tests.test_public_url`                                      | done   |
| 2  | Dimensões e proporção: `SanitizedImage` com largura/altura e `aspect_ratio_within(10)` `[P]`                                                               | AC-3                                                  | —          | `… test apps.social.tests.test_images`                                          | done   |
| 3  | Formulário: valida/sanitiza imagem com Threads, proporção, endereço público; remove "imagem ignorada"/`image_ignored`; texto de ajuda                      | AC-1, AC-2, AC-3, AC-4                                | 1, 2       | `… test apps.social.tests.test_threads_image_form`                              | done   |
| 4  | Rota pública `/publico/imagem.<ext>` (anônima, escopo mínimo, cabeçalhos, 404 uniforme, logs sem token) + `docker/gunicorn.conf.py` com log sem query      | AC-6, AC-7, AC-8, AC-9, AC-10, AC-20                  | 1          | `… test apps.social.tests.test_public_image_view`                               | done   |
| 5  | `ThreadsClient.create_image_container` (`IMAGE`, `image_url`, `text`, token no corpo) `[P]`                                                                 | AC-11                                                 | 1          | `… test apps.social.tests.test_threads_client`                                  | done   |
| 6  | Publicador do Threads TEXT/IMAGE: gera URL, grava container, espera por tipo, `ERROR`/`EXPIRED` descartam id, espera esgotada mantém id, retomada, mensagens, log do enum | AC-11, AC-12, AC-13, AC-14, AC-15, AC-16 | 4, 5       | `… test apps.social.tests.test_threads_image_publisher apps.social.tests.test_threads_publisher` | done   |
| 7  | Orçamento de tempo em `send_pending` (não inicia alvo com < 40 s; espera = `min(config, restante − 25 s)`; log `publish_budget_exhausted`)                  | AC-17, AC-18                                          | 6          | `… test apps.social.tests.test_publish_budget apps.social.tests.test_publishing` | todo   |
| 8  | Alvos mistos com imagem; atualizar **specs 0004** (AC-14, AC-17, AC-21, non-goal) e testes `test_AC_14_*`/`test_AC_17_*`/`test_AC_21_*`; suíte existente verde | AC-19, AC-21                                          | 3, 6, 7    | `… test apps` + `node scripts/eval-spec-fidelity.mjs .`                         | todo   |
| 9  | Segurança transversal: token/URL assinada fora de HTML, mensagens e logs; `Host` forjado; imagem de outra publicação inacessível; log do Gunicorn sem query | AC-10, AC-20                                          | 4, 6, 8    | `… test apps.social.tests.test_threads_image_security`                          | todo   |
| 10 | Documentação (README, `TESTING.md`, `STATE.md`, `lessons.md`, `.env.example`, Dockerfile/compose com `gunicorn.conf.py`), túnel e **UAT real** com a imagem de teste | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17, AC-18, AC-19, AC-20, AC-21 | 1–9 | `docker compose exec web python manage.py test` + `makemigrations --check` + auditoria (`audit-esteira`, `validate-mermaid`, `eval-spec-fidelity`) + roteiro manual | todo   |

> Ordem sugerida: (1, 2 em paralelo) → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10.
> Uma task só vira `done` quando o **gate passa** — não por inspeção. Um commit por task.

## Plano de teste
- **Unidade:** token (válido, expirado com relógio controlado, adulterado, outra chave, outra publicação); `build_public_image_url` (base configurada × origem do redirect × sem HTTPS; `Host` ignorado); proporção (10:1 aceito, > 10 nos dois sentidos, 320/4096 não bloqueiam).
- **Integração:** rota pública com banco real (todas as linhas da matriz, `HEAD`, 405, cabeçalhos, sem `Set-Cookie`); publicador com banco real e Threads mockado (todas as linhas da matriz do container, reuso/descarte do id); `send_pending` com relógio controlado (< 40 s não inicia; espera limitada pelo restante).
- **Aceite:** um teste por AC (`test_AC_N_*`); cada linha das **quatro matrizes** da spec vira um caso.
- **Regressão:** suíte das 0002–0004 verde, salvo os testes de AC-14/17/21 da 0004 atualizados na task 8.
- **UAT (task 10):** túnel novo, publicar a imagem de `exemplos/` em Threads (e Facebook), forçar falha (túnel fora) e Tentar de novo; responder as questões em aberto (issue #5).

## Divergências (SPEC_DEVIATION)
> Se a implementação precisar fugir da spec, registre aqui antes de seguir (ver `CLAUDE.md`).
- Nenhuma até agora.

## Checklist de Definition of Done
- [ ] Todos os AC verdes **pelo gate executável** (não por inspeção)
- [ ] Nenhum `SPEC_DEVIATION` pendente
- [x] ADRs de decisões difíceis de reverter registrados (0008, 0009)
- [x] Glossário / context-map atualizados
- [ ] Specs 0004 atualizadas (task 8) e 0005 reflete o que foi construído
- [ ] `docs/STATE.md` atualizado (próximo passo / decisões)
- [ ] Cobertura e análise estática conforme `docs/engineering/TESTING.md`
