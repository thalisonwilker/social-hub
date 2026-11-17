---
name: domain
description: Modelo DDD da feature 0004 — perfil do Threads com token que expira e publicação em alvos mistos.
alwaysApply: false
---

# Domain Model (DDD) — Threads: conectar perfil e publicar texto

> Evolui os agregados `SocialAccount` (0002) e `Publication` (0003) no contexto **Social (integrações)**, subdomínio **core**.

## Bounded Context
**Social (integrações)** (`apps.social`). O Threads entra como nova **plataforma** de `SocialAccount` e como novo tipo de destino
de `PublicationTarget`. Nenhum contexto novo é criado.

## Linguagem ubíqua

| Termo                  | Definição                                                                                   | NÃO confundir com              |
|------------------------|---------------------------------------------------------------------------------------------|--------------------------------|
| Perfil do Threads      | Conta do Threads conectada; é uma Conta social com plataforma `threads`.                     | Página do Facebook             |
| Token de longa duração | Token do Threads válido por 60 dias, renovável depois de 24 h de vida.                       | Token de Página (não expira)   |
| Renovar                | Trocar o token vigente por um novo de 60 dias, sem o usuário fazer login.                    | Reconectar (exige login)       |
| Expiração do token     | Instante em que o token deixa de valer; passado esse instante a conta exige reconexão.       | Reconexão necessária (o estado)|
| Container (Threads)    | Objeto intermediário criado antes de publicar; tem status (IN_PROGRESS, FINISHED, ERROR, EXPIRED, PUBLISHED). | Publicação / Post |
| Peso do texto          | Medida usada para validar o limite de 500 do Threads (emoji conta por bytes UTF-8).         | Número de caracteres           |
| Alvo misto             | Publicação cujos destinos incluem Páginas do Facebook e perfis do Threads.                  | Publicação só do Facebook      |

## Agregados, entidades e value objects
- **Agregado `SocialAccount`** (evolução da 0002; raiz: `SocialAccount`)
  - Novos value objects: `TokenValidity` (`expires_at`, `refreshed_at`; nulo para Páginas), `Platform.THREADS`, `Username`.
  - **Novas invariantes:**
    1. Conta `threads` ativa **sempre** tem `token_expires_at` no futuro; passada a expiração, a conta é `needs_reauth`.
    2. O token só é renovado se faltar **menos que a janela** (30 dias) **e** tiver **≥ 24 h**; a renovação reinicia a validade em 60 dias.
    3. Renovar nunca troca o dono nem o `external_id` (ID do perfil).
    4. Páginas do Facebook não têm expiração de token (campos nulos).
  - Invariantes da 0002 continuam (token sempre cifrado e nunca exposto; só o dono acessa; unicidade por dono, plataforma e ID externo).
- **Agregado `Publication`** (evolução da 0003; raiz: `Publication`)
  - Novos value objects: `ContainerRef` (`external_container_id`), `TextWeight`.
  - **Invariantes alteradas/novas:**
    1. A **imagem é obrigatória se e somente se** há ao menos um alvo `facebook_page`; sem alvo do Facebook a publicação não tem imagem.
    2. Se há alvo `threads`: peso do texto **≤ 500** e **≤ 5** links únicos.
    3. Alvo `threads` **nunca** envia imagem.
    4. O `external_container_id` é gravado **antes** de publicar; um container já `PUBLISHED` nunca é publicado de novo.
    5. Invariantes de idempotência da 0003 (claim, `published` imutável, snapshot, status geral derivado) valem para **todas** as plataformas.
  - Fronteira de consistência: criação continua uma transação; cada alvo é independente no envio.

## Eventos de domínio
> Eventos **lógicos** em log (`apps.social.meta`); sem barramento.

| Evento (passado)              | Disparado quando                                              | Quem reage                              |
|-------------------------------|---------------------------------------------------------------|-----------------------------------------|
| `ConexaoThreadsIniciada`      | Usuário inicia o login do Threads                             | log                                     |
| `PerfilThreadsConectado`      | Callback válido salva/atualiza a conta                        | dashboard ("Conectado"), log            |
| `TokenThreadsRenovado`        | `th_refresh_token` bem-sucedido                               | log                                     |
| `TokenThreadsExpirou`         | Expiração passou (ou erro de token)                           | Conta → `needs_reauth`, tela de contas  |
| `ContainerThreadsCriado`      | Container de texto criado e gravado no alvo                   | log                                     |
| `ContainerThreadsPronto`      | Status do container chega a `FINISHED`                        | publicador                              |
| `AlvoPublicado` / `AlvoFalhou`| Resultado do envio (já existentes, agora também para Threads) | histórico, log                          |

## Relações com outros contextos
- **Social → Threads (Graph API do Threads):** **Anti-Corruption Layer** (`ThreadsClient`); o domínio não vê respostas cruas.
- **Publicação → Conta social:** dependência direta no mesmo contexto; o publicador pode mudar o status da conta (`needs_reauth`).
- **Social → Identidade:** **Conformist** (FK para `User`). **Social → Painel:** **Customer/Supplier** (conexão do Threads na dashboard).
