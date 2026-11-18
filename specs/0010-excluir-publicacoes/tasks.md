---
name: tasks
description: Decomposição e gates da feature 0010 — excluir publicações (modelo, clientes, serviço, views, telas, UAT).
alwaysApply: false
---

# Tasks — Excluir publicações

> Cada task mapeia para `AC-N` da [`spec.md`](./spec.md) e tem um **gate executável**. `[P]` = pode rodar em paralelo.
> Um commit por task, citando os ACs. **Liste os ACs explicitamente** (sem intervalos).
> **Comando-base dos gates:** `docker compose run --rm --build web python manage.py test <módulo>`
> (iteração rápida local: `.venv/bin/python manage.py test <módulo>`). Testes em `apps/social/tests/`, `test_AC_N_*`, com o token `AC-N` no docstring. Graph e Threads sempre mockados no transporte.

## Plano
| #  | Task | Cobre AC | Depende de | Gate (comando) | Status |
|----|------|----------|------------|----------------|--------|
| 1  | Modelo e decisão: `PublicationTarget.deleted_at`, migration 0008, escopo `threads_delete`, **ADR-0014**, glossário | AC-14, AC-17 | — | `… test apps.social.tests.test_deletion_model` + `makemigrations --check` | done |
| 2  | Clientes: `GraphClient.delete_post` e `ThreadsClient.delete_media` (token no header/corpo, `effect`, classificação de erro) `[P]` | AC-5, AC-6, AC-10, AC-15 | 1 | `… test apps.social.tests.test_deletion_clients` | done |
| 3  | Serviço `deletion`: elegibilidade (matriz), apagar na plataforma (sucesso, inexistente, erros, desconhecido), apagar tudo, remover do Hub (alvo e publicação, arquivo, bloqueio `sending`) | AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12 | 1, 2 | `… test apps.social.tests.test_deletion_service` | done |
| 4  | Views e rotas (`POST`, CSRF, dono → 404, mensagens, redirecionamentos, URL pública 404 após remover) | AC-1, AC-2, AC-3, AC-12, AC-15, AC-16 | 3 | `… test apps.social.tests.test_deletion_views` | done |
| 5  | Telas: botões por alvo e por publicação, textos "Apague pelo app", confirmações, "Apagado na plataforma" no detalhe e na lista | AC-4, AC-7, AC-13 | 4 | `… test apps.social.tests.test_deletion_ui` | done |
| 6  | Segurança transversal com transporte falso (token só no header, nada de segredo em log/HTML/mensagem, isolamento entre usuários) | AC-9, AC-10, AC-15 | 3, 4, 5 | `… test apps.social.tests.test_deletion_security` | done |
| 7  | Documentação (README, `TESTING.md`, `STATE.md`, `lessons.md`, specs 0005/0009), regressão total e **UAT real** (apagar posts de teste no Facebook e no Threads) | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17 | 1–6 | `docker compose exec web python manage.py test` + `makemigrations --check` + `node scripts/eval-spec-fidelity.mjs .` + roteiro manual | em andamento |

> Ordem sugerida: 1 → (2) → 3 → 4 → 5 → 6 → 7.

## Plano de teste
- **Unidade:** elegibilidade (cada linha da matriz); classificação de erros (token, permissão, limite, inexistente, desconhecido).
- **Integração:** serviço com banco real e APIs mockadas; remoção de alvo/publicação com arquivo real em diretório temporário; bloqueio por `sending`.
- **Aceite:** um teste por AC; cada linha das três matrizes vira caso.
- **Regressão:** suítes 0002–0009 verdes.
- **UAT (task 7):** publicar post de teste no Facebook e no Threads, **apagar na plataforma**, conferir nas redes; repetir (objeto inexistente); **Remover do Hub**; confirmar `threads_delete` e se o Facebook apaga posts criados fora do app.

## Divergências (SPEC_DEVIATION)
- Nenhuma até agora.

## Checklist de Definition of Done
- [ ] Todos os AC verdes **pelo gate executável**
- [ ] Nenhum `SPEC_DEVIATION` pendente
- [x] ADR-0014 registrado
- [x] Glossário atualizado
- [ ] Spec reflete o que foi construído
- [ ] `docs/STATE.md` atualizado
- [ ] Cobertura e análise estática conforme `docs/engineering/TESTING.md`
