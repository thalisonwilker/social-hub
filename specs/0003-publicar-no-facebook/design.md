---
name: design
description: Technical Design Doc da feature 0003 — publicar texto + imagem em várias Páginas do Facebook (envio síncrono em lotes, idempotente, imagem sanitizada).
alwaysApply: false
---

# Technical Design Doc — Publicar no Facebook (texto + imagem, várias Páginas)

> **Tier:** arquitetural · **Status:** aprovado
> **Autor:** Thalyson · **Revisores:** — · **Data:** 2026-11-17
> Responde: **como** no nível de sistema. O porquê está em [`product.md`](./product.md).

## Links e artefatos

| Artefato                 | Onde        | Link                                         |
|--------------------------|-------------|----------------------------------------------|
| Página do design         | —           | (sem Confluence/Notion conectado)            |
| Issue / épico            | —           | (sem Jira/Linear conectado)                  |
| Spec · Product · Domínio | repositório | `./spec.md` · `./product.md` · `./domain.md` |
| Feature base             | repositório | [`0002-facebook-page-connect`](../0002-facebook-page-connect/spec.md) |

## Contexto da funcionalidade
A 0002 entregou `SocialAccount` (Página conectada, token cifrado, status `active`/`needs_reauth`), o `GraphClient`
(`requests`, v27.0, erros sanitizados) e a regra de segredos (nada em URL/log/HTML). Esta feature é a primeira que
**escreve** na Meta. Restrições do ambiente: Gunicorn síncrono com **timeout padrão de 30 s**, SQLite, sem fila/worker,
sem armazenamento de mídia. O app Meta está em modo Desenvolvimento, com `pages_manage_posts` liberada.

## Goals / Non-goals
**Goals**
- Publicar **1 imagem + texto** em **N Páginas** com resultado individual e retry só das falhas, sem duplicar posts.
- Receber, validar e **sanitizar** a imagem; guardá-la em volume persistente e enviá-la à Meta por **upload multipart**.
- Histórico de publicações com status por Página; imagens servidas **só a usuários autenticados donos**.
- Nenhuma requisição ultrapassar o timeout do Gunicorn, mesmo com muitas Páginas.

**Non-goals**
- Agendamento, fila/worker, rascunhos, editar/excluir post na Meta, várias imagens, vídeo, só texto, Instagram/Threads, insights.

## Glossário (da funcionalidade)

| Termo               | Descrição                                                                                         |
|---------------------|---------------------------------------------------------------------------------------------------|
| Publicação          | Conteúdo (texto + imagem) criado pelo usuário para ser publicado em uma ou mais Páginas.           |
| Alvo da publicação  | Par (Publicação, Página): carrega o estado e o resultado do envio àquela Página.                   |
| Lote                | Conjunto de alvos enviados numa única requisição (máx. `PUBLISH_BATCH_SIZE`, padrão 5).            |
| Reivindicar (claim) | Marcar atomicamente um alvo como `sending` para garantir que só uma requisição o envia.            |
| Post na Meta        | O post criado no Facebook; identificado por `post_id` (`{page_id}_{post}`) e link permanente.      |

## Design proposto

### Fluxo

```mermaid
sequenceDiagram
    actor U as Usuário
    participant H as Social Hub (Django)
    participant D as SQLite + volume /media
    participant M as Meta Graph API
    U->>H: POST /publicacoes/nova/ (texto, imagem, Páginas) + CSRF
    H->>H: valida form; sanitiza imagem (Pillow, re-encode)
    H->>D: salva Publication + imagem + 1 Target "pending" por Página
    loop até 5 alvos pendentes (lote)
        H->>D: claim atômico (pending/failed → sending)
        H->>M: POST /{page_id}/photos (multipart: source, message) Bearer token da Página
        alt sucesso
            H->>D: published + post_id + link
        else erro de token (190/102)
            H->>D: failed + conta needs_reauth
        else outro erro / timeout
            H->>D: failed + motivo amigável
        end
    end
    H-->>U: 302 /publicacoes/{id}/ com resultado por Página
    U->>H: POST /publicacoes/{id}/enviar/ (continuar / tentar de novo)
    H->>D: reivindica só pending/failed e repete o ciclo
```

