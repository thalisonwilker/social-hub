---
name: domain
description: Modelo de domínio da feature 0009 — conta Instagram vinculada à Página, alvo e container do Instagram. Puxe ao modelar ou implementar.
alwaysApply: false
---

# Domain Model — Instagram: conectar pela Página e publicar

## Bounded Context
**Social** (app `social`), o mesmo das 0002–0008. Subdomínio **core**. Nenhum contexto novo: o Instagram é mais uma plataforma de destino do agregado **Publicação**, tratada pelo despacho por plataforma (ADR-0007).

## Linguagem ubíqua
| Termo | Definição | NÃO confundir com |
|-------|-----------|-------------------|
| Conta Instagram | `SocialAccount` com `platform=instagram`: a conta profissional do Instagram (`external_id` = id da conta, `username` = @usuário) **vinculada a uma Página** conectada (`parent`). | Página do Facebook; perfil do Threads |
| Página vinculada | A Página do Facebook (conta pai) pela qual a Conta Instagram é alcançada; seu token é copiado (cifrado) para a Conta Instagram. | Página qualquer |
| Container (Instagram) | Objeto intermediário `POST /{ig_id}/media` com `image_url` e `caption`; tem `status_code` (IN_PROGRESS, FINISHED, ERROR, EXPIRED, PUBLISHED). | Container (Threads) |
| Legenda | O texto da publicação enviado ao Instagram (`caption`); até 2.200 caracteres e 30 hashtags. | Texto do Threads |
| Imagem do Instagram | A imagem da publicação entregue ao Instagram em **JPEG**, numa URL pública temporária; PNG é convertido só nessa entrega. | Imagem armazenada (a original sanitizada) |

> Termos novos a promover ao `docs/glossary.md`: Conta Instagram, Página vinculada, Container (Instagram), Imagem do Instagram. "Alvo em andamento" passa a valer também para o Instagram.

## Agregados, entidades e value objects
- **Agregado `SocialAccount`** (existente) — ganha `platform=instagram` e `parent` (FK opcional para a Página vinculada, `CASCADE`).
  - **Invariantes:** a Conta Instagram tem `parent` = Página do mesmo dono; seu token é o da Página (cifrado, nunca em claro); `unique (owner, platform, external_id)` continua valendo; remover a Página remove a Conta Instagram.
- **Agregado `Publication`** (existente) — raiz; `PublicationTarget` com `platform=instagram` usa os mesmos campos (`external_container_id`, `external_post_id`, `permalink`, estados).
  - **Invariantes novas:** publicação com alvo Instagram **tem imagem**, com proporção entre 4:5 e 1.91:1, legenda ≤ 2.200 caracteres e ≤ 30 hashtags (validadas no formulário).
  - Fronteira de consistência: alvo ↔ container gravado antes da espera; `published` só após `media_publish`.

## Eventos de domínio
| Evento | Disparado quando | Quem reage |
|--------|------------------|------------|
| `InstagramAccountLinked` | Página salva com Instagram vinculado | Hub cria/atualiza a Conta Instagram |
| `InstagramContainerCreated` | `POST /{ig_id}/media` ok | grava `external_container_id` |
| `InstagramTargetPublished` | `media_publish` ok | alvo `published` + permalink |
| `InstagramTargetUncertain` | `media_publish` sem resposta | alvo `uncertain` (usuário resolve) |

## Relações com outros contextos
**Anti-Corruption Layer** existente (`services/meta.py`, `GraphClient`): ganha métodos do Instagram sem expor a Graph API ao domínio. Nenhuma mudança no context-map além de listar a plataforma Instagram no contexto Social.
