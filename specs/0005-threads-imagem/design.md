---
name: design
description: Technical Design Doc da feature 0005 — imagem + texto no Threads via URL pública temporária e assinada servida pelo Hub, com orçamento de tempo por requisição.
alwaysApply: false
---

# Technical Design Doc — Threads: publicar imagem junto com o texto

> **Tier:** arquitetural · **Status:** aprovado
> **Autor:** Thalyson · **Revisores:** — · **Data:** 2026-11-17
> Responde: **como** no nível de sistema. O porquê está em [`product.md`](./product.md).
> Requisitos da Threads API verificados na documentação oficial (posts/overview) em 2026-11-17; o que ela **não** informa está marcado.

## Links e artefatos

| Artefato                 | Onde                | Link                                                                  |
|--------------------------|---------------------|-----------------------------------------------------------------------|
| Docs Threads — posts     | Meta for Developers | https://developers.facebook.com/docs/threads/posts/                   |
| Spec · Product · Domínio | repositório         | `./spec.md` · `./product.md` · `./domain.md`                          |
| Features base            | repositório         | [0003](../0003-publicar-no-facebook/spec.md) · [0004](../0004-threads-conectar-e-publicar/spec.md) |
| ADRs base                | repositório         | [ADR-0004](../../docs/architecture/adr/0004-publicacao-sincrona-em-lotes-idempotente.md) · [ADR-0005](../../docs/architecture/adr/0005-imagens-sanitizadas-volume-dedicado-e-entrega-autenticada.md) · [ADR-0007](../../docs/architecture/adr/0007-publicacao-por-plataforma-despacho-por-alvo-e-formulario-misto.md) |

## Contexto da funcionalidade
A 0004 publica **texto** no Threads (container `TEXT` → espera o status → publica). A imagem é guardada, sanitizada e **privada** (ADR-0005), entregue só ao dono
por uma rota autenticada. A Threads API **não aceita upload**: o container `IMAGE` recebe `image_url` e a Meta **busca a imagem numa URL pública**.
Restrições herdadas: Gunicorn síncrono com `--timeout 180`, sem fila/worker, lotes de 5 alvos e claim atômico por alvo (ADR-0004).
Observação do UAT: o container de **texto** ficou `FINISHED` em ~220 ms; o de **imagem** deve levar mais (a documentação sugere ~30 s), o que pressiona o tempo da requisição.

## Goals / Non-goals
**Goals**
- Threads recebe **texto + imagem** sempre que a publicação tiver imagem; sem imagem, só texto.
- **URL pública temporária e assinada**, servida pelo Hub, com escopo mínimo e validade curta; **sem** depender do `Host` da requisição.
- Container `IMAGE` com espera própria, retomada pelo `external_container_id` e falha **explícita** e reenviável.
- **Orçamento de tempo por requisição** para que lotes com imagem nunca estourem o timeout do Gunicorn.
- Validação da proporção (10:1) e do endereço público já no formulário.

**Non-goals**
- Carrossel, vídeo, GIF, `alt_text`, S3/R2, mudança no Facebook, galeria pública, imagem no Instagram.

## Glossário (da funcionalidade)

| Termo                | Descrição                                                                                              |
|----------------------|--------------------------------------------------------------------------------------------------------|
| URL pública assinada | URL temporária, com token assinado, que permite à Meta baixar **uma** imagem sem login.                |
| Token da imagem      | Valor assinado (HMAC + carimbo de tempo) que identifica a publicação e expira.                         |
| Endereço público     | Base HTTPS pela qual a Meta alcança o Hub (`PUBLIC_BASE_URL`, ou a origem do `THREADS_REDIRECT_URI`).  |
| Orçamento da requisição | Tempo máximo que uma requisição de envio pode gastar antes de deixar o restante para "Continuar envio". |
| Container de imagem  | Container do Threads criado com `media_type=IMAGE` e `image_url`.                                      |

## Design proposto

### Fluxo (alvo do Threads com imagem)

