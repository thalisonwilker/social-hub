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
- Feature ativa: `specs/0004-threads-conectar-e-publicar/` — implementada (tasks 1–11); **UAT feito em parte** (2026-11-17).
- UAT já confirmado: conectar o perfil do Threads pelo túnel; publicação mista #3 (2 Páginas do Facebook + 1 perfil do Threads), 3/3 `published` com link,
  em ~15 s; o Threads recebeu só o texto (por spec); container de texto `FINISHED` em ~220 ms. A 0003 também publicou (#1 e #2).
- Falta confirmar: se os links dos posts abrem; **forçar uma falha e Tentar de novo**; e testar **POST** em `th_exchange_token`/`th_refresh_token` e **Bearer** nos GETs
  (ainda não testados). Depois marcar as specs 0003 e 0004 como `implementado`.
- Próxima feature candidata: **0005 — imagem no Threads** (exige URL pública temporária assinada e um ADR; hoje é non-goal).

## Decisões recentes
> Resumo cronológico. Se for difícil de reverter, vire um ADR e linke aqui.
- 2026-11-17: tokens de Página criptografados com Fernet, chave no `.env` — [ADR-0002](architecture/adr/0002-tokens-de-pagina-criptografados-com-fernet.md)
- 2026-11-17: OAuth com `config_id` + cliente Graph próprio no app `social`; Graph API fixada em v27.0 — [ADR-0003](architecture/adr/0003-integracao-meta-oauth-config-id-e-cliente-graph-proprio.md)
- 2026-11-17: Publicação síncrona em lotes de 5, idempotente por claim atômico — [ADR-0004](architecture/adr/0004-publicacao-sincrona-em-lotes-idempotente.md)
- 2026-11-17: Imagens sanitizadas (Pillow), volume `/media` e entrega por view autenticada — [ADR-0005](architecture/adr/0005-imagens-sanitizadas-volume-dedicado-e-entrega-autenticada.md)
- 2026-11-17: Threads com cliente próprio e token de 60 dias renovado sob demanda — [ADR-0006](architecture/adr/0006-threads-cliente-proprio-token-60-dias-renovacao-sob-demanda.md)
- 2026-11-17: Publicação por plataforma (despacho por alvo) e formulário misto com imagem condicional — [ADR-0007](architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md)
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
- Imagem no Threads (URL pública assinada), respostas/insights e Instagram → próximas features.
- **Janela de duplicidade ao reenviar alvo `sending` preso** → [issue #1](https://github.com/thalisonwilker/social-hub/issues/1); revisitar ao introduzir fila/agendamento.
- Limpeza automática de imagens antigas e armazenamento externo (S3) → quando o volume `/media` crescer.

## Todos soltos
- [ ] Fazer backup da `META_TOKEN_ENCRYPTION_KEY` fora do repositório (perdê-la exige reconectar as Páginas).
- [ ] Fazer backup do volume `media_data` (imagens do histórico de publicações).
- [ ] Cadastrar política de privacidade e exclusão de dados no app Meta antes do modo Live / App Review.