- **Idempotência:** o envio só ocorre se o alvo for **reivindicado** com `UPDATE … WHERE status IN (pending, failed)
  OR (status=sending AND last_attempt_at < agora−5 min)`; `rowcount == 1` autoriza. Alvo `published` **nunca** é reenviado.
  Duplo clique ou duas abas não geram post duplicado. `sending` preso por queda do processo é recuperado após 5 min.
- **Lotes:** cada requisição processa no máximo `PUBLISH_BATCH_SIZE` alvos (padrão 5). Restantes ficam `pending` e o usuário
  usa **"Continuar envio"**. Com `META_UPLOAD_TIMEOUT=30 s` por chamada, o pior caso é 5×30 = 150 s; o Gunicorn passa a
  rodar com `--timeout 180`.
- **Falha parcial** é normal: cada alvo carrega o seu estado; a publicação nunca é "desfeita".
- A imagem **não** é exposta por URL pública: o arquivo vai à Meta por multipart e é servido ao usuário por uma view
  autenticada (`/publicacoes/{id}/imagem/`).
- Antes de enviar, a tela pede confirmação (`data-confirm`): "Será publicado de verdade nas Páginas selecionadas."

### Rotas (app `social`)

| Rota                              | Método | Nome                  | Função                                                              |
|-----------------------------------|--------|-----------------------|---------------------------------------------------------------------|
| `/publicacoes/`                   | GET    | `social:posts`        | Histórico (substitui o placeholder)                                 |
| `/publicacoes/nova/`              | GET, POST | `social:post_new`  | Formulário; no POST cria e envia o 1º lote                          |
| `/publicacoes/<id>/`              | GET    | `social:post_detail`  | Resultado por Página                                                |
| `/publicacoes/<id>/enviar/`       | POST   | `social:post_send`    | Continuar envio / tentar de novo as que falharam                    |
| `/publicacoes/<id>/imagem/`       | GET    | `social:post_image`   | Serve a imagem ao dono (404 para outros)                            |

Todas exigem login e filtram por `owner=request.user`.

### Modelo de dados (`apps/social/models.py`)

`Publication`
| Campo        | Tipo                 | Notas                                                         |
|--------------|----------------------|---------------------------------------------------------------|
| `owner`      | FK → User            | `CASCADE`                                                     |
| `text`       | TextField            | Legenda, 1–5000 caracteres                                    |
| `image`      | FileField            | `upload_to="publications/%Y/%m/"`, nome aleatório (uuid)      |
| `image_content_type` | CharField    | `image/jpeg` ou `image/png` (após sanitização)                |
| `created_at` | DateTime             |                                                               |

`PublicationTarget`
| Campo              | Tipo                 | Notas                                                                 |
|--------------------|----------------------|-----------------------------------------------------------------------|
| `publication`      | FK → Publication     | `CASCADE`                                                             |
| `account`          | FK → SocialAccount   | `SET_NULL`, nulo se a conta for desconectada                          |
| `page_external_id`, `page_name` | CharField | **Snapshot** para o histórico sobreviver à desconexão            |
| `status`           | CharField            | `pending` · `sending` · `published` · `failed`                        |
| `external_post_id` | CharField (opcional) | `post_id` devolvido pela Meta                                         |
| `permalink`        | URLField (opcional)  | Link do post                                                          |
| `error_message`    | CharField (opcional) | Motivo **amigável**; nunca o texto cru da Meta                        |
| `error_code`       | CharField (opcional) | Código da Meta (diagnóstico)                                          |
| `attempts`, `last_attempt_at`, `published_at` | — | Auditoria e recuperação de `sending` preso            |

Restrição única: (`publication`, `page_external_id`). Status geral da publicação é **derivado** dos alvos
(Publicada · Com falhas · Pendente), sem coluna própria (evita inconsistência).

### Componentes

