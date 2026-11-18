---
name: tasks
description: Decomposição e gates da feature 0009 — Instagram via Página (modelo, conexão, imagem pública JPEG, formulário, publicador, telas, UAT).
alwaysApply: false
---

# Tasks — Instagram: conectar pela Página e publicar

> Cada task mapeia para `AC-N` da [`spec.md`](./spec.md) e tem um **gate executável**. `[P]` = pode rodar em paralelo.
> Um commit por task, citando os ACs. **Liste os ACs explicitamente** (sem intervalos).
> **Comando-base dos gates:** `docker compose run --rm --build web python manage.py test <módulo>`
> (iteração rápida local: `.venv/bin/python manage.py test <módulo>`).
> Testes em `apps/social/tests/`, nomeados `test_AC_N_*`, com o token literal `AC-N` no docstring. A Graph API é **sempre mockada** no transporte; relógio e `sleep` injetados.

## Plano
| #  | Task | Cobre AC | Depende de | Gate (comando) | Status |
|----|------|----------|------------|----------------|--------|
| 1  | Modelo e decisão: `Platform.INSTAGRAM`, `SocialAccount.parent`, migration 0007, `INSTAGRAM_CONTAINER_WAIT_SECONDS` (settings + `.env.example`), **ADR-0013**, termos no glossário | AC-22 | — | `… test apps.social.tests.test_instagram_model` + `makemigrations --check` | done |
| 2  | Conexão: `list_pages` com `instagram_business_account`, sessão pendente com resumo do Instagram, `save_selected` cria/atualiza/remove a Conta Instagram | AC-1, AC-2, AC-3, AC-4, AC-21 | 1 | `… test apps.social.tests.test_instagram_connect` | done |
| 3  | Contas: desconectar Página remove a Conta Instagram; desconectar só o Instagram; telas de contas mostram o Instagram (@usuário, Página vinculada, reconexão) `[P]` | AC-5, AC-21 | 1 | `… test apps.social.tests.test_instagram_accounts` | done |
| 4  | `GraphClient`: `create_instagram_container`, `instagram_container_status`, `publish_instagram_container` (`effect=True`), `get_instagram_permalink` `[P]` | AC-13, AC-14, AC-18 | 1 | `… test apps.social.tests.test_instagram_client` | done |
| 5  | Imagem pública JPEG: `public.build_instagram_image_url`, conversão PNG→JPEG, rota `/publico/instagram.jpg` (escopo, cabeçalhos, 404 uniforme) + nota no ADR-0008 | AC-11, AC-12, AC-21 | 1 | `… test apps.social.tests.test_instagram_public_image` | done |
| 6  | Formulário: destino Instagram; imagem obrigatória, proporção 0,8–1,91, largura ≥ 320, legenda ≤ 2.200 e ≤ 30 hashtags, endereço público | AC-6, AC-7, AC-8, AC-9, AC-10 | 1 | `… test apps.social.tests.test_instagram_form` | done |
| 7  | Publicador `instagram_publish` (container gravado, espera, `FINISHED`/`PUBLISHED`/`ERROR`/`EXPIRED`/esgotada, retomada, `media_publish` → Incerto) e ramo `instagram` em `dispatch_claimed` | AC-13, AC-14, AC-15, AC-16, AC-17, AC-18, AC-20 | 4, 5 | `… test apps.social.tests.test_instagram_publisher` | done |
| 8  | Erros amigáveis e reconexão (token → Instagram **e** Página `needs_reauth`; permissão; limite; rede) e histórico/tela da publicação com o Instagram (link, Incerto, Tentar novamente) | AC-19, AC-10 | 7 | `… test apps.social.tests.test_instagram_errors apps.social.tests.test_instagram_views` | done |
| 9  | Segurança transversal: segredos fora de logs/HTML/JSON/mensagens, isolamento entre usuários, modo inline | AC-20, AC-21 | 2, 3, 5, 7, 8 | `… test apps.social.tests.test_instagram_security` | done |
| 10 | Documentação (README, `TESTING.md`, `STATE.md`, `lessons.md`, context-map), regressão total e **UAT real** (publicar imagem de `exemplos/` numa conta de teste) | AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-16, AC-17, AC-18, AC-19, AC-20, AC-21, AC-22 | 1–9 | `docker compose exec web python manage.py test` + `makemigrations --check` + `node scripts/eval-spec-fidelity.mjs .` + roteiro manual | em andamento |

> Ordem sugerida: 1 → (2, 3, 4, 5, 6 em paralelo) → 7 → 8 → 9 → 10.

## Plano de teste
- **Unidade:** conversão PNG→JPEG (alfa sobre branco, qualidade); proporção 0,8/1,91 nos limites; contagem de hashtags e caracteres; token da URL (escopo, expirado, outra publicação).
- **Integração:** conexão com banco real e `GraphClient` mockado (com/sem Instagram, reconexão, perda do vínculo); rota pública com todas as linhas da matriz; publicador com banco real e Graph mockada (todas as linhas da matriz do container).
- **Aceite:** um teste por AC; cada linha das três matrizes vira caso.
- **Regressão:** suítes 0002–0008 verdes.
- **UAT (task 10):** túnel HTTPS, `config_id` com `instagram_basic` + `instagram_content_publish`, reconectar a Página, publicar 1 imagem + legenda; forçar falha (túnel fora) e **Tentar novamente**; confirmar o código de erro do limite diário e o campo `instagram_business_account`.

## Divergências (SPEC_DEVIATION)
- Nenhuma até agora.

## Checklist de Definition of Done
- [ ] Todos os AC verdes **pelo gate executável** (não por inspeção)
- [ ] Nenhum `SPEC_DEVIATION` pendente
- [x] ADR-0013 registrado e nota no ADR-0008
- [x] Glossário atualizado (context-map sem mudança de fronteira)
- [ ] Spec reflete o que foi construído
- [ ] `docs/STATE.md` atualizado (próximo passo / decisões)
- [ ] Cobertura e análise estática conforme `docs/engineering/TESTING.md`
