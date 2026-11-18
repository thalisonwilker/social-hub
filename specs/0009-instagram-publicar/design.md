---
name: design
description: Technical Design Doc da feature 0009 — Instagram via Página (Graph API com login do Facebook), publicador por container, URL pública JPEG. Puxe ao implementar ou revisar a feature.
alwaysApply: false
---

# Technical Design Doc — Instagram: conectar pela Página e publicar

> **Tier:** arquitetural · **Status:** aprovado
> **Autor:** Claude + Thalyson · **Data:** 2026-11-18
> Decisão difícil de reverter → **ADR-0013** (task 1).

## Links e artefatos
| Artefato | Onde | Link |
|----------|------|------|
| Spec · Product · Domínio · Tasks | repositório | `./spec.md` · `./product.md` · `./domain.md` · `./tasks.md` |
| ADRs base | repositório | [ADR-0003](../../docs/architecture/adr/0003-integracao-meta-oauth-config-id-e-cliente-graph-proprio.md) · [ADR-0007](../../docs/architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md) · [ADR-0008](../../docs/architecture/adr/0008-url-publica-temporaria-assinada-para-imagem-do-threads.md) · [ADR-0011](../../docs/architecture/adr/0011-publicacao-em-segundo-plano-worker-no-banco-estado-incerto-e-recuperacao-sem-reenvio.md) |

## Contexto da funcionalidade
O Hub conecta Páginas pelo Login do Facebook for Business (`config_id`, ADR-0003) e publica por plataforma no worker (ADR-0007/0011). O Threads já usa container + URL pública assinada (ADR-0008). A Graph API do Instagram (login do Facebook) tem o mesmo desenho: **container → espera → publicar**, a imagem é **buscada pela Meta** numa URL pública, e o token é o **da Página** vinculada. Aproveitamos quase tudo.

## Goals / Non-goals
**Goals** — conectar o Instagram pela Página (sem novo OAuth); publicar imagem + legenda pelo worker; validações no formulário; sem duplicar (Incerto).
**Non-goals** — Instagram sem Página; Reels/Stories/carrossel/vídeo; agendamento; App Review; cortar imagem.

## Design proposto

### Conexão (descoberta automática por Página)
- `GraphClient.list_pages` passa a pedir também `instagram_business_account{id,username,name,profile_picture_url}` (campo da Página; exige `instagram_basic`). A sessão de Páginas pendentes guarda o resumo do Instagram de cada Página (sem token extra: o Instagram usa o token da Página, já cifrado).
- `save_selected`, ao salvar uma Página, **cria/atualiza** a Conta Instagram (`platform=instagram`, `external_id` = id da conta, `username`, `name`, foto, `parent` = Página, mesmo `access_token_enc`). Se a Página **não** tem Instagram vinculado, não cria nada; se tinha e **perdeu** o vínculo, a Conta Instagram é removida.
- `SocialAccount` ganha `Platform.INSTAGRAM` e `parent` (FK `self`, `null=True`, `CASCADE`). Migration 0007. Desconectar a Página remove a Conta Instagram; desconectar só o Instagram remove só ela (volta se a Página for reconectada).
- Token inválido (102/190) numa chamada do Instagram marca **as duas contas** (Instagram e Página) como `needs_reauth`.

### Publicação (worker; mesmo caminho do inline)
`dispatch_claimed` ganha o ramo `instagram` → `instagram_publish.publish_image(...)` (módulo novo, irmão de `threads_publish`):
1. **Container:** `POST /{ig_id}/media` com `image_url` (URL pública JPEG) e `caption` (token no header). `id` **gravado** em `external_container_id` antes de esperar (retomada sem recriar).
2. **Espera:** `GET /{container_id}?fields=status_code` a cada 3 s até `INSTAGRAM_CONTAINER_WAIT_SECONDS` (padrão 60; no modo inline limitada pelo orçamento como no Threads). `FINISHED` segue; `ERROR`/`EXPIRED` → falha e descarta o id; `PUBLISHED` → publicado sem republicar; tempo esgotado → falha e **mantém** o id.
3. **Publicar (chamada com efeito):** `POST /{ig_id}/media_publish` com `creation_id`, `effect=True` → sem resposta = **Incerto**.
4. **Permalink:** `GET /{media_id}?fields=permalink` (melhor esforço).
Erros de transporte/limite reaproveitam `friendly_error` e `classify_request_error`; o código de limite diário do Instagram é mapeado à mensagem de limite.

### Imagem pública JPEG (generaliza o ADR-0008)
- Nova rota anônima `GET/HEAD /publico/instagram.jpg?t=<token>` (mesmo token assinado e TTL; **escopo próprio**: só serve com alvo **Instagram** em andamento). A rota do Threads continua exigindo alvo **Threads** em andamento — uma URL de um não abre o outro.
- Imagem JPEG é entregue como está; **PNG é convertido para JPEG** na entrega (achata transparência sobre branco, qualidade 92). A imagem armazenada e as do Facebook/Threads não mudam.
- Mesmos cabeçalhos (`no-store`, `nosniff`, `noindex`, sem cookie), 404 uniforme e log sem query (gunicorn já configurado).