```
apps/social/
  images.py                 sanitize_image(upload) → (ContentFile, content_type); validações
  forms.py                  PublicationForm (texto, imagem, Páginas ativas do usuário)
  models.py                 + Publication, PublicationTarget
  services/meta.py          + GraphClient.publish_photo(page_id, page_token, image, message)
  services/publishing.py    create_publication(), send_pending(), claim, mapeamento de erros
  views.py                  PostsView, PostNewView, PostDetailView, PostSendView, PostImageView
templates/social/posts.html · post_form.html · post_detail.html
```

### Chamada à Graph API
`POST https://graph.facebook.com/v27.0/{page_id}/photos` com `Authorization: Bearer <token da Página>`, corpo multipart:
`source` (arquivo), `message` (legenda), `published=true`. Resposta esperada: `{"id": "<photo_id>", "post_id": "<page_id>_<post>"}`.
Link: `https://www.facebook.com/{post_id}` (a validar no UAT — Questões em aberto). `GraphClient._request` ganha o parâmetro
`files` e um `timeout` por chamada (`META_UPLOAD_TIMEOUT`).

### Mapeamento de erros (alvo → mensagem amigável)

| Situação (código Meta)                   | Efeito no alvo                                  | Mensagem                                            |
|------------------------------------------|-------------------------------------------------|-----------------------------------------------------|
| 190 / 102 (token)                        | `failed`; conta → `needs_reauth`                | "Reconexão necessária para esta Página."            |
| 10 / 200 / 220 (permissão)               | `failed`                                        | "Sem permissão para publicar nesta Página."         |
| 4 / 17 / 32 / 613 (limite)               | `failed` (pode tentar de novo)                  | "Limite de requisições da Meta. Tente mais tarde."  |
| 368 (bloqueio por política/spam)         | `failed`                                        | "A Meta bloqueou esta publicação."                  |
| rede / timeout / resposta inválida       | `failed` (pode tentar de novo)                  | "Falha de comunicação com a Meta."                  |
| conta desconectada (`account` nulo)      | `failed`, **não** reenviável                    | "Conta desconectada."                               |
| demais                                   | `failed`                                        | "A Meta recusou a publicação (código N)."           |

### Configuração

| Variável / setting              | Padrão          | Descrição                                                         |
|---------------------------------|-----------------|-------------------------------------------------------------------|
| `MEDIA_ROOT`                    | `/media`        | Volume persistente das imagens (`BASE_DIR/media` em dev)          |
| `PUBLISH_BATCH_SIZE`            | `5`             | Alvos por requisição                                              |
| `PUBLICATION_MAX_IMAGE_BYTES`   | `8 MiB`         | Tamanho máximo do upload                                          |
| `PUBLICATION_MAX_IMAGE_PIXELS`  | `40_000_000`    | Limite de pixels (proteção contra *decompression bomb*)           |
| `META_UPLOAD_TIMEOUT`           | `30` s          | Timeout por upload à Meta                                         |
| Gunicorn `--timeout`            | `180`           | Em `GUNICORN_CMD_ARGS` no compose                                 |

## Cobertura dos 5 eixos

### 1. Tech stack
Nova dependência: **Pillow** (validação real do formato e re-encode). Sem fila, sem S3, sem JS framework (a seleção de
Páginas e a confirmação usam o JS puro existente).

### 2. Arquitetura base
Mesmo contexto **Social**. Novo agregado `Publication` (raiz) com `PublicationTarget`. `publishing.py` orquestra e usa o
`GraphClient` (ACL) e o modelo; as views ficam finas. A regra de segredos da 0002 vale: o token da Página é descriptografado
só na hora da chamada.

### 3. Infra
**Novo volume** `media_data:/media` no compose (e `chown` no Dockerfile para o usuário `app`). Gunicorn com `--timeout 180`.
**Reversão segura:** a feature é aditiva (novas tabelas e rotas); reverter o código mantém as tabelas sem efeito; o volume
pode ser removido sem afetar o resto. A rota `social:posts` volta ao placeholder se o template for revertido.

