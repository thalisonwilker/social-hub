---
name: STATE
description: Memória de trabalho volátil — onde paramos, próximo passo, bloqueios.
alwaysApply: true
---

# STATE — Memória viva do projeto

> Memória de trabalho **entre sessões** (humanos e agentes). É **volátil**: atualizada o tempo
> todo. Diferente do **ADR** (decisão durável e imutável). Decisão estrutural → ADR; estado do
> trabalho → aqui. Atualize ao **pausar/encerrar**; leia ao **retomar**. Use a skill `/handoff`.

**Última atualização:** 2026-11-21 por Thalyson

## Em andamento / próximo passo
> O que está aberto agora e a **próxima ação concreta** (não "continuar a feature" — diga o passo).
- **0017 central de conexões**: implementada (985 testes verdes, commitada na `main` (1f47aab, sem push); migração `social.0010_account_followers_count`; `npm run build` refeito). `/contas/` com coluna de ícones + painel, troca sem recarregar (`static/js/connections.js`), seguidores lidos ao "Atualizar informações" (Facebook/Instagram; Threads mostra "—" porque exigiria `threads_manage_insights`). UAT no navegador feito com dados fictícios (desktop, celular, claro/escuro, teclado). Próximo: **seu UAT com contas reais**; confirmar que o Instagram devolve `followers_count` com o token da Página; depois fazer o push.
- **0016 recuperação de senha**: implementada (952 testes verdes, nada commitado; migração `accounts.0004`). UAT no navegador feito com e-mail em arquivo (`var/emails/`): pedido → link → nova senha → login com aviso; reuso do link recusado. Próximo: **configurar o SMTP real no `.env`** (`EMAIL_HOST`…`DEFAULT_FROM_EMAIL`) e conferir a entrega e o `PUBLIC_BASE_URL` (hoje aponta para um túnel antigo); depois commitar. ADR-0017.
- **0015 revisão do cadastro**: implementada (925 testes verdes, nada commitado; migração `accounts.0003_unique_lower_email` — índice único em `lower(email)`). Botão "Registrar" com carregamento e envio único, mensagem final nova, nomes com acento decomposto, e-mail do navegador igual ao do Django, erros acessíveis. UAT no navegador feito. Próximo: commitar.
- **0014 jornada de login**: implementada (916 testes verdes, nada commitado; migração `accounts.0002_loginattempt`; `npm run build:css` refeito). UAT no navegador feito: validação antes do envio, 401 genérico, login certo → seleção de perfil, carregamento "Entrando…" com envio único. Próximo: **seu UAT** (bloqueio 429 com 5 erros, tema claro, celular) e commitar. O `admin` agora entra com o **e-mail** (`DJANGO_SUPERUSER_EMAIL`), inclusive em `/admin/`. ADR-0016.
- **0013 cadastro de usuário**: implementada (885 testes verdes, nada commitado; migração `accounts.0001_initial`; `npm run build` refeito). UAT no navegador feito: validação campo a campo, botão só habilita com tudo válido, cadastro → login com aviso, login com o e-mail em outra caixa. Próximo: **seu UAT** (tema claro, celular, duplo clique em Criar conta) e commitar. Login agora é por e-mail (`EmailOrUsernameBackend`; `admin` continua pelo username). Texto real de Termos/Política e limite de tentativas no cadastro/login ficam para depois.
- **0012 interface MUI**: implementada (849 testes verdes, nada commitado). Bundle `frontend/mui/*` → `static/dist/js/mui.js` (`npm run build`); ADR-0015. Próximo: **UAT visual** nas telas restantes (detalhe/lista de publicações, WhatsApp, seleção de Páginas, Minha conta) e em celular; `<input type=file>` e `<details>` ficam nativos. Telas já conferidas no navegador: login, seleção, wizard, dashboard, contas, nova publicação (claro/escuro) e diálogo de confirmação.
- **0011 perfis + wizard + login novo**: implementada (841 testes verdes, nada commitado; CSS rebuild com `npm run build`). Próximo: **UAT visual** (login, seleção, wizard com OAuth real do Facebook/Threads voltando ao dashboard) e commitar. Contas existentes migram para o perfil "Principal". Twitter/X e TikTok são só ícones "Em breve"; renomear/excluir perfil ficou fora do escopo.
- **0010 excluir publicações**: implementada (tasks 1–6, 810 testes verdes, nada commitado). Próximo: **UAT real** — habilitar `threads_delete` no app Meta e reconectar o Threads; apagar um post de teste no Facebook e no Threads e conferir; repetir (confirmar o código de "objeto inexistente") e **Remover do Hub**; checar se o Facebook apaga posts criados fora do app. ADR-0014.
- **0009 Instagram (via Página)**: implementada (tasks 1–9, 760 testes verdes, nada commitado). Próximo: **UAT real** — confirmar que o `config_id` inclui `instagram_basic` + `instagram_content_publish`, **reconectar a Página** (a conta Instagram aparece sozinha), subir túnel HTTPS/`PUBLIC_BASE_URL` e publicar `exemplos/teste-publicacao.jpg`; confirmar o campo `instagram_business_account`, o código de erro do limite diário e a decisão A × B (login unificado). ADR-0013.
- **0008 gerar imagem com IA (Gemini)**: implementada (655 testes verdes, nada commitado). Próximo: UAT com chave real do Gemini e confirmar os IDs de modelo em `GEMINI_IMAGE_MODELS` (padrões provisórios); depois commitar e marcar a spec como validada. ADR-0012.
- Feature ativa: nenhuma. `specs/0006-whatsapp-status/` **implementada** (tasks 1–10, 496 testes verdes) com UAT real na Evolution 2.3.7: cadastro, falha + Tentar novamente e envio real (texto e imagem em data URI) funcionaram. Aprendizados: timeout não é falha (a Evolution concluiu depois e o reenvio duplicou o Status; ~2265 contatos), `allContacts` = contatos que a Evolution conhece (não a agenda). Pendências: apagar o Status duplicado de teste pelo celular; fila/idempotência para o WhatsApp (issues #1 e #4).
- Antes: `specs/0005-threads-imagem/` — implementada; UAT da imagem OK (falta só a falha forçada + Tentar novamente com o túnel fora).
- **UAT da imagem (2026-11-17): OK** — Facebook + Threads com imagem 2/2 publicados (1ª tentativa falhou com o túnel recém-criado; reenvio funcionou). Falta só a falha forçada + Tentar novamente (túnel fora) e fechar o túnel.
- (feito) Para o UAT: subir um **túnel novo** (a URL muda), atualizar `THREADS_REDIRECT_URI` no `.env` e a URL de callback na Meta, recriar o container
  (`docker compose up -d --force-recreate`), publicar `exemplos/teste-publicacao.jpg` no Threads (e no Facebook), forçar uma falha (túnel fora) e **Tentar novamente**.
  Responder as questões abertas na [issue #5](https://github.com/thalisonwilker/social-hub/issues/5). Fechar o túnel ao terminar.
- Pendências de UAT das 0003/0004 (links abrem, Tentar novamente, POST/Bearer nos tokens do Threads); depois marcar as specs 0003, 0004 e 0005 como `implementado`.
- Issues abertas: [#1](https://github.com/thalisonwilker/social-hub/issues/1) duplicidade, [#2](https://github.com/thalisonwilker/social-hub/issues/2) diagnóstico da rota pública,
  [#3](https://github.com/thalisonwilker/social-hub/issues/3) orientar `PUBLIC_BASE_URL`, [#4](https://github.com/thalisonwilker/social-hub/issues/4) fila/worker, [#5](https://github.com/thalisonwilker/social-hub/issues/5) UAT da Meta.

## Decisões recentes
> Resumo cronológico. Se for difícil de reverter, vire um ADR e linke aqui.
- 2026-11-21: Seguidores do Threads ficam fora da 0017 (exigiria a permissão `threads_manage_insights` e reconexão); Facebook/Instagram usam `followers_count` com as permissões atuais — spec 0017.
- 2026-11-20: E-mail pelo SMTP nativo do Django (arquivo em `var/emails/` sem SMTP) e recuperação de senha com token de uso único em hash, limites no banco e link sem token nos logs — [ADR-0017](architecture/adr/0017-envio-de-e-mail-smtp-e-recuperacao-de-senha-com-token-em-hash.md)
- 2026-11-19: Limite de tentativas e idempotência do login no banco (`LoginAttempt`, e-mail como HMAC, `REMOTE_ADDR`, retenção 24 h); login só por e-mail — [ADR-0016](architecture/adr/0016-limitacao-de-tentativas-e-idempotencia-do-login-no-banco.md)
- 2026-11-19: Cadastro público com `username` = e-mail em minúsculas e login por e-mail sem diferenciar maiúsculas; trava de idempotência no banco (chave assinada de 2 h, única, gravada na transação do usuário) porque há 2 workers e nenhum cache compartilhado — spec 0013.
- 2026-11-17: tokens de Página criptografados com Fernet, chave no `.env` — [ADR-0002](architecture/adr/0002-tokens-de-pagina-criptografados-com-fernet.md)
- 2026-11-17: OAuth com `config_id` + cliente Graph próprio no app `social`; Graph API fixada em v27.0 — [ADR-0003](architecture/adr/0003-integracao-meta-oauth-config-id-e-cliente-graph-proprio.md)
- 2026-11-17: Publicação síncrona em lotes de 5, idempotente por claim atômico — [ADR-0004](architecture/adr/0004-publicacao-sincrona-em-lotes-idempotente.md)
- 2026-11-17: Imagens sanitizadas (Pillow), volume `/media` e entrega por view autenticada — [ADR-0005](architecture/adr/0005-imagens-sanitizadas-volume-dedicado-e-entrega-autenticada.md)
- 2026-11-17: Threads com cliente próprio e token de 60 dias renovado sob demanda — [ADR-0006](architecture/adr/0006-threads-cliente-proprio-token-60-dias-renovacao-sob-demanda.md)
- 2026-11-17: Publicação por plataforma (despacho por alvo) e formulário misto com imagem condicional — [ADR-0007](architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md)
- 2026-11-17: URL pública temporária e assinada para a imagem do Threads — [ADR-0008](architecture/adr/0008-url-publica-temporaria-assinada-para-imagem-do-threads.md)
- 2026-11-17: Orçamento de tempo por requisição de publicação — [ADR-0009](architecture/adr/0009-orcamento-de-tempo-por-requisicao-de-publicacao.md)
- 2026-11-17: WhatsApp (Status) via Evolution — conta = instância com chave cifrada, host só do servidor, imagem em base64, Baileys não oficial — [ADR-0010](architecture/adr/0010-whatsapp-status-via-evolution-api-instancia-chave-cifrada-e-host-fixo.md)
- 2026-11-18: Exclusão em duas ações (Remover do Hub / Apagar na plataforma), `deleted_at` no alvo, Facebook e Threads — [ADR-0014](architecture/adr/0014-excluir-publicacoes-remover-do-hub-e-apagar-na-plataforma.md)
- 2026-11-18: Instagram pela Página (conta vinculada, token da Página, container, imagem JPEG em `/publico/instagram.jpg`, Incerto no `media_publish`) — [ADR-0013](architecture/adr/0013-instagram-via-pagina-conta-vinculada-token-da-pagina-e-imagem-jpeg-publica.md)
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
