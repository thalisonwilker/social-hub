---
name: spec
description: Contrato da feature 0009 — conectar o Instagram pela Página e publicar imagem + legenda (container, URL pública JPEG, estado Incerto). Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Instagram: conectar pela Página e publicar

> **Fonte da verdade.** Status: aprovado · implementado (aguardando UAT real)
> Os `AC-N` desta spec são numerados a partir de 1 (independentes das demais).

## Resumo
Ao conectar uma Página que tem **conta profissional do Instagram vinculada**, o Hub cria também a **Conta Instagram** (mesmo login e token da Página). No formulário misto o Instagram vira um destino: o worker cria o container com a imagem (URL pública temporária em JPEG), espera ficar pronto, publica e guarda o link — com o estado **Incerto** quando não dá para saber se publicou.

## Critérios de aceite

### AC-1: Descoberta do Instagram ao buscar as Páginas
- **Dado** um login da Meta concluído com `instagram_basic`
- **Quando** o Hub lista as Páginas
- **Então** pede também `instagram_business_account{id,username,name,profile_picture_url}` de cada Página e guarda, junto de cada Página pendente na sessão, o resumo do Instagram (ou nada, se não há); nenhum token novo é guardado e a sessão continua só com tokens cifrados

### AC-2: Conta Instagram criada com a Página
- **Dado** uma Página selecionada que tem Instagram vinculado
- **Quando** a seleção é confirmada
- **Então** é criada (ou atualizada, sem duplicar) uma `SocialAccount` `platform=instagram` do mesmo dono, com `external_id`, `username`, `name`, foto, `parent` = a Página e o **mesmo token cifrado**, status `active`; a Página continua conectada normalmente

### AC-3: Página sem Instagram
- **Dado** uma Página selecionada sem Instagram vinculado
- **Quando** a seleção é confirmada
- **Então** nenhuma Conta Instagram é criada e não há erro nem aviso

### AC-4: Reconexão atualiza ou remove a Conta Instagram
- **Dado** uma Página já conectada com Conta Instagram
- **Quando** ela é reconectada
- **Então** o token da Conta Instagram acompanha o da Página e o status volta a `active`; se a Página **não tem mais** Instagram vinculado, a Conta Instagram é removida

### AC-5: Desconectar
- **Dado** uma Página com Conta Instagram
- **Quando** a Página é desconectada
- **Então** a Conta Instagram dela também é removida (os alvos antigos mantêm o histórico, sem conta); desconectar **só** a Conta Instagram remove apenas ela, e só o dono pode fazê-lo

### AC-6: Imagem obrigatória com Instagram
- **Dado** o formulário com ao menos uma Conta Instagram marcada
- **Quando** não há imagem
- **Então** o formulário é rejeitado com a mensagem de que o Instagram exige imagem e nada é criado

### AC-7: Proporção e tamanho da imagem
- **Dado** o formulário com Instagram marcado e imagem válida
- **Quando** `largura / altura` está **fora de 0,8 a 1,91** (inclusive nos limites) ou a largura é **menor que 320 px**
- **Então** o formulário é rejeitado com mensagem clara (proporção aceita 4:5 a 1,91:1) e nada é criado; exatamente 0,8 e 1,91 são aceitos

### AC-8: Legenda do Instagram
- **Dado** o formulário com Instagram marcado
- **Quando** o texto tem **mais de 2.200 caracteres** ou **mais de 30 hashtags**
- **Então** o formulário é rejeitado indicando o limite e o valor atual e nada é criado; sem Instagram marcado, os limites das outras plataformas não mudam

### AC-9: Endereço público obrigatório
- **Dado** o formulário com Instagram marcado e imagem válida
- **Quando** não há endereço público HTTPS configurado (mesma regra do Threads, 0005 AC-4)
- **Então** o formulário é rejeitado mandando configurar `PUBLIC_BASE_URL` e nada é criado

### AC-10: Destinos mistos
- **Dado** uma publicação com imagem e destinos de Instagram, Facebook, Threads e/ou WhatsApp
- **Quando** é criada e enviada
- **Então** cada destino vira um alvo da sua plataforma, o resultado é por alvo (falha parcial permitida), as regras do Instagram **só** se aplicam quando há Instagram marcado e o envio dos demais destinos é idêntico ao das specs anteriores

### AC-11: URL pública JPEG do Instagram
- **Dado** uma publicação com imagem e endereço público configurado
- **Quando** o Hub monta a URL para o container do Instagram
- **Então** ela é `{endereço público}/publico/instagram.jpg?t=<token>` (token assinado sobre o id da publicação, validade `THREADS_IMAGE_URL_TTL_SECONDS`), nunca derivada do cabeçalho `Host`; uma imagem JPEG é entregue como está e uma **PNG é convertida para JPEG** (transparência sobre fundo branco) só nessa entrega, sem alterar a imagem armazenada