### 4. Qualidade
- Graph API mockada (como na 0002); um teste por AC; cada linha das matrizes da spec vira um caso.
- **Imagem:** arquivos válidos, formato falso (extensão `.jpg` com conteúdo não-imagem), grande demais, pixels demais, EXIF removido.
- **Concorrência/idempotência:** dois `send` simultâneos não duplicam; `published` não reenvia; `sending` antigo é recuperado.
- **Segurança:** isolamento entre usuários (404), imagem só ao dono, segredos fora de HTML/logs/URLs (regressão da 0002).

### 5. Observabilidade
Logger `apps.social.meta`: `publication_created targets=N`, `publish_ok page=<id>`, `publish_failed page=<id> code=<c>`,
`publish_batch size=N ok=X failed=Y`, `target_reclaimed` (sending preso). Sem tokens, sem texto da publicação, sem corpo
de resposta. Prova de funcionamento: razão ok/falhas por lote e ausência de `sending` antigo.

## Mapa de dependências

| Dependência              | Tipo        | Descrição                              | Endpoints / métodos                                   |
|--------------------------|-------------|----------------------------------------|-------------------------------------------------------|
| Graph API                | REST        | Publicar foto com legenda na Página    | `POST /{page-id}/photos` (multipart)                  |
| `SocialAccount` (0002)   | modelo      | Página, token cifrado, status          | `get_token()`, `status`                               |
| `GraphClient` (0002)     | serviço     | Cliente HTTP e erros sanitizados       | `publish_photo()` (novo)                              |
| Pillow                   | biblioteca  | Validação e re-encode de imagem        | `Image.open`, `verify`, `save`                        |
| Sistema de arquivos      | volume      | Armazena imagens                       | `/media/publications/…`                               |

## Solução

| #  | Bloco                                  | Descrição                                                                  | Status     |
|----|----------------------------------------|----------------------------------------------------------------------------|------------|
| 1  | Settings, volume, Gunicorn timeout     | `MEDIA_ROOT`, limites, compose, Dockerfile, `.env.example`                 | definido   |
| 2  | `images.py`                            | Validação, limites, re-encode sem EXIF, nome aleatório                     | definido   |
| 3  | Modelos + migration                    | `Publication`, `PublicationTarget`, unicidade, status derivado             | definido   |
| 4  | `GraphClient.publish_photo`            | Multipart, timeout próprio, parse de `id`/`post_id`                        | definido   |
| 5  | `publishing.py`                        | Criar publicação, claim atômico, lote, mapeamento de erros                 | definido   |
| 6  | Form e views de criação/detalhe/envio  | Validações, confirmação, retry                                             | definido   |
| 7  | Histórico e imagem protegida           | Lista, miniatura via view autenticada                                      | definido   |
| 8  | Formato do link do post                | `facebook.com/{post_id}` vs `permalink_url`                                | indefinido |

## Alternativas consideradas

| Alternativa                                              | Prós                                              | Contras                                                    | Decisão |
|----------------------------------------------------------|---------------------------------------------------|------------------------------------------------------------|---------|
| **A. Envio síncrono em lotes de 5 + "Continuar envio"**  | Sem infra nova; timeout limitado; retry simples   | Usuário espera; muitas Páginas exigem mais de um clique    | **Escolhida** |
| B. Fila/worker (Celery/RQ)                               | Robusto, sem espera                               | Redis/worker no Docker; desproporcional agora              | Futuro (com agendamento) |
| C. Enviar tudo numa requisição só                        | Simples                                           | Estoura timeout com muitas Páginas                         | Não     |
| **D. Upload multipart à Meta**                           | Sem URL pública; imagem permanece privada         | Cada Página re-envia o arquivo                             | **Escolhida** |
| E. Imagem por URL pública (`url=`)                       | Menos tráfego                                     | Exige expor mídia publicamente e domínio HTTPS             | Não     |
| **F. Sanitizar com Pillow (re-encode, sem EXIF)**        | Remove GPS/metadados; rejeita arquivo falso       | Pequena perda/mudança no arquivo; dependência              | **Escolhida** |
| G. Guardar o arquivo como veio                           | Fiel ao original                                  | Vaza EXIF; aceita conteúdo não validado                    | Não     |
| **H. Servir imagem por view autenticada**                | Privacidade; sem `MEDIA_URL` público              | Passa pelo Django (ok neste volume)                        | **Escolhida** |
| I. `MEDIA_URL` público via proxy                         | Rápido                                            | Imagens acessíveis sem login                               | Não     |
| **J. Claim atômico por alvo (idempotência)**             | Sem duplicar com cliques/abas duplicados          | Estado `sending` precisa de recuperação                    | **Escolhida** |