```mermaid
sequenceDiagram
    participant H as Social Hub
    participant T as Threads API
    participant M as Buscador de mídia da Meta
    H->>H: alvo reivindicado; renova o token se devido
    H->>H: gera token assinado da publicação (validade curta) e monta a URL com o endereço público
    H->>T: POST /v1.0/{user}/threads (media_type=IMAGE, image_url, text)
    T-->>H: id do container (gravado no alvo)
    T->>M: baixa a imagem da URL pública
    M->>H: GET /publico/imagem.jpg?t=token
    H->>H: valida assinatura, validade e se há alvo do Threads em andamento
    H-->>M: 200 com a imagem sanitizada (sem cache, nosniff)
    loop até o limite de espera (dentro do orçamento)
        H->>T: GET /v1.0/{container}?fields=status,error_message
        T-->>H: IN_PROGRESS / FINISHED / ERROR / EXPIRED
    end
    H->>T: POST /v1.0/{user}/threads_publish (creation_id)
    H->>T: GET /v1.0/{media}?fields=permalink
```

- **Retomada:** com `external_container_id` já gravado, o envio seguinte **reutiliza** o container (sem nova URL). Em `ERROR`/`EXPIRED` o id é descartado e o próximo envio gera **nova URL assinada**.
- **Sem degradar:** se o container não fica pronto, o alvo **falha** (reenviável); nunca publica só o texto.

### URL pública assinada
`{endereço público}/publico/imagem.{jpg|png}?t=<token>`

- **Token:** `TimestampSigner(salt="threads-public-image", sep=".")` sobre o **id da publicação**; validade `THREADS_IMAGE_URL_TTL_SECONDS` (padrão **1800** s). Assinatura HMAC com a `SECRET_KEY`; imprevisível, sem estado no banco.
  Não é de uso único (a Meta pode buscar mais de uma vez), por isso a validade é curta.
- **Token na *query*, não no caminho:** o Gunicorn registra o caminho (`--access-logfile -`). Passamos a registrar só `%(U)s` (caminho **sem** query) com um `docker/gunicorn.conf.py`; assim o token não vai para o log do Hub.
- **Extensão** `.jpg`/`.png` conforme o tipo guardado (alguns buscadores usam a extensão); o `Content-Type` real vem do banco.
- **Rota** `GET/HEAD /publico/imagem.<ext>` com `@login_not_required` (a única rota anônima de mídia). Antes de servir, **todas** as condições:
  1. assinatura válida e **dentro da validade**;
  2. a publicação existe e **tem imagem**;
  3. a publicação tem **ao menos um alvo `threads` em `pending`, `sending` ou `failed`** (em andamento): depois de publicada, a URL deixa de funcionar mesmo antes de expirar.
