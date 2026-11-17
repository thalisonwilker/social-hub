---
name: spec
description: Contrato da feature 0005 — imagem + texto no Threads via URL pública temporária e assinada, com orçamento de tempo por requisição. Base enquanto a feature está ativa.
alwaysApply: true
---

# Spec — Threads: publicar imagem junto com o texto

> **Fonte da verdade.** Status: aprovado
> Os critérios de aceite são (a) o contrato com o negócio, (b) o oráculo de teste,
> (c) o prompt para o agente de IA implementar. Os `AC-N` desta spec são numerados a partir de 1 (independentes das 0003/0004).

## Resumo
Quando a publicação tem imagem, o alvo do Threads passa a enviar **imagem + texto**: o Hub serve a imagem sanitizada numa **URL pública temporária e assinada**, a Meta a baixa, e o alvo só é publicado quando o container de imagem estiver pronto — ou **falha** de forma reenviável, sem nunca degradar para só texto. O tempo de cada requisição de envio passa a ter um **orçamento**.

## Critérios de aceite
> Cada `AC-N` reaparece em `tasks.md` (coluna "Cobre AC"), no teste que o valida e no commit.

### AC-1: Formulário aceita imagem com Threads
- **Dado** um formulário com texto válido e ao menos um perfil do Threads marcado (com ou sem Página do Facebook)
- **Quando** uma imagem válida é enviada
- **Então** ela é validada e sanitizada (como na 0003), **gravada** na publicação e **não** aparece aviso de imagem ignorada; sem imagem, valem as regras da 0004 (obrigatória só com Página do Facebook)

### AC-2: Imagem inválida com Threads
- **Dado** um formulário com Threads marcado
- **Quando** a imagem enviada é inválida (formato, tamanho, corrompida)
- **Então** o formulário é rejeitado com o erro da imagem e nada é criado (antes, com só Threads, a imagem era ignorada)

### AC-3: Proporção máxima
- **Dado** um formulário com Threads marcado e imagem válida
- **Quando** `max(largura, altura) / min(largura, altura)` é **maior que 10** (em qualquer sentido)
- **Então** o formulário é rejeitado com mensagem de proporção e nada é criado; exatamente 10:1 é aceito; largura < 320 ou dimensão > 4096 **não** bloqueiam

### AC-4: Endereço público obrigatório para imagem no Threads
- **Dado** um formulário com Threads marcado e imagem presente
- **Quando** não há endereço público HTTPS configurado (`PUBLIC_BASE_URL` vazio e `THREADS_REDIRECT_URI` não HTTPS)
- **Então** o formulário é rejeitado com erro claro mandando configurar `PUBLIC_BASE_URL`, e nada é criado; só Facebook, ou Threads **sem** imagem, não exigem endereço público

### AC-5: Montagem da URL pública assinada
- **Dado** uma publicação com imagem e endereço público configurado
- **Quando** o Hub gera a URL para o container
- **Então** ela é `{endereço público}/publico/imagem.{jpg|png}?t=<token>` (extensão conforme o tipo guardado), com o token assinado sobre o id da publicação e validade `THREADS_IMAGE_URL_TTL_SECONDS` (padrão 1800); a base é `PUBLIC_BASE_URL` ou, se vazio, a origem do `THREADS_REDIRECT_URI` — **nunca** o cabeçalho `Host`

### AC-6: Rota pública serve a imagem
- **Dado** um token válido e dentro da validade, uma publicação com imagem e ao menos um alvo `threads` em `pending`, `sending` ou `failed`
- **Quando** `GET` (ou `HEAD`) `/publico/imagem.<ext>?t=<token>` é feito **sem login**
- **Então** a resposta é 200 com a imagem sanitizada e o `Content-Type` guardado (`HEAD` sem corpo), **direto, sem redirecionar**, e é logado `public_image_served`

### AC-7: Rota pública recusa token inválido
- **Dado** a rota pública
- **Quando** o token está ausente, adulterado, assinado com outra chave, de **outra publicação** que não a da imagem pedida ou **expirado**
- **Então** a resposta é **404** genérica (idêntica nos casos), nada da imagem é revelado e é logado `public_image_rejected reason=invalid|expired`