### AC-12: Rota pública do Instagram — escopo
- **Dado** a rota `GET/HEAD /publico/instagram.jpg?t=…`
- **Quando** é chamada **sem login** com token válido e há alvo **Instagram** em andamento (`pending`, `sending` ou `failed`)
- **Então** responde 200 com o JPEG (`HEAD` sem corpo, sem redirecionar) e `Cache-Control: no-store`, `nosniff`, `noindex`, sem cookie; com token ausente/adulterado/expirado/de outra publicação, sem imagem ou **sem alvo Instagram em andamento**, responde **404** uniforme (e outros métodos, 405); a rota do Threads **não** serve publicação cujo único alvo em andamento é Instagram, e esta não serve a que só tem Threads

### AC-13: Container do Instagram
- **Dado** um alvo do Instagram reivindicado, sem `external_container_id`
- **Quando** é enviado
- **Então** o Hub cria o container (`POST /{ig_id}/media` com `image_url` e `caption`; token no header `Authorization`) e **grava o `id` no alvo antes de esperar**, com log `instagram_container_created`

### AC-14: Publicar imagem + legenda
- **Dado** um container criado
- **Quando** o `status_code` chega a `FINISHED` dentro da espera (consulta a cada 3 s até `INSTAGRAM_CONTAINER_WAIT_SECONDS`, padrão 60; no modo inline limitada pelo orçamento restante − folga)
- **Então** o Hub chama `POST /{ig_id}/media_publish` com `creation_id`, lê o `permalink` (melhor esforço) e o alvo fica `published` com `external_post_id` e link; se a consulta já diz `PUBLISHED`, marca `published` sem republicar

### AC-15: Container com erro
- **Dado** um container do Instagram
- **Quando** o `status_code` é `ERROR` ou `EXPIRED`
- **Então** o alvo fica `failed` com mensagem amigável de que o Instagram não conseguiu processar a imagem, **nada é publicado**, o `external_container_id` é **descartado** (próximo envio cria outro, com nova URL) e só o enum vai ao log (`instagram_container_error code=…`)

### AC-16: Espera esgotada
- **Dado** um container que continua `IN_PROGRESS`
- **Quando** o limite de espera termina
- **Então** o alvo fica `failed` (reenviável) com mensagem de que o Instagram ainda está processando, **sem** publicar, e o `external_container_id` é **mantido**

### AC-17: Retomada reutiliza o container
- **Dado** um alvo com `external_container_id` gravado (falha mantida ou reenvio)
- **Quando** é reenviado
- **Então** o container é **reutilizado** (nenhum novo `POST …/media`, nenhuma nova URL) e o fluxo segue na consulta de status

### AC-18: Publicação sem resposta vira Incerto
- **Dado** um container `FINISHED`
- **Quando** `media_publish` é enviado e a resposta não vem (timeout/interrompido) ou chega inválida depois de aceita
- **Então** o alvo vira `uncertain` (nunca é reenviado sozinho) com a mensagem padrão de incerteza, e o usuário resolve por **"Já foi publicado"** ou **"Reenviar"** como nas demais plataformas (0007)

### AC-19: Erros amigáveis e reconexão
- **Dado** uma falha da Graph API no envio ao Instagram
- **Quando** o código é de token (102/190), permissão, limite de requisições/publicações, bloqueio ou rede
- **Então** a mensagem do alvo é amigável e **nunca** o texto cru da Meta; erro de token marca a Conta Instagram **e** a Página vinculada como `needs_reauth`; alvo de conta em `needs_reauth` não chama a Meta

### AC-20: Mesmo publicador no worker e no modo inline
- **Dado** `PUBLISH_MODE=worker` ou `inline`
- **Quando** um alvo do Instagram é processado
- **Então** o resultado é o mesmo (estados, mensagens, container reutilizado); no worker a espera é `INSTAGRAM_CONTAINER_WAIT_SECONDS` inteira, no inline é limitada pelo orçamento (0005 AC-17/AC-18)

### AC-21: Segredos e isolamento
- **Dado** o Hub em operação
- **Quando** há conexão, envio ou acesso à rota pública
- **Então** token, URL assinada, legenda e corpo de resposta da Meta **não** aparecem em logs, HTML, JSON nem mensagens; um usuário não vê nem opera contas/alvos de outro; o token da Conta Instagram é guardado só cifrado

