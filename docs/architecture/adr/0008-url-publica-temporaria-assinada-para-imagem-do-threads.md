---
name: ADR-0008
description: URL pública temporária e assinada, servida pelo Hub, para a Meta buscar a imagem do Threads (exceção ao ADR-0005).
alwaysApply: false
---

# ADR-0008: URL pública temporária e assinada para a imagem do Threads

- **Status:** aceito
- **Data:** 2026-11-17
- **Decisores:** Thalyson

## Contexto
A feature `0005-threads-imagem` publica imagem + texto no Threads. A Threads API **não aceita upload**: o container `IMAGE` recebe `image_url`, e a Meta
**busca a imagem numa URL pública**. O ADR-0005 definiu que as imagens são privadas, entregues só ao dono por uma rota autenticada, sem URL pública.
A documentação **não informa** se HTTPS é obrigatório, se redirecionamentos funcionam, o user-agent do buscador nem o tempo limite. O Gunicorn registra a
requisição completa no access log (`--access-logfile -`).

## Decisão
- O Hub passa a expor **uma única rota anônima** de mídia: `GET/HEAD /publico/imagem.<jpg|png>?t=<token>`, **exclusivamente** para a Meta buscar a imagem do Threads.
- **Token** assinado com `TimestampSigner` (HMAC com a `SECRET_KEY`) sobre o id da publicação, **validade curta** (`THREADS_IMAGE_URL_TTL_SECONDS`, 1800 s). Sem estado no banco; **não** é de uso único
  (a Meta pode buscar várias vezes).
- **Escopo mínimo:** só serve se (1) a assinatura é válida e não expirou, (2) a publicação tem imagem e (3) existe **alvo `threads` em andamento** (`pending`, `sending` ou `failed`); depois de publicado, a URL deixa de funcionar.
  Resposta direta (sem redirecionar), `Cache-Control: no-store`, `nosniff`, `noindex`, sem cookies; qualquer falha devolve **404** uniforme.
- A URL é **sempre montada** a partir de `PUBLIC_BASE_URL` (ou da origem do `THREADS_REDIRECT_URI`), **nunca** do cabeçalho `Host`.
- O token vai na **query** e o Gunicorn passa a registrar apenas o caminho (`%(U)s`), via `docker/gunicorn.conf.py`, para o token não ir ao log do Hub.
- O ADR-0005 **continua valendo** para o Facebook (upload) e para a visualização autenticada pelo dono; esta é uma exceção restrita ao Threads.
- Alternativas descartadas: **armazenamento externo** (S3/R2: dependência e custo), **token no caminho** (iria ao access log) e **token de uso único no banco** (a Meta pode buscar várias vezes).

## Consequências
- **+** Imagem no Threads sem infra nova e com exposição mínima e temporária.
- **+** Escopo e validade limitam o dano de uma URL vazada.
- **−** Uma rota anônima no Hub; o Hub precisa estar **alcançável pela Meta** (túnel em dev; domínio com TLS em produção).
- **−** Dependência de comportamentos não documentados do buscador da Meta; validar no UAT.
- **−** URL assinada vazada dá acesso à imagem até expirar (≤ 30 min) ou até a publicação concluir.

> **Nota (2026-11-18, [ADR-0013](0013-instagram-via-pagina-conta-vinculada-token-da-pagina-e-imagem-jpeg-publica.md)):** o Instagram usa o mesmo token assinado em uma rota irmã, `/publico/instagram.jpg`, sempre em JPEG e com escopo próprio (só com alvo **Instagram** em andamento). A rota do Threads continua exigindo alvo Threads.
