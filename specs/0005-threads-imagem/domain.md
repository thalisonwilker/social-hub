---
name: domain
description: Modelo DDD da feature 0005 — imagem no Threads via URL pública assinada e orçamento de tempo do envio.
alwaysApply: false
---

# Domain Model (DDD) — Threads: publicar imagem junto com o texto

> Evolui `Publication`/`PublicationTarget` (0003/0004) no contexto **Social (integrações)**, subdomínio **core**.

## Bounded Context
**Social (integrações)** (`apps.social`). Nenhum contexto novo; entra uma **superfície pública mínima** (rota de leitura para a Meta) e uma política de tempo no envio.

## Linguagem ubíqua

| Termo                  | Definição                                                                                         | NÃO confundir com                         |
|------------------------|---------------------------------------------------------------------------------------------------|-------------------------------------------|
| URL pública assinada   | URL temporária, com token assinado, que permite à Meta baixar **uma** imagem sem login.            | Rota autenticada de imagem (do dono)      |
| Token da imagem        | Valor assinado (HMAC + carimbo de tempo) que identifica a publicação e expira.                     | Token de acesso do Threads/Página         |
| Endereço público       | Base HTTPS pela qual a Meta alcança o Hub (`PUBLIC_BASE_URL` ou origem do redirect).               | `Host` da requisição                      |
| Container de imagem    | Container do Threads criado com `media_type=IMAGE` e `image_url`.                                  | Container de texto                        |
| Orçamento da requisição| Tempo máximo que uma requisição de envio pode gastar antes de deixar o restante para "Continuar envio". | Lote (limite de quantidade)          |
| Alvo em andamento      | Alvo do Threads em `pending`, `sending` ou `failed` (reenviável): ainda pode precisar da imagem.   | Alvo publicado                            |

## Agregados, entidades e value objects
- **Agregado `Publication`** (evolução da 0003/0004; raiz: `Publication`)
  - Novos value objects: `PublicImageToken` (id da publicação + instante, assinado), `PublicBaseUrl` (HTTPS, nunca derivado do `Host`), `ImageDimensions` (largura, altura).
  - **Invariantes alteradas/novas:**
    1. O alvo do Threads envia a imagem **se e somente se** a publicação tem imagem (antes: nunca enviava). O Facebook segue com upload direto.
    2. Com Threads entre os destinos e imagem presente, a **proporção** (maior/menor lado) é **≤ 10** e há **endereço público HTTPS** configurado; caso contrário a publicação **não é criada**.
    3. A URL pública só **resolve** a imagem se: (a) assinatura válida e dentro da validade (30 min), (b) a publicação tem imagem, (c) existe alvo do Threads **em andamento**.
    4. A URL é montada **sempre** do endereço público configurado, nunca do `Host`.
    5. Container de imagem que não fica pronto → o alvo **falha** (reenviável) e **nunca** publica só o texto.
    6. Container `ERROR`/`EXPIRED` → o id é descartado; o próximo envio cria outro container com **nova URL**.
    7. Uma requisição de envio **não inicia** novo alvo com menos de 40 s de orçamento restante; os alvos não iniciados continuam `pending`.
  - Invariantes de idempotência (claim, `published` imutável, snapshot, status derivado) valem para todas as plataformas e **não mudam**.
  - Fronteira de consistência: igual à 0004; o orçamento de tempo é política do **serviço de envio**, não do agregado.

## Eventos de domínio
> Eventos **lógicos** em log (`apps.social.meta`); sem barramento. **Nenhum log traz o token, a URL assinada ou o texto.**

| Evento (passado)            | Disparado quando                                              | Quem reage                       |
|-----------------------------|---------------------------------------------------------------|----------------------------------|
| `UrlPublicaEmitida`         | O envio ao Threads monta a URL assinada para o container      | log                              |
| `ImagemPublicaServida`      | A Meta busca a imagem com token válido                        | log (`public_image_served`)      |
| `ImagemPublicaRecusada`     | Token expirado/inválido, sem imagem ou sem alvo em andamento  | log (`public_image_rejected`)    |
| `ContainerImagemCriado`     | Container `IMAGE` criado e gravado no alvo                    | log                              |
| `OrcamentoEsgotado`         | A requisição não inicia mais alvos por falta de tempo         | tela ("Continuar envio")         |
| `AlvoPublicado` / `AlvoFalhou` | Resultado do envio (já existentes)                         | histórico, log                   |

## Relações com outros contextos
- **Buscador de mídia da Meta → Social:** **Open Host Service** mínimo e somente leitura (`GET/HEAD /publico/imagem.*`), protegido por token assinado de validade curta; é a única rota anônima de mídia.
- **Social → Threads (Graph API):** **Anti-Corruption Layer** (`ThreadsClient`), agora com o container de imagem.
- **Publicação → Conta social, Social → Identidade, Social → Painel:** sem mudança.