- **Resposta:** arquivo sanitizado direto, **sem redirecionamento**; `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `X-Robots-Tag: noindex`, sem cookies de sessão. Falhas retornam **404** genérico (não revelam o motivo).
- **Endereço público:** `PUBLIC_BASE_URL` (HTTPS); se vazio, usa a **origem do `THREADS_REDIRECT_URI`** (que já é HTTPS e público para o login funcionar). A URL é **sempre** montada desse valor, **nunca** do `Host`.
  `ALLOWED_HOSTS` deve conter o host público (já é o caso do túnel e do domínio).

### Container de imagem e espera
- `ThreadsClient.create_image_container(user_id, token, text, image_url)` → `POST /v1.0/{user}/threads` com `media_type=IMAGE`, `image_url`, `text`, `access_token` no **corpo**. `is_carousel_item` fica omitido.
- Espera: consulta o status a cada **3 s** até `THREADS_IMAGE_WAIT_SECONDS` (padrão **60**) **limitado pelo tempo restante do orçamento**; `FINISHED` → publica; `ERROR`/`EXPIRED` → falha; `PUBLISHED` → sem republicar; estourou → falha reenviável.
- Erros de container de **imagem**: a documentação só lista valores de vídeo → mensagem genérica ("O Threads não conseguiu processar a imagem…") e o valor de `error_message` da Meta vai para o **log** (é um enum, sem segredo) para ajustarmos depois do UAT.
- `threads_publish` e o `permalink` seguem como no texto.

### Orçamento de tempo por requisição (complementa o ADR-0004)
O lote de 5 alvos com 30 s por upload (Facebook) e até 60 s de espera por imagem (Threads) **excede** o timeout de 180 s.
- `PUBLISH_REQUEST_BUDGET_SECONDS` (padrão **150**, menor que o `--timeout 180`).
- `send_pending` mede o tempo desde o início; **não inicia** um novo alvo se restarem **< 40 s**; o restante fica `pending` ("Continuar envio", já existente).
- A espera do container é `min(configurado, restante − 25 s)`.
- Efeito: o lote de 5 passa a ser um **teto**, e o tempo é o limite real; nenhum worker é morto no meio de um envio.

### Validação no formulário (`PublicationForm.clean`)
- Imagem: obrigatória só com Página do Facebook (como antes); **enviada com Threads marcado ⇒ também validada/sanitizada** (hoje era ignorada).
- **Proporção:** com Threads marcado e imagem presente, `max(l,a)/min(l,a)` **≤ 10** (conservador nos dois sentidos; a doc não diz a direção).
- **Endereço público:** com Threads marcado e imagem presente, se não houver endereço público HTTPS configurado ⇒ erro claro no formulário ("Para enviar imagem ao Threads, configure `PUBLIC_BASE_URL`…"). Nada é criado.
- Largura mínima (320) e dimensões máximas (4096) **não** bloqueiam: a Meta reescala.
- Texto: regras do Threads inalteradas (peso ≤ 500, ≤ 5 links); `text` continua obrigatório no Hub.
- O aviso "a imagem foi ignorada" (0004) **deixa de existir**; `image_ignored` é removido.

### Componentes

```
apps/social/
  public.py                  endereço público, assinatura/validação do token, build_public_image_url(publication)
  views_public.py            PublicImageView (anônima, escopo mínimo)
  images.py                  SanitizedImage + largura/altura; aspect_ratio_within(limit)
  services/threads.py        + create_image_container()
  services/threads_publish.py  publish(): TEXT ou IMAGE; espera por tipo e pelo orçamento
  services/publishing.py     orçamento de tempo em send_pending; mensagens de imagem
  forms.py                   regras da imagem no Threads
  conf.py                    public_base_url(), public_url_configured()