### AC-22: Regressão e documentação
- **Dado** as specs 0002–0008 e o ADR-0008
- **Quando** esta feature é entregue
- **Então** todos os seus critérios continuam passando; o **ADR-0013** registra a decisão; o ADR-0008 recebe nota apontando que a rota pública também serve ao Instagram; README, `.env.example`, glossário e `STATE.md` são atualizados

## Matrizes de decisão

### Formulário (Instagram marcado)
| Imagem | Proporção (l/a) | Largura | Legenda | Endereço público | Resultado | AC |
|--------|-----------------|---------|---------|------------------|-----------|----|
| ausente | — | — | — | — | Erro: Instagram exige imagem | AC-6 |
| válida | < 0,8 ou > 1,91 | — | — | — | Erro de proporção | AC-7 |
| válida | 0,8 … 1,91 | < 320 | — | — | Erro de tamanho | AC-7 |
| válida | 0,8 … 1,91 | ≥ 320 | > 2.200 car. ou > 30 hashtags | — | Erro de legenda | AC-8 |
| válida | 0,8 … 1,91 | ≥ 320 | ok | ausente | Erro de endereço público | AC-9 |
| válida | 0,8 … 1,91 | ≥ 320 | ok | configurado | Cria (alvo Instagram + demais) | AC-10 |

### Container / publicação
| Situação | Resultado | AC |
|----------|-----------|----|
| sem `external_container_id` | cria container, grava id, espera | AC-13 |
| com `external_container_id` | reutiliza; não cria nem gera URL | AC-17 |
| `IN_PROGRESS` dentro da espera | continua consultando (3 s) | AC-14 |
| `FINISHED` | `media_publish`; permalink; `published` | AC-14 |
| `PUBLISHED` | `published` sem republicar | AC-14 |
| `ERROR` / `EXPIRED` | `failed`; descarta id; sem publicar | AC-15 |
| espera esgotada | `failed`; mantém id | AC-16 |
| `media_publish` sem resposta | `uncertain` | AC-18 |
| código 102/190 | `failed` + `needs_reauth` (Instagram e Página) | AC-19 |

### Rota pública `/publico/instagram.jpg`
| Token | Imagem | Alvo Instagram em andamento | Resposta | AC |
|-------|--------|-----------------------------|----------|----|
| válido | sim (JPEG) | sim | 200 JPEG direto | AC-12 |
| válido | sim (PNG) | sim | 200 JPEG convertido | AC-11, AC-12 |
| válido, `HEAD` | sim | sim | 200 sem corpo | AC-12 |
| válido | sim | só Threads / todos `published` | 404 | AC-12 |
| ausente / adulterado / expirado / de outra publicação | — | — | 404 | AC-12 |
| método ≠ GET/HEAD | — | — | 405 | AC-12 |

## Casos de borda e erros
- Imagem convertida para JPEG acima de 8 MB: o Instagram recusa → container `ERROR` → AC-15.
- Container expira (24 h) com id gravado: a consulta devolve `EXPIRED` → AC-15 e o reenvio cria outro.
- Legenda com links: aceitos (no Instagram não são clicáveis); sem validação.
- Limite de ~100 publicações por 24 h por conta: mensagem de limite (AC-19).
- Conta Instagram cujo token não pode ser lido: falha com a mensagem de credenciais, sem chamar a Meta.
- Página reconectada com **outro** Instagram vinculado: a conta antiga é removida e a nova criada (AC-4).
- Conta Instagram removida manualmente volta a ser criada ao reconectar a Página (AC-2).
- Alvo cuja conta foi removida: não reenviável; histórico mantido (AC-5).

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- Instagram sem Página (Instagram Login / login unificado) e renovação de token própria.
- Reels, Stories, carrossel, vídeo, marcações, `alt_text`, local, primeiro comentário.
- Cortar/reenquadrar imagem ou truncar legenda automaticamente.
- Agendamento, insights, comentários, DMs, App Review e modo Live.
- Escolher, por Página, se o Instagram é conectado (é automático).
- Confirmar no código o comportamento não documentado da Graph API do Instagram (fica para o UAT).

## Rastreabilidade
- Product: `./product.md` · Design: `./design.md` · Domínio: `./domain.md` · Tasks: `./tasks.md`
- ADRs: [ADR-0003](../../docs/architecture/adr/0003-integracao-meta-oauth-config-id-e-cliente-graph-proprio.md), [ADR-0007](../../docs/architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md), [ADR-0008](../../docs/architecture/adr/0008-url-publica-temporaria-assinada-para-imagem-do-threads.md), [ADR-0011](../../docs/architecture/adr/0011-publicacao-em-segundo-plano-worker-no-banco-estado-incerto-e-recuperacao-sem-reenvio.md); novo ADR-0013 (task 1)
