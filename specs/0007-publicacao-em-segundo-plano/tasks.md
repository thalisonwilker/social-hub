---
name: tasks
description: Decomposição e gates da feature 0007 — publicação em segundo plano (worker no banco, estado Incerto, polling e modo inline).
alwaysApply: false
---

# Tasks — Publicação em segundo plano

> Cada task mapeia para `AC-N` da [`spec.md`](./spec.md) e tem um **gate executável**. `[P]` = pode rodar em paralelo.
> Um commit por task, citando os ACs. **Liste os ACs explicitamente** (sem intervalos): o eval só reconhece `AC-N`.
> **Comando-base dos gates:** `docker compose run --rm --build web python manage.py test <módulo>`
> (iteração rápida local: `.venv/bin/python manage.py test <módulo>`).
> Testes em `apps/social/tests/`, nomeados `test_AC_N_*`; **inclua o token literal `AC-N` num docstring/comentário** de cada teste.
> Plataformas **sempre mockadas** no transporte; relógio e `sleep` injetados; testes do worker usam `run_once()`/`--once` (nunca laço infinito); testes de concorrência usam duas conexões reais ao SQLite.
> Os testes existentes rodam em **`PUBLISH_MODE=inline`** (padrão de dev/testes); os novos do worker usam `override_settings(PUBLISH_MODE="worker")`.

## Plano
| #  | Task                                                                                                                                                                              | Cobre AC                                   | Depende de | Gate (comando)                                                                                   | Status   |
|----|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------|------------|--------------------------------------------------------------------------------------------------|----------|
| 1  | Modelo e config: `PublicationTarget.Status.UNCERTAIN`, `WorkerHeartbeat`, status geral "Incerta" e contagens, `is_retryable`/`is_resolvable`, settings (`PUBLISH_MODE`, `WORKER_POLL_SECONDS`, `WORKER_HEARTBEAT_STALE_SECONDS`, `PUBLISH_SENDING_STALE_SECONDS`), `.env.example`, migração aditiva | AC-11, AC-18                               | —          | `… test apps.social.tests.test_background_models` + `makemigrations --check`                      | done     |
| 2  | Clientes classificam o erro: "nunca chegou ao servidor" (`network`) × "enviei e não veio resposta" (`interrupted`/`timeout`) no Graph, Threads e Evolution; marca as chamadas com efeito `[P]` | AC-6                                       | —          | `… test apps.social.tests.test_outcome_classification`                                            | done     |
| 3  | `process_target` e regras de incerteza em `publishing` (Facebook, Threads, WhatsApp); reivindica só `pending`; **remove** a recuperação de `sending` de 5 min; `send_pending` (inline) passa a usá-lo; "Tentar novamente" = `failed → pending` | AC-2, AC-4, AC-6                           | 1, 2       | `… test apps.social.tests.test_uncertain_outcomes apps.social.tests.test_claim apps.social.tests.test_publishing` | done     |
| 4  | Worker: `run_worker` (`--once`), FIFO sem orçamento, heartbeat, recuperação na partida, *reaper* de `sending` vencido, SIGTERM gracioso, `worker_health`                              | AC-3, AC-7, AC-8, AC-15                    | 3          | `… test apps.social.tests.test_worker`                                                            | done     |
| 5  | Views: Publicar enfileira (modo `worker`), "Tentar novamente" enfileira, **Resolver** (`publicado`/`reenviar`), `GET …/estado/` (JSON mínimo, só o dono)                              | AC-1, AC-5, AC-9, AC-10, AC-12, AC-17      | 3          | `… test apps.social.tests.test_background_views`                                                  | pendente |
| 6  | Detalhe e histórico: estados "Na fila"/"Enviando…"/"Incerto", botões do Incerto, polling de 3 s com recarga ao mudar, aviso de worker inativo, remover "Continuar envio" no modo `worker` | AC-11, AC-13, AC-14                        | 5          | `… test apps.social.tests.test_background_ui`                                                     | pendente |
| 7  | Infra e docs: serviço `worker` no `docker-compose.yml`, README, `.env.example`, **ADR-0011**, `TESTING.md`, glossário, notas de supersessão nas specs 0003–0006                       | AC-16, AC-19, AC-20                        | 4, 6       | `… test apps.social.tests.test_background_docs` + `node scripts/eval-spec-fidelity.mjs .`         | pendente |
| 8  | Segurança transversal e regressão: sem segredo/texto em log/JSON/HTML, isolamento e CSRF, suíte das 0002–0006 verde em `inline`                                                      | AC-17, AC-20                               | 3, 4, 5, 6, 7 | `… test apps` (suíte completa) + `… test apps.social.tests.test_background_security`            | pendente |
| 9  | **UAT real** com `docker compose` (web + worker): enfileirar, acompanhar, matar o worker no meio de um envio, resolver o Incerto, parar o worker (aviso), confirmar o timeout do Graph | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17, AC-18, AC-19, AC-20 | 1–8 | `docker compose exec web python manage.py test` + `makemigrations --check` + auditoria (`audit-esteira`, `validate-mermaid`, `eval-spec-fidelity`) + roteiro manual | pendente |