### AC-8: Rota pública só enquanto há alvo em andamento
- **Dado** um token válido
- **Quando** a publicação não tem imagem, ou **não tem alvo `threads` em andamento** (todos `published`, ou só alvos do Facebook)
- **Então** a resposta é **404** genérica e é logado `public_image_rejected reason=no_image|not_in_flight`

### AC-9: Cabeçalhos e escopo mínimo da rota pública
- **Dado** uma resposta 200 ou 404 da rota pública
- **Quando** ela é entregue
- **Então** traz `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` e `X-Robots-Tag: noindex`, **sem** `Set-Cookie` de sessão; só aceita `GET`/`HEAD` (outros métodos → 405); as demais rotas continuam exigindo login (inclusive `/publicacoes/<id>/imagem/`)

### AC-10: Token fora dos logs
- **Dado** o Hub em operação
- **Quando** a rota pública é acessada ou o envio ao Threads ocorre
- **Então** o token e a URL assinada **não** aparecem em logs do app, mensagens ao usuário, HTML nem exceções; o `docker/gunicorn.conf.py` registra o caminho **sem a query** (`%(U)s`), e o `docker-compose`/`Dockerfile` o usam

### AC-11: Container de imagem
- **Dado** um alvo do Threads, reivindicado, de publicação **com imagem**, sem `external_container_id`
- **Quando** ele é enviado
- **Então** a renovação do token é avaliada (0004 AC-12), é criado o container (`POST /v1.0/{user_id}/threads` com `media_type=IMAGE`, `image_url` e `text`, `access_token` no **corpo**) e o `id` é **gravado** no alvo (`external_container_id`) antes da espera; é logado `threads_image_container_created`

### AC-12: Publicar imagem + texto
- **Dado** um container de imagem criado
- **Quando** o status chega a `FINISHED` dentro da espera (consulta a cada 3 s até `THREADS_IMAGE_WAIT_SECONDS`, padrão 60, limitada pelo orçamento — AC-17/AC-18)
- **Então** o Hub publica (`threads_publish` com `creation_id`), lê o `permalink` (melhor esforço) e o alvo fica `published` com `external_post_id` e link; `PUBLISHED` na consulta marca `published` sem republicar

### AC-13: Container de imagem com erro
- **Dado** um container de imagem
- **Quando** o status é `ERROR` ou `EXPIRED`
- **Então** o alvo fica `failed` com a mensagem "O Threads não conseguiu processar a imagem. Tente novamente.", **nada é publicado** (nem só o texto), o `external_container_id` é **descartado**, o valor de `error_message` da Meta (enum) vai ao log `threads_container_error code=…`, e o próximo envio cria container novo com **nova URL assinada**

### AC-14: Espera esgotada sem degradar
- **Dado** um container de imagem que continua `IN_PROGRESS`
- **Quando** o limite de espera termina
- **Então** o alvo fica `failed` (reenviável) com a mensagem de que o Threads ainda está processando a imagem, **nenhum** post de só texto é criado e o `external_container_id` é **mantido**

### AC-15: Retomada reutiliza o container
> **Atualizado pela [0007](../0007-publicacao-em-segundo-plano/spec.md):** a retomada pelo container gravado continua valendo para o "Tentar novamente"/"Reenviar"; um `sending` preso **não** é mais recuperado sozinho: vira **Incerto** (0007), em ambos os modos (`worker` e `inline`).
- **Dado** um alvo de imagem com `external_container_id` gravado (falha anterior mantida, ou `sending` preso ≥ 5 min)
- **Quando** ele é reenviado
- **Então** o container é **reutilizado** (nenhum novo `POST …/threads`, nenhuma nova URL gerada) e o fluxo segue na consulta de status

### AC-16: Sem imagem, o Threads segue como antes
- **Dado** uma publicação **sem** imagem com alvo do Threads
- **Quando** é enviada
- **Então** o container é `TEXT` (0004 AC-17), sem `image_url`, e a rota pública não é envolvida

### AC-17: Orçamento de tempo do envio
> **Atualizado pela [0007](../0007-publicacao-em-segundo-plano/spec.md):** o orçamento por requisição (40 s) vale só no modo `inline`; o **worker** não tem orçamento e usa a espera configurada (`THREADS_IMAGE_WAIT_SECONDS`).
- **Dado** uma requisição de envio com `PUBLISH_REQUEST_BUDGET_SECONDS` (padrão 150)
- **Quando** restam **menos de 40 s** do orçamento antes de iniciar um novo alvo
- **Então** esse alvo e os seguintes **não** são iniciados e permanecem `pending` ("Continuar envio"), é logado `publish_budget_exhausted remaining=N`, e os alvos já em curso terminam normalmente; o lote de `PUBLISH_BATCH_SIZE` continua sendo o teto