### Formulário
Contas Instagram entram na lista de destinos. Com Instagram marcado: **imagem obrigatória**, largura/altura entre **0,8 e 1,91**, largura ≥ 320 px, legenda ≤ 2.200 caracteres e ≤ 30 hashtags, e endereço público HTTPS configurado. Violação → formulário rejeitado, nada criado.

## Cobertura dos 5 eixos
1. **Tech stack:** sem dependência nova (Pillow, requests, Django já presentes).
2. **Arquitetura base:** novo publicador na borda de integração (`services/`), despachado por plataforma; domínio e camadas inalterados. `GraphClient` ganha 4 métodos finos (`create_instagram_container`, `instagram_container_status`, `publish_instagram_container`, `get_instagram_permalink`).
3. **Infra:** nenhuma. Config nova: `INSTAGRAM_CONTAINER_WAIT_SECONDS`. Exige `PUBLIC_BASE_URL` HTTPS (como o Threads). Reversão: remover o ramo do despacho; contas Instagram ficam inertes.
4. **Qualidade:** Graph API **sempre mockada** no transporte; um teste por AC; regressão das suítes 0002–0008.
5. **Observabilidade:** logs só com ids, plataforma e enum (`instagram_container_created`, `instagram_container_error code=…`, `publish_ok platform=instagram`); nada de token, URL assinada, legenda ou resposta da Meta.

## Mapa de dependências
| Dependência | Tipo | Descrição | Endpoints |
|-------------|------|-----------|-----------|
| Graph API (Instagram, login do Facebook) | REST | container e publicação de imagem | `POST /{ig_id}/media` · `GET /{container}?fields=status_code` · `POST /{ig_id}/media_publish` · `GET /{media}?fields=permalink` |
| Graph API (Página) | REST | descobrir o Instagram vinculado | `GET /me/accounts?fields=…,instagram_business_account{…}` |
| Pillow | biblioteca | conversão PNG→JPEG na entrega | `Image.convert`, `save(JPEG)` |

## Solução
| # | Bloco | Status |
|---|-------|--------|
| 1 | Modelo (`Platform.INSTAGRAM`, `parent`) + migration + ADR-0013 | definido |
| 2 | Descoberta e vínculo na conexão da Página | definido |
| 3 | Métodos do Instagram no `GraphClient` | definido |
| 4 | Imagem pública JPEG (rota `/publico/instagram.jpg`) | definido |
| 5 | Validações do formulário | definido |
| 6 | Publicador (`instagram_publish`) e despacho | definido |
| 7 | Telas (contas, destinos, histórico) e erros amigáveis | definido |
| 8 | Docs, segurança transversal e UAT real | definido |

## Alternativas consideradas
| Alternativa | Prós | Contras | Decisão |
|-------------|------|---------|---------|
| **A — via Página** (escolhida) | Reaproveita login, token (Fernet), `GraphClient`, ADR-0008 | Exige Página vinculada; configuração "API com login do Facebook" aparece como **obsoleta** no painel | Escolhida: menor mudança; troca futura isolada no cliente/conexão |
| B — Instagram Login / login unificado | Sem Página; recomendada pela Meta | Outro OAuth, token próprio (60 dias, renovação), outro cliente; **comportamento ainda não confirmado** | Adiada (non-goal); decidir após UAT da A |
| Cortar a imagem automaticamente | Aceita qualquer imagem | Altera o enquadramento sem o usuário ver | Rejeitada |
| Converter PNG→JPEG ao salvar | Uma única imagem | Muda Facebook/Threads também | Rejeitada: converte só na entrega ao Instagram |

## Trade-offs e consequências
Ganhamos o Instagram com ~1 módulo novo e reuso do worker, do estado Incerto e da URL assinada. Aceitamos depender de uma configuração marcada como obsoleta pela Meta e de uma rota pública a mais (escopo próprio, só com alvo Instagram em andamento).

## Riscos
| Risco | Descrição | Prob. × Impacto | Mitigação |
|-------|-----------|-----------------|-----------|
| Config obsoleta | Meta pode descontinuar "API com login do Facebook" | baixo × alto | Isolar no cliente/conexão; alternativa B documentada |
| Doc ≠ realidade | Campos/códigos/limites vieram da doc, não confirmados | médio × médio | UAT real; erros desconhecidos viram mensagem genérica sem texto cru |
| URL inalcançável | Túnel caiu / `ALLOWED_HOSTS` | médio × baixo | Container `ERROR`/espera esgotada → falha reenviável (como Threads) |
| Duplicar post | `media_publish` sem resposta | baixo × alto | Estado Incerto (nunca reenvia sozinho) |
| Imagem > 8 MB após JPEG | Instagram recusa | baixo × baixo | Falha com mensagem; limite de 8 MB documentado como borda |

## Roadmap da feature
| Fase | Entrega | Depende de |
|------|---------|------------|
| 1 (MVP) | Conectar via Página + publicar imagem/legenda + UAT real | — |
| 2 | Instagram sem Página (Instagram Login), Stories/carrossel | 1 |

## Questões em aberto
- [ ] O `config_id` atual retorna `instagram_business_account` e permite `instagram_content_publish` (confirmar no UAT; nome exato do código de erro do limite diário).
- [ ] Decidir A × B (login unificado) depois do UAT.
