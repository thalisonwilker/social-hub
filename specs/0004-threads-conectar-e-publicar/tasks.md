---
name: tasks
description: Decomposição e gates da feature 0004 — conectar perfil do Threads e publicar texto em alvos mistos.
alwaysApply: false
---

# Tasks — Threads: conectar perfil e publicar texto

> Cada task mapeia para `AC-N` da [`spec.md`](./spec.md) e tem um **gate executável**. `[P]` = pode rodar em paralelo.
> Um commit por task, citando os ACs. **Liste os ACs explicitamente** (sem intervalos como "AC-1 a AC-5"): o eval só reconhece `AC-N`.
> **Comando-base dos gates:** `docker compose run --rm --build web python manage.py test <módulo>`
> (iteração rápida local: `.venv/bin/python manage.py test <módulo>`).
> Testes em `apps/social/tests/`, nomeados `test_AC_N_*`; **inclua o token literal `AC-N` num docstring/comentário** de cada teste
> (o eval procura `AC-N` com hífen). A Threads API é **sempre mockada** no transporte; testes não gravam no `MEDIA_ROOT` real.

## Plano
| #  | Task                                                                                                                                                  | Cobre AC                                                          | Depende de | Gate (comando)                                                  | Status |
|----|-------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|------------|-----------------------------------------------------------------|--------|
| 1  | Config e regras de texto: settings `THREADS_*`, `.env.example`, `threads_configured()`, `textrules.py` (peso com emoji = 4, links únicos)             | AC-1, AC-15                                                       | —          | `… test apps.social.tests.test_threads_config apps.social.tests.test_textrules` | todo |
| 2  | Modelos + migração: `Platform.THREADS`, `username`, `token_expires_at`, `token_refreshed_at`, `external_container_id`; `image` opcional em `Publication` `[P]` | AC-4, AC-5, AC-9, AC-23                                        | 1          | `… test apps.social.tests.test_threads_models` + `makemigrations --check` | todo |
| 3  | Clientes: extrair `BaseGraphClient` (sem regressão no `GraphClient`) e criar `ThreadsClient` (login URL, troca, token longo, renovação, perfil, container, status, publicar, permalink) `[P]` | AC-2, AC-4, AC-8, AC-10, AC-17, AC-18, AC-19, AC-20, AC-25 | 1 | `… test apps.social.tests.test_threads_client apps.social.tests.test_meta_client apps.social.tests.test_publish_photo_client` | todo |
| 4  | Renovação sob demanda: `threads_tokens.ensure_fresh` (expirado, janela de 30 dias, 24 h de idade, erros)                                               | AC-12                                                             | 2, 3       | `… test apps.social.tests.test_threads_tokens`                  | todo   |
| 5  | Conexão: `threads_connect` + views `conectar`/`callback` + rotas, aviso de host, botão "Conectar Threads" em *Contas conectadas*                       | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-26             | 1, 2, 3    | `… test apps.social.tests.test_threads_connect_views`           | todo   |
| 6  | Contas: listagem com validade (expiração local → `needs_reauth`), **Verificar** com renovação, **Desconectar** e **Reconectar** por plataforma     | AC-9, AC-10, AC-11, AC-26                                         | 4, 5       | `… test apps.social.tests.test_threads_accounts_views`          | todo   |
| 7  | Publicador do Threads + despacho por plataforma em `publishing` (container → espera → publica → permalink; reuso/descarte do container; claim comum) | AC-17, AC-18, AC-19, AC-20, AC-21, AC-22                        | 2, 3, 4    | `… test apps.social.tests.test_threads_publisher apps.social.tests.test_publishing` | todo |
| 8  | Formulário misto: destinos por plataforma, imagem condicional (`Form.clean`), limites do texto por destino; telas de lista/detalhe e view da imagem sem imagem | AC-13, AC-14, AC-15, AC-16, AC-21, AC-23                       | 1, 2, 7    | `… test apps.social.tests.test_threads_post_form apps.social.tests.test_views_post_new apps.social.tests.test_views_post_detail apps.social.tests.test_views_posts_list` | todo |
| 9  | Dashboard: Threads "Conectado" com conta `active` `[P]`                                                                                               | AC-24                                                             | 2          | `… test apps.social.tests.test_dashboard`                       | todo   |
| 10 | Atualizar a **spec 0003** (AC-1 e AC-5) e os testes `test_AC_1_*`/`test_AC_5_*` da 0003; suíte existente verde                                         | AC-27                                                             | 8          | `… test apps` (suíte completa) + `node scripts/eval-spec-fidelity.mjs .` | todo |
| 11 | Testes transversais de segurança com o fluxo real e só o transporte HTTP interceptado: segredos/tokens/texto fora de HTML/logs; nada de URL/params em log; token cifrado | AC-25, AC-26                                  | 5, 6, 7, 8 | `… test apps.social.tests.test_threads_security`                | todo   |
| 12 | Documentação (README, `TESTING.md`, `STATE.md`, `.env.example`), recriar o container com `THREADS_*` e **UAT real** com o perfil de teste via túnel | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17, AC-18, AC-19, AC-20, AC-21, AC-22, AC-23, AC-24, AC-25, AC-26, AC-27 | 1–11 | `docker compose exec web python manage.py test` + `makemigrations --check` + auditoria (`audit-esteira`, `validate-mermaid`, `eval-spec-fidelity`) + roteiro manual | todo |