> Ordem sugerida: (1, 2 em paralelo) → 3 → 4 → 5 → 6 → 7 → 8 → 9. A 4 e a 5 só dependem da 3 e podem andar juntas.
> Uma task só vira `done` quando o **gate passa** — não por inspeção. Um commit por task.
> **A task 9 depende de você:** matar o worker no meio de um envio e publicar de verdade exige o seu número/contas de teste; o Status do WhatsApp é visível a ~2265 contatos e o Hub não o apaga — use um destino de teste (ex.: Threads/Facebook de teste, ou o WhatsApp só com a lista restrita na Evolution).

## Plano de teste
- **Unidade:** estados e status geral derivado (precedência); `is_retryable`/`is_resolvable`; classificação de erro nos três clientes (cada linha da matriz de incerteza); settings e modo de publicação.
- **Integração:** `process_target` com banco real e plataforma mockada no transporte (efeito enviado sem resposta → `uncertain`; antes de chegar → `failed`); reivindicação concorrente com **duas conexões**; worker via `run_once()` (FIFO, um por vez, recuperação na partida, *reaper* com relógio injetado, SIGTERM simulado); views com `PUBLISH_MODE=worker`.
- **Aceite:** um teste por AC (`test_AC_N_*`); cada linha das **três matrizes** vira um caso.
- **Segurança:** busca de chave/token/texto/base64/corpo cru em logs, JSON de estado e HTML; 404 entre usuários; GET onde exige POST; sem CSRF → 403.
- **Regressão:** a suíte atual (496+ testes) verde em `inline`; testes que dependiam de "Continuar envio"/recuperação de 5 min/mensagem de timeout do WhatsApp são **atualizados** na task 3/7 (e citados na spec).
- **UAT (task 9):** web + worker no Docker; fila e polling; `docker kill` do worker durante um envio → `uncertain` na partida; "Já foi publicado"/"Reenviar"; parar o worker → aviso; confirmar o comportamento do upload do Graph em timeout (questão em aberto do design).

## Divergências (SPEC_DEVIATION)
> Se a implementação precisar fugir da spec, registre aqui antes de seguir (ver `CLAUDE.md`).
- Nenhuma até agora.

## Checklist de Definition of Done
- [ ] Todos os AC verdes **pelo gate executável** (não por inspeção)
- [ ] Nenhum `SPEC_DEVIATION` pendente
- [ ] ADR-0011 registrado (worker no banco, `uncertain`, recuperação sem reenvio; substitui parcialmente 0004 e 0009)
- [x] Glossário / context-map atualizados
- [ ] Specs 0003–0006 com as notas de supersessão e a 0007 reflete o que foi construído
- [ ] `docs/STATE.md` atualizado (próximo passo / decisões)
- [ ] Issues #1 e #4 comentadas/fechadas com o resultado
- [ ] Cobertura e análise estática conforme `docs/engineering/TESTING.md`