### AC-18: Espera limitada pelo restante do orçamento
> **Atualizado pela [0007](../0007-publicacao-em-segundo-plano/spec.md):** a espera limitada pelo restante do orçamento vale só no modo `inline`; o **worker** espera `THREADS_IMAGE_WAIT_SECONDS` inteiro.
- **Dado** um alvo de imagem iniciado com orçamento restante R
- **Quando** o Hub espera o container
- **Então** a espera é `min(THREADS_IMAGE_WAIT_SECONDS, R − 25 s)`; se o tempo acabar, vale o AC-14

### AC-19: Alvos mistos com imagem
- **Dado** uma publicação com imagem, Páginas do Facebook e perfis do Threads
- **Quando** é enviada
- **Então** o Facebook publica foto + texto como na 0003 (idêntico), o Threads publica imagem + texto, o resultado é por alvo (falha parcial permitida) e retentar reenvia só `pending`/`failed`; a mensagem de erro do Threads não afeta alvos do Facebook

### AC-20: Imagem de outra publicação não vaza
- **Dado** duas publicações A e B com imagem e alvos Threads em andamento
- **Quando** o token de A é usado para pedir a imagem de B (ou com `Host` forjado)
- **Então** só a imagem de A pode ser obtida com o token de A, e a URL gerada **não** muda com o `Host` da requisição

### AC-21: Atualização das specs 0003/0004
- **Dado** as specs 0004 (AC-14, AC-17, AC-21 e o non-goal de imagem) e 0003 (se citar)
- **Quando** esta feature é implementada
- **Então** essas specs são atualizadas para refletir "Threads envia imagem + texto quando há imagem", com nota de supersessão apontando para a 0005; os testes `test_AC_14_*`, `test_AC_17_*` e `test_AC_21_*` da 0004 são ajustados; todos os demais critérios das 0003/0004 continuam passando sem alteração

## Matrizes de decisão

### Formulário (destinos × imagem)
| Destinos                 | Imagem   | Proporção | Endereço público | Resultado                                       | AC            |
|--------------------------|----------|-----------|------------------|-------------------------------------------------|---------------|
| só Facebook              | ausente  | —         | —                | Erro: imagem obrigatória                        | AC-1          |
| só Facebook              | válida   | —         | não exigido      | Cria como na 0003                               | AC-1          |
| só Threads               | ausente  | —         | não exigido      | Cria sem imagem (texto)                         | AC-1, AC-16   |
| só Threads               | inválida | —         | —                | Erro da imagem; nada criado                     | AC-2          |
| só Threads               | válida   | ≤ 10      | configurado      | Cria **com** imagem                             | AC-1          |
| só Threads               | válida   | > 10      | configurado      | Erro de proporção; nada criado                  | AC-3          |
| só Threads               | válida   | ≤ 10      | ausente          | Erro de endereço público; nada criado           | AC-4          |
| Facebook + Threads       | válida   | ≤ 10      | configurado      | Cria; os dois tipos de alvo                     | AC-1, AC-19   |
| Facebook + Threads       | válida   | > 10      | —                | Erro de proporção; nada criado                  | AC-3          |
| Facebook + Threads       | válida   | ≤ 10      | ausente          | Erro de endereço público; nada criado           | AC-4          |
| Facebook + Threads       | ausente  | —         | —                | Erro: imagem obrigatória (há Página)            | AC-1          |

### Rota pública
| Token                         | Publicação tem imagem | Alvo Threads em andamento | Resposta | AC   |
|-------------------------------|-----------------------|---------------------------|----------|------|
| válido, fresco                | sim                   | sim (pending/sending/failed) | 200   | AC-6 |
| válido, fresco, `HEAD`        | sim                   | sim                       | 200 sem corpo | AC-6 |
| ausente / adulterado / chave errada | —               | —                         | 404      | AC-7 |
| expirado                      | sim                   | sim                       | 404      | AC-7 |
| de outra publicação           | sim                   | sim                       | 404 (ou a imagem de quem assinou) | AC-7, AC-20 |
| válido, fresco                | não                   | —                         | 404      | AC-8 |
| válido, fresco                | sim                   | não (todos `published`)   | 404      | AC-8 |
| válido, fresco                | sim                   | só alvos do Facebook      | 404      | AC-8 |
| qualquer, método ≠ GET/HEAD   | —                     | —                         | 405      | AC-9 |

