---
name: STATE
description: Memória de trabalho volátil — onde paramos, próximo passo, bloqueios.
alwaysApply: true
---

# STATE — Memória viva do projeto

> Memória de trabalho **entre sessões** (humanos e agentes). É **volátil**: atualizada o tempo
> todo. Diferente do **ADR** (decisão durável e imutável). Decisão estrutural → ADR; estado do
> trabalho → aqui. Atualize ao **pausar/encerrar**; leia ao **retomar**. Use a skill `/handoff`.

**Última atualização:** 2026-11-17 por Thalyson

## Em andamento / próximo passo
> O que está aberto agora e a **próxima ação concreta** (não "continuar a feature" — diga o passo).
- Feature ativa: `specs/0005-threads-imagem/` — implementada (tasks 1–9, 371 testes verdes); falta o **UAT real** (task 10).
- **UAT da imagem (2026-11-17): OK** — Facebook + Threads com imagem 2/2 publicados (1ª tentativa falhou com o túnel recém-criado; reenvio funcionou). Falta só a falha forçada + Tentar novamente (túnel fora) e fechar o túnel.
- (feito) Para o UAT: subir um **túnel novo** (a URL muda), atualizar `THREADS_REDIRECT_URI` no `.env` e a URL de callback na Meta, recriar o container
  (`docker compose up -d --force-recreate`), publicar `exemplos/teste-publicacao.jpg` no Threads (e no Facebook), forçar uma falha (túnel fora) e **Tentar novamente**.
  Responder as questões abertas na [issue #5](https://github.com/thalisonwilker/social-hub/issues/5). Fechar o túnel ao terminar.
- Pendências de UAT das 0003/0004 (links abrem, Tentar novamente, POST/Bearer nos tokens do Threads); depois marcar as specs 0003, 0004 e 0005 como `implementado`.
- Issues abertas: [#1](https://github.com/thalisonwilker/social-hub/issues/1) duplicidade, [#2](https://github.com/thalisonwilker/social-hub/issues/2) diagnóstico da rota pública,
  [#3](https://github.com/thalisonwilker/social-hub/issues/3) orientar `PUBLIC_BASE_URL`, [#4](https://github.com/thalisonwilker/social-hub/issues/4) fila/worker, [#5](https://github.com/thalisonwilker/social-hub/issues/5) UAT da Meta.

## Decisões recentes
> Resumo cronológico. Se for difícil de reverter, vire um ADR e linke aqui.
- 2026-11-17: tokens de Página criptografados com Fernet, chave no `.env` — [ADR-0002](architecture/adr/0002-tokens-de-pagina-criptografados-com-fernet.md)
- 2026-11-17: OAuth com `config_id` + cliente Graph próprio no app `social`; Graph API fixada em v27.0 — [ADR-0003](architecture/adr/0003-integracao-meta-oauth-config-id-e-cliente-graph-proprio.md)
- 2026-11-17: Publicação síncrona em lotes de 5, idempotente por claim atômico — [ADR-0004](architecture/adr/0004-publicacao-sincrona-em-lotes-idempotente.md)
- 2026-11-17: Imagens sanitizadas (Pillow), volume `/media` e entrega por view autenticada — [ADR-0005](architecture/adr/0005-imagens-sanitizadas-volume-dedicado-e-entrega-autenticada.md)
- 2026-11-17: Threads com cliente próprio e token de 60 dias renovado sob demanda — [ADR-0006](architecture/adr/0006-threads-cliente-proprio-token-60-dias-renovacao-sob-demanda.md)
- 2026-11-17: Publicação por plataforma (despacho por alvo) e formulário misto com imagem condicional — [ADR-0007](architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md)
- 2026-11-17: URL pública temporária e assinada para a imagem do Threads — [ADR-0008](architecture/adr/0008-url-publica-temporaria-assinada-para-imagem-do-threads.md)
- 2026-11-17: Orçamento de tempo por requisição de publicação — [ADR-0009](architecture/adr/0009-orcamento-de-tempo-por-requisicao-de-publicacao.md)
- 2026-11-17: Seleção multi-Página numa tela do Hub; Páginas pendentes ficam na sessão, com tokens cifrados (TTL 10 min).

## Bloqueios
- [ ] UAT real das features 0003 e 0004 depende de você publicar nas suas Páginas/perfil de teste (a publicação é real e o Hub não exclui posts).
- [ ] O túnel de desenvolvimento muda de URL ao reiniciar: atualizar a Meta (Threads) e o `THREADS_REDIRECT_URI` quando isso acontecer; fechar o túnel ao terminar.

## Ideias adiadas / backlog técnico
- Cofre de segredos (Vault/KMS) para a chave Fernet → quando houver mais de um ambiente ou time.
- Limitação de tentativas de login (ex.: django-axes) → antes de expor o sistema publicamente.
- Lint e análise estática na CI (ruff, SAST) → ao configurar a esteira de CI.
- Renovação do token do Threads em segundo plano e webhooks → junto com o agendamento.
- Callbacks de desinstalação e exclusão de dados do Threads → antes do modo Live / App Review.
- Respostas/insights, carrossel/vídeo/`alt_text` no Threads e Instagram → próximas features.
- **Janela de duplicidade ao reenviar alvo `sending` preso** → [issue #1](https://github.com/thalisonwilker/social-hub/issues/1); revisitar ao introduzir fila/agendamento.
- Limpeza automática de imagens antigas e armazenamento externo (S3) → quando o volume `/media` crescer.

## Todos soltos
- [ ] Fazer backup da `META_TOKEN_ENCRYPTION_KEY` fora do repositório (perdê-la exige reconectar as Páginas).
- [ ] Fazer backup do volume `media_data` (imagens do histórico de publicações).
- [ ] Cadastrar política de privacidade e exclusão de dados no app Meta antes do modo Live / App Review.
