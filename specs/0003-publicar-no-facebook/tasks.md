---
name: tasks
description: Decomposição e gates da feature 0003 — publicar texto + imagem em várias Páginas do Facebook.
alwaysApply: false
---

# Tasks — Publicar no Facebook (texto + imagem, várias Páginas)

> Cada task mapeia para `AC-N` da [`spec.md`](./spec.md) e tem um **gate executável**. `[P]` = pode rodar em paralelo.
> Um commit por task, citando os ACs.
> **Comando-base dos gates:** `docker compose run --rm --build web python manage.py test <módulo>`
> (iteração rápida local: `.venv/bin/python manage.py test <módulo>`, ver `docs/engineering/TESTING.md`).
> Testes em `apps/social/tests/`, nomeados `test_AC_N_*`. Imagens de teste são geradas com Pillow em memória.

## Plano
| #  | Task                                                                                                                                      | Cobre AC                     | Depende de | Gate (comando)                                              | Status |
|----|-------------------------------------------------------------------------------------------------------------------------------------------|------------------------------|------------|-------------------------------------------------------------|--------|
| 1  | Infra e settings: Pillow, `MEDIA_ROOT`, limites, `PUBLISH_BATCH_SIZE`, `META_UPLOAD_TIMEOUT`; compose com volume `media_data:/media` e Gunicorn `--timeout 180`; Dockerfile (`/media` com dono `app`); `.env.example` | AC-17 (sem MEDIA_URL público) | — | `… test apps.social.tests.test_publication_config` + `docker compose config` | todo |
| 2  | `images.py`: validação (formato real, bytes, pixels), re-encode sem EXIF (com `exif_transpose`), nome aleatório `[P]`                        | AC-5, AC-6                   | 1          | `… test apps.social.tests.test_images`                      | todo   |
| 3  | Modelos `Publication` e `PublicationTarget` + migration: snapshot da Página, único (publicação, Página), status geral derivado `[P]`        | AC-14, AC-15, AC-18          | 1          | `… test apps.social.tests.test_publication_models`          | todo   |
| 4  | `GraphClient.publish_photo`: multipart (`source`, `message`, `published=true`), Bearer, timeout de upload, parse de `id`/`post_id`, erros sanitizados `[P]` | AC-3, AC-9, AC-10, AC-19 | 1      | `… test apps.social.tests.test_publish_photo_client`        | todo   |
| 5  | `services/publishing.py`: criar publicação, claim atômico, lote de 5, mapeamento de erros, `needs_reauth`, recuperação de `sending`, logs     | AC-3, AC-8 a AC-14, AC-19    | 2, 3, 4    | `… test apps.social.tests.test_publishing`                  | todo   |
| 6  | `PublicationForm` + view/template de **nova publicação** (seleção de Páginas, "Marcar todas", confirmação, botão desabilitado no envio)     | AC-1, AC-2, AC-3, AC-4, AC-5, AC-7, AC-20 | 2, 3, 5 | `… test apps.social.tests.test_views_post_new`         | todo   |
| 7  | Detalhe da publicação, ação **enviar/continuar/tentar novamente** e **imagem protegida** (view autenticada, `nosniff`)                      | AC-11, AC-12, AC-16, AC-17, AC-18, AC-20 | 5, 6 | `… test apps.social.tests.test_views_post_detail`      | todo   |
| 8  | **Histórico** em `/publicacoes/` (substitui o placeholder): resumo, miniatura, status geral, contagens, estado vazio `[P]`                  | AC-15, AC-18                 | 3, 7       | `… test apps.social.tests.test_views_posts_list`            | todo   |
| 9  | Testes transversais de segurança: segredos e texto fora de logs/HTML/URLs, isolamento entre usuários, `/media/` inexistente, login obrigatório | AC-17, AC-18, AC-19, AC-20 | 6, 7, 8   | `… test apps.social.tests.test_publication_security`        | todo   |
| 10 | Documentação (README, `TESTING.md`, `STATE.md`, `.env.example`), subir o Docker e **UAT real** com 2 Páginas de teste                       | AC-1 a AC-20                 | 1–9        | `docker compose exec web python manage.py test` + `makemigrations --check` + roteiro manual | todo |

> Ordem sugerida: 1 → (2, 3, 4 em paralelo) → 5 → 6 → 7 → 8 → 9 → 10.
> Uma task só vira `done` quando o **gate passa**. Um commit por task.

## Plano de teste
- **Unidade:** `images.py` (JPEG/PNG válidos, formato falso, GIF/WebP/SVG, bytes e pixels acima do limite, EXIF removido, orientação aplicada,
  nome aleatório); status geral derivado; `GraphClient.publish_photo` com transporte mockado (multipart, Bearer, segredo fora da URL).
- **Integração:** `publishing.py` com banco real, Graph mockada e arquivo temporário em `MEDIA_ROOT` de teste: lote de 5, retry sem
  duplicar, falha parcial, `needs_reauth`, conta desconectada, claim atômico e recuperação de `sending` (relógio controlado).
- **Concorrência:** duas reivindicações do mesmo alvo → só uma chama a Meta (simulada com `update` condicional e `rowcount`).
- **Aceite:** um teste por AC (`test_AC_N_*`); cada linha das três **matrizes de decisão** vira um caso.
- **Segurança:** varredura de HTML, mensagens, logs (`assertLogs`) e URLs por token, segredo e **texto da publicação**; 404 para outro usuário;
  `/media/…` não responde.
- **UAT manual (task 10):** com 2 Páginas de teste, publicar texto + imagem nas duas; forçar uma falha (ex.: desconectar uma antes de enviar
  ou token inválido) e **tentar de novo**; conferir links dos posts no Facebook (resolve a questão do `permalink`); 6+ Páginas se houver, para
  validar os lotes.

## Divergências (SPEC_DEVIATION)
> Se a implementação precisar fugir da spec, registre aqui antes de seguir (ver `CLAUDE.md`).
- [ ] (nenhuma até agora)

## Checklist de Definition of Done
- [ ] Todos os AC verdes **pelo gate executável** (não por inspeção)
- [ ] Nenhum `SPEC_DEVIATION` pendente
- [ ] ADRs de decisões difíceis de reverter registrados (ADR-0004, ADR-0005)
- [ ] Glossário / context-map atualizados se mudaram
- [ ] Spec reflete o que foi construído
- [ ] `docs/STATE.md` atualizado (próximo passo / decisões)
- [ ] Volume `media_data` e Gunicorn `--timeout 180` ativos no Docker (verificados com `docker compose config`)
- [ ] UAT real concluído com 2 Páginas de teste; formato do link do post confirmado
- [ ] Issue [#1](https://github.com/thalisonwilker/social-hub/issues/1) (janela de duplicidade) referenciada no README/STATE como dívida conhecida