## Trade-offs e consequências
- **Ganhamos:** publicar em várias Páginas sem infra nova, imagens privadas e limpas, sem duplicidade.
- **Aceitamos:** espera síncrona; lotes de 5 com clique extra; o upload se repete por Página; histórico depende do volume `/media`.
- **Dívida assumida:** janela residual de post duplicado (issue #1); sem pré-checagem de permissão (a Meta recusa e mostramos o motivo); sem fila (agendamento exigirá uma); sem exclusão/edição do post na Meta; sem limpeza automática de imagens antigas.

## Riscos

| Risco                          | Descrição                                                         | Prob. × Impacto | Ações / mitigações                                                               |
|--------------------------------|-------------------------------------------------------------------|-----------------|----------------------------------------------------------------------------------|
| Timeout do Gunicorn            | Lote lento derruba o worker no meio do envio                      | média × alta    | `--timeout 180`, lote de 5, timeout por chamada, `sending` recuperável           |
| Post duplicado                 | Reenvio, duplo clique, queda após a Meta publicar e antes de gravar | duplo clique: baixa × alta; queda: baixa × média | Claim atômico e `published` imutável cobrem cliques; a janela de queda é aceita e rastreada na issue #1 |
| Publicar em Página errada      | Teste em Página real                                              | baixa × alta    | Confirmação explícita; README recomenda Páginas de teste                         |
| Arquivo malicioso/enorme       | Polyglot, bomba de descompressão                                  | baixa × alta    | Pillow `verify` + re-encode, limites de bytes e pixels, nome aleatório           |
| Token caiu no envio            | Falha parcial                                                     | média × média   | Por alvo; conta → `needs_reauth`; retry após reconectar                          |
| Perda do volume de mídia       | Histórico perde miniaturas                                        | baixa × média   | Documentar backup de `/media`; posts na Meta não são afetados                    |
| Comportamento real de `/photos`| Resposta/permalink diferem do previsto                            | média × baixa   | UAT com Página de teste; erros tratados de forma genérica                        |

## Roadmap da feature

| Fase / onda | Entrega                                                  | Quando       | Depende de |
|-------------|----------------------------------------------------------|--------------|------------|
| 1 (MVP)     | Publicar texto + 1 imagem em N Páginas, retry, histórico | esta feature | 0002       |
| 2           | Agendamento (exige fila/worker)                          | próxima      | 1          |
| 3           | Mais de uma imagem, vídeo, só texto; Instagram/Threads   | depois       | 1          |

## Questões em aberto
- [ ] **Link do post:** confirmar no UAT se `https://www.facebook.com/{post_id}` abre o post; senão, consultar `permalink_url` na Meta.
- [x] **Janela residual de duplicidade** (decidido em 2026-11-17): **mantemos a opção simples**. Se o processo cair após a Meta publicar e
      antes de gravar `published`, o alvo ficará `sending` e será reenviado após 5 min (possível post duplicado). Tratamento melhor
      fica na issue [#1](https://github.com/thalisonwilker/social-hub/issues/1).
- [x] **Permissão de publicar** (decidido em 2026-11-17): **sem pré-checagem**. Toda conta `active` aparece no formulário; se a Meta
      recusar por falta de permissão, o alvo falha com "Sem permissão para publicar nesta Página." (ver mapeamento de erros).

> Decisões difíceis de reverter → ADRs ao aprovar este design:
> **ADR-0004** Publicação síncrona em lotes, idempotente por claim atômico ·
> **ADR-0005** Imagens: sanitização com Pillow, volume dedicado e entrega por view autenticada.