### Container de imagem
| Situação do alvo                                  | Resultado                                                                 | AC    |
|---------------------------------------------------|---------------------------------------------------------------------------|-------|
| sem `external_container_id`, com imagem           | Gera URL, cria `IMAGE`, grava o id, espera                                | AC-11 |
| com `external_container_id` (retomada)            | Reutiliza; não cria nem gera URL; espera                                  | AC-15 |
| `IN_PROGRESS` dentro da espera                    | Continua consultando (3 s)                                                | AC-12 |
| `FINISHED`                                        | Publica; permalink; `published`                                           | AC-12 |
| `PUBLISHED`                                       | `published` sem republicar                                                | AC-12 |
| `ERROR` / `EXPIRED`                               | `failed`; descarta id; log do enum; sem texto                             | AC-13 |
| espera esgotada                                   | `failed`; mantém id; sem texto                                            | AC-14 |
| espera = `min(config, restante − 25 s)`           | Limitada pelo orçamento                                                   | AC-18 |
| publicação sem imagem                             | `TEXT` como na 0004                                                       | AC-16 |

### Orçamento
| Restante ao iniciar um alvo | Resultado                                              | AC    |
|-----------------------------|--------------------------------------------------------|-------|
| ≥ 40 s                      | Inicia o alvo                                          | AC-17 |
| < 40 s                      | Não inicia; fica `pending`; log `publish_budget_exhausted` | AC-17 |

## Casos de borda e erros
- Meta não alcança a URL (túnel caiu, sem HTTPS, recusa o redirecionamento): o container vira `ERROR` ou não sai de `IN_PROGRESS` → AC-13/AC-14; o log do enum orienta o ajuste.
- Token da URL expira durante uma espera longa: o container já foi criado; o que importa é a Meta ter buscado antes; reenvio com `ERROR` gera nova URL (AC-13).
- A Meta busca a imagem mais de uma vez (HEAD + GET): permitido enquanto o alvo está em andamento (AC-6).
- Publicação `published` em todos os alvos do Threads: a URL deixa de funcionar mesmo antes de expirar (AC-8).
- Imagem enviada junto a alvo do Threads que já falhou por erro de token: segue AC-20 da 0004 (reconexão); a URL só vale com alvo em andamento.
- Publicações antigas (0004 só-Threads, sem imagem): continuam sem imagem e enviam `TEXT`.
- Erro de rede/limite da Meta no container de imagem: mensagens da 0004 AC-20 (sem texto cru da Meta).
- `ALLOWED_HOSTS` sem o host público: a Meta recebe 400 → AC-13/AC-14; o README documenta.

## Fora de escopo
> Vinculante. Não implemente nada aqui.
- Carrossel, vídeo, GIF, enquete e `alt_text` no Threads.
- Armazenamento externo (S3/R2), CDN e galeria pública de imagens.
- Fila/worker e agendamento (o orçamento de tempo é a mitigação desta etapa).
- Alterar o fluxo do Facebook ou publicar só texto no Facebook.
- Instagram.
- Token de uso único no banco; rate limit da rota pública.
- Confirmar no código o comportamento não documentado do buscador da Meta (fica para o UAT).

## Rastreabilidade
- Product: `./product.md`
- Design: `./design.md`
- Domínio: `./domain.md`
- ADRs relacionados: [ADR-0008](../../docs/architecture/adr/0008-url-publica-temporaria-assinada-para-imagem-do-threads.md), [ADR-0009](../../docs/architecture/adr/0009-orcamento-de-tempo-por-requisicao-de-publicacao.md), [ADR-0004](../../docs/architecture/adr/0004-publicacao-sincrona-em-lotes-idempotente.md), [ADR-0005](../../docs/architecture/adr/0005-imagens-sanitizadas-volume-dedicado-e-entrega-autenticada.md), [ADR-0007](../../docs/architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md)