> Ordem sugerida: 1 → (2, 3 em paralelo) → 4 → 5 → 6 → 7 → 8 → (9, 10) → 11 → 12.
> Uma task só vira `done` quando o **gate passa** — não por inspeção. Um commit por task.

## Plano de teste
- **Unidade:** `textrules` (peso: ASCII, acentos, emoji, ZWJ, links repetidos/únicos); `ThreadsClient` com transporte mockado (host `graph.threads.com`, caminhos,
  corpo × query, `client_secret`/`code` só em POST, parse de `expires_in`, erros sanitizados, timeout); `ensure_fresh` com relógio controlado (todas as linhas da matriz).
- **Integração:** conexão com sessão e `SocialAccount` reais; publicador com banco real e Threads mockado (todos os status do container, reuso e descarte do id,
  `PUBLISHED` sem republicar); alvos mistos (Facebook + Threads) com lotes e retry.
- **Aceite:** um teste por AC (`test_AC_N_*`); cada linha das **quatro matrizes de decisão** da spec vira um caso.
- **Regressão:** toda a suíte existente (0002 e 0003) continua verde, exceto os ajustes declarados no AC-27.
- **Segurança:** varredura de HTML, mensagens, logs (`assertLogs`) e do que o cliente registra, por token curto/longo, `THREADS_APP_SECRET`, `code` e texto; cookies/sessão; 404 entre usuários.
- **UAT manual (task 12), com o túnel ativo e acessando o Hub pela URL do túnel:**
  1. Conectar o perfil de teste do Threads (testador aceito, perfil público).
  2. Publicar um **texto só no Threads**; conferir o post no Threads e o link.
  3. Publicar **Facebook + Threads** juntos (com imagem); conferir que o Threads recebe só texto.
  4. Forçar uma falha (ex.: desconectar antes de enviar) e **tentar de novo**.
  5. Tentar `th_exchange_token`/`th_refresh_token` por **POST** e **Bearer** nos GETs e registrar o que a Meta aceita.
  6. Medir o tempo do container de texto até `FINISHED` e anotar os códigos de erro reais (token inválido, limite).

## Divergências (SPEC_DEVIATION)
> Se a implementação precisar fugir da spec, registre aqui antes de seguir (ver `CLAUDE.md`).
- [ ] (nenhuma até agora)

## Checklist de Definition of Done
- [ ] Todos os AC verdes **pelo gate executável** (não por inspeção)
- [ ] Nenhum `SPEC_DEVIATION` pendente
- [ ] ADRs de decisões difíceis de reverter registrados (ADR-0006, ADR-0007)
- [ ] Spec **0003** atualizada (AC-1 e AC-5) e sua suíte verde (AC-27)
- [ ] Glossário / context-map atualizados
- [ ] Spec reflete o que foi construído (incluindo as respostas do UAT sobre POST/Bearer, tempo do container e códigos de erro)
- [ ] `docs/STATE.md` atualizado (próximo passo / decisões)
- [ ] CI da esteira verde (auditoria, Mermaid e eval)
- [ ] UAT real concluído; túnel fechado (`docker rm -f social-hub-tunnel`) ao terminar
- [ ] README documenta a configuração do Threads e a atualização do túnel
