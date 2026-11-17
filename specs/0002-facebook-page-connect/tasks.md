---
name: tasks
description: Decomposição e gates da feature 0002 — conectar Páginas do Facebook.
alwaysApply: false
---

# Tasks — Conectar Página do Facebook

> Cada task mapeia para `AC-N` da [`spec.md`](./spec.md) e tem um **gate executável**. Marque `[P]` nas que podem
> rodar em paralelo. Um commit por task, citando os ACs.
> **Comando-base dos gates** (reconstrói a imagem quando as dependências mudam):
> `docker compose run --rm --build web python manage.py test <módulo>`
> Testes ficam em `apps/social/tests/` e são nomeados `test_AC_N_*` para rastreabilidade.

## Plano
| #  | Task                                                                                                                | Cobre AC            | Depende de | Gate (comando)                                               | Status |
|----|---------------------------------------------------------------------------------------------------------------------|---------------------|------------|--------------------------------------------------------------|--------|
| 1  | Dependências (`requests`, `cryptography`), settings `META_*`, `.env.example`, helper `meta_configured()`            | AC-1                | —          | `… test apps.social.tests.test_config`                       | done |
| 2  | `crypto.py`: Fernet/`MultiFernet`, rotação de chave, chave ausente/inválida tratada `[P]`                           | AC-16               | 1          | `… test apps.social.tests.test_crypto`                       | done |
| 3  | Modelo `SocialAccount` + migration: único (owner, platform, external_id), `set_token/get_token`, `repr` seguro `[P]` | AC-5, AC-11, AC-14, AC-16 | 1    | `… test apps.social.tests.test_models`                       | done |
| 4  | `services/meta.py`: `GraphClient` (login URL, troca de code, token longo, `/me/accounts`, `GET /{id}`), `MetaApiError` sanitizado, POST/Bearer, timeout `[P]` | AC-2, AC-3, AC-8, AC-12, AC-16 | 1 | `… test apps.social.tests.test_meta_client`        | done |
| 5  | `services/facebook_connect.py`: Páginas na sessão (cifradas, TTL 10 min), validação de IDs, upsert das selecionadas | AC-3, AC-4, AC-5, AC-9, AC-10 | 2, 3, 4 | `… test apps.social.tests.test_facebook_connect`       | done |
| 6  | Views `conectar` (POST + `state`) e `callback` (erros, `state`, falhas da Meta, sem Páginas)                         | AC-2, AC-6, AC-7, AC-8, AC-9, AC-17 | 5 | `… test apps.social.tests.test_views_oauth`            | done |
| 7  | View e template de **seleção multi-Página** (checkboxes, "Marcar todas" em JS puro, erros)                           | AC-3, AC-4, AC-5, AC-10 | 5, 6   | `… test apps.social.tests.test_views_select`                 | done |
| 8  | Tela *Contas conectadas* (lista, estado vazio, "não configurada"), **verificar** e **desconectar** com confirmação `[P]` | AC-1, AC-11, AC-12, AC-13, AC-14 | 3, 4 | `… test apps.social.tests.test_views_accounts`        | done |
| 9  | Dashboard: "Conectado" conforme contas `active` do usuário `[P]`                                                    | AC-15               | 3          | `… test apps.social.tests.test_dashboard`                    | done |
| 10 | Testes transversais de segurança: segredos fora de HTML/mensagens/logs/URLs; token cifrado no banco e na sessão; login obrigatório | AC-16, AC-17 | 6, 7, 8  | `… test apps.social.tests.test_security`                     | done |
| 11 | Documentação (README, `docs/engineering/TESTING.md`, `docs/STATE.md`), `.env` local e **UAT real** com a Página de teste | AC-1 a AC-17    | 1–10       | `docker compose exec web python manage.py test` + `makemigrations --check` + roteiro manual | done |

> Uma task só vira `done` quando o **gate passa** — não por inspeção visual. Ordem sugerida: 1 → (2, 3, 4 em paralelo)
> → 5 → 6 → 7 → (8, 9 em paralelo) → 10 → 11.

## Plano de teste
- **Unidade:** criptografia (ida e volta, rotação, chave inválida), modelo (unicidade, `repr` sem token), `GraphClient`
  (formato das chamadas, erros mapeados, sem segredo em URL, timeout) com transporte HTTP **mockado**.
- **Integração:** `facebook_connect` com sessão do Django e `SocialAccount` reais em banco de teste.
- **Aceite:** um teste por AC (`test_AC_N_*`) usando o cliente de teste do Django; cada linha das três **matrizes de
  decisão** da spec vira um caso (callback, seleção, verificação).
- **Segurança:** varredura de HTML, mensagens, logs (`assertLogs`) e URLs mockadas por token/segredo/`code`.
- **UAT manual (task 11):** conectar a Página de teste real em `http://localhost:8080`, validar o spike do `config_id`,
  conectar várias Páginas, verificar, desconectar e reconectar. Sem lint/análise estática configurados no projeto
  ainda; fica registrado como pendência de qualidade para a CI.

## Divergências (SPEC_DEVIATION)
> Se a implementação precisar fugir da spec, registre aqui antes de seguir (ver `CLAUDE.md`).
- [ ] (nenhuma até agora)

## Checklist de Definition of Done
- [ ] Todos os AC verdes **pelo gate executável** (não por inspeção)
- [ ] Nenhum `SPEC_DEVIATION` pendente
- [ ] ADRs de decisões difíceis de reverter registrados (ADR-0002, ADR-0003)
- [ ] Glossário / context-map atualizados se mudaram
- [ ] Spec reflete o que foi construído
- [ ] `docs/STATE.md` atualizado (próximo passo / decisões)
- [ ] UAT real com a Página de teste concluído e `config_id` validado (senão, ADR-0003 revisto)