docker/gunicorn.conf.py      access_log_format sem query
templates/social/post_form.html  texto de ajuda atualizado
```

### Configuração

| Variável                          | Padrão                            | Descrição                                                              |
|-----------------------------------|-----------------------------------|------------------------------------------------------------------------|
| `PUBLIC_BASE_URL`                 | vazio (usa a origem do redirect)  | Base HTTPS pela qual a Meta alcança o Hub                              |
| `THREADS_IMAGE_URL_TTL_SECONDS`   | `1800`                            | Validade do token da URL pública                                       |
| `THREADS_IMAGE_WAIT_SECONDS`      | `60`                              | Espera máxima pelo container de imagem                                 |
| `PUBLISH_REQUEST_BUDGET_SECONDS`  | `150`                             | Orçamento de tempo de uma requisição de envio (< Gunicorn `--timeout`) |

## Cobertura dos 5 eixos

### 1. Tech stack
Sem dependências novas (`django.core.signing` já existe). Um arquivo de configuração do Gunicorn.

### 2. Arquitetura base
Mesmo contexto **Social**. A rota pública é a **única** exceção à regra "mídia só por view autenticada" (novo ADR), com escopo mínimo. O `ThreadsClient` ganha o container de imagem; o publicador do Threads
passa a escolher TEXT/IMAGE pela presença de imagem na publicação.

### 3. Infra
Nada de serviço novo. **Exige o Hub alcançável pela internet em HTTPS**: túnel em desenvolvimento, domínio com TLS em produção. O proxy/túnel deve permitir `GET`/`HEAD` anônimos em `/publico/imagem.*`.
Nova configuração do Gunicorn (formato de log). **Reversão:** remover o endereço público desabilita o envio de imagem ao Threads (o formulário avisa); a rota pode ser removida sem migração.

### 4. Qualidade
- Threads API e transporte HTTP mockados; um teste por AC; cada linha das matrizes vira um caso.
- **Rota pública:** token válido/expirado/adulterado/de outra `SECRET_KEY`; publicação sem imagem; sem alvo Threads em andamento; alvo já publicado; HEAD; cabeçalhos; 404 uniforme; ausência de cookie.
- **Orçamento:** relógio controlado (não inicia alvo com < 40 s; espera limitada pelo restante); regressão da 0003/0004.
- **Segurança:** o token/URL assinada nunca em HTML, mensagens nem logs; `Host` forjado não altera a URL gerada; imagem de outra publicação não acessível com o token de outra.

### 5. Observabilidade
Logger `apps.social.meta`: `public_image_served`, `public_image_rejected reason=expired|invalid|no_image|not_in_flight`, `threads_image_container_created`, `threads_container_ready wait_ms=…`,
`threads_container_error code=<enum da Meta>`, `publish_budget_exhausted remaining=N`. **Nunca** o token, a URL nem o texto.

## Mapa de dependências

| Dependência                | Tipo        | Descrição                                      | Endpoints / métodos                                                |
|----------------------------|-------------|------------------------------------------------|--------------------------------------------------------------------|
| Threads Graph API          | REST        | Container de imagem, status, publicar          | `POST /v1.0/{id}/threads` (`IMAGE`) · `GET /v1.0/{container}` · `POST …/threads_publish` |
| Buscador de mídia da Meta  | HTTP        | Baixa a imagem da URL pública                  | `GET`/`HEAD /publico/imagem.<ext>?t=…` (no Hub)                    |
| `django.core.signing`      | biblioteca  | Token assinado com validade                    | `TimestampSigner(sep=".")`                                         |
| Túnel / domínio HTTPS      | infra       | Torna o Hub alcançável pela Meta               | `PUBLIC_BASE_URL` ou origem do `THREADS_REDIRECT_URI`              |
| Publicação (0003/0004)     | serviço     | Claim, lotes, retry, container                 | + orçamento de tempo                                               |

## Solução

| #  | Bloco                                      | Descrição                                                                | Status     |
|----|--------------------------------------------|--------------------------------------------------------------------------|------------|
| 1  | Config + `public.py` + `conf`              | Endereço público, token assinado, validade                               | definido   |
| 2  | Rota pública                               | Escopo mínimo, cabeçalhos, logs sem token; `gunicorn.conf.py`            | definido   |
| 3  | `images.py` + formulário                   | Dimensões, proporção, endereço público, remoção do "imagem ignorada"     | definido   |
| 4  | `ThreadsClient.create_image_container`     | `IMAGE` com `image_url` no corpo                                         | definido   |
| 5  | Publicador do Threads (TEXT/IMAGE)         | Espera por tipo, retomada, mensagens de imagem, log do `error_message`   | definido   |
| 6  | Orçamento de tempo                         | `send_pending` com deadline; espera limitada pelo restante               | definido   |
| 7  | Atualização das specs 0004                 | AC-14, AC-17, AC-21 e non-goal de imagem                                 | definido   |
| 8  | HTTPS exigido / redirecionamentos / UA     | A doc não informa: confirmar no UAT                                      | indefinido |

## Alternativas consideradas

| Alternativa                                                   | Prós                                             | Contras                                                          | Decisão |
|---------------------------------------------------------------|--------------------------------------------------|------------------------------------------------------------------|---------|
| **A. URL assinada temporária servida pelo Hub**               | Sem infra nova; escopo mínimo; funciona com túnel | Rota anônima no Hub; exige Hub alcançável                        | **Escolhida** |
| B. Armazenamento externo (S3/R2)                              | Não expõe o Hub                                  | Dependência, credenciais, custo                                  | Futuro  |
| **C. Token na *query* + log do Gunicorn sem query**           | Token fora do log do Hub                         | Arquivo de config do Gunicorn                                    | **Escolhida** |
| D. Token no caminho                                           | URL "limpa"                                      | Vai para o access log do Gunicorn                                | Não     |
| **E. Token assinado sem estado (validade curta)**            | Sem tabela; simples                              | Não é de uso único; vazar vale até expirar                       | **Escolhida** |
| F. Token de uso único no banco                                | Menor janela de abuso                            | A Meta pode buscar várias vezes → quebra o envio; mais estado    | Não     |
| **G. Servir só com alvo Threads em andamento**                | Fecha a URL após publicar                        | Uma consulta a mais                                              | **Escolhida** |
| **H. Orçamento de tempo por requisição**                      | Nunca estoura o timeout; reaproveita "Continuar" | Lote deixa de ser garantia de 5                                  | **Escolhida** |
| I. Fila/worker para o envio                                   | Sem limite de tempo                              | Infra nova; é o caminho do agendamento                           | Futuro  |
| **J. Falha explícita sem degradar para texto**                | Previsível                                       | Usuário precisa reenviar                                         | **Escolhida** |
| **K. Endereço = `PUBLIC_BASE_URL` ou origem do redirect**     | Zero configuração extra em dev                   | Acopla com o redirect do Threads                                 | **Escolhida** |

## Trade-offs e consequências
- **Ganhamos:** imagem no Threads no mesmo clique, sem armazenamento externo, com exposição mínima e temporária.
- **Aceitamos:** uma rota anônima (escopo mínimo, validade 30 min); o Hub precisa estar alcançável pela Meta; o lote de 5 vira teto (o tempo manda); a janela de duplicidade (#1) segue como está.
- **Dívida:** sem fila (agendamento); sem `alt_text`; dependemos de comportamentos não documentados do buscador da Meta (HTTPS, redirecionamentos, UA, timeout).

## Riscos

| Risco                              | Descrição                                                         | Prob. × Impacto | Ações / mitigações                                                                  |
|------------------------------------|-------------------------------------------------------------------|-----------------|-------------------------------------------------------------------------------------|
| Exposição da imagem                | URL assinada vazada dá acesso à imagem                            | baixa × média   | Validade 30 min, escopo de 1 imagem, só com alvo em andamento, 404 uniforme, sem cache |
| Token em log                       | Access log do Gunicorn registra a requisição                      | alta × média    | Token na query + `access_log_format` com `%(U)s`; testes de log                      |
| Host header forjado                | URL montada com `Host` malicioso redirecionaria a Meta            | baixa × alta    | URL **sempre** de `PUBLIC_BASE_URL`/redirect; teste com `Host` forjado               |
| Hub inalcançável                   | Túnel caiu / sem TLS                                              | média × baixa   | Container falha reenviável; aviso claro; erro explícito no formulário sem endereço  |
| Comportamento do buscador da Meta  | HTTPS, redirecionamento, UA e timeout não documentados            | média × média   | Servir direto, sem redirecionar; validar no UAT; ajustar                             |
| Estouro de tempo                   | Espera por imagem × 5 alvos > timeout                             | média × alta    | Orçamento de 150 s, alvo só inicia com ≥ 40 s, espera limitada pelo restante         |
| Proporção "10:1" ambígua           | Direção não documentada                                           | média × baixa   | Validação conservadora nos dois sentidos; erro da Meta tratado                       |
| Erros de imagem não documentados   | Só há códigos de vídeo                                            | média × baixa   | Mensagem genérica + log do enum para ajustar após o UAT                              |
| Regressão em 0003/0004             | Mudança do formulário e do envio                                  | baixa × alta    | Suíte existente verde; atualizar só os critérios declarados                          |

## Roadmap da feature

| Fase / onda | Entrega                                                     | Quando       | Depende de |
|-------------|-------------------------------------------------------------|--------------|------------|
| 1 (MVP)     | Imagem + texto no Threads com URL assinada e orçamento      | esta feature | 0003, 0004 |
| 2           | Fila/worker (sem limite de tempo) e agendamento             | depois       | 1          |
| 3           | Carrossel, vídeo, `alt_text`; Instagram                     | depois       | 1          |

## Questões em aberto
- [ ] **UAT:** a Meta aceita buscar a imagem por esta URL (HTTPS do túnel, sem redirecionar, `HEAD`/`GET`)? Qual o user-agent e o tempo real do container de imagem?
- [ ] **Erros de imagem:** quais valores de `error_message` aparecem na prática (arquivo inacessível, formato, proporção)?
- [ ] **Proporção:** a Meta recusa 10:1 nos dois sentidos ou só em um?
- [ ] **`alt_text`:** não consta na documentação lida; ficará fora até confirmarmos na referência do endpoint.

> Decisões difíceis de reverter → ADRs ao aprovar este design:
> **ADR-0008** URL pública temporária e assinada para a Meta buscar a imagem (exceção ao ADR-0005) ·
> **ADR-0009** Orçamento de tempo por requisição de publicação (complementa o ADR-0004).
